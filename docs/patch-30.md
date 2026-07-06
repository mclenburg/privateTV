# Patch 30 - Series detection foundation

This patch adds the scanner foundation for scheduled series rotations.

## What is included

- New `media.series_detection` configuration section.
- Built-in automatic episode patterns for common naming styles:
  - `S01E02`
  - `1x02`
  - `Staffel 1/Folge 02`
  - `Season 1/Episode 02`
- Custom relative path patterns such as:
  - `{seriesName}/{seasonNo}/{episodeNo}_*`
- New media metadata fields:
  - `series_title`
  - `season_number`
  - `episode_number`
  - `episode_title`
  - `episode_sort_key`
- Detected episodes are stored as `media_type: episode` and receive automatic `series` and `episode` tags.
- Filler scans do not use series detection, even if a filler filename matches an episode pattern.

## Example

With media root `/data/Serien` and this pattern:

```yaml
media:
  series_detection:
    enabled: true
    auto_patterns: true
    custom_patterns:
      - name: "Serienname Staffelnummer Folgennummer"
        pattern: "{seriesName}/{seasonNo}/{episodeNo}_*"
```

This file:

```text
/data/Serien/ALF/1/03_Katzenjammer.mkv
```

is scanned as:

```text
series_title: ALF
season_number: 1
episode_number: 3
episode_sort_key: alf|0001|0003
media_type: episode
tags: episode, series
```

## Not included yet

This patch does not yet schedule series rotations. It only teaches PrivateTV to recognize and persist episodes in a reliable, configurable way.
