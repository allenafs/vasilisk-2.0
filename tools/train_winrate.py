#!/usr/bin/env python3
"""Обучение модели драфта на публичных матчах OpenDota.
python train_winrate.py --pages 200        # скачать ~20 000 матчей (лимит API ~1 запрос/сек) и обучить
python train_winrate.py --train-only       # только переобучить на уже скачанных
"""
import argparse, json, math, os, random, time, urllib.request
from collections import defaultdict
HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DATA, OUT = os.path.join(HERE, "matches.jsonl"), os.path.join(HERE, "winmodel.json")


def download(pages, min_rank):
    last = None
    if os.path.exists(DATA):                       # докачка: идём дальше вглубь истории
        with open(DATA) as f:
            ids = [json.loads(l)["id"] for l in f if l.strip()]
        last = min(ids) if ids else None
    with open(DATA, "a") as out:
        for i in range(pages):
            url = f"https://api.opendota.com/api/publicMatches?min_rank={min_rank}" + (f"&less_than_match_id={last}" if last else "")
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "DotaBooster"}), timeout=30) as r:
                    rows = json.load(r)
            except Exception as e:
                print("ошибка запроса, жду 10 с:", e); time.sleep(10); continue
            if not rows:
                break
            for m in rows:
                last = min(last or m["match_id"], m["match_id"])
                if m.get("game_mode") == 22 and m.get("radiant_team") and m.get("dire_team"):
                    rad = [int(x) for x in m["radiant_team"].split(",")] if isinstance(m["radiant_team"], str) else m["radiant_team"]
                    dire = [int(x) for x in m["dire_team"].split(",")] if isinstance(m["dire_team"], str) else m["dire_team"]
                    if len(rad) == 5 and len(dire) == 5:
                        out.write(json.dumps({"id": m["match_id"], "r": rad, "d": dire, "w": int(m["radiant_win"])}) + "\n")
            out.flush(); print(f"страница {i + 1}/{pages}", end="\r"); time.sleep(1.1)


def sigmoid(z): return 1 / (1 + math.exp(-max(-30, min(30, z))))


def train(data_path=DATA, out_path=OUT, epochs=25, lr=0.03, l2=2e-4):
    rows = [json.loads(l) for l in open(data_path) if l.strip()]
    rows = [(r["r"], r["d"], r["w"]) for r in rows]
    random.seed(1); random.shuffle(rows)
    cut = max(1, len(rows) // 10); test, tr = rows[:cut], rows[cut:]
    w = defaultdict(float)
    for ep in range(epochs):
        random.shuffle(tr)
        for rad, dire, y in tr:
            g = sigmoid(sum(w[i] for i in rad) - sum(w[i] for i in dire)) - y
            for i in rad: w[i] -= lr * (g + l2 * w[i])
            for i in dire: w[i] -= lr * (-g + l2 * w[i])
    acc = sum((sigmoid(sum(w[i] for i in r) - sum(w[i] for i in d)) > .5) == bool(y) for r, d, y in test) / len(test)
    json.dump({"w": {str(k): v for k, v in w.items()}, "matches": len(rows), "accuracy": acc}, open(out_path, "w"))
    print(f"\nМатчей: {len(rows)}, точность на отложенной выборке: {acc:.1%} (драфт даёт ограниченный сигнал: 53–58% нормально)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=100)
    ap.add_argument("--min-rank", type=int, default=60, help="минимальный ранг-тир (60 = Crusader)")
    ap.add_argument("--train-only", action="store_true")
    a = ap.parse_args()
    if not a.train_only:
        download(a.pages, a.min_rank)
    train()
