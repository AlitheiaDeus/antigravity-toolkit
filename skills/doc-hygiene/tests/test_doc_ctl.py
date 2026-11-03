#!/usr/bin/env python3
"""
test_doc_ctl.py - Unit tests for doc_ctl.py
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

from doc_ctl import TreeBuilder, GitIgnoreFilter, cmd_tree, cmd_links, cmd_verify


class TestDocCtl(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="doc_hygiene_test_")
        self.root = Path(self.test_dir)

        # Create sample project structure
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
        (self.root / "src" / "utils.py").write_text("def add(a, b): return a + b", encoding="utf-8")
        (self.root / "docs").mkdir()
        (self.root / "docs" / "guide.md").write_text("# Guide", encoding="utf-8")

        # Noise / ignored folders
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "pkg.js").write_text("module.exports = {}", encoding="utf-8")
        (self.root / "temp_cache").mkdir()
        (self.root / "temp_cache" / "cache.bin").write_text("cache", encoding="utf-8")

        # Custom .gitignore
        (self.root / ".gitignore").write_text("temp_cache/\n*.log\n", encoding="utf-8")
        (self.root / "app.log").write_text("error", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_gitignore_and_default_ignores(self):
        """Test default ignore set and custom .gitignore patterns are respected."""
        builder = TreeBuilder(self.root, max_depth=3)
        ascii_tree = builder.render_ascii()

        # Should include real files
        self.assertIn("src/", ascii_tree)
        self.assertIn("main.py", ascii_tree)
        self.assertIn("docs/", ascii_tree)
        self.assertIn("guide.md", ascii_tree)

        # Should NOT include default ignores or gitignored files
        self.assertNotIn("node_modules", ascii_tree)
        self.assertNotIn("temp_cache", ascii_tree)
        self.assertNotIn("app.log", ascii_tree)

    def test_mermaid_tree_view(self):
        """Test rendering Mermaid treeView-beta syntax."""
        builder = TreeBuilder(self.root, max_depth=3)
        mermaid_tree = builder.render_mermaid()

        self.assertIn("```mermaid", mermaid_tree)
        self.assertIn("treeView-beta", mermaid_tree)
        self.assertIn(f'"{self.root.name}"', mermaid_tree)
        self.assertIn('"src"', mermaid_tree)
        self.assertIn('"main.py"', mermaid_tree)
        self.assertTrue(mermaid_tree.strip().endswith("```"))

    def test_inplace_doc_update(self):
        """Test in-place replacement between <!-- TREE_START --> and <!-- TREE_END -->."""
        sample_doc = """# Project Documentation

Welcome to our project.

## Directory Layout
<!-- TREE_START -->
Old stale tree that needs updating
<!-- TREE_END -->

## Getting Started
Follow instructions below.
"""
        doc_file = self.root / "README.md"
        doc_file.write_text(sample_doc, encoding="utf-8")

        class Args:
            dir = str(self.root)
            format = "ascii"
            max_depth = 2
            doc = str(doc_file)
            output = None
            timestamp = False

        cmd_tree(Args())

        updated_content = doc_file.read_text(encoding="utf-8")
        self.assertIn("<!-- TREE_START -->", updated_content)
        self.assertIn("<!-- TREE_END -->", updated_content)
        self.assertNotIn("Old stale tree that needs updating", updated_content)
        self.assertIn("src/", updated_content)
        self.assertIn("## Getting Started", updated_content)

    def test_markdown_link_checker(self):
        """Test detecting valid and broken relative markdown links."""
        # Valid link doc
        valid_doc = self.root / "docs" / "valid.md"
        valid_doc.write_text("See [Guide](guide.md) and [External](https://google.com).", encoding="utf-8")

        class ArgsValid:
            dir = str(self.root / "docs")

        # Should not raise / exit
        cmd_links(ArgsValid())

        # Broken link doc
        broken_doc = self.root / "docs" / "broken.md"
        broken_doc.write_text("See [Missing](non_existent_file.md).", encoding="utf-8")

        class ArgsBroken:
            dir = str(self.root / "docs")

        with self.assertRaises(SystemExit) as cm:
            cmd_links(ArgsBroken())
        self.assertEqual(cm.exception.code, 1)

    def test_verify_target_string(self):
        """Test pre-flight string verification for unique, missing, and duplicate matches."""
        target_file = self.root / "src" / "main.py"
        target_file.write_text("line 1\nunique_function_name()\nline 3\nduplicate\nduplicate\n", encoding="utf-8")

        class ArgsUnique:
            file = str(target_file)
            target = "unique_function_name()"

        # Unique match: should succeed without error
        cmd_verify(ArgsUnique())

        class ArgsMissing:
            file = str(target_file)
            target = "does_not_exist_xyz"

        # Missing match: should exit with code 1
        with self.assertRaises(SystemExit) as cm:
            cmd_verify(ArgsMissing())
        self.assertEqual(cm.exception.code, 1)

        class ArgsDuplicate:
            file = str(target_file)
            target = "duplicate"

        # Duplicate match: should exit with code 1
        with self.assertRaises(SystemExit) as cm:
            cmd_verify(ArgsDuplicate())
        self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
