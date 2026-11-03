#!/usr/bin/env python3
"""
doc_ctl.py - Unified Documentation Hygiene & File Tree Controller

Capabilities:
  1. tree: Scans directory and renders ASCII, Mermaid treeView-beta, or Markdown trees.
           Supports in-place doc replacement between <!-- TREE_START --> and <!-- TREE_END -->.
  2. links: Crawls Markdown files and verifies relative links resolve to existing files.
  3. verify: Pre-flight check verifying target strings exist and are unique before editing.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import fnmatch
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Set, Tuple, Optional, Dict, Any

DEFAULT_IGNORES = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", "venv", ".venv",
    "env", ".env", "dist", "build", ".pytest_cache", ".idea", ".vscode",
    ".coverage", "htmlcov", ".mypy_cache", ".tox"
}

MARKER_START_RE = re.compile(r'<!--\s*TREE_START\s*-->', re.IGNORECASE)
MARKER_END_RE = re.compile(r'<!--\s*TREE_END\s*-->', re.IGNORECASE)
BLOCK_RE = re.compile(r'(<!--\s*TREE_START\s*-->)(.*?)(<!--\s*TREE_END\s*-->)', re.DOTALL | re.IGNORECASE)
MD_LINK_RE = re.compile(r'\[(?P<text>[^\]]+)\]\((?P<url>[^)]+)\)')


class GitIgnoreFilter:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.patterns: List[str] = []
        self._load_gitignore()

    def _load_gitignore(self):
        gi_file = self.root / ".gitignore"
        if gi_file.exists():
            for line in gi_file.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    self.patterns.append(line)

    def is_ignored(self, path: Path) -> bool:
        name = path.name
        if name in DEFAULT_IGNORES:
            return True

        # Check relative path against gitignore patterns
        try:
            rel = path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            rel = name

        for pat in self.patterns:
            pat_clean = pat.rstrip("/")
            if fnmatch.fnmatch(name, pat_clean) or fnmatch.fnmatch(rel, pat_clean):
                return True
            if pat.endswith("/") and path.is_dir() and (fnmatch.fnmatch(name, pat_clean) or fnmatch.fnmatch(rel, pat_clean)):
                return True
            if fnmatch.fnmatch(rel, f"*/{pat_clean}"):
                return True
        return False


class TreeBuilder:
    def __init__(self, root: Path, max_depth: int = 3):
        self.root = root.resolve()
        self.max_depth = max_depth
        self.gi_filter = GitIgnoreFilter(self.root)

    def _collect(self, dir_path: Path, current_depth: int = 0) -> List[Tuple[Path, bool, int, List[Any]]]:
        if current_depth >= self.max_depth:
            return []

        try:
            entries = sorted(list(dir_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return []

        tree = []
        for p in entries:
            if self.gi_filter.is_ignored(p):
                continue
            is_dir = p.is_dir()
            children = self._collect(p, current_depth + 1) if is_dir else []
            tree.append((p, is_dir, current_depth, children))
        return tree

    def render_ascii(self) -> str:
        lines = [f"{self.root.name}/"]

        def _draw(items: list, prefix: str = ""):
            n = len(items)
            for idx, (path, is_dir, _, children) in enumerate(items):
                is_last = (idx == n - 1)
                connector = "└── " if is_last else "├── "
                display = f"{path.name}/" if is_dir else path.name
                lines.append(f"{prefix}{connector}{display}")
                next_prefix = prefix + ("    " if is_last else "│   ")
                if is_dir and children:
                    _draw(children, next_prefix)

        top_items = self._collect(self.root, 0)
        _draw(top_items)
        return "\n".join(lines)

    def render_mermaid(self) -> str:
        lines = ["```mermaid", "treeView-beta", f'"{self.root.name}"']

        def _draw(items: list, indent_level: int):
            indent = "    " * indent_level
            for path, is_dir, _, children in items:
                lines.append(f'{indent}"{path.name}"')
                if is_dir and children:
                    _draw(children, indent_level + 1)

        top_items = self._collect(self.root, 0)
        _draw(top_items, 1)
        lines.append("```")
        return "\n".join(lines)

    def render_markdown(self) -> str:
        lines = [f"* **{self.root.name}/**"]

        def _draw(items: list, indent_level: int):
            indent = "  " * indent_level
            for path, is_dir, _, children in items:
                display = f"**{path.name}/**" if is_dir else f"`{path.name}`"
                lines.append(f"{indent}* {display}")
                if is_dir and children:
                    _draw(children, indent_level + 1)

        top_items = self._collect(self.root, 0)
        _draw(top_items, 1)
        return "\n".join(lines)

    def render(self, fmt: str = "ascii") -> str:
        fmt = fmt.lower()
        if fmt == "mermaid":
            return self.render_mermaid()
        elif fmt == "markdown":
            return self.render_markdown()
        else:
            return self.render_ascii()


def cmd_tree(args):
    target_dir = Path(args.dir).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"Error: Directory '{target_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    builder = TreeBuilder(target_dir, max_depth=args.max_depth)
    rendered = builder.render(args.format)

    # Prepend timestamp if requested
    if args.timestamp:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rendered = f"<!-- Generated at: {ts} -->\n" + rendered

    # Mode 1: In-place doc replacement between markers
    if args.doc:
        doc_path = Path(args.doc).resolve()
        if not doc_path.exists():
            print(f"Error: Document '{doc_path}' not found.", file=sys.stderr)
            sys.exit(1)

        content = doc_path.read_text(encoding="utf-8")
        if not (MARKER_START_RE.search(content) and MARKER_END_RE.search(content)):
            print(f"Error: Markers '<!-- TREE_START -->' and '<!-- TREE_END -->' not found in '{doc_path.name}'.", file=sys.stderr)
            sys.exit(1)

        # Wrap in clean code fence if ascii format
        replacement_body = rendered
        if args.format == "ascii":
            replacement_body = f"```text\n{rendered}\n```"

        new_content = BLOCK_RE.sub(
            f"\\1\n{replacement_body}\n\\3",
            content
        )
        doc_path.write_text(new_content, encoding="utf-8")
        print(f"[OK] In-place tree updated in {doc_path.name} (Format: {args.format}, Depth: {args.max_depth})")
        return

    # Mode 2: Output to standalone file
    if args.output:
        out_path = Path(args.output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"[OK] Tree saved to {out_path} (Format: {args.format})")
        return

    # Mode 3: Stdout (Direct to AI)
    print(rendered)


def cmd_links(args):
    target_dir = Path(args.dir).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        print(f"Error: Directory '{target_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    gi_filter = GitIgnoreFilter(target_dir)
    md_files: List[Path] = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if not gi_filter.is_ignored(Path(root) / d)]
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() == ".md" and not gi_filter.is_ignored(p):
                md_files.append(p)

    total_links = 0
    broken_links: List[Tuple[Path, int, str, str]] = []  # (doc, lineno, text, url)

    for doc in md_files:
        lines = doc.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx, line in enumerate(lines, start=1):
            for m in MD_LINK_RE.finditer(line):
                url = m.group("url").strip()
                text = m.group("text").strip()

                # Skip external urls or local page anchors
                if url.startswith(("http://", "https://", "mailto:", "#")):
                    continue

                total_links += 1
                # Strip anchor fragment e.g. path/file.md#section
                clean_path = url.split("#")[0].split("?")[0]
                if not clean_path:
                    continue

                # Strip file:/// scheme if present
                if clean_path.lower().startswith("file:///"):
                    clean_path = clean_path[8:]

                # Resolve relative to current doc's directory
                target_file = (doc.parent / clean_path).resolve()
                if not target_file.exists():
                    broken_links.append((doc, idx, text, url))

    rel_root = target_dir.name
    print(f"=== Markdown Link Audit: {rel_root} ===")
    print(f"Scanned {len(md_files)} markdown file(s), checked {total_links} relative link(s).")

    if not broken_links:
        print("[PASS] All relative markdown links resolve to existing files!")
    else:
        print(f"\n[FAIL] Found {len(broken_links)} broken relative link(s):", file=sys.stderr)
        for doc, lineno, text, url in broken_links:
            rel_doc = doc.relative_to(target_dir) if doc.is_relative_to(target_dir) else doc
            print(f"  - {rel_doc}:{lineno} -> [{text}]({url}) [FILE NOT FOUND]", file=sys.stderr)
        sys.exit(1)


def cmd_verify(args):
    target_file = Path(args.file).resolve()
    if not target_file.exists() or not target_file.is_file():
        print(f"[FAIL] Target file '{target_file}' does not exist.", file=sys.stderr)
        sys.exit(1)

    target_str = args.target
    if not target_str:
        print("[FAIL] Target search string is empty.", file=sys.stderr)
        sys.exit(1)

    content = target_file.read_text(encoding="utf-8", errors="replace")
    matches = [m.start() for m in re.finditer(re.escape(target_str), content)]
    count = len(matches)

    if count == 0:
        print(f"[FAIL] Target string NOT found in '{target_file.name}'.", file=sys.stderr)
        sys.exit(1)
    elif count == 1:
        # Find line number of match
        line_num = content[:matches[0]].count("\n") + 1
        print(f"[OK] Unique match verified: Target string found exactly once in '{target_file.name}' at line {line_num}.")
    else:
        lines = [content[:pos].count("\n") + 1 for pos in matches]
        lines_str = ", ".join(f"L{l}" for l in lines)
        print(f"[FAIL] Ambiguous target: Found {count} matches in '{target_file.name}' at lines: {lines_str}.", file=sys.stderr)
        print("Tip: Provide more surrounding context to make the target string unique.", file=sys.stderr)
        sys.exit(1)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Unified Documentation Hygiene & File Tree Controller")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. tree
    p_tree = subparsers.add_parser("tree", help="Generate or update project file tree")
    p_tree.add_argument("dir", nargs="?", default=".", help="Directory to scan (default: CWD)")
    p_tree.add_argument("--format", choices=["ascii", "mermaid", "markdown"], default="ascii", help="Tree format (default: ascii)")
    p_tree.add_argument("--max-depth", type=int, default=3, help="Max recursion depth (default: 3)")
    p_tree.add_argument("--doc", help="Target markdown file for in-place update between <!-- TREE_START --> and <!-- TREE_END -->")
    p_tree.add_argument("--output", help="Save tree output to standalone file")
    p_tree.add_argument("--timestamp", action="store_true", help="Add timestamp header")

    # 2. links
    p_links = subparsers.add_parser("links", help="Verify relative markdown links resolve on disk")
    p_links.add_argument("dir", nargs="?", default=".", help="Directory to scan (default: CWD)")

    # 3. verify
    p_verify = subparsers.add_parser("verify", help="Pre-flight check verifying target strings exist and are unique")
    p_verify.add_argument("file", help="File to inspect")
    p_verify.add_argument("--target", required=True, help="Exact string snippet to search for")

    args = parser.parse_args()

    if args.command == "tree":
        cmd_tree(args)
    elif args.command == "links":
        cmd_links(args)
    elif args.command == "verify":
        cmd_verify(args)


if __name__ == "__main__":
    main()
