FROM python:3.12-alpine

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH=/config/config.json
ENV MODE=run
ENV RUN_INTERVAL=300
ENV LOG_LEVEL=INFO

RUN pip install --no-cache-dir requests

COPY main.py /app/main.py

ENTRYPOINT ["python", "/app/main.py"]
