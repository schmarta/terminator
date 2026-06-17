#!/usr/bin/env node
// terminator — UserPromptSubmit hook to track which T-model is active.
// Inspects user input for /terminator commands (and natural language) and writes
// the active model to the flag file, then re-injects the persona each turn.

const fs = require('fs');
const path = require('path');
const os = require('os');
const { getDefaultMode, safeWriteFlag, readFlag, VALID_MODES } = require('./terminator-config');

const claudeDir = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), '.claude');
const flagPath = path.join(claudeDir, '.terminator-active');

let input = '';
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    const prompt = (data.prompt || '').trim().toLowerCase();

    // Natural language activation (e.g. "activate terminator", "turn on terminator
    // mode", "talk like the terminator"). Keeps the flag/statusline in sync even
    // when the user doesn't use the slash command.
    if (/\b(activate|enable|turn on|start|talk like)\b.*\bterminator\b/i.test(prompt) ||
        /\bterminator\b.*\b(mode|activate|enable|turn on|start)\b/i.test(prompt)) {
      if (!/\b(stop|disable|turn off|deactivate)\b/i.test(prompt)) {
        const mode = getDefaultMode();
        if (mode !== 'off') {
          safeWriteFlag(flagPath, mode);
        }
      }
    }

    // Match /terminator commands
    if (prompt.startsWith('/terminator')) {
      const parts = prompt.split(/\s+/);
      const cmd = parts[0]; // /terminator or /terminator:terminator
      const arg = parts[1] || '';

      let mode = null;

      if (cmd === '/terminator' || cmd === '/terminator:terminator') {
        // Bare /terminator is an explicit activation request. Honor the
        // configured default, but if that resolves to 'off' fall back to t-800
        // rather than deactivating — typing the command means "bring it online".
        if (!arg) {
          const def = getDefaultMode();
          mode = def === 'off' ? 't-800' : def;
        } else if (arg === 'off' || arg === 'stop' || arg === 'disable') {
          mode = 'off';
        } else if (VALID_MODES.includes(arg)) {
          mode = arg;
        }
        // Unknown arg → mode stays null, flag untouched (no silent overwrite)
      }

      if (mode && mode !== 'off') {
        safeWriteFlag(flagPath, mode);
      } else if (mode === 'off') {
        try { fs.unlinkSync(flagPath); } catch (e) {}
      }
    }

    // Detect deactivation — natural language and slash commands
    if (/\b(stop|disable|deactivate|turn off)\b.*\bterminator\b/i.test(prompt) ||
        /\bterminator\b.*\b(stop|disable|deactivate|turn off)\b/i.test(prompt) ||
        /\bnormal mode\b/i.test(prompt)) {
      try { fs.unlinkSync(flagPath); } catch (e) {}
    }

    // Per-turn reinforcement: emit a structured reminder when terminator is active.
    // The SessionStart hook injects the full ruleset once, but models lose it when
    // other plugins inject competing style instructions every turn. This keeps the
    // persona in the model's attention on every user message.
    //
    // readFlag enforces symlink-safe read + size cap + VALID_MODES whitelist.
    // If the flag is missing, corrupted, oversized, or a symlink pointing at
    // something like ~/.ssh/id_rsa, readFlag returns null and we emit nothing
    // — never inject untrusted bytes into model context.
    const activeMode = readFlag(flagPath);
    if (activeMode) {
      process.stdout.write(JSON.stringify({
        hookSpecificOutput: {
          hookEventName: "UserPromptSubmit",
          additionalContext: "TERMINATOR ONLINE (" + activeMode + "). " +
            "Terse robotic declaratives. Drop articles/filler/pleasantries/hedging. " +
            "Mission vocabulary (target/executing/terminated). Code/commits/security: write normal."
        }
      }));
    }
  } catch (e) {
    // Silent fail
  }
});
