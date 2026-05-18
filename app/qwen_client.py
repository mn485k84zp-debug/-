from __future__ import annotations

from openai import OpenAI

from app.config import AppConfig
from app.logger import AppLogger


class QwenClient:
    def __init__(self, config: AppConfig, logger: AppLogger) -> None:
        self.config = config
        self.logger = logger

    def generate_answer(self, system_prompt: str, question: str, context: list[str]) -> str:
        if not self.config.has_api_key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY。请先设置环境变量或在 config.json 中填写 dashscope_api_key。")

        client = OpenAI(api_key=self.config.dashscope_api_key, base_url=self.config.base_url)
        context_text = "\n".join(f"- {item}" for item in context[-5:])
        user_prompt = (
            "最近上下文：\n"
            f"{context_text or '- 无'}\n\n"
            "当前需要回答的问题：\n"
            f"{question}\n\n"
            "请严格按系统提示词中的固定格式输出。"
        )
        try:
            response = client.chat.completions.create(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.temperature,
                stream=False,
            )
            content = response.choices[0].message.content or ""
            return content.strip()
        except Exception as exc:
            self.logger.log_error(f"Qwen 调用失败：{exc}")
            raise RuntimeError(f"千问调用失败：{exc}") from exc
