# -*- coding: utf-8 -*-
"""
ВАСИЛИСК 2.0 — единый установщик «всё в один клик».

Одна кнопка (launcher.pyw «УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ» или install_all.bat)
ставит ВСЁ, что нужно для полного функционала ИИ-тренера:

  [1/6] Python-пакеты (aiohttp)         — pip install -r requirements.txt
  [2/6] GSI-конфиг Dota 2               — в game\\dota\\cfg\\gamestate_integration\\
  [3/6] Параметр запуска Dota 2         — -gamestateintegration (авто-прописка,
                                          Steam должен быть закрыт; иначе инструкция)
  [4/6] Ollama + qwen2.5:7b-instruct    — локальный ИИ-мозг (~4,7 ГБ; --no-llm чтобы пропустить)
  [5/6] Снимок меты OpenDota            — обновляется, если старше 14 дней
  [6/6] Ярлык «ВАСИЛИСК 2.0» на столе   — с иконкой василиска

Запуск:
    python tools/install_all.py --all           # установить всё
    python tools/install_all.py --all --no-llm  # без ИИ-мозга (слабый ПК)
    python tools/install_all.py --check         # только диагностика, ничего не меняет

ВАСИЛИСК 2.0 · создатель: ALLENAFS
При поддержке: Carassius, Репозиторий Гитхабович, GLM
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_NAME = "gamestate_integration_vasilisk.cfg"
LEGACY_CFGS = ("gamestate_integration_ptsdiy.cfg",)   # старые версии — удаляем
FLAG = "-gamestateintegration"
MODEL_FALLBACK = "qwen2.5:7b-instruct"
APP_NAME = "ВАСИЛИСК 2.0"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# ------------------------------------------------------------------ утилиты
def run_stream(cmd, log=print, cwd=None, line_pause=0.0):
    """Выполнить команду, транслируя вывод в log(). Вернуть код возврата."""
    try:
        p = subprocess.Popen(
            [str(c) for c in cmd], cwd=cwd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, universal_newlines=True,
            encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    except FileNotFoundError as e:
        log(f"      ✗ команда не найдена: {e}")
        return 127
    last = 0.0
    for line in p.stdout:                      # \r тоже считается переводом строки
        line = line.rstrip()
        if not line:
            continue
        now = time.time()
        if line_pause and now - last < line_pause \
                and not line.lower().startswith(("error", "success", "failure")):
            continue                           # прогресс-спам качающейся модели
        log("    " + line[:160])
        last = now
    return p.wait()


def _ps_run(script: str, timeout=90):
    """PowerShell -EncodedCommand (без мучений с кавычками)."""
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=NO_WINDOW, timeout=timeout)


# ------------------------------------------------------------------ Steam
def find_steam():
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                path, _ = winreg.QueryValueEx(k, "SteamPath")
            if path and os.path.isdir(os.path.join(path, "steamapps")):
                return os.path.normpath(path)
        except OSError:
            pass
    for cand in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam",
                 r"D:\Steam", r"E:\Steam", r"F:\Steam",
                 r"D:\Program Files (x86)\Steam", r"E:\Program Files (x86)\Steam"):
        if os.path.isdir(os.path.join(cand, "steamapps")):
            return cand
    return None


def steam_libraries(steam):
    libs = [steam]
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    try:
        with open(vdf, encoding="utf-8", errors="replace") as f:
            text = f.read()
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):
            p = m.group(1).replace("\\\\", "\\")
            if os.path.isdir(os.path.join(p, "steamapps")) and p not in libs:
                libs.append(p)
    except OSError:
        pass
    return libs


def find_dota(steam):
    if not steam:
        return None
    for lib in steam_libraries(steam):
        cand = os.path.join(lib, "steamapps", "common", "dota 2 beta")
        if os.path.isdir(os.path.join(cand, "game", "dota")):
            return cand
    return None


def steam_running():
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                             capture_output=True, text=True, creationflags=NO_WINDOW)
        return "steam.exe" in (out.stdout or "").lower()
    except Exception:
        return False


def _localconfigs(steam):
    """Все localconfig.vdf (по одному на аккаунт Steam)."""
    out = []
    ud = os.path.join(steam, "userdata")
    if os.path.isdir(ud):
        for acc in sorted(os.listdir(ud)):
            p = os.path.join(ud, acc, "config", "localconfig.vdf")
            if os.path.isfile(p):
                out.append(p)
    return out


def _find_vdf_block(text, key):
    """Найти блок "key" { ... } (Valve пишет "key" и "{" на разных строках).

    Возвращает (indent, начало_внутри, конец_внутри) или None.
    """
    m = re.search(r'(?m)^([ \t]*)"%s"[ \t]*\{[ \t]*$' % re.escape(key), text)
    if m:
        inner_start = m.end()
    else:
        m = re.search(r'(?m)^([ \t]*)"%s"[ \t]*$' % re.escape(key), text)
        if not m:
            return None
        rest = text[m.end():]
        if rest.lstrip()[:1] != "{":
            return None
        inner_start = m.end() + rest.find("{") + 1
    indent = m.group(1)
    depth, i = 1, inner_start
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return indent, inner_start, i
        i += 1
    return None


def steam_param_status(steam):
    """(True/False/None, пояснение) — стоит ли FLAG в параметрах запуска Dota 2."""
    if not steam:
        return None, "Steam не найден"
    files = _localconfigs(steam)
    if not files:
        return None, "нет профилей Steam — войди в Steam хотя бы раз"
    for p in files:
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        blk = _find_vdf_block(text, "570")
        if blk and FLAG in text[blk[1]:blk[2]]:
            return True, "уже прописан"
    return False, "не стоит в параметрах запуска Dota 2"


def _edit_localconfig(path, log=print):
    """Аккуратно вписать FLAG в LaunchOptions приложения 570 (Dota 2).

    Возвращает (ok, changed, why): ok=False → файл НЕ тронут (или восстановлен).
    Бэкап кладётся рядом: localconfig.vdf.vasilisk-bak.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        return False, False, str(e)
    text = raw.decode("utf-8", errors="surrogateescape")

    blk = _find_vdf_block(text, "570")
    added_braces = 0                          # сколько { и } добавляем (по одному)
    if blk:
        indent, s, e = blk
        block = text[s:e]
        lo = re.search(r'(?m)^([ \t]*)"LaunchOptions"[ \t]+"([^"]*)"[ \t]*$', block)
        if lo:
            if FLAG in lo.group(2):
                return True, False, "уже стоит"
            merged = (lo.group(2).strip() + " " + FLAG).strip()
            new_block = (block[:lo.start()] + lo.group(1) + '"LaunchOptions"\t\t"'
                         + merged + '"' + block[lo.end():])
            why = "дописан к твоим существующим параметрам"
        else:
            new_block = ("\n" + indent + "\t\"LaunchOptions\"\t\t\"" + FLAG + "\""
                         + block)
            why = "добавлен в секцию Dota 2"
        new_text = text[:s] + new_block + text[e:]
    else:
        apps = _find_vdf_block(text, "Apps")
        if not apps:
            return False, False, "не нашёл секцию Apps — пропиши вручную"
        aindent, as_, _ae = apps
        block570 = ("\n" + aindent + "\t\"570\"\n" + aindent + "\t{\n"
                    + aindent + "\t\t\"LaunchOptions\"\t\t\"" + FLAG + "\"\n"
                    + aindent + "\t}")
        new_text = text[:as_] + block570 + text[as_:]
        added_braces = 1
        why = "создана секция Dota 2 с параметром"

    # --- контроль: скобки не потерялись, ключ на месте
    if (new_text.count("{") != text.count("{") + added_braces
            or new_text.count("}") != text.count("}") + added_braces):
        return False, False, "контроль скобок не сошёлся — файл не тронут"

    bak = path + ".vasilisk-bak"
    try:
        shutil.copy2(path, bak)
        with open(path, "wb") as f:
            f.write(new_text.encode("utf-8", errors="surrogateescape"))
    except OSError as e:
        return False, False, f"запись не удалась: {e}"

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            check = f.read()
        blk2 = _find_vdf_block(check, "570")
        if (not blk2 or FLAG not in check[blk2[1]:blk2[2]]
                or check.count("{") != text.count("{") + added_braces):
            shutil.copy2(bak, path)
            return False, False, "контроль после записи не прошёл — файл восстановлен"
    except Exception as e:
        shutil.copy2(bak, path)
        return False, False, f"перечитать не удалось ({e}) — файл восстановлен"
    return True, True, why


# ------------------------------------------------------------------ Ollama
def find_ollama():
    p = shutil.which("ollama")
    if p:
        return p
    cands = []
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA", "")
        if la:
            cands.append(os.path.join(la, "Programs", "Ollama", "ollama.exe"))
        cands.append(r"C:\Program Files\Ollama\ollama.exe")
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def ollama_alive(timeout=2):
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def ollama_models():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read().decode("utf-8"))
            return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return None


def _model_present(model, models):
    if not models:
        return False
    base = model.split(":")[0]
    return any(m == model or m.split(":")[0] == base for m in models)


def cfg_llm_model():
    try:
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
            return json.load(f).get("llm_model") or MODEL_FALLBACK
    except Exception:
        return MODEL_FALLBACK


# ------------------------------------------------------------------ шаги
def step_python_deps(log):
    log("[1/6] Python-пакеты тренера (aiohttp)…")
    run_stream([sys.executable, "-m", "pip", "install",
                "-r", os.path.join(ROOT, "requirements.txt"),
                "--quiet", "--disable-pip-version-check"], log=log)
    ok = importlib.util.find_spec("aiohttp") is not None
    log("      ✓ готово" if ok else "      ✗ pip не смог поставить пакеты (см. выше)")
    return ok, "aiohttp установлен" if ok else "pip не смог поставить aiohttp"


def step_gsi(log, steam=None):
    log("[2/6] GSI-конфиг Dota 2 — игра начнёт слать данные тренеру…")
    steam = steam or find_steam()
    if not steam:
        return False, "Steam не найден — укажи папку Steam вручную"
    dota = find_dota(steam)
    if not dota:
        libs = ", ".join(steam_libraries(steam))
        return False, f"Dota 2 не найдена в библиотеках Steam ({libs})"
    dst_dir = os.path.join(dota, "game", "dota", "cfg", "gamestate_integration")
    src = os.path.join(ROOT, "install", CFG_NAME)
    if not os.path.isfile(src):
        return False, f"в комплекте нет файла install\\{CFG_NAME}"
    os.makedirs(dst_dir, exist_ok=True)
    shutil.copy2(src, os.path.join(dst_dir, CFG_NAME))
    for old in LEGACY_CFGS:                    # подчистить прошлые версии
        p = os.path.join(dst_dir, old)
        if os.path.isfile(p):
            try:
                os.remove(p)
                log(f"      удалён устаревший {old}")
            except OSError:
                pass
    log(f"      ✓ {os.path.join(dst_dir, CFG_NAME)}")
    return True, "GSI-конфиг установлен"


def step_steam_param(log, steam=None):
    log(f"[3/6] Параметр запуска Dota 2: {FLAG}…")
    steam = steam or find_steam()
    if not steam:
        return False, "Steam не найден"
    ok, _why = steam_param_status(steam)
    if ok:
        log("      ✓ уже прописан")
        return True, "уже прописан"
    files = _localconfigs(steam)
    if not files:
        return False, "нет профилей Steam — войди в Steam и повтори"
    if steam_running():
        log("      ⚠ Steam сейчас ЗАПУЩЕН — авто-прописка возможна только при закрытом Steam")
        return False, ("Steam запущен: закрой его полностью (трей → Exit) и нажми кнопку "
                       "ещё раз, или впиши вручную: Steam → Библиотека → Dota 2 → ПКМ → "
                       "Свойства → Общие → Параметры запуска → " + FLAG)
    changed = failed = 0
    for p in files:
        ok, ch, why = _edit_localconfig(p, log=log)
        if ch:
            changed += 1
            log(f"      ✓ профиль {os.path.basename(os.path.dirname(os.path.dirname(p)))}: {why}")
        elif not ok:
            failed += 1
            log(f"      ✗ {p}: {why}")
    if changed:
        log("      ⚠ перезапусти Steam, чтобы параметр вступил в силу")
        return True, f"прописан автоматически ({changed} профиль), перезапусти Steam"
    return False, ("авто-прописка не удалась — впиши " + FLAG +
                   " в параметры запуска Dota 2 вручную")


def step_ollama(log, model=None):
    model = model or cfg_llm_model()
    log(f"[4/6] Ollama + модель {model} — «живые» фразы тренера (~4,7 ГБ)…")
    exe = find_ollama()
    if not exe:
        if shutil.which("winget"):
            log("      Ollama не установлена — ставлю через winget (тихо)…")
            run_stream(["winget", "install", "-e", "--id", "Ollama.Ollama",
                        "--accept-source-agreements", "--accept-package-agreements"],
                       log=log, line_pause=2.0)
            exe = find_ollama()
    if not exe:
        log("      качаю установщик с ollama.com…")
        setup = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
        try:
            urllib.request.urlretrieve("https://ollama.com/download/OllamaSetup.exe", setup)
            log("      запускаю тихую установку…")
            rc = run_stream([setup, "/VERYSILENT", "/NORESTART"], log=log)
            if rc != 0:
                log("      тихая не удалась — открываю обычный установщик (нажми Install)…")
                run_stream([setup], log=log)
            exe = find_ollama()
        except Exception as e:
            log(f"      ✗ скачать/запустить не удалось: {e}")
    if not exe:
        return False, ("Ollama не установилась — скачай с https://ollama.com/download "
                       "и нажми кнопку ещё раз")
    log(f"      Ollama: {exe}")
    if not ollama_alive():
        log("      запускаю сервис Ollama…")
        try:
            flags = subprocess.DETACHED_PROCESS if os.name == "nt" else 0
            subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True)
        except Exception as e:
            log(f"      ⚠ не смог запустить serve: {e}")
        for _ in range(20):
            if ollama_alive():
                break
            time.sleep(1)
    if not ollama_alive():
        return False, "сервис Ollama не отвечает — запусти приложение Ollama и повтори"
    if _model_present(model, ollama_models()):
        log("      ✓ модель уже скачана")
        return True, f"Ollama + {model} готовы"
    log(f"      качаю модель {model} — не закрывай окно, время зависит от интернета…")
    rc = run_stream([exe, "pull", model], log=log, line_pause=1.0)
    if rc == 0 and _model_present(model, ollama_models()):
        log("      ✓ модель готова")
        return True, f"модель {model} скачана"
    return False, f"модель не скачалась (код {rc}) — попробуй вручную: ollama pull {model}"


def meta_age_days():
    p = os.path.join(ROOT, "data", "meta.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            head = json.load(f)
        ts = str(head.get("generated_at") or head.get("generated") or "")
        if ts:
            d = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return max(0, (_dt.datetime.now(_dt.timezone.utc) - d).days)
    except Exception:
        pass
    try:
        return max(0, int((time.time() - os.path.getmtime(p)) // 86400))
    except OSError:
        return None


def step_meta(log, max_age=14):
    log("[5/6] Актуальные сборки — снимок меты OpenDota…")
    p = os.path.join(ROOT, "data", "meta.json")
    if not os.path.isfile(p):
        log("      снимка нет — качаю полный (7–9 минут, не закрывай окно)…")
        rc = run_stream([sys.executable, os.path.join(ROOT, "tools", "fetch_meta.py")], log=log)
        return (rc == 0), ("снимок меты скачан" if rc == 0 else "не удалось скачать снимок")
    age = meta_age_days()
    if age is None:
        log("      ⚠ возраст не определить — оставляю офлайн-копию")
        return True, "офлайн-снимок на месте"
    if age <= max_age:
        log(f"      ✓ снимок свежий ({age} дн. назад)")
        return True, f"снимок свежий ({age} дн.)"
    log(f"      снимку {age} дн. — обновляю (7–9 минут)…")
    rc = run_stream([sys.executable, os.path.join(ROOT, "tools", "fetch_meta.py")], log=log)
    return (rc == 0), ("снимок обновлён" if rc == 0 else f"обновление не удалось — осталась копия {age} дн.")


def step_shortcut(log, name=APP_NAME):
    log(f"[6/6] Ярлык «{name}» на рабочем столе…")
    if os.name != "nt":
        return False, "ярлык создаётся только в Windows"
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = sys.executable
    target = os.path.join(ROOT, "launcher.pyw")
    ico = os.path.join(ROOT, "icon", "vasilisk.ico")
    if not os.path.isfile(target):
        return False, "нет launcher.pyw в корне проекта"
    ps = "\n".join([
        "$ws = New-Object -ComObject WScript.Shell",
        "$desktop = [Environment]::GetFolderPath('Desktop')",
        f"$lnk = $ws.CreateShortcut((Join-Path $desktop '{name}.lnk'))",
        f"$lnk.TargetPath = '{pythonw}'",
        f"$lnk.Arguments = '\"{target}\"'",
        f"$lnk.WorkingDirectory = '{ROOT}'",
        f"$lnk.IconLocation = '{ico},0'",
        f"$lnk.Description = '{APP_NAME} — ИИ-тренер Dota 2. Создатель: ALLENAFS'",
        "$lnk.Save()",
        "Write-Output ('SHORTCUT_OK:' + $lnk.FullName)",
    ])
    try:
        r = _ps_run(ps)
    except Exception as e:
        return False, f"PowerShell не отработал: {e}"
    if "SHORTCUT_OK:" in (r.stdout or ""):
        lnk = r.stdout.split("SHORTCUT_OK:")[1].strip().splitlines()[0]
        log(f"      ✓ {lnk}")
        return True, "ярлык создан"
    return False, "ярлык не создался — запускай через start.bat"


# ------------------------------------------------------------------ диагностика
def desktop_dir():
    if os.name != "nt":
        return ""
    try:
        r = _ps_run("[Environment]::GetFolderPath('Desktop')", timeout=30)
        out = (r.stdout or "").strip()
        return out.splitlines()[-1].strip() if out else ""
    except Exception:
        return ""


def run_checks():
    """Список (ключ, заголовок, ok: True/False/None, пояснение)."""
    out = []
    ok = importlib.util.find_spec("aiohttp") is not None
    out.append(("deps", "Python-пакеты (aiohttp)", ok,
                "" if ok else "нажми «УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ»"))

    steam = find_steam()
    dota = find_dota(steam) if steam else None
    installed = bool(dota) and os.path.isfile(
        os.path.join(dota, "game", "dota", "cfg", "gamestate_integration", CFG_NAME))
    out.append(("gsi", "GSI-конфиг в папке Dota 2",
                installed if dota else None,
                dota or "Steam/Dota 2 не найдены"))

    ok, why = steam_param_status(steam) if steam else (None, "Steam не найден")
    out.append(("param", "Параметр запуска -gamestateintegration", ok, why))

    model = cfg_llm_model()
    exe = find_ollama()
    models = ollama_models()
    ok = bool(models is not None and _model_present(model, models))
    out.append(("llm", f"Ollama + {model}", ok, exe if exe else "Ollama не установлена"))

    age = meta_age_days()
    out.append(("meta", "Свежий снимок меты OpenDota",
                age is not None and age <= 14,
                f"{age} дн. назад" if age is not None else "нет data/meta.json"))

    desk = desktop_dir()
    ok = os.path.isfile(os.path.join(desk, f"{APP_NAME}.lnk")) if desk else None
    out.append(("shortcut", "Ярлык «ВАСИЛИСК 2.0» на рабочем столе", ok,
                desk if desk else "не удалось определить"))
    return out


# ------------------------------------------------------------------ оркестратор
def install_all(log=print, with_llm=True, with_meta=True, with_shortcut=True,
                steam=None, ask=None):
    """Прогнать все шаги. ask(prompt) — спросить у человека папку Steam (GUI/CLI).

    Возвращает список (шаг, ok, сообщение) для итогового отчёта.
    """
    report = []
    log("")
    log("=" * 64)
    log(f"  {APP_NAME} — установка всего для полного функционала")
    log("  создатель: ALLENAFS · при поддержке: Carassius, Репозиторий Гитхабович, GLM")
    log("=" * 64)
    log("")
    if os.name != "nt":
        log("⚠ запущено не в Windows — шаги Dota 2/Ollama/ярлык пропущены")

    ok, msg = step_python_deps(log)
    report.append(("Python-пакеты", ok, msg))

    if steam is None:
        steam = find_steam()
        if not steam and ask:
            ans = ask("Steam не найден автоматически.\nУкажи папку Steam "
                      "(например C:\\Program Files (x86)\\Steam).")
            if ans and os.path.isdir(os.path.join(ans, "steamapps")):
                steam = os.path.normpath(ans)
            elif ans:
                log(f"⚠ в «{ans}» нет папки steamapps — шаги Dota 2 пропускаю")

    ok, msg = step_gsi(log, steam=steam)
    report.append(("GSI-конфиг Dota 2", ok, msg))
    ok, msg = step_steam_param(log, steam=steam)
    report.append(("Параметр запуска Dota 2", ok, msg))

    if with_llm:
        ok, msg = step_ollama(log)
    else:
        log("[4/6] Ollama пропущена по твоему выбору — фразы будут шаблонными")
        ok, msg = None, "пропущено по выбору"
    report.append(("Ollama + модель", ok, msg))

    if with_meta:
        ok, msg = step_meta(log)
    else:
        ok, msg = None, "пропущено по выбору"
    report.append(("Снимок меты OpenDota", ok, msg))

    if with_shortcut:
        ok, msg = step_shortcut(log)
    else:
        ok, msg = None, "пропущено по выбору"
    report.append(("Ярлык на рабочем столе", ok, msg))

    log("")
    log("=" * 64)
    bad = [r for r in report if r[1] is False]
    if not bad:
        log(f"  ✓ ВСЁ ГОТОВО! Запуск тренера: ярлык «{APP_NAME}», launcher.pyw или start.bat")
        log("  ⚠ перед первой игрой перезапусти Steam (параметр запуска Dota 2)")
    else:
        log(f"  ⚠ готово с заметками ({len(bad)}):")
        for name, ok, msg in report:
            if ok is False:
                log(f"    • {name}: {msg}")
    log("=" * 64)
    return report


# ------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(
        description=f"{APP_NAME} — единый установщик. Создатель: ALLENAFS")
    ap.add_argument("--all", action="store_true", help="установить всё (полный функционал)")
    ap.add_argument("--check", action="store_true", help="только диагностика, ничего не менять")
    ap.add_argument("--no-llm", action="store_true", help="без Ollama/модели (шаблонные фразы)")
    ap.add_argument("--no-meta", action="store_true", help="не обновлять снимок меты")
    ap.add_argument("--no-shortcut", action="store_true", help="не создавать ярлык")
    args = ap.parse_args()

    if not args.all and not args.check:
        args.check = True

    if args.check:
        print(f"\n{APP_NAME} — диагностика\n" + "-" * 46)
        for _key, title, ok, detail in run_checks():
            mark = "✓" if ok else ("✗" if ok is False else "?")
            print(f"  [{mark}] {title}" + (f" — {detail}" if detail else ""))
        print("-" * 46)
        if not args.all:
            print(f"\nустановить/починить всё:  python tools\\install_all.py --all")
            return 0

    def ask_cli(prompt):
        try:
            print("\n" + prompt)
            return input("папка Steam> ").strip().strip('"')
        except EOFError:
            return None

    install_all(print, with_llm=not args.no_llm, with_meta=not args.no_meta,
                with_shortcut=not args.no_shortcut, ask=ask_cli)
    return 0


if __name__ == "__main__":
    sys.exit(main())
