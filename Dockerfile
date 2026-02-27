# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install only necessary system packages
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create a simple health check file
RUN echo "OK" > health.html

# Command to run
CMD ["python", "index.py"]
