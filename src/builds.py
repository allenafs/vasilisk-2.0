# -*- coding: utf-8 -*-
"""
Builds v2 — «актуальные сборки с таймингами» ТОЛЬКО из реальных данных.

Приоритет источников (все — реальная статистика, не выдумка):
  1. OpenDota /api/scenarios/itemTimings — во сколько минут предмет обычно
     покупают на этом герое (живой запрос, есть сеть);
  2. data/meta.json — офлайн-снимок меты (tools/fetch_meta.py):
     популярность предметов по фазам (start/early/mid/late) + бенчмарки
     GPM/XPM/ластхитов по перцентилям;
  3. кэш builds_cache.json (прошлые живые запросы);
  4. rules_data.STATIC_BUILDS — аварийный фолбэк, когда сети и снимка нет
     вообще; в текстах честно помечается как устаревший.

Обновление снимка: python tools/fetch_meta.py
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json
import os
import time
from typing import Dict, List, Optional

import aiohttp

from rules_data import STATIC_BUILDS, ITEM_RU, CONSUMABLES, item_ru

OD = "https://api.opendota.com/api"
UA = {"User-Agent": "Mozilla/5.0 (vasilisk/2.0)"}
CACHE_TTL = 24 * 3600

# фазам popular-снимка сопоставляем плановые минуты (это НАША цель, не факт)
PHASE_TARGET_MIN = {"early_game": 10, "mid_game": 20, "late_game": 30}
CORE_COST_MIN = 1500          # кор-итем: дороже 1500 золота
PLAN_SIZE = 6


class GoalItem:
    __slots__ = ("key", "ru", "cost", "target_min", "done", "done_clock", "source", "winrate")

    def __init__(self, key, cost, target_min, source="static", winrate=None):
        self.key = key
        ru, c = item_ru(key)
        self.ru = ru
        self.cost = int(cost or c or 0)
        self.target_min = int(target_min)
        self.done = False
        self.done_clock = None
        self.source = source          # opendota:timings | opendota:snapshot | cache | static
        self.winrate = winrate

    def to_dict(self):
        return {"key": self.key, "ru": self.ru, "cost": self.cost,
                "target_min": self.target_min, "source": self.source,
                "winrate": self.winrate}


class Builds:
    def __init__(self, cache_path="builds_cache.json", meta_path=None):
        self.cache_path = cache_path
        self.cache: dict = {}
        if os.path.exists(cache_path):
            try:
                self.cache = json.load(open(cache_path, encoding="utf-8"))
            except Exception:
                self.cache = {}
        self.meta_path = meta_path
        self.meta: dict = {}
        self.meta_items: Dict[str, dict] = {}   # key -> {cost, dname}
        self.meta_generated_at = ""
        if meta_path and os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    m = json.load(f)
                self.meta = m.get("heroes") or {}
                self.meta_items = m.get("items") or {}
                self.meta_generated_at = m.get("generated_at") or ""
            except Exception:
                self.meta = {}
        self.hero_ids: Dict[str, int] = {}
        self.item_costs: Dict[str, int] = {}
        self.online = False

    # -------------------------------------------------------------- загрузка
    async def warm_up(self):
        """Константы (герои/цены) + признак сети. Ошибки не фатальны."""
        try:
            heroes = await self._get_json(f"{OD}/constants/heroes", timeout=8)
            if isinstance(heroes, dict):
                for hid, info in heroes.items():
                    name = info.get("name") if isinstance(info, dict) else None
                    if name:
                        self.hero_ids[str(name)] = int(hid)
        except Exception:
            pass
        try:
            items = await self._get_json(f"{OD}/constants/items", timeout=8)
            if isinstance(items, dict):
                for k, v in items.items():
                    if isinstance(v, dict) and isinstance(v.get("cost"), (int, float)):
                        self.item_costs[str(k)] = int(v["cost"])
        except Exception:
            pass
        self.online = bool(self.hero_ids)

    async def _get_json(self, url, timeout=10, params=None):
        async with aiohttp.ClientSession(headers=UA) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=timeout), params=params) as r:
                r.raise_for_status()
                return await r.json()

    # -------------------------------------------------------------- снимок
    def has_meta(self, hero_npc: str) -> bool:
        h = self.meta.get(hero_npc) or {}
        return bool(h.get("item_popularity"))

    def meta_age_days(self) -> Optional[int]:
        if not self.meta_generated_at:
            return None
        try:
            dt = _dt.datetime.fromisoformat(self.meta_generated_at)
            return max(0, (_dt.datetime.now() - dt).days)
        except ValueError:
            return None

    def starting_items(self, hero_npc: str, limit=3) -> List[dict]:
        """Реальные стартовые предметы (частоты из снимка)."""
        h = self.meta.get(hero_npc) or {}
        ip = h.get("item_popularity") or {}
        rows = ip.get("start_game") or []
        out = []
        for key, cnt in rows[:limit]:
            if not key:
                continue
            ru, cost = item_ru(key)
            out.append({"key": key, "ru": ru, "cost": cost, "count": cnt})
        return out

    def benchmarks(self, hero_npc: str) -> dict:
        """Перцентили GPM/ластхитов из снимка (реальные)."""
        h = self.meta.get(hero_npc) or {}
        b = h.get("benchmarks") or {}
        out = {}
        for name, table in (("gpm", b.get("gold_per_min")),
                            ("lh_per_min", b.get("last_hits_per_min"))):
            if table:
                p20 = _p(table, 0.2)
                p50 = _p(table, 0.5)
                p80 = _p(table, 0.8)
                if p50:
                    out[name] = {"p20": int(p20 or 0), "p50": int(p50),
                                  "p80": int(p80 or 0)}
        return out

    # -------------------------------------------------------------- матчапы
    def matchups(self, hero_npc: str) -> Dict[str, dict]:
        """{npc врага: {games, wins, wr}} — реальные вингейты OpenDota."""
        out: Dict[str, dict] = {}
        for row in (self.meta.get(hero_npc) or {}).get("matchups") or []:
            try:
                npc, games, wins = str(row[0]), int(row[1]), int(row[2])
            except (TypeError, ValueError, IndexError):
                continue
            if games:
                out[npc] = {"games": games, "wins": wins, "wr": wins / games}
        return out

    def matchup_vs(self, hero_npc: str, enemy_npc: str) -> Optional[dict]:
        """Вингейт моего героя против конкретного врага (или None)."""
        return self.matchups(hero_npc).get(enemy_npc)

    def meta_win_rate(self, hero_npc: str) -> Optional[tuple]:
        """(win_rate, picks) героя по снимку; None, если нет данных."""
        h = self.meta.get(hero_npc) or {}
        if h.get("win_rate") is not None:
            return h.get("win_rate"), h.get("picks_sample") or 0
        return None

    def luxury_items(self, hero_npc: str, owned: set, top=3) -> List[dict]:
        """Топ лейт-предметы из снимка, которых ещё нет (совет «после кора»)."""
        h = self.meta.get(hero_npc) or {}
        rows = (h.get("item_popularity") or {}).get("late_game") or []
        if not rows:
            return []
        consum = {c.replace("item_", "", 1) for c in CONSUMABLES}
        owned_norm = {str(k).replace("item_", "", 1) for k in owned}
        out = []
        for key, cnt in rows:
            k = str(key)
            if not k or k in consum or k in owned_norm:
                continue
            ru, cost = item_ru(k)
            out.append({"key": k, "ru": ru, "cost": cost, "count": cnt})
            if len(out) >= top:
                break
        return out

    def derive_role(self, hero_npc: str) -> str:
        """Роль по тегам Valve из снимка (для role=auto)."""
        roles = set((self.meta.get(hero_npc) or {}).get("roles") or [])
        if "Support" in roles:
            return "support"
        if "Carry" in roles:
            return "carry"
        if roles & {"Initiator", "Durable"}:
            return "offlane"
        return "carry"

    # -------------------------------------------------------------- план
    async def load_plan(self, hero_npc: str, role: str = "carry") -> List[GoalItem]:
        """План сборки: живые тайминги → снимок → кэш → статический фолбэк."""
        cache_key = f"{hero_npc}:{role}"
        hero_id = self.hero_ids.get(hero_npc) or (self.meta.get(hero_npc) or {}).get("id")

        # 1) живая статистика таймингов
        live_plan: List[GoalItem] = []
        if hero_id:
            try:
                rows = await self._get_json(f"{OD}/scenarios/itemTimings",
                                            timeout=12, params={"hero_id": hero_id})
                live_plan = self._plan_from_timings(rows)
            except Exception:
                pass
        if live_plan:
            plan = self._merge_snapshot(hero_npc, live_plan)
            self._save_cache(cache_key, [g.to_dict() for g in plan])
            return plan

        # 2) офлайн-снимок популярности
        if self.has_meta(hero_npc):
            plan = self._plan_from_snapshot(hero_npc)
            if plan:
                self._save_cache(cache_key, [g.to_dict() for g in plan])
                return plan

        # 3) кэш от прошлых запусков
        cached = self.cache.get(cache_key)
        if cached and time.time() - cached.get("ts", 0) < CACHE_TTL:
            return [GoalItem(d["key"], d["cost"], d["target_min"], d.get("source"), d.get("winrate"))
                    for d in cached["plan"]]

        # 4) аварийная статика (честно помечаем)
        return self._merge_snapshot(hero_npc, [])

    def _plan_from_timings(self, rows: list) -> List[GoalItem]:
        """Кор-итемы по частоте покупок; целевая минута — типичная из данных."""
        if not rows:
            return []
        agg: Dict[str, dict] = {}
        for r in rows:
            key = str(r.get("item") or "")
            if not key or key in CONSUMABLES:
                continue
            try:
                games, wins, t = int(r.get("games") or 0), int(r.get("wins") or 0), int(r.get("time") or 0)
            except (TypeError, ValueError):
                continue
            a = agg.setdefault(key, {"games": 0, "wt": 0, "wins": 0})
            a["games"] += games
            a["wt"] += games * t
            a["wins"] += wins
        picked = []
        for key, a in agg.items():
            if a["games"] < 25:
                continue
            cost = self.item_costs.get(key) or self._snapshot_cost(key) or item_ru(key)[1]
            if cost < CORE_COST_MIN:               # кор-итемы, не мелочь
                continue
            typical_sec = a["wt"] / a["games"]
            if typical_sec > 36 * 60:               # лейт-опции — не цель
                continue
            target_min = max(6, round(typical_sec / 60) + 1)
            wr = round(a["wins"] / a["games"], 3)
            picked.append(GoalItem(key, cost, target_min, "opendota:timings", wr))
        picked.sort(key=lambda g: (g.target_min, -g.cost))
        plan: List[GoalItem] = []
        for g in picked:
            if plan and g.target_min - plan[-1].target_min < 2 and g.key != "black_king_bar":
                continue
            plan.append(g)
            if len(plan) >= PLAN_SIZE:
                break
        return plan

    def _plan_from_snapshot(self, hero_npc: str) -> List[GoalItem]:
        """Офлайн-план из популярности mid/late фаз снимка."""
        ip = (self.meta.get(hero_npc) or {}).get("item_popularity") or {}
        by_key: Dict[str, GoalItem] = {}
        for phase in ("mid_game", "late_game"):
            for key, cnt in ip.get(phase) or []:
                if not key or key in CONSUMABLES or key in by_key:
                    continue
                cost = self._snapshot_cost(key) or item_ru(key)[1]
                if cost < CORE_COST_MIN:
                    continue
                share = 100.0 * cnt / max(1, ip[phase][0][1]) if ip.get(phase) else 0
                if share < 8:                       # берём массовые предметы
                    continue
                g = GoalItem(key, cost, PHASE_TARGET_MIN[phase], "opendota:snapshot")
                by_key[key] = g
        plan = sorted(by_key.values(), key=lambda g: (g.target_min, -g.cost))
        out: List[GoalItem] = []
        for g in plan:
            if out and g.target_min - out[-1].target_min < 2 and g.key != "black_king_bar":
                continue
            out.append(g)
            if len(out) >= PLAN_SIZE:
                break
        return out

    def _merge_snapshot(self, hero_npc: str, live_plan: List[GoalItem]) -> List[GoalItem]:
        """Живой план + массовые предметы из снимка, которых нет в живых данных."""
        by_key = {g.key: g for g in live_plan}
        if self.has_meta(hero_npc):
            for key, target in self._snapshot_gaps(hero_npc, by_key):
                cost = self._snapshot_cost(key) or item_ru(key)[1]
                by_key[key] = GoalItem(key, cost, target, "opendota:snapshot")
        for key, target in (STATIC_BUILDS.get(hero_npc) or [])[:PLAN_SIZE]:
            if key not in by_key:
                cost = self.item_costs.get(key) or self._snapshot_cost(key) or item_ru(key)[1]
                by_key[key] = GoalItem(key, cost, target, "static")
        plan = sorted(by_key.values(), key=lambda g: g.target_min)
        out: List[GoalItem] = []
        for g in plan:
            if (out and g.target_min - out[-1].target_min < 2
                    and g.key != "black_king_bar"):
                continue
            out.append(g)
            if len(out) >= PLAN_SIZE:
                break
        return out

    def _snapshot_gaps(self, hero_npc: str, have: Dict[str, GoalItem]) -> List[tuple]:
        """Массовые mid/late предметы снимка, отсутствующие в плане."""
        ip = (self.meta.get(hero_npc) or {}).get("item_popularity") or {}
        gaps = []
        for phase in ("mid_game", "late_game"):
            rows = ip.get(phase) or []
            top_cnt = rows[0][1] if rows else 1
            for key, cnt in rows[:8]:
                if (not key or key in have or key in CONSUMABLES):
                    continue
                cost = self._snapshot_cost(key) or item_ru(key)[1]
                if cost < CORE_COST_MIN:
                    continue
                if 100.0 * cnt / max(1, top_cnt) >= 25:    # очень массовый
                    gaps.append((key, PHASE_TARGET_MIN[phase]))
        return gaps[:2]

    def _snapshot_cost(self, key: str) -> Optional[int]:
        """Цена предмета из офлайн-снимка (items-константы OpenDota)."""
        info = self.meta_items.get(key)
        if isinstance(info, dict):
            try:
                return int(info.get("cost") or 0) or None
            except (TypeError, ValueError):
                return None
        return None

    def _save_cache(self, key, plan_dicts):
        self.cache[key] = {"ts": time.time(), "plan": plan_dicts}
        try:
            json.dump(self.cache, open(self.cache_path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
        except Exception:
            pass


def _p(table: list, percentile: float):
    """Ближайшее значение перцентиля из таблицы [[p, v], ...]."""
    if not table:
        return None
    return min(table, key=lambda pv: abs(pv[0] - percentile))[1]
