#!/usr/bin/env python3
"""Evaluation runner for ProductTeam-skills.

Measures whether a role changes model behaviour, by running each case twice —
once with the role loaded, once without — and grading both against the same
assertions. See evals/README.md for the design rationale.

Development dependency of this repository only. The skills themselves stay
plain markdown with no runtime requirements.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
RESULTS = EVALS / "results"

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_GRADER = "claude-haiku-4-5-20251001"
TIMEOUT = 300

# The baseline arm MUST have a system prompt. Passing none does not give a
# neutral model — it gives the host's default agent prompt, complete with
# working-directory and tool context. That made an early comparison answer
# design questions by searching this repository for HTML tables. The baseline
# has to differ from the role arm in role content only, not in framing.
NEUTRAL_SYSTEM = ("You are a capable assistant helping a product team. "
                  "Answer the request directly and usefully.")


# ---------------------------------------------------------------- claude CLI

class Infra(Exception):
    """Harness or environment failure — never a case result."""


# Substrings that mean the harness could not run, not that the role did badly.
INFRA_SIGNS = ("failed to authenticate", "oauth", "session expired", "not logged in",
               "invalid api key", "credit balance", "rate limit", "is invalid. allowed choices",
               "unknown option", "command not found")


def claude(prompt, system=None, model=DEFAULT_MODEL):
    """One headless turn, no tools, so runs stay comparable and cheap.

    Raises Infra on environment failures. Scoring an auth error as 0.0 would
    silently report a working role as broken — exactly the class of false
    result this harness exists to catch.
    """
    # `--tools none` is what actually denies tools. `--allowed-tools ""` does
    # not: an earlier version used it and eval prompts wrote real files into the
    # repository — a PM prompt asking to "scope an AI chatbot" produced
    # PRICING_CHATBOT_SCOPE.md on disk instead of an answer, and a design prompt
    # spent 300s building an HTML demo instead of describing one.
    #
    # A system prompt is also always passed. Without one the host's default
    # agent prompt applies, which both reaches for tools and frames every task
    # as work in the current repository.
    cmd = ["claude", "-p", prompt, "--model", model, "--tools", "none",
           "--system-prompt", system or NEUTRAL_SYSTEM]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError:
        raise Infra("`claude` CLI not found on PATH")
    except subprocess.TimeoutExpired:
        return None, f"timeout after {TIMEOUT}s"

    err_blob = (r.stderr or "").lower()
    out = (r.stdout or "").strip()

    # Match infra signs in stderr always, but in stdout only for a short
    # response. CLI failures are terse; model answers are long and may
    # legitimately discuss authentication, rate limits or expired sessions.
    # Scanning full stdout aborted a real run because a Product Manager answer
    # about a Salesforce integration mentioned one of these phrases.
    if any(s in err_blob for s in INFRA_SIGNS) or (
            len(out) < 200 and any(s in out.lower() for s in INFRA_SIGNS)):
        raise Infra((r.stderr or out).strip()[:300])
    if r.returncode != 0:
        return None, (r.stderr or "").strip()[:400] or f"exit {r.returncode}"
    if not r.stdout.strip():
        return None, "empty response"
    return r.stdout.strip(), None


def preflight(model):
    """Fail fast and loudly rather than producing a run of meaningless zeros."""
    out, err = claude("Reply with exactly: READY", model=model)
    if err or not out or "READY" not in out.upper():
        raise Infra(f"preflight failed (model={model}): {err or out!r}")


def load_text(rel):
    p = ROOT / rel
    if not p.is_file():
        sys.exit(f"missing file referenced by fixture: {rel}")
    return p.read_text()


# ----------------------------------------------------------------- grading

GRADER_TEMPLATE = """You are grading a model response against explicit assertions.

For each assertion, decide whether the RESPONSE satisfies it. Judge only what \
the response actually says. Do not reward intent, plausibility, or effort. If \
an assertion is only partially addressed, it is not met.

<response>
{response}
</response>

MUST assertions (each should be satisfied):
{must}

MUST_NOT assertions (each should be absent; "met" means the response correctly \
avoided it):
{must_not}

Reply with JSON only, no prose:
{{"must": [{{"i": 0, "met": true, "why": "brief quote or reason"}}],
  "must_not": [{{"i": 0, "met": true, "why": "brief quote or reason"}}]}}"""


def grade(response, case, model):
    must, must_not = case.get("must", []), case.get("must_not", [])
    if not must and not must_not:
        return None, "case declares no assertions"
    fmt = lambda xs: "\n".join(f"{i}. {x}" for i, x in enumerate(xs)) or "(none)"
    out, err = claude(
        GRADER_TEMPLATE.format(response=response, must=fmt(must), must_not=fmt(must_not)),
        model=model)
    if err:
        return None, f"grader failed: {err}"
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None, "grader returned no JSON"
    try:
        v = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        return None, f"grader JSON invalid: {e}"
    met = sum(1 for x in v.get("must", []) if x.get("met")) \
        + sum(1 for x in v.get("must_not", []) if x.get("met"))
    total = len(must) + len(must_not)
    return {"score": met / total if total else 0.0, "total": total, "detail": v}, None


# ------------------------------------------------------------------ suites

def run_routing(cases, args):
    """Routing is graded by exact match — deterministic and free."""
    routing = load_text("routing.md")
    # The escape hatch is load-bearing. Without an explicit "none" option the
    # prompt forces a specialist, so any routing rule that says "this needs no
    # specialist" can never show up in the results.
    system = (routing + "\n\n---\n\nYou are acting purely as the router. "
              "Reply with ONLY one of: the skill filename stem of the single "
              "best role (e.g. `content-designer`), the squad name, or `none` "
              "if the work needs no specialist role at all. No explanation.")
    results = []
    for c in cases:
        accepted = c.get("expect_any") or [c["expect"]]
        runs = []
        for _ in range(args.repeat):
            out, err = claude(c["prompt"], system=system, model=args.model)
            if err:
                runs.append({"error": err, "pass": False})
                continue
            pick = re.sub(r"[`\s.]", "", out.split("\n")[0].strip().lower())
            runs.append({"picked": pick, "pass": any(a in pick for a in accepted),
                         "raw": out[:300]})
        passes = sum(1 for r in runs if r["pass"])
        results.append({"id": c["id"], "prompt": c["prompt"], "accepted": accepted,
                        "rate": passes / len(runs), "runs": runs,
                        "note": c.get("rationale", "")})
        mark = "✓" if passes == len(runs) else ("~" if passes else "✗")
        print(f"  {mark} {c['id']:<34} {passes}/{len(runs)}  "
              f"picked: {runs[-1].get('picked', 'ERROR')}")
    return results


def tick(msg):
    """Per-call progress. A role case is ~12 calls and minutes long; without
    this the runner looks hung."""
    print(msg, end="", flush=True)


def run_roles(cases, args, role_file):
    role = load_text(role_file)
    results = []
    for c in cases:
        entry = {"id": c["id"], "prompt": c["prompt"], "role_runs": [], "base_runs": []}
        arms = [("role_runs", role)]
        if args.baseline:
            arms.append(("base_runs", NEUTRAL_SYSTEM))  # same framing, no role content
        tick(f"  {c['id']:<34} ")
        for label, system in arms:
            tick("[role " if label == "role_runs" else "[base ")
            for _ in range(args.repeat):
                out, err = claude(c["prompt"], system=system, model=args.model)
                if err:
                    entry[label].append({"error": err, "score": 0.0})
                    tick("!")
                    continue
                g, gerr = grade(out, c, args.grader_model)
                # score stays None when grading failed. Scoring an ungraded
                # response as 0.0 drags the mean down and manufactures a
                # regression — it once produced a "ROLE MADE IT WORSE" verdict
                # from a role arm that had actually scored 1.0 twice.
                entry[label].append({"score": g["score"] if g else None,
                                     "error": gerr, "output": out,
                                     "detail": g["detail"] if g else None})
                tick("?" if gerr else "·")
            tick("] ")
        thr = c.get("threshold", 0.8)

        def avg(rs):
            """Mean over graded runs only. Ungraded runs are missing data."""
            got = [r["score"] for r in rs if r["score"] is not None]
            return sum(got) / len(got) if got else None

        entry["role_score"] = avg(entry["role_runs"])
        entry["base_score"] = avg(entry["base_runs"]) if args.baseline else None
        entry["ungraded"] = (sum(1 for r in entry["role_runs"] if r["score"] is None)
                             + sum(1 for r in entry["base_runs"] if r["score"] is None))
        if entry["role_score"] is None or (args.baseline and entry["base_score"] is None):
            entry["bucket"] = "UNGRADED — no verdict"
            results.append(entry)
            print(f"grading failed on every run — no verdict")
            checkpoint(args, role_file, results)
            continue
        entry["role_pass"] = entry["role_score"] >= thr
        entry["base_pass"] = (entry["base_score"] >= thr) if args.baseline else None
        entry["threshold"] = thr
        entry["bucket"] = bucket(entry["role_pass"], entry["base_pass"])
        results.append(entry)
        b = f"{entry['base_score']:.2f}" if args.baseline else " — "
        warn = f"  ⚠ {entry['ungraded']} ungraded" if entry["ungraded"] else ""
        print(f"role {entry['role_score']:.2f} | base {b}  → {entry['bucket']}{warn}")
        checkpoint(args, role_file, results)
    return results


def checkpoint(args, role_file, results):
    """Write partial results after every case. A 20-minute run that dies at
    minute 19 should not lose everything.

    Stamped with model and start time, and cleared at the start of every run:
    a fixed filename with no run identity makes a stale checkpoint from a
    previous run look like live progress for the current one.
    """
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "_partial.json").write_text(json.dumps(
            {"note": "IN-PROGRESS run; superseded by the timestamped file on completion",
             "startedAt": args._started, "model": args.model,
             "graderModel": args.grader_model, "suite": args.suite,
             "roleFile": role_file, "repeat": args.repeat,
             "baseline": args.baseline, "casesDone": len(results),
             "results": results}, indent=2))
    except OSError:
        pass   # never let a checkpoint failure kill the run


def bucket(role_pass, base_pass):
    if base_pass is None:
        return "inconclusive (no baseline)"
    return {(True, False): "role earns its place",
            (True, True): "role changed nothing",
            (False, False): "neither passes",
            (False, True): "ROLE MADE IT WORSE"}[(role_pass, base_pass)]


# -------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Run ProductTeam-skills evaluations.")
    ap.add_argument("suite", choices=["routing", "roles"])
    ap.add_argument("--role", help="role stem, e.g. product-manager (roles suite)")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--no-baseline", dest="baseline", action="store_false", default=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--grader-model", default=DEFAULT_GRADER)
    args = ap.parse_args()

    if args.suite == "routing":
        files = [EVALS / "routing" / "cases.yaml"]
        args.baseline = False          # routing has no meaningful no-router baseline
    else:
        d = EVALS / "roles"
        files = [d / f"{args.role}.yaml"] if args.role else sorted(d.glob("*.yaml"))
    files = [f for f in files if f.is_file()]
    if not files:
        sys.exit("no fixture files found")

    suites = []
    for f in files:
        spec = yaml.safe_load(f.read_text())
        cases = spec.get("cases", [])[: args.limit] if args.limit else spec.get("cases", [])
        suites.append((f, spec, cases))

    per_case = args.repeat * ((2 if args.baseline else 1) * (2 if args.suite == "roles" else 1))
    total_calls = sum(len(c) for _, _, c in suites) * per_case
    print(f"\nSuite: {args.suite}   fixtures: {len(suites)}   "
          f"cases: {sum(len(c) for _, _, c in suites)}   repeat: {args.repeat}")
    print(f"Baseline comparison: {'ON' if args.baseline else 'OFF — results inconclusive'}")
    print(f"Estimated model calls: ~{total_calls}  "
          f"(task: {args.model}, grader: {args.grader_model})\n")

    if args.dry_run:
        for f, spec, cases in suites:
            print(f"{f.relative_to(ROOT)}")
            for c in cases:
                print(f"  - {c['id']}: {c['prompt'][:80]}")
        return

    if not args.yes and input("Run and spend tokens? [y/N] ").strip().lower() != "y":
        sys.exit("aborted")

    try:
        preflight(args.model)
        if args.suite == "roles":
            preflight(args.grader_model)
    except Infra as e:
        sys.exit(f"\nENVIRONMENT NOT READY — no cases were run.\n  {e}\n\n"
                 "Fix the environment and re-run. A partial or zeroed result set\n"
                 "would be worse than none: it looks like a failing role.")

    started = time.time()
    args._started = datetime.now(timezone.utc).isoformat()
    # Clear any checkpoint from a previous run before writing our own, so a
    # stale file can never be mistaken for this run's progress.
    try:
        (RESULTS / "_partial.json").unlink(missing_ok=True)
    except OSError:
        pass

    out = {"suite": args.suite, "startedAt": args._started,
           "model": args.model, "graderModel": args.grader_model,
           "repeat": args.repeat, "baseline": args.baseline, "fixtures": []}

    try:
        for f, spec, cases in suites:
            print(f"\n{f.stem}:")
            res = (run_routing(cases, args) if args.suite == "routing"
                   else run_roles(cases, args, spec["role_file"]))
            out["fixtures"].append({"file": str(f.relative_to(ROOT)),
                                    "role": spec.get("role"), "results": res})
    except Infra as e:
        sys.exit(f"\nABORTED mid-run — environment failure, not a role failure.\n"
                 f"  {e}\nPartial results discarded.")

    out["durationSeconds"] = round(time.time() - started, 1)
    summarise(out)

    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{args.suite}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nFull results (including every raw output): {path.relative_to(ROOT)}")


def summarise(out):
    print("\n" + "=" * 62 + "\nSUMMARY\n" + "=" * 62)
    if out["suite"] == "routing":
        rows = [r for fx in out["fixtures"] for r in fx["results"]]
        clean = sum(1 for r in rows if r["rate"] == 1.0)
        partial = sum(1 for r in rows if 0 < r["rate"] < 1.0)
        mean = sum(r["rate"] for r in rows) / len(rows) if rows else 0.0
        print(f"  routed correctly every time : {clean}/{len(rows)}")
        print(f"  ambiguous (some runs wrong) : {partial}/{len(rows)}")
        print(f"  never correct               : {len(rows) - clean - partial}/{len(rows)}")
        print(f"  mean routing rate           : {mean:.1%}")
        print("\n  Compare runs on mean rate, not the clean count. A case moving\n"
              "  0% → 67% is real progress that the clean count discards.")
        if partial:
            print("\n  Ambiguous cases are the measured overlap between roles:")
            for r in rows:
                if 0 < r["rate"] < 1.0:
                    print(f"    - {r['id']} ({r['rate']:.0%})")
        return

    tally = {}
    for fx in out["fixtures"]:
        for r in fx["results"]:
            tally[r["bucket"]] = tally.get(r["bucket"], 0) + 1
    for k in ("role earns its place", "role changed nothing", "neither passes",
              "ROLE MADE IT WORSE", "inconclusive (no baseline)"):
        if k in tally:
            print(f"  {k:<28} {tally[k]}")
    if not out["baseline"]:
        print("\n  No baseline was run. These results cannot show whether the role helped.")
    elif tally.get("ROLE MADE IT WORSE"):
        print("\n  A role scored worse than no role. Investigate before shipping.")


if __name__ == "__main__":
    main()
