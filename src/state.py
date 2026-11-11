# -*- coding: utf-8 -*-
"""
MatchState — трекер состояния матча Dota 2 из GSI-пакетов.

Сливает частичные POST-пакеты игры (Dota присылает только изменившиеся блоки,
плюс ключи previously/added) в единое состояние и детектит переходы:
смерть Рошана, покупки предметов, смерть/респавн героя, исчезновение врагов
с миникарты, падение башен.

Ключи повторяют официальную схему Dota 2 GSI
(см. библиотеку Dota2GSI: map/player/hero/items/minimap/buildings/events).
"""
from __future__ import annotations

import time as _time
from typing import Any, Dict, List, Optional


def _merge(dst: dict, src: dict):
    for k, v in src.items():
        if k in ("previously", "added"):
            continue
        if k == "minimap":
            dst[k] = v          # миникарта приходит целиком — заменяем (так же делает их агент)
            continue
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _merge(dst[k], v)
        else:
            dst[k] = v


def _walk(d: dict, path=""):
    """Итератор (путь, значение) по вложенным dict/list."""
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, d


def _towers_alive(buildings: dict) -> Dict[str, float]:
    """{путь_башни: hp} из блока buildings (ключи вида team2/team3 → towers)."""
    out: Dict[str, float] = {}
    if not isinstance(buildings, dict):
        return out
    for path, val in _walk(buildings):
        low = path.lower()
        if "tower" in low and isinstance(val, (int, float)):
            out[path] = float(val)
    return out


class MatchState:
    """Единое состояние матча + производные события."""

    def __init__(self):
        self.raw: Dict[str, Any] = {}
        self.last_payload_ts = 0.0
        self.payloads = 0
        # --- производные трекеры ---
        self.seen_items: set = set()          # текущие предметы (инвентарь+стеш)
        self.prev_roshan_state: Optional[str] = None
        self.roshan_death_clock: Optional[float] = None   # секунды clock_time
        self.rosh_death_idx = 0
        self.prev_alive: Optional[bool] = None
        self.prev_gold: float = 0.0
        self.prev_minute = -1
        self.enemy_seen: Dict[str, float] = {}    # npc-имя -> clock последней видимости
        self.enemy_last_known: Dict[str, dict] = {}  # npc-имя -> {x,y,clock}
        self.own_wards_last_placed: Optional[float] = None
        self.hero_key: Optional[str] = None
        self.team: str = "radiant"             # уточняется из player.team_name
        self.aegis_pick_clock: Optional[float] = None
        self.matchid: Optional[str] = None
        self.match_started = False
        self.game_over = False
        self.auth_token_ok: Optional[bool] = None
        # атрибуты, заполняются при каждом update()
        self.recent_purchases: List[str] = []
        self.just_died = False
        self.just_respawned = False
        self.enemy_vanished: List[str] = []
        self.towers_destroyed: List[str] = []
        self.towers_alive: Dict[str, float] = {}
        self.ward_just_placed = False
        # --- день/ночь
        self._daynight: Optional[bool] = None
        self.is_night = False
        self.daynight_changed = False
        # --- счёт видимых врагов
        self.enemy_visible_count = 0

    # ------------------------------------------------------------------ api
    @property
    def map(self) -> dict:
        return self.raw.get("map") or {}

    @property
    def player(self) -> dict:
        return self.raw.get("player") or {}

    @property
    def hero(self) -> dict:
        return self.raw.get("hero") or {}

    @property
    def items(self) -> dict:
        return self.raw.get("items") or {}

    @property
    def minimap(self) -> dict:
        return self.raw.get("minimap") or {}

    @property
    def clock(self) -> float:
        v = self.map.get("clock_time")
        return float(v) if isinstance(v, (int, float)) else 0.0

    @property
    def game_state(self) -> str:
        return str(self.map.get("game_state") or "")

    @property
    def gold(self) -> float:
        v = self.player.get("gold")
        return float(v) if isinstance(v, (int, float)) else 0.0

    @property
    def gpm(self) -> float:
        v = self.player.get("gpm")
        return float(v) if isinstance(v, (int, float)) else 0.0

    def inventory_names(self) -> set:
        """Имена предметов инвентаря/стеша/нейтралки/тп (GSI-имена с item_)."""
        names = set()
        for k, v in self.items.items():
            if k.startswith(("slot", "stash", "teleport", "neutral")) and isinstance(v, dict):
                nm = v.get("name")
                if nm and nm != "empty":
                    names.add(nm)
        return names

    def minimap_elements(self) -> List[dict]:
        els = []
        for k, v in self.minimap.items():
            if not isinstance(v, dict):
                continue
            v = dict(v)
            v.setdefault("_id", k)
            els.append(v)
        return els

    def enemy_heroes(self) -> Dict[str, dict]:
        """Видимые сейчас вражеские герои из элементов миникарты."""
        out = {}
        my_team = 2 if self.team == "radiant" else 3
        for el in self.minimap_elements():
            unit = str(el.get("unitname") or el.get("name") or "")
            if "hero" not in unit:
                continue
            team = el.get("team")
            try:
                team_i = int(team)
            except (TypeError, ValueError):
                team_i = None
            if team_i is None or team_i == my_team:
                continue
            out[unit] = {
                "x": el.get("xpos"), "y": el.get("ypos"),
                "visionrange": el.get("visionrange"),
            }
        return out

    # ------------------------------------------------------------------ update
    def update(self, payload: dict) -> "MatchState":
        """Сливает пакет; возвращает self (события читает advisor через поля)."""
        if not isinstance(payload, dict):
            return self
        self.payloads += 1
        self.last_payload_ts = _time.time()

        prev_snapshot = {
            "clock": self.clock,
            "minute": int(max(self.clock, 0) // 60),
            "roshan": self.map.get("roshan_state"),
            "alive": self.hero.get("alive"),
            "items": set(self.seen_items),
            "towers": _towers_alive(self.raw.get("buildings") or {}),
            "wards_placed": self.player.get("wards_placed"),
            "hero": self.hero.get("name"),
            "game_state": self.game_state,
            "gold": self.gold,
        }

        _merge(self.raw, payload)
        tn = str(self.player.get("team_name") or "").lower()
        if tn in ("radiant", "dire"):
            self.team = tn                      # надёжный источник: игра сама говорит сторону

        # --- идентификация матча/героя/команды
        mid = self.map.get("matchid")
        if mid:
            self.matchid = str(mid)
        if not self.hero_key:
            nm = self.hero.get("name")
            if nm and str(nm).startswith("npc_dota_hero_"):
                self.hero_key = str(nm)
        if self.team == "auto":
            pass
        # авто-определение стороны по позиции героя в начале игры (Radiant: x<0,y<0)
        if self.team == "radiant" and self.clock < 120 and self.hero.get("xpos") is not None:
            try:
                x, y = float(self.hero["xpos"]), float(self.hero.get("ypos") or 0)
                if x > 2000 and y > 2000:
                    self.team = "dire"
            except (TypeError, ValueError):
                pass

        # --- смерть/респавн Рошана
        rs = self.map.get("roshan_state")
        if rs and prev_snapshot["roshan"] and rs != prev_snapshot["roshan"]:
            if ("ALIVE" in str(prev_snapshot["roshan"]).upper()
                    and "ALIVE" not in str(rs).upper()):
                # защита от «мерцания» статуса: новую смерть пишем только если
                # старой нет или она давно устарела (>11 мин)
                if (self.roshan_death_clock is None
                        or self.clock - self.roshan_death_clock > 660):
                    self.roshan_death_clock = self.clock
                    self.rosh_death_idx += 1
        if rs and "ALIVE" in str(rs).upper():
            if self.roshan_death_clock is not None and self.clock - self.roshan_death_clock > 660:
                self.roshan_death_clock = None  # новый цикл

        # --- покупки предметов
        cur_items = self.inventory_names()
        purchased = cur_items - prev_snapshot["items"]
        disappeared = prev_snapshot["items"] - cur_items
        # ушли из инвентаря (проданы/съедены/переехали в courier) — не событие покупки
        self.recent_purchases = sorted(n for n in purchased if n not in disappeared and n not in CONSUMABLE_VIEW)
        self.seen_items = cur_items
        if "item_aegis" in purchased:
            self.aegis_pick_clock = self.clock   # 5 минут считаем с момента подбора

        # --- смерть/респавн героя
        alive = self.hero.get("alive")
        self.just_died = bool(prev_snapshot["alive"] is True and alive is False)
        self.just_respawned = bool(prev_snapshot["alive"] is False and alive is True)

        # --- минута
        self.prev_minute = prev_snapshot["minute"]

        # --- враги на миникарте: появление/исчезновение
        cur_enemy = self.enemy_heroes()
        self.enemy_visible_count = len(cur_enemy)
        for unit, info in cur_enemy.items():
            self.enemy_seen[unit] = self.clock
            self.enemy_last_known[unit] = {
                "x": info["x"], "y": info["y"], "clock": self.clock,
            }
        self.enemy_vanished = [
            u for u in list(self.enemy_seen.keys())
            if u not in cur_enemy and self.clock - self.enemy_seen[u] < 90
        ]
        for u in self.enemy_vanished:
            self.enemy_seen.pop(u, None)

        # --- башни
        now_towers = _towers_alive(self.raw.get("buildings") or {})
        before = prev_snapshot["towers"]
        destroyed = []
        for path, hp in before.items():
            if path not in now_towers or now_towers.get(path, hp) <= 0 < hp:
                destroyed.append(path)
        # у Dota башня при смерти пропадает из блока: ловим исчезновение ключа
        self.towers_destroyed = destroyed
        self.towers_alive = now_towers

        # --- варды (счётчик игрока)
        wp = self.player.get("wards_placed")
        self.ward_just_placed = bool(
            prev_snapshot["wards_placed"] is not None
            and wp is not None and wp != prev_snapshot["wards_placed"]
        )
        if self.ward_just_placed:
            self.own_wards_last_placed = self.clock

        # --- день/ночь (переход фиксируем в каждом пакете)
        daytime = self.map.get("daytime")
        if daytime is not None:
            night = (daytime is False) or bool(self.map.get("nightstalker_night"))
            self.daynight_changed = (self._daynight is not None and night != self._daynight)
            self.is_night = night
            self._daynight = night

        # --- старт/конец
        if not self.match_started and "GAME_IN_PROGRESS" in self.game_state and self.clock >= 0:
            self.match_started = True
        if self.game_state and ("POST_GAME" in self.game_state or self.map.get("win_team")):
            self.game_over = True

        return self

    def roshan_timers(self) -> dict:
        """Таймеры Рошана для панели."""
        rs = str(self.map.get("roshan_state") or "")
        end_s = self.map.get("roshan_state_end_seconds")
        info = {"state": rs, "respawn_in": None, "window": None}
        if self.roshan_death_clock is not None:
            d = self.roshan_death_clock
            info["window"] = (d + 480, d + 660)      # 8–11 минут после смерти
            info["aegis_until"] = d + 300
        if isinstance(end_s, (int, float)) and end_s > 0:
            info["respawn_in"] = float(end_s)
        return info

    def fmt_clock(self) -> str:
        c = int(self.clock)
        return f"{c // 60:02d}:{c % 60:02d}"


# GSI-предметы, которые мы считаем «информационными», а не покупкой-кор-итемом
CONSUMABLE_VIEW = set()


def mmss(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"
