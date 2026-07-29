#!/usr/bin/env python3
"""Blind A/B comparison: role vs no role, on real product tasks.

The fixture harness in run.py measures compliance — did the output contain the
properties an assertion said it should. This measures usefulness: given the same
real task twice, which artefact would you rather have received?

Two commands:

    compare.py generate --role product-designer --tasks evals/tasks/design.yaml
    compare.py reveal   evals/comparisons/<dir>

`generate` writes judge.md with the outputs labelled A and B in a random order,
and hides the mapping in .key.json. Read judge.md, decide, then run `reveal`.
"""

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run import (claude, Infra, load_text, preflight, ROOT, DEFAULT_MODEL,  # noqa: E402
                 NEUTRAL_SYSTEM)

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

COMPARISONS = ROOT / "evals" / "comparisons"

# Applied identically to both arms. routing.md instructs roles to state which
# role they are using, which would unblind the comparison in the first line.
# Both arms get the same suppression so it cannot bias the result.
NO_PREAMBLE = ("\n\nDo not preamble. Do not state which role, persona, or "
               "perspective you are adopting. Begin directly with the deliverable.")


def generate(args):
    role_path = f"product-team/{args.role}.md"
    role = load_text(role_path)

    if args.task:
        tasks = [{"id": "adhoc", "prompt": args.task}]
    else:
        spec = yaml.safe_load(Path(args.tasks).read_text())
        tasks = spec["tasks"][: args.limit] if args.limit else spec["tasks"]

    print(f"\nRole: {args.role}   tasks: {len(tasks)}   model: {args.model}")
    print(f"Calls: {len(tasks) * 2}\n")
    if args.dry_run:
        for t in tasks:
            print(f"  - {t['id']}: {t['prompt'][:90]}")
        return
    if not args.yes and input("Run and spend tokens? [y/N] ").strip().lower() != "y":
        sys.exit("aborted")

    try:
        preflight(args.model)
    except Infra as e:
        sys.exit(f"\nENVIRONMENT NOT READY — nothing was run.\n  {e}")

    rng = random.Random(args.seed)
    stamp = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    outdir = COMPARISONS / f"{stamp}-{args.role}"
    outdir.mkdir(parents=True, exist_ok=True)

    key, doc = [], [
        f"# Blind comparison — {args.role}", "",
        "Two responses per task. One had the role loaded, one did not.",
        "**You are not told which.** Read both, decide which you would rather",
        "have received, and note it. Then run:", "",
        f"    python3 evals/compare.py reveal {outdir.relative_to(ROOT)}", "",
        "Judge on usefulness, not length or polish. A longer answer is not a",
        "better one. If they are genuinely equivalent, say tie — that is a",
        "real and useful result.", "", "---", "",
    ]

    for i, t in enumerate(tasks, 1):
        print(f"  [{i}/{len(tasks)}] {t['id']} ", end="", flush=True)
        prompt = t["prompt"] + NO_PREAMBLE
        with_role, e1 = claude(prompt, system=role, model=args.model)
        print("·", end="", flush=True)
        without, e2 = claude(prompt, system=NEUTRAL_SYSTEM, model=args.model)
        print("· ", end="", flush=True)
        if e1 or e2:
            print(f"skipped ({e1 or e2})")
            continue

        flip = rng.random() < 0.5          # which arm is shown as A
        a, b = (with_role, without) if flip else (without, with_role)
        key.append({"n": i, "id": t["id"], "A": "role" if flip else "no-role",
                    "B": "no-role" if flip else "role"})
        doc += [f"## Task {i} — {t['id']}", "", f"> {t['prompt']}", "",
                "### Response A", "", a, "", "### Response B", "", b, "",
                f"**Task {i} verdict:** A / B / tie", "", "---", ""]
        print("ok")

    if not key:
        sys.exit("no tasks completed")

    (outdir / "judge.md").write_text("\n".join(doc))
    (outdir / ".key.json").write_text(json.dumps(
        {"role": args.role, "model": args.model, "seed": args.seed,
         "createdAt": stamp, "mapping": key}, indent=2))

    print(f"\nRead:   {(outdir / 'judge.md').relative_to(ROOT)}")
    print(f"Then:   python3 evals/compare.py reveal {outdir.relative_to(ROOT)}")
    print("\nThe mapping is in .key.json — don't open it until you've decided.")


def reveal(args):
    d = Path(args.dir)
    key = json.loads((d / ".key.json").read_text())
    print(f"\n{key['role']}  (model {key['model']})\n")

    verdicts = {}
    if args.verdicts:
        for line in Path(args.verdicts).read_text().splitlines():
            if ":" in line:
                n, v = line.split(":", 1)
                verdicts[int(n.strip())] = v.strip().lower()

    score = {"role": 0, "no-role": 0, "tie": 0}
    for m in key["mapping"]:
        v = verdicts.get(m["n"])
        while v not in ("a", "b", "tie"):
            v = input(f"  Task {m['n']} ({m['id']}) — which did you prefer? [A/B/tie] ").strip().lower()
        picked = "tie" if v == "tie" else m[v.upper()]
        score[picked] += 1
        label = "tie" if picked == "tie" else f"you picked the {picked} response"
        print(f"    → A was {m['A']}, B was {m['B']}  —  {label}")

    n = sum(score.values())
    print(f"\n  role preferred     {score['role']}/{n}")
    print(f"  no-role preferred  {score['no-role']}/{n}")
    print(f"  tie                {score['tie']}/{n}")
    # Read wins and losses before ties. An early version fired "mostly ties: the
    # role is not changing the work" on a 2 win / 0 loss / 2 tie result, which
    # is a clearly favourable outcome.
    if score["no-role"] > score["role"]:
        print("\n  The role is making outputs worse on these tasks. Investigate before shipping.")
    elif score["role"] > score["no-role"]:
        never_worse = " and never lost" if score["no-role"] == 0 else ""
        print(f"\n  The role won more often than it lost{never_worse}. Ties mean it was")
        print("  neutral there, not harmful — worth knowing which tasks those were.")
    elif score["tie"] == n:
        print("\n  Every task tied: on this sample the role is not changing the work.")
    else:
        print("\n  Wins and losses are level. No signal either way on this sample.")
    print(f"\n  n={n} with one judge. A strong signal, not a statistic.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate")
    g.add_argument("--role", required=True, help="role stem, e.g. product-designer")
    g.add_argument("--tasks", help="YAML file of tasks")
    g.add_argument("--task", help="a single ad-hoc task prompt")
    g.add_argument("--model", default=DEFAULT_MODEL)
    g.add_argument("--limit", type=int)
    g.add_argument("--seed", type=int, default=1, help="recorded, so A/B order is reproducible")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--yes", action="store_true")

    r = sub.add_parser("reveal")
    r.add_argument("dir")
    r.add_argument("--verdicts", help="file of 'N: A|B|tie' lines instead of prompting")

    args = ap.parse_args()
    if args.cmd == "generate":
        if not (args.tasks or args.task):
            sys.exit("pass --tasks <file> or --task <prompt>")
        generate(args)
    else:
        reveal(args)


if __name__ == "__main__":
    main()
