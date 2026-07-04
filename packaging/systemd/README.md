# systemd units

These units are production templates for Raspberry Pi OS and Debian-like systems.
They assume:

- application checkout: `/opt/privatetv`
- virtual environment: `/opt/privatetv/.venv`
- configuration: `/etc/privatetv/config.yml`
- runtime database: `/var/lib/privatetv/privatetv.sqlite3`
- media root: `/srv/media`
- service user and group: `privatetv`

Install the units with `sudo install -m 0644 packaging/systemd/*.service packaging/systemd/*.timer /etc/systemd/system/`, then run `sudo systemctl daemon-reload`.
