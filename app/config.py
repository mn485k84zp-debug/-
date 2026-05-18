from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


@dataclass(slots=True)
class AppConfig:
    dashscope_api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name: str = "qwen-plus"
    asr_model_name: str = "qwen3-asr-flash"
    temperature: float = 0.3
    max_context_items: int = 10
    answer_cooldown_seconds: int = 15
    mock_mode: bool = True
    ui_opacity: float = 0.92
    always_on_top: bool = True

    @property
    def has_api_key(self) -> bool:
        return bool(self.dashscope_api_key.strip())


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_config(project_root: Path | None = None) -> AppConfig:
    root = project_root or Path.cwd()
    load_dotenv(root / ".env")
    data = _read_json(root / "config.json")
    defaults = AppConfig()

    cfg = AppConfig(
        dashscope_api_key=str(data.get("dashscope_api_key", "")),
        base_url=str(data.get("base_url", defaults.base_url)),
        model_name=str(data.get("model_name", defaults.model_name)),
        asr_model_name=str(data.get("asr_model_name", defaults.asr_model_name)),
        temperature=float(data.get("temperature", defaults.temperature)),
        max_context_items=int(data.get("max_context_items", defaults.max_context_items)),
        answer_cooldown_seconds=int(
            data.get("answer_cooldown_seconds", defaults.answer_cooldown_seconds)
        ),
        mock_mode=bool(data.get("mock_mode", defaults.mock_mode)),
        ui_opacity=float(data.get("ui_opacity", defaults.ui_opacity)),
        always_on_top=bool(data.get("always_on_top", defaults.always_on_top)),
    )
    env_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if env_key:
        cfg.dashscope_api_key = env_key
    cfg.ui_opacity = max(0.55, min(1.0, cfg.ui_opacity))
    cfg.max_context_items = max(3, min(50, cfg.max_context_items))
    cfg.answer_cooldown_seconds = max(3, cfg.answer_cooldown_seconds)
    return cfg
