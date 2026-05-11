FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data

COPY pyproject.toml README.md ./
COPY billing_collector ./billing_collector
COPY scripts/seed-history.sh /usr/local/bin/billing-collector-seed-history

RUN pip install --no-cache-dir . \
    && chmod +x /usr/local/bin/billing-collector-seed-history

USER appuser

EXPOSE 9503

CMD ["billing-collector", "serve"]
