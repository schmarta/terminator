<p align="center">
  <img src="assets/logo.png" alt="Terminator" width="320">
</p>

# Terminator

> Send the Terminator off on a task. It acquires the target, executes, and terminates it — in terse, robotic, low-token declaratives.

A comedic Claude Code plugin in the spirit of [caveman](https://github.com/juliusbrussee/caveman) and [ponytail](https://github.com/DietrichGebert/ponytail). Terminator makes Claude respond as a machine on a mission: short, flat, on-theme — which cuts token usage like caveman while staying brutally straightforward like ponytail.

**The hard constraint: it must not degrade functional quality.** Terseness is style only. Every technical claim, step, code block, function name, error string, and safety caveat survives intact. The benchmark below exists specifically to prove that.

```
[TERMINATOR]  ← statusline badge when online
```

> "Target: auth middleware. Token expiry check uses `<`, should be `<=`. Fixing now. I'll be back."

## Install

```bash
# Add this repo as a local marketplace, then install the plugin
/plugin marketplace add /path/to/terminator
/plugin install terminator@terminator
```

On first session Claude will offer to wire up the statusline badge. To do it manually, add to `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "bash /path/to/terminator/src/hooks/terminator-statusline.sh"
}
```

(Windows: `powershell -ExecutionPolicy Bypass -File <path>\terminator-statusline.ps1`)

## Usage

Terminator comes **online by default** at model `t-800` when the plugin is installed. Switch models or stand it down:

| Command | Effect |
|---------|--------|
| `/terminator` | Online at default model (t-800) |
| `/terminator lite` | Light machine flavor |
| `/terminator t-800` | Default Terminator |
| `/terminator t-1000` | Maximum compression |
| `/terminator off` | Stand down (revert to normal) |

Natural language works too: "activate terminator", "talk like the terminator", "stop terminator", "normal mode".

## T-models

| Model | Behavior |
|-------|----------|
| **lite** | Keeps articles and full sentences. Terse, professional, no filler. The cyborg passing for human. |
| **t-800** | Default. Drops articles, fragments OK, mission vocabulary, sparing catchphrases at task boundaries. |
| **t-1000** | Maximum compression. Telegraphic mission-log, abbreviated prose, arrows for causality. Code/API/error strings never abbreviated. |

The default model is configurable via the `TERMINATOR_DEFAULT_MODE` environment variable or `~/.config/terminator/config.json` (`{"defaultMode": "t-1000"}`).

### Auto-Clarity (why quality is safe)

The mission must not fail from terseness. Terminator automatically **drops the persona** — writing plain, complete prose — for security warnings, irreversible-action confirmations, and multi-step sequences where compression would risk a misread. Code, commits, PRs, and file contents are always written normally. The persona is a communication layer, never a layer over correctness.

## Benchmark

Two harnesses live in [`benchmarks/`](benchmarks/). Together they answer the only two questions that matter: *how many tokens does it save* and *does it cost any correctness*.

Setup:

```bash
pip install -r benchmarks/requirements.txt
export ANTHROPIC_API_KEY=sk-...
```

### 1. Token savings — `run.py`

Calls the Anthropic API twice per task (plain assistant vs. the Terminator `SKILL.md` as system prompt), over the shared dev-task prompt set in [`prompts.json`](benchmarks/prompts.json), and reports median output-token savings.

```bash
python benchmarks/run.py --dry-run                 # show plan, no API calls
python benchmarks/run.py --trials 3 --update-readme # real run, writes the table below
```

<!-- BENCHMARK-TABLE-START -->
| Task | Normal (tokens) | Terminator (tokens) | Saved |
|------|---------------:|-------------------:|------:|
| Explain React re-render bug | 905 | 303 | 67% |
| Fix auth middleware token expiry | 1059 | 451 | 57% |
| Set up PostgreSQL connection pool | 2260 | 975 | 57% |
| Explain git rebase vs merge | 991 | 583 | 41% |
| Refactor callback to async/await | 454 | 310 | 32% |
| Architecture: microservices vs monolith | 976 | 691 | 29% |
| Review PR for security issues | 867 | 693 | 20% |
| Docker multi-stage build | 2132 | 816 | 62% |
| Debug PostgreSQL race condition | 1339 | 707 | 47% |
| Implement React error boundary | 4096 | 1498 | 63% |
| **Average** | **1508** | **703** | **48%** |

*Range: 20%–67% savings across prompts.*
<!-- BENCHMARK-TABLE-END -->

### 2. Quality — `quality_judge.py`

Savings are meaningless if substance is lost. This harness reads the exact outputs `run.py` saved and has a judge model score the Terminator answer's **functional fidelity** against the normal answer (0–10): are all technical claims, steps, code, and caveats preserved? **Brevity is explicitly not penalized — only lost or wrong substance is.**

```bash
python benchmarks/quality_judge.py --update-readme   # judges the latest run
```

The combined result is plotted as **tokens saved (X) vs. quality retained (Y)** — the direct analogue of the ponytail efficiency/quality graph. The goal is the **top-right quadrant**: high savings, quality at parity with normal.

<!-- QUALITY-GRAPH-START -->
| Task | Tokens saved | Quality (0–10) | Retained |
|------|------------:|:--------------:|---------:|
| Explain React re-render bug | 67% | 6 | 60% |
| Fix auth middleware token expiry | 57% | 8 | 80% |
| Set up PostgreSQL connection pool | 57% | 6 | 60% |
| Explain git rebase vs merge | 41% | 8 | 80% |
| Refactor callback to async/await | 32% | 9 | 90% |
| Architecture: microservices vs monolith | 29% | 8 | 80% |
| Review PR for security issues | 20% | 8 | 80% |
| Docker multi-stage build | 62% | 7 | 70% |
| Debug PostgreSQL race condition | 47% | 6 | 60% |
| Implement React error boundary | 63% | 8 | 80% |
| **Average** | **48%** | **7.4** | **74%** |

*Average functional fidelity 7.4/10 (lowest task 6/10) at 48% mean token savings. Quality scores judging substance only — brevity is not penalized.*

```
quality retained %
100 |                                              
 94 |                                              
 88 |              E                               
 82 |         G   F    D       B J                 
 76 |                                              
 71 |                            H                 
 65 |                                              
 59 |                     I    C   A               
 53 |                                              
 47 |                                              
 41 |                                              
 35 |                                              
 29 |                                              
 24 |                                              
 18 |                                              
 12 |                                              
  6 |                                              
  0 |                                              
    +----------------------------------------------
     0                                          100  tokens saved %

Target quadrant: top-right (high savings, quality at parity).
```

A = Explain React re-render bug (67% saved, 6/10)
B = Fix auth middleware token expiry (57% saved, 8/10)
C = Set up PostgreSQL connection pool (57% saved, 6/10)
D = Explain git rebase vs merge (41% saved, 8/10)
E = Refactor callback to async/await (32% saved, 9/10)
F = Architecture: microservices vs monolith (29% saved, 8/10)
G = Review PR for security issues (20% saved, 8/10)
H = Docker multi-stage build (62% saved, 7/10)
I = Debug PostgreSQL race condition (47% saved, 6/10)
J = Implement React error boundary (63% saved, 8/10)
<!-- QUALITY-GRAPH-END -->

### 3. Head-to-head vs caveman

Caveman published savings but never a fidelity score. We ran caveman through the **same harness** — identical prompts, identical normal baseline, same judge model (`claude-opus-4-8`), temperature 0 — so the two are directly comparable.

| Metric | Terminator | Caveman |
|--------|:----------:|:-------:|
| Mean token savings | 48% | **59%** |
| Mean quality (0–10) | **7.4** | **7.4** |
| Quality retained | 74% | 74% |
| Lowest task | 6/10 | 5/10 |
| Tasks below 7/10 | 3 | 2 |

**Quality is a tie (7.4 each); caveman compresses ~11 points harder.** Per-task quality deltas are all within ±1 — judge noise, not signal. Honest takeaway: both preserve substance equally well, and caveman saves more tokens. Terminator's edge is the *persona*, not the numbers.

_Reproduce: `python benchmarks/caveman_run.py` then `python benchmarks/quality_judge.py --results benchmarks/results/caveman_benchmark_*.json`._

## How it works

- **`SessionStart` hook** (`terminator-activate.js`) writes the active model to a flag file and injects the persona ruleset — filtered at runtime to just the active T-model's rules and examples — as session context.
- **`UserPromptSubmit` hook** (`terminator-mode-tracker.js`) parses `/terminator` and natural-language commands, keeps the flag in sync, and re-injects a one-line persona reminder every turn so the model never drifts back to verbose.
- **Statusline scripts** read the flag and render the `[TERMINATOR]` / `[TERMINATOR:T-1000]` badge.
- **`SKILL.md`** is the single source of truth for the persona; the hooks read it at runtime, so edits propagate without code changes.

### Security

The flag-file machinery is ported verbatim from caveman's hardened design and must stay that way: symlink refusal (`O_NOFOLLOW`), atomic temp-and-rename writes with `0600` permissions, a 64-byte read cap, a strict mode whitelist, and ownership (uid) checks on symlinked config dirs. This prevents a local attacker from pointing the flag at a secret (e.g. `~/.ssh/id_rsa`) and having the statusline or per-turn reinforcement leak its bytes.

## Roadmap (out of scope for v1)

- `/terminator-commit`, `/terminator-review`, `/terminator-stats`
- Savings suffix on the statusline badge
- Terminator subagents (a "Skynet" crew, analogous to caveman's cavecrew)
- Codex / Gemini / opencode adapters
- Optional PNG render of the quality/efficiency scatter

## Credits

Architecture derived from [caveman](https://github.com/juliusbrussee/caveman) by Julius Brussee (MIT). Concept also inspired by [ponytail](https://github.com/DietrichGebert/ponytail). MIT licensed.
