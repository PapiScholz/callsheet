"""Tests for scripts/apply.py. Every test runs against a fake home and a fake repo
in a temporary directory: the real ~/.claude.json is never touched."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import apply as cs  # noqa: E402


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.repo = root / "work" / "repo"
        self.repo.mkdir(parents=True)
        self.backups = root / "backups"
        self.key = cs.project_key(self.repo)
        self.claude_json = self.home / ".claude.json"
        write(self.claude_json, {
            "numStartups": 7,
            "mcpServers": {"lab": {"command": "x"}},
            "projects": {
                self.key: {"allowedTools": ["Bash"], "disabledMcpServers": ["already-off"]},
                "C:/other/repo": {"disabledMcpServers": ["keep-me"]},
            },
        })
        self.local = self.repo / ".claude" / "settings.local.json"
        write(self.local, {
            "permissions": {"allow": ["Bash(npm test)"]},
            "enabledMcpjsonServers": ["21st", "next-devtools"],
            "enabledPlugins": {"kept@market": True},
        })
        self.decision = {
            "plugins": {"mercadopago@official": "repo has no payments"},
            "mcpjson": {"next-devtools": "repo is not Next.js"},
            "mcp": {"claude.ai Gmail": "repo sends no email", "lab": "infra not used here"},
            "skills": {"almacen-novedades": "belongs to another repo"},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def run_apply(self, decision=None):
        return cs.apply(self.repo, decision or self.decision, home=self.home, backup_root=self.backups)


class ProjectKey(unittest.TestCase):
    def test_uses_forward_slashes_and_is_absolute(self):
        key = cs.project_key(Path("."))
        self.assertNotIn("\\", key)
        self.assertTrue(Path(key).is_absolute())

    def test_variants_include_existing_spellings_and_both_drive_cases(self):
        # Claude Code keys the same repo as "C:/..", "c:/.." and even "C:\\..";
        # which one a session reads depends on how it was launched.
        projects = {"C:\\Users\\X\\Repo": {}, "C:/Users/X/Other": {}}
        got = cs.key_variants(projects, "C:/Users/X/Repo")
        self.assertIn("C:\\Users\\X\\Repo", got)
        self.assertIn("C:/Users/X/Repo", got)
        self.assertIn("c:/Users/X/Repo", got)
        self.assertNotIn("C:/Users/X/Other", got)

    def test_posix_path_has_a_single_variant(self):
        self.assertEqual(cs.key_variants({}, "/home/x/repo"), ["/home/x/repo"])


class Apply(Base):
    def test_disables_each_kind_in_its_own_place(self):
        self.run_apply()
        local = read(self.local)
        self.assertIs(local["enabledPlugins"]["mercadopago@official"], False)
        self.assertIn("next-devtools", local["disabledMcpjsonServers"])
        self.assertEqual(local["skillOverrides"]["almacen-novedades"], "user-invocable-only")
        entry = read(self.claude_json)["projects"][self.key]
        self.assertIn("claude.ai Gmail", entry["disabledMcpServers"])
        self.assertIn("lab", entry["disabledMcpServers"])

    def test_keeps_every_existing_key(self):
        self.run_apply()
        local = read(self.local)
        self.assertEqual(local["permissions"], {"allow": ["Bash(npm test)"]})
        self.assertIs(local["enabledPlugins"]["kept@market"], True)
        cj = read(self.claude_json)
        self.assertEqual(cj["numStartups"], 7)
        self.assertEqual(cj["mcpServers"], {"lab": {"command": "x"}})
        self.assertEqual(cj["projects"][self.key]["allowedTools"], ["Bash"])
        self.assertIn("already-off", cj["projects"][self.key]["disabledMcpServers"])

    def test_writes_every_variant_of_the_project_key(self):
        variants = cs.key_variants({}, self.key)
        if len(variants) < 2:
            self.skipTest("POSIX path: one key only")
        self.run_apply()
        projects = read(self.claude_json)["projects"]
        for k in variants:
            self.assertIn("lab", projects[k]["disabledMcpServers"], k)
        cs.enable(self.repo, "lab", home=self.home)
        projects = read(self.claude_json)["projects"]
        for k in variants:
            self.assertNotIn("lab", projects[k]["disabledMcpServers"], k)

    def test_never_touches_other_projects(self):
        self.run_apply()
        self.assertEqual(read(self.claude_json)["projects"]["C:/other/repo"], {"disabledMcpServers": ["keep-me"]})

    def test_disabled_mcpjson_server_leaves_the_enabled_list(self):
        self.run_apply()
        local = read(self.local)
        self.assertNotIn("next-devtools", local["enabledMcpjsonServers"])
        self.assertIn("21st", local["enabledMcpjsonServers"])

    def test_never_writes_off(self):
        write(self.local, {"skillOverrides": {"old-skill": "off"}})
        self.run_apply()
        values = read(self.local)["skillOverrides"].values()
        self.assertNotIn("off", values)
        self.assertEqual(read(self.local)["skillOverrides"]["old-skill"], "user-invocable-only")

    def test_no_duplicates_when_applied_twice(self):
        self.run_apply()
        self.run_apply()
        entry = read(self.claude_json)["projects"][self.key]["disabledMcpServers"]
        self.assertEqual(len(entry), len(set(entry)))

    def test_creates_files_and_project_entry_when_missing(self):
        self.local.unlink()
        cj = read(self.claude_json)
        del cj["projects"][self.key]
        write(self.claude_json, cj)
        self.run_apply()
        self.assertTrue(self.local.exists())
        self.assertIn("lab", read(self.claude_json)["projects"][self.key]["disabledMcpServers"])

    def test_backup_is_verified_copy_of_both_files(self):
        before_cj = self.claude_json.read_bytes()
        before_local = self.local.read_bytes()
        result = self.run_apply()
        backup = Path(result["backup_dir"])
        self.assertEqual((backup / "claude.json").read_bytes(), before_cj)
        self.assertEqual((backup / "settings.local.json").read_bytes(), before_local)

    def test_ledger_records_reasons(self):
        self.run_apply()
        ledger = read(self.repo / ".claude" / cs.LEDGER_NAME)
        self.assertEqual(ledger["disabled"]["mcp"]["lab"], "infra not used here")
        self.assertIn("backup_dir", ledger)

    def test_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            self.run_apply({"hooks": {"x": "y"}})

    def test_invalid_claude_json_aborts_without_writing(self):
        self.claude_json.write_text("{not json", encoding="utf-8")
        before = self.local.read_bytes()
        with self.assertRaises(ValueError):
            self.run_apply()
        self.assertEqual(self.local.read_bytes(), before)


class Gitignore(Base):
    def test_adds_local_files_to_gitignore(self):
        self.run_apply()
        text = (self.repo / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".claude/settings.local.json", text)
        self.assertIn(".claude/" + cs.LEDGER_NAME, text)

    def test_does_not_duplicate_gitignore_lines(self):
        (self.repo / ".gitignore").write_text("node_modules/\n.claude/settings.local.json\n", encoding="utf-8")
        self.run_apply()
        self.run_apply()
        lines = (self.repo / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines.count(".claude/settings.local.json"), 1)
        self.assertEqual(lines[0], "node_modules/")


class Enable(Base):
    def test_enable_reverses_each_kind(self):
        self.run_apply()
        for name in ["mercadopago@official", "next-devtools", "claude.ai Gmail", "almacen-novedades"]:
            kind = cs.enable(self.repo, name, home=self.home)
            self.assertIsNotNone(kind, name)
        local = read(self.local)
        self.assertNotIn("mercadopago@official", local.get("enabledPlugins", {}))
        self.assertNotIn("next-devtools", local.get("disabledMcpjsonServers", []))
        self.assertNotIn("almacen-novedades", local.get("skillOverrides", {}))
        self.assertNotIn("claude.ai Gmail", read(self.claude_json)["projects"][self.key]["disabledMcpServers"])
        ledger = read(self.repo / ".claude" / cs.LEDGER_NAME)
        self.assertNotIn("claude.ai Gmail", ledger["disabled"]["mcp"])
        self.assertIn("lab", ledger["disabled"]["mcp"])

    def test_enable_unknown_name_returns_none(self):
        self.run_apply()
        self.assertIsNone(cs.enable(self.repo, "nothing-like-this", home=self.home))


class StatusAndRestore(Base):
    def test_status_detects_drift_and_reapply_fixes_it(self):
        self.run_apply()
        cj = read(self.claude_json)
        cj["projects"][self.key]["disabledMcpServers"] = ["already-off"]
        write(self.claude_json, cj)
        st = cs.status(self.repo, home=self.home)
        self.assertEqual(sorted(st["drift"]["mcp"]), ["claude.ai Gmail", "lab"])
        cs.reapply(self.repo, home=self.home, backup_root=self.backups)
        self.assertEqual(cs.status(self.repo, home=self.home)["drift"], {})

    def test_restore_returns_both_files_to_backup(self):
        before_local = read(self.local)
        before_entry = read(self.claude_json)["projects"][self.key]
        self.run_apply()
        cj = read(self.claude_json)
        cj["numStartups"] = 99  # a change made after the apply must survive restore
        write(self.claude_json, cj)
        cs.restore(self.repo, home=self.home)
        self.assertEqual(read(self.local), before_local)
        after = read(self.claude_json)
        self.assertEqual(after["projects"][self.key], before_entry)
        self.assertEqual(after["numStartups"], 99)
        self.assertFalse((self.repo / ".claude" / cs.LEDGER_NAME).exists())

    def test_restore_removes_project_entry_that_did_not_exist(self):
        cj = read(self.claude_json)
        del cj["projects"][self.key]
        write(self.claude_json, cj)
        self.run_apply()
        cs.restore(self.repo, home=self.home)
        self.assertNotIn(self.key, read(self.claude_json)["projects"])

    def test_restore_removes_local_file_that_did_not_exist(self):
        self.local.unlink()
        self.run_apply()
        cs.restore(self.repo, home=self.home)
        self.assertFalse(self.local.exists())


class AtomicWrite(unittest.TestCase):
    def test_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            cs.write_json_atomic(p, {"a": 1})
            self.assertEqual(os.listdir(d), ["x.json"])
            self.assertEqual(read(p), {"a": 1})


if __name__ == "__main__":
    unittest.main()
