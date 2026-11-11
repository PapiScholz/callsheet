#!/usr/bin/env python3
"""callsheet inventory: everything that loads into a Claude Code session for one repo,
with FULL descriptions, so the model judges each item on what it does, not its name.
Read-only: writes nothing except the --out file.

Usage:
  inventory.py --repo PATH [--out FILE.json] [--no-health]

--no-health skips `claude mcp list` (it health-checks every server and can take a
minute). Without it, claude.ai connectors cannot be listed: they live in no file.
Standard library only.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply import HIDE, LEDGER_NAME, home_dir, key_variants, project_key, read_json  # noqa: E402

HIDDEN_VALUES = (HIDE, "off", "name-only")


def frontmatter(md_path):
    """name and description from a SKILL.md / command .md, multi-line values included."""
    try:
        text = Path(md_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out, key = {}, None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if km:
            key, val = km.group(1), km.group(2).strip()
            out[key] = "" if val in ("|", ">", "|-", ">-") else val.strip("\"'")
        elif key and line.startswith((" ", "\t")):
            out[key] = (out[key] + " " + line.strip()).strip()
    return {k: out[k] for k in ("name", "description", "disable-model-invocation") if k in out}


def run(cmd, cwd, timeout):
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        r = subprocess.run([exe] + cmd[1:], cwd=str(cwd), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.stdout
    except (subprocess.TimeoutExpired, OSError):
        return None


# ---------- plugins ----------

def plugin_details(install_path):
    root = Path(install_path or "")
    info = {"description": "", "skills": [], "commands": [], "mcp_servers": [], "hooks": False}
    for manifest in (root / ".claude-plugin" / "plugin.json", root / "plugin.json"):
        if manifest.exists():
            info["description"] = read_json(manifest).get("description", "")
            break
    for skill_md in sorted(root.glob("skills/*/SKILL.md")) + ([root / "SKILL.md"] if (root / "SKILL.md").exists() else []):
        fm = frontmatter(skill_md)
        info["skills"].append({"name": fm.get("name", skill_md.parent.name), "description": fm.get("description", "")})
    for cmd in sorted(root.glob("commands/*.md")):
        fm = frontmatter(cmd)
        info["commands"].append({"name": cmd.stem, "description": fm.get("description", "")})
    mcp = root / ".mcp.json"
    if mcp.exists():
        data = read_json(mcp)
        info["mcp_servers"] = sorted((data.get("mcpServers") or data).keys())
    info["hooks"] = (root / "hooks" / "hooks.json").exists()
    return info


def plugins(repo):
    raw = run(["claude", "plugin", "list", "--json"], repo, 120)
    if raw is None:
        return {"error": "`claude plugin list --json` did not run"}
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "`claude plugin list --json` returned no JSON"}
    items = items if isinstance(items, list) else items.get("plugins", [])
    seen, out = set(), []
    for p in items:
        pid = p.get("id")
        if not p.get("enabled") or pid in seen:
            continue  # disabled plugins cost nothing; same id can repeat per scope
        seen.add(pid)
        out.append({"id": pid, "scope": p.get("scope"), **plugin_details(p.get("installPath"))})
    return out


# ---------- MCP servers ----------

def mcpjson_files(repo, home):
    """.mcp.json in the repo, every parent folder, and home: all of them load."""
    found, d = [], Path(repo).resolve()
    while True:
        f = d / ".mcp.json"
        if f.exists():
            found.append(f)
        if d.parent == d:
            break
        d = d.parent
    h = Path(home) / ".mcp.json"
    if h.exists() and h not in found:
        found.append(h)
    return found


LINE = re.compile(r"^(?P<name>.+?): (?P<target>.*) - (?P<status>[^\w\s]?\s?.+)$")


def mcp_servers(repo, home, health=True):
    cj = read_json(Path(home) / ".claude.json")
    user = set((cj.get("mcpServers") or {}).keys())
    from_files = {}
    for f in mcpjson_files(repo, home):
        data = read_json(f)
        for name in (data.get("mcpServers") or {}):
            from_files.setdefault(name, str(f))
    servers = {}
    for name in user:
        servers[name] = {"kind": "mcp", "source": "~/.claude.json (user)"}
    for name, f in from_files.items():
        servers.setdefault(name, {"kind": "mcpjson", "source": f})
    if health:
        raw = run(["claude", "mcp", "list"], repo, 240) or ""
        for line in raw.splitlines():
            m = LINE.match(line.strip())
            if not m:
                continue
            name = m.group("name")
            if name.startswith("plugin:"):
                continue  # switched on/off with its plugin
            entry = servers.setdefault(name, {"kind": "mcp", "source": "claude.ai connector" if name.startswith("claude.ai ") else "unknown"})
            entry["status"] = m.group("status").strip()
            entry["target"] = m.group("target").strip()
    return [{"name": n, **v} for n, v in sorted(servers.items())]


# ---------- skills and hooks ----------

def user_skills(home):
    settings = read_json(Path(home) / ".claude" / "settings.json")
    overrides = settings.get("skillOverrides", {})
    registry = read_json(Path(home) / ".claude" / "greenroom" / "registry.json")
    gates = {f.get("gate") for f in registry.get("families", []) if isinstance(f, dict)}
    out = []
    for skill_md in sorted((Path(home) / ".claude" / "skills").glob("*/SKILL.md")):
        name = skill_md.parent.name
        fm = frontmatter(skill_md)
        hidden = overrides.get(name) in HIDDEN_VALUES or fm.get("disable-model-invocation") == "true"
        out.append({
            "name": name,
            "description": fm.get("description", ""),
            "already_hidden_globally": hidden,  # costs no context already: nothing to do
            "greenroom_gate": name in gates,     # the route to hidden skills: protected
            "path": str(skill_md),
        })
    return out


def hooks(home, repo):
    out = []
    for label, f in (("user", Path(home) / ".claude" / "settings.json"),
                     ("project", Path(repo) / ".claude" / "settings.json"),
                     ("local", Path(repo) / ".claude" / "settings.local.json")):
        for event, groups in (read_json(f).get("hooks") or {}).items():
            for g in groups:
                for h in g.get("hooks", []):
                    out.append({"scope": label, "event": event, "matcher": g.get("matcher", ""),
                                "command": (h.get("command") or "")[:160]})
    return out


def current_state(repo, home):
    local = read_json(Path(repo) / ".claude" / "settings.local.json")
    projects = read_json(Path(home) / ".claude.json").get("projects", {})
    disabled = set()
    for k in key_variants(projects, project_key(repo)):
        disabled |= set(projects.get(k, {}).get("disabledMcpServers", []))
    return {
        "plugins_off": sorted(k for k, v in local.get("enabledPlugins", {}).items() if v is False),
        "mcpjson_off": local.get("disabledMcpjsonServers", []),
        "skills_hidden": sorted(k for k, v in local.get("skillOverrides", {}).items() if v in HIDDEN_VALUES),
        "mcp_off": sorted(disabled),
        "ledger": read_json(Path(repo) / ".claude" / LEDGER_NAME) or None,
    }


def inventory(repo, home=None, health=True):
    home = home_dir(home)
    return {
        "repo": project_key(repo),
        "plugins": plugins(repo),
        "mcp_servers": mcp_servers(repo, home, health),
        "user_skills": user_skills(home),
        "hooks": hooks(home, repo),
        "current": current_state(repo, home),
    }


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    ap = argparse.ArgumentParser(description="callsheet inventory (read-only)")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out")
    ap.add_argument("--no-health", action="store_true")
    a = ap.parse_args(argv)
    data = inventory(a.repo, health=not a.no_health)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
        p = data["plugins"]
        print(json.dumps({
            "out": a.out,
            "plugins_enabled": len(p) if isinstance(p, list) else p,
            "mcp_servers": len(data["mcp_servers"]),
            "user_skills_visible": sum(1 for s in data["user_skills"] if not s["already_hidden_globally"]),
            "hooks": len(data["hooks"]),
        }, indent=2))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
