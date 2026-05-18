from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from app.config import AppConfig
from app.logger import AppLogger
from app.qwen_client import QwenClient
from app.utils import chinese_char_count, clean_text, text_similarity


QUESTION_KEYWORDS = (
    "什么", "为什么", "怎么", "如何", "能不能", "可不可以", "你了解", "你做过",
    "介绍一下", "说一下", "讲一下", "项目", "经验", "技术", "Agent", "RAG",
    "FastAPI", "Python", "模型", "数据库", "接口", "部署", "实习", "简历",
    "为什么选择", "优势", "缺点",
)

CHATTER = ("你好", "嗯", "啊", "哦", "好的", "可以", "行", "谢谢", "喂", "hello", "hi")


@dataclass(slots=True)
class AgentResult:
    should_answer: bool
    status: str
    question: str
    answer: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "should_answer": self.should_answer,
            "status": self.status,
            "question": self.question,
            "answer": self.answer,
            "reason": self.reason,
        }


class AgentAssistant:
    def __init__(
        self,
        config: AppConfig,
        qwen_client: QwenClient,
        logger: AppLogger,
        prompt_path: Path,
    ) -> None:
        self.config = config
        self.qwen_client = qwen_client
        self.logger = logger
        self.prompt_path = prompt_path
        self.context: list[str] = []
        self.last_answered: list[tuple[str, float]] = []

    def clear_context(self) -> None:
        self.context.clear()
        self.last_answered.clear()

    def is_question(self, text: str) -> tuple[bool, str]:
        normalized = clean_text(text)
        if not normalized:
            return False, "空文本"
        if normalized.lower() in CHATTER:
            return False, "寒暄或语气词"
        has_question_mark = "?" in text or "？" in text
        has_keyword = any(keyword.lower() in normalized.lower() for keyword in QUESTION_KEYWORDS)
        if chinese_char_count(normalized) < 6 and not (has_question_mark and has_keyword):
            return False, "短句且问题特征不足"
        if has_question_mark or has_keyword:
            return True, "命中问题规则"
        return False, "未命中问题规则"

    def is_duplicate(self, question: str) -> bool:
        now = time.time()
        cooldown = self.config.answer_cooldown_seconds
        self.last_answered = [(q, ts) for q, ts in self.last_answered if now - ts <= cooldown]
        return any(text_similarity(question, old) >= 0.84 for old, _ in self.last_answered)

    def handle_text(self, text: str) -> dict[str, object]:
        question = clean_text(text)
        if not question:
            return AgentResult(False, "ignored", question, reason="空文本").as_dict()

        self.context.append(question)
        self.context = self.context[-self.config.max_context_items :]
        should_answer, reason = self.is_question(question)
        self.logger.log_transcript(question, should_answer)

        if not should_answer:
            return AgentResult(False, "ignored", question, reason=reason).as_dict()
        if self.is_duplicate(question):
            return AgentResult(False, "duplicate", question, reason="15 秒内相似问题已回答").as_dict()

        system_prompt = self._load_prompt()
        answer = self.qwen_client.generate_answer(
            system_prompt=system_prompt,
            question=question,
            context=self.context[-5:],
        )
        self.last_answered.append((question, time.time()))
        self.logger.log_answer(question, answer, self.config.model_name)
        return AgentResult(True, "answered", question, answer=answer, reason=reason).as_dict()

    def regenerate(self) -> dict[str, object]:
        if not self.context:
            return AgentResult(False, "ignored", "", reason="暂无可重新生成的问题").as_dict()
        question = self.context[-1]
        system_prompt = self._load_prompt()
        answer = self.qwen_client.generate_answer(system_prompt, question, self.context[-5:])
        self.last_answered.append((question, time.time()))
        self.logger.log_answer(question, answer, self.config.model_name)
        return AgentResult(True, "answered", question, answer=answer, reason="重新生成").as_dict()

    def _load_prompt(self) -> str:
        try:
            return self.prompt_path.read_text(encoding="utf-8").strip()
        except OSError:
            return "你是面试实时辅助助手，请给出口语化、简短、自然的中文回答。"
