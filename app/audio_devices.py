from __future__ import annotations

from dataclasses import dataclass

import sounddevice as sd


@dataclass(slots=True)
class AudioDeviceInfo:
    index: int
    name: str
    samplerate: int
    channels: int

    @property
    def display_name(self) -> str:
        return f"{self.name}  |  {self.samplerate} Hz  |  {self.channels} ch"


def list_input_devices() -> list[AudioDeviceInfo]:
    devices: list[AudioDeviceInfo] = []
    try:
        for index, device in enumerate(sd.query_devices()):
            channels = int(device.get("max_input_channels", 0))
            if channels <= 0:
                continue
            samplerate = int(device.get("default_samplerate", 16000) or 16000)
            devices.append(
                AudioDeviceInfo(
                    index=index,
                    name=str(device.get("name", f"Input {index}")),
                    samplerate=samplerate,
                    channels=channels,
                )
            )
    except Exception:
        return []
    return devices
