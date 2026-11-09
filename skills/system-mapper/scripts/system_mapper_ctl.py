#!/usr/bin/env python3
"""
system_mapper_ctl.py - Executive Architecture Cartographer & Intent-Aware System Scout

Reads codebases of any size, extracts plain-English roles for files and processes,
identifies God-files, unpacks embedded subsystems, detects "Tightrope" coupling debt
(proxy pass-throughs, in-memory bleeds), harvests roadmap tickets (TKT-XX), and outputs
rich architectural telemetry and colorized C4-style Mermaid flowcharts.

Designed so non-coders, technical leads, and architects can quickly spot
system flows, bottlenecks, and issue directive high-level fixes.

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import ast
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
            content = f.read(25000)
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


# =========================================================================
# ADVANCED ARCHITECTURAL TELEMETRY (Intent & Tension Probes)
# =========================================================================

def detect_god_files_and_subsystems(file_path: Path, content: str, line_threshold: int = 500) -> Optional[Dict[str, Any]]:
    """Identifies God-files and unpacks their internal method clusters and composition."""
    lines = content.splitlines()
    total_lines = len(lines)
    if total_lines < line_threshold:
        return None

    posix_path = file_path.as_posix()
    detected_subsystems: List[Dict[str, Any]] = []
    embedded_instances: Set[str] = set()

    # Try native AST analysis for Python
    if file_path.suffix == ".py":
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check instantiated instances in __init__
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                            for sub in ast.walk(item):
                                if isinstance(sub, ast.Assign):
                                    for target in sub.targets:
                                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                                            if isinstance(sub.value, ast.Call):
                                                if isinstance(sub.value.func, ast.Name):
                                                    embedded_instances.add(f"self.{target.attr} ({sub.value.func.id})")
                                                elif isinstance(sub.value.func, ast.Attribute):
                                                    embedded_instances.add(f"self.{target.attr} ({sub.value.func.attr})")

                    # Cluster methods by prefix or domain
                    method_names = [m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                    prefix_counts: Dict[str, List[str]] = {}
                    for m in method_names:
                        parts = m.strip("_").split("_")
                        prefix = parts[0] if parts else ""
                        if len(prefix) >= 2:
                            prefix_counts.setdefault(prefix, []).append(m)

                    for pfx, m_list in prefix_counts.items():
                        if len(m_list) >= 3 and pfx not in {"get", "set", "is", "has", "init"}:
                            detected_subsystems.append({
                                "prefix": pfx,
                                "name": f"{pfx.upper()} Subsystem",
                                "method_count": len(m_list),
                                "methods": m_list[:5]
                            })
        except Exception:
            pass

    # Regex fallback or supplement for JS/TS/Python
    if not detected_subsystems:
        method_matches = re.findall(r'(?:def|async def|function)\s+([a-zA-Z0-9_]+)\(', content)
        prefix_map: Dict[str, List[str]] = {}
        for m in method_matches:
            prefix = m.strip("_").split("_")[0]
            if len(prefix) >= 2:
                prefix_map.setdefault(prefix, []).append(m)
        for pfx, m_list in prefix_map.items():
            if len(m_list) >= 4 and pfx not in {"get", "set", "is", "has", "init", "handle"}:
                detected_subsystems.append({
                    "prefix": pfx,
                    "name": f"{pfx.upper()} Subsystem",
                    "method_count": len(m_list),
                    "methods": m_list[:5]
                })

    return {
        "file": posix_path,
        "line_count": total_lines,
        "detected_subsystems": detected_subsystems,
        "embedded_instances": sorted(list(embedded_instances))
    }


def detect_proxy_tightropes(file_path: Path, content: str) -> List[Dict[str, Any]]:
    """Detects 'Tightrope' proxy method delegation patterns (e.g., sim forwarding 20+ methods to self.c2)."""
    proxy_counts: Dict[str, List[str]] = {}

    # Match def method(self, ...): return self.target.method(...) or self.target.method(...)
    pattern = r'def\s+([a-zA-Z0-9_]+)\(self,[^\)]*\):\s*(?:"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')?\s*(?:return\s+)?self\.([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\('
    for match in re.finditer(pattern, content):
        method_name, target_obj, forwarded_name = match.groups()
        if target_obj not in {"_logger", "logger", "log"}:
            proxy_counts.setdefault(f"self.{target_obj}", []).append(f"{method_name} ➔ {forwarded_name}()")

    results: List[Dict[str, Any]] = []
    for target, methods in proxy_counts.items():
        if len(methods) >= 3:
            results.append({
                "file": file_path.as_posix(),
                "target": target,
                "proxy_count": len(methods),
                "sample_methods": methods[:5]
            })

    return results


def detect_in_memory_bleeds(file_path: Path, content: str) -> List[Dict[str, Any]]:
    """Detects in-memory object references leaking across network/airgap boundaries."""
    bleeds: List[Dict[str, Any]] = []
    posix_path = file_path.as_posix()
    p_lower = posix_path.lower()

    # Web servers, GCS routers, or API handlers holding simulator / physics engines directly in memory
    is_interface = any(k in p_lower for k in ["web_server", "router", "gcs", "api", "controller", "endpoint"])
    if is_interface:
        # Check constructor or attributes
        leaks = re.findall(r'self\.(sim|simulator|engine|firmware|drones|fc_twin)\b', content)
        if leaks:
            unique_leaks = sorted(list(set(leaks)))
            bleeds.append({
                "file": posix_path,
                "type": "In-Memory Airgap Bleed",
                "severity": "HIGH",
                "leak": f"Holds direct reference to {', '.join(f'self.{l}' for l in unique_leaks)} in-memory rather than network serialization"
            })

        # Check app['sim'] or request.app['sim']
        dict_leaks = re.findall(r'(?:request\.)?app\[[\'"](sim|simulator|engine|drones)[\'"]\]', content)
        if dict_leaks:
            unique_dict_leaks = sorted(list(set(dict_leaks)))
            bleeds.append({
                "file": posix_path,
                "type": "In-Memory State Sharing",
                "severity": "MEDIUM",
                "leak": f"Shares {', '.join(unique_dict_leaks)} via web framework app state"
            })

    return bleeds


def detect_roadmap_tickets(file_path: Path, content: str) -> List[Dict[str, Any]]:
    """Harvests active tickets (TKT-XX, TODO, FIXME) with their contextual lines."""
    tickets: List[Dict[str, Any]] = []
    ticket_pattern = r'\b(TKT-\d+|ISSUE-\d+|TASK-\d+|TODO|FIXME|DEPRECATED)\b[:\s\-]*([^\r\n]*)'

    for line_idx, line in enumerate(content.splitlines(), start=1):
        for match in re.finditer(ticket_pattern, line):
            tag, note = match.groups()
            cleaned_note = note.strip().strip("#/*-")
            tickets.append({
                "file": file_path.as_posix(),
                "line": line_idx,
                "tag": tag,
                "note": cleaned_note[:80] if cleaned_note else "Active roadmap marker"
            })

    return tickets


def detect_network_bindings(file_path: Path, content: str) -> List[Dict[str, Any]]:
    """Detects physical network port listeners, broadcasts, and protocol boundaries."""
    bindings: List[Dict[str, Any]] = []
    # Match port patterns: port=9000, Port 9001, port: 14550, bind(('...', 9000))
    port_pattern = r'(?:port|Port)\s*[:= ]\s*(\d{4,5})|\b(?:bind|listen)\s*\(\s*.*?(\d{4,5})\b'
    found_ports: Set[int] = set()

    for match in re.finditer(port_pattern, content):
        port_str = match.group(1) or match.group(2)
        if port_str:
            p = int(port_str)
            if 1024 <= p <= 65535:
                found_ports.add(p)

    if found_ports:
        # Detect protocol hints
        proto = "TCP/UDP"
        c_lower = content.lower()
        if "mavlink" in c_lower:
            proto = "MAVLink UDP"
        elif "ws" in c_lower or "websocket" in c_lower:
            proto = "WebSocket"
        elif "aiohttp" in c_lower or "fastapi" in c_lower or "http" in c_lower:
            proto = "HTTP / REST"

        for p in sorted(list(found_ports)):
            bindings.append({
                "file": file_path.as_posix(),
                "port": p,
                "protocol": proto
            })

    return bindings


def build_system_map(root_dir: Path, max_depth: int = 5, focus: Optional[str] = None, exclude_dirs: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Scans root_dir and constructs the full architectural model including telemetry."""
    files = find_codebase_files(root_dir, max_depth=max_depth, exclude_dirs=exclude_dirs)

    # Map stems to relative posix paths for dependency resolution
    scanned_stems: Dict[str, str] = {}
    for full_path, rel_path in files:
        scanned_stems[rel_path.stem] = rel_path.as_posix()

    components: List[Dict[str, Any]] = []
    god_files: List[Dict[str, Any]] = []
    tightropes: List[Dict[str, Any]] = []
    bleeds: List[Dict[str, Any]] = []
    all_tickets: List[Dict[str, Any]] = []
    network_bindings: List[Dict[str, Any]] = []

    for full_path, rel_path in files:
        posix_str = rel_path.as_posix()
        if focus and focus.lower() not in posix_str.lower():
            continue

        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(50000)
        except Exception:
            content = ""

        category = classify_file(rel_path, content)
        role = extract_file_role(full_path, rel_path)
        deps = detect_file_dependencies(full_path, scanned_stems)
        deps = [d for d in deps if d != posix_str]

        # Domain grouping heuristic
        domain = rel_path.parts[0] if len(rel_path.parts) > 1 else "Root / Core"

        # Harvest tickets for this component
        comp_tickets = detect_roadmap_tickets(rel_path, content)
        all_tickets.extend(comp_tickets)

        # Harvest God-files
        gf = detect_god_files_and_subsystems(rel_path, content)
        if gf:
            god_files.append(gf)

        # Harvest tightropes
        proxies = detect_proxy_tightropes(rel_path, content)
        tightropes.extend(proxies)

        # Harvest in-memory bleeds
        in_mem = detect_in_memory_bleeds(rel_path, content)
        bleeds.extend(in_mem)

        # Harvest network bindings
        net = detect_network_bindings(rel_path, content)
        network_bindings.extend(net)

        components.append({
            "id": sanitize_node_id(posix_str),
            "path": posix_str,
            "filename": rel_path.name,
            "domain": domain,
            "category": category,
            "role": role,
            "dependencies": deps,
            "ticket_count": len(comp_tickets)
        })

    return {
        "root": str(root_dir.resolve()),
        "total_files": len(components),
        "components": components,
        "telemetry": {
            "god_files": god_files,
            "proxy_tightropes": tightropes,
            "in_memory_bleeds": bleeds,
            "roadmap_tickets": all_tickets,
            "network_bindings": network_bindings
        }
    }


def generate_mermaid_flowchart(system_data: Dict[str, Any], direction: str = "TD") -> str:
    """Generates an intent-aware colorized C4 Mermaid flowchart with tightrope styling."""
    components = system_data.get("components", [])
    telemetry = system_data.get("telemetry", {})
    god_files = {g["file"]: g for g in telemetry.get("god_files", [])}
    tightropes = telemetry.get("proxy_tightropes", [])
    bleeds = telemetry.get("in_memory_bleeds", [])

    if not components:
        return "```mermaid\nflowchart TD\n    Empty[No components detected in scope]\n```"

    lines = ["```mermaid", f"flowchart {direction}"]

    # 1. Palette definitions (Standard C4 colorized classes + Tightrope styles)
    lines.append("    %% Architectural Palette Classes")
    lines.append("    classDef actor fill:#0f172a,stroke:#475569,stroke-width:2px,color:#f8fafc;")
    lines.append("    classDef entrypoint fill:#1e40af,stroke:#3b82f6,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef core fill:#166534,stroke:#22c55e,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef async fill:#854d0e,stroke:#eab308,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef storage fill:#581c87,stroke:#a855f7,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef external fill:#374151,stroke:#9ca3af,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef flag fill:#991b1b,stroke:#ef4444,stroke-width:2px,color:#ffffff;")
    lines.append("    classDef config fill:#475569,stroke:#64748b,stroke-width:1px,color:#ffffff;")
    lines.append("    classDef tightrope fill:#332200,stroke:#ffb800,stroke-width:2px,stroke-dasharray: 5 5,color:#fff4d4;")

    # 2. Group components by domain
    domains: Dict[str, List[Dict[str, Any]]] = {}
    for comp in components:
        d = comp["domain"]
        domains.setdefault(d, []).append(comp)

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
            p_str = c["path"]
            role_short = c["role"].replace('"', "'")
            if len(role_short) > 60:
                role_short = role_short[:57] + "..."

            # Append ticket marker if present
            if c.get("ticket_count", 0) > 0:
                role_short += f" <b>[{c['ticket_count']} Tasks]</b>"

            # Check if this is a God-File
            if p_str in god_files:
                gf_info = god_files[p_str]
                lines.append(f"        {node_id}[\"👑 {fname} ({gf_info['line_count']} Lines)<br/><i>{role_short}</i>\"]:::{cat}")
                # Render embedded subsystems inside God-file
                for s in gf_info.get("detected_subsystems", [])[:3]:
                    sub_node_id = f"{node_id}_{s['prefix']}"
                    lines.append(f"        {sub_node_id}[\"• Subsystem: {s['name']} ({s['method_count']} methods)\"]:::core")
                    lines.append(f"        {node_id} --- {sub_node_id}")
            elif cat == "storage":
                lines.append(f"        {node_id}[(\"{fname}<br/><i>{role_short}</i>\")]:::{cat}")
            elif cat == "flag":
                lines.append(f"        {node_id}[\"⚠️ {fname}<br/><b>[HOTSPOT]</b> <i>{role_short}</i>\"]:::{cat}")
            else:
                lines.append(f"        {node_id}[\"{fname}<br/><i>{role_short}</i>\"]:::{cat}")

        lines.append("    end")
        subgraph_idx += 1

    # 4. Render 'Tightropes' Subgraph if coupling smells are detected
    if tightropes or bleeds:
        lines.append("\n    subgraph TIGHTROPES[\"⚠️ The Web of Tightropes (Monolithic Debt & Leaks)\"]")
        lines.append("        direction LR")
        for idx, t in enumerate(tightropes, start=1):
            t_node = f"tightrope_proxy_{idx}"
            lines.append(f"        {t_node}[\"Proxy Debt: {t['proxy_count']} methods forwarding to {t['target']}<br/><i>in {Path(t['file']).name}</i>\"]:::tightrope")
            src_node = path_to_node.get(t['file'])
            if src_node:
                lines.append(f"        {src_node} -.->|Forwards calls| {t_node}")

        for idx, b in enumerate(bleeds, start=1):
            b_node = f"tightrope_bleed_{idx}"
            lines.append(f"        {b_node}[\"In-Memory Bleed: {b['leak']}\"]:::tightrope")
            src_node = path_to_node.get(b['file'])
            if src_node:
                lines.append(f"        {src_node} -.->|Holds in-memory| {b_node}")
        lines.append("    end")

    # 5. Render Inter-module Dependency Edges
    lines.append("\n    %% Clean System Dataflows")
    for comp in components:
        src_id = comp["id"]
        for dep_path in comp.get("dependencies", []):
            if dep_path in path_to_node:
                target_id = path_to_node[dep_path]
                lines.append(f"    {src_id} --> {target_id}")

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


def generate_telemetry_report(system_data: Dict[str, Any]) -> str:
    """Formats the architectural telemetry into an executive briefing."""
    telemetry = system_data.get("telemetry", {})
    god_files = telemetry.get("god_files", [])
    tightropes = telemetry.get("proxy_tightropes", [])
    bleeds = telemetry.get("in_memory_bleeds", [])
    tickets = telemetry.get("roadmap_tickets", [])
    net_bindings = telemetry.get("network_bindings", [])

    lines = ["# Architectural Telemetry & Intent Briefing\n"]

    # 1. God-Files & Subsystems
    lines.append("## 1. 👑 God-Files & Hidden Subsystems")
    if god_files:
        for g in god_files:
            lines.append(f"* **`{g['file']}`** — **{g['line_count']:,} Lines of Code**")
            if g["detected_subsystems"]:
                lines.append("  * *Detected Embedded Subsystems*:")
                for sub in g["detected_subsystems"]:
                    lines.append(f"    * `{sub['name']}` ({sub['method_count']} methods, prefix: `{sub['prefix']}_`)")
            if g["embedded_instances"]:
                lines.append(f"  * *Instantiated Components*: {', '.join(g['embedded_instances'])}")
    else:
        lines.append("✅ No monolithic God-files (>500 lines) detected.")
    lines.append("")

    # 2. Tightropes & Coupling Smells
    lines.append("## 2. ⚠️ The Web of Tightropes (Coupling & Debt)")
    if tightropes or bleeds:
        for t in tightropes:
            lines.append(f"* **Proxy Delegation**: `{t['file']}` delegates **{t['proxy_count']}** methods directly to `{t['target']}`")
            lines.append(f"  * *Examples*: {', '.join(t['sample_methods'][:3])}")
        for b in bleeds:
            lines.append(f"* **[{b['severity']}] {b['type']}**: `{b['file']}` — {b['leak']}")
    else:
        lines.append("✅ No proxy method tightropes or in-memory boundary bleeds detected.")
    lines.append("")

    # 3. Network Boundaries
    lines.append("## 3. 🌐 Physical Network Boundaries & Protocols")
    if net_bindings:
        for n in net_bindings:
            lines.append(f"* **Port {n['port']}** ({n['protocol']}): Defined in `{n['file']}`")
    else:
        lines.append("ℹ️ No hardcoded network port bindings detected.")
    lines.append("")

    # 4. Roadmap & Active Tickets
    lines.append("## 4. 🎯 Active Roadmap Tickets & Tasks")
    if tickets:
        tag_groups: Dict[str, List[Dict[str, Any]]] = {}
        for tk in tickets:
            tag_groups.setdefault(tk["tag"], []).append(tk)

        for tag, items in sorted(tag_groups.items()):
            lines.append(f"* **`{tag}`** ({len(items)} references):")
            for item in items[:4]:
                lines.append(f"  * `{item['file']}:{item['line']}` — *{item['note']}*")
            if len(items) > 4:
                lines.append(f"  * ... (+{len(items) - 4} more)")
    else:
        lines.append("ℹ️ No active tickets or TODO markers found in comments.")

    return "\n".join(lines)


def generate_full_report(system_data: Dict[str, Any], direction: str = "TD") -> str:
    """Generates a complete executive briefing ready for non-code leads."""
    total = system_data.get("total_files", 0)
    root = system_data.get("root", "")

    mermaid_code = generate_mermaid_flowchart(system_data, direction=direction)
    table_code = generate_system_table(system_data)
    telemetry_code = generate_telemetry_report(system_data)

    report = f"""# System Architecture Blueprint & Intent-Aware Map

**Target Root**: `{root}`  
**Analyzed Components**: {total} file(s)

---

## 1. High-Level Visual Architecture Map (C4 Model)

This diagram visualizes architectural domains, active tasks, God-file subsystems, and **The Web of Tightropes** (in-memory bleeds & proxy debt).

{mermaid_code}

### Color Legend for Non-Coders:
* 🔵 **Blue**: **Entrypoints / UI / API** — Ingress traffic, routes, pages, and CLI commands.
* 🟢 **Green**: **Core Logic / Services** — Business rules, calculations, and domain orchestrators.
* 🟡 **Amber**: **Async / Background Queues** — Scheduled jobs, workers, message consumers.
* 🟣 **Purple**: **Storage / State** — Databases, models, cache, state stores.
* ⚪ **Dark Slate**: **External Integrations** — Third-party SDKs, payment gateways, external APIs.
* 🔴 **Red**: **Hotspot / Tech Debt** — Legacy files, risky bottlenecks, or unhandled debt.
* 🟨 **Dashed Amber**: **The Tightropes** — In-memory leaks and monolithic proxy delegation.

---

## 2. Architectural Telemetry & Intent Briefing

{telemetry_code}

---

## 3. Plain-English System Ledger

{table_code}
"""
    return report


def main():
    parser = argparse.ArgumentParser(description="System Mapper: Executive Architecture Cartographer & Intent Scout")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: scan
    scan_p = subparsers.add_parser("scan", help="Scan codebase and output JSON structure")
    scan_p.add_argument("path", nargs="?", default=".", help="Root path of the codebase to scan")
    scan_p.add_argument("--depth", type=int, default=5, help="Maximum directory scan depth (default: 5)")
    scan_p.add_argument("--focus", type=str, default=None, help="Filter files containing this keyword")
    scan_p.add_argument("--exclude", "-e", type=str, default=None, help="Comma-separated directories to exclude")
    scan_p.add_argument("--json", action="store_true", help="Output raw JSON data")

    # Command: telemetry
    tel_p = subparsers.add_parser("telemetry", help="Extract God-files, tightropes, tickets, and network ports")
    tel_p.add_argument("path", nargs="?", default=".", help="Root path of the codebase to scan")
    tel_p.add_argument("--depth", type=int, default=5, help="Maximum directory scan depth (default: 5)")
    tel_p.add_argument("--focus", type=str, default=None, help="Filter files containing this keyword")
    tel_p.add_argument("--exclude", "-e", type=str, default=None, help="Comma-separated directories to exclude")
    tel_p.add_argument("--json", action="store_true", help="Output raw JSON data")
    tel_p.add_argument("--output", type=str, default=None, help="Write output to a specific file")

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
    rep_p = subparsers.add_parser("report", help="Generate full executive report (Diagram + Telemetry + Ledger)")
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

    elif args.command == "telemetry":
        if args.json:
            output_str = json.dumps(system_data.get("telemetry", {}), indent=2)
        else:
            output_str = generate_telemetry_report(system_data)

        if args.output:
            Path(args.output).write_text(output_str, encoding="utf-8")
            print(f"[OK] Telemetry briefing written to {args.output}")
        else:
            print(output_str)

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
