#!/usr/bin/env python3
"""
git_sanitize_check.py - Pre-Commit Privacy, Path & Hygiene Shield

Scans Git repositories before committing to ensure:
  1. No hardcoded local machine paths (e.g., C:\\Users\\<user>, /home/<user>, /Users/<user>).
  2. No staged credentials, API keys, or .env secrets.
  3. Proper .gitignore hygiene (internal/, scratch/, *.env, __pycache__/).

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Set, Optional

# Regex patterns for local machine paths
PATH_LEAK_PATTERNS = [
    (re.compile(r'[a-zA-Z]:[\\/][uU]sers[\\/]([a-zA-Z0-9_\-\.]+)[\\/]'), "Windows user profile path"),
    (re.compile(r'/(?:home|Users)/([a-zA-Z0-9_\-\.]+)/'), "Unix/macOS home directory path")
]

# High-risk secret patterns
SECRET_PATTERNS = [
    (re.compile(r'-----BEGIN (?:RSA|OPENSSH|PRIVATE|EC) KEY-----'), "Private cryptographic key"),
    (re.compile(r'\b(?:AIza[0-9A-Za-z\-_]{30,40})\b'), "Google API key"),
    (re.compile(r'\b(?:ghp_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{82})\b'), "GitHub Personal Access Token"),
    (re.compile(r'\b(?:sk-[a-zA-Z0-9]{32,})\b'), "OpenAI API secret key"),
    (re.compile(r'\b(?:AKIA[0-9A-Z]{16})\b'), "AWS Access Key ID")
]

# Standard .gitignore rules required for agent hygiene
STANDARD_GITIGNORE_RULES = [
    "# --- Agent & Developer Scratchpads ---",
    "internal/",
    "scratch/",
    "ideas/",
    "",
    "# --- Credentials & Environment Overrides ---",
    ".env",
    "*.local.env",
    "",
    "# --- Runtime Caches & Build Artifacts ---",
    "__pycache__/",
    "*.py[cod]",
    ".pytest_cache/",
    ".coverage"
]

REQUIRED_GITIGNORE_TOKENS = {
    "internal/": "Private internal scratchpads (internal/)",
    "scratch/": "Temporary experiment scripts (scratch/)",
    ".env": "Environment credentials (.env)",
    "__pycache__/": "Python bytecode cache (__pycache__/)"
}

SAFE_FILE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".zip", ".tar", ".gz", ".pdf", ".pyc"
}


def get_git_root(path: Path) -> Optional[Path]:
    try:
        res = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        return Path(res.stdout.strip())
    except Exception:
        return None


def get_staged_or_target_files(git_root: Path, check_staged: bool = True) -> List[Tuple[Path, str]]:
    """Returns list of (file_path, file_content) to scan."""
    files_to_scan = []

    if check_staged:
        try:
            res = subprocess.run(
                ["git", "-C", str(git_root), "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                capture_output=True, text=True, check=True
            )
            rel_files = [f.strip() for f in res.stdout.splitlines() if f.strip()]
            for rf in rel_files:
                p = git_root / rf
                if p.exists() and p.is_file() and p.suffix.lower() not in SAFE_FILE_EXTENSIONS:
                    files_to_scan.append((p, p.read_text(encoding="utf-8", errors="replace")))
            return files_to_scan
        except Exception:
            pass

    # Fallback to scanning working directory files (excluding .git)
    for root, dirs, files in os.walk(git_root):
        if ".git" in dirs:
            dirs.remove(".git")
        if "node_modules" in dirs:
            dirs.remove("node_modules")
        if "venv" in dirs:
            dirs.remove("venv")

        for f in files:
            p = Path(root) / f
            if p.suffix.lower() not in SAFE_FILE_EXTENSIONS and not p.name.startswith(".git"):
                try:
                    files_to_scan.append((p, p.read_text(encoding="utf-8", errors="replace")))
                except Exception:
                    pass

    return files_to_scan


def scan_for_path_leaks(files: List[Tuple[Path, str]], current_user: str) -> List[Tuple[Path, int, str, str]]:
    """Detects hardcoded user machine paths."""
    issues = []
    user_lower = current_user.lower()

    for path, content in files:
        # Skip git_sanitize_check.py itself or test files that test these patterns
        if "git_sanitize_check" in path.name or "test_" in path.name:
            continue

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            # Check for current username or generic profile path patterns
            for pat, desc in PATH_LEAK_PATTERNS:
                m = pat.search(line)
                if m:
                    username = m.group(1).lower()
                    # Only flag if matches current user or typical user path
                    if username in {user_lower, "username", "user"} or len(username) > 2:
                        issues.append((path, idx, desc, line.strip()))
                        break
    return issues


def scan_for_secrets(files: List[Tuple[Path, str]]) -> List[Tuple[Path, int, str, str]]:
    """Detects private keys, API tokens, or staged secret files."""
    issues = []
    for path, content in files:
        # Flag any staged .env file
        if path.name == ".env" or path.name.endswith(".local.env"):
            issues.append((path, 1, "Staged Environment Secret File", path.name))
            continue

        if "git_sanitize_check" in path.name or "test_" in path.name:
            continue

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            for pat, desc in SECRET_PATTERNS:
                if pat.search(line):
                    issues.append((path, idx, desc, line.strip()[:40] + "... [REDACTED]"))
                    break
    return issues


def audit_gitignore(git_root: Path) -> Tuple[bool, List[str]]:
    """Verifies that .gitignore contains essential agent hygiene blocks."""
    gi_path = git_root / ".gitignore"
    if not gi_path.exists():
        return False, ["Missing .gitignore file at repository root!"]

    content = gi_path.read_text(encoding="utf-8", errors="replace")
    missing = []

    for token, desc in REQUIRED_GITIGNORE_TOKENS.items():
        if token not in content:
            missing.append(desc)

    return len(missing) == 0, missing


def fix_gitignore(git_root: Path):
    gi_path = git_root / ".gitignore"
    existing = gi_path.read_text(encoding="utf-8", errors="replace") if gi_path.exists() else ""

    addition = "\n\n# --- Standard Agentic Hygiene & Privacy (Added by git_sanitize_check) ---\n"
    for line in STANDARD_GITIGNORE_RULES:
        addition += f"{line}\n"

    gi_path.write_text(existing.rstrip() + addition, encoding="utf-8")
    print(f"[OK] Appended standard agent hygiene rules to {gi_path.name}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Pre-Commit Privacy, Path & Hygiene Shield")
    parser.add_argument("path", nargs="?", default=".", help="Target directory or Git repository root")
    parser.add_argument("--all", action="store_true", help="Scan all project files instead of only staged Git files")
    parser.add_argument("--fix-gitignore", action="store_true", help="Automatically append missing hygiene rules to .gitignore")

    args = parser.parse_args()
    target_path = Path(args.path).resolve()

    git_root = get_git_root(target_path) or target_path

    print(f"=== Running Pre-Commit Sanitization Shield: {git_root.name} ===")

    # 1. Audit .gitignore
    gi_clean, missing_gi = audit_gitignore(git_root)
    if not gi_clean:
        print("[WARN] .gitignore is missing standard agent hygiene blocks:", file=sys.stderr)
        for m in missing_gi:
            print(f"  - Missing: {m}", file=sys.stderr)
        if args.fix_gitignore:
            fix_gitignore(git_root)
            print("[FIXED] .gitignore updated with required rules.")
        else:
            print("Tip: Run with --fix-gitignore to auto-append standard rules.\n", file=sys.stderr)
    else:
        print("[PASS] .gitignore hygiene rules verified.")

    # 2. Collect files to scan
    check_staged = not args.all
    files = get_staged_or_target_files(git_root, check_staged=check_staged)
    mode_str = "staged Git files" if check_staged else "all working directory files"
    print(f"Scanning {len(files)} {mode_str}...")

    # 3. Check for Path Leaks
    current_user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    path_issues = scan_for_path_leaks(files, current_user)

    # 4. Check for Secret Leaks
    secret_issues = scan_for_secrets(files)

    # 5. Report Findings
    total_issues = len(path_issues) + len(secret_issues)

    if path_issues:
        print(f"\n[FAIL] Found {len(path_issues)} hardcoded local machine path(s):", file=sys.stderr)
        for p, line_no, desc, snippet in path_issues:
            rel = p.relative_to(git_root) if p.is_relative_to(git_root) else p.name
            print(f"  - {rel}:L{line_no} [{desc}] -> {snippet}", file=sys.stderr)

    if secret_issues:
        print(f"\n[FAIL] Found {len(secret_issues)} credential/secret risk(s):", file=sys.stderr)
        for p, line_no, desc, snippet in secret_issues:
            rel = p.relative_to(git_root) if p.is_relative_to(git_root) else p.name
            print(f"  - {rel}:L{line_no} [{desc}] -> {snippet}", file=sys.stderr)

    if total_issues > 0:
        print(f"\n[BLOCKED] Commit check failed with {total_issues} issue(s). Please sanitize before committing.", file=sys.stderr)
        sys.exit(1)

    print("\n[PASS] Pre-commit privacy & path sanitization check passed cleanly!")


if __name__ == "__main__":
    main()
