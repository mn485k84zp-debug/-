from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.agent import AgentAssistant
from app.config import load_config
from app.logger import AppLogger
from app.qwen_client import QwenClient
from app.ui import MainWindow


def main() -> int:
    project_root = Path(__file__).resolve().parent
    config = load_config(project_root)
    logger = AppLogger(project_root / "logs")
    qwen_client = QwenClient(config=config, logger=logger)
    prompt_path = project_root / "prompts" / "interview_prompt.txt"
    assistant = AgentAssistant(
        config=config,
        qwen_client=qwen_client,
        logger=logger,
        prompt_path=prompt_path,
    )

    app = QApplication(sys.argv)
    app.setApplicationName("实时语音面试回答助手")
    window = MainWindow(config=config, assistant=assistant, logger=logger)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
