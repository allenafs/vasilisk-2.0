"""Модель шанса победы по драфту (логистическая регрессия на героях). Обучается train_winrate.py."""
import json, math, os
PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "winmodel.json")
_m = None


def load():
    global _m
    if _m is None and os.path.exists(PATH):
        with open(PATH) as f:
            _m = json.load(f)
    return _m


def predict(mine, enemy):
    """Вероятность победы твоей команды. Работает и с неполным драфтом. None, если модель не обучена."""
    m = load()
    if not m:
        return None
    w = m["w"]
    z = sum(w.get(str(i), 0) for i in mine) - sum(w.get(str(i), 0) for i in enemy)
    return 1 / (1 + math.exp(-z))
