from __future__ import annotations

import logging
from pathlib import Path

from app.utils import now_text, today_text


class AppLogger:
    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = logs_dir
        self.transcripts_dir = logs_dir / "transcripts"
        self.answers_dir = logs_dir / "answers"
        self.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.answers_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(logs_dir / "app.log"),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            encoding="utf-8",
        )

    def log_transcript(self, text: str, is_question: bool) -> None:
        line = f"[{now_text()}] is_question={is_question} text={text}\n"
        (self.transcripts_dir / f"{today_text()}.txt").open("a", encoding="utf-8").write(line)
        logging.info("transcript is_question=%s text=%s", is_question, text)

    def log_answer(self, question: str, answer: str, model_name: str) -> None:
        content = (
            f"[{now_text()}] model={model_name}\n"
            f"Question: {question}\n"
            f"Answer:\n{answer}\n"
            f"{'-' * 72}\n"
        )
        (self.answers_dir / f"{today_text()}.txt").open("a", encoding="utf-8").write(content)
        logging.info("answer model=%s question=%s", model_name, question)

    def log_error(self, message: str) -> None:
        logging.exception(message)
