"""The Starwilds: a colorful math-powered wizard adventure for Kate and Lola."""

from __future__ import annotations

import base64
import random
import streamlit as st


st.set_page_config(
    page_title="The Starwilds Wizard Quest",
    page_icon="🏰",
    layout="wide",
    initial_sidebar_state="collapsed",
)


MATH_LEVELS = {
    1: {"label": "Tiny sums", "max": 5, "kind": "add", "summary": "Addition with numbers 0–5"},
    2: {"label": "Little leaps", "max": 10, "kind": "add", "summary": "Addition with numbers 0–10"},
    3: {"label": "Meadow sums", "max": 15, "kind": "add", "summary": "Addition with numbers 0–15"},
    4: {"label": "Big bridges", "max": 20, "kind": "add", "summary": "Addition with numbers 0–20"},
    5: {"label": "First takeaways", "max": 20, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–20"},
    6: {"label": "Silver sums", "max": 25, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–25"},
    7: {"label": "Forest numbers", "max": 30, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–30"},
    8: {"label": "Crystal challenge", "max": 40, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–40"},
    9: {"label": "Wizard's workshop", "max": 50, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–50"},
    10: {"label": "Maldred's challenge", "max": 50, "kind": "subtract", "summary": "Subtraction with numbers 0–50"},
}


CASTLES = [
    {"place": "Sunpetal Meadow", "boss": "Pebblehex", "subtitle": "The Lantern Seed", "emoji": "🌻", "color": "#f5bd48", "hp": 50, "scene": "Golden flowers sway while Pebblehex guards the little lantern seed."},
    {"place": "Whispering Woods", "boss": "Bramblewyn", "subtitle": "The Stolen Echo", "emoji": "🌲", "color": "#47a772", "hp": 100, "scene": "Fireflies guide the way through Bramblewyn's twisty forest spell."},
    {"place": "Moonstone Caves", "boss": "Gloam", "subtitle": "The Shattered Moonstone", "emoji": "💎", "color": "#9a78dc", "hp": 150, "scene": "Glowing crystals light Gloam's purple cave and underground lake."},
    {"place": "Stormglass Skybridge", "boss": "Vexa Stormwhirl", "subtitle": "The Wandering Wind", "emoji": "🌩️", "color": "#55a5df", "hp": 200, "scene": "Cloud castles float above Vexa's rainbow bridge and playful storms."},
    {"place": "Obsidian Tower", "boss": "Maldred", "subtitle": "The Last Spell", "emoji": "🏰", "color": "#bf668d", "hp": 250, "scene": "Maldred waits in the tallest tower beneath a sky full of brave stars."},
]


SPELLS = {
    "spark": {"name": "Spark Bolt", "emoji": "✨", "questions": 5, "damage": 25, "color": "#ffc83d", "description": "A speedy golden bolt of bright wizard light."},
    "moonbeam": {"name": "Moonbeam Arc", "emoji": "🌙", "questions": 10, "damage": 50, "color": "#67b6ee", "description": "A ribbon of moonlight that sweeps across the arena."},
    "dragonflame": {"name": "Dragonflame", "emoji": "🔥", "questions": 15, "damage": 75, "color": "#ff805e", "description": "A friendly dragon's warm, roaring burst of magic."},
    "starstorm": {"name": "Starstorm", "emoji": "🌠", "questions": 20, "damage": 100, "color": "#ad7ff2", "description": "A giant shower of sparkling stars for the toughest foes."},
}


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@500;600;700;800;900&display=swap');
:root { --ink:#302853; --purple:#6754b6; --soft:#f4f6ff; }
.stApp { background:radial-gradient(ellipse at 90% 0%,#fff0c5 0,transparent 28%),linear-gradient(180deg,#fffaf0 0%,#f5f5ff 48%,#effaff 100%); color:var(--ink); font-family:'Nunito','Trebuchet MS',sans-serif; }
.block-container { max-width:1240px; padding-top:1.15rem; padding-bottom:3rem; }
h1,h2,h3,p,label,[data-testid="stMarkdownContainer"] { font-family:'Nunito','Trebuchet MS',sans-serif; }
h1,h2,h3 { color:var(--ink); letter-spacing:-.025em; }
div.stButton > button { min-height:3rem; border-radius:16px; border:2px solid #dedbf0; color:#38315e; background:#fff; font-weight:900; box-shadow:0 4px 0 rgba(53,46,99,.09); transition:transform .14s ease,box-shadow .14s ease; }
div.stButton > button:hover { transform:translateY(-2px); border-color:#a18be6; color:#2e255e; box-shadow:0 6px 0 rgba(53,46,99,.12); }
div.stButton > button:disabled { color:#aaa8b7; background:#e7e6eb; border-color:#e0dfe6; box-shadow:none; }
[data-testid="stProgressBar"] > div > div { background:linear-gradient(90deg,#67d38b,#f7cb56); }
.hero { padding:2rem; border-radius:30px; color:white; background:linear-gradient(125deg,#39316e,#7055bd 58%,#a18ae6); box-shadow:0 13px 28px rgba(66,51,133,.17); margin:.25rem 0 1.15rem; }
.hero h1 { color:white!important; margin:.2rem 0 .45rem; font-size:2.35rem; }
.hero p { color:#f2edff; margin:.15rem 0; font-size:1.08rem; }
.eyebrow { text-transform:uppercase; letter-spacing:.13em; font-size:.75rem; font-weight:900; opacity:.82; }
.pill { display:inline-block; padding:.42rem .78rem; border-radius:999px; border:1px solid #e5e0f0; background:white; margin:.15rem .25rem .3rem 0; font-weight:900; color:#514a77; }
.home-card { min-height:160px; border-radius:24px; padding:1.1rem; border:1px solid #e5def3; background:linear-gradient(145deg,#fff,#f5f0ff); box-shadow:0 8px 20px rgba(48,44,94,.07); }
.island-intro { color:#514d70; font-weight:800; margin:.35rem 0 .65rem; }
/* The map artwork is static SVG; actual Streamlit buttons are transparent, positioned hit areas over each castle. */
.st-key-island_map { position:relative; height:580px; min-height:430px; overflow:hidden; border:7px solid white; border-radius:32px; box-shadow:0 16px 32px rgba(35,93,143,.2); background:#69cce5; margin:.45rem 0 1rem; }
.st-key-island_map .map-art { position:absolute; inset:0; width:100%; height:100%; z-index:0; }
.st-key-island_map .map-art img { width:100%; height:100%; display:block; object-fit:fill; }
.st-key-island_map [class*="st-key-castle_hit_"] { position:absolute!important; z-index:3; width:10%; height:17%; min-width:54px; }
.st-key-island_map .st-key-castle_hit_0 { left:6.5%; top:54%; }
.st-key-island_map .st-key-castle_hit_1 { left:25.5%; top:28%; }
.st-key-island_map .st-key-castle_hit_2 { left:44.5%; top:51%; }
.st-key-island_map .st-key-castle_hit_3 { left:63.5%; top:27%; }
.st-key-island_map .st-key-castle_hit_4 { left:82.5%; top:47%; }
.st-key-island_map [class*="st-key-castle_hit_"] button { width:100%; height:100%; min-height:0; color:transparent!important; background:transparent!important; border:2px solid transparent!important; box-shadow:none!important; padding:0!important; font-size:0!important; }
.st-key-island_map [class*="st-key-castle_hit_"] button:hover { background:rgba(255,240,120,.18)!important; border:3px solid rgba(255,255,255,.85)!important; box-shadow:0 0 24px 10px rgba(255,239,116,.55)!important; }
.st-key-island_map [class*="st-key-castle_hit_"] button:disabled { opacity:0!important; }
@media(max-width:720px) { .st-key-island_map { height:430px; } .hero { padding:1.35rem; } .hero h1 { font-size:1.75rem; } }
.battle-shell { border-radius:30px; border:2px solid white; background:linear-gradient(145deg,#fff,#f8f5ff); box-shadow:0 12px 28px rgba(49,42,95,.1); padding:1rem; }
.battle-title { color:#51497a; font-size:1.05rem; font-weight:900; }
.battle-arena { --sky1:#b9eeff; --sky2:#72d6e9; --ground:#89d27f; position:relative; overflow:hidden; min-height:420px; border-radius:28px; border:5px solid white; box-shadow:inset 0 0 0 2px rgba(255,255,255,.45),0 12px 26px rgba(43,43,93,.15); background:linear-gradient(180deg,var(--sky1),var(--sky2) 64%,var(--ground) 64%,#5fb978); padding:1rem; }
.battle-arena:before { content:'☁️'; position:absolute; top:12%; left:7%; font-size:2.7rem; opacity:.75; }
.battle-arena:after { content:'✦　✧　✦'; position:absolute; top:13%; right:7%; color:#fff5a9; font-size:1.3rem; letter-spacing:.7rem; }
.battle-arena.woods { --sky1:#b7e6be; --sky2:#62b98b; --ground:#54985e; }
.battle-arena.caves { --sky1:#7465bc; --sky2:#514786; --ground:#38335e; }
.battle-arena.sky { --sky1:#b7e9ff; --sky2:#82c9f2; --ground:#d5f4ff; }
.battle-arena.tower { --sky1:#393759; --sky2:#61528f; --ground:#393554; }
.duel { position:absolute; left:5%; right:5%; bottom:7%; height:74%; display:flex; align-items:flex-end; justify-content:space-between; z-index:2; }
.character { width:36%; height:100%; position:relative; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; }
.character.hero { animation:hero-bob 2.3s ease-in-out infinite; }
.character.boss { animation:boss-bob 2.8s ease-in-out infinite; }
.character.boss.hurt { animation:enemy-flinch .58s ease-in-out 1,boss-bob 2.8s ease-in-out infinite; filter:saturate(.68); }
.sprite { width:min(100%,205px); height:78%; overflow:visible; filter:drop-shadow(0 9px 7px rgba(32,31,67,.2)); }
.char-name { background:rgba(255,255,255,.88); padding:.18rem .55rem; border-radius:999px; font-size:.86rem; color:#322c56; font-weight:900; margin-top:.1rem; }
.head-health { position:absolute; top:0; width:90%; text-align:center; z-index:5; }
.head-health b { display:block; color:white; text-shadow:0 2px 4px #392f63; font-size:.8rem; }
.health-track { height:12px; border:2px solid white; border-radius:99px; background:#5b3449; overflow:hidden; box-shadow:0 2px 5px rgba(37,31,75,.25); }
.health-fill { display:block; height:100%; border-radius:99px; background:linear-gradient(90deg,#68dd75,#a9ef6b); transition:width .35s ease; }
.boss .health-fill { background:linear-gradient(90deg,#ff727a,#f7be54); }
.spell-impact { position:absolute; left:50%; top:34%; transform:translate(-50%,-50%); z-index:4; font-size:4rem; filter:drop-shadow(0 0 16px #fff5a7); animation:impact .85s ease-out 1; }
.boss-hurt { position:absolute; top:18%; right:6%; z-index:5; color:#fff4e8; font-size:1.5rem; font-weight:1000; text-shadow:0 3px 4px #5c315b; animation:damage-pop .85s ease-out 1; }
.arena-caption { position:absolute; z-index:1; left:0; right:0; top:5%; color:white; text-align:center; font-weight:900; text-shadow:0 2px 5px #474075; }
@keyframes hero-bob { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-8px); } }
@keyframes boss-bob { 0%,100% { transform:translateY(0) rotate(0); } 50% { transform:translateY(-5px) rotate(1deg); } }
@keyframes enemy-flinch { 0%,100% { transform:translateX(0) rotate(0); } 25% { transform:translateX(-11px) rotate(-7deg); } 60% { transform:translateX(9px) rotate(6deg); } }
@keyframes impact { from { opacity:.2; transform:translate(-50%,-50%) scale(.35) rotate(-30deg); } to { opacity:1; transform:translate(-50%,-50%) scale(1.2) rotate(18deg); } }
@keyframes damage-pop { from { opacity:0; transform:translateY(18px) scale(.7); } to { opacity:1; transform:translateY(-10px) scale(1.1); } }
.spell-pick { min-height:94px; border-radius:19px; padding:.75rem; border:1px solid #e6dff2; background:linear-gradient(140deg,#fff,#f5f1ff); margin:.25rem 0 .25rem; }
.spell-pick .spell-title { font-size:1rem; font-weight:1000; color:#352e64; }
.spell-pick .spell-detail { font-size:.84rem; color:#6a6480; line-height:1.3; }
.spell-chip { display:inline-block; padding:.22rem .55rem; border-radius:999px; background:#fff2c7; color:#65501c; font-weight:900; font-size:.8rem; margin-top:.3rem; }
@keyframes spell-ready { 50% { box-shadow:0 0 0 6px rgba(255,210,73,.12),0 5px 0 rgba(82,61,23,.1)!important; } }
.challenge-card { border-radius:26px; padding:1.3rem; background:linear-gradient(135deg,#fff,#f2edff); border:2px solid white; box-shadow:0 12px 28px rgba(51,42,99,.11); text-align:center; margin:.6rem 0 1rem; }
.challenge-math { font-size:3rem; font-weight:1000; color:#30285f; padding:.6rem; }
.challenge-finish { border-radius:25px; background:linear-gradient(130deg,#fff0b9,#fff,#e4fbe9); padding:1.2rem; text-align:center; font-weight:900; }
.notice { padding:.8rem 1rem; border-radius:18px; background:#fff3c8; border:1px solid #efd77b; color:#56451d; font-weight:900; margin:.5rem 0; }
@media(max-width:700px) { .battle-arena { min-height:330px; } .duel { left:2%; right:2%; } .character { width:42%; } .sprite { width:100%; } .challenge-math { font-size:2.2rem; } }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "screen": "home", "player": "Kate", "math_level": 1,
        "unlocked_castle": 0, "completed_castles": [], "active_castle": 0,
        "enemy_hp": 0, "spell_inventory": [], "challenge_spell": None,
        "challenge_questions": [], "challenge_index": 0, "challenge_attempt": 0,
        "challenge_feedback": "", "challenge_notice": "", "map_notice": "",
        "new_spell_highlight": None, "last_spell": None, "last_damage": 0,
        "adventure_over": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, list) else value


init_state()
S = st.session_state


def make_choices(answer: int, max_answer: int) -> list[int]:
    choices = {answer}
    distance = 1
    while len(choices) < 3:
        for item in (answer - distance, answer + distance):
            if 0 <= item <= max_answer:
                choices.add(item)
            if len(choices) == 3:
                break
        distance += 1
    result = list(choices)
    random.shuffle(result)
    return result


def make_problem(level: int) -> dict:
    cfg = MATH_LEVELS[level]
    maximum = cfg["max"]
    subtract = cfg["kind"] == "subtract" or (cfg["kind"] == "mixed" and random.random() < .45)
    if subtract:
        first = random.randint(0, maximum)
        second = random.randint(0, first)
        answer, op = first - second, "−"
    else:
        first = random.randint(0, maximum)
        second = random.randint(0, maximum - first)
        answer, op = first + second, "+"
    expression = f"{first} {op} {second}"
    hint = f"Start at {first} and count {'back' if subtract else 'forward'} {second} {('step' if second == 1 else 'steps')}"
    explanation = f"{expression} = {answer}. {hint} to reach {answer}."
    return {"expression": expression, "answer": answer, "choices": make_choices(answer, maximum), "hint": hint + ".", "explanation": explanation}


def start_adventure(player: str, level: int) -> None:
    S.update({
        "screen": "map", "player": player, "math_level": level,
        "unlocked_castle": 0, "completed_castles": [], "active_castle": 0,
        "enemy_hp": 0, "spell_inventory": [], "challenge_spell": None,
        "challenge_questions": [], "challenge_index": 0, "challenge_attempt": 0,
        "challenge_feedback": "", "challenge_notice": "", "map_notice": "",
        "new_spell_highlight": None, "last_spell": None, "last_damage": 0,
        "adventure_over": False,
    })


def enter_castle(index: int) -> None:
    S["active_castle"] = index
    S["enemy_hp"] = CASTLES[index]["hp"]
    S["last_spell"] = None
    S["last_damage"] = 0
    S["new_spell_highlight"] = None
    S["challenge_notice"] = ""
    S["screen"] = "battle"


def begin_spell_challenge(spell_id: str) -> None:
    spell = SPELLS[spell_id]
    S["challenge_spell"] = spell_id
    S["challenge_questions"] = [make_problem(S["math_level"]) for _ in range(spell["questions"])]
    S["challenge_index"] = 0
    S["challenge_attempt"] = 0
    S["challenge_feedback"] = ""
    S["last_spell"] = None
    S["last_damage"] = 0
    S["screen"] = "spell_challenge"


def answer_challenge(answer: int) -> None:
    problem = S["challenge_questions"][S["challenge_index"]]
    if answer == problem["answer"]:
        S["challenge_index"] += 1
        S["challenge_attempt"] = 0
        S["challenge_feedback"] = "Yes! One more answer powers your spell!"
        if S["challenge_index"] >= len(S["challenge_questions"]):
            spell_id = S["challenge_spell"]
            S["spell_inventory"].append(spell_id)
            S["new_spell_highlight"] = spell_id
            S["challenge_notice"] = f"{SPELLS[spell_id]['emoji']} {SPELLS[spell_id]['name']} is ready! Click its glowing card to cast it."
            S["screen"] = "battle"
    else:
        S["challenge_attempt"] += 1
        S["challenge_feedback"] = "Not that one yet. Try again, or tap for a counting hint!"


def cast_spell(inventory_index: int) -> None:
    if inventory_index >= len(S["spell_inventory"]):
        return
    spell_id = S["spell_inventory"].pop(inventory_index)
    spell = SPELLS[spell_id]
    S["new_spell_highlight"] = None
    S["last_spell"] = spell_id
    S["last_damage"] = min(spell["damage"], S["enemy_hp"])
    S["enemy_hp"] = max(0, S["enemy_hp"] - spell["damage"])
    if S["enemy_hp"] == 0:
        index = S["active_castle"]
        if index not in S["completed_castles"]:
            S["completed_castles"].append(index)
        if index < len(CASTLES) - 1:
            S["unlocked_castle"] = index + 1
            S["map_notice"] = f"🏆 {CASTLES[index]['boss']} is defeated! Castle {index + 2} is open on the island map!"
        else:
            S["adventure_over"] = True
            S["map_notice"] = "🌟 Maldred is defeated! The Starwilds are sparkling again!"
        S["screen"] = "map"
    else:
        S["screen"] = "battle"


def hero_svg(color: str = "#8a71d5") -> str:
    return f"""<svg class='sprite' viewBox='0 0 180 220' aria-hidden='true'>
    <ellipse cx='91' cy='207' rx='56' ry='10' fill='rgba(35,35,69,.2)'/>
    <path d='M48 202 Q53 139 68 122 L111 122 Q131 147 139 202 Q97 217 48 202Z' fill='{color}' stroke='#41376f' stroke-width='5'/>
    <path d='M69 127 L90 160 L112 126' fill='#fff2cf' stroke='#41376f' stroke-width='4'/>
    <circle cx='91' cy='89' r='37' fill='#f4c99f' stroke='#4f3c62' stroke-width='4'/>
    <path d='M55 85 Q55 35 95 32 Q134 37 128 85 Q107 62 80 66 Q68 67 55 85Z' fill='#523d71'/>
    <path d='M38 62 L94 4 L140 64 Q91 48 38 62Z' fill='{color}' stroke='#41376f' stroke-width='5'/>
    <path d='M32 66 Q89 49 148 68 Q116 84 34 76Z' fill='#44376d' stroke='#41376f' stroke-width='4'/>
    <circle cx='77' cy='91' r='4' fill='#302853'/><circle cx='105' cy='91' r='4' fill='#302853'/>
    <path d='M81 107 Q92 116 103 106' fill='none' stroke='#a34e56' stroke-width='4' stroke-linecap='round'/>
    <path d='M52 139 Q31 148 25 171' fill='none' stroke='#f4c99f' stroke-width='12' stroke-linecap='round'/>
    <path d='M130 142 Q145 153 151 168' fill='none' stroke='#f4c99f' stroke-width='12' stroke-linecap='round'/>
    <path d='M23 173 L25 133' stroke='#745a37' stroke-width='6' stroke-linecap='round'/><path d='M13 135 L25 115 L37 135Z' fill='#ffe66c'/>
    <circle cx='25' cy='111' r='12' fill='#fff9c7' opacity='.85'/></svg>"""


def boss_svg(index: int, hurt: bool = False) -> str:
    colors = ["#58704e", "#596b4b", "#68508f", "#526b96", "#493b70"]
    trim = ["#d78857", "#72ae62", "#76dcf0", "#68b9ec", "#c95c87"]
    color, accent = colors[index], trim[index]
    mouth = "M75 111 Q91 101 106 111" if hurt else "M76 106 Q91 112 106 106"
    return f"""<svg class='sprite' viewBox='0 0 180 220' aria-hidden='true'>
    <ellipse cx='91' cy='207' rx='58' ry='10' fill='rgba(35,35,69,.24)'/>
    <path d='M42 203 Q50 136 65 123 L117 123 Q134 151 141 203 Q95 216 42 203Z' fill='{color}' stroke='#302843' stroke-width='5'/>
    <path d='M60 142 L89 164 L119 141' fill='none' stroke='{accent}' stroke-width='8'/>
    <circle cx='91' cy='89' r='39' fill='#9cb278' stroke='#352e43' stroke-width='5'/>
    <path d='M52 78 Q54 29 92 27 Q129 32 132 77 L113 68 L100 78 L84 66 L68 80Z' fill='{color}' stroke='#302843' stroke-width='5'/>
    <path d='M48 68 Q88 47 135 69 L126 82 Q90 69 54 83Z' fill='{accent}' stroke='#302843' stroke-width='4'/>
    <path d='M74 89 L83 91 M101 91 L110 89' stroke='#2e2545' stroke-width='5' stroke-linecap='round'/>
    <path d='{mouth}' fill='none' stroke='#5c303a' stroke-width='4' stroke-linecap='round'/>
    <path d='M54 139 Q37 151 31 174 M126 140 Q145 149 151 173' fill='none' stroke='#9cb278' stroke-width='13' stroke-linecap='round'/>
    <path d='M28 175 L22 153 L42 158Z M153 174 L142 158 L164 154Z' fill='{accent}' stroke='#302843' stroke-width='3'/>
    <path d='M59 48 L69 31 L77 51 M105 49 L113 28 L123 49' fill='none' stroke='#f5df9d' stroke-width='5' stroke-linecap='round'/>
    {"<path d='M57 85 L65 102 M126 83 L118 100' stroke='#ffe3c2' stroke-width='5' opacity='.9'/>" if hurt else ""}</svg>"""


def castle_svg(x: int, y: int, num: int, color: str, status: str, title: str) -> str:
    shade = color if status != "locked" else "#83919a"
    flag = "#ffd753" if status == "open" else ("#79d28b" if status == "done" else "#d2d7df")
    return f"""<g class='castle {status}' transform='translate({x} {y})'>
      <ellipse cx='0' cy='47' rx='67' ry='15' fill='rgba(40,104,73,.18)'/>
      <path d='M-50 35 V-16 H-32 V-43 H-14 V-16 H14 V-43 H32 V-16 H50 V35Z' fill='{shade}' stroke='#4f4772' stroke-width='5' stroke-linejoin='round'/>
      <path d='M-32 -43 L-23 -65 L-14 -43 M14 -43 L23 -65 L32 -43' fill='{shade}' stroke='#4f4772' stroke-width='5'/>
      <path d='M-50 -16 L-42 -32 L-34 -16 M34 -16 L42 -32 L50 -16' fill='{shade}' stroke='#4f4772' stroke-width='5'/>
      <path d='M-9 35 V8 Q0 -5 9 8 V35Z' fill='#fff4cc' stroke='#514879' stroke-width='4'/>
      <rect x='-34' y='-4' width='12' height='13' rx='3' fill='#fff4cc'/><rect x='22' y='-4' width='12' height='13' rx='3' fill='#fff4cc'/>
      <path d='M30 -56 V-87' stroke='#584778' stroke-width='4'/><path d='M31 -86 L57 -79 L31 -70Z' fill='{flag}'/>
      <circle cx='0' cy='-104' r='19' fill='white' stroke='#514879' stroke-width='4'/><text x='0' y='-97' text-anchor='middle' font-size='22' font-weight='1000' fill='#3e356a'>{num}</text>
      <text x='0' y='75' text-anchor='middle' font-size='19' font-weight='1000' fill='#304366'>{title}</text>
      {"<path d='M-61 -28 L-49 -19 M50 -48 L62 -38' stroke='#fff5b8' stroke-width='5' stroke-linecap='round'/>" if status == "open" else ""}
    </g>"""


def island_map() -> str:
    coords = [(120, 365), (310, 225), (500, 377), (690, 218), (880, 335)]
    castles = []
    for index, ((x, y), castle) in enumerate(zip(coords, CASTLES)):
        if index in S["completed_castles"]:
            status = "done"
        elif index == S["unlocked_castle"]:
            status = "open"
        else:
            status = "locked"
        castles.append(castle_svg(x, y, index + 1, castle["color"], status, castle["place"]))
    svg = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1000 600' preserveAspectRatio='xMidYMid slice'>
    <defs><linearGradient id='ocean' x1='0' y1='0' x2='0' y2='1'><stop stop-color='#7ce0ef'/><stop offset='1' stop-color='#39a9d8'/></linearGradient><linearGradient id='island' x1='0' y1='0' x2='0' y2='1'><stop stop-color='#d7f4a0'/><stop offset='1' stop-color='#75cb82'/></linearGradient></defs>
    <rect width='1000' height='600' fill='url(#ocean)'/>
    <g fill='none' stroke='#c5f6ff' stroke-width='8' stroke-linecap='round' opacity='.75'><path d='M25 113 Q68 91 112 113 T198 113'/><path d='M736 99 Q779 77 822 99 T908 99'/><path d='M793 521 Q836 499 879 521 T965 521'/><path d='M-10 472 Q30 450 70 472 T150 472'/></g>
    <path d='M0 323 Q75 245 142 271 Q220 308 278 221 Q343 145 411 208 Q462 265 526 232 Q603 187 661 236 Q736 295 790 231 Q869 151 931 223 Q977 270 1000 260 L1000 600 L0 600Z' fill='#e6cc7e'/>
    <path d='M0 308 Q75 230 142 256 Q220 293 278 206 Q343 130 411 193 Q462 250 526 217 Q603 172 661 221 Q736 280 790 216 Q869 136 931 208 Q977 255 1000 245 L1000 600 L0 600Z' fill='url(#island)' stroke='#60b877' stroke-width='8'/>
    <path d='M453 253 C403 289 437 324 388 357 S390 425 445 432 S496 495 445 536' fill='none' stroke='#67cde4' stroke-width='18' stroke-linecap='round'/>
    <path d='M447 254 C401 290 434 323 385 356 S390 422 443 432' fill='none' stroke='#c6f6ff' stroke-width='5' stroke-linecap='round'/>
    <g fill='#a7c4df' stroke='white' stroke-width='7'><path d='M90 291 L146 188 L204 291Z'/><path d='M144 291 L198 216 L246 291Z'/><path d='M762 240 L821 130 L884 240Z'/><path d='M822 240 L873 172 L923 240Z'/></g>
    <g fill='#fff'><path d='M125 229 L146 188 L169 229 L148 222Z'/><path d='M800 170 L821 130 L845 173 L820 164Z'/></g>
    <g fill='#318c60'><path d='M218 458 l32 -80 32 80Z M250 474 l26 -68 26 68Z M188 481 l22 -57 23 57Z M727 415 l29 -72 30 72Z M757 434 l25 -63 26 63Z M696 440 l20 -51 20 51Z'/><rect x='244' y='449' width='14' height='29' fill='#8c6249'/><rect x='753' y='407' width='12' height='26' fill='#8c6249'/></g>
    <g fill='#fff4ad'><circle cx='67' cy='210' r='8'/><circle cx='560' cy='133' r='7'/><circle cx='951' cy='120' r='8'/><circle cx='567' cy='500' r='6'/></g>
    <g fill='#fff' opacity='.9'><path d='M340 82 q20 -24 40 0 q30 -16 40 12 h-85Z'/><path d='M676 82 q19 -23 38 0 q28 -16 40 12 h-82Z'/></g>
    <text x='36' y='51' font-size='30' font-weight='1000' fill='white' letter-spacing='3'>THE STARWILDS</text>
    <text x='764' y='565' font-size='20' font-weight='900' fill='white'>🌊 Sparkle Sea</text>
    """ + "".join(castles) + "</svg>"
    encoded_svg = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"<div class='map-art'><img alt='A bright island with five numbered castles, mountains, forests, rivers and ocean' src='data:image/svg+xml;base64,{encoded_svg}'></div>"


def render_hero(title: str, subtitle: str, eyebrow: str = "The Starwilds") -> None:
    st.markdown(f"<div class='hero'><div class='eyebrow'>{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>", unsafe_allow_html=True)


def render_home() -> None:
    render_hero("The Starwilds Wizard Quest", "Choose your wizard and math level. Then help save a magical island from Maldred!")
    left, right = st.columns([.9, 1.1], gap="large")
    with left:
        st.markdown("### Who is playing?")
        player = st.radio("Choose your wizard", ["Kate", "Lola"], horizontal=True, key="home_player")
        wizard_color = "#f0a7c5" if player == "Kate" else "#74cfe0"
        st.markdown(f"<div class='home-card' style='border-top:6px solid {wizard_color}'><div style='font-size:3.5rem'>🧙🏻‍♀️</div><b style='font-size:1.2rem'>Wizard {player}</b><p>A brave spell-caster, ready to protect the Starwilds!</p></div>", unsafe_allow_html=True)
    with right:
        st.markdown("### Pick a starting math level")
        level = st.select_slider("Math level", options=list(MATH_LEVELS), value=1, format_func=lambda n: str(n), key="home_level")
        cfg = MATH_LEVELS[int(level)]
        st.markdown(f"<div class='home-card' style='border-top:6px solid #f0bd48'><div style='font-size:2.5rem'>📚 ✨</div><b style='font-size:1.2rem'>Level {level}: {cfg['label']}</b><p>{cfg['summary']}</p></div>", unsafe_allow_html=True)
        st.caption("You can change the practice level from the island map at any time.")
    st.markdown("### How to save the island")
    st.info("Click a castle to meet its bad wizard. Pick one of four spells, solve its math challenge, then click your glowing spell card to cast it. Stronger castles have more health!")
    if st.button("🏝️ Enter the Starwilds", type="primary", use_container_width=True, key="start_game"):
        start_adventure(player, int(level))
        st.rerun()


def render_map() -> None:
    render_hero(f"Welcome, Wizard {S['player']}!", "Choose the glowing castle to explore. Defeat each wizard to open the next castle.", "Your magical island map")
    status_left, status_right = st.columns(2)
    with status_left:
        st.markdown(f"<span class='pill'>📚 Math level {S['math_level']} of 10</span><span class='pill'>🏰 {len(S['completed_castles'])} of 5 castles cleared</span>", unsafe_allow_html=True)
    with status_right:
        updated_level = st.select_slider("Practice level", options=list(MATH_LEVELS), value=S["math_level"], key="map_level", format_func=lambda n: str(n))
        S["math_level"] = int(updated_level)
        st.caption(MATH_LEVELS[int(updated_level)]["summary"])
    st.markdown("### Click a castle to play")
    st.markdown("<div class='island-intro'>Follow the golden trail across the ocean, mountains, forests, and bridges. A glowing castle is ready!</div>", unsafe_allow_html=True)
    with st.container(key="island_map"):
        st.markdown(island_map(), unsafe_allow_html=True)
        for index, castle in enumerate(CASTLES):
            available = index == S["unlocked_castle"] and index not in S["completed_castles"]
            if st.button(f"Castle {index + 1}: {castle['place']}", key=f"castle_hit_{index}", disabled=not available, help=f"Castle {index + 1}: {castle['place']} — {castle['boss']}"):
                enter_castle(index)
                st.rerun()
    if S.get("map_notice"):
        st.markdown(f"<div class='notice'>{S['map_notice']}</div>", unsafe_allow_html=True)
    if S["adventure_over"]:
        st.markdown("<div class='challenge-finish'><div style='font-size:3rem'>🌟 🧙‍♀️ 🏰 🌟</div><h2>Maldred is defeated!</h2><p>The Starwilds sparkle again thanks to your math magic.</p></div>", unsafe_allow_html=True)
        if st.button("🔁 Start a new adventure", key="new_adventure", use_container_width=True):
            S["screen"] = "home"
            st.rerun()


def render_battle_scene() -> None:
    index = S["active_castle"]
    castle = CASTLES[index]
    enemy_ratio = max(0, S["enemy_hp"]) / castle["hp"]
    hero_color = "#eaa5c5" if S["player"] == "Kate" else "#54bfd5"
    arena_class = ["meadow", "woods", "caves", "sky", "tower"][index]
    hurt = S["enemy_hp"] < castle["hp"]
    effect = SPELLS.get(S.get("last_spell") or "")
    effect_html = f"<div class='spell-impact'>{effect['emoji']}</div><div class='boss-hurt'>−{S.get('last_damage', 0)}!</div>" if effect and hurt else ""
    st.markdown(
        f"""<div class='battle-arena {arena_class}'>
        <div class='arena-caption'>{castle['emoji']} {castle['place']} · {castle['subtitle']}</div>
        <div class='duel'>
          <div class='character hero'><div class='head-health'><b>{S['player']}</b><div class='health-track'><span class='health-fill' style='width:100%'></span></div></div>{hero_svg(hero_color)}<div class='char-name'>Wizard {S['player']}</div></div>
          {effect_html}
          <div class='character boss {'hurt' if hurt else ''}'><div class='head-health'><b>{castle['boss']}</b><div class='health-track'><span class='health-fill' style='width:{enemy_ratio * 100:.1f}%'></span></div></div>{boss_svg(index, hurt)}<div class='char-name'>{castle['boss']}</div></div>
        </div></div>""",
        unsafe_allow_html=True,
    )
    st.caption(castle["scene"])


def render_spell_choices() -> None:
    st.markdown("### 🪄 Choose a spell to earn")
    st.caption("Each correct answer fills the spell's power. Wrong answers don't count—take your time!")
    for spell_id, spell in SPELLS.items():
        st.markdown(
            f"<div class='spell-pick' style='border-left:6px solid {spell['color']}'><div class='spell-title'>{spell['emoji']} {spell['name']}</div><div class='spell-detail'>{spell['description']}</div><span class='spell-chip'>{spell['questions']} correct answers · {spell['damage']} damage</span></div>",
            unsafe_allow_html=True,
        )
        if st.button(f"Get {spell['name']}", key=f"get_spell_{spell_id}", use_container_width=True):
            begin_spell_challenge(spell_id)
            st.rerun()


def render_battle() -> None:
    castle = CASTLES[S["active_castle"]]
    render_hero(f"Castle {S['active_castle'] + 1}: {castle['boss']}!", "Choose a spell challenge, earn your magic, and cast at the right moment.", "Wizard battle")
    left, right = st.columns([.9, 1.2], gap="large")
    with left:
        st.markdown("### ✨ Your spellbook")
        if S.get("challenge_notice"):
            st.markdown(f"<div class='notice'>{S['challenge_notice']}</div>", unsafe_allow_html=True)
        if S["spell_inventory"]:
            st.markdown("#### Ready to cast")
            for inventory_index, spell_id in enumerate(list(S["spell_inventory"])):
                spell = SPELLS[spell_id]
                is_new = spell_id == S.get("new_spell_highlight")
                st.markdown(
                    f"<div class='spell-pick' style='border:2px solid {spell['color']};background:{'#fff8d8' if is_new else '#fff'}'><div class='spell-title'>{'🌟 NEW! ' if is_new else ''}{spell['emoji']} {spell['name']}</div><div class='spell-detail'>{spell['damage']} damage to {castle['boss']}</div></div>",
                    unsafe_allow_html=True,
                )
                if is_new:
                    st.markdown(f"<style>.st-key-owned_spell_{inventory_index} button{{border-color:#f3c853!important;background:linear-gradient(135deg,#fff9d9,#fff)!important;box-shadow:0 0 0 3px rgba(255,210,73,.22),0 5px 0 rgba(82,61,23,.1)!important;animation:spell-ready 1.7s ease-in-out infinite}}</style>", unsafe_allow_html=True)
                if st.button(f"⚡ Cast {spell['name']} · {spell['damage']} damage", key=f"owned_spell_{inventory_index}", use_container_width=True):
                    cast_spell(inventory_index)
                    st.rerun()
        else:
            st.markdown("<div class='notice'>Your spellbook is empty. Earn your first spell below!</div>", unsafe_allow_html=True)
        st.divider()
        render_spell_choices()
    with right:
        render_battle_scene()
        st.markdown(f"<span class='pill'>💜 {S['enemy_hp']} / {castle['hp']} shadow hearts left</span><span class='pill'>🧙‍♀️ {len(S['spell_inventory'])} spell{'s' if len(S['spell_inventory']) != 1 else ''} ready</span>", unsafe_allow_html=True)


def render_spell_challenge() -> None:
    spell_id = S["challenge_spell"]
    spell = SPELLS[spell_id]
    total = spell["questions"]
    index = S["challenge_index"]
    problem = S["challenge_questions"][index]
    render_hero(f"Power up {spell['name']}!", f"Solve {total} questions correctly to earn this spell and take it back to the battle.", "Spell challenge")
    st.markdown(f"<div class='challenge-card' style='border-top:7px solid {spell['color']}'><div style='font-size:3.5rem'>{spell['emoji']}</div><h2>{spell['name']}</h2><p>{spell['description']}</p><span class='pill'>{spell['questions']} correct answers</span><span class='pill'>{spell['damage']} damage</span></div>", unsafe_allow_html=True)
    st.progress(index / total, text=f"{index} of {total} correct answers")
    st.markdown(f"<div class='question-box'><div class='question-caption'>Spell question {index + 1} of {total}</div><div class='challenge-math'>{problem['expression']} = ?</div></div>", unsafe_allow_html=True)
    if S.get("challenge_feedback"):
        if S["challenge_feedback"].startswith("Yes"):
            st.success(S["challenge_feedback"])
        else:
            st.info(S["challenge_feedback"])
    hint_col, blank = st.columns([1, 3])
    with hint_col:
        if st.button("💡 Counting hint", key=f"challenge_hint_{index}_{S['challenge_attempt']}"):
            st.info(problem["hint"])
    options = st.columns(3, gap="medium")
    for col, answer in zip(options, problem["choices"]):
        with col:
            if st.button(str(answer), key=f"challenge_answer_{index}_{S['challenge_attempt']}_{answer}", use_container_width=True):
                answer_challenge(answer)
                st.rerun()
    if st.button("← Back to the wizard battle", key="leave_challenge", use_container_width=True):
        S["screen"] = "battle"
        S["challenge_feedback"] = ""
        st.rerun()


def render_app() -> None:
    if S["screen"] == "home":
        render_home()
    elif S["screen"] == "map":
        render_map()
    elif S["screen"] == "battle":
        render_battle()
    elif S["screen"] == "spell_challenge":
        render_spell_challenge()
    else:
        S["screen"] = "home"
        st.rerun()


render_app()
