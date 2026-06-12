FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py .
COPY shared/ shared/
COPY storage/ storage/
COPY core/ core/
COPY bot/ bot/
COPY api/ api/
COPY scripts/ scripts/
