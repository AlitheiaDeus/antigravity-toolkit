---
name: code-landmarks
description: >-
  Fast structural symbol and landmark indexer for navigating large or monolithic codebases and documents.
  Use when locating classes, methods, functions, or [LANDMARK: ...] bookmarks in files (>300 lines),
  or when finding exact line ranges before calling read_file, edit_file, refactoring, or debugging.
---

# `code-landmarks` - Structural Symbol & Landmark Indexer

This skill equips the agent with instant, zero-guess navigation for large monolithic source files and complex documentation. It maps classes, methods, functions, and manual landmark bookmarks with exact line ranges (`start_line`, `end_line`) without burning token budget on blind file reads.

---

## 1. When to Use

Always reach for `code-landmarks` when:
1. **Navigating Monolithic Files**: Before reading files >300 lines, run the scanner to identify the exact line range of the class or function you need.
2. **Pre-Flight Edit Planning**: Get exact line bounds before calling `read_file(StartLine, EndLine)` or `edit_file`.
3. **Locating Conceptual Landmarks**: Find custom `# [LANDMARK: ...]` or `# [BM: ...]` bookmarks placed in code or docs.
4. **Targeted Code Slicing**: Inspect a specific function or class definition without dumping the entire file.

---

## 2. Global Tool Execution

**Script Path**:  
`$HOME/.gemini/config/skills/code-landmarks/scripts/scan_landmarks.py`

### CLI Quick Reference

```bash
# 1. Output a compact Table of Contents (TOC) with line ranges (AST + Landmarks)
python "$HOME/.gemini/config/skills/code-landmarks/scripts/scan_landmarks.py" path/to/file.py

# 2. Find exact line ranges for a specific class, method, or function
python "$HOME/.gemini/config/skills/code-landmarks/scripts/scan_landmarks.py" path/to/file.py --find "setup_ui"

# 3. Slice and inspect the code block directly (with 3 lines of context padding)
python "$HOME/.gemini/config/skills/code-landmarks/scripts/scan_landmarks.py" path/to/file.py --slice "WorkerEngine.execute" --context 3

# 4. Filter only manual [LANDMARK: ...] and [BM: ...] bookmarks
python "$HOME/.gemini/config/skills/code-landmarks/scripts/scan_landmarks.py" path/to/file.py --landmarks-only

# 5. Scan an entire directory for all manual landmark comments across all source files
python "$HOME/.gemini/config/skills/code-landmarks/scripts/scan_landmarks.py" src/

# 6. JSON output for programmatic tooling or subagents
python "$HOME/.gemini/config/skills/code-landmarks/scripts/scan_landmarks.py" path/to/file.py --json
```

---

## 3. Supported File Types & Parsers

* **Python (`.py`)**: Uses native Python AST (`ast.parse`) to map:
  * Module docstrings
  * Classes and inner methods (`ClassName.method_name`)
  * Top-level functions and async functions
  * `if __name__ == '__main__':` entry points
* **Markdown (`.md`)**: Maps heading hierarchies (`H1`, `H2`, `H3`) with calculated section span boundaries.
* **C-Style & Web (`.js`, `.ts`, `.jsx`, `.tsx`, `.go`, `.rs`, `.c`, `.cpp`, `.h`, `.java`)**: Structural regex extraction for classes, functions, and interfaces.
* **All Files**: Scans for manual landmark tags.

---

## 4. Manual Landmark Tagging Convention

When authoring complex algorithms, lengthy configuration tables, or non-symbol logic blocks, drop landmark comments for future navigation:

```python
# Python / Shell:
# [LANDMARK: auth_refresh_rotation] Handles zero-downtime token refresh
# [BM: jwt_secret_rotation]
```

```javascript
// JavaScript / TypeScript / Go / Rust / C / C++:
// [LANDMARK: event_bus_dispatch] Central telemetry fan-out loop
/* [LANDMARK: webgl_shader_pipeline] */
```

```html
<!-- HTML / Markdown / XML: -->
<!-- [LANDMARK: telemetry_dashboard_grid] -->
```
