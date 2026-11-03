#!/usr/bin/env python3
"""
test_git_sanitize_check.py - Unit tests for git_sanitize_check.py
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

from git_sanitize_check import (
    audit_gitignore,
    fix_gitignore,
    scan_for_path_leaks,
    scan_for_secrets
)


class TestGitSanitizeCheck(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="git_sanitize_test_")
        self.root = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_audit_and_fix_gitignore(self):
        """Test detecting missing gitignore rules and auto-fixing them."""
        # Initially empty gitignore
        gi_file = self.root / ".gitignore"
        gi_file.write_text("# Initial\nbuild/\n", encoding="utf-8")

        clean, missing = audit_gitignore(self.root)
        self.assertFalse(clean)
        self.assertGreater(len(missing), 0)

        # Fix it
        fix_gitignore(self.root)

        # Audit again
        clean_after, missing_after = audit_gitignore(self.root)
        self.assertTrue(clean_after)
        self.assertEqual(len(missing_after), 0)

        content = gi_file.read_text(encoding="utf-8")
        self.assertIn("internal/", content)
        self.assertIn("scratch/", content)
        self.assertIn(".env", content)

    def test_detect_path_leaks(self):
        """Test detecting hardcoded user profile paths."""
        leaky_content = """# Config
path = "C:\\Users\\JohnDoe\\Documents\\secret"
portable_path = os.environ.get("HOME")
linux_path = "/home/developer/workspace/app"
"""
        p = self.root / "config.py"
        files = [(p, leaky_content)]

        issues = scan_for_path_leaks(files, current_user="JohnDoe")
        self.assertEqual(len(issues), 2)
        descs = [iss[2] for iss in issues]
        self.assertIn("Windows user profile path", descs)
        self.assertIn("Unix/macOS home directory path", descs)

    def test_detect_secrets(self):
        """Test detecting API keys and staged .env files."""
        secret_content = """
GOOGLE_KEY = "AIzaSyD-1234567890abcdefghijklmnopqrst"
GITHUB_TOKEN = "ghp_123456789012345678901234567890123456"
"""
        p = self.root / "secrets.py"
        files = [(p, secret_content)]

        issues = scan_for_secrets(files)
        self.assertEqual(len(issues), 2)

        # Test .env file detection
        env_file = self.root / ".env"
        env_files = [(env_file, "DATABASE_URL=postgres://...")]
        env_issues = scan_for_secrets(env_files)
        self.assertEqual(len(env_issues), 1)
        self.assertEqual(env_issues[0][2], "Staged Environment Secret File")


if __name__ == "__main__":
    unittest.main()
