# Modbus Simulator container
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Create app directory
WORKDIR /app

# Copy dependency file and install
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source
COPY . /app

# Create data directory for persistent storage
RUN mkdir -p /app/data

# Expose Modbus TCP (502) and API (8000)
EXPOSE 502 8000

# Default: run the module
CMD ["python", "-m", "modSim"]
