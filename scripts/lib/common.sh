# Shared bash helpers; source it, do not execute. Requires bash.

# The monorepo root, or $STITCH_REPO_ROOT when set.
stitch_repo_root() {
  if [ -n "${STITCH_REPO_ROOT:-}" ]; then
    printf '%s\n' "$STITCH_REPO_ROOT"
    return 0
  fi

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

# Export KEY=VALUE pairs from one env file, keeping anything already set.
stitch_load_env_file() {
  local line key value
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}"
    case "$line" in '' | '#'*) continue ;; esac
    line="${line#export }"

    key="${line%%=*}"
    [ "$key" = "$line" ] && continue
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"

    case "$key" in '' | *[!A-Za-z0-9_]*) continue ;; esac

    case "$value" in
      \"*\") value="${value#\"}" && value="${value%\"}" ;;
      \'*\') value="${value#\'}" && value="${value%\'}" ;;
    esac

    [ -n "${!key+set}" ] && continue
    export "$key=$value"
  done <"$1"
}

# Load any extra files given, then .env.scripts, scripts/.env and .env.
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
