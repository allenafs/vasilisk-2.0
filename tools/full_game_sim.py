# -*- coding: utf-8 -*-
"""
full_game_sim — СКВОЗНАЯ симуляция ОДНОЙ ПОЛНОЙ игры Dota 2 вместе с тренером:

  этап 1  «запуск Dota 2»: клиент с GSI-конфигом подключается к тренеру
  этап 2  загрузка карты → пик героя → стратегия (прегейм-советы)
  этап 3  матч ~36 минут: лейнинг → мидгейм → лейт → трон
  этап 4  пост-гейм (win_team) → финальный совет тренера

Пакеты — официальная схема GSI (map/player/hero/items/minimap/buildings),
причём как их реально шлёт клиент: ЧАСТИЧНЫЕ блоки (только изменившееся)
+ heartbeat каждые ~5 секунд игровых событий.

Сценарий (Radiant, Джаггернаут-керри, сапог 36 минут):
  покупки строго по плану OpenDota: ПТ(8:00) → Фалькон(9:30) → Батл фьюри(13:50)
  → Yasha(18:00) → Мьолнир(23:30) → Манта(24:30); БКБ вне плана (26:00);
  Рошан №1 на 14:00 (наш аегис), №2 на 26:30 (забрали враги);
  матчапы: Снайпер 41% (жёсткий), Зевс 67% (комфорт);
  смерть на 19:10 (байбек-подсказка) и в драке на 30:10;
  башни: наша Т1(топ) 11:00, их Т1(бот) 16:00, Т2(бот) 20:10, Т3(бот) 33:00;
  смок-группировка врага на 22:00; трон Dire на 36:30.

    python tools/full_game_sim.py             # скорость x1 (реальное время!)
    python tools/full_game_sim.py --speed 12  # 12 игровых секунд за реальную
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import aiohttp

AUTH = {"token": "vasilisk_2026"}
HERO = "npc_dota_hero_juggernaut"
MATCHID = "7700000002"

# игровые состояния (как в клиенте)
S_WAIT = "DOTA_GAMERULES_STATE_WAIT_FOR_MAP_TO_LOAD"
S_PICK = "DOTA_GAMERULES_STATE_HERO_SELECTION"
S_STRAT = "DOTA_GAMERULES_STATE_STRATEGY_TIME"
S_PRE = "DOTA_GAMERULES_STATE_PRE_GAME"
S_PLAY = "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"
S_POST = "DOTA_GAMERULES_STATE_POST_GAME"
R_ALIVE, R_DEAD, R_UNK = ("DOTA_ROSHAN_STATE_ALIVE",
                          "DOTA_ROSHAN_STATE_DEAD",
                          "DOTA_ROSHAN_STATE_UNKNOWN")

T_FOUNTAIN = (-4700, -4700)   # Radiant фонтан
T_BOT_LANE = (1400, -4000)    # бот-лейн (наш)
T_JUNGLE = (-300, -3100)      # наш лес

# ------------------------------------------------------------------ блоки GSI
def map_block(t, state, *, rs=R_ALIVE, rsend=0, day=True, score=(0, 0),
              wcd=0.0, ns_night=False, win_team=None):
    m = {
        "name": "dota", "matchid": MATCHID,
        "game_time": t + 125, "clock_time": t,
        "game_state": state, "paused": False,
        "daytime": day, "nightstalker_night": ns_night,
        "radiant_score": score[0], "dire_score": score[1],
        "radiant_ward_purchase_cooldown": wcd,
        "dire_ward_purchase_cooldown": 135.0,
        "roshan_state": rs, "roshan_state_end_seconds": rsend,
    }
    if win_team:
        m["win_team"] = win_team
    return m


def player_block(gold, lh, kills=0, deaths=0, assists=0, gpm=0, net=600,
                 wards_pur=0, wards_pl=0, dmg=0):
    return {
        "steamid": "76561198000000001", "accountid": 100000001,
        "name": "ALLENAFS", "team_slot": 0, "player_slot": 0,
        "kills": kills, "deaths": deaths, "assists": assists,
        "last_hits": lh, "denies": 5 + lh // 12, "kill_streak": 0,
        "commands_issued": 800 + lh * 4,
        "gold": gold, "gold_reliable": gold // 3, "gold_unreliable": 2 * gold // 3,
        "gpm": gpm, "xpm": gpm, "net_worth": net,
        "wards_purchased": wards_pur, "wards_placed": wards_pl,
        "wards_destroyed": 0, "runes_activated": 4, "camps_stacked": 2,
        "hero_damage": dmg, "hero_healing": 0, "tower_damage": dmg // 3,
    }


def hero_block(level=1, hp=None, mana=None, pos=T_BOT_LANE, alive=True,
               respawn=0, bb_cost=800, smoked=False):
    max_hp = 560 + level * 66
    max_mana = 240 + level * 40
    return {
        "id": 8, "name": HERO, "level": level, "xp": level * 100,
        "alive": alive, "respawn_seconds": respawn,
        "buyback_cost": bb_cost, "buyback_cooldown": 0,
        "health": hp if hp is not None else max_hp,
        "max_health": max_hp,
        "mana": mana if mana is not None else int(max_mana * 0.55),
        "max_mana": max_mana,
        "xpos": pos[0], "ypos": pos[1],
        "smoked": smoked, "silenced": False, "stunned": False,
    }


def items_block(inv, stash=(), tp="item_tpscroll"):
    b = {}
    for i, name in enumerate(inv):
        b[f"slot{i}"] = {"name": name, "purchaser": 0, "item_level": 0,
                         "can_cast": True, "cooldown": 0}
    for i, name in enumerate(stash):
        b[f"stash{i}"] = {"name": name, "purchaser": 0}
    b["teleport0"] = {"name": tp, "purchaser": 0, "item_level": 0,
                      "can_cast": True, "cooldown": 0}
    return b


def minimap_block(elements):
    mm = {}
    for i, (team, unit, x, y) in enumerate(elements):
        mm[f"o{i}"] = {"team": team, "unitname": unit, "name": unit,
                       "xpos": x, "ypos": y, "yaw": 0,
                       "visionrange": 1800, "remainingtime": -1,
                       "eventduration": 0, "image": "icon"}
    return mm


def buildings_delta(towers=()):
    """towers: [(team_key, name, hp)] — частичный блок изменений."""
    b = {}
    for team_key, name, hp in towers:
        b.setdefault(team_key, {})[name] = {
            "health": hp, "max_health": 1800 if "tower4" not in name else 2600}
    return b


FULL_ENEMY = {  # состав врага (Dire)
    "sniper": ("npc_dota_hero_sniper", (-1000, -3500), "бот"),
    "pudge": ("npc_dota_hero_pudge", (1200, 3800), "топ"),
    "zuus": ("npc_dota_hero_zuus", (-2000, 2000), "мид"),
    "pa": ("npc_dota_hero_phantom_assassin", (-1400, 1000), "мид"),
    "lion": ("npc_dota_hero_lion", (-1600, 900), "мид"),
}


def mm(*keys):
    """Собрать миникарту из ключей FULL_ENEMY (+ свои герои при 'cm','axe'…)."""
    els = [(3, FULL_ENEMY[k][0], *FULL_ENEMY[k][1]) for k in keys if k in FULL_ENEMY]
    own = {"cm": (2, "npc_dota_hero_crystal_maiden", (1500, -4100)),
           "axe": (2, "npc_dota_hero_axe", (-500, -3800)),
           "storm": (2, "npc_dota_hero_storm_spirit", (-1800, 1900))}
    for k in keys:
        if k in own:
            els.append(own[k])
    return els


# ------------------------------------------------------------------ сценарий
class Sim:
    def __init__(self, session, uri, speed):
        self.s = session
        self.uri = uri
        self.speed = speed
        self.sent = 0
        # «жизнь» игрока
        self.inv = []
        self.tp = "item_tpscroll"
        self.gold = 0
        self.lh = 0
        self.gpm = 0
        self.level = 1
        self.kills = self.deaths = self.assists = 0
        self.net = 600
        self.dmg = 0
        self.wards_pur = self.wards_pl = 0
        self.dead_at = None          # clock смерти (для респавна)

    # --- служебное ------------------------------------------------------
    async def post(self, payload, comment=None):
        try:
            async with self.s.post(self.uri, json=payload,
                                   timeout=aiohttp.ClientTimeout(total=10)) as r:
                pass
        except Exception as e:
            print(f"    [sim] ошибка POST: {e}")
            raise SystemExit(1)
        self.sent += 1
        if comment:
            c = int(max(comment[0], 0))
            print(f"[{c // 60:02d}:{c % 60:02d}] (dota) {comment[1]}")
        await asyncio.sleep(0.05 / self.speed)

    def respawn_sec(self, t):
        if self.dead_at is None:
            return 0
        return max(0, int(self.dead_at + 48 + (60 if t > 1800 else 0) - t))

    # --- один кадр игры --------------------------------------------------
    async def frame(self, t, state=S_PLAY, *, rs=R_ALIVE, rsend=0, day=True,
                    score=(0, 0), elements=None, towers=(), wcd=0.0,
                    win_team=None, blocks="full", comment=None, hp=None,
                    mana=None, pos=T_BOT_LANE, smoked=False, ns_night=False):
        """blocks: 'full' — все блоки; 'map' — heartbeat (только карта)."""
        p = {"auth": AUTH,
             "provider": {"name": "dota", "appid": 570, "timestamp": t + 3},
             "map": map_block(t, state, rs=rs, rsend=rsend, day=day, score=score,
                             wcd=wcd, win_team=win_team, ns_night=ns_night)}
        if blocks != "map":
            alive = self.dead_at is None
            respawn = self.respawn_sec(t)
            p["player"] = player_block(
                int(self.gold), self.lh, self.kills, self.deaths, self.assists,
                int(self.gpm), int(self.net), self.wards_pur, self.wards_pl,
                int(self.dmg))
            p["hero"] = hero_block(self.level, hp=hp, mana=mana, pos=pos,
                                   alive=alive, respawn=respawn,
                                   bb_cost=800 if t < 1500 else 900,
                                   smoked=smoked)
            p["items"] = items_block(self.inv, tp=self.tp)
            if elements is not None:
                p["minimap"] = minimap_block(elements)
            if towers:
                p["buildings"] = buildings_delta(towers)
        await self.post(p, comment)


async def run(uri, speed):
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        sim = Sim(s, uri, speed)

        # ============ ЭТАП 1: «запуск Dota 2» ===============================
        print("=== [1] ЗАПУСК STEAM + DOTA 2 (симуляция реального клиента) ===")
        print("[steam] Steam.exe запущен, вошли в аккаунт ALLENAFS")
        print("[dota2 ] dota2.exe -novid -language russian")
        print("[gsi   ] подключён конфиг gamestate_integration_vasilisk.cfg")
        print("[gsi   ] цель POST: http://127.0.0.1:9001/  token=vasilisk_2026")
        print("[gsi   ] ждём соединения с тренером…")
        await asyncio.sleep(1.0)

        print()
        print("=== [2] ЗАГРУЗКА КАРТЫ И ПИК ГЕРОЕВ ===")
        await sim.frame(-125, S_WAIT, rs=R_UNK, blocks="map",
                       comment=(-125, "клиент загрузился, карта в памяти"))
        await sim.frame(-120, S_PICK, rs=R_UNK, blocks="map",
                       comment=(-120, "экран пика: выбираем героя"))
        sim.gold, sim.gpm, sim.lh, sim.net = 600, 0, 0, 600
        await sim.frame(-95, S_STRAT, blocks="map",
                       comment=(-95, "ПИК: Джаггернаут (Radiant, позиция 1)"))
        await sim.frame(-94, S_STRAT, rs=R_UNK, blocks="full",
                       elements=[],
                       comment=(-94, "GSI прислал блок hero — тренер видит героя"))

        # закупка на страте
        sim.inv = ["item_tango", "item_branches", "item_quelling_blade"]
        sim.gold = 260
        await sim.frame(-90, S_STRAT, rs=R_UNK,
                       comment=(-90, "куплены стартовые предметы (Tango/Branches/QB)"))
        await sim.frame(-45, S_PRE, rs=R_UNK, blocks="map",
                       comment=(-45, "пре-гейм, крипы на подходе"))
        await sim.frame(-15, S_PRE, rs=R_UNK, blocks="map",
                       comment=(-15, "закрываем лагеря, встаём на линию"))

        # ============ ЭТАП 3: МАТЧ ==========================================
        print()
        print("=== [3] МАТЧ: 0:00 → 36:30 (Radiant vs Dire) ===")

        # --- тайминги покупок/событий (анкоры) ---------------------------
        ANCH = {
            240: dict(elements=mm("sniper"), comment=(240, "на лайне виден их керри Снайпер")),
            270: dict(elements=[], comment=(270, "Снайпер пропал из вижена")),
            480: dict(inv_a=["item_power_treads"], spend=1400, lh=62, level=11,
                      gold=1500, gpm=520, comment=(480, "КУПЛЕН Power Treads (по плану, 8:00)")),
            570: dict(inv_a=["item_falcon_blade"], spend=1125, lh=70, level=12,
                      gold=1225, gpm=525, comment=(570, "КУПЛЕН Falcon Blade (по плану, 9:30)")),
            600: dict(gpm=430, lh=68, comment=(600, "GPM просел (430) — тренер должен заметить")),
            660: dict(towers=[("team2", "goodguys_tower1_top", 0)],
                      score=(2, 1), comment=(660, "НАША Т1(топ) пала — враги продавили топ")),
            720: dict(elements=mm("pudge"), comment=(720, "их Пудж роумит у топ-руны")),
            750: dict(elements=[], tp="empty",
                      comment=(750, "Пудж пропал; наш ТП израсходован")),
            830: dict(inv_a=["item_bfury"], inv_r=["item_quelling_blade"], spend=3900,
                      lh=110, level=15, gold=4000, gpm=530,
                      comment=(830, "КУПЛЕН Battle Fury (по плану, 13:50)")),
            840: dict(rs=R_DEAD, rsend=580, score=(3, 1),
                      comment=(840, "команда убила РОШАНА №1")),
            860: dict(inv_a=["item_aegis"], comment=(860, "мы подобрали АЕГИС")),
            900: dict(inv_a=["item_ward_observer"], wards_pur=1, gold=1300,
                      comment=(900, "куплен Observer Ward (золотой на варды)")),
            930: dict(wards_pl=1, comment=(930, "вард поставлен на хайграунд топ")),
            960: dict(towers=[("team3", "badguys_tower1_bot", 0)], score=(4, 2),
                      comment=(960, "ИХ Т1(бот) пала — наш пуш")),
            1020: dict(elements=mm("zuus"), pos=(1000, -3800),
                       comment=(1020, "их Зевс показался на миде")),
            1080: dict(inv_a=["item_yasha"], spend=2100, lh=200, level=18,
                      gold=2200, gpm=560, elements=[],
                       comment=(1080, "КУПЛЕН Yasha (по плану, 18:00)")),
            1140: dict(inv_r=["item_aegis"],
                       comment=(1140, "аегис истёк")),
            1150: dict(dead=True, gold=4100, score=(6, 3),
                       comment=(1150, "СМЕРТЬ №1 (ганк Пуджа) — золото на байбек есть")),
            1198: dict(revive=True, lh=205, comment=(1198, "возрождение в фонтане")),
            1200: dict(gpm=690, pos=T_JUNGLE,
                       comment=(1200, "20:00 — фарм леса после респавна")),
            1210: dict(towers=[("team3", "badguys_tower2_bot", 0)], score=(7, 3),
                       comment=(1210, "ИХ Т2(бот) пала — открываем карту")),
            1310: dict(elements=mm("sniper", "pa", "lion"), pos=(500, -3400),
                       comment=(1310, "трое врагов кучкуются у мид-ривера")),
            1320: dict(inv_a=["item_smoke_of_deceit"], elements=[], smoked=True,
                       gold=1800, comment=(1320, "враги СМОКНУЛИСЬ; мы тоже взяли смок")),
            1350: dict(inv_r=["item_smoke_of_deceit"], smoked=False,
                       comment=(1350, "смок использован — идём на Рошана")),
            1410: dict(inv_a=["item_mjollnir"], spend=5500, lh=310, level=22,
                      gold=5600, gpm=620, score=(8, 5),
                      comment=(1410, "КУПЛЕН Mjollnir (по плану, 23:30)")),
            1420: dict(rs=R_ALIVE, comment=(1420, "РОШАН заспавнился")),
            1470: dict(inv_a=["item_manta"], inv_r=["item_yasha", "item_falcon_blade"],
                       spend=4650, lh=340, level=23, gold=4700,
                       comment=(1470, "КУПЛЕНА Manta (Yasha+recipe, по плану)")),
            1500: dict(gold=5400, gpm=640, kills=3, assists=4,
                       comment=(1500, "25:00 — копим на байбек и следующий итем")),
            1560: dict(inv_a=["item_black_king_bar"], spend=4050, gold=4100,
                       kills=4, comment=(1560, "КУПЛЕН BKB (вне плана — под их Зевса/Лайона)")),
            1590: dict(rs=R_DEAD, rsend=640, score=(10, 6),
                       comment=(1590, "враги забрали РОШАНА №2 (аегис у их ПА)")),
            1620: dict(inv_a=["item_gem"], spend=900, gold=900,
                       comment=(1620, "КУПЛЕН Gem — вычищаем их варды перед пушем")),
            1800: dict(elements=mm("sniper", "pa", "lion"), pos=(2600, -3900),
                       kills=5, score=(12, 8), hp=1400,
                       comment=(1800, "30:00 — нас находят: завязывается ДРАКА")),
            1810: dict(dead=True, gold=5200, score=(13, 9), hp=0,
                       elements=mm("sniper", "pa", "lion"),
                       comment=(1810, "СМЕРТЬ №2 в замесе — есть золото на байбек")),
            1870: dict(revive=True, kills=6, comment=(1870, "выкупились из смерти, вернулись в бой")),
            1980: dict(towers=[("team3", "badguys_tower3_bot", 0)], score=(17, 12),
                       kills=8, elements=mm("cm", "axe", "sniper", "pa"),
                       comment=(1980, "ИХ Т3(бот) пала — хайграунд открыт")),
            2040: dict(towers=[("team3", "badguys_melee_barracks_bot", 0),
                               ("team3", "badguys_ranged_barracks_bot", 0)],
                       score=(20, 13), kills=10,
                       elements=mm("cm", "axe", "storm", "sniper"),
                       comment=(2040, "бараки бота снесены — мега-крипы близко")),
            2100: dict(towers=[("team3", "badguys_tower4_1", 0),
                               ("team3", "badguys_tower4_2", 0)],
                       score=(22, 14), kills=12, wcd=2.0,
                       comment=(2100, "их Т4 пали — ТРОН открыт, варды с кулдауна")),
            2190: dict(final=True, comment=(2190, "ТРОН DIRE РАЗРУШЕН — победа!")),
        }

        score = (0, 0)
        for t in range(0, 2191, 5):
            a = ANCH.get(t)
            # день/ночь: 5-минутные половины
            day = (int(t) // 300) % 2 == 0
            # плавные кривые между анкорами
            sim.net = int(600 + t * 10.5)
            sim.dmg = int(t * 30)

            if a:
                if a.get("final"):
                    sim.gold, sim.gpm, sim.lh, sim.level = 3000, 650, 560, 25
                    sim.kills, sim.deaths, sim.assists = 14, 2, 9
                    await sim.frame(
                        t, S_POST, rs=R_ALIVE, day=day, score=(24, 16),
                        win_team="radiant", elements=[],
                        towers=[("team3", "badguys_tower4_1", 0)],
                        comment=a["comment"])
                    continue
                if "score" in a:
                    score = a["score"]
                if "gold" in a:
                    sim.gold = a["gold"]
                if "gpm" in a:
                    sim.gpm = a["gpm"]
                if "lh" in a:
                    sim.lh = a["lh"]
                if "level" in a:
                    sim.level = a["level"]
                if "kills" in a:
                    sim.kills = a["kills"]
                if a.get("dead"):
                    sim.dead_at = t
                    sim.deaths += 1
                if a.get("revive"):
                    sim.dead_at = None
                    sim.pos_hint = T_FOUNTAIN
                for k in a.get("inv_a", []):
                    if k not in sim.inv:
                        sim.inv.append(k)
                for k in a.get("inv_r", []):
                    if k in sim.inv:
                        sim.inv.remove(k)
                if "spend" in a:
                    sim.gold = max(0, int(sim.gold - a["spend"]))
                if "tp" in a:
                    sim.tp = a["tp"]
                if "wards_pur" in a:
                    sim.wards_pur = a["wards_pur"]
                if "wards_pl" in a:
                    sim.wards_pl = a["wards_pl"]
                rsend = a.get("rsend", 0)
                rs = a.get("rs", R_ALIVE)
                # Рошан: обратный отсчёт респавна
                if rs == R_DEAD:
                    respawn_at = t + rsend
                    rsend = max(0, respawn_at - t)
                else:
                    rsend = 0
                # после смерти Рошана — держим счётчик до респавна
                if rs == R_ALIVE and t < 2000:
                    # жив (или до первой смерти — просто жив)
                    pass
                await sim.frame(
                    t, S_PLAY, rs=rs, rsend=rsend if rs == R_DEAD else 0,
                    day=day, score=score,
                    elements=a.get("elements", mm()) if "elements" in a else None,
                    towers=a.get("towers", ()), wcd=a.get("wcd", 0.0),
                    hp=a.get("hp"), pos=a.get("pos", T_BOT_LANE),
                    smoked=a.get("smoked", False),
                    comment=a["comment"])
                continue

            # обычный кадр (heartbeat «только карта» на :50, иначе полный)
            kind = "map" if t % 60 == 50 else ("small" if t % 30 == 5 else "full")
            # Рошан в обычных кадрах: мёртв до анкора возрождения
            if 840 <= t < 1420:
                rs, rsend = R_DEAD, max(0, 1420 - t)
            elif 1590 <= t < 2230:
                rs, rsend = R_DEAD, max(0, 2230 - t)
            else:
                rs, rsend = R_ALIVE, 0
            # золото капает между покупками
            if sim.gold < 6000:
                sim.gold = int(min(6000, sim.gold + 6 * 5))
            if t % 30 == 0:
                sim.lh = int(sim.lh + 7 * 2.5) if t > 30 else sim.lh
            sim.gpm = 520 if t < 600 else (560 if t < 1080 else 640)
            if kind == "map":
                await sim.frame(t, S_PLAY, rs=rs, rsend=rsend, day=day,
                                score=score, blocks="map")
            else:
                await sim.frame(t, S_PLAY, rs=rs, rsend=rsend, day=day,
                                score=score)

        print()
        print("=== [4] ПОСТ-ГЕЙМ: win_team=radiant, счёт 24:16 ==========")
        print(f"=== симуляция завершена: {sim.sent} GSI-пакетов отправлено ===")
        print("=== смотри лог тренера (vasilisk.log) и разбор: python src/post_match.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Полная симуляция одной игры Dota 2 для ВАСИЛИСК 2.0")
    ap.add_argument("--uri", default="http://127.0.0.1:9001/")
    ap.add_argument("--speed", type=float, default=12,
                   help="игровых секунд за реальную секунду (по умолчанию 12)")
    a = ap.parse_args()
    print(f"скорость симуляции: x{a.speed} (матч 36 мин ≈ "
          f"{36 * 60 / a.speed:.0f} секунд реального времени)")
    asyncio.run(run(a.uri.rstrip("/") + "/", a.speed))
