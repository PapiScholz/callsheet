#!/usr/bin/env python3
"""callsheet apply: switch plugins, MCP servers, connectors and skills off for ONE repo.

Nothing is uninstalled. Every change is per-project and reversible:

  plugins     -> <repo>/.claude/settings.local.json  enabledPlugins["<id>"] = false
  mcpjson     -> <repo>/.claude/settings.local.json  disabledMcpjsonServers  (servers from .mcp.json files)
  skills      -> <repo>/.claude/settings.local.json  skillOverrides["<name>"] = "user-invocable-only"
  mcp         -> ~/.claude.json projects["<repo>"].disabledMcpServers  (user servers, claude.ai connectors)

The last one is the same list /mcp writes when you switch a server off "for this project".
A ledger with the reasons lives at <repo>/.claude/callsheet.local.json.

Usage:
  apply.py apply   --repo PATH --decision FILE.json
  apply.py enable  --repo PATH --name NAME
  apply.py status  --repo PATH
  apply.py reapply --repo PATH
  apply.py restore --repo PATH

Decision file: {"plugins": {id: reason}, "mcpjson": {...}, "mcp": {...}, "skills": {...}}
Standard library only.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

KINDS = ("plugins", "mcpjson", "mcp", "skills")
HIDE = "user-invocable-only"  # never "off": that also drops /name from the user's menu
LEDGER_NAME = "callsheet.local.json"
GITIGNORE_LINES = (".claude/settings.local.json", ".claude/" + LEDGER_NAME)


# ---------- paths and io ----------

def project_key(repo):
    """Key Claude Code uses in ~/.claude.json projects: absolute, forward slashes."""
    return str(Path(repo).resolve()).replace("\\", "/")


def key_variants(projects, key):
    """Every spelling of this repo's key. Claude Code stores the same repo as
    "C:/x", "c:/x" and sometimes "C:\\x", and which one a session reads depends on
    how it was launched (terminal vs. IDE). Writing only one leaves the others on."""
    def norm(k):
        return k.replace("\\", "/").lower()
    canon = key.replace("\\", "/")
    keys = [k for k in projects if norm(k) == norm(canon)]
    if re.match(r"^[A-Za-z]:/", canon):
        for v in (canon[0].upper() + canon[1:], canon[0].lower() + canon[1:]):
            if v not in keys:
                keys.append(v)
    elif not keys:
        keys = [canon]
    return keys


def home_dir(home=None):
    return Path(home) if home else Path(os.environ.get("CALLSHEET_HOME") or Path.home())


def files(repo, home=None):
    repo = Path(repo)
    return {
        "local": repo / ".claude" / "settings.local.json",
        "ledger": repo / ".claude" / LEDGER_NAME,
        "claude_json": home_dir(home) / ".claude.json",
        "gitignore": repo / ".gitignore",
    }


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return {} if default is None else default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} is not valid JSON: {e}") from e


def write_json_atomic(path, data):
    """Write to a temp file in the same folder, re-read it as JSON, then replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        json.loads(Path(tmp).read_text(encoding="utf-8"))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def backup(paths, backup_root=None):
    """Copy both files to a fresh folder and verify byte-for-byte before going on."""
    root = Path(backup_root) if backup_root else Path(tempfile.gettempdir())
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = root / f"callsheet-backup-{stamp}"
    dest.mkdir(parents=True)
    manifest = {}
    for label, src in (("claude.json", paths["claude_json"]), ("settings.local.json", paths["local"])):
        if src.exists():
            shutil.copy2(src, dest / label)
            if (dest / label).read_bytes() != src.read_bytes():
                raise RuntimeError(f"backup of {src} does not match the original")
            manifest[label] = str(src)
        else:
            manifest[label] = None  # did not exist: restore removes it
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return dest


# ---------- the four switches ----------

def _uniq_add(lst, items):
    for i in items:
        if i not in lst:
            lst.append(i)
    return lst


def _set_local(local, kind, names):
    if kind == "plugins":
        ep = local.setdefault("enabledPlugins", {})
        for n in names:
            ep[n] = False
    elif kind == "mcpjson":
        _uniq_add(local.setdefault("disabledMcpjsonServers", []), names)
        if "enabledMcpjsonServers" in local:
            local["enabledMcpjsonServers"] = [s for s in local["enabledMcpjsonServers"] if s not in names]
    elif kind == "skills":
        so = local.setdefault("skillOverrides", {})
        for n in names:
            so[n] = HIDE


def _normalize_off(local):
    so = local.get("skillOverrides", {})
    for k, v in so.items():
        if v == "off":
            so[k] = HIDE


def _project_entries(cj, repo):
    projects = cj.setdefault("projects", {})
    return [projects.setdefault(k, {}) for k in key_variants(projects, project_key(repo))]


def ensure_gitignore(repo):
    gi = files(repo)["gitignore"]
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    lines = text.splitlines()
    missing = [l for l in GITIGNORE_LINES if l not in lines]
    if missing:
        sep = "" if (not text or text.endswith("\n")) else "\n"
        with open(gi, "w", encoding="utf-8", newline="\n") as f:
            f.write(text + sep + "\n".join(missing) + "\n")


def validate(decision):
    unknown = set(decision) - set(KINDS)
    if unknown:
        raise ValueError(f"unknown kinds {sorted(unknown)}; allowed: {list(KINDS)}")
    for k, v in decision.items():
        if not isinstance(v, dict):
            raise ValueError(f"{k} must map name -> reason")


def apply(repo, decision, home=None, backup_root=None):
    validate(decision)
    p = files(repo, home)
    # Read everything first: a broken file aborts before anything is written.
    local = read_json(p["local"])
    cj = read_json(p["claude_json"])
    ledger = read_json(p["ledger"], {"disabled": {}})
    dest = backup(p, backup_root)

    for kind in ("plugins", "mcpjson", "skills"):
        _set_local(local, kind, list(decision.get(kind, {})))
    _normalize_off(local)
    for entry in _project_entries(cj, repo):
        _uniq_add(entry.setdefault("disabledMcpServers", []), list(decision.get("mcp", {})))

    write_json_atomic(p["local"], local)
    write_json_atomic(p["claude_json"], cj)

    for kind in KINDS:
        ledger["disabled"].setdefault(kind, {}).update(decision.get(kind, {}))
    ledger.setdefault("first_backup_dir", str(dest))
    ledger["backup_dir"] = str(dest)
    ledger["applied_at"] = datetime.now().isoformat(timespec="seconds")
    write_json_atomic(p["ledger"], ledger)
    ensure_gitignore(repo)
    return {"backup_dir": str(dest), "ledger": str(p["ledger"])}


def enable(repo, name, home=None):
    """Switch one item back on. Returns its kind, or None if it was not off."""
    p = files(repo, home)
    local = read_json(p["local"])
    cj = read_json(p["claude_json"])
    found = None
    if local.get("enabledPlugins", {}).get(name) is False:
        del local["enabledPlugins"][name]
        found = "plugins"
    elif name in local.get("disabledMcpjsonServers", []):
        local["disabledMcpjsonServers"].remove(name)
        found = "mcpjson"
    elif local.get("skillOverrides", {}).get(name) in (HIDE, "off"):
        del local["skillOverrides"][name]
        found = "skills"
    else:
        for entry in _project_entries(cj, repo):
            if name in entry.get("disabledMcpServers", []):
                entry["disabledMcpServers"].remove(name)
                found = "mcp"
    if not found:
        return None
    if found == "mcp":
        write_json_atomic(p["claude_json"], cj)
    else:
        write_json_atomic(p["local"], local)
    if p["ledger"].exists():
        ledger = read_json(p["ledger"])
        ledger.get("disabled", {}).get(found, {}).pop(name, None)
        write_json_atomic(p["ledger"], ledger)
    return found


def status(repo, home=None):
    """What the ledger says is off, and what is no longer off on disk (drift)."""
    p = files(repo, home)
    ledger = read_json(p["ledger"], {"disabled": {}})
    local = read_json(p["local"])
    projects = read_json(p["claude_json"]).get("projects", {})
    # Off only if it is off under EVERY spelling of the key.
    mcp_sets = [set(projects.get(k, {}).get("disabledMcpServers", []))
                for k in key_variants(projects, project_key(repo))]
    actual = {
        "plugins": {k for k, v in local.get("enabledPlugins", {}).items() if v is False},
        "mcpjson": set(local.get("disabledMcpjsonServers", [])),
        "skills": {k for k, v in local.get("skillOverrides", {}).items() if v in (HIDE, "off")},
        "mcp": set.intersection(*mcp_sets) if mcp_sets else set(),
    }
    drift = {}
    for kind in KINDS:
        missing = sorted(set(ledger.get("disabled", {}).get(kind, {})) - actual[kind])
        if missing:
            drift[kind] = missing
    return {"ledger": ledger, "actual": {k: sorted(v) for k, v in actual.items()}, "drift": drift}


def reapply(repo, home=None, backup_root=None):
    """Re-write what the ledger says, e.g. after Claude Code rewrote ~/.claude.json."""
    ledger = read_json(files(repo, home)["ledger"], {"disabled": {}})
    return apply(repo, ledger.get("disabled", {}), home=home, backup_root=backup_root)


def restore(repo, home=None):
    """Back to the state before the FIRST apply: settings.local.json whole, and only
    this repo's entry in ~/.claude.json (everything else there is kept)."""
    p = files(repo, home)
    ledger = read_json(p["ledger"])
    if not ledger:
        raise ValueError("nothing to restore: no ledger in this repo")
    dest = Path(ledger.get("first_backup_dir") or ledger["backup_dir"])
    manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))

    if manifest.get("settings.local.json"):
        shutil.copy2(dest / "settings.local.json", p["local"])
    elif p["local"].exists():
        p["local"].unlink()

    old_cj = read_json(dest / "claude.json") if manifest.get("claude.json") else {}
    old_projects = old_cj.get("projects", {})
    cj = read_json(p["claude_json"])
    projects = cj.setdefault("projects", {})
    for key in key_variants(projects, project_key(repo)):
        if key in old_projects:
            projects[key] = old_projects[key]
        else:
            projects.pop(key, None)
    write_json_atomic(p["claude_json"], cj)
    p["ledger"].unlink()
    return str(dest)


# ---------- cli ----------

def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    ap = argparse.ArgumentParser(description="callsheet: per-repo switch for plugins, MCP and skills")
    ap.add_argument("command", choices=["apply", "enable", "status", "reapply", "restore"])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--decision")
    ap.add_argument("--name")
    a = ap.parse_args(argv)
    try:
        if a.command == "apply":
            if not a.decision:
                ap.error("apply needs --decision FILE.json")
            out = apply(a.repo, read_json(a.decision))
        elif a.command == "enable":
            if not a.name:
                ap.error("enable needs --name")
            kind = enable(a.repo, a.name)
            out = {"enabled": a.name, "kind": kind} if kind else {"error": f"'{a.name}' is not switched off here"}
        elif a.command == "status":
            out = status(a.repo)
        elif a.command == "reapply":
            out = reapply(a.repo)
        else:
            out = {"restored_from": restore(a.repo)}
    except (ValueError, RuntimeError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    sys.exit(main())
