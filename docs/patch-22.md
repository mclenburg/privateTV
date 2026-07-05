# Patch 22: Docker runtime

Adds a Docker runtime for PrivateTV:

- `Dockerfile` based on Python slim with FFmpeg/ffprobe installed
- `.dockerignore` to keep media and runtime state out of the build context
- `docker-compose.yml` for an immediately runnable container
- `docker/config.yml` as a container-path example configuration
- `docs/DOCKER.md` with installation, scan, schedule, tvheadend, and permission notes

The container keeps configuration, media, SQLite state, and generated countdowns outside the image through bind mounts/volumes.
