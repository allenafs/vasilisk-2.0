# -*- coding: utf-8 -*-
"""
capture_gsi — записывает РЕАЛЬНЫЕ пакеты Dota 2 GSI и показывает, что
приходит именно от твоего клиента. Это ответ на вопрос «а точно ли обычный
клиент игрока шлёт minimap/buildings?» — без домыслов, фактами.

Как пользоваться (перед первым матчем с тренером):
    1. Запусти ЭТО ВМЕСТО тренера:      python tools/capture_gsi.py
       (по умолчанию слушает тот же порт 9001, что и cfg).
    2. Запусти Dota 2 → любой матч (можно демо-героя: Play → Create Demo Hero),
       сыграй 1–2 минуты.
    3. Вернись в консоль и нажми Ctrl+C — получишь отчёт: какие блоки
       приходят (map/player/hero/items/minimap/buildings/events) и какие
       функции тренера от них зависят.

    python tools/capture_gsi.py --max 200          # авто-стоп после 200 пакетов
    python tools/capture_gsi.py --port 9001 --out my_capture.jsonl

Файлы результата (рядом с проектом):
    gsi_capture.jsonl        — все сырые пакеты (можно ревьюить глазами)
    gsi_first_payload.json   — первый пакет целиком (красиво отформатирован)
Зависимостей нет: только стандартная библиотека Python.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# блок → функции тренера, которые от него зависят
FEATURES = [
    ("map",      "таймеры матча, счёт, день/ночь, Рошан (если roshan_state есть в map)"),
    ("player",  "экономика: GPM/ластхиты/золото, варды-счётчики"),
    ("hero",    "смерти/байбек/ресурсы/уровень"),
    ("items",   "«что купить»: тайминги сборки, ТП-чек, роскошь"),
    ("minimap", "«враг пропал из вижена» — ганк-тревоги и матчапы по появлению"),
    ("buildings", "«их Т2 пала — пуш», «наша Т3 пала — деф»"),
    ("events",  "события (доп. триггеры)"),
]


class CaptureState:
    def __init__(self, out_path: str):
        self.out_path = out_path
        self.count = 0
        self.blocks: set = set()
        self.first_payload_saved = False
        self.map_keys: set = set()
        self.minimap_units: set = set()
        self.building_keys: set = set()
        self.stop_after = 0          # 0 = без авто-стопа
        self.server = None           # ThreadingHTTPServer (для авто-стопа)


CAP = None  # type: CaptureState


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        try:
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
        except Exception:
            raw = b""
        # сразу отвечаем 204 — клиенту всё равно, лишь бы без ошибки
        self.send_response(204)
        self.end_headers()
        if not raw:
            return
        try:
            payload = json.loads(raw)
        except Exception:
            return
        if not isinstance(payload, dict):
            return

        CAP.count += 1
        CAP.blocks.update(
            k for k in payload if k not in ("auth", "provider", "previously", "added"))

        # сырая строка в jsonl
        try:
            with open(CAP.out_path, "a", encoding="utf-8") as f:
                f.write(raw.decode("utf-8", "replace").strip() + "\n")
        except Exception as e:
            print(f"  [!] не могу записать {CAP.out_path}: {e}")

        # первый пакет — целиком, красиво
        if not CAP.first_payload_saved:
            CAP.first_payload_saved = True
            try:
                with open("gsi_first_payload.json", "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # детали: ключи map, юниты minimap, башни buildings
        m = payload.get("map")
        if isinstance(m, dict):
            CAP.map_keys.update(m.keys())
        mm = payload.get("minimap")
        if isinstance(mm, dict):
            for v in mm.values():
                if isinstance(v, dict):
                    u = str(v.get("unitname") or v.get("name") or "")
                    if u:
                        CAP.minimap_units.add(u)
        b = payload.get("buildings")
        if isinstance(b, dict):
            def _walk(d, path=""):
                if isinstance(d, dict):
                    for k, v in d.items():
                        if "tower" in k or "barracks" in k:
                            CAP.building_keys.add(f"{path}{k}")
                        _walk(v, f"{path}{k}.")
            _walk(b)

        if CAP.count % 50 == 0:
            print(f"  …принято пакетов: {CAP.count}; блоки: {sorted(CAP.blocks)}")

        if CAP.stop_after and CAP.count >= CAP.stop_after:
            print(f"  достигнут лимит {CAP.stop_after} пакетов — останавливаюсь…")
            # shutdown() блокирует до выхода serve_forever — отдельным потоком
            threading.Thread(target=CAP.server.shutdown, daemon=True).start()

    def log_message(self, fmt, *args):  # глушим стандартный access-лог
        pass


def report():
    print()
    print("=" * 64)
    print("ОТЧЁТ О РЕАЛЬНОМ GSI-ПОТОКЕ (твой клиент Dota 2)")
    print("=" * 64)
    if CAP.count == 0:
        print("Пакетов НЕТ — данные от игры не приходят. Проверь:")
        print("  1) конфиг лежит в  <dota 2 beta>\\game\\dota\\cfg\\gamestate_integration\\")
        print("     и называется gamestate_integration_*.cfg")
        print("  2) в Steam у Dota 2 в параметрах запуска стоит -gamestateintegration")
        print("     (Свойства → Общие → Параметры запуска; после — перезапусти Steam)")
        print("  3) порт в uri конфига совпадает с портом этого рекордера")
        print("  4) после правки конфига перезапусти Dota 2")
        return
    print(f"Пакетов получено: {CAP.count}")
    print()
    print("Блоки и функции тренера:")
    for block, feat in FEATURES:
        ok = block in CAP.blocks
        mark = "ЕСТЬ  " if ok else "НЕТ   "
        print(f"  [{mark}] {block:10s} → {feat}")
    print()
    # углубляемся в интересные детали
    if "map" in CAP.blocks:
        rs = "roshan_state" in CAP.map_keys
        print(f"  roshan_state внутри map: {'ЕСТЬ — таймеры Рошана работают' if rs else 'НЕТ — таймеры Рошана будут молчать'}")
    if "minimap" in CAP.blocks:
        heroes = sorted(u for u in CAP.minimap_units if "npc_dota_hero" in u)
        print(f"  героев видел на миникарте: {len(heroes)}"
              + (f" ({', '.join(h.replace('npc_dota_hero_', '') for h in heroes[:6])}…)"
                 if heroes else ""))
        print("    → «враг пропал из вижена» будет работать, если среди них")
        print("      бывают вражеские герои (не только твои союзники).")
    if "buildings" in CAP.blocks:
        print(f"  башен/бараков видел в buildings: {len(CAP.building_keys)}")
        print("    → значит «их башня пала — пуш» работает на реальных данных.")
    print()
    print(f"Сырые пакеты:       {CAP.out_path}")
    print( "Первый пакет:       gsi_first_payload.json (можно скинуть разработчику)")
    print()
    print("Если minimap/buildings НЕ приходят — тренер тоже сообщит об этом")
    print("в своём логе при первом реальном матче (строка [GSI] ⚠ …).")


def main():
    global CAP
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Запись реальных GSI-пакетов Dota 2")
    ap.add_argument("--port", type=int, default=9001, help="порт (по умолчанию 9001, как в cfg)")
    ap.add_argument("--out", default=os.path.join(here, "gsi_capture.jsonl"),
                    help="куда писать сырые пакеты")
    ap.add_argument("--max", type=int, default=0,
                    help="остановиться после N пакетов (0 = без лимита, Ctrl+C)")
    a = ap.parse_args()
    CAP = CaptureState(a.out)
    CAP.stop_after = a.max

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    CAP.server = srv
    print(f"capture_gsi: слушаю http://127.0.0.1:{a.port}/ — жду пакеты от Dota 2")
    print("Запусти матч (или демо-героя), сыграй минуту-две, потом Ctrl+C тут.")
    print(f"Запись: {CAP.out_path}")
    print()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    report()


if __name__ == "__main__":
    main()
