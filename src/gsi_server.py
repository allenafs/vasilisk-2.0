# -*- coding: utf-8 -*-
"""
GSI-сервер: слушает POST-пакеты Dota 2 Game State Integration на 127.0.0.1:9001.

Dota шлёт частичные JSON-блоки (map/player/hero/items/minimap/buildings/events)
~раз в 100 мс при изменениях + heartbeat. Здесь они сливаются в MatchState,
прогоняются через Advisor, советы уходят в озвучку/оверлей/лог.
"""
from __future__ import annotations

import asyncio
import json
import time

from aiohttp import web

from state import MatchState
from advisor import Advisor
from llm import CoachLLM
from tts import Speaker
from extras import build_context


class CoachApp:
    def __init__(self, advisor: Advisor, llm: CoachLLM, speaker: Speaker,
                 renderer, logger=print, token="vasilisk_2026", record_path=None):
        self.state = MatchState()
        self.advisor = advisor
        self.llm = llm
        self.speaker = speaker
        self.renderer = renderer
        self.log = logger
        self.token = token
        self.advice_log: list = []          # последние 50 (для /advice)
        self.plan_loader = None            # async callable -> plan
        self._plan_loading = False
        self._started_at = time.time()
        # --- диагностика реального GSI-потока ------------------------------
        self.record_path = record_path      # сырые пакеты в JSONL (—record)
        self.blocks_seen: set = set()       # какие блоки реально приходили
        self._blocks_warned = False
        # --- очередь доставки (LLM не задерживает ответ игре) и свободный тренер
        self._dq: asyncio.Queue = asyncio.Queue()
        self.free_coach = True
        self.coach_interval = 30
        self._next_coach = 0.0
        self._next_llm_check = 0.0
        self._last_spoken = 0.0

    # ------------------------------------------------------------------ http
    async def handle_gsi(self, request: web.Request):
        try:
            payload = await request.json(loads=json.loads)
        except Exception:
            return web.Response(status=400)
        if not isinstance(payload, dict):
            return web.Response(status=400)
        tok = (payload.get("auth") or {}).get("token")
        if self.token and tok != self.token:        # пакет без токена тоже отклоняем
            if self.state.auth_token_ok is not False:
                self.log("[GSI] пакет без токена или с чужим токеном — игнорирую (проверь auth.token в .cfg)")
            self.state.auth_token_ok = False
            return web.Response(status=403)
        self.state.auth_token_ok = True

        # сырая запись пакета (для отладки реального клиента)
        if self.record_path:
            try:
                with open(self.record_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, ensure_ascii=False,
                                       separators=(",", ":")) + "\n")
            except Exception as e:
                self.log(f"[GSI] не удалось записать пакет: {e}")

        # какие блоки реально присылает клиент
        self.blocks_seen.update(
            k for k in payload if k not in ("auth", "provider", "previously", "added"))

        await self._maybe_load_plan()

        self.state.update(payload)
        st = self.state

        advices = self.advisor.on_state(st)
        for adv in advices:
            self._dq.put_nowait(adv)
        self.renderer.timers(self.advisor.timers_panel(st))
        self._warn_missing_blocks()
        return web.Response(status=204)

    async def _maybe_load_plan(self):
        st = self.state
        if (self.plan_loader and st.hero_key and not self.advisor.plan
                and not self._plan_loading):
            self._plan_loading = True
            try:
                plan = await self.plan_loader(st.hero_key)
                self.advisor.plan = plan
                goals = ", ".join(f"{g.ru}({g.target_min}м)" for g in plan[:4])
                self.log(f"[BUILD] план для {st.hero_key}: {goals}")
            except Exception as e:
                self.log(f"[BUILD] не удалось загрузить план: {e}")
            finally:
                self._plan_loading = False

    # ------------------------------------------------------------------ фоновые задачи
    async def deliver_worker(self):
        """Доставляет советы по порядку: ожидание нейросети не задерживает ответ игре."""
        while True:
            adv = await self._dq.get()
            try:
                await self._deliver(adv)
            except Exception as e:
                self.log(f"[GSI] ошибка доставки совета: {e}")

    async def coach_loop(self):
        """Раз в coach_interval секунд сам даёт короткий совет «что делать сейчас» (если есть Ollama)."""
        while True:
            await asyncio.sleep(3)
            try:
                now = time.time()
                if self.llm.enabled and not self.llm.available and now >= self._next_llm_check:
                    self._next_llm_check = now + 30        # Ollama могли запустить уже после тренера
                    if await self.llm.check():
                        self.log(f"[LLM] Ollama появилась: {self.llm.model}")
                st = self.state
                if not (self.free_coach and self.llm.enabled and self.llm.available):
                    continue
                if (now - st.last_payload_ts > 10 or not st.match_started or st.game_over
                        or st.clock < 60 or now < self._next_coach or now - self._last_spoken < 15):
                    continue
                self._next_coach = now + self.coach_interval
                recent = [a["text"] for a in self.advice_log[-3:]]
                text = await self.llm.coach(build_context(st, self.advisor), recent)
                if text:
                    clock_s = st.fmt_clock()
                    self.renderer.advice(text, 1, clock_s)
                    self.log(f"[{clock_s}] [ИИ] {text}")
                    self.advice_log.append({"clock": clock_s, "text": text, "cat": "coach", "prio": 1})
                    self.advice_log = self.advice_log[-50:]
                    self._last_spoken = time.time()
                    await self.speaker.say(text)
            except Exception:
                pass

    def blocks_report(self) -> str:
        got = sorted(self.blocks_seen)
        if not got:
            return "Ожидание пакетов от Dota 2…"
        core_miss = [b for b in ("map", "player", "hero", "items", "abilities") if b not in self.blocks_seen]
        opt = {"minimap": "видимость врагов", "buildings": "состояние башен", "events": "события"}
        miss = [f"{b} ({why})" for b, why in opt.items() if b not in self.blocks_seen]
        msg = f"Блоки из игры: {', '.join(got)}."
        if core_miss:
            msg += f" Не приходят важные: {', '.join(core_miss)}."
        if miss:
            msg += " Не приходят: " + ", ".join(miss) + " — зависящие подсказки отключены."
        return msg

    def _warn_missing_blocks(self):
        """Одно предупреждение, если реальный клиент не шлёт minimap/buildings.

        (Например, если Valve в конкретном патче отдаёт их только наблюдателям:
        тогда пропадают советы «враг пропал» / «башня пала» — лучше знать это
        сразу, чем гадать, почему тренер молчит.)
        """
        if self._blocks_warned or self.state.payloads < 30 or self.state.clock < 60:
            return
        self._blocks_warned = True
        known = {
            "map": "таймеры/счёт",
            "player": "экономика (GPM/ластхиты)",
            "hero": "смерть/байбек/ресурсы",
            "items": "тайминги покупок",
            "minimap": "«враг пропал из вижена» (ганк-тревоги)",
            "buildings": "«их башня пала — пуш»",
            "events": "события",
        }
        missing = [b for b in known if b not in self.blocks_seen]
        if missing:
            feats = "; ".join(known[b] for b in missing)
            self.log(
                f"[GSI] ⚠ твой клиент не присылает блоки: {', '.join(missing)}. "
                f"Отключены функции: {feats}.")
            self.log(
                "[GSI] проверить, что реально приходит: python tools/capture_gsi.py "
                "(запусти вместо тренера, сыграй минуту, Ctrl+C)")

    async def _deliver(self, adv):
        clock_s = f"{int(adv.clock // 60):02d}:{int(adv.clock % 60):02d}"
        self.renderer.advice(adv.text, adv.prio, clock_s)
        self.log(f"[{clock_s}] {adv.text}")
        self.advice_log.append({"clock": clock_s, "text": adv.text,
                                "cat": adv.cat, "prio": adv.prio})
        self.advice_log = self.advice_log[-50:]
        if adv.tts:
            self._last_spoken = time.time()
            # факт правила → живая фраза (Ollama); нет нейросети — шаблон
            phrase = None
            if self.llm.enabled and self.llm.available:
                phrase = await self.llm.phrase(adv.text, self.state)
            final = phrase or adv.text
            await self.speaker.say(final)   # спикер сам знает, включён ли он
            if phrase:
                self.log(f"[LLM] → {phrase}")

    # ------------------------------------------------------------------ http misc
    async def handle_health(self, request):
        st = self.state
        return web.json_response({
            "ok": True,
            "payloads": st.payloads,
            "clock": st.fmt_clock(),
            "hero": st.hero_key,
            "team": st.team,
            "matchid": st.matchid,
            "llm": self.llm.available,
            "blocks": sorted(self.blocks_seen),
            "advice_total": len(self.advisor.match_events),
        })

    async def handle_advice(self, request):
        return web.json_response(self.advice_log)


def make_app(coach: CoachApp, port=9001):
    app = web.Application(client_max_size=2 * 1024 * 1024)   # пакеты GSI маленькие: ограничиваем размер

    async def _start(a):
        coach._bg = [asyncio.create_task(coach.deliver_worker()), asyncio.create_task(coach.coach_loop())]

    async def _stop(a):
        for t in getattr(coach, "_bg", []):
            t.cancel()

    app.on_startup.append(_start)
    app.on_cleanup.append(_stop)
    app.router.add_post("/", coach.handle_gsi)
    app.router.add_get("/health", coach.handle_health)
    app.router.add_get("/advice", coach.handle_advice)
    return app
