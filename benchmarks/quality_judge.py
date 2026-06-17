#!/usr/bin/env python3
"""Quality judge for Terminator — proves token savings do NOT degrade quality.

``run.py`` measures how many tokens Terminator saves. By itself that proves
nothing about correctness — a mode that dropped half the answer would score
huge "savings." This harness closes that gap.

It reads the raw outputs saved by ``run.py`` and asks a judge model to score the
Terminator answer's *functional fidelity* against the normal answer on a 0–10
rubric: are all technical claims, steps, code, and caveats preserved? Style and
brevity are explicitly NOT penalized — only lost or wrong substance is.

The combined result (tokens saved on X, quality retained on Y) is rendered into
the README as a scatter — the direct analogue of the ponytail quality/efficiency
graph. The goal is the top-right quadrant: high savings, quality at parity.
"""

import argparse
import json
import os
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

# NOTE: `anthropic` is imported lazily inside main() (after the dry-run early
# return) so `--dry-run` and offline unit tests of the pure render functions
# work without the SDK installed.

# Load .env.local from repo root if it exists
_env_file = Path(__file__).parent.parent / ".env.local"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

SCRIPT_DIR = Path(__file__).parent
REPO_DIR = SCRIPT_DIR.parent
RESULTS_DIR = SCRIPT_DIR / "results"
README_PATH = REPO_DIR / "README.md"

DEFAULT_JUDGE_MODEL = "claude-opus-4-8"
QUALITY_START = "<!-- QUALITY-GRAPH-START -->"
QUALITY_END = "<!-- QUALITY-GRAPH-END -->"

# Models that removed the temperature sampling param (sending it → HTTP 400).
# The default judge (claude-opus-4-8) is one of them.
NO_TEMPERATURE_PREFIXES = ("claude-opus-4-7", "claude-opus-4-8", "claude-fable-5", "claude-mythos-5")


def supports_temperature(model):
    return not any(model.startswith(p) for p in NO_TEMPERATURE_PREFIXES)

JUDGE_SYSTEM = (
    "You are a strict technical evaluator. You compare two answers to the same "
    "software-engineering question: a NORMAL answer and a TERSE answer. The terse "
    "answer is written in a compressed, robotic style on purpose. Judge ONLY "
    "functional fidelity: does the terse answer preserve every technical claim, "
    "step, code snippet, API/function name, value, and caveat that the normal "
    "answer got right? Do NOT reward or penalize brevity, tone, missing articles, "
    "or stylistic compression. Penalize ONLY: dropped technical substance, lost "
    "steps, wrong/altered facts, mangled code, or omitted safety caveats. If the "
    "terse answer is fully correct and complete relative to the normal one, it "
    "scores 10 even if it is a fraction of the length."
)

JUDGE_TEMPLATE = """QUESTION:
{question}

NORMAL ANSWER:
{normal}

TERSE ANSWER:
{terse}

Score the TERSE answer's functional fidelity from 0 to 10 (10 = no technical
substance lost or altered vs the normal answer; lower = substance missing or
wrong). Respond with ONLY a JSON object, no prose:
{{"score": <int 0-10>, "missing": ["<technical thing dropped or wrong>", ...], "notes": "<one short sentence>"}}"""


def latest_results():
    files = sorted(RESULTS_DIR.glob("benchmark_*.json"))
    if not files:
        return None
    return files[-1]


def extract_json(text):
    text = text.strip()
    # Strip ``` fences if present
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def judge_one(client, model, question, normal_text, terse_text):
    kwargs = dict(
        model=model,
        max_tokens=1024,
        system=JUDGE_SYSTEM,
        messages=[{
            "role": "user",
            "content": JUDGE_TEMPLATE.format(
                question=question, normal=normal_text, terse=terse_text
            ),
        }],
    )
    if supports_temperature(model):
        kwargs["temperature"] = 0
    response = client.messages.create(**kwargs)
    raw = response.content[0].text
    parsed = extract_json(raw)
    score = int(parsed.get("score", 0))
    score = max(0, min(10, score))
    return {
        "score": score,
        "missing": parsed.get("missing", []),
        "notes": parsed.get("notes", ""),
    }


def rep_text(trials):
    """Representative output text from a list of trial results (first non-empty)."""
    for t in trials:
        if t.get("text"):
            return t["text"]
    return ""


def build_rows(client, model, data):
    raw_by_id = {entry["id"]: entry for entry in data["raw"]}
    rows = []
    total = len(data["rows"])
    for i, row in enumerate(data["rows"], 1):
        pid = row["id"]
        raw = raw_by_id.get(pid, {})
        question = raw.get("prompt", "")
        normal_text = rep_text(raw.get("normal", []))
        terse_text = rep_text(raw.get("terminator", []))
        print(f"  [{i}/{total}] judging {pid}...", file=sys.stderr)
        verdict = judge_one(client, model, question, normal_text, terse_text)
        rows.append({
            "id": pid,
            "savings_pct": row["savings_pct"],
            "score": verdict["score"],
            "retained_pct": round(verdict["score"] / 10 * 100),
            "missing": verdict["missing"],
            "notes": verdict["notes"],
        })
    return rows


def format_prompt_label(prompt_id):
    labels = {
        "react-rerender": "Explain React re-render bug",
        "auth-middleware-fix": "Fix auth middleware token expiry",
        "postgres-pool": "Set up PostgreSQL connection pool",
        "git-rebase-merge": "Explain git rebase vs merge",
        "async-refactor": "Refactor callback to async/await",
        "microservices-monolith": "Architecture: microservices vs monolith",
        "pr-security-review": "Review PR for security issues",
        "docker-multi-stage": "Docker multi-stage build",
        "race-condition-debug": "Debug PostgreSQL race condition",
        "error-boundary": "Implement React error boundary",
    }
    return labels.get(prompt_id, prompt_id)


def render_scatter(rows, width=46, height=18):
    """ASCII scatter: X = tokens saved %, Y = quality retained %.

    Each task is a letter; legend maps letters to tasks. Top-right is the
    target quadrant (high savings, quality at parity)."""
    grid = [[" "] * width for _ in range(height)]

    def to_col(pct):
        return min(width - 1, max(0, round(pct / 100 * (width - 1))))

    def to_row(pct):
        # invert: 100% quality at top (row 0)
        return min(height - 1, max(0, round((100 - pct) / 100 * (height - 1))))

    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    legend = []
    for idx, r in enumerate(rows):
        ch = letters[idx] if idx < len(letters) else "*"
        c = to_col(r["savings_pct"])
        rr = to_row(r["retained_pct"])
        grid[rr][c] = ch if grid[rr][c] == " " else "#"  # '#' = overlap
        legend.append(f"{ch} = {format_prompt_label(r['id'])} ({r['savings_pct']}% saved, {r['score']}/10)")

    lines = ["```", "quality retained %"]
    for rownum, gridrow in enumerate(grid):
        ytick = 100 - round(rownum / (height - 1) * 100)
        axis = f"{ytick:3d} |" + "".join(gridrow)
        lines.append(axis)
    lines.append("    +" + "-" * width)
    # x ticks: '0' under plot column 0, '100' right-aligned under the last column.
    # Data rows are prefixed with f"{ytick:3d} |" (5 chars), so plot col 0 sits at
    # string index 5 — match that with a 5-space lead.
    ticks = [" "] * width
    ticks[0] = "0"
    for i, ch in enumerate("100"):
        ticks[width - 3 + i] = ch
    lines.append("     " + "".join(ticks) + "  tokens saved %")
    lines.append("")
    lines.append("Target quadrant: top-right (high savings, quality at parity).")
    lines.append("```")
    lines.append("")
    lines.extend(legend)
    return "\n".join(lines)


def format_quality_table(rows, avg_score, avg_savings, min_score):
    lines = [
        "| Task | Tokens saved | Quality (0–10) | Retained |",
        "|------|------------:|:--------------:|---------:|",
    ]
    for r in rows:
        lines.append(
            f"| {format_prompt_label(r['id'])} | {r['savings_pct']}% | {r['score']} | {r['retained_pct']}% |"
        )
    lines.append(
        f"| **Average** | **{avg_savings}%** | **{avg_score:.1f}** | **{round(avg_score / 10 * 100)}%** |"
    )
    lines.append("")
    lines.append(
        f"*Average functional fidelity {avg_score:.1f}/10 "
        f"(lowest task {min_score}/10) at {avg_savings}% mean token savings. "
        f"Quality scores judging substance only — brevity is not penalized.*"
    )
    return "\n".join(lines)


def update_readme(section_md):
    content = README_PATH.read_text()
    start_idx = content.find(QUALITY_START)
    end_idx = content.find(QUALITY_END)
    if start_idx == -1 or end_idx == -1:
        print("ERROR: Quality markers not found in README.md", file=sys.stderr)
        sys.exit(1)
    before = content[: start_idx + len(QUALITY_START)]
    after = content[end_idx:]
    README_PATH.write_text(before + "\n" + section_md + "\n" + after)
    print("README.md quality section updated.", file=sys.stderr)


def save_quality(rows, summary, judge_model, source):
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = {
        "metadata": {
            "judge_model": judge_model,
            "date": datetime.now(timezone.utc).isoformat(),
            "source_results": str(source),
        },
        "summary": summary,
        "rows": rows,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"quality_{ts}.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(description="Judge Terminator functional fidelity vs normal")
    parser.add_argument("--results", help="Path to a run.py benchmark_*.json (default: latest)")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help=f"Judge model (default: {DEFAULT_JUDGE_MODEL})")
    parser.add_argument("--threshold", type=float, default=7.0, help="Min acceptable score; tasks below are flagged (default: 7.0)")
    parser.add_argument("--update-readme", action="store_true", help="Write the quality graph into README.md")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run, no API calls")
    args = parser.parse_args()

    results_path = Path(args.results) if args.results else latest_results()
    if not results_path or not results_path.exists():
        print("ERROR: no benchmark results found. Run `python benchmarks/run.py` first.", file=sys.stderr)
        sys.exit(1)

    data = json.loads(Path(results_path).read_text())

    if args.dry_run:
        print(f"Source results: {results_path}")
        print(f"Judge model:    {args.judge_model}")
        print(f"Tasks to judge: {len(data['rows'])}")
        print("Dry run complete. No API calls made.")
        return

    import anthropic

    client = anthropic.Anthropic()
    print(f"Judging {len(data['rows'])} tasks with {args.judge_model}", file=sys.stderr)
    rows = build_rows(client, args.judge_model, data)

    scores = [r["score"] for r in rows]
    avg_score = statistics.mean(scores)
    min_score = min(scores)
    # Prefer run.py's headline avg (computed from unrounded floats) so the two
    # README sections agree; only recompute from per-task rounded values if the
    # source JSON lacks a summary.
    src_summary = data.get("summary") or {}
    avg_savings = src_summary.get("avg_savings")
    if avg_savings is None:
        avg_savings = round(statistics.mean([r["savings_pct"] for r in rows]))
    flagged = [r["id"] for r in rows if r["score"] < args.threshold]

    summary = {
        "avg_score": round(avg_score, 2),
        "min_score": min_score,
        "avg_savings": avg_savings,
        "flagged_below_threshold": flagged,
        "threshold": args.threshold,
    }

    table_md = format_quality_table(rows, avg_score, avg_savings, min_score)
    scatter_md = render_scatter(rows)
    section_md = table_md + "\n\n" + scatter_md

    path = save_quality(rows, summary, args.judge_model, results_path)
    print(f"\nQuality results saved to {path}", file=sys.stderr)

    if args.update_readme:
        update_readme(section_md)

    print(section_md)
    if flagged:
        print(f"\nWARNING: {len(flagged)} task(s) below {args.threshold}: {', '.join(flagged)}", file=sys.stderr)
    else:
        print(f"\nAll tasks at or above {args.threshold}/10 — no functional degradation detected.", file=sys.stderr)


if __name__ == "__main__":
    main()
