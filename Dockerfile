FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY app/ ./app/
COPY rules/ ./rules/

# Default entrypoint is overridden per service in docker-compose.yml
