# PrivateTV installation on Raspberry Pi OS Trixie

This guide describes a clean production-style installation on Raspberry Pi OS Trixie. It assumes that PrivateTV is installed on the same Raspberry Pi as tvheadend, but it also works if tvheadend runs elsewhere.

## 1. Requirements

Use Raspberry Pi OS Trixie or another Debian-like system with Python 3.11 or newer.

Check the system:

```bash
cat /etc/os-release
python3 --version
```

PrivateTV requires:

- Python 3.11 or newer
- FFmpeg and ffprobe
- SQLite
- a writable state directory, normally `/var/lib/privatetv`
- readable media directories, for example `/data/Filme` and `/data/DVDs`

Install packages:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip ffmpeg sqlite3 curl unzip
```

Check FFmpeg:

```bash
ffmpeg -version | head -1
ffprobe -version | head -1
```

## 2. Clone the repository

Recommended production path:

```bash
cd /opt
sudo git clone <REPOSITORY-URL> privatetv
cd /opt/privatetv
```

If the checkout is named `privateTV`, rename it to match the systemd templates:

```bash
cd /opt
sudo mv privateTV privatetv
cd /opt/privatetv
```

## 3. Create the Python virtual environment

Create and activate the venv:

```bash
cd /opt/privatetv
python3 -m venv .venv
. .venv/bin/activate
```

Upgrade packaging tools first. This is important on Raspberry Pi OS images that ship an older pip/setuptools combination:

```bash
python -m pip install --upgrade pip setuptools wheel
```

Install PrivateTV:

```bash
pip install -e .
```

For development and tests:

```bash
pip install -e '.[dev]'
```

Check the CLI:

```bash
privatetv --version
```

## 4. Prepare production directories and user

PrivateTV's systemd units use the `privatetv` service user.

```bash
cd /opt/privatetv
sudo scripts/prepare-production-layout.sh
```

The expected layout is:

```text
/opt/privatetv                 application checkout
/opt/privatetv/.venv           Python virtual environment
/etc/privatetv/config.yml      production configuration
/var/lib/privatetv             database and generated runtime files
```

Ensure the service user can read the checkout and write the state directory:

```bash
sudo chmod -R a+rX /opt/privatetv
sudo chown -R privatetv:privatetv /var/lib/privatetv
```

## 5. Create the production configuration

Copy the example configuration:

```bash
sudo mkdir -p /etc/privatetv
sudo cp /opt/privatetv/config/privatetv.example.yml /etc/privatetv/config.yml
sudo nano /etc/privatetv/config.yml
```

At minimum, adjust these values:

```yaml
server:
  host: "0.0.0.0"
  port: 9988
  public_base_url: "http://<IP-OF-RASPBERRY-PI>:9988"

media:
  directories:
    - "/data/Filme"
    - "/data/DVDs"

database:
  path: "/var/lib/privatetv/privatetv.sqlite3"
```

The database path must be absolute. Do not use `var/lib/privatetv/...` without the leading slash.

Check the configuration:

```bash
cd /opt/privatetv
. .venv/bin/activate
privatetv doctor --config /etc/privatetv/config.yml
```

Expected result:

```text
OK  config
OK  ffmpeg
OK  ffprobe
OK  media directory: ...
```

## 6. Initialize the database

Run the first database initialization:

```bash
privatetv init-db --config /etc/privatetv/config.yml
```

Fix ownership if you ran the command as root:

```bash
sudo chown -R privatetv:privatetv /var/lib/privatetv
```

Check the database file:

```bash
ls -lh /var/lib/privatetv/
```

## 7. Scan media

Run the media scan:

```bash
privatetv scan --config /etc/privatetv/config.yml
```

The scanner prints progress and keeps going when individual files cannot be probed. A successful scan summary looks similar to this:

```text
Scanned media items: 1456
Local files:         1448
DVD structures:      8
Imported/updated:    1451
Probe failures:       5
Marked missing:       0
```

Probe failures are usually damaged files, unsupported formats, or files that ffprobe cannot analyze. They do not stop the whole scan.

List imported media:

```bash
privatetv list-media --config /etc/privatetv/config.yml | head -40
```

## 8. Build the schedule

Create or extend the stored timeline:

```bash
privatetv schedule --config /etc/privatetv/config.yml
```

Check the current programme:

```bash
privatetv current --config /etc/privatetv/config.yml
```

The schedule is stored in the SQLite database. It survives a reboot as long as `/var/lib/privatetv/privatetv.sqlite3` is preserved.

## 9. Install and start systemd units

Install the systemd units:

```bash
cd /opt/privatetv
sudo scripts/install-systemd.sh
sudo systemctl daemon-reload
```

Start the service:

```bash
sudo systemctl start privatetv.service
sudo systemctl status privatetv.service --no-pager
```

Enable the service at boot:

```bash
sudo systemctl enable privatetv.service
```

Enable scheduled scan and schedule maintenance:

```bash
sudo systemctl enable --now privatetv-scan.timer
sudo systemctl enable --now privatetv-schedule.timer
```

Check timers:

```bash
systemctl list-timers | grep privatetv
```

## 10. Test the HTTP service

Health endpoint:

```bash
curl -s http://127.0.0.1:9988/health
```

Playlist:

```bash
curl -s http://127.0.0.1:9988/playlist.m3u | head -40
```

XMLTV:

```bash
curl -s http://127.0.0.1:9988/xmltv.xml | head -40
```

Short stream test:

```bash
timeout 30 curl -v http://127.0.0.1:9988/stream/main.ts --output /tmp/privatetv-test.ts
ffprobe -hide_banner /tmp/privatetv-test.ts
```

A valid file should show an MPEG-TS container with video and optionally audio streams.

## 11. Log commands

PrivateTV service log:

```bash
journalctl -u privatetv.service -b --no-pager | tail -120
```

Scan timer log:

```bash
journalctl -u privatetv-scan.service -b --no-pager | tail -120
```

Schedule timer log:

```bash
journalctl -u privatetv-schedule.service -b --no-pager | tail -120
```

## 12. Common installation problems

### Editable install complains about missing setup.py

Upgrade pip/setuptools/wheel inside the venv:

```bash
. /opt/privatetv/.venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e .
```

### Python version is too old

PrivateTV requires Python 3.11 or newer. Raspberry Pi OS Bullseye's default Python 3.9 is not sufficient. Use Raspberry Pi OS Trixie or install a suitable Python version.

### `Missing configuration section: channel`

The config file is incomplete. Re-copy the example config and edit it carefully:

```bash
sudo cp /opt/privatetv/config/privatetv.example.yml /etc/privatetv/config.yml
```

### Database is created in the wrong directory

Check for a missing leading slash:

```bash
grep -A2 '^database:' /etc/privatetv/config.yml
```

Correct:

```yaml
database:
  path: "/var/lib/privatetv/privatetv.sqlite3"
```

Wrong:

```yaml
database:
  path: "var/lib/privatetv/privatetv.sqlite3"
```

### `attempt to write a readonly database`

The service user cannot write the SQLite file or its directory:

```bash
sudo systemctl stop privatetv.service
sudo chown -R privatetv:privatetv /var/lib/privatetv
sudo systemctl start privatetv.service
```

### Scan fails on old non-UTF-8 filenames

Current scanner versions should not abort the whole scan. If you want to find such paths manually:

```bash
python - <<'PY'
from pathlib import Path
for root in [Path("/data/Filme"), Path("/data/DVDs")]:
    for p in root.rglob("*"):
        s = str(p)
        if any("\udc80" <= ch <= "\udcff" for ch in s):
            print(repr(s))
PY
```

