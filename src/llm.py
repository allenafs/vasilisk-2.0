# -*- coding: utf-8 -*-
"""
LLM — локальная нейросеть (Ollama) для живых фраз тренера.

Правила выдают ФАКТ, Ollama превращает его в разговорную русскую фразу
в стиле «отпушь бот — затем стягивайся к Рошану». Нет Ollama — используется
шаблонный текст (полная работоспособность без нейросети).
"""
from __future__ import annotations

import re

import aiohttp

SYSTEM = (
    "Ты — голосовой тренер по Dota 2. Получаешь ФАКТ о текущем матче и "
    "молодёжно-спокойно озвучиваешь его ОДНОЙ короткой русской фразой "
    "(не больше 12 слов). Без списков, без кавычек, без латиницы. "
    "СТРОГО: не добавляй героев, предметов и чисел, которых нет в факте. "
    "Стиль: «отпушь бот — затем стягивайся к Рошану», «отойди из вражеского вижена», "
    "«добрать БКБ — забери ближайшую пачку на боте». "
    "Числа проговаривай просто: «осталось 300 золота»."
)

FEWSHOT = [
    {"role": "user", "content": "ФАКТ: вражеский герой Пудж пропал из вида у топ-руны, была видна 10 секунд назад."},
    {"role": "assistant", "content": "Пудж пропал наверху — отойди, жди ганк."},
    {"role": "user", "content": "ФАКТ: нужно 900 золота до БКБ, цель 25-я минута, идёт 23-я."},
    {"role": "assistant", "content": "До БКБ не хватает 900 — забери пачку на боте."},
    {"role": "user", "content": "ФАКТ: Рошан умер на 14:20, окно респавна 22:20—25:20, игра идёт 21:30."},
    {"role": "assistant", "content": "Рошан скоро — поставь варда на питу и собери смок."},
]


class CoachLLM:
    def __init__(self, url="http://127.0.0.1:11434", model="qwen2.5:7b-instruct", enabled=True):
        self.url = url.rstrip("/")
        self.model = model
        self.enabled = enabled
        self.available = False
        self.last_error = ""

    async def check(self) -> bool:
        if not self.enabled:
            return False
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{self.url}/api/tags",
                                 timeout=aiohttp.ClientTimeout(total=2)) as r:
                    self.available = r.status == 200
        except Exception as e:
            self.available = False
            self.last_error = str(e)
        return self.available

    def _context(self, st) -> str:
        """Компактный контекст матча для промпта."""
        try:
            hero = st.hero.get("name") or ""
            goal = None
            return (
                f"контекст: герой={hero.replace('npc_dota_hero_', '')}, "
                f"минута={int(st.clock // 60)}, золото={int(st.gold)}, "
                f"gpm={int(st.gpm)}, счёт={st.map.get('radiant_score')}:{st.map.get('dire_score')}"
            )
        except Exception:
            return ""

    async def phrase(self, fact: str, st) -> str | None:
        """ФАКТ -> живая фраза. None, если LLM недоступен/ответ мусорный."""
        if not self.available:
            return None
        ctx = self._context(st)
        user = f"{ctx}\nФАКТ: {fact}" if ctx else f"ФАКТ: {fact}"
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM}, *FEWSHOT,
                         {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0.6, "num_predict": 60},
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{self.url}/api/chat", json=payload,
                                  timeout=aiohttp.ClientTimeout(total=6)) as r:
                    if r.status != 200:
                        return None
                    data = await r.json()
            text = str((data.get("message") or {}).get("content") or "").strip()
            text = text.replace("\n", " ").strip().strip('"«»')
            if not text or len(text) > 160 or "**" in text:
                return None
            # анти-выдумки: цифры в фразе обязаны быть в факте
            fact_digits = set(re.findall(r"\d+", fact))
            if not set(re.findall(r"\d+", text)) <= fact_digits:
                return None
            return text
        except Exception:
            return None
