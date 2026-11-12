"""A family-friendly, original math-adventure game built with Streamlit."""

from __future__ import annotations

import random
import streamlit as st


st.set_page_config(
    page_title="The Wizard's Math Quest",
    page_icon="🪄",
    layout="wide",
    initial_sidebar_state="collapsed",
)


MATH_LEVELS = {
    1: {"title": "Tiny sums", "range": 5, "kind": "add", "summary": "Addition with numbers 0–5"},
    2: {"title": "Little leaps", "range": 10, "kind": "add", "summary": "Addition with numbers 0–10"},
    3: {"title": "Meadow sums", "range": 15, "kind": "add", "summary": "Addition with numbers 0–15"},
    4: {"title": "Big bridges", "range": 20, "kind": "add", "summary": "Addition with numbers 0–20"},
    5: {"title": "First takeaways", "range": 20, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–20"},
    6: {"title": "Silver sums", "range": 25, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–25"},
    7: {"title": "Forest numbers", "range": 30, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–30"},
    8: {"title": "Crystal challenge", "range": 40, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–40"},
    9: {"title": "Wizard's workshop", "range": 50, "kind": "mixed", "summary": "Addition and subtraction with numbers 0–50"},
    10: {"title": "Maldred's challenge", "range": 50, "kind": "subtract", "summary": "Subtraction with numbers 0–50"},
}


QUESTS = [
    {
        "name": "Sunpetal Meadow",
        "emoji": "🌻",
        "boss": "Pebblehex",
        "boss_emoji": "🧌",
        "subtitle": "The Lantern Seed",
        "story": "Pebblehex has hidden the meadow's glowing seed beneath a maze of thorny roots. Find the light before the flowers fall asleep.",
        "scene": "A golden meadow, a tiny winding stream, and flowers that blink like stars.",
        "reward": "Sunpetal Badge",
        "accent": "#d58d24",
        "ward": 92,
    },
    {
        "name": "Whispering Woods",
        "emoji": "🌲",
        "boss": "Bramblewyn",
        "boss_emoji": "🧙‍♀️",
        "subtitle": "The Stolen Echo",
        "story": "Bramblewyn has trapped the forest's friendly voices in a glass acorn. Follow the fireflies and set their echoes free.",
        "scene": "Tall blue-green trees, floating fireflies, and a path of silver leaves.",
        "reward": "Echo Acorn",
        "accent": "#418b63",
        "ward": 108,
    },
    {
        "name": "Moonstone Caves",
        "emoji": "💎",
        "boss": "Gloam the Crystal Mage",
        "boss_emoji": "🧙",
        "subtitle": "The Shattered Moonstone",
        "story": "Gloam has split the cave's moonstone into sparkling pieces. Light each crystal bridge to put the moonstone back together.",
        "scene": "A deep violet cavern with glowing crystals and a quiet underground lake.",
        "reward": "Moonstone Shard",
        "accent": "#8673d1",
        "ward": 124,
    },
    {
        "name": "Stormglass Skybridge",
        "emoji": "🌩️",
        "boss": "Vexa Stormwhirl",
        "boss_emoji": "🧝‍♀️",
        "subtitle": "The Wandering Wind",
        "story": "Vexa has turned the skybridge into a spinning wind maze. Bring the calm breeze back so the cloud villages can visit one another.",
        "scene": "Cloud castles, rainbow bridges, and harmless little storm clouds.",
        "reward": "Skybridge Crest",
        "accent": "#4384c5",
        "ward": 142,
    },
    {
        "name": "Obsidian Tower",
        "emoji": "🏰",
        "boss": "Maldred",
        "boss_emoji": "🧙‍♂️",
        "subtitle": "The Last Spell",
        "story": "Maldred waits at the top of the tower with a spell that could dim every star. Bring your friends' gifts together and break his shadow shield.",
        "scene": "A midnight tower above the clouds, with friendly stars lighting the stairs.",
        "reward": "Starkeeper Crown",
        "accent": "#bd668d",
        "ward": 165,
    },
]


SPELLS = {
    "spark": {
        "name": "Spark Bolt",
        "emoji": "✨",
        "cost": 0,
        "kind": "attack",
        "power": 12,
        "description": "A bright, dependable bolt of wizard light.",
    },
    "leaf": {
        "name": "Mending Leaf",
        "emoji": "🍃",
        "cost": 0,
        "kind": "heal",
        "power": 18,
        "description": "A kind forest spell that restores some shield hearts.",
    },
    "moonbeam": {
        "name": "Moonbeam Arc",
        "emoji": "🌙",
        "cost": 15,
        "kind": "attack",
        "power": 20,
        "description": "A curved ribbon of cool moonlight that cuts through dark magic.",
    },
    "frost": {
        "name": "Frostberry Flurry",
        "emoji": "🫐",
        "cost": 22,
        "kind": "attack",
        "power": 27,
        "description": "A burst of sparkling frostberries bonks the enemy's shadow shield.",
    },
    "sunshield": {
        "name": "Sunflower Shield",
        "emoji": "🌞",
        "cost": 18,
        "kind": "heal",
        "power": 34,
        "description": "A warm golden shield that restores lots of hearts.",
    },
    "starstorm": {
        "name": "Starstorm",
        "emoji": "🌠",
        "cost": 35,
        "kind": "attack",
        "power": 42,
        "description": "A dazzling shower of stars for the bravest wizard battles.",
    },
}


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@500;600;700;800;900&display=swap');
.stApp {
  background:
    radial-gradient(ellipse at 90% 3%, rgba(255, 212, 132, .25), transparent 30%),
    radial-gradient(ellipse at 4% 18%, rgba(177, 208, 255, .24), transparent 32%),
    linear-gradient(180deg, #fffaf0 0%, #f5f6ff 55%, #f2f9ff 100%);
  color: #27304c;
  font-family: 'Nunito', 'Trebuchet MS', sans-serif;
}
.block-container { max-width: 1120px; padding-top: 1.6rem; padding-bottom: 3rem; }
h1, h2, h3, p, label, [data-testid="stMarkdownContainer"] { font-family: 'Nunito', 'Trebuchet MS', sans-serif; }
h1 { color: #31295f; letter-spacing: -.03em; }
div.stButton > button {
  min-height: 3.05rem;
  border-radius: 16px;
  border: 1px solid #d9d7ef;
  background: #fff;
  color: #332d63;
  font-weight: 800;
  box-shadow: 0 4px 0 rgba(63, 56, 112, .08);
  transition: transform .12s ease, box-shadow .12s ease;
}
div.stButton > button:hover { border-color: #9887e8; color: #2d245f; transform: translateY(-2px); box-shadow: 0 6px 0 rgba(63, 56, 112, .10); }
div.stButton > button:focus { border-color: #6354b2; color: #2d245f; }
[data-testid="stProgressBar"] > div > div { background: linear-gradient(90deg, #79c786, #f4c765); }
.hero-banner {
  padding: 2rem 2rem 1.8rem; border-radius: 30px; color: white;
  background: linear-gradient(125deg, #39316e, #6651b6 58%, #987bd9);
  box-shadow: 0 12px 30px rgba(66, 51, 133, .18); margin-bottom: 1.2rem;
}
.hero-banner h1 { color: white !important; margin: .2rem 0 .4rem; }
.hero-banner p { color: #f2edff; font-size: 1.08rem; margin-bottom: .2rem; }
.eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: .78rem; font-weight: 900; opacity: .82; }
.quest-card {
  border: 1px solid rgba(72, 67, 112, .12); border-top: 5px solid var(--accent);
  border-radius: 22px; padding: 1rem 1.1rem; min-height: 205px; margin: .35rem 0 .5rem;
  background: linear-gradient(145deg, color-mix(in srgb, var(--accent) 10%, white), rgba(255,255,255,.94));
  box-shadow: 0 8px 20px rgba(47, 48, 90, .07);
}
.quest-emoji { font-size: 2.2rem; }
.quest-name { font-size: 1.18rem; font-weight: 900; color: #332d63; margin-top: .1rem; }
.quest-meta { color: #6b6686; font-size: .93rem; font-weight: 800; }
.quest-story { color: #514e6c; font-size: .95rem; line-height: 1.4; margin-top: .45rem; }
.locked { filter: saturate(.5); opacity: .68; }
.arena {
  border-radius: 26px; padding: 1.3rem 1.4rem; margin: .6rem 0 1rem;
  background: linear-gradient(125deg, color-mix(in srgb, var(--accent) 13%, white), #fff 55%, #f2efff);
  border: 1px solid color-mix(in srgb, var(--accent) 24%, white);
}
.arena-title { color: #332d63; font-size: 1.45rem; font-weight: 900; }
.arena-scene { color: #615c7b; font-size: .97rem; }
.battle-portrait { font-size: 3rem; line-height: 1.15; }
.battle-label { color: #5c5878; font-weight: 900; font-size: 1.05rem; }
.question-box {
  border: 2px solid #ded8ff; border-radius: 24px; background: white;
  padding: 1.15rem; text-align: center; margin: .8rem 0 .7rem;
  box-shadow: 0 8px 22px rgba(72, 58, 138, .08);
}
.question-caption { color: #716d8a; font-weight: 900; font-size: .95rem; }
.question-math { color: #30285f; font-weight: 900; font-size: 2.7rem; letter-spacing: .03em; }
.spell-card {
  height: 100%; padding: 1rem; border-radius: 20px; border: 1px solid #e4def6;
  background: linear-gradient(145deg, #fff, #f7f4ff); margin-bottom: .45rem;
}
.spell-icon { font-size: 1.8rem; }
.spell-name { font-size: 1.05rem; color: #332d63; font-weight: 900; }
.spell-detail { color: #68627f; font-size: .91rem; min-height: 3.1rem; }
.status-pill { display: inline-block; padding: .38rem .75rem; margin: .2rem .2rem .2rem 0; border-radius: 999px; background: #fff; border: 1px solid #e2def0; color: #514b76; font-weight: 900; }
.victory-banner {
  border-radius: 28px; padding: 2rem; color: #fff; text-align: center;
  background: linear-gradient(130deg, #43366e, #7960bc, #e5a257);
  box-shadow: 0 12px 30px rgba(66, 51, 133, .18);
}
.victory-banner h1 { color: #fff !important; }
@media (max-width: 700px) {
  .hero-banner { padding: 1.4rem; border-radius: 22px; }
  .question-math { font-size: 2.15rem; }
  .quest-card { min-height: 0; }
}
</style>
"""


st.markdown(CSS, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "screen": "home",
        "player": "Kate",
        "math_level": 1,
        "unlocked_stage": 0,
        "completed_stages": [],
        "stardust": 8,
        "owned_spells": ["spark", "leaf"],
        "current_stage": 0,
        "return_screen": "map",
        "question_index": 0,
        "attempt_count": 0,
        "questions": [],
        "turn_mode": "question",
        "hero_hp": 100,
        "enemy_hp": 100,
        "enemy_max_hp": 100,
        "battle_correct": 0,
        "battle_earned": 0,
        "is_replay": False,
        "hint_shown": False,
        "feedback": "",
        "round_message": "",
        "guardian_save": False,
        "maldred_defeated": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, list) else value


init_state()
S = st.session_state


def make_choices(answer: int, maximum: int) -> list[int]:
    choices = {answer}
    distance = 1
    while len(choices) < 3:
        for candidate in (answer - distance, answer + distance):
            if 0 <= candidate <= maximum:
                choices.add(candidate)
            if len(choices) == 3:
                break
        distance += 1
    result = list(choices)
    random.shuffle(result)
    return result


def make_problem(level: int) -> dict:
    info = MATH_LEVELS[level]
    maximum = info["range"]
    kind = info["kind"]
    if kind == "add":
        subtraction = False
    elif kind == "subtract":
        subtraction = True
    else:
        subtraction = random.random() < 0.45

    if subtraction:
        first = random.randint(0, maximum)
        second = random.randint(0, first)
        answer = first - second
        operator = "−"
        symbol = "−"
    else:
        first = random.randint(0, maximum)
        second = random.randint(0, maximum - first)
        answer = first + second
        operator = "+"
        symbol = "+"

    expression = f"{first} {symbol} {second}"
    if operator == "+":
        hint = f"Start at {first} and count forward {second} {('step' if second == 1 else 'steps')}."
        explanation = f"{first} + {second} = {answer}. Start at {first} and count forward {second} {('step' if second == 1 else 'steps')} to reach {answer}."
    else:
        hint = f"Start at {first} and count backward {second} {('step' if second == 1 else 'steps')}."
        explanation = f"{first} − {second} = {answer}. Start at {first} and count backward {second} {('step' if second == 1 else 'steps')} to reach {answer}."

    return {
        "first": first,
        "second": second,
        "operator": operator,
        "expression": expression,
        "answer": answer,
        "hint": hint,
        "explanation": explanation,
        "choices": make_choices(answer, maximum),
    }


def start_battle(stage_index: int) -> None:
    stage = QUESTS[stage_index]
    S["current_stage"] = stage_index
    S["is_replay"] = stage_index in S["completed_stages"]
    S["questions"] = [make_problem(S["math_level"]) for _ in range(10)]
    S["question_index"] = 0
    S["attempt_count"] = 0
    S["turn_mode"] = "question"
    S["hero_hp"] = 100
    S["enemy_max_hp"] = stage["ward"]
    S["enemy_hp"] = stage["ward"]
    S["battle_correct"] = 0
    S["battle_earned"] = 0
    S["hint_shown"] = False
    S["feedback"] = ""
    S["round_message"] = ""
    S["guardian_save"] = False
    S["screen"] = "battle"


def answer_question(answer: int) -> None:
    question = S["questions"][S["question_index"]]
    S["guardian_save"] = False
    if answer == question["answer"]:
        S["battle_correct"] += 1
        S["attempt_count"] = 0
        S["hint_shown"] = False
        if not S["is_replay"]:
            S["stardust"] += 3
            S["battle_earned"] += 3
        S["feedback"] = "Yes! Your math powered up a spell. Choose what to cast."
        S["turn_mode"] = "spell"
    else:
        if S["attempt_count"] == 0:
            S["attempt_count"] = 1
            S["hero_hp"] = max(0, S["hero_hp"] - 12)
            S["feedback"] = "Not quite yet. Would you like a hint and one more try, or would you like to see how to solve it?"
            if S["hero_hp"] == 0:
                S["hero_hp"] = 40
                S["guardian_save"] = True
            S["turn_mode"] = "first_miss"
        else:
            S["feedback"] = question["explanation"]
            S["turn_mode"] = "miss_feedback"


def cast_spell(spell_id: str) -> None:
    spell = SPELLS[spell_id]
    if spell["kind"] == "attack":
        actual_damage = min(spell["power"], S["enemy_hp"])
        S["enemy_hp"] = max(0, S["enemy_hp"] - spell["power"])
        if actual_damage:
            message = f"{spell['emoji']} {spell['name']} sparkles across the arena and breaks {actual_damage} points of {QUESTS[S['current_stage']]['boss']}'s shadow shield!"
            if S["enemy_hp"] == 0:
                message += " The shield is down! Finish all 10 questions to close the portal."
        else:
            message = f"{spell['emoji']} {spell['name']} lights the arena. The shadow shield is already down—finish all 10 questions to close the portal."
    else:
        before = S["hero_hp"]
        S["hero_hp"] = min(100, S["hero_hp"] + spell["power"])
        healed = S["hero_hp"] - before
        message = f"{spell['emoji']} {spell['name']} wraps you in a warm glow and restores {healed} shield hearts."

    S["round_message"] = message
    S["turn_mode"] = "spell_result"


def next_question() -> None:
    if S["question_index"] >= 9:
        S["turn_mode"] = "encounter_done"
    else:
        S["question_index"] += 1
        S["attempt_count"] = 0
        S["turn_mode"] = "question"
        S["hint_shown"] = False


def finish_battle() -> None:
    stage_index = S["current_stage"]
    stage = QUESTS[stage_index]
    if stage_index not in S["completed_stages"]:
        S["completed_stages"].append(stage_index)
        S["stardust"] += 8
        S["battle_earned"] += 8
        S["unlocked_stage"] = min(len(QUESTS) - 1, max(S["unlocked_stage"], stage_index + 1))
    if stage_index == len(QUESTS) - 1:
        S["maldred_defeated"] = True
        S["screen"] = "ending"
    else:
        S["screen"] = "reward"


def open_shop(return_screen: str = "map") -> None:
    S["return_screen"] = return_screen
    S["screen"] = "shop"


def open_spellbook(return_screen: str = "map") -> None:
    S["return_screen"] = return_screen
    S["screen"] = "spellbook"


def nav_buttons() -> None:
    left, middle, right = st.columns([1, 1, 1])
    with left:
        if st.button("🗺️ Quest map", key="nav_map", use_container_width=True):
            S["screen"] = "map"
            st.rerun()
    with middle:
        if st.button("✨ Spell shop", key="nav_shop", use_container_width=True):
            open_shop("map")
            st.rerun()
    with right:
        if st.button("📖 Spellbook", key="nav_spellbook", use_container_width=True):
            open_spellbook("map")
            st.rerun()


def render_banner(title: str, subtitle: str, eyebrow: str = "A magical math adventure") -> None:
    st.markdown(
        f"<div class='hero-banner'><div class='eyebrow'>{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>",
        unsafe_allow_html=True,
    )


def render_home() -> None:
    render_banner("The Wizard's Math Quest", "Answer math, earn spell gems, and help Kate or Lola save the stars.")
    st.markdown("### Choose your wizard")
    player_col, difficulty_col = st.columns([1, 1.35])
    with player_col:
        player = st.radio("Who is playing?", ["Kate", "Lola"], horizontal=True, key="home_player")
        avatar = "🧙🏻‍♀️" if player == "Kate" else "🧙🏽‍♀️"
        st.markdown(
            f"<div class='quest-card' style='--accent:#8a72d2'><div class='quest-emoji'>{avatar}</div><div class='quest-name'>Wizard {player}</div><div class='quest-story'>A brave spell-solver ready to help the friendly creatures of the Starwilds.</div></div>",
            unsafe_allow_html=True,
        )
    with difficulty_col:
        level = st.select_slider(
            "Choose a starting math level",
            options=list(MATH_LEVELS),
            value=1,
            key="home_math_level",
        )
        st.markdown(
            f"<div class='quest-card' style='--accent:#e5ad4c'><div class='quest-name'>Level {level}: {MATH_LEVELS[level]['title']}</div><div class='quest-story'>{MATH_LEVELS[level]['summary']}. Every battle has 10 questions. You can change the practice level from the quest map.</div></div>",
            unsafe_allow_html=True,
        )
        st.caption("The 1–10 setting changes the math. The story has five unique places to explore, ending at Maldred's tower.")

    with st.expander("How the adventure works"):
        st.markdown(
            "1. Visit a place on the quest map and meet its shadow wizard.\n"
            "2. Solve 10 math questions. A correct answer earns 3 star gems and lets you cast a spell.\n"
            "3. Spend gems in the spell shop to learn new attack and healing spells.\n"
            "4. Missed answers show a small explanation. The story keeps going, and a guardian protects your wizard.\n"
            "5. Collect the five keepsakes and use their light to face Maldred."
        )

    if st.button("✨ Begin the adventure", type="primary", use_container_width=True, key="begin_adventure"):
        S["player"] = player
        S["math_level"] = int(level)
        S["map_math_level"] = int(level)
        S["unlocked_stage"] = 0
        S["completed_stages"] = []
        S["stardust"] = 8
        S["owned_spells"] = ["spark", "leaf"]
        S["maldred_defeated"] = False
        S["screen"] = "map"
        st.rerun()


def quest_card(stage_index: int) -> None:
    stage = QUESTS[stage_index]
    complete = stage_index in S["completed_stages"]
    available = stage_index <= S["unlocked_stage"]
    locked_class = " locked" if not available else ""
    status = "✅ Complete — replay any time" if complete else ("🔓 Ready to explore" if available else "🔒 Complete the earlier place first")
    boss_line = "Final shadow wizard: Maldred" if stage_index == 4 else f"Shadow wizard: {stage['boss']}"
    st.markdown(
        f"<div class='quest-card{locked_class}' style='--accent:{stage['accent']}'><div class='quest-emoji'>{stage['emoji']}</div><div class='quest-name'>Place {stage_index + 1}: {stage['name']}</div><div class='quest-meta'>{stage['subtitle']} · {boss_line}</div><div class='quest-story'>{stage['story']}</div><div class='quest-meta'>{status}</div></div>",
        unsafe_allow_html=True,
    )
    label = "🔁 Replay place" if complete else "🪄 Enter this place"
    if available:
        if st.button(label, key=f"enter_stage_{stage_index}", use_container_width=True):
            start_battle(stage_index)
            st.rerun()
    else:
        st.button("Finish the earlier place to unlock", key=f"locked_stage_{stage_index}", disabled=True, use_container_width=True)


def render_map() -> None:
    nav_buttons()
    render_banner(f"Welcome, Wizard {S['player']}!", "The Starwilds need your help. Choose the next place on your map.", "Your quest map")
    a, b, c = st.columns(3)
    with a:
        st.markdown(f"<span class='status-pill'>✨ {S['stardust']} star gems</span>", unsafe_allow_html=True)
    with b:
        st.markdown(f"<span class='status-pill'>📚 Math level {S['math_level']} of 10</span>", unsafe_allow_html=True)
    with c:
        st.markdown(f"<span class='status-pill'>🏵️ {len(S['completed_stages'])} of 5 keepsakes</span>", unsafe_allow_html=True)

    level_options = list(MATH_LEVELS)
    if "map_math_level" not in st.session_state:
        st.session_state["map_math_level"] = S["math_level"]
    new_level = st.select_slider(
        "Practice level for the next battle",
        options=level_options,
        key="map_math_level",
    )
    S["math_level"] = int(new_level)
    st.caption(f"Level {new_level}: {MATH_LEVELS[new_level]['summary']}")

    st.markdown("### Places in the Starwilds")
    for row_start in range(0, len(QUESTS), 2):
        cols = st.columns(2, gap="medium")
        for offset, col in enumerate(cols):
            stage_index = row_start + offset
            if stage_index < len(QUESTS):
                with col:
                    quest_card(stage_index)


def render_battle() -> None:
    stage = QUESTS[S["current_stage"]]
    q_index = S["question_index"]
    question = S["questions"][q_index]
    answered_count = q_index if S["turn_mode"] == "question" else q_index + 1
    st.markdown(
        f"<div class='arena' style='--accent:{stage['accent']}'><div class='arena-title'>{stage['emoji']} {stage['name']} · {stage['subtitle']}</div><div class='arena-scene'>{stage['scene']}</div><div class='quest-story'>{stage['story']}</div></div>",
        unsafe_allow_html=True,
    )
    hero_col, enemy_col = st.columns(2)
    with hero_col:
        st.markdown(f"<div class='battle-portrait'>🧙‍♀️</div><div class='battle-label'>Wizard {S['player']}'s shield</div>", unsafe_allow_html=True)
        st.progress(S["hero_hp"] / 100, text=f"{S['hero_hp']} shield hearts")
    with enemy_col:
        st.markdown(f"<div class='battle-portrait'>{stage['boss_emoji']}</div><div class='battle-label'>{stage['boss']}'s shadow shield</div>", unsafe_allow_html=True)
        st.progress(S["enemy_hp"] / S["enemy_max_hp"], text=f"{S['enemy_hp']} shield power left")

    st.progress(answered_count / 10, text=f"{answered_count} of 10 math questions answered")
    st.markdown(
        f"<div class='question-box'><div class='question-caption'>Question {q_index + 1} of 10</div><div class='question-math'>{question['expression']} = ?</div></div>",
        unsafe_allow_html=True,
    )

    if S["turn_mode"] == "question":
        st.markdown("### Which number belongs in the spell circle?")
        if S["attempt_count"] > 0:
            st.caption("One more try — use the hint to help you think it through.")
        if not S["hint_shown"] and st.button("💡 Show me a hint", key=f"hint_{S['current_stage']}_{q_index}"):
            S["hint_shown"] = True
        if S["hint_shown"]:
            st.info(question["hint"])
        answer_cols = st.columns(3, gap="medium")
        for col, answer in zip(answer_cols, question["choices"]):
            with col:
                if st.button(str(answer), key=f"answer_{S['current_stage']}_{q_index}_{answer}", use_container_width=True):
                    answer_question(answer)
                    st.rerun()

    elif S["turn_mode"] == "spell":
        st.success(S["feedback"])
        if S["is_replay"]:
            st.caption("Replay battle: your star gems are safe, but you won't earn extra gems for this place.")
        else:
            st.caption("+3 star gems! Choose one of your learned spells to cast.")
        st.markdown("### Choose a spell")
        owned = [spell_id for spell_id in S["owned_spells"] if spell_id in SPELLS]
        for row_start in range(0, len(owned), 2):
            spell_cols = st.columns(2, gap="medium")
            for offset, col in enumerate(spell_cols):
                spell_pos = row_start + offset
                if spell_pos < len(owned):
                    spell_id = owned[spell_pos]
                    spell = SPELLS[spell_id]
                    power_label = f"{spell['power']} damage" if spell["kind"] == "attack" else f"up to {spell['power']} hearts"
                    with col:
                        st.markdown(
                            f"<div class='spell-card'><div class='spell-icon'>{spell['emoji']}</div><div class='spell-name'>{spell['name']}</div><div class='spell-detail'>{spell['description']}<br><b>{power_label}</b></div></div>",
                            unsafe_allow_html=True,
                        )
                        if st.button(f"Cast {spell['name']}", key=f"cast_{spell_id}_{q_index}", use_container_width=True):
                            cast_spell(spell_id)
                            st.rerun()

    elif S["turn_mode"] == "spell_result":
        st.success(S["round_message"])
        if q_index == 9:
            st.markdown("### The last spell is ready!")
            st.caption("Answer all 10 questions to finish this battle and claim your keepsake.")
            if st.button("🌟 Finish the battle", key="finish_last_correct", type="primary", use_container_width=True):
                next_question()
                st.rerun()
        else:
            if st.button("➡️ Next math question", key="next_after_spell", type="primary", use_container_width=True):
                next_question()
                st.rerun()

    elif S["turn_mode"] == "first_miss":
        st.info(S["feedback"])
        if S["guardian_save"]:
            st.success("Your friendly guardian caught you and restored some shield hearts. Keep going!")
        retry_col, solution_col = st.columns(2, gap="medium")
        with retry_col:
            if st.button("💡 Hint and try once more", key="retry_with_hint", type="primary", use_container_width=True):
                S["hint_shown"] = True
                S["turn_mode"] = "question"
                st.rerun()
        with solution_col:
            if st.button("📖 Show me how to solve it", key="show_solution", use_container_width=True):
                S["feedback"] = question["explanation"]
                S["turn_mode"] = "show_solution"
                st.rerun()

    elif S["turn_mode"] in ("miss_feedback", "show_solution"):
        st.info(S["feedback"])
        if S["turn_mode"] == "miss_feedback":
            st.caption("A little shadow bonk tapped your shield. You'll get another chance on the next question.")
        button_label = "🌟 Finish the battle" if q_index == 9 else "➡️ I understand — next question"
        if st.button(button_label, key="next_after_miss", type="primary", use_container_width=True):
            next_question()
            st.rerun()

    elif S["turn_mode"] == "encounter_done":
        st.success(f"You solved all 10 questions and chased {stage['boss']} away!")
        st.markdown(f"### Keepsake found: {stage['reward']} 🏵️")
        st.markdown(f"**Correct answers:** {S['battle_correct']} of 10")
        st.markdown(f"**Star gems earned in the battle:** {S['battle_earned']}")
        if st.button("🏵️ Claim the keepsake", key="claim_keepsake", type="primary", use_container_width=True):
            finish_battle()
            st.rerun()


def render_shop() -> None:
    back_label = "Back to the quest map" if S["return_screen"] == "map" else "Back to your reward"
    if st.button(f"← {back_label}", key="shop_back"):
        S["screen"] = S["return_screen"]
        st.rerun()
    render_banner("The Spell Shop", "Spend star gems to learn spells for your next battle.", "A friendly shop in the Starwilds")
    st.markdown(f"### ✨ You have {S['stardust']} star gems")
    st.caption("Learning a spell is a one-time purchase. Casting a learned spell is free.")

    spell_ids = list(SPELLS)
    for row_start in range(0, len(spell_ids), 2):
        cols = st.columns(2, gap="medium")
        for offset, col in enumerate(cols):
            pos = row_start + offset
            if pos < len(spell_ids):
                spell_id = spell_ids[pos]
                spell = SPELLS[spell_id]
                owned = spell_id in S["owned_spells"]
                kind_label = f"⚔️ {spell['power']} shield damage" if spell["kind"] == "attack" else f"💚 Heal up to {spell['power']} hearts"
                with col:
                    st.markdown(
                        f"<div class='spell-card'><div class='spell-icon'>{spell['emoji']}</div><div class='spell-name'>{spell['name']}</div><div class='spell-detail'>{spell['description']}<br><b>{kind_label}</b></div><span class='status-pill'>Cost: {spell['cost']} gems</span></div>",
                        unsafe_allow_html=True,
                    )
                    if owned:
                        st.success("Learned and ready to cast")
                    elif S["stardust"] >= spell["cost"]:
                        if st.button(f"Learn {spell['name']}", key=f"buy_{spell_id}", use_container_width=True):
                            S["stardust"] -= spell["cost"]
                            S["owned_spells"].append(spell_id)
                            st.rerun()
                    else:
                        st.button(f"Need {spell['cost'] - S['stardust']} more gems", key=f"need_{spell_id}", disabled=True, use_container_width=True)


def render_spellbook() -> None:
    if st.button("← Back to the quest map", key="spellbook_back"):
        S["screen"] = S["return_screen"]
        st.rerun()
    render_banner("Your Spellbook", "All learned spells are ready to cast after a correct answer.", "Magic you have learned")
    st.markdown(f"### ✨ Star gems: {S['stardust']}")
    for spell_id in S["owned_spells"]:
        spell = SPELLS[spell_id]
        kind_label = f"Deals {spell['power']} shield damage" if spell["kind"] == "attack" else f"Heals up to {spell['power']} shield hearts"
        st.markdown(
            f"<div class='spell-card'><span class='spell-icon'>{spell['emoji']}</span> &nbsp; <span class='spell-name'>{spell['name']}</span><br><div class='spell-detail'>{spell['description']} · {kind_label}</div></div>",
            unsafe_allow_html=True,
        )
    st.caption("Need a new spell? Visit the shop from the quest map.")


def render_reward() -> None:
    stage = QUESTS[S["current_stage"]]
    render_banner(f"{stage['reward']} collected!", f"The path to {QUESTS[S['unlocked_stage']]['name']} is open.", "Quest complete")
    accuracy = S["battle_correct"]
    st.markdown(f"### Great wizarding, {S['player']}! ✨")
    st.markdown(f"You answered **{accuracy} of 10** questions correctly and earned **{S['battle_earned']} star gems**.")
    st.progress(accuracy / 10, text=f"Math power: {accuracy} correct answers")
    st.markdown(f"**Keepsake:** {stage['reward']} {stage['emoji']}  ")
    st.markdown(f"**Next place:** {QUESTS[S['unlocked_stage']]['name']} {QUESTS[S['unlocked_stage']]['emoji']}")
    left, right = st.columns(2)
    with left:
        if st.button("✨ Visit the spell shop", key="reward_shop", type="primary", use_container_width=True):
            open_shop("reward")
            st.rerun()
    with right:
        if st.button("🗺️ Continue to the quest map", key="reward_map", use_container_width=True):
            S["screen"] = "map"
            st.rerun()


def render_ending() -> None:
    render_banner("Maldred's shadow is gone!", "The Starwilds shine again because you kept learning, one spell at a time.", "The final quest")
    st.markdown(
        "<div class='victory-banner'><div style='font-size:4rem'>🌟 🧙‍♀️ 🏰 🌟</div><div class='eyebrow'>A story saved by math</div><h1>Well done, Wizard "
        + S["player"]
        + "!</h1><p>You gathered five keepsakes, faced Maldred, and brought the stars back to the Starwilds.</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown("### Your keepsakes")
    keepsakes = st.columns(5)
    for col, stage in zip(keepsakes, QUESTS):
        with col:
            st.markdown(f"<div class='quest-card' style='--accent:{stage['accent']};text-align:center'><div class='quest-emoji'>{stage['emoji']}</div><div class='quest-meta'>{stage['reward']}</div></div>", unsafe_allow_html=True)
    st.markdown(f"### ✨ Star gems left: {S['stardust']}")
    if st.button("🗺️ Visit the completed quest map", key="ending_map", use_container_width=True):
        S["screen"] = "map"
        st.rerun()
    if st.button("🔁 Start a new adventure", key="new_adventure", use_container_width=True):
        S["screen"] = "home"
        S["maldred_defeated"] = False
        st.rerun()


screen = S["screen"]
if screen == "home":
    render_home()
elif screen == "map":
    render_map()
elif screen == "battle":
    render_battle()
elif screen == "shop":
    render_shop()
elif screen == "spellbook":
    render_spellbook()
elif screen == "reward":
    render_reward()
elif screen == "ending":
    render_ending()
else:
    S["screen"] = "home"
    st.rerun()
