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

# Expose the web API (8000) and a range of Modbus TCP ports for server 0 plus
# any additional servers added later through the UI/API (each new server needs
# a port within this range published in docker-compose.yml to be reachable
# from outside the container — see MODBUS_PORT_RANGE there).
EXPOSE 8000
EXPOSE 502-520

# Default: run the module
CMD ["python", "-m", "modSim"]
