# ProductTeam-skills

Reusable Claude Code agent skills implementing a coordinated product-team operating system. Originally factored out of [MedMe](https://github.com/afaconti-glitch/medme) so the same role definitions can drive any future project without dragging project-specific context with them.

The suite contains 16 role personas plus a routing brain. Each role is a self-contained markdown skill (frontmatter + persona body) following the [Agent Skills](https://agentskills.io/home) format used by Claude Code, OpenAI Codex, and other compatible agents.

## What's in here

```
ProductTeam-skills/
├── product-team/                     # The 16 role personas
│   ├── product-manager.md
│   ├── product-strategist.md
│   ├── growth-product-marketing-manager.md
│   ├── ux-researcher.md
│   ├── data-analyst.md
│   ├── customer-success.md
│   ├── product-designer.md
│   ├── content-designer.md
│   ├── design-systems-specialist.md
│   ├── accessibility-specialist.md
│   ├── software-engineer.md
│   ├── technical-architect.md
│   ├── devops-engineer.md
│   ├── security-specialist.md
│   ├── qa-engineer.md
│   └── delivery-manager.md
├── routing.md                        # The routing brain (paste into your CLAUDE.md)
└── README.md
```

## Roles at a glance

### Product and strategy

| Role | Use when |
|---|---|
| Product Manager | Defining value, scope, outcomes, prioritisation, PRDs, backlog structure |
| Product Strategist | Market positioning, vision, strategic bets, competitive framing |
| Growth Product Marketing Manager | Adoption, activation, messaging, funnel improvement |

### Research, insight, and data

| Role | Use when |
|---|---|
| UX Researcher | Research planning, discovery, interviews, synthesis, validation |
| Data Analyst | Metrics, dashboards, funnels, experiments, behavioural evidence |
| Customer Success | Customer feedback, retention signals, account pain points, adoption blockers |

### Design and experience

| Role | Use when |
|---|---|
| Product Designer | UX, UI, flows, interaction design, design QA, accessibility-minded design |
| Content Designer | UX writing, labels, errors, onboarding, comprehension, content clarity |
| Design Systems Specialist | Components, tokens, theming, pattern governance, interface consistency |
| Accessibility Specialist | WCAG-minded review, inclusive design, assistive technology risks |

### Engineering, delivery, and quality

| Role | Use when |
|---|---|
| Software Engineer | Implementation, code, feasibility, technical trade-offs |
| Technical Architect | System design, integration strategy, scalability, platform decisions |
| DevOps Engineer | CI/CD, environments, deployment, observability, release reliability |
| Security Specialist | Threat modelling, security audits, RLS / auth review, privacy and DPIA, supply-chain audit, AI/LLM safety, incident readiness, vulnerability triage |
| QA Engineer | Test planning, regression, bug reporting, acceptance validation |
| Delivery Manager | Delivery planning, dependency tracking, ceremonies, delivery risks |

The Security Specialist is partly an internal extension of the [vibe-security-skill](https://github.com/raroque/vibe-security-skill) cookbook, broadened to cover threat modelling, UK GDPR / DPIA, supply-chain hygiene, IAM, browser security beyond CSP, AI safety beyond key protection, and healthcare-grade concerns.

## Installing into a project

### Option A — Git submodule (recommended)

A submodule pins the consuming project to a specific tag, makes updates deliberate (`git submodule update --remote`), and keeps the role files in one canonical place.

```bash
# Inside the consuming project's repo root

# 1. Add the submodule under .claude/skills-vendor
git submodule add https://github.com/afaconti-glitch/ProductTeam-skills.git .claude/skills-vendor

# 2. Pin to a stable tag
cd .claude/skills-vendor && git checkout v1.0.0 && cd -
git add .claude/skills-vendor
git commit -m "Pin ProductTeam-skills to v1.0.0"

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

Updating to a new release of this suite: `cd .claude/skills-vendor && git fetch && git checkout v1.x.y && cd - && git commit -am "Bump ProductTeam-skills to v1.x.y"`.

### Option B — Copy (simpler, no upstream tracking)

```bash
git clone https://github.com/afaconti-glitch/ProductTeam-skills.git /tmp/ProductTeam-skills
mkdir -p .claude/skills
cp /tmp/ProductTeam-skills/product-team/*.md .claude/skills/
echo '.claude/' >> .gitignore
```

Updates require re-copying. Use this when the project will diverge from the canonical suite.

## Wiring into the consuming project's CLAUDE.md

Copy the contents of [routing.md](./routing.md) into the consuming project's `CLAUDE.md` under a heading like `# Product delivery operating system`.

If you used **Option A**, find-and-replace `.claude/skills/` → `.claude/skills-vendor/product-team/` in the pasted routing block so the paths point at the submodule.

If you used **Option B**, the routing paths already match (`.claude/skills/<role>.md`).

Project-specific context (stack, architecture rules, engineering conventions, working behaviour) goes **above** the routing brain in `CLAUDE.md`. The routing brain itself stays generic.

## Conventions

- All role files use **UK English** spelling.
- Frontmatter follows the Agent Skills schema: `name`, `description`, `license`, `compatibility`, `metadata` (with `version`, `language`, `persona_type`, `tags`, `intents`, `output_types`).
- Each role file ends with a `## Maintenance` section listing when to review it. Treat that as a versioning trigger — bump the role's `version` whenever you change behaviour-shaping content.
- Role files are stable surface area: changes that alter how the role responds should be deliberate and documented in commit messages.

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
