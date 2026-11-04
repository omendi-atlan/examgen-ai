# EXAMGEN AI container image.
#
# The SQLite database, uploaded coursework, extracted content and generated
# PDFs all live under EXAMGEN_DATA_DIR. Mount a volume at /data to persist
# them across container restarts.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EXAMGEN_DATA_DIR=/data \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md ./
COPY examgen ./examgen
RUN pip install --no-cache-dir .

COPY app.py Procfile docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh && mkdir -p /data

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

ENTRYPOINT ["./docker-entrypoint.sh"]
