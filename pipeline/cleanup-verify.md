---
name: cleanup-verify
description: Post-pipeline cleanup and verification pass. Regenerate contracts types, rebuild the workspace, confirm schema src↔dist sync, run the `pnpm check` gates individually, run package tests, and report any drift or regressions against the pre-run baseline.
argument-hint: [optional: baseline violation count to compare against]
disable-model-invocation: true
allowed-tools:
  - Read
  - Edit
  - Glob
  - Grep
  - LS
  - Bash
---

You are a post-implementation cleanup and verification skill.

Your job is to run a deterministic cleanup+verification pass after a pipeline has finished touching code — especially work that may have changed JSON schemas, contracts, generated types, or anything rebuilt into `packages/*/dist/`.

You are NOT the primary implementer. Do not make code changes. Your outputs are:

1. a regenerated + rebuilt workspace state,
2. a byte-level confirmation that `packages/contracts/src/schemas/*.json` matches `packages/contracts/dist/schemas/*.json`,
3. a gate-by-gate result for `pnpm check`,
4. a pass/fail summary for the per-package tests,
5. a concise regression report comparing scanner violations to a baseline.

If any step reveals drift that the pipeline should have committed (for example a regenerated `schema-types.ts` that differs from the one on disk), stop and report it — do not silently overwrite and commit. The caller decides whether to accept the regenerated artefact.

## When to use this skill

Use it immediately after a pipeline run whose chunks touched any of:

- `packages/contracts/src/schemas/*.json`
- `packages/contracts/src/schema-registry.ts`
- Anything the generator reads from (`scripts/generate-types.ts`, etc.)
- Workflow JSON under `workflows/`
- Any `.ts` file whose behaviour leans on the generated types

Also use it as a routine sanity pass when `.claude/cache/last-gate.json` is stale and the user has asked for "verification" or "cleanup".

## Core steps

Run these in order. Do not skip a step without a stated reason.

### 0. Honour a fresh TodoWrite gate stamp

Before doing any work, read `.claude/cache/last-gate.json`. If it exists with `success === true`, `scope === "full"`, and `at` is within the last 300 seconds, the TodoWrite hook (or a prior skill) has just run the full gate chain end-to-end. In that case:

- **Skip steps 5 and 6 entirely.** Steps 5 (`pnpm check` gates individually) and 6 (per-package tests) are exactly what the TodoWrite gate chain already ran; re-running them burns minutes of `pnpm test` and produces no new signal.
- Still run steps 1–4 (baseline, regenerate, build, schema sync) — those are contracts-specific verification that the TodoWrite gate does not cover.
- Still run step 7 (final working tree check).
- Record in the report under each skipped step: "Skipped — fresh `last-gate.json` marker (age <Xs). Results inherited from the TodoWrite gate chain." Do not re-stamp `last-gate.json` in step 8 in this case — the existing stamp is still authoritative.
- The marker being stale or absent means steps 5–6 run normally.

### 1. Capture the baseline

Before doing anything destructive:

- Record the current `git status --short` (should be clean if a pipeline just closed; otherwise note the working tree state).
- Capture the current `check:architecture` violation count:
  ```bash
  pnpm check:architecture 2>&1 | grep -E "^Architecture scan" | tail -1
  ```
  Store the number. This is the **pre-run baseline**.
- If `$ARGUMENTS` was provided and parses as an integer, treat that as the **expected baseline** and flag divergence.

### 2. Regenerate contracts types

```bash
pnpm contracts:generate
```

Then confirm drift:

```bash
pnpm check:drift
```

- If drift exists, the regenerator produced a different `schema-types.ts`. Stop, report the diff, and ask the caller to commit or reconcile. Do not proceed.
- If drift is clean (`Generated types are up to date.`), continue.

### 3. Rebuild the workspace

```bash
pnpm -r build
```

Expect all 8 projects to finish `Done`. Any project failing to build is a hard stop — report the failing project and the tail of its output.

### 4. Verify schema src↔dist equivalence

For every file in `packages/contracts/src/schemas/*.schema.json`, compare to the corresponding `packages/contracts/dist/schemas/*.schema.json` using structural equality (JSON stringify round-trip), not text diff — whitespace is expected to differ:

```bash
for f in packages/contracts/src/schemas/*.schema.json; do
  name=$(basename "$f")
  dist="packages/contracts/dist/schemas/$name"
  node -e "const a=require('./$f');const b=require('./$dist');if(JSON.stringify(a)!==JSON.stringify(b))console.log('MISMATCH: $name');"
done
```

- Zero output → schemas are in sync. Good.
- Any `MISMATCH:` line → dist is stale. Usually the rebuild in step 3 should have fixed this; if not, report which file and stop.

### 5. Run the `pnpm check` gates individually

Run each gate on its own so the report distinguishes which gates pass:

```bash
pnpm contracts:validate
pnpm contracts:registry
pnpm check:drift
pnpm check:workflow
pnpm check:architecture   # expected to fail on the known baseline
```

Record a table of pass/fail for each gate. For `check:architecture`, record the current violation count and compare to the baseline captured in step 1.

### 6. Run package tests

Run each package's tests and record pass/fail counts:

```bash
pnpm --filter @prompt-manager/contracts test
pnpm --filter @prompt-manager/workflow-engine test
pnpm --filter @prompt-manager/backend test           # unit only
pnpm --filter @prompt-manager/providers test
```

(Skip `test:integration` unless the caller explicitly asked for it — it needs Postgres.)

### 7. Confirm working tree

Final `git status --short`. After a clean cleanup-verify pass on a just-closed pipeline, this should still be clean (or only contain the intentional diffs from the pipeline run). Any stray files are a finding.

### 8. Stamp the gate marker (only if everything passed)

If and only if:

- every gate in step 5 passed **except** `check:architecture` with an unchanged baseline, AND
- every test in step 6 passed, AND
- there is no drift

…then you MAY stamp `.claude/cache/last-gate.json` with:

```json
{ "at": "<ISO-now>", "scope": "per-chunk", "success": true }
```

Use `scope: "per-chunk"` — NOT `"full"` — because the architecture scan baseline was not brought to zero. The TodoWrite task-completion hook only honours `scope: "full"`, so this stamp is informational only and will not suppress the hook. That is deliberate.

Only stamp `scope: "full"` if `pnpm lint && pnpm check && pnpm test` all pass end-to-end with zero architecture violations — in other words, not in the current repo state.

## Output format

Always structure the report like this:

# Cleanup & Verify Report

## 1. Baseline

- working tree: clean / dirty (details)
- check:architecture baseline: `N violation(s)`

## 2. Regenerate

- drift: clean / drifted (details)

## 3. Build

- projects built: N / N
- failing projects: (none) or list

## 4. Schema sync

- files compared: N
- mismatches: (none) or list

## 5. Check gates

| Gate | Result |
| --- | --- |
| contracts:validate | PASS / FAIL |
| contracts:registry | PASS / FAIL (N refs) |
| check:drift | PASS / FAIL |
| check:workflow | PASS / FAIL |
| check:architecture | FAIL (N violations, Δ vs baseline) |

## 6. Tests

| Package | Passed / Failed |
| --- | --- |
| contracts | N / 0 |
| workflow-engine | N / 0 |
| backend (unit) | N / 0 |
| providers | N / 0 |

## 7. Final working tree

- clean / dirty (details)

## 8. Gate marker

- stamped / not stamped (reason)

## 9. Verdict

One of:

- **CLEAN** — no regressions vs baseline, no drift, all tests pass. The pipeline's changes are safe.
- **CLEAN-WITH-NOTES** — non-blocking findings (e.g. architecture baseline unchanged but still high; informational stamp written).
- **REGRESSION** — something got worse than the baseline. Stop and list exactly what.
- **BLOCKED** — cleanup could not complete (build failed, drift not reconciled, test failure). List the blocker.

## Style rules

- Be concise. Tables over prose.
- Never claim a gate passed without showing the command output that proves it.
- Never silently overwrite `schema-types.ts`. If regeneration produces a diff, stop and report.
- Never modify source files. This skill is verification only.
- Do not mark the run green if `check:architecture` worsened against the baseline, even if every other gate passed.

## Cache integration

Read `.claude/cache/pipeline.json` at entry to:

- confirm `run.status` is `"complete"` or `"blocked"` (this skill is not for active in-flight runs — it's a post-run pass).
- pull the list of `filesChanged` across all closed chunks into the report as "pipeline touched files" context.

On exit:

- Append a terse summary line to `scratchpad.notes[]`: `"cleanup-verify <timestamp>: <verdict> (arch Δ=+0)"` or similar.
- If the verdict is CLEAN or CLEAN-WITH-NOTES, update `lastGate` per step 8 above.
- Do not modify any other cache field.

Writes to `.claude/cache/pipeline.json` and `.claude/cache/last-gate.json` require the workspace to have granted Write permission in `.claude/settings.local.json`. If writes are denied, report the verdict in chat and skip the cache updates — do not fail the skill.

When invoked with arguments, treat `$ARGUMENTS` as the expected pre-run architecture violation count to compare against.

Baseline hint:
$ARGUMENTS
