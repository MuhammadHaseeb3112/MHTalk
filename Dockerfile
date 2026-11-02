FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.org/simple \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to preserve Docker layer caching.
COPY requirements/ requirements/

# Use the official PyPI index and retry transient network interruptions.
RUN python -m pip install --upgrade pip \
    --index-url https://pypi.org/simple \
    --timeout 120 \
    --retries 10

RUN python -m pip install --no-cache-dir \
    --index-url https://pypi.org/simple \
    --timeout 120 \
    --retries 10 \
    -r requirements/development.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
