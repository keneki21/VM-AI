"""
Temporary Flask web UI for UX heuristics evaluation.
Run:  python web_app.py
Then open:  http://127.0.0.1:5000
"""

import math
import os
import uuid
from datetime import date
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for, send_from_directory
from PIL import Image

from evaluator.scorer     import UIClipScorer
from evaluator.detector   import WebUIDetector
from evaluator.heuristics import check as heuristic_check
from evaluator.report     import generate

app = Flask(__name__)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Load models once at startup
print("Loading models…")
_scorer   = UIClipScorer()
_detector = WebUIDetector()
if not _detector.available:
    print("  WebUI detector not available — run download_models.py first.")
print("Ready.\n")


# ── helpers ────────────────────────────────────────────────────────────────

def _color(score: float):
    if score >= 7.0:
        return "c-green", "bg-green", "#16a34a", "tag-pass", "OK"
    if score >= 5.5:
        return "c-orange", "bg-orange", "#ea580c", "tag-medium", "MEDIUM"
    return "c-red", "bg-red", "#dc2626", "tag-high", "HIGH"


def _grade(score: float) -> str:
    for thr, letter in [(8.5,"A"),(7.5,"B+"),(6.5,"B"),(5.5,"C+"),(4.5,"C"),(3.5,"D"),(0,"F")]:
        if score >= thr:
            return letter
    return "F"


def _summary(overall: float, issues: list) -> str:
    high = sum(1 for i in issues if i["severity"] == "high")
    med  = sum(1 for i in issues if i["severity"] == "medium")
    if overall >= 7.5:
        return f"This interface scores well overall. {'Watch for ' + str(high+med) + ' medium/high issue(s) identified below.' if high+med else 'No significant issues detected — great work!'}"
    if overall >= 5.5:
        return f"Moderate UX quality. {high} high-priority and {med} medium-priority issue(s) need attention. See the issues section for specific fixes."
    return f"Several UX problems detected ({high} high, {med} medium). Addressing the high-priority issues will have the biggest impact on usability."


# ── routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/evaluate", methods=["POST"])
def evaluate():
    file = request.files.get("screenshot")
    if not file or file.filename == "":
        return redirect(url_for("index"))

    ext      = Path(file.filename).suffix.lower() or ".png"
    uid      = uuid.uuid4().hex[:8]
    saved    = UPLOAD_DIR / f"{uid}{ext}"
    file.save(str(saved))

    image = Image.open(saved).convert("RGB")

    # Run pipeline
    clip_scores   = _scorer.score(image)
    elements      = _detector.detect(image)
    extra_issues  = heuristic_check(elements, clip_scores)
    report, _     = generate(clip_scores, extra_issues, file.filename)

    # Build template context
    overall  = report["overall_score"]
    grade    = _grade(overall)
    issues   = report["issues"]

    # Score ring geometry
    r            = 46
    circumference = round(2 * math.pi * r, 2)
    dashoffset    = round(circumference * (1 - overall / 10), 2)
    tc, _, stroke_hex, _, _ = _color(overall)

    heuristics_ctx = []
    for i, h in enumerate(clip_scores, 1):
        tc2, bc, _, tag_cls, tag = _color(h["score"])
        heuristics_ctx.append({
            "name":       h["name"],
            "score":      h["score"],
            "bar_pct":    round(h["score"] * 10, 1),
            "bar_color":  bc,
            "text_color": tc2,
            "tag_class":  tag_cls,
            "tag":        tag,
        })

    return render_template(
        "results.html",
        filename     = file.filename,
        date         = str(date.today()),
        overall      = overall,
        grade        = grade,
        issue_count  = len(issues),
        summary      = _summary(overall, issues),
        heuristics   = heuristics_ctx,
        issues       = issues,
        image_url    = url_for("uploaded_file", filename=saved.name),
        circumference = circumference,
        dashoffset    = dashoffset,
        ring_color    = tc,
        stroke_hex    = stroke_hex,
    )


if __name__ == "__main__":
    app.run(debug=False, port=5000)
