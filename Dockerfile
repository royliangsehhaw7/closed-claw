FROM python:3.12-slim

# curl is useful for testing health check from inside the container
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv provides uvx, which fetches and runs workspace-mcp at runtime
RUN pip install uv --no-cache-dir

WORKDIR /app

# Install dependencies first — this layer is cached and only rebuilds
# when requirements.txt changes, not on every code change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project source code into /app inside the image
COPY . .

EXPOSE 10000

# PORT env var lets the host override the port without rebuilding
CMD ["sh", "-c", "uvicorn gateway.app:app --host 0.0.0.0 --port ${PORT:-10000}"]