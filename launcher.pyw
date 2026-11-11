# -*- coding: utf-8 -*-
"""
ВАСИЛИСК 2.0 — Центр управления (графический).

Одна кнопка «УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ» ставит всё, что нужно тренеру:
Python-пакеты, GSI-конфиг Dota 2, параметр запуска -gamestateintegration,
Ollama с моделью qwen2.5:7b-instruct, свежие сборки OpenDota и ярлык
«ВАСИЛИСК 2.0» на рабочем столе (с иконкой василиска).

Запуск: двойной клик по этому файлу (или ярлык с рабочего стола).
ВАСИЛИСК 2.0 · создатель: ALLENAFS
При поддержке: Carassius, Репозиторий Гитхабович, GLM
"""
from __future__ import annotations

import importlib.util
import os
import queue
import socket
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

ROOT = os.path.dirname(os.path.abspath(__file__))

# --- движок установки (общий с install_all.bat) ---------------------------
_spec = importlib.util.spec_from_file_location(
    "vasilisk_install_all", os.path.join(ROOT, "tools", "install_all.py"))
ia = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(ia)
except Exception as e:                      # установка недоступна — GUI всё равно жив
    ia = None
    _IA_ERROR = str(e)

APP_NAME = "ВАСИЛИСК 2.0"
CREDITS = "создатель: ALLENAFS  ·  при поддержке: Carassius, Репозиторий Гитхабович, GLM"

BG = "#0b0f14"
PANEL = "#10161d"
LINE = "#1f2a33"
FG = "#e6edf3"
MUT = "#8b949e"
GREEN = "#3fb950"
GREEN_D = "#238636"
GREEN_H = "#2ea043"
PURPLE = "#a371f7"
YELLOW = "#d4a72c"
RED = "#f85149"

CHECKS_ORDER = ["deps", "gsi", "param", "llm", "meta", "shortcut"]


class VasiliskCenter:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.ask_answer: "queue.Queue[str | None]" = queue.Queue()
        self.rows: dict = {}
        self.busy = False

        root.title(f"{APP_NAME} — Центр управления")
        root.configure(bg=BG)
        try:
            root.iconbitmap(os.path.join(ROOT, "icon", "vasilisk.ico"))
        except Exception:
            pass
        root.minsize(760, 700)

        self._build_header()
        self._build_checks()
        self._build_actions()
        self._build_log()
        self._build_footer()

        self.log("gray", "Центр управления запущен. Сначала — «УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ».")
        self.log("gray", "Дальше: «ЗАПУСК ТРЕНЕРА» перед игрой в Dota 2.")
        self.after(200, self._poll)
        self.refresh_checks()

    # ------------------------------------------------------------- интерфейс
    def _build_header(self):
        fr = tk.Frame(self.root, bg=BG)
        fr.pack(fill="x", padx=18, pady=(16, 6))
        try:
            self.logo = tk.PhotoImage(file=os.path.join(ROOT, "icon", "vasilisk_logo.png"))
            tk.Label(fr, image=self.logo, bg=BG).pack(side="left", padx=(0, 16))
        except Exception:
            pass
        box = tk.Frame(fr, bg=BG)
        box.pack(side="left", fill="x", expand=True)
        tk.Label(box, text="ВАСИЛИСК 2.0", fg=GREEN, bg=BG,
                 font=("Segoe UI", 26, "bold")).pack(anchor="w")
        tk.Label(box, text="ИИ-тренер по Dota 2: что покупать, куда идти и что делать — "
                           "по актуальным сборкам OpenDota", fg=FG, bg=BG,
                 font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(box, text=CREDITS, fg=PURPLE, bg=BG,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

    def _build_checks(self):
        fr = tk.LabelFrame(self.root, text=" Состояние компонентов ", fg=MUT, bg=PANEL,
                           bd=1, relief="solid", font=("Segoe UI", 9))
        fr.configure(fg=FG)
        fr.pack(fill="x", padx=18, pady=(6, 4), ipady=4)
        titles = {
            "deps": "Python-пакеты (aiohttp)",
            "gsi": "GSI-конфиг в папке Dota 2",
            "param": "Параметр запуска -gamestateintegration",
            "llm": "Ollama + модель ИИ",
            "meta": "Свежий снимок меты OpenDota",
            "shortcut": "Ярлык на рабочем столе",
        }
        for key in CHECKS_ORDER:
            row = tk.Frame(fr, bg=PANEL)
            row.pack(fill="x", padx=10, pady=2)
            mark = tk.Label(row, text="…", fg=MUT, bg=PANEL, width=3,
                            font=("Segoe UI", 11, "bold"))
            mark.pack(side="left")
            tk.Label(row, text=titles[key], fg=FG, bg=PANEL,
                     font=("Segoe UI", 10)).pack(side="left")
            det = tk.Label(row, text="", fg=MUT, bg=PANEL,
                           font=("Segoe UI", 9), anchor="e")
            det.pack(side="right")
            self.rows[key] = (mark, det)

    def _build_actions(self):
        fr = tk.Frame(self.root, bg=BG)
        fr.pack(fill="x", padx=18, pady=6)

        self.llm_var = tk.BooleanVar(value=True)
        tk.Checkbutton(fr, text="ставить ИИ-мозг: Ollama + qwen2.5:7b-instruct (~4,7 ГБ) — "
                                "живые фразы вместо шаблонов",
                       variable=self.llm_var, fg=FG, bg=BG, selectcolor=PANEL,
                       activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))

        self.btn_install = tk.Button(
            fr, text="УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ", bg=GREEN_D, fg="white",
            activebackground=GREEN_H, activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=18, pady=10,
            font=("Segoe UI", 13, "bold"), command=self.on_install)
        self.btn_install.pack(fill="x")

        row = tk.Frame(fr, bg=BG)
        row.pack(fill="x", pady=(8, 0))
        self.btn_run = tk.Button(row, text="▶  ЗАПУСК ТРЕНЕРА", bg=PANEL, fg=GREEN,
                                 activebackground=LINE, relief="flat", bd=0,
                                 cursor="hand2", padx=10, pady=6,
                                 font=("Segoe UI", 10, "bold"), command=self.on_run)
        self.btn_run.pack(side="left", expand=True, fill="x")
        self.btn_panel = tk.Button(row, text="ПАНЕЛЬ (вопросы ИИ, драфт)", bg=PANEL, fg=PURPLE,
                                   activebackground=LINE, relief="flat", bd=0,
                                   cursor="hand2", padx=10, pady=6,
                                   font=("Segoe UI", 10, "bold"), command=self.on_panel)
        self.btn_panel.pack(side="left", expand=True, fill="x")
        self.btn_demo = tk.Button(row, text="ДЕМО-МАТЧ (без Dota 2)", bg=PANEL, fg=YELLOW,
                                  activebackground=LINE, relief="flat", bd=0,
                                  cursor="hand2", padx=10, pady=6,
                                  font=("Segoe UI", 10, "bold"), command=self.on_demo)
        self.btn_demo.pack(side="left", expand=True, fill="x")
        self.btn_log = tk.Button(row, text="открыть лог", bg=PANEL, fg=MUT,
                                 activebackground=LINE, relief="flat", bd=0,
                                 cursor="hand2", padx=10, pady=6,
                                 font=("Segoe UI", 9), command=self.on_open_log)
        self.btn_log.pack(side="left")

    def _build_log(self):
        fr = tk.LabelFrame(self.root, text=" Журнал установки ", fg=FG, bg=PANEL,
                           bd=1, relief="solid", font=("Segoe UI", 9))
        fr.pack(fill="both", expand=True, padx=18, pady=(4, 2))
        self.txt = tk.Text(fr, bg="#060a0e", fg=FG, bd=0, wrap="word",
                           font=("Consolas", 9), height=12, state="disabled")
        self.txt.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(fr, command=self.txt.yview)
        sb.pack(side="right", fill="y")
        self.txt.configure(yscrollcommand=sb.set)
        for tag, color in (("green", GREEN), ("yellow", YELLOW), ("red", RED),
                           ("gray", MUT), ("white", FG), ("purple", PURPLE)):
            self.txt.tag_configure(tag, foreground=color)

    def _build_footer(self):
        tk.Label(self.root, text=f"{APP_NAME} · {CREDITS} · GSI — официальный "
                                 "интерфейс Valve (не чит)", fg=MUT, bg=BG,
                 font=("Segoe UI", 8)).pack(side="bottom", pady=(2, 8))

    # ------------------------------------------------------------- журнал
    def log(self, tag, text):
        self.txt.configure(state="normal")
        self.txt.insert("end", text + "\n", tag)
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def after(self, ms, fn):
        self.root.after(ms, fn)

    # ------------------------------------------------------------- диагностика
    def refresh_checks(self):
        if ia is None:
            self.log("red", f"✗ установщик повреждён: {_IA_ERROR}")
            return
        for mark, det in self.rows.values():
            mark.config(text="…", fg=MUT)
            det.config(text="")
        threading.Thread(target=self._worker_checks, daemon=True).start()

    def _worker_checks(self):
        try:
            results = ia.run_checks()
        except Exception as e:
            self.q.put(("log", ("red", f"✗ диагностика упала: {e}")))
            return
        self.q.put(("checks", results))

    # ------------------------------------------------------------- установка
    def on_install(self):
        if self.busy:
            return
        if ia is None:
            messagebox.showerror(APP_NAME, "Установщик недоступен: " + _IA_ERROR)
            return
        self.busy = True
        self.btn_install.config(text="УСТАНАВЛИВАЮ… не закрывай окно", bg=LINE, fg=MUT)
        self.log("purple", "")
        self.log("purple", "▸ нажата кнопка «УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ» — поехали")
        threading.Thread(target=self._worker_install, daemon=True).start()

    def _worker_install(self):
        def ask(prompt):
            self.q.put(("ask", prompt))
            try:
                return self.ask_answer.get(timeout=600)
            except queue.Empty:
                return None

        try:
            report = ia.install_all(
                log=lambda s: self.q.put(("log", ("white", str(s)))),
                with_llm=self.llm_var.get(), ask=ask)
        except Exception as e:
            self.q.put(("log", ("red", f"✗ установка упала: {e}")))
            report = []
        self.q.put(("done", report))

    # ------------------------------------------------------------- прочие кнопки
    def on_run(self):
        if importlib.util.find_spec("aiohttp") is None:
            messagebox.showwarning(APP_NAME, "Пакетов ещё нет — сначала нажми "
                                             "«УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ».")
            return
        if self._trainer_running():
            self.log("yellow", "▸ Тренер уже запущен (порт 9001 занят). Открой панель кнопкой справа.")
            return
        exe = sys.executable
        if os.name == "nt":
            cand = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if os.path.isfile(cand):
                exe = cand
        try:
            subprocess.Popen([exe, os.path.join(ROOT, "src", "main.py"), "--mode", "overlay"],
                             cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.log("green", "▸ Тренер запущен (оверлей + голос). Окно советов появится "
                              "возле нижней кромки экрана. Полный лог: vasilisk.log")
        except Exception as e:
            self.log("red", f"✗ не удалось запустить тренера: {e}")

    @staticmethod
    def _trainer_running(port=9001):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            return False

    def on_panel(self):
        if not self._trainer_running():
            self.log("yellow", "▸ Тренер не запущен — сначала нажми «ЗАПУСК ТРЕНЕРА».")
            return
        webbrowser.open("http://127.0.0.1:9001/ui")

    def on_demo(self):
        bat = os.path.join(ROOT, "start_demo.bat")
        try:
            if os.name == "nt":
                os.startfile(bat)     # откроет консоль с живым выводом
            else:
                subprocess.Popen(["bash", bat], cwd=ROOT)
            self.log("yellow", "▸ ДЕМО: тренер + симулятор 24-минутного матча без Dota 2 "
                               "(два консольных окна).")
        except Exception as e:
            self.log("red", f"✗ демо не запустилось: {e}")

    def on_open_log(self):
        p = os.path.join(ROOT, "vasilisk.log")
        try:
            if not os.path.isfile(p):
                with open(p, "w", encoding="utf-8") as f:
                    f.write("лог ВАСИЛИСК 2.0 появится после запуска тренера\n")
            if os.name == "nt":
                os.startfile(p)
            else:
                subprocess.Popen(["xdg-open", p])
        except Exception as e:
            self.log("red", f"✗ лог не открылся: {e}")

    # ------------------------------------------------------------- цикл очереди
    def _poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    tag, text = payload
                    self.log(tag, text)
                elif kind == "checks":
                    self._apply_checks(payload)
                elif kind == "ask":
                    self._handle_ask(payload)
                elif kind == "done":
                    self._install_done(payload)
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _apply_checks(self, results):
        for key, _title, ok, detail in results:
            if key not in self.rows:
                continue
            mark, det = self.rows[key]
            if ok is True:
                mark.config(text="✓", fg=GREEN)
            elif ok is False:
                mark.config(text="✗", fg=RED)
            else:
                mark.config(text="?", fg=YELLOW)
            det.config(text=detail or "")
        ready = all(ok is not False for _k, _t, ok, _d in
                    [r for r in results if r[0] != "shortcut"])
        if ready:
            self.log("green", "✓ все компоненты на месте — можно запускать тренер.")

    def _handle_ask(self, prompt):
        self.log("yellow", "▸ " + prompt)
        path = filedialog.askdirectory(
            title="Укажи папку Steam (например C:\\Program Files (x86)\\Steam)",
            initialdir="C:\\")
        self.ask_answer.put(path if path else None)

    def _install_done(self, report):
        self.busy = False
        self.btn_install.config(text="УСТАНОВИТЬ / ПОЧИНИТЬ ВСЁ", bg=GREEN_D, fg="white")
        bad = [r for r in report if r[1] is False]
        if report and not bad:
            self.log("green", "✓ УСТАНОВКА ЗАВЕРШЕНА — всё готово к бою!")
        elif report:
            self.log("yellow", "⚠ завершено, но есть ручные шаги (см. журнал выше).")
        self.refresh_checks()


def main():
    root = tk.Tk()
    VasiliskCenter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
