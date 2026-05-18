from __future__ import annotations

import queue
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd


AudioChunkCallback = Callable[[np.ndarray, int], None]
ErrorCallback = Callable[[str], None]


class AudioCapture:
    def __init__(
        self,
        on_chunk: AudioChunkCallback,
        on_error: ErrorCallback | None = None,
        chunk_seconds: float = 3.0,
    ) -> None:
        self.on_chunk = on_chunk
        self.on_error = on_error
        self.chunk_seconds = chunk_seconds
        self._stream: sd.InputStream | None = None
        self._queue: queue.Queue[np.ndarray] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._samplerate = 16000

    @property
    def is_running(self) -> bool:
        return self._stream is not None

    def start(self, device_index: int | None, samplerate: int = 16000, channels: int = 1) -> None:
        if self.is_running:
            return
        self._samplerate = int(samplerate or 16000)
        self._stop_event.clear()
        blocksize = max(1024, int(self._samplerate * 0.2))

        def callback(indata: np.ndarray, frames: int, time_info: object, status: object) -> None:
            if status and self.on_error:
                self.on_error(str(status))
            self._queue.put(indata.copy())

        try:
            self._stream = sd.InputStream(
                device=device_index,
                channels=max(1, min(2, channels)),
                samplerate=self._samplerate,
                dtype="float32",
                blocksize=blocksize,
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            if self.on_error:
                self.on_error(f"启动录音失败：{exc}")
            return

        self._worker = threading.Thread(target=self._emit_loop, name="audio-capture", daemon=True)
        self._worker.start()

    def pause(self) -> None:
        self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def _emit_loop(self) -> None:
        chunks: list[np.ndarray] = []
        target_frames = int(self._samplerate * self.chunk_seconds)
        total_frames = 0
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            chunks.append(item)
            total_frames += item.shape[0]
            if total_frames < target_frames:
                continue
            audio = np.concatenate(chunks, axis=0)
            chunks.clear()
            total_frames = 0
            if audio.ndim == 2 and audio.shape[1] > 1:
                audio = np.mean(audio, axis=1)
            else:
                audio = audio.reshape(-1)
            self.on_chunk(audio.astype(np.float32), self._samplerate)
