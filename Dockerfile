# Pinned to match this project's actual development environment (Python 3.12.3)
# — avoids any subtle stdlib/typing behavior differences from a different minor version.
FROM python:3.12-slim

# Prevents .pyc write attempts and forces unbuffered stdout/stderr so logs
# appear immediately in `docker logs` rather than being buffered.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies in their own layer so `docker build` only re-installs
# them when requirements.txt actually changes, not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# google-auth is intentionally NOT in the base requirements.txt (it's only
# needed if GDRIVE_BACKUP_ENABLED=true — see storage/drive_backup.py). Install
# it unconditionally in the image anyway so the feature works out of the box
# without requiring a rebuild just to turn on backups.
RUN pip install --no-cache-dir google-auth==2.35.0

COPY . .

# data/ (SQLite DB) and logs/ are meant to be mounted as volumes in
# production (see docker-compose.yml and the README's persistence section)
# so they survive a container recreation — created here only so a bare
# `docker run` without a volume mount still works for a quick smoke test.
RUN mkdir -p data logs

# Runs as a non-root user — this process only needs to read/write its own
# data/logs directories and make outbound HTTPS calls, no reason to run as root.
RUN useradd --create-home --uid 1000 botuser \
    && chown -R botuser:botuser /app
USER botuser

# No ports are exposed by default: this bot only makes outbound connections
# (Telegram long-polling, CoinDCX REST, optional Google Drive). If you
# enable the optional CoinDCX webhook receiver (WEBHOOK_ENABLED=true), it
# does listen for inbound HTTP — expose that port via `docker run -p` or
# docker-compose.yml's `ports:` section (commented out there by default).

CMD ["python", "main.py"]
