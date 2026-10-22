#!/bin/bash
# Smart Flow Agent - install/update inside the LXC (run as root INSIDE the container).
# Expects the bundle at /tmp/smartflow.tgz. Idempotent: re-running updates code and restarts the services.
# Usage: install_ct.sh <expected-hostname> [all|api]   (api = restart only the API, leave the paper agents running)
set -euo pipefail
EXPECTED_HOST="${1:-botstrike}"
ONLY="${2:-all}"
[ "$(hostname)" = "$EXPECTED_HOST" ] || { echo "refusing: hostname is $(hostname), expected $EXPECTED_HOST"; exit 1; }

if ! python3 -c "import venv, ensurepip" 2>/dev/null; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv >/dev/null
fi
id smartflow >/dev/null 2>&1 || useradd --system --home-dir /opt/smartflow --shell /usr/sbin/nologin smartflow

APP=/opt/smartflow/app
mkdir -p "$APP"
# keep runtime state across updates
tar --no-same-owner -xzf /tmp/smartflow.tgz -C "$APP"
mkdir -p "$APP/runs" "$APP/data"
[ -d "$APP/.venv" ] || python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -e "$APP[dev]"
chown -R smartflow:smartflow /opt/smartflow
chmod 750 /opt/smartflow "$APP"

echo "--- tests (as smartflow)"
runuser -u smartflow -- bash -c "cd $APP && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests 2>&1 | tail -2"

install -m 644 "$APP/deploy/smartflow-paper@.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-data.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-data.timer" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-api.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-push.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-push-qa.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-news.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-copy.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-fleet.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-fleet-mainnet.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-backup.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-backup.timer" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-watchdog.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-watchdog.timer" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-health.service" /etc/systemd/system/
install -m 644 "$APP/deploy/smartflow-health.timer" /etc/systemd/system/
install -d -o smartflow -g smartflow -m 750 /var/backups/smartflow   # the audit trail, every day (90 days)
systemctl daemon-reload
systemctl enable --now smartflow-data.timer
systemctl enable --now smartflow-backup.timer
# alerts to the operator's phone: /etc/smartflow/alert.env (SMARTFLOW_ALERT_WEBHOOK=...), written from the operator's
# PC (docs/08 "Alertas"); without it everything runs the same and nothing is sent
[ -f /etc/smartflow/alert.env ] && { chown root:smartflow /etc/smartflow/alert.env; chmod 640 /etc/smartflow/alert.env; }
systemctl enable --now smartflow-watchdog.timer
systemctl enable --now smartflow-health.timer
# the official paper agent of every strategy of the registry (config/strategies.json), then the internal variants
PAPER=$(runuser -u smartflow -- "$APP/.venv/bin/python" -c "from smartflow.live.watchdog import paper_agents; print(' '.join(paper_agents()))")
echo "paper agents: $PAPER"
for i in $PAPER; do
  systemctl enable "smartflow-paper@$i" >/dev/null 2>&1
  [ "$ONLY" = "api" ] || systemctl restart "smartflow-paper@$i"
done
systemctl enable smartflow-api >/dev/null 2>&1
systemctl restart smartflow-api
if [ -f /etc/smartflow/push.env ]; then   # created once from the operator's PC (docs/08), never in the bundle
  systemctl enable smartflow-push >/dev/null 2>&1
  systemctl restart smartflow-push
fi
if [ -f /etc/smartflow/push-qa.env ]; then   # the QA site (testnet world) also shows the official agents
  systemctl enable smartflow-push-qa >/dev/null 2>&1
  systemctl restart smartflow-push-qa
fi
# users' agents (builder connect): encrypted key pool + its master key, created here once and never overwritten
install -d -o smartflow -g smartflow -m 700 /var/lib/smartflow /var/lib/smartflow/keys
install -d -o root -g smartflow -m 750 /etc/smartflow
if [ ! -f /etc/smartflow/keys.key ]; then
  (umask 027; python3 -c "import os; print(os.urandom(32).hex())" > /etc/smartflow/keys.key)
  chown root:smartflow /etc/smartflow/keys.key; chmod 640 /etc/smartflow/keys.key
fi
# the News Tower's data (never touches the agents); its model key, if any, in /etc/smartflow/news.env (docs/08)
install -d -o smartflow -g smartflow -m 750 /var/lib/smartflow/news
[ -f /etc/smartflow/news.env ] && { chown root:smartflow /etc/smartflow/news.env; chmod 640 /etc/smartflow/news.env; }
systemctl enable smartflow-news >/dev/null 2>&1
systemctl restart smartflow-news
# Strike's copy trading for the Copy Arena (public data only, never touches the agents)
install -d -o smartflow -g smartflow -m 750 /var/lib/smartflow/copy
systemctl enable smartflow-copy >/dev/null 2>&1
systemctl restart smartflow-copy
if [ -f /etc/smartflow/fleet.env ]; then   # site URL + secret + SMARTFLOW_LIVE_ACK, written from the operator's PC
  systemctl enable smartflow-fleet >/dev/null 2>&1
  systemctl restart smartflow-fleet
fi
# real money: only with its own settings file, written on purpose when Edgar switches mainnet on (docs/08)
if [ -f /etc/smartflow/fleet-mainnet.env ]; then
  systemctl enable smartflow-fleet-mainnet >/dev/null 2>&1
  systemctl restart smartflow-fleet-mainnet
else
  systemctl disable --now smartflow-fleet-mainnet >/dev/null 2>&1 || true
fi
sleep 20
systemctl --no-pager --lines=0 status $(for i in $PAPER; do echo "smartflow-paper@$i"; done) smartflow-api smartflow-push smartflow-push-qa smartflow-news smartflow-copy smartflow-fleet smartflow-fleet-mainnet | grep -E "Loaded|Active|Main PID|Memory"
echo "--- push"
journalctl -u smartflow-push -n 3 --no-pager | cut -c1-200
echo "--- news"
journalctl -u smartflow-news -n 2 --no-pager | cut -c1-200
echo "--- fleet"
journalctl -u smartflow-fleet -n 3 --no-pager | cut -c1-200
echo "--- api"
curl -s -m 5 http://127.0.0.1:8787/api/health; echo
echo "--- last log lines"
journalctl -u smartflow-paper@recommended -n 4 --no-pager | cut -c1-200
echo "--- timers"
systemctl list-timers --no-pager 'smartflow-*' 2>/dev/null | head -8 || true
echo "--- alerts: $([ -f /etc/smartflow/alert.env ] && echo configured || echo 'not configured (/etc/smartflow/alert.env)')"
echo "--- botstrike untouched:"; systemctl is-active botstrike-bridge.service
