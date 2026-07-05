# PrivateTV

PrivateTV turns a local media library into a private linear TV channel for tvheadend.

Remember switching on the TV without choosing anything first? No endless menus, no decision fatigue, no "what should we watch tonight". Just switch on and join whatever is already on.

PrivateTV brings that feeling back with your own movie collection. It scans videos and DVD folder structures on your disk, builds a real linear programme schedule, exposes proper XMLTV EPG data, and streams the currently scheduled movie at the position where it should be according to the clock. Tune in at 20:42 and you are already 27 minutes into the film, just like broadcast TV.

PrivateTV is designed for Raspberry Pi OS and Debian-like systems. Version 1.0 focuses on local media files and DVD file structures. The architecture keeps future media providers, such as browser-based streaming service integrations, separate from the local file implementation.

## Current status

PrivateTV is under active development. The current implementation provides:

- project packaging and CLI entry point
- YAML configuration loading
- SQLite database schema
- recursive scanning of multiple media directories
- local video file import
- `VIDEO_TS` / DVD structure detection
- logical DVD main-title import based on the largest VOB title set
- automatic schedule maintenance with a 3-day minimum and 5-day target horizon
- a 5-day schedule builder
- `shuffle_no_repeat` and `alphabetical` schedule strategies
- production-oriented XMLTV rendering from the stored schedule
- M3U playlist rendering with stable tvheadend channel metadata
- built-in sender logos for PrivateTV and Hazard TV, served by the HTTP service and referenced from the M3U
- HTTP endpoints for `/health`, `/playlist.m3u`, `/xmltv.xml`, and `/stream/main.ts`
- per-client FFmpeg streaming with clock-based seek offset
- startup hardening for empty or broken FFmpeg streams
- stream limit enforcement for concurrent viewers
- systemd unit templates and production layout helper scripts
- optional Hazard TV random channel streaming without EPG
- optional broadcast-style program blocks with local filler clips and generated countdowns
- built-in web configuration page with server-side media directory browsing
- test fixtures and unit tests


## Detailed Raspberry Pi installation guides

For a real Raspberry Pi OS Trixie installation, use the dedicated guides instead of relying on the short quickstart alone:

- [Raspberry Pi OS Trixie installation](docs/INSTALL_RASPBERRY_PI_OS_TRIXIE.md)
- [Configuration reference](docs/CONFIGURATION.md)
- [tvheadend integration](docs/TVHEADEND.md)
- [Docker installation](docs/DOCKER.md)

These guides cover Python/venv setup, absolute database paths, systemd ownership, media scans, XMLTV, tvheadend, Kodi playback diagnosis, optional program blocks, generated countdowns, and local filler clips.

## Requirements

- Python 3.11 or newer
- FFmpeg and ffprobe
- Raspberry Pi OS, Debian, Ubuntu, or a comparable Linux system

Install system packages on Raspberry Pi OS / Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ffmpeg sqlite3 curl
```


## Docker quickstart

PrivateTV can also run as a container. The image contains PrivateTV, Python, FFmpeg, and ffprobe. Configuration, media directories, SQLite state, and generated countdown clips stay outside the container image.

```bash
docker compose up --build -d
docker compose exec privatetv privatetv doctor --config /config/config.yml
docker compose exec privatetv privatetv scan --config /config/config.yml
docker compose exec privatetv privatetv schedule --config /config/config.yml
```

See [Docker installation](docs/DOCKER.md) for volume layout, real media folders, tvheadend URLs, and permission notes.

## Installation for local use

From the repository root:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e '.[dev]'
```

## Production layout on Raspberry Pi OS

The repository includes systemd templates for a typical Raspberry Pi OS installation.
They assume:

- application checkout: `/opt/privatetv`
- virtual environment: `/opt/privatetv/.venv`
- configuration: `/etc/privatetv/config.yml`
- database and runtime state: `/var/lib/privatetv`
- media root: `/srv/media`
- service user: `privatetv`

Prepare the service user and directories:

```bash
sudo scripts/prepare-production-layout.sh
```

Install the systemd units:

```bash
sudo scripts/install-systemd.sh
```

Then start the service and open the web configuration page:

```bash
sudo systemctl start privatetv.service
sudo systemctl status privatetv.service
```

Open the configuration UI in a browser:

```text
http://<raspberry-pi>:9988/
```

The media directory browser in the UI selects paths on the PrivateTV server, not files or folders from the browser client.

Security note: the built-in configuration UI is intended for a trusted LAN only. Do not expose the PrivateTV HTTP service through router port forwarding or a public reverse proxy without adding an authentication layer in front of it. The configuration UI can change server-side paths and persist the YAML configuration.

Enable the main service after the configuration is verified:

```bash
sudo systemctl enable privatetv.service
```

## Configuration

PrivateTV can be configured through the built-in web page once the HTTP service is running:

```text
http://127.0.0.1:9988/
http://127.0.0.1:9988/config
```

The configuration page edits the YAML file that was passed to `privatetv serve --config ...`. Media directories are selected from the server filesystem. This is important when you administer PrivateTV from a laptop: the browser never uploads local client paths; it asks the Raspberry Pi to browse its own directories.

Example configuration:

```bash
config/privatetv.example.yml
```

Important sections:

```yaml
media:
  directories:
    - "tests/fixtures/media"
  recursive: true

schedule:
  minimum_days_ahead: 3
  days_ahead: 5
  timezone: "Europe/Berlin"
  strategy: "shuffle_no_repeat"
```

PrivateTV scans all configured media directories recursively. Subdirectories do not need to be listed separately.

### Optional program blocks, fillers, and countdowns

PrivateTV uses the continuous legacy scheduler by default: one enabled media item follows the next one and no filler clips are required. Program blocks are disabled by default. When enabled, PrivateTV can bridge the gap before an anchor such as 20:15 with short local filler clips and then use the generated countdown only for the final fine adjustment.

```yaml
program_blocks:
  enabled: false
  anchors:
    - enabled: false
      time: "20:15"
      title: "Der 20:15 Film"
      allowed_tags:
        - "movie"
  fillers:
    enabled: false
    directories:
      - "/data/PrivateTV/Filler"
      - "/data/PrivateTV/Werbung"
      - "/data/PrivateTV/Bumper"
    max_duration_seconds: 900
    distribution: "anchor_bridge"  # or "between_programmes"
    insert_between_movies: false
    max_consecutive_fillers: 3
    max_total_filler_block_seconds: 120
    prefer_filler_after_minutes: 45
    min_gap_between_filler_blocks_minutes: 20
    if_no_filler: "continue_current_mode"
  generated_countdown:
    enabled: false
    max_duration_seconds: 60
    title: "Gleich geht's weiter"
```

Generated countdowns are intentionally limited to at most 60 seconds. Longer gaps must be filled by normal programming or configured filler media, not by an endless countdown. Filler directories are scanned as short local clips with `media_type: filler`; they are not scheduled as normal movies. `distribution: "anchor_bridge"` keeps the simple bridge-before-anchor behavior. `distribution: "between_programmes"` with `insert_between_movies: true` lets PrivateTV place short ad/bumper/trailer blocks between normal programmes, bounded by `max_consecutive_fillers` and `max_total_filler_block_seconds`, so old commercials or DVD previews do not pile up as one long wall before 20:15.

## Test fixtures

Create small local fixture files:

```bash
scripts/create_test_fixtures.sh
```

The script creates a few tiny MP4 files and a minimal `VIDEO_TS`-like directory. These files are only fixtures for scanner and scheduling tests; they are not meant to be a fully authored DVD.

## Scanning media

Run a scan:

```bash
privatetv scan --config config/privatetv.example.yml
```

List imported media:

```bash
privatetv list-media --config config/privatetv.example.yml
```

DVD structures are imported as one logical media item. PrivateTV does not import each VOB part as a separate movie.

## Building the schedule

Build or extend the channel timeline:

```bash
privatetv schedule --config config/privatetv.example.yml
```

PrivateTV keeps the stored programme guide long enough for tvheadend. By default, the schedule must always reach at least 3 days into the future. Whenever it falls below that minimum, PrivateTV extends it up to the 5-day target horizon. The same maintenance logic is used by the `schedule` command and by XMLTV generation.

You can run the explicit maintenance command as well:

```bash
privatetv maintain-schedule --config config/privatetv.example.yml
```

Show the programme that is currently scheduled:

```bash
privatetv current --config config/privatetv.example.yml
```

Generate XMLTV output from the stored schedule:

```bash
privatetv xmltv --config config/privatetv.example.yml
```

Generate the M3U playlist for tvheadend:

```bash
privatetv m3u --config config/privatetv.example.yml
```

The default strategy is `shuffle_no_repeat`: all enabled titles are shuffled, and each title is used once before the next shuffled cycle starts. The `alphabetical` strategy is available for deterministic testing and debugging.

If `channel.icon` or `hazard_channel.icon` is left empty, PrivateTV automatically uses the built-in logo assets that are served by the PrivateTV HTTP service.

## Running the HTTP service

Start the local PrivateTV HTTP service:

```bash
privatetv serve --config config/privatetv.example.yml
```

The service opens the configuration page at `http://127.0.0.1:9988/` and exposes:

- `http://127.0.0.1:9988/config`
- `http://127.0.0.1:9988/config/browse`
- `http://127.0.0.1:9988/health`
- `http://127.0.0.1:9988/logos/privatetv.png`
- `http://127.0.0.1:9988/logos/hazardtv.png`
- `http://127.0.0.1:9988/playlist.m3u`
- `http://127.0.0.1:9988/xmltv.xml`
- `http://127.0.0.1:9988/stream/main.ts`
- `http://127.0.0.1:9988/stream/hazard.ts` when Hazard TV is enabled

The stream endpoint starts FFmpeg for the currently scheduled programme, seeks to the clock-based offset, and returns an MPEG-TS stream. With stream-copy mode, seek accuracy depends on source keyframes; PrivateTV documents this as an accepted tolerance for version 1.0 rather than pretending to be frame-accurate broadcast automation.

## Hazard TV

PrivateTV can expose an optional second M3U channel called **Hazard TV**. It is deliberately different from the scheduled main channel:

- no XMLTV schedule
- no prebuilt playlist
- each tune-in starts a random library title from the beginning
- after that title ends, the next title is chosen randomly
- immediate repeats are avoided when more than one playable title exists
- Hazard TV streams count against the same global `streaming.max_parallel_streams` limit as the main channel

Enable it in the configuration:

```yaml
hazard_channel:
  enabled: true
  id: "hazardtv"
  name: "Hazard TV"
  random_seed: 20260704
  avoid_immediate_repeat: true
```

When enabled, `/playlist.m3u` contains both the scheduled PrivateTV channel and Hazard TV. XMLTV remains limited to the scheduled main channel.

## tvheadend integration target

The tvheadend integration target uses:

- `/playlist.m3u` for the IPTV channel definition
- `/xmltv.xml` for EPG data
- `/stream/main.ts` for the scheduled MPEG-TS stream
- `/stream/hazard.ts` for the optional Hazard TV random stream

The M3U playlist contains a stable stream URL and an `url-tvg` reference to the XMLTV URL. XMLTV programme timestamps are formatted with the configured time zone, including daylight-saving transitions such as Europe/Berlin changing between `+0100` and `+0200`. The stream endpoint serves MPEG-TS through FFmpeg and is intended to be consumed by tvheadend as a normal IPTV mux.

## Security notice

PrivateTV is designed for LAN use in version 1.0. The web configuration page can change server paths and service settings. Do not expose the HTTP endpoints to the internet through port forwarding unless a reverse proxy with proper authentication and access control is placed in front of it.

## License

See the `LICENSE` file in this repository.


## Diagnostics and technical spikes

PrivateTV includes a few diagnostic commands for integration risks that are typical for local IPTV playback:

```bash
privatetv spike-seek --config config/privatetv.example.yml
privatetv spike-dvd-concat --config config/privatetv.example.yml /path/to/VTS_01_1.VOB /path/to/VTS_01_2.VOB
privatetv spike-tvh-upstream --host 0.0.0.0 --port 9998
```

`spike-seek` documents the accepted V1.0 behavior for fast stream-copy seeking. Startup may be keyframe-aligned rather than frame-exact.

`spike-dvd-concat` builds DVD VOB concat candidate commands and can optionally execute them against real VOB files.

`spike-tvh-upstream` starts a small probe server so you can verify whether tvheadend opens one or multiple upstream connections when several clients watch the same IPTV channel.

Logo overlays inside the actual video stream are intentionally not enabled by default. Overlaying a channel logo would force video filtering and re-encoding, which would defeat the current low-overhead stream-copy design and reduce the number of reliable parallel streams on a Raspberry Pi.
