# Modbus Simulator

This project provides a Modbus TCP server with configurable registers and simulation capabilities. The server is configurable via a RESTful API and supports dynamic updates, including register simulation.

## Features

- Modbus TCP server with configurable IP, port, and identity.
- REST API for managing server settings and registers.
- Register simulation with random value generation.
- Persistent storage of register configurations using SQLite.
- Web server with endpoints for interacting with the Modbus server.

## Prerequisites

- Python 3.11 or higher.
- `pip` (Python package manager).
- A Linux, macOS, or Windows environment.
- Git
- Make (MacOS/Linux Only)

## Installation

### Docker (Recommended)
The easiest way to run modSim is using Docker:

1. Clone the repository
2. Start the container:
   ```bash
   docker-compose up -d
   ```
3. The simulator will be available at:
   - Modbus TCP: `localhost:502`
   - REST API: `http://localhost:8000/api/v1/docs`

Configuration files (`settings.json`, `settings.db`) will be persisted in the `./data` directory.

To stop the container:
```bash
docker-compose down
```

To view logs:
```bash
docker-compose logs -f
```

### Local Development

1. Clone the repository
2. Depending on the OS you are using, run the following commands:
    - **MacOS/Linux**: `make local`
    - **Windows**:
      - Create the virtual environment: `python -m venv env`
      - Activate the virtual environment: `env\Scripts\activate`
      - Install the required packages: `pip install -r requirements.txt`

### Production (Systemd Service)

For a production environment on Linux with systemd:
- **MacOS/Linux:** `sudo make install` (This will create a virtual environment, install the required packages, and install the service.)

## Configuration

### Default Settings
If the `settings.json` file does not exist, it will be created with the following default values:
```json
{
  "modbus": {
    "ip": "0.0.0.0",
    "port": 502,
    "slaves": 1,
    "registers": 100,
    "instances": 1,
    "identity": {
      "VendorName": "ModbusSimulator",
      "ProductCode": "MSIM",
      "MajorMinorRevision": "1.0"
    },
    "register_sizes": {
      "co": 100,
      "di": 100,
      "hr": 100,
      "ir": 100
    },
    "config": {
      "registers": [{ "slave_id": 0, "register_type": "all", "simulate": true }]
    }
  },
  "web": {
    "port": 8000
  }
}
```

> **NOTE:** The `settings.json` file is used only for the initial setup of the program. Afterwards, configuration is controlled with the API unless the `settings.db` file is deleted, then the `settings.json` can be used again.

#### Register Sizes
The `register_sizes` field allows you to configure individual sizes for each register type:
- `co` - Coils (discrete outputs)
- `di` - Discrete Inputs
- `hr` - Holding Registers
- `ir` - Input Registers

Each type can have a different size, allowing for flexible memory allocation based on your simulation needs.

With the default config, the server will be configured automatically to simulate all registers with:
```json
"config": {
  "registers": [{ "slave_id": 0, "register_type": "all", "simulate": true }]
}
```
This can be updated after the program is running using the endpoints described below.

### Database
The program uses an SQLite database (`settings.db`) to store register configurations. The database is initialized automatically if it does not exist.

## Running the Server

1. Start the simulator:
   ```bash
   python -m modSim
   ```

2. Optional: Enable debug mode for detailed logging:
   ```bash
   python -m modSim --debug
   ```

3. The REST API documentation will be available at:
   ```
   http://localhost:8000/api/v1/docs
   ```

## API Endpoints

The server can be configured over a REST API located at **http://server_address:web_port/api/v1/docs**.

### Server Configuration
- **POST /configure-server**  
  Configure the Modbus server (IP, port, identity).  
  Example:
  ```json
  {
    "modbus": {
      "ip": "0.0.0.0",
      "port": 502,
      "slaves": 1,
      "registers": 100,
      "instances": 1,
      "identity": {
        "VendorName": "ModbusSimulator",
        "ProductCode": "MSIM",
        "MajorMinorRevision": "1.0"
      },
      "config": {
        "registers": [{ "slave_id": 0, "register_type": "all", "simulate": true }]
      }
    },
    "web": {
      "port": 8000
    }
  }
  ```

- **GET /get-server-config**  
  Retrieve the current server configuration.

### Register Management
- **POST /configure-registers**
  Configure Modbus registers (addresses, values, simulation settings).

  **Basic Examples:**
  ```json
  {
    "registers": [
      {"server_id": 1, "slave_id": 1, "register_type": "hr", "address": 0, "simulate": true},
      {"server_id": 1, "slave_id": 2, "register_type": "co", "address": 1, "simulate": false}
    ]
  }
  ```

  **Simulate all registers:**
  ```json
  {
    "registers": [
      {"slave_id": 1, "register_type": "all", "simulate": true}
    ]
  }
  ```

  **New Features:**

  1. **Register Range Simulation** - Simulate a range of consecutive addresses:
  ```json
  {
    "registers": [
      {
        "server_id": 0,
        "slave_id": 0,
        "register_type": "hr",
        "address": 0,
        "address_end": 50,
        "simulate": true
      }
    ]
  }
  ```
  This simulates holding registers from address 0 to 50 (inclusive).

  2. **Individual Register Type Sizes** - Override the default size for a specific register type:
  ```json
  {
    "registers": [
      {
        "server_id": 0,
        "slave_id": 0,
        "register_type": "co",
        "register_size": 200,
        "simulate": true
      }
    ]
  }
  ```
  This creates a coil register space of 200 addresses instead of the default 100.

  3. **Combined Configuration** - Use ranges and custom sizes together:
  ```json
  {
    "registers": [
      {
        "slave_id": 0,
        "register_type": "hr",
        "address": 0,
        "address_end": 99,
        "simulate": true
      },
      {
        "slave_id": 0,
        "register_type": "ir",
        "address": 100,
        "address_end": 199,
        "register_size": 300,
        "simulate": true
      }
    ]
  }
  ```

  **Default Configuration (applies to all servers):**
  If `server_id` is omitted from a register configuration, it will apply to all server instances that don't have explicit configurations:
  ```json
  {
    "registers": [
      {"slave_id": 0, "register_type": "all", "simulate": true}
    ]
  }
  ```
  This applies the configuration to all server instances.

  You can combine default and specific configurations:
  ```json
  {
    "registers": [
      {"slave_id": 0, "register_type": "all", "simulate": true},
      {"server_id": 1, "slave_id": 0, "register_type": "hr", "simulate": false}
    ]
  }
  ```
  This applies the default config to all servers except server 1, which gets its own specific configuration.

  **Available Register Types:**
  - `all` - All register types
  - `co` - Coils (discrete outputs)
  - `di` - Discrete Inputs
  - `hr` - Holding Registers
  - `ir` - Input Registers

- **GET /get-registers**  
  Retrieve the current register configuration.

- **GET /get-context**  
  Retrieve the Modbus context.

## Testing

You can test the Modbus server using tools like `modpoll` or any Modbus client software:
```bash
modpoll -m tcp -r 0 -c 10 -t 3:int -a 1 127.0.0.1
```

## Logs

Logs are managed using Python’s `logging` module. By default:
- Info logs are output to the console.
- Debug logs are enabled when using the `--debug` flag.

## Stopping the Simulator

The simulator gracefully shuts down when receiving a `SIGINT` or `SIGTERM` signal:
```bash
Ctrl+C  # To stop the server
```
