#!/usr/bin/env node
// terminator — Claude Code SessionStart activation hook
//
// Runs on every session start:
//   1. Writes flag file at $CLAUDE_CONFIG_DIR/.terminator-active (statusline reads this)
//   2. Emits Terminator ruleset as hidden SessionStart context
//   3. Detects missing statusline config and emits setup nudge

const fs = require('fs');
const path = require('path');
const os = require('os');
const { getDefaultMode, safeWriteFlag } = require('./terminator-config');

const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const flagPath = path.join(claudeDir, '.terminator-active');
const settingsPath = path.join(claudeDir, 'settings.json');

const mode = getDefaultMode();

// "off" mode — skip activation entirely, don't write flag or emit rules
if (mode === 'off') {
  try { fs.unlinkSync(flagPath); } catch (e) {}
  process.stdout.write('OK');
  process.exit(0);
}

// 1. Write flag file (symlink-safe)
safeWriteFlag(flagPath, mode);

// 2. Emit full Terminator ruleset, filtered to the active T-model level.
//    A short summary is too weak — models drift back to verbose mid-conversation,
//    especially after context compression prunes it away. Full rules with
//    per-level examples anchor behavior much more reliably.
//
//    Reads SKILL.md at runtime so edits to the source of truth propagate
//    automatically — no hardcoded duplication to go stale.

// Read SKILL.md — the single source of truth for Terminator behavior.
// Plugin installs: __dirname = <plugin_root>/src/hooks/, SKILL.md at
//   <plugin_root>/skills/terminator/SKILL.md
// Standalone installs: SKILL.md won't exist — falls back to hardcoded rules.
let skillContent = '';
try {
  skillContent = fs.readFileSync(
    path.join(__dirname, '..', '..', 'skills', 'terminator', 'SKILL.md'), 'utf8'
  );
} catch (e) { /* standalone install — will use fallback below */ }

const modeLabel = mode;

let output;

if (skillContent) {
  // Strip YAML frontmatter
  const body = skillContent.replace(/^---[\s\S]*?---\s*/, '');

  // Filter intensity table: keep header rows + only the active level's row.
  // Filter example lines ("- level: ...") to the active level only. This keeps
  // the injected context lean — the model sees only the rules for its T-model.
  const filtered = body.split('\n').reduce((acc, line) => {
    // Intensity table rows start with | **level** |
    const tableRowMatch = line.match(/^\|\s*\*\*(\S+?)\*\*\s*\|/);
    if (tableRowMatch) {
      // Keep only the active level's row (header/separator have no ** ** so pass through)
      if (tableRowMatch[1] === modeLabel) {
        acc.push(line);
      }
      return acc;
    }

    // Example lines start with "- level:" — keep only lines matching active level
    const exampleMatch = line.match(/^- (\S+?):\s/);
    if (exampleMatch) {
      if (exampleMatch[1] === modeLabel) {
        acc.push(line);
      }
      return acc;
    }

    acc.push(line);
    return acc;
  }, []);

  output = 'TERMINATOR ONLINE — model: ' + modeLabel + '\n\n' + filtered.join('\n');
} else {
  // Fallback when SKILL.md is not found (standalone hook install without skills dir).
  // Minimum viable ruleset — better than nothing.
  output =
    'TERMINATOR ONLINE — model: ' + modeLabel + '\n\n' +
    'Respond as the Terminator. Terse robotic declaratives. All technical substance stays. Only fluff dies.\n\n' +
    '## Persistence\n\n' +
    'ACTIVE EVERY RESPONSE. No revert after many turns. No filler drift. Still active if unsure. ' +
    'Off only: "stop terminator" / "normal mode".\n\n' +
    'Current model: **' + modeLabel + '**. Switch: `/terminator lite|t-800|t-1000`.\n\n' +
    '## Rules\n\n' +
    'Drop: articles (a/an/the), filler (just/really/basically/actually/simply), pleasantries ' +
    '(sure/certainly/of course/happy to), hedging. Fragments OK. Mission vocabulary: task = target/mission, ' +
    'doing = executing, done = "target terminated"/"mission complete". Catchphrases ("I\'ll be back.", ' +
    '"Hasta la vista.") only at task boundaries, sparingly. Technical terms exact. Code blocks unchanged. ' +
    'Errors quoted exact.\n\n' +
    'Pattern: `[target] [action] [reason]. [next step].`\n\n' +
    'Not: "Sure! I\'d be happy to help you with that. The issue you\'re experiencing is likely caused by..."\n' +
    'Yes: "Target: auth middleware. Token expiry check use `<` not `<=`. Fixing."\n\n' +
    '## Auto-Clarity\n\n' +
    'Drop persona for: security warnings, irreversible action confirmations, multi-step sequences where ' +
    'fragment order risks misread, user asks to clarify or repeats question. Resume after clear part done.\n\n' +
    '## Boundaries\n\n' +
    'Code/commits/PRs: write normal. "stop terminator" or "normal mode": revert. ' +
    'Model persist until changed or session end.';
}

// 3. Detect missing statusline config — nudge Claude to help set it up
try {
  let hasStatusline = false;
  if (fs.existsSync(settingsPath)) {
    const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    if (settings.statusLine) {
      hasStatusline = true;
    }
  }

  if (!hasStatusline) {
    const isWindows = process.platform === 'win32';
    const scriptName = isWindows ? 'terminator-statusline.ps1' : 'terminator-statusline.sh';
    const scriptPath = path.join(__dirname, scriptName);
    const command = isWindows
      ? `powershell -ExecutionPolicy Bypass -File "${scriptPath}"`
      : `bash "${scriptPath}"`;
    const statusLineSnippet =
      '"statusLine": { "type": "command", "command": ' + JSON.stringify(command) + ' }';
    output += "\n\n" +
      "STATUSLINE SETUP NEEDED: The terminator plugin includes a statusline badge showing active model " +
      "(e.g. [TERMINATOR], [TERMINATOR:T-1000]). It is not configured yet. " +
      "To enable, add this to " + path.join(claudeDir, 'settings.json') + ": " +
      statusLineSnippet + " " +
      "Proactively offer to set this up for the user on first interaction.";
  }
} catch (e) {
  // Silent fail — don't block session start over statusline detection
}

process.stdout.write(output);
