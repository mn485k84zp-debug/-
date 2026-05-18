from __future__ import annotations

import base64
import io
import wave
from abc import ABC, abstractmethod

import numpy as np
from openai import OpenAI

from app.config import AppConfig
from app.logger import AppLogger


class BaseTranscriber(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray | None = None, samplerate: int = 16000, text: str = "") -> str:
        raise NotImplementedError


class MockTranscriber(BaseTranscriber):
    def transcribe(self, audio: np.ndarray | None = None, samplerate: int = 16000, text: str = "") -> str:
        return text.strip()


class RealTranscriber(BaseTranscriber):
    """Short-chunk ASR implementation based on DashScope Qwen3-ASR.

    This is not websocket streaming yet. It sends each recorded chunk as a
    small WAV data URL to the OpenAI-compatible DashScope endpoint.
    """

    def __init__(self, config: AppConfig, logger: AppLogger) -> None:
        self.config = config
        self.logger = logger

    def transcribe(self, audio: np.ndarray | None = None, samplerate: int = 16000, text: str = "") -> str:
        if text:
            return text.strip()
        if audio is None or audio.size == 0:
            return ""
        if not self.config.has_api_key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法使用真实语音转写。")

        wav_bytes = self._to_wav_bytes(audio, samplerate)
        data_uri = "data:audio/wav;base64," + base64.b64encode(wav_bytes).decode("ascii")
        client = OpenAI(api_key=self.config.dashscope_api_key, base_url=self.config.base_url)
        try:
            completion = client.chat.completions.create(
                model=self.config.asr_model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": data_uri},
                            }
                        ],
                    }
                ],
                stream=False,
                extra_body={
                    "asr_options": {
                        "language": "zh",
                        "enable_itn": True,
                    }
                },
            )
            return (completion.choices[0].message.content or "").strip()
        except Exception as exc:
            self.logger.log_error(f"真实语音转写失败：{exc}")
            raise RuntimeError(f"真实语音转写失败：{exc}") from exc

    def _to_wav_bytes(self, audio: np.ndarray, samplerate: int) -> bytes:
        mono = audio.astype(np.float32).reshape(-1)
        target_rate = 16000
        if samplerate != target_rate and mono.size > 1:
            duration = mono.size / float(samplerate)
            target_size = max(1, int(duration * target_rate))
            source_x = np.linspace(0.0, duration, num=mono.size, endpoint=False)
            target_x = np.linspace(0.0, duration, num=target_size, endpoint=False)
            mono = np.interp(target_x, source_x, mono).astype(np.float32)
        pcm = (np.clip(mono, -1.0, 1.0) * 32767).astype(np.int16)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(target_rate)
            wav.writeframes(pcm.tobytes())
        return buffer.getvalue()
