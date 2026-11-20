FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1. Install system build tools and shared graphic/DB libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    libpng-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Upgrade core packaging tools (ensures manylinux binary wheels match)
RUN pip install --upgrade pip setuptools wheel

# 3. Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# 4. Copy application source
COPY . .

# PVR spool (PDFs waiting for Google Drive); mounted as a volume in docker-compose
RUN mkdir -p /app/spool

EXPOSE 8000

# Exactly 1 worker: the PVR background uploader is an in-process thread
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]