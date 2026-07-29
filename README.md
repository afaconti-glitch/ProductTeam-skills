# ProductTeam-skills

A portable persona and prompt operating system for a coordinated product team. The role definitions are project-agnostic, so the same suite can drive any project without dragging project-specific context with it.

The suite contains 19 role personas, an eight-skill delivery pipeline, and a routing brain. Each role is a self-contained markdown file: Agent-Skills-shaped frontmatter plus a persona body.

### Packaging: what this is, and what it is not

These are **flat markdown files invoked through the routing brain**, not natively packaged Agent Skills.

The [Agent Skills](https://code.claude.com/docs/en/skills) format requires one directory per skill containing a `SKILL.md`, and hosts discover skills by scanning for that layout. This repository ships `product-team/<role>.md` instead. The practical consequences:

- **Roles are not auto-discovered or auto-triggered.** They are read on demand via the paths in `routing.md`, which you paste into your `CLAUDE.md`. That is the intended design — the routing brain decides which lens applies, rather than a description match.
- **`disable-model-invocation: true` in the frontmatter is inert** under this install. It is a skill-discovery field, and nothing discovers these as skills. It is retained so the files are ready to package later.
- **`metadata`, `license` and `compatibility` are documentation**, not part of the Agent Skills schema, which requires only `name` and `description`.
- **`allowed-tools` in the pipeline files is a host allow-list.** Entries a host does not recognise are ignored.

**This is a deliberate choice, not an unfinished migration.** Three reasons:

- **The routing brain measurably works.** Role selection was tested at 89.6% mean accuracy across 16 cases, up from 70.8% before targeted fixes. Auto-discovery would bypass that logic and select on description-matching instead.
- **The roles set `disable-model-invocation: true` on purpose.** They are meant to be dispatched deliberately, not triggered by keyword proximity — which is exactly the failure mode routing testing exposed ("payments integration" pulling Pricing Strategist).
- **`install.sh` removes the friction packaging would have solved.** Path rewriting was the error-prone step, and it is now automated and tested.

If you do want auto-discovery, wrapping each role in its own directory with a `SKILL.md` is mechanical — the frontmatter already carries `name` and `description`. Weigh it against the fact that 29 skill descriptions would then be preloaded on every turn.

## What's in here

```
ProductTeam-skills/
├── product-team/                     # The 18 role personas
│   ├── product-manager.md
│   ├── product-strategist.md
│   ├── growth-product-marketing-manager.md
│   ├── pricing-strategist.md
│   ├── ux-researcher.md
│   ├── data-analyst.md
│   ├── customer-success.md
│   ├── storm-researcher.md
│   ├── product-designer.md
│   ├── content-designer.md
│   ├── design-systems-specialist.md
│   ├── motion-designer.md
│   ├── accessibility-specialist.md
│   ├── software-engineer.md
│   ├── technical-architect.md
│   ├── devops-engineer.md
│   ├── security-specialist.md
│   ├── qa-engineer.md
│   ├── delivery-manager.md
│   └── references/                   # Detail loaded on demand, not by default
│       ├── security-audit-cookbook.md
│       ├── security-healthcare-pack.md
│       └── motion-resources.md
├── pipeline/                         # Delivery pipeline execution suite
│   ├── run-pipeline.md               # Entry point — classify, confirm, dispatch
│   ├── requirements-generator.md     # Lightweight coding-task intake
│   ├── shape-task.md                 # Decompose brief into chunks
│   ├── execute-chunk.md              # Implement one chunk safely
│   ├── close-chunk.md                # Verify chunk closure
│   ├── cleanup-verify.md             # Post-pipeline gate sweep
│   ├── diagnose.md                   # Systematic root-cause analysis
│   ├── design-critique.md            # Final-pass design review
│   ├── project-adapter.md            # Per-project commands, gates, risky paths
│   └── state-schema.md               # Shared pipeline state contract
├── evals/                            # Does any of this actually help?
│   ├── README.md                     # Design, and how to read the results
│   ├── run.py                        # Runner — role vs no-role baseline
│   ├── routing/cases.yaml            # Does routing pick the right role?
│   └── roles/*.yaml                  # Per-role behaviour fixtures
├── routing.md                        # The routing brain (paste into your CLAUDE.md)
└── README.md
```

## Delivery pipeline

Six skills that work as an integrated execution framework. The entry point is `run-pipeline` — it classifies work by size and routes it through the right phase composition, sharing state via `.claude/cache/pipeline.json`.

| Skill | Use when |
|---|---|
| run-pipeline | Starting any coding task — it classifies scope (Small/Medium/Large) and dispatches to the right flow |
| requirements-generator | Turning a rough engineering request into a confirmation-ready brief |
| shape-task | Decomposing a confirmed brief into requirements, strategy, and execution chunks |
| execute-chunk | Implementing one approved chunk safely with inspection, scoped edits, and targeted validation |
| close-chunk | Verifying a completed chunk against its acceptance criteria before moving on |
| cleanup-verify | Post-pipeline gate sweep: regenerate types, rebuild, check schema sync, run tests |
| diagnose | Systematic root-cause analysis for bugs — reproduce → isolate → verify → fix |
| design-critique | Final-pass design review producing a SHIP / SHIP_WITH_NOTES / HOLD decision |

Two supporting documents make the pipeline portable:

| Document | Purpose |
|---|---|
| [project-adapter.md](./pipeline/project-adapter.md) | Declares this project's package manager, gate chain, generated artefacts, risky paths and host integrations. Copy to `.claude/pipeline-adapter.md` and fill in. |
| [state-schema.md](./pipeline/state-schema.md) | The shared state contract for `pipeline.json` and `last-gate.json`, including how skills degrade when state is unavailable. |

**The pipeline runs without an adapter.** Skills fall back to discovering commands from repository instructions, manifests, CI config and the lockfile, and they state what they found. Writing the adapter makes it deterministic and lets you declare things discovery cannot infer — which gates may fail, which paths are risky, whether an independent reviewer exists.

Nothing in the pipeline assumes a JavaScript toolchain, a specific agent host, or a writable cache. The worked example in the adapter is illustrative only.

### Verified, not just written

The pipeline has been run end to end against two purpose-built projects rather than only reviewed:

| Testbed | Exercises | Result |
|---|---|---|
| npm project **with** an adapter — blocking drift gate, ratcheted style gate at accepted baseline 3, deliberately stale generated artefact | `run-pipeline` (Small + bump-up), `execute-chunk`, `close-chunk`, `cleanup-verify` | All correct |
| Python/Make project with **no adapter** and no cache | the discovery fallback | All correct, zero JS assumptions |

Specifically observed:

- **Tier classification and bump-up.** A "one-line" schema change was correctly promoted Small → Medium, citing the rule rather than the surface size. Plans stopped for confirmation instead of proceeding.
- **Targeted validation.** `execute-chunk` ran lint and tests but correctly skipped the build and drift gates, because the chunk didn't touch the declared risk path.
- **Stamp discipline.** `close-chunk` re-ran the gate chain itself rather than trusting the implementer's report, then withheld the `last-gate` stamp because no state directory existed — citing the schema's availability rule.
- **Drift handling.** `cleanup-verify` regenerated the stale artefact, reported the diff, refused to commit it, withheld the stamp, and returned `BLOCKED`. On the no-adapter project it also restored the working tree to its original state afterwards.
- **Ratchet handling.** A permanently-failing style gate at its accepted baseline was treated as no-worse-than-baseline, not as a failure.
- **Discovery.** With no adapter, gates were discovered from `CONTRIBUTING.md` cross-checked against the `Makefile`, and the source of each was stated.

See `routing.md` for the full tier matrix and when to invoke each skill directly.

## Roles at a glance

### Product and strategy

| Role | Use when |
|---|---|
| Product Manager | Defining value, scope, outcomes, prioritisation, PRDs, backlog structure |
| Product Strategist | Market positioning, vision, strategic bets, competitive framing |
| Growth Product Marketing Manager | Adoption, activation, messaging, funnel improvement, CRO, content strategy, SEO |
| Pricing Strategist | Pricing model design, tier structure, packaging, willingness-to-pay, monetisation trade-offs |

### Research, insight, and data

| Role | Use when |
|---|---|
| UX Researcher | Research planning, discovery, interviews, synthesis, validation |
| Data Analyst | Metrics, dashboards, funnels, experiments, behavioural evidence |
| Customer Success | Customer feedback, retention signals, account pain points, adoption blockers |
| STORM Researcher | Deep, strategic, or contested research via a five-perspective scan (practitioner, academic, sceptic, incentive, historical), contradiction mapping, evidence-weighted synthesis, and adversarial peer review |

### Design and experience

| Role | Use when |
|---|---|
| Product Designer | UX, UI, flows, interaction design, design QA, accessibility-minded design |
| Content Designer | UX writing, labels, errors, onboarding, comprehension, content clarity |
| Design Systems Specialist | Components, tokens, theming, pattern governance, interface consistency, UI foundation selection, component source intake |
| Motion Designer | UI animation, transitions, micro-interactions, expressive and brand-led motion, cursor/hover effects, ambient and particle backgrounds, motion tokens/systems, reduced-motion, animation performance, third-party motion component intake |
| Accessibility Specialist | WCAG-minded review, inclusive design, assistive technology risks, data-visualisation accessibility |

### Engineering, delivery, and quality

| Role | Use when |
|---|---|
| Software Engineer | Implementation, code, feasibility, technical trade-offs, library selection, version-matched API use |
| Technical Architect | System design, integration strategy, scalability, platform decisions, standing-dependency evaluation |
| DevOps Engineer | CI/CD, environments, deployment, observability, release reliability |
| Security Specialist | Threat modelling, security audits, RLS / auth review, privacy and DPIA, supply-chain audit including licence boundaries and tool servers, AI/LLM safety, incident readiness, vulnerability triage |
| QA Engineer | Test planning, regression, bug reporting, acceptance validation, durable proof of verification |
| Delivery Manager | Delivery planning, dependency tracking, ceremonies, delivery risks |

The Security Specialist covers threat modelling, UK GDPR / DPIA, supply-chain hygiene including licence and commercial boundaries, IAM, browser security beyond CSP, and AI safety. Its nine-category audit checklist and its health-data domain pack live under `product-team/references/` and load only when the task calls for them. It can also invoke the [vibe-security-skill](https://github.com/raroque/vibe-security-skill) cookbook for focused AI-introduced-vulnerability audits.

## Installing into a project

### Quickest — the install script

```bash
git clone https://github.com/afaconti-glitch/ProductTeam-skills.git
./ProductTeam-skills/install.sh /path/to/your-project
```

It copies the roles, pipeline and references into `.claude/skills/`, appends the routing brain to the project's `CLAUDE.md` **with the paths already rewritten**, updates `.gitignore`, and seeds a pipeline adapter template. Add `--submodule` to pin to a tag instead of copying.

Re-running it updates the routing block in place between its markers, leaving everything you wrote above it untouched. Verified on both fresh install and update.

The manual routes below do the same thing by hand; the path rewriting in step 4 is the part that most often goes wrong.

### Option A — Git submodule (recommended)

A submodule pins the consuming project to a specific tag, makes updates deliberate (`git submodule update --remote`), and keeps the role files in one canonical place.

```bash
# Inside the consuming project's repo root

# 1. Add the submodule under .claude/skills-vendor
git submodule add https://github.com/afaconti-glitch/ProductTeam-skills.git .claude/skills-vendor

# 2. Pin to a stable tag
cd .claude/skills-vendor && git checkout v1.1.0 && cd -
git add .claude/skills-vendor
git commit -m "Pin ProductTeam-skills to v1.1.0"

# 3. Configure .gitignore so other Claude state stays local-only
#    but the submodule path is allowed through
cat >> .gitignore <<'EOF'

# Claude Code project-local state. The skills suite lives in the
# tracked submodule below; everything else stays local.
.claude/*
!.claude/skills-vendor/
EOF

# 4. In CLAUDE.md, paste the contents of routing.md and update the
#    skill paths to point at the vendor directory:
#    .claude/skills/<role>.md  →  .claude/skills-vendor/product-team/<role>.md
```

Cloning the consuming project later: `git clone --recurse-submodules <url>` (or `git submodule update --init` after a normal clone).

Updating to a new release of this suite: `cd .claude/skills-vendor && git fetch && git checkout v1.1.0 && cd - && git commit -am "Bump ProductTeam-skills to v1.1.0"`.

### Option B — Copy (simpler, no upstream tracking)

```bash
git clone https://github.com/afaconti-glitch/ProductTeam-skills.git /tmp/ProductTeam-skills
mkdir -p .claude/skills/pipeline .claude/skills/references
cp /tmp/ProductTeam-skills/product-team/*.md .claude/skills/
cp /tmp/ProductTeam-skills/product-team/references/*.md .claude/skills/references/
cp /tmp/ProductTeam-skills/pipeline/*.md .claude/skills/pipeline/
echo '.claude/' >> .gitignore
```

Copy `references/` too — roles link to it by relative path, and the links break without it.

Updates require re-copying. Use this when the project will diverge from the canonical suite.

## Wiring into the consuming project's CLAUDE.md

Copy the contents of [routing.md](./routing.md) into the consuming project's `CLAUDE.md` under a heading like `# Product delivery operating system`.

If you used **Option A**, find-and-replace `.claude/skills/` → `.claude/skills-vendor/product-team/` in the pasted routing block so the paths point at the submodule.

If you used **Option B**, the routing paths already match (`.claude/skills/<role>.md`).

Project-specific context (stack, architecture rules, engineering conventions, working behaviour) goes **above** the routing brain in `CLAUDE.md`. The routing brain itself stays generic.

## Conventions

- All role files use **UK English** spelling.
- Frontmatter carries `name` and `description` (the two fields the Agent Skills schema requires) plus `license`, `compatibility`, `disable-model-invocation` and `metadata` (`version`, `language`, `persona_type`, `tags`, `intents`, `output_types`). Everything beyond `name` and `description` is this repo's own documentation convention — see the packaging note above.
- Keep role bodies **under 500 lines**, per [Anthropic's authoring guidance](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices). Past that, move detail into `product-team/references/` and link to it from the role with a stated trigger for when to read it.
- Each role file ends with a `## Maintenance` section listing when to review it. Treat that as a versioning trigger — bump the role's `version` whenever you change behaviour-shaping content.
- Role files are stable surface area: changes that alter how the role responds should be deliberate and documented in commit messages.

## Evaluation

Every role ships a `Regression prompts` section. Those are test-case *seeds*, not tests — nothing executed them. `evals/` turns them into something that runs.

The design point is the baseline: each case runs twice, once with the role loaded and once without, and both are graded against the same assertions. **The metric that matters is the delta, not the pass rate.** A role that passes its own fixtures proves nothing if the same model passes them unaided.

```bash
python3 evals/run.py routing --dry-run
```

This is deliberately unflattering. [Benchmark evidence](https://arxiv.org/abs/2603.15401) across 49 public agent skills found 39 produced no measurable improvement at all, and three made results worse — so expect a meaningful share of cases to land in "role changed nothing." Those cases are the point: they identify content that can be cut.

Evals are a development dependency of this repository (`claude` CLI, `python3`, PyYAML). The skills themselves remain plain markdown with no runtime requirements. See [evals/README.md](./evals/README.md).

## Versioning

This repo uses semver. Tag releases as `v<MAJOR>.<MINOR>.<PATCH>` on `main`.

- **MAJOR** — breaking change to a role's contract (e.g. a renamed intent that consuming routing depends on, or a removed role).
- **MINOR** — new role added, new intent on an existing role, new output type.
- **PATCH** — wording tweaks, clarifications, regression-prompt additions, frontmatter fixes.

Consuming projects should pin to a specific tag and update deliberately.

## Licence

Proprietary. Internal use only. See [LICENSE](./LICENSE).

## Contributing (internal)

- Follow the existing role file structure when adding a new role.
- Update [routing.md](./routing.md) when adding a role: new row in the relevant table, new squad memberships if the role is cross-functional, new entry in the specialist-routing examples.
- Bump the version in the role file's frontmatter on behaviour-shaping changes.
- Tag a new release after merge to `main`.
