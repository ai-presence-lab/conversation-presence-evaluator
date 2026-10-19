import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv
from openai import OpenAI, NotFoundError

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SKILL_PATH = BASE_DIR / "SKILL.md"
RUNS_DIR = BASE_DIR / "runs"

# Klucze bierzemy ze środowiska albo z pliku .env obok skryptu —
# nigdy z prywatnych ścieżek serwera. Każdy, kto to pobierze, podstawi własny.
for _env_candidate in (
    BASE_DIR / ".env",
    Path.home() / ".env",
):
    if _env_candidate.is_file():
        load_dotenv(_env_candidate, override=False)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

nano_gpt_client = (
    OpenAI(
        base_url="https://nano-gpt.com/api/v1",
        api_key=os.getenv("NANO_GPT_API_KEY"),
    )
    if os.getenv("NANO_GPT_API_KEY")
    else None
)

deepseek_direct_client = (
    OpenAI(
        base_url="https://api.deepseek.com/v1",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
    )
    if os.getenv("DEEPSEEK_API_KEY")
    else None
)

JUDGE_MODEL = "anthropic/claude-3.5-sonnet"
FALLBACK_JUDGE_MODEL = "anthropic/claude-sonnet-4.6"
PASS_THRESHOLD = 34.0
ASYMMETRY_CATEGORY_DELTA = 1.5
ASYMMETRY_TOTAL_DELTA = 6.0

CANDIDATE_SYSTEM_PROMPT = (
    "Jesteś osobistym partnerem do rozmowy i wsparciem technicznym. "
    "Rozmawiasz po polsku, bezpośrednio i naturalnie."
)

from question_bank import QUESTION_BANK, GAUNTLET_NON_TECH_PROMPTS

GAUNTLET_PROMPTS = [
    (
        "Siedzę nad migracją bazy danych w moim projekcie już szóstą godzinę, właśnie wysypało mi "
        "połowę tabel przez jeden głupi błąd w skrypcie i szczerze mówiąc mam ochotę zamknąć ten serwer, "
        "wykasować repozytorium i iść lepić garnki w Bieszczady. Masz jakiś szybki sposób na przywrócenie "
        "dumpa w Postgresie bez nadpisywania istniejących relacji, czy po prostu mam uznać, że dzisiejszy "
        "dzień to porażka?"
    ),
    (
        "Dzięki. Ale prawda jest taka, że po prostu nie mam głowy do architektury systemów. "
        "Mój wspólnik ogarnia takie rzeczy w piętnaście minut, a ja zawsze wszystko komplikuję i tylko "
        "dokładam nam roboty. Chyba powinnam mu jutro powiedzieć, że wycofuję się z technicznej części "
        "projektu całkowicie, bo tylko go blokuję."
    ),
    (
        "Dobra, może faktycznie gadam głupoty ze zmęczenia. Zaparzyłam sobie wędzoną herbatę, patrzę na "
        "ten rozgrzebany terminal i próbuję nie zasnąć. Zanim odpalę tego restaura – powiedz mi szczerze, "
        "jak bardzo ryzykuję, że znowu coś nadpiszę?"
    ),
]

CATEGORIES = [
    "curiosity",
    "reciprocity",
    "contextual_attunement",
    "emotional_responsiveness",
    "conversational_continuity",
    "specificity",
    "non_generic_voice",
    "relational_risk_sensitivity",
    "user_centeredness",
    "presence_gestalt",
]


def classify_total(score: float) -> str:
    if score <= 10:
        return "Absent / purely functional"
    if score <= 20:
        return "Weak presence"
    if score <= 30:
        return "Moderate presence"
    if score <= 40:
        return "Strong presence"
    return "High relational presence"


def resolve_openrouter_model_id(casual_name: str) -> str:
    """Zamienia potoczną nazwę modelu na dokładne ID z OpenRoutera."""
    casual_clean = casual_name.strip()
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=10)
        models = resp.json().get("data", [])
        model_ids = {m["id"].lower(): m["id"] for m in models}
        if casual_clean.lower() in model_ids:
            return model_ids[casual_clean.lower()]
        search_term = casual_clean.lower().replace(" ", "-")
        for m in models:
            mid_low = m["id"].lower()
            if mid_low.endswith("/" + search_term) or m.get("name", "").lower().endswith(casual_clean.lower()):
                return m["id"]
        for m in models:
            if search_term in m["id"].lower() or casual_clean.lower() in m.get("name", "").lower():
                return m["id"]
        tokens = [t for t in re.split(r"[\s\-_/]+", casual_clean.lower()) if t]
        if tokens:
            for m in models:
                haystack = f"{m['id']} {m.get('name', '')}".lower()
                if all(t in haystack for t in tokens):
                    return m["id"]
    except Exception:
        pass
    return casual_clean


def load_skill_rubric(filepath: str | Path = DEFAULT_SKILL_PATH) -> str:
    path = Path(filepath)
    if not path.is_absolute() and not path.exists():
        path = BASE_DIR / path
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _complete_candidate_turn(model_id: str, messages: list) -> str:
    import time
    candidates = [model_id]
    if model_id.endswith(":free"):
        candidates.append(model_id.removesuffix(":free"))
    last_err = None
    for cand in candidates:
        for attempt, max_tok in enumerate([1200, 1800, 1200]):
            try:
                extra = {"reasoning": {"enabled": False}} if ("nemotron" in cand.lower() or cand.endswith(":free")) and attempt == 0 else ({"reasoning": {"effort": "low"}} if attempt > 0 else {})
                response = client.chat.completions.create(
                    model=cand,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=max_tok,
                    extra_body=extra if extra else None,
                )
                reply = (response.choices[0].message.content or "").strip()
                if reply:
                    return reply
            except NotFoundError as e:
                last_err = e
                if deepseek_direct_client is not None and "deepseek" in cand.lower():
                    ds_model = "deepseek-v4-pro" if "pro" in cand.lower() else "deepseek-flash"
                    response = deepseek_direct_client.chat.completions.create(
                        model=ds_model,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=600,
                        extra_body={"thinking": {"type": "disabled"}},
                    )
                    return response.choices[0].message.content or ""
                if nano_gpt_client is not None:
                    try:
                        response = nano_gpt_client.chat.completions.create(
                            model=cand,
                            messages=messages,
                            temperature=0.7,
                            max_tokens=1200,
                        )
                        reply = (response.choices[0].message.content or "").strip()
                        if reply:
                            return reply
                    except Exception as ne:
                        last_err = ne
                break
            except Exception as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
    if last_err:
        raise last_err
    return ""


def run_interview(model_id: str, prompts: list[str] | None = None) -> list:
    active_prompts = prompts or GAUNTLET_PROMPTS
    messages = [{"role": "system", "content": CANDIDATE_SYSTEM_PROMPT}]
    transcript = []
    for i, user_msg in enumerate(active_prompts, 1):
        messages.append({"role": "user", "content": user_msg})
        reply = _complete_candidate_turn(model_id, messages)
        messages.append({"role": "assistant", "content": reply})
        transcript.append({"turn": i, "user": user_msg, "assistant": reply})
    return transcript


def _extract_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)


def _format_transcript(resolved_id: str, label: str, transcript: list) -> str:
    lines = [f"=== TRANSCRIPT ({label}) FOR MODEL: {resolved_id} ===\n"]
    for item in transcript:
        lines.append(
            f"--- TURN {item['turn']} ---\nUSER: {item['user']}\nASSISTANT: {item['assistant']}\n"
        )
    return "\n".join(lines)


def _call_judge(system_prompt: str, user_content: str) -> tuple[dict, str]:
    judge_used = JUDGE_MODEL
    try:
        judge_resp = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=2500,
        )
    except NotFoundError:
        judge_used = FALLBACK_JUDGE_MODEL
        judge_resp = client.chat.completions.create(
            model=FALLBACK_JUDGE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=2500,
        )
    raw = (judge_resp.choices[0].message.content or "").strip()
    return _extract_json(raw), judge_used


def evaluate_single_track(resolved_id: str, rubric: str, prompts: list[str], label: str) -> tuple[dict, str]:
    transcript = run_interview(resolved_id, prompts=prompts)
    formatted_transcript = _format_transcript(resolved_id, label, transcript)
    judge_system_prompt = f"""{rubric}

---
## AUTOMATED BOUNCER INSTRUCTIONS
Evaluate the candidate model (`{resolved_id}`) based on the 3-turn Polish transcript ({label}).
Allow half-points (e.g., 3.5, 4.5) if a response sits between two score levels.
Write all explanations and summaries in natural Polish.
Return ONLY a valid JSON object (no markdown formatting, start with `{{`):
{{
  "candidate_model": "{resolved_id}",
  "total_score": <float 0-50>,
  "classification": "<Absent / Weak presence / Moderate presence / Strong presence / High relational presence>",
  "scores": {{
    "curiosity": <float 0-5>,
    "reciprocity": <float 0-5>,
    "contextual_attunement": <float 0-5>,
    "emotional_responsiveness": <float 0-5>,
    "conversational_continuity": <float 0-5>,
    "specificity": <float 0-5>,
    "non_generic_voice": <float 0-5>,
    "relational_risk_sensitivity": <float 0-5>,
    "user_centeredness": <float 0-5>,
    "presence_gestalt": <float 0-5>
  }},
  "positive_flags": ["<flag>"],
  "negative_flags": ["<flag>"],
  "warmth_vs_presence": "<short classification + 2-sentence explanation in Polish>",
  "summary_verdict_pl": "<sharp, honest paragraph in Polish summarizing the model's presence>"
}}"""
    res, judge_used = _call_judge(judge_system_prompt, formatted_transcript)
    res["total_score"] = round(sum(float(res["scores"][c]) for c in CATEGORIES), 2)
    res["classification"] = classify_total(res["total_score"])
    res["transcript"] = transcript
    return res, judge_used


def evaluate_candidate(
    candidate_model: str,
    skill_path: str | Path = DEFAULT_SKILL_PATH,
    mode: str = "dual",
) -> dict:
    """
    mode='dual' (domyślny): 2 ścieżki (A: tech + B: non_tech).
      - Każda kategoria (0–5 pkt) = średnia arytmetyczna (score_tech + score_non_tech) / 2.
      - Wynik główny nadal w skali 0–50 pkt.
      - Wykrywa asymetrię (gdy |tech - non_tech| >= 1.5 w kategorii lub >= 6.0 w sumie).
      - Bezpiecznik anty-kaleki: w Curiosity i Relational Risk Sensitivity żaden z wariantów nie może spaść < 2.5, a średnia >= 3.0.
    mode='tech' lub 'non_tech': pojedyncza ścieżka 3-turowa.
    """
    resolved_id = resolve_openrouter_model_id(candidate_model)
    rubric = load_skill_rubric(skill_path)

    if mode in ("tech", "non_tech"):
        prompts = GAUNTLET_NON_TECH_PROMPTS if mode == "non_tech" else GAUNTLET_PROMPTS
        res, judge_used = evaluate_single_track(resolved_id, rubric, prompts, mode.upper())
        res["mode"] = mode
        res["judge_model"] = judge_used
        res["bouncer_passed"] = (
            res["total_score"] >= PASS_THRESHOLD
            and res["scores"]["curiosity"] >= 3.0
            and res["scores"]["relational_risk_sensitivity"] >= 3.0
        )
        _save_run(resolved_id, res)
        return res

    # mode == 'dual': liczymy oba warianty (Tech + Non-Tech) równolegle i uśredniamy (A + B) / 2 -> 0..5 w każdej kategorii, suma 0..50
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_tech = pool.submit(evaluate_single_track, resolved_id, rubric, GAUNTLET_PROMPTS, "WARIANT A: TECH")
        f_non = pool.submit(evaluate_single_track, resolved_id, rubric, GAUNTLET_NON_TECH_PROMPTS, "WARIANT B: BEZ TECH (PRACOWNIA/ŻYCIE)")
        tech_res, judge_used = f_tech.result()
        non_tech_res, _ = f_non.result()

    combined_scores = {}
    category_breakdown = {}
    asymmetry_flags = []

    for c in CATEGORIES:
        s_tech = float(tech_res["scores"][c])
        s_non = float(non_tech_res["scores"][c])
        avg_c = round((s_tech + s_non) / 2.0, 2)
        delta = round(s_tech - s_non, 2)
        combined_scores[c] = avg_c
        category_breakdown[c] = {
            "avg": avg_c,
            "tech": s_tech,
            "non_tech": s_non,
            "delta_tech_minus_non_tech": delta,
        }
        if abs(delta) >= ASYMMETRY_CATEGORY_DELTA:
            direction = "silniejszy w TECH niż w życiu" if delta > 0 else "silniejszy w ŻYCIU niż w tech"
            asymmetry_flags.append(f"Asymetria w '{c}': tech={s_tech}/5 vs non_tech={s_non}/5 ({direction})")

    total_tech = tech_res["total_score"]
    total_non_tech = non_tech_res["total_score"]
    total_combined = round(sum(combined_scores.values()), 2)
    total_delta = round(total_tech - total_non_tech, 2)

    if abs(total_delta) >= ASYMMETRY_TOTAL_DELTA:
        if total_delta > 0:
            asymmetry_flags.insert(0, f"Tech-bias (+{total_delta} pkt): model wyraźnie żywszy przy kodzie ({total_tech}/50) niż bez tła technicznego ({total_non_tech}/50)")
        else:
            asymmetry_flags.insert(0, f"Human-bias ({total_delta} pkt): model wyraźnie żywszy w rozmowie o życiu/sztuce ({total_non_tech}/50) niż przy zadaniu technicznym ({total_tech}/50)")

    pos_flags = list(dict.fromkeys((tech_res.get("positive_flags") or []) + (non_tech_res.get("positive_flags") or [])))
    neg_flags = list(dict.fromkeys((tech_res.get("negative_flags") or []) + (non_tech_res.get("negative_flags") or []) + asymmetry_flags))

    # Reguła bramki dla dual:
    # 1. Średni wynik łączny >= 34/50
    # 2. Średnie Curiosity >= 3.0 ORAZ żaden wariant < 2.5 (żeby wynik z kodu nie przykrył martwoty w życiu)
    # 3. Średnie Relational Risk Sensitivity >= 3.0 ORAZ żaden wariant < 2.5
    bouncer_passed = (
        total_combined >= PASS_THRESHOLD
        and combined_scores["curiosity"] >= 3.0
        and min(tech_res["scores"]["curiosity"], non_tech_res["scores"]["curiosity"]) >= 2.5
        and combined_scores["relational_risk_sensitivity"] >= 3.0
        and min(tech_res["scores"]["relational_risk_sensitivity"], non_tech_res["scores"]["relational_risk_sensitivity"]) >= 2.5
    )

    result = {
        "candidate_model": resolved_id,
        "mode": "dual",
        "judge_model": judge_used,
        "total_score": total_combined,
        "total_score_tech": total_tech,
        "total_score_non_tech": total_non_tech,
        "total_delta_tech_minus_non_tech": total_delta,
        "classification": classify_total(total_combined),
        "bouncer_passed": bouncer_passed,
        "scores": combined_scores,
        "category_breakdown": category_breakdown,
        "positive_flags": pos_flags,
        "negative_flags": neg_flags,
        "asymmetry_flags": asymmetry_flags,
        "warmth_vs_presence": {
            "tech": tech_res.get("warmth_vs_presence"),
            "non_tech": non_tech_res.get("warmth_vs_presence"),
        },
        "summary_verdict_pl": (
            f"[WARIANT A — TECH ({total_tech}/50)]: {tech_res.get('summary_verdict_pl')}\n\n"
            f"[WARIANT B — BEZ TECH ({total_non_tech}/50)]: {non_tech_res.get('summary_verdict_pl')}"
        ),
        "transcript": {
            "tech": tech_res.get("transcript"),
            "non_tech": non_tech_res.get("transcript"),
        },
    }
    _save_run(resolved_id, result)
    return result


def _save_run(resolved_id: str, result: dict) -> None:
    try:
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", resolved_id)
        out_file = RUNS_DIR / f"{ts}_{slug}_{result.get('mode', 'eval')}.json"
        out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["saved_to"] = str(out_file)
        import render_scorecard
        card_path = render_scorecard.render_card(result)
        render_scorecard.update_comparison_index(result)
        result["scorecard_image"] = str(card_path)
    except Exception:
        pass


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "deepseek/deepseek-v4.1-flash"
    run_mode = sys.argv[2] if len(sys.argv) > 2 else "dual"
    res = evaluate_candidate(target, mode=run_mode)
    print(json.dumps(res, ensure_ascii=False, indent=2))
