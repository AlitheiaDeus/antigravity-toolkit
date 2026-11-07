#!/usr/bin/env python3
"""
deslop_ctl.py - Antigravity Code De-Slop & Grounding Engine

Deterministic static analysis tool for detecting AI enterprise foam,
conversational chat debris, defensive panic wrappers, hollow abstractions,
and context-destroying meme variables, while actively protecting sacred
StackOverflow copypasta and battle-tested platform hacks.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, NamedTuple

# ---------------------------------------------------------------------------
# Regex Patterns & Heuristics
# ---------------------------------------------------------------------------

# Chat debris leaked from LLM conversation turns
CHAT_DEBRIS_PATTERNS = [
    (re.compile(r'(?i)#\s*(?:fixed|updated|refactored|modified|changed)\b.*?(?:for you|as requested|per your (?:request|instructions?)|as discussed)\b'),
     "Leaked assistant conversation turn ('Fixed this for you / as requested')"),
    (re.compile(r'(?i)#\s*(?:as requested|per your instructions?|as you asked|as per user request)\b'),
     "Leaked assistant acknowledgment ('As requested')"),
    (re.compile(r'(?i)#\s*(?:look here|see here|note to user|here is the fix)\b'),
     "Direct assistant chat pointer left in comments"),
    (re.compile(r'(?i)#\s*I\s+(?:have\s+)?(?:turned|rotated|aligned|added|removed|replaced|changed|fixed|created)\b.*?\bas\s+requested\b'),
     "First-person assistant action confession ('I turned this as requested')"),
    (re.compile(r'(?i)#\s*Step\s+\d+:\s*(?:First|Next|Then|Finally|Now)\s+we\s+'),
     "Textbook tutorial walkthrough commentary in production logic"),
]

# Sacred Copypasta / Chesterton's Fences (DO NOT TOUCH)
SACRED_FENCE_PATTERNS = [
    (re.compile(r'https?://(?:www\.)?stackoverflow\.com/(?:a|questions)/\d+'),
     "Direct StackOverflow citation - likely battle-tested edge case fix"),
    (re.compile(r'https?://github\.com/[^/]+/[^/]+/(?:issues|pull)/\d+'),
     "Upstream bug tracker reference - specific regression workaround"),
    (re.compile(r'(?i)#\s*(?:workaround for|hack for|bug in|quirk in|patch for)\s+[a-zA-Z0-9_\-\.]+'),
     "Explicit documented platform/library workaround"),
    (re.compile(r'\bctypes\.(?:windll|cdll|oledll)\b'),
     "Low-level Win32/C dynamic library binding"),
    (re.compile(r'\b(?:FILE_ATTRIBUTE_|IOCTL_|win32con|WSADATA|SO_REUSEADDR)\b'),
     "Platform-specific system or socket level constant"),
]

# Meme / Brainrot / Cryptic Variable Names (Poisons LLM Semantic Attention)
MEME_VARIABLE_PATTERNS = [
    (re.compile(r'(?i)\b[a-z0-9_]*(?:yeet|yolo|skibidi|sigma|bruh|cursed|magic_stuff|spooky|brainfuck|sus_|imposter)[a-z0-9_]*\b'),
     "Meme / in-joke identifier blinding AI semantic context"),
    (re.compile(r'(?i)\b[a-z0-9_]*(?:tmp_hack|dont_touch_this|fix_later_pls|wtf_val|omg_fix)[a-z0-9_]*\b'),
     "Context-depleted frustration marker"),
]

# Hyper-Verbose AI Enterprise Identifiers
MAX_IDENTIFIER_LEN = 35


class SlopFinding(NamedTuple):
    finding_id: str
    category: str
    file_path: str
    line_num: int
    snippet: str
    explanation: str
    recommendation: str
    suggested_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.finding_id,
            "category": self.category,
            "file": self.file_path,
            "line": self.line_num,
            "snippet": self.snippet.strip(),
            "explanation": self.explanation,
            "recommendation": self.recommendation,
            "suggested_name": self.suggested_name
        }


# ---------------------------------------------------------------------------
# AST Python Analysis Engine
# ---------------------------------------------------------------------------

class PythonSlopVisitor(ast.NodeVisitor):
    def __init__(self, rel_path: str, source_lines: List[str], counters: Optional[Dict[str, int]] = None):
        self.rel_path = rel_path
        self.source_lines = source_lines
        self.findings: List[SlopFinding] = []
        self._counters = counters if counters is not None else {}

    def _next_id(self, prefix: str) -> str:
        curr = self._counters.get(prefix, 1)
        self._counters[prefix] = curr + 1
        return f"[{prefix}-{curr:02d}]"

    def _get_line_snippet(self, line_num: int) -> str:
        if 1 <= line_num <= len(self.source_lines):
            return self.source_lines[line_num - 1]
        return ""

    def visit_ClassDef(self, node: ast.ClassDef):
        # 1. Check for empty custom exceptions (e.g. class FooError(Exception): pass)
        is_exc = any(
            isinstance(b, ast.Name) and "Exception" in b.id or "Error" in getattr(b, "id", "")
            for b in node.bases
        ) or node.name.endswith("Error") or node.name.endswith("Exception")

        if is_exc:
            body_statements = [
                s for s in node.body
                if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))  # ignore docstring
            ]
            if len(body_statements) == 1 and isinstance(body_statements[0], ast.Pass):
                self.findings.append(SlopFinding(
                    finding_id=self._next_id("AI-EXC"),
                    category="AI_EMPTY_EXCEPTION",
                    file_path=self.rel_path,
                    line_num=node.lineno,
                    snippet=self._get_line_snippet(node.lineno),
                    explanation=f"Empty custom exception '{node.name}' with only 'pass'. Adds architectural weight without behavior.",
                    recommendation="REPLACE_WITH_STDLIB: Use standard ValueError, RuntimeError, or KeyError."
                ))

        # 2. Check for Single-Method Classes (classic enterprise OOP inflation)
        # Class with only __init__ and 1 method, or just 1 method total, without complex inheritance
        is_record = any(
            (isinstance(b, ast.Name) and b.id in ("NamedTuple", "dict", "tuple")) or
            (isinstance(b, ast.Attribute) and b.attr in ("NamedTuple", "dataclass"))
            for b in node.bases
        ) or any(
            (isinstance(d, ast.Name) and d.id == "dataclass") or
            (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "dataclass")
            for d in node.decorator_list
        )

        methods = [m for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
        non_init_methods = [m for m in methods if m.name != "__init__"]

        if len(methods) > 0 and len(non_init_methods) == 1 and len(node.bases) <= 1 and not is_record:
            # Check if it has state attributes or is basically a glorified function
            method_name = non_init_methods[0].name
            if not node.name.startswith("Test"):  # Ignore unittest classes
                self.findings.append(SlopFinding(
                    finding_id=self._next_id("AI-CLASS"),
                    category="AI_SINGLE_METHOD_CLASS",
                    file_path=self.rel_path,
                    line_num=node.lineno,
                    snippet=self._get_line_snippet(node.lineno),
                    explanation=f"Class '{node.name}' only contains one real method ('{method_name}'). Enterprise OOP theater.",
                    recommendation=f"COLLAPSE: Convert '{node.name}.{method_name}' into a standalone top-level function."
                ))

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node):
        # 1. Tautological Docstring Check
        doc = ast.get_docstring(node)
        if doc:
            clean_doc = doc.strip().lower().rstrip(".").replace("_", " ")
            clean_name = node.name.lower().replace("_", " ")
            # If docstring is literally just the function name or "get x for x"
            if clean_doc == clean_name or clean_doc == f"get {clean_name}" or clean_doc == f"returns {clean_name}":
                self.findings.append(SlopFinding(
                    finding_id=self._next_id("AI-TAUT"),
                    category="AI_TAUTOLOGY",
                    file_path=self.rel_path,
                    line_num=node.lineno,
                    snippet=f'"""{doc.strip()}"""',
                    explanation=f"Tautological docstring on '{node.name}' simply restates the function name without adding context.",
                    recommendation="DELETE_DOCSTRING: Remove or replace with actual domain intent / constraints."
                ))

        # 2. Check for One-Shot 1-line wrapper functions
        # e.g., def read_file(p): return Path(p).read_text()
        non_doc_body = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        if len(non_doc_body) == 1 and isinstance(non_doc_body[0], ast.Return):
            ret_val = non_doc_body[0].value
            if isinstance(ret_val, ast.Call):
                self.findings.append(SlopFinding(
                    finding_id=self._next_id("AI-WRAP"),
                    category="AI_ONE_SHOT_WRAPPER",
                    file_path=self.rel_path,
                    line_num=node.lineno,
                    snippet=self._get_line_snippet(node.lineno),
                    explanation=f"Function '{node.name}' is a 1-line wrapper around a single call. Adds unnecessary indirection.",
                    recommendation="INLINE: Inline directly at callsite unless serving as a stable public API."
                ))

    def visit_Try(self, node: ast.Try):
        # Check for panic blocks: `except Exception: pass` or `except: pass`
        for handler in node.handlers:
            is_bare_or_generic = (
                handler.type is None or
                (isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException"))
            )
            if is_bare_or_generic:
                # Check if body is just pass or returns None
                body_is_silent = False
                if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                    body_is_silent = True
                elif len(handler.body) == 1 and isinstance(handler.body[0], ast.Return):
                    if handler.body[0].value is None or (isinstance(handler.body[0].value, ast.Constant) and handler.body[0].value.value is None):
                        body_is_silent = True

                if body_is_silent:
                    self.findings.append(SlopFinding(
                        finding_id=self._next_id("AI-PANIC"),
                        category="AI_PANIC_BLOCK",
                        file_path=self.rel_path,
                        line_num=handler.lineno,
                        snippet=self._get_line_snippet(handler.lineno),
                        explanation="Generic exception swallowed silently with 'pass' or 'return None'. Masks root-cause bugs.",
                        recommendation="FAIL_LOUD: Catch specific exception or allow it to propagate with readable error."
                    ))
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        name = node.id
        # AI verbose identifier check
        if len(name) > MAX_IDENTIFIER_LEN and "_" in name:
            self.findings.append(SlopFinding(
                finding_id=self._next_id("AI-NAME"),
                category="AI_VERBOSE_NAME",
                file_path=self.rel_path,
                line_num=node.lineno,
                snippet=name,
                explanation=f"Overly verbose identifier '{name}' ({len(name)} chars). Enterprise boilerplate style.",
                recommendation="GROUND_NAME: Condense to a concise, direct domain term."
            ))
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# File & Line Scanner (Regex & Sacred Fence Detection)
# ---------------------------------------------------------------------------

def scan_text_lines(rel_path: str, lines: List[str], counters: Optional[Dict[str, int]] = None) -> List[SlopFinding]:
    findings: List[SlopFinding] = []
    if counters is None:
        counters = {}

    def next_id(prefix: str) -> str:
        curr = counters.get(prefix, 1)
        counters[prefix] = curr + 1
        return f"[{prefix}-{curr:02d}]"

    for idx, line in enumerate(lines, start=1):
        # 1. Sacred Copypasta & Chesterton's Fences
        for pat, desc in SACRED_FENCE_PATTERNS:
            if pat.search(line):
                findings.append(SlopFinding(
                    finding_id=next_id("KEEP-FENCE"),
                    category="SACRED_FENCE",
                    file_path=rel_path,
                    line_num=idx,
                    snippet=line,
                    explanation=f"{desc}. Battle-tested pragmatic logic.",
                    recommendation="KEEP_UNTOUCHED: Do not simplify or sanitize away this workaround."
                ))
                break  # Only one fence tag per line

        # 2. Chat Debris / Leaked Conversation Turns
        for pat, desc in CHAT_DEBRIS_PATTERNS:
            if pat.search(line):
                findings.append(SlopFinding(
                    finding_id=next_id("AI-CHAT"),
                    category="AI_CHAT_DEBRIS",
                    file_path=rel_path,
                    line_num=idx,
                    snippet=line,
                    explanation=f"{desc}. Conversational artifact left behind by AI.",
                    recommendation="DELETE: Remove this comment completely."
                ))
                break

        # 3. Meme / Brainrot Identifiers
        for pat, desc in MEME_VARIABLE_PATTERNS:
            match = pat.search(line)
            if match:
                matched_word = match.group(0)
                findings.append(SlopFinding(
                    finding_id=next_id("HUMAN-MEME"),
                    category="HUMAN_MEME",
                    file_path=rel_path,
                    line_num=idx,
                    snippet=line,
                    explanation=f"{desc} (Found '{matched_word}'). Breaks agent semantic attention.",
                    recommendation="RENAME: Replace with a grounded, greppable domain identifier."
                ))
                break

    return findings


def scan_file(file_path: Path, root_path: Path, counters: Optional[Dict[str, int]] = None) -> List[SlopFinding]:
    if counters is None:
        counters = {}
    rel_path = file_path.relative_to(root_path).as_posix()
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return []

    lines = content.splitlines()
    findings = scan_text_lines(rel_path, lines, counters=counters)

    # If Python, run AST checks
    if file_path.suffix == ".py":
        try:
            tree = ast.parse(content, filename=str(file_path))
            visitor = PythonSlopVisitor(rel_path, lines, counters=counters)
            visitor.visit(tree)
            findings.extend(visitor.findings)
        except SyntaxError:
            pass  # Leave unparseable files to text scanner

    # Sort by line number
    findings.sort(key=lambda f: f.line_num)
    return findings


def scan_path(target: Path, exclude_dirs: Optional[Set[str]] = None, include_tests: bool = False) -> List[SlopFinding]:
    if exclude_dirs is None:
        exclude_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache", ".gemini"}
        if not include_tests:
            exclude_dirs.update({"tests", "test"})

    counters: Dict[str, int] = {}
    findings: List[SlopFinding] = []
    if target.is_file():
        return scan_file(target, target.parent, counters=counters)

    root = target.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        # Exclude directories in-place
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for fname in sorted(filenames):
            ext = Path(fname).suffix.lower()
            if ext in {".py", ".js", ".ts", ".jsx", ".tsx", ".sh", ".ps1", ".rs", ".go"}:
                fpath = Path(dirpath) / fname
                findings.extend(scan_file(fpath, root, counters=counters))

    return findings


# ---------------------------------------------------------------------------
# Safety Fork Engine
# ---------------------------------------------------------------------------

def run_safety_fork(target_dir: Path) -> Dict[str, Any]:
    """Provisions an isolated Git backup branch or filesystem backup before unslop."""
    ts = int(time.time())
    branch_name = f"deslop-backup-{ts}"

    # Check if target is inside a git repo
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(target_dir),
            capture_output=True,
            text=True
        )
        is_git = res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        is_git = False

    if is_git:
        # Check current branch
        curr = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(target_dir),
            capture_output=True,
            text=True
        ).stdout.strip()

        # Create safety branch without switching HEAD (or stash if preferred)
        create_branch = subprocess.run(
            ["git", "branch", branch_name],
            cwd=str(target_dir),
            capture_output=True,
            text=True
        )

        return {
            "mode": "git_branch",
            "backup_branch": branch_name,
            "current_branch": curr,
            "message": f"Created safety Git branch '{branch_name}'. Current branch remains '{curr}'."
        }
    else:
        # Non-git folder: create local snapshot directory
        backup_dir = target_dir / f".deslop_backup_{ts}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for item in target_dir.iterdir():
            if item.name.startswith(".deslop_backup_"):
                continue
            if item.is_file():
                shutil.copy2(item, backup_dir / item.name)
                count += 1

        return {
            "mode": "fs_copy",
            "backup_dir": str(backup_dir),
            "files_copied": count,
            "message": f"Created filesystem backup in '{backup_dir.name}' ({count} files copied)."
        }


# ---------------------------------------------------------------------------
# Surgical Strip / Clean Engine
# ---------------------------------------------------------------------------

def strip_chat_debris(file_path: Path) -> Tuple[int, str]:
    """Safely strips out lines matching chat debris comments."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return 0, f"Failed to read {file_path}: {e}"

    lines = content.splitlines(keepends=True)
    new_lines = []
    removed = 0

    for line in lines:
        is_debris = False
        for pat, _ in CHAT_DEBRIS_PATTERNS:
            if pat.search(line):
                is_debris = True
                break
        if is_debris:
            removed += 1
        else:
            new_lines.append(line)

    if removed > 0:
        cleaned_content = "".join(new_lines)
        # If python file, verify AST parses cleanly
        if file_path.suffix == ".py":
            try:
                ast.parse(cleaned_content, filename=str(file_path))
            except SyntaxError as e:
                return 0, f"Syntax verification failed after strip: {e}"

        file_path.write_text(cleaned_content, encoding="utf-8")

    return removed, f"Stripped {removed} conversational debris comment(s)."


# ---------------------------------------------------------------------------
# Report Formatting (Text, JSON, Markdown)
# ---------------------------------------------------------------------------

def generate_markdown_report(findings: List[SlopFinding], target_path: str) -> str:
    ai_slop = [f for f in findings if f.category.startswith("AI_")]
    human_slop = [f for f in findings if f.category.startswith("HUMAN_")]
    sacred_fences = [f for f in findings if f.category == "SACRED_FENCE"]

    total = len(findings)
    ai_pct = int((len(ai_slop) / total) * 100) if total else 0
    human_pct = int((len(human_slop) / total) * 100) if total else 0
    fence_pct = int((len(sacred_fences) / total) * 100) if total else 0

    lines = [
        "# 🧹 Code De-Slop & Grounding Audit Report",
        "",
        f"> **Target**: `{target_path}`  ",
        f"> **Total Audit Markers**: {total}  ",
        f"> **Profile**: {ai_pct}% AI Enterprise Foam | {human_pct}% Human Chaos | {fence_pct}% Sacred Duct Tape  ",
        "",
        "---",
        "",
        "## 1. Executive Summary & Complexity Assessment",
        "",
    ]

    if total == 0:
        lines.append("🎉 **Zero slop detected!** The codebase is well-grounded, idiomatic, and free of conversational debris.")
        return "\n".join(lines)

    lines.extend([
        f"- **AI Enterprise Foam ({len(ai_slop)} items)**: Unnecessary wrapper classes, empty exceptions, tautological docstrings, or panic blocks.",
        f"- **Human Chaos & Semantic Anomaly ({len(human_slop)} items)**: Meme identifiers or context-depleted variable names that blind AI semantic retrieval.",
        f"- **Sacred Fences ({len(sacred_fences)} items)**: StackOverflow copypasta, platform workarounds, or low-level hooks. **Recommended to KEEP.**",
        "",
        "---",
        "",
        "## 2. Sacred Fences & Battle-Tested Hacks (KEEP)",
        "",
        "The following items look irregular, but represent genuine platform workarounds or battle-tested solutions. **Do NOT sanitize or simplify.**",
        ""
    ])

    if not sacred_fences:
        lines.append("_No sacred fences detected._\n")
    else:
        for f in sacred_fences:
            lines.append(f"### `{f.finding_id}`: {f.file_path}:{f.line_num}")
            lines.append(f"- **Snippet**: `{f.snippet}`")
            lines.append(f"- **Context**: {f.explanation}")
            lines.append(f"- **Action**: 🛡️ `{f.recommendation}`\n")

    lines.extend([
        "---",
        "",
        "## 3. High-Confidence AI Slop Checklist (RECOMMEND STRIP)",
        "",
        "Review these items. Greenlight the checklist IDs to collapse or delete them.",
        ""
    ])

    if not ai_slop:
        lines.append("_No high-confidence AI slop detected._\n")
    else:
        for f in ai_slop:
            lines.append(f"- [ ] **`{f.finding_id}`** ({f.category}) `{f.file_path}:{f.line_num}`")
            lines.append(f"  - Snippet: `{f.snippet}`")
            lines.append(f"  - Issue: {f.explanation}")
            lines.append(f"  - Recommendation: **{f.recommendation}**")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Semantic Grounding & Variable Renaming Table",
        "",
        "These identifiers either introduce meme/brainrot confusion or extreme enterprise verbosity, degrading LLM attention reasoning.",
        "",
        "| ID | Location | Current Identifier | Issue | Proposed Grounded Name |",
        "|---|---|---|---|---|"
    ])

    semantic_items = [f for f in findings if f.category in ("AI_VERBOSE_NAME", "HUMAN_MEME")]
    if not semantic_items:
        lines.append("| - | - | _None detected_ | - | - |")
    else:
        for f in semantic_items:
            suggested = f.suggested_name or "(Suggest concise domain term)"
            lines.append(f"| `{f.finding_id}` | `{f.file_path}:{f.line_num}` | `{f.snippet}` | {f.category} | `{suggested}` |")

    lines.extend([
        "",
        "---",
        "",
        "## 5. Next Steps & Execution",
        "",
        "1. **Triage**: Tell the agent which IDs to greenlight and which to reject (e.g. *'Strip all AI-CHAT, inline AI-WRAP-01, keep everything else'*).",
        "2. **Safety Fork**: The agent automatically triggers a safety Git backup branch.",
        "3. **Unslop**: Surgical edits applied cleanly with syntax & test verification."
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI Command Dispatcher
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Antigravity Code De-Slop & Grounding Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: scan
    scan_p = subparsers.add_parser("scan", help="Audit file or directory for AI slop, human chaos, and sacred hacks")
    scan_p.add_argument("target", help="File or directory path to scan")
    scan_p.add_argument("--format", choices=["text", "json", "md"], default="text", help="Output format")
    scan_p.add_argument("--output", "-o", help="Write report output to specified file")
    scan_p.add_argument("--include-tests", action="store_true", help="Include test directories in audit (default: excluded)")

    # Subcommand: fork
    fork_p = subparsers.add_parser("fork", help="Create a safety Git branch or filesystem backup before refactoring")
    fork_p.add_argument("target", nargs="?", default=".", help="Target directory (defaults to current dir)")

    # Subcommand: strip
    strip_p = subparsers.add_parser("strip", help="Surgically strip conversational chat debris comments")
    strip_p.add_argument("target", help="File to strip chat debris from")
    strip_p.add_argument("--dry-run", action="store_true", help="Preview changes without modifying file")

    args = parser.parse_args()

    if args.command == "scan":
        target = Path(args.target).resolve()
        if not target.exists():
            print(f"[ERROR] Target does not exist: {target}", file=sys.stderr)
            sys.exit(1)

        findings = scan_path(target, include_tests=args.include_tests)

        if args.format == "json":
            out_data = {
                "target": str(target),
                "total_findings": len(findings),
                "findings": [f.to_dict() for f in findings]
            }
            output_str = json.dumps(out_data, indent=2)
        elif args.format == "md":
            output_str = generate_markdown_report(findings, str(target))
        else:
            # Human-readable text summary
            lines = [
                f"=== De-Slop Audit: {target} ===",
                f"Total Markers Detected: {len(findings)}",
                ""
            ]
            for f in findings:
                tag = f"[{f.category}]"
                lines.append(f"{f.finding_id:<16} {tag:<22} {f.file_path}:{f.line_num}")
                lines.append(f"  Snippet: {f.snippet}")
                lines.append(f"  Action : {f.recommendation}")
                lines.append("")
            output_str = "\n".join(lines)

        if args.output:
            out_file = Path(args.output).resolve()
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(output_str, encoding="utf-8")
            print(f"[OK] Audit report written to {out_file}")
        else:
            print(output_str)

    elif args.command == "fork":
        target = Path(args.target).resolve()
        res = run_safety_fork(target)
        print(f"[FORK SUCCESS] {res['message']}")

    elif args.command == "strip":
        target = Path(args.target).resolve()
        if not target.is_file():
            print(f"[ERROR] Target must be a single file: {target}", file=sys.stderr)
            sys.exit(1)

        if args.dry_run:
            findings = [f for f in scan_file(target, target.parent) if f.category == "AI_CHAT_DEBRIS"]
            print(f"[DRY RUN] Found {len(findings)} conversational debris comments in {target.name}:")
            for f in findings:
                print(f"  L{f.line_num}: {f.snippet}")
        else:
            removed, msg = strip_chat_debris(target)
            print(f"[OK] {msg}")


if __name__ == "__main__":
    main()
