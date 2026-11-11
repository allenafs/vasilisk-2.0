# -*- coding: utf-8 -*-
"""
mock_ollama — подделка Ollama для тестов без установки настоящей модели.
Отвечает на /api/tags и /api/chat, превращая ФАКТ в короткую «тренерскую» фразу.

    python tools/mock_ollama.py            # 127.0.0.1:11434
    python tools/mock_ollama.py --port 11440
"""
from __future__ import annotations

import argparse
import asyncio
import re

from aiohttp import web


def coach_answer(fact: str) -> str:
    f = fact.lower()
    # вытаскиваем предмет из факта («До Мьолнир не хватает…»)
    m = re.search(r"до ([а-яё]+) не хватает", f) or re.search(r"добираем ([а-яё]+)", f)
    item = m.group(1).capitalize() if m else "БКБ"
    if "не хватает" in f or "добираем" in f or "золота" in f:
        return f"Добрать {item} — забери ближайшую пачку на боте."
    if "рошан" in f and "заспавн" in f:
        return "Рошан жив — собери смок и проверь питу."
    if "рошан" in f and ("окно" in f or "питу" in f or "аегис" in f):
        return "Окно Рошана открыто — поставь варда и собирай группу."
    if "пропал" in f or "вижен" in f:
        return "Отойди из вражеского вижена — жди ротацию."
    if "башн" in f and "пал" in f:
        return "Отпушь бот — затем стягивайся к Рошану."
    if "умер" in f or "возрожд" in f:
        return "Не флуди — купи расходники и держи ТП."
    if "gpm" in f or "фарм" in f:
        return "Фарм просел — стаки и пачки, меньше смертей."
    if "смоук" in f or "смок" in f:
        return "Возьмите смок и сходите на Рошана."
    if "вард" in f or "обсервер" in f:
        return "Поставь вард на хайграунд — прикрой фарм."
    if "матч начался" in f or "план" in f:
        return "Играй по плану: фарм, объекты, без смертей."
    return "Держи фарм и смотри на карту."


async def tags(request):
    return web.json_response({"models": [{"name": "mock-coach:latest"}]})


async def chat(request):
    try:
        body = await request.json()
        msgs = body.get("messages") or []
        user_msgs = [m for m in msgs if m.get("role") == "user"]
        fact = user_msgs[-1].get("content", "") if user_msgs else ""
        # отрезаем строку контекста
        if "\nФАКТ:" in fact:
            fact = fact.split("\nФАКТ:", 1)[1]
        await asyncio.sleep(0.05)
        return web.json_response({
            "model": body.get("model", "mock-coach"),
            "message": {"role": "assistant", "content": coach_answer(fact)},
            "done": True,
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


def make_app():
    app = web.Application()
    app.router.add_get("/api/tags", tags)
    app.router.add_post("/api/chat", chat)
    return app


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11434)
    a = ap.parse_args()
    print(f"mock ollama: http://127.0.0.1:{a.port}  (Ctrl+C — стоп)")
    web.run_app(make_app(), host="127.0.0.1", port=a.port, print=None)
