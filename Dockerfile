FROM python:3.12.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CRYPTOFLASH_STATE_DIR=/app/state

WORKDIR /app
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock
COPY . .
RUN mkdir -p /app/state

CMD ["python", "src/flash_service.py"]
