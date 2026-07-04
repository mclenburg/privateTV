#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root: sudo scripts/install-systemd.sh" >&2
  exit 1
fi

install -d -m 0755 /etc/systemd/system
install -m 0644 packaging/systemd/privatetv.service /etc/systemd/system/privatetv.service
install -m 0644 packaging/systemd/privatetv-scan.service /etc/systemd/system/privatetv-scan.service
install -m 0644 packaging/systemd/privatetv-scan.timer /etc/systemd/system/privatetv-scan.timer
install -m 0644 packaging/systemd/privatetv-schedule.service /etc/systemd/system/privatetv-schedule.service
install -m 0644 packaging/systemd/privatetv-schedule.timer /etc/systemd/system/privatetv-schedule.timer

systemctl daemon-reload
systemctl enable privatetv-scan.timer privatetv-schedule.timer

echo "Installed PrivateTV systemd units."
echo "Start service with: sudo systemctl start privatetv.service"
