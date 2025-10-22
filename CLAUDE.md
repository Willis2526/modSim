# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

modSim is a configurable Modbus TCP simulator with a RESTful API for dynamic configuration. It provides a Modbus TCP server that can simulate multiple slaves with various register types, controlled via a FastAPI web interface.

## Requirements

- Python 3.11+ (required for pymodbus compatibility)
- Dependencies: pymodbus, fastapi, uvicorn

## Development Commands

### Docker (Recommended)
```bash
docker-compose up -d          # Start container in background
docker-compose logs -f        # View logs
docker-compose down           # Stop container
docker-compose up --build     # Rebuild and start
```

Configuration files are persisted in `./data` directory (mounted as volume).

### Local Development Setup
**MacOS/Linux:**
```bash
make local
```

**Windows:**
```bash
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
```

### Running the Application
```bash
python -m modSim              # Run with default settings
python -m modSim --debug      # Run with debug logging
```

## Architecture

### Core Components

**server.py** - Main orchestrator (`Server` class)
- Loads/saves configuration from `settings.json`
- Initializes database (`Database` class from database.py)
- Spawns multiple Modbus server instances based on config
- Starts web server for API interface
- Main loop: continuously simulates registers every 1 second based on database config
- Handles graceful shutdown via `SignalHandler`

**modbus.py** - Modbus server implementation (`Server` class)
- Each instance runs in a separate thread
- Uses pymodbus library to create TCP servers
- Manages ModbusServerContext with multiple slaves
- Each slave has 4 register types: coils (co), discrete inputs (di), holding registers (hr), input registers (ir)
- Each register type can have an individual size configured via `registerSizes` parameter
- `simulate()` method: updates register values with random data based on database configuration
- Supports simulating single addresses or address ranges (address to address_end)

**web.py** - FastAPI web server (`WebServer` class)
- Runs in separate thread
- Endpoints at `/api/v1/docs` for OpenAPI documentation
- Endpoints: `/configure-server`, `/get-server-config`, `/configure-registers`, `/get-registers`, `/get-context`
- Interacts with database to persist register configurations
- Note: `/configure-server` endpoint currently raises `NotImplementedError`

**database.py** - SQLite persistence (`Database` class)
- Single table: `registers` with columns: server_id, slave_id, register_type, address, address_end, register_size, simulate
- `save_registers()` clears and replaces all register configs
- `get_registers()` retrieves all stored configurations

**utils.py** - Signal handling
- `SignalHandler` class captures SIGINT/SIGTERM for graceful shutdown

### Configuration Flow

1. On startup, `Server` loads `settings.json` (creates default if missing)
2. Default config simulates all registers for slave 0 on server 0
3. Initial register config from `settings.json` is saved to database
4. Main loop reads database and calls `simulate()` on each Modbus server every second
5. API endpoints modify database; changes take effect in next simulation cycle

### Register Configuration

Register type codes used internally:
- 0 = all (special case to configure all types at once)
- 1 = co (coils)
- 2 = di (discrete inputs)
- 3 = hr (holding registers)
- 4 = ir (input registers)

Special behavior: `register_type: "all"` simulates all register types for a slave.

**New Configuration Options:**
- `address_end`: Optional field to specify end address for range simulation (simulates address to address_end inclusive)
- `register_size`: Optional field to override the default register size for a specific register type
- Individual register sizes can be configured globally in settings.json via `register_sizes` object with keys: co, di, hr, ir

## Important Notes

- Modbus servers run on sequential ports: base port + instance number
- Each Modbus server instance has its own context with independent slaves
- Simulation generates: random True/False for di/co, random 0-500 for hr/ir
- Database is recreated if missing; registers table initialized on first run
- PEP8 formatting is used throughout the codebase
