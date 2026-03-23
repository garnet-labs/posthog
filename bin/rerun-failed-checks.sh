#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# rerun-failed-checks.sh
#
# Polls your open GitHub PRs and reruns failed CI checks automatically.
# Only acts on PRs you've explicitly approved. Stores permissions in a
# JSON config file so a second terminal can enable/disable PRs on the fly.
#
# Usage (watcher — interactive, runs in a loop):
#   ./bin/rerun-failed-checks.sh                  # interactive watcher
#   ./bin/rerun-failed-checks.sh --dry-run        # watch but don't rerun
#   ./bin/rerun-failed-checks.sh --interval 120   # poll every 120s
#
# While the watcher is running, press:
#   e  — open interactive PR selector (toggle which PRs are watched)
#   q  — quit
#
# Management commands (run from another terminal):
#   ./bin/rerun-failed-checks.sh --status          # show all tracked PRs
#   ./bin/rerun-failed-checks.sh --enable 51277    # start watching a PR
#   ./bin/rerun-failed-checks.sh --disable 51277   # stop watching a PR
# ---------------------------------------------------------------------------

CONFIG_FILE="${HOME}/.rerun-failed-checks.json"
DRY_RUN=false
INTERVAL=300
INTERVAL_SET=false
REPO=""
ALL_CHECKS=false
MAX_RETRIES=5

# Commands (mutually exclusive with the watcher)
CMD=""
CMD_ARG=""

usage() {
    cat <<'EOF'
Usage: rerun-failed-checks.sh [OPTIONS]

Watcher mode (runs in a loop):
  (no command)             Start the interactive watcher
  --dry-run                Log what would be done without rerunning anything
  --all-checks             Rerun all failed checks (default: required only)
  --interval SECONDS       Polling interval (default: 300)
  --repo OWNER/REPO        Target a specific repo (default: current repo)

  While running, press:
    e  — edit which PRs are watched (interactive selector)
    q  — quit

Management commands (run once and exit):
  --status                 Show all tracked PRs and their permissions
  --enable PR_NUMBER       Enable auto-rerun for a PR
  --disable PR_NUMBER      Disable auto-rerun for a PR
  -h, --help               Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)    DRY_RUN=true; shift ;;
        --all-checks) ALL_CHECKS=true; shift ;;
        --interval)   INTERVAL="$2"; INTERVAL_SET=true; shift 2 ;;
        --repo)       REPO="$2"; shift 2 ;;
        --status)     CMD="status"; shift ;;
        --enable)     CMD="enable"; CMD_ARG="$2"; shift 2 ;;
        --disable)    CMD="disable"; CMD_ARG="$2"; shift 2 ;;
        -h|--help)    usage ;;
        *)            echo "Unknown option: $1"; usage ;;
    esac
done

REPO_FLAG=""
if [[ -n "$REPO" ]]; then
    REPO_FLAG="--repo $REPO"
fi

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
info() { log "INFO   $*"; }
warn() { log "WARN   $*"; }
skip() { log "SKIP   $*"; }
act()  { log "ACTION $*"; }

# ---------------------------------------------------------------------------
# Config file helpers
#
# Config format:
#   { "prs": { "<number>": { "enabled": bool, "title": "..." }, ... },
#     "retries": { "<run_id>": count, ... },
#     "settings": { "all_checks": bool, "interval": int, "max_retries": int } }
# ---------------------------------------------------------------------------

# gh CLI sometimes mixes debug/trace lines into stdout alongside JSON.
# This filters down to just the JSON array.
extract_json() {
    grep -E '^\[' | tail -1
}

config_read() {
    if [[ -f "$CONFIG_FILE" ]]; then
        cat "$CONFIG_FILE"
    else
        echo '{"prs":{},"retries":{},"settings":{}}'
    fi
}

config_write() {
    local json="$1"
    echo "$json" | jq '.' > "$CONFIG_FILE"
}

# Migrate old flat format (PR keys at top level) to nested "prs" key.
config_migrate() {
    if [[ ! -f "$CONFIG_FILE" ]]; then
        return
    fi
    local current
    current=$(cat "$CONFIG_FILE")
    if echo "$current" | jq -e 'has("prs")' >/dev/null 2>&1; then
        return
    fi
    local migrated
    migrated=$(echo "$current" | jq '{
        prs: (to_entries | map(select(.key != "settings" and .key != "retries")) | from_entries),
        retries: (.retries // {}),
        settings: (.settings // {})
    }')
    config_write "$migrated"
}

config_get_enabled() {
    local pr_number="$1"
    config_read | jq -r --arg pr "$pr_number" \
        'if .prs | has($pr) then .prs[$pr].enabled | tostring else "unknown" end'
}

config_set() {
    local pr_number="$1"
    local enabled="$2"
    local title="${3:-}"
    local current
    current=$(config_read)
    local updated
    updated=$(echo "$current" | jq --arg pr "$pr_number" --argjson enabled "$enabled" --arg title "$title" \
        '.prs[$pr] = (.prs[$pr] // {}) + {enabled: $enabled} | if $title != "" then .prs[$pr].title = $title else . end')
    config_write "$updated"
}

config_remove_closed() {
    local open_prs_json="$1"
    local current
    current=$(config_read)
    local open_numbers
    open_numbers=$(echo "$open_prs_json" | jq -r '.[].number | tostring')

    local pr_number
    for pr_number in $(echo "$current" | jq -r '.prs | keys[]'); do
        if ! echo "$open_numbers" | grep -qx "$pr_number"; then
            info "PR #${pr_number} is no longer open — removing from config"
            current=$(echo "$current" | jq --arg pr "$pr_number" 'del(.prs[$pr])')
        fi
    done
    config_write "$current"
}

# ---------------------------------------------------------------------------
# Management commands (--status, --enable, --disable)
# ---------------------------------------------------------------------------
cmd_status() {
    local config
    config=$(config_read)
    local count
    count=$(echo "$config" | jq '.prs | length')

    if (( count == 0 )); then
        echo "No PRs tracked yet. Start the watcher to detect PRs."
        exit 0
    fi

    echo ""
    echo "Tracked PRs:"
    echo "---------------------------------------------------"
    echo "$config" | jq -r '.prs | to_entries[] | "  #\(.key)  \(if .value.enabled then "ENABLED " else "DISABLED" end)  \(.value.title // "(no title)")"'
    echo "---------------------------------------------------"
    echo ""
    echo "Use --enable PR_NUMBER or --disable PR_NUMBER to change."
    exit 0
}

cmd_enable() {
    local pr_number="$1"
    config_set "$pr_number" true
    echo "Enabled auto-rerun for PR #${pr_number}"
    exit 0
}

cmd_disable() {
    local pr_number="$1"
    config_set "$pr_number" false
    echo "Disabled auto-rerun for PR #${pr_number}"
    exit 0
}

# Handle management commands immediately
config_migrate
case "$CMD" in
    status)  cmd_status ;;
    enable)  cmd_enable "$CMD_ARG" ;;
    disable) cmd_disable "$CMD_ARG" ;;
esac

# ---------------------------------------------------------------------------
# Interactive TUI screens — delegate to Python curses
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

edit_prs() {
    local count
    count=$(config_read | jq '.prs | length')

    if (( count == 0 )); then
        info "No PRs tracked yet — nothing to edit"
        return
    fi

    python3 "${SCRIPT_DIR}/pr-selector.py" prs < /dev/tty > /dev/tty 2>/dev/tty
    echo ""
}

edit_settings() {
    python3 "${SCRIPT_DIR}/pr-selector.py" settings < /dev/tty > /dev/tty 2>/dev/tty
    load_settings
    echo ""
}

# Read settings from the config file (called on startup and after editing)
load_settings() {
    local config
    config=$(config_read)

    local saved_all_checks
    saved_all_checks=$(echo "$config" | jq -r '.settings.all_checks // false')
    if [[ "$saved_all_checks" == "true" ]]; then
        ALL_CHECKS=true
    else
        ALL_CHECKS=false
    fi

    local saved_interval
    saved_interval=$(echo "$config" | jq -r '.settings.interval // empty')
    if [[ -n "$saved_interval" ]]; then
        INTERVAL="$saved_interval"
    fi

    local saved_max_retries
    saved_max_retries=$(echo "$config" | jq -r '.settings.max_retries // empty')
    if [[ -n "$saved_max_retries" ]]; then
        MAX_RETRIES="$saved_max_retries"
    fi
}

# ---------------------------------------------------------------------------
# Rerun cache — don't re-trigger the same workflow run within 10 minutes
# ---------------------------------------------------------------------------
declare -A RERUN_CACHE

cache_key_fresh() {
    local run_id="$1"
    local now
    now=$(date +%s)
    if [[ -n "${RERUN_CACHE[$run_id]:-}" ]]; then
        local last="${RERUN_CACHE[$run_id]}"
        local age=$(( now - last ))
        if (( age < 600 )); then
            return 0  # still fresh, skip
        fi
    fi
    return 1  # not fresh, ok to rerun
}

cache_mark() {
    local run_id="$1"
    RERUN_CACHE[$run_id]=$(date +%s)
}

# ---------------------------------------------------------------------------
# Retry tracking — persisted in config file under "retries" key
# ---------------------------------------------------------------------------
retry_get_count() {
    local run_id="$1"
    config_read | jq -r --arg id "$run_id" '.retries[$id] // 0'
}

retry_increment() {
    local run_id="$1"
    local current
    current=$(config_read)
    config_write "$(echo "$current" | jq --arg id "$run_id" '.retries[$id] = ((.retries[$id] // 0) + 1)')"
}

# Remove retry entries for runs that are no longer failing
retry_cleanup() {
    local active_run_ids="$1"
    local current
    current=$(config_read)
    local retries_json
    retries_json=$(echo "$current" | jq '.retries // {}')

    if [[ "$retries_json" == "{}" ]]; then
        return
    fi

    local updated="$current"
    for stored_id in $(echo "$retries_json" | jq -r 'keys[]'); do
        if ! echo "$active_run_ids" | grep -qx "$stored_id"; then
            updated=$(echo "$updated" | jq --arg id "$stored_id" 'del(.retries[$id])')
        fi
    done
    config_write "$updated"
}

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
process_pr() {
    local pr_number="$1"
    local pr_title="$2"

    local checks_scope="required"
    local required_flag="--required"
    if [[ "$ALL_CHECKS" == true ]]; then
        checks_scope="all"
        required_flag=""
    fi

    info "Checking PR #${pr_number} (${checks_scope} checks): ${pr_title}"

    local checks_json
    checks_json=$(gh pr checks "$pr_number" $REPO_FLAG $required_flag --json "name,state,bucket,link" 2>/dev/null | extract_json) || {
        warn "  Could not fetch checks for PR #${pr_number}"
        return
    }

    if [[ -z "$checks_json" ]]; then
        warn "  No checks data returned for PR #${pr_number}"
        return
    fi

    local total failed pending passed
    total=$(echo "$checks_json" | jq 'length')
    failed=$(echo "$checks_json" | jq '[.[] | select(.bucket == "fail")] | length')
    pending=$(echo "$checks_json" | jq '[.[] | select(.bucket == "pending")] | length')
    passed=$(echo "$checks_json" | jq '[.[] | select(.bucket == "pass")] | length')

    info "  Checks: ${passed} passed, ${failed} failed, ${pending} pending (${total} total)"

    if (( failed == 0 )); then
        if (( pending > 0 )); then
            info "  No failures — ${pending} still pending"
        else
            info "  All checks passed!"
        fi
        return
    fi

    # Log each failed check by name
    echo "$checks_json" | jq -r '.[] | select(.bucket == "fail") | "  FAILED: \(.name)"' | while read -r line; do
        warn "$line"
    done

    # Extract unique run IDs from the failed check links
    local run_ids
    run_ids=$(echo "$checks_json" | jq -r '.[] | select(.bucket == "fail") | .link' \
        | grep -oE '/actions/runs/[0-9]+' \
        | grep -oE '[0-9]+' \
        | sort -u || true)

    if [[ -z "$run_ids" ]]; then
        warn "  Could not extract run IDs from failed checks"
        return
    fi

    # Track all failed run IDs for retry cleanup
    ALL_FAILED_RUN_IDS+=" $run_ids"

    for run_id in $run_ids; do
        local retries
        retries=$(retry_get_count "$run_id")

        if (( retries >= MAX_RETRIES )); then
            warn "  Run ${run_id} has been retried ${retries}/${MAX_RETRIES} times — giving up"
            continue
        fi

        if cache_key_fresh "$run_id"; then
            skip "  Run ${run_id} was rerun recently — waiting for it to finish (retry ${retries}/${MAX_RETRIES})"
            continue
        fi

        if [[ "$DRY_RUN" == true ]]; then
            act "[DRY RUN] Would rerun failed jobs in run ${run_id} (retry $((retries + 1))/${MAX_RETRIES})"
        else
            act "Rerunning failed jobs in run ${run_id} (retry $((retries + 1))/${MAX_RETRIES})"
            if gh run rerun "$run_id" --failed $REPO_FLAG 2>/dev/null; then
                info "  Rerun triggered successfully"
                retry_increment "$run_id"
            else
                warn "  Rerun command failed for run ${run_id}"
                continue
            fi
        fi
        cache_mark "$run_id"
    done
}

register_new_pr() {
    local pr_number="$1"
    local pr_title="$2"

    config_set "$pr_number" true "$pr_title"
    info "New PR detected: #${pr_number} — ${pr_title} (auto-enabled)"
}

poll() {
    ALL_FAILED_RUN_IDS=""
    info "========================================="
    info "Polling..."
    if [[ "$DRY_RUN" == true ]]; then
        info "(DRY RUN mode — no reruns will be triggered)"
    fi

    local prs_json
    prs_json=$(gh pr list --author @me --state open $REPO_FLAG --json number,title 2>/dev/null | extract_json) || {
        warn "Could not list PRs"
        return
    }

    if [[ -z "$prs_json" ]]; then
        warn "No PR data returned"
        return
    fi

    local pr_count
    pr_count=$(echo "$prs_json" | jq 'length')

    if (( pr_count == 0 )); then
        info "No open PRs found"
        return
    fi

    info "Found ${pr_count} open PR(s)"

    config_remove_closed "$prs_json"

    local enabled_count=0
    local number title
    while read -r pr; do
        number=$(echo "$pr" | jq -r '.number')
        title=$(echo "$pr" | jq -r '.title')

        local status
        status=$(config_get_enabled "$number")

        if [[ "$status" == "unknown" ]]; then
            register_new_pr "$number" "$title"
            status="true"
        else
            # Update title only if it changed
            local current_title
            current_title=$(config_read | jq -r --arg pr "$number" '.prs[$pr].title // ""')
            if [[ "$current_title" != "$title" ]]; then
                local current
                current=$(config_read)
                config_write "$(echo "$current" | jq --arg pr "$number" --arg title "$title" '.prs[$pr].title = $title')"
            fi
        fi

        if [[ "$status" == "true" ]]; then
            process_pr "$number" "$title"
            enabled_count=$((enabled_count + 1))
            echo ""
        else
            skip "PR #${number}: auto-rerun disabled"
        fi
    done < <(echo "$prs_json" | jq -c '.[]')

    if (( enabled_count == 0 )); then
        info "No enabled PRs to check"
    fi

    # Clean up retry counts for runs no longer failing
    local active_ids
    active_ids=$(echo "$ALL_FAILED_RUN_IDS" | tr ' ' '\n' | sort -u | grep -v '^$' || true)
    retry_cleanup "$active_ids"
}

# ---------------------------------------------------------------------------
# Interruptible sleep — listens for keypresses while waiting
# ---------------------------------------------------------------------------
wait_for_next_poll() {
    local remaining=$INTERVAL

    while (( remaining > 0 )); do
        local mins=$(( remaining / 60 ))
        local secs=$(( remaining % 60 ))
        printf "\r[$(date '+%H:%M:%S')] Next poll in %d:%02d — 'e' edit PRs | 's' settings | 'q' quit  " "$mins" "$secs"

        local key=""
        if read -rsn1 -t1 key < /dev/tty 2>/dev/null; then
            case "$key" in
                e|E)
                    printf "\n"
                    edit_prs
                    ;;
                s|S)
                    printf "\n"
                    edit_settings
                    # Interval may have changed — restart countdown
                    remaining=$INTERVAL
                    ;;
                q|Q)
                    printf "\n"
                    info "Quitting..."
                    exit 0
                    ;;
            esac
        fi
        remaining=$((remaining - 1))
    done
    printf "\n"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
main() {
    local cli_all_checks=$ALL_CHECKS
    local cli_interval=$INTERVAL
    load_settings
    # CLI flags win over persisted settings
    if [[ "$cli_all_checks" == true ]]; then ALL_CHECKS=true; fi
    if [[ "$INTERVAL_SET" == true ]]; then INTERVAL="$cli_interval"; fi

    echo ""
    info "Starting rerun-failed-checks"
    info "  Mode:     $(if $DRY_RUN; then echo 'DRY RUN'; else echo 'LIVE'; fi)"
    info "  Checks:   $(if $ALL_CHECKS; then echo 'all'; else echo 'required only'; fi)"
    info "  Max retries: ${MAX_RETRIES}"
    info "  Interval: ${INTERVAL}s"
    info "  Repo:     ${REPO:-<current>}"
    info "  Config:   ${CONFIG_FILE}"
    echo ""
    info "Hotkeys:  e = edit PRs  |  s = settings  |  q = quit"
    echo ""

    while true; do
        poll
        wait_for_next_poll
    done
}

main
