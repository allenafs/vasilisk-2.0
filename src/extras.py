# -*- coding: utf-8 -*-
"""
Дополнительные правила и утилиты:
  • файты: изменение счёта убийств за последние секунды → «ломайте башню / отходи»;
  • ганк: ульта готова и ресурсы в порядке (нужен блок abilities);
  • контр-предметы и подбор пика по вражескому драфту (данные из data/meta.json);
  • нормализация роли 1-5 → внутренние названия.
Все правила работают только на данных, которые игра реально отдаёт игроку (GSI).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

ROLE_ALIASES = {
    "1": "carry", "pos1": "carry", "керри": "carry",
    "2": "mid", "pos2": "mid", "мид": "mid",
    "3": "offlane", "pos3": "offlane", "оффлейн": "offlane",
    "4": "pos4", "pos4": "pos4",
    "5": "support", "pos5": "support", "саппорт": "support",
}
FIGHT_WINDOW = 30
INVIS = {"Riki", "Clinkz", "Bounty Hunter", "Weaver", "Nyx Assassin", "Mirana", "Invoker", "Sand King"}


def normalize_role(role) -> str:
    r = str(role).strip().lower()
    return ROLE_ALIASES.get(r, r)


# --------------------------------------------------------------------------- драфт
def counter_items(enemies: List[dict]) -> List[dict]:
    """enemies: записи героев из meta (localized_name, roles). Эвристика по ролям."""
    out, names = [], {h.get("localized_name") for h in enemies}
    cnt = lambda role: sum(role in (h.get("roles") or []) for h in enemies)
    if names & INVIS:
        out.append({"item": "Dust of Appearance / Sentry / Gem", "why": "невидимки у врагов: " + ", ".join(sorted(names & INVIS)),
                    "say": "У врагов есть невидимки — купи Дасты или Сентри."})
    if cnt("Disabler") >= 3:
        out.append({"item": "BKB / Linken's Sphere", "why": f"{cnt('Disabler')} героев с контролем",
                    "say": "У врагов много контроля — думай о БКБ или Линкене."})
    if cnt("Nuker") >= 3:
        out.append({"item": "Pipe / Hood / Glimmer Cape", "why": "много магического урона",
                    "say": "У врагов много магического урона — возьми Пайп, Худ или Глиммер."})
    if cnt("Escape") >= 3:
        out.append({"item": "Orchid / Hex / Scythe / Eul's", "why": "много побегов",
                    "say": "У врагов много побегов — нужен Орхид, Хекс или Скайф."})
    if cnt("Carry") >= 3:
        out.append({"item": "Ghost / Force Staff / Shadow Blade", "why": "несколько керри у врагов",
                    "say": "Несколько керри у врагов — нужна выживаемость."})
    return out


def draft_picks(meta: Dict[str, dict], enemy_npc: List[str], ally_npc: List[str], limit=12) -> List[dict]:
    """Лучшие пики против выбранных врагов: средний винрейт кандидата против каждого врага
    (из таблицы матчапов врага: wr_кандидата = 1 - wr_врага_против_кандидата)."""
    import winmodel
    ids = {k: v.get("id") for k, v in meta.items()}
    score: Dict[str, List[float]] = {}
    for e in enemy_npc:
        for row in (meta.get(e) or {}).get("matchups") or []:
            try:
                npc, games, wins = str(row[0]), int(row[1]), int(row[2])
            except (TypeError, ValueError, IndexError):
                continue
            if games >= 30:
                score.setdefault(npc, []).append(1 - wins / games)
    taken = set(enemy_npc) | set(ally_npc)
    res = []
    for npc, vals in score.items():
        if npc in taken or npc not in meta:
            continue
        # нет данных о матчапе против какого-то врага -> считаем нейтральным (50%)
        wr = (sum(vals) + 0.5 * (len(enemy_npc) - len(vals))) / len(enemy_npc)
        m = winmodel.predict([ids[a] for a in ally_npc + [npc] if ids.get(a)],
                             [ids[e] for e in enemy_npc if ids.get(e)])
        res.append({"npc": npc, "name": meta[npc].get("localized_name", npc), "wr": wr, "model": m,
                    "known": len(vals)})
    res.sort(key=lambda r: (-r["known"], -(r["model"] if r["model"] is not None else r["wr"])))
    return res[:limit]


def win_probability(meta, ally_npc, enemy_npc) -> Optional[float]:
    import winmodel
    ids = {k: v.get("id") for k, v in meta.items()}
    return winmodel.predict([ids[a] for a in ally_npc if ids.get(a)], [ids[e] for e in enemy_npc if ids.get(e)])


# --------------------------------------------------------------------------- правила
class ExtraRules:
    """Подключается к Advisor: вызывается из Advisor.on_state(). Возвращает список Advice."""

    def __init__(self, advisor):
        self.adv = advisor
        self.hist: List[tuple] = []        # (clock, мои_убийства, убийства_врагов)
        self.enemies: List[str] = []       # npc-имена вражеских героев (вручную из UI или из миникарты)
        self.allies: List[str] = []
        self._counter_said: set = set()
        self._deaths_warned = -1

    def set_draft(self, enemies, allies):
        self.enemies, self.allies = list(enemies), list(allies)

    def _scores(self, st):
        m = st.map
        mine_key, en_key = ("radiant_score", "dire_score") if st.team == "radiant" else ("dire_score", "radiant_score")
        a, b = m.get(mine_key), m.get(en_key)
        return (a, b) if isinstance(a, int) and isinstance(b, int) else (None, None)

    def on_state(self, st):
        from advisor import PRIORITY_HIGH, PRIORITY_MED
        out, adv = [], self.adv
        if st.clock < 0 or st.game_over:
            return out
        if st.clock < 5 and self.hist and self.hist[-1][0] > st.clock + 5:
            self.hist.clear()                                  # началась новая игра

        # --- враги из миникарты дополняют драфт (если блок приходит)
        for npc in st.enemy_heroes():
            if npc not in self.enemies and len(self.enemies) < 5:
                self.enemies.append(npc)

        # --- файты по счёту убийств
        mine, enemy = self._scores(st)
        if mine is not None:
            if not self.hist or self.hist[-1][1:] != (mine, enemy):
                self.hist.append((st.clock, mine, enemy)); del self.hist[:-60]
            prev = [h for h in self.hist if h[0] < st.clock - FIGHT_WINDOW]
            base = prev[-1] if prev else self.hist[0]
            dm, de = mine - base[1], enemy - base[2]
            key = f"fight:{mine}-{enemy}"
            if dm - de >= 2 and adv._ready(st, key):
                tgt = "Рошана" if str(st.map.get("roshan_state", "")).upper().endswith("ALIVE") and st.clock >= 900 else "ближайшую башню"
                out.append(adv.emit(st, f"Выиграли файт {dm} к {de}. Враги на респауне — ломайте {tgt}, не расходитесь.",
                                    "macro", PRIORITY_HIGH, key=key, cd=45))
            elif de - dm >= 2 and adv._ready(st, key):
                out.append(adv.emit(st, f"Проиграли файт {dm} к {de}. Не форсируй — отходи к башне и жди сбор.",
                                    "defense", PRIORITY_HIGH, key=key, cd=45))

        # --- ганк: ульта готова
        h, ab = st.hero, st.raw.get("abilities") or {}
        spells = [a for a in ab.values() if isinstance(a, dict) and not a.get("passive") and a.get("level", 0) > 0]
        ult = any(a.get("ultimate") and a.get("can_cast") for a in spells)
        ready = sum(1 for a in spells if a.get("can_cast"))
        hp, mp = h.get("health_percent", 100), h.get("mana_percent", 100)
        calm = not (h.get("stunned") or h.get("silenced") or h.get("hexed")) and h.get("alive", True)
        if calm and hp >= 60 and mp >= 40 and adv._ready(st, "gank"):
            if h.get("level", 1) >= 6 and ult and st.clock >= 360:
                out.append(adv.emit(st, "Ульта готова, здоровья и маны хватает — можно идти на ганк.", "macro", PRIORITY_MED, key="gank", cd=100))
            elif 150 <= st.clock < 600 and h.get("level", 1) >= 3 and ready >= 2 and hp >= 70:
                out.append(adv.emit(st, "Скиллы готовы — можно подойти на размен или ганк.", "macro", PRIORITY_MED, key="gank", cd=100))

        # --- слишком много смертей
        p = st.player
        d, k = p.get("deaths", 0), p.get("kills", 0)
        if d >= 4 and d >= k + 4 and d != self._deaths_warned and adv._ready(st, "feed"):
            self._deaths_warned = d
            out.append(adv.emit(st, f"Уже {d} смертей — играй осторожнее, фарми под башней.", "economy", PRIORITY_MED, key="feed", cd=240))

        # --- контр-предметы (один раз на тип)
        meta = adv.builds.meta if adv.builds else {}
        enemy_recs = [meta[e] for e in self.enemies if e in meta]
        for c in counter_items(enemy_recs):
            if c["item"] not in self._counter_said and adv._ready(st, "counter:" + c["item"]):
                self._counter_said.add(c["item"])
                out.append(adv.emit(st, c["say"], "economy", PRIORITY_MED, key="counter:" + c["item"], cd=600))
        return [a for a in out if a]


def build_context(st, adv) -> str:
    """Компактный текст о матче для LLM (только то, что реально известно из GSI и драфта)."""
    meta = adv.builds.meta if adv.builds else {}
    h, p = st.hero, st.player
    ab = [a for a in (st.raw.get("abilities") or {}).values() if isinstance(a, dict)]
    ult = any(a.get("ultimate") and a.get("can_cast") for a in ab)
    mine, enemy = adv.extra._scores(st)
    hero = (st.hero_key or "").replace("npc_dota_hero_", "")
    lines = [f"Герой: {hero}, уровень {h.get('level', '?')}, роль: {adv.role}",
             f"Время: {int(max(st.clock, 0) // 60)} мин, счёт убийств (мы:враги): {mine}:{enemy}",
             f"У меня: {p.get('kills', 0)}/{p.get('deaths', 0)}/{p.get('assists', 0)}, ластхитов {p.get('last_hits', 0)}, "
             f"золото {int(st.gold)}, GPM {int(st.gpm)}, HP {h.get('health_percent', '?')}%, мана {h.get('mana_percent', '?')}%",
             f"Ульта готова: {'да' if ult else 'нет'}"]
    en = [meta[e].get("localized_name", e) for e in adv.extra.enemies if e in meta]
    if en:
        lines.append("Известные враги: " + ", ".join(en))
        wp = win_probability(meta, adv.extra.allies, adv.extra.enemies)
        if wp is not None:
            lines.append(f"Шанс победы по драфту: {int(wp * 100)}%")
    return "\n".join(lines)
