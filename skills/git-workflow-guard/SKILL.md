---
name: git-workflow-guard
description: >-
  Enforce pragmatic Git commit hygiene, atomic feature commits, remote publication safety, privacy sanitization, and .gitignore guardrails.
  Use when staging, committing, pushing, or reviewing version control changes. Prevents micro-commit clutter, hardcoded personal path leaks,
  unwanted destructive git rewinds, and repository pollution with local documentation and scratch files.
---

# `git-workflow-guard` - Pragmatic Git Hygiene, Commit Discipline & Privacy Guard

This skill governs version control operations for AI coding assistants and human developers. It enforces clean commit granularity, eliminates administrative clutter, prevents destructive history rewrites, and ensures no personal data or machine-specific paths leak into public or shared repositories.

---

## 1. The Core Commit Philosophy

### 1. One Feature, One Cohesive Commit
* **Atomic Feature Bundling**: Commits must represent a complete, functional unit of work:
  $$\text{Code Implementation} + \text{Passing Targeted Tests} + \text{Kanban State Transition} = \mathbf{1\text{ Commit}}$$
* **No Micro-Commit Clutter**: Do **NOT** create commits for every single file edit, typo fix, styling tweak, or card move.
* **Standalone Bugfix Exception**: Significant, verified bugfixes can and should have their own isolated commit.
* **Documentation Architecture Migration Exception**: Large structural refactors of documentation or task tracking topology (e.g. migrating to modular `tasks/`) are authorized as isolated milestone commits (e.g. `chore(docs): migrate to modular 1-card-1-doc tasks/`).

### 2. Forward Progress Only (No Retrospective History Rewinds)
* **Never Rewind to Fabricate "Middle" Commits**: If multiple features or fixes were implemented before a commit was created, **do not** perform destructive rebases, interactive git squashes, or `git reset --hard` to retroactively slice work into artificial intermediate commits.
* Stage the accumulated working changes cleanly into a clear, unified commit and keep forward momentum.

### 3. Push on Milestones Only
* **Never Auto-Push**: Do not push to remote repositories after every local commit.
* Remote pushes occur **only on major milestone completions** or upon **explicit developer command**.

---

## 4. Pre-Commit Privacy & Path Sanitization (Zero Leakage)

Before staging or committing any code, perform a strict sanitization scan:

### 1. Zero Hardcoded Personal / Local Machine Paths
* **Hardcoded local filesystem paths are strictly prohibited** in committed code (e.g., `C:\Users\<Username>\...`, `/home/<user>/...`, `/Users/<user>/...`).
* **Why it matters**: Hardcoded machine paths leak developer usernames/environments, break portability across machines, and represent poor software engineering.
* **Remediation**:
  * Use relative paths (e.g., `Join-Path $PSScriptRoot "backend"` or `os.path.join(os.path.dirname(__file__), ...)`).
  * Use portable environment variables (`$CONDA_PREFIX`, `$env:USERPROFILE`, `$HOME`).
  * Never commit launcher scripts or configuration files hardcoded to a specific user's home directory.

### 2. Zero Secrets & Personal Identifiers
* Ensure no API keys, private tokens, personal email addresses, or unredacted credentials are staged.
* Utilize `.env` files (which must be `.gitignore`d) or runtime environment injection for all sensitive credentials.

---

## 5. Repository Hygiene: `.gitignore` for "Sidechick Documentation" & Local Artifacts

A clean Git repository contains only production code, core assets, and verification suites. Internal scratchpads, brainstorm files, and historical logs must be kept out of version control.

### Recommended `.gitignore` Rules

```gitignore
# --- Private Internal Landmarks & Sidechick Scratchpads ---
internal/                  # Private architecture specs, handoffs, scratchpads
scratch/                   # Temporary experiment scripts & logs
ideas/                     # Unscoped feature musings
*.tmp
*.bak

# --- Agent Steering Documents (When Local Only) ---
AGENTS.md
GEMINI.md

# --- Task Tracking Archives (When Kept Local) ---
kanban_archive.md          # Local historical settlement records

# --- Machine-Specific Launchers & Overrides ---
run_local.ps1              # Hardcoded local environment bootstrapper
*.local.env
.env

# --- Test Caches & Ephemeral Output ---
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/
tests/.cache/
```

### What Stays in Git vs What Stays Local:
* **Automated Unit Tests (`tests/test_*.py`)**: **Keep in Git.** Unit tests are regression assets that protect the codebase across machines, branches, and CI pipelines.
* **Modular Task Specifications (`tasks/`)**: **Keep in Git.** Scoped task specifications are version-controlled and transition atomically with the code they define (Code + Test + `tasks/TKT-xx.md` = 1 Commit). Ensure zero personal machine paths exist.
* **Public Landmark Docs (`README.md`, `kanban.md`)**: **Keep in Git.** Public specification and active visual board.
* **Private Internal Landmarks (`internal/`)**: **Keep out of Git.** Private specs, brainstorm files, and handoffs remain in `internal/`.
* **Test Logs & Caches (`__pycache__`, `.pytest_cache`)**: **Keep out of Git.** Always gitignore runtime test artifacts.

---

## 6. Pre-Commit Verification Checklist

Before executing `git commit`:
1. [ ] **Scope Check**: Does this commit represent one complete feature or significant bugfix?
2. [ ] **No Wasteful Tests**: Were tests run only for executable code changes, skipping doc-only updates?
3. [ ] **Sanitization Check**: Did I inspect `git diff --cached` to guarantee **no hardcoded `C:\Users\...` paths** or private credentials exist?
4. [ ] **Artifact Check**: Are scratch files, archives, and temporary notes excluded via `.gitignore`?
5. [ ] **Commit Message**: Is the message descriptive, imperative, and focused on functional impact? (e.g. `feat(sim): implement 4-zone relative velocity momentum damping`).

---

## 7. Automated Pre-Commit Sanitization (`git_sanitize_check.py`)

To guarantee zero machine path leaks, verify `.gitignore` blocks, and catch accidental secrets before committing, run the sanitization shield:

**Script Path**:  
`C:\Users\AlitheiaDeus\DeusLocker\AI\antigravity-toolkit\skills\git-workflow-guard\scripts\git_sanitize_check.py`

### CLI Quick Reference

```bash
# 1. Standard pre-commit check (scans staged Git files & .gitignore)
python "C:\Users\AlitheiaDeus\DeusLocker\AI\antigravity-toolkit\skills\git-workflow-guard\scripts\git_sanitize_check.py"

# 2. Automatically fix / append standard hygiene rules to .gitignore
python "C:\Users\AlitheiaDeus\DeusLocker\AI\antigravity-toolkit\skills\git-workflow-guard\scripts\git_sanitize_check.py" --fix-gitignore

# 3. Scan all working directory files (deep audit before pushing)
python "C:\Users\AlitheiaDeus\DeusLocker\AI\antigravity-toolkit\skills\git-workflow-guard\scripts\git_sanitize_check.py" --all
```
