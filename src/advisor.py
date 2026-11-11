# -*- coding: utf-8 -*-
"""
Advisor v3 — «мозг» ВАСИЛИСК 2.0: что делать, куда идти и что покупать.

Философия: БЕЗ ВЫДУМАННЫХ ЦИФР. Каждый совет опирается на:
  • состояние матча из GSI (золото, ХП, тайминги, миникарта, башни);
  • реальную статистику OpenDota (снимок data/meta.json + живые запросы):
    тайминги покупок, популярность предметов, перцентили GPM/ластхитов;
  • общеизвестные механики Dota 2 (руны каждые 2/3 мин, руна мудрости с 7:00,
    ночь/день, аегис ~5 мин, Рошан 8–11 мин).

Категории советов: Timing / Buyback / Lane /
Smoke / Resource / Recovery / Defense / Vision / Roshan / Macro / Economy.
"""
from __future__ import annotations

from typing import Optional

from rules_data import (
    GPM_PLAN, ROLE_INDEX, LH_PLAN_10, FARM_HINTS, CONSUMABLES,
    LANE_GUIDE, LANE_RU, ward_spot, item_ru, hero_ru, zone_name,
)
from state import MatchState, mmss
from extras import ExtraRules

PRIORITY_LOW, PRIORITY_MED, PRIORITY_HIGH = 1, 2, 3
MAX_ADVICE_PER_TICK = 4          # не захлёбываем игрока

CAT_CD = {
    "timing": 60, "roshan": 90, "vision": 150, "smoke": 210,
    "buyback": 120, "economy": 300, "lane": 120, "macro": 180,
    "missing": 90, "recovery": 150, "match": 1, "resource": 60,
}

SUPPORT_ROLES = ("support", "pos4")


class Advice:
    __slots__ = ("text", "cat", "prio", "tts", "ttl", "clock", "key")

    def __init__(self, text, cat, prio=PRIORITY_MED, tts=True, ttl=8, key=None, clock=0):
        self.text = text
        self.cat = cat
        self.prio = prio
        self.tts = tts
        self.ttl = ttl
        self.key = key or cat
        self.clock = clock


class Advisor:
    def __init__(self, build_plan=None, role="auto", rank="legend", voice=True,
                 builds=None):
        self.plan = build_plan            # список GoalItem
        self.role = role                  # auto → по тегам героя из снимка
        self.rank = rank
        self.voice = voice
        self.builds = builds              # Builds (реальная статистика)
        self._cd: dict = {}               # ключ -> clock до которого молчим
        self._farm_hint_i = 0
        self._ward_i = 0
        self._start_announced = False
        self._pregame_announced = False
        self._no_data_warned = False
        self._rosh_phase = 0
        self._aegis_hinted = False
        self._gpm_checks = set()
        self._lh_checked = False
        self._smoke_marks = set()
        self._outpost_marks = set()
        self._rune_marks = set()
        self._night_prev: Optional[bool] = None
        self._tome_last = -999
        self._matchup_warned: set = set()   # враги, о чьих вингейтах уже сказали
        self._luxury_said: set = set()     # люксы, о которых уже сказали
        self.match_events: list = []      # журнал (текст, clock, cat, prio)
        self.extra = ExtraRules(self)     # файты, ганк, контр-предметы

    # ------------------------------------------------------------------ utils
    def _ready(self, st: MatchState, key: str, cd=None) -> bool:
        """Проверка кулдауна (без расхода)."""
        cd = cd if cd is not None else CAT_CD.get(key.split(":")[0], 60)
        return self._cd.get(key, -1) <= st.clock

    def _farm_hint(self) -> str:
        h = FARM_HINTS[self._farm_hint_i % len(FARM_HINTS)]
        self._farm_hint_i += 1
        return h

    def _phase(self, clock) -> str:
        if clock < 480:
            return "early"
        if clock < 1200:
            return "mid"
        return "late"

    def emit(self, st, text, cat, prio=PRIORITY_MED, tts=True, key=None, ttl=8,
             cd=None) -> Optional[Advice]:
        if not text:
            return None
        k = key or cat
        self._cd[k] = st.clock + (cd if cd is not None else CAT_CD.get(cat, 60))
        a = Advice(text, cat, prio, tts and self.voice, ttl, k, st.clock)
        self.match_events.append((text, st.clock, cat, prio))
        return a

    # ------------------------------------------------------------------ main
    def on_state(self, st: MatchState):
        """Возвращает список Advice по текущему состоянию (максимум 4 за тик)."""
        out = []
        if st.game_over:
            out.extend(self._on_game_over(st))
            return out

        out.extend(self._on_pregame(st))
        out.extend(self._on_purchases(st))
        out.extend(self._on_minute_tick(st))
        out.extend(self._on_resources(st))
        out.extend(self._on_roshan(st))
        out.extend(self._on_vision(st))
        out.extend(self._on_enemies(st))
        out.extend(self._on_towers(st))
        out.extend(self._on_death(st))
        out.extend(self._on_match_start(st))
        out.extend(self._on_lane_guide(st))
        out.extend(self.extra.on_state(st))
        out = [a for a in out if a]
        out.sort(key=lambda a: -a.prio)
        return out[:MAX_ADVICE_PER_TICK]

    # ------------------------------------------------------------------ старт
    def _on_pregame(self, st: MatchState):
        """Прегейм: реальные стартовые предметы + куда идти."""
        out = []
        if self._pregame_announced or st.match_started or st.clock > 0:
            return out
        if not st.hero_key:
            return out
        self._pregame_announced = True

        start = self.builds.starting_items(st.hero_key) if self.builds else []
        if start:
            items_txt = ", ".join(s["ru"] for s in start[:3])
            src = self.builds.meta_generated_at[:10] if self.builds else ""
            out.append(self.emit(
                st, f"Старт по статистике OpenDota (снимок {src}): {items_txt}.",
                "match", PRIORITY_HIGH, key="pregame:items", ttl=12, cd=1))
        lane = LANE_RU.get(self.role, "свою линию")
        tips = {
            "carry": "иди на лёгкую, проси саппорта закрыть лагеря врага",
            "mid": "мид: блокни лагерь врага до крипов и держи ластхиты",
            "offlane": "сложная: стой за крипами, не теряй ХП на ровном месте",
            "support": "с керри на лёгкую: варди вход в лес, стяни первый лагерь",
            "pos4": "с керри на лёгкую: варди и готовься ротировать на мид",
        }
        tip = tips.get(self.role, "займи свою линию и помоги с вардами")
        out.append(self.emit(st, f"Куда идти: {tip} ({lane}).",
                             "lane", PRIORITY_HIGH, key="pregame:lane", ttl=12, cd=1))
        return out

    def _on_match_start(self, st: MatchState):
        if self._start_announced or not st.match_started:
            return []
        self._start_announced = True
        first = self._current_goal()
        wr_txt = ""
        if self.builds and st.hero_key:
            mr = self.builds.meta_win_rate(st.hero_key)
            if mr and (mr[1] or 0) >= 100:
                wr_txt = f" Винрейт героя по OpenDota: {mr[0] * 100:.0f}%."
        if first:
            return [self.emit(st, f"Матч начался. План: {first.ru} к {first.target_min}-й минуте. Фармим.{wr_txt}",
                              "match", PRIORITY_MED, key="match:start")]
        if not self._no_data_warned and self.builds and not self.builds.has_meta(st.hero_key or ""):
            self._no_data_warned = True
            return [self.emit(st, "Нет данных по герою в снимке. Обнови: python tools/fetch_meta.py",
                              "match", PRIORITY_LOW, tts=False, key="match:nodata")]
        return [self.emit(st, "Матч начался. Играй по плану и следи за картой.", "match",
                          PRIORITY_MED, key="match:start")]

    def _current_goal(self):
        if not self.plan:
            return None
        for g in self.plan:
            if not g.done:
                return g
        return None

    # ------------------------------------------------------------------ покупки
    def _on_purchases(self, st: MatchState):
        out = []
        for name in st.recent_purchases:
            if name == "item_smoke_of_deceit":
                out.append(self.emit(st, "Смоук куплен — собери группу и проверь Рошана или их лес.",
                                     "smoke", PRIORITY_MED, key="smoke:bought"))
                continue
            if name == "item_aegis":
                out.append(self.emit(st, "Аегис твой: живи эти 5 минут и толкай объекты.",
                                     "roshan", PRIORITY_HIGH, key="roshan:aegis_pick"))
                continue
            if name == "item_cheese":
                out.append(self.emit(st, "Чиз в кармане: держи до драки — мгновенное ХП.",
                                     "roshan", PRIORITY_LOW, key="roshan:cheese", tts=False))
                continue
            if name == "item_gem":
                out.append(self.emit(st, "Гем куплен: вычисти их варды, но не умирай с ним.",
                                     "vision", PRIORITY_MED, key="vision:gem"))
                continue
            if name == "item_ward_observer":
                spot, why = ward_spot(self._phase(st.clock), self._ward_i)
                out.append(self.emit(st, f"Обсервер куплен: поставь {spot} — {why}.",
                                     "vision", PRIORITY_MED, key="vision:bought_obs"))
                continue
            if name == "item_ward_sentry":
                out.append(self.emit(st, "Сентри в кармане: грей вард в их лес или на Рошана.",
                                     "vision", PRIORITY_LOW, key="vision:bought_sen"))
                continue
            if name == "item_tome_of_knowledge":
                out.append(self.emit(st, "Томик съеден — опыт пошёл команде.",
                                     "economy", PRIORITY_LOW, tts=False,
                                     key=f"tome:{int(st.clock // 60)}"))
                continue
            if name in CONSUMABLES:
                continue
            key = name.replace("item_", "", 1)
            goal = next((g for g in (self.plan or []) if g.key == key), None)
            if goal and not goal.done:
                goal.done = True
                goal.done_clock = st.clock
                delta = st.clock / 60.0 - goal.target_min
                verdict = "в целевом окне" if delta <= 1.5 else "поздновато, но норм"
                nxt = self._current_goal()
                nxt_txt = f" Следующая цель: {nxt.ru} к {nxt.target_min}-й." if nxt else ""
                out.append(self.emit(
                    st, f"{goal.ru} собран на {mmss(st.clock)} — {verdict}.{nxt_txt}",
                    "timing", PRIORITY_HIGH, key=f"timing:done:{key}"))
            else:
                ru, _ = item_ru(key)
                out.append(self.emit(st, f"{ru} куплен — вне плана, учтён в нетворсе.", "timing",
                                     PRIORITY_LOW, key=f"timing:extra:{key}", tts=False))
        return out

    # ------------------------------------------------------------------ минуты
    def _on_minute_tick(self, st: MatchState):
        out = []
        if not st.match_started or st.clock < 0:
            return out
        minute = int(st.clock // 60)
        sec = int(st.clock % 60)
        goal = self._current_goal()
        gold = st.gold

        # --- тайминги кор-итемов
        if goal and self._ready(st, f"tick:goal:{goal.key}", 75):
            if gold >= goal.cost:
                out.append(self.emit(
                    st, f"Добираем {goal.ru}: золота хватает ({int(gold)}). {self._farm_hint().capitalize()}.",
                    "timing", PRIORITY_MED, key=f"timing:afford:{goal.key}"))
            elif st.clock / 60.0 >= goal.target_min:
                diff = int(goal.cost - gold)
                late = st.clock / 60.0 >= goal.target_min + 4
                if late:
                    out.append(self.emit(
                        st, f"{goal.ru} критичен: цель была к {goal.target_min}-й, не хватает {diff} золота. Держи фарм без смертей.",
                        "timing", PRIORITY_HIGH, key=f"timing:late:{goal.key}"))
                else:
                    out.append(self.emit(
                        st, f"До {goal.ru} не хватает {diff} золота — {self._farm_hint()}.",
                        "timing", PRIORITY_MED, key=f"timing:need:{goal.key}"))

        # --- нет ТП в кармане
        if st.hero.get("alive") and st.clock >= 180:
            inv_tp = st.inventory_names()
            if not inv_tp & {"item_tpscroll", "item_travel_boots", "item_travel_boots_2"} \
                    and self._ready(st, "lane:tp", 240):
                out.append(self.emit(st, "Нет свитка ТП — купи телепорт, ротации дороже.",
                                     "lane", PRIORITY_MED, key="lane:tp"))

        # --- кор-план закрыт: люкс по реальной статистике
        if (self.plan and all(g.done for g in self.plan) and st.clock >= 900
                and self.builds):
            for lux in self.builds.luxury_items(st.hero_key or "", st.inventory_names(), top=3):
                if lux["key"] in self._luxury_said:
                    continue
                self._luxury_said.add(lux["key"])
                out.append(self.emit(
                    st, f"Кор-план закрыт: дальше по статистике — {lux['ru']} "
                        f"(один из топовых лейт-предметов на этом герое).",
                    "timing", PRIORITY_LOW, key=f"luxury:{lux['key']}", tts=False))

        # --- руны: сила каждые 2 мин (с 2:00), изобилие в лесу каждые 3 мин (с 3:00)
        if minute >= 2 and minute % 2 == 0 and 48 <= sec <= 58:
            mk = f"rune:power:{minute}"
            if mk not in self._rune_marks:
                self._rune_marks.add(mk)
                out.append(self.emit(st, "Руна силы через 10 секунд — займи позицию у реки.",
                                     "lane", PRIORITY_LOW, tts=False, key=mk))
        if minute >= 3 and minute % 3 == 0 and 48 <= sec <= 58:
            mk = f"rune:bounty:{minute}"
            if mk not in self._rune_marks:
                self._rune_marks.add(mk)
                out.append(self.emit(st, "Руны изобилия в лесу через 10 секунд — забери свои.",
                                     "lane", PRIORITY_LOW, tts=False, key=mk))

        # --- стаки :53 для саппортов (2–12 мин)
        if self.role in SUPPORT_ROLES and 2 <= minute <= 12 and 50 <= sec <= 58:
            if self._ready(st, "lane:stack", 115):
                out.append(self.emit(st, "53-я секунда — застакай лагерь для керри.",
                                     "lane", PRIORITY_MED, key="lane:stack"))

        # --- руна мудрости: 7:00 и далее каждые 7 минут (с патча 7.33 она заменила томик;
        #     аутпосты опыта и обзора больше не дают — советов про них нет)
        if minute >= 6 and (minute + 1) % 7 == 0 and 48 <= sec <= 58:
            mk = f"rune:wisdom:{minute}"
            if mk not in self._rune_marks:
                self._rune_marks.add(mk)
                out.append(self.emit(st, "Руна мудрости через 10 секунд — не отдавай её врагу, опыт всей команде.",
                                     "macro", PRIORITY_MED, key=mk))

        # --- GPM-чек на 10/20 минутах: РЕАЛЬНЫЕ перцентили героя
        if minute in (10, 20) and minute not in self._gpm_checks:
            self._gpm_checks.add(minute)
            gpm = st.gpm
            bench = (self.builds.benchmarks(st.hero_key) if self.builds else {}).get("gpm")
            if gpm and bench:
                if gpm < bench["p20"]:
                    out.append(self.emit(
                        st, f"GPM {int(gpm)} ниже 20-го перцентиля ({bench['p20']} по OpenDota): "
                            f"{self._farm_hint()}, меньше смертей.",
                        "economy", PRIORITY_HIGH, key=f"economy:{minute}"))
                elif gpm < bench["p50"] * 0.9:
                    out.append(self.emit(
                        st, f"GPM {int(gpm)} ниже медианы героя ({bench['p50']}) — поджимай фарм.",
                        "economy", PRIORITY_MED, key=f"economy:{minute}"))
                elif gpm > bench["p80"]:
                    out.append(self.emit(st, f"GPM {int(gpm)} выше 80-го перцентиля — продавливай темп.",
                                          "economy", PRIORITY_LOW, tts=False, key=f"economy:{minute}"))
            elif gpm:
                plan = GPM_PLAN.get(self.rank, GPM_PLAN["legend"])[ROLE_INDEX.get(self.role, 0)]
                if gpm < plan * 0.85:
                    out.append(self.emit(
                        st, f"GPM {int(gpm)} ниже плана {plan}: {self._farm_hint()}, меньше смертей.",
                        "economy", PRIORITY_MED, key=f"economy:{minute}"))

        # --- ластхиты на 10-й (реальная планка из бенчмарков)
        if minute == 10 and not self._lh_checked:
            self._lh_checked = True
            lh = st.player.get("last_hits")
            bench = (self.builds.benchmarks(st.hero_key) if self.builds else {}).get("lh_per_min")
            plan_lh = int(bench["p50"] * 10) if bench else LH_PLAN_10.get(self.role, 40)
            if isinstance(lh, (int, float)) and lh < plan_lh * 0.8:
                out.append(self.emit(
                    st, f"К 10-й минуте {int(lh)} ластхитов из ~{plan_lh} (медиана OpenDota): навёрстывай в лесу.",
                    "lane", PRIORITY_MED, key="lane:lh10"))

        # --- смок в ключевые минуты
        if minute in (15, 22, 30) and f"smoke:{minute}" not in self._smoke_marks:
            self._smoke_marks.add(f"smoke:{minute}")
            rt = st.roshan_timers()
            target = "Рошана" if (rt.get("window") or st.roshan_death_clock) else "их лес"
            out.append(self.emit(st, f"Время смока: собери двоих-троих и иди на {target}.",
                                 "smoke", PRIORITY_MED, key=f"smoke:{minute}"))

        # --- байбек: держать золото после 25-й
        hero = st.hero
        if hero.get("alive") and minute >= 25:
            bb = hero.get("buyback_cost") or 0
            if bb and gold >= bb and self._ready(st, "buyback:hold", 300):
                out.append(self.emit(
                    st, f"Держи {int(gold)} золота: {int(bb)} — на байбек, не трать всё.",
                    "buyback", PRIORITY_MED, key="buyback:hold"))

        # --- мёртв: байбек по делу
        if hero.get("alive") is False:
            respawn = hero.get("respawn_seconds") or 0
            bb_cost = hero.get("buyback_cost") or 0
            if isinstance(respawn, (int, float)) and respawn > 25 and bb_cost and gold >= bb_cost:
                rt = st.roshan_timers()
                objective = "Рошан вот-вот" if (rt.get("window") or st.roshan_death_clock) else "объектив рядом"
                out.append(self.emit(
                    st, f"Есть {int(gold)} на байбек ({int(bb_cost)}) — {objective}: возвращайся.",
                    "buyback", PRIORITY_HIGH, key="buyback:hint"))
        return out

    # ------------------------------------------------------------------ ресурсы
    def _on_resources(self, st: MatchState):
        out = []
        h = st.hero
        if not h.get("alive"):
            return out
        try:
            hp, mhp = float(h.get("health") or 0), float(h.get("max_health") or 0)
            mn, mmn = float(h.get("mana") or 0), float(h.get("max_mana") or 0)
        except (TypeError, ValueError):
            return out
        # ХП мало + враг в вижене → отход
        if mhp and hp / mhp < 0.3 and st.enemy_visible_count >= 1 and self._ready(st, "resource:hp", 45):
            out.append(self.emit(
                st, f"ХП критично ({int(hp)}/{int(mhp)}) — отойди из вижена врага.",
                "resource", PRIORITY_HIGH, key="resource:hp", cd=45))
        # мана на нуле — не инициируй
        if mmn and mn / mmn < 0.12 and self._ready(st, "resource:mana", 90):
            out.append(self.emit(st, "Мана почти ноль — не инициируй, отойди восполниться.",
                                 "resource", PRIORITY_LOW, key="resource:mana", cd=90))
        return out

    # ------------------------------------------------------------------ ночь/день
    def _on_lane_guide(self, st: MatchState):
        out = []
        if not st.match_started:
            return out
        # переход ночь/день
        if st.daynight_changed:
            if st.is_night:
                out.append(self.emit(st, "Ночь: поставь вард на руне — ганги в темноте.",
                                     "vision", PRIORITY_MED, key="vision:night", cd=60))
            else:
                out.append(self.emit(st, "Рассвет — обнови варды в лесу.",
                                     "vision", PRIORITY_LOW, tts=False, key="vision:dawn", cd=60))
        # общий гайд «куда идти» по роли и фазе
        if self._ready(st, "lane:guide", 300):
            guide = LANE_GUIDE.get(self._phase(st.clock), {}).get(self.role)
            if guide:
                out.append(self.emit(st, guide.capitalize() + ".",
                                     "lane", PRIORITY_LOW, tts=False,
                                     key="lane:guide", cd=300))
        return out

    # ------------------------------------------------------------------ Рошан
    def _on_roshan(self, st: MatchState):
        out = []
        if st.roshan_death_clock is not None and self._rosh_phase < 1:
            self._rosh_phase = 1
            self._aegis_hinted = False
            d = st.roshan_death_clock
            out.append(self.emit(
                st, f"Рошан пал на {mmss(d)}. Аегис ~5 минут, следующий — {mmss(d + 480)}–{mmss(d + 660)}.",
                "roshan", PRIORITY_HIGH, key="roshan:death"))
        if (st.roshan_death_clock is not None and self._rosh_phase == 1
                and st.clock >= (st.aegis_pick_clock or st.roshan_death_clock) + 300 and not self._aegis_hinted):
            self._aegis_hinted = True
            self._rosh_phase = 2
            out.append(self.emit(st, "Аегис истёк: соперники пойдут на нового Рошана — держи питу под контролем.",
                                 "roshan", PRIORITY_MED, key="roshan:aegis_end"))
        if (st.roshan_death_clock is not None and self._rosh_phase == 2
                and st.clock >= st.roshan_death_clock + 480):
            self._rosh_phase = 3
            spot, _why = ward_spot("late", 0)
            out.append(self.emit(
                st, f"Окно Рошана открыто ({mmss(st.roshan_death_clock + 480)}–{mmss(st.roshan_death_clock + 660)}): "
                    f"{spot} под контролем и смок в питу.",
                "roshan", PRIORITY_HIGH, key="roshan:window"))
        rs = str(st.map.get("roshan_state") or "")
        if "ALIVE" in rs.upper() and st.roshan_death_clock is not None and self._rosh_phase == 3:
            self._rosh_phase = 0
            st.roshan_death_clock = None
            st.aegis_pick_clock = None
            out.append(self.emit(st, "Рошан заспавнился!", "roshan", PRIORITY_HIGH, key="roshan:alive"))
        return out

    # ------------------------------------------------------------------ вижн
    def _on_vision(self, st: MatchState):
        out = []
        minute = st.clock / 60.0
        inv = st.inventory_names()
        if minute >= 6 and self._ready(st, "vision:cycle", 150):
            if "item_ward_observer" in inv:
                spot, why = ward_spot(self._phase(st.clock), self._ward_i)
                self._ward_i += 1
                out.append(self.emit(st, f"Обсервер лежит в кармане: {spot} — {why}.",
                                     "vision", PRIORITY_MED, key="vision:cycle"))
            elif self.role in SUPPORT_ROLES:
                wp = st.player.get("wards_placed")
                last = st.own_wards_last_placed
                stale = (not isinstance(wp, (int, float)) or wp <= 0) and minute > 8
                if stale or (last is not None and st.clock - last > 210):
                    spot, why = ward_spot(self._phase(st.clock), self._ward_i)
                    self._ward_i += 1
                    out.append(self.emit(st, f"Карта тёмная: поставь вард {spot} — {why}.",
                                         "vision", PRIORITY_MED, key="vision:cycle"))
        for unit in st.enemy_last_known:
            if any(h in unit for h in ("riki", "bounty_hunter", "nyx", "clinkz", "broodmother", "weaver", "invoker")):
                if "item_ward_sentry" not in inv and self._ready(st, f"vision:sentry:{unit}", 420):
                    out.append(self.emit(
                        st, f"Против {hero_ru(unit)} — сентри: ставь на подходе к линии.",
                        "vision", PRIORITY_MED, key=f"vision:sentry:{unit}"))
                break
        wcd = (st.map.get("ward_purchase_cooldown")
               or st.map.get("radiant_ward_purchase_cooldown" if st.team == "radiant"
                             else "dire_ward_purchase_cooldown"))
        if isinstance(wcd, (int, float)) and 0 < wcd < 3 and self._ready(st, "vision:cd", 120):
            out.append(self.emit(st, "Варды только что ушли с кулдауна — докупай обзор.",
                                 "vision", PRIORITY_LOW, key="vision:cd", tts=False))
        return out

    # ------------------------------------------------------------------ враги
    def _on_enemies(self, st: MatchState):
        out = []
        # --- реальные матчапы против видимых врагов (OpenDota, без выдумок)
        if self.builds and st.hero_key:
            for unit in list(st.enemy_seen):
                if unit in self._matchup_warned:
                    continue
                info = self.builds.matchup_vs(st.hero_key, unit)
                if not info or info["games"] < 30:
                    continue
                self._matchup_warned.add(unit)
                if info["wr"] <= 0.47:
                    out.append(self.emit(
                        st, f"{hero_ru(unit)} — жёсткий матчап: против него по OpenDota "
                            f"{info['wr'] * 100:.0f}% побед ({info['games']} матчей). Играй аккуратнее.",
                        "match", PRIORITY_MED, key=f"matchup:{unit}"))
                elif info["wr"] >= 0.56:
                    out.append(self.emit(
                        st, f"{hero_ru(unit)} — комфортный матчап: {info['wr'] * 100:.0f}% побед "
                            f"по OpenDota ({info['games']} матчей) — дави его.",
                        "match", PRIORITY_LOW, key=f"matchup:{unit}", tts=False))
        # весь состав пропал → смок-опасность
        if len(st.enemy_vanished) >= 3 and self._ready(st, "missing:team", 120):
            out.append(self.emit(
                st, f"{len(st.enemy_vanished)} врага пропали с карты — вероятно смок: отойди от реки.",
                "missing", PRIORITY_HIGH, key="missing:team", cd=120))
        for unit in st.enemy_vanished:
            lk = st.enemy_last_known.get(unit)
            if not lk:
                continue
            zone = zone_name(lk.get("x"), lk.get("y"))
            if self._ready(st, f"missing:{unit}", 120):
                out.append(self.emit(
                    st, f"{hero_ru(unit)} пропал из вижена ({zone}, {mmss(lk['clock'])}) — отойди и жди ганк.",
                    "missing", PRIORITY_HIGH, key=f"missing:{unit}"))
        return out

    # ------------------------------------------------------------------ башни
    def _on_towers(self, st: MatchState):
        out = []
        for path in st.towers_destroyed:
            low = path.lower()
            if "badguys" in low or ("team3" in low and "tower" in low):
                lane = "топ" if "top" in low else ("бот" if "bot" in low else "мид")
                tier = next((t for t in ("tower1", "tower2", "tower3") if t in low), "tower")
                rt = st.roshan_timers()
                window_open = rt.get("window") and st.clock >= rt["window"][0] - 120
                if window_open:
                    out.append(self.emit(
                        st, f"Их {tier.replace('tower', 'Т')}({lane}) пал — отпушь {lane}, затем стягивайся к Рошану.",
                        "macro", PRIORITY_HIGH, key=f"macro:tower:{path}", ttl=10))
                else:
                    out.append(self.emit(
                        st, f"Их {tier.replace('tower', 'Т')}({lane}) пал — пуш {lane} и контроль леса.",
                        "macro", PRIORITY_MED, key=f"macro:tower:{path}"))
            elif "goodguys" in low or ("team2" in low and "tower" in low):
                if "tower3" in low:
                    out.append(self.emit(
                        st, "Наша Т3 пала — дефь базу: соберись пятерыми, не разделяйся.",
                        "defense", PRIORITY_HIGH, key=f"defense:tower:{path}", ttl=10))
                else:
                    out.append(self.emit(st, "Наша башня пала — соберись и защити следующие объекты.",
                                         "macro", PRIORITY_MED, key=f"macro:tower:{path}", tts=False))
        return out

    # ------------------------------------------------------------------ смерть
    def _on_death(self, st: MatchState):
        out = []
        if st.just_died:
            respawn = st.hero.get("respawn_seconds") or 0
            gold = st.gold
            hint = f"Возрождение через {int(respawn)}с." if isinstance(respawn, (int, float)) and respawn else "Держи спокойствие."
            out.append(self.emit(
                st, f"Ты умер на {st.fmt_clock()} — {hint} Не флуди, купи расходники и держи ТП.",
                "recovery", PRIORITY_MED, key=f"recovery:{int(st.clock // 60)}"))
            goal = self._current_goal()
            if goal:
                diff = max(0, int(goal.cost - gold))
                out.append(self.emit(
                    st, f"После респавна — сразу в фарм: до {goal.ru} не хватает {diff} золота.",
                    "recovery", PRIORITY_LOW, key=f"recovery:goal:{goal.key}", ttl=10))
        return out

    # ------------------------------------------------------------------ конец
    def _on_game_over(self, st: MatchState):
        win = str(st.map.get("win_team") or "")
        my = st.team
        if win:
            won = ("radiant" in win and my == "radiant") or ("dire" in win and my == "dire")
            msg = "Матч выигран! Красиво." if won else "Матч проигран. Разбор будет полезен."
        else:
            msg = "Матч окончен."
        if self._ready(st, "match:end", 1):
            return [self.emit(st, msg + " Разбор матча: python src/post_match.py", "match",
                              PRIORITY_HIGH, key="match:end", ttl=12)]
        return []

    # ------------------------------------------------------------------ панель
    def timers_panel(self, st: MatchState) -> str:
        parts = []
        rt = st.roshan_timers()
        if rt.get("respawn_in"):
            parts.append(f"Рошан: через {mmss(rt['respawn_in'])}")
        elif st.roshan_death_clock is not None:
            w = rt.get("window")
            if st.clock < st.roshan_death_clock + 480:
                parts.append(f"Рошан: окно {mmss(w[0])}–{mmss(w[1])}")
            else:
                parts.append("Рошан: может заспавниться")
        else:
            parts.append("Рошан: жив" if st.match_started else "Рошан: —")
        goal = self._current_goal()
        if goal:
            parts.append(f"Цель: {goal.ru} к {goal.target_min}-й")
        if st.is_night:
            parts.append("ночь")
        dead = st.hero.get("respawn_seconds")
        if isinstance(dead, (int, float)) and dead > 0:
            parts.append(f"Респавн: {mmss(dead)}")
        return "  |  ".join(parts)
