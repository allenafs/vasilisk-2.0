# -*- coding: utf-8 -*-
"""
Статическая база знаний тренера ВАСИЛИСК 2.0.
Цены предметов добираются онлайн из OpenDota /api/constants/items,
поэтому здесь только фолбэк и русские названия.

ПРИМЕЧАНИЕ: тайминги/цены в Dota меняются от патча к патчу.
При наличии интернета прототип берёт актуальные данные сам.
"""

# ---------------------------------------------------------------------------
# Русские названия популярных предметов (ключ = имя GSI/OpenDota без item_)
ITEM_RU = {
    "power_treads":      ("ПТ",            1400),
    "phase_boots":       ("Фаза",          1300),
    "arcane_boots":      ("Арканы",        1300),
    "boots":             ("Ботинки",        500),
    "travel_boots":      ("ТП-боты",       2500),
    "bfury":             ("Батл фьюри",    4300),
    "black_king_bar":    ("БКБ",           4050),
    "blink":             ("Блинк",         2250),
    "blink_dagger":      ("Блинк",         2250),
    "manta":             ("Манта",         4600),
    "diffusal_blade":    ("Диффуз",        3100),
    "butterfly":         ("Бабочка",       4975),
    "satanic":           ("Сатаник",       5050),
    "skadi":             ("Скади",         5300),
    "abyssal_blade":     ("Абиссал",       5400),
    "greater_crit":      ("Дэдэлус",      5300),
    "desolator":         ("Дезолятор",     3500),
    "radiance":          ("Радианс",       5100),
    "assault":           ("Ассаулт",       4150),
    "heart":             ("Сердце",        5000),
    "shivas_guard":      ("Шива",          4850),
    "blade_mail":        ("Блэйдмэйл",     2200),
    "vanguard":          ("Вангард",       2150),
    "crimson_guard":     ("Кримсон",       3800),
    "pipe":              ("Пайп",          4200),
    "mekansm":           ("Меканизм",      2300),
    "guardian_greaves":  ("Гривз",         5250),
    "aether_lens":       ("Линза",         2300),
    "ultimate_scepter":  ("Аганим",        4200),
    "octarine_core":     ("Октарин",       4700),
    "refresher":         ("Рефрешер",      5000),
    "sheepstick":        ("Хекс",          5675),
    "force_staff":       ("Форс-стафф",    2200),
    "glimmer_cape":      ("Глиммер",       2150),
    "ghost":             ("Гост-серп",    5000),
    "euls_scepter":      ("Еуль",          2725),
    "orchid":            ("Орхидея",       3475),
    "hurricane_pike":    ("Пика",          4375),
    "silver_edge":       ("Сильвер",       4550),
    "solar_crest":       ("Соларка",       3900),
    "spirit_vessel":     ("Вессел",        2940),
    "urn_of_shadows":    ("Урна",           880),
    "medallion_of_courage": ("Медальон",   1200),
    "witch_blade":       ("Витч-блэйд",    2700),
    "meteor_hammer":     ("Метеор",        2350),
    "sange_yasha":       ("СнЯ",           4100),
    "disperser":         ("Дисперсер",     5550),
    "harpoon":           ("Харпун",        4950),
    "bloodstone":        ("Блудстоун",     4400),
    "eternal_shroud":    ("Шрауд",         3900),
    "wind_waker":        ("Виндвейкер",    5675),
    "rod_of_atos":       ("Атос",          2700),
    "veil_of_discord":   ("Вейл",          2200),
    "hand_of_midas":     ("Мидас",         2200),
    "maelstrom":         ("Мьолнир(осн)",  2700),
    "mjollnir":          ("Мьолнир",       4900),
    "dragon_lance":      ("Ланса",         1900),
    "mask_of_madness":   ("МоМ",           1775),
    "helm_of_the_dominator": ("Хельм",     2350),
    "echo_sabre":        ("Эхо-сабля",     2500),
    "falcon_blade":      ("Фалькон",       1125),
    "dagon":             ("Дагон",         1250),
}

# Расходники и мелочь — не считаем "коровой" сборки (GSI имена с item_)
CONSUMABLES = {
    "item_tango", "item_flask", "item_clarity", "item_branches", "item_faerie_fire",
    "item_tpscroll", "item_ward_observer", "item_ward_sentry", "item_ward_dispenser",
    "item_smoke_of_deceit", "item_dust", "item_gem", "item_enchanted_mango",
    "item_blood_grenade", "item_quelling_blade", "item_magic_stick", "item_ring_of_protection",
    "item_circlet", "item_slippers", "item_gauntlets", "item_mantle", "item_belt_of_strength",
    "item_boots", "item_wind_lace", "item_orb_of_venom", "item_blades_of_attack",
    "item_recipe", "item_bracer", "item_wraith_band", "item_null_talisman",
}

# ---------------------------------------------------------------------------
# Русские названия героев (ключ = npc_dota_hero_xxx)
HERO_RU = {
    "npc_dota_hero_juggernaut": "Джаггернаут",
    "npc_dota_hero_zuus": "Зевс",
    "npc_dota_hero_mars": "Марс",
    "npc_dota_hero_pudge": "Пудж",
    "npc_dota_hero_axe": "Акс",
    "npc_dota_hero_antimage": "АМ",
    "npc_dota_hero_phantom_assassin": "ПА",
    "npc_dota_hero_spectre": "Спектра",
    "npc_dota_hero_drow_ranger": "Дроу",
    "npc_dota_hero_sniper": "Снайпер",
    "npc_dota_hero_faceless_void": "Фейслесс",
    "npc_dota_hero_slark": "Сларк",
    "npc_dota_hero_luna": "Луна",
    "npc_dota_hero_sven": "Свен",
    "npc_dota_hero_tiny": "Тини",
    "npc_dota_hero_nevermore": "СФ",
    "npc_dota_hero_storm_spirit": "Сторм",
    "npc_dota_hero_puck": "Пак",
    "npc_dota_hero_queenofpain": "КьюПи",
    "npc_dota_hero_tinker": "Тинкер",
    "npc_dota_hero_riki": "Рики",
    "npc_dota_hero_bounty_hunter": "Баунти",
    "npc_dota_hero_nyx_assassin": "Никс",
    "npc_dota_hero_broodmother": "Бруда",
    "npc_dota_hero_clinkz": "Клинз",
    "npc_dota_hero_weaver": "Вивер",
    "npc_dota_hero_invoker": "Инвокер",
    "npc_dota_hero_mirana": "Мирана",
    "npc_dota_hero_lina": "Лина",
    "npc_dota_hero_lion": "Лайон",
    "npc_dota_hero_crystal_maiden": "Кристалка",
    "npc_dota_hero_witch_doctor": "Вичдоктор",
    "npc_dota_hero_shadow_shaman": "Шаман",
    "npc_dota_hero_earthshaker": "Эршейкер",
    "npc_dota_hero_tidehunter": "Тайд",
    "npc_dota_hero_undying": "Андаинг",
    "npc_dota_hero_lich": "Лич",
    "npc_dota_hero_disruptor": "Дизраптор",
    "npc_dota_hero_warlock": "Варлок",
    "npc_dota_hero_oracle": "Оракл",
    "npc_dota_hero_winter_wyvern": "Виверна",
    "npc_dota_hero_dazzle": "Даззл",
    "npc_dota_hero_mars": "Марс",
    "npc_dota_hero_ursa": "Урса",
    "npc_dota_hero_templar_assassin": "ТА",
    "npc_dota_hero_viper": "Вайпер",
    "npc_dota_hero_razor": "Рэйзор",
    "npc_dota_hero_venomancer": "Веномансер",
    "npc_dota_hero_leshrac": "Лешрак",
    "npc_dota_hero_death_prophet": "ДП",
    "npc_dota_hero_necrophos": "Некрофос",
    "npc_dota_hero_batrider": "Бэтрайдер",
    "npc_dota_hero_beastmaster": "Бистмастер",
    "npc_dota_hero_magnataur": "Магнус",
    "npc_dota_hero_magnus": "Магнус",
    "npc_dota_hero_shredder": "Тимбер",
    "npc_dota_hero_timbersaw": "Тимбер",
    "npc_dota_hero_bristleback": "Бристл",
    "npc_dota_hero_centaur": "Кентавр",
    "npc_dota_hero_legion_commander": "Легион",
    "npc_dota_hero_omniknight": "Омник",
    "npc_dota_hero_dark_seer": "Дарк Сир",
    "npc_dota_hero_enigma": "Энигма",
    "npc_dota_hero_chen": "Чен",
    "npc_dota_hero_enchantress": "Энча",
    "npc_dota_hero_furion": "НП",
    "npc_dota_hero_natures_prophet": "НП",
    "npc_dota_hero_keeper_of_the_light": "КотЛ",
    "npc_dota_hero_phoenix": "Феникс",
    "npc_dota_hero_sand_king": "Сэнд Кинг",
    "npc_dota_hero_skywrath_mage": "Скайврат",
    "npc_dota_hero_ancient_apparition": "АА",
    "npc_dota_hero_pugna": "Пугна",
    "npc_dota_hero_windranger": "Виндраннер",
    "npc_dota_hero_windrunner": "Виндраннер",
    "npc_dota_hero_silencer": "Сайленсер",
    "npc_dota_hero_kunkka": "Кунка",
    "npc_dota_hero_pangolier": "Панголир",
    "npc_dota_hero_void_spirit": "Войд Спирит",
    "npc_dota_hero_grimstroke": "Гримстроук",
    "npc_dota_hero_hoodwink": "Худвинк",
    "npc_dota_hero_snapfire": "Снапфайр",
    "npc_dota_hero_muerta": "Муэрта",
    "npc_dota_hero_primal_beast": "Праймал",
    "npc_dota_hero_ringmaster": "Рингмастер",
    "npc_dota_hero_kez": "Кез",
}

# ---------------------------------------------------------------------------
# Статические сборки-фолбэки (когда нет интернета): npc-имя героя -> список
# (item_key, target_min). Цены подтянутся из ITEM_RU/констант.
STATIC_BUILDS = {
    "npc_dota_hero_juggernaut": [
        ("power_treads", 8), ("falcon_blade", 10), ("bfury", 17),
        ("mjollnir", 24), ("black_king_bar", 27), ("satanic", 33),
    ],
    "npc_dota_hero_phantom_assassin": [
        ("power_treads", 8), ("bfury", 16), ("desolator", 21),
        ("black_king_bar", 25), ("satanic", 32),
    ],
    "npc_dota_hero_spectre": [
        ("power_treads", 8), ("falcon_blade", 10), ("diffusal_blade", 17),
        ("manta", 23), ("black_king_bar", 27), ("skadi", 33),
    ],
    "npc_dota_hero_drow_ranger": [
        ("power_treads", 8), ("dragon_lance", 12), ("black_king_bar", 24),
        ("butterfly", 28), ("satanic", 33),
    ],
    "npc_dota_hero_faceless_void": [
        ("power_treads", 8), ("falcon_blade", 10), ("maelstrom", 15),
        ("black_king_bar", 22), ("butterfly", 27), ("abyssal_blade", 33),
    ],
    "npc_dota_hero_slark": [
        ("power_treads", 8), ("diffusal_blade", 15),
        ("black_king_bar", 22), ("skadi", 28),
    ],
    "npc_dota_hero_sven": [
        ("power_treads", 8), ("helm_of_the_dominator", 12),
        ("black_king_bar", 21), ("greater_crit", 27), ("satanic", 33),
    ],
    "npc_dota_hero_tiny": [
        ("phase_boots", 7), ("blink", 14), ("black_king_bar", 22),
        ("shivas_guard", 28),
    ],
    "npc_dota_hero_ursa": [
        ("phase_boots", 7), ("falcon_blade", 9), ("blink", 13),
        ("black_king_bar", 23), ("satanic", 31),
    ],
    "npc_dota_hero_luna": [
        ("power_treads", 8), ("dragon_lance", 12), ("black_king_bar", 23),
        ("butterfly", 27),
    ],
    "npc_dota_hero_sniper": [
        ("power_treads", 8), ("dragon_lance", 11), ("maelstrom", 16),
        ("black_king_bar", 25), ("butterfly", 30),
    ],
    "npc_dota_hero_axe": [
        ("phase_boots", 7), ("vanguard", 11), ("blink", 14),
        ("blade_mail", 18), ("shivas_guard", 26),
    ],
    "npc_dota_hero_tidehunter": [
        ("arcane_boots", 7), ("vanguard", 12), ("blink", 16),
        ("shivas_guard", 25), ("heart", 33),
    ],
    "npc_dota_hero_legion_commander": [
        ("phase_boots", 7), ("blink", 14), ("black_king_bar", 22),
        ("blade_mail", 26),
    ],
    "npc_dota_hero_lion": [
        ("arcane_boots", 7), ("blink", 15), ("aether_lens", 20),
        ("ultimate_scepter", 26), ("sheepstick", 32),
    ],
    "npc_dota_hero_crystal_maiden": [
        ("arcane_boots", 7), ("glimmer_cape", 15), ("force_staff", 19),
        ("ultimate_scepter", 25), ("sheepstick", 31),
    ],
    "npc_dota_hero_shadow_shaman": [
        ("arcane_boots", 7), ("glimmer_cape", 14), ("aether_lens", 18),
        ("ultimate_scepter", 24), ("sheepstick", 30), ("refresher", 38),
    ],
    "npc_dota_hero_witch_doctor": [
        ("arcane_boots", 7), ("glimmer_cape", 14), ("aether_lens", 19),
        ("ultimate_scepter", 25), ("sheepstick", 31),
    ],
    "npc_dota_hero_nevermore": [
        ("power_treads", 7), ("maelstrom", 13), ("black_king_bar", 21),
        ("butterfly", 27),
    ],
    "npc_dota_hero_storm_spirit": [
        ("power_treads", 8), ("orchid", 16), ("black_king_bar", 23),
        ("sheepstick", 30),
    ],
    "npc_dota_hero_pudge": [
        ("phase_boots", 7), ("blink", 14), ("blade_mail", 19),
        ("shivas_guard", 27), ("heart", 34),
    ],
}

# ---------------------------------------------------------------------------
# Точки для вардов по фазам игры: (название, почему)
WARD_SPOTS = {
    "early": [
        ("река у топ-руны", "видишь ротации мид/топ и воду"),
        ("река у бот-руны", "контроль воды и ганков бот"),
        ("вход в наш лес", "раннее предупреждение о ганке"),
    ],
    "mid": [
        ("хайграунд топ (у руны)", "контроль верха и подхода к Рошану"),
        ("вход в их лес (мид)", "ловим фармящих мидера/керри"),
        ("река перед их Т2 (мид)", "виден любой переход мид"),
        ("наш лес глубоко (бот)", "защита фармящего керри"),
    ],
    "late": [
        ("пит Рошана", "контроль аегиса — решает игру"),
        ("подход к их Т3 (бот)", "видим защиту базы"),
        ("их лес у мид-Т3", "ловим отступающих"),
        ("наш хайграунд", "анти-ганк при дефе базы"),
    ],
}

# Гонки за фарм — ротация подсказок (как у них: «забери пачку на боте»)
FARM_HINTS = [
    "забери пачку на боте",
    "стяни стаки у топ-Т1",
    "почисти лес за вардами",
    "забери большой лагерь на линии",
    "подчисти двойные лагеря леса",
    "забери пачку на топе",
]

# GPM план по роли и рангу (эвристика; STRATZ даёт точные перцентили)
GPM_PLAN = {
    # ранг: (carry, mid, offlane, support)
    "herald":   (380, 400, 350, 280),
    "guardian": (430, 450, 400, 300),
    "crusader": (470, 500, 430, 320),
    "archon":   (500, 530, 460, 340),
    "legend":   (530, 560, 490, 360),
    "ancient":  (560, 590, 520, 380),
    "divine":   (590, 620, 545, 400),
    "immortal": (620, 650, 570, 420),
}
ROLE_INDEX = {"carry": 0, "mid": 1, "offlane": 2, "pos4": 3, "support": 3}

# Ластхиты к 10-й минуте (эвристика — заменяется бенчмарками OpenDota)
LH_PLAN_10 = {"carry": 60, "mid": 48, "offlane": 38, "support": 8, "pos4": 8}

# Куда идти по роли (позиции линии)
LANE_RU = {
    "carry": "лёгкая линия", "mid": "мид", "offlane": "сложная линия",
    "support": "лёгкая линия с керри", "pos4": "лёгкая линия с керри",
}

# Гайд «куда идти» по фазе и роли — базовые дота-принципы (не статистика)
LANE_GUIDE = {
    "early": {
        "carry": "фарм линию, не заходи в их лес без вижена",
        "mid": "держи ластхиты и контролируй руну, с 6-го уровня ганкай",
        "offlane": "дави башню и мешай их керри, отходи при ганке",
        "support": "варди вход в лес, стаки на :53, ротации на мид",
        "pos4": "варди и стяни лагеря, ганкай мид при шансe",
    },
    "mid": {
        "carry": "фарм лес между пачками, не фарми один без вижена",
        "mid": "фарм + ищи килы по карте с руной",
        "offlane": "фарм их лес при вижене, помогай дефить свои Т2",
        "support": "варди их лес на входах, стягивайся с керри",
        "pos4": "варди и иди с инициатором на смоках",
    },
    "late": {
        "carry": "не фарми один: враги с ·греем· ищут тебя, стой с командой",
        "mid": "собирайся в смок и ищи пик-офф перед Рошаном",
        "offlane": "придержи ТП для дефа, инициируй только с виженом",
        "support": "держи сентри на Рошане и варди перед каждым пушем",
        "pos4": "варди хайграунд, готовь глиммер/форс для дефа",
    },
}


# ---------------------------------------------------------------------------
def hero_ru(npc_name: str) -> str:
    if not npc_name:
        return "герой"
    return HERO_RU.get(npc_name, npc_name.replace("npc_dota_hero_", "").replace("_", " ").title())


def item_ru(item_key: str):
    """item_key без префикса item_ -> (ru, cost)"""
    k = item_key.replace("item_", "", 1)
    if k in ITEM_RU:
        return ITEM_RU[k]
    return (k.replace("_", " ").title(), 0)


def ward_spot(phase: str, idx: int):
    spots = WARD_SPOTS.get(phase) or WARD_SPOTS["mid"]
    return spots[idx % len(spots)]


def zone_name(x, y) -> str:
    """Примерная зона по мировым координатам (Radiant — низ/лево, Dire — верх/право)."""
    try:
        v = float(y)
        h = float(x)
    except (TypeError, ValueError):
        return "карта"
    if v > 2500:
        vert = "топ"
    elif v < -2500:
        vert = "бот"
    else:
        vert = "мид"
    if h > 3000:
        return f"{vert}, их сторона"
    if h < -3000:
        return f"{vert}, наша сторона"
    return vert
