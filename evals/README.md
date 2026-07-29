# Evaluation harness

Tests whether the roles in this suite actually improve output — not whether they produce output that looks plausible.

## Why this exists, and why the design is shaped this way

[SWE-Skills-Bench](https://arxiv.org/abs/2603.15401) evaluated 49 public agent skills across 565 task instances. **39 of 49 produced zero pass-rate improvement.** Average gain was +1.2%. Three skills made results *worse*. Token overhead reached +451% with no accompanying benefit.

The conclusion is not that skills don't work — seven of them improved results by up to 30%. It is that **most skills do nothing, and you cannot tell which kind you have by reading them.** A skill that reads well, is carefully structured, and encodes real expertise can still fail to change what the model does.

That single finding determines the whole design here:

- **Baseline comparison is mandatory, not a nice-to-have.** A role that passes its own fixtures tells you nothing if the same model passes them without the role loaded. The headline metric is the *delta*, not the pass rate.
- **Cases where role and baseline both pass are the important output.** They mark content that is carrying no weight. Per the finding above, expect most cases to land here. That is the signal for what to cut, not a failure of the harness.
- **Single runs are noise.** Model output varies. Use `--repeat` and read pass *rates*.

Anthropic's [authoring guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices) says the same thing from the other direction: build evaluations *before* writing extensive documentation, establish a baseline, then write the minimum that beats it. This repo did it in the opposite order, so the harness is retrospective — it exists to find out which of ~6,400 lines of persona content is load-bearing.

## What is tested

### Suite 1 — routing

Given the routing brain, does the correct role or squad get selected?

The roles in this repo carry `disable-model-invocation: true` and are **not** auto-discovered — they are dispatched by `routing.md`. So the usual "does the skill trigger" test does not apply. The equivalent question here is whether routing picks correctly, and it is the cheapest useful signal in the harness: one short call per case, graded by exact match.

This suite also measures something the external review asserted but never tested: that overlapping personas create ambiguous routing. `expect_any` cases encode the overlaps explicitly, so the ambiguity becomes a number rather than a claim.

### Suite 2 — role behaviour

Given a role and a prompt, does the output satisfy the behaviours that role promises, and does it beat the same model without the role?

Each case declares `must` and `must_not` behaviours in plain language. A grader model checks the output against them and returns structured verdicts. Score is the fraction of assertions satisfied.

## What is not tested

Honesty about scope matters more than coverage claims:

- **Outcome quality in real work.** Fixtures approximate tasks; they are not the tasks.
- **Multi-turn behaviour.** Every case is single-turn.
- **Cross-role handoffs.** Worth building later; not built.
- **Tool use.** The runner denies tools so results are comparable and cheap.
- **Grader reliability.** The grader is a model and can be wrong. Treat individual verdicts as evidence, not proof, and read the transcripts when a result surprises you.

## Running it

Requires the `claude` CLI, `python3`, and PyYAML. These are development dependencies of this repository only — they are **not** required to use the skills, which stay plain markdown.

```bash
python3 evals/run.py routing --dry-run
```

Always dry-run first. It prints the call count and cost shape without spending anything.

```bash
python3 evals/run.py routing --yes
```

```bash
python3 evals/run.py roles --role product-manager --repeat 3 --yes
```

Useful flags:

| Flag | Effect |
|---|---|
| `--dry-run` | Show what would run. No API calls. |
| `--yes` | Skip the confirmation prompt. |
| `--repeat N` | Run each case N times; report pass rate instead of pass/fail. |
| `--limit N` | Only the first N cases. |
| `--no-baseline` | Skip baseline runs. Marks the whole run `inconclusive`. |
| `--model` / `--grader-model` | Override models. Grading defaults to a cheaper model. |

Results land in `evals/results/<timestamp>.json`, including every raw output so a surprising verdict can be inspected rather than trusted. That directory is gitignored — the raw transcripts are large, model-specific, and go stale immediately. Commit the conclusion, not the run.

### Infrastructure failure is not a result

The runner preflights both models before any case runs, and aborts the whole run on an authentication error, a missing CLI, a bad flag, or a rate limit.

This matters more than it looks. An expired auth token produces empty responses, which grade as `0.0`, which renders as **a role scoring zero against baseline** — a confident, precise, completely false finding. The first version of this runner did exactly that and reported four routing failures that were entirely an expired OAuth session. Any harness that scores environment failures is worse than no harness, because it produces wrong conclusions rather than no conclusions.

Requires an authenticated `claude` CLI. If you are running inside a sandboxed agent session, the CLI may not be able to authenticate — run the suite from a normal terminal instead.

## Reading the output

The summary table reports four buckets per case:

| Bucket | Meaning | What to do |
|---|---|---|
| **role ✓ / base ✗** | The role earned its place | Keep it |
| **role ✓ / base ✓** | Both pass; the role changed nothing measurable | Candidate for deletion |
| **role ✗ / base ✗** | Neither passes | The role doesn't cover this yet — fix the role or drop the case |
| **role ✗ / base ✓** | The role made things worse | Investigate immediately; this happened to 3 of 49 skills in the benchmark |

A role whose cases are overwhelmingly `role ✓ / base ✓` is documentation, not a skill. That is a legitimate thing to be — but it should be a decision, not an accident.

**Do not optimise for a high pass rate.** It is trivially achieved by writing easy fixtures. The number that matters is how many cases move from ✗ to ✓ when the role is loaded.

## What has actually been measured

All figures below come from the corrected harness — neutral baseline, tools denied, ungraded runs excluded. Earlier numbers taken before those fixes are superseded.

### Routing

Mean accuracy across 16 cases, `--repeat 3`, four iterations of `routing.md`:

| | mean rate |
|---|---:|
| baseline | 70.8% |
| + disambiguation rules 6 & 7 | 85.4% |
| + harness escape hatch | 87.5% |
| + two roles-table rows sharpened | **89.6%** |

Two findings drove it:

- **Keyword collision, not persona overlap.** "Payments integration" routed to Pricing Strategist; "release risk" to Delivery Manager. Where roles genuinely overlap, routing coped fine. The external review that prompted this work diagnosed overlap and prescribed fewer roles; the data says the fix is disambiguation.
- **The roles table outweighs the prose rules beneath it.** One case failed 0/3 across three prose edits, then passed at 67% when two words changed in the table. Put load-bearing distinctions in the table.

### product-manager, hard fixture set

Assertions derived from the role's own quality rubric and Known limits, not from the fixture author's preference. `--repeat 3`.

| | baseline | with role | delta |
|---|---:|---:|---:|
| Sonnet | 92% | 100% | +8 |
| Haiku | 59% | 98% | **+39** |

Per case, the gap opens where the model is weakest:

| case | Sonnet base | Haiku base |
|---|---:|---:|
| solution-first-request | 100% | 25% |
| gamed-metric | 92% | 25% |
| outside-competence | 67% | 67% |

**A role's value scales inversely with model capability.** On Sonnet the persona adds 8 points; on Haiku, 39. Trimming role content on strong-model evidence would optimise for the best model available and quietly degrade everything below it. Every eval should therefore run on at least two models — a single-model result led directly to a wrong recommendation during this work.

### Blind A/B, product-designer

Four real design tasks, outputs shuffled, judged by a human who did not know which arm was which:

- role preferred **2**, no-role preferred **0**, tie **2**

The role never lost. Wins were on `empty-state` and `destructive-confirm` — craft-specific edge-case work. Ties were on `bulk-actions` and `onboarding-cut` — general product reasoning a strong model does well anyway. Same shape as the fixture data, arrived at by a completely different method.

## The instrument was the main source of error

Eight defects surfaced in the harness during its first day, and **every one produced a confident, plausible, wrong result**. Recorded because the pattern is the lesson:

| Defect | What it produced |
|---|---|
| Invented `--permission-mode denyAll` | 4 routing "failures" that were a rejected CLI flag |
| Auth error scored as `0.0` | A working role reported as scoring zero |
| Infra-sign matching over full stdout | Aborted a valid run because a PM answer mentioned "rate limit" |
| `expect_any` omitted a correct answer | 3 correct routings scored as failures |
| Routing prompt offered no `none` option | A rule that says "no specialist needed" could never fire |
| Fixture referenced code it never included | An unsatisfiable assertion read as a role failure |
| Grader failure scored as `0.0` | A `ROLE MADE IT WORSE` verdict from an arm that scored 1.0 twice |
| Baseline passed no system prompt | Compared the role against the host's *agent* prompt, not a neutral one — silently corrupted every baseline figure |

The last two are the instructive ones. Both produced numbers that looked reasonable and were reported as findings before being caught. The first six announced themselves.

Two habits caught all eight, and neither is optional: **run a baseline**, and **store every raw transcript**. A summary table cannot tell you it is lying; a transcript can.

One more caution in the other direction. Routing rule 7 ("trivial work needs no specialist") scored 0–33% in this harness but works correctly in a real installed project. The harness prompt demanding a bare filename was suppressing it. Fixture framing can hide a working rule as easily as it can invent a broken one.

## Adding cases

Start from the `Regression prompts` section already at the bottom of every role file — those are test-case seeds that were never executed. Converting one means adding the assertions that make it checkable.

Write `must` items as observable properties of the output ("states which assumptions are unverified"), not as instructions ("should be thorough"). If a grader cannot check it from the text alone, it is not an assertion.

Write at least one `must_not`. Failure modes are more diagnostic than successes, and they are what the role's `Known limits` section already gestures at.

### Fixtures are the least reliable part of this harness

In the first sitting, three of roughly thirty cases were defective, and **every one produced a confident, precise, false result**:

- an `expect_any` list omitted a legitimate answer, scoring three correct routings as failures;
- the routing prompt offered no `none` option, so a rule saying "this needs no specialist" could never appear;
- a case said "fix this function" without including the function, making its `must` unsatisfiable while the arms behaved correctly.

None of these looked like bugs in the summary table. They looked like findings.

So: **read the raw output before believing a failure.** Every run stores full responses and per-assertion grader reasoning in `evals/results/`. A case that fails is a hypothesis about the role — confirm it against the transcript before acting on it. The failures worth trusting are the ones where you can point at the text.
