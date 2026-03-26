# Contributing: Tackling a Trello Card

Step-by-step workflow for picking up and completing any card from the [Legends of Amara Trello board](https://trello.com/b/FEqdR6QL/legends-of-amara).

---

## Before You Start: Create a Tracker Doc

**This is mandatory.** Before doing anything else, create a file `docs/tracker_<branch>.md` with every step from this runbook as a checkbox list. Example:

```markdown
# Tracker: fix/room-transition-race

## Phase 1: Pick Up the Card
- [ ] Pull latest master
- [ ] Read the card (description, comments, linked docs)
- [ ] Move card to In Progress
- [ ] Create worktree and branch

## Phase 2: Research
- [ ] Read the referenced code
- [ ] Trace the call chain
...
```

Check off each step as you complete it. This is your source of truth for progress — if you get interrupted or context is lost, the tracker tells you exactly where you left off. Delete the tracker file after the card is shipped.

---

## Worktree Quick Reference

All work happens in an isolated **git worktree** under `.trees/`. This lets multiple agents work on different cards simultaneously without interfering with each other. The root checkout stays on `master` — never switch it to a feature branch.

| Command | What it does |
|---------|-------------|
| `git worktree add .trees/<name> -b <branch> master` | Create a new worktree + branch from master |
| `git worktree list` | Show all active worktrees |
| `git worktree remove .trees/<name>` | Remove a worktree (clean up) |
| `git worktree prune` | Clean up stale worktree references |

**Key rules:**
- Each worktree gets its own branch; a branch can only be checked out in one worktree at a time
- Gitignored files (`.env`, `venv/`, etc.) do NOT exist in new worktrees — copy `.env` manually if needed for local testing
- All worktree directories live under `.trees/` (gitignored)

---

## Phase 1: Pick Up the Card

1. **Pull latest master** — `git pull origin master` to ensure you're working from the newest code
2. **Read the card** — Read the full card description, comments, and any linked docs (e.g. `docs/PLAN_AI_GENERATION.md`, `docs/PLAN_WALK_SYSTEM.md`)
3. **Move card to In Progress** — `move_card` to the "Features (In Progress)" list
4. **Create worktree and branch** — Branch off `master` with a descriptive name:
    - Bugs: `fix/card-name` (e.g. `fix/room-transition-race`)
    - Features: `feat/card-name` (e.g. `feat/bump-animation`)
    - Refactoring: `refactor/card-name` (e.g. `refactor/walk-state-dataclass`)
    ```
    git worktree add .trees/<branch> -b <branch> master
    cd .trees/<branch>
    git push -u origin <branch>
    ```
5. **Copy `.env` into the worktree** — Gitignored files don't carry over to new worktrees. Copy it so the server picks up `DEBUG_MODE`, `AI_BACKEND`, etc.:
    ```
    copy_env.sh <branch>
    ```
6. **All subsequent work happens inside `.trees/<branch>/`**

## Phase 2: Research

Dig into the problem before proposing solutions. Use `/research` for topics that need external context (e.g. asyncio patterns, websocket edge cases, game design precedents).

6. **Read the referenced code** — Every card cites specific files and line numbers. Read those files to understand current state (card descriptions may be stale)
7. **Trace the call chain** — For bugs, trace how the problematic code gets invoked. For features, trace the existing system the feature plugs into
8. **Identify the blast radius** — What other systems touch this code? Check imports, callers, and the client/server boundary
9. **Research unknowns** — Use `/research` for anything that needs external knowledge:
   - Bugs: known pitfalls in the library/pattern involved (e.g. asyncio task lifecycle, websocket reconnection semantics)
   - Features: prior art, best practices, design patterns relevant to the feature
   - Refactoring: established patterns for the refactor type (e.g. state machine consolidation, command registry patterns)
10. **Summarize findings** — Brief writeup of what you learned: root cause (bugs), design options (features), or risk areas (refactors). This becomes input to the design phase

## Phase 3: Design

11. **Draft the approach** — Write a plan file with:
   - **Context**: what the card is about and why it matters
   - **Approach**: the specific changes, file by file
   - **Edge cases**: what could go wrong, what existing behavior must be preserved
12. **Check for reusable patterns** — Look for existing utilities, constants, or conventions that apply (e.g. `bfs_reachable()` in `constants.py`, `_load_prompt()` for prompt templates, message batching pattern in `game_tick()`)
13. **Align with the user** — Present the plan, get approval before writing code

## Phase 4: Implement

14. **Make the changes** — Edit files per the approved plan. Follow project conventions:
    - Server state on `GameState` singleton, client state on `G` namespace
    - Prompts in `server/prompts/*.txt`, not inline
    - Data-driven content from JSON in `data/`
    - No `await` inside `game_tick()` — messages batched as tuples
    - 2-char tile codes, `[colorKey, x, y, w, h]` sprite format
15. **Run safety checks** — If `ai_generator.py`, `content_viewer.py`, or `.env` were touched: `python tools/test_api_leak.py` (all 4 tests must pass)
16. **Don't run `worldgen.py`** — Ever, unless explicitly told to. It overwrites hand-edited `.room` files

## Phase 5: Verify

17. **Smoke test — does it even start?** — `python -c "import mud_server"` to catch syntax errors and broken imports
18. **Run existing tests** — `python tools/test_api_leak.py` and any other test files in `tools/`
19. **Spot-check logic** — Read through the diff one more time looking for obvious issues: typos, off-by-ones, missing `await`, dict keys that don't exist
20. **Flag what needs manual testing** — Leave a note for the user of what to verify in-browser (e.g. "walk into a dungeon and check door locking", "talk to Smith NPC")

## Phase 6: Review & Ship

21. **Update CLAUDE.md** — If the change introduces new conventions, gotchas, or modifies documented behavior, update `CLAUDE.md` before committing (project rule)
22. **Commit & push** — Descriptive message, reference the card number if useful. Push to the feature branch
23. **Peer review** — Spawn a fresh agent to review the branch diff (`git diff master...<branch>`). The agent has no prior context, so it catches things we've gone blind to: logic errors, missed edge cases, convention violations, naming issues. Fix all findings — even minor ones — unless the fix would be a major undertaking (in which case, note it as a follow-up). Act on all feedback before proceeding
24. **Pull master into the branch** — `git pull origin master` into the feature branch to pick up any changes that landed while we worked. Resolve conflicts if any — see **Merge Conflict Rules** below
25. **Re-run smoke tests** — Make sure the merge didn't break anything: `python -c "import mud_server"` + `python tools/test_api_leak.py`
26. **Return to the root checkout** — `cd` back to the project root (where `master` is checked out). All remaining steps run from here, not from inside the worktree
27. **Merge to master** — `git merge <branch> && git push`
28. **Clean up** — Remove the worktree, then delete the branch:
    ```
    git worktree remove .trees/<branch>
    git worktree prune
    git branch -d <branch>
    git push origin --delete <branch>
    ```
29. **Move card to Done** — `move_card` to the "Done" list
30. **Comment on the card** — Add a fix/feature summary to the Trello card: what changed, which files, what it fixes/adds, commit hash, and what needs manual testing. This leaves a paper trail for future debugging
31. **Create follow-up tickets** — If the peer review, implementation, or testing surfaced issues that are out of scope for this card (pre-existing bugs, minor improvements, edge cases deferred as too risky to bundle), create new Trello cards in the appropriate list (Bugs, Future Features, or Refactoring). Reference the original card so there's a trail. Don't let follow-up work disappear into commit messages — if it's worth noting, it's worth tracking
32. **Deploy (if requested)** — `ssh root@46.225.218.207` → `cd /opt/NotZelda && git pull && systemctl restart notzelda`

---

## Merge Conflict Rules

When pulling master into your branch (step 24), conflicts mean someone else landed changes while you worked. Follow these principles:

1. **Default to master's version.** If a conflict is in code you didn't intentionally change, accept master's side. Someone else fixed a bug or added a feature — don't silently revert their work.
2. **Assume incoming changes are important.** Treat every conflict as "master has a critical fix" until you've read the diff and confirmed otherwise. Be very careful about overwriting new code with your version.
3. **Only keep your side for lines you specifically wrote.** If you changed a function and master also changed it, read both versions carefully. Merge surgically — keep their fixes, layer your feature on top.
4. **If the merge is messy, restart from master.** When conflicts are widespread or hard to reason about, it's safer to take master wholesale and reimplement your changes on top of the updated code. A clean re-apply is better than a botched merge.
5. **Re-read the final result.** After resolving, read through every conflicted file in full. Make sure the merged code actually makes sense — don't just trust the conflict markers.

---

## Quick Reference: Card Categories

| Category | Key concerns |
|----------|-------------|
| **Critical bugs** (#1-8) | Race conditions, async safety, state corruption. Test under load / rapid actions |
| **Non-critical bugs** (#9-19) | Edge cases, missing validation. Usually single-file fixes |
| **In-progress features** (#20-22) | Have existing plan docs. Read the plan doc first, pick up where it left off |
| **Future features** (#23-31) | Larger scope. May need multi-session work. Plan docs in `docs/` |
| **Refactoring** (#32-40) | High blast radius, low urgency. Test everything nearby after changes |
