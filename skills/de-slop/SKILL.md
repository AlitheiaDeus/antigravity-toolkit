---
name: de-slop
description: Audit, ground, and de-slop codebases across code, test suites, documentation prose, and filenames. Detects AI enterprise foam, conversational chat debris, defensive panic wrappers, hollow abstractions, test suite paper tigers (mock theatre, hollow assertions), and hyper-verbose filenames, while strictly protecting battle-tested StackOverflow copypasta and platform hacks.
---

# `de-slop` - Codebase & Repository De-Slopping Engine

A specialized skill for identifying and stripping artificial AI enterprise foam, conversational chat debris, defensive panic wrappers, test suite paper tigers, documentation filler prose, and jawbreaker filenames—while strictly protecting battle-tested StackOverflow copypasta and platform workarounds.

> [!IMPORTANT]
> **Invocation & Target Resolution Rule**:
> When invoked via `/de-slop` or asked to de-slop:
> 1. **Default Target**: If the user does not specify a file or path, **immediately audit the current workspace root (`.`)**.
> 2. **Execute, Do Not Meta-Review**: Do **NOT** write an essay reviewing or praising this skill. Immediately run the scan/sweep against the user's project and present the actionable audit report.

---

## 1. The 4 Dimensions of Slop

```
┌────────────────────────────────────────────────────────────────────────┐
│                        THE 4-TIER SLOP SPECTRUM                        │
├──────────────────────────────────┬─────────────────────────────────────┤
│ 1. CODE LOGIC (The Paranoia)     │ 2. TEST SUITES (The Paper Tigers)   │
├──────────────────────────────────┼─────────────────────────────────────┤
│ • Leaked chat comments           │ • Mock Theatre                      │
│   ("# Fixed this for you")       │   (asserting mocks, not logic)      │
│ • Hyper-verbose variable names   │ • Sycophantic assertion mirroring   │
│   (40-character jawbreakers)     │ • Zero-entropy inputs ("test", 10)  │
│ • Empty exception hierarchies    │ • Suppressed test failures          │
│ • 1-method classes & wrappers    │   (try/except: pass in tests)       │
│ • Panic `try/except: pass`       │ • Flaky hardcoded `sleep(2)`        │
├──────────────────────────────────┼─────────────────────────────────────┤
│ 3. DOCUMENTATION (The Foam)      │ 4. FILENAMES (The Bloat)            │
├──────────────────────────────────┼─────────────────────────────────────┤
│ • Conversational opening filler  │ • Hyper-verbose enterprise names    │
│   ("Certainly! Below is the...") │   (user_auth_service_controller.py) │
│ • AI corporate foam ("In this    │ • Stale version suffixes            │
│   guide, we delve deeply into")  │   (client_v2.py, service_final.py)  │
└──────────────────────────────────┴─────────────────────────────────────┘
                                   │
                                   ▼
             ┌───────────────────────────────────────────┐
             │   "CHESTERTON'S FENCE" (KEEP & GROUND)    │
             ├───────────────────────────────────────────┤
             │ Strange, ugly StackOverflow copypasta or  │
             │ weird edge-case patches that look like    │
             │ slop, but actually hold the system        │
             │ together. -> RECOMMEND: KEEP & ADD NOTE   │
             └───────────────────────────────────────────┘
```

### The Sacred Copypasta Invariant
**StackOverflow copypasta is sacred duct tape.** When code has an ugly snippet referencing a StackOverflow thread or an obscure Win32/POSIX workaround, it is usually the only thing standing between the application and a silent platform crash.
* **Never** "simplify" or "clean up" an ugly OS workaround or StackOverflow fix without understanding the bug it was copied to solve.
* Mark these findings as `[KEEP-FENCE-xx]` and recommend keeping them intact.

---

## 2. Global Tool Execution

**Script Path**:  
`$HOME/.gemini/config/skills/de-slop/scripts/deslop_ctl.py`

*(Windows native environment: `C:\msys64\mingw64\bin\python.exe`)*

### CLI Quick Reference

```bash
# 1. Full Repository De-Slop Sweep (Audits Code, Tests, Docs, and Filenames)
python "$HOME/.gemini/config/skills/de-slop/scripts/deslop_ctl.py" sweep .

# 2. Output Full Sweep as a Markdown Report
python "$HOME/.gemini/config/skills/de-slop/scripts/deslop_ctl.py" sweep . --format md

# 3. Standard Code-Only Audit
python "$HOME/.gemini/config/skills/de-slop/scripts/deslop_ctl.py" scan path/to/file.py

# 4. Create an isolated safety Git backup branch before editing
python "$HOME/.gemini/config/skills/de-slop/scripts/deslop_ctl.py" fork .

# 5. Surgically strip conversational comments from a file
python "$HOME/.gemini/config/skills/de-slop/scripts/deslop_ctl.py" strip path/to/file.py
```

---

## 3. How to Execute a De-Slop Session

1. **Run the Sweep**: Execute `deslop_ctl.py sweep .` to produce the 4-tier scorecard.
2. **Present the Scorecard**: Give the user a clear count across Code, Tests, Docs, and Filenames.
3. **Safety First**: Before making destructive edits, always run `fork` or ensure a clean Git status.
4. **Surgical Triage**:
   * **Chat Debris**: Strip with `deslop_ctl.py strip`.
   * **Test Paper Tigers**: Replace hollow assertions (`is not None`, mock calls) with concrete return value assertions.
   * **Panic Blocks**: Replace generic `try/except: pass` with explicit exception types.
   * **Sacred Fences**: Protect with `[KEEP-FENCE]` tags.

---

## 4. Verification & Testing

All tools in this skill must adhere to the zero external dependencies policy and pass the master test suite:

```bash
C:\msys64\mingw64\bin\python.exe setup_toolkit.py
```
