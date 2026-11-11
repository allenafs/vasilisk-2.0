# -*- coding: utf-8 -*-
"""
Рендер советов: консоль (ANSI) или оверлей поверх игры (tkinter).

Оверлей — маленькое всегда-поверх окно у нижней кромки экрана:
строка таймеров (Рошан/варды/цель) + последние советы.
На Windows включается click-through (WS_EX_TRANSPARENT), как у их Tauri-оверлея.

Важно: tkinter создаётся И крутится в одном фоновом потоке
(создание в одном потоке, mainloop в другом = «Tcl from different apartment»).
"""
from __future__ import annotations

import platform
import queue
import threading

PRIO_COLOR = {
    3: "#ff5c5c",   # высокий — красный
    2: "#ffd24a",   # средний — жёлтый
    1: "#9fd6ff",   # низкий — голубой
}
ANSI = {3: "\033[1;91m", 2: "\033[1;93m", 1: "\033[96m"}
RESET = "\033[0m"


def console_line(text: str, prio: int) -> str:
    return f"{ANSI.get(prio, '')}{text}{RESET}"


class ConsoleRenderer:
    """Вывод в терминал: линия таймеров + советы."""

    def __init__(self):
        self.last_timers = ""

    def advice(self, text: str, prio: int, clock: str):
        print(f"[{clock}] {console_line(text, prio)}", flush=True)

    def timers(self, line: str):
        if line and line != self.last_timers:
            self.last_timers = line
            print(f"\033[90m  таймеры: {line}{RESET}", flush=True)


class TkOverlay:
    """Окно-оверлей (Windows/Linux). Потокобезопасно через очередь."""

    def __init__(self, width=540, height=150):
        self.width, self.height = width, height
        self.q: "queue.Queue[tuple]" = queue.Queue(maxsize=50)
        self.started = threading.Event()
        self.error = None
        self.root = None
        self._timers_lbl = None
        self._lines = []

    # ---------------------------------------------------- поток оверлея
    def run_forever(self):
        """Вызывается в фоновом потоке: создаёт окно и крутит mainloop."""
        try:
            self._build()
        except Exception as e:            # нет дисплея и т.п. — фолбэк в консоль
            self.error = e
            self.started.set()
            return
        self.started.set()
        self.root.mainloop()

    def _build(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.title("ВАСИЛИСК 2.0")
        self.root.overrideredirect(True)            # без рамки
        self.root.attributes("-topmost", True)      # поверх всего
        try:
            self.root.attributes("-alpha", 0.9)
        except tk.TclError:
            pass
        self.root.configure(bg="#0d1117")

        self._timers_lbl = tk.Label(self.root, text="ВАСИЛИСК 2.0: ожидание матча…",
                                    fg="#8b949e", bg="#0d1117",
                                    font=("Segoe UI", 11), anchor="w")
        self._timers_lbl.pack(fill="x", padx=10, pady=(8, 2))

        for _ in range(4):
            lbl = tk.Label(self.root, text="", fg="#e6edf3", bg="#0d1117",
                           font=("Segoe UI", 12, "bold"), anchor="w",
                           wraplength=self.width - 20)
            lbl.pack(fill="x", padx=10)
            self._lines.append(lbl)

        self._apply_click_through()

        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = (sw - self.width) // 2
        y = int(sh * 0.70)          # над нижним HUD, не мешая панели
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")
        self.root.after(120, self._poll)

    def _apply_click_through(self):
        if platform.system() != "Windows":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x8000000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE)
        except Exception:
            pass

    # ---------------------------------------------------- api из async-мира
    def advice(self, text: str, prio: int, clock: str):
        try:
            self.q.put_nowait(("adv", text, prio, clock))
        except queue.Full:
            pass

    def timers(self, line: str):
        try:
            self.q.put_nowait(("timers", line))
        except queue.Full:
            pass

    # ---------------------------------------------------- цикл отрисовки
    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "timers":
                    self._timers_lbl.config(text=f"  {msg[1]}")
                elif msg[0] == "adv":
                    _, text, prio, clock = msg
                    color = PRIO_COLOR.get(prio, "#e6edf3")
                    for i in range(len(self._lines) - 1):
                        self._lines[i].config(text=self._lines[i + 1].cget("text"),
                                              fg=self._lines[i + 1].cget("fg"))
                    self._lines[-1].config(text=f"[{clock}] {text}", fg=color)
        except queue.Empty:
            pass
        if self.root is not None:
            self.root.after(120, self._poll)
