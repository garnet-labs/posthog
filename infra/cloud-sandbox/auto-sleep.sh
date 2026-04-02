#!/usr/bin/env bash
#
# Auto-sleep cron script for cloud sandboxes.
# Runs every 10 minutes via cron. If no SSH sessions exist for 2 hours,
# gracefully stops docker compose and shuts down the instance.
#
# EBS persists across stop/start, so waking back up is cheap (~1-2 min).
#
set -euo pipefail

MARKER="/tmp/sandbox-no-sessions"
IDLE_THRESHOLD=7200  # 2 hours in seconds

# Count active SSH sessions (excluding the cron's own SSH, if any)
SESSION_COUNT=$(who | grep -v "^$" | wc -l)

if [ "$SESSION_COUNT" -gt 0 ]; then
    # Someone is connected - remove the idle marker
    rm -f "$MARKER"
    exit 0
fi

# No sessions - check how long we've been idle
if [ ! -f "$MARKER" ]; then
    # First time seeing no sessions - start the clock
    date +%s > "$MARKER"
    exit 0
fi

IDLE_SINCE=$(cat "$MARKER")
NOW=$(date +%s)
IDLE_SECONDS=$((NOW - IDLE_SINCE))

if [ "$IDLE_SECONDS" -lt "$IDLE_THRESHOLD" ]; then
    # Not idle long enough yet
    exit 0
fi

# Idle for too long - shut down
echo "$(date): No SSH sessions for ${IDLE_SECONDS}s, shutting down..." >> /var/log/sandbox-auto-sleep.log

# Graceful docker compose stop
cd /home/ubuntu/posthog
sudo -u ubuntu docker compose -f docker-compose.sandbox.yml stop 2>/dev/null || true

rm -f "$MARKER"
shutdown -h now
