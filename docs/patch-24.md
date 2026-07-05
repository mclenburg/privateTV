# Patch 24 - Media tags

Patch 24 adds a file based tagging system for media selection and programme anchors.

## Added

- Optional `media.tag_file` setting.
- Example tag file: `config/tags.example.yml`.
- `directory_tags` rules for tagging whole folders.
- `file_tags` rules with `add` and `remove` for individual media files.
- New SQLite table `media_tag`.
- Automatic tags such as `movie`, `dvd`, `filler`, `short`, `countdown`.
- Scan stores tags for every imported media item.
- `privatetv list-tags` command.
- `privatetv list-media --tag <tag>` filter.
- `doctor` validates the optional tag file and warns about missing paths.
- Programme anchors support `allowed_tags`, `denied_tags`, and `tag_match`.
- Filler selection supports `allowed_tags` and `denied_tags`.

## Compatibility

The tag file is optional. Without `media.tag_file`, PrivateTV keeps working and assigns automatic tags during scan. Existing databases need a new scan to populate `media_tag`.

## Tests

- `84 passed`
