FROM python:3.12-alpine

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH=/config/config.json
ENV MODE=loop
ENV RUN_INTERVAL=300
ENV LOG_LEVEL=INFO
ENV LOG_FILE=/config/logs/qbit-rectificarr.log
ENV LOG_MAX_BYTES=1048576
ENV LOG_BACKUP_COUNT=3

RUN pip install --no-cache-dir requests

COPY main.py /app/main.py

ENTRYPOINT ["python", "/app/main.py"]
