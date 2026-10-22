#!/bin/bash
# Daily copy of the audit trail (docs/OPERATIONS.md "Audit trail"): every agent's journal, the accounts' fills and
# readings, the site's copied rows. Kept 90 days in /var/backups/smartflow. Then every chain is checked: a broken one
# fails the unit (systemctl --failed, journalctl -u smartflow-backup). No keys live under runs/.
set -euo pipefail
cd /opt/smartflow/app
dest=/var/backups/smartflow
stamp=$(date -u +%Y%m%d)
tar -czf "$dest/runs-$stamp.tgz.part" --exclude='*.tmp' runs
mv "$dest/runs-$stamp.tgz.part" "$dest/runs-$stamp.tgz"
find "$dest" -name 'runs-*.tgz' -mtime +90 -delete
echo "backup: $dest/runs-$stamp.tgz ($(du -h "$dest/runs-$stamp.tgz" | cut -f1))"
/opt/smartflow/app/.venv/bin/smartflow audit verify --runs runs | tail -3
