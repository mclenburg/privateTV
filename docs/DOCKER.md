# Docker installation

This guide starts a PrivateTV container while keeping configuration, media folders, the SQLite database, and generated countdown clips outside the image.

## What is inside the image

The image contains:

- PrivateTV itself
- Python runtime
- FFmpeg and ffprobe
- curl for the health check

The image does **not** contain your video library or your active production configuration.

## Repository layout for Docker

The repository ships with:

```text
Dockerfile
docker-compose.yml
docker/config.yml
media/
docker/state/
```

`docker/config.yml` is a host-side example configuration mounted into the container as `/config/config.yml`.

`media/` is a host-side example media directory mounted into the container as `/media`.

`docker/state/` is mounted into the container as `/var/lib/privatetv` and stores:

```text
privatetv.sqlite3
generated/countdowns/...
```

## Quick start

From the repository root:

```bash
docker compose up --build -d
```

Check the service:

```bash
docker compose ps
docker compose logs -f privatetv
curl -s http://127.0.0.1:9988/health
```

The HTTP service is available on the host at:

```text
http://127.0.0.1:9988/
http://127.0.0.1:9988/playlist.m3u
http://127.0.0.1:9988/xmltv.xml
http://127.0.0.1:9988/stream/main.ts
```

## Use real media folders

Edit `docker-compose.yml` and replace the example media mount:

```yaml
- ./media:/media:ro
```

with your real host folders, for example:

```yaml
- /data/Filme:/media/Filme:ro
- /data/DVDs:/media/DVDs:ro
- /data/PrivateTV/Filler:/media/Filler:ro
```

Then adapt `docker/config.yml` accordingly:

```yaml
media:
  directories:
    - "/media/Filme"
    - "/media/DVDs"
```

For local filler clips:

```yaml
program_blocks:
  fillers:
    enabled: true
    directories:
      - "/media/Filler"
```

Remember: paths inside `docker/config.yml` are **container paths**, not host paths.

## Set the public URL

For tvheadend on another machine, set `public_base_url` to the Docker host address:

```yaml
server:
  host: "0.0.0.0"
  port: 9988
  public_base_url: "http://192.168.5.116:9988"
```

If tvheadend runs on the same Docker host, `http://127.0.0.1:9988` can be sufficient for host-to-container port publishing. If tvheadend runs in another container, use a shared Docker network and the service name, or expose the port to the host and use the host address.

## Run doctor, scan, and schedule

The container starts the HTTP service. The first media import is still explicit:

```bash
docker compose exec privatetv privatetv doctor --config /config/config.yml
docker compose exec privatetv privatetv scan --config /config/config.yml
docker compose exec privatetv privatetv schedule --config /config/config.yml
```

Check the current programme:

```bash
docker compose exec privatetv privatetv current --config /config/config.yml
```

## Restart after configuration changes

After editing `docker/config.yml`:

```bash
docker compose restart privatetv
```

If media folders changed, rescan:

```bash
docker compose exec privatetv privatetv scan --config /config/config.yml
docker compose exec privatetv privatetv schedule --config /config/config.yml
```

## tvheadend integration

Use the same URLs as on a native installation, but with the Docker host address:

```text
M3U:    http://<docker-host>:9988/playlist.m3u
XMLTV:  http://<docker-host>:9988/xmltv.xml
Stream: http://<docker-host>:9988/stream/main.ts
```

For tvheadend's IPTV Automatic Network, use:

```text
http://<docker-host>:9988/playlist.m3u
```

For the XMLTV grabber script on the Docker host or tvheadend host:

```sh
#!/bin/sh
case "$1" in
  --description) echo "PrivateTV XMLTV"; exit 0 ;;
  --capabilities) echo "baseline"; exit 0 ;;
  --version) echo "1.0"; exit 0 ;;
esac
curl -fsS http://<docker-host>:9988/xmltv.xml
```

## Permissions

The image runs PrivateTV as UID `1000` inside the container. This matches the default `pi` user on many Raspberry Pi installations and works well for bind-mounted state directories owned by that user.

If `docker/state` is not writable, fix it on the host:

```bash
mkdir -p docker/state
chown -R 1000:1000 docker/state
```

Media mounts can be read-only.

## Health check

The Dockerfile includes a health check against:

```text
http://127.0.0.1:9988/health
```

Inspect it with:

```bash
docker compose ps
docker inspect --format='{{json .State.Health}}' privatetv | python3 -m json.tool
```

## Build without Compose

```bash
docker build -t privatetv:local .
```

Run with external config, media, and state:

```bash
docker run --rm \
  --name privatetv \
  -p 9988:9988 \
  -v "$PWD/docker/config.yml:/config/config.yml:ro" \
  -v "$PWD/media:/media:ro" \
  -v "$PWD/docker/state:/var/lib/privatetv" \
  privatetv:local
```

In another shell:

```bash
docker exec privatetv privatetv doctor --config /config/config.yml
docker exec privatetv privatetv scan --config /config/config.yml
docker exec privatetv privatetv schedule --config /config/config.yml
```

## Notes

- The active config file is mounted read-only into the container.
- The SQLite database is stored outside the container image.
- Generated countdown clips are stored outside the container image.
- Do not put large media files into the Docker build context. Mount them as volumes.
