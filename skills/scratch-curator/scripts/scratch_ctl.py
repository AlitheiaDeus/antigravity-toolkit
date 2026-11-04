#!/usr/bin/env python3
"""
scratch_ctl.py - Workspace Scratch & Debug Script Curator

Tidies up, catalogs, and indexes ad-hoc scripts and temporary artifacts
created during agentic debugging and pair-programming sessions.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Standard patterns for ad-hoc / scratch files
EPHEMERAL_PATTERNS = [
    r"^tmp_.*",
    r"^temp_.*",
    r"^dump_.*\.json$",
    r"^dump_.*\.txt$",
    r"^scratch_.*\.txt$",
    r".*\.tmp$",
    r".*\.temp$",
    r".*\.bak$",
    r"^probe_.*\.log$",
]

DEBUG_SCRIPT_PATTERNS = [
    r"^debug_.*\.(py|ps1|sh)$",
    r"^probe_.*\.(py|ps1|sh)$",
    r"^scratch_.*\.(py|ps1|sh)$",
    r"^check_.*\.(py|ps1|sh)$",
]

# Standard directories to skip during scratch scanning
IGNORE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    "tests",
    "test",
    ".gemini",
    ".system_generated",
}

IGNORE_FILES = {
    "setup.py",
    "run.py",
    "main.py",
    "__init__.py",
    "conftest.py",
    "setup_toolkit.py",
    "sync.py",
}

HEADER_TEMPLATE = '''"""
[SCRATCH ARTIFACT]
Script   : {script_name}
Ticket   : {ticket}
Created  : {created_date}
Purpose  : {purpose}
Command  : python {rel_path}
"""
'''


class ScratchItem:
    def __init__(self, path: Path, item_type: str, reason: str, size: int):
        self.path = path
        self.item_type = item_type  # "trash" or "script"
        self.reason = reason
        self.size = size


class ScratchCurator:
    def __init__(self, root: Path, scratch_dir: Optional[Path] = None):
        self.root = root.resolve()
        self.scratch_dir = (scratch_dir or (self.root / "scripts" / "scratch")).resolve()
        self.phonebook_file = self.scratch_dir / "SCRATCH_PHONEBOOK.md"

    def get_untracked_git_files(self) -> Optional[Set[Path]]:
        """Queries git status --porcelain for untracked (??) files if in git repo."""
        git_dir = self.root / ".git"
        if not git_dir.exists():
            return None

        try:
            res = subprocess.run(
                ["git", "status", "--porcelain", "-uall"],
                cwd=str(self.root),
                capture_output=True,
                text=True,
                check=False
            )
            if res.returncode != 0:
                return None

            untracked: Set[Path] = set()
            for line in res.stdout.splitlines():
                if line.startswith("?? "):
                    rel_p = line[3:].strip().strip('"')
                    untracked.add((self.root / rel_p).resolve())
            return untracked
        except Exception:
            return None

    def scan(self) -> List[ScratchItem]:
        """Scans the workspace for scratch items, categorizing into trash vs reusable debug scripts."""
        items: List[ScratchItem] = []
        untracked = self.get_untracked_git_files()

        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune ignored directories
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]

            current_dir = Path(dirpath).resolve()

            # Skip the curated scratch directory itself
            if current_dir == self.scratch_dir or self.scratch_dir in current_dir.parents:
                continue

            for fname in filenames:
                if fname in IGNORE_FILES:
                    continue

                fpath = (current_dir / fname).resolve()
                try:
                    fsize = fpath.stat().st_size
                except OSError:
                    fsize = 0

                # Check 1: Ephemeral Trash patterns
                is_trash = False
                for pat in EPHEMERAL_PATTERNS:
                    if re.match(pat, fname, re.IGNORECASE):
                        items.append(ScratchItem(fpath, "trash", f"Matches ephemeral pattern '{pat}'", fsize))
                        is_trash = True
                        break

                if is_trash:
                    continue

                # Check 2: Debug / probe / scratch script patterns
                is_debug_script = False
                for pat in DEBUG_SCRIPT_PATTERNS:
                    if re.match(pat, fname, re.IGNORECASE):
                        items.append(ScratchItem(fpath, "script", f"Matches debug script pattern '{pat}'", fsize))
                        is_debug_script = True
                        break

                if is_debug_script:
                    continue

                # Check 3: Loose test_*.py outside tests directory
                if fname.startswith("test_") and fname.endswith(".py"):
                    rel_to_root = fpath.relative_to(self.root)
                    if len(rel_to_root.parts) == 1:
                        items.append(ScratchItem(fpath, "script", "Ad-hoc root test file (outside tests/)", fsize))
                        continue

                # Check 4: Untracked python files at root that look like one-offs
                if untracked is not None and fpath in untracked:
                    if fpath.parent == self.root and fpath.suffix == ".py":
                        if fname not in {"run.py", "main.py", "setup.py"}:
                            items.append(ScratchItem(fpath, "script", "Untracked ad-hoc Python script at root", fsize))

        return sorted(items, key=lambda x: (x.item_type, str(x.path)))

    def catalog(self, file_path: Path, ticket: str = "ADHOC", purpose: str = "Debug verification script") -> Tuple[bool, str]:
        """Moves an ad-hoc script to the curated scratch directory, injects metadata, and updates phonebook."""
        src = file_path.resolve()
        if not src.exists():
            return False, f"File not found: {src}"

        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        dest = self.scratch_dir / src.name

        today = datetime.date.today().isoformat()

        # Read content
        try:
            content = src.read_text(encoding="utf-8")
        except Exception as e:
            return False, f"Could not read {src}: {e}"

        # Inject or update metadata header
        try:
            rel_path = dest.relative_to(self.root).as_posix()
        except ValueError:
            rel_path = dest.name

        header = HEADER_TEMPLATE.format(
            script_name=dest.name,
            ticket=ticket.upper(),
            created_date=today,
            purpose=purpose,
            rel_path=rel_path
        )

        if "[SCRATCH ARTIFACT]" not in content:
            # Prepend header (preserve shebang if present)
            if content.startswith("#!"):
                lines = content.splitlines(True)
                shebang = lines[0]
                rest = "".join(lines[1:])
                new_content = shebang + header + "\n" + rest.lstrip()
            else:
                new_content = header + "\n" + content.lstrip()
        else:
            new_content = content

        # Write to destination and remove source if moving
        try:
            dest.write_text(new_content, encoding="utf-8")
            if src != dest:
                src.unlink()
        except Exception as e:
            return False, f"Failed to catalog {src} -> {dest}: {e}"

        # Update phonebook
        self.update_phonebook()

        return True, f"Cataloged '{dest.name}' -> {rel_path} (Logged in Phonebook)"

    def update_phonebook(self) -> int:
        """Regenerates SCRATCH_PHONEBOOK.md by reading metadata from all scripts in scratch_dir."""
        if not self.scratch_dir.exists():
            return 0

        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        scripts: List[Dict[str, str]] = []

        for p in sorted(self.scratch_dir.iterdir()):
            if p.is_file() and p.name != "SCRATCH_PHONEBOOK.md" and p.suffix in {".py", ".ps1", ".sh"}:
                meta = self._extract_metadata(p)
                scripts.append(meta)

        lines: List[str] = [
            "# Scratch & Debug Script Phonebook",
            "",
            "> Curated repository of isolated debug testbeds, hardware probes, and one-off diagnostics.",
            f"> Maintained automatically by `/scratch-curator` in `{self.scratch_dir.relative_to(self.root).as_posix() if self.scratch_dir.is_relative_to(self.root) else self.scratch_dir}`.",
            "",
            "| Script Name | Ticket / Tag | Purpose | Created | Execution Command |",
            "| :--- | :--- | :--- | :--- | :--- |"
        ]

        for s in scripts:
            name_link = f"[`{s['name']}`]({s['name']})"
            cmd = f"`python {s['rel_path']}`" if s['name'].endswith(".py") else f"`{s['rel_path']}`"
            lines.append(f"| {name_link} | `{s['ticket']}` | {s['purpose']} | {s['created']} | {cmd} |")

        lines.append("")
        self.phonebook_file.write_text("\n".join(lines), encoding="utf-8")
        return len(scripts)

    def _extract_metadata(self, file_path: Path) -> Dict[str, str]:
        """Extracts [SCRATCH ARTIFACT] metadata or infers defaults."""
        try:
            rel_path = file_path.relative_to(self.root).as_posix()
        except ValueError:
            rel_path = file_path.name

        meta = {
            "name": file_path.name,
            "ticket": "ADHOC",
            "created": "Unknown",
            "purpose": "Ad-hoc diagnostic script",
            "rel_path": rel_path
        }

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            m_tkt = re.search(r"Ticket\s*:\s*([^\n]+)", content)
            if m_tkt:
                meta["ticket"] = m_tkt.group(1).strip()

            m_date = re.search(r"Created\s*:\s*([^\n]+)", content)
            if m_date:
                meta["created"] = m_date.group(1).strip()

            m_purp = re.search(r"Purpose\s*:\s*([^\n]+)", content)
            if m_purp:
                meta["purpose"] = m_purp.group(1).strip()
        except Exception:
            pass

        return meta

    def purge_trash(self, dry_run: bool = False) -> List[Tuple[Path, int]]:
        """Deletes ephemeral trash files found in the workspace."""
        trash_items = [item for item in self.scan() if item.item_type == "trash"]
        deleted: List[Tuple[Path, int]] = []

        for item in trash_items:
            if not dry_run:
                try:
                    item.path.unlink()
                    deleted.append((item.path, item.size))
                except Exception as e:
                    print(f"[WARN] Failed to delete {item.path}: {e}", file=sys.stderr)
            else:
                deleted.append((item.path, item.size))

        return deleted


def cmd_scan(args, curator: ScratchCurator):
    items = curator.scan()
    print(f"=== Scratch & Transient Artifact Audit: {curator.root.name} ===")

    if not items:
        print("[PASS] Clean workspace! No untracked scratch files or ephemeral dumps found.")
        return

    trash = [i for i in items if i.item_type == "trash"]
    scripts = [i for i in items if i.item_type == "script"]

    if trash:
        print(f"\n[🗑️ Ephemeral Trash] ({len(trash)} item(s) recommended for purge):")
        for t in trash:
            rel = t.path.relative_to(curator.root).as_posix()
            print(f"  - {rel:<40} ({t.size} B) -> {t.reason}")

    if scripts:
        print(f"\n[🔧 Debug Scripts] ({len(scripts)} item(s) recommended for cataloging):")
        for s in scripts:
            rel = s.path.relative_to(curator.root).as_posix()
            print(f"  * {rel:<40} ({s.size} B) -> {s.reason}")

    print("\nNext Actions:")
    if trash:
        print("  - To clean ephemeral trash: python scratch_ctl.py purge")
    if scripts:
        print("  - To catalog a script:      python scratch_ctl.py catalog <path> --ticket TKT-XX --purpose '...'")


def cmd_catalog(args, curator: ScratchCurator):
    file_path = Path(args.path)
    if not file_path.is_absolute():
        file_path = (curator.root / file_path).resolve()

    ticket = args.ticket or "ADHOC"
    purpose = args.purpose or "Isolated debug script"

    success, msg = curator.catalog(file_path, ticket=ticket, purpose=purpose)
    if success:
        print(f"[OK] {msg}")
    else:
        print(f"[ERROR] {msg}", file=sys.stderr)
        sys.exit(1)


def cmd_purge(args, curator: ScratchCurator):
    if not args.force and not args.dry_run:
        print("[SAFETY] Purge requires --force to delete files permanently, or --dry-run to preview.", file=sys.stderr)
        sys.exit(1)

    deleted = curator.purge_trash(dry_run=args.dry_run)
    mode = "[DRY-RUN]" if args.dry_run else "[PURGED]"

    if not deleted:
        print(f"{mode} No ephemeral trash files to remove.")
        return

    total_bytes = sum(size for _, size in deleted)
    print(f"{mode} Removed {len(deleted)} ephemeral file(s) ({total_bytes} bytes freed):")
    for p, sz in deleted:
        try:
            rel = p.relative_to(curator.root).as_posix()
        except ValueError:
            rel = p.name
        print(f"  - {rel} ({sz} B)")


def cmd_phonebook(args, curator: ScratchCurator):
    count = curator.update_phonebook()
    print(f"[OK] Scratch Phonebook regenerated at {curator.phonebook_file} ({count} script(s) indexed).")
    if curator.phonebook_file.exists():
        print("\n" + curator.phonebook_file.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description="Workspace Scratch & Debug Script Curator")
    parser.add_argument("--root", type=str, default=".", help="Workspace root directory (default: CWD)")
    parser.add_argument("--scratch-dir", type=str, help="Destination directory for cataloged scripts (default: scripts/scratch)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # scan
    subparsers.add_parser("scan", help="Scan workspace for loose scratch scripts and ephemeral trash")

    # catalog
    p_cat = subparsers.add_parser("catalog", help="Move script to scratch directory, inject metadata header, and update Phonebook")
    p_cat.add_argument("path", help="Path to script to catalog")
    p_cat.add_argument("--ticket", default="ADHOC", help="Ticket ID or topic tag (e.g. TKT-42, BUG-01, MAVLINK)")
    p_cat.add_argument("--purpose", default="Ad-hoc debug script", help="Brief explanation of what the script does")

    # purge
    p_purge = subparsers.add_parser("purge", help="Delete ephemeral trash files (*.tmp, dump_*.json, loose logs)")
    p_purge.add_argument("--dry-run", action="store_true", help="Preview files that would be deleted without deleting")
    p_purge.add_argument("--force", action="store_true", help="Execute actual deletion")

    # phonebook
    subparsers.add_parser("phonebook", help="Rebuild and print the SCRATCH_PHONEBOOK.md index")

    args = parser.parse_args()
    root_path = Path(args.root).resolve()
    scratch_dir = Path(args.scratch_dir).resolve() if args.scratch_dir else None

    curator = ScratchCurator(root=root_path, scratch_dir=scratch_dir)

    if args.command == "scan":
        cmd_scan(args, curator)
    elif args.command == "catalog":
        cmd_catalog(args, curator)
    elif args.command == "purge":
        cmd_purge(args, curator)
    elif args.command == "phonebook":
        cmd_phonebook(args, curator)


if __name__ == "__main__":
    main()
