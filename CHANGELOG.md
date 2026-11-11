# Changelog

## 0.1.0 — 2026-11-11

First release.

- `/callsheet`: inventories every plugin, MCP server, claude.ai connector, skill and hook that loads in the current repo, judges each one against the repo, and switches off the ones that are of no use there, for this repo only.
- `/callsheet status`, `enable <name>`, `restore`.
- `scripts/apply.py` writes every spelling of the repo's key in `~/.claude.json` (`C:/…`, `c:/…`, `C:\…`): Claude Code reads a different one depending on how the session was launched.
- Skills are hidden with `user-invocable-only`, never `off`, so they stay in your `/` menu.
