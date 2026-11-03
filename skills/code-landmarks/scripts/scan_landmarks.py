#!/usr/bin/env python3
"""
scan_landmarks.py - Fast Structural Symbol & Landmark Indexer

Extracts explicit landmark bookmarks ([LANDMARK: ...], [BM: ...]) and
language-native AST/structural symbols (classes, methods, functions, headings)
with exact line ranges (start_line, end_line) for zero-guess file navigation.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

# Regex for manual landmark tags
LANDMARK_REGEX = re.compile(
    r'(?:#|//|<!--|/\*|\*)\s*\[(?P<tag>LANDMARK|BM):\s*(?P<name>[^\]\r\n]+)\]\s*(?P<desc>[^\r\n]*)',
    re.IGNORECASE
)

# Common directories to skip in directory scan mode
IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", "venv", ".venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "target", ".idea", ".vscode"
}


class Node:
    def __init__(self, kind: str, name: str, start_line: int, end_line: int,
                 detail: str = "", indent: int = 0):
        self.kind = kind          # 'LANDMARK', 'CLASS', 'METHOD', 'FUNC', 'HEADING', 'DOC'
        self.name = name.strip()
        self.start_line = start_line
        self.end_line = end_line
        self.detail = detail.strip()
        self.indent = indent
        self.children: List['Node'] = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "detail": self.detail,
            "children": [c.to_dict() for c in self.children]
        }

    def format_line(self) -> str:
        prefix = "  " * self.indent
        lines_badge = f"L{self.start_line}-L{self.end_line}".ljust(12)
        kind_badge = f"[{self.kind}]".ljust(11)
        detail_text = f" - {self.detail}" if self.detail else ""
        return f"{prefix}{lines_badge} : {kind_badge} {self.name}{detail_text}"


class LandmarkScanner:
    def __init__(self, filepath: Path):
        self.path = filepath
        self.content: str = ""
        self.lines: List[str] = []
        self.nodes: List[Node] = []

    def load(self) -> bool:
        if not self.path.exists() or not self.path.is_file():
            return False
        try:
            self.content = self.path.read_text(encoding="utf-8", errors="replace")
            self.lines = self.content.splitlines()
            return True
        except Exception:
            return False

    def scan_manual_landmarks(self) -> List[Node]:
        """Extracts all [LANDMARK: ...] or [BM: ...] comments."""
        landmarks: List[Node] = []
        for idx, line in enumerate(self.lines, start=1):
            m = LANDMARK_REGEX.search(line)
            if m:
                tag = m.group("tag").upper()
                name = m.group("name").strip()
                desc = m.group("desc").strip()
                # If block comment end exists in desc, strip it
                desc = re.sub(r'(-->|\*/)\s*$', '', desc).strip()
                kind = "LANDMARK" if tag == "LANDMARK" else "BM"
                landmarks.append(Node(
                    kind=kind,
                    name=name,
                    start_line=idx,
                    end_line=idx,
                    detail=desc
                ))
        return landmarks

    def scan_python(self) -> List[Node]:
        """Uses Python AST to extract classes, methods, functions, and docstrings."""
        nodes: List[Node] = []
        try:
            tree = ast.parse(self.content, filename=str(self.path))
        except SyntaxError:
            # Fallback to manual landmarks only if syntax error
            return nodes

        # 1. Module docstring
        docstring = ast.get_docstring(tree)
        if docstring and tree.body:
            first_stmt = tree.body[0]
            if isinstance(first_stmt, ast.Expr) and isinstance(first_stmt.value, ast.Constant):
                nodes.append(Node(
                    kind="DOC",
                    name="Module Docstring",
                    start_line=first_stmt.lineno,
                    end_line=getattr(first_stmt, "end_lineno", first_stmt.lineno),
                    detail=docstring.split("\n")[0][:60]
                ))

        # 2. Iterate top-level statements
        for item in tree.body:
            if isinstance(item, ast.ClassDef):
                cls_node = Node(
                    kind="CLASS",
                    name=item.name,
                    start_line=item.lineno,
                    end_line=getattr(item, "end_lineno", item.lineno),
                    indent=0
                )
                # Parse methods inside class
                for sub in item.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_node = Node(
                            kind="METHOD",
                            name=f"{item.name}.{sub.name}",
                            start_line=sub.lineno,
                            end_line=getattr(sub, "end_lineno", sub.lineno),
                            indent=1
                        )
                        cls_node.children.append(method_node)
                nodes.append(cls_node)

            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_kind = "ASYNC_FUNC" if isinstance(item, ast.AsyncFunctionDef) else "FUNC"
                nodes.append(Node(
                    kind=func_kind,
                    name=item.name,
                    start_line=item.lineno,
                    end_line=getattr(item, "end_lineno", item.lineno),
                    indent=0
                ))

            elif isinstance(item, ast.If):
                # Check for if __name__ == '__main__':
                try:
                    if (isinstance(item.test, ast.Compare) and
                        isinstance(item.test.left, ast.Name) and
                        item.test.left.id == "__name__"):
                        nodes.append(Node(
                            kind="ENTRY",
                            name="if __name__ == '__main__'",
                            start_line=item.lineno,
                            end_line=getattr(item, "end_lineno", item.lineno),
                            indent=0
                        ))
                except Exception:
                    pass

        return nodes

    def scan_markdown(self) -> List[Node]:
        """Extracts markdown headings with spans."""
        nodes: List[Node] = []
        heading_re = re.compile(r'^(?P<hashes>#{1,6})\s+(?P<title>.+)$')
        raw_headings: List[Tuple[int, int, str]] = []  # (lineno, level, title)

        for idx, line in enumerate(self.lines, start=1):
            m = heading_re.match(line)
            if m:
                level = len(m.group("hashes"))
                title = m.group("title").strip()
                raw_headings.append((idx, level, title))

        total_lines = len(self.lines)
        for i, (lineno, level, title) in enumerate(raw_headings):
            # End line is line before next heading of equal or lesser level, or EOF
            end_line = total_lines
            for next_line, next_lvl, _ in raw_headings[i + 1:]:
                if next_lvl <= level:
                    end_line = max(lineno, next_line - 1)
                    break

            nodes.append(Node(
                kind=f"H{level}",
                name=title,
                start_line=lineno,
                end_line=end_line,
                indent=max(0, level - 1)
            ))
        return nodes

    def scan_generic_c_style(self) -> List[Node]:
        """Regex-based structural parser for JS, TS, Go, Rust, C/C++, Java."""
        nodes: List[Node] = []
        fn_re = re.compile(
            r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function|class|interface|type)\s+(?P<name>[a-zA-Z0-9_$]+)'
        )
        go_re = re.compile(r'^\s*func\s+(?:\([^)]+\)\s+)?(?P<name>[a-zA-Z0-9_]+)\s*\(')
        rust_re = re.compile(r'^\s*(?:pub\s+)?(?:async\s+)?(?:fn|struct|enum|impl|trait)\s+(?P<name>[a-zA-Z0-9_]+)')

        for idx, line in enumerate(self.lines, start=1):
            # Check function / class
            m = fn_re.match(line) or go_re.match(line) or rust_re.match(line)
            if m:
                name = m.group("name")
                nodes.append(Node(
                    kind="SYMBOL",
                    name=name,
                    start_line=idx,
                    end_line=idx,  # Span estimated to line for regex parser
                    indent=0
                ))
        return nodes

    def scan(self, landmarks_only: bool = False) -> List[Node]:
        manual = self.scan_manual_landmarks()
        if landmarks_only:
            self.nodes = manual
            return self.nodes

        ext = self.path.suffix.lower()
        ast_nodes: List[Node] = []

        if ext == ".py":
            ast_nodes = self.scan_python()
        elif ext in {".md", ".markdown"}:
            ast_nodes = self.scan_markdown()
        elif ext in {".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".c", ".cpp", ".h", ".java"}:
            ast_nodes = self.scan_generic_c_style()

        # Merge manual landmarks with ast_nodes sorted by start_line
        all_nodes = ast_nodes + manual
        all_nodes.sort(key=lambda x: x.start_line)

        self.nodes = all_nodes
        return self.nodes

    def find(self, query: str) -> List[Tuple[Node, Optional[Node]]]:
        """Returns matching nodes. Returns (matching_node, parent_node)."""
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results: List[Tuple[Node, Optional[Node]]] = []

        for parent in self.nodes:
            if pattern.search(parent.name) or pattern.search(parent.detail):
                results.append((parent, None))
            for child in parent.children:
                if pattern.search(child.name) or pattern.search(child.detail):
                    results.append((child, parent))

        return results

    def slice_lines(self, start: int, end: int, context: int = 0) -> str:
        pad_start = max(1, start - context)
        pad_end = min(len(self.lines), end + context)

        output: List[str] = []
        for i in range(pad_start, pad_end + 1):
            marker = " > " if start <= i <= end else "   "
            output.append(f"{i:5d}{marker}{self.lines[i - 1]}")
        return "\n".join(output)


def scan_directory(dir_path: Path) -> List[Tuple[Path, List[Node]]]:
    """Recursively scans directory for manual [LANDMARK: ...] tags."""
    results = []
    for root, dirs, files in os.walk(dir_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for f in files:
            p = Path(root) / f
            if p.suffix.lower() in {".py", ".js", ".ts", ".jsx", ".tsx", ".md", ".go", ".rs", ".c", ".cpp", ".h", ".java", ".sh", ".ps1"}:
                scanner = LandmarkScanner(p)
                if scanner.load():
                    landmarks = scanner.scan_manual_landmarks()
                    if landmarks:
                        results.append((p, landmarks))
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Fast structural symbol and landmark indexer for navigating large codebases."
    )
    parser.add_argument("target", help="File or directory path to inspect")
    parser.add_argument("--find", help="Filter symbols/landmarks matching query string")
    parser.add_argument("--slice", help="Extract code snippet for matching symbol/landmark")
    parser.add_argument("--context", type=int, default=3, help="Context lines around sliced block (default: 3)")
    parser.add_argument("--landmarks-only", action="store_true", help="Only show explicit [LANDMARK: ...] bookmarks")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()
    target_path = Path(args.target).resolve()

    if not target_path.exists():
        print(f"Error: Path '{target_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # 1. Directory Mode
    if target_path.is_dir():
        results = scan_directory(target_path)
        if args.json:
            data = [
                {
                    "file": str(p.relative_to(target_path)),
                    "landmarks": [n.to_dict() for n in nodes]
                }
                for p, nodes in results
            ]
            print(json.dumps(data, indent=2))
            return

        total_landmarks = sum(len(nodes) for _, nodes in results)
        print(f"=== Found {total_landmarks} landmark(s) across {len(results)} file(s) in '{target_path.name}' ===")
        for p, nodes in results:
            rel = p.relative_to(target_path)
            print(f"\n📄 {rel}:")
            for n in nodes:
                print(f"  {n.format_line()}")
        return

    # 2. File Mode
    scanner = LandmarkScanner(target_path)
    if not scanner.load():
        print(f"Error: Unable to read file '{target_path}'.", file=sys.stderr)
        sys.exit(1)

    nodes = scanner.scan(landmarks_only=args.landmarks_only)

    # Mode: Slice Code Snippet
    if args.slice:
        matches = scanner.find(args.slice)
        if not matches:
            print(f"No symbol or landmark matching '{args.slice}' found in {target_path.name}.", file=sys.stderr)
            sys.exit(1)
        node, parent = matches[0]
        header = f"=== Slicing {node.kind} '{node.name}' (L{node.start_line}-L{node.end_line}) ==="
        print(header)
        print(scanner.slice_lines(node.start_line, node.end_line, context=args.context))
        return

    # Mode: Find Query
    if args.find:
        matches = scanner.find(args.find)
        if args.json:
            data = [n.to_dict() for n, _ in matches]
            print(json.dumps(data, indent=2))
            return

        if not matches:
            print(f"No matches found for '{args.find}' in {target_path.name}.")
            return

        print(f"=== Found {len(matches)} match(es) in {target_path.name} ===")
        for node, parent in matches:
            print(f"  {node.format_line()}")
        return

    # Mode: Full TOC / Landmark Index
    if args.json:
        data = {
            "file": str(target_path),
            "lines": len(scanner.lines),
            "symbols": [n.to_dict() for n in nodes]
        }
        print(json.dumps(data, indent=2))
        return

    print(f"=== Landmark & Symbol Map: {target_path.name} ({len(scanner.lines)} lines) ===")
    if not nodes:
        print("  (No structural symbols or landmark comments found)")
        return

    for node in nodes:
        print(node.format_line())
        for child in node.children:
            print(child.format_line())


if __name__ == "__main__":
    main()
