# Contributing: Tackling a Trello Card

Step-by-step workflow for picking up and completing any card from the [Legends of Amara Trello board](https://trello.com/b/FEqdR6QL/legends-of-amara).

---

## Before You Start: Create a Tracker Doc

**This is mandatory.** Before doing anything else, create a file `docs/tracker_<branch-name>.md` with every step from this runbook as a checkbox list. Example:

```markdown
# Tracker: fix/room-transition-race

## Phase 1: Pick Up the Card
- [ ] Pull latest master
- [ ] Read the card (description, comments, linked docs)
- [ ] Move card to In Progress

## Phase 2: Research
- [ ] Read the referenced code
- [ ] Trace the call chain
...
```

Check off each step as you complete it. This is your source of truth for progress — if you get interrupted or context is lost, the tracker tells you exactly where you left off. Delete the tracker file after the card is shipped.

---

## Phase 1: Pick Up the Card

1. **Pull latest master** — `git pull origin master` to ensure you're working from the newest code
2. **Pull the card** — Read the full card description, comments, and any linked docs (e.g. `docs/PLAN_AI_GENERATION.md`, `docs/PLAN_WALK_SYSTEM.md`)
3. **Move card to In Progress** — `move_card` to the "Features (In Progress)" list

## Phase 2: Research

Dig into the problem before proposing solutions. Use `/research` for topics that need external context (e.g. asyncio patterns, websocket edge cases, game design precedents).

3. **Read the referenced code** — Every card cites specific files and line numbers. Read those files to understand current state (card descriptions may be stale)
4. **Trace the call chain** — For bugs, trace how the problematic code gets invoked. For features, trace the existing system the feature plugs into
5. **Identify the blast radius** — What other systems touch this code? Check imports, callers, and the client/server boundary
6. **Research unknowns** — Use `/research` for anything that needs external knowledge:
   - Bugs: known pitfalls in the library/pattern involved (e.g. asyncio task lifecycle, websocket reconnection semantics)
   - Features: prior art, best practices, design patterns relevant to the feature
   - Refactoring: established patterns for the refactor type (e.g. state machine consolidation, command registry patterns)
7. **Summarize findings** — Brief writeup of what you learned: root cause (bugs), design options (features), or risk areas (refactors). This becomes input to the design phase

## Phase 3: Design

8. **Draft the approach** — Write a plan file with:
   - **Context**: what the card is about and why it matters
   - **Approach**: the specific changes, file by file
   - **Edge cases**: what could go wrong, what existing behavior must be preserved
9. **Check for reusable patterns** — Look for existing utilities, constants, or conventions that apply (e.g. `bfs_reachable()` in `constants.py`, `_load_prompt()` for prompt templates, message batching pattern in `game_tick()`)
10. **Align with the user** — Present the plan, get approval before writing code

## Phase 4: Branch & Implement

11. **Create a feature branch** — Branch off `master` with a descriptive name:
    - Bugs: `fix/card-name` (e.g. `fix/room-transition-race`)
    - Features: `feat/card-name` (e.g. `feat/bump-animation`)
    - Refactoring: `refactor/card-name` (e.g. `refactor/walk-state-dataclass`)
    - Push the empty branch to origin so it exists on GitHub: `git push -u origin <branch>`
12. **Make the changes** — Edit files per the approved plan. Follow project conventions:
    - Server state on `GameState` singleton, client state on `G` namespace
    - Prompts in `server/prompts/*.txt`, not inline
    - Data-driven content from JSON in `data/`
    - No `await` inside `game_tick()` — messages batched as tuples
    - 2-char tile codes, `[colorKey, x, y, w, h]` sprite format
13. **Run safety checks** — If `ai_generator.py`, `content_viewer.py`, or `.env` were touched: `python tools/test_api_leak.py` (all 4 tests must pass)
14. **Don't run `worldgen.py`** — Ever, unless explicitly told to. It overwrites hand-edited `.room` files

## Phase 5: Verify

15. **Smoke test — does it even start?** — `python -c "import mud_server"` to catch syntax errors and broken imports
16. **Run existing tests** — `python tools/test_api_leak.py` and any other test files in `tools/`
17. **Spot-check logic** — Read through the diff one more time looking for obvious issues: typos, off-by-ones, missing `await`, dict keys that don't exist
18. **Flag what needs manual testing** — Leave a note for the user of what to verify in-browser (e.g. "walk into a dungeon and check door locking", "talk to Smith NPC")

## Phase 6: Review & Ship

19. **Update CLAUDE.md** — If the change introduces new conventions, gotchas, or modifies documented behavior, update `CLAUDE.md` before committing (project rule)
20. **Commit & push** — Descriptive message, reference the card number if useful. Push to the feature branch
21. **Peer review** — Spawn a fresh agent to review the branch diff (`git diff master...<branch>`). The agent has no prior context, so it catches things we've gone blind to: logic errors, missed edge cases, convention violations, naming issues. Act on any valid feedback before proceeding
22. **Pull master into the branch** — `git pull origin master` into the feature branch to pick up any changes that landed while we worked. Resolve conflicts if any
23. **Re-run smoke tests** — Make sure the merge didn't break anything: `python -c "import mud_server"` + `python tools/test_api_leak.py`
24. **Merge to master** — `git checkout master && git merge <branch> && git push`
25. **Clean up the branch** — `git branch -d <branch> && git push origin --delete <branch>`. Branches are just labels — the commits live on in master's history. If a worktree was used, remove it first with `git worktree remove <path>` then `git worktree prune`
26. **Move card to Done** — `move_card` to the "Done" list
27. **Comment on the card** — Add a fix/feature summary to the Trello card: what changed, which files, what it fixes/adds, commit hash, and what needs manual testing. This leaves a paper trail for future debugging
28. **Deploy (if requested)** — `ssh root@46.225.218.207` → `cd /opt/NotZelda && git pull && systemctl restart notzelda`

---

## Quick Reference: Card Categories

| Category | Key concerns |
|----------|-------------|
| **Critical bugs** (#1-8) | Race conditions, async safety, state corruption. Test under load / rapid actions |
| **Non-critical bugs** (#9-19) | Edge cases, missing validation. Usually single-file fixes |
| **In-progress features** (#20-22) | Have existing plan docs. Read the plan doc first, pick up where it left off |
| **Future features** (#23-31) | Larger scope. May need multi-session work. Plan docs in `docs/` |
| **Refactoring** (#32-40) | High blast radius, low urgency. Test everything nearby after changes |
