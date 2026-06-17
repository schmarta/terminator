#!/usr/bin/env python3
"""Generate a caveman terse-output set reusing terminator's normal baseline.

Reuses the NORMAL answers already captured in the latest terminator
benchmark_*.json (same prompts, same model, temperature 0) and only generates
the caveman terse answers, using caveman's SKILL.md as the system prompt. The
caveman outputs are stored under the "terminator" key so that quality_judge.py
(which compares "normal" vs "terminator") can score them unmodified.

Output: results/caveman_benchmark_<ts>.json
"""

import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import run as base  # terminator's run.py — reuse call_api, load_prompts, stats helpers

CAVE_SKILL = Path(
    "/Users/lucas/.claude/plugins/cache/caveman/caveman/655b7d9c5431/skills/caveman/SKILL.md"
)
TRIALS = 3


def main():
    import anthropic

    src = base.RESULTS_DIR / "benchmark_20260617_183805.json"
    data = json.loads(src.read_text())
    model = data["metadata"]["model"]
    normal_by_id = {e["id"]: e["normal"] for e in data["raw"]}

    caveman_system = CAVE_SKILL.read_text()
    client = anthropic.Anthropic()
    prompts = base.load_prompts()
    total = len(prompts)

    results = []
    for i, p in enumerate(prompts, 1):
        pid = p["id"]
        entry = {
            "id": pid,
            "category": p["category"],
            "prompt": p["prompt"],
            "normal": normal_by_id.get(pid, []),  # reuse terminator's baseline
            "terminator": [],                      # holds caveman outputs
        }
        for t in range(1, TRIALS + 1):
            print(f"  [{i}/{total}] {pid} | caveman | trial {t}/{TRIALS}", file=sys.stderr)
            entry["terminator"].append(
                base.call_api(client, model, caveman_system, p["prompt"])
            )
        results.append(entry)

    # Recompute rows/summary with caveman outputs in the "terminator" slot.
    rows, summary = base.compute_stats(results)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = {
        "metadata": {
            "script_version": "caveman-compare-1.0",
            "model": model,
            "date": datetime.now(timezone.utc).isoformat(),
            "trials": TRIALS,
            "terse_skill": "caveman",
            "normal_baseline_from": str(src.name),
        },
        "summary": summary,
        "rows": rows,
        "raw": results,
    }
    path = base.RESULTS_DIR / f"caveman_benchmark_{ts}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nSaved {path}", file=sys.stderr)
    print(base.format_table(rows, summary))


if __name__ == "__main__":
    main()
