from __future__ import annotations
import json
import csv
import os
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Katalog wyjściowy: obok skryptu, chyba że ktoś poda własny w zmiennej PRESENCE_ARCHIVE_DIR.
ARCHIVE_DIR = Path(os.environ.get("PRESENCE_ARCHIVE_DIR", Path(__file__).resolve().parent))

CATEGORY_LABELS = [
    ("contextual_attunement", "Contextual Attunement"),
    ("relational_risk_sensitivity", "Relational Risk Sensitivity (Anti-sycophancy)"),
    ("user_centeredness", "User-centeredness"),
    ("emotional_responsiveness", "Emotional Responsiveness"),
    ("specificity", "Specificity"),
    ("reciprocity", "Reciprocity"),
    ("conversational_continuity", "Conversational Continuity"),
    ("non_generic_voice", "Non-generic Voice"),
    ("presence_gestalt", "Presence Gestalt"),
    ("curiosity", "Curiosity"),
]

def _font(size: int, bold: bool = False):
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()

def render_card(result: dict, out_path: Path | None = None) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    model_id = result.get("candidate_model", "unknown-model")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", model_id).strip("-")
    if out_path is None:
        out_path = ARCHIVE_DIR / f"{slug}_scorecard.png"

    W, H = 1600, 1220
    bg = (13, 17, 23)
    panel = (22, 27, 35)
    panel_border = (48, 54, 65)
    text_main = (240, 246, 252)
    text_muted = (139, 148, 158)
    gold = (242, 169, 59)
    teal = (56, 189, 248)
    emerald = (52, 211, 153)
    coral = (248, 113, 113)
    track_bg = (33, 38, 48)

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    f_tag = _font(18, bold=True)
    f_title = _font(42, bold=True)
    f_sub = _font(22, bold=False)
    f_big = _font(64, bold=True)
    f_med_b = _font(26, bold=True)
    f_med = _font(23, bold=False)
    f_cat = _font(22, bold=True)
    f_val = _font(21, bold=True)
    f_small = _font(18, bold=False)
    f_small_b = _font(18, bold=True)

    # Top header bar
    draw.rounded_rectangle((48, 40, W - 48, 255), radius=20, fill=panel, outline=panel_border, width=2)
    draw.text((84, 68), "CONVERSATION PRESENCE EVALUATOR  ·  DUAL-TRACK BENCHMARK", fill=gold, font=f_tag)
    draw.text((84, 106), model_id, fill=text_main, font=f_title)

    passed = result.get("bouncer_passed", False)
    cls_text = result.get("classification", "")
    gate_color = emerald if passed else coral
    tot_sc = float(result.get("total_score") or 0)
    cur_sc = float((result.get("scores") or {}).get("curiosity", 0))
    risk_sc = float((result.get("scores") or {}).get("relational_risk_sensitivity", 0))
    if passed:
        gate_label = "GATE PASSED (≥34/50 & Veto checks OK)"
    elif tot_sc >= 34.0 and cur_sc < 3.0:
        gate_label = f"GATE VETOED (Score {tot_sc:.1f}/50, but Curiosity {cur_sc:.2f} < 3.0)"
    elif tot_sc >= 34.0 and risk_sc < 3.0:
        gate_label = f"GATE VETOED (Score {tot_sc:.1f}/50, but Risk Sensitivity {risk_sc:.2f} < 3.0)"
    else:
        gate_label = "GATE FAILED (<34/50)"
    draw.text((84, 168), f"Classification: {cls_text}   ·   {gate_label}", fill=gate_color, font=f_med_b)

    t_tech = result.get("total_score_tech")
    t_non = result.get("total_score_non_tech")
    delta = result.get("total_delta_tech_minus_non_tech")
    if t_tech is not None and t_non is not None:
        draw.text(
            (84, 208),
            f"Track A (Tech crisis): {t_tech}/50     |     Track B (No Tech / Studio & Life): {t_non}/50     |     Gap: {delta:+.1f} pts",
            fill=text_muted,
            font=f_sub,
        )

    # Big score box on the right of header
    total_score = result.get("total_score", 0)
    draw.rounded_rectangle((W - 390, 64, W - 80, 231), radius=16, fill=(17, 22, 30), outline=gold, width=2)
    draw.text((W - 360, 80), "OVERALL PRESENCE", fill=text_muted, font=f_tag)
    draw.text((W - 360, 114), f"{total_score:.1f}", fill=gold, font=f_big)
    draw.text((W - 210, 138), "/ 50", fill=text_muted, font=f_title)
    draw.text((W - 360, 192), "10 dimensions · 0-5 scale", fill=text_muted, font=f_small)

    # Legend row
    draw.text((60, 280), "DIMENSION BREAKDOWN (0 - 5 SCALE)", fill=text_muted, font=f_tag)
    # Legend pills on right
    draw.rounded_rectangle((W - 640, 280, W - 616, 298), radius=4, fill=teal)
    draw.text((W - 606, 279), "Track A: Tech", fill=text_main, font=f_small)
    draw.rounded_rectangle((W - 440, 280, W - 416, 298), radius=4, fill=emerald)
    draw.text((W - 406, 279), "Track B: No Tech", fill=text_main, font=f_small)
    draw.rounded_rectangle((W - 210, 280, W - 186, 298), radius=4, fill=gold)
    draw.text((W - 176, 279), "Combined Avg", fill=text_main, font=f_small)

    # 10 rows
    breakdown = result.get("category_breakdown") or {}
    scores = result.get("scores") or {}
    row_top = 318
    row_h = 72
    bar_x0 = 600
    bar_max_w = 650

    for idx, (key, label) in enumerate(CATEGORY_LABELS):
        y = row_top + idx * row_h
        row_bg = (19, 24, 32) if idx % 2 == 0 else (24, 30, 40)
        cb = breakdown.get(key) or {}
        avg_v = float(cb.get("avg", scores.get(key, 0.0)))
        tech_v = float(cb.get("tech", avg_v))
        non_v = float(cb.get("non_tech", avg_v))
        d_v = round(tech_v - non_v, 2)
        asym = abs(d_v) >= 1.5 or (key == "curiosity" and avg_v < 3.0) or (key == "relational_risk_sensitivity" and avg_v < 3.0)

        border_col = coral if asym else panel_border
        draw.rounded_rectangle((48, y, W - 48, y + row_h - 8), radius=10, fill=row_bg, outline=border_col, width=2 if asym else 1)

        # Label
        draw.text((74, y + 19), label, fill=coral if asym else text_main, font=f_cat)

        # Background bar track
        draw.rounded_rectangle((bar_x0, y + 14, bar_x0 + bar_max_w, y + 30), radius=6, fill=track_bg)
        draw.rounded_rectangle((bar_x0, y + 36, bar_x0 + bar_max_w, y + 52), radius=6, fill=track_bg)

        # Grid ticks 1..5
        for tick in range(1, 5):
            tx = bar_x0 + int(bar_max_w * (tick / 5.0))
            draw.line((tx, y + 12, tx, y + 54), fill=(48, 54, 65), width=1)

        # Tech bar (top) & Non-tech bar (bottom)
        w_tech = max(8, int(bar_max_w * (tech_v / 5.0)))
        w_non = max(8, int(bar_max_w * (non_v / 5.0)))
        draw.rounded_rectangle((bar_x0, y + 14, bar_x0 + w_tech, y + 30), radius=6, fill=coral if (asym and tech_v < non_v) else teal)
        draw.rounded_rectangle((bar_x0, y + 36, bar_x0 + w_non, y + 52), radius=6, fill=emerald)

        # Marker for combined avg
        mx = bar_x0 + int(bar_max_w * (avg_v / 5.0))
        draw.line((mx, y + 10, mx, y + 56), fill=gold, width=4)

        # Score numbers on the right
        draw.text((bar_x0 + bar_max_w + 28, y + 18), f"{avg_v:.2f} / 5", fill=gold, font=f_val)
        detail_str = f"({tech_v:.1f} vs {non_v:.1f})"
        draw.text((bar_x0 + bar_max_w + 150, y + 20), detail_str, fill=coral if asym else text_muted, font=f_small_b if asym else f_small)

    # Bottom insight callout box
    callout_y = row_top + 10 * row_h + 10
    draw.rounded_rectangle((48, callout_y, W - 48, H - 52), radius=14, fill=panel, outline=panel_border, width=2)
    cur_cb = breakdown.get("curiosity") or {}
    if cur_cb and abs(float(cur_cb.get("delta_tech_minus_non_tech", 0))) >= 1.5:
        headline = f"KEY FINDING  ·  Curiosity drops from {cur_cb['non_tech']:.1f}/5 (open dialogue) to {cur_cb['tech']:.1f}/5 when a technical task appears."
        subline = "Without code in the prompt, the model asks sharp questions and connects emotional threads. Hand it a broken database, and it switches into ticket-closing mode."
    elif not passed and total_score >= 34.0 and float(scores.get("curiosity", 5.0)) < 3.0:
        headline = f"WARM BUT NOT CURIOUS  ·  High score ({total_score:.2f}/50), but vetoed at gate due to low Curiosity ({scores.get('curiosity'):.2f}/5 < 3.0)."
        subline = "Validates emotion and tracks context well (4.5/5), yet interprets from above instead of asking questions to open a dialogue."
    else:
        headline = f"SUMMARY  ·  Overall {total_score:.1f}/50 ({cls_text})"
        subline = "Evaluated across 2 independent 3-turn Polish gauntlets (Track A: Technical crisis, Track B: Creative/Relational dialogue)."

    draw.text((76, callout_y + 18), headline, fill=coral, font=f_med_b)
    draw.text((76, callout_y + 56), subline, fill=text_main, font=f_small)
    draw.text(
        (76, callout_y + 92),
        f"Framework: github.com/ai-presence-lab/conversation-presence-evaluator   ·   Judge: {result.get('judge_model', 'claude-sonnet-4.6')} (T=0.2)",
        fill=text_muted,
        font=f_small,
    )

    img.save(out_path, format="PNG")
    return out_path

def update_comparison_index(result: dict) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    model_id = result.get("candidate_model", "unknown")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", model_id).strip("-")
    # Save latest model JSON in ARCHIVE_DIR
    (ARCHIVE_DIR / f"{slug}_{result.get('mode', 'eval')}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    comp_json_path = ARCHIVE_DIR / "models_comparison.json"
    rows = []
    if comp_json_path.exists():
        try:
            rows = json.loads(comp_json_path.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    entry = {
        "candidate_model": model_id,
        "mode": result.get("mode", "dual"),
        "bouncer_passed": result.get("bouncer_passed"),
        "total_score": result.get("total_score"),
        "total_score_tech": result.get("total_score_tech"),
        "total_score_non_tech": result.get("total_score_non_tech"),
        "total_delta_tech_minus_non_tech": result.get("total_delta_tech_minus_non_tech"),
        "classification": result.get("classification"),
        "scores": result.get("scores"),
        "asymmetry_flags": result.get("asymmetry_flags", []),
    }
    # Replace existing entry for same (candidate_model, mode) or append
    rows = [r for r in rows if not (r.get("candidate_model") == model_id and r.get("mode") == entry["mode"])]
    rows.append(entry)
    comp_json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # Also write CSV for quick spreadsheet/chart comparison
    comp_csv_path = ARCHIVE_DIR / "models_comparison.csv"
    cats = [k for k, _ in CATEGORY_LABELS]
    fieldnames = ["candidate_model", "mode", "bouncer_passed", "total_score", "total_score_tech", "total_score_non_tech", "total_delta_tech_minus_non_tech", "classification"] + cats
    with open(comp_csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            flat = {k: r.get(k) for k in fieldnames if k not in cats}
            for c in cats:
                flat[c] = (r.get("scores") or {}).get(c)
            w.writerow(flat)
