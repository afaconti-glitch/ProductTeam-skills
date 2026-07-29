#!/usr/bin/env bash
#
# Install ProductTeam-skills into a consuming project.
#
#   ./install.sh                 # from inside a clone, installs into $PWD's parent project
#   ./install.sh /path/to/repo   # explicit target
#   ./install.sh --submodule /path/to/repo
#
# Copy mode (default) writes the role, pipeline and reference files into
# .claude/skills/ and leaves the project free to diverge. Submodule mode pins
# the suite to a tag and keeps updates deliberate.
#
# Either way the routing brain is appended to the project's CLAUDE.md with its
# paths already rewritten — the step most likely to be got wrong by hand.

set -euo pipefail

SUITE_URL="https://github.com/afaconti-glitch/ProductTeam-skills.git"
MODE="copy"
TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --submodule) MODE="submodule"; shift ;;
    --copy)      MODE="copy"; shift ;;
    -h|--help)   sed -n '2,16p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *)           TARGET="$1"; shift ;;
  esac
done

SUITE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${TARGET:-$PWD}"

[[ -d "$TARGET" ]] || { echo "error: target '$TARGET' is not a directory" >&2; exit 1; }
TARGET="$(cd "$TARGET" && pwd)"

if [[ "$TARGET" == "$SUITE_ROOT" ]]; then
  echo "error: target is the suite itself. Pass the consuming project's path." >&2
  exit 1
fi

echo "Installing ProductTeam-skills"
echo "  from:  $SUITE_ROOT"
echo "  into:  $TARGET"
echo "  mode:  $MODE"
echo

# ---------------------------------------------------------------- place files

if [[ "$MODE" == "submodule" ]]; then
  git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1 || {
    echo "error: submodule mode needs '$TARGET' to be a git repository" >&2; exit 1; }
  if [[ -e "$TARGET/.claude/skills-vendor" ]]; then
    echo "  .claude/skills-vendor already exists — leaving it alone"
  else
    git -C "$TARGET" submodule add -q "$SUITE_URL" .claude/skills-vendor
    LATEST_TAG="$(git -C "$SUITE_ROOT" tag -l 'v*' --sort=-v:refname | head -1)"
    if [[ -n "$LATEST_TAG" ]]; then
      git -C "$TARGET/.claude/skills-vendor" checkout -q "$LATEST_TAG"
      echo "  pinned to $LATEST_TAG"
    fi
  fi
  SKILL_PREFIX=".claude/skills-vendor/product-team"
  PIPE_PREFIX=".claude/skills-vendor/pipeline"
else
  mkdir -p "$TARGET/.claude/skills/pipeline" "$TARGET/.claude/skills/references"
  cp "$SUITE_ROOT"/product-team/*.md              "$TARGET/.claude/skills/"
  cp "$SUITE_ROOT"/product-team/references/*.md   "$TARGET/.claude/skills/references/"
  cp "$SUITE_ROOT"/pipeline/*.md                  "$TARGET/.claude/skills/pipeline/"
  echo "  copied $(ls "$SUITE_ROOT"/product-team/*.md | wc -l | tr -d ' ') roles,"\
       "$(ls "$SUITE_ROOT"/pipeline/*.md | wc -l | tr -d ' ') pipeline skills,"\
       "$(ls "$SUITE_ROOT"/product-team/references/*.md | wc -l | tr -d ' ') references"
  SKILL_PREFIX=".claude/skills"
  PIPE_PREFIX=".claude/skills/pipeline"
fi

# ------------------------------------------------------- routing into CLAUDE.md

MARK_START="<!-- ProductTeam-skills:start -->"
MARK_END="<!-- ProductTeam-skills:end -->"
CLAUDE_MD="$TARGET/CLAUDE.md"

# Rewrite the paths in routing.md to match where the files actually landed.
ROUTING="$(sed \
  -e "s#\`\.claude/skills/pipeline/#\`$PIPE_PREFIX/#g" \
  -e "s#\`\.claude/skills/#\`$SKILL_PREFIX/#g" \
  "$SUITE_ROOT/routing.md")"

if [[ -f "$CLAUDE_MD" ]] && grep -qF "$MARK_START" "$CLAUDE_MD"; then
  # The routing text goes via a temp file, not stdin: stdin is already taken by
  # the heredoc carrying the script, and supplying both silently feeds the
  # markdown to python as its source.
  ROUTING_TMP="$(mktemp)"
  printf '%s' "$ROUTING" > "$ROUTING_TMP"
  python3 - "$CLAUDE_MD" "$MARK_START" "$MARK_END" "$ROUTING_TMP" <<'PY'
import sys, pathlib
path, start, end, block_file = sys.argv[1:5]
block = pathlib.Path(block_file).read_text()
p = pathlib.Path(path); t = p.read_text()
head, _, rest = t.partition(start)
_, _, tail = rest.partition(end)
p.write_text(f"{head}{start}\n{block}\n{end}{tail}")
PY
  rm -f "$ROUTING_TMP"
  echo "  updated existing routing block in CLAUDE.md"
else
  { [[ -f "$CLAUDE_MD" ]] && printf '\n'; printf '%s\n%s\n%s\n' "$MARK_START" "$ROUTING" "$MARK_END"; } >> "$CLAUDE_MD"
  echo "  appended routing block to CLAUDE.md"
fi

# ------------------------------------------------------------------ gitignore

GI="$TARGET/.gitignore"
if [[ "$MODE" == "submodule" ]]; then
  grep -qF '!.claude/skills-vendor/' "$GI" 2>/dev/null || {
    printf '\n# Claude Code project state. The skills suite is the tracked submodule below.\n.claude/*\n!.claude/skills-vendor/\n' >> "$GI"
    echo "  updated .gitignore (keeps the submodule tracked)"; }
else
  grep -qE '^\.claude/?$' "$GI" 2>/dev/null || {
    printf '\n# Claude Code project state, including the copied skills suite.\n.claude/\n' >> "$GI"
    echo "  updated .gitignore"; }
fi

# ------------------------------------------------------------------- adapter

ADAPTER="$TARGET/.claude/pipeline-adapter.md"
if [[ -e "$ADAPTER" ]]; then
  echo "  pipeline adapter already present — leaving it alone"
else
  cp "$SUITE_ROOT/pipeline/project-adapter.md" "$ADAPTER"
  echo "  seeded .claude/pipeline-adapter.md (template — fill it in)"
fi

echo
echo "Done. Next:"
echo "  1. Fill in .claude/pipeline-adapter.md with this project's commands and gates."
echo "     Without it the pipeline still runs, discovering commands from your"
echo "     manifests and CI config, but it has to guess."
echo "  2. Put project-specific context ABOVE the routing block in CLAUDE.md."
echo "  3. Try it:  ask for something narrow and see which role gets invoked."
