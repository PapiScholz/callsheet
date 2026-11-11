---
name: callsheet
description: Use when a repo's Claude Code sessions start with too much context from global plugins, MCP servers, claude.ai connectors or skills that this repo does not use; when /context shows tens of thousands of tokens before any work; when the user asks to keep only what is useful in this repo, to switch something back on here, or to undo a previous trim. Per-repo only, nothing is uninstalled.
---

# callsheet

A call sheet says who is needed on set today. Everyone else stays in the cast.

This skill switches off, **for the current repo only**, the plugins, MCP servers, claude.ai connectors and skills that are of no use there. Nothing is uninstalled and every change can be undone. The scripts do the writing; your job is the judgment.

**The failure this skill exists to prevent:** switching off things that ARE useful because you judged them by their name, by a shallow read of the repo, or by "not needed". Keeping something useless costs a few hundred tokens. Removing something useful costs the user a broken session and their trust.

## Modes

| Invocation | Do |
|---|---|
| `/callsheet` | Full run: steps 1-6 below |
| `/callsheet status` | `python "<base>/scripts/apply.py" status --repo .`; report what is off and any `drift`. If there is drift, offer `reapply` |
| `/callsheet enable <name>` | `python "<base>/scripts/apply.py" enable --repo . --name "<name>"` |
| `/callsheet restore` | Confirm with the user, then `python "<base>/scripts/apply.py" restore --repo .` |

`<base>` is this skill's base directory. On Windows, add `-X utf8` after `python`.

## Full run

**1. Inventory.** Run `python "<base>/scripts/inventory.py" --repo . --out "<scratchpad>/callsheet-inventory.json"`. It takes up to a minute because it health-checks MCP servers. Read the whole file in parts. It holds the full description of every enabled plugin, the skills and MCP servers inside each plugin, every MCP server, every user skill, every hook, and what is already off in this repo.

**2. Profile the repo.** Read `references/criteria.md`, then:
- `CLAUDE.md` and `AGENTS.md` for the repo, **and the user's global `~/.claude/CLAUDE.md`**. Global rules can make a plugin mandatory, for example "invoke X before any subagent".
- `README`, `ROADMAP`, `HANDOFF.md`, `docs/`, and the manifests.
- **The main source files**, not just the manifests: a "backend" can serve a web page.

Write down the answers to the questions in `references/criteria.md` § Profile. Do not judge any item until they are answered.

**3. Judge every item** with `references/criteria.md`. Read each item's full description. When the description does not settle it, open its `SKILL.md` or README. Every item gets one of three verdicts:
- **keep**: any concrete use now, or on the roadmap, or cross-cutting process.
- **off**: a concrete reason that cites the profile.
- **ask**: unsure. Unsure is never off.

**4. Propose and wait.** Show one table per kind with columns `Item | keep / off / ask | Reason (≤12 words)`, then the `ask` items as questions. **Write nothing until the user answers.**

**5. Apply.** Write the approved `off` items to `<scratchpad>/callsheet-decision.json` as `{"plugins": {id: reason}, "mcpjson": {...}, "mcp": {...}, "skills": {...}}`, then run `python "<base>/scripts/apply.py" apply --repo . --decision <file>`.

| Kind | Inventory field | Where it is switched off |
|---|---|---|
| `plugins` | `plugins[].id` | `.claude/settings.local.json` `enabledPlugins` |
| `mcpjson` | `mcp_servers` with `kind: mcpjson` | `.claude/settings.local.json` `disabledMcpjsonServers` |
| `mcp` | `mcp_servers` with `kind: mcp` (user servers and `claude.ai …` connectors) | `~/.claude.json` this repo's `disabledMcpServers`, under every spelling of its key |
| `skills` | `user_skills[].name` | `.claude/settings.local.json` `skillOverrides: user-invocable-only` (still in the user's `/` menu) |

A plugin's own skills and MCP servers go off **with the plugin**; there is no way to switch them off one by one. Hooks cannot be switched off one by one per repo: report them, never touch them.

**6. Report.** Say what went off, the backup folder, how to turn any item back on (`/callsheet enable <name>`), and that the effect starts in the **next** session, where `/context` shows the drop.

## Never switch off

- `callsheet` itself.
- Skills with `greenroom_gate: true`. They are the only route to the hidden skills behind them.
- Anything a global or repo instruction file makes mandatory.
- Items that cost no context (hooks-only plugins, LSP plugins): nothing is saved.

Judge what is **already off** in this repo (`current` in the inventory) by the same rules. An earlier trim may have been wrong. If an item already off is protected or useful, propose `enable` for it.

## Red flags: stop and re-read the item

Any of these as your reason means you have not done the work:
- "Not needed", "Not used", "Rarely used", "Can be invoked on demand"
- "Duplicates X" or "Overlaps with X" (two tools covering one area is not a reason when both are useful)
- "Small repo", "Simple repo"
- "No UI", "No frontend", "API only", when you only read the manifests
- "Only mentioned in the research docs", when that research feeds the roadmap

See `references/criteria.md` for the reasoning behind each one and examples.
