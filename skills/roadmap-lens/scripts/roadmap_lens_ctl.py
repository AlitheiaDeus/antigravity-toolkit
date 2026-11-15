#!/usr/bin/env python3
"""
roadmap_lens_ctl.py - Strategic Evolution (Wardley) & Triage (Cynefin/Kano) Visualizer

Strictly READ-ONLY against project files. Auto-detects roadmap/kanban.md or root
kanban.md, parses tasks/*.md and tasks/backlog/*.md (ignoring archived/), and
renders terminal summaries, Markdown triage matrices, or a self-contained
ChromaForge-themed interactive HTML/SVG HUD.

Zero external dependencies (Python 3.8+ standard library only).
"""

import argparse
import html as html_lib
import json
import re
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants & Taxonomies
# ---------------------------------------------------------------------------

CYNEFIN_DOMAINS = ("clear", "complicated", "complex", "chaotic")
KANO_VALUES = ("must-be", "performance", "delighter")
WARDLEY_STAGES = ("genesis", "custom", "product", "commodity")
RECOMMENDED_ACTIONS = ("Execute Now", "Spike First", "Hold")

TICKET_PREFIXES = ("PLN-", "TKT-", "BUG-", "TLK-")

CARD_REGEX = re.compile(
    r'^\s*(?P<var>[a-zA-Z0-9_\-]+)\[(?P<quote>["\']?)(?P<title>.*?)(?P=quote)\](?:\s*@\{(?P<meta>.*?)\})?\s*$'
)
COL_REGEX = re.compile(
    r'^\s*(?P<id>[a-zA-Z0-9_\-]+)\[(?P<quote>["\']?)(?P<title>.*?)(?P=quote)\]\s*$'
)
TICKET_ID_REGEX = re.compile(r'\b([A-Z]{2,5}-\d+)\b')

TAG_CYNEFIN_RE = re.compile(r'(?i)\bcynefin\s*[:=]\s*(clear|complicated|complex|chaotic)\b')
TAG_KANO_RE = re.compile(r'(?i)\bkano\s*[:=]\s*(must-be|must_be|mustbe|performance|delighter)\b')
TAG_WARDLEY_RE = re.compile(r'(?i)\bwardley\s*[:=]\s*(genesis|custom|product|commodity)\b')
TAG_VISIBILITY_RE = re.compile(r'(?i)\bvisibility\s*[:=]\s*([1-5])\b')
DEP_LINE_RE = re.compile(r'(?i)(?:dependencies|depends\s+on|blocked\s+by|upstream)\s*[:\-]\s*(.+)')


# ---------------------------------------------------------------------------
# Board Detection & Parsing (Strictly Read-Only)
# ---------------------------------------------------------------------------

def detect_kanban_base(root: Path) -> Tuple[Path, Optional[Path]]:
    """Auto-detect roadmap/kanban.md or root kanban.md (mirroring kanban_ctl.py)."""
    roadmap_kanban = root / "roadmap" / "kanban.md"
    root_kanban = root / "kanban.md"

    if roadmap_kanban.exists() and not root_kanban.exists():
        return root / "roadmap", roadmap_kanban
    if root_kanban.exists():
        return root, root_kanban
    if (root / "roadmap" / "tasks").exists() and not (root / "tasks").exists():
        return root / "roadmap", None
    return root, None


def _infer_ticket_from_var(var: str) -> str:
    m = re.match(r'^([a-zA-Z]+)(\d+)$', var)
    if m:
        prefix, num = m.groups()
        return f"{prefix.upper()}-{num}"
    return var.upper()


def _extract_prefix(ticket: str) -> str:
    for p in TICKET_PREFIXES:
        if ticket.upper().startswith(p):
            return p
    m = re.match(r'^([A-Z]+-)', ticket.upper())
    return m.group(1) if m else "OTHER"


def _parse_kanban_md(kanban_path: Path) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, str]]]:
    """Parse Mermaid kanban columns/cards and Markdown glance table."""
    cards_by_ticket: Dict[str, Dict[str, Any]] = {}
    table_by_ticket: Dict[str, Dict[str, str]] = {}

    if not kanban_path or not kanban_path.exists():
        return cards_by_ticket, table_by_ticket

    lines = kanban_path.read_text(encoding="utf-8", errors="replace").splitlines()
    in_mermaid = False
    in_kanban = False
    in_theme = False
    in_table = False
    current_col: Optional[str] = None

    for line in lines:
        stripped = line.strip()

        if not in_mermaid and not in_table:
            if stripped.startswith("```mermaid"):
                in_mermaid = True
                continue
            if "|" in line and "Ticket ID" in line and "Spec Document" in line:
                in_table = True
                continue

        if in_mermaid:
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
                    current_col = col_match.group("id").lower()
                    continue
                if card_match and current_col:
                    var = card_match.group("var")
                    title = card_match.group("title").strip()
                    meta_str = card_match.group("meta") or ""

                    ticket = None
                    t_match = re.search(
                        r"ticket\s*:\s*['\"](?:\[)?([^'\"\]]+)(?:\])?['\"]",
                        meta_str,
                    )
                    if t_match:
                        ticket = t_match.group(1).strip().upper()
                    if not ticket:
                        ticket = _infer_ticket_from_var(var)

                    priority = "Normal"
                    p_match = re.search(r"priority\s*:\s*['\"]([^'\"]+)['\"]", meta_str)
                    if p_match:
                        priority = p_match.group(1).strip()

                    cards_by_ticket[ticket] = {
                        "ticket": ticket,
                        "title": title,
                        "column": current_col,
                        "priority": priority,
                        "raw_meta": meta_str,
                    }
                    continue
        elif in_table:
            if re.match(r'^\s*\|(?:\s*:?-+:?\s*\|)+\s*$', line):
                continue
            if stripped.startswith("|") and stripped.endswith("|"):
                parts = [p.strip() for p in stripped.strip("|").split("|")]
                if len(parts) >= 5:
                    t_id = parts[0].strip("`[] ").upper()
                    if t_id and t_id != "TICKET ID":
                        link_m = re.search(r'\(([^)]+\.md)\)', parts[4])
                        table_by_ticket[t_id] = {
                            "grade": parts[1],
                            "title": parts[2],
                            "inspiration": parts[3],
                            "spec_link": link_m.group(1) if link_m else "",
                        }
            elif stripped:
                in_table = False

    return cards_by_ticket, table_by_ticket


def _is_archived_path(path: Path) -> bool:
    return any(part.lower() == "archived" for part in path.parts)


def _scan_task_files(base_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Scan tasks/*.md and tasks/backlog/*.md, strictly ignoring archived/."""
    tasks_dir = base_dir / "tasks"
    if not tasks_dir.exists():
        return {}

    candidates: List[Path] = []
    for p in sorted(tasks_dir.glob("*.md")):
        if not _is_archived_path(p):
            candidates.append(p)
    backlog_dir = tasks_dir / "backlog"
    if backlog_dir.exists():
        for p in sorted(backlog_dir.glob("*.md")):
            if not _is_archived_path(p):
                candidates.append(p)

    parsed: Dict[str, Dict[str, Any]] = {}
    for md_path in candidates:
        text = md_path.read_text(encoding="utf-8", errors="replace")
        rel_path = md_path.relative_to(base_dir).as_posix()

        ticket = None
        title = md_path.stem

        # Try heading first: # TKT-22: Title
        for line in text.splitlines()[:15]:
            h_match = re.match(r'^\s*#\s+(?:\[)?([A-Z]{2,5}-\d+)(?:\])?\s*[:\-–]\s*(.+)$', line)
            if h_match:
                ticket = h_match.group(1).upper()
                title = h_match.group(2).strip()
                break
            t_in_head = TICKET_ID_REGEX.search(line)
            if line.lstrip().startswith("#") and t_in_head:
                ticket = t_in_head.group(1).upper()
                title = line.lstrip("# ").strip()
                break

        if not ticket:
            fn_match = TICKET_ID_REGEX.search(md_path.stem.upper())
            if fn_match:
                ticket = fn_match.group(1).upper()
            else:
                # Fallback synthetic ID from filename
                clean_stem = re.sub(r'[^A-Za-z0-9]+', '-', md_path.stem).strip('-').upper()
                ticket = clean_stem[:16] or "TASK-00"

        # Extract optional explicit tags
        tags: Dict[str, Any] = {}
        m_cyn = TAG_CYNEFIN_RE.search(text)
        if m_cyn:
            tags["cynefin"] = m_cyn.group(1).lower()

        m_kan = TAG_KANO_RE.search(text)
        if m_kan:
            val = m_kan.group(1).lower().replace("_", "-")
            if val == "mustbe":
                val = "must-be"
            tags["kano"] = val

        m_war = TAG_WARDLEY_RE.search(text)
        if m_war:
            tags["wardley"] = m_war.group(1).lower()

        m_vis = TAG_VISIBILITY_RE.search(text)
        if m_vis:
            tags["visibility"] = int(m_vis.group(1))

        # Extract priority if mentioned in header blockquote
        priority = None
        m_prio = re.search(r'(?i)\*\*Priority\*\*\s*:\s*([A-Za-z]+)', text)
        if m_prio:
            priority = m_prio.group(1).strip()

        # Extract dependencies from explicit dependency lines first, then body refs
        deps: List[str] = []
        for line in text.splitlines():
            dep_m = DEP_LINE_RE.search(line)
            if dep_m:
                for ref in TICKET_ID_REGEX.findall(dep_m.group(1).upper()):
                    if ref != ticket and ref not in deps:
                        deps.append(ref)

        default_col = "backlog" if md_path.parent.name.lower() == "backlog" else "todo"

        parsed[ticket] = {
            "ticket": ticket,
            "title": title,
            "spec_path": rel_path,
            "body": text,
            "tags": tags,
            "dependencies": deps,
            "priority": priority,
            "default_column": default_col,
        }

    return parsed


# ---------------------------------------------------------------------------
# Heuristic Classification Engine
# ---------------------------------------------------------------------------

def _has_any(text: str, keywords: Tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(re.search(rf'\b{re.escape(kw)}\b', lower) for kw in keywords)


def classify_cynefin(ticket: str, prefix: str, priority: str, text: str, deps: List[str], explicit: Optional[str]) -> str:
    if explicit in CYNEFIN_DOMAINS:
        return explicit

    prio_l = priority.lower()
    if prefix == "BUG-" and (prio_l in ("high", "critical", "urgent") or _has_any(text, ("crash", "outage", "hotfix", "security", "panic", "corrupt", "broken"))):
        return "chaotic"
    if _has_any(text, ("outage", "hotfix", "data loss", "vulnerability", "exploit")):
        return "chaotic"

    if prefix == "PLN-" or _has_any(text, ("spike", "research", "experiment", "novel", "explore", "architecture", "strategy", "unknown", "prototype", "heuristic")):
        return "complex"

    if prefix == "TLK-" or prio_l == "high" or len(deps) >= 2 or _has_any(text, ("refactor", "migrate", "optimize", "pipeline", "engine", "parser", "graph", "sync", "audit", "integration")):
        return "complicated"

    return "clear"


def classify_kano(prefix: str, text: str, explicit: Optional[str]) -> str:
    if explicit in KANO_VALUES:
        return explicit

    if prefix == "BUG-" or _has_any(text, ("fix", "security", "auth", "crash", "validation", "guard", "test", "ci", "sanitize", "error", "fallback", "stability", "regression")):
        return "must-be"

    if _has_any(text, ("visual", "interactive", "hud", "theme", "animation", "canvas", "svg", "lens", "starmap", "delight", "magic", "studio", "1-click")):
        return "delighter"

    return "performance"


def classify_wardley(prefix: str, cynefin: str, text: str, explicit: Optional[str]) -> str:
    if explicit in WARDLEY_STAGES:
        return explicit

    if cynefin == "complex" and (prefix == "PLN-" or _has_any(text, ("experiment", "prototype", "novel", "spike", "concept", "idea"))):
        return "genesis"

    if prefix in ("PLN-", "TLK-") or _has_any(text, ("custom", "bespoke", "lens", "mapper", "engine", "parser", "hud", "starmap")):
        return "custom"

    if prefix == "BUG-" or _has_any(text, ("docs", "readme", "lint", "ci", "test", "gitignore", "cleanup", "config", "utility", "sanitize")):
        return "commodity"

    return "product"


def classify_visibility(text: str, explicit: Optional[int]) -> int:
    if isinstance(explicit, int) and 1 <= explicit <= 5:
        return explicit

    if _has_any(text, ("ui", "hud", "html", "dashboard", "button", "view", "ux", "frontend", "cli", "menu", "command", "slash")):
        return 5
    if _has_any(text, ("export", "report", "matrix", "table", "board", "preview", "skill", "chart")):
        return 4
    if _has_any(text, ("parser", "analyzer", "heuristic", "graph", "engine", "pipeline", "sync", "workflow")):
        return 3
    if _has_any(text, ("test", "audit", "guard", "sanitize", "schema", "config", "loader", "validator")):
        return 2
    if _has_any(text, ("storage", "db", "database", "file", "io", "stdlib", "bootstrap", "kernel", "infra")):
        return 1
    return 3


def compute_recommendation(column: str, cynefin: str, kano: str, priority: str, deps_count: int, dependents_count: int) -> Tuple[str, str, str]:
    """Return (recommended_action, structural_leverage, agent_directive_template)."""
    col_l = column.lower()

    if col_l in ("frozen", "completed"):
        action = "Hold"
    elif cynefin == "complex":
        action = "Spike First"
    elif cynefin == "complicated" and col_l in ("reported", "backlog") and deps_count >= 2:
        action = "Spike First"
    elif col_l == "backlog" and kano == "delighter" and priority.lower() != "high":
        action = "Hold"
    else:
        action = "Execute Now"

    score = dependents_count * 2 + (1 if priority.lower() == "high" else 0) + (1 if kano == "must-be" else 0)
    if score >= 3:
        leverage = "High"
    elif score >= 1:
        leverage = "Medium"
    else:
        leverage = "Low"

    return action, leverage, col_l


def build_agent_directive(ticket: str, cynefin: str, action: str, column: str) -> str:
    if column == "frozen":
        return f"Keep [{ticket}] shelved in Frozen until upstream priorities clear"
    if column == "completed":
        return f"Archive [{ticket}] via kanban-workflow-guard after final verification"
    if cynefin == "chaotic":
        return f"Stabilize [{ticket}] immediately: isolate root cause and add regression test"
    if action == "Spike First" or cynefin == "complex":
        return f"Scope [{ticket}] with a time-boxed spike first before committing to full implementation"
    if cynefin == "clear":
        return f"Promote [{ticket}] via kanban-workflow-guard and execute on Low /goal"
    return f"Plan [{ticket}] dependencies via /plan then execute via kanban-workflow-guard"


# ---------------------------------------------------------------------------
# Unified Repository Scout
# ---------------------------------------------------------------------------

def scout_roadmap(target_path: Path) -> Dict[str, Any]:
    """Read-only scan of kanban.md and tasks/ returning structured roadmap telemetry."""
    root = target_path.resolve()
    base_dir, kanban_path = detect_kanban_base(root)

    board_cards, table_rows = _parse_kanban_md(kanban_path) if kanban_path else ({}, {})
    task_files = _scan_task_files(base_dir)

    all_tickets: List[str] = list(board_cards.keys())
    for t in task_files:
        if t not in board_cards:
            all_tickets.append(t)

    cards: List[Dict[str, Any]] = []
    for ticket in all_tickets:
        b = board_cards.get(ticket, {})
        f = task_files.get(ticket, {})
        tbl = table_rows.get(ticket, {})

        title = b.get("title") or f.get("title") or tbl.get("title") or ticket
        column = b.get("column") or f.get("default_column") or "reported"
        priority = b.get("priority") or f.get("priority") or "Normal"
        spec_path = f.get("spec_path") or tbl.get("spec_link") or ""
        deps = list(f.get("dependencies", []))
        tags = f.get("tags", {})
        combined_text = f"{title}\n{f.get('body', '')}"
        prefix = _extract_prefix(ticket)

        cynefin = classify_cynefin(ticket, prefix, priority, combined_text, deps, tags.get("cynefin"))
        kano = classify_kano(prefix, combined_text, tags.get("kano"))
        wardley = classify_wardley(prefix, cynefin, combined_text, tags.get("wardley"))
        visibility = classify_visibility(combined_text, tags.get("visibility"))

        cards.append({
            "ticket": ticket,
            "prefix": prefix,
            "title": title,
            "column": column,
            "priority": priority,
            "spec_path": spec_path,
            "dependencies": deps,
            "dependents": [],
            "cynefin": cynefin,
            "kano": kano,
            "wardley": wardley,
            "visibility": visibility,
            "evolving": column in ("todo", "in_progress"),
        })

    return _finalize_roadmap_payload(
        cards,
        root_str=root.as_posix(),
        base_dir_str=base_dir.as_posix(),
        kanban_file_str=kanban_path.as_posix() if kanban_path else None,
    )


def _finalize_roadmap_payload(
    cards: List[Dict[str, Any]],
    root_str: str = ".",
    base_dir_str: str = ".",
    kanban_file_str: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute reverse dependents, leverage, defaults, and summary telemetry."""
    by_ticket = {c["ticket"]: c for c in cards}
    for c in cards:
        valid_deps = [d for d in c["dependencies"] if d in by_ticket and d != c["ticket"]]
        c["dependencies"] = valid_deps
        for d in valid_deps:
            if c["ticket"] not in by_ticket[d]["dependents"]:
                by_ticket[d]["dependents"].append(c["ticket"])

    for c in cards:
        action, leverage, col_l = compute_recommendation(
            c["column"],
            c["cynefin"],
            c["kano"],
            c["priority"],
            len(c["dependencies"]),
            len(c["dependents"]),
        )
        if not c.get("recommended_action"):
            c["recommended_action"] = action
        c["structural_leverage"] = leverage
        if not c.get("agent_directive"):
            c["agent_directive"] = build_agent_directive(
                c["ticket"], c["cynefin"], c["recommended_action"], col_l
            )

    by_col: Dict[str, int] = {}
    by_cynefin: Dict[str, int] = {k: 0 for k in CYNEFIN_DOMAINS}
    by_kano: Dict[str, int] = {k: 0 for k in KANO_VALUES}
    by_wardley: Dict[str, int] = {k: 0 for k in WARDLEY_STAGES}
    by_action: Dict[str, int] = {k: 0 for k in RECOMMENDED_ACTIONS}

    for c in cards:
        by_col[c["column"]] = by_col.get(c["column"], 0) + 1
        by_cynefin[c["cynefin"]] = by_cynefin.get(c["cynefin"], 0) + 1
        by_kano[c["kano"]] = by_kano.get(c["kano"], 0) + 1
        by_wardley[c["wardley"]] = by_wardley.get(c["wardley"], 0) + 1
        act = c["recommended_action"]
        by_action[act] = by_action.get(act, 0) + 1

    return {
        "root": root_str,
        "base_dir": base_dir_str,
        "kanban_file": kanban_file_str,
        "total_cards": len(cards),
        "summary": {
            "columns": by_col,
            "cynefin": by_cynefin,
            "kano": by_kano,
            "wardley": by_wardley,
            "actions": by_action,
        },
        "cards": cards,
    }


def normalize_roadmap_json(raw_payload: Any) -> Dict[str, Any]:
    """Normalize arbitrary repo-synthesized JSON into the Roadmap Lens HUD schema."""
    if isinstance(raw_payload, list):
        raw_cards = raw_payload
        meta: Dict[str, Any] = {}
    elif isinstance(raw_payload, dict):
        raw_cards = raw_payload.get("cards", [])
        meta = raw_payload
    else:
        raise ValueError("JSON payload must be a list of cards or an object with a 'cards' list.")

    cards: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_cards, start=1):
        if not isinstance(item, dict):
            continue
        raw_ticket = item.get("ticket") or item.get("id") or f"ITEM-{idx:02d}"
        ticket = str(raw_ticket).strip().upper()
        title = str(item.get("title") or ticket).strip()
        column = str(item.get("column") or item.get("status") or "todo").strip().lower().replace(" ", "_")
        priority = str(item.get("priority") or "Normal").strip()
        spec_path = str(item.get("spec_path") or "").strip()
        prefix = _extract_prefix(ticket)

        raw_deps = item.get("dependencies") or []
        deps = [str(d).strip().upper() for d in raw_deps if str(d).strip()]

        raw_cyn = str(item.get("cynefin") or "").strip().lower()
        cynefin = raw_cyn if raw_cyn in CYNEFIN_DOMAINS else classify_cynefin(
            ticket, prefix, priority, title, deps, None
        )

        raw_kano = str(item.get("kano") or "").strip().lower().replace("_", "-")
        if raw_kano == "mustbe":
            raw_kano = "must-be"
        kano = raw_kano if raw_kano in KANO_VALUES else classify_kano(prefix, title, None)

        raw_war = str(item.get("wardley") or "").strip().lower()
        wardley = raw_war if raw_war in WARDLEY_STAGES else classify_wardley(
            prefix, cynefin, title, None
        )

        raw_vis = item.get("visibility")
        try:
            vis_int = int(raw_vis) if raw_vis is not None else None
        except (TypeError, ValueError):
            vis_int = None
        visibility = vis_int if (vis_int is not None and 1 <= vis_int <= 5) else classify_visibility(title, None)

        cards.append({
            "ticket": ticket,
            "prefix": prefix,
            "title": title,
            "column": column,
            "priority": priority,
            "spec_path": spec_path,
            "dependencies": deps,
            "dependents": [],
            "cynefin": cynefin,
            "kano": kano,
            "wardley": wardley,
            "visibility": visibility,
            "evolving": bool(item["evolving"]) if "evolving" in item else column in ("todo", "in_progress"),
            "recommended_action": str(item.get("recommended_action") or "").strip(),
            "agent_directive": str(item.get("agent_directive") or "").strip(),
        })

    return _finalize_roadmap_payload(
        cards,
        root_str=str(meta.get("root") or "."),
        base_dir_str=str(meta.get("base_dir") or "."),
        kanban_file_str=meta.get("kanban_file"),
    )


# ---------------------------------------------------------------------------
# Output Formatters: Scout & Matrix
# ---------------------------------------------------------------------------

def format_scout_summary(data: Dict[str, Any]) -> str:
    s = data["summary"]
    lines = [
        "=== ROADMAP LENS // STRATEGIC & TRIAGE SCOUT ===",
        f"Board   : {data['kanban_file'] or '(no kanban.md; scanned tasks/)'}",
        f"Cards   : {data['total_cards']} active/backlog/frozen",
        "",
        "Columns : " + (", ".join(f"{k}={v}" for k, v in s["columns"].items()) or "none"),
        "Cynefin : " + ", ".join(f"{k}={v}" for k, v in s["cynefin"].items()),
        "Kano    : " + ", ".join(f"{k}={v}" for k, v in s["kano"].items()),
        "Wardley : " + ", ".join(f"{k}={v}" for k, v in s["wardley"].items()),
        "Actions : " + ", ".join(f"{k}={v}" for k, v in s["actions"].items()),
    ]
    if data["cards"]:
        lines.append("")
        lines.append("Top Tickets:")
        for c in data["cards"][:10]:
            lines.append(
                f"  - [{c['ticket']}] {c['title']} "
                f"({c['column']} | {c['cynefin']} | {c['kano']} | {c['wardley']} V{c['visibility']} -> {c['recommended_action']})"
            )
        if len(data["cards"]) > 10:
            lines.append(f"  ... and {len(data['cards']) - 10} more")
    return "\n".join(lines)


def format_markdown_matrix(data: Dict[str, Any]) -> str:
    if not data["cards"]:
        return "_No roadmap cards or tasks found._"

    lines = [
        "| Ticket | State | Cynefin Domain | Kano Value | Structural Leverage | Recommended Move |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for c in data["cards"]:
        lines.append(
            f"| `{c['ticket']}` {c['title']} | `{c['column']}` | "
            f"{c['cynefin'].title()} | {c['kano'].title()} | "
            f"{c['structural_leverage']} | **{c['recommended_action']}** |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive ChromaForge HTML/SVG Generator
# ---------------------------------------------------------------------------

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "resources" / "template.html"


def generate_html_viewer(data: Dict[str, Any], output_path: Path) -> Path:
    """Render self-contained ChromaForge HTML viewer to output_path."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    rendered = template.replace("__ROADMAP_JSON__", payload_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path

# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roadmap_lens_ctl.py",
        description="Read-only Wardley Map & Cynefin/Kano Triage Lens for kanban.md and tasks/.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scout = sub.add_parser("scout", help="Parse board & tasks and output summary or JSON.")
    p_scout.add_argument("path", nargs="?", default=".", help="Project root path (default: .)")
    p_scout.add_argument("--json", action="store_true", help="Output structured JSON payload")

    p_matrix = sub.add_parser("matrix", help="Output compact Markdown triage matrix.")
    p_matrix.add_argument("path", nargs="?", default=".", help="Project root path (default: .)")

    p_html = sub.add_parser("html", help="Generate interactive ChromaForge HTML HUD from kanban.md/tasks/.")
    p_html.add_argument("path", nargs="?", default=".", help="Project root path (default: .)")
    p_html.add_argument("--output", default=".agents/roadmap_lens.html", help="Output HTML file path (default: .agents/roadmap_lens.html)")
    p_html.add_argument("--open", action="store_true", help="Open generated HTML in default browser (opt-in)")

    p_render = sub.add_parser("render", help="Render ChromaForge HTML HUD from synthesized JSON (--stdin or --data).")
    src_group = p_render.add_mutually_exclusive_group(required=True)
    src_group.add_argument("--stdin", action="store_true", help="Read structured roadmap JSON from stdin")
    src_group.add_argument("--data", help="Path to structured roadmap JSON file")
    p_render.add_argument("--output", default=".agents/roadmap_lens.html", help="Output HTML file path (default: .agents/roadmap_lens.html)")
    p_render.add_argument("--open", action="store_true", help="Open generated HTML in default browser (opt-in)")

    return parser


def _write_and_maybe_open(data: Dict[str, Any], output_arg: str, open_browser: bool) -> int:
    out = Path(output_arg)
    if not out.is_absolute():
        out = Path.cwd() / out
    written = generate_html_viewer(data, out)
    print(f"[OK] Generated Roadmap Lens HUD: {written}")
    if open_browser:
        webbrowser.open(written.resolve().as_uri())
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "render":
        if args.stdin:
            raw_text = sys.stdin.read()
        else:
            raw_text = Path(args.data).read_text(encoding="utf-8")
        raw_payload = json.loads(raw_text)
        data = normalize_roadmap_json(raw_payload)
        return _write_and_maybe_open(data, args.output, args.open)

    target = Path(args.path)
    data = scout_roadmap(target)

    if args.command == "scout":
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(format_scout_summary(data))
        return 0

    if args.command == "matrix":
        print(format_markdown_matrix(data))
        return 0

    if args.command == "html":
        return _write_and_maybe_open(data, args.output, args.open)

    return 1


if __name__ == "__main__":
    sys.exit(main())
