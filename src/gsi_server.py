# -*- coding: utf-8 -*-
"""
GSI-сервер: слушает POST-пакеты Dota 2 Game State Integration на 127.0.0.1:9001.

Dota шлёт частичные JSON-блоки (map/player/hero/items/minimap/buildings/events)
~раз в 100 мс при изменениях + heartbeat. Здесь они сливаются в MatchState,
прогоняются через Advisor, советы уходят в озвучку/оверлей/лог.
"""
from __future__ import annotations

import json
import time
from typing import Callable

from aiohttp import web

from state import MatchState
from advisor import Advisor
from llm import CoachLLM
from tts import Speaker


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

    # ------------------------------------------------------------------ http
    async def handle_gsi(self, request: web.Request):
        try:
            payload = await request.json(loads=json.loads)
        except Exception:
            return web.Response(status=400)
        if not isinstance(payload, dict):
            return web.Response(status=400)
        auth = payload.get("auth") or {}
        tok = auth.get("token")
        if self.token and tok and tok != self.token:
            if self.state.auth_token_ok is not False:
                self.log("[GSI] чужой токен — пакет проигнорирован")
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
            await self._deliver(adv)
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
    app = web.Application()
    app.router.add_post("/", coach.handle_gsi)
    app.router.add_get("/health", coach.handle_health)
    app.router.add_get("/advice", coach.handle_advice)
    return app
