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
