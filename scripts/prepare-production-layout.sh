#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root: sudo scripts/prepare-production-layout.sh" >&2
  exit 1
fi

if ! id privatetv >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/privatetv --shell /usr/sbin/nologin privatetv
fi

install -d -m 0750 -o privatetv -g privatetv /var/lib/privatetv
install -d -m 0750 -o root -g privatetv /etc/privatetv

if [[ ! -f /etc/privatetv/config.yml ]]; then
  install -m 0640 -o root -g privatetv config/privatetv.example.yml /etc/privatetv/config.yml
fi

echo "Prepared /etc/privatetv and /var/lib/privatetv."
echo "Review /etc/privatetv/config.yml before starting the service."
