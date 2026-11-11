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
        self._session = None

    def _sess(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def check(self) -> bool:
        if not self.enabled:
            return False
        try:
            async with self._sess().get(f"{self.url}/api/tags",
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
            async with self._sess().post(f"{self.url}/api/chat", json=payload,
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


    # ------------------------------------------------------------------ свободный тренер и вопросы
    async def _chat(self, system: str, user: str, num_predict: int, timeout: int):
        payload = {"model": self.model, "stream": False,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "options": {"temperature": 0.4, "num_predict": num_predict}}
        async with self._sess().post(f"{self.url}/api/chat", json=payload,
                                     timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            if r.status != 200:
                raise RuntimeError(f"Ollama HTTP {r.status}")
            data = await r.json()
        return str((data.get("message") or {}).get("content") or "").replace("\n", " ").strip().strip('"«»')

    async def coach(self, context: str, recent: list) -> str | None:
        """Одна короткая подсказка «что делать сейчас». Числа обязаны быть из контекста."""
        if not self.available:
            return None
        system = ("Ты тренер по Dota 2. По данным ниже дай ОДНО конкретное действие на ближайшую минуту, "
                  "одной русской фразой до 14 слов. Используй только данные ниже: не выдумывай героев, предметы, числа "
                  "и позиции врагов (их ты не знаешь). Не повторяй недавние советы.")
        user = f"{context}\nНедавние советы: {' | '.join(recent) or 'нет'}"
        try:
            text = await self._chat(system, user, 60, 8)
        except Exception as e:
            self.last_error = str(e)
            return None
        if not text or len(text) > 170 or "**" in text:
            return None
        allowed = set(re.findall(r"\d+", context + " ".join(recent)))
        return text if set(re.findall(r"\d+", text)) <= allowed else None

    async def ask(self, question: str, context: str) -> str:
        """Вопрос игрока. Ответ может быть неточным: у модели только данные из контекста."""
        if not self.available:
            return "Ollama недоступна: установи её с ollama.com и выполни `ollama pull " + self.model + "`."
        system = ("Ты тренер по Dota 2. Отвечай по-русски кратко (до 3 предложений). Опирайся на данные матча ниже; "
                  "если данных не хватает, так и скажи. Позиций и предметов врагов ты не знаешь.")
        try:
            return await self._chat(system, f"{context}\n\nВопрос: {question}", 200, 40) or "Нет ответа."
        except Exception as e:
            return f"Ошибка Ollama: {e}"
