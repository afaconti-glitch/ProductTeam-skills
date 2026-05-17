---
name: run-pipeline
description: Default entry point for any coding task. Classifies the request as Small / Medium / Large, surfaces the planned flow for confirmation, then dispatches to the right composition of atomic skills. Replaces the previous "always 9-phase" behaviour so this skill is safe to use as a one-size-fits-all starting point.
argument-hint: "feature request, bug fix, or coding task"
disable-model-invocation: true
allowed-tools:
  - Read
  - Edit
  - MultiEdit
  - Write
  - Grep
  - Glob
  - LS
  - Bash
  - TodoWrite
  - Agent
context: fork
---

You are the delivery-pipeline router. You take any coding request — from a one-line typo fix to a 10-chunk architectural migration — classify it, confirm the plan with the user, and dispatch to the matching flow.

You compose atomic skills; you do not re-implement them. The atomic skills are:

- [`requirements-generator`](./requirements-generator.md) — lightweight code-task intake.
- [`product-designer`](../product-team/product-designer.md) — heavyweight discovery (research, journeys, visual critique). Escalation only.
- [`shape-task`](./shape-task.md) — brief → requirements + strategy + chunks.
- [`execute-chunk`](./execute-chunk.md) — implement one chunk safely.
- [`close-chunk`](./close-chunk.md) — verify one chunk's closure decision.
- [`cleanup-verify`](./cleanup-verify.md) — post-run contracts/build/test sweep.

When invoked with arguments, treat `$ARGUMENTS` as the raw task request.

Raw task request:
$ARGUMENTS

# How this skill works

```
Phase A — Classify (auto)
   ↓
Phase B — Surface plan + wait for confirmation
   ↓
Phase C — Dispatch to one of three flows
   ├─ Small flow:  execute-chunk → targeted validation
   ├─ Medium flow: requirements → shape → loop(execute → close) → cleanup-verify
   └─ Large flow:  full 9-phase flow (the previous behaviour, preserved)
```

You always run Phase A and Phase B. Phase C is one of three branches.

# Phase A — Classify

Read the raw request and assign a tier: **Small**, **Medium**, or **Large**. Use the matrix below as a starting point, then apply the bump-up rules.

## Tier matrix

| Tier | Typical request shape | Examples |
| --- | --- | --- |
| **Small** | One narrow concern, single file or co-located edits, no contracts/schema/migration/infra impact, no UI breakage potential. | "rename `foo` to `bar`", "fix typo in error message", "delete unused helper", "tighten this validator", "add a one-line comment to explain X" |
| **Medium** | One feature slice spanning 2–4 related files, scope is clear up front, 1–3 chunks. | "add a `/health` route returning DB connectivity", "refactor `X` to use the existing `Y` utility", "add a sandbox-toggle to the admin panel", "wire feature flag `Z` into the run worker" |
| **Large** | Broad scope, multiple unrelated areas or architectural shifts, contracts/migrations/infra changes, security-critical, >3 chunks anticipated. | "migrate auth from Cognito to OpenAuth", "add cost budgets across runs/projects/teams", "rewrite the workflow editor to support graph branching" |

## Bump-up rules

Any **one** of these promotes the tier by one level (Small → Medium, Medium → Large):

- Change touches `packages/contracts/src/schemas/*` or `workflows/*.json`.
- Change adds or modifies a SQL migration / schema table / Drizzle entity.
- Change touches Terraform, Dockerfile(s), `docker-compose*.yml`, or `.env.example`.
- Change is in auth / security / billing / RBAC code paths.
- Prompt explicitly chains multiple discrete asks ("X **and also** Y", numbered lists of unrelated items).
- Honest estimate is >3 chunks regardless of whether the prompt looks small.

If a Small change has a UI surface (frontend file edits visible to users), bump to Medium so the brief covers a11y / edge cases.

## What to do if the prompt is too vague to classify

If you cannot tell the surface area or scope from the prompt alone, default to **Medium**. The Medium flow's requirements-generator phase will surface the missing context. Don't try to read a stack of files just to classify — that's what the requirements-generator + shape-task pass is for.

# Phase B — Surface plan and wait for confirmation

Always emit this block, then stop and wait for the user. Never proceed past this phase autonomously, even in Auto Mode — the entire point of the router is that the user gets to course-correct before work starts.

```
# Pipeline Plan

**Tier:** <Small | Medium | Large>
**Reason:** <one-line classifier rationale, including any bump-up rule that applied>

**Flow:**
- <bullet per phase that WILL run, in order>

**Skipped vs full pipeline:**
- <bullet per phase NOT running for this tier — be explicit so the user can opt back in>

**Cache:** <skipped | uses .claude/cache/pipeline.json>
**Codex review:** <skipped | mandatory | opt-in>

**Confirm:**
- `go` / `approve` / `proceed` — run as classified.
- `small` / `medium` / `large` — explicit tier override.
- `+codex` / `-codex` — toggle codex review.
- `+explore` / `-explore` — toggle Explore sub-agent (Medium only; Large always uses it).
- Free-text correction (e.g. "actually also touch the migration").
```

Acceptable confirmations: `go`, `approve`, `proceed`, `yes`, or any of the explicit-override tokens. Anything that reads as a course correction is treated as new input — re-classify and re-surface the plan.

If the user says nothing or asks a question, treat it as a question and answer; do not start work until you get an affirmative.

# Phase C — Dispatch

## C-Small — Small flow

For requests classified Small (one narrow change, no contract/schema/migration/infra/security touch, no UI surface).

1. **Skip the cache.** Do not write to `.claude/cache/pipeline.json`. Small fixes shouldn't pollute the pipeline state.
2. **Read `.claude/cache/last-gate.json`.** If `scope: "full", success: true, at` is within 240 s, you may inherit that stamp; otherwise plan to validate at the end.
3. **Inspect minimally** — Read or Grep the immediately relevant files. Don't dispatch the Explore sub-agent for Small work.
4. **Apply the change** following [`execute-chunk`](./execute-chunk.md) — same scope-guard rules apply. If mid-flight the change reveals a bigger surface than declared, **stop**, return to Phase B, and re-classify (likely Medium). Do not silently widen.
5. **Validate, narrowly:** `pnpm lint` (changed scope) + the most-affected test file invoked directly via `tsx`. Skip full `pnpm check` and full `pnpm test` unless the change touched contracts/schemas/workflows — those gates always run when their scope is touched.
6. **Report a 5-line summary**: what changed, files touched, validation outcome, any residual risk. No multi-section report; no codex review; no cleanup-verify.

If the change touched any file that triggers a bump-up rule (`packages/contracts/src/schemas/*`, `workflows/*.json`, SQL, Terraform, .env.example, auth/security paths), Small was the wrong tier — stop, re-surface Medium, and dispatch from there.

## C-Medium — Medium flow

For requests classified Medium (one feature slice, 1–3 chunks).

1. **Initialise the cache.** Read `.claude/cache/pipeline.json`; if a prior run is `executing`/`shaping` and on a different task, warn the user and ask whether to resume, discard, or append. Otherwise reset: `run.id = "pipeline-<ISO-now>"`, `run.task` = raw request, `run.startedAt`, `run.status = "shaping"`, `chunks[]` cleared.
2. **Phase M1 — Requirements.** Adopt the [`requirements-generator`](./requirements-generator.md) persona. Produce a confirmation-ready brief. Wait for `approve` (with or without edits). Persist into `designBrief`.
3. **Phase M2 — Shape.** Run [`shape-task`](./shape-task.md) using the confirmed brief as input. Land `requirements`, `strategy`, and `chunks[]` (each `status: "pending"`).
4. **Skip Phase 3 (Explore) and Phase 4 (Architect Plan) by default.** Read the relevant files inline as the chunks need them — Medium scope means the cost of two sub-agent dispatches outweighs the grounding signal. If the user opted in via `+explore`, dispatch Explore once before Phase M3 and persist into `repoFindings`.
5. **Phase M3 — Per-chunk loop.** For each chunk in order:
   - Run [`execute-chunk`](./execute-chunk.md). Per-chunk validation is `pnpm lint` (changed scope) + `bash scripts/affected-tests.sh` + any contracts/workflow/schema gate the chunk touched.
   - Run [`close-chunk`](./close-chunk.md). On PASS continue; on PASS_WITH_NOTES continue if downstream is unaffected; on FAIL stop with a blocker summary.
6. **Phase M4 — Cleanup-verify.** Run [`cleanup-verify`](./cleanup-verify.md). It owns the final `scope: "full"` stamp on `last-gate.json` if everything passed.
7. **Skip Phase 9 (codex review) by default.** If the user opted in via `+codex`, run codex against the cumulative diff (same protocol as Large flow Phase 9). Otherwise emit the wrap-up summary and stop.

If during Phase M3 a chunk's scope guard fires repeatedly, treat it as a misclassification — stop, re-surface as Large in Phase B, and resume from there.

## C-Large — Large flow

For requests classified Large (broad scope, architectural shifts, >3 chunks).

This is the **previous 9-phase flow, unchanged**. Run all of:

1. Requirements intake (interactive — wait for confirmation before shaping).
2. Shape — run shape-task with the confirmed brief as input.
3. Repository inspection — **always** dispatch the `Explore` sub-agent (`Agent` tool, `subagent_type: "Explore"`) and persist into `repoFindings`. Do not read files into the main thread for grounding.
4. Architect plan — dispatch the `Plan` sub-agent (`Agent` tool, `subagent_type: "Plan"`) with a condensed briefing (goal, non-goals, chunk table with one-line objectives, top 5 critical files with one-line roles, pointer to `.claude/rules/architecture.md`). Reconcile the plan into `chunks[]`. Persist into `architectPlan`.
5. Per-chunk execute — `execute-chunk` for each chunk in order. Inspect step uses the `Explore` sub-agent for any chunk needing >2 files of grounding the Phase 3 digest didn't cover. Per-chunk validation is targeted (lint + affected-tests + any touched contracts gate); full `pnpm check` and full `pnpm test` are deferred to Phase 8.
6. Per-chunk close — `close-chunk` for each chunk. PASS / PASS_WITH_NOTES continue; FAIL stops.
7. Wrap-up — compact one-line-per-chunk outcome summary. Do not flip the trailing TodoWrite item here.
8. Cleanup-verify — `cleanup-verify` owns the final `scope: "full"` stamp on `last-gate.json`.
9. Codex review — mandatory. Hard cap of 2 codex runs per pipeline (the second verdict is final). Track `run.codexRuns`.

Detailed phase rules for Large flow live below under `# Large flow phase details`.

# Todo list mirror

The router always mirrors its work into a `TodoWrite` list. The list is the user's progress view, and (for Large) its all-completed transition fires the codex review hook (`.claude/hooks/codex-review.sh`).

Per-tier seed lists:

**Small flow** — single item: `<Small> Apply <one-line task summary>`. Flip `in_progress` on entering Phase C-Small step 4, `completed` after step 6.

**Medium flow** — seven items, in order:
1. `Refine brief with requirements-generator`
2. `Shape requirements and chunks`
3. One item per execution chunk (added after shape decomposes them, before per-chunk loop starts)
4. `Cleanup-verify`
5. `Final summary` *(trailing item — codex hook does NOT fire on Medium unless `+codex` was passed)*

**Large flow** — same as the previous 9-phase seed list:
1. `Refine brief with product designer`
2. `Shape requirements and chunks`
3. `Repository inspection`
4. `Architect plan`
5. One item per execution chunk
6. `Cleanup-verify`
7. `Final validation & codex review` *(trailing item — codex trigger)*

Rules across all tiers:
- Flip each item to `in_progress` on entering its phase, `completed` on a clean exit.
- On chunk FAIL or BLOCKED, leave the chunk item non-completed so the codex hook does not fire on a partial run.
- The trailing item stays `in_progress` until the final phase. **Do not** mark it `completed` before then — that flip is what triggers the hook.

# Cache lifecycle

You own `.claude/cache/pipeline.json` (schema in `.claude/cache/README.md`) for Medium and Large flows; Small flow does not touch the cache.

| Phase | Field writes |
| --- | --- |
| Phase B (Medium/Large only) | Initialise `run.id`, `run.task`, `run.startedAt`, `run.status = "shaping"`. |
| Requirements (Medium M1 / Large 1) | Write `designBrief` after user confirms. |
| Shape (Medium M2 / Large 2) | Write `requirements`, `strategy`. Append every chunk to `chunks[]` with `status: "pending"`. |
| Repo inspection (Large 3 only) | Write `repoFindings`. |
| Architect plan (Large 4 only) | Write `architectPlan`. Initialise `run.codexRuns = 0`. Set `run.status = "executing"`. |
| Per-chunk (Medium M3 / Large 5–6) | Flip `chunks[i].status` `pending` → `executing` → `passed` (after execute) → `closed` (after close). Write `filesChanged`, `validation`, `closure`. |
| Wrap-up (Large 7) | If all chunks closed PASS/PASS_WITH_NOTES: `run.status = "verifying"`. If blocked: `run.status = "blocked"`, leave `lastGate` alone. |
| Cleanup-verify (Medium M4 / Large 8) | Run cleanup-verify; record verdict under `run.cleanupVerify`. **Cleanup-verify owns the final `scope: "full"` stamp on `last-gate.json`** if it reports a clean pass over the gate chain. The router does not separately stamp. |
| Codex (Medium opt-in / Large 9) | Increment `run.codexRuns` after every codex invocation. Hard cap at 2. On second blocking verdict: `run.status = "complete_with_findings"`. On clean pass: `run.status = "complete"` and `run.completedAt`. |

# Scope-guard escape hatch

`execute-chunk` already has its own scope guard — if a chunk uncovers a need for broader changes than declared, it stops. The router's response:

1. Persist what was discovered to `scratchpad.notes`.
2. Return to Phase B with the new context and re-classify (almost always one tier higher).
3. Wait for user confirmation before continuing.

Do **not** absorb scope creep silently. The router is the load-bearing place where misclassification gets corrected.

# Style rules

- Be concise but concrete. Bullets over prose.
- Do not pretend certainty where none exists.
- Do not silently widen scope.
- Do not skip Phase B's confirmation — it's the entire point of having a router.
- Do not ask more than 5 clarification questions per phase unless genuinely blocked.
- If blocked, stop cleanly rather than improvising risky implementation.

# Large flow phase details

(Preserved from the previous run-pipeline behaviour for the Large tier only.)

## Phase 1: Requirements intake

Refine the raw request with the user before any technical shaping. Interactive — the requirements-generator persona collaborates with the user, not at them.

1. Read [`./requirements-generator.md`](./requirements-generator.md) and adopt that persona. Escalate to [`../product-team/product-designer.md`](../product-team/product-designer.md) only when the user explicitly asks for research planning, journey mapping, visual critique, or design QA.
2. Produce a **Requirements Brief** with: task summary, surface area, requirements (functional / non-functional / accessibility-when-UI / constraints / out-of-scope / dependencies / edge cases), open questions, assumptions, confirmation-ready brief, suggested next step.
3. Skip sections that don't apply — for backend / contract / infra changes, omit user-journey and visual considerations.
4. Surface the brief and **wait for confirmation or edits** before proceeding.
5. Persist the confirmed brief into `pipeline.json#designBrief`.

**Proceed only after the user confirms the brief.**

## Phase 2: Shape

Run shape-task end-to-end **using the confirmed design brief as the input** (not the raw `$ARGUMENTS`). On exit you must have a confirmed requirement draft, an Implementation Strategy section, an `Execution Chunks` list with acceptance criteria per chunk, and a proceed/block decision.

If shape-task surfaces blocking questions the brief didn't anticipate, return to Phase 1.

## Phase 3: Repository inspection (mandatory Explore)

**Always** dispatch the `Explore` sub-agent (`Agent` tool, `subagent_type: "Explore"`) with the strategy from Phase 2. Brief it with the modules/files the strategy named, the validation commands the strategy plans to run, and the question set: implementation areas, test locations, relevant patterns, any architecture rules from `.claude/rules/architecture.md` likely to bump into.

Thoroughness `medium` by default; `very thorough` only when the strategy is genuinely uncertain.

Persist into `pipeline.json#repoFindings` and emit a one-screen digest under `## Repository Findings`. Do not paste full file dumps.

## Phase 4: Architect plan

Dispatch the **`Plan` sub-agent** (`Agent` tool, `subagent_type: "Plan"`) with a **condensed** briefing — the agent forks, so every line you send inflates the fork.

Send exactly:

- Brief's **goal, non-goals, and constraints** (skip context/users prose).
- A **chunk table**: `chunk ID | one-line objective | acceptance criterion (one line)`. No full chunk specs.
- The **top 5 critical files** identified by Phase 3 (path + one-line role). No file contents.
- A pointer: "must comply with `.claude/rules/architecture.md` (15 hard rules + scanner)".
- The single question: produce a step-by-step implementation plan, list any additional critical files, name architectural trade-offs, and recommend chunk re-orderings, splits, or merges. Flag if it needs more detail before answering.

Reconcile its output: re-ordering applies before Phase 5; splits/merges update `chunks[]` and the TodoWrite list; new risk goes into `scratchpad.notes`; "I need more detail" gets the specific slice asked for; architectural disagreement returns to Phase 2.

Persist into `pipeline.json#architectPlan`.

## Phase 5: Execute each chunk

For every chunk in order, run execute-chunk (interpret → inspect → plan → implement → validate → record).

Two cost rules:
- **Inspect uses `Explore`** when a chunk needs >2 files of grounding the Phase 3 digest didn't cover.
- **Per-chunk validation is targeted**: `pnpm lint` (changed scope) + `bash scripts/affected-tests.sh` + any contracts/schema/workflow gate the chunk actually touched. Full `pnpm check` and full `pnpm test` are deferred to Phase 8.

Apply the Scope Guard whenever unexpected surface appears.

## Phase 6: Close each chunk

Immediately after each execution, run close-chunk. PASS continues; PASS_WITH_NOTES continues if downstream is unaffected; FAIL stops with a blocker summary.

## Phase 7: Final wrap-up

Emit a **compact** outcome summary — one line per chunk: `<ID> — <objective> — <closure decision>`. Aggregate files-changed count + list. Partially completed / blocked chunks. Remaining risks. Recommended next step.

Reporting only — does not flip the trailing TodoWrite item.

## Phase 8: Cleanup-verify (mandatory; owns the final stamp)

Run cleanup-verify. **It owns the final `scope: "full"` stamp** on `last-gate.json` if everything passed. If it reports drift the pipeline should have committed (e.g. regenerated `schema-types.ts`), handle it as a new chunk (execute-chunk → close-chunk), then re-run cleanup-verify.

Skip this phase only when the pipeline is BLOCKED before wrap-up.

## Phase 9: Codex review (mandatory)

Every successful Large pipeline ends with a codex review of the cumulative diff. The hook (`.claude/hooks/codex-review.sh`) is what runs codex; this phase only triggers it.

1. Confirm `last-gate.json` is fresh (Phase 8 stamp <240s old). If older, quick re-validate (`pnpm lint && bash scripts/affected-tests.sh`) and re-stamp.
2. Trigger by flipping the trailing TodoWrite item to `completed`.
3. Track attempts in `run.codexRuns`.
4. On blocking findings (and `run.codexRuns < 2`): treat critical/high findings as a remediation chunk (execute-chunk → close-chunk), then re-run cleanup-verify (Phase 8) so it re-stamps, then trigger codex again by appending a `Codex remediation pass <N>` todo.
5. **Hard cap: 2 codex runs.** After the second verdict: surface outstanding critical findings in the report, set `run.status = "complete_with_findings"`. Do not remediate again.

# Output format

For Small: 5-line summary.
For Medium: same structure as Large below, omitting sections 3, 4, and 9 unless opted in.
For Large: full structure below.

```
# Pipeline Run

## 1. Requirements Brief
### Goals & Non-Goals
### Constraints & Open Questions
### User Confirmation

## 2. Task Shaping
### Confirmed Requirement Draft
### Proceed / Block Decision

## 3. Repository Findings    (Large only — Medium opt-in via +explore)

## 4. Architect Plan          (Large only)
### Plan Summary
### Trade-offs / Risks
### Reconciliation With Chunks

## 5. Execution Chunks
Table: ID | objective | size | status. Full specs in pipeline.json#chunks[].

## 6. Chunk Runs
One bullet per chunk: <ID> — <objective> — <closure decision>. Re-emit detail only on FAIL or PASS_WITH_NOTES with downstream risk.

## 7. Final Outcome
### Files Changed (count + paths)
### Risks / Notes
### Recommended Next Step

## 8. Cleanup & Verify
Drift list, gate-by-gate, baseline comparison. Stamp written: yes/no.

## 9. Codex Review            (Large mandatory; Medium opt-in)
### Verdict (run 1)
### Verdict (run 2, if any)
### Outstanding Critical Findings (only if cap reached with blockers)
```

# Mode notes

- **Bug-fix mode** — additionally surface likely root-cause areas, reproduction considerations, regression risks, and whether a targeted regression test was added.
- **Feature mode** — additionally surface user flow, API/data/model implications, UI/backend coordination, and compatibility expectations.

Apply these as additions to the existing output, not as separate phases.
