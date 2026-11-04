#!/usr/bin/env python3
"""
test_scratch_ctl.py - Unit tests for scratch_ctl.py

Verifies scanning heuristics, cataloging, header injection, phonebook generation,
and ephemeral trash purging.
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

from scratch_ctl import ScratchCurator


class TestScratchCtl(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="scratch_test_")
        self.root = Path(self.test_dir)
        self.curator = ScratchCurator(self.root)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_scan_classification(self):
        """Test scanning accurately separates trash from reusable debug scripts and ignores standard code."""
        # 1. Standard project files (should be ignored)
        (self.root / "main.py").write_text("print('hello')", encoding="utf-8")
        (self.root / "setup.py").write_text("# setup", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_main.py").write_text("# legitimate test", encoding="utf-8")

        # 2. Ephemeral trash
        (self.root / "temp_cache.tmp").write_text("trash", encoding="utf-8")
        (self.root / "dump_state.json").write_text("{}", encoding="utf-8")
        (self.root / "scratch_notes.txt").write_text("notes", encoding="utf-8")

        # 3. Ad-hoc debug scripts
        (self.root / "debug_kinematics.py").write_text("import math", encoding="utf-8")
        (self.root / "probe_rf.ps1").write_text("Write-Host 'probe'", encoding="utf-8")
        (self.root / "test_adhoc_quick.py").write_text("assert True", encoding="utf-8")

        items = self.curator.scan()
        item_names = {i.path.name: i.item_type for i in items}

        # Verify standard files ignored
        self.assertNotIn("main.py", item_names)
        self.assertNotIn("setup.py", item_names)
        self.assertNotIn("test_main.py", item_names)

        # Verify trash classified correctly
        self.assertEqual(item_names.get("temp_cache.tmp"), "trash")
        self.assertEqual(item_names.get("dump_state.json"), "trash")
        self.assertEqual(item_names.get("scratch_notes.txt"), "trash")

        # Verify scripts classified correctly
        self.assertEqual(item_names.get("debug_kinematics.py"), "script")
        self.assertEqual(item_names.get("probe_rf.ps1"), "script")
        self.assertEqual(item_names.get("test_adhoc_quick.py"), "script")

    def test_catalog_script_and_phonebook(self):
        """Test cataloging moves script, injects metadata header, and generates phonebook."""
        test_script = self.root / "debug_atc.py"
        test_script.write_text("def run_debug(): pass\nrun_debug()\n", encoding="utf-8")

        success, msg = self.curator.catalog(
            test_script,
            ticket="BUG-42",
            purpose="Verify ATC recovery timing"
        )
        self.assertTrue(success)

        # Check source was moved
        self.assertFalse(test_script.exists())

        # Check destination file
        dest_file = self.curator.scratch_dir / "debug_atc.py"
        self.assertTrue(dest_file.exists())

        # Check injected header
        content = dest_file.read_text(encoding="utf-8")
        self.assertIn("[SCRATCH ARTIFACT]", content)
        self.assertIn("Ticket   : BUG-42", content)
        self.assertIn("Purpose  : Verify ATC recovery timing", content)
        self.assertIn("def run_debug(): pass", content)

        # Check Phonebook was created and indexed
        phonebook = self.curator.phonebook_file
        self.assertTrue(phonebook.exists())
        pb_content = phonebook.read_text(encoding="utf-8")
        self.assertIn("debug_atc.py", pb_content)
        self.assertIn("BUG-42", pb_content)
        self.assertIn("Verify ATC recovery timing", pb_content)

    def test_catalog_preserves_shebang(self):
        """Test cataloging preserves shebang on line 1."""
        script_with_shebang = self.root / "probe_tool.py"
        script_with_shebang.write_text("#!/usr/bin/env python3\nprint('probing')\n", encoding="utf-8")

        success, _ = self.curator.catalog(script_with_shebang, ticket="PROBE-01", purpose="Shebang check")
        self.assertTrue(success)

        dest_file = self.curator.scratch_dir / "probe_tool.py"
        lines = dest_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "#!/usr/bin/env python3")
        self.assertIn("[SCRATCH ARTIFACT]", "\n".join(lines[:4]))

    def test_purge_ephemeral_trash(self):
        """Test purge deletes ephemeral files and honors dry-run."""
        trash1 = self.root / "temp_file.tmp"
        trash2 = self.root / "dump_data.json"
        trash1.write_text("junk", encoding="utf-8")
        trash2.write_text("{}", encoding="utf-8")

        # 1. Dry run -> should NOT delete
        dry_deleted = self.curator.purge_trash(dry_run=True)
        self.assertEqual(len(dry_deleted), 2)
        self.assertTrue(trash1.exists())
        self.assertTrue(trash2.exists())

        # 2. Actual purge -> deletes files
        deleted = self.curator.purge_trash(dry_run=False)
        self.assertEqual(len(deleted), 2)
        self.assertFalse(trash1.exists())
        self.assertFalse(trash2.exists())


if __name__ == "__main__":
    unittest.main()
