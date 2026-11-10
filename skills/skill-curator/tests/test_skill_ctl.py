#!/usr/bin/env python3
"""
test_skill_ctl.py - Unit tests for skill_ctl.py
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

from skill_ctl import SkillCurator, parse_frontmatter


class TestSkillCtl(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="skill_curator_test_")
        self.root = Path(self.test_dir)
        self.curator = SkillCurator(self.root)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_and_list_skill(self):
        """Test creating a project skill creates valid anatomy and lists it."""
        skill_dir = self.curator.create_skill(
            name="local-builder",
            description="Specialized build runner for local hardware tests."
        )

        self.assertTrue((skill_dir / "SKILL.md").exists())
        self.assertTrue((skill_dir / "scripts").exists())
        self.assertTrue((skill_dir / "tests").exists())

        # List skills
        skills = self.curator.list_skills()
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0]["name"], "local-builder")
        self.assertTrue(skills[0]["has_scripts"])

    def test_audit_catches_issues(self):
        """Test audit detects short description, name mismatch, and path leaks."""
        # 1. Invalid skill: name mismatch + short description
        bad_dir = self.curator.skills_dir / "bad-skill"
        bad_dir.mkdir(parents=True, exist_ok=True)
        (bad_dir / "SKILL.md").write_text(
            "---\nname: different-name\ndescription: short\n---\n# Bad",
            encoding="utf-8"
        )

        issues = self.curator.audit_skill(bad_dir)
        self.assertGreater(len(issues), 0)
        issue_text = " ".join(issues)
        self.assertIn("does not match directory", issue_text)
        self.assertIn("Description is too short", issue_text)

        # 2. Path leak
        leaky_dir = self.curator.skills_dir / "leaky-skill"
        leaky_dir.mkdir(parents=True, exist_ok=True)
        (leaky_dir / "SKILL.md").write_text(
            "---\nname: leaky-skill\ndescription: Valid long description for the leaky skill.\n---\n"
            + "Hardcoded path: C:\\Users\\Developer\\Desktop\n",  # noqa: path-leak
            encoding="utf-8"
        )
        leaky_issues = self.curator.audit_skill(leaky_dir)
        self.assertIn("Leaked hardcoded user profile path", " ".join(leaky_issues))

    def test_promote_skill(self):
        """Test promoting a verified skill to a global directory."""
        skill_dir = self.curator.create_skill(
            name="proven-tool",
            description="A proven workflow ready to be promoted across all projects.",
            with_script=False
        )

        global_mock = self.root / "global_skills"
        global_mock.mkdir()

        success, msg = self.curator.promote_skill("proven-tool", global_mock)
        self.assertTrue(success)
        self.assertTrue((global_mock / "proven-tool" / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
