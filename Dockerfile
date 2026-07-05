FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PRIVATETV_CONFIG=/config/config.yml

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin privatetv

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir .

RUN mkdir -p /config /media /var/lib/privatetv \
    && chown -R privatetv:privatetv /config /media /var/lib/privatetv

USER privatetv

VOLUME ["/config", "/media", "/var/lib/privatetv"]
EXPOSE 9988

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9988/health >/dev/null || exit 1

CMD ["privatetv", "serve", "--config", "/config/config.yml"]
