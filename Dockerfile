FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/_runtime && \
    chmod +x /app/docker/entrypoint.sh && \
    chown -R appuser:appuser /app

USER appuser

VOLUME ["/app/_runtime"]

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["--help"]
