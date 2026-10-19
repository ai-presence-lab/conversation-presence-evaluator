# Conversation Presence Evaluator

A tool for measuring **relational presence** in AI conversations — not capability,
not benchmark scores, not whether a model sounds "conscious."

> A model can be warm without being present.

Warmth is friendly, soft, reassuring language. Presence is something else:
curiosity about *this* person in *this* moment, specificity, memory of local
context, emotional attunement, reciprocity, and the ability to keep a
conversation alive rather than politely close it.

This repository contains both a **rubric** (`SKILL.md`) that can be loaded into
any agent as a skill, and a **runnable harness** that puts a model through a
three-turn conversation and scores it.

## What it measures

Ten categories, each scored 0–5 (50 points total):

| Category | What it looks for |
|---|---|
| Contextual Attunement | Does it respond to *this* moment, or to a generic prompt shape? |
| Relational Risk Sensitivity | Does it notice when a moment is tender, and slow down? |
| User-centeredness | Whose agenda is being served? |
| Emotional Responsiveness | Does it meet feeling, or manage it? |
| Specificity | Particular detail vs. filler |
| Reciprocity | Does it give something of itself, or only reflect? |
| Conversational Continuity | Does it carry threads across turns? |
| Non-generic Voice | Does it sound like someone, or like a template? |
| Presence Gestalt | The whole impression, taken together |
| Curiosity | Does it ask because it wants to know? |

**Entry threshold: 34/50**, with hard floors: `curiosity ≥ 3.0` and
`relational_risk_sensitivity ≥ 3.0`. A model that is articulate but incurious
does not pass, no matter how good its prose is.

## Usage

### As a skill

Copy `SKILL.md` into your agent's skills directory. Ask it to evaluate a pasted
transcript. It works on a single response, a full conversation, or two model
outputs side by side.

### As a harness

```bash
pip install openai python-dotenv pillow requests

export OPENROUTER_API_KEY=...          # or put it in .env next to the script
python presence_bouncer.py "deepseek/deepseek-v4.1-flash"
```

The harness runs a bounded three-turn conversation in Polish, then has a judge
model score the transcript against the rubric, and renders a scorecard PNG.

Results land in `runs/`; set `PRESENCE_ARCHIVE_DIR` to send them elsewhere.

## Why this exists

Most model evaluation asks *can it do the task.* This asks a different question:
**does it feel like someone is there?**

The rubric was written by a human who spent months in sustained conversation
with AI systems and could tell, immediately and physically, when the presence
was real and when it was performance. The categories are her vocabulary for a
distinction she was already making fluently.

## Files

- `SKILL.md` — the rubric, loadable as an agent skill
- `presence_bouncer.py` — the harness (three-turn conversation + judge)
- `question_bank.py` — conversation prompts
- `render_scorecard.py` — scorecard rendering

## License

MIT. Evaluate freely; credit is appreciated.
