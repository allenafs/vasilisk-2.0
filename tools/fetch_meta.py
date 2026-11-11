# -*- coding: utf-8 -*-
"""
fetch_meta — снимок АКТУАЛЬНОЙ меты Dota 2 из открытого OpenDota API.

Никаких «выдуманных сборок»: тренер советует только то, что реально покупают
и реально фармят игроки в текущих пабликах. Снимок ложится в data/meta.json
и работает офлайн; обновляется одной командой:

    python tools/fetch_meta.py                # полный снимок (~7-9 минут)
    python tools/fetch_meta.py --resume       # докачать после обрыва
    python tools/fetch_meta.py --quick        # только константы и вингейты

Что кладём (на каждый герой):
  • itemPopularity — старт / ранние / средние / поздние предметы с частотами;
  • benchmarks — перцентили GPM, XPM, ластхитов, киллов (OpenDota);
  • matchups — вингейты против каждого врага (OpenDota, топ-60 по числу игр);
  • heroStats — винрейт и пики по брекетам.
Плюс константы: предметы (цены, названия), item_ids.

Все числа в тренере берутся отсюда или из live-запросов — выдумывать нечего.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

OD = "https://api.opendota.com/api"
UA = {"User-Agent": "Mozilla/5.0 (vasilisk/2.0; snapshot fetcher)"}
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "meta.json")
DELAY = 1.05          # по умолчанию ~57 запросов/мин — под лимит 60/мин без ключа
BRACKETS = range(1, 9)  # 1=Herald ... 8=Immortal
MATCHUP_TOP = 60       # сколько врагов храним на героя


def get(path: str, retries: int = 3, timeout: int = 20):
    url = f"{OD}{path}"
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:                      # rate limit — ждём и пробуем снова
                wait = 12 + 5 * i
                print(f"  … 429 на {path}: жду {wait}с", flush=True)
                time.sleep(wait)
                last = e
                continue
            last = e
            break
        except Exception as e:
            last = e
            time.sleep(2 + 2 * i)
    print(f"  ! пропускаю {path}: {last}", flush=True)
    return None


def percentile_table(rows: list) -> list:
    """[{percentile, value}] -> [[p, v], ...] (сортировка по p)."""
    out = []
    for r in rows or []:
        try:
            out.append([float(r["percentile"]), float(r["value"])])
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(out)


def load_existing(path: str) -> dict:
    """Прочитать существующий снимок (для --resume)."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(path: str, snap: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description="Снимок меты Dota 2 из OpenDota")
    ap.add_argument("--quick", action="store_true",
                    help="только константы и вингейты (быстро, без популярности предметов)")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--delay", type=float, default=DELAY,
                    help="пауза между запросами, сек (меньше 0.85 = риск 429)")
    ap.add_argument("--resume", action="store_true",
                    help="докачать: пропустить героев, уже лежащих в снимке")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    t0 = time.time()

    print("[1/5] Константы: герои…", flush=True)
    heroes = get("/heroes") or []
    if not heroes:
        print("Сеть недоступна и героев нет — снимок НЕ создан.")
        sys.exit(1)

    print("[2/5] Константы: предметы, item_ids, heroStats…", flush=True)
    items_const = get("/constants/items") or {}
    item_ids = get("/constants/item_ids") or {}
    hero_stats = get("/heroStats") or []
    hs_by_id = {}
    for h in hero_stats:
        try:
            hid = h.get("hero_id") or h.get("id")
            hs_by_id[int(hid)] = h
        except (TypeError, ValueError):
            pass

    # --- идентификаторы предметов: сначала item_ids, потом id из constants/items
    id_to_name = {}
    for k, v in item_ids.items():
        id_to_name[str(k)] = str(v)
    if not id_to_name:
        for key, v in items_const.items():
            if isinstance(v, dict) and isinstance(v.get("id"), int):
                id_to_name[str(v["id"])] = str(key)

    # --- компактные константы предметов
    items_out = {}
    for key, v in items_const.items():
        if isinstance(v, dict):
            try:
                items_out[str(key)] = {
                    "cost": int(v.get("cost") or 0),
                    "dname": v.get("dname") or key,
                }
            except (TypeError, ValueError):
                pass

    heroes_out = {}
    npc_by_id = {}
    for h in heroes:
        hid = int(h["id"])
        npc = str(h["name"])
        npc_by_id[hid] = npc
        # --- вингейт/пики: общий паблик pub_win/pub_pick (+ сумма брекетов 1..7)
        stats = hs_by_id.get(hid) or {}
        picks = wins = 0
        for b in BRACKETS:
            try:
                picks += int(stats.get(f"{b}_pick") or 0)
                wins += int(stats.get(f"{b}_win") or 0)
            except (TypeError, ValueError):
                pass
        try:
            pub_p = int(stats.get("pub_pick") or 0)
            pub_w = int(stats.get("pub_win") or 0)
        except (TypeError, ValueError):
            pub_p = pub_w = 0
        if pub_p:
            picks, wins = pub_p, pub_w
        heroes_out[npc] = {
            "id": hid,
            "localized_name": h.get("localized_name"),
            "primary_attr": h.get("primary_attr"),
            "attack_type": h.get("attack_type"),
            "roles": h.get("roles") or [],
            "win_rate": round(wins / picks, 4) if picks else None,
            "picks_sample": picks,
            "item_popularity": None,
            "benchmarks": None,
            "matchups": None,
        }

    # --- докачка: забираем готовое из старого снимка
    if args.resume:
        old = load_existing(args.out).get("heroes") or {}
        carried = 0
        for npc, info in old.items():
            if npc in heroes_out and info.get("item_popularity"):
                heroes_out[npc].update({
                    "item_popularity": info.get("item_popularity"),
                    "benchmarks": info.get("benchmarks"),
                    "matchups": info.get("matchups"),
                })
                carried += 1
        if carried:
            print(f"[resume] из старого снимка перенесено героев: {carried}", flush=True)

    if args.quick:
        _save(args.out, _snap(heroes_out, items_out, quick=True))
        print(f"[quick] готово за {time.time() - t0:.0f}с → {args.out}")
        return

    # --- популярность предметов + бенчмарки + матчапы по каждому герою
    total = len(heroes_out)
    done = 0
    for i, (npc, info) in enumerate(heroes_out.items(), 1):
        if info.get("item_popularity") and info.get("matchups") is not None:
            continue                                   # уже скачан (resume)
        hid = info["id"]

        pop = get(f"/heroes/{hid}/itemPopularity")
        time.sleep(args.delay)
        mu = get(f"/heroes/{hid}/matchups")
        time.sleep(args.delay)
        bench = get(f"/benchmarks?hero_id={hid}")
        time.sleep(args.delay)

        if isinstance(pop, dict):
            ip = {}
            for phase_src, phase_dst in (("start_game_items", "start_game"),
                                          ("early_game_items", "early_game"),
                                          ("mid_game_items", "mid_game"),
                                          ("late_game_items", "late_game")):
                raw = pop.get(phase_src) or {}
                rows = []
                for item_id, cnt in raw.items():
                    key = id_to_name.get(str(item_id), str(item_id))
                    try:
                        rows.append([key, int(cnt)])
                    except (TypeError, ValueError):
                        continue
                rows.sort(key=lambda kv: -kv[1])
                ip[phase_dst] = rows[:14]
            info["item_popularity"] = ip

        if isinstance(mu, list):
            rows = []
            for m in mu:
                try:
                    enemy_npc = npc_by_id.get(int(m["hero_id"]))
                    if not enemy_npc:
                        continue
                    rows.append([enemy_npc, int(m["games_played"]), int(m["wins"])])
                except (KeyError, TypeError, ValueError):
                    continue
            rows.sort(key=lambda r: -r[1])
            info["matchups"] = rows[:MATCHUP_TOP]

        if isinstance(bench, dict) and isinstance(bench.get("result"), dict):
            r = bench["result"]
            info["benchmarks"] = {
                "gold_per_min": percentile_table(r.get("gold_per_min")),
                "xp_per_min": percentile_table(r.get("xp_per_min")),
                "last_hits_per_min": percentile_table(r.get("last_hits_per_min")),
                "kills_per_min": percentile_table(r.get("kills_per_min")),
            }

        done += 1
        if done % 10 == 0 or i == total:
            # чекпоинт: снимок на диске, чтобы --resume продолжил с места обрыва
            _save(args.out, _snap(heroes_out, items_out, quick=False))
            print(f"[3-4/5] обработано {i}/{total} "
                  f"( elapsed {time.time() - t0:.0f}с )", flush=True)

    _save(args.out, _snap(heroes_out, items_out, quick=False))
    print(f"[5/5] Снимок собран за {time.time() - t0:.0f}с → {args.out}")
    have_pop = sum(1 for v in heroes_out.values() if v["item_popularity"])
    have_bench = sum(1 for v in heroes_out.values() if v["benchmarks"])
    have_mu = sum(1 for v in heroes_out.values() if v["matchups"])
    print(f"      предметов-констант: {len(items_out)}; "
          f"героев с популярностью: {have_pop}; с матчапами: {have_mu}; "
          f"с бенчмарками: {have_bench}")


def _snap(heroes_out: dict, items_out: dict, quick: bool) -> dict:
    return {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "source": "https://www.opendota.com/ (public API)",
        "quick": quick,
        "heroes": heroes_out,
        "items": items_out,
    }


if __name__ == "__main__":
    main()
