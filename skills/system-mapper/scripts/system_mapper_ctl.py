#!/usr/bin/env python3
"""
system_mapper_ctl.py - Executive Architecture Cartographer & System Ledger

Reads codebases of any size, extracts plain-English roles for files and processes,
groups them into logical architectural domains, and outputs colorized Mermaid
C4-style flowcharts and structured system ledgers.

Designed so non-coders, technical leads, and architects can quickly spot
system flows, bottlenecks, and issue directive high-level fixes.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# Common directories and patterns to ignore during scans
DEFAULT_IGNORES = {
    ".git", ".svn", ".hg",
    "node_modules", "vendor",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    ".venv", "venv", "env", ".env",
    "dist", "build", "out", ".next", ".nuxt", ".turbo",
    "target", ".cargo",
    ".idea", ".vscode",
    "coverage", ".nyc_output",
    ".system_generated", "scratch",
}

# Recognized code and config extensions
SUPPORTED_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".cs", ".swift",
    ".sh", ".bash", ".ps1",
    ".sql", ".graphql", ".proto",
    ".yaml", ".yml", ".json", ".toml"
}

# Domain / Category definitions with associated colors and icons
CATEGORIES = {
    "entrypoint": {
        "label": "Entrypoint / API / UI",
        "icon": "🔵",
        "color": "#1e40af",
        "stroke": "#3b82f6",
        "text": "#ffffff",
        "description": "Traffic ingress, UI components, API routers, CLI controllers"
    },
    "core": {
        "label": "Core Logic / Services",
        "icon": "🟢",
        "color": "#166534",
        "stroke": "#22c55e",
        "text": "#ffffff",
        "description": "Business rules, calculations, algorithms, orchestrators"
    },
    "async": {
        "label": "Async / Queues / Workers",
        "icon": "🟡",
        "color": "#854d0e",
        "stroke": "#eab308",
        "text": "#ffffff",
        "description": "Background jobs, schedulers, cron tasks, message consumers"
    },
    "storage": {
        "label": "Storage / Database / State",
        "icon": "🟣",
        "color": "#581c87",
        "stroke": "#a855f7",
        "text": "#ffffff",
        "description": "Databases, caches, repositories, models, migrations"
    },
    "external": {
        "label": "External Integration / Client",
        "icon": "⚪",
        "color": "#374151",
        "stroke": "#9ca3af",
        "text": "#ffffff",
        "description": "Third-party APIs, SDK clients, payment gateways, outbound webhooks"
    },
    "flag": {
        "label": "Hotspot / Tech Debt / Legacy",
        "icon": "🔴",
        "color": "#991b1b",
        "stroke": "#ef4444",
        "text": "#ffffff",
        "description": "Deprecated code, bottlenecks, circular loops, unhandled debt"
    },
    "config": {
        "label": "Config / Infrastructure",
        "icon": "⚙️",
        "color": "#475569",
        "stroke": "#64748b",
        "text": "#ffffff",
        "description": "Settings, environment setup, deployment descriptors, build rules"
    }
}

# Keywords used to heuristically categorize files
CATEGORY_KEYWORDS = {
    "flag": ["legacy", "deprecated", "old_", "_v1", "backup", "todo_fix", "hack"],
    "entrypoint": ["route", "controller", "endpoint", "api", "view", "page", "handler", "main", "app", "cli", "server"],
    "async": ["worker", "queue", "task", "job", "cron", "schedul", "consumer", "celery", "rabbit", "kafka", "event_bus"],
    "storage": ["db", "database", "repo", "store", "model", "schema", "migration", "cache", "redis", "postgres", "sql", "entity"],
    "external": ["client", "adapter", "sdk", "integration", "stripe", "twilio", "aws", "s3", "github", "webhook", "provider"],
    "config": ["config", "setting", "env", "docker", "setup", "manifest", "infra", "deploy"],
    "core": ["service", "manager", "engine", "domain", "logic", "processor", "calc", "helper", "util", "core"]
}


def sanitize_node_id(path_str: str) -> str:
    """Creates a deterministic and safe Mermaid node identifier."""
    clean = re.sub(r'[^a-zA-Z0-9_]', '_', path_str)
    clean = re.sub(r'_+', '_', clean).strip('_')
    return f"node_{clean}" if clean else "node_root"


def classify_file(relative_path: Path, content_snippet: str = "") -> str:
    """Classifies a file into an architectural category based on path and keywords."""
    p_lower = relative_path.as_posix().lower()
    snippet_lower = content_snippet[:2000].lower()

    # Priority 1: Flagged legacy or hotspots
    for kw in CATEGORY_KEYWORDS["flag"]:
        if kw in p_lower:
            return "flag"

    # Priority 2: Async workers & queues
    for kw in CATEGORY_KEYWORDS["async"]:
        if kw in p_lower:
            return "async"

    # Priority 3: Storage, models & persistence
    for kw in CATEGORY_KEYWORDS["storage"]:
        if kw in p_lower:
            return "storage"

    # Priority 4: External integrations & third-party adapters
    for kw in CATEGORY_KEYWORDS["external"]:
        if kw in p_lower:
            return "external"

    # Priority 5: Entrypoints, routes & UI
    for kw in CATEGORY_KEYWORDS["entrypoint"]:
        if kw in p_lower:
            return "entrypoint"

    # Priority 6: Config & infra
    for kw in CATEGORY_KEYWORDS["config"]:
        if kw in p_lower:
            return "config"

    # Priority 7: Content inspection fallback
    if "celery" in snippet_lower or "background_tasks" in snippet_lower:
        return "async"
    if "fastapi" in snippet_lower or "express" in snippet_lower or "router" in snippet_lower:
        return "entrypoint"
    if "sqlalchemy" in snippet_lower or "prisma" in snippet_lower or "mongoose" in snippet_lower:
        return "storage"
    if "requests.get" in snippet_lower or "fetch(" in snippet_lower or "axios" in snippet_lower:
        if "client" in snippet_lower or "api" in snippet_lower:
            return "external"

    # Default to Core Logic
    return "core"


def extract_file_role(file_path: Path, relative_path: Path, max_lines: int = 50) -> str:
    """Extracts a concise 1-sentence plain-English role from docstrings or comments."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [f.readline() for _ in range(max_lines)]
    except Exception:
        return "System file or executable module."

    text = "".join(lines)

    # 1. Look for Python docstring
    py_doc = re.search(r'^[ \t]*(?:"""|\'\'\')([\s\S]*?)(?:"""|\'\'\')', text, re.MULTILINE)
    if py_doc:
        doc = py_doc.group(1).strip()
        first_sentence = doc.split("\n\n")[0].replace("\n", " ").strip()
        first_sentence = re.sub(r'^[a-zA-Z0-9_\-\.]+ - ', '', first_sentence)
        if len(first_sentence) > 10:
            return clean_role_sentence(first_sentence)

    # 2. Look for JS/TS/C-style block comment /** ... */
    block_doc = re.search(r'/\*\*?([\s\S]*?)\*/', text)
    if block_doc:
        doc = block_doc.group(1).strip()
        cleaned = re.sub(r'^[ \t]*\*[ \t]?', '', doc, flags=re.MULTILINE)
        first_sentence = cleaned.strip().split("\n\n")[0].replace("\n", " ").strip()
        if len(first_sentence) > 10 and not is_license_header(first_sentence):
            return clean_role_sentence(first_sentence)

    # 3. Look for consecutive top-level # or // comments
    comment_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if comment_lines:
                break
            continue
        if stripped.startswith("#!"):
            continue
        if stripped.startswith("#") or stripped.startswith("//"):
            clean = re.sub(r'^[#/\s]+', '', stripped).strip()
            if not is_license_header(clean):
                comment_lines.append(clean)
        else:
            break

    if comment_lines:
        first_sentence = " ".join(comment_lines).split(". ")[0].strip()
        if len(first_sentence) > 10:
            return clean_role_sentence(first_sentence)

    # 4. Fallback inference based on name and category
    category = classify_file(relative_path, text)
    stem = relative_path.stem.replace("_", " ").replace("-", " ").capitalize()
    cat_desc = CATEGORIES.get(category, {}).get("description", "System module")
    return f"{stem} component ({cat_desc.lower()})."


def is_license_header(text: str) -> bool:
    """Detects standard open source / copyright headers."""
    t_lower = text.lower()
    return any(k in t_lower for k in ["copyright", "license", "spdx", "all rights reserved", "mit license", "apache"])


def clean_role_sentence(sentence: str, max_length: int = 120) -> str:
    """Trims and normalizes role text to a punchy single sentence."""
    s = re.sub(r'\s+', ' ', sentence).strip()
    if "." in s:
        s = s.split(". ")[0].strip()
        if not s.endswith("."):
            s += "."
    if len(s) > max_length:
        s = s[:max_length - 3] + "..."
    return s


def find_codebase_files(root_dir: Path, max_depth: int = 5, exclude_dirs: Optional[Set[str]] = None) -> List[Tuple[Path, Path]]:
    """Recursively walks root_dir collecting supported files, excluding ignores."""
    scanned: List[Tuple[Path, Path]] = []
    ignores = set(DEFAULT_IGNORES)
    if exclude_dirs:
        ignores.update(exclude_dirs)

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # In-place prune of ignored directories
        dirnames[:] = [d for d in dirnames if d not in ignores and not d.startswith(".")]

        rel_dir = Path(dirpath).resolve().relative_to(root_dir.resolve())
        if len(rel_dir.parts) > max_depth:
            continue

        for f in filenames:
            ext = Path(f).suffix.lower()
            if ext in SUPPORTED_EXTENSIONS or f in {"Dockerfile", "Makefile"}:
                full_path = Path(dirpath) / f
                rel_path = full_path.resolve().relative_to(root_dir.resolve())
                scanned.append((full_path, rel_path))

    return scanned


def detect_file_dependencies(file_path: Path, scanned_stems: Dict[str, str]) -> List[str]:
    """Detects internal project imports matching other scanned files."""
    deps: Set[str] = set()
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(15000)
    except Exception:
        return []

    # Python imports: import foo / from foo.bar import baz, qux
    for match in re.finditer(r'^\s*(?:from\s+([a-zA-Z0-9_\.]*)\s+import\s+([^\n]+)|import\s+([^\n]+))', content, re.MULTILINE):
        from_mod = match.group(1) or ""
        imports = match.group(2) or ""
        direct_mod = match.group(3) or ""
        for part in from_mod.split("."):
            if part in scanned_stems:
                deps.add(scanned_stems[part])
        for sym in re.split(r'[,() ]+', imports):
            sym_clean = sym.strip()
            if sym_clean in scanned_stems:
                deps.add(scanned_stems[sym_clean])
        for part in re.split(r'[,() ]+', direct_mod):
            part_stem = part.split(".")[-1].strip()
            if part_stem in scanned_stems:
                deps.add(scanned_stems[part_stem])

    # JS/TS imports: import ... from './foo', import './foo', or require('./foo')
    for match in re.finditer(r'(?:^\s*(?:import|export)\s+.*?\s+from\s*|^\s*import\s*|require\s*\(\s*)[\'"](?:\./|\.\./|@/)?([a-zA-Z0-9_\-\./]+)[\'"]', content, re.MULTILINE):
        raw_target = Path(match.group(1)).stem
        if raw_target in scanned_stems:
            deps.add(scanned_stems[raw_target])

    return sorted(list(deps))


def build_system_map(root_dir: Path, max_depth: int = 5, focus: Optional[str] = None, exclude_dirs: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Scans root_dir and constructs the full architectural model."""
    files = find_codebase_files(root_dir, max_depth=max_depth, exclude_dirs=exclude_dirs)

    # Map stems to relative posix paths for dependency resolution
    scanned_stems: Dict[str, str] = {}
    for full_path, rel_path in files:
        scanned_stems[rel_path.stem] = rel_path.as_posix()

    components: List[Dict[str, Any]] = []

    for full_path, rel_path in files:
        posix_str = rel_path.as_posix()
        if focus and focus.lower() not in posix_str.lower():
            continue

        category = classify_file(rel_path)
        role = extract_file_role(full_path, rel_path)
        deps = detect_file_dependencies(full_path, scanned_stems)
        # Avoid self-dependency
        deps = [d for d in deps if d != posix_str]

        # Detect top-level domain folder
        domain = rel_path.parts[0] if len(rel_path.parts) > 1 else "Root / Core"

        components.append({
            "id": sanitize_node_id(posix_str),
            "path": posix_str,
            "filename": rel_path.name,
            "domain": domain,
            "category": category,
            "role": role,
            "dependencies": deps
        })

    return {
        "root": str(root_dir.resolve()),
        "total_files": len(components),
        "components": components
    }


def generate_mermaid_flowchart(system_data: Dict[str, Any], direction: str = "TD") -> str:
    """Generates a colorized, C4-style Mermaid flowchart from system data."""
    components = system_data.get("components", [])
    if not components:
        return "```mermaid\nflowchart TD\n    Empty[No components detected in scope]\n```"

    lines = ["```mermaid", f"flowchart {direction}"]

    # 1. Palette definitions (Standard C4 colorized classes)
    lines.append("    %% Architectural Palette Classes")
    lines.append("    classDef actor fill:#0f172a,stroke:#475569,stroke-width:2px,color:#f8fafc;")
    lines.append("    classDef entrypoint fill:#1e40af,stroke:#3b82f6,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef core fill:#166534,stroke:#22c55e,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef async fill:#854d0e,stroke:#eab308,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef storage fill:#581c87,stroke:#a855f7,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef external fill:#374151,stroke:#9ca3af,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef flag fill:#991b1b,stroke:#ef4444,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef config fill:#475569,stroke:#64748b,stroke-width:1px,color:#ffffff;")

    # 2. Group components by domain or category
    domains: Dict[str, List[Dict[str, Any]]] = {}
    for comp in components:
        d = comp["domain"]
        domains.setdefault(d, []).append(comp)

    # Track map from path -> node_id for edges
    path_to_node: Dict[str, str] = {c["path"]: c["id"] for c in components}

    # 3. Render Subgraphs and Nodes
    subgraph_idx = 1
    for domain_name, comps in sorted(domains.items()):
        sub_id = f"sub_{subgraph_idx}_{re.sub(r'[^a-zA-Z0-9_]', '_', domain_name)}"
        lines.append(f"\n    subgraph {sub_id}[\"Domain: {domain_name}\"]")
        for c in comps:
            cat = c["category"]
            node_id = c["id"]
            fname = c["filename"]
            # Shorten role if necessary for neat diagram bubbles
            role_short = c["role"]
            if len(role_short) > 60:
                role_short = role_short[:57] + "..."
            # Clean HTML escape
            role_short = role_short.replace('"', "'")

            # Choose shape based on category
            if cat == "storage":
                shape = f"{node_id}[(\"{fname}<br/><i>{role_short}</i>\")]:::{cat}"
            elif cat == "flag":
                shape = f"{node_id}[\"⚠️ {fname}<br/><b>[HOTSPOT]</b> <i>{role_short}</i>\"]:::{cat}"
            else:
                shape = f"{node_id}[\"{fname}<br/><i>{role_short}</i>\"]:::{cat}"

            lines.append(f"        {shape}")
        lines.append("    end")
        subgraph_idx += 1

    # 4. Render Edges (Inter-module connections)
    edge_count = 0
    lines.append("\n    %% System Dataflow & Dependencies")
    for comp in components:
        src_id = comp["id"]
        for dep_path in comp.get("dependencies", []):
            if dep_path in path_to_node:
                target_id = path_to_node[dep_path]
                lines.append(f"    {src_id} --> {target_id}")
                edge_count += 1

    # If no internal edges were detected, link top-level entrypoints down to core/storage
    if edge_count == 0:
        lines.append("    %% Note: Loose coupling mode (showing standalone domain blocks)")

    lines.append("```")
    return "\n".join(lines)


def generate_system_table(system_data: Dict[str, Any]) -> str:
    """Generates the Markdown System Ledger table."""
    components = system_data.get("components", [])
    if not components:
        return "No components found."

    lines = [
        "| Component / File | Domain | Category | Plain-English Role | Calls / Depends On |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]

    for c in sorted(components, key=lambda x: (x["domain"], x["category"], x["filename"])):
        cat_info = CATEGORIES.get(c["category"], {})
        cat_badge = f"{cat_info.get('icon', '🔹')} {c['category'].capitalize()}"
        deps_str = ", ".join(f"`{d}`" for d in c["dependencies"][:3])
        if len(c["dependencies"]) > 3:
            deps_str += f" (+{len(c['dependencies']) - 3} more)"
        if not deps_str:
            deps_str = "*(Standalone / Ingress)*"

        lines.append(f"| `{c['path']}` | {c['domain']} | {cat_badge} | {c['role']} | {deps_str} |")

    return "\n".join(lines)


def generate_hotspots_report(system_data: Dict[str, Any]) -> str:
    """Analyzes components to highlight architectural smells or debt."""
    components = system_data.get("components", [])
    hotspots: List[str] = []

    # Count fan-in (how many modules import this file)
    fan_in: Dict[str, int] = {}
    for c in components:
        for dep in c.get("dependencies", []):
            fan_in[dep] = fan_in.get(dep, 0) + 1

    # Check 1: High fan-in bottlenecks (>5 callers)
    for c in components:
        callers = fan_in.get(c["path"], 0)
        if callers >= 5:
            hotspots.append(f"- **Critical Nexus / Bottleneck**: `{c['path']}` is imported by **{callers}** other modules. Changes here carry high regression risk.")

    # Check 2: Flagged files
    for c in components:
        if c["category"] == "flag":
            hotspots.append(f"- **Flagged / Technical Debt**: `{c['path']}` has markers of legacy code or unhandled debt (`{c['role']}`).")

    # Check 3: Entrypoint bypassing core directly into storage
    path_to_cat = {c["path"]: c["category"] for c in components}
    for c in components:
        if c["category"] == "entrypoint":
            for dep in c.get("dependencies", []):
                if path_to_cat.get(dep) == "storage":
                    hotspots.append(f"- **Layer Violation**: Entrypoint `{c['path']}` directly calls storage `{dep}`, bypassing business logic layer.")

    if not hotspots:
        return "✅ **Clean Architecture**: No obvious layering violations or high-risk bottlenecks detected."

    return "### ⚠️ Architectural Hotspots & Review Points\n" + "\n".join(hotspots)


def generate_full_report(system_data: Dict[str, Any], direction: str = "TD") -> str:
    """Generates a complete executive briefing ready for non-code leads."""
    total = system_data.get("total_files", 0)
    root = system_data.get("root", "")

    mermaid_code = generate_mermaid_flowchart(system_data, direction=direction)
    table_code = generate_system_table(system_data)
    hotspots_code = generate_hotspots_report(system_data)

    report = f"""# System Architecture Blueprint & Functional Map

**Target Root**: `{root}`  
**Analyzed Components**: {total} file(s)

---

## 1. High-Level Visual Architecture Map

This color-coded map illustrates how components are grouped by domain and how data flows across the system.

{mermaid_code}

### Color Legend for Non-Coders:
* 🔵 **Blue**: **Entrypoints / UI / API** — Ingress traffic, routes, pages, and CLI commands.
* 🟢 **Green**: **Core Logic / Services** — Business rules, calculations, and domain orchestrators.
* 🟡 **Amber**: **Async / Background Queues** — Scheduled jobs, workers, message consumers.
* 🟣 **Purple**: **Storage / State** — Databases, models, cache, state stores.
* ⚪ **Dark Slate**: **External Integrations** — Third-party SDKs, payment gateways, external APIs.
* 🔴 **Red**: **Hotspot / Tech Debt** — Legacy files, risky bottlenecks, or unhandled debt.

---

## 2. Plain-English System Ledger

{table_code}

---

## 3. Executive Review & Architectural Triage

{hotspots_code}

### Non-Coder Fix Guide:
1. **Identify the Broken Path**: Follow the arrows from the 🔵 Entrypoint to the 🟣 Storage layer.
2. **Spot Layer Bypasses**: If a 🔵 Entrypoint directly touches a 🟣 Storage component without passing through 🟢 Core Logic, request an encapsulation refactor.
3. **Decouple Bottlenecks**: Components with high incoming arrows should be broken into modular sub-services.
"""
    return report


def main():
    parser = argparse.ArgumentParser(description="System Mapper: Executive Architecture Cartographer")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: scan
    scan_p = subparsers.add_parser("scan", help="Scan codebase and output JSON structure")
    scan_p.add_argument("path", nargs="?", default=".", help="Root path of the codebase to scan")
    scan_p.add_argument("--depth", type=int, default=5, help="Maximum directory scan depth (default: 5)")
    scan_p.add_argument("--focus", type=str, default=None, help="Filter files containing this keyword")
    scan_p.add_argument("--exclude", "-e", type=str, default=None, help="Comma-separated directories to exclude")
    scan_p.add_argument("--json", action="store_true", help="Output raw JSON data")

    # Command: map (Mermaid)
    map_p = subparsers.add_parser("map", help="Generate colorized Mermaid C4-style diagram")
    map_p.add_argument("path", nargs="?", default=".", help="Root path of the codebase to scan")
    map_p.add_argument("--depth", type=int, default=5, help="Maximum directory scan depth (default: 5)")
    map_p.add_argument("--focus", type=str, default=None, help="Filter files containing this keyword")
    map_p.add_argument("--exclude", "-e", type=str, default=None, help="Comma-separated directories to exclude")
    map_p.add_argument("--direction", choices=["TD", "LR"], default="TD", help="Diagram orientation (default: TD)")
    map_p.add_argument("--output", type=str, default=None, help="Write output to a specific file")

    # Command: table
    tbl_p = subparsers.add_parser("table", help="Generate Markdown System Ledger table")
    tbl_p.add_argument("path", nargs="?", default=".", help="Root path of the codebase to scan")
    tbl_p.add_argument("--depth", type=int, default=5, help="Maximum directory scan depth (default: 5)")
    tbl_p.add_argument("--focus", type=str, default=None, help="Filter files containing this keyword")
    tbl_p.add_argument("--exclude", "-e", type=str, default=None, help="Comma-separated directories to exclude")
    tbl_p.add_argument("--output", type=str, default=None, help="Write output to a specific file")

    # Command: report
    rep_p = subparsers.add_parser("report", help="Generate full executive report (Diagram + Ledger + Hotspots)")
    rep_p.add_argument("path", nargs="?", default=".", help="Root path of the codebase to scan")
    rep_p.add_argument("--depth", type=int, default=5, help="Maximum directory scan depth (default: 5)")
    rep_p.add_argument("--focus", type=str, default=None, help="Filter files containing this keyword")
    rep_p.add_argument("--exclude", "-e", type=str, default=None, help="Comma-separated directories to exclude")
    rep_p.add_argument("--direction", choices=["TD", "LR"], default="TD", help="Diagram orientation (default: TD)")
    rep_p.add_argument("--output", type=str, default=None, help="Write output to a specific file")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    target_dir = Path(args.path).resolve()
    if not target_dir.exists():
        print(f"[ERROR] Path does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    exclude_dirs: Set[str] = set()
    if getattr(args, "exclude", None):
        for item in args.exclude.split(","):
            item_clean = item.strip()
            if item_clean:
                exclude_dirs.add(item_clean)

    system_data = build_system_map(target_dir, max_depth=args.depth, focus=args.focus, exclude_dirs=exclude_dirs)

    if args.command == "scan":
        if args.json:
            print(json.dumps(system_data, indent=2))
        else:
            print(f"=== System Scan: {system_data['root']} ===")
            print(f"Total Components Mapped: {system_data['total_files']}\n")
            for c in system_data["components"]:
                icon = CATEGORIES.get(c["category"], {}).get("icon", "🔹")
                print(f"{icon} [{c['category'].upper()}] {c['path']}")
                print(f"   Role: {c['role']}")
                if c["dependencies"]:
                    print(f"   Dependencies: {', '.join(c['dependencies'])}")
                print()

    elif args.command == "map":
        diagram = generate_mermaid_flowchart(system_data, direction=args.direction)
        if args.output:
            Path(args.output).write_text(diagram, encoding="utf-8")
            print(f"[OK] Mermaid diagram written to {args.output}")
        else:
            print(diagram)

    elif args.command == "table":
        table = generate_system_table(system_data)
        if args.output:
            Path(args.output).write_text(table, encoding="utf-8")
            print(f"[OK] System ledger written to {args.output}")
        else:
            print(table)

    elif args.command == "report":
        report = generate_full_report(system_data, direction=args.direction)
        if args.output:
            Path(args.output).write_text(report, encoding="utf-8")
            print(f"[OK] Full system report written to {args.output}")
        else:
            print(report)


if __name__ == "__main__":
    main()
