"""Tests for scripts/inventory.py against a fake home. Calls to the `claude` CLI are
skipped (health=False, and plugins() is stubbed) so the tests run anywhere."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import inventory as inv  # noqa: E402


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Inventory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "home"
        self.parent = root / "work"
        self.repo = self.parent / "repo"
        self.repo.mkdir(parents=True)
        write(self.home / ".claude.json", json.dumps({"mcpServers": {"lab": {}}, "projects": {}}))
        write(self.home / ".mcp.json", json.dumps({"mcpServers": {"from-home": {}}}))
        write(self.parent / ".mcp.json", json.dumps({"mcpServers": {"from-parent": {}}}))
        write(self.home / ".claude" / "settings.json", json.dumps({
            "skillOverrides": {"hidden-one": "user-invocable-only"},
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo hi"}]}]},
        }))
        write(self.home / ".claude" / "greenroom" / "registry.json",
              json.dumps({"families": [{"id": "x", "gate": "my-gate", "skills": []}]}))
        write(self.home / ".claude" / "skills" / "visible-one" / "SKILL.md",
              "---\nname: visible-one\ndescription: >\n  Use when the repo deploys\n  to Workers.\n---\nbody\n")
        write(self.home / ".claude" / "skills" / "hidden-one" / "SKILL.md",
              "---\nname: hidden-one\ndescription: x\n---\n")
        write(self.home / ".claude" / "skills" / "my-gate" / "SKILL.md",
              "---\nname: my-gate\ndescription: gate\n---\n")
        self._orig = inv.plugins
        inv.plugins = lambda repo: []

    def tearDown(self):
        inv.plugins = self._orig
        self.tmp.cleanup()

    def test_multiline_description_is_read_whole(self):
        fm = inv.frontmatter(self.home / ".claude" / "skills" / "visible-one" / "SKILL.md")
        self.assertEqual(fm["description"], "Use when the repo deploys to Workers.")

    def test_skills_flag_hidden_and_gates(self):
        skills = {s["name"]: s for s in inv.inventory(self.repo, home=self.home, health=False)["user_skills"]}
        self.assertTrue(skills["hidden-one"]["already_hidden_globally"])
        self.assertFalse(skills["visible-one"]["already_hidden_globally"])
        self.assertTrue(skills["my-gate"]["greenroom_gate"])

    def test_mcp_servers_come_from_user_parents_and_home(self):
        servers = {s["name"]: s for s in inv.inventory(self.repo, home=self.home, health=False)["mcp_servers"]}
        self.assertEqual(servers["lab"]["kind"], "mcp")
        self.assertEqual(servers["from-parent"]["kind"], "mcpjson")
        self.assertEqual(servers["from-home"]["kind"], "mcpjson")

    def test_hooks_are_listed(self):
        hooks = inv.inventory(self.repo, home=self.home, health=False)["hooks"]
        self.assertEqual(hooks[0]["event"], "SessionStart")

    def test_mcp_list_line_parsing(self):
        m = inv.LINE.match("claude.ai Gmail: https://gmailmcp.googleapis.com/mcp/v1 - \u2714 Connected")
        self.assertEqual(m.group("name"), "claude.ai Gmail")
        m = inv.LINE.match("lab: node C:\\x\\main.js run - \u2298 Disabled for this project (re-enable via /mcp)")
        self.assertEqual(m.group("name"), "lab")
        self.assertIn("Disabled", m.group("status"))

    def test_plugin_details_reads_skills_commands_and_mcp(self):
        root = Path(self.tmp.name) / "plug"
        write(root / ".claude-plugin" / "plugin.json", json.dumps({"description": "does things"}))
        write(root / "skills" / "a" / "SKILL.md", "---\nname: a\ndescription: skill a\n---\n")
        write(root / "commands" / "run.md", "---\ndescription: run it\n---\n")
        write(root / ".mcp.json", json.dumps({"mcpServers": {"srv": {}}}))
        d = inv.plugin_details(root)
        self.assertEqual(d["description"], "does things")
        self.assertEqual(d["skills"][0]["description"], "skill a")
        self.assertEqual(d["commands"][0]["name"], "run")
        self.assertEqual(d["mcp_servers"], ["srv"])


if __name__ == "__main__":
    unittest.main()
