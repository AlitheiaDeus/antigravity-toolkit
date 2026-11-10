---
name: code-starmap
description: >-
  Map the call-graph topology and functional nervous system of a codebase into an interactive Cyberpunk HTML Starfield or Gephi GEXF graph.
  Use when exploring unfamiliar functional codebases, untangling messy function/method/class call chains, isolating blast radius with Short-Range EMP,
  hunting dead stars (uncalled functions), identifying black-hole dispatchers, or copying direct pipe links into chat for pairing.
---

# `code-starmap` - Codebase Chaos Constellation Mapper

`code-starmap` renders the functional connectome of a codebase. Where `system-mapper` provides orbital C4 architecture maps (files, systems, airgaps) and `code-landmarks` provides surgical single-file line bounds, `code-starmap` traces **every function, method, class, and call edge** across the repository into a navigable celestial galaxy.

It eliminates the "Hairball of Death" through a dual-output architecture:
1. **Interactive Cyberpunk HTML Starfield Artifact**: Pure vanilla Canvas2D/JS force-directed galaxy with zero external dependencies, dark-space aesthetics, pan-zoom, instant search, and cluster nebulae.
2. **Gephi GEXF 1.2 Export**: Full XML export with typed attributes for deep analysis in desktop Gephi.
3. **Agent Pipe Link Teleportation**: 1-click clipboard copying of exact call pipes (`[PIPE: caller -> callee (Line X)]`) directly into Antigravity chat.
4. **Short-Range EMP Blast Radius**: Spacebar/click shockwave that dims everything beyond Hop 1 & Hop 2 callers/callees.
5. **Boundary Sensing**: Identifies external library dependencies as "Deep Space" nodes and bridges frontend `fetch()` API calls to backend Python route handlers.

---

## 1. When to Use

Invoke `code-starmap` whenever:
1. **Call-Graph Exploration & Topology**: You or the user need to understand how functions and methods interact across files.
2. **Untangling Spaghetti Calls**: Navigating complex call trees where functions jump across multiple modules.
3. **Short-Range EMP Blast Radius Analysis**: Isolating a target function's immediate callers and callees before refactoring.
4. **Hunting Dead Code ("Dead Stars")**: Finding functions and methods with 0 internal callers.
5. **Spotting Dispatcher Bottlenecks ("Black Holes")**: Identifying mega-hubs with high in-degree gravity ($\ge 6$ callers).
6. **Gephi Desktop Exploration**: Exporting `.gexf` graphs for advanced network analysis.

---

## 2. Global Tool Execution

**Script Path**:  
`$HOME/.gemini/config/skills/code-starmap/scripts/code_starmap_ctl.py`  
*(Windows native environment: `C:\msys64\mingw64\bin\python.exe`)*

### CLI Quick Reference

```bash
# 1. Scout telemetric summary (Pure internal architecture: no tests, no external libs)
python "$HOME/.gemini/config/skills/code-starmap/scripts/code_starmap_ctl.py" scout . --no-tests --no-externals

# 2. Generate Interactive 2-Tier HTML Starfield (Internal files only)
python "$HOME/.gemini/config/skills/code-starmap/scripts/code_starmap_ctl.py" html . --no-tests --no-externals --open

# 3. Export Gephi GEXF 1.3 (Macro File Level, zero external clutter)
python "$HOME/.gemini/config/skills/code-starmap/scripts/code_starmap_ctl.py" gexf . --no-tests --no-externals --output starmap.gexf

# 4. Export Gephi GEXF 1.3 (Micro Function Level)
python "$HOME/.gemini/config/skills/code-starmap/scripts/code_starmap_ctl.py" gexf . --no-tests --level function --output starmap_funcs.gexf

# 5. Isolate a specific subsystem/folder
python "$HOME/.gemini/config/skills/code-starmap/scripts/code_starmap_ctl.py" html . --subsystem system-mapper --open

# 6. Output a focused, scoped Mermaid constellation lens around a specific function
python "$HOME/.gemini/config/skills/code-starmap/scripts/code_starmap_ctl.py" lens . --focus run --depth 2
```

---

## 3. Celestial Call-Graph Taxonomy

| Stellar Type | Badge / Color | Definition & Visual Meaning |
| :--- | :--- | :--- |
| **Supergiant / Black Hole** | 🟣 Pulsing Magenta | Mega-hubs / dispatchers ($\ge 6$ incoming callers). High gravity. |
| **Core Star** | 🔵 Neon Cyan | Standard functions and active class methods. |
| **Comet / Leaf** | 🟢 Emerald Green | Pure helpers and calculations (in-degree $> 0$, out-degree $= 0$). |
| **Dead Star** | 🟡 Dim Amber | Zero internal callers (candidates for deletion or public entrypoints). |
| **Deep Space** | ⚪ Slate Ring | External library calls (`os`, `sys`, third-party packages). |
| **Cross-Realm Wormhole** | ⚡ Electric Yellow | Frontend API calls (`fetch`, `axios`) bridged to backend route handlers. |

---

## 4. Interactive Starfield Controls (HTML Viewer)

When opening `starmap.html` in the browser:
* **Pan & Zoom**: Click and drag to pan; mouse wheel to zoom in and out.
* **Inspect Star / Pipe**: Click any node or connecting edge to slide out the telemetry HUD.
* **Copy Agent Directive**: Click `[Copy Agent Directive]` in the HUD to put a surgical directive on your clipboard:
  ```text
  [PIPE: worker.py:dispatch -> task.py:execute (Line 84)]
  ```
  Paste this into chat so Antigravity locks directly onto the exact call site.
* **Short-Range EMP Blast (`Space` / Button)**:
  Triggers a shockwave from the selected star. Dims the rest of the universe to 5% opacity and isolates Hop-1 and Hop-2 callers/callees. Press `Esc` to restore full view.
* **Instant Search (`/`)**:
  Press `/` to focus the search bar. Real-time fuzzy filtering will fly the camera directly to any symbol.
