# -*- coding: utf-8 -*-
"""
simulate_match — демо без запуска Dota 2: проигрывает сценарий реального матча
(жирные GSI-пакеты по официальной схеме) на живой сервер тренера.

Сценарий ~24 минуты: сборка Джаггернаута, вода/руны, покупка БФ и БКБ,
смерть Рошана и окно респавна, пропавший из вижена Пудж, падение вражеской
башни и связка «отпушь бот — стягивайся к Рошану», ГPM-чеки.

    python tools/simulate_match.py                    # скорость x20
    python tools/simulate_match.py --speed 60         # быстрее
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import aiohttp

AUTH = {"token": "vasilisk_2026"}
HERO = "npc_dota_hero_juggernaut"


def P(game_time, **kw):
    """Основа пакета: карта."""
    clock = game_time
    m = {"name": "dota", "matchid": "7700000001", "game_time": game_time,
         "clock_time": clock, "game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS",
         "paused": False, "daytime": True, "nightstalker_night": False,
         "radiant_score": 0, "dire_score": 0,
         "radiant_ward_purchase_cooldown": 0.0, "dire_ward_purchase_cooldown": 0.0,
         "roshan_state": "DOTA_ROSHAN_STATE_ALIVE", "roshan_state_end_seconds": 0}
    m.update(kw)
    return m


def player_block(game_time, gold, lh, kills=0, deaths=0, gpm=0, net=0, wards=0):
    return {
        "steamid": "76561198000000001", "accountid": 100000001,
        "name": "ALLENAFS", "team_slot": 0, "player_slot": 0,
        "kills": kills, "deaths": deaths, "assists": 0,
        "last_hits": lh, "denies": 5, "kill_streak": 0, "commands_issued": 400,
        "gold": gold, "gold_reliable": gold // 2, "gold_unreliable": gold // 2,
        "gpm": gpm, "xpm": gpm, "net_worth": net,
        "wards_purchased": wards, "wards_placed": wards, "wards_destroyed": 0,
        "runes_activated": 0, "camps_stacked": 1,
        "hero_damage": 0, "hero_healing": 0, "tower_damage": 0,
    }


def hero_block(alive=True, respawn=0, x=-4000, y=-4000, level=1, hp=800, mhp=800):
    return {
        "id": 8, "name": HERO, "level": level, "xp": 0,
        "alive": alive, "respawn_seconds": respawn,
        "buyback_cost": 800, "buyback_cooldown": 0,
        "health": hp, "max_health": mhp, "mana": 300, "max_mana": 500,
        "xpos": x, "ypos": y, "smoked": False, "silenced": False, "stunned": False,
    }


def items_block(inv, stash=()):
    b = {}
    for i, name in enumerate(inv):
        b[f"slot{i}"] = {"name": name, "purchaser": 0, "item_level": 0,
                         "can_cast": True, "cooldown": 0}
    for i, name in enumerate(stash):
        b[f"stash{i}"] = {"name": name, "purchaser": 0}
    return b


def minimap_block(elements):
    """elements: список (id, team, unitname, x, y, vision)"""
    mm = {}
    for i, (team, unit, x, y) in enumerate(elements):
        mm[f"o{i}"] = {"team": team, "unitname": unit, "name": unit,
                        "xpos": x, "ypos": y, "yaw": 0,
                        "visionrange": 1800, "remainingtime": -1,
                        "eventduration": 0, "image": "icon"}
    return mm


def is_day(t):
    """День/ночь для демо: 5-минутные половины от 0:00 (как в Dota)."""
    return (int(t) // 300) % 2 == 0


def towers_block(bot2_hp=1300, top1_hp=1000, mid2_dire=1400):
    """Здоровья башен Dire (врагов) и Radiant."""
    return {
        "team3": {
            "badguys_tower1_bot": {"health": 1400, "max_health": 1400},
            "badguys_tower2_bot": {"health": bot2_hp, "max_health": 1300},
            "badguys_tower1_top": {"health": top1_hp, "max_health": 1400},
            "badguys_tower2_mid": {"health": mid2_dire, "max_health": 1300},
        },
        "team2": {
            "goodguys_tower1_bot": {"health": 1400, "max_health": 1400},
            "goodguys_tower2_bot": {"health": 1300, "max_health": 1300},
        },
    }


# ------------------------------------------------------------------ сценарий
async def run(uri, speed):
    timeout = aiohttp.ClientTimeout(total=5)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async def post(payload, label=""):
            try:
                async with s.post(uri, json=payload) as r:
                    pass
                if label:
                    print(f"    [sim] {label}")
            except Exception as e:
                print(f"    [sim] ошибка POST: {e}")
                raise SystemExit(1)

        async def tick(t, gold=0, lh=0, kills=0, deaths=0, gpm=0, net=0,
                       inv=(), stash=(), roshan="DOTA_ROSHAN_STATE_ALIVE",
                       rsend=0, elements=(), towers=None, ward_cd=0.0,
                       alive=True, respawn=0, level=1, daytime=None):
            dt = is_day(t) if daytime is None else daytime
            p = {"auth": AUTH, "provider": {"name": "dota", "appid": 570},
                 "map": P(t, roshan_state=roshan, roshan_state_end_seconds=rsend,
                           radiant_ward_purchase_cooldown=ward_cd, daytime=dt),
                 "player": player_block(t, gold, lh, kills, deaths, gpm, net),
                 "hero": hero_block(alive, respawn, level=level),
                 "items": items_block(inv, stash),
                 "minimap": minimap_block(elements)}
            if towers is not None:
                p["buildings"] = towers
            await post(p)

        base = {"inv": ["item_tango", "item_quelling_blade", "item_slippers"]}

        print("=== 0:00 прегейм/пик")
        await tick(-90, gold=600, lh=0, inv=base["inv"], roshan="DOTA_ROSHAN_STATE_UNKNOWN")
        await asyncio.sleep(0.3 / speed)

        print("=== 0:00 старт")
        await tick(0, gold=600, lh=0, inv=base["inv"])
        await asyncio.sleep(0.4 / speed)

        # --- 0..8 минута: фарм
        for t in [30, 60, 90, 120, 150, 180, 240, 300, 360, 420, 460]:
            els = [(3, "npc_dota_hero_sniper", -1200, 4200)] if t == 360 else ()
            # Снайпер — реальный жёсткий контрпик Джаггернаута (41% по OpenDota)
            await tick(t, gold=300 + t, lh=min(60, t // 9), gpm=520,
                       inv=base["inv"] + (["item_power_treads"] if t >= 470 else []),
                       elements=els)
            await asyncio.sleep(0.25 / speed)

        # --- 8:00: ПТ куплен (в инвентаре появился)
        print("=== 8:00 куплены ПТ")
        inv = ["item_tango", "item_quelling_blade", "item_power_treads", "item_falcon_blade"]
        await tick(480, gold=1500, lh=62, gpm=560, inv=inv, level=11)
        await asyncio.sleep(0.5 / speed)

        # --- 10:00 GPM-чек (gpm низкий → совет)
        print("=== 10:00 GPM-чек")
        await tick(600, gold=2100, lh=74, gpm=430, inv=inv, level=13)
        await asyncio.sleep(0.5 / speed)

        # --- 12:00 вражеский Пудж виден у топ-руны, потом пропадает
        print("=== 12:00 Пудж в вижене → пропадает (ганк-предупреждение)")
        await tick(720, gold=2900, lh=90, gpm=440, inv=inv, level=14,
                   elements=[(3, "npc_dota_hero_pudge", 2600, 4700)])
        await asyncio.sleep(0.4 / speed)
        await tick(745, gold=2950, lh=92, gpm=440, inv=inv, level=14,
                   elements=[])
        await asyncio.sleep(0.5 / speed)

        # --- 13:30 куплен БФ
        print("=== 13:30 Батл фьюри собран")
        inv = ["item_power_treads", "item_falcon_blade", "item_bfury"]
        await tick(810, gold=400, lh=110, gpm=520, inv=inv, level=15)
        await asyncio.sleep(0.5 / speed)

        # --- 14:00 Рошан умер
        print("=== 14:00 Рошан пал")
        await tick(840, gold=700, lh=118, gpm=530, inv=inv, level=16,
                   roshan="DOTA_ROSHAN_STATE_DEAD", rsend=560)
        await asyncio.sleep(0.5 / speed)

        # --- 14:20 аегис подобран (совет «живи 5 минут и толкай»)
        print("=== 14:20 аегис подобран")
        await tick(860, gold=700, lh=120, gpm=530, inv=inv + ["item_aegis"], level=16,
                   roshan="DOTA_ROSHAN_STATE_DEAD", rsend=540)
        await asyncio.sleep(0.5 / speed)

        # --- 15:30 куплен обсервер (совет куда ставить); Рошан мёртв
        print("=== 15:30 куплен обсервер")
        await tick(930, gold=1200, lh=140, gpm=540, inv=inv + ["item_ward_observer"],
                   level=17, roshan="DOTA_ROSHAN_STATE_DEAD", rsend=470)
        await asyncio.sleep(0.5 / speed)

        # --- 17:00 золото на БКБ копится
        print("=== 17:00 идёт фарм на БКБ; Зевс в вижене (матчап-перевес)")
        await tick(1020, gold=3300, lh=180, gpm=560, inv=inv, level=18,
                   roshan="DOTA_ROSHAN_STATE_DEAD", rsend=380,
                   elements=[(3, "npc_dota_hero_zuus", -2000, 3000)])
        await asyncio.sleep(0.4 / speed)
        await tick(1080, gold=3900, lh=195, gpm=570, inv=inv, level=19,
                   roshan="DOTA_ROSHAN_STATE_DEAD", rsend=320,
                   elements=[(3, "npc_dota_hero_zuus", -1900, 3100)])
        await asyncio.sleep(0.5 / speed)

        # --- 18:30 смерть и байбек-подсказка
        print("=== 18:30 смерть (байбек-чек)")
        await tick(1110, gold=4100, lh=200, gpm=565, inv=inv, level=19,
                   alive=False, respawn=48, roshan="DOTA_ROSHAN_STATE_DEAD", rsend=290)
        await asyncio.sleep(0.6 / speed)
        await tick(1160, gold=4300, lh=200, gpm=560, inv=inv, level=19,
                   alive=True, respawn=0, roshan="DOTA_ROSHAN_STATE_DEAD", rsend=240)
        await asyncio.sleep(0.4 / speed)

        # --- 19:15 БКБ куплен (их пример: «добрать БКБ»)
        print("=== 19:15 БКБ собран")
        inv = ["item_power_treads", "item_falcon_blade", "item_bfury", "item_black_king_bar"]
        await tick(1155, gold=50, lh=205, gpm=580, inv=inv, level=20,
                   roshan="DOTA_ROSHAN_STATE_DEAD", rsend=245)
        await asyncio.sleep(0.6 / speed)

        # --- 20:00 смок-напоминание + вражеская Т2(бот) падает → «отпушь бот…»
        print("=== 20:10 вражеская Т2(бот) пала")
        await tick(1200, gold=600, lh=220, gpm=590, inv=inv, level=21,
                   towers=towers_block(bot2_hp=200), roshan="DOTA_ROSHAN_STATE_DEAD", rsend=200)
        await asyncio.sleep(0.3 / speed)
        await tick(1210, gold=640, lh=224, gpm=590, inv=inv, level=21,
                   towers=towers_block(bot2_hp=0), roshan="DOTA_ROSHAN_STATE_DEAD", rsend=190)
        await asyncio.sleep(0.4 / speed)

        # --- 22:00 окно Рошана открывается (14:00 + 8 мин)
        print("=== 22:00 окно Рошана открылось")
        await tick(1320, gold=1100, lh=250, gpm=595, inv=inv, level=22,
                   roshan="DOTA_ROSHAN_STATE_DEAD", rsend=60)
        await asyncio.sleep(0.6 / speed)

        # --- 23:40 Рошан заспавнился
        print("=== 23:40 Рошан заспавнился")
        await tick(1420, gold=1600, lh=270, gpm=600, inv=inv, level=23,
                   roshan="DOTA_ROSHAN_STATE_ALIVE")
        await asyncio.sleep(0.6 / speed)

        # --- 24:00 конец
        print("=== 24:00 конец матча")
        p = {"auth": AUTH,
             "map": P(1440, win_team="radiant", game_state="DOTA_GAMERULES_STATE_POST_GAME"),
             "player": player_block(1440, 1800, 280, 14, 3, 600, 21000),
             "hero": hero_block(True, 0, level=25),
             "items": items_block(inv)}
        await post(p, "post-game")
        print("=== симуляция завершена — смотри лог тренера")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="http://127.0.0.1:9001/")
    ap.add_argument("--speed", type=float, default=6, help="игровых секунд за 0.1 реальной секунды")
    a = ap.parse_args()
    asyncio.run(run(a.uri.rstrip("/") + "/", a.speed))
