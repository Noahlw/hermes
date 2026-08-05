#!/usr/bin/env bash
# Hermes VM health check — reboot replacement for the lost vm_health.sh.
#
# Emits one line per check (digest-friendly), exits 0 when everything
# OK, 1 otherwise. Checks: Postgres :5433, Tailscale, Hermes systemd
# units that exist, disk usage.
#
# Scheduled per AGENTS.md Step 2f (upstream scheduling or systemd timer,
# daily ~06:00; formerly InProcessCronScheduler cron/jobs.json, archived).

set -u

fail=0
ok()  { printf '[health] OK   %s\n' "$1"; }
bad() { printf '[health] FAIL %s\n' "$1"; fail=1; }

# 1. Postgres 16 (hermes + codebase_index) on 127.0.0.1:5433
if command -v pg_isready >/dev/null 2>&1 && pg_isready -h 127.0.0.1 -p 5433 -q 2>/dev/null; then
  ok "postgres 127.0.0.1:5433"
else
  bad "postgres 127.0.0.1:5433"
fi

# 2. Tailscale
if command -v tailscale >/dev/null 2>&1 && tailscale status >/dev/null 2>&1; then
  ok "tailscale up"
else
  bad "tailscale"
fi

# 3. Hermes systemd units (only ones that exist; gateway/honcho land later)
for unit in hermes-indexer-webhook.service hermes-indexer-reconcile.timer \
            hermes-gateway.service honcho-api.service; do
  if [ -e "/etc/systemd/system/$unit" ] || [ -e "/usr/lib/systemd/system/$unit" ]; then
    if systemctl is-active --quiet "$unit"; then
      ok "$unit active"
    else
      bad "$unit not active"
    fi
  fi
done

# 4. Disk
used="$(df -P / | awk 'NR==2 {print $5}' | tr -d '%')"
if [ "${used:-100}" -lt 90 ]; then
  ok "disk ${used}% used"
else
  bad "disk ${used}% used (>=90%)"
fi

[ "$fail" -eq 0 ]
