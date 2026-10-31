# CLAUDE.md

This file provides guidance to AI coding agents when working with code in this repository. `AGENTS.md` is a symlink to it, so every agent reads the same file; edit `CLAUDE.md`.

## Communication
- Speak in simple, plain English whenever possible. Lead with non-technical framing (motivation, what changed, what success looks like) and keep math, code paths, and implementation detail in lower sections or appendices.
- Decision rules belong in tables with concrete numerical thresholds, not prose.

## Scratch space
- `scratch/` at the repo root is gitignored and is where anything the work needs but the history does not goes: ad-hoc scripts, probe output, query dumps, run logs, etc.
- Use it instead of `/tmp`.
- One directory per piece of work, named `<YYYY-MM-DD>-<slug>` — the date it was created, never renamed afterwards — with the issue number first in the slug when there is one: `scratch/2026-10-04-99-variance-inflation/`, `scratch/2026-10-04-thriftserver-oom/`. So `ls scratch/` reads oldest to newest, which is the only question ever asked of the folder ("what can go?"), and an issue's work is still found with `ls scratch/ | grep 99`. The date is the directory's birthday, not the date of the thing it is about.
- A dated directory that is worth keeping gets a one-line `README.md` saying what the question was — a month later the slug gives the topic and nothing else.
- A loose file at the top level (`scratch/probe.py`) means throwaway: it may be deleted at any time, by anyone. Anything that should survive goes in a dated directory. Nothing sweeps the folder automatically; pruning is by hand, by date.

## Git conventions
- Unless told otherwise, make the code changes for a PR in a separate git worktree under `.claude/worktrees/` (gitignored), not in the main checkout, which stays on `main` for other work.
- Branches follow [Conventional Branch](https://conventionalbranch.org/)
- Commits follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)

## Code clarity
- For Python code, always use NumPy-style docstrings (`Parameters` / `Returns` / `Raises` sections with the underlined-header format), not Google-style `Args:`.
- Use builtin types (`tuple`, `dict`, `list`, `set`) instead of typing module equivalents (`Tuple`, `Dict`, `List`, `Set`).
- Use `xxx | None` instead of `Optional[xxx]` for optional types.

## Logging
- Use `loguru` for all logging instead of `print()` or the standard library `logging` module.
- Import the logger directly: `from loguru import logger`
- Do not use `logging.getLogger(__name__)` or `logging.basicConfig()`.
- Use `logger.info()`, `logger.debug()`, `logger.warning()`, `logger.error()`, etc.

## Pandas DataFrame Core Rules

### Use domain wrappers

**Pattern**
- One wrapper per DF "type" (e.g., `Orders`, `RaceEntries`, `DailyKpis`).
- The wrapper owns the contract: **schema + grain + invariants**.
- Construct wrappers only via validated constructors:
  - `from_df(df)` (strict)
  - `coerce(df)` (optional; casts dtypes then validates)
- Wrapper surface area:
  - `.df` (underlying DataFrame; treat as read-only in shared code)
  - metadata: `.grain`, `.keys`, `.schema_name`
  - domain methods for common transforms (avoid free-form mutation outside)

**Rules**
- Functions should accept/return wrappers (not raw `pd.DataFrame`) for domain concepts.
- Inside functions, it's OK to unwrap to `.df` for pandas ops—return a wrapper again.
- Avoid in-place mutation of `.df` in shared/app code; prefer returning a new wrapper.

### Validate at boundaries (ingress/egress + major transforms)
Validate schema + invariants:
- after reading external data (DB/files/APIs)
- before/after joins
- at entry to business-critical functions (unless wrapper construction guarantees it)
- before writing/publishing

Validation must check (at minimum):
- required columns present
- dtypes as expected (or coercible via `coerce`)
- key columns: no unexpected nulls
- grain key uniqueness (if required)
- category/value constraints (when relevant)

Fail fast with clear error messages.

### Prefer explicit, small transforms (predictable outputs)
- Keep transforms small, named, and single-purpose.
- Functions must return predictable DF “types” (wrappers), not “whatever columns happen to exist.”
- Avoid in-place mutation in application/shared code; prefer `.assign(...)`, `.pipe(...)`, and returning new objects.

### Standardize joins (schema drift hot-spot)
- Every `merge` must specify `how=` and join keys explicitly (`on=` or `left_on/right_on`).
- Set `validate=` (`one_to_one`, `one_to_many`, etc.) whenever possible.
- Control suffixes explicitly and rename columns back to canonical names.
- After merge, validate:
  - row count sanity (if expected)
  - grain key uniqueness (if required)
  - no unexpected nulls in keys

### Use column sets instead of ad-hoc strings
- Use predefined `KEY_COLS`, `DIM_COLS`, `FACT_COLS` (and other groups) for selects, merges, and outputs.
- Avoid copying/pasting raw column name lists across modules.

### Log compact schema diagnostics at key points
At major pipeline steps, log:
- `df.shape`
- key column null counts
- a compact schema summary (columns + dtypes)

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues (hankehly/tv-commercial-detector) via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
