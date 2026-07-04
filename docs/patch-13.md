# Patch 13: Web Configuration UI

This patch adds a built-in web configuration page to the existing PrivateTV HTTP service.

## Added

- `GET /` now opens the web configuration page.
- `GET /config` opens the same configuration editor.
- `POST /config` validates and saves the YAML configuration file used to start the service.
- `GET /config/browse` browses directories on the PrivateTV server filesystem.
- `POST /config/media-directories/add` adds a selected server directory to `media.directories`.
- The previous JSON index remains available at `GET /api`.
- Runtime providers are refreshed after saving configuration.
- Configuration serialization helpers were added for YAML round-tripping.

## Important behavior

Media path selection is server-side. The browser does not upload a local folder path from the client computer. When the page browses `/srv/media`, that is `/srv/media` on the Raspberry Pi or server running PrivateTV.

## Security note

The configuration UI is intentionally unauthenticated for LAN-only V1.0 usage. Do not expose it to the internet without an authenticated reverse proxy.
