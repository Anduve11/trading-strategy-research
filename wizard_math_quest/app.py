"""The Starwilds: a colorful math-powered wizard adventure for Kate and Lola."""

from __future__ import annotations

import base64
import random
import time
from pathlib import Path
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

ATTACK_INTRO_SECONDS = 3.6
ATTACK_INTERVAL_SECONDS = 3.8
ATTACK_HIT_OFFSET_SECONDS = 2.9
DEFEAT_ANIMATION_SECONDS = 2.4


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
.map-topbar {display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.7rem 1rem;margin:.15rem 0 .35rem;border-radius:22px;color:#fff;background:linear-gradient(110deg,#38316a,#7055bd 65%,#9b83df);box-shadow:0 7px 18px #44357933;}
.map-topbar h1 {color:#fff!important;font-size:clamp(1.15rem,2.5vw,1.7rem);margin:0;}
.map-topbar p {margin:.1rem 0 0;color:#f1ebff;font-weight:700;font-size:.9rem;}
.map-level {padding:.2rem .55rem;border-radius:14px;background:#fff;color:#4d427d;font-weight:900;}
.eyebrow { text-transform:uppercase; letter-spacing:.13em; font-size:.75rem; font-weight:900; opacity:.82; }
.pill { display:inline-block; padding:.42rem .78rem; border-radius:999px; border:1px solid #e5e0f0; background:white; margin:.15rem .25rem .3rem 0; font-weight:900; color:#514a77; }
.home-card { min-height:160px; border-radius:24px; padding:1.1rem; border:1px solid #e5def3; background:linear-gradient(145deg,#fff,#f5f0ff); box-shadow:0 8px 20px rgba(48,44,94,.07); }
.st-key-home_kate button,.st-key-home_lola button { min-height:4rem!important; font-size:1.2rem!important; border:3px solid #cfc7e4!important; color:#292344!important; background:#fff!important; }
.st-key-home_kate [data-testid="stBaseButton-primary"],.st-key-home_lola [data-testid="stBaseButton-primary"] { border-color:#6b53b7!important; color:#302853!important; background:linear-gradient(140deg,#fff3bd,#fff)!important; box-shadow:0 0 0 4px rgba(107,83,183,.14),0 5px 0 rgba(53,46,99,.1)!important; }
.island-intro { color:#514d70; font-weight:800; margin:.35rem 0 .65rem; }
/* The map artwork is static SVG; actual Streamlit buttons are transparent, positioned hit areas over each castle. */
.st-key-island_map { position:relative; isolation:isolate; height:min(72vh,760px); min-height:540px; overflow:hidden; border:7px solid white; border-radius:32px; box-shadow:0 16px 32px rgba(35,93,143,.2); background:linear-gradient(180deg,#67d1f2,#239fc9); margin:.35rem 0 .8rem; }
.st-key-island_map .map-art { position:absolute; inset:0; width:100%; height:min(72vh,760px)!important; z-index:0; }
.map-art { color:#fff; }
.island-sand,.island-land { position:absolute; left:-3%; right:-3%; bottom:-8%; height:80%; clip-path:polygon(0 40%,7% 28%,14% 34%,21% 18%,29% 26%,37% 8%,45% 22%,53% 20%,61% 31%,69% 12%,77% 23%,85% 13%,93% 31%,100% 20%,100% 100%,0 100%); }
.island-sand { bottom:-11%; background:#e5c27b; z-index:0; }
.island-land { background:linear-gradient(145deg,#d8f2a1 0%,#a4e17f 38%,#72c97d 100%); z-index:1; }
.map-heading { position:absolute; top:2.5%; left:3.5%; font-size:clamp(1rem,2vw,1.45rem); font-weight:1000; letter-spacing:.13em; text-shadow:0 2px 4px #459db1; }
.map-cloud { position:absolute; z-index:4; color:#fff; font-size:2.8rem; filter:drop-shadow(0 3px 2px rgba(47,144,175,.2)); }
.map-cloud.one { left:35%; top:9%; }.map-cloud.two { right:12%; top:12%; }
.map-wave { position:absolute; z-index:4; color:#d2f8ff; font-size:2.1rem; letter-spacing:.3rem; white-space:nowrap; opacity:.8; }
.map-wave.one { left:3%; top:28%; }.map-wave.two { right:2%; bottom:6%; }
.map-peak { position:absolute; z-index:4; width:0; height:0; border-left:47px solid transparent; border-right:47px solid transparent; border-bottom:92px solid #a9c6e0; filter:drop-shadow(0 5px 0 white); }
.map-peak:after { content:''; position:absolute; left:-17px; top:12px; border-left:17px solid transparent; border-right:17px solid transparent; border-bottom:31px solid white; }
.map-peak.peak-a { left:10%; top:30%; transform:scale(.9); }.map-peak.peak-b { right:12%; top:22%; transform:scale(1.05); }
.map-tree { position:absolute; z-index:4; font-size:2.5rem; filter:drop-shadow(0 3px 2px rgba(37,94,61,.2)); }
.map-tree.tree-a { left:21%; bottom:19%; }.map-tree.tree-b { left:69%; bottom:26%; }.map-tree.tree-c { left:73%; bottom:18%; font-size:2rem; }
.map-river { position:absolute; z-index:2; left:36%; top:45%; width:17%; height:49%; border-left:13px solid #62c9e6; border-radius:50%; transform:rotate(7deg); opacity:.9; }
.map-castle { position:absolute; width:clamp(112px,18%,150px); height:155px; transform:translate(-50%,-50%); z-index:5; text-align:center; color:#304366; }
.map-castle-0 { left:12%; top:63%; }.map-castle-1 { left:31%; top:38%; }.map-castle-2 { left:50%; top:65%; }.map-castle-3 { left:69%; top:37%; }.map-castle-4 { left:88%; top:58%; }
.castle-building { position:absolute; width:104px; height:93px; left:50%; transform:translateX(-50%); top:23px; filter:drop-shadow(0 7px 3px rgba(51,89,63,.18)); }
.castle-wall { position:absolute; bottom:0; left:21px; width:62px; height:53px; background:linear-gradient(150deg,#fff1bd,#e7d6aa); border:4px solid #625783; border-bottom-width:5px; border-radius:5px 5px 0 0; }
.castle-tower { position:absolute; bottom:38px; width:33px; height:68px; background:linear-gradient(150deg,#fff0bd,var(--castle-color)); border:4px solid #625783; border-bottom:0; }
.castle-tower:before { content:''; position:absolute; left:-5px; top:-21px; width:35px; height:22px; background:var(--castle-color); border:4px solid #625783; clip-path:polygon(0 100%,50% 0,100% 100%); }
.castle-tower.left { left:7px; }.castle-tower.right { right:7px; }
.castle-roof { position:absolute; top:3px; left:33px; width:36px; height:55px; background:linear-gradient(160deg,#fff3c9,var(--castle-color)); border:4px solid #625783; border-radius:16px 16px 0 0; }
.castle-door { position:absolute; bottom:0; left:44px; width:17px; height:29px; background:#745540; border:3px solid #58486d; border-radius:11px 11px 0 0; }
.castle-window { position:absolute; top:31px; left:17px; width:10px; height:13px; background:#bdefff; border:2px solid #554b73; border-radius:7px 7px 1px 1px; }.castle-window.right { left:auto; right:17px; }
.castle-flag { position:absolute; right:12px; top:-20px; width:4px; height:30px; background:#55466f; }.castle-flag:after { content:''; position:absolute; top:0; left:3px; width:18px; height:11px; background:#ffd64e; clip-path:polygon(0 0,100% 50%,0 100%); }
.castle-number { position:absolute; left:55px; top:-6px; z-index:2; width:40px; height:40px; border:4px solid #5c5078; border-radius:50%; background:#fff; color:#342d61; font-size:1.2rem; line-height:32px; font-weight:1000; box-shadow:0 3px 0 rgba(40,38,74,.14); }
.castle-name { position:absolute; left:0; right:0; bottom:0; padding:.22rem .3rem; border:2px solid rgba(83,70,125,.2); border-radius:999px; background:rgba(255,255,255,.97); font-size:.72rem; line-height:1.1; font-weight:1000; color:#304366; box-shadow:0 3px 5px #3d795e55; }
.map-castle.locked { filter:grayscale(.8) saturate(.5); opacity:.72; }
.map-castle.open { filter:drop-shadow(0 0 16px #fff38b); animation:castle-glow 1.6s ease-in-out infinite alternate; }
.map-path {position:absolute;z-index:3;width:22%;border-top:8px dotted #fff0a0;filter:drop-shadow(0 3px 1px #5e9a6477);transform-origin:left center;}
.map-path.a {left:14%;top:53%;transform:rotate(-38deg)}.map-path.b {left:33%;top:49%;transform:rotate(39deg)}.map-path.c {left:52%;top:51%;transform:rotate(-39deg)}.map-path.d {left:71%;top:46%;transform:rotate(34deg)}
.map-castle.done .castle-flag:after { background:#74d58d; }
@keyframes castle-glow { to { filter:drop-shadow(0 0 22px #fff394); transform:translate(-50%,-52%) scale(1.035); } }
.st-key-island_map [class*="st-key-castle_hit_"] { position:absolute!important; z-index:3; width:14%; height:24%; min-width:54px; }
.st-key-island_map .st-key-castle_hit_0 { left:5%; top:51%; }
.st-key-island_map .st-key-castle_hit_1 { left:24%; top:26%; }
.st-key-island_map .st-key-castle_hit_2 { left:43%; top:53%; }
.st-key-island_map .st-key-castle_hit_3 { left:62%; top:25%; }
.st-key-island_map .st-key-castle_hit_4 { left:81%; top:46%; }
.st-key-island_map [class*="st-key-castle_hit_"] button { width:100%; height:100%; min-height:0; color:transparent!important; background:transparent!important; border:2px solid transparent!important; box-shadow:none!important; padding:0!important; font-size:0!important; }
.st-key-island_map [class*="st-key-castle_hit_"] button:hover { background:rgba(255,240,120,.18)!important; border:3px solid rgba(255,255,255,.85)!important; box-shadow:0 0 24px 10px rgba(255,239,116,.55)!important; }
.st-key-island_map [class*="st-key-castle_hit_"] button:disabled { opacity:0!important; }
@media(max-width:900px) { .block-container { padding-left:.8rem!important; padding-right:.8rem!important; padding-top:.55rem!important; } .st-key-island_map { height:min(70vh,700px); min-height:500px; } .st-key-island_map .map-art {height:min(70vh,700px)!important;} .map-castle { transform:translate(-50%,-50%) scale(.9); } .map-heading {font-size:1.05rem} .st-key-island_map [class*="st-key-castle_hit_"] { min-width:44px; height:22%; } .map-cloud {font-size:2rem} .map-peak { transform:scale(.75)!important; } }
@media(max-width:600px) { .st-key-island_map { min-height:470px;height:64vh; } .st-key-island_map .map-art {height:64vh!important;} .map-castle { transform:translate(-50%,-50%) scale(.74); } .castle-name {font-size:.9rem;padding:.35rem;} }
.battle-shell { border-radius:30px; border:2px solid white; background:linear-gradient(145deg,#fff,#f8f5ff); box-shadow:0 12px 28px rgba(49,42,95,.1); padding:1rem; }
.battle-title { color:#51497a; font-size:1.05rem; font-weight:900; }
.battle-arena { --sky1:#b9eeff; --sky2:#72d6e9; --ground:#89d27f; position:relative; overflow:hidden; min-height:500px; border-radius:28px; border:5px solid white; box-shadow:inset 0 0 0 2px rgba(255,255,255,.45),0 12px 26px rgba(43,43,93,.15); background:radial-gradient(ellipse at 52% 48%,#fff8b655 0 15%,transparent 45%),linear-gradient(180deg,var(--sky1),var(--sky2) 60%,var(--ground) 60%,#5fb978); padding:1rem; }
.battle-arena:before { content:'☁️'; position:absolute; top:12%; left:7%; font-size:2.7rem; opacity:.75; }
.battle-arena:after { content:'✦　✧　✦'; position:absolute; top:13%; right:7%; color:#fff5a9; font-size:1.3rem; letter-spacing:.7rem; }
.battle-arena.woods { --sky1:#b7e6be; --sky2:#62b98b; --ground:#54985e; background:radial-gradient(ellipse at 50% 55%,#f6ffb533 0 20%,transparent 55%),linear-gradient(180deg,var(--sky1),var(--sky2) 60%,var(--ground) 60%,#386c47); }
.battle-arena.caves { --sky1:#7465bc; --sky2:#514786; --ground:#38335e; background:radial-gradient(ellipse at 50% 55%,#ff83f155 0 13%,transparent 47%),linear-gradient(180deg,var(--sky1),var(--sky2) 60%,var(--ground) 60%,#282541); }
.battle-arena.sky { --sky1:#b7e9ff; --sky2:#82c9f2; --ground:#d5f4ff; background:radial-gradient(ellipse at 50% 55%,#fffcc877 0 14%,transparent 48%),linear-gradient(180deg,var(--sky1),var(--sky2) 60%,var(--ground) 60%,#78b4da); }
.battle-arena.tower { --sky1:#393759; --sky2:#61528f; --ground:#393554; background:radial-gradient(ellipse at 50% 56%,#ec75c344 0 14%,transparent 48%),linear-gradient(180deg,var(--sky1),var(--sky2) 60%,var(--ground) 60%,#25243a); }
.arena-backdrop {position:absolute;inset:12% 0 23%;z-index:1;pointer-events:none;}
.arena-backdrop:before {content:'';position:absolute;left:-7%;right:-7%;bottom:-28%;height:65%;border-radius:55% 55% 0 0 / 78% 78% 0 0;background:linear-gradient(180deg,#ffffff22,#2b674433);}
.arena-prop {position:absolute;font-size:clamp(2.5rem,7vw,5rem);filter:drop-shadow(0 5px 3px #30304455);opacity:.78;animation:prop-float 4s ease-in-out infinite;}
.arena-prop.one {left:8%;bottom:3%;}.arena-prop.two {right:8%;bottom:8%;animation-delay:-2s;}
.battle-arena.caves .arena-prop {filter:drop-shadow(0 0 18px #c39aff);}
.battle-arena.tower .arena-prop {filter:drop-shadow(0 0 14px #f29bdf);}
.battle-arena.caves .arena-prop,.battle-arena.tower .arena-prop {opacity:.52;}
.duel { position:absolute; left:5%; right:5%; bottom:7%; height:74%; display:flex; align-items:flex-end; justify-content:space-between; z-index:2; }
.character { width:36%; height:100%; position:relative; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; }
.character.player-character { animation:hero-bob 2.3s ease-in-out infinite; }
.character.player-character.attacking { animation:hero-lunge .82s cubic-bezier(.2,.8,.3,1) 1; }
.character.boss { animation:boss-bob 2.8s ease-in-out infinite; }
.character.boss.hurt { animation:enemy-flinch .58s ease-in-out 1,boss-bob 2.8s ease-in-out infinite; filter:saturate(.68); }
.character.boss.hurt .sprite {animation:sprite-flinch .58s ease-in-out 1;filter:drop-shadow(0 0 15px #ffd064) saturate(.65);}
.sprite { width:min(100%,205px); height:78%; overflow:visible; filter:drop-shadow(0 9px 7px rgba(32,31,67,.2)); }
.char-name { background:rgba(255,255,255,.88); padding:.18rem .55rem; border-radius:999px; font-size:.86rem; color:#322c56; font-weight:900; margin-top:.1rem; }
.head-health { position:absolute; top:0; width:90%; text-align:center; z-index:5; }
.head-health b { display:block; color:white; text-shadow:0 2px 4px #392f63; font-size:.8rem; }
.health-track { height:12px; border:2px solid white; border-radius:99px; background:#5b3449; overflow:hidden; box-shadow:0 2px 5px rgba(37,31,75,.25); }
.health-fill { display:block; height:100%; border-radius:99px; background:linear-gradient(90deg,#68dd75,#a9ef6b); transition:width .35s ease; }
.boss .health-fill { background:linear-gradient(90deg,#ff727a,#f7be54); }
.spell-projectile {position:absolute;left:27%;top:51%;z-index:4;font-size:2.7rem;filter:drop-shadow(0 0 16px #fff5a7);animation:projectile .65s cubic-bezier(.2,.85,.25,1) 1 forwards;}
.spell-impact { position:absolute; left:76%; top:42%; transform:translate(-50%,-50%); z-index:4; font-size:clamp(3rem,7vw,5.2rem); filter:drop-shadow(0 0 18px #fff5a7); animation:impact .85s ease-out 1 forwards; }
.boss-hurt { position:absolute; top:18%; right:6%; z-index:5; color:#fff4e8; font-size:1.5rem; font-weight:1000; text-shadow:0 3px 4px #5c315b; animation:damage-pop .85s ease-out 1 forwards; }
.arena-caption { position:absolute; z-index:1; left:0; right:0; top:5%; color:white; text-align:center; font-weight:900; text-shadow:0 2px 5px #474075; }
@keyframes hero-bob { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-8px); } }
@keyframes hero-lunge {0%{transform:translateX(0) translateY(0)}35%{transform:translateX(48%) translateY(-36px) rotate(9deg)}70%{transform:translateX(34%) translateY(-12px) rotate(3deg)}100%{transform:translateX(0) translateY(0)}}
@keyframes sprite-flinch {0%,100%{transform:translateX(0) rotate(0)}20%{transform:translateX(-13px) rotate(-9deg)}55%{transform:translateX(12px) rotate(7deg)}80%{transform:translateX(-5px) rotate(-3deg)}}
@keyframes projectile {0%{opacity:0;transform:translate(0,0) scale(.5) rotate(0)}20%{opacity:1}80%{opacity:1}100%{opacity:0;transform:translate(420%, -35%) scale(1.7) rotate(420deg)}}
@keyframes prop-float {0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
@keyframes boss-bob { 0%,100% { transform:translateY(0) rotate(0); } 50% { transform:translateY(-5px) rotate(1deg); } }
@keyframes enemy-flinch { 0%,100% { transform:translateX(0) rotate(0); } 25% { transform:translateX(-11px) rotate(-7deg); } 60% { transform:translateX(9px) rotate(6deg); } }
@keyframes impact { 0% { opacity:.2; transform:translate(-50%,-50%) scale(.35) rotate(-30deg); } 35% {opacity:1;transform:translate(-50%,-50%) scale(1.2) rotate(18deg)} 100% {opacity:0;transform:translate(-50%,-50%) scale(1.5) rotate(35deg)} }
@keyframes damage-pop { 0% { opacity:0; transform:translateY(18px) scale(.7); } 35% {opacity:1;transform:translateY(-10px) scale(1.1)} 100% {opacity:0;transform:translateY(-25px) scale(1.15)} }
.spell-pick { min-height:94px; border-radius:19px; padding:.75rem; border:1px solid #e6dff2; background:linear-gradient(140deg,#fff,#f5f1ff); margin:.25rem 0 .25rem; }
.spell-pick .spell-title { font-size:1rem; font-weight:1000; color:#352e64; }
.spell-pick .spell-detail { font-size:.84rem; color:#6a6480; line-height:1.3; }
.spell-chip { display:inline-block; padding:.22rem .55rem; border-radius:999px; background:#fff2c7; color:#65501c; font-weight:900; font-size:.8rem; margin-top:.3rem; }
@keyframes spell-ready { 50% { box-shadow:0 0 0 6px rgba(255,210,73,.12),0 5px 0 rgba(82,61,23,.1)!important; } }
.challenge-card { border-radius:26px; padding:1.3rem; background:linear-gradient(135deg,#fff,#f2edff); border:2px solid white; box-shadow:0 12px 28px rgba(51,42,99,.11); text-align:center; margin:.6rem 0 1rem; }
.challenge-math { font-size:3rem; font-weight:1000; color:#30285f; padding:.6rem; }
.challenge-finish { border-radius:25px; background:linear-gradient(130deg,#fff0b9,#fff,#e4fbe9); padding:1.2rem; text-align:center; font-weight:900; }
.leaderboard-hero { padding:1.2rem 1.5rem; border-radius:26px; color:#fff; background:linear-gradient(110deg,#30295e,#684cb2 62%,#a575dc); box-shadow:0 10px 25px #3b2b6633; margin:.2rem 0 1rem; text-align:center; }
.leaderboard-hero h1 { color:#fff!important; margin:.15rem 0; font-size:clamp(1.7rem,4vw,2.5rem); }
.leaderboard-hero p { color:#f7edff; margin:0; font-weight:800; }
.leaderboard-summary { border-radius:23px; border:2px solid #fff; padding:.9rem; background:linear-gradient(145deg,#fff,#f1eaff); box-shadow:0 8px 18px #4c39751a; text-align:center; min-height:115px; }
.leaderboard-summary .summary-value { display:block; font-size:clamp(1.15rem,2.2vw,1.7rem); font-weight:1000; color:#45347c; }
.leaderboard-summary .summary-label { color:#72648d; font-size:.82rem; font-weight:900; }
.leaderboard-table-title { margin:1.2rem 0 .45rem; font-size:1.3rem; font-weight:1000; color:#392e6d; }
.st-key-new_adventure button { min-height:3.5rem!important; border:3px solid white!important; background:linear-gradient(120deg,#ffe45f,#ffad48)!important; box-shadow:0 5px 0 #b9683a!important; font-size:1.05rem!important; }
.notice { padding:.8rem 1rem; border-radius:18px; background:#fff3c8; border:1px solid #efd77b; color:#56451d; font-weight:900; margin:.5rem 0; }
@media(max-width:700px) { .battle-arena { min-height:330px; } .duel { left:2%; right:2%; } .character { width:42%; } .sprite { width:100%; } .challenge-math { font-size:2.2rem; } }

/* Rich, original game artwork and large tablet-friendly play areas. */
.st-key-island_map { --map-height:min(70vh,760px); height:var(--map-height)!important; min-height:var(--map-height)!important; }
.st-key-island_map .map-art { inset:0; width:100%; height:var(--map-height)!important; min-height:var(--map-height)!important; background:url('/app/static/starwilds_map.webp') center/100% 100% no-repeat; }
.st-key-island_map .map-art > :not(.map-castle) { display:none!important; }
.map-castle { width:14%; height:24%; transform:translate(-50%,-50%); z-index:4; color:#fff; pointer-events:none; }
.map-castle-0 { left:15%; top:56%; }.map-castle-1 { left:22%; top:18%; }.map-castle-2 { left:50%; top:57%; }.map-castle-3 { left:73%; top:16%; }.map-castle-4 { left:83%; top:48%; }
.castle-number { left:50%; top:50%; transform:translate(-50%,-50%); width:clamp(36px,4vw,50px); height:clamp(36px,4vw,50px); line-height:clamp(28px,3.3vw,42px); border:4px solid #fff; background:linear-gradient(145deg,#ffdc5e,#ff9f35); color:#382b67; box-shadow:0 4px 0 #59407b,0 0 0 4px #fff5; }
.castle-name { bottom:0; padding:.35rem .4rem; font-size:clamp(.58rem,1vw,.82rem); background:linear-gradient(135deg,#fff,#fff3ce); border:2px solid #fff; box-shadow:0 4px 9px #28234b66; white-space:nowrap; }
.map-castle.locked { opacity:.82; filter:grayscale(.55) saturate(.72); }
.map-castle.open { opacity:1; filter:drop-shadow(0 0 15px #fff45f); animation:castle-glow 1.5s ease-in-out infinite alternate; }
.map-castle.done .castle-number { background:linear-gradient(145deg,#8cf5a9,#42c978); }
.st-key-island_map [class*="st-key-castle_hit_"] { position:absolute!important; z-index:6; width:clamp(84px,16%,165px)!important; height:clamp(120px,24%,170px)!important; min-width:0!important; transform:translate(-50%,-50%)!important; }
.st-key-island_map .st-key-castle_hit_0 { left:15%; top:56%; }.st-key-island_map .st-key-castle_hit_1 { left:22%; top:18%; }.st-key-island_map .st-key-castle_hit_2 { left:50%; top:57%; }.st-key-island_map .st-key-castle_hit_3 { left:73%; top:16%; }.st-key-island_map .st-key-castle_hit_4 { left:83%; top:48%; }
.st-key-island_map [class*="st-key-castle_hit_"] button { display:block!important; width:100%!important; height:100%!important; min-height:100%!important; padding:0!important; color:transparent!important; font-size:0!important; border:2px solid transparent!important; border-radius:24px!important; background:transparent!important; box-shadow:none!important; }
.st-key-island_map [class*="st-key-castle_hit_"] [data-testid="stButton"],.st-key-island_map [class*="st-key-castle_hit_"] [data-testid="stButton"]>div,.st-key-island_map [class*="st-key-castle_hit_"] [data-testid="stTooltipIcon"],.st-key-island_map [class*="st-key-castle_hit_"] [data-testid="stTooltipHoverTarget"] { display:block!important; height:100%!important; min-height:100%!important; }
.st-key-island_map [class*="st-key-castle_hit_"] button:hover { border:3px solid #fff!important; background:#ffe15b22!important; box-shadow:0 0 30px 12px #ffe15b99!important; }
.st-key-island_map [class*="st-key-castle_hit_"] button:disabled { opacity:0!important; pointer-events:none!important; }
.map-topbar { padding:.5rem .9rem; }
.battle-heading { margin:.1rem 0 .65rem; padding:.8rem 1.1rem; border-radius:22px; color:#fff; background:linear-gradient(110deg,#30295e,#6348a7 65%,#9b68dc); box-shadow:0 8px 18px #39315a33; }
.battle-heading .eyebrow { color:#ffe693; }
.battle-heading h1 { color:#fff!important; margin:.15rem 0; font-size:clamp(1.25rem,2.5vw,1.9rem); }
.battle-heading p { margin:0; color:#f4eaff; font-weight:800; }
.store-title { padding:.6rem .8rem; margin:.1rem 0 .55rem; border-radius:18px; color:#fff; background:linear-gradient(130deg,#d17c31,#f1ad42); box-shadow:0 4px 0 #b86635; font-size:1.2rem; font-weight:1000; text-align:center; }
.st-key-battle_arena { --arena-height:min(78vh,900px); position:relative!important; isolation:isolate; height:var(--arena-height)!important; min-height:560px!important; overflow:visible!important; margin:0!important; }
.st-key-battle_arena .battle-arena { position:absolute; inset:0; width:100%; height:var(--arena-height)!important; min-height:var(--arena-height)!important; padding:0; border:6px solid #fff; border-radius:30px; background:#362d5b url('/app/static/arena.webp') center/cover no-repeat; box-shadow:0 15px 34px #2f285044,inset 0 0 0 2px #fff8; }
.st-key-battle_arena .battle-arena:before { content:''; inset:0; top:0; left:0; width:auto; height:auto; border-radius:24px; background:linear-gradient(180deg,#10143335 0%,#1b153022 44%,#26132816 100%); opacity:1; font-size:0; }
.st-key-battle_arena .battle-arena:after { content:'✦  ✧  ✦'; top:15%; right:4%; color:#fff4a3; text-shadow:0 0 14px #ffdb55; animation:star-twinkle 1.7s ease-in-out infinite; }
.st-key-battle_arena .arena-caption { top:3%; z-index:4; font-size:clamp(.85rem,1.45vw,1.15rem); letter-spacing:.03em; }
.st-key-battle_arena .duel { left:2%; right:2%; bottom:5%; height:78%; align-items:flex-end; }
.st-key-battle_arena .character { width:34%; height:100%; }
.st-key-battle_arena .player-character { margin-right:auto; }
.st-key-battle_arena .boss { margin-left:auto; }
.st-key-battle_arena .sprite { display:block; width:100%; height:90%; max-width:none; object-fit:contain; object-position:center bottom; filter:drop-shadow(0 10px 9px #17152a88); }
.st-key-battle_arena .hero-sprite { background:url('/app/static/hero.webp') center bottom/auto 72% no-repeat; }
.st-key-battle_arena .boss-sprite { background:url('/app/static/maldred.webp') center bottom/auto 72% no-repeat; transform-origin:center bottom; }
.st-key-battle_arena .boss-scale-1 { transform:scale(1); }
.st-key-battle_arena .boss-scale-2 { transform:scale(1.1); }
.st-key-battle_arena .boss-scale-3 { transform:scale(1.2); }
.st-key-battle_arena .boss-scale-4 { transform:scale(1.32); }
.st-key-battle_arena .boss-scale-5 { transform:scale(1.52); }
.st-key-battle_arena .character.player-character { animation:hero-prowl 4s ease-in-out infinite; }
.st-key-battle_arena .character.player-character.attacking { animation:hero-lunge .82s cubic-bezier(.2,.8,.3,1) 1; }
.st-key-battle_arena .character.boss { animation:boss-prowl 4.6s ease-in-out infinite; }
.st-key-battle_arena .character.boss.hurt .sprite { filter:drop-shadow(0 0 22px #ffe158) saturate(.7); animation:sprite-flinch .6s ease-in-out 1; }
.st-key-battle_arena .character.boss.defeated { transform-origin:center bottom; animation:boss-disappear 2.4s cubic-bezier(.45,0,.9,.4) forwards; }
.st-key-battle_arena .head-health { top:18%; width:92%; }
.st-key-battle_arena .head-health b { font-size:clamp(.75rem,1.2vw,1rem); }
.st-key-battle_arena .health-track { height:16px; box-shadow:0 2px 8px #171329a8; }
.st-key-battle_arena .char-name { position:absolute; bottom:1%; font-size:clamp(.72rem,1.05vw,.95rem); box-shadow:0 4px 10px #19162d88; }
.st-key-battle_arena .enemy-attack { position:absolute; z-index:4; left:76%; top:52%; width:clamp(30px,4.2vw,46px); aspect-ratio:1; border:2px solid #ffd5ff; border-radius:50%; background:radial-gradient(circle at 32% 28%,#fff 0 7%,#ffc2ff 10%,#e45cff 31%,#a22de9 62%,#55129b 100%); box-shadow:0 0 12px #f4a0ff,0 0 28px #d454ff,0 0 48px #9b35ee88; animation:enemy-bolt 3.8s linear infinite; }
.st-key-battle_arena .enemy-attack:before { content:''; position:absolute; left:-50%; top:28%; width:70%; height:42%; border-radius:50%; background:linear-gradient(90deg,transparent,#f78affaa,#ffdbff); filter:blur(4px); transform:rotate(-18deg); }
.st-key-battle_arena .enemy-attack:after { content:'✦'; position:absolute; left:-18%; top:-24%; color:#fff; font-size:clamp(.75rem,1.2vw,1rem); text-shadow:0 0 8px #fff; }
.st-key-battle_arena .spell-projectile { left:26%; top:46%; font-size:4rem; animation:projectile .72s cubic-bezier(.2,.85,.25,1) 1 forwards; }
.st-key-battle_arena .spell-impact { left:77%; top:48%; font-size:5rem; }
.st-key-battle_arena .boss-hurt { top:26%; right:12%; font-size:2rem; }
.battle-warning { position:absolute; z-index:12; top:8%; right:3%; width:min(49%,520px); padding:.75rem 1rem; border:3px solid #fff; border-radius:22px; color:#49325b; background:linear-gradient(135deg,#fff7b8,#ffd270); box-shadow:0 8px 24px #39275b88,0 0 0 4px #ffd85e66; text-align:center; font-weight:1000; font-size:clamp(.9rem,1.45vw,1.16rem); animation:warning-pop .35s cubic-bezier(.2,.8,.2,1) both; }
.battle-warning span { display:block; font-size:.82em; color:#684a6d; margin-top:.12rem; }
.battle-winner { position:absolute; z-index:15; top:32%; left:14%; right:14%; padding:1.1rem; border:4px solid #fff; border-radius:28px; color:#51376d; background:linear-gradient(135deg,#fff7b8f5,#ffda6cf5); box-shadow:0 10px 30px #29203d88,0 0 0 6px #ffe77366; text-align:center; animation:winner-pop .55s cubic-bezier(.2,.9,.3,1.2) both; }
.battle-winner h2 { color:#62398f!important; margin:.1rem 0; font-size:clamp(1.45rem,3vw,2.25rem); }
.battle-winner p { margin:.15rem 0 0; color:#593c70; font-size:clamp(.85rem,1.4vw,1.05rem); font-weight:900; }
.st-key-battle_arena .st-key-defeat_continue { position:absolute!important; z-index:18; width:min(64%,360px)!important; left:50%!important; bottom:10%!important; transform:translateX(-50%)!important; }
.st-key-battle_arena .st-key-defeat_continue button { min-height:3.6rem!important; border:3px solid white!important; color:#523563!important; background:linear-gradient(120deg,#ffe45f,#ffac48)!important; box-shadow:0 5px 0 #b9683a,0 0 20px #ffe35c!important; font-size:1.05rem!important; }
.st-key-battle_arena [class*="st-key-battle_spell_"] { position:absolute!important; z-index:8; width:clamp(62px,12%,100px)!important; transform:translate(-50%,-50%)!important; }
.st-key-battle_arena .st-key-battle_spell_0 { left:49%; top:56%; }.st-key-battle_arena .st-key-battle_spell_1 { left:49%; top:68%; }.st-key-battle_arena .st-key-battle_spell_2 { left:49%; top:80%; }.st-key-battle_arena .st-key-battle_spell_3 { left:49%; top:92%; }
.st-key-battle_arena [class*="st-key-battle_spell_"] button { width:100%; min-height:clamp(70px,9vh,82px)!important; padding:.35rem!important; border:3px solid #fff!important; border-radius:20px!important; color:#382a5f!important; background:linear-gradient(145deg,#fffbe4,#ffe18b)!important; box-shadow:0 5px 0 #a77745,0 0 18px #ffe669!important; font-size:clamp(.68rem,1.05vw,.9rem)!important; line-height:1.08!important; white-space:normal!important; animation:spell-ready 1.8s ease-in-out infinite; }
.st-key-battle_arena [class*="st-key-battle_spell_"] button:hover { transform:translateY(-4px) scale(1.03)!important; }
.st-key-battle_arena [class*="st-key-battle_spell_"] button:disabled { opacity:.7!important; }
.spell-pick { min-height:unset; padding:.55rem .6rem; border-radius:16px; background:linear-gradient(145deg,#fff,#fff7df); box-shadow:0 4px 11px #49356013; }
.spell-pick.new-spell { border:3px solid #ffbe37!important; background:linear-gradient(135deg,#fff6a8,#ffe08a)!important; box-shadow:0 0 0 4px #ffc83d55,0 0 24px #ffca4caa!important; animation:new-spell-glow .9s ease-in-out infinite alternate; }
.spell-pick .spell-title { font-size:.9rem; }
.spell-pick .spell-detail { font-size:.73rem; }
.spell-chip { font-size:.7rem; line-height:1.2; }
.store-caption { font-size:.82rem; color:#61577d; font-weight:800; margin-bottom:.55rem; }
.challenge-heading { padding:.75rem 1rem; margin:.1rem 0 .55rem; border-radius:22px; color:#fff; background:linear-gradient(110deg,#30295e,#6348a7 65%,#9b68dc); }
.challenge-heading h1 { color:#fff!important; font-size:clamp(1.4rem,3vw,2rem); margin:.1rem 0; }
.challenge-heading p { color:#f7edff; margin:0; font-weight:800; }
.pressure-banner { position:relative; height:132px; overflow:hidden; border:3px solid #fff; border-radius:24px; margin:.3rem 0 .65rem; background:linear-gradient(110deg,#353056cc,#774277aa),url('/app/static/arena.webp') center 50%/cover; box-shadow:0 7px 20px #362e5b33; }
.pressure-label { position:absolute; top:9px; left:0; right:0; text-align:center; color:#fff; text-shadow:0 2px 5px #1f1836; font-weight:1000; font-size:.95rem; z-index:5; }
.pressure-hero,.pressure-boss { position:absolute; bottom:-17px; width:22%; height:115px; background-repeat:no-repeat; background-size:contain; background-position:center bottom; filter:drop-shadow(0 4px 4px #15132b88); }
.pressure-hero { left:8%; background-image:url('/app/static/hero.webp'); animation:hero-bob 1.4s ease-in-out infinite; }
.pressure-boss { right:8%; background-image:url('/app/static/maldred.webp'); animation:boss-bob 1.4s ease-in-out infinite; }
.pressure-bolt { position:absolute; z-index:3; left:72%; top:44%; width:28px; height:28px; border:2px solid #ffd5ff; border-radius:50%; background:radial-gradient(circle at 32% 28%,#fff 0 7%,#ffc2ff 10%,#e45cff 31%,#a22de9 62%,#55129b 100%); box-shadow:0 0 12px #f4a0ff,0 0 28px #d454ff; animation:enemy-bolt 3.8s linear infinite; }
.pressure-health { position:absolute; left:7%; bottom:5px; z-index:4; width:26%; color:#fff; font-size:.75rem; font-weight:1000; text-shadow:0 2px 5px #1e1639; }
.pressure-health .health-track { height:14px; }
.attack-flash { position:absolute; inset:0; pointer-events:none; background:#ef65e71c; animation:pressure-pulse 1.2s steps(2,end) infinite; }
.challenge-card { padding:.9rem 1rem; margin:.2rem 0 .5rem; }
.challenge-card h2 { margin:.1rem 0; font-size:1.4rem; }
.challenge-math { font-size:clamp(2.2rem,5vw,3.2rem); padding:.1rem; }
.question-box { padding:.7rem; border:3px solid #fff; border-radius:23px; background:linear-gradient(135deg,#fff,#fff5d6); box-shadow:0 7px 18px #53427c22; text-align:center; }
.question-caption { color:#735f9b; font-weight:1000; }
.st-key-challenge_hint_ button { min-height:2.8rem!important; }
.st-key-leave_challenge button { min-height:2.7rem!important; }
.challenge-answer-row button { min-height:4.4rem!important; font-size:1.7rem!important; border-color:#a995da!important; background:linear-gradient(145deg,#fff,#f1eaff)!important; }
.st-key-challenge_answers button { min-height:4.2rem!important; font-size:1.6rem!important; border-color:#a995da!important; background:linear-gradient(145deg,#fff,#f1eaff)!important; }
.hp-badge { color:#fff; }
@keyframes enemy-bolt { 0%,12% { opacity:0; transform:translateX(0) scale(.6) rotate(0); } 22% {opacity:1;} 76% {opacity:1;transform:translateX(-1050%) scale(1.35) rotate(330deg);} 100% {opacity:0;transform:translateX(-1120%) scale(.6) rotate(420deg);} }
@keyframes hero-prowl { 0%,100% { transform:translate(0,0) rotate(0); } 24% {transform:translate(7px,-7px) rotate(1deg);} 53% {transform:translate(22px,0) rotate(-1deg);} 78% {transform:translate(5px,-11px) rotate(1deg);} }
@keyframes boss-prowl { 0%,100% { transform:translate(0,0) rotate(0); } 26% {transform:translate(-8px,-6px) rotate(-1deg);} 58% {transform:translate(-24px,0) rotate(1deg);} 82% {transform:translate(-4px,-10px) rotate(-1deg);} }
@keyframes boss-disappear { 0% {opacity:1;transform:scale(1) rotate(0);filter:brightness(1);} 35% {opacity:1;transform:scale(.82) rotate(8deg);filter:brightness(1.5);} 70% {opacity:.65;transform:scale(.38) rotate(-16deg);filter:brightness(2);} 100% {opacity:0;transform:scale(0) rotate(30deg);filter:brightness(3);} }
@keyframes warning-pop { from {opacity:0;transform:translateY(-12px) scale(.94);} to {opacity:1;transform:translateY(0) scale(1);} }
@keyframes winner-pop { from {opacity:0;transform:scale(.65) rotate(-3deg);} to {opacity:1;transform:scale(1) rotate(0);} }
@keyframes new-spell-glow { from {filter:brightness(1);box-shadow:0 0 0 3px #ffc83d44,0 0 12px #ffca4c88;} to {filter:brightness(1.13);box-shadow:0 0 0 6px #ffe24c99,0 0 28px #ffe24ccc;} }
@keyframes star-twinkle { 50% {opacity:.25; transform:scale(.8);} }
@keyframes pressure-pulse { 50% {background:#e147ea18;} }
@media(max-width:900px) {
  .block-container { padding-left:.7rem!important; padding-right:.7rem!important; padding-top:.45rem!important; }
  .st-key-island_map { --map-height:min(68vh,700px); }
  .st-key-island_map .map-art { background-size:100% 100%; }
  .map-castle { width:16%; height:23%; }
  .st-key-island_map [class*="st-key-castle_hit_"] { width:clamp(88px,17%,150px)!important; height:clamp(120px,23%,160px)!important; }
  .st-key-battle_arena { --arena-height:min(74vh,780px); min-height:500px!important; }
  .store-title { padding:.45rem .4rem; font-size:1rem; }
  .store-caption { font-size:.74rem; }
  .spell-pick { padding:.42rem; }
  .st-key-battle_arena [class*="st-key-battle_spell_"] button { font-size:.7rem!important; }
}
@media(max-width:600px) {
  .st-key-island_map { --map-height:min(64vh,590px); }
  .map-topbar { align-items:flex-start; }
  .map-topbar p { font-size:.75rem; }
  .map-level { font-size:.75rem; white-space:nowrap; }
  .st-key-battle_arena { --arena-height:540px; min-height:540px!important; }
  .battle-heading { padding:.6rem .8rem; }
  .st-key-battle_arena .character { width:35%; }
  .st-key-battle_arena .duel { left:0; right:0; }
  .st-key-battle_arena [class*="st-key-battle_spell_"] { width:70px!important; }
  .st-key-battle_arena .st-key-battle_spell_0 { left:49%;top:56%; }.st-key-battle_arena .st-key-battle_spell_1 { left:49%;top:68%; }.st-key-battle_arena .st-key-battle_spell_2 { left:49%;top:80%; }.st-key-battle_arena .st-key-battle_spell_3 { left:49%;top:92%; }
  .pressure-label { font-size:.8rem; }
  .pressure-hero,.pressure-boss { width:28%; }
  .battle-warning { top:7%; right:3%; width:56%; padding:.55rem .65rem; font-size:.8rem; }
  .battle-winner { left:5%; right:5%; top:34%; padding:.75rem; }
}
</style>
"""


def inline_art(filename: str) -> str:
    image_path = Path(__file__).resolve().parent / "static" / filename
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/webp;base64,{encoded}"


for art_file in ("starwilds_map.webp", "arena.webp", "hero.webp", "maldred.webp"):
    CSS = CSS.replace(f"/app/static/{art_file}", inline_art(art_file))


st.markdown(CSS, unsafe_allow_html=True)


def init_state() -> None:
    defaults = {
        "screen": "map", "player": "Kate", "math_level": 1,
        "unlocked_castle": 0, "completed_castles": [], "active_castle": 0,
        "enemy_hp": 0, "hero_hp": 100, "spell_inventory": [], "challenge_spell": None,
        "challenge_questions": [], "challenge_index": 0, "challenge_attempt": 0,
        "challenge_started_at": 0.0, "challenge_elapsed": 0,
        "enemy_attack_start_at": 0.0, "enemy_attack_hits": 0,
        "defeat_started_at": 0.0,
        "challenge_feedback": "", "challenge_notice": "", "map_notice": "",
        "new_spell_highlight": None, "last_spell": None, "last_damage": 0,
        "adventure_over": False,
        "adventure_started_at": 0.0, "adventure_finished_at": 0.0,
        "run_math_level": 0, "run_player": "", "run_duration_seconds": 0,
        "run_score": 0, "leaderboard_recorded": False,
        "leaderboard_entries": [], "latest_run": None,
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
        "enemy_hp": 0, "hero_hp": 100, "spell_inventory": [], "challenge_spell": None,
        "challenge_questions": [], "challenge_index": 0, "challenge_attempt": 0,
        "challenge_started_at": 0.0, "challenge_elapsed": 0,
        "enemy_attack_start_at": 0.0, "enemy_attack_hits": 0,
        "defeat_started_at": 0.0,
        "challenge_feedback": "", "challenge_notice": "", "map_notice": "",
        "new_spell_highlight": None, "last_spell": None, "last_damage": 0,
        "adventure_over": False,
        "adventure_started_at": 0.0, "adventure_finished_at": 0.0,
        "run_math_level": int(level), "run_player": player,
        "run_duration_seconds": 0, "run_score": 0, "leaderboard_recorded": False,
    })


def enter_castle(index: int) -> None:
    now = time.time()
    if not S.get("adventure_started_at"):
        S["adventure_started_at"] = now
        S["run_math_level"] = int(S["math_level"])
        S["run_player"] = S["player"]
    S["active_castle"] = index
    S["enemy_hp"] = CASTLES[index]["hp"]
    S["enemy_attack_start_at"] = now + ATTACK_INTRO_SECONDS
    S["enemy_attack_hits"] = 0
    S["defeat_started_at"] = 0.0
    S["last_spell"] = None
    S["last_damage"] = 0
    S["new_spell_highlight"] = None
    S["challenge_notice"] = ""
    S["screen"] = "battle"


def format_duration(seconds: int) -> str:
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes}m {remainder:02d}s"


def record_completed_adventure() -> None:
    if S.get("leaderboard_recorded"):
        return
    finished_at = time.time()
    started_at = S.get("adventure_started_at") or finished_at
    duration = max(0, int(finished_at - started_at))
    level = int(S.get("run_math_level") or S["math_level"])
    health = max(0, min(100, int(S["hero_hp"])))
    # Difficulty rewards tackling harder math; remaining hearts and a quick clear
    # add bonuses. The speed bonus is one point per second under 30 minutes.
    score = level * 1000 + health * 50 + max(0, 1800 - duration)
    entry = {
        "player": S.get("run_player") or S["player"],
        "level": level,
        "difficulty": f"Level {level} · {MATH_LEVELS[level]['label']}",
        "ending_health": health,
        "duration_seconds": duration,
        "time": format_duration(duration),
        "score": score,
        "finished_at": finished_at,
    }
    entries = list(S.get("leaderboard_entries", []))
    entries.append(entry)
    S["leaderboard_entries"] = sorted(entries, key=lambda row: (row["score"], row["ending_health"], -row["duration_seconds"]), reverse=True)[:25]
    S["adventure_finished_at"] = finished_at
    S["run_duration_seconds"] = duration
    S["run_score"] = score
    S["leaderboard_recorded"] = True
    S["latest_run"] = entry


def update_enemy_attacks() -> None:
    if S["screen"] not in ("battle", "spell_challenge"):
        return
    if S["enemy_hp"] <= 0 or S.get("defeat_started_at"):
        return
    elapsed = time.time() - S.get("enemy_attack_start_at", 0.0)
    if elapsed < ATTACK_HIT_OFFSET_SECONDS:
        return
    hit_count = 1 + int((elapsed - ATTACK_HIT_OFFSET_SECONDS) // ATTACK_INTERVAL_SECONDS)
    missed_hits = hit_count - S.get("enemy_attack_hits", 0)
    if missed_hits > 0:
        S["hero_hp"] = max(0, S["hero_hp"] - missed_hits)
        S["enemy_attack_hits"] = hit_count


def begin_spell_challenge(spell_id: str) -> None:
    spell = SPELLS[spell_id]
    S["challenge_spell"] = spell_id
    S["challenge_questions"] = [make_problem(S["math_level"]) for _ in range(spell["questions"])]
    S["challenge_index"] = 0
    S["challenge_attempt"] = 0
    S["challenge_started_at"] = time.time()
    S["challenge_elapsed"] = 0
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
            S["challenge_notice"] = f"{SPELLS[spell_id]['emoji']} {SPELLS[spell_id]['name']} is ready! Tap the glowing spell beside your wizard to cast it."
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
    S["challenge_notice"] = ""
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
            S["adventure_finished_at"] = time.time()
            record_completed_adventure()
        S["defeat_started_at"] = time.time()
        S["screen"] = "battle"
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


def castle_marker(num: int, status: str, title: str) -> str:
    return f"""<div class='map-castle map-castle-{num - 1} {status}'>
      <div class='castle-number'>{num}</div><div class='castle-name'>{title}</div></div>"""


def island_map() -> str:
    castles = []
    for index, castle in enumerate(CASTLES):
        if index in S["completed_castles"]:
            status = "done"
        elif index == S["unlocked_castle"]:
            status = "open"
        else:
            status = "locked"
        castles.append(castle_marker(index + 1, status, castle["place"]))
    return "<div class='map-art' aria-label='Illustrated map of the Starwilds'>" + "".join(castles) + "</div>"


def render_hero(title: str, subtitle: str, eyebrow: str = "The Starwilds") -> None:
    st.markdown(f"<div class='hero'><div class='eyebrow'>{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></div>", unsafe_allow_html=True)


def render_home() -> None:
    render_hero("The Starwilds Wizard Quest", "Choose your wizard and math level. Then help save a magical island from Maldred!")
    left, right = st.columns([.9, 1.1], gap="large")
    with left:
        st.markdown("### Who is playing?")
        player = st.session_state.get("home_player", "Kate")
        pick_kate, pick_lola = st.columns(2, gap="small")
        with pick_kate:
            if st.button("🌸  Kate", key="home_kate", type="primary" if player == "Kate" else "secondary", use_container_width=True):
                st.session_state.home_player = "Kate"
                st.rerun()
        with pick_lola:
            if st.button("💙  Lola", key="home_lola", type="primary" if player == "Lola" else "secondary", use_container_width=True):
                st.session_state.home_player = "Lola"
                st.rerun()
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
    locked = bool(S.get("adventure_started_at"))
    player_col, level_col, progress_col = st.columns([1.05, 2, 1.05], vertical_alignment="center", gap="small")
    with player_col:
        selected_player = st.selectbox(
            "Choose your wizard",
            ["Kate", "Lola"],
            index=0 if S["player"] == "Kate" else 1,
            key="map_player_picker",
            disabled=locked,
        )
        S["player"] = selected_player
    with level_col:
        updated_level = st.select_slider(
            "Choose your math level",
            options=list(MATH_LEVELS),
            value=S["math_level"],
            key="map_level",
            format_func=str,
            disabled=locked,
        )
        S["math_level"] = int(updated_level)
    with progress_col:
        st.markdown(f"<span class='pill'>🏰 {len(S['completed_castles'])} / 5 cleared</span>", unsafe_allow_html=True)
    subtitle = "Choose a wizard and math level, then tap the glowing castle!" if not locked else "Tap the glowing castle and follow the golden trail!"
    st.markdown(f"<div class='map-topbar'><div><h1>🧙‍♀️ Wizard {S['player']}'s Island</h1><p>{subtitle}</p></div><div class='map-level'>{CASTLES[S['unlocked_castle']]['emoji']} Castle {S['unlocked_castle'] + 1} is ready</div></div>", unsafe_allow_html=True)
    if locked:
        st.caption(f"Wizard {S['run_player']} · Math Level {S['run_math_level']} · Hearts carry between castles")
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
        if st.button("📊 View the leaderboard", key="map_leaderboard", use_container_width=True):
            S["screen"] = "leaderboard"
            st.rerun()


def render_leaderboard() -> None:
    st.markdown(
        "<div class='leaderboard-hero'><div class='eyebrow'>THE STARWILDS · HALL OF HEROES</div><h1>🏆 Wizard Leaderboard</h1><p>Brave math, healthy hearts, and speedy spell-casting earn the most stars!</p></div>",
        unsafe_allow_html=True,
    )
    latest = S.get("latest_run")
    if latest:
        summary_cols = st.columns(4, gap="small")
        summary_values = [
            (f"🧙 {latest['player']}", "Wizard"),
            (latest["difficulty"], "Math difficulty"),
            (f"💚 {latest['ending_health']} / 100", "Hearts at the finish"),
            (latest["time"], "Adventure time"),
        ]
        for col, (value, label) in zip(summary_cols, summary_values):
            with col:
                st.markdown(f"<div class='leaderboard-summary'><span class='summary-value'>{value}</span><span class='summary-label'>{label}</span></div>", unsafe_allow_html=True)
        st.success(f"🌟 {latest['player']} finished with **{latest['score']:,} points**!")
    else:
        st.info("Finish all five castles to add your first score to the Hall of Heroes.")

    st.markdown("<div class='leaderboard-table-title'>✨ Top Starwilds Champions</div>", unsafe_allow_html=True)
    entries = S.get("leaderboard_entries", [])
    if entries:
        rows = [
            {
                "Rank": rank,
                "Name": entry["player"],
                "Difficulty": entry["difficulty"],
                "Ending health": f"{entry['ending_health']} / 100",
                "Time": entry["time"],
                "Score": entry["score"],
            }
            for rank, entry in enumerate(entries[:10], start=1)
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True, height=min(430, 48 + 36 * len(rows)))
    else:
        st.markdown("<div class='notice'>Your first completed adventure will appear here!</div>", unsafe_allow_html=True)
    st.caption("Score = math level × 1,000 + ending hearts × 50 + speed bonus (1 point for each second under 30 minutes).")
    if st.button("🔁 Start a new adventure", key="new_adventure", use_container_width=True):
        start_adventure(S["player"], int(S["math_level"]))
        st.rerun()


@st.fragment(run_every="1s")
def render_battle_scene() -> None:
    if S["screen"] != "battle":
        return
    update_enemy_attacks()
    index = S["active_castle"]
    castle = CASTLES[index]
    now = time.time()
    defeated = S["enemy_hp"] <= 0 and bool(S.get("defeat_started_at"))
    defeat_elapsed = now - S["defeat_started_at"] if defeated else 0
    enemy_ratio = max(0, S["enemy_hp"]) / castle["hp"]
    hurt = S["enemy_hp"] < castle["hp"]
    effect = SPELLS.get(S.get("last_spell") or "")
    effect_html = f"<div class='spell-projectile'>{effect['emoji']}</div><div class='spell-impact'>{effect['emoji']}</div><div class='boss-hurt'>−{S.get('last_damage', 0)}!</div>" if effect and hurt else ""
    warning_html = ""
    if not defeated and now < S.get("enemy_attack_start_at", 0):
        warning_html = f"<div class='battle-warning'>⚠️ Hurry! Answer math questions!<span>{castle['boss']} is starting to attack us!</span></div>"
    attack_html = "<div class='enemy-attack' aria-hidden='true'></div>" if not defeated and now >= S.get("enemy_attack_start_at", 0) else ""
    winner_html = ""
    if defeated and defeat_elapsed >= DEFEAT_ANIMATION_SECONDS:
        next_text = "Maldred is defeated and the Starwilds are safe!" if S["adventure_over"] else f"Castle {S['unlocked_castle'] + 1} is open. Keep your math magic going!"
        winner_html = f"<div class='battle-winner'><div style='font-size:2.4rem'>🏆 ✨ 🎉</div><h2>Winner!</h2><p>{next_text}</p></div>"
    arena_markup = (
        f"<div class='battle-arena'>"
        f"<div class='arena-caption'>{castle['emoji']} {castle['place']} · {castle['subtitle']}</div>"
        f"{warning_html}{attack_html}{winner_html}"
        f"<div class='duel'>"
        f"<div class='character player-character {'attacking' if hurt else ''}'><div class='head-health'><b>Wizard {S['player']} · {S['hero_hp']} HP</b><div class='health-track'><span class='health-fill' style='width:{S['hero_hp']}%'></span></div></div><div class='sprite hero-sprite' role='img' aria-label='Wizard {S['player']}'></div><div class='char-name'>Wizard {S['player']}</div></div>"
        f"{effect_html}"
        f"<div class='character boss {'hurt' if hurt else ''} {'defeated' if defeated else ''}'><div class='head-health'><b>{castle['boss']} · {S['enemy_hp']} HP</b><div class='health-track'><span class='health-fill' style='width:{enemy_ratio * 100:.1f}%'></span></div></div><div class='sprite boss-sprite boss-scale-{index + 1}' role='img' aria-label='{castle['boss']}'></div><div class='char-name'>{castle['boss']}</div></div>"
        f"</div></div>"
    )
    with st.container(key="battle_arena"):
        st.markdown(arena_markup, unsafe_allow_html=True)
        if not defeated:
            for inventory_index, spell_id in enumerate(S["spell_inventory"]):
                spell = SPELLS[spell_id]
                is_new = spell_id == S.get("new_spell_highlight")
                position_x = 49 + (inventory_index // 4) * 12
                position_y = 56 + (inventory_index % 4) * 12
                if is_new:
                    st.markdown(f"<style>.st-key-battle_arena .st-key-battle_spell_{inventory_index} button{{border:4px solid #fff!important;background:linear-gradient(145deg,#fff9ad,#ffbe42)!important;box-shadow:0 0 0 5px #ffe24c99,0 0 28px 12px #ffe24ccc!important;animation:new-spell-glow .9s ease-in-out infinite alternate}}</style>", unsafe_allow_html=True)
                st.markdown(f"<style>.st-key-battle_arena .st-key-battle_spell_{inventory_index}{{left:{position_x}%;top:{position_y}%}}</style>", unsafe_allow_html=True)
                label = f"🌟 READY!\n{spell['emoji']} {spell['name']}\n{spell['damage']} damage" if is_new else f"{spell['emoji']}\n{spell['name']}\n{spell['damage']} dmg"
                if st.button(label, key=f"battle_spell_{inventory_index}", help=f"Cast {spell['name']} for {spell['damage']} damage", use_container_width=True):
                    cast_spell(inventory_index)
                    st.rerun()
        elif defeat_elapsed >= DEFEAT_ANIMATION_SECONDS:
            button_label = "🏝️ Keep going to the island" if not S["adventure_over"] else "📊 See the leaderboard"
            if st.button(button_label, key="defeat_continue", use_container_width=True):
                S["screen"] = "map" if not S["adventure_over"] else "leaderboard"
                S["defeat_started_at"] = 0.0
                st.rerun()


def render_spell_choices() -> None:
    st.markdown("<div class='store-title'>🛍️ SPELL STORE</div>", unsafe_allow_html=True)
    st.markdown("<div class='store-caption'>Choose a spell and solve its questions to charge it.</div>", unsafe_allow_html=True)
    for spell_id, spell in SPELLS.items():
        st.markdown(
            f"<div class='spell-pick' style='border-left:6px solid {spell['color']}'><div class='spell-title'>{spell['emoji']} {spell['name']}</div><div class='spell-detail'>{spell['description']}</div><span class='spell-chip'>{spell['questions']} correct answers · {spell['damage']} damage</span></div>",
            unsafe_allow_html=True,
        )
        if st.button(f"Get · {spell['questions']} answers", key=f"get_spell_{spell_id}", use_container_width=True):
            begin_spell_challenge(spell_id)
            st.rerun()


def render_battle() -> None:
    castle = CASTLES[S["active_castle"]]
    is_defeated = S["enemy_hp"] <= 0 and bool(S.get("defeat_started_at"))
    title = f"{castle['boss']} is guarding {castle['subtitle']}!" if not is_defeated else f"{castle['boss']} has been defeated!"
    subtitle = "Earn a spell in the Store, then tap it beside your wizard to cast." if not is_defeated else "Watch the shadow wizard vanish, then head back to the island!"
    st.markdown(f"<div class='battle-heading'><div class='eyebrow'>WIZARD DUEL · CASTLE {S['active_castle'] + 1}</div><h1>{title}</h1><p>{subtitle}</p></div>", unsafe_allow_html=True)
    left, right = st.columns([.72, 2.85], gap="medium")
    with left:
        if is_defeated:
            st.markdown("<div class='store-title'>🏆 VICTORY!</div><div class='notice'>Great spell-casting! Your next castle is waiting on the island.</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='store-title'>✨ READY SPELLS</div>", unsafe_allow_html=True)
            if S.get("challenge_notice"):
                st.markdown(f"<div class='notice'>{S['challenge_notice']}</div>", unsafe_allow_html=True)
            if S["spell_inventory"]:
                for inventory_index, spell_id in enumerate(list(S["spell_inventory"])):
                    spell = SPELLS[spell_id]
                    is_new = spell_id == S.get("new_spell_highlight")
                    st.markdown(
                        f"<div class='spell-pick {'new-spell' if is_new else ''}' style='border:2px solid {spell['color']};background:{'#fff8d8' if is_new else '#fff'}'><div class='spell-title'>{'🌟 NEW! ' if is_new else ''}{spell['emoji']} {spell['name']}</div><div class='spell-detail'>{spell['questions']} questions · {spell['damage']} damage</div><div class='spell-detail'><b>Tap the glowing spell beside your wizard to use it!</b></div></div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown("<div class='notice'>Earn a spell, and it will appear beside your wizard in the battle room.</div>", unsafe_allow_html=True)
            render_spell_choices()
    with right:
        render_battle_scene()


@st.fragment(run_every="1s")
def render_spell_challenge() -> None:
    if S["screen"] != "spell_challenge":
        return
    update_enemy_attacks()
    spell_id = S["challenge_spell"]
    spell = SPELLS[spell_id]
    total = spell["questions"]
    index = S["challenge_index"]
    problem = S["challenge_questions"][index]
    st.markdown(f"<div class='challenge-heading'><div class='eyebrow'>THE WIZARD IS ATTACKING!</div><h1>Power up {spell['name']}!</h1><p>Answer quickly! Each shadow bolt hit takes 1 heart.</p></div>", unsafe_allow_html=True)
    hp = max(0, S["hero_hp"])
    st.markdown(f"<div class='pressure-banner'><div class='pressure-label'>🟣 {CASTLES[S['active_castle']]['boss']} is casting a shadow bolt!</div><div class='attack-flash'></div><div class='pressure-hero'></div><div class='pressure-bolt'>🟣</div><div class='pressure-boss'></div><div class='pressure-health'>Wizard {S['player']} · {hp} HP<div class='health-track'><span class='health-fill' style='width:{hp}%'></span></div></div></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='challenge-card' style='border-top:7px solid {spell['color']}'><div style='font-size:2.4rem'>{spell['emoji']}</div><h2>{spell['name']}</h2><p>{spell['description']}</p><span class='pill'>{spell['questions']} correct answers</span><span class='pill'>{spell['damage']} damage</span></div>", unsafe_allow_html=True)
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
    with st.container(key="challenge_answers"):
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
        # The island map is now the opening screen; retain compatibility with
        # sessions that were sitting on the older start page during deployment.
        S["screen"] = "map"
    if S["screen"] == "map":
        render_map()
    elif S["screen"] == "battle":
        render_battle()
    elif S["screen"] == "spell_challenge":
        render_spell_challenge()
    elif S["screen"] == "leaderboard":
        render_leaderboard()
    else:
        S["screen"] = "map"
        st.rerun()


render_app()
