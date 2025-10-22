# Modbus Simulator

This project provides a Modbus TCP server with configurable registers and simulation capabilities. The server is configurable via a RESTful API and supports dynamic updates, including register simulation.

## Features

- Modbus TCP server with configurable IP, port, and identity.
- REST API for managing server settings and registers.
- Advanced simulation modes (random, static, equation, sine, ramp, square wave).
- Persistent storage of register configurations using SQLite.
- Web server with endpoints for interacting with the Modbus server.
- Support for register ranges and individual register type sizes.

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

### Configuration Architecture

modSim uses a two-layer configuration system:

1. **settings.json** - Application-level settings and initial defaults
   - Web server port
   - Default Modbus server settings (used only when database is empty)
   - Only loaded at startup to initialize database if empty

2. **settings.db** - Runtime configuration database
   - Server instances and their properties (IP, port, identity)
   - Slave configurations and register sizes
   - Register simulation settings
   - All runtime configuration is stored here and persists across restarts

### Default Settings
If the `settings.json` file does not exist, it will be created with the following default values:
```json
{
  "web": {
    "port": 8000
  },
  "modbus": {
    "ip": "0.0.0.0",
    "port": 502,
    "slaves": 1,
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
  }
}
```

> **NOTE:** The `settings.json` file is used **only for initial database population**. After the first run, all configuration is managed via the database and API. To reset configuration, delete `settings.db` and restart the application.

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
  Configure Modbus server instances and slaves. This dynamically updates the running configuration and restarts all Modbus servers.

  Example - Single server with one slave:
  ```json
  {
    "servers": [
      {
        "server_id": 0,
        "ip": "0.0.0.0",
        "port": 502,
        "vendor_name": "ModbusSimulator",
        "product_code": "MSIM",
        "version": "1.0"
      }
    ],
    "slaves": [
      {
        "server_id": 0,
        "slave_id": 0,
        "co_size": 100,
        "di_size": 100,
        "hr_size": 100,
        "ir_size": 100
      }
    ]
  }
  ```

  Example - Multiple servers with multiple slaves:
  ```json
  {
    "servers": [
      {
        "server_id": 0,
        "ip": "0.0.0.0",
        "port": 502,
        "vendor_name": "ModbusSimulator",
        "product_code": "MSIM",
        "version": "1.0"
      },
      {
        "server_id": 1,
        "ip": "0.0.0.0",
        "port": 503,
        "vendor_name": "ModbusSimulator2",
        "product_code": "MSIM",
        "version": "1.0"
      }
    ],
    "slaves": [
      {
        "server_id": 0,
        "slave_id": 0,
        "co_size": 100,
        "di_size": 100,
        "hr_size": 100,
        "ir_size": 100
      },
      {
        "server_id": 0,
        "slave_id": 1,
        "co_size": 200,
        "di_size": 200,
        "hr_size": 200,
        "ir_size": 200
      },
      {
        "server_id": 1,
        "slave_id": 0,
        "co_size": 150,
        "di_size": 150,
        "hr_size": 150,
        "ir_size": 150
      }
    ]
  }
  ```

- **GET /get-server-config**
  Retrieve the current server and slave configuration from the database.

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

## Simulation Modes

modSim supports multiple simulation modes for registers, similar to Ignition's device simulator. Each register can be configured with a specific simulation mode and associated configuration parameters.

### Available Simulation Modes

#### 1. Random (Default)
Generates random values within a specified range.

**Parameters:**
- `min` (optional): Minimum value (default: 0)
- `max` (optional): Maximum value (default: 500)

**Example:**
```json
{
  "slave_id": 0,
  "register_type": "hr",
  "address": 0,
  "simulate": true,
  "simulation_mode": "random",
  "simulation_config": {
    "min": 0,
    "max": 1000
  }
}
```

#### 2. Static
Returns a fixed value.

**Parameters:**
- `value`: The static value to return

**Example:**
```json
{
  "slave_id": 0,
  "register_type": "hr",
  "address": 10,
  "simulate": true,
  "simulation_mode": "static",
  "simulation_config": {
    "value": 42
  }
}
```

#### 3. Equation
Evaluates a mathematical expression to generate values. Similar to Ignition's expression-based simulation.

**Available Variables:**
- `x`: Counter that increments with each simulation cycle (per register)
- `address`: The register address
- `slave_id`: The slave ID
- `server_id`: The server ID

**Available Functions:**
- Trigonometric: `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`
- Hyperbolic: `sinh`, `cosh`, `tanh`
- Math: `sqrt`, `abs`, `pow`, `exp`, `log`, `log10`
- Rounding: `floor`, `ceil`, `round`
- Other: `min`, `max`
- Constants: `pi`, `e`

**Parameters:**
- `equation`: The mathematical expression to evaluate

**Examples:**
```json
{
  "slave_id": 0,
  "register_type": "hr",
  "address": 20,
  "simulate": true,
  "simulation_mode": "equation",
  "simulation_config": {
    "equation": "sin(x / 10) * 100 + 200"
  }
}
```

```json
{
  "slave_id": 0,
  "register_type": "hr",
  "address": 30,
  "simulate": true,
  "simulation_mode": "equation",
  "simulation_config": {
    "equation": "x * 2 + address"
  }
}
```

#### 4. Ramp
Generates a linear ramp that increases by a step value and wraps around.

**Parameters:**
- `min`: Minimum value (default: 0)
- `max`: Maximum value (default: 100)
- `step`: Increment per cycle (default: 1)

**Example:**
```json
{
  "slave_id": 0,
  "register_type": "hr",
  "address": 50,
  "simulate": true,
  "simulation_mode": "ramp",
  "simulation_config": {
    "min": 0,
    "max": 100,
    "step": 5
  }
}
```

#### 5. Sine Wave
Generates a sine wave pattern.

**Parameters:**
- `amplitude`: Wave amplitude (default: 100)
- `offset`: Vertical offset (default: 0)
- `period`: Period in simulation cycles (default: 60)

**Example:**
```json
{
  "slave_id": 0,
  "register_type": "hr",
  "address": 60,
  "simulate": true,
  "simulation_mode": "sine",
  "simulation_config": {
    "amplitude": 150,
    "offset": 200,
    "period": 60
  }
}
```

#### 6. Square Wave
Generates a square wave pattern.

**Parameters:**
- `high`: High value (default: 100)
- `low`: Low value (default: 0)
- `period`: Period in simulation cycles (default: 10)
- `duty_cycle`: Duty cycle from 0.0 to 1.0 (default: 0.5)

**Example:**
```json
{
  "slave_id": 0,
  "register_type": "co",
  "address": 70,
  "simulate": true,
  "simulation_mode": "square",
  "simulation_config": {
    "high": 1,
    "low": 0,
    "period": 20,
    "duty_cycle": 0.3
  }
}
```

### Boolean Registers

For boolean register types (`co` and `di`):
- **random**: Returns random True/False
- **static**: Converts value to boolean (0 = False, non-zero = True)
- **equation**: Converts result to boolean
- **ramp**: Returns True/False based on odd/even value
- **sine**: Returns True when value > offset
- **square**: Returns boolean based on high/low values

### Simulation Configuration Examples

**Configure via API:**
```bash
curl -X POST http://localhost:8000/configure-registers \
  -H "Content-Type: application/json" \
  -d '{
    "registers": [
      {
        "slave_id": 0,
        "register_type": "hr",
        "address": 200,
        "simulate": true,
        "simulation_mode": "sine",
        "simulation_config": {
          "amplitude": 100,
          "offset": 200,
          "period": 20
        }
      },
      {
        "slave_id": 0,
        "register_type": "hr",
        "address": 300,
        "simulate": true,
        "simulation_mode": "ramp",
        "simulation_config": {
          "min": 0,
          "max": 50,
          "step": 5
        }
      },
      {
        "slave_id": 0,
        "register_type": "hr",
        "address": 400,
        "simulate": true,
        "simulation_mode": "static",
        "simulation_config": {
          "value": 42
        }
      }
    ]
  }'
```

**Configure via settings.json:**
```json
{
  "modbus": {
    "config": {
      "registers": [
        {
          "slave_id": 0,
          "register_type": "hr",
          "address": 0,
          "address_end": 10,
          "simulate": true,
          "simulation_mode": "equation",
          "simulation_config": {
            "equation": "sin(x) * 100 + address * 10"
          }
        },
        {
          "slave_id": 0,
          "register_type": "hr",
          "address": 20,
          "simulate": true,
          "simulation_mode": "ramp",
          "simulation_config": {
            "min": 0,
            "max": 100,
            "step": 1
          }
        }
      ]
    }
  }
}
```

### Simulation Notes

- Each register maintains its own counter (`x`) for equation and pattern-based simulations
- Counters increment with each simulation cycle (default: 1 second)
- The equation mode uses a restricted namespace for security (no file I/O, imports, etc.)
- For range simulations (using `address_end`), each address in the range gets its own counter
- All simulation modes work with register range simulation

## Testing

### Running Unit Tests

The project includes a comprehensive test suite using pytest. Tests cover the simulation engine, database operations, and API endpoints.

**Install test dependencies:**
```bash
pip install -r requirements.txt
```

**Run all tests:**
```bash
pytest
```

**Run tests with coverage report:**
```bash
pytest --cov=modSim --cov-report=html
```

**Run specific test files:**
```bash
pytest tests/test_simulator.py      # Test simulation engine
pytest tests/test_database.py       # Test database operations
pytest tests/test_web.py           # Test API endpoints
```

**Run tests with verbose output:**
```bash
pytest -v
```

The test suite includes:
- **test_simulator.py**: Tests for all simulation modes (random, static, equation, ramp, sine, square)
- **test_database.py**: Tests for register storage, retrieval, and validation
- **test_web.py**: Tests for all API endpoints and configurations

Coverage reports are generated in the `htmlcov/` directory after running tests with `--cov-report=html`.

### Testing the Modbus Server

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
