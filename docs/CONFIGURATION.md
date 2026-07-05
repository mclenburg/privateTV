# PrivateTV configuration reference

The production configuration is normally stored at:

```text
/etc/privatetv/config.yml
```

The example file is:

```text
config/privatetv.example.yml
```

## Minimal production configuration

```yaml
server:
  host: "0.0.0.0"
  port: 9988
  public_base_url: "http://192.168.5.116:9988"

channel:
  id: "privatetv"
  name: "PrivateTV"
  icon: ""
  group_title: "Local"
  language: "de"

hazard_channel:
  enabled: false
  id: "hazardtv"
  name: "Hazard TV"
  icon: ""
  group_title: "Local"
  language: "de"
  random_seed: 20260704
  avoid_immediate_repeat: true

media:
  directories:
    - "/data/Filme"
    - "/data/DVDs"
  recursive: true
  follow_symlinks: false
  ignore_hidden_directories: true
  extensions:
    - ".avi"
    - ".mpg"
    - ".mpeg"
    - ".mp4"
    - ".mkv"
    - ".ts"
    - ".vob"
  dvd:
    enabled: true
    detect_video_ts: true
    main_title_strategy: "largest_titleset"
    min_main_title_size_mb: 500
    min_main_title_duration_seconds: 1200

schedule:
  minimum_days_ahead: 3
  days_ahead: 5
  timezone: "Europe/Berlin"
  rebuild_hour: 3
  strategy: "shuffle_no_repeat"
  random_seed: 20260704

streaming:
  max_parallel_streams: 4
  output_container: "mpegts"
  prefer_stream_copy: true
  transcode_when_needed: false
  ffmpeg_path: "/usr/bin/ffmpeg"
  ffprobe_path: "/usr/bin/ffprobe"
  accepted_seek_tolerance_seconds: 10

database:
  path: "/var/lib/privatetv/privatetv.sqlite3"

logging:
  level: "INFO"

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
    directories: []
    max_duration_seconds: 900
    if_no_filler: "continue_current_mode"
  generated_countdown:
    enabled: false
    max_duration_seconds: 60
    title: "Gleich geht's weiter"
```

## server

```yaml
server:
  host: "0.0.0.0"
  port: 9988
  public_base_url: "http://192.168.5.116:9988"
```

`host` controls where the HTTP service listens. Use `0.0.0.0` when tvheadend or a browser on another machine should reach PrivateTV.

`public_base_url` is written into M3U and XMLTV-related links. Use a URL that tvheadend can reach. If tvheadend runs on the same Pi, `http://127.0.0.1:9988` works for local-only integration. If other devices use the playlist directly, use the Pi's LAN IP or hostname.

## channel

```yaml
channel:
  id: "privatetv"
  name: "PrivateTV"
  icon: ""
  group_title: "Local"
  language: "de"
```

The `id` must match the XMLTV channel and the M3U `tvg-id`. Keep it stable after tvheadend has mapped the channel.

If `icon` is empty, PrivateTV uses the built-in logo.

## hazard_channel

Hazard TV is an optional second channel.

```yaml
hazard_channel:
  enabled: true
```

When enabled, it appears in the M3U but not in XMLTV. Every tune-in starts a random media item from the beginning and continues randomly. Hazard TV uses the same global stream limit as the main channel.

## media

`media.directories` lists server-side directories. They are paths on the Raspberry Pi, not on the laptop used to open the web UI.

```yaml
media:
  directories:
    - "/data/Filme"
    - "/data/DVDs"
```

DVD handling:

```yaml
media:
  dvd:
    enabled: true
    detect_video_ts: true
    main_title_strategy: "largest_titleset"
```

PrivateTV detects common DVD structures and tries to import the main title as one logical item instead of scheduling every VOB as a separate film. For DVD-like names such as `VTS_01_2.VOB`, PrivateTV derives a friendlier title from the nearest meaningful parent directory.

Title cleanup replaces underscores with spaces and inserts word boundaries in CamelCase names where possible.

## schedule

```yaml
schedule:
  minimum_days_ahead: 3
  days_ahead: 5
  timezone: "Europe/Berlin"
  strategy: "shuffle_no_repeat"
```

PrivateTV stores a real timeline in SQLite. By default, it keeps at least 3 days of future schedule and extends up to 5 days.

The timeline survives restarts because it is stored in `/var/lib/privatetv/privatetv.sqlite3`.

## streaming

```yaml
streaming:
  max_parallel_streams: 4
  prefer_stream_copy: true
  transcode_when_needed: false
```

PrivateTV normally uses FFmpeg stream copy and outputs MPEG-TS. This is lightweight and suitable for Raspberry Pi use.

Seek accuracy depends on source keyframes. PrivateTV starts at the clock-based offset, but the first decoded frame may be near the requested position rather than frame-perfect.

## database

Use an absolute path:

```yaml
database:
  path: "/var/lib/privatetv/privatetv.sqlite3"
```

The systemd service user must be able to write this directory and file:

```bash
sudo chown -R privatetv:privatetv /var/lib/privatetv
```

## program_blocks

Program blocks are optional and disabled by default.

```yaml
program_blocks:
  enabled: false
```

When disabled, PrivateTV behaves like the original continuous scheduler: one normal media item follows the next.

### 20:15 anchor with countdown and fillers

Example:

```yaml
program_blocks:
  enabled: true
  anchors:
    - enabled: true
      time: "20:15"
      title: "Der 20:15 Film"
      allowed_tags:
        - "movie"
  fillers:
    enabled: true
    directories:
      - "/data/PrivateTV/Filler"
      - "/data/PrivateTV/Werbung"
      - "/data/PrivateTV/Bumper"
    max_duration_seconds: 900
    # anchor_bridge keeps the simple patch-20 behavior.
    # between_programmes spreads short clips between normal programmes.
    distribution: "between_programmes"
    insert_between_movies: true
    max_consecutive_fillers: 3
    max_total_filler_block_seconds: 120
    prefer_filler_after_minutes: 45
    min_gap_between_filler_blocks_minutes: 20
    if_no_filler: "continue_current_mode"
  generated_countdown:
    enabled: true
    max_duration_seconds: 60
    title: "Gleich geht's weiter"
```

Rules:

- Existing behavior remains the default.
- Filler clips are not part of the normal movie rotation.
- With `distribution: "anchor_bridge"`, fillers are used only when a configured anchor would otherwise be crossed by the next normal item.
- With `distribution: "between_programmes"` and `insert_between_movies: true`, short filler blocks can also be placed between normal programmes so the remaining time before an anchor is split into smaller, TV-like breaks.
- `max_consecutive_fillers` and `max_total_filler_block_seconds` prevent long walls of commercials/trailers.
- The generated countdown is only for final fine adjustment.
- The generated countdown must never be longer than 60 seconds.
- If no fitting filler exists and the gap is longer than the countdown limit, `continue_current_mode` keeps the old film-after-film behavior.

A useful folder layout is:

```text
/data/PrivateTV/Filler
/data/PrivateTV/Werbung
/data/PrivateTV/Trailer
/data/PrivateTV/Bumper
/data/PrivateTV/DVD-Vorschauen
```

Add those folders to `program_blocks.fillers.directories` when you have local clips ready.

## logging

```yaml
logging:
  level: "INFO"
```

Use `DEBUG` only temporarily. Scans and streams can become noisy.

