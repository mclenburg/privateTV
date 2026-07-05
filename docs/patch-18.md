# Patch 18 - Optional program block scaffolding

This patch prepares the configuration model for future broadcast-style scheduling without changing the current scheduler behavior.

## Added

- New optional `program_blocks` configuration section.
- Default remains disabled, so PrivateTV continues to schedule film after film exactly as before.
- Optional 20:15 anchor metadata for a future primetime block.
- Optional filler directory metadata for future filler/trailer/bumper clips.
- Optional generated countdown metadata.
- Validation that generated countdown clips must never be longer than 60 seconds.
- Configuration UI fields for the new program block scaffolding.
- Health endpoint flags for program block/countdown configuration.

## Behavior

`program_blocks.enabled: false` is the default and preserves the legacy continuous scheduler. No filler clips are required and no schedule output changes are made by this patch.

The generated countdown settings are preparatory only in this patch. Actual countdown clip generation will be implemented in a later patch.
