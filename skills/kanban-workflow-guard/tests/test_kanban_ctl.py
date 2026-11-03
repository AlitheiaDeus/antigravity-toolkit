#!/usr/bin/env python3
"""
test_kanban_ctl.py - Unit tests for kanban_ctl.py

Verifies initialization, parsing, card additions, movement, WIP enforcement,
shelving, archiving, and real-world board compatibility.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Add scripts directory to sys.path
import sys
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from kanban_ctl import KanbanBoard, Card, cmd_init, cmd_add, cmd_move, cmd_shelve, cmd_archive


class TestKanbanCtl(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="kanban_test_")
        self.root = Path(self.test_dir)
        self.board = KanbanBoard(self.root)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_init_scaffolding(self):
        """Test init creates valid directory structure and passes validation."""
        class Args:
            title = "Test Scaffolding"
        cmd_init(Args(), self.board)

        self.assertTrue(self.board.kanban_file.exists())
        self.assertTrue(self.board.archive_file.exists())
        self.assertTrue(self.board.tasks_dir.exists())
        self.assertTrue(self.board.backlog_dir.exists())
        self.assertTrue(self.board.archived_dir.exists())
        self.assertTrue(self.board.shelved_dir.exists())

        # Load and validate
        self.assertTrue(self.board.load())
        self.assertEqual(len(self.board.columns), 6)
        issues = self.board.validate()
        self.assertEqual(issues, [])

    def test_add_and_promote(self):
        """Test adding cards to candidate and active columns, and promoting files."""
        class Args:
            title = "Test Board"
        cmd_init(Args(), self.board)
        self.board.load()

        # Add candidate card PLN-01
        self.board.add_card(
            ticket="PLN-01",
            title="Candidate Concept",
            priority="Low",
            inspiration="Idea from flowstate"
        )
        self.board.save()

        # Check file was placed in tasks/backlog/
        self.assertTrue((self.board.backlog_dir / "PLN-01.md").exists())
        self.assertFalse((self.board.tasks_dir / "PLN-01.md").exists())

        # Promote to todo
        success, msg = self.board.move_card("PLN-01", "todo")
        self.assertTrue(success)
        self.board.save()

        # Check file was moved to tasks/
        self.assertFalse((self.board.backlog_dir / "PLN-01.md").exists())
        self.assertTrue((self.board.tasks_dir / "PLN-01.md").exists())

        # Validate board
        issues = self.board.validate()
        self.assertEqual(issues, [])

    def test_wip_limit_enforcement(self):
        """Test that in_progress enforces WIP = 1 unless forced."""
        class Args:
            title = "WIP Test"
        cmd_init(Args(), self.board)
        self.board.load()

        self.board.add_card("TKT-01", "First Task", column="todo")
        self.board.add_card("TKT-02", "Second Task", column="todo")
        self.board.save()

        # Move TKT-01 to in_progress -> should succeed
        success, msg = self.board.move_card("TKT-01", "in_progress")
        self.assertTrue(success)

        # Move TKT-02 to in_progress -> should FAIL due to WIP limit
        success, msg = self.board.move_card("TKT-02", "in_progress")
        self.assertFalse(success)
        self.assertIn("WIP LIMIT REACHED", msg)

        # Force move TKT-02 -> should succeed
        success, msg = self.board.move_card("TKT-02", "in_progress", force=True)
        self.assertTrue(success)

    def test_shelve_anti_burnout(self):
        """Test shelving removes card from board and saves to tasks/archived/shelved/."""
        class Args:
            title = "Shelve Test"
        cmd_init(Args(), self.board)
        self.board.load()

        self.board.add_card("PLN-99", "Wild Idea That Got Dropped", column="reported")
        self.board.save()
        self.assertTrue((self.board.backlog_dir / "PLN-99.md").exists())

        # Shelve it
        success, msg = self.board.shelve_card("PLN-99", reason="Too complex for current milestone")
        self.assertTrue(success)
        self.board.save()

        # Check it is removed from active board
        col, card, _ = self.board.find_card("PLN-99")
        self.assertIsNone(col)

        # Check it was moved to tasks/archived/shelved/
        self.assertTrue((self.board.shelved_dir / "PLN-99.md").exists())
        self.assertFalse((self.board.backlog_dir / "PLN-99.md").exists())

        # Check it was logged to kanban_archive.md
        archive_content = self.board.archive_file.read_text(encoding="utf-8")
        self.assertIn("PLN-99", archive_content)
        self.assertIn("Too complex for current milestone", archive_content)

    def test_archive_completed(self):
        """Test archiving verified card moves to tasks/archived/ and logs milestone."""
        class Args:
            title = "Archive Test"
        cmd_init(Args(), self.board)
        self.board.load()

        self.board.add_card("TKT-42", "ATC Pad Recovery", column="completed", priority="High")
        self.board.save()

        # Archive it with a milestone label
        success, msg = self.board.archive_card("TKT-42", milestone="v1.2-Recovery")
        self.assertTrue(success)
        self.board.save()

        # Verify moved to tasks/archived/
        self.assertTrue((self.board.archived_dir / "TKT-42.md").exists())
        self.assertFalse((self.board.tasks_dir / "TKT-42.md").exists())

        # Verify logged in kanban_archive.md
        archive_content = self.board.archive_file.read_text(encoding="utf-8")
        self.assertIn("TKT-42", archive_content)
        self.assertIn("Milestone: v1.2-Recovery", archive_content)

    def test_preserve_mermaid_theme(self):
        """Test custom %%{init:...}%% theme blocks are preserved during load/save cycles."""
        sample_kanban = """# Themed Board

```mermaid
%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#custom_navy'
  }
}}%%
kanban
  todo["Todo"]
    tkt01["Custom Card"]@{ ticket: '[TKT-01]', priority: 'High' }
```

## Active Glance Index

| Ticket ID | Grade | Title | Operational Inspiration | Spec Document |
| :--- | :--- | :--- | :--- | :--- |
| **`TKT-01`** | `TKT` | Custom Card | Custom inspiration | [TKT-01.md](tasks/TKT-01.md) |
"""
        self.board.kanban_file.write_text(sample_kanban, encoding="utf-8")
        (self.board.tasks_dir).mkdir(parents=True, exist_ok=True)
        (self.board.tasks_dir / "TKT-01.md").write_text("# TKT-01", encoding="utf-8")

        self.assertTrue(self.board.load())
        self.assertEqual(len(self.board.mermaid_theme_lines), 6)
        self.assertIn("'primaryColor': '#custom_navy'", "\n".join(self.board.mermaid_theme_lines))

        # Add a card and save
        self.board.add_card("TKT-02", "Another Card", column="todo")
        self.board.save()

        # Read back raw text
        saved_text = self.board.kanban_file.read_text(encoding="utf-8")
        self.assertIn("'primaryColor': '#custom_navy'", saved_text)
        self.assertIn("tkt02", saved_text)

    def test_clockity_real_world_fixture(self):
        """Test loading real-world kanban board from Clockity using exact fixture."""
        clockity_content = """# Clockity Kanban Board

```mermaid
kanban
  todo["Todo (Active Pipeline)"]
    tkt12["High-Rate vs Zero-Idle HUD Visual Distinction"]@{ ticket: '[TKT-12]', priority: 'Medium' }
  reported["Reported (Backlog Candidates)"]
    pln01["New Ambient Screensavers (Pixel Rain, Lasers, Tetriminos)"]@{ ticket: '[PLN-01]', priority: 'Low' }
    pln02["Modular Settings Windows & Animation Studio"]@{ ticket: '[PLN-02]', priority: 'Low' }
  in_progress["In Progress (WIP = 1)"]
  completed["Completed (Fresh / Review)"]
    tkt09["Off-Screen Horizon for Cyber Grid & Water"]@{ ticket: '[TKT-09]', priority: 'High' }
    tkt10["Warp-Drive Starfield Acceleration & Streaks"]@{ ticket: '[TKT-10]', priority: 'High' }
    tkt11["CRT Barrel Lens Warp & Snow Calibration"]@{ ticket: '[TKT-11]', priority: 'Medium' }
```

## Active Glance Index

| Ticket ID | Grade | Title | Operational Inspiration | Spec Document |
| :--- | :--- | :--- | :--- | :--- |
| **`TKT-09`** | `TKT` | Off-Screen Horizon for Cyber Grid & Water | Zero-hotspot full-screen perspective projection | [TKT-09.md](file:///c:/Users/AlitheiaDeus/DeusLocker/L2C/Clockity/tasks/archived/TKT-09.md) |
| **`TKT-10`** | `TKT` | Warp-Drive Starfield Acceleration & Streaks | Hyperbolic Z-acceleration & speed laser streaks | [TKT-10.md](file:///c:/Users/AlitheiaDeus/DeusLocker/L2C/Clockity/tasks/archived/TKT-10.md) |
| **`TKT-11`** | `TKT` | CRT Barrel Lens Warp & Snow Calibration | Curved glass bulb distortion & contrast floor | [TKT-11.md](file:///c:/Users/AlitheiaDeus/DeusLocker/L2C/Clockity/tasks/archived/TKT-11.md) |
| **`TKT-12`** | `TKT` | High-Rate vs Zero-Idle HUD Visual Distinction | Clear demarcation of 0 Hz sleep vs active RAF | [TKT-12.md](file:///c:/Users/AlitheiaDeus/DeusLocker/L2C/Clockity/tasks/TKT-12.md) |
| **`PLN-01`** | `PLN` | New Ambient Screensavers | Pixel rain, random lasers, rotating tetriminos | [PLN-01.md](file:///c:/Users/AlitheiaDeus/DeusLocker/L2C/Clockity/tasks/backlog/PLN-01.md) |
| **`PLN-02`** | `PLN` | Modular Settings Windows & Animation Studio | Multi-pane tabbed menus & JSON preset backup | [PLN-02.md](file:///c:/Users/AlitheiaDeus/DeusLocker/L2C/Clockity/tasks/backlog/PLN-02.md) |
"""
        self.board.kanban_file.write_text(clockity_content, encoding="utf-8")
        self.assertTrue(self.board.load())

        # Verify columns
        col_ids = [cid for cid, _ in self.board.columns]
        self.assertIn("todo", col_ids)
        self.assertIn("reported", col_ids)
        self.assertIn("in_progress", col_ids)
        self.assertIn("completed", col_ids)

        # Verify card counts
        self.assertEqual(len(self.board.column_cards["todo"]), 1)
        self.assertEqual(self.board.column_cards["todo"][0].ticket, "TKT-12")
        self.assertEqual(len(self.board.column_cards["reported"]), 2)
        self.assertEqual(len(self.board.column_cards["completed"]), 3)
        self.assertEqual(len(self.board.table_rows), 6)

    def test_adhoc_columns(self):
        """Test moving a card to an ad-hoc column dynamically creates it."""
        class Args:
            title = "Adhoc Test"
        cmd_init(Args(), self.board)
        self.board.load()

        self.board.add_card("TKT-55", "Hardware Issue", column="todo")
        self.board.save()

        # Move to ad-hoc 'blocked' column
        success, msg = self.board.move_card("TKT-55", "blocked")
        self.assertTrue(success)
        self.board.save()

        # Verify 'blocked' is now in columns
        col_ids = [cid for cid, _ in self.board.columns]
        self.assertIn("blocked", col_ids)
        self.assertEqual(len(self.board.column_cards["blocked"]), 1)
        self.assertEqual(self.board.column_cards["blocked"][0].ticket, "TKT-55")

    def test_incomplete_metadata_tolerance(self):
        """Test cards without ticket attribute or quotes parse without error."""
        sample_kanban = """# Tolerant Board

```mermaid
kanban
  reported["Reported (Triage)"]
    rep1[Fluid Animation Transitions]@{ priority: 'Low' }
    rep2[Log Drawer Search Tree]
```

## Active Glance Index

| Ticket ID | Grade | Title | Operational Inspiration | Spec Document |
| :--- | :--- | :--- | :--- | :--- |
"""
        self.board.kanban_file.write_text(sample_kanban, encoding="utf-8")
        self.assertTrue(self.board.load())

        cards = self.board.column_cards["reported"]
        self.assertEqual(len(cards), 2)
        # rep1 inferred ticket REP-1 or REP1
        self.assertIn(cards[0].ticket, ["REP-1", "REP1"])
        self.assertEqual(cards[0].priority, "Low")
        self.assertEqual(cards[1].title, "Log Drawer Search Tree")
        self.assertEqual(cards[1].priority, "Normal")



if __name__ == "__main__":
    unittest.main()
