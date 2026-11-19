#!/usr/bin/env python3
"""
roadmap_studio_ctl.py - Unified Kanban + Wardley + Cynefin/Kano Studio Controller

Manages per-repo `.roadmap/` workspaces (board.json, tasks/*.md, open.ps1, and
auto-rendered read-only kanban.md), supports deterministic import from existing
kanban.md boards or semantic JSON stdin ingestion, and serves the interactive
3-tab ChromaForge studio over localhost with 15s heartbeat auto-exit.

Zero external dependencies (Python 3.8+ standard library only).
"""

import argparse
import datetime
import html as html_lib
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants & Taxonomies
# ---------------------------------------------------------------------------

DEFAULT_COLUMNS: List[Dict[str, Any]] = [
    {"id": "reported", "label": "Reported", "wip_limit": None, "collapsed": False},
    {"id": "frozen", "label": "Frozen", "wip_limit": None, "collapsed": False},
    {"id": "backlog", "label": "Backlog", "wip_limit": None, "collapsed": False},
    {"id": "todo", "label": "Todo", "wip_limit": None, "collapsed": False},
    {"id": "in_progress", "label": "In Progress", "wip_limit": 1, "collapsed": False},
    {"id": "completed", "label": "Completed", "wip_limit": None, "collapsed": False},
]

CYNEFIN_DOMAINS = ("clear", "complicated", "complex", "chaotic")
KANO_VALUES = ("must-be", "performance", "delighter")
WARDLEY_STAGES = ("genesis", "custom", "product", "commodity")
PRIORITY_LEVELS = ("Very High", "High", "Medium", "Low", "Very Low")
TICKET_PREFIXES = ("PLN-", "TKT-", "BUG-", "FIX-", "TLK-")

CARD_REGEX = re.compile(
    r'^\s*(?P<var>[a-zA-Z0-9_\-]+)\[(?P<quote>["\']?)(?P<title>.*?)(?P=quote)\](?:\s*@\{(?P<meta>.*?)\})?\s*$'
)
COL_REGEX = re.compile(
    r'^\s*(?P<id>[a-zA-Z0-9_\-]+)\[(?P<quote>["\']?)(?P<title>.*?)(?P=quote)\]\s*$'
)
TICKET_ID_REGEX = re.compile(r'\b([A-Z][A-Z0-9]{0,11}-\d+)\b')
SAFE_ID_RE = re.compile(r'[^A-Za-z0-9_.\-]+')

TAG_CYNEFIN_RE = re.compile(r'(?i)\bcynefin\s*[:=]\s*(clear|complicated|complex|chaotic)\b')
TAG_KANO_RE = re.compile(r'(?i)\bkano\s*[:=]\s*(must-be|must_be|mustbe|performance|delighter)\b')
TAG_WARDLEY_RE = re.compile(r'(?i)\bwardley\s*[:=]\s*(genesis|custom|product|commodity)\b')
TAG_VISIBILITY_RE = re.compile(r'(?i)\bvisibility\s*[:=]\s*([1-5])\b')
DEP_LINE_RE = re.compile(r'(?i)(?:dependencies|depends\s+on|blocked\s+by|upstream)\s*[:\-]\s*(.+)')

OPEN_PS1_TEMPLATE = """<#
.SYNOPSIS
    Launches Roadmap Studio for this repository on localhost.
#>
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SkillScript = Join-Path $env:USERPROFILE ".gemini\\config\\skills\\roadmap-studio\\scripts\\roadmap_studio_ctl.py"

if (-not (Test-Path $SkillScript)) {
    Write-Error "roadmap_studio_ctl.py not found at $SkillScript. Run sync.py --deploy from antigravity-toolkit first."
    exit 1
}

$PythonExe = "C:\\msys64\\mingw64\\bin\\python.exe"
if (-not (Test-Path $PythonExe)) {
    $Cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($Cmd -and (Get-Item $Cmd.Source).Length -gt 0) {
        $PythonExe = $Cmd.Source
    } else {
        Write-Error "Python 3 executable not found."
        exit 1
    }
}

& $PythonExe $SkillScript serve $RepoRoot --open
"""

SPEC_TEMPLATE = """# {card_id}: {title}

## 1. Overview & Motivation
Brief summary of the goal, user/system value, and constraints.

## 2. Target Files & Scope
- `path/to/file`

## 3. Implementation Notes
Key design decisions, edge cases, and interfaces.

## 4. Acceptance Criteria
- [ ] Criterion 1
- [ ] Relevant tests pass

## 5. Verification Command(s)
```bash
# Exact command(s) to verify this ticket
```
"""


# ---------------------------------------------------------------------------
# Classification Heuristics & Normalization
# ---------------------------------------------------------------------------

def _sanitize_card_id(raw_id: str) -> str:
    cleaned = SAFE_ID_RE.sub("-", str(raw_id).strip()).strip("-")
    return cleaned.upper() if cleaned else "ITEM-1"


def _normalize_prefix(raw_prefix: str) -> str:
    cleaned = SAFE_ID_RE.sub("-", str(raw_prefix).strip()).strip("-").upper()
    if not cleaned:
        raise ValueError("Prefix cannot be empty.")
    return cleaned


def _extract_prefix(ticket: str) -> str:
    upper = ticket.upper()
    for p in TICKET_PREFIXES:
        if upper.startswith(p):
            return p
    m = re.match(r'^([A-Z]+-)', upper)
    return m.group(1) if m else "OTHER"


def _normalize_kano(raw: Optional[str]) -> str:
    if not raw:
        return ""
    val = str(raw).strip().lower().replace("_", "-")
    if val == "mustbe":
        return "must-be"
    return val if val in KANO_VALUES else ""


def _normalize_priority(raw: Optional[str]) -> str:
    if not raw:
        return "Medium"
    val = re.sub(r'[\s_\-]+', ' ', str(raw).strip().lower())
    mapping = {
        "very high": "Very High",
        "critical": "Very High",
        "p0": "Very High",
        "high": "High",
        "p1": "High",
        "medium": "Medium",
        "med": "Medium",
        "normal": "Medium",
        "p2": "Medium",
        "low": "Low",
        "p3": "Low",
        "very low": "Very Low",
        "p4": "Very Low",
    }
    return mapping.get(val, "Medium")


def classify_cynefin(prefix: str, text: str, explicit: Optional[str] = None) -> str:
    if explicit and explicit.lower() in CYNEFIN_DOMAINS:
        return explicit.lower()
    low = text.lower()
    if prefix in ("BUG-", "FIX-") or any(w in low for w in ("crash", "incident", "hotfix", "outage", "urgent", "broken", "panic")):
        return "chaotic"
    if prefix in ("PLN-", "TLK-") or any(w in low for w in ("explore", "research", "spike", "prototype", "experiment", "unknown", "discover", "architecture")):
        return "complex"
    if any(w in low for w in ("refactor", "sync", "migrate", "engine", "pipeline", "schema", "scheduler", "concurrency", "integration")):
        return "complicated"
    if any(w in low for w in ("button", "flag", "typo", "copy", "label", "style", "css", "doc", "readme", "trivial", "lint")):
        return "clear"
    return "complicated" if prefix == "TKT-" else "complex"


def classify_kano(prefix: str, text: str, priority: str, explicit: Optional[str] = None) -> str:
    norm = _normalize_kano(explicit)
    if norm:
        return norm
    low = text.lower()
    if prefix in ("BUG-", "FIX-") or any(w in low for w in ("security", "auth", "crash", "fix", "regression", "sanitize", "guard", "validation", "test")):
        return "must-be"
    if any(w in low for w in ("theme", "visual", "hud", "polish", "delight", "interactive", "animation", "audio", "studio", "starmap")):
        return "delighter"
    if priority.lower() in ("very high", "high") or any(w in low for w in ("perf", "cache", "speed", "faster", "latency", "throughput", "index", "automation", "drag")):
        return "performance"
    return "performance"


def classify_wardley(prefix: str, cynefin: str, text: str, explicit: Optional[str] = None) -> str:
    if explicit and explicit.lower() in WARDLEY_STAGES:
        return explicit.lower()
    low = text.lower()
    if any(w in low for w in ("novel", "genesis", "experimental", "spike", "prototype", "research", "vector", "ai ")):
        return "genesis"
    if any(w in low for w in ("standard", "utility", "ci", "lint", "git", "logging", "config", "cleanup")) or prefix in ("BUG-", "FIX-"):
        return "commodity"
    if any(w in low for w in ("cli", "api", "plugin", "export", "report", "template", "adapter", "product")):
        return "product"
    if prefix in ("PLN-", "TLK-") or cynefin == "complex":
        return "genesis"
    return "custom"


def classify_visibility(text: str, explicit: Optional[int] = None) -> int:
    if isinstance(explicit, int) and 1 <= explicit <= 5:
        return explicit
    low = text.lower()
    if any(w in low for w in ("ui", "hud", "html", "dashboard", "canvas", "drag", "browser", "chat", "menu", "user")):
        return 5
    if any(w in low for w in ("cli", "command", "flag", "endpoint", "api", "export", "markdown")):
        return 4
    if any(w in low for w in ("parser", "engine", "pipeline", "sync", "scheduler", "planner", "controller")):
        return 3
    if any(w in low for w in ("schema", "storage", "cache", "model", "database", "store")):
        return 2
    if any(w in low for w in ("infra", "ci", "git", "lock", "env", "runtime", "helper", "util")):
        return 1
    return 3


def compute_recommendation(column: str, cynefin: str, kano: str, priority: str, deps_count: int, dependents_count: int) -> Tuple[str, str]:
    col = column.lower()
    prio_low = priority.lower()
    prio_bonus = 2 if prio_low == "very high" else (1 if prio_low == "high" else 0)
    score = dependents_count * 2 + prio_bonus + (1 if kano == "must-be" else 0)
    leverage = "High" if (dependents_count >= 2 or score >= 4) else ("Medium" if (dependents_count >= 1 or score >= 2) else "Low")

    if col in ("frozen", "completed"):
        return "Hold", leverage
    if cynefin == "chaotic":
        return "Execute Now", leverage
    if cynefin == "complex":
        return "Spike First", leverage
    if col in ("todo", "in_progress") or (kano == "must-be" and deps_count == 0):
        return "Execute Now", leverage
    if cynefin == "clear" and deps_count == 0:
        return "Execute Now", leverage
    if col == "reported" and dependents_count == 0:
        return "Hold", leverage
    return ("Execute Now" if prio_low in ("very high", "high") else "Hold"), leverage


# ---------------------------------------------------------------------------
# Workspace Paths & Board Persistence
# ---------------------------------------------------------------------------

def roadmap_dir(root: Path) -> Path:
    return root / ".roadmap"


def board_path(root: Path) -> Path:
    return roadmap_dir(root) / "board.json"


def tasks_dir(root: Path) -> Path:
    return roadmap_dir(root) / "tasks"


def archived_dir(root: Path) -> Path:
    return tasks_dir(root) / "archived"


def spec_file_path(root: Path, card_id: str, spec_rel: Optional[str] = None) -> Path:
    cid = _sanitize_card_id(card_id)
    t_dir = tasks_dir(root).resolve()
    if spec_rel:
        candidate = (roadmap_dir(root) / spec_rel).resolve()
        try:
            candidate.relative_to(t_dir)
            return candidate
        except ValueError:
            pass
    return tasks_dir(root) / f"{cid}.md"


def _default_spec_rel(card_id: str, group: str = "", is_group: bool = False) -> str:
    cid = _sanitize_card_id(card_id)
    if group and _sanitize_card_id(group) != cid:
        return f"tasks/{_sanitize_card_id(group)}/{cid}.md"
    if is_group:
        return f"tasks/{cid}/{cid}.md"
    return f"tasks/{cid}.md"


def _infer_group_from_spec(card_id: str, spec_rel: str) -> str:
    norm = str(spec_rel or "").replace("\\", "/")
    m = re.match(r'^tasks/([^/]+)/([^/]+)\.md$', norm)
    if not m:
        return ""
    folder_id = _sanitize_card_id(m.group(1))
    if folder_id in ("ARCHIVED", "SHELVED") or folder_id == _sanitize_card_id(card_id):
        return ""
    return folder_id


def _sync_group_spec_files(root: Path, board: Dict[str, Any]) -> None:
    """Relocate spec files between flat tasks/<ID>.md and grouped tasks/<GROUP>/<ID>.md."""
    group_ids = set()
    for c in board.get("cards", []):
        grp = _infer_group_from_spec(c["id"], c.get("spec_file", ""))
        if grp:
            group_ids.add(grp)

    for c in board.get("cards", []):
        cid = c["id"]
        grp = _infer_group_from_spec(cid, c.get("spec_file", ""))
        is_group = cid in group_ids
        desired_rel = _default_spec_rel(cid, group=grp, is_group=is_group)
        cur_rel = c.get("spec_file") or f"tasks/{cid}.md"
        if cur_rel == desired_rel:
            continue
        old_sp = spec_file_path(root, cid, cur_rel)
        new_sp = spec_file_path(root, cid, desired_rel)
        if old_sp.exists() and old_sp != new_sp and not new_sp.exists():
            new_sp.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_sp), str(new_sp))
        c["spec_file"] = desired_rel


def _copy_default_columns() -> List[Dict[str, Any]]:
    return [dict(c) for c in DEFAULT_COLUMNS]


def _normalize_card(raw: Dict[str, Any], valid_cols: set) -> Dict[str, Any]:
    cid = _sanitize_card_id(raw.get("id") or raw.get("ticket") or "ITEM-1")
    title = str(raw.get("title") or cid).strip()
    col = str(raw.get("column") or raw.get("status") or "todo").strip().lower()
    if col not in valid_cols:
        # Keep custom column if explicitly provided and non-empty
        col = re.sub(r'[^a-z0-9_\-]+', '_', col).strip('_') or "todo"
    priority = _normalize_priority(raw.get("priority"))
    prefix = _extract_prefix(cid)
    cynefin = classify_cynefin(prefix, title, raw.get("cynefin"))
    kano = classify_kano(prefix, title, priority, raw.get("kano"))
    wardley = classify_wardley(prefix, cynefin, title, raw.get("wardley"))
    vis_raw = raw.get("visibility")
    try:
        vis_int = int(vis_raw) if vis_raw is not None else None
    except (TypeError, ValueError):
        vis_int = None
    visibility = classify_visibility(title, vis_int)

    deps_raw = raw.get("dependencies") or []
    if isinstance(deps_raw, str):
        deps_raw = [x.strip() for x in deps_raw.split(",") if x.strip()]
    deps: List[str] = []
    for d in deps_raw:
        dc = _sanitize_card_id(d)
        if dc != cid and dc not in deps:
            deps.append(dc)

    if "group" in raw:
        grp_raw = str(raw.get("group") or "").strip()
        grp_clean = _sanitize_card_id(grp_raw) if grp_raw else ""
        spec_rel = _default_spec_rel(cid, group=grp_clean)
    else:
        spec_rel = str(raw.get("spec_file") or f"tasks/{cid}.md")
    return {
        "column": col,
        "cynefin": cynefin,
        "dependencies": deps,
        "id": cid,
        "kano": kano,
        "priority": priority,
        "spec_file": spec_rel,
        "title": title,
        "visibility": visibility,
        "wardley": wardley,
    }


def load_board(root: Path, enrich: bool = True) -> Dict[str, Any]:
    b_path = board_path(root)
    if not b_path.exists():
        raise FileNotFoundError(f"Missing {b_path}. Run `init` first.")

    raw = json.loads(b_path.read_text(encoding="utf-8"))
    cols_in = raw.get("columns") or _copy_default_columns()
    columns: List[Dict[str, Any]] = []
    seen_cols = set()
    for c in cols_in:
        cid = str(c.get("id") or "").strip().lower()
        if not cid or cid in seen_cols:
            continue
        seen_cols.add(cid)
        columns.append({
            "collapsed": bool(c.get("collapsed", False)),
            "id": cid,
            "label": str(c.get("label") or cid.replace("_", " ").title()),
            "wip_limit": c.get("wip_limit", None),
        })

    cards: List[Dict[str, Any]] = []
    seen_ids = set()
    for item in raw.get("cards", []):
        norm = _normalize_card(item, seen_cols)
        if norm["id"] in seen_ids:
            continue
        seen_ids.add(norm["id"])
        if norm["column"] not in seen_cols:
            seen_cols.add(norm["column"])
            columns.append({
                "collapsed": False,
                "id": norm["column"],
                "label": norm["column"].replace("_", " ").title(),
                "wip_limit": None,
            })
        cards.append(norm)

    board = {
        "anchor": str(raw.get("anchor") or "USER").strip().upper() or "USER",
        "cards": cards,
        "columns": columns,
        "title": str(raw.get("title") or "Project Roadmap").strip(),
        "version": int(raw.get("version") or 1),
    }
    return enrich_board(root, board) if enrich else board


def enrich_board(root: Path, board: Dict[str, Any]) -> Dict[str, Any]:
    dependents_map: Dict[str, List[str]] = {c["id"]: [] for c in board["cards"]}
    children_map: Dict[str, List[str]] = {c["id"]: [] for c in board["cards"]}
    disk_groups: Dict[str, str] = {}
    t_dir = tasks_dir(root)
    a_dir = archived_dir(root).resolve()
    if t_dir.exists():
        for md in t_dir.rglob("*.md"):
            try:
                md.resolve().relative_to(a_dir)
                continue
            except ValueError:
                pass
            rel = md.relative_to(roadmap_dir(root)).as_posix()
            cid_guess = _sanitize_card_id(md.stem)
            grp_guess = _infer_group_from_spec(cid_guess, rel)
            if grp_guess:
                disk_groups[cid_guess] = grp_guess

    card_groups: Dict[str, str] = {}
    for c in board["cards"]:
        for dep in c["dependencies"]:
            if dep in dependents_map and c["id"] not in dependents_map[dep]:
                dependents_map[dep].append(c["id"])
        grp = _infer_group_from_spec(c["id"], c.get("spec_file", "")) or disk_groups.get(c["id"], "")
        card_groups[c["id"]] = grp
        if grp and grp in children_map and c["id"] not in children_map[grp]:
            children_map[grp].append(c["id"])

    enriched_cards: List[Dict[str, Any]] = []
    for c in board["cards"]:
        copy = dict(c)
        deps_out = dependents_map.get(c["id"], [])
        children = children_map.get(c["id"], [])
        rec, lev = compute_recommendation(
            c["column"], c["cynefin"], c["kano"], c["priority"], len(c["dependencies"]), len(deps_out)
        )
        sp = spec_file_path(root, c["id"], c.get("spec_file"))
        copy["group"] = card_groups.get(c["id"], "")
        copy["children"] = children
        copy["is_group"] = len(children) > 0
        copy["dependents"] = deps_out
        copy["structural_leverage"] = lev
        copy["recommended_action"] = rec
        copy["has_spec"] = sp.exists()
        copy["evolving"] = c["column"] in ("todo", "in_progress")
        enriched_cards.append(copy)

    # Check WIP warnings per column
    col_counts: Dict[str, int] = {}
    for c in enriched_cards:
        col_counts[c["column"]] = col_counts.get(c["column"], 0) + 1
    wip_warnings = []
    for col in board["columns"]:
        limit = col.get("wip_limit")
        cnt = col_counts.get(col["id"], 0)
        if isinstance(limit, int) and limit > 0 and cnt > limit:
            wip_warnings.append({"column": col["id"], "count": cnt, "limit": limit})

    out = dict(board)
    out["cards"] = enriched_cards
    out["total_cards"] = len(enriched_cards)
    out["archived_count"] = len(load_archived(root))
    out["wip_warnings"] = wip_warnings
    return out


def _strip_derived_fields(board: Dict[str, Any]) -> Dict[str, Any]:
    clean_cards = []
    for c in board.get("cards", []):
        clean_cards.append({
            "column": c["column"],
            "cynefin": c["cynefin"],
            "dependencies": list(c.get("dependencies", [])),
            "id": c["id"],
            "kano": c["kano"],
            "priority": c["priority"],
            "spec_file": c.get("spec_file") or f"tasks/{c['id']}.md",
            "title": c["title"],
            "visibility": int(c["visibility"]),
            "wardley": c["wardley"],
        })
    clean_cols = []
    for col in board.get("columns", []):
        clean_cols.append({
            "collapsed": bool(col.get("collapsed", False)),
            "id": col["id"],
            "label": col["label"],
            "wip_limit": col.get("wip_limit", None),
        })
    return {
        "anchor": board.get("anchor", "USER"),
        "cards": clean_cards,
        "columns": clean_cols,
        "title": board.get("title", "Project Roadmap"),
        "version": int(board.get("version", 1)),
    }


def render_kanban_summary(board: Dict[str, Any]) -> str:
    """Render a clean read-only Markdown board snapshot for GitHub/IDE viewing."""
    lines = [
        "<!-- AUTO-GENERATED by roadmap-studio from .roadmap/board.json — DO NOT EDIT MANUALLY -->",
        "",
        f"# {board['title']}",
        "",
        f"> **Wardley Anchor**: `{board['anchor']}` | **Total Cards**: {len(board['cards'])}",
        "",
    ]

    by_col: Dict[str, List[Dict[str, Any]]] = {col["id"]: [] for col in board["columns"]}
    for c in board["cards"]:
        by_col.setdefault(c["column"], []).append(c)

    lines.append("## Columns")
    lines.append("")
    for col in board["columns"]:
        cards = by_col.get(col["id"], [])
        limit = col.get("wip_limit")
        wip_note = f" [WIP {len(cards)}/{limit}]" if isinstance(limit, int) and limit > 0 else ""
        lines.append(f"### {col['label']} ({len(cards)}){wip_note}")
        if not cards:
            lines.append("- *(empty)*")
        else:
            for c in cards:
                deps = f" (deps: {', '.join(c['dependencies'])})" if c["dependencies"] else ""
                lines.append(
                    f"- **`{c['id']}`** {c['title']} — `{c['priority']}` | "
                    f"{c['cynefin']} / {c['kano']} / {c['wardley']} V{c['visibility']}{deps}"
                )
        lines.append("")

    lines.extend([
        "## Index Table",
        "",
        "| ID | Column | Priority | Cynefin | Kano | Wardley | Vis | Spec |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for c in board["cards"]:
        spec_rel = c.get("spec_file") or f"tasks/{c['id']}.md"
        lines.append(
            f"| `{c['id']}` | {c['column']} | {c['priority']} | {c['cynefin']} | "
            f"{c['kano']} | {c['wardley']} | V{c['visibility']} | `{spec_rel}` |"
        )
    lines.append("")
    return "\n".join(lines)


def save_board(root: Path, board: Dict[str, Any]) -> Dict[str, Any]:
    """Persist board.json deterministically and refresh read-only .roadmap/kanban.md."""
    r_dir = roadmap_dir(root)
    r_dir.mkdir(parents=True, exist_ok=True)
    clean = _strip_derived_fields(board)

    b_path = board_path(root)
    tmp_path = b_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(clean, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(b_path)

    (r_dir / "kanban.md").write_text(render_kanban_summary(clean), encoding="utf-8")
    sync_markdown_markers_in_roadmap(root, clean)
    return enrich_board(root, clean)


def render_mermaid_kanban(board: Dict[str, Any], init_block: Optional[str] = None) -> str:
    """Render a fenced Mermaid kanban block from board.json."""
    lines = ["```mermaid"]
    if init_block:
        lines.append(init_block.strip())
    lines.append("kanban")

    by_col: Dict[str, List[Dict[str, Any]]] = {col["id"]: [] for col in board["columns"]}
    for c in board["cards"]:
        by_col.setdefault(c["column"], []).append(c)

    for col in board["columns"]:
        col_label = col["label"].replace('"', "'")
        lines.append(f'  {col["id"]}["{col_label}"]')
        for c in by_col.get(col["id"], []):
            var = re.sub(r'[^a-zA-Z0-9_]', '', c["id"].lower()) or "card"
            title = c["title"].replace('"', "'")
            prio = c.get("priority", "Normal").replace("'", "")
            lines.append(f'    {var}["{title}"]@{{ ticket: \'[{c["id"]}]\', priority: \'{prio}\' }}')
    lines.append("```")
    return "\n".join(lines)


MARKER_RE = re.compile(
    r'(<!--\s*ROADMAP_STUDIO:START\s*-->)(.*?)(<!--\s*ROADMAP_STUDIO:END\s*-->)',
    re.DOTALL,
)


def sync_markdown_markers_in_roadmap(root: Path, board: Dict[str, Any]) -> int:
    """Update only <!-- ROADMAP_STUDIO:START/END --> fenced Mermaid blocks inside .roadmap/*.md."""
    r_dir = roadmap_dir(root)
    if not r_dir.exists():
        return 0
    updated = 0
    for md_path in sorted(r_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        if not MARKER_RE.search(text):
            continue

        def _repl(match: re.Match) -> str:
            inner = match.group(2)
            m_init = re.search(r'(%%\{init:.*?\}%%)', inner, re.DOTALL)
            init_blk = m_init.group(1) if m_init else None
            mermaid_blk = render_mermaid_kanban(board, init_block=init_blk)
            return f"{match.group(1)}\n{mermaid_blk}\n{match.group(3)}"

        new_text = MARKER_RE.sub(_repl, text)
        if new_text != text:
            md_path.write_text(new_text, encoding="utf-8")
            updated += 1
    return updated


# ---------------------------------------------------------------------------
# Import Helpers (kanban.md + tasks/ OR Semantic JSON Stdin)
# ---------------------------------------------------------------------------

def _detect_legacy_kanban(root: Path) -> Tuple[Path, Optional[Path]]:
    roadmap_kanban = root / "roadmap" / "kanban.md"
    root_kanban = root / "kanban.md"
    if roadmap_kanban.exists() and not root_kanban.exists():
        return root / "roadmap", roadmap_kanban
    if root_kanban.exists():
        return root, root_kanban
    if (root / "roadmap" / "tasks").exists() and not (root / "tasks").exists():
        return root / "roadmap", None
    return root, None


def _parse_legacy_kanban_md(kanban_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    cols: List[Dict[str, Any]] = []
    cards: Dict[str, Dict[str, Any]] = {}
    if not kanban_path or not kanban_path.exists():
        return cols, cards

    lines = kanban_path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_mermaid = False
    in_kanban = False
    in_theme = False
    current_col: Optional[str] = None
    seen_cols = set()

    for line in lines:
        stripped = line.strip()
        if not in_mermaid:
            if stripped.startswith("```mermaid"):
                in_mermaid = True
            continue
        if stripped == "```":
            in_mermaid = False
            in_kanban = False
            continue
        if stripped.startswith("%%{init:"):
            in_theme = not stripped.endswith("}}%%")
            continue
        if in_theme:
            if stripped.endswith("}}%%"):
                in_theme = False
            continue
        if stripped == "kanban":
            in_kanban = True
            continue
        if in_kanban:
            leading = len(line) - len(line.lstrip(" "))
            col_match = COL_REGEX.match(line)
            card_match = CARD_REGEX.match(line)
            if col_match and leading <= 2 and not stripped.startswith("@"):
                cid = col_match.group("id").lower()
                label = col_match.group("title").strip()
                current_col = cid
                if cid not in seen_cols:
                    seen_cols.add(cid)
                    cols.append({
                        "id": cid,
                        "label": label,
                        "wip_limit": 1 if cid == "in_progress" else None,
                        "collapsed": False,
                    })
                continue
            if card_match and current_col:
                var = card_match.group("var")
                title = card_match.group("title").strip()
                meta_str = card_match.group("meta") or ""
                t_match = re.search(r"ticket\s*:\s*['\"](?:\[)?([^'\"\]]+)(?:\])?['\"]", meta_str)
                if t_match:
                    ticket = t_match.group(1).strip().upper()
                else:
                    m_var = re.match(r'^([a-zA-Z]+)(\d+)$', var)
                    ticket = f"{m_var.group(1).upper()}-{m_var.group(2)}" if m_var else var.upper()
                p_match = re.search(r"priority\s*:\s*['\"]([^'\"]+)['\"]", meta_str)
                priority = p_match.group(1).strip() if p_match else "Normal"
                cards[ticket] = {
                    "id": ticket,
                    "title": title,
                    "column": current_col,
                    "priority": priority,
                }
    return cols, cards


def _scan_legacy_task_specs(base_dir: Path) -> Dict[str, Dict[str, Any]]:
    specs: Dict[str, Dict[str, Any]] = {}
    t_root = base_dir / "tasks"
    if not t_root.exists():
        return specs

    for sub in (t_root, t_root / "backlog"):
        if not sub.exists():
            continue
        for md in sorted(sub.glob("*.md")):
            cid = md.stem.upper()
            text = md.read_text(encoding="utf-8", errors="replace")
            deps: List[str] = []
            for dmatch in DEP_LINE_RE.finditer(text):
                for found in TICKET_ID_REGEX.findall(dmatch.group(1).upper()):
                    if found != cid and found not in deps:
                        deps.append(found)
            m_cyn = TAG_CYNEFIN_RE.search(text)
            m_kan = TAG_KANO_RE.search(text)
            m_war = TAG_WARDLEY_RE.search(text)
            m_vis = TAG_VISIBILITY_RE.search(text)
            specs[cid] = {
                "path": md,
                "text": text,
                "deps": deps,
                "cynefin": m_cyn.group(1).lower() if m_cyn else None,
                "kano": _normalize_kano(m_kan.group(1)) if m_kan else None,
                "wardley": m_war.group(1).lower() if m_war else None,
                "visibility": int(m_vis.group(1)) if m_vis else None,
            }
    return specs


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def cmd_init(root: Path, title: str = "Project Roadmap", anchor: str = "USER", force: bool = False) -> int:
    r_dir = roadmap_dir(root)
    b_path = board_path(root)
    if b_path.exists() and not force:
        print(f"[SKIP] {b_path} already exists (use --force to overwrite).")
        return 0

    archived_dir(root).mkdir(parents=True, exist_ok=True)
    ps1_path = r_dir / "open.ps1"
    ps1_path.write_text(OPEN_PS1_TEMPLATE, encoding="utf-8")
    (r_dir / ".gitignore").write_text(
        ".server.json\nsnapshot.html\ntasks/archived/\n",
        encoding="utf-8",
    )

    board = {
        "version": 1,
        "title": title,
        "anchor": anchor.upper() or "USER",
        "columns": _copy_default_columns(),
        "cards": [],
    }
    save_board(root, board)
    print(f"[OK] Initialized Roadmap Studio in {r_dir}")
    return 0


def cmd_import(root: Path, use_stdin: bool = False, merge: bool = False) -> int:
    if not board_path(root).exists():
        cmd_init(root)

    board = load_board(root, enrich=False)
    existing_by_id = {c["id"]: c for c in board["cards"]}
    valid_cols = {c["id"] for c in board["columns"]}

    if use_stdin:
        raw_text = sys.stdin.read().strip()
        if not raw_text:
            print("[ERROR] No JSON received on stdin.", file=sys.stderr)
            return 1
        payload = json.loads(raw_text)
        if isinstance(payload, dict):
            if payload.get("title"):
                board["title"] = str(payload["title"])
            if payload.get("anchor"):
                board["anchor"] = str(payload["anchor"]).upper()
            if isinstance(payload.get("columns"), list) and payload["columns"]:
                board["columns"] = payload["columns"]
                valid_cols = {c["id"] for c in board["columns"]}
            items = payload.get("cards", [])
        elif isinstance(payload, list):
            items = payload
        else:
            print("[ERROR] Stdin JSON must be an array or object with 'cards'.", file=sys.stderr)
            return 1

        imported = 0
        for item in items:
            norm = _normalize_card(item, valid_cols)
            if norm["column"] not in valid_cols:
                valid_cols.add(norm["column"])
                board["columns"].append({
                    "collapsed": False,
                    "id": norm["column"],
                    "label": norm["column"].replace("_", " ").title(),
                    "wip_limit": 1 if norm["column"] == "in_progress" else None,
                })
            if merge and norm["id"] in existing_by_id:
                idx = board["cards"].index(existing_by_id[norm["id"]])
                board["cards"][idx] = norm
            elif norm["id"] not in existing_by_id:
                board["cards"].append(norm)
            else:
                continue
            existing_by_id[norm["id"]] = norm
            spec_md = item.get("spec_markdown") or item.get("spec")
            if spec_md:
                sp = spec_file_path(root, norm["id"], norm["spec_file"])
                sp.parent.mkdir(parents=True, exist_ok=True)
                sp.write_text(str(spec_md), encoding="utf-8")
            imported += 1

        save_board(root, board)
        print(f"[OK] Imported {imported} card(s) from stdin into {board_path(root)}")
        return 0

    # Deterministic clone from legacy kanban.md + tasks/
    base_dir, kanban_file = _detect_legacy_kanban(root)
    legacy_cols, legacy_cards = _parse_legacy_kanban_md(kanban_file) if kanban_file else ([], {})
    legacy_specs = _scan_legacy_task_specs(base_dir)

    if not legacy_cards and not legacy_specs:
        print(f"[ERROR] No kanban.md or tasks/ found under {root}", file=sys.stderr)
        return 1

    if legacy_cols and not merge:
        board["columns"] = legacy_cols
        valid_cols = {c["id"] for c in board["columns"]}

    all_ids = list(legacy_cards.keys())
    for sid in legacy_specs:
        if sid not in legacy_cards:
            all_ids.append(sid)

    imported = 0
    for cid in all_ids:
        k_meta = legacy_cards.get(cid, {})
        s_meta = legacy_specs.get(cid, {})
        title = k_meta.get("title") or cid
        if title == cid and s_meta.get("text"):
            m_h1 = re.search(r'^#\s+(?:[A-Z]+-\d+\s*[:\-]\s*)?(.+)$', s_meta["text"], re.MULTILINE)
            if m_h1:
                title = m_h1.group(1).strip()
        col = k_meta.get("column") or ("backlog" if s_meta.get("path") and s_meta["path"].parent.name == "backlog" else "todo")
        prio = k_meta.get("priority", "Normal")
        combined = f"{title}\n{s_meta.get('text', '')}"
        prefix = _extract_prefix(cid)
        cynefin = classify_cynefin(prefix, combined, s_meta.get("cynefin"))
        kano = classify_kano(prefix, combined, prio, s_meta.get("kano"))
        wardley = classify_wardley(prefix, cynefin, combined, s_meta.get("wardley"))
        vis = classify_visibility(combined, s_meta.get("visibility"))

        card_obj = _normalize_card({
            "id": cid,
            "title": title,
            "column": col,
            "priority": prio,
            "cynefin": cynefin,
            "kano": kano,
            "wardley": wardley,
            "visibility": vis,
            "dependencies": s_meta.get("deps", []),
        }, valid_cols)

        if cid in existing_by_id and not merge:
            continue
        if cid in existing_by_id and merge:
            idx = board["cards"].index(existing_by_id[cid])
            board["cards"][idx] = card_obj
        else:
            board["cards"].append(card_obj)
        existing_by_id[cid] = card_obj

        if s_meta.get("text"):
            sp = spec_file_path(root, cid, card_obj["spec_file"])
            sp.parent.mkdir(parents=True, exist_ok=True)
            sp.write_text(s_meta["text"], encoding="utf-8")
        imported += 1

    save_board(root, board)
    print(f"[OK] Cloned {imported} card(s) into {board_path(root)}")
    return 0


def allocate_free_ids(
    root: Path,
    prefix: str,
    count: int = 1,
    fill_gaps: bool = False,
    width: Optional[int] = None,
) -> Dict[str, Any]:
    """Compute the next free ticket ID(s) for a prefix across active, archived, and shelved cards."""
    norm_prefix = _normalize_prefix(prefix)
    if count < 1:
        raise ValueError("--count must be >= 1.")

    board = load_board(root, enrich=False)
    arch_entries = load_archived(root)

    active_ids = {str(c.get("id", "")).upper() for c in board["cards"]}
    archived_ids = {str(e.get("id", "")).upper() for e in arch_entries}
    loose_ids = set()
    t_dir = tasks_dir(root)
    a_dir = archived_dir(root).resolve()
    if t_dir.exists():
        for md in t_dir.rglob("*.md"):
            try:
                md.resolve().relative_to(a_dir)
                continue
            except ValueError:
                pass
            loose_ids.add(_sanitize_card_id(md.stem))

    all_ids = active_ids | archived_ids | loose_ids
    pat = re.compile(rf"^{re.escape(norm_prefix)}-(\d+)$")

    used_nums = set()
    detected_width = 2
    active_count = 0
    archived_count = 0

    for cid in active_ids:
        if pat.match(cid):
            active_count += 1
    for cid in archived_ids:
        if pat.match(cid):
            archived_count += 1
    for cid in all_ids:
        m = pat.match(cid)
        if m:
            used_nums.add(int(m.group(1)))
            detected_width = max(detected_width, len(m.group(1)))

    if width is not None:
        if width < 1:
            raise ValueError("--width must be >= 1.")
        pad_width = width
    else:
        pad_width = detected_width

    max_num = max(used_nums, default=0)
    latest_id = f"{norm_prefix}-{max_num:0{pad_width}d}" if max_num > 0 else None

    if fill_gaps:
        free_nums: List[int] = []
        candidate = 1
        while len(free_nums) < count:
            if candidate not in used_nums:
                free_nums.append(candidate)
            candidate += 1
    else:
        start = max_num + 1
        free_nums = list(range(start, start + count))

    ids = [f"{norm_prefix}-{n:0{pad_width}d}" for n in free_nums]
    return {
        "active_count": active_count,
        "archived_count": archived_count,
        "fill_gaps": fill_gaps,
        "ids": ids,
        "latest_id": latest_id,
        "latest_index": max_num,
        "next_id": ids[0],
        "prefix": norm_prefix,
        "used_count": len(used_nums),
        "width": pad_width,
    }


def cmd_next_id(
    root: Path,
    prefix: str,
    count: int = 1,
    fill_gaps: bool = False,
    width: Optional[int] = None,
    as_json: bool = False,
) -> int:
    try:
        info = allocate_free_ids(root, prefix, count=count, fill_gaps=fill_gaps, width=width)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(info, indent=2, sort_keys=True))
    else:
        print("\n".join(info["ids"]))
    return 0


def cmd_add(root: Path, card_id: Optional[str], title: str, column: str = "todo", priority: str = "Medium",
            cynefin: Optional[str] = None, kano: Optional[str] = None,
            wardley: Optional[str] = None, visibility: Optional[int] = None,
            with_spec: bool = False, prefix: Optional[str] = None,
            group: Optional[str] = None) -> int:
    if bool(card_id) == bool(prefix):
        print("[ERROR] Specify either --id or --prefix (not both).", file=sys.stderr)
        return 1
    if prefix:
        try:
            card_id = allocate_free_ids(root, prefix, count=1)["next_id"]
        except (FileNotFoundError, ValueError) as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1

    board = load_board(root, enrich=False)
    valid_cols = {c["id"] for c in board["columns"]}
    norm_payload: Dict[str, Any] = {
        "id": card_id,
        "title": title,
        "column": column,
        "priority": priority,
        "cynefin": cynefin,
        "kano": kano,
        "wardley": wardley,
        "visibility": visibility,
    }
    if group:
        norm_payload["group"] = group
    norm = _normalize_card(norm_payload, valid_cols)

    if any(c["id"] == norm["id"] for c in board["cards"]):
        print(f"[ERROR] Card {norm['id']} already exists.", file=sys.stderr)
        return 1
    if any(str(e.get("id", "")).upper() == norm["id"] for e in load_archived(root)):
        print(f"[ERROR] Card {norm['id']} already exists in archive.", file=sys.stderr)
        return 1
    if norm["column"] not in valid_cols:
        board["columns"].append({
            "collapsed": False,
            "id": norm["column"],
            "label": norm["column"].replace("_", " ").title(),
            "wip_limit": None,
        })

    board["cards"].append(norm)
    _sync_group_spec_files(root, board)
    if with_spec:
        sp = spec_file_path(root, norm["id"], norm["spec_file"])
        sp.parent.mkdir(parents=True, exist_ok=True)
        if not sp.exists():
            sp.write_text(SPEC_TEMPLATE.format(card_id=norm["id"], title=norm["title"]), encoding="utf-8")
    save_board(root, board)
    print(f"[OK] Added {norm['id']} -> {norm['column']}")
    return 0


def move_card_in_board(
    board: Dict[str, Any],
    card_ids: Any,
    target_col: str,
    target_index: Optional[int] = None,
    enforce_wip: bool = False,
) -> Tuple[Dict[str, Any], Optional[str]]:
    raw_ids = [card_ids] if isinstance(card_ids, str) else list(card_ids)
    if not raw_ids:
        raise ValueError("At least one card ID is required.")
    cids: List[str] = []
    seen: set[str] = set()
    for raw_id in raw_ids:
        cid = _sanitize_card_id(raw_id)
        if cid not in seen:
            seen.add(cid)
            cids.append(cid)

    col_id = target_col.strip().lower()
    col_meta = next((c for c in board["columns"] if c["id"] == col_id), None)
    if col_meta is None:
        raise ValueError(f"Unknown column '{target_col}'.")

    cards_by_id = {c["id"]: c for c in board["cards"]}
    missing = [cid for cid in cids if cid not in cards_by_id]
    if missing:
        raise KeyError(f"Card(s) not found: {', '.join(missing)}.")

    other_in_col = [c for c in board["cards"] if c["column"] == col_id and c["id"] not in seen]
    limit = col_meta.get("wip_limit")
    wip_msg = None
    new_count = len(other_in_col) + len(cids)
    if isinstance(limit, int) and limit > 0 and new_count > limit:
        wip_msg = f"Column '{col_id}' WIP limit ({limit}) exceeded ({new_count}/{limit})."
        if enforce_wip:
            raise RuntimeError(wip_msg)

    # Remove from current positions and re-insert at target position within column
    remaining = [c for c in board["cards"] if c["id"] not in seen]
    moved_cards = []
    for cid in cids:
        card = dict(cards_by_id[cid])
        card["column"] = col_id
        moved_cards.append(card)

    if target_index is None:
        remaining.extend(moved_cards)
    else:
        col_indices = [i for i, c in enumerate(remaining) if c["column"] == col_id]
        if not col_indices or target_index >= len(col_indices):
            insert_at = (col_indices[-1] + 1) if col_indices else len(remaining)
        elif target_index <= 0:
            insert_at = col_indices[0]
        else:
            insert_at = col_indices[target_index]
        for offset, card in enumerate(moved_cards):
            remaining.insert(insert_at + offset, card)

    board["cards"] = remaining
    return board, wip_msg


def cmd_move(root: Path, card_ids: Any, target_col: str, force: bool = False) -> int:
    raw_ids = [card_ids] if isinstance(card_ids, str) else list(card_ids)
    board = load_board(root, enrich=False)
    try:
        updated, wip_msg = move_card_in_board(board, raw_ids, target_col, enforce_wip=False)
    except (ValueError, KeyError, RuntimeError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    save_board(root, updated)
    if wip_msg:
        print(f"[WARN] {wip_msg} Keep WIP minimal.")
    moved_label = ", ".join(_sanitize_card_id(cid) for cid in raw_ids)
    print(f"[OK] Moved {moved_label} -> {target_col.lower()}")
    return 0


def load_archived(root: Path) -> List[Dict[str, Any]]:
    arch_log_path = roadmap_dir(root) / "archived.json"
    entries: List[Dict[str, Any]] = []
    if arch_log_path.exists():
        try:
            data = json.loads(arch_log_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                entries = data
        except Exception:
            entries = []

    known_ids = {str(e.get("id", "")).upper() for e in entries}
    a_dir = archived_dir(root)
    added = False
    if a_dir.exists():
        scan_dirs = [(a_dir, False), (a_dir / "shelved", True)]
        for scan_root, is_shelved in scan_dirs:
            if not scan_root.exists():
                continue
            for md in sorted(scan_root.glob("*.md")):
                if md.name.startswith("milestone_"):
                    continue
                cid = _sanitize_card_id(md.stem)
                if cid in known_ids:
                    continue
                known_ids.add(cid)
                text = md.read_text(encoding="utf-8", errors="replace")
                m_h1 = re.search(r'^#\s+(?:[A-Z]+-\d+\s*[:\-]\s*)?(.+)$', text, re.MULTILINE)
                title = m_h1.group(1).strip() if m_h1 else cid
                mtime = datetime.datetime.fromtimestamp(md.stat().st_mtime, tz=datetime.timezone.utc).isoformat()
                entry: Dict[str, Any] = {
                    "archived_at": mtime,
                    "id": cid,
                    "last_column": "archived",
                    "title": title,
                }
                if is_shelved:
                    entry["shelved"] = True
                entries.append(entry)
                added = True

    if (not arch_log_path.exists() or added) and roadmap_dir(root).exists():
        arch_log_path.write_text(json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return entries


def archive_card_in_board(
    root: Path,
    card_id: str,
    milestone: Optional[str] = None,
    shelved: bool = False,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    cid = _sanitize_card_id(card_id)
    board = load_board(root, enrich=False)
    card = next((c for c in board["cards"] if c["id"] == cid), None)
    if card is None:
        raise KeyError(f"Card '{cid}' not found.")

    board["cards"] = [c for c in board["cards"] if c["id"] != cid]
    sp = spec_file_path(root, cid, card.get("spec_file"))
    if sp.exists():
        dest_dir = (archived_dir(root) / "shelved") if shelved else archived_dir(root)
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(sp), str(dest_dir / sp.name))

    arch_log_path = roadmap_dir(root) / "archived.json"
    arch_entries = load_archived(root)
    entry: Dict[str, Any] = {
        "archived_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "card": card,
        "id": cid,
        "last_column": card["column"],
        "title": card["title"],
    }
    if milestone:
        entry["milestone"] = milestone.strip()
    if shelved:
        entry["shelved"] = True
    if reason:
        entry["reason"] = reason.strip()
    arch_entries.append(entry)
    arch_log_path.write_text(json.dumps(arch_entries, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return save_board(root, board)


def restore_card_from_archive(root: Path, card_id: str) -> Dict[str, Any]:
    cid = _sanitize_card_id(card_id)
    arch_entries = load_archived(root)
    idx = next((i for i in range(len(arch_entries) - 1, -1, -1) if arch_entries[i].get("id") == cid), None)
    if idx is None:
        raise KeyError(f"Archived card '{cid}' not found.")

    entry = arch_entries.pop(idx)
    board = load_board(root, enrich=False)
    valid_cols = {c["id"] for c in board["columns"]}
    raw_card = entry.get("card") or {
        "id": cid,
        "title": entry.get("title", cid),
        "column": entry.get("last_column", "todo"),
    }
    norm = _normalize_card(raw_card, valid_cols)
    if norm["column"] not in valid_cols:
        norm["column"] = "todo" if "todo" in valid_cols else board["columns"][0]["id"]

    if not any(c["id"] == norm["id"] for c in board["cards"]):
        board["cards"].append(norm)

    for candidate in (archived_dir(root) / f"{cid}.md", archived_dir(root) / "shelved" / f"{cid}.md"):
        if candidate.exists():
            dest = spec_file_path(root, cid, norm.get("spec_file"))
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(candidate), str(dest))
            break

    # Remove matching entry from archived.json
    arch_log_path = roadmap_dir(root) / "archived.json"
    persisted_entries = [e for e in arch_entries if str(e.get("id", "")).upper() != cid]
    arch_log_path.write_text(
        json.dumps(persisted_entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return save_board(root, board)


def cmd_archive(root: Path, card_ids: Any, milestone: Optional[str] = None) -> int:
    raw_ids = [card_ids] if isinstance(card_ids, str) else list(card_ids)
    if not raw_ids:
        print("[ERROR] At least one card ID is required.", file=sys.stderr)
        return 1
    cids = [_sanitize_card_id(cid) for cid in raw_ids]
    board = load_board(root, enrich=False)
    active_ids = {c["id"] for c in board["cards"]}
    missing = [cid for cid in cids if cid not in active_ids]
    if missing:
        print(f"[ERROR] Card(s) not found: {', '.join(missing)}.", file=sys.stderr)
        return 1
    try:
        for cid in cids:
            archive_card_in_board(root, cid, milestone=milestone)
    except KeyError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] Archived {', '.join(cids)}")
    return 0


def cmd_shelve(root: Path, card_id: str, reason: str = "") -> int:
    try:
        archive_card_in_board(root, card_id, shelved=True, reason=reason or "Shelved")
    except KeyError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] Shelved {_sanitize_card_id(card_id)}")
    return 0


def cmd_locate(root: Path, card_id: str, as_json: bool = False) -> int:
    cid = _sanitize_card_id(card_id)
    board = load_board(root, enrich=True)
    card = next((c for c in board["cards"] if c["id"] == cid), None)
    if card:
        sp = spec_file_path(root, cid, card.get("spec_file"))
        info = {
            "id": cid,
            "location": "active",
            "column": card["column"],
            "priority": card["priority"],
            "cynefin": card["cynefin"],
            "kano": card["kano"],
            "wardley": card["wardley"],
            "visibility": card["visibility"],
            "spec_path": str(sp),
            "spec_exists": sp.exists(),
        }
    else:
        arch = next((e for e in load_archived(root) if str(e.get("id", "")).upper() == cid), None)
        if not arch:
            print(f"[ERROR] Card '{cid}' not found in active or archived.", file=sys.stderr)
            return 1
        sp_arch = archived_dir(root) / ("shelved" if arch.get("shelved") else "") / f"{cid}.md"
        if arch.get("bundle_file"):
            sp_arch = roadmap_dir(root) / arch["bundle_file"]
        info = {
            "id": cid,
            "location": "shelved" if arch.get("shelved") else "archived",
            "milestone": arch.get("milestone"),
            "reason": arch.get("reason"),
            "spec_path": str(sp_arch),
            "spec_exists": sp_arch.exists(),
        }
    if as_json:
        print(json.dumps(info, indent=2, sort_keys=True))
    else:
        print(f"[{info['id']}] location={info['location']} | spec={info['spec_path']} (exists={info['spec_exists']})")
    return 0


def cmd_cat(root: Path, card_id: str) -> int:
    cid = _sanitize_card_id(card_id)
    board = load_board(root, enrich=True)
    card = next((c for c in board["cards"] if c["id"] == cid), None)
    if card:
        sp = spec_file_path(root, cid, card.get("spec_file"))
        print(
            f"# {cid}: {card['title']}\n"
            f"> Column: {card['column']} | Priority: {card['priority']} | "
            f"{card['cynefin']} / {card['kano']} / {card['wardley']} V{card['visibility']}\n"
        )
        if sp.exists():
            print(sp.read_text(encoding="utf-8", errors="replace"))
        else:
            print("(no spec file)")
        return 0

    arch = next((e for e in load_archived(root) if str(e.get("id", "")).upper() == cid), None)
    if not arch:
        print(f"[ERROR] Card '{cid}' not found.", file=sys.stderr)
        return 1
    print(f"# {cid}: {arch.get('title', cid)} [ARCHIVED]")
    for cand in (
        archived_dir(root) / f"{cid}.md",
        archived_dir(root) / "shelved" / f"{cid}.md",
    ):
        if cand.exists():
            print(cand.read_text(encoding="utf-8", errors="replace"))
            return 0
    if arch.get("bundle_file"):
        bundle_p = roadmap_dir(root) / arch["bundle_file"]
        if bundle_p.exists():
            print(f"(consolidated in {bundle_p})")
            return 0
    print("(no spec file)")
    return 0


def cmd_consolidate(
    root: Path,
    milestone: str,
    ids_csv: Optional[str] = None,
    use_all: bool = False,
    keep_singles: bool = False,
) -> int:
    if not ids_csv and not use_all:
        print("[ERROR] Specify --ids ID1,ID2,... or --all to choose which archived cards to consolidate.", file=sys.stderr)
        return 1

    entries = load_archived(root)
    if ids_csv:
        target_ids = {_sanitize_card_id(x) for x in ids_csv.split(",") if x.strip()}
    else:
        target_ids = {str(e.get("id", "")).upper() for e in entries if not e.get("bundle_file")}

    matched = [e for e in entries if str(e.get("id", "")).upper() in target_ids]
    if not matched:
        print("[ERROR] No matching archived cards found to consolidate.", file=sys.stderr)
        return 1

    slug = re.sub(r'[^a-z0-9]+', '_', milestone.strip().lower()).strip('_') or "milestone"
    bundle_rel = f"tasks/archived/milestone_{slug}.md"
    bundle_path = roadmap_dir(root) / bundle_rel
    bundle_path.parent.mkdir(parents=True, exist_ok=True)

    today = datetime.date.today().isoformat()
    lines = [
        f"# Milestone: {milestone}",
        "",
        f"> **Consolidated**: {today} | **Cards**: {len(matched)}",
        "",
        "| ID | Title | Last Column | Status |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for e in matched:
        status = f"Shelved ({e.get('reason', '')})" if e.get("shelved") else "Archived"
        lines.append(f"| `{e['id']}` | {e.get('title', e['id'])} | {e.get('last_column', '-')} | {status} |")
    lines.append("")

    for e in matched:
        cid = str(e["id"]).upper()
        lines.extend(["---", "", f"## {cid}: {e.get('title', cid)}", ""])
        spec_found = None
        for cand in (archived_dir(root) / f"{cid}.md", archived_dir(root) / "shelved" / f"{cid}.md"):
            if cand.exists():
                spec_found = cand
                break
        if spec_found:
            lines.append(spec_found.read_text(encoding="utf-8", errors="replace").strip())
            if not keep_singles:
                spec_found.unlink()
        else:
            lines.append("*(no individual spec file)*")
        lines.append("")

        e["milestone"] = milestone
        e["bundle_file"] = bundle_rel

    bundle_path.write_text("\n".join(lines), encoding="utf-8")
    (roadmap_dir(root) / "archived.json").write_text(
        json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[OK] Consolidated {len(matched)} card(s) -> {bundle_path}")
    return 0


def cmd_sync_md(root: Path) -> int:
    board = load_board(root, enrich=False)
    count = sync_markdown_markers_in_roadmap(root, board)
    print(f"[OK] Synced Mermaid kanban markers in {count} file(s) under {roadmap_dir(root)}")
    return 0


def cmd_list(root: Path, as_json: bool = False) -> int:
    board = load_board(root, enrich=True)
    if as_json:
        print(json.dumps(board, indent=2, sort_keys=True))
        return 0
    print(f"=== {board['title']} (Anchor: {board['anchor']}, Cards: {board['total_cards']}) ===")
    for col in board["columns"]:
        cards = [c for c in board["cards"] if c["column"] == col["id"]]
        limit = col.get("wip_limit")
        warn = " [WIP EXCEEDED]" if (isinstance(limit, int) and len(cards) > limit) else ""
        print(f"\n[{col['label']}] ({len(cards)}){warn}")
        for c in cards:
            print(f"  - {c['id']}: {c['title']} ({c['priority']} | {c['cynefin']} | {c['kano']} | {c['wardley']} V{c['visibility']})")
    return 0


def cmd_validate(root: Path) -> int:
    board = load_board(root, enrich=True)
    issues = []
    known_ids = {c["id"] for c in board["cards"]}
    for c in board["cards"]:
        for dep in c["dependencies"]:
            if dep not in known_ids:
                issues.append(f"{c['id']} depends on missing card {dep}")
    for w in board["wip_warnings"]:
        issues.append(f"WIP limit exceeded in {w['column']}: {w['count']}/{w['limit']}")
    if issues:
        for i in issues:
            print(f"[WARN] {i}")
    print(f"[OK] Validated {board['total_cards']} card(s) across {len(board['columns'])} column(s).")
    return 0


def _studio_html_path() -> Path:
    return Path(__file__).resolve().parent.parent / "resources" / "studio.html"


def cmd_export_static(root: Path, output: str) -> int:
    board = load_board(root, enrich=True)
    html_src = _studio_html_path().read_text(encoding="utf-8")
    payload = json.dumps(board).replace("</", "<\\/")
    rendered = html_src.replace("__STATIC_BOARD_JSON__", payload)
    out_path = Path(output)
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(f"[OK] Exported static snapshot -> {out_path}")
    return 0


# ---------------------------------------------------------------------------
# Local HTTP Server (Loopback-only, Port Reuse & 15s Heartbeat Auto-Exit)
# ---------------------------------------------------------------------------

def _server_lock_path(root: Path) -> Path:
    return roadmap_dir(root) / ".server.json"


def _check_existing_server(root: Path) -> Optional[str]:
    lock_p = _server_lock_path(root)
    if not lock_p.exists():
        return None
    try:
        info = json.loads(lock_p.read_text(encoding="utf-8"))
        url = str(info.get("url") or "")
        if not url:
            return None
        req = urllib.request.Request(f"{url}/api/health", method="GET")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=0.6) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "ok":
                    return url
    except Exception:
        pass
    try:
        lock_p.unlink()
    except OSError:
        pass
    return None


class StudioAppState:
    """Thread-safe shared state for the local Roadmap Studio HTTP server."""

    def __init__(self, root: Path, auto_exit: bool = True, heartbeat_timeout: float = 15.0):
        self.root = root
        self.lock = threading.Lock()
        self.auto_exit = auto_exit
        self.heartbeat_timeout = heartbeat_timeout
        self.last_activity = time.monotonic()
        self.saw_client = False
        self.shutdown_event = threading.Event()
        self.server: Optional[ThreadingHTTPServer] = None

    def touch(self, is_heartbeat: bool = False) -> None:
        self.last_activity = time.monotonic()
        if is_heartbeat:
            self.saw_client = True


def _make_handler(app: StudioAppState):
    studio_html_template = _studio_html_path().read_text(encoding="utf-8")

    class StudioHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return  # Keep console clean

        def _send_json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length > 0 else b"{}"
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:
            app.touch()
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/api/health":
                self._send_json(200, {"status": "ok", "root": str(app.root)})
                return

            if path == "/api/board":
                with app.lock:
                    board = load_board(app.root, enrich=True)
                self._send_json(200, board)
                return

            if path == "/api/archived":
                with app.lock:
                    entries = load_archived(app.root)
                self._send_json(200, {"archived": entries})
                return

            if path == "/api/next-id":
                qs = urllib.parse.parse_qs(parsed.query)
                prefix = (qs.get("prefix") or ["TKT"])[0]
                try:
                    count = int((qs.get("count") or ["1"])[0])
                    fill_gaps = (qs.get("fill_gaps") or ["0"])[0].lower() in ("1", "true", "yes")
                    with app.lock:
                        info = allocate_free_ids(app.root, prefix, count=count, fill_gaps=fill_gaps)
                except (FileNotFoundError, ValueError) as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                self._send_json(200, info)
                return

            m_spec = re.match(r'^/api/card/([^/]+)/spec$', path)
            if m_spec:
                cid = urllib.parse.unquote(m_spec.group(1))
                with app.lock:
                    board = load_board(app.root, enrich=False)
                    card = next((c for c in board["cards"] if c["id"] == _sanitize_card_id(cid)), None)
                    if not card:
                        self._send_json(404, {"error": "Card not found"})
                        return
                    sp = spec_file_path(app.root, card["id"], card.get("spec_file"))
                    content = sp.read_text(encoding="utf-8", errors="replace") if sp.exists() else ""
                self._send_json(200, {"id": card["id"], "exists": sp.exists(), "content": content, "spec_file": card["spec_file"]})
                return

            if path in ("/", "/index.html"):
                html_out = studio_html_template.replace("__STATIC_BOARD_JSON__", "null")
                body = html_out.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path

            if path == "/api/heartbeat":
                app.touch(is_heartbeat=True)
                self._send_json(200, {"ok": True})
                return

            app.touch()

            if path == "/api/shutdown":
                self._send_json(200, {"ok": True, "stopping": True})
                app.shutdown_event.set()
                return

            try:
                body = self._read_json()
            except Exception as exc:
                self._send_json(400, {"error": f"Invalid JSON: {exc}"})
                return

            if path == "/api/board/meta":
                with app.lock:
                    board = load_board(app.root, enrich=False)
                    if "title" in body and str(body["title"]).strip():
                        board["title"] = str(body["title"]).strip()
                    if "anchor" in body:
                        board["anchor"] = (str(body["anchor"]).strip().upper() or "USER")
                    enriched = save_board(app.root, board)
                self._send_json(200, enriched)
                return

            if path == "/api/board/columns":
                with app.lock:
                    board = load_board(app.root, enrich=False)
                    col_id = str(body.get("id") or "").strip().lower()
                    for col in board["columns"]:
                        if col["id"] == col_id:
                            if "collapsed" in body:
                                col["collapsed"] = bool(body["collapsed"])
                            if "label" in body and str(body["label"]).strip():
                                col["label"] = str(body["label"]).strip()
                            break
                    enriched = save_board(app.root, board)
                self._send_json(200, enriched)
                return

            if path == "/api/board/move":
                cid = str(body.get("id") or "")
                target_col = str(body.get("column") or "")
                target_idx = body.get("index", None)
                with app.lock:
                    board = load_board(app.root, enrich=False)
                    try:
                        updated, wip_msg = move_card_in_board(board, cid, target_col, target_idx, enforce_wip=False)
                    except (ValueError, KeyError) as exc:
                        self._send_json(400, {"error": str(exc)})
                        return
                    enriched = save_board(app.root, updated)
                self._send_json(200, {"board": enriched, "wip_warning": wip_msg})
                return

            if path == "/api/card":
                with app.lock:
                    board = load_board(app.root, enrich=False)
                    valid_cols = {c["id"] for c in board["columns"]}
                    norm = _normalize_card(body, valid_cols)
                    if norm["column"] not in valid_cols:
                        board["columns"].append({
                            "collapsed": False,
                            "id": norm["column"],
                            "label": norm["column"].replace("_", " ").title(),
                            "wip_limit": None,
                        })
                    existing_idx = next((i for i, c in enumerate(board["cards"]) if c["id"] == norm["id"]), None)
                    if existing_idx is not None:
                        old_card = board["cards"][existing_idx]
                        old_sp = spec_file_path(app.root, old_card["id"], old_card.get("spec_file"))
                        new_sp = spec_file_path(app.root, norm["id"], norm.get("spec_file"))
                        if old_sp.exists() and old_sp != new_sp and not new_sp.exists():
                            new_sp.parent.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(old_sp), str(new_sp))
                        board["cards"][existing_idx] = norm
                    else:
                        board["cards"].append(norm)
                    _sync_group_spec_files(app.root, board)
                    if body.get("create_spec") and not spec_file_path(app.root, norm["id"], norm["spec_file"]).exists():
                        sp = spec_file_path(app.root, norm["id"], norm["spec_file"])
                        sp.parent.mkdir(parents=True, exist_ok=True)
                        sp.write_text(SPEC_TEMPLATE.format(card_id=norm["id"], title=norm["title"]), encoding="utf-8")
                    enriched = save_board(app.root, board)
                self._send_json(200, {"board": enriched, "card_id": norm["id"]})
                return

            m_spec = re.match(r'^/api/card/([^/]+)/spec$', path)
            if m_spec:
                cid = urllib.parse.unquote(m_spec.group(1))
                with app.lock:
                    board = load_board(app.root, enrich=False)
                    card = next((c for c in board["cards"] if c["id"] == _sanitize_card_id(cid)), None)
                    if not card:
                        self._send_json(404, {"error": "Card not found"})
                        return
                    sp = spec_file_path(app.root, card["id"], card.get("spec_file"))
                    sp.parent.mkdir(parents=True, exist_ok=True)
                    sp.write_text(str(body.get("content") or ""), encoding="utf-8")
                    enriched = load_board(app.root, enrich=True)
                self._send_json(200, {"ok": True, "board": enriched})
                return

            m_arch = re.match(r'^/api/card/([^/]+)/archive$', path)
            if m_arch:
                cid = urllib.parse.unquote(m_arch.group(1))
                with app.lock:
                    try:
                        enriched = archive_card_in_board(
                            app.root,
                            cid,
                            milestone=body.get("milestone"),
                            shelved=bool(body.get("shelved", False)),
                            reason=body.get("reason"),
                        )
                    except KeyError as exc:
                        self._send_json(404, {"error": str(exc)})
                        return
                self._send_json(200, {"board": enriched})
                return

            m_rest = re.match(r'^/api/card/([^/]+)/restore$', path)
            if m_rest:
                cid = urllib.parse.unquote(m_rest.group(1))
                with app.lock:
                    try:
                        enriched = restore_card_from_archive(app.root, cid)
                    except KeyError as exc:
                        self._send_json(404, {"error": str(exc)})
                        return
                self._send_json(200, {"board": enriched})
                return

            self._send_json(404, {"error": "Not found"})

    return StudioHandler


def start_server(
    root: Path,
    port: int = 0,
    open_browser: bool = False,
    auto_exit: bool = True,
    heartbeat_timeout: float = 15.0,
) -> Tuple[ThreadingHTTPServer, StudioAppState, str]:
    if not board_path(root).exists():
        cmd_init(root)

    app = StudioAppState(root, auto_exit=auto_exit, heartbeat_timeout=heartbeat_timeout)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(app))
    app.server = httpd
    actual_port = httpd.server_address[1]
    url = f"http://127.0.0.1:{actual_port}"

    lock_p = _server_lock_path(root)
    lock_p.write_text(
        json.dumps({"pid": os.getpid(), "port": actual_port, "url": url}, indent=2) + "\n",
        encoding="utf-8",
    )

    def watchdog() -> None:
        while not app.shutdown_event.is_set():
            time.sleep(0.5)
            if app.auto_exit and app.saw_client and (time.monotonic() - app.last_activity) > app.heartbeat_timeout:
                app.shutdown_event.set()
                break
        try:
            httpd.shutdown()
        except Exception:
            pass

    threading.Thread(target=watchdog, daemon=True).start()
    if open_browser:
        webbrowser.open(url)
    return httpd, app, url


def cmd_serve(root: Path, port: int = 0, open_browser: bool = False, auto_exit: bool = True) -> int:
    existing_url = _check_existing_server(root)
    if existing_url:
        print(f"[OK] Roadmap Studio already running at {existing_url}")
        if open_browser:
            webbrowser.open(existing_url)
        return 0

    httpd, app, url = start_server(root, port=port, open_browser=open_browser, auto_exit=auto_exit)
    print(f"[OK] Roadmap Studio serving at {url} (root: {root})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown_event.set()
        httpd.server_close()
        lock_p = _server_lock_path(root)
        if lock_p.exists():
            try:
                lock_p.unlink()
            except OSError:
                pass
    print("[OK] Roadmap Studio stopped.")
    return 0


# ---------------------------------------------------------------------------
# CLI Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roadmap_studio_ctl.py",
        description="Unified Kanban + Wardley + Cynefin/Kano Studio for .roadmap/ workspaces.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize .roadmap/ structure and open.ps1")
    p_init.add_argument("root", nargs="?", default=".", help="Repository root")
    p_init.add_argument("--title", default="Project Roadmap", help="Board title")
    p_init.add_argument("--anchor", default="USER", help="Wardley anchor label")
    p_init.add_argument("--force", action="store_true", help="Overwrite existing board.json")

    p_imp = sub.add_parser("import", help="Clone existing kanban.md or semantic stdin JSON into .roadmap/")
    p_imp.add_argument("root", nargs="?", default=".", help="Repository root")
    p_imp.add_argument("--stdin", action="store_true", help="Read semantic JSON card payload from stdin")
    p_imp.add_argument("--merge", action="store_true", help="Overwrite matching card IDs")

    p_srv = sub.add_parser("serve", help="Launch interactive Roadmap Studio web server")
    p_srv.add_argument("root", nargs="?", default=".", help="Repository root")
    p_srv.add_argument("--port", type=int, default=0, help="Port to bind (default: random free port)")
    p_srv.add_argument("--open", action="store_true", help="Open in default browser")
    p_srv.add_argument("--no-auto-exit", action="store_true", help=argparse.SUPPRESS)

    p_add = sub.add_parser("add", help="Add a card to .roadmap/board.json")
    p_add.add_argument("root", nargs="?", default=".", help="Repository root")
    p_add.add_argument("--id", default=None, help="Ticket ID (e.g. TKT-01)")
    p_add.add_argument("--prefix", default=None, help="Auto-allocate next free ID for this prefix (e.g. TKT)")
    p_add.add_argument("--title", required=True, help="Card title")
    p_add.add_argument("--column", default="todo", help="Target column ID")
    p_add.add_argument("--priority", default="Medium", help="Priority (Very High, High, Medium, Low, Very Low)")
    p_add.add_argument("--group", default="", help="Optional folder group ID (stores spec at tasks/<GROUP>/<ID>.md)")
    p_add.add_argument("--cynefin", choices=CYNEFIN_DOMAINS, default=None)
    p_add.add_argument("--kano", choices=KANO_VALUES, default=None)
    p_add.add_argument("--wardley", choices=WARDLEY_STAGES, default=None)
    p_add.add_argument("--visibility", type=int, choices=[1, 2, 3, 4, 5], default=None)
    p_add.add_argument("--with-spec", action="store_true", help="Scaffold tasks/<ID>.md")

    p_nxt = sub.add_parser("next-id", help="Find next free ticket ID(s) for a prefix across active and archived cards")
    p_nxt.add_argument("root", nargs="?", default=".", help="Repository root")
    p_nxt.add_argument("prefix", help="Ticket prefix (e.g. TKT, FIX, PLN, BUG)")
    p_nxt.add_argument("--count", type=int, default=1, help="Number of free IDs to emit (default: 1)")
    p_nxt.add_argument("--fill-gaps", action="store_true", help="Reuse gaps in numbering instead of starting after latest index")
    p_nxt.add_argument("--width", type=int, default=None, help="Zero-padding width (default: auto-detected, min 2)")
    p_nxt.add_argument("--json", action="store_true", help="Emit JSON with latest index and counts")

    p_mov = sub.add_parser("move", help="Move one or more cards to another column (warns if WIP limit exceeded)")
    p_mov.add_argument("root", nargs="?", default=".", help="Repository root")
    p_mov.add_argument("card_ids", nargs="+", help="Ticket ID(s)")
    p_mov.add_argument("column", help="Target column ID")
    p_mov.add_argument("--force", action="store_true", help="Accepted for backwards compatibility (WIP limit warns instead of blocking)")

    p_arc = sub.add_parser("archive", help="Archive one or more cards and move their specs to tasks/archived/")
    p_arc.add_argument("root", nargs="?", default=".", help="Repository root")
    p_arc.add_argument("card_ids", nargs="+", help="Ticket ID(s)")
    p_arc.add_argument("--milestone", default=None, help="Optional milestone label")

    p_shv = sub.add_parser("shelve", help="Shelve an abandoned/parked card with a reason")
    p_shv.add_argument("root", nargs="?", default=".", help="Repository root")
    p_shv.add_argument("card_id", help="Ticket ID")
    p_shv.add_argument("--reason", default="Shelved", help="Reason for shelving")

    p_loc = sub.add_parser("locate", help="Locate a card and print its spec path")
    p_loc.add_argument("root", nargs="?", default=".", help="Repository root")
    p_loc.add_argument("card_id", help="Ticket ID")
    p_loc.add_argument("--json", action="store_true", help="Emit JSON")

    p_cat = sub.add_parser("cat", help="Print card metadata and Markdown spec to stdout")
    p_cat.add_argument("root", nargs="?", default=".", help="Repository root")
    p_cat.add_argument("card_id", help="Ticket ID")

    p_con = sub.add_parser("consolidate", help="Bundle selected archived specs into a milestone file")
    p_con.add_argument("root", nargs="?", default=".", help="Repository root")
    p_con.add_argument("--milestone", required=True, help="Milestone name")
    p_con.add_argument("--ids", default=None, help="Comma-separated card IDs to include")
    p_con.add_argument("--all", action="store_true", help="Include all unbundled archived cards")
    p_con.add_argument("--keep-singles", action="store_true", help="Keep individual archived .md files")

    p_syn = sub.add_parser("sync-md", help="Update ROADMAP_STUDIO marker blocks inside .roadmap/*.md")
    p_syn.add_argument("root", nargs="?", default=".", help="Repository root")

    p_lst = sub.add_parser("list", help="Print board summary")
    p_lst.add_argument("root", nargs="?", default=".", help="Repository root")
    p_lst.add_argument("--json", action="store_true", help="Emit JSON")

    p_val = sub.add_parser("validate", help="Validate board references and WIP limits")
    p_val.add_argument("root", nargs="?", default=".", help="Repository root")

    p_exp = sub.add_parser("export-static", help="Export static read-only HTML snapshot")
    p_exp.add_argument("root", nargs="?", default=".", help="Repository root")
    p_exp.add_argument("--output", default=".roadmap/snapshot.html", help="Output HTML path")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "init":
        return cmd_init(root, title=args.title, anchor=args.anchor, force=args.force)
    if args.command == "import":
        return cmd_import(root, use_stdin=args.stdin, merge=args.merge)
    if args.command == "serve":
        return cmd_serve(root, port=args.port, open_browser=args.open, auto_exit=(not args.no_auto_exit))
    if args.command == "add":
        return cmd_add(
            root, args.id, args.title, column=args.column, priority=args.priority,
            cynefin=args.cynefin, kano=args.kano, wardley=args.wardley,
            visibility=args.visibility, with_spec=args.with_spec, prefix=args.prefix,
            group=args.group,
        )
    if args.command == "next-id":
        return cmd_next_id(
            root, args.prefix, count=args.count, fill_gaps=args.fill_gaps,
            width=args.width, as_json=args.json,
        )
    if args.command == "move":
        return cmd_move(root, args.card_ids, args.column, force=args.force)
    if args.command == "archive":
        return cmd_archive(root, args.card_ids, milestone=args.milestone)
    if args.command == "shelve":
        return cmd_shelve(root, args.card_id, reason=args.reason)
    if args.command == "locate":
        return cmd_locate(root, args.card_id, as_json=args.json)
    if args.command == "cat":
        return cmd_cat(root, args.card_id)
    if args.command == "consolidate":
        return cmd_consolidate(
            root, args.milestone, ids_csv=args.ids, use_all=args.all, keep_singles=args.keep_singles
        )
    if args.command == "sync-md":
        return cmd_sync_md(root)
    if args.command == "list":
        return cmd_list(root, as_json=args.json)
    if args.command == "validate":
        return cmd_validate(root)
    if args.command == "export-static":
        return cmd_export_static(root, output=args.output)
    return 1


if __name__ == "__main__":
    sys.exit(main())
