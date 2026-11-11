# -*- coding: utf-8 -*-
"""Автотесты на GSI-пакеты: python -m unittest discover tests"""
import asyncio, os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import extras  # noqa: E402
from advisor import Advisor  # noqa: E402
from builds import Builds  # noqa: E402
from gsi_server import CoachApp, make_app  # noqa: E402
from llm import CoachLLM  # noqa: E402
from state import MatchState  # noqa: E402
from tts import Speaker, _ps_speak  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "t0k"


class Null:
    def advice(self, *a): pass
    def timers(self, *a): pass


def packet(t, mine=0, enemy=0, team="radiant", token=TOKEN, **kw):
    p = {"auth": {"token": token},
         "map": {"clock_time": t, "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS", "radiant_score": mine if team == "radiant" else enemy,
                 "dire_score": enemy if team == "radiant" else mine, "roshan_state": "DOTA_ROSHAN_STATE_ALIVE", "daytime": True},
         "player": {"team_name": team, "gold": 500, "kills": 1, "deaths": 0, "last_hits": 30, "gpm": 400},
         "hero": {"name": "npc_dota_hero_axe", "level": 8, "alive": True, "health_percent": 90, "mana_percent": 80},
         "abilities": {"ability0": {"level": 3, "can_cast": True}, "ability5": {"level": 1, "can_cast": True, "ultimate": True}},
         "items": {"slot0": {"name": "item_blink"}, "teleport0": {"name": "item_tpscroll"}}}
    p.update(kw)
    return p


def make():
    builds = Builds(os.path.join(BASE, "builds_cache.json"), meta_path=os.path.join(BASE, "data", "meta.json"))
    adv = Advisor(build_plan=[], role="carry", builds=builds)
    return CoachApp(adv, CoachLLM(enabled=False), Speaker(enabled=False), Null(), logger=lambda m: None, token=TOKEN), builds


class Tests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    def test_token_required(self):
        async def go():
            coach, _ = make()
            async with TestClient(TestServer(make_app(coach))) as c:
                self.assertEqual((await c.post("/", json=packet(10))).status, 204)
                self.assertEqual((await c.post("/", json=packet(11, token="bad"))).status, 403)
                nt = packet(12); nt.pop("auth")
                self.assertEqual((await c.post("/", json=nt)).status, 403)   # без токена тоже отказ
        self.run_async(go())

    def test_team_from_player_block(self):
        st = MatchState(); st.update(packet(10, team="dire"))
        self.assertEqual(st.team, "dire")

    def test_fight_swing_push_and_defend(self):
        coach, _ = make(); st = MatchState()
        for t, a, b in [(1000, 3, 3), (1015, 4, 3), (1025, 6, 3)]:
            st.update(packet(t, a, b))
            out = coach.advisor.on_state(st)
        self.assertTrue(any("Выиграли файт" in a.text for a in out))
        coach, _ = make(); st = MatchState()
        for t, a, b in [(1000, 3, 3), (1015, 3, 4), (1025, 3, 6)]:
            st.update(packet(t, a, b))
            out = coach.advisor.on_state(st)
        self.assertTrue(any("Проиграли файт" in a.text for a in out))

    def test_gank_when_ult_ready(self):
        coach, _ = make(); st = MatchState(); st.update(packet(600, 2, 2))
        self.assertTrue(any("ганк" in a.text for a in coach.advisor.on_state(st)))

    def test_no_outpost_or_tome_advice(self):
        coach, _ = make(); st = MatchState(); texts = []
        for t in range(0, 2100, 5):
            st.update(packet(t)); texts += [a.text.lower() for a in coach.advisor.on_state(st)]
        self.assertFalse(any("аутпост" in x or "томик" in x for x in texts))

    def test_wisdom_rune_and_aegis_pickup(self):
        coach, _ = make(); st = MatchState(); texts = []
        for t in range(400, 430):
            st.update(packet(t)); texts += [a.text for a in coach.advisor.on_state(st)]
        self.assertTrue(any("Руна мудрости" in x for x in texts))
        st.update(packet(900, items={"slot0": {"name": "item_aegis"}}))
        self.assertEqual(st.aegis_pick_clock, 900)

    def test_roles_and_counters(self):
        self.assertEqual(extras.normalize_role("5"), "support"); self.assertEqual(extras.normalize_role("pos1"), "carry")
        _, b = make(); recs = [b.meta[k] for k in ("npc_dota_hero_riki", "npc_dota_hero_axe") if k in b.meta]
        self.assertTrue(any("Dust" in c["item"] for c in extras.counter_items(recs)))
        self.assertTrue(extras.draft_picks(b.meta, ["npc_dota_hero_axe"], []))

    def test_free_coach_speaks_and_guards_numbers(self):
        class FakeLLM(CoachLLM):
            def __init__(self):
                super().__init__(enabled=True); self.available = True; self.calls = 0
            async def _chat(self, system, user, num_predict, timeout):
                self.calls += 1
                return "Забери руну и играй на 99 минуте" if self.calls == 1 else "Выбей Рошана вместе с командой"
            async def check(self): return True

        async def go():
            coach, _ = make(); coach.llm = FakeLLM(); coach.coach_interval = 0
            coach.state.update(packet(300, 2, 2)); coach.state.last_payload_ts = __import__("time").time()
            coach.state.match_started = True
            import gsi_server; orig = gsi_server.asyncio.sleep
            task = asyncio.create_task(coach.coach_loop())
            for _ in range(60):
                await orig(0.1)
                coach.state.last_payload_ts = __import__("time").time()
                if any(a["cat"] == "coach" for a in coach.advice_log): break
            task.cancel()
            texts = [a["text"] for a in coach.advice_log if a["cat"] == "coach"]
            self.assertTrue(texts and "99" not in texts[0], texts)   # фраза с выдуманным числом отброшена
        self.run_async(go())

    def test_tts_escaping(self):
        cmd = _ps_speak("Привет '$(calc)' \n мир", "Irina'; calc; '", 99)
        self.assertNotIn("calc;", cmd); self.assertIn("Rate = 10", cmd)


if __name__ == "__main__":
    unittest.main()
