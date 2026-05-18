from __future__ import annotations

from typing import Any

import numpy as np
from PySide6.QtCore import QObject, QPoint, QThread, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizeGrip,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.agent import AgentAssistant
from app.audio_capture import AudioCapture
from app.audio_devices import AudioDeviceInfo, list_input_devices
from app.config import AppConfig
from app.hotkeys import bind_window_hotkeys
from app.logger import AppLogger
from app.transcriber import MockTranscriber, RealTranscriber
from app.utils import now_text


STATUS_COLORS = {
    "未监听": "#9ca3af",
    "监听中": "#22c55e",
    "正在转写": "#facc15",
    "正在思考": "#38bdf8",
    "已生成回答": "#a78bfa",
    "错误": "#f87171",
}


class AgentWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, assistant: AgentAssistant, text: str = "", regenerate: bool = False) -> None:
        super().__init__()
        self.assistant = assistant
        self.text = text
        self.regenerate = regenerate

    def run(self) -> None:
        try:
            result = self.assistant.regenerate() if self.regenerate else self.assistant.handle_text(self.text)
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class TranscribeWorker(QObject):
    finished = Signal(str, float)
    failed = Signal(str, float)

    def __init__(self, transcriber, audio: np.ndarray, samplerate: int, level: float) -> None:
        super().__init__()
        self.transcriber = transcriber
        self.audio = audio
        self.samplerate = samplerate
        self.level = level

    def run(self) -> None:
        try:
            text = self.transcriber.transcribe(audio=self.audio, samplerate=self.samplerate)
            self.finished.emit(text, self.level)
        except Exception as exc:
            self.failed.emit(str(exc), self.level)


class MainWindow(QMainWindow):
    audio_chunk_signal = Signal(object, int)
    capture_error_signal = Signal(str)

    def __init__(self, config: AppConfig, assistant: AgentAssistant, logger: AppLogger) -> None:
        super().__init__()
        self.config = config
        self.assistant = assistant
        self.logger = logger
        self.devices: list[AudioDeviceInfo] = []
        self.is_listening = False
        self.is_collapsed = False
        self.drag_pos: QPoint | None = None
        self.worker_thread: QThread | None = None
        self.agent_worker: AgentWorker | None = None
        self.transcribe_thread: QThread | None = None
        self.transcribe_worker: TranscribeWorker | None = None
        self.transcriber = RealTranscriber(config, logger) if config.has_api_key else MockTranscriber()
        self.audio_capture = AudioCapture(self._on_audio_chunk, self._on_capture_error)
        self.audio_chunk_signal.connect(self._handle_audio_chunk)
        self.capture_error_signal.connect(self._show_error)

        flags = Qt.FramelessWindowHint | Qt.Tool
        if config.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(520, 420)
        self.resize(760, 680)
        self.setWindowOpacity(config.ui_opacity)

        self._build_ui()
        self._apply_style()
        self.shortcuts = bind_window_hotkeys(
            self,
            self.toggle_listening,
            self.clear_context,
            self.regenerate_answer,
            self.toggle_collapse,
        )
        self.refresh_devices()
        self._set_status("未监听")

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 14, 14, 14)

        self.panel = QFrame()
        self.panel.setObjectName("Panel")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.panel.setGraphicsEffect(shadow)
        outer.addWidget(self.panel)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(11, 11)
        self.title = QLabel("实时语音面试回答助手")
        self.title.setObjectName("Title")
        self.status_label = QLabel("未监听")
        self.status_label.setObjectName("StatusLabel")
        api_text = "API Key 已配置" if self.config.has_api_key else "未配置 API Key"
        self.model_label = QLabel(f"{self.config.model_name} · {api_text}")
        self.model_label.setObjectName("ModelLabel")
        self.min_btn = QPushButton("—")
        self.close_btn = QPushButton("×")
        self.collapse_btn = QPushButton("▾")
        for button in (self.min_btn, self.collapse_btn, self.close_btn):
            button.setObjectName("WindowButton")
            button.setFixedSize(30, 26)
        self.min_btn.clicked.connect(self.showMinimized)
        self.close_btn.clicked.connect(self.close)
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        header.addWidget(self.status_dot)
        header.addWidget(self.title)
        header.addWidget(self.status_label)
        header.addStretch(1)
        header.addWidget(self.model_label)
        header.addWidget(self.min_btn)
        header.addWidget(self.collapse_btn)
        header.addWidget(self.close_btn)
        layout.addLayout(header)

        self.body = QWidget()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        layout.addWidget(self.body)

        device_card = self._card()
        device_layout = QHBoxLayout(device_card)
        device_layout.setContentsMargins(14, 12, 14, 12)
        self.device_combo = QComboBox()
        self.refresh_btn = QPushButton("刷新设备")
        self.start_btn = QPushButton("开始监听")
        self.pause_btn = QPushButton("暂停监听")
        self.clear_btn = QPushButton("清空上下文")
        self.audio_level_label = QLabel("音量: --")
        self.audio_level_label.setObjectName("Hint")
        self.start_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.start_btn.clicked.connect(self.start_listening)
        self.pause_btn.clicked.connect(self.pause_listening)
        self.clear_btn.clicked.connect(self.clear_context)
        device_layout.addWidget(QLabel("输入设备"))
        device_layout.addWidget(self.device_combo, 1)
        device_layout.addWidget(self.refresh_btn)
        device_layout.addWidget(self.start_btn)
        device_layout.addWidget(self.pause_btn)
        device_layout.addWidget(self.clear_btn)
        device_layout.addWidget(self.audio_level_label)
        body_layout.addWidget(device_card)

        transcript_card = self._section("实时转写", "复制全部文字")
        self.copy_transcript_btn = transcript_card.findChild(QPushButton)
        if self.copy_transcript_btn:
            self.copy_transcript_btn.clicked.connect(lambda: self._copy(self.transcript_text.toPlainText()))
        self.transcript_text = QTextEdit()
        self.transcript_text.setReadOnly(True)
        self.transcript_text.setPlaceholderText("最近识别到的语音会显示在这里。Mock 模式下可用底部输入框测试。")
        transcript_card.layout().addWidget(self.transcript_text)
        body_layout.addWidget(transcript_card, 2)

        answer_card = self._section("AI 回答", "复制回答")
        answer_card.setObjectName("AnswerCard")
        self.copy_answer_btn = answer_card.findChild(QPushButton)
        if self.copy_answer_btn:
            self.copy_answer_btn.clicked.connect(lambda: self._copy(self.answer_text.toPlainText()))
        self.answer_text = QTextEdit()
        self.answer_text.setReadOnly(True)
        self.answer_text.setPlaceholderText("检测到完整问题后，会在这里生成 20 秒口头版、60 秒展开版和追问要点。")
        answer_card.layout().addWidget(self.answer_text)
        answer_actions = QHBoxLayout()
        self.regen_btn = QPushButton("重新生成")
        self.regen_btn.clicked.connect(self.regenerate_answer)
        answer_actions.addStretch(1)
        answer_actions.addWidget(self.regen_btn)
        answer_card.layout().addLayout(answer_actions)
        body_layout.addWidget(answer_card, 3)

        manual_card = self._card()
        manual_layout = QHBoxLayout(manual_card)
        manual_layout.setContentsMargins(14, 12, 14, 12)
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("手动输入面试官的问题，例如：介绍一下你做过的 Agent 项目")
        self.mock_btn = QPushButton("模拟识别")
        self.mock_btn.setObjectName("PrimaryButton")
        self.mock_btn.clicked.connect(self.submit_mock_text)
        self.manual_input.returnPressed.connect(self.submit_mock_text)
        manual_layout.addWidget(self.manual_input, 1)
        manual_layout.addWidget(self.mock_btn)
        body_layout.addWidget(manual_card)

        footer = QHBoxLayout()
        self.hint_label = QLabel("窗口内快捷键：Ctrl+Alt+S 开始/暂停 · Ctrl+Alt+C 清空 · Ctrl+Alt+R 重新生成 · Ctrl+Alt+M 折叠")
        self.hint_label.setObjectName("Hint")
        footer.addWidget(self.hint_label)
        footer.addStretch(1)
        footer.addWidget(QSizeGrip(self.panel))
        layout.addLayout(footer)

    def _card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        return card

    def _section(self, title: str, action: str) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        row = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("SectionTitle")
        button = QPushButton(action)
        button.setObjectName("GhostButton")
        row.addWidget(label)
        row.addStretch(1)
        row.addWidget(button)
        layout.addLayout(row)
        return card

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { color: #f9fafb; font-family: "Microsoft YaHei", "Segoe UI"; font-size: 14px; }
            #Panel { background: rgba(17, 24, 39, 238); border: 1px solid rgba(148, 163, 184, 45); border-radius: 18px; }
            #Title { font-size: 18px; font-weight: 700; }
            #StatusLabel { color: #d1d5db; padding-left: 10px; }
            #ModelLabel, #Hint { color: #9ca3af; font-size: 12px; }
            #Card { background: rgba(31, 41, 55, 224); border: 1px solid rgba(148, 163, 184, 36); border-radius: 14px; }
            #AnswerCard { background: rgba(44, 55, 78, 235); border: 1px solid rgba(167, 139, 250, 90); }
            #SectionTitle { font-size: 15px; font-weight: 700; color: #e5e7eb; }
            QPushButton { background: rgba(55, 65, 81, 230); border: 1px solid rgba(148, 163, 184, 55); border-radius: 9px; padding: 8px 12px; color: #f9fafb; }
            QPushButton:hover { background: rgba(75, 85, 99, 240); border-color: rgba(191, 219, 254, 130); }
            QPushButton:disabled { color: #9ca3af; background: rgba(31, 41, 55, 170); }
            #PrimaryButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #2563eb, stop:1 #7c3aed); border: 0; font-weight: 700; }
            #PrimaryButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #3b82f6, stop:1 #8b5cf6); }
            #GhostButton, #WindowButton { padding: 4px 8px; background: rgba(17, 24, 39, 140); }
            QComboBox, QLineEdit, QTextEdit { background: rgba(15, 23, 42, 210); border: 1px solid rgba(148, 163, 184, 55); border-radius: 10px; padding: 8px; selection-background-color: #4f46e5; }
            QComboBox QAbstractItemView { background: #111827; color: #f9fafb; border: 1px solid rgba(148, 163, 184, 90); selection-background-color: #4f46e5; selection-color: #ffffff; outline: 0; padding: 6px; }
            QTextEdit { font-size: 15px; line-height: 1.35; }
            QComboBox::drop-down { border: 0; width: 24px; }
            """
        )

    def refresh_devices(self) -> None:
        self.devices = list_input_devices()
        self.device_combo.clear()
        if not self.devices:
            self.device_combo.addItem("未发现输入设备", None)
            return
        for device in self.devices:
            self.device_combo.addItem(device.display_name, device)

    def start_listening(self) -> None:
        device = self.device_combo.currentData()
        if not isinstance(device, AudioDeviceInfo):
            self._show_error("没有可用输入设备。你仍然可以使用手动模拟输入测试。")
            return
        self.audio_capture.start(device.index, samplerate=device.samplerate, channels=min(1, device.channels))
        self.is_listening = self.audio_capture.is_running
        if self.is_listening:
            self._set_status("监听中")
            if isinstance(self.transcriber, MockTranscriber):
                self._append_transcript("系统：已开始录音，但当前没有可用 API Key；麦克风音量会显示，真实转写需要 DASHSCOPE_API_KEY。", highlight=False)

    def pause_listening(self) -> None:
        self.audio_capture.pause()
        self.is_listening = False
        self._set_status("未监听")

    def toggle_listening(self) -> None:
        self.pause_listening() if self.is_listening else self.start_listening()

    def clear_context(self) -> None:
        self.assistant.clear_context()
        self.transcript_text.clear()
        self.answer_text.clear()
        self._set_status("未监听" if not self.is_listening else "监听中")

    def submit_mock_text(self) -> None:
        text = self.transcriber.transcribe(text=self.manual_input.text())
        if not text:
            return
        self.manual_input.clear()
        self._append_transcript(text, highlight=True)
        self._run_agent(text)

    def regenerate_answer(self) -> None:
        self._run_agent("", regenerate=True)

    def _on_audio_chunk(self, audio: np.ndarray, samplerate: int) -> None:
        self.audio_chunk_signal.emit(audio, samplerate)

    def _on_capture_error(self, message: str) -> None:
        self.capture_error_signal.emit(message)

    def _handle_audio_chunk(self, audio: np.ndarray, samplerate: int) -> None:
        level = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        self.audio_level_label.setText(f"音量: {level:.3f}")
        if level < 0.003:
            if self.is_listening:
                self._set_status("监听中")
            return
        if isinstance(self.transcriber, MockTranscriber):
            self._append_transcript(f"系统：检测到麦克风声音，音量 {level:.3f}。当前未启用真实语音识别，请配置 API Key 后重启。", highlight=False)
            self._set_status("监听中")
            return
        if self.transcribe_thread is not None:
            return
        self._set_status("正在转写")
        self.transcribe_thread = QThread()
        self.transcribe_worker = TranscribeWorker(self.transcriber, audio, samplerate, level)
        self.transcribe_worker.moveToThread(self.transcribe_thread)
        self.transcribe_thread.started.connect(self.transcribe_worker.run)
        self.transcribe_worker.finished.connect(self._on_transcribe_finished)
        self.transcribe_worker.failed.connect(self._on_transcribe_failed)
        self.transcribe_worker.finished.connect(self.transcribe_thread.quit)
        self.transcribe_worker.failed.connect(self.transcribe_thread.quit)
        self.transcribe_thread.finished.connect(self._cleanup_transcribe_worker)
        self.transcribe_thread.start()

    def _on_transcribe_finished(self, text: str, level: float) -> None:
        cleaned = text.strip()
        if cleaned:
            self._append_transcript(cleaned, highlight=True)
            self._run_agent(cleaned)
        elif self.is_listening:
            self._append_transcript(f"系统：收到声音但本段未识别出文字，音量 {level:.3f}。请靠近麦克风或换输入设备。", highlight=False)
            self._set_status("监听中")

    def _on_transcribe_failed(self, message: str, level: float) -> None:
        self._show_error(f"{message}（本段音量 {level:.3f}）")

    def _cleanup_transcribe_worker(self) -> None:
        if self.transcribe_worker is not None:
            self.transcribe_worker.deleteLater()
        if self.transcribe_thread is not None:
            self.transcribe_thread.deleteLater()
        self.transcribe_worker = None
        self.transcribe_thread = None

    def _run_agent(self, text: str, regenerate: bool = False) -> None:
        if self.worker_thread is not None:
            return
        self._set_status("正在思考")
        self.mock_btn.setDisabled(True)
        self.regen_btn.setDisabled(True)
        self.start_btn.setDisabled(True)
        self.worker_thread = QThread()
        self.agent_worker = AgentWorker(self.assistant, text=text, regenerate=regenerate)
        self.agent_worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.agent_worker.run)
        self.agent_worker.finished.connect(self._on_agent_finished)
        self.agent_worker.failed.connect(self._on_agent_failed)
        self.agent_worker.finished.connect(self.worker_thread.quit)
        self.agent_worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._cleanup_worker)
        self.worker_thread.start()

    def _on_agent_finished(self, result: dict[str, Any]) -> None:
        if result.get("should_answer"):
            self.answer_text.setPlainText(str(result.get("answer", "")))
            self._set_status("已生成回答")
        else:
            reason = str(result.get("reason", "未触发回答"))
            self._append_transcript(f"系统：{reason}", highlight=False)
            self._set_status("监听中" if self.is_listening else "未监听")

    def _on_agent_failed(self, message: str) -> None:
        self._show_error(message)
        self.answer_text.setPlainText(f"调用失败：{message}")

    def _cleanup_worker(self) -> None:
        self.mock_btn.setDisabled(False)
        self.regen_btn.setDisabled(False)
        self.start_btn.setDisabled(False)
        if self.agent_worker is not None:
            self.agent_worker.deleteLater()
        if self.worker_thread is not None:
            self.worker_thread.deleteLater()
        self.agent_worker = None
        self.worker_thread = None

    def _append_transcript(self, text: str, highlight: bool) -> None:
        color = "#bfdbfe" if highlight else "#9ca3af"
        self.transcript_text.append(f'<span style="color:{color};">[{now_text()}] {text}</span>')

    def _show_error(self, message: str) -> None:
        self.logger.log_error(message)
        self._set_status("错误")
        self.status_label.setText(f"错误：{message[:32]}")

    def _set_status(self, status: str) -> None:
        self.status_label.setText(status)
        color = STATUS_COLORS.get(status, STATUS_COLORS["未监听"])
        self.status_dot.setStyleSheet(f"background: {color}; border-radius: 5px;")

    def _copy(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    def toggle_collapse(self) -> None:
        self.is_collapsed = not self.is_collapsed
        self.body.setVisible(not self.is_collapsed)
        self.hint_label.setVisible(not self.is_collapsed)
        self.collapse_btn.setText("▴" if self.is_collapsed else "▾")
        if self.is_collapsed:
            self.resize(760, 86)
        else:
            self.resize(760, 680)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def closeEvent(self, event) -> None:
        self.audio_capture.stop()
        if self.worker_thread is not None:
            self.worker_thread.quit()
            self.worker_thread.wait(1500)
        QApplication.restoreOverrideCursor()
        super().closeEvent(event)
