# -*- coding: utf-8 -*-
"""
TTS — озвучка советов тренера: Windows SAPI через PowerShell
(движок System.Speech; маркеры VASILISK_TTS_STARTED/COMPLETED — для зерка
трейса, как это делают стрим-оверлеи).

Windows: powershell System.Speech (голос из config.json, напр. Irina).
Linux/тест: заглушка-лог.
"""
from __future__ import annotations

import asyncio
import platform
import subprocess
import sys

MARK_START = "VASILISK_TTS_STARTED"
MARK_DONE = "VASILISK_TTS_COMPLETED"


def _ps_speak(text: str, voice: str, rate: int) -> str:
    t = text.replace("'", "’").replace('"', "")
    sel = f"$s.SelectVoice('{voice}');" if voice else ""
    return (
        "Add-Type -AssemblyName System.Speech;"
        f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"{sel}"
        f"$s.Rate = {rate};"
        f"$s.Speak('{t}');"
    )


class Speaker:
    def __init__(self, enabled=True, voice="", rate=0):
        self.enabled = enabled
        self.voice = voice
        self.rate = rate
        self.is_windows = platform.system() == "Windows"
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=4)
        self._log = print

    # ------------------------------------------------------------- интерфейс
    async def say(self, text: str):
        """Поставить фразу в очередь озвучки (не блокирует)."""
        if not self.enabled or not text:
            return
        try:
            self._queue.put_nowait(text)
        except asyncio.QueueFull:
            pass  # очередь переполнена — пропускаем, не душим игру

    async def run_forever(self, logger=print):
        """Рабочий корутин: читает очередь и говорит."""
        self._log = logger
        while True:
            text = await self._queue.get()
            try:
                await self._speak(text)
            except Exception as e:
                logger(f"[TTS] ошибка: {e}")
            finally:
                self._queue.task_done()

    async def _speak(self, text: str):
        if not self.is_windows:
            logger = self._log
            logger(f"[{MARK_START}] (stub) {text}")
            logger(f"[{MARK_DONE}] (stub)")
            await asyncio.sleep(0.05)
            return
        logger = self._log
        logger(f"[{MARK_START}] {text}")
        cmd = ["powershell", "-NoProfile", "-Command", _ps_speak(text, self.voice, self.rate)]
        creation = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL, creationflags=creation)
        try:
            await asyncio.wait_for(proc.wait(), timeout=25)
        except asyncio.TimeoutError:
            proc.kill()
        logger(f"[{MARK_DONE}]")
