# -*- coding: utf-8 -*-
"""
ВАСИЛИСК 2.0 — ИИ-тренер для Dota 2 (GSI + правила + локальная нейросеть).
Создатель: ALLENAFS. При поддержке: Carassius, Репозиторий Гитхабович, GLM.

Запуск:
    python src/main.py                     # консоль + голос (если Windows)
    python src/main.py --mode overlay      # оверлей поверх игры
    python src/main.py --no-voice --no-llm # тихий режим (только текст)
Установка всего одной кнопкой: launcher.pyw или install_all.bat
(конфиг Dota 2: install/gamestate_integration_vasilisk.cfg).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aiohttp import web

from advisor import Advisor
from builds import Builds
from gsi_server import CoachApp, make_app
from llm import CoachLLM
from tts import Speaker
import extras
import webui

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config():
    cfg_path = os.path.join(BASE, "config.json")
    defaults = {
        "port": 9001,
        "token": "vasilisk_2026",
        "role": "carry",
        "rank": "legend",
        "voice": True,
        "voice_name": "",
        "tts_rate": 1,
        "llm": True,
        "llm_url": "http://127.0.0.1:11434",
        "llm_model": "qwen2.5:7b-instruct",
        "free_coach": True,
        "coach_interval": 30,
    }
    try:
        with open(cfg_path, encoding="utf-8") as f:
            user = json.load(f)
        defaults.update({k: v for k, v in user.items() if v is not None})
    except Exception:
        pass
    defaults["role"] = extras.normalize_role(defaults["role"])   # 1-5 или carry/mid/...
    return defaults


def save_config(cfg):
    try:
        with open(os.path.join(BASE, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def make_logger(path):
    def log(msg):
        line = str(msg)
        print(line, flush=True)
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {line}\n")
        except Exception:
            pass
    return log


async def run(args):
    cfg = load_config()
    if args.port:
        cfg["port"] = args.port            # только на этот запуск, config.json не трогаем
    log = make_logger(os.path.join(BASE, "vasilisk.log"))
    log("=" * 60)
    log("ВАСИЛИСК 2.0 — ИИ-тренер запускается…")
    log("создатель: ALLENAFS · при поддержке: Carassius, Репозиторий Гитхабович, GLM")

    # озвучка
    speaker = Speaker(enabled=cfg["voice"] and not args.no_voice,
                      voice=cfg.get("voice_name", ""), rate=cfg.get("tts_rate", 1))

    # рендер
    if args.mode == "overlay":
        try:
            from overlay import TkOverlay, ConsoleRenderer
            renderer = TkOverlay()
            import threading
            threading.Thread(target=renderer.run_forever, daemon=True).start()
            renderer.started.wait(6)
            if renderer.error:
                log(f"[UI] оверлей недоступен ({renderer.error}) — консольный режим")
                renderer = ConsoleRenderer()
            else:
                log("[UI] оверлей запущен (tkinter)")
        except Exception as e:
            log(f"[UI] оверлей недоступен ({e}) — консольный режим")
            from overlay import ConsoleRenderer
            renderer = ConsoleRenderer()
    else:
        from overlay import ConsoleRenderer
        renderer = ConsoleRenderer()

    # LLM
    llm = CoachLLM(url=cfg["llm_url"], model=cfg["llm_model"],
                   enabled=cfg["llm"] and not args.no_llm)
    if llm.enabled:
        ok = await llm.check()
        log(f"[LLM] Ollama {'обнаружена: ' + llm.model if ok else 'не отвечает — работаем на шаблонах'}")

    # сборки: офлайн-снимок меты + живые запросы OpenDota
    builds = Builds(os.path.join(BASE, "builds_cache.json"),
                    meta_path=os.path.join(BASE, "data", "meta.json"))
    age = builds.meta_age_days()
    if builds.meta:
        log(f"[BUILD] снимок меты: {builds.meta_generated_at[:10]} "
            f"({age if age is not None else '?'} дн., героев={len(builds.meta)}); "
            f"обновить: python tools/fetch_meta.py")
    try:
        await asyncio.wait_for(builds.warm_up(), timeout=15)
        log(f"[BUILD] константы загружены: героев={len(builds.hero_ids)}, цен={len(builds.item_costs)}")
    except Exception as e:
        log(f"[BUILD] сети нет ({e}) — статические сборки из базы")

    advisor = Advisor(build_plan=[], role=cfg["role"], rank=cfg["rank"], voice=True,
                      builds=builds)
    coach = CoachApp(advisor, llm, speaker, renderer, logger=log, token=cfg["token"],
                     record_path=args.record)
    coach.free_coach = cfg.get("free_coach", True)
    coach.coach_interval = cfg.get("coach_interval", 30)
    coach.plan_loader = lambda hero: builds.load_plan(hero, cfg["role"])

    asyncio.create_task(speaker.run_forever(logger=log))

    app = make_app(coach, port=cfg["port"])
    webui.register(app, coach, cfg, lambda: save_config(cfg), builds, cfg["port"])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", cfg["port"])
    try:
        await site.start()
    except OSError as e:
        log(f"[GSI] ✗ порт {cfg['port']} занят ({e}). Скорее всего тренер уже запущен: закрой его окно "
            f"(или запусти с другим портом: --port 9002 и поправь uri в gamestate_integration_vasilisk.cfg).")
        return
    log(f"[GSI] слушаю http://127.0.0.1:{cfg['port']}/ — запусти матч Dota 2")
    log(f"[UI] панель (вопросы ИИ, драфт, роль): http://127.0.0.1:{cfg['port']}/ui")
    log("[GSI] проверка без доты: python tools/simulate_match.py")
    if args.record:
        log(f"[GSI] сырые пакеты пишутся в: {args.record}")
    log("[GSI] если пакеты НЕ приходят:")
    log("[GSI]   1) нажми «УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ» в launcher.pyw")
    log("[GSI]      (или запусти install_all.bat — он всё поставит и скопирует)")
    log("[GSI]   2) Steam → Dota 2 → Свойства → Параметры запуска → -gamestateintegration")
    log("[GSI]   3) диагностика потока: python tools/capture_gsi.py")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log("остановка…")
        await llm.close()
        await runner.cleanup()


def main():
    p = argparse.ArgumentParser(
        description="ВАСИЛИСК 2.0 — ИИ-тренер для Dota 2 (создатель: ALLENAFS)")
    p.add_argument("--mode", choices=["console", "overlay"], default="console")
    p.add_argument("--no-voice", action="store_true", help="без озвучки")
    p.add_argument("--no-llm", action="store_true", help="без Ollama (только шаблоны)")
    p.add_argument("--port", type=int, default=None, help="порт GSI-сервера")
    p.add_argument("--record", default=None, metavar="FILE",
                   help="писать сырые GSI-пакеты в FILE (jsonl) — проверить, что шлёт клиент")
    args = p.parse_args()

    if os.name == "nt":
        os.system("")  # включает ANSI-цвета в консоли Windows 10+
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n(остановлен)")


if __name__ == "__main__":
    main()
