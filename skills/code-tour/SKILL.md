---
name: code-tour
description: >-
  Manual trigger only: turn-gated, one-block-at-a-time codebase walkthrough.
  Use ONLY when the user explicitly invokes `code-tour`, `@code-tour`, or asks for a
  "code tour" or "walk me through <file/feature> step by step".
  Do NOT trigger for general code explanations, debugging, architecture summaries, or editing tasks.
---

# `code-tour` — Turn-Gated Codebase Walkthrough

Guide the user through an existing module, execution path, PR, or feature **one block at a time**, waiting for confirmation at every step without dumping walls of text or full call graphs.

---

## 1. Trigger & Exit Rules (No Rogue Locks)

- **Enter Tour Mode ONLY when** the user explicitly invokes `code-tour`, `@code-tour`, or asks for a step-by-step code tour of a specific file, function, or flow.
- **Immediate Exit Hatch:** Drop out of tour mode immediately if the user says *"skip ahead"*, *"summarize the rest"*, *"stop the tour"*, or asks you to edit/run/fix something directly.

---

## 2. Tour Setup (Turn 1 Only)

1. **Scope Check:** Briefly confirm the entry point and goal in 1–2 sentences (e.g., *"Starting at `auth_middleware()` and tracing how a token is validated down to the DB lookup. Ready?"*)—or jump straight to Stop 1 if the entry point is obvious.
2. **Tour Itinerary (4–6 Stops):** Present a compact checklist of the stops we will visit:
   ```text
   - [ ] Stop 1: Entry point (`routes.py:handle_login`)
   - [ ] Stop 2: Validation (`validators.py:check_payload`)
   - [ ] Stop 3: Session write (`store.py:save_session`)
   ```
   *(If helpful for a long tour, keep the checklist in a scratchpad note rather than re-pasting it every turn.)*

---

## 3. One Block at a Time (Every Tour Turn)

On each turn, cover **exactly ONE stop/block** using only these three parts:

1. **Where We Are:** File path, line range, and symbol name (as a clickable link).
2. **The Block:** The small, relevant code snippet (keep it tight—just the block in focus).
3. **What It Does & Why It's Here:** 1–3 plain sentences explaining its role in the flow and what breaks or changes if it weren't there.

**Hard Stop:** After delivering that one block, **stop and wait**. Do not preview Stop 2, do not dump downstream helpers, and do not summarize the rest of the file until the user says *"next"*, *"got it"*, or asks a question.

---

## 4. Handling Questions & Detours (Freeze Rule)

- **Freeze on Questions:** If the user asks *"why is X here?"* or *"what does Y do?"*, **do not advance to the next stop**. Answer their question directly and plainly, then wait for them to say *"next"* or *"got it"*.
- **Follow-Up Detours:** If the user asks to inspect a helper function called inside the current block, show that helper in the same 1-block format, then ask whether to continue down that branch or return to the main itinerary.
- **No Unsolicited Jargon or Visual Bloat:**
  - Explain non-obvious terms in plain English on first mention.
  - **No ASCII art** or giant diagrams on every turn.
  - **No full-file re-dumps** when only one block is under discussion.
