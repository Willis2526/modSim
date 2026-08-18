# modSim — Modbus TCP Simulator

A configurable Modbus TCP server with a browser-based UI and REST API. Supports multiple server instances, multiple slaves per server, per-register simulation modes, and persistent SQLite-backed configuration.

## Features

- **Modbus TCP** — multiple server instances, each with one or more slaves
- **Browser UI** — dashboard, live register view, server/rule management, import/export, mobile-friendly
- **Six simulation modes** — `random`, `static`, `sine`, `ramp`, `square`, `equation`
- **Per-rule CRUD** — add, edit, and delete individual simulation rules without restart
- **Import / Export** — backup and restore configuration (servers, slaves, or rules) as JSON; merge (additive/sync) or replace modes, with selective section support
- **Persistent storage** — all runtime configuration stored in SQLite (`settings.db`)
- **pymodbus 3.13 compatible** — uses `ModbusSimulatorContext` internally; no deprecated APIs

---

## Prerequisites

- Python 3.11 or higher
- `pip`
- Linux, macOS, or Windows
- Git

---

## Installation

### Docker (recommended)

Prebuilt images are published to GitHub Container Registry.

**Quick try** — one-liner, no clone, no persistence (config resets when the container is removed):

```bash
docker run -d --name modsim -p 8000:8000 -p 502-520:502-520 ghcr.io/twillislabs/modsim:latest
```

```bash
docker compose -f - up -d --pull always <<< '
services:
  modsim:
    image: ghcr.io/twillislabs/modsim:latest
    ports:
      - "8000:8000"
      - "502-520:502-520"
'
```

#### Option A — `docker compose` (build from source)

```bash
git clone <repo>
docker-compose up -d
```

#### Option B — `docker compose` (prebuilt image)

Pulls the published image instead of building locally:

```bash
git clone <repo>
docker compose pull
docker compose up -d
```

Pin a specific version instead of `latest` by setting `MODSIM_TAG`, e.g. in `.env`:

```bash
MODSIM_TAG=v1.2.0
```

#### Option C — `docker run` (prebuilt image, no compose)

```bash
docker run -d \
  --name modsim \
  -p 8000:8000 \
  -p 502-520:502-520 \
  -v $(pwd)/data:/app/data \
  -w /app/data \
  --restart unless-stopped \
  ghcr.io/twillislabs/modsim:latest
```

All three options expose:

- Modbus TCP: `localhost:502`
- Web UI / API: `http://localhost:8000`

Configuration files (`settings.json`, `settings.db`) are persisted in `./data`.

```bash
docker-compose down        # stop (compose)
docker-compose logs -f     # stream logs (compose)
docker stop modsim         # stop (docker run)
docker logs -f modsim      # stream logs (docker run)
```

**Additional servers.** New servers can be added at any time from the web UI
or API (see [Servers](#servers)), each on its own port. Docker only forwards
ports that are explicitly published, so `docker-compose.yml` publishes a
range — `502-520` by default — covering server 0 plus headroom for more.
A new server's port must fall inside this range to be reachable from outside
the container.

To widen the range, copy `.env.example` to `.env`, adjust `MODBUS_PORT_RANGE`
(and `WEB_PORT` if needed), then re-create the container:

```bash
cp .env.example .env
# edit .env, e.g. MODBUS_PORT_RANGE=502-550
docker-compose up -d
```

With `docker run`, widen the range by changing the `-p 502-520:502-520` flag
to match instead.

A server outside the published range still runs and is reachable from other
containers on the compose network, just not from outside Docker.

### Local — Windows

```powershell
python -m venv env
env\Scripts\activate
pip install -r requirements.txt
```

### Local — macOS / Linux

```bash
make local
```

### Production (systemd)

```bash
sudo make install
```

---

## Configuration

modSim uses a two-layer configuration system:

| Layer | File | Purpose |
|-------|------|---------|
| Startup defaults | `settings.json` | Seeds the database on first run only |
| Runtime config | `settings.db` | All live configuration; survives restarts |

After the first run, use the web UI or API to change configuration — edits to `settings.json` are ignored unless `settings.db` is deleted.

### Default `settings.json`

```json
{
  "web": { "port": 8000 },
  "modbus": {
    "ip": "0.0.0.0",
    "port": 502,
    "instances": 1,
    "slaves": 1,
    "identity": {
      "VendorName": "ModbusSimulator",
      "ProductCode": "MSIM",
      "MajorMinorRevision": "1.0"
    },
    "register_sizes": { "co": 100, "di": 100, "hr": 100, "ir": 100 },
    "config": {
      "registers": [{ "slave_id": 0, "register_type": "all", "simulate": true }]
    }
  }
}
```

> To reset all configuration, delete `settings.db` and restart.

### Register types

| Key | Description |
|-----|-------------|
| `co` | Coils (FC 1/5/15) |
| `di` | Discrete Inputs (FC 2) |
| `hr` | Holding Registers (FC 3/6/16) |
| `ir` | Input Registers (FC 4) |

---

## Addressing

Each server has a **zero_based** flag (default `true`) that controls how the
`address`/`address_end` in register rules map to physical registers. It can be
set per server from the **Servers** page in the web UI, via the server APIs, or
seeded from `settings.json` (`modbus.zero_based`).

| Mode | `zero_based` | Rule `address` N maps to | Client reads it at (wire) |
|------|--------------|--------------------------|---------------------------|
| 0-based (default) | `true`  | register `N`   | `N`   |
| 1-based           | `false` | register `N-1` | `N-1` |

The Modbus wire protocol is **always 0-based** — the flag only shifts how rule
addresses (and the addresses shown in the live view) are interpreted, so you can
configure rules using 1-based reference numbers from SCADA/OPC documentation.
The `address` variable available to `equation` mode always reflects the
user-facing address you entered.

---

## Running

```bash
python -m modSim           # normal
python -m modSim --debug   # verbose logging
```

- Web UI: `http://localhost:8000`
- API docs (Swagger): `http://localhost:8000/api/v1/docs`

---

## Web UI

The browser interface is served at `/`. It provides:

| Page | Description |
|------|-------------|
| Dashboard | Live status of every Modbus server and key counters |
| Servers | Add, edit, delete server instances and their slaves |
| Register Rules | Add, edit, delete simulation rules; inline mode-config editor |
| Live Values | Real-time register snapshot, auto-refreshes every second |
| Import / Export | Download the full config as JSON; upload to merge into or replace the current config; selective section export |
| Reference | Simulation mode quick-reference |

The UI is responsive and works on mobile (hamburger sidebar navigation).

---

## API Endpoints

Interactive docs: `http://localhost:8000/api/v1/docs`

Endpoints are grouped into five categories.

---

### Servers

#### `POST /configure-server` — bulk configure servers & slaves

Replaces the **entire** server/slave topology. Accepts two formats.

**Simplified** — all servers share the same identity; all slaves share the same register sizes:

```json
{
  "ip": "0.0.0.0",
  "port": 502,
  "instances": 2,
  "slaves": 3,
  "zero_based": true,
  "identity": {
    "VendorName": "MySimulator",
    "ProductCode": "SIM1",
    "MajorMinorRevision": "2.0"
  },
  "register_sizes": { "co": 200, "di": 200, "hr": 500, "ir": 500 }
}
```

Creates server 0 on port 502 and server 1 on port 503, each with slaves 0–2.
`zero_based` (default `true`) is applied to every instance created here — set it
to `false` to enter rule addresses in 1-based numbering (see [Addressing](#addressing)).

**Detailed** — full per-server and per-slave control:

```json
{
  "servers": [
    { "server_id": 0, "ip": "0.0.0.0", "port": 502,
      "vendor_name": "Acme", "product_code": "SIM1", "version": "1.0",
      "zero_based": true }
  ],
  "slaves": [
    { "server_id": 0, "slave_id": 0, "co_size": 100, "di_size": 100, "hr_size": 100, "ir_size": 1200 },
    { "server_id": 0, "slave_id": 1, "co_size": 100, "di_size": 100, "hr_size": 100, "ir_size": 1200 }
  ]
}
```

Triggers a Modbus server restart.

---

#### `GET /get-server-config` — get all servers and slaves

Returns the current database records.

---

#### `POST /servers/add` — add or upsert a single server

Inserts or replaces one server without touching others. Triggers restart.

```json
{
  "server_id": 1,
  "ip": "0.0.0.0",
  "port": 503,
  "vendor_name": "Acme",
  "product_code": "SIM2",
  "version": "2.0",
  "zero_based": true
}
```

---

#### `PUT /servers/{server_id}` — update a server

Updates one server's fields. `server_id` in the URL takes precedence. Triggers restart.

---

#### `DELETE /servers/{server_id}` — delete a server

Removes the server and all its slave records (cascade). Triggers restart.

---

### Register Rules

Simulation rules are evaluated every second. Add or delete rules; they take effect within one cycle — no restart needed.

#### `POST /configure-registers` — bulk replace all rules

Drops every existing rule and replaces with the supplied list. To append without replacing, use `/rules/add`.

```json
{
  "registers": [
    {
      "server_id": 0,
      "slave_id": 1,
      "register_type": "ir",
      "address": 76,
      "address_end": 87,
      "simulate": true,
      "simulation_mode": "static",
      "simulation_config": { "value": 0 }
    },
    {
      "slave_id": 0,
      "register_type": "hr",
      "address": 0,
      "address_end": 99,
      "simulate": true,
      "simulation_mode": "sine",
      "simulation_config": { "amplitude": 100, "offset": 200, "period": 60 }
    }
  ]
}
```

If `server_id` is omitted from a rule, it applies to all server instances that don't have an explicit rule.

---

#### `GET /get-registers` — get all rules

Returns all rules including their database `id` (needed for PUT/DELETE).

---

#### `POST /rules/add` — add a single rule

Appends one rule without touching others. Returns the new `id`.

```json
{
  "slave_id": 1,
  "register_type": "ir",
  "address": 1141,
  "simulate": true,
  "simulation_mode": "sine",
  "simulation_config": { "amplitude": 2, "offset": 6, "period": 7200 }
}
```

Response:
```json
{ "success": true, "id": 7, "message": "Rule 7 added." }
```

---

#### `PUT /rules/{rule_id}` — update a rule

Replaces all fields of the rule with the given database `id`.

---

#### `DELETE /rules/{rule_id}` — delete a rule

Removes the rule. Takes effect within the next simulation cycle.

---

### Live Data

#### `GET /status` — server status

Returns the running state and port of every Modbus server instance.

#### `GET /live-values` — live register snapshot

Reads every simulated register from every running slave. Useful for verifying simulation output.

#### `GET /get-context?server_id={id}` — raw Modbus context

Returns the raw pymodbus context object for debugging.

---

### Import / Export

#### `GET /export?sections=servers,slaves,registers` — export config

Downloads a JSON file. Use the `sections` query parameter to export only specific parts:

| `sections` value | What is exported |
|------------------|-----------------|
| `servers,slaves,registers` (default) | Full configuration |
| `registers` | Only simulation rules |
| `servers,slaves` | Only topology |

The response includes `Content-Disposition: attachment` so browsers prompt to save the file.

---

#### `POST /import` — import config

The `mode` field selects how the payload is applied. Either way, only sections
present in the payload are touched.

| `mode` | Behavior |
|--------|----------|
| `merge` (default) | **Additive / sync.** Servers and slaves are upserted by id; register rules are upserted by their natural key `(server_id, slave_id, register_type, address, address_end)`. Anything not in the payload is left untouched, so re-importing the same file is idempotent (no duplicate rules). Use this to add a server to a running config. |
| `replace` | Wipes and replaces each supplied section wholesale — servers/slaves/rules not named for that section are removed. |

```json
{
  "mode": "merge",
  "servers": [
    { "server_id": 2, "ip": "0.0.0.0", "port": 504,
      "vendor_name": "ASCO", "product_code": "5210", "zero_based": false }
  ],
  "slaves": [
    { "server_id": 2, "slave_id": 0, "hr_size": 100 }
  ],
  "registers": [
    { "server_id": 2, "slave_id": 0, "register_type": "hr", "address": 17,
      "simulate": true, "simulation_mode": "sine",
      "simulation_config": { "offset": 480, "amplitude": 3, "period": 30 } }
  ]
}
```

Omit `servers`/`slaves` to affect only rules. Omit `registers` to affect only topology. Server changes trigger a restart. The web UI's Import / Export page exposes the same modes via a Mode selector (defaulting to Merge).

---

### System

#### `POST /restart` — restart Modbus servers

Stops and restarts all Modbus server threads using the current database configuration. The web server, simulation loop, and API remain available during the restart.

---

## Simulation Modes

Every register rule specifies a `simulation_mode` and a `simulation_config` dict.

### `random`

Generates a random integer each cycle.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min` | `0` | Minimum value |
| `max` | `500` | Maximum value |

```json
{ "simulation_mode": "random", "simulation_config": { "min": 0, "max": 1000 } }
```

---

### `static`

Returns a fixed value every cycle.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `value` | `0` | Value to hold |

```json
{ "simulation_mode": "static", "simulation_config": { "value": 3 } }
```

---

### `sine`

Generates a sine wave: `value = amplitude × sin(2π × counter / period) + offset`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `amplitude` | `100` | Peak deviation from offset |
| `offset` | `0` | Vertical centre |
| `period` | `60` | Cycle length in simulation ticks (1 tick ≈ 1 s) |

```json
{
  "simulation_mode": "sine",
  "simulation_config": { "amplitude": 500, "offset": 3000, "period": 7200 }
}
```

---

### `ramp`

Increases by `step` each cycle, wrapping back to `min` after `max`.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min` | `0` | Start value (also reset value) |
| `max` | `100` | Value that triggers wrap |
| `step` | `1` | Increment per cycle |

```json
{ "simulation_mode": "ramp", "simulation_config": { "min": 0, "max": 100, "step": 5 } }
```

---

### `square`

Alternates between two values based on a duty cycle.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `high` | `100` | Value during the ON phase |
| `low` | `0` | Value during the OFF phase |
| `period` | `10` | Full cycle length in ticks |
| `duty_cycle` | `0.5` | Fraction of period spent at `high` (0.0–1.0) |

```json
{
  "simulation_mode": "square",
  "simulation_config": { "high": 1, "low": 0, "period": 20, "duty_cycle": 0.3 }
}
```

---

### `equation`

Evaluates a Python expression each cycle. Counter variable `x` increments per tick per register.

**Available variables:** `x`, `address`, `slave_id`, `server_id`

**Available functions:** `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `atan2`, `sinh`, `cosh`, `tanh`, `sqrt`, `abs`, `pow`, `exp`, `log`, `log10`, `floor`, `ceil`, `round`, `min`, `max`, `pi`, `e`

```json
{
  "simulation_mode": "equation",
  "simulation_config": { "equation": "sin(x / 10) * 100 + address" }
}
```

> Built-in Python functions and imports are disabled for security.

---

### Boolean registers (`co`, `di`)

All modes work with coil/discrete-input registers:

| Mode | Boolean result |
|------|---------------|
| `random` | Random `True`/`False` |
| `static` | `bool(value)` |
| `ramp` | `True` when value is odd |
| `sine` | `True` when value > offset |
| `square` | `bool(high)` during ON phase |
| `equation` | `bool(result)` |

---

### Simulation notes

- Each register in a range rule gets its own independent counter
- Counters increment once per simulation cycle (default ≈ 1 second)
- `period` for `sine`/`square`/`ramp` is in simulation ticks, not seconds (though with a 1 s cycle they are equivalent)
- `register_size` in a rule overrides the slave's configured size for address-range validation only

---

## Import/Export format

The JSON format used by `/export` and `/import`:

```json
{
  "servers": [
    {
      "server_id": 0,
      "ip": "0.0.0.0",
      "port": 502,
      "vendor_name": "Acme",
      "product_code": "SIM1",
      "version": "1.0"
    }
  ],
  "slaves": [
    { "server_id": 0, "slave_id": 0, "co_size": 100, "di_size": 100, "hr_size": 100, "ir_size": 200 },
    { "server_id": 0, "slave_id": 1, "co_size": 100, "di_size": 100, "hr_size": 100, "ir_size": 200 }
  ],
  "registers": [
    {
      "slave_id": 1, "register_type": "ir",
      "address": 0, "address_end": 9,
      "simulate": true, "simulation_mode": "static",
      "simulation_config": { "value": 0 }
    },
    {
      "slave_id": 1, "register_type": "hr", "address": 100,
      "simulate": true, "simulation_mode": "sine",
      "simulation_config": { "amplitude": 100, "offset": 500, "period": 3600 }
    }
  ]
}
```

Any `id` fields in `registers` are stripped during import — IDs are always assigned by the database.

---

## Testing

```bash
pytest                          # all tests
pytest --cov=modSim --cov-report=html   # with coverage
pytest tests/test_simulator.py  # simulation engine only
pytest tests/test_database.py   # database only
pytest tests/test_web.py        # API endpoints only
pytest -v                       # verbose
```

Test coverage includes simulation engine, database CRUD, and all API endpoints (100 tests).

### Testing with a Modbus client

```bash
modpoll -m tcp -r 0 -c 10 -t 3:int -a 1 127.0.0.1
```

---

## Logs

```bash
python -m modSim           # INFO to stdout
python -m modSim --debug   # DEBUG to stdout
```

---

## Stopping

```
Ctrl+C
```

The simulator handles `SIGINT` and `SIGTERM` gracefully.
