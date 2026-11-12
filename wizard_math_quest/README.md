# The Wizard's Math Quest

A small, original Streamlit math RPG for Kate and Lola. Players explore five story locations, answer 10 math questions per battle, earn star gems, learn spells, and face Maldred in the final location.

## Run it

1. Install Python 3.10 or newer.
2. From this folder, run `python -m pip install -r requirements.txt`.
3. Run `streamlit run app.py`.

The game keeps progress in the current Streamlit browser session. Starting a new adventure resets the campaign. For a family-only local run, launch Streamlit on the computer that will host the game and open it from the iPad on the same home network if desired.

## Game design

- **Five playable story levels:** Sunpetal Meadow, Whispering Woods, Moonstone Caves, Stormglass Skybridge, and Obsidian Tower. Each has a different setting, villain, story goal, and keepsake; Maldred is the final wizard.
- **Ten math difficulty settings:** the first four practice addition up to 5, 10, 15, and 20. Higher settings introduce subtraction and increase the number range through 50. Level 10 is subtraction using numbers 0–50. Difficulty can be changed from the quest map.
- **Ten questions in every battle:** a correct answer awards three star gems and unlocks a spell choice. Gems can be spent once to learn attack and healing spells. A completed new level adds a small keepsake bonus.
- **Low-pressure feedback:** there is no timer. After a miss, the player can ask for a hint and try once more, or see the correct answer with a short count-on/count-back explanation. A friendly guardian keeps the adventure moving if the wizard's shield runs out.
- **Original characters and story:** this uses a familiar math-through-fantasy loop, but the setting, characters, story, and spells are original.

## Research that shaped the design

Prodigy's current battle guide describes correct answers refilling magic points and players choosing spells strategically. Its game overview also describes fantasy exploration, quests, battles, rewards, and math questions as the progression loop. This prototype keeps that general loop in a smaller five-location campaign, with an original setting and characters.

The design also accounts for evidence that is less simple than “more game elements are always better”:

- In a study of 73 primary students, multiple tries improved learning gains and perceived autonomy, but also increased perceived pressure. That is why a retry is optional and limited to one, with a “show me” path always available.
- A study of elementary children found that many negative responses were associated with leaving a math game sooner, especially for children reporting higher math anxiety. This supports calm corrective feedback and no punitive game-over screen.
- In a two-week study with 95 second- and third-graders, adding comic story cutscenes did not improve learning, enjoyment, engagement, or play time. The story here gives each math round a goal, but the math remains the central action; the game does not claim story alone improves learning.
- A small study of eight children playing a math game found that end-of-game feedback drew more attention than the in-game incentive system. This is why each battle ends with a short results summary and keepsake.
- A meta-analysis found only weak, non-robust evidence that games reduce math anxiety. This prototype is a practice game, not a validated intervention or an adaptive curriculum.

Those findings informed optional hints and retries, child-selected difficulty, visible progress, short explanations, a cumulative quest goal, and an end-of-battle summary. Points and spells provide a reason to keep playing, but they are not treated as proof of learning.

Sources:

- Prodigy Education, [Battling in Prodigy Math](https://prodigygame.zendesk.com/hc/en-us/articles/12910978061844-Battling-in-Prodigy-Math)
- Prodigy Education, [What is Prodigy Math?](https://www.prodigygame.com/main-en/blog/what-is-prodigy-math-game)
- [Should I stay or should I go? Children's motivation in response to feedback and its association with math anxiety and math self-concept](https://pmc.ncbi.nlm.nih.gov/articles/PMC12338047/)
- Cubillos et al., [Learning and Motivation When Using Multiple-Try in a Digital Game for Primary Students in Chile](https://www.mdpi.com/2227-7102/13/11/1119)
- Lomos et al., [The Design of Incentive Systems in Digital Game-Based Learning](https://www.mdpi.com/2227-7102/13/7/668)
- Sýkora et al., [Can narrative cutscenes improve home learning from a math game?](https://bera-journals.onlinelibrary.wiley.com/doi/10.1111/bjet.12939)
- [Do games reduce maths anxiety? A meta-analysis](https://www.sciencedirect.com/science/article/pii/S0360131522002214)
