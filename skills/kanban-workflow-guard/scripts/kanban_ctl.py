#!/usr/bin/env python3
"""
kanban_ctl.py - Unified Kanban Controller & Task Lifecycle Guard

Manages the Modular Task Architecture (1-Card-1-Doc) across kanban.md, tasks/,
tasks/backlog/, tasks/archived/, and kanban_archive.md.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Standard 6-Tier Columns
DEFAULT_COLUMNS = [
    ("reported", "Reported (Triage / Ideas)"),
    ("frozen", "Frozen (Parked / Anti-Burnout)"),
    ("backlog", "Backlog (Staged / Non-Essential)"),
    ("todo", "Todo (Active Pipeline)"),
    ("in_progress", "In Progress (WIP = 1)"),
    ("completed", "Completed (Fresh / Review)")
]

CANDIDATE_COLUMNS = {"reported", "frozen", "backlog"}
ACTIVE_COLUMNS = {"todo", "in_progress", "completed"}

CARD_REGEX = re.compile(
    r'^\s*(?P<var>[a-zA-Z0-9_\-]+)\[(?P<quote>["\']?)(?P<title>.*?)(?P=quote)\](?:\s*@\{(?P<meta>.*?)\})?\s*$'
)
COL_REGEX = re.compile(r'^\s*(?P<id>[a-zA-Z0-9_\-]+)\[(?P<quote>["\']?)(?P<title>.*?)(?P=quote)\]\s*$')

TABLE_HEADER = "| Ticket ID | Grade | Title | Operational Inspiration | Spec Document |"
TABLE_SEP = "| :--- | :--- | :--- | :--- | :--- |"

SPEC_TEMPLATE = """# {ticket}: {title}

> **Category**: {grade} | **Priority**: {priority} | **State**: {status}  
> **Operational Inspiration**: {inspiration}

---

## 1. Operational Overview & Objectives
Brief description of the task, architectural motivation, and user-facing or system impact.

## 2. Target Files & Architectural Scope
* Key files to create or modify:
  * `path/to/target/file`

## 3. Implementation Blueprint
Concrete implementation steps, algorithmic details, interface contracts, and state transformations.

## 4. Acceptance Criteria & Verification Invariants
* [ ] Acceptance invariant 1
* [ ] Acceptance invariant 2
* [ ] Targeted test module passes (e.g., `python -m unittest tests/test_...`)
"""

MERMAID_THEME_DEFAULT = """%%{init: {
  'theme': 'base',
  'themeVariables': {
    'primaryColor': '#0d2235',
    'primaryTextColor': '#d4f4ff',
    'primaryBorderColor': '#00f0ff',
    'lineColor': '#00f0ff',
    'background': '#061019',
    'mainBkg': '#0a1926',
    'secondaryColor': '#081420',
    'secondaryTextColor': '#5a7e96',
    'secondaryBorderColor': '#134e6f',
    'tertiaryColor': '#0e263d',
    'tertiaryTextColor': '#00ffaa',
    'tertiaryBorderColor': '#00ffaa',
    'clusterBkg': '#081420',
    'clusterBorder': '#134e6f',
    'fontFamily': "'JetBrains Mono', 'Courier New', monospace"
  }
}}%%"""


class Card:
    def __init__(self, var: str, title: str, ticket: Optional[str] = None, priority: str = "Normal", raw_meta: str = ""):
        self.var = var
        self.title = title
        self.ticket = ticket or self._infer_ticket(var)
        self.priority = priority
        self.raw_meta = raw_meta

    @staticmethod
    def _infer_ticket(var: str) -> str:
        # e.g. tkt12 -> TKT-12, bug06 -> BUG-06, pln01 -> PLN-01
        m = re.match(r'^([a-zA-Z]+)(\d+)$', var)
        if m:
            prefix, num = m.groups()
            return f"{prefix.upper()}-{num}"
        return var.upper()

    def format_mermaid(self) -> str:
        prio = f", priority: '{self.priority}'" if self.priority else ""
        return f"    {self.var}[\"{self.title}\"]@{{ ticket: '[{self.ticket}]'{prio} }}"


class KanbanBoard:
    def __init__(self, root: Path, roadmap: bool = False):
        self.root = root

        # Check if roadmap/ layout is requested or already present
        roadmap_kanban = root / "roadmap" / "kanban.md"
        root_kanban = root / "kanban.md"

        if roadmap or (roadmap_kanban.exists() and not root_kanban.exists()):
            self.base_dir = root / "roadmap"
            self.is_roadmap = True
        else:
            self.base_dir = root
            self.is_roadmap = False

        self.kanban_file = self.base_dir / "kanban.md"
        self.archive_file = self.base_dir / "kanban_archive.md"
        self.tasks_dir = self.base_dir / "tasks"
        self.backlog_dir = self.tasks_dir / "backlog"
        self.archived_dir = self.tasks_dir / "archived"
        self.shelved_dir = self.archived_dir / "shelved"

        # Parsed state
        self.pre_mermaid_lines: List[str] = []
        self.mermaid_theme_lines: List[str] = []
        self.columns: List[Tuple[str, str]] = []  # (col_id, display_title)
        self.column_cards: Dict[str, List[Card]] = {}  # col_id -> [Card]
        self.post_mermaid_lines: List[str] = []
        self.table_rows: List[Dict[str, str]] = []
        self.post_table_lines: List[str] = []
        self.is_loaded = False

    def load(self) -> bool:
        if not self.kanban_file.exists():
            return False

        content = self.kanban_file.read_text(encoding="utf-8")
        lines = content.splitlines()

        in_mermaid = False
        in_kanban_block = False
        in_theme = False
        in_table = False
        table_headers_found = False

        current_col = None
        self.columns = []
        self.column_cards = {}
        self.pre_mermaid_lines = []
        self.mermaid_theme_lines = []
        self.post_mermaid_lines = []
        self.table_rows = []
        self.post_table_lines = []

        i = 0
        n = len(lines)
        while i < n:
            line = lines[i]

            if not in_mermaid:
                if line.strip().startswith("```mermaid"):
                    in_mermaid = True
                    i += 1
                    continue
                else:
                    self.pre_mermaid_lines.append(line)
                    i += 1
                    continue

            # We are inside ```mermaid
            if line.strip() == "```":
                in_mermaid = False
                in_kanban_block = False
                i += 1
                # The rest belongs to post_mermaid / table
                break

            # Inside mermaid: check for theme init
            stripped = line.strip()
            if stripped.startswith("%%{init:"):
                in_theme = True
                self.mermaid_theme_lines.append(line)
                if stripped.endswith("}}%%"):
                    in_theme = False
                i += 1
                continue
            elif in_theme:
                self.mermaid_theme_lines.append(line)
                if stripped.endswith("}}%%"):
                    in_theme = False
                i += 1
                continue

            if stripped == "kanban":
                in_kanban_block = True
                i += 1
                continue

            if in_kanban_block:
                # Column check: indented with 2 spaces or not card
                card_match = CARD_REGEX.match(line)
                col_match = COL_REGEX.match(line)

                # Prioritize column if line matches column and not preceded by 4+ spaces
                leading_spaces = len(line) - len(line.lstrip(' '))
                if col_match and leading_spaces <= 2 and not line.strip().startswith("@"):
                    col_id = col_match.group("id")
                    col_title = col_match.group("title")
                    current_col = col_id
                    if (col_id, col_title) not in self.columns:
                        self.columns.append((col_id, col_title))
                        self.column_cards[col_id] = []
                    i += 1
                    continue

                if card_match and current_col:
                    var = card_match.group("var")
                    title = card_match.group("title")
                    meta_str = card_match.group("meta") or ""

                    # Extract ticket and priority from meta
                    ticket = None
                    t_match = re.search(r"ticket\s*:\s*['\"](?:\[)?([^'\"\]]+)(?:\])?['\"]", meta_str)
                    if t_match:
                        ticket = t_match.group(1).strip()

                    priority = "Normal"
                    p_match = re.search(r"priority\s*:\s*['\"]([^'\"]+)['\"]", meta_str)
                    if p_match:
                        priority = p_match.group(1).strip()

                    card = Card(var=var, title=title, ticket=ticket, priority=priority, raw_meta=meta_str)
                    self.column_cards[current_col].append(card)
                    i += 1
                    continue

            i += 1

        # Now parse post-mermaid lines and glance table
        while i < n:
            line = lines[i]

            # Check if this line looks like the 5-column table header
            if "|" in line and "Ticket ID" in line and "Spec Document" in line:
                in_table = True
                table_headers_found = True
                # Skip header and separator
                i += 1
                if i < n and re.match(r'^\s*\|(?:\s*:?-+:?\s*\|)+\s*$', lines[i]):
                    i += 1
                continue

            if in_table:
                # Table row
                if line.strip().startswith("|") and line.strip().endswith("|"):
                    parts = [p.strip() for p in line.strip().split("|")[1:-1]]
                    if len(parts) >= 5:
                        # Extract ticket cleaned of markdown
                        raw_tkt = parts[0]
                        clean_tkt = re.sub(r'[*`\[\]]', '', raw_tkt).strip()
                        self.table_rows.append({
                            "ticket": clean_tkt,
                            "grade": parts[1].replace("`", "").strip(),
                            "title": parts[2].strip(),
                            "inspiration": parts[3].strip(),
                            "spec": parts[4].strip()
                        })
                    i += 1
                    continue
                else:
                    # End of table
                    in_table = False
                    self.post_table_lines.append(line)
                    i += 1
                    continue

            if not table_headers_found:
                self.post_mermaid_lines.append(line)
            else:
                self.post_table_lines.append(line)

            i += 1

        self.is_loaded = True
        return True

    def save(self):
        lines: List[str] = []

        # 1. Pre-mermaid
        if self.pre_mermaid_lines:
            lines.extend(self.pre_mermaid_lines)
            if lines and lines[-1] != "":
                lines.append("")
        else:
            lines.append("# Project Kanban Board")
            lines.append("")

        # 2. Mermaid block
        lines.append("```mermaid")
        if self.mermaid_theme_lines:
            lines.extend(self.mermaid_theme_lines)
        else:
            lines.append(MERMAID_THEME_DEFAULT)

        lines.append("kanban")
        for col_id, col_title in self.columns:
            lines.append(f'  {col_id}["{col_title}"]')
            for card in self.column_cards.get(col_id, []):
                lines.append(card.format_mermaid())
        lines.append("```")
        lines.append("")

        # 3. Post-mermaid headers / text
        if self.post_mermaid_lines:
            # Strip trailing blanks
            while self.post_mermaid_lines and self.post_mermaid_lines[0] == "":
                self.post_mermaid_lines.pop(0)
            lines.extend(self.post_mermaid_lines)
            if lines and lines[-1] != "":
                lines.append("")
        else:
            lines.append("## Active Glance Index")
            lines.append("")

        # 4. Glance Table
        lines.append(TABLE_HEADER)
        lines.append(TABLE_SEP)
        for row in self.table_rows:
            tkt = row['ticket']
            grade = row.get('grade', 'TKT')
            title = row.get('title', '')
            insp = row.get('inspiration', 'Standard engineering change')
            spec = row.get('spec', f'[{tkt}.md](tasks/{tkt}.md)')
            lines.append(f"| **`{tkt}`** | `{grade}` | {title} | {insp} | {spec} |")

        lines.append("")

        # 5. Post-table lines
        if self.post_table_lines:
            while self.post_table_lines and self.post_table_lines[0] == "":
                self.post_table_lines.pop(0)
            lines.extend(self.post_table_lines)
            if lines and lines[-1] != "":
                lines.append("")

        self.kanban_file.write_text("\n".join(lines), encoding="utf-8")

    def ensure_column(self, col_id: str, display_name: Optional[str] = None):
        for cid, _ in self.columns:
            if cid == col_id:
                return
        title = display_name or col_id.replace("_", " ").title()
        self.columns.append((col_id, title))
        self.column_cards[col_id] = []

    def find_card(self, ticket_or_id: str) -> Tuple[Optional[str], Optional[Card], Optional[int]]:
        target = ticket_or_id.upper()
        clean_target = re.sub(r'[^A-Z0-9]', '', target)

        for col_id, _ in self.columns:
            cards = self.column_cards.get(col_id, [])
            for idx, c in enumerate(cards):
                c_ticket = c.ticket.upper() if c.ticket else ""
                c_clean = re.sub(r'[^A-Z0-9]', '', c_ticket)
                c_var = re.sub(r'[^A-Z0-9]', '', c.var.upper())
                if target in (c_ticket, c.var.upper()) or (clean_target and clean_target in (c_clean, c_var)):
                    return col_id, c, idx
        return None, None, None

    def add_card(self, ticket: str, title: str, column: Optional[str] = None,
                 priority: str = "Normal", grade: Optional[str] = None, inspiration: str = ""):
        # Determine column if not provided
        if not column:
            if ticket.startswith("PLN") or ticket.startswith("TLK"):
                column = "reported"
            else:
                column = "todo"

        self.ensure_column(column)

        # Build var name e.g. TKT-12 -> tkt12
        var = re.sub(r'[^a-zA-Z0-9]', '', ticket).lower()
        if not var:
            var = f"card_{len(self.column_cards.get(column, [])) + 1}"

        # Inferred grade
        if not grade:
            m = re.match(r'^([A-Za-z]+)', ticket)
            grade = m.group(1).upper() if m else "TKT"

        card = Card(var=var, title=title, ticket=ticket, priority=priority)

        # Check if already on board
        old_col, _, old_idx = self.find_card(ticket)
        if old_col is not None and old_idx is not None:
            self.column_cards[old_col].pop(old_idx)

        self.column_cards[column].append(card)

        # Sync table row
        insp = inspiration if inspiration else "Active task specification"
        spec_path = f"tasks/backlog/{ticket}.md" if column in CANDIDATE_COLUMNS else f"tasks/{ticket}.md"
        spec_link = f"[{ticket}.md]({spec_path})"

        # Update or append table row
        updated = False
        for r in self.table_rows:
            if r["ticket"].upper() == ticket.upper():
                r["title"] = title
                r["grade"] = grade
                r["inspiration"] = insp
                r["spec"] = spec_link
                updated = True
                break
        if not updated:
            self.table_rows.append({
                "ticket": ticket,
                "grade": grade,
                "title": title,
                "inspiration": insp,
                "spec": spec_link
            })

        # Scaffold spec doc if does not exist anywhere
        doc_path = self.locate_spec_file(ticket)
        if not doc_path:
            target_dir = self.backlog_dir if column in CANDIDATE_COLUMNS else self.tasks_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            new_file = target_dir / f"{ticket}.md"
            content = SPEC_TEMPLATE.format(
                ticket=ticket,
                title=title,
                grade=grade,
                priority=priority,
                status=column,
                inspiration=insp
            )
            new_file.write_text(content, encoding="utf-8")

    def move_card(self, ticket: str, target_col: str, force: bool = False) -> Tuple[bool, str]:
        old_col, card, idx = self.find_card(ticket)
        if not old_col or not card or idx is None:
            return False, f"Card '{ticket}' not found on the board."

        if old_col == target_col:
            return True, f"Card '{ticket}' is already in column '{target_col}'."

        self.ensure_column(target_col)

        # Enforce WIP = 1 for in_progress
        if target_col == "in_progress" and not force:
            in_prog_cards = self.column_cards.get("in_progress", [])
            if len(in_prog_cards) >= 1:
                active_tkt = in_prog_cards[0].ticket
                return False, (
                    f"WIP LIMIT REACHED: 'in_progress' already has active card '{active_tkt}'. "
                    f"Complete or move it before starting '{ticket}' (or use --force)."
                )

        # Move card
        self.column_cards[old_col].pop(idx)
        self.column_cards[target_col].append(card)

        # Update files between tasks/backlog/ and tasks/
        self._sync_file_location(card.ticket, old_col, target_col)

        # Update table link
        spec_path = f"tasks/backlog/{card.ticket}.md" if target_col in CANDIDATE_COLUMNS else f"tasks/{card.ticket}.md"
        for r in self.table_rows:
            if r["ticket"].upper() == card.ticket.upper():
                r["spec"] = f"[{card.ticket}.md]({spec_path})"
                break

        return True, f"Moved '{card.ticket}' ({card.title}) from '{old_col}' -> '{target_col}'."

    def _sync_file_location(self, ticket: str, from_col: str, to_col: str):
        current_path = self.locate_spec_file(ticket)
        if not current_path or not current_path.exists():
            return

        if from_col in CANDIDATE_COLUMNS and to_col in ACTIVE_COLUMNS:
            # Promote to active tasks/
            new_path = self.tasks_dir / current_path.name
            if current_path != new_path:
                self.tasks_dir.mkdir(parents=True, exist_ok=True)
                current_path.rename(new_path)
        elif from_col in ACTIVE_COLUMNS and to_col in CANDIDATE_COLUMNS:
            # Demote to backlog
            new_path = self.backlog_dir / current_path.name
            if current_path != new_path:
                self.backlog_dir.mkdir(parents=True, exist_ok=True)
                current_path.rename(new_path)

    def locate_spec_file(self, ticket: str) -> Optional[Path]:
        clean_name = f"{ticket}.md"
        # 1. tasks/
        if (self.tasks_dir / clean_name).exists():
            return self.tasks_dir / clean_name
        # 2. tasks/backlog/
        if (self.backlog_dir / clean_name).exists():
            return self.backlog_dir / clean_name
        # 3. tasks/archived/
        if (self.archived_dir / clean_name).exists():
            return self.archived_dir / clean_name
        # 4. tasks/archived/shelved/
        if (self.shelved_dir / clean_name).exists():
            return self.shelved_dir / clean_name

        # Case-insensitive scan
        for p in [self.tasks_dir, self.backlog_dir, self.archived_dir, self.shelved_dir]:
            if p.exists():
                for f in p.glob("*.md"):
                    if f.stem.upper() == ticket.upper():
                        return f
        return None

    def shelve_card(self, ticket: str, reason: str = "Parked / Decided against") -> Tuple[bool, str]:
        old_col, card, idx = self.find_card(ticket)
        if not card or idx is None:
            return False, f"Card '{ticket}' not found on the board."

        # Remove from Mermaid
        self.column_cards[old_col].pop(idx)

        # Remove from table
        self.table_rows = [r for r in self.table_rows if r["ticket"].upper() != card.ticket.upper()]

        # Move file to tasks/archived/shelved/
        file_path = self.locate_spec_file(ticket)
        shelved_path = self.shelved_dir / f"{card.ticket}.md"
        self.shelved_dir.mkdir(parents=True, exist_ok=True)
        if file_path and file_path.exists():
            file_path.rename(shelved_path)

        # Append to kanban_archive.md
        self._append_archive_entry(
            section="Shelved & Parked Candidates",
            ticket=card.ticket,
            state="Shelved",
            title=card.title,
            note=reason,
            spec_rel=f"tasks/archived/shelved/{card.ticket}.md"
        )

        return True, f"Shelved '{card.ticket}' ({card.title}) to {shelved_path}."

    def archive_card(self, ticket: str, milestone: Optional[str] = None) -> Tuple[bool, str]:
        old_col, card, idx = self.find_card(ticket)
        if not card or idx is None:
            return False, f"Card '{ticket}' not found on the board."

        # Remove from Mermaid
        self.column_cards[old_col].pop(idx)

        # Find row metadata before removing
        row_match = next((r for r in self.table_rows if r["ticket"].upper() == card.ticket.upper()), None)
        grade = row_match["grade"] if row_match else "TKT"
        insp = row_match["inspiration"] if row_match else "Verified deliverable"

        # Remove from table
        self.table_rows = [r for r in self.table_rows if r["ticket"].upper() != card.ticket.upper()]

        # Move file to tasks/archived/
        file_path = self.locate_spec_file(ticket)
        arch_path = self.archived_dir / f"{card.ticket}.md"
        self.archived_dir.mkdir(parents=True, exist_ok=True)
        if file_path and file_path.exists():
            file_path.rename(arch_path)

        # Append to kanban_archive.md
        section = f"Milestone: {milestone}" if milestone else "Settled Milestones"
        self._append_archive_entry(
            section=section,
            ticket=card.ticket,
            state=grade,
            title=card.title,
            note=insp,
            spec_rel=f"tasks/archived/{card.ticket}.md"
        )

        return True, f"Archived '{card.ticket}' ({card.title}) to tasks/archived/."

    def _append_archive_entry(self, section: str, ticket: str, state: str, title: str, note: str, spec_rel: str):
        if not self.archive_file.exists():
            init_content = (
                "# Settled Milestones & Architectural Ledger\n\n"
                "Permanent historical ledger of completed, developer-verified task blueprints and shelved candidates.\n\n"
                "---\n\n"
            )
            self.archive_file.write_text(init_content, encoding="utf-8")

        content = self.archive_file.read_text(encoding="utf-8")
        entry = f"| **`{ticket}`** | `{state}` | {title} | {note} | [{ticket}.md]({spec_rel}) |\n"

        sec_header = f"## {section}"
        if sec_header in content:
            # Insert after the table separator of that section
            parts = content.split(sec_header, 1)
            after_header = parts[1]
            # Find next table separator | :---
            sep_idx = after_header.find("| :---")
            if sep_idx != -1:
                end_of_line = after_header.find("\n", sep_idx)
                if end_of_line != -1:
                    new_after = after_header[:end_of_line + 1] + entry + after_header[end_of_line + 1:]
                    self.archive_file.write_text(parts[0] + sec_header + new_after, encoding="utf-8")
                    return

        # If section does not exist, append it
        new_section = (
            f"\n## {section}\n\n"
            "| Ticket ID | State | Title | Context / Note | Spec Document |\n"
            "| :--- | :--- | :--- | :--- | :--- |\n"
            f"{entry}\n"
        )
        self.archive_file.write_text(content + new_section, encoding="utf-8")

    def validate(self) -> List[str]:
        issues: List[str] = []

        # 1. Check WIP limit on in_progress
        in_prog = self.column_cards.get("in_progress", [])
        if len(in_prog) > 1:
            tickets = ", ".join(c.ticket for c in in_prog)
            issues.append(f"WIP Violation: 'in_progress' has {len(in_prog)} active cards (allowed: 1): {tickets}")

        # 2. Check each card in Mermaid has spec on disk
        for col_id, _ in self.columns:
            for card in self.column_cards.get(col_id, []):
                doc = self.locate_spec_file(card.ticket)
                if not doc:
                    issues.append(f"Missing Spec: Card '{card.ticket}' in '{col_id}' has no corresponding .md file in tasks/")

        # 3. Check table sync
        board_tickets = set()
        for col_id, _ in self.columns:
            for c in self.column_cards.get(col_id, []):
                board_tickets.add(c.ticket.upper())

        table_tickets = set(r["ticket"].upper() for r in self.table_rows)

        missing_in_table = board_tickets - table_tickets
        if missing_in_table:
            issues.append(f"Table Sync: Cards in diagram missing from glance table: {', '.join(missing_in_table)}")

        extra_in_table = table_tickets - board_tickets
        if extra_in_table:
            issues.append(f"Table Sync: Rows in glance table missing from visual diagram: {', '.join(extra_in_table)}")

        return issues


def cmd_init(args, board: KanbanBoard):
    title = args.title or board.base_dir.name.replace("_", " ").title()
    if title.lower() == "roadmap":
        title = f"{board.root.name.replace('_', ' ').title()} Roadmap"
    board.tasks_dir.mkdir(parents=True, exist_ok=True)
    board.backlog_dir.mkdir(parents=True, exist_ok=True)
    board.archived_dir.mkdir(parents=True, exist_ok=True)
    board.shelved_dir.mkdir(parents=True, exist_ok=True)

    if not board.kanban_file.exists():
        board.pre_mermaid_lines = [f"# {title} Kanban Board", ""]
        board.mermaid_theme_lines = MERMAID_THEME_DEFAULT.splitlines()
        board.columns = list(DEFAULT_COLUMNS)
        board.column_cards = {cid: [] for cid, _ in DEFAULT_COLUMNS}
        board.post_mermaid_lines = ["## Active Glance Index", ""]
        board.table_rows = []
        board.save()
        print(f"[OK] Initialized kanban.md with 6 standard columns in {board.base_dir}")
    else:
        print(f"[INFO] kanban.md already exists in {board.base_dir}. Ensuring directories...")

    if not board.archive_file.exists():
        board._append_archive_entry("Settled Milestones", "INIT-00", "Baseline", "Project Scaffold", "Initial setup", "kanban.md")
        print(f"[OK] Initialized kanban_archive.md in {board.base_dir}")

    print(f"[DONE] Project Kanban Scaffolding ready in {board.base_dir}.")


def cmd_add(args, board: KanbanBoard):
    board.load()
    board.add_card(
        ticket=args.id,
        title=args.title,
        column=args.column,
        priority=args.priority,
        grade=args.grade,
        inspiration=args.inspiration or ""
    )
    board.save()
    print(f"[OK] Added card '{args.id}' (\"{args.title}\") -> Column '{args.column or 'default'}'")


def cmd_move(args, board: KanbanBoard):
    board.load()
    success, msg = board.move_card(args.id, args.column, force=args.force)
    if success:
        board.save()
        print(f"[OK] {msg}")
    else:
        print(f"[ERROR] {msg}", file=sys.stderr)
        sys.exit(1)


def cmd_shelve(args, board: KanbanBoard):
    board.load()
    success, msg = board.shelve_card(args.id, reason=args.reason or "Shelved candidate")
    if success:
        board.save()
        print(f"[OK] {msg}")
    else:
        print(f"[ERROR] {msg}", file=sys.stderr)
        sys.exit(1)


def cmd_archive(args, board: KanbanBoard):
    board.load()
    success, msg = board.archive_card(args.id, milestone=args.milestone)
    if success:
        board.save()
        print(f"[OK] {msg}")
    else:
        print(f"[ERROR] {msg}", file=sys.stderr)
        sys.exit(1)


def cmd_locate(args, board: KanbanBoard):
    board.load()
    col_id, card, _ = board.find_card(args.id)
    doc_path = board.locate_spec_file(args.id)

    print(f"Ticket:   {args.id.upper()}")
    print(f"Board Col:{col_id or 'NOT_ON_BOARD'}")
    if card:
        print(f"Title:    {card.title}")
        print(f"Priority: {card.priority}")
    if doc_path:
        print(f"File:     {doc_path}")
        print(f"Rel Path: {doc_path.relative_to(board.root)}")
    else:
        print("File:     [NOT FOUND ON DISK]")


def cmd_cat(args, board: KanbanBoard):
    board.load()
    doc_path = board.locate_spec_file(args.id)
    if doc_path and doc_path.exists():
        print(doc_path.read_text(encoding="utf-8"))
    else:
        print(f"Error: Specification file for '{args.id}' not found.", file=sys.stderr)
        sys.exit(1)


def cmd_validate(args, board: KanbanBoard):
    if not board.load():
        print(f"Error: kanban.md not found in {board.base_dir}", file=sys.stderr)
        sys.exit(1)

    issues = board.validate()
    if not issues:
        print(f"[PASS] Board and task specifications in '{board.base_dir}' are 100% compliant!")
    else:
        print(f"[FAIL] Found {len(issues)} issue(s):", file=sys.stderr)
        for iss in issues:
            print(f"  - {iss}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args, board: KanbanBoard):
    if not board.load():
        print(f"Error: kanban.md not found in {board.base_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"=== Kanban Board: {board.base_dir.name} ===")
    for col_id, col_title in board.columns:
        cards = board.column_cards.get(col_id, [])
        print(f"\n[{col_title}] ({len(cards)} cards)")
        for c in cards:
            print(f"  * {c.ticket:<8} : {c.title} ({c.priority})")


def main():
    parser = argparse.ArgumentParser(description="Unified Kanban Controller & Guard")
    parser.add_argument("--root", type=str, default=".", help="Project root directory (default: CWD)")
    parser.add_argument("--roadmap", action="store_true", help="Force roadmap/ subdirectory layout")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = subparsers.add_parser("init", help="Scaffold new project kanban structure")
    p_init.add_argument("--title", type=str, help="Project display title")
    p_init.add_argument("--roadmap", action="store_true", help="Scaffold kanban structure inside roadmap/ directory")

    # add
    p_add = subparsers.add_parser("add", help="Add a card and scaffold its specification doc")
    p_add.add_argument("--id", required=True, help="Ticket ID (e.g. TKT-01, PLN-05)")
    p_add.add_argument("--title", required=True, help="Card title")
    p_add.add_argument("--column", help="Target column (default inferred from prefix)")
    p_add.add_argument("--priority", default="Normal", help="Priority (Low, Normal, High, Critical, etc.)")
    p_add.add_argument("--grade", help="Ticket grade (TKT, PLN, FIX, BUG, TLK)")
    p_add.add_argument("--inspiration", help="Operational inspiration / rationale")

    # move
    p_move = subparsers.add_parser("move", help="Move card between columns")
    p_move.add_argument("id", help="Ticket ID to move")
    p_move.add_argument("column", help="Target column ID")
    p_move.add_argument("--force", action="store_true", help="Force move bypassing WIP check")

    # convenience aliases: start, review, promote, freeze
    p_start = subparsers.add_parser("start", help="Move card to 'in_progress' (WIP=1)")
    p_start.add_argument("id", help="Ticket ID")
    p_start.add_argument("--force", action="store_true", help="Force bypass WIP limit")

    p_review = subparsers.add_parser("review", help="Move card to 'completed' (review)")
    p_review.add_argument("id", help="Ticket ID")

    p_promote = subparsers.add_parser("promote", help="Move card to 'todo' (active pipeline)")
    p_promote.add_argument("id", help="Ticket ID")

    p_freeze = subparsers.add_parser("freeze", help="Move card to 'frozen' (parked)")
    p_freeze.add_argument("id", help="Ticket ID")

    # shelve
    p_shelve = subparsers.add_parser("shelve", help="Shelve/abandon card to anti-burnout archive")
    p_shelve.add_argument("id", help="Ticket ID to shelve")
    p_shelve.add_argument("--reason", default="Shelved / Decided against", help="Shelving rationale")

    # archive
    p_archive = subparsers.add_parser("archive", help="Archive completed ticket")
    p_archive.add_argument("id", help="Ticket ID to archive")
    p_archive.add_argument("--milestone", help="Milestone label or release name")

    # locate
    p_locate = subparsers.add_parser("locate", help="Locate task specification and card status")
    p_locate.add_argument("id", help="Ticket ID")

    # cat
    p_cat = subparsers.add_parser("cat", help="Print task specification markdown to stdout")
    p_cat.add_argument("id", help="Ticket ID")

    # validate
    subparsers.add_parser("validate", help="Validate board integrity and syntax")

    # list
    subparsers.add_parser("list", help="List cards by column")

    args = parser.parse_args()
    root_path = Path(args.root).resolve()
    is_roadmap = getattr(args, "roadmap", False)
    board = KanbanBoard(root_path, roadmap=is_roadmap)

    if args.command == "init":
        cmd_init(args, board)
    elif args.command == "add":
        cmd_add(args, board)
    elif args.command == "move":
        cmd_move(args, board)
    elif args.command == "start":
        args.column = "in_progress"
        cmd_move(args, board)
    elif args.command == "review":
        args.column = "completed"
        args.force = False
        cmd_move(args, board)
    elif args.command == "promote":
        args.column = "todo"
        args.force = False
        cmd_move(args, board)
    elif args.command == "freeze":
        args.column = "frozen"
        args.force = False
        cmd_move(args, board)
    elif args.command == "shelve":
        cmd_shelve(args, board)
    elif args.command == "archive":
        cmd_archive(args, board)
    elif args.command == "locate":
        cmd_locate(args, board)
    elif args.command == "cat":
        cmd_cat(args, board)
    elif args.command == "validate":
        cmd_validate(args, board)
    elif args.command == "list":
        cmd_list(args, board)


if __name__ == "__main__":
    main()
