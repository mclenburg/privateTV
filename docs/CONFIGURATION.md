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
  blocks:
    - enabled: false
      start: "06:00"
      duration: "02:30:00"
      title: "PrivateTV Kinderzeit"
      allowed_tags:
        - "kids"
      denied_tags:
        - "nicht_fuer_kinder"
      tag_match: "any"
      if_empty: "continue_current_mode"
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


### Time blocks

Patch 25 adds real time blocks. A block is a daily time window during which PrivateTV prefers media with matching tags. This is useful for broad slots such as kids' programming without having to over-classify every film.

Example:

```yaml
program_blocks:
  enabled: true
  blocks:
    - enabled: true
      start: "06:00"
      duration: "02:30:00"
      title: "PrivateTV Kinderzeit"
      allowed_tags:
        - "kids"
      denied_tags:
        - "nicht_fuer_kinder"
      tag_match: "any"
      if_empty: "continue_current_mode"

    - enabled: true
      start: "22:30"
      duration: "03:00:00"
      title: "Spätprogramm"
      allowed_tags:
        - "late"
        - "movie"
      denied_tags:
        - "kids"
      tag_match: "any"
      if_empty: "continue_current_mode"
```

Rules:

- Blocks are optional. With no enabled blocks, existing scheduling behavior is unchanged.
- A block does not require highly granular tags. Use broad tags such as `kids`, `family`, `late`, `movie`, `retro` or `commercial`.
- Inside a block, PrivateTV prefers matching media and tries to pick items that fit before the block ends.
- Before an upcoming block, PrivateTV avoids starting a long normal item when a shorter one can fit before the block start.
- If no matching media exists and `if_empty: "continue_current_mode"`, PrivateTV falls back to the normal rotation instead of failing.
- Anchors, such as `20:15`, remain fixed points. Blocks are wider time windows.

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


## Media tags

PrivateTV can assign tags during `privatetv scan`. Tags are stored in the SQLite database and can be used by programme anchors and filler rules.

In `/etc/privatetv/config.yml`:

```yaml
media:
  directories:
    - "/data/Filme"
    - "/data/DVDs"
  tag_file: "/etc/privatetv/tags.yml"
```

Example `/etc/privatetv/tags.yml`:

```yaml
version: 1

directory_tags:
  "/data/Filme/Kinder":
    - kids
    - family

  "/data/Filme/SimsalaGrimm":
    - kids
    - series
    - fairy_tale

  "/data/PrivateTV/Werbung":
    - filler
    - commercial
    - retro

file_tags:
  "/data/Filme/Buddy&Terence/2_Himmelhunde_auf_dem_Weg_zur_Hoelle.mp4":
    add:
      - late
      - comedy
    remove:
      - kids
```

After changing tags, run:

```bash
privatetv scan --config /etc/privatetv/config.yml
```

Inspect tags:

```bash
privatetv list-tags --config /etc/privatetv/config.yml
privatetv list-media --tag kids --config /etc/privatetv/config.yml
```

Anchors can filter by tags:

```yaml
program_blocks:
  enabled: true
  anchors:
    - enabled: true
      time: "06:00"
      title: "Kinderprogramm"
      allowed_tags:
        - kids
      denied_tags:
        - filler
      tag_match: "any"

    - enabled: true
      time: "20:15"
      title: "Der 20:15 Film"
      allowed_tags:
        - movie
      denied_tags:
        - filler
        - kids
```

`tag_match: "any"` means at least one allowed tag must match. `tag_match: "all"` requires all allowed tags.


## Program block empty behavior

For `program_blocks.blocks[]`, `if_empty` controls what happens when no media item matches the block's tag rules.

```yaml
program_blocks:
  blocks:
    - enabled: true
      start: "06:00"
      duration: "02:30:00"
      title: "PrivateTV Kinderzeit"
      allowed_tags:
        - "kids"
      if_empty: "continue_current_mode"
```

Supported values:

- `continue_current_mode`: keep the channel continuous and schedule normal rotation when the block has no matching media.
- `skip_block`: do not schedule unrelated media inside the block window. This can intentionally create an EPG/stream gap for that block.
