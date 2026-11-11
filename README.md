# callsheet

**Keep only what is useful in each repo, without uninstalling anything.**

[Español](README.es.md)

On a film set, the *call sheet* says who is needed today. Everyone else stays in the cast, ready for another day.

Every plugin, MCP server, claude.ai connector and skill you install globally loads into **every** Claude Code session, in every repo. A web app does not need your Proxmox server, your payments plugin or another client's release skill. They still cost tokens and attention in every session, and they push useful skills out of the model's view.

`/callsheet` switches those off **for the current repo only**. Every change can be turned back on with one command, and other repos are left as they were.

## Install

```bash
npx skills add PapiScholz/callsheet
```

Needs Python 3.9+ (standard library only) and Claude Code.

## Use

| You type | It does |
|---|---|
| `/callsheet` | Inventories everything that loads here, profiles the repo, proposes what to switch off with a reason for each, waits for your OK, applies it with a backup |
| `/callsheet status` | Shows what is off here, and detects if Claude Code rewrote its config since |
| `/callsheet enable <name>` | Switches one item back on, here |
| `/callsheet restore` | Undoes everything callsheet did in this repo |

Changes take effect in the **next** session. Run `/context` there to see the difference.

## What it changes, and where

Nothing global. Everything is a per-project switch that Claude Code already supports:

| Item | Switched off in |
|---|---|
| Plugins (including the ones synced from claude.ai) | `<repo>/.claude/settings.local.json` → `enabledPlugins: false` |
| MCP servers from `.mcp.json` files (also the ones inherited from parent folders) | same file → `disabledMcpjsonServers` |
| Your skills | same file → `skillOverrides: "user-invocable-only"`: hidden from the model, still in your `/` menu |
| User MCP servers and claude.ai connectors | `~/.claude.json` → this repo's `disabledMcpServers`, the same list `/mcp` writes |

`settings.local.json` and the ledger `callsheet.local.json` are added to `.gitignore`, because they describe your machine, not the project. A verified backup of both files is made before every write.

Hooks are listed but never touched: Claude Code has no per-repo switch for a single hook.

## Why it asks before switching anything off

The cheap mistake is keeping a tool you do not need: a few hundred tokens. The expensive one is removing a tool you do need: the model cannot use what it cannot see, and it will not tell you.

callsheet is written against that second mistake. Before judging any item, the model must:
- read the item's full description;
- read the repo's entry point, roadmap and handoff, not only `package.json`;
- read your global instructions, which can make a plugin mandatory.

Unsure means keep, and you get asked. Reasons like "not needed" or "rarely used" are banned.

## Works well with

[greenroom](https://github.com/PapiScholz/greenroom) hides skills globally behind gates; callsheet trims per repo. callsheet never switches off a greenroom gate, and hides skills the same way greenroom does.

## Development

```bash
python -m unittest discover tests
```

The tests run against a fake home folder; your real `~/.claude.json` is never touched.

## License

MIT
