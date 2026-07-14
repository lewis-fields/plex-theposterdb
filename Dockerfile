FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8765 \
    CONFIG_PATH=/config/config.json \
    PUID=10001 \
    PGID=10001

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --create-home --uid 10001 --gid 10001 app \
    && mkdir /config

COPY --chown=app:app server.py ./
COPY --chown=app:app static ./static
COPY --chown=app:app docker_entrypoint.py ./

EXPOSE 8765
VOLUME ["/config"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8765') + '/', timeout=3)" || exit 1

ENTRYPOINT ["python", "docker_entrypoint.py"]
CMD ["python", "server.py"]
