#!/usr/bin/env python3
"""Unit and local-server integration tests for roadmap_studio_ctl.py."""

import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import roadmap_studio_ctl as rs  # noqa: E402


SAMPLE_LEGACY_KANBAN = """# Legacy Board

```mermaid
kanban
  triage["Custom Triage"]
    pln04["Explore Caching Layer"]@{ ticket: '[PLN-04]', priority: 'Normal' }
  todo["Todo"]
    tkt10["Build Export Endpoint"]@{ ticket: '[TKT-10]', priority: 'High' }
  in_progress["In Progress"]
    bug02["Fix Startup Crash"]@{ ticket: '[BUG-02]', priority: 'High' }
```
"""


def _http_json(url: str, method: str = "GET", payload: dict = None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=3.0) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


class TestRoadmapStudioCtl(unittest.TestCase):
    def test_init_scaffolds_workspace_and_ps1(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = rs.main(["init", str(root), "--title", "Demo Studio", "--anchor", "DEV"])
            self.assertEqual(rc, 0)

            r_dir = root / ".roadmap"
            self.assertTrue((r_dir / "board.json").exists())
            self.assertTrue((r_dir / "kanban.md").exists())
            self.assertTrue((r_dir / "open.ps1").exists())
            self.assertTrue((r_dir / ".gitignore").exists())
            self.assertTrue((r_dir / "tasks" / "archived").is_dir())
            gi_text = (r_dir / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".server.json", gi_text)
            self.assertIn("tasks/archived/", gi_text)

            board = json.loads((r_dir / "board.json").read_text(encoding="utf-8"))
            self.assertEqual(board["title"], "Demo Studio")
            self.assertEqual(board["anchor"], "DEV")
            self.assertEqual(len(board["columns"]), 6)

            ps1_text = (r_dir / "open.ps1").read_text(encoding="utf-8")
            self.assertIn("$PSScriptRoot", ps1_text)
            self.assertIn("$env:USERPROFILE", ps1_text)
            self.assertNotIn("AlitheiaDeus", ps1_text)

    def test_import_legacy_kanban_and_preserve_custom_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tasks" / "archived").mkdir(parents=True)
            (root / "kanban.md").write_text(SAMPLE_LEGACY_KANBAN, encoding="utf-8")
            (root / "tasks" / "PLN-04.md").write_text(
                "# PLN-04: Explore Caching Layer\n\n- cynefin: complex\n- kano: delighter\n- wardley: genesis\n- visibility: 3\n",
                encoding="utf-8",
            )
            (root / "tasks" / "TKT-10.md").write_text(
                "# TKT-10: Build Export Endpoint\n\nDependencies: PLN-04\n",
                encoding="utf-8",
            )
            (root / "tasks" / "archived" / "TKT-99.md").write_text("# Archived\n", encoding="utf-8")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = rs.main(["import", str(root)])
            self.assertEqual(rc, 0)

            board = rs.load_board(root, enrich=True)
            col_ids = [c["id"] for c in board["columns"]]
            self.assertIn("triage", col_ids)
            by_id = {c["id"]: c for c in board["cards"]}
            self.assertNotIn("TKT-99", by_id)
            self.assertEqual(by_id["PLN-04"]["column"], "triage")
            self.assertEqual(by_id["PLN-04"]["dependents"], ["TKT-10"])
            self.assertEqual(by_id["BUG-02"]["cynefin"], "chaotic")
            self.assertTrue((root / ".roadmap" / "tasks" / "PLN-04.md").exists())
            self.assertIn("AUTO-GENERATED", (root / ".roadmap" / "kanban.md").read_text(encoding="utf-8"))

    def test_import_stdin_semantic_and_cli_wip_archive_export(self):
        synth = {
            "title": "Semantic Board",
            "anchor": "USER",
            "cards": [
                {
                    "id": "FEAT-01",
                    "title": "Auth Guard",
                    "column": "in_progress",
                    "kano": "must_be",
                    "cynefin": "complicated",
                    "wardley": "commodity",
                    "visibility": 2,
                    "spec_markdown": "# FEAT-01: Auth Guard\n\nDetailed spec.\n",
                },
                {
                    "id": "FEAT-02",
                    "title": "HUD Polish",
                    "column": "todo",
                    "dependencies": ["FEAT-01"],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_stdin = sys.stdin
            try:
                sys.stdin = io.StringIO(json.dumps(synth))
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = rs.main(["import", str(root), "--stdin"])
            finally:
                sys.stdin = old_stdin
            self.assertEqual(rc, 0)

            # WIP=1 enforcement blocks moving 2nd card into in_progress without --force
            rc_blocked = rs.main(["move", str(root), "FEAT-02", "in_progress"])
            self.assertNotEqual(rc_blocked, 0)

            # --force overrides WIP=1
            rc_forced = rs.main(["move", str(root), "FEAT-02", "in_progress", "--force"])
            self.assertEqual(rc_forced, 0)

            # Add + validate + archive + export-static
            self.assertEqual(rs.main(["add", str(root), "--id", "TKT-03", "--title", "Extra", "--with-spec"]), 0)
            self.assertEqual(rs.main(["validate", str(root)]), 0)
            self.assertEqual(rs.main(["archive", str(root), "TKT-03"]), 0)
            self.assertTrue((root / ".roadmap" / "tasks" / "archived" / "TKT-03.md").exists())
            self.assertTrue((root / ".roadmap" / "archived.json").exists())

            self.assertEqual(rs.main(["export-static", str(root)]), 0)
            snap = (root / ".roadmap" / "snapshot.html").read_text(encoding="utf-8")
            self.assertIn("FEAT-01", snap)
            self.assertIn('rel="icon"', snap)

    def test_http_server_crud_move_spec_collapse_reuse_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rs.main(["init", str(root), "--title", "HTTP Test"])
            rs.main(["add", str(root), "--id", "TKT-01", "--title", "First Card", "--column", "in_progress", "--with-spec"])
            rs.main(["add", str(root), "--id", "TKT-02", "--title", "Second Card", "--column", "todo"])

            httpd, app, url = rs.start_server(root, port=0, open_browser=False, auto_exit=True, heartbeat_timeout=5.0)
            srv_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            srv_thread.start()

            try:
                # Active server detection
                self.assertEqual(rs._check_existing_server(root), url)

                # GET / returns studio HTML
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(f"{url}/", timeout=3.0) as resp:
                    html_body = resp.read().decode("utf-8")
                self.assertIn("1. Kanban Board", html_body)
                self.assertIn("teleportTo", html_body)

                # GET /api/board
                status, board = _http_json(f"{url}/api/board")
                self.assertEqual(status, 200)
                self.assertEqual(board["total_cards"], 2)

                # UI move into in_progress allows drop and returns wip_warning
                status, move_res = _http_json(
                    f"{url}/api/board/move", "POST", {"id": "TKT-02", "column": "in_progress", "index": 0}
                )
                self.assertEqual(status, 200)
                self.assertIsNotNone(move_res["wip_warning"])

                # Update anchor + collapse column + edit spec
                _http_json(f"{url}/api/board/meta", "POST", {"anchor": "AGENT"})
                _http_json(f"{url}/api/board/columns", "POST", {"id": "frozen", "collapsed": True})
                _http_json(f"{url}/api/card/TKT-01/spec", "POST", {"content": "# Updated Spec\n\nBody text.\n"})
                _, spec_res = _http_json(f"{url}/api/card/TKT-01/spec")
                self.assertIn("Updated Spec", spec_res["content"])

                # Archive via API, inspect /api/archived, and restore via API
                _, arch_res = _http_json(f"{url}/api/card/TKT-02/archive", "POST", {})
                self.assertEqual(arch_res["board"]["total_cards"], 1)
                self.assertEqual(arch_res["board"]["archived_count"], 1)
                _, arch_list = _http_json(f"{url}/api/archived")
                self.assertEqual(len(arch_list["archived"]), 1)
                self.assertEqual(arch_list["archived"][0]["id"], "TKT-02")
                _, rest_res = _http_json(f"{url}/api/card/TKT-02/restore", "POST", {})
                self.assertEqual(rest_res["board"]["total_cards"], 2)
                self.assertEqual(rest_res["board"]["archived_count"], 0)

                # Loose .md file in .roadmap/tasks/archived/ is discovered without archived.json
                (root / ".roadmap" / "tasks" / "archived" / "OLD-07.md").write_text(
                    "# OLD-07: Legacy Archived Item\n", encoding="utf-8"
                )
                _, arch_list2 = _http_json(f"{url}/api/archived")
                self.assertEqual([x["id"] for x in arch_list2["archived"]], ["OLD-07"])
                _, rest_old = _http_json(f"{url}/api/card/OLD-07/restore", "POST", {})
                self.assertEqual(rest_old["board"]["total_cards"], 3)
                self.assertTrue((root / ".roadmap" / "tasks" / "OLD-07.md").exists())

                # Verify persisted deterministic board.json and auto-rendered kanban.md
                persisted = rs.load_board(root, enrich=False)
                self.assertEqual(persisted["anchor"], "AGENT")
                self.assertTrue(next(c for c in persisted["columns"] if c["id"] == "frozen")["collapsed"])
                self.assertIn("AGENT", (root / ".roadmap" / "kanban.md").read_text(encoding="utf-8"))

                # Clean shutdown via /api/shutdown
                _, stop_res = _http_json(f"{url}/api/shutdown", "POST", {})
                self.assertTrue(stop_res["stopping"])
            finally:
                app.shutdown_event.set()
                httpd.shutdown()
                srv_thread.join(timeout=3.0)
                httpd.server_close()

    def test_heartbeat_auto_exit_on_idle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rs.main(["init", str(root)])
            httpd, app, url = rs.start_server(root, port=0, open_browser=False, auto_exit=True, heartbeat_timeout=0.3)
            srv_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            srv_thread.start()
            try:
                status, res = _http_json(f"{url}/api/heartbeat", "POST", {})
                self.assertEqual(status, 200)
                self.assertTrue(res["ok"])
                # Watchdog should trigger shutdown within ~1.2s after heartbeat_timeout expires
                srv_thread.join(timeout=3.0)
                self.assertFalse(srv_thread.is_alive())
            finally:
                app.shutdown_event.set()
                httpd.server_close()

    def test_locate_cat_shelve_consolidate_and_marker_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rs.main(["init", str(root), "--title", "Ergonomics Test"])
            rs.main(["add", str(root), "--id", "TKT-01", "--title", "Active Task", "--column", "todo", "--with-spec"])
            rs.main(["add", str(root), "--id", "TKT-02", "--title", "Done Task", "--column", "completed", "--with-spec"])
            rs.main(["add", str(root), "--id", "PLN-03", "--title", "Parked Idea", "--column", "reported", "--with-spec"])

            # locate & cat on active card
            buf_loc = io.StringIO()
            with redirect_stdout(buf_loc):
                self.assertEqual(rs.main(["locate", str(root), "TKT-01", "--json"]), 0)
            loc_info = json.loads(buf_loc.getvalue())
            self.assertEqual(loc_info["location"], "active")
            self.assertTrue(loc_info["spec_exists"])

            buf_cat = io.StringIO()
            with redirect_stdout(buf_cat):
                self.assertEqual(rs.main(["cat", str(root), "TKT-01"]), 0)
            self.assertIn("TKT-01: Active Task", buf_cat.getvalue())

            # shelve & archive
            self.assertEqual(rs.main(["shelve", str(root), "PLN-03", "--reason", "Out of scope"]), 0)
            self.assertTrue((root / ".roadmap" / "tasks" / "archived" / "shelved" / "PLN-03.md").exists())
            self.assertEqual(rs.main(["archive", str(root), "TKT-02", "--milestone", "v1.0"]), 0)

            # consolidate selected ID into milestone bundle (removes single by default)
            self.assertEqual(rs.main(["consolidate", str(root), "--milestone", "v1.0", "--ids", "TKT-02"]), 0)
            bundle = root / ".roadmap" / "tasks" / "archived" / "milestone_v1_0.md"
            self.assertTrue(bundle.exists())
            self.assertFalse((root / ".roadmap" / "tasks" / "archived" / "TKT-02.md").exists())
            self.assertIn("TKT-02", bundle.read_text(encoding="utf-8"))

            # Marker sync only touches .roadmap/*.md with ROADMAP_STUDIO markers and preserves init theme
            marked = root / ".roadmap" / "custom_view.md"
            marked.write_text(
                "# Custom Header\n\n<!-- ROADMAP_STUDIO:START -->\n```mermaid\n%%{init: {'theme': 'dark'}}%%\nkanban\n```\n<!-- ROADMAP_STUDIO:END -->\n\nFooter\n",
                encoding="utf-8",
            )
            self.assertEqual(rs.main(["sync-md", str(root)]), 0)
            synced_text = marked.read_text(encoding="utf-8")
            self.assertIn("# Custom Header", synced_text)
            self.assertIn("%%{init: {'theme': 'dark'}}%%", synced_text)
            self.assertIn("tkt01[\"Active Task\"]", synced_text)
            self.assertIn("Footer", synced_text)


if __name__ == "__main__":
    unittest.main()
