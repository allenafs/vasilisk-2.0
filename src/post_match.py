# -*- coding: utf-8 -*-
"""
post_match — «рекомендации на основе твоих матчей» (как у них).

Тянет твои последние игры из OpenDota и разбирает:
  • GPM/XPM против перцентилей твоего скилл-брекета (benchmarks);
  • тайминги кор-итемов против статистики itemTimings (во сколько обычно покупают);
  • варды/сентри и стаки (для саппортов);
  • краткий список «что чинить».

Использование:
    python src/post_match.py --steamid 76561198XXXXXXXXX   (SteamID64)
    python src/post_match.py --account 12345678            (account_id32)
    python src/post_match.py --matchid 3703866531          (разбор одного матча)
    python src/post_match.py --player-name "LINE"          (разбор любого игрока)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import aiohttp

OD = "https://api.opendota.com/api"
UA = {"User-Agent": "Mozilla/5.0 (vasilisk/2.0)"}
STEAM64_BASE = 76561197960265728

CORE_ITEMS = {
    "bfury", "black_king_bar", "blink", "manta", "diffusal_blade", "butterfly",
    "satanic", "skadi", "greater_crit", "desolator", "radiance", "assault",
    "heart", "shivas_guard", "blade_mail", "vanguard", "crimson_guard", "pipe",
    "mekansm", "guardian_greaves", "aether_lens", "ultimate_scepter",
    "octarine_core", "refresher", "sheepstick", "force_staff", "glimmer_cape",
    "euls_scepter", "orchid", "hurricane_pike", "silver_edge", "solar_crest",
    "spirit_vessel", "urn_of_shadows", "witch_blade", "meteor_hammer",
    "sange_yasha", "disperser", "harpoon", "bloodstone", "eternal_shroud",
    "wind_waker", "rod_of_atos", "veil_of_discord", "hand_of_midas",
    "maelstrom", "mjollnir", "dragon_lance", "mask_of_madness",
    "helm_of_the_dominator", "echo_sabre", "falcon_blade", "phase_boots",
    "power_treads", "arcane_boots",
}
WATCH_TOL = 90  # сек допуска на «нормальный» тайминг


def acc_from_steam64(sid) -> int:
    return int(sid) - STEAM64_BASE


async def get(session, url, params=None, timeout=15):
    async with session.get(url, params=params,
                           timeout=aiohttp.ClientTimeout(total=timeout)) as r:
        r.raise_for_status()
        return await r.json()


async def find_account(session, name):
    pros = await get(session, f"{OD}/proPlayers", timeout=20)
    for p in pros:
        if p.get("name", "").lower() == name.lower():
            return p["account_id"]
    raise SystemExit(f"игрок {name} не найден среди про")


def fmt_pct(raw) -> str:
    try:
        return f"{int(float(raw) * 100)}%"
    except (TypeError, ValueError):
        return "—"


async def analyze_match(session, match_id, account_id, timings_cache) -> str:
    m = await get(session, f"{OD}/matches/{match_id}", timeout=25)
    me = None
    for p in m.get("players", []):
        if p.get("account_id") == account_id:
            me = p
            break
    if me is None and not account_id:
        for p in m.get("players", []):
            if p.get("benchmarks"):
                me = p
                break
    if me is None:
        return f"матч {match_id}: ты в нём не найден"

    dur = m.get("duration") or 0
    win = me.get("radiant_win") == (me.get("isRadiant") is True)
    hero = me.get("hero_id")
    lines = []
    lines.append(f"=== Матч {match_id} — {'Победа' if win else 'Поражение'}, "
                 f"{dur // 60} мин, герой {me.get('hero_id')}, "
                 f"KDA {me.get('kills')}/{me.get('deaths')}/{me.get('assists')}")

    # 1) перцентили брекета
    bench = me.get("benchmarks") or {}
    for k, label in [("gold_per_min", "GPM"), ("xp_per_min", "XPM"),
                     ("last_hits_per_min", "LH/мин"), ("hero_damage_per_min", "урон/мин")]:
        b = bench.get(k)
        if isinstance(b, dict):
            raw = b.get("raw")
            try:
                raw = f"{float(raw):.1f}".rstrip("0").rstrip(".")
            except (TypeError, ValueError):
                raw = b.get("raw")
            lines.append(f"  {label}: {raw} (перцентиль {fmt_pct(b.get('pct'))} твоего брекета)")

    # 2) тайминги кор-итемов против статистики
    plog = me.get("purchase_log") or []
    if plog:
        rows = timings_cache.setdefault(hero, await get_timings(session, hero))
        stats = {}
        for r in rows:
            stats.setdefault(r.get("item"), []).append(r)
        core_buys = [e for e in plog if e.get("key") in CORE_ITEMS]
        late_items = []
        for e in core_buys[:8]:
            key = e.get("key")
            t = e.get("time") or 0
            typical = typical_minute(stats.get(key) or [])
            if typical and t > typical * 60 + WATCH_TOL:
                late_items.append(f"{key} куплен на {t // 60}м (обычно к {typical}м)")
        if late_items:
            lines.append("  тайминги (поздние): " + "; ".join(late_items))
        else:
            lines.append("  тайминги кор-итемов: в норме")

    # 3) варды и стаки
    obs, sen, stacks = me.get("obs_placed"), me.get("sen_placed"), me.get("camps_stacked")
    if obs is not None or sen is not None:
        lines.append(f"  варды: обсерверов {obs or 0}, сентри {sen or 0}, стаков {stacks or 0}")
        if (obs or 0) + (sen or 0) < dur / 120:
            lines.append("    → мало обзора: цель ~1 вард каждые 2 минуты на саппорте")

    # 4) выводы
    recs = []
    gpm_b = bench.get("gold_per_min", {})
    try:
        if float(gpm_b.get("pct", 1)) < 0.5:
            recs.append("фарм-план: приоритет на пачки/стаки, меньше смертей")
    except (TypeError, ValueError):
        pass
    if late_items:
        recs.append("покупай кор-итемы по окнам (см. тайминги выше)")
    if not recs:
        recs.append("держи темп: цифры в норме — добавь агрегрессии на объекты")
    lines.append("  Рекомендации: " + "; ".join(recs))
    return "\n".join(lines)


async def get_timings(session, hero_id):
    if not hero_id:
        return []
    try:
        return await get(session, f"{OD}/scenarios/itemTimings",
                         params={"hero_id": hero_id}, timeout=20)
    except Exception:
        return []


def typical_minute(rows) -> int | None:
    if not rows:
        return None
    games = wt = 0
    for r in rows:
        try:
            g = int(r.get("games") or 0)
            games += g
            wt += g * int(r.get("time") or 0)
        except (TypeError, ValueError):
            continue
    if games < 10:
        return None
    return max(4, round(wt / games / 60))


async def main_async(args):
    async with aiohttp.ClientSession(headers=UA) as s:
        account_id = None
        if args.account:
            account_id = int(args.account)
        elif args.steamid:
            account_id = acc_from_steam64(args.steamid)
        elif args.player_name:
            account_id = await find_account(s, args.player_name)

        out = []
        if account_id is None and args.matchid:
            # матч без аккаунта — берём первого игрока с бенчмарками
            out.append(await analyze_match(s, args.matchid, 0, {}))
        elif args.matchid:
            out.append(await analyze_match(s, args.matchid, account_id, {}))
        else:
            matches = await get(s, f"{OD}/players/{account_id}/recentMatches", timeout=20)
            if not matches:
                raise SystemExit("не найдено матчей — ты точно играл? :)")
            n = min(args.games, len(matches))
            out.append(f"=== Последние {n} матчей игрока {account_id} (OpenDota)")
            timings_cache = {}
            for i, mm in enumerate(matches[:n]):
                mid = mm["match_id"]
                try:
                    out.append(await analyze_match(s, mid, account_id, timings_cache))
                except Exception as e:
                    out.append(f"матч {mid}: разбор недоступен ({e})")

        report = "\n\n".join(out)
        print(report)
        fname = f"post_match_report_{account_id or args.matchid}.txt"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        print(f"\nсохранено: {fname}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group()
    g.add_argument("--steamid", help="SteamID64 (7656...)")
    g.add_argument("--account", help="account_id (32-битный)")
    g.add_argument("--player-name", help="имя про-игрока для теста")
    g.add_argument("--matchid", type=int, help="разбор одного матча")
    p.add_argument("--games", type=int, default=3, help="сколько последних матчей (по умолчанию 3)")
    asyncio.run(main_async(p.parse_args()))
