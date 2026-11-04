FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \\\n    && rm -rf /var/lib/apt/lists/*\n\nWORKDIR /srv/examgen
COPY pyproject.toml ./
COPY alembic.ini ./
COPY backend ./backend
RUN python -m pip install --upgrade pip && python -m pip install .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
