#!/usr/bin/env python3
"""
code_starmap_ctl.py - Codebase Chaos Starmap Engine

Deterministically maps the call-graph topology of a codebase using pure Python AST
and boundary sensing, rendering interactive HTML Starfield artifacts and Gephi GEXF exports.

Supports 2-tier Hierarchical Navigation:
- Level 1: Macro File-to-File Planetary Constellation (Zero Hairball).
- Level 2: Micro Function-to-Function Star Constellation (Exploded on demand).

Compatible with Python 3.8+ (Zero external dependencies).
"""

import argparse
import ast
import json
import math
import os
import re
import sys
import webbrowser
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET

IGNORED_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".pytest_cache", ".tox", ".eggs", "dist", "build", ".mypy_cache"
}

BUILTIN_FUNCS = {
    "print", "len", "range", "str", "int", "float", "bool", "list", "dict", "set",
    "tuple", "enumerate", "zip", "map", "filter", "any", "all", "min", "max",
    "sum", "isinstance", "issubclass", "getattr", "setattr", "hasattr", "open",
    "super", "type", "id", "hash", "repr", "iter", "next", "sorted", "reversed"
}


CYBER_PALETTE: List[Tuple[int, int, int]] = [
    (0, 240, 255),    # Electric Cyan
    (217, 70, 239),   # Neon Magenta
    (245, 158, 11),   # Cyber Amber
    (16, 185, 129),   # Emerald
    (168, 85, 247),   # Plasma Purple
    (56, 189, 248),   # Sky Blue
    (251, 113, 133),  # Hot Pink / Rose
    (52, 211, 153),   # Electric Mint
    (249, 115, 22),   # High-Voltage Orange
    (129, 140, 248),  # Lavender Indigo
    (234, 179, 8),    # Solar Yellow
    (14, 165, 233),   # Deep Cyan
    (244, 63, 94),    # Crimson Red
    (132, 204, 22),   # Neon Lime
]


def get_subsystem(file_path: str) -> str:
    """Extracts logical module or subsystem folder name for categorization."""
    parts = Path(file_path).parts
    if len(parts) <= 1:
        return "root"
    if parts[0] in ("skills", "src", "packages", "apps", "libs", "modules", "services") and len(parts) >= 2:
        return parts[1]
    return parts[0]


def hsl_to_rgb(h: float, s: float, l: float) -> Tuple[int, int, int]:
    """Converts HSL (h in [0, 360), s in [0, 1], l in [0, 1]) to integer RGB [0, 255]."""
    c = (1.0 - abs(2.0 * l - 1.0)) * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = l - c / 2.0
    if 0 <= h < 60:
        r1, g1, b1 = c, x, 0.0
    elif 60 <= h < 120:
        r1, g1, b1 = x, c, 0.0
    elif 120 <= h < 180:
        r1, g1, b1 = 0.0, c, x
    elif 180 <= h < 240:
        r1, g1, b1 = 0.0, x, c
    elif 240 <= h < 300:
        r1, g1, b1 = x, 0.0, c
    else:
        r1, g1, b1 = c, 0.0, x
    return (int((r1 + m) * 255), int((g1 + m) * 255), int((b1 + m) * 255))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass
class Node:
    id: str
    label: str
    file: str
    cluster: str
    stellar_type: str = "star"  # supergiant, star, leaf, dead_star, external, cross_realm
    line_start: int = 1
    line_end: int = 1
    doc: str = ""
    in_degree: int = 0
    out_degree: int = 0
    color: str = "#00f0ff"
    color_rgb: Tuple[int, int, int] = (0, 240, 255)


@dataclass
class Edge:
    source: str
    target: str
    line: int = 1
    kind: str = "internal"  # internal, external, cross_realm


@dataclass
class FileNode:
    id: str
    label: str
    folder: str
    func_count: int = 0
    in_degree: int = 0
    out_degree: int = 0
    color: str = "#00f0ff"
    color_rgb: Tuple[int, int, int] = (0, 240, 255)
    size: float = 12.0


@dataclass
class FileEdge:
    source: str
    target: str
    weight: int = 1
    kind: str = "internal"
    pipes: List[Dict[str, str]] = field(default_factory=list)


class ASTCallScout:
    """Extracts functional symbols, imports, and call sites across Python files."""

    def __init__(self, root_dir: Path, exclude_tests: bool = False, exclude_externals: bool = False, subsystem: Optional[str] = None):
        self.root_dir = root_dir.resolve()
        self.exclude_tests = exclude_tests
        self.exclude_externals = exclude_externals
        self.subsystem = subsystem

        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.clusters: List[Dict[str, str]] = []

        # Tracking maps
        self.file_modules: Dict[str, str] = {}  # file_rel -> module_dotted
        self.module_files: Dict[str, str] = {}  # module_dotted -> file_rel
        self.symbols_by_file: Dict[str, Set[str]] = {}
        self.class_methods: Dict[str, Set[str]] = {}
        self.route_handlers: Dict[str, str] = {}

    def scan(self):
        py_files = self._collect_python_files()

        # Step 1: Map module names and discover all definitions
        for py_path in py_files:
            rel = self._rel_path(py_path)
            mod_name = self._to_module_name(rel)
            self.file_modules[rel] = mod_name
            self.module_files[mod_name] = rel
            stem = Path(rel).stem
            if stem not in self.module_files:
                self.module_files[stem] = rel
            self.symbols_by_file[rel] = set()

            self.clusters.append({"id": rel, "label": Path(rel).name, "kind": "file"})
            self._index_file_definitions(py_path, rel)

        # Step 2: Resolve function calls across all files
        for py_path in py_files:
            rel = self._rel_path(py_path)
            self._resolve_file_calls(py_path, rel)

        # Step 3: Scan boundary files (.js, .html) for web endpoints
        self._scan_web_boundaries()

        # Step 4: Compute graph metrics and stellar classifications
        self._compute_stellar_metrics()

    def _collect_python_files(self) -> List[Path]:
        files = []
        if self.root_dir.is_file() and self.root_dir.suffix == ".py":
            return [self.root_dir]

        for p in self.root_dir.rglob("*.py"):
            parts = set(p.parts)
            if parts.intersection(IGNORED_DIRS):
                continue

            # Filter tests if requested
            if self.exclude_tests:
                if "tests" in parts or p.name.startswith("test_") or p.name.endswith("_test.py"):
                    continue

            # Subsystem filter
            if self.subsystem:
                if self.subsystem.lower() not in p.as_posix().lower():
                    continue

            files.append(p)
        return sorted(files)

    def _rel_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.root_dir).as_posix()
        except ValueError:
            return path.name

    def _to_module_name(self, rel_path: str) -> str:
        clean = rel_path.replace(".py", "").replace("/", ".")
        if clean.endswith(".__init__"):
            clean = clean[:-9]
        return clean

    def _index_file_definitions(self, py_path: Path, rel: str):
        try:
            content = py_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_path))
        except Exception:
            return

        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node_id = f"{rel}:{stmt.name}"
                doc = ast.get_docstring(stmt) or ""
                doc_first_line = doc.strip().split("\n")[0] if doc else ""
                self.nodes[node_id] = Node(
                    id=node_id,
                    label=stmt.name,
                    file=rel,
                    cluster=rel,
                    line_start=stmt.lineno,
                    line_end=getattr(stmt, "end_lineno", stmt.lineno),
                    doc=doc_first_line
                )
                self.symbols_by_file[rel].add(stmt.name)
                self._check_route_decorator(stmt, node_id)

            elif isinstance(stmt, ast.ClassDef):
                class_key = f"{rel}:{stmt.name}"
                self.class_methods[class_key] = set()
                self.clusters.append({"id": class_key, "label": stmt.name, "kind": "class"})

                for item in stmt.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_label = f"{stmt.name}.{item.name}"
                        node_id = f"{rel}:{method_label}"
                        doc = ast.get_docstring(item) or ""
                        doc_first_line = doc.strip().split("\n")[0] if doc else ""
                        self.nodes[node_id] = Node(
                            id=node_id,
                            label=method_label,
                            file=rel,
                            cluster=class_key,
                            line_start=item.lineno,
                            line_end=getattr(item, "end_lineno", item.lineno),
                            doc=doc_first_line
                        )
                        self.symbols_by_file[rel].add(method_label)
                        self.class_methods[class_key].add(item.name)
                        self._check_route_decorator(item, node_id)

    def _check_route_decorator(self, func_node, node_id: str):
        for dec in getattr(func_node, "decorator_list", []):
            if isinstance(dec, ast.Call):
                if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                    route_path = dec.args[0].value
                    if route_path.startswith("/"):
                        self.route_handlers[route_path] = node_id

    def _resolve_file_calls(self, py_path: Path, rel: str):
        try:
            content = py_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_path))
        except Exception:
            return

        imports: Dict[str, str] = {}
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    name = alias.asname or alias.name
                    imports[name] = alias.name
            elif isinstance(stmt, ast.ImportFrom):
                mod = stmt.module or ""
                for alias in stmt.names:
                    local_name = alias.asname or alias.name
                    full_target = f"{mod}.{alias.name}" if mod else alias.name
                    imports[local_name] = full_target

        visitor = CallVisitor(self, rel, imports)
        visitor.visit(tree)

    def _scan_web_boundaries(self):
        web_files = []
        for ext in ("*.js", "*.ts", "*.html"):
            for p in self.root_dir.rglob(ext):
                parts = set(p.parts)
                if not parts.intersection(IGNORED_DIRS):
                    if not self.exclude_tests or ("tests" not in parts and "test" not in p.name):
                        web_files.append(p)

        fetch_pattern = re.compile(r"""(?:fetch|axios\.(?:get|post|put|delete)|\$\.ajax)\s*\(\s*['"`](/[^'"`]+)['"`]""")

        for wf in web_files:
            rel = self._rel_path(wf)
            try:
                text = wf.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for match in fetch_pattern.finditer(text):
                endpoint = match.group(1)
                line_no = text[:match.start()].count("\n") + 1
                if endpoint in self.route_handlers:
                    target_node_id = self.route_handlers[endpoint]
                    source_id = f"{rel}:endpoint[{endpoint}]"

                    if source_id not in self.nodes:
                        self.nodes[source_id] = Node(
                            id=source_id,
                            label=f"fetch('{endpoint}')",
                            file=rel,
                            cluster=rel,
                            stellar_type="cross_realm",
                            line_start=line_no,
                            line_end=line_no,
                            doc=f"Frontend API dispatch to {endpoint}"
                        )
                        if not any(c["id"] == rel for c in self.clusters):
                            self.clusters.append({"id": rel, "label": Path(rel).name, "kind": "web"})

                    self.edges.append(Edge(source=source_id, target=target_node_id, line=line_no, kind="cross_realm"))

    def _compute_stellar_metrics(self):
        in_counts: Dict[str, int] = {nid: 0 for nid in self.nodes}
        out_counts: Dict[str, int] = {nid: 0 for nid in self.nodes}

        for e in self.edges:
            if e.target in in_counts:
                in_counts[e.target] += 1
            if e.source in out_counts:
                out_counts[e.source] += 1

        # Assign unique chromatic colors by logical subsystem
        unique_folders = sorted(list(set(
            get_subsystem(n.file) for n in self.nodes.values()
        )))

        folder_colors = {}
        for idx, fld in enumerate(unique_folders):
            if "external" in fld.lower() or fld.startswith("["):
                rgb = (100, 116, 139)
            elif idx < len(CYBER_PALETTE):
                rgb = CYBER_PALETTE[idx]
            else:
                hue = (idx * 137.508) % 360
                rgb = hsl_to_rgb(hue, 0.90, 0.60)
            folder_colors[fld] = (rgb, rgb_to_hex(*rgb))

        for nid, node in self.nodes.items():
            node.in_degree = in_counts.get(nid, 0)
            node.out_degree = out_counts.get(nid, 0)

            folder = get_subsystem(node.file)
            rgb, hex_c = folder_colors.get(folder, ((0, 240, 255), "#00f0ff"))
            node.color_rgb = rgb
            node.color = hex_c

            if node.stellar_type in ("external", "cross_realm"):
                continue

            if node.in_degree >= 6:
                node.stellar_type = "supergiant"
            elif node.in_degree == 0:
                node.stellar_type = "dead_star"
            elif node.out_degree == 0:
                node.stellar_type = "leaf"
            else:
                node.stellar_type = "star"


class CallVisitor(ast.NodeVisitor):
    def __init__(self, scout: ASTCallScout, current_file: str, imports: Dict[str, str]):
        self.scout = scout
        self.file = current_file
        self.imports = imports
        self.current_scope: Optional[str] = None
        self.current_class: Optional[str] = None

    def visit_ClassDef(self, node: ast.ClassDef):
        prev_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._enter_func(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._enter_func(node)

    def _enter_func(self, node):
        prev_scope = self.current_scope
        if self.current_class:
            self.current_scope = f"{self.file}:{self.current_class}.{node.name}"
        else:
            self.current_scope = f"{self.file}:{node.name}"

        self.generic_visit(node)
        self.current_scope = prev_scope

    def visit_Call(self, node: ast.Call):
        if not self.current_scope:
            self.generic_visit(node)
            return

        target_node_id = self._resolve_target(node)
        if target_node_id and target_node_id != self.current_scope:
            self.scout.edges.append(Edge(
                source=self.current_scope,
                target=target_node_id,
                line=node.lineno,
                kind="external" if self.scout.nodes.get(target_node_id, Node("", "", "", "")).stellar_type == "external" else "internal"
            ))

        self.generic_visit(node)

    def _find_module_file(self, mod_name: str) -> Optional[str]:
        if mod_name in self.scout.module_files:
            return self.scout.module_files[mod_name]
        stem = mod_name.split(".")[-1]
        if stem in self.scout.module_files:
            return self.scout.module_files[stem]
        return None

    def _resolve_target(self, node: ast.Call) -> Optional[str]:
        if isinstance(node.func, ast.Name):
            callee_name = node.func.id
            if callee_name in BUILTIN_FUNCS:
                return None

            candidate_same_file = f"{self.file}:{callee_name}"
            if candidate_same_file in self.scout.nodes:
                return candidate_same_file

            if callee_name in self.imports:
                full_import = self.imports[callee_name]
                parts = full_import.rsplit(".", 1)
                if len(parts) == 2:
                    mod_part, sym_part = parts
                    target_file = self._find_module_file(mod_part)
                    if target_file:
                        target_id = f"{target_file}:{sym_part}"
                        if target_id in self.scout.nodes:
                            return target_id
                else:
                    target_file = self._find_module_file(full_import)
                    if target_file:
                        target_id = f"{target_file}:{callee_name}"
                        if target_id in self.scout.nodes:
                            return target_id

                if self.scout.exclude_externals:
                    return None
                return self._get_or_create_external_node(full_import, node.lineno)

        elif isinstance(node.func, ast.Attribute):
            method_name = node.func.attr

            if isinstance(node.func.value, ast.Name) and node.func.value.id in ("self", "cls"):
                if self.current_class:
                    target_id = f"{self.file}:{self.current_class}.{method_name}"
                    if target_id in self.scout.nodes:
                        return target_id

            elif isinstance(node.func.value, ast.Name):
                obj_name = node.func.value.id
                if obj_name in self.imports:
                    mod_target = self.imports[obj_name]
                    target_file = self._find_module_file(mod_target)
                    if target_file:
                        target_id = f"{target_file}:{method_name}"
                        if target_id in self.scout.nodes:
                            return target_id
                    if self.scout.exclude_externals:
                        return None
                    return self._get_or_create_external_node(f"{mod_target}.{method_name}", node.lineno)

        return None

    def _get_or_create_external_node(self, full_symbol: str, line: int) -> Optional[str]:
        if self.scout.exclude_externals:
            return None
        mod_prefix = full_symbol.split(".")[0]
        node_id = f"ext:{full_symbol}"
        if node_id not in self.scout.nodes:
            self.scout.nodes[node_id] = Node(
                id=node_id,
                label=full_symbol,
                file=f"[{mod_prefix}]",
                cluster="Deep Space (External)",
                stellar_type="external",
                line_start=1,
                line_end=1,
                doc=f"External dependency symbol from {mod_prefix}",
                color="#64748b",
                color_rgb=(100, 116, 139)
            )
            if not any(c["id"] == "Deep Space (External)" for c in self.scout.clusters):
                self.scout.clusters.append({
                    "id": "Deep Space (External)",
                    "label": "Deep Space (External)",
                    "kind": "external"
                })
        return node_id


# --- Macro Level 1: File-Level Network Aggregator ---
def build_file_level_graph(scout: ASTCallScout) -> Tuple[List[FileNode], List[FileEdge]]:
    """Aggregates all function calls into a clean, macro file-to-file constellation."""
    files_map: Dict[str, FileNode] = {}
    edges_map: Dict[Tuple[str, str], FileEdge] = {}

    # 1. Discover all files
    for n in scout.nodes.values():
        fpath = n.file
        if scout.exclude_externals and (fpath.startswith("[") or n.stellar_type == "external"):
            continue
        if fpath not in files_map:
            folder = get_subsystem(fpath)
            is_ext = fpath.startswith("[") or "external" in folder.lower()
            files_map[fpath] = FileNode(
                id=fpath,
                label=Path(fpath).name,
                folder=folder,
                func_count=0,
                in_degree=0,
                out_degree=0,
                color=n.color,
                color_rgb=n.color_rgb,
                size=8.0 if is_ext else 14.0
            )
        files_map[fpath].func_count += 1

    # 2. Aggregate inter-file edges
    for e in scout.edges:
        source_node = scout.nodes.get(e.source)
        target_node = scout.nodes.get(e.target)
        if not source_node or not target_node:
            continue

        sf = source_node.file
        tf = target_node.file
        if sf == tf:
            continue  # Intra-file call stays internal to file

        if scout.exclude_externals and (sf.startswith("[") or tf.startswith("[")):
            continue

        pair = (sf, tf)
        if pair not in edges_map:
            edges_map[pair] = FileEdge(
                source=sf,
                target=tf,
                weight=0,
                kind=e.kind,
                pipes=[]
            )

        edges_map[pair].weight += 1
        edges_map[pair].pipes.append({
            "caller": source_node.label,
            "callee": target_node.label,
            "line": e.line
        })

    # 3. Compute in/out degrees and sizes
    for (sf, tf), fe in edges_map.items():
        if sf in files_map:
            files_map[sf].out_degree += fe.weight
        if tf in files_map:
            files_map[tf].in_degree += fe.weight

    for fn in files_map.values():
        fn.size = max(8.0, min(36.0, 10.0 + math.sqrt(fn.func_count) * 3.5 + fn.in_degree * 0.8))

    # 4. Color file planets vibrantly by subsystem (or by file if monolithic)
    unique_folders = sorted(list(set(fn.folder for fn in files_map.values())))
    if len(unique_folders) == 1 and len(files_map) > 1:
        for idx, (fpath, fn) in enumerate(sorted(files_map.items())):
            color_rgb = CYBER_PALETTE[idx % len(CYBER_PALETTE)]
            fn.color_rgb = color_rgb
            fn.color = rgb_to_hex(*color_rgb)
    else:
        folder_colors = {}
        for idx, fld in enumerate(unique_folders):
            if "external" in fld.lower() or fld.startswith("["):
                rgb = (100, 116, 139)
            elif idx < len(CYBER_PALETTE):
                rgb = CYBER_PALETTE[idx]
            else:
                hue = (idx * 137.508) % 360
                rgb = hsl_to_rgb(hue, 0.90, 0.60)
            folder_colors[fld] = rgb
        for fn in files_map.values():
            rgb = folder_colors.get(fn.folder, (0, 240, 255))
            fn.color_rgb = rgb
            fn.color = rgb_to_hex(*rgb)

    return list(files_map.values()), list(edges_map.values())


# --- Upgraded Gephi GEXF 1.3 XML Serializer ---
def export_gexf(scout: ASTCallScout, out_path: Path, level: str = "file"):
    """
    Generates standard Gephi GEXF 1.3 XML with:
    - Pre-baked colors (<viz:color>) by folder
    - Pre-baked node sizes (<viz:size>) by degree/functions
    - Weighted, merged parallel edges (Zero Gephi parallel edge warnings!)
    """
    gexf = ET.Element("gexf", {
        "xmlns": "http://gexf.net/1.3",
        "xmlns:viz": "http://gexf.net/1.3/viz",
        "version": "1.3"
    })
    meta = ET.SubElement(gexf, "meta")
    creator = ET.SubElement(meta, "creator")
    creator.text = "Antigravity Code-Starmap"
    desc = ET.SubElement(meta, "description")
    desc.text = f"Codebase Call-graph Constellation ({level.capitalize()} Level)"

    graph = ET.SubElement(gexf, "graph", {"defaultedgetype": "directed", "mode": "static"})

    if level == "file":
        file_nodes, file_edges = build_file_level_graph(scout)

        node_attrs = ET.SubElement(graph, "attributes", {"class": "node"})
        ET.SubElement(node_attrs, "attribute", {"id": "0", "title": "folder", "type": "string"})
        ET.SubElement(node_attrs, "attribute", {"id": "1", "title": "functions", "type": "integer"})
        ET.SubElement(node_attrs, "attribute", {"id": "2", "title": "in_degree", "type": "integer"})

        nodes_el = ET.SubElement(graph, "nodes")
        for fn in file_nodes:
            n_el = ET.SubElement(nodes_el, "node", {"id": fn.id, "label": fn.label})
            # Pre-color and size
            ET.SubElement(n_el, "{http://gexf.net/1.3/viz}color", {
                "r": str(fn.color_rgb[0]),
                "g": str(fn.color_rgb[1]),
                "b": str(fn.color_rgb[2])
            })
            ET.SubElement(n_el, "{http://gexf.net/1.3/viz}size", {"value": f"{fn.size:.1f}"})

            attvalues = ET.SubElement(n_el, "attvalues")
            ET.SubElement(attvalues, "attvalue", {"for": "0", "value": fn.folder})
            ET.SubElement(attvalues, "attvalue", {"for": "1", "value": str(fn.func_count)})
            ET.SubElement(attvalues, "attvalue", {"for": "2", "value": str(fn.in_degree)})

        edges_el = ET.SubElement(graph, "edges")
        for idx, fe in enumerate(file_edges):
            ET.SubElement(edges_el, "edge", {
                "id": f"fe{idx}",
                "source": fe.source,
                "target": fe.target,
                "weight": str(fe.weight)
            })

    else:
        # Function Level with merged parallel edges
        node_attrs = ET.SubElement(graph, "attributes", {"class": "node"})
        ET.SubElement(node_attrs, "attribute", {"id": "0", "title": "file", "type": "string"})
        ET.SubElement(node_attrs, "attribute", {"id": "1", "title": "stellar_type", "type": "string"})
        ET.SubElement(node_attrs, "attribute", {"id": "2", "title": "in_degree", "type": "integer"})

        nodes_el = ET.SubElement(graph, "nodes")
        for n in scout.nodes.values():
            n_el = ET.SubElement(nodes_el, "node", {"id": n.id, "label": n.label})
            ET.SubElement(n_el, "{http://gexf.net/1.3/viz}color", {
                "r": str(n.color_rgb[0]),
                "g": str(n.color_rgb[1]),
                "b": str(n.color_rgb[2])
            })
            size_val = 14.0 if n.stellar_type == "supergiant" else max(4.0, 4.0 + n.in_degree * 1.5)
            ET.SubElement(n_el, "{http://gexf.net/1.3/viz}size", {"value": f"{size_val:.1f}"})

            attvalues = ET.SubElement(n_el, "attvalues")
            ET.SubElement(attvalues, "attvalue", {"for": "0", "value": n.file})
            ET.SubElement(attvalues, "attvalue", {"for": "1", "value": n.stellar_type})
            ET.SubElement(attvalues, "attvalue", {"for": "2", "value": str(n.in_degree)})

        # Merge parallel edges
        edge_weights: Dict[Tuple[str, str], int] = {}
        for e in scout.edges:
            pair = (e.source, e.target)
            edge_weights[pair] = edge_weights.get(pair, 0) + 1

        edges_el = ET.SubElement(graph, "edges")
        for idx, ((src, tgt), w) in enumerate(edge_weights.items()):
            ET.SubElement(edges_el, "edge", {
                "id": f"e{idx}",
                "source": src,
                "target": tgt,
                "weight": str(w)
            })

    tree = ET.ElementTree(gexf)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(out_path), encoding="utf-8", xml_declaration=True)


# --- HTML Artifact Generator ---
def export_html(scout: ASTCallScout, out_path: Path, template_path: Optional[Path] = None):
    """Bakes multi-level graph JSON into the self-contained HTML Starfield viewer."""
    if template_path is None:
        template_path = Path(__file__).resolve().parent / "template_starmap.html"

    if template_path.exists():
        template_text = template_path.read_text(encoding="utf-8")
    else:
        template_text = "<html><body><h1>Starmap Template Missing</h1></body></html>"

    file_nodes, file_edges = build_file_level_graph(scout)

    graph_payload = {
        "files": {
            "nodes": [asdict(fn) for fn in file_nodes],
            "edges": [asdict(fe) for fe in file_edges]
        },
        "functions": {
            "nodes": [asdict(n) for n in scout.nodes.values()],
            "edges": [{"source": e.source, "target": e.target, "line": e.line, "kind": e.kind} for e in scout.edges],
            "clusters": scout.clusters
        }
    }

    data_json_str = json.dumps(graph_payload, indent=2)
    html_content = template_text.replace("__STARMAP_DATA_JSON__", data_json_str)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_content, encoding="utf-8")


# --- Scoped Mermaid / Text Constellation Lens ---
def export_mermaid_lens(nodes: Dict[str, Node], edges: List[Edge], focus: str, depth: int = 1) -> str:
    focal_id = None
    for nid, node in nodes.items():
        if focus in (node.label, nid) or nid.endswith(f":{focus}"):
            focal_id = nid
            break

    if not focal_id:
        return f"%% Focal symbol '{focus}' not found in starmap."

    visited_nodes: Set[str] = {focal_id}
    frontier: Set[str] = {focal_id}

    for _ in range(depth):
        next_frontier = set()
        for e in edges:
            if e.source in frontier and e.target not in visited_nodes:
                visited_nodes.add(e.target)
                next_frontier.add(e.target)
            elif e.target in frontier and e.source not in visited_nodes:
                visited_nodes.add(e.source)
                next_frontier.add(e.source)
        frontier = next_frontier

    relevant_edges = [e for e in edges if e.source in visited_nodes and e.target in visited_nodes]

    lines = ["```mermaid", "flowchart LR"]

    def mid(raw: str) -> str:
        return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", raw)

    for nid in visited_nodes:
        n = nodes.get(nid)
        label = n.label if n else nid
        if nid == focal_id:
            lines.append(f'    {mid(nid)}["★ {label} ★"]:::focal')
        else:
            lines.append(f'    {mid(nid)}["{label}"]')

    for e in relevant_edges:
        lines.append(f"    {mid(e.source)} -->|L{e.line}| {mid(e.target)}")

    lines.append("    classDef focal fill:#d946ef,stroke:#fff,stroke-width:2px,color:#fff;")
    lines.append("```")
    return "\n".join(lines)


# --- Telemetric Scout Summary ---
def print_scout_summary(scout: ASTCallScout):
    nodes = list(scout.nodes.values())
    edges = scout.edges
    file_nodes, file_edges = build_file_level_graph(scout)

    supergiants = [n for n in nodes if n.stellar_type == "supergiant"]
    dead_stars = [n for n in nodes if n.stellar_type == "dead_star"]

    print("=== Codebase Chaos Starmap Telemetry ===")
    print(f"Macro File Planets:           {len(file_nodes)} files, {len(file_edges)} inter-file pipes")
    print(f"Micro Function Stars:         {len(nodes)} symbols, {len(edges)} total calls")
    print(f"Supergiants / Black Holes:    {len(supergiants)}")
    print(f"Dead Stars (0 Callers):       {len(dead_stars)}")
    print("-----------------------------------------")

    print("\n🪐 Key Inter-File Highway Bridges (Top Traffic):")
    for fe in sorted(file_edges, key=lambda x: x.weight, reverse=True)[:6]:
        print(f"  * {fe.source} ➔ {fe.target} ({fe.weight} calls)")

    if supergiants:
        print("\n★ Top Supergiant Hubs (Highest Gravity):")
        for h in sorted(supergiants, key=lambda x: x.in_degree, reverse=True)[:5]:
            print(f"  * {h.label:<32} ({h.in_degree} callers) [File: {h.file}]")


def main():
    parser = argparse.ArgumentParser(description="Codebase Chaos Starmap Engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Common filtering flags
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument("path", nargs="?", default=".", help="Target directory or file")
    parent_parser.add_argument("--no-tests", action="store_true", help="Exclude test files and test suites from scan")
    parent_parser.add_argument("--no-externals", "--internal-only", action="store_true", help="Exclude external libraries, stdlib packages, and non-file symbols (e.g. re, sys, os)")
    parent_parser.add_argument("--subsystem", help="Filter scan to a specific folder or subsystem name")

    # Scout
    p_scout = subparsers.add_parser("scout", parents=[parent_parser], help="Print telemetric summary of call-graph")
    p_scout.add_argument("--json", action="store_true", help="Output summary in JSON")

    # HTML
    p_html = subparsers.add_parser("html", parents=[parent_parser], help="Generate interactive HTML Starfield artifact")
    p_html.add_argument("--output", "-o", default="starmap.html", help="Output HTML file path")
    p_html.add_argument("--open", action="store_true", help="Open immediately in default browser")

    # GEXF
    p_gexf = subparsers.add_parser("gexf", parents=[parent_parser], help="Export Gephi-compatible GEXF graph XML")
    p_gexf.add_argument("--output", "-o", default="starmap.gexf", help="Output GEXF file path")
    p_gexf.add_argument("--level", choices=["file", "function"], default="file", help="Graph level for Gephi (default: file)")

    # Lens
    p_lens = subparsers.add_parser("lens", parents=[parent_parser], help="Output scoped Mermaid constellation for a specific symbol")
    p_lens.add_argument("--focus", required=True, help="Symbol or function name to isolate")
    p_lens.add_argument("--depth", type=int, default=1, help="Hop depth (default: 1)")

    args = parser.parse_args()

    target_dir = Path(args.path).resolve()
    if not target_dir.exists():
        print(f"[ERROR] Path does not exist: {target_dir}", file=sys.stderr)
        sys.exit(1)

    scout = ASTCallScout(
        target_dir,
        exclude_tests=getattr(args, "no_tests", False),
        exclude_externals=getattr(args, "no_externals", False),
        subsystem=getattr(args, "subsystem", None)
    )
    scout.scan()

    if args.command == "scout":
        if args.json:
            file_nodes, file_edges = build_file_level_graph(scout)
            print(json.dumps({
                "file_planets_count": len(file_nodes),
                "inter_file_pipes_count": len(file_edges),
                "stars_count": len(scout.nodes),
                "pipes_count": len(scout.edges),
                "supergiants": [n.id for n in scout.nodes.values() if n.stellar_type == "supergiant"]
            }, indent=2))
        else:
            print_scout_summary(scout)

    elif args.command == "html":
        out_p = Path(args.output).resolve()
        export_html(scout, out_p)
        print(f"[OK] Generated Interactive HTML Starmap: {out_p}")
        if args.open:
            webbrowser.open(out_p.as_uri())

    elif args.command == "gexf":
        out_p = Path(args.output).resolve()
        export_gexf(scout, out_p, level=args.level)
        print(f"[OK] Generated Gephi GEXF 1.3 Export ({args.level.capitalize()} Level): {out_p}")

    elif args.command == "lens":
        mermaid_out = export_mermaid_lens(scout.nodes, scout.edges, args.focus, args.depth)
        print(mermaid_out)


if __name__ == "__main__":
    main()
