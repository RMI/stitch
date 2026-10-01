# Shared bash helpers for the scripts in scripts/. Source it, do not execute:
#
#     source "${BASH_SOURCE[0]%/*}/lib/common.sh"
#
# Requires bash (uses indirect expansion to test whether a name is already set).
# Mirrors scripts/lib/env.py: same file order, same "already set wins" rule.

stitch_repo_root() {
  # STITCH_REPO_ROOT is the bash counterpart of env.py's `root=` argument:
  # an explicit override, mainly for tests and for running against a copy.
  if [ -n "${STITCH_REPO_ROOT:-}" ]; then
    printf '%s\n' "$STITCH_REPO_ROOT"
    return 0
  fi

  # Every workspace member carries a pyproject.toml, so pair it with a marker
  # only the root has.
  local dir="${1:-${BASH_SOURCE[0]%/*}}"
  dir=$(cd "$dir" 2>/dev/null && pwd) || return 1

  while [ -n "$dir" ] && [ "$dir" != "/" ]; do
    if [ -f "$dir/pyproject.toml" ] &&
      { [ -e "$dir/.git" ] || [ -f "$dir/uv.lock" ]; }; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir=$(dirname "$dir")
  done

  printf 'no repo root above %s\n' "${1:-$PWD}" >&2
  return 1
}

# Load one env file without clobbering anything already exported.
stitch_load_env_file() {
  local line key value
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}" # strip leading blanks
    case "$line" in '' | '#'*) continue ;; esac
    line="${line#export }"

    key="${line%%=*}"
    [ "$key" = "$line" ] && continue # no '=' on the line
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}" # strip trailing blanks

    case "$key" in '' | *[!A-Za-z0-9_]*) continue ;; esac

    # Strip one layer of matching quotes, as dotenv does.
    case "$value" in
      \"*\") value="${value#\"}" && value="${value%\"}" ;;
      \'*\') value="${value#\'}" && value="${value%\'}" ;;
    esac

    [ -n "${!key+set}" ] && continue # already set: keep it
    export "$key=$value"
  done <"$1"
}

# Load extra files (highest precedence, in the order given) then the defaults.
stitch_load_env() {
  local root file
  root=$(stitch_repo_root) || return 1

  for file in "$@" \
    "$root/.env.scripts" \
    "$root/scripts/.env" \
    "$root/.env"; do
    [ -f "$file" ] || continue
    stitch_load_env_file "$file"
  done
}
