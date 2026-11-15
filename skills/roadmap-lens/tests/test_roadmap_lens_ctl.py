#!/usr/bin/env python3
"""Unit tests for roadmap_lens_ctl.py."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import roadmap_lens_ctl as rl  # noqa: E402


SAMPLE_KANBAN = """# Project Roadmap

```mermaid
kanban
  reported["Reported (Triage / Ideas)"]
    pln08["Explore Vector Cache"]@{ ticket: '[PLN-08]', priority: 'Normal' }
  frozen["Frozen (Parked)"]
    tlk02["Experimental Audio Theme"]@{ ticket: '[TLK-02]', priority: 'Low' }
  backlog["Backlog"]
    tkt14["Refactor Sync Engine"]@{ ticket: '[TKT-14]', priority: 'High' }
  todo["Todo"]
    tkt22["Add CLI Flag for Matrix"]@{ ticket: '[TKT-22]', priority: 'Normal' }
  in_progress["In Progress"]
    bug06["Fix Crash on Empty Board"]@{ ticket: '[BUG-06]', priority: 'High' }
```
"""


class TestRoadmapLensCtl(unittest.TestCase):
    def _create_sample_repo(self, root: Path, nested_roadmap: bool = False) -> Path:
        base = root / "roadmap" if nested_roadmap else root
        (base / "tasks" / "backlog").mkdir(parents=True, exist_ok=True)
        (base / "tasks" / "archived").mkdir(parents=True, exist_ok=True)

        (base / "kanban.md").write_text(SAMPLE_KANBAN, encoding="utf-8")

        (base / "tasks" / "PLN-08.md").write_text(
            "# PLN-08: Explore Vector Cache\n\n"
            "Dependencies: TKT-14\n"
            "- cynefin: complex\n"
            "- kano: delighter\n"
            "- wardley: genesis\n"
            "- visibility: 3\n",
            encoding="utf-8",
        )
        (base / "tasks" / "TKT-22.md").write_text(
            "# TKT-22: Add CLI Flag for Matrix\n\n"
            "Simple CLI button and flag update.\n"
            "Dependencies: TKT-14\n",
            encoding="utf-8",
        )
        (base / "tasks" / "BUG-06.md").write_text(
            "# BUG-06: Fix Crash on Empty Board\n\n"
            "Urgent crash fix with regression test.\n",
            encoding="utf-8",
        )
        (base / "tasks" / "backlog" / "TKT-14.md").write_text(
            "# TKT-14: Refactor Sync Engine\n\n"
            "Core pipeline engine refactor.\n",
            encoding="utf-8",
        )
        # Archived file must be ignored
        (base / "tasks" / "archived" / "TKT-99.md").write_text(
            "# TKT-99: Archived Old Task\n",
            encoding="utf-8",
        )
        return base

    def test_auto_detect_root_and_roadmap_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root_repo = Path(tmp) / "root_repo"
            root_repo.mkdir()
            self._create_sample_repo(root_repo, nested_roadmap=False)
            base_dir, kanban = rl.detect_kanban_base(root_repo)
            self.assertEqual(base_dir, root_repo)
            self.assertEqual(kanban, root_repo / "kanban.md")

            nested_repo = Path(tmp) / "nested_repo"
            nested_repo.mkdir()
            self._create_sample_repo(nested_repo, nested_roadmap=True)
            base_dir2, kanban2 = rl.detect_kanban_base(nested_repo)
            self.assertEqual(base_dir2, nested_repo / "roadmap")
            self.assertEqual(kanban2, nested_repo / "roadmap" / "kanban.md")

    def test_scout_parsing_tags_heuristics_and_archived_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_sample_repo(root, nested_roadmap=True)

            data = rl.scout_roadmap(root)
            tickets = {c["ticket"]: c for c in data["cards"]}

            self.assertNotIn("TKT-99", tickets)
            self.assertIn("PLN-08", tickets)
            self.assertIn("TKT-22", tickets)
            self.assertIn("BUG-06", tickets)
            self.assertIn("TKT-14", tickets)
            self.assertIn("TLK-02", tickets)

            # Explicit tags honored on PLN-08
            pln = tickets["PLN-08"]
            self.assertEqual(pln["cynefin"], "complex")
            self.assertEqual(pln["kano"], "delighter")
            self.assertEqual(pln["wardley"], "genesis")
            self.assertEqual(pln["visibility"], 3)
            self.assertEqual(pln["recommended_action"], "Spike First")
            self.assertEqual(pln["dependencies"], ["TKT-14"])

            # Heuristics on BUG-06
            bug = tickets["BUG-06"]
            self.assertEqual(bug["cynefin"], "chaotic")
            self.assertEqual(bug["kano"], "must-be")
            self.assertEqual(bug["wardley"], "commodity")
            self.assertEqual(bug["recommended_action"], "Execute Now")
            self.assertTrue(bug["evolving"])

            # Reverse dependency leverage on TKT-14 (depended on by PLN-08 and TKT-22)
            tkt14 = tickets["TKT-14"]
            self.assertEqual(sorted(tkt14["dependents"]), ["PLN-08", "TKT-22"])
            self.assertEqual(tkt14["structural_leverage"], "High")

            # Frozen card should be Hold
            self.assertEqual(tickets["TLK-02"]["recommended_action"], "Hold")

    def test_cli_scout_json_and_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_sample_repo(root, nested_roadmap=False)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = rl.main(["scout", str(root), "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["total_cards"], 5)
            self.assertIn("cynefin", payload["summary"])

            buf_mat = io.StringIO()
            with redirect_stdout(buf_mat):
                rc2 = rl.main(["matrix", str(root)])
            self.assertEqual(rc2, 0)
            matrix_out = buf_mat.getvalue()
            self.assertIn("| Ticket | State | Cynefin Domain |", matrix_out)
            self.assertIn("`PLN-08`", matrix_out)
            self.assertIn("**Spike First**", matrix_out)

    def test_html_generation_and_read_only_guarantee(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._create_sample_repo(root, nested_roadmap=False)
            kanban_before = (root / "kanban.md").read_text(encoding="utf-8")
            out_html = root / "out" / "roadmap_lens.html"

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = rl.main(["html", str(root), "--output", str(out_html)])
            self.assertEqual(rc, 0)
            self.assertTrue(out_html.exists())

            html_text = out_html.read_text(encoding="utf-8")
            # Verify ChromaForge palette tokens & HUD components
            for token in (
                "#0d0c0b",
                "#161412",
                "#f59e0b",
                "#ea580c",
                "#fef3c7",
                "Wardley Value Chain",
                "Cynefin &amp; Kano Triage",
                "Evolution Vectors",
                "[Copy Agent Directive]",
                "PLN-08",
            ):
                self.assertIn(token, html_text)

            # Verify strictly read-only against kanban.md
            kanban_after = (root / "kanban.md").read_text(encoding="utf-8")
            self.assertEqual(kanban_before, kanban_after)

    def test_render_stdin_normalization_and_defaults(self):
        synth_payload = [
            {
                "id": "mod-auth",
                "title": "Auth Token Validator",
                "status": "todo",
                "cynefin": "complicated",
                "kano": "must_be",
                "wardley": "commodity",
                "visibility": 2,
                "dependencies": [],
                "recommended_action": "Execute Now",
                "agent_directive": "Harden [MOD-AUTH] token expiry checks",
            },
            {
                "id": "mod-ui",
                "title": "Dashboard Overview",
                "status": "in_progress",
                "cynefin": "complex",
                "kano": "delighter",
                "wardley": "genesis",
                "visibility": 5,
                "dependencies": ["mod-auth"],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out_html = root / ".agents" / "roadmap_lens.html"
            old_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO(json.dumps(synth_payload))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = rl.main(["render", "--stdin", "--output", str(out_html)])
            finally:
                sys.stdin = old_stdin

            self.assertEqual(rc, 0)
            self.assertTrue(out_html.exists())
            html_text = out_html.read_text(encoding="utf-8")

            # Verify reverse dependents, leverage, and unselected initial state
            self.assertIn("MOD-AUTH", html_text)
            self.assertIn("MOD-UI", html_text)
            self.assertIn('"dependents": ["MOD-UI"]', html_text)
            self.assertIn('"kano": "must-be"', html_text)
            self.assertIn("selectedTicket: null", html_text)
            self.assertIn("MIN_Y_GAP", html_text)

            # Verify parser default --output is .agents/roadmap_lens.html
            args = rl.build_parser().parse_args(["render", "--stdin"])
            self.assertEqual(args.output, ".agents/roadmap_lens.html")
            self.assertFalse(args.open)


if __name__ == "__main__":
    unittest.main()
