import argparse
import struct
from pathlib import Path
from pydantic import BaseModel
import logging
import threading
from typing import Optional, Union

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).parent
_TEMPLATES_DIR = _PACKAGE_DIR / "templates"
_STATIC_DIR = _PACKAGE_DIR / "static"

logging.getLogger("asyncio").setLevel(logging.WARNING)


# ── Pydantic models ────────────────────────────────────────────────────────────

class ModbusIdentity(BaseModel):
    VendorName: str = "ModbusSimulator"
    ProductCode: str = "MSIM"
    MajorMinorRevision: str = "1.0"

    class Config:
        json_schema_extra = {
            "example": {
                "VendorName": "ModbusSimulator",
                "ProductCode": "MSIM",
                "MajorMinorRevision": "1.0"
            }
        }


class RegisterSizes(BaseModel):
    co: int = 100
    di: int = 100
    hr: int = 100
    ir: int = 100

    class Config:
        json_schema_extra = {
            "example": {
                "co": 100,
                "di": 100,
                "hr": 100,
                "ir": 100
            }
        }


class ServerConfig(BaseModel):
    ip: str = "0.0.0.0"
    port: int = 502
    instances: int = 1
    slaves: int = 1
    zero_based: bool = True  # applied to every server instance created here
    identity: ModbusIdentity = ModbusIdentity()
    register_sizes: RegisterSizes = RegisterSizes()

    class Config:
        json_schema_extra = {
            "example": {
                "ip": "0.0.0.0",
                "port": 502,
                "instances": 2,
                "slaves": 3,
                "zero_based": True,
                "identity": {
                    "VendorName": "MySimulator",
                    "ProductCode": "SIM1",
                    "MajorMinorRevision": "2.0"
                },
                "register_sizes": {
                    "co": 200,
                    "di": 200,
                    "hr": 500,
                    "ir": 500
                }
            }
        }


class RegisterConfig(BaseModel):
    registers: list  # List of registers to configure

    class Config:
        json_schema_extra = {
            "example": {
                "registers": [
                    {
                        "server_id": 0,
                        "slave_id": 0,
                        "register_type": "all",
                        "simulate": True,
                        "simulation_mode": "random"
                    },
                    {
                        "server_id": 0,
                        "slave_id": 1,
                        "register_type": "hr",
                        "address": 0,
                        "address_end": 50,
                        "simulate": True,
                        "simulation_mode": "sine",
                        "simulation_config": {
                            "amplitude": 100,
                            "offset": 200,
                            "period": 60
                        }
                    },
                    {
                        "server_id": 0,
                        "slave_id": 1,
                        "register_type": "hr",
                        "address": 100,
                        "simulate": True,
                        "simulation_mode": "equation",
                        "simulation_config": {
                            "equation": "sin(x / 10) * 100 + address"
                        }
                    },
                    {
                        "server_id": 0,
                        "slave_id": 1,
                        "register_type": "hr",
                        "address": 200,
                        "simulate": True,
                        "simulation_mode": "ramp",
                        "simulation_config": {
                            "min": 0,
                            "max": 100,
                            "step": 5
                        }
                    },
                    {
                        "server_id": 0,
                        "slave_id": 1,
                        "register_type": "co",
                        "register_size": 200,
                        "simulate": True,
                        "simulation_mode": "square",
                        "simulation_config": {
                            "high": 1,
                            "low": 0,
                            "period": 20,
                            "duty_cycle": 0.5
                        }
                    },
                    {
                        "server_id": 0,
                        "slave_id": 1,
                        "register_type": "hr",
                        "address": 300,
                        "simulate": True,
                        "simulation_mode": "static",
                        "simulation_config": {
                            "value": 42
                        }
                    }
                ]
            }
        }


class ServerItem(BaseModel):
    server_id: int
    ip: str
    port: int
    vendor_name: str = "ModbusSimulator"
    product_code: str = "MSIM"
    version: str = "1.0"
    zero_based: bool = True  # False → rule addresses are 1-based (address N ⇒ register N-1)

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": 0,
                "ip": "0.0.0.0",
                "port": 502,
                "vendor_name": "ModbusSimulator",
                "product_code": "MSIM",
                "version": "1.0",
                "zero_based": True
            }
        }


class SlaveItem(BaseModel):
    server_id: int
    slave_id: int
    co_size: int = 100
    di_size: int = 100
    hr_size: int = 100
    ir_size: int = 100

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": 0,
                "slave_id": 0,
                "co_size": 1000,
                "di_size": 1000,
                "hr_size": 1000,
                "ir_size": 1000
            }
        }


class SingleRegisterRule(BaseModel):
    server_id: Optional[int] = None
    slave_id: int
    register_type: str
    address: int = 0
    address_end: Optional[int] = None
    register_size: Optional[int] = None
    simulate: bool = False
    simulation_mode: str = "random"
    simulation_config: dict = {}

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": 0,
                "slave_id": 1,
                "register_type": "ir",
                "address": 100,
                "address_end": 109,
                "simulate": True,
                "simulation_mode": "sine",
                "simulation_config": {"amplitude": 500, "offset": 3000, "period": 7200}
            }
        }


class ImportPayload(BaseModel):
    # "merge" (default) upserts servers/slaves by id and register rules by their
    # natural key, leaving anything not in the payload untouched. "replace" wipes
    # each supplied section and replaces it wholesale (the original behaviour).
    mode: str = "merge"
    servers: list = []
    slaves: list = []
    registers: list = []

    class Config:
        json_schema_extra = {
            "example": {
                "servers": [
                    {"server_id": 0, "ip": "0.0.0.0", "port": 502,
                     "vendor_name": "Acme", "product_code": "SIM1", "version": "1.0"}
                ],
                "slaves": [
                    {"server_id": 0, "slave_id": 0, "co_size": 100, "di_size": 100,
                     "hr_size": 100, "ir_size": 200},
                    {"server_id": 0, "slave_id": 1, "co_size": 100, "di_size": 100,
                     "hr_size": 100, "ir_size": 200}
                ],
                "registers": [
                    {"slave_id": 1, "register_type": "hr", "address": 100,
                     "simulate": True, "simulation_mode": "sine",
                     "simulation_config": {"amplitude": 100, "offset": 500, "period": 3600}}
                ]
            }
        }


class DetailedServerConfig(BaseModel):
    servers: list[ServerItem]
    slaves: list[SlaveItem]

    class Config:
        json_schema_extra = {
            "example": {
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
                        "co_size": 1000,
                        "di_size": 1000,
                        "hr_size": 1000,
                        "ir_size": 1000
                    },
                    {
                        "server_id": 0,
                        "slave_id": 1,
                        "co_size": 1000,
                        "di_size": 1000,
                        "hr_size": 1000,
                        "ir_size": 1000
                    }
                ]
            }
        }




# ── Web server ─────────────────────────────────────────────────────────────────

class WebServer(threading.Thread):
    """Web interface Server"""

    def __init__(self, port, database, modbus_servers, server_manager=None, debug=False):
        super().__init__()
        self._stop_event = threading.Event()
        self.app = FastAPI(
            title="modSim",
            description=(
                "A configurable Modbus TCP simulator with a browser-based UI and REST API.\n\n"
                "**Endpoint groups**\n"
                "- **Servers** — create, inspect, and delete Modbus server instances and their slave configurations\n"
                "- **Register Rules** — configure per-address simulation rules (add, update, delete individually or in bulk)\n"
                "- **Live Data** — read current register values and running-server status\n"
                "- **Import / Export** — backup and restore the full configuration as a single JSON file\n"
                "- **System** — restart the Modbus servers without restarting the process\n\n"
                "Interactive UI is served at **/**. "
                "Simulation modes: `random`, `static`, `sine`, `ramp`, `square`, `equation`."
            ),
            version="1.0.0",
            license_info={
                "name": "Apache 2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
            },
            openapi_url="/api/v1/openapi.json",
            docs_url="/api/v1/docs",
            openapi_tags=[
                {
                    "name": "Servers",
                    "description": "Manage Modbus server instances and slave configurations.",
                },
                {
                    "name": "Register Rules",
                    "description": "Manage per-address simulation rules. Rules take effect within one simulation cycle (~1 s) without a restart.",
                },
                {
                    "name": "Live Data",
                    "description": "Read the current state of running Modbus servers.",
                },
                {
                    "name": "Import / Export",
                    "description": "Backup and restore configuration. Selective export lets you choose which sections (servers, slaves, registers) to include.",
                },
                {
                    "name": "System",
                    "description": "Application-level operations.",
                },
            ],
        )
        self.daemon = True
        self.database = database
        self.modbus_servers = modbus_servers
        self.server_manager = server_manager
        self.debug = debug
        self.port = port

        # ── Routes ────────────────────────────────────────────────────────────
        self.app.add_api_route(
            path="/",
            endpoint=self.ui_handler,
            methods=["GET"],
            include_in_schema=False,
            response_class=FileResponse,
        )
        self.app.mount(
            "/static",
            StaticFiles(directory=str(_STATIC_DIR)),
            name="static",
        )

        # ── Live Data ─────────────────────────────────────────────────────────
        self.app.add_api_route(
            path="/status",
            endpoint=self.status_handler,
            methods=["GET"],
            tags=["Live Data"],
            summary="Running-server status",
            description="Returns the running state and basic info for every Modbus server instance.",
        )
        self.app.add_api_route(
            path="/live-values",
            endpoint=self.live_values_handler,
            methods=["GET"],
            tags=["Live Data"],
            summary="Live register snapshot",
            description="Reads the current value of every simulated register from every running slave. Polling this endpoint is the easiest way to observe the simulation in action.",
        )
        self.app.add_api_route(
            path="/get-context",
            endpoint=self.get_context_handler,
            methods=["GET"],
            tags=["Live Data"],
            summary="Raw Modbus context for a server",
            description="Returns the internal Modbus context object for the specified server. Useful for debugging register state.",
        )

        # ── Servers ───────────────────────────────────────────────────────────
        self.app.add_api_route(
            path="/configure-server",
            endpoint=self.configure_server_handler,
            methods=["POST"],
            tags=["Servers"],
            summary="Bulk configure servers and slaves",
            description=(
                "Replaces the entire server/slave configuration in one call. "
                "Accepts two formats:\n\n"
                "**Simplified** (`ip`, `port`, `instances`, `slaves`, `identity`, `register_sizes`) — "
                "all servers share the same identity; all slaves share the same register sizes.\n\n"
                "**Detailed** (`servers[]`, `slaves[]`) — full per-server and per-slave control. "
                "Triggers a Modbus server restart."
            ),
        )
        self.app.add_api_route(
            path="/get-server-config",
            endpoint=self.get_server_config_handler,
            methods=["GET"],
            tags=["Servers"],
            summary="Get all server and slave configurations",
            description="Returns the persisted server and slave records from the database.",
        )
        self.app.add_api_route(
            path="/servers/add",
            endpoint=self.add_server_handler,
            methods=["POST"],
            tags=["Servers"],
            summary="Add or upsert a single server",
            description="Inserts or replaces a single server record. Does not affect other servers. Triggers a Modbus server restart.",
        )
        self.app.add_api_route(
            path="/servers/{server_id}",
            endpoint=self.update_server_handler,
            methods=["PUT"],
            tags=["Servers"],
            summary="Update a server",
            description="Updates the fields of an existing server. The `server_id` in the URL takes precedence over any `server_id` in the body. Triggers a Modbus server restart.",
        )
        self.app.add_api_route(
            path="/servers/{server_id}",
            endpoint=self.delete_server_handler,
            methods=["DELETE"],
            tags=["Servers"],
            summary="Delete a server",
            description="Removes a server and all its slave records (cascades). Triggers a Modbus server restart.",
        )
        self.app.add_api_route(
            path="/slaves/{server_id}/{slave_id}",
            endpoint=self.update_slave_handler,
            methods=["PUT"],
            tags=["Servers"],
            summary="Update a slave",
            description="Updates the register sizes of an existing slave. Triggers a Modbus server restart.",
        )
        self.app.add_api_route(
            path="/slaves/{server_id}/{slave_id}",
            endpoint=self.delete_slave_handler,
            methods=["DELETE"],
            tags=["Servers"],
            summary="Delete a slave",
            description="Removes a slave from a server. Triggers a Modbus server restart.",
        )

        # ── Register Rules ────────────────────────────────────────────────────
        self.app.add_api_route(
            path="/configure-registers",
            endpoint=self.configure_registers_handler,
            methods=["POST"],
            tags=["Register Rules"],
            summary="Bulk replace all register rules",
            description=(
                "Drops all existing rules and replaces them with the supplied list. "
                "Use `/rules/add` to append a single rule without disturbing the rest."
            ),
        )
        self.app.add_api_route(
            path="/get-registers",
            endpoint=self.get_registers_handler,
            methods=["GET"],
            tags=["Register Rules"],
            summary="Get all register rules",
            description="Returns every simulation rule stored in the database, including the auto-assigned `id` field used by PUT/DELETE.",
        )
        self.app.add_api_route(
            path="/rules/add",
            endpoint=self.add_rule_handler,
            methods=["POST"],
            tags=["Register Rules"],
            summary="Add a single register rule",
            description="Appends one rule without touching existing rules. Returns the new rule's `id`. The rule takes effect within the next simulation cycle (~1 s).",
        )
        self.app.add_api_route(
            path="/rules/{rule_id}",
            endpoint=self.update_rule_handler,
            methods=["PUT"],
            tags=["Register Rules"],
            summary="Update a register rule",
            description="Replaces the fields of an existing rule identified by its database `id`.",
        )
        self.app.add_api_route(
            path="/rules/{rule_id}",
            endpoint=self.delete_rule_handler,
            methods=["DELETE"],
            tags=["Register Rules"],
            summary="Delete a register rule",
            description="Removes the rule with the given database `id`. Takes effect within the next simulation cycle.",
        )

        # ── Import / Export ───────────────────────────────────────────────────
        self.app.add_api_route(
            path="/export",
            endpoint=self.export_handler,
            methods=["GET"],
            tags=["Import / Export"],
            summary="Export configuration as JSON",
            description=(
                "Downloads a JSON file containing the selected sections. "
                "Use the `sections` query parameter to choose which sections to include "
                "(comma-separated: `servers`, `slaves`, `registers`). "
                "Defaults to all three sections."
            ),
        )
        self.app.add_api_route(
            path="/import",
            endpoint=self.import_handler,
            methods=["POST"],
            tags=["Import / Export"],
            summary="Import configuration from JSON",
            description=(
                "Imports configuration in one of two modes set by the `mode` field. "
                "`merge` (default) adds to the running config: servers/slaves are upserted "
                "by id and register rules by their natural key "
                "(server_id, slave_id, register_type, address, address_end), leaving anything "
                "not in the payload untouched — re-importing the same file is idempotent. "
                "`replace` wipes and replaces each supplied section wholesale. "
                "Either way, only sections present in the payload are touched — omit "
                "`servers`/`slaves` to import only register rules, or omit `registers` to "
                "import only topology. Server changes trigger a Modbus server restart."
            ),
        )

        # ── System ────────────────────────────────────────────────────────────
        self.app.add_api_route(
            path="/restart",
            endpoint=self.restart_handler,
            methods=["POST"],
            tags=["System"],
            summary="Restart Modbus servers",
            description="Stops and restarts all Modbus server threads using the current database configuration. The web server and simulation loop remain running.",
        )

    def run(self):
        logger.info("Web server started on port %s", self.port)
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            reload=True,
            log_config=None,
            log_level="debug" if self.debug else "error"
        )
        server = uvicorn.Server(config)
        server.run()

    def stop(self):
        self._stop_event.set()
        logger.info("Web server stopped")

    def stopped(self):
        return self._stop_event.is_set()

    # ── New handlers ──────────────────────────────────────────────────────────

    def ui_handler(self):
        """Serve the web configuration UI."""
        return FileResponse(str(_TEMPLATES_DIR / "index.html"))

    def status_handler(self):
        """Return a summary of running servers and configured objects."""
        try:
            servers = self.database.get_servers()
            slaves = self.database.get_slaves()
            registers = self.database.get_registers()
            return {
                "success": True,
                "servers_configured": len(servers),
                "slaves_configured": len(slaves),
                "registers_configured": len(registers),
                "servers_running": list(self.modbus_servers.keys()),
            }
        except Exception as e:
            logger.error("Error in status_handler: %s", e)
            return {"success": False, "message": str(e)}

    def live_values_handler(self, server_id: int = Query(0, description="Server ID")):
        """
        Return current Modbus register values for all simulated registers on a server.

        Reads the live Modbus context for each register rule that has an explicit
        address (skips 'all'-type bulk rules). Range rules (address_end set) return
        up to 50 values.
        """
        modbus_server = self.modbus_servers.get(server_id)
        if not modbus_server:
            return {"success": False, "message": f"Server {server_id} is not running"}

        reg_type_codes = {"co": 1, "di": 2, "hr": 3, "ir": 4}

        try:
            registers = self.database.get_registers()
            values = []

            for reg in registers:
                if reg.get("server_id") != server_id:
                    continue
                if not reg.get("simulate"):
                    continue

                slave_id = reg.get("slave_id")
                reg_type = reg.get("register_type")
                if reg_type not in reg_type_codes:
                    continue  # skip "all" bulk rules

                func_code = reg_type_codes[reg_type]
                addr_start = int(reg.get("address", 0))
                addr_end = reg.get("address_end")
                # Read from the 0-based datastore; report the user-facing address.
                addr_offset = 0 if getattr(modbus_server, "zero_based", True) else 1
                read_start = addr_start - addr_offset
                sim_config = reg.get("simulation_config") or {}
                use_float32 = bool(sim_config.get("float32")) and reg_type in ("hr", "ir")

                def _decode_float(hi, lo):
                    return round(struct.unpack('>f', struct.pack('>HH', hi, lo))[0], 6)

                try:
                    if addr_end is not None:
                        phys_count = min(int(addr_end) - addr_start + 1, 50)
                        raw = modbus_server.read_registers(slave_id, func_code, read_start, phys_count)
                        if use_float32:
                            for i in range(0, len(raw) - 1, 2):
                                values.append({
                                    "slave_id": slave_id,
                                    "register_type": reg_type,
                                    "address": addr_start + i,
                                    "value": _decode_float(raw[i], raw[i + 1]),
                                    "simulation_mode": reg.get("simulation_mode"),
                                    "float32": True,
                                })
                        else:
                            for i, v in enumerate(raw):
                                values.append({
                                    "slave_id": slave_id,
                                    "register_type": reg_type,
                                    "address": addr_start + i,
                                    "value": bool(v) if isinstance(v, bool) else int(v),
                                    "simulation_mode": reg.get("simulation_mode"),
                                })
                    else:
                        if use_float32:
                            raw = modbus_server.read_registers(slave_id, func_code, read_start, 2)
                            fval = _decode_float(raw[0], raw[1]) if len(raw) >= 2 else None
                            values.append({
                                "slave_id": slave_id,
                                "register_type": reg_type,
                                "address": addr_start,
                                "value": fval,
                                "simulation_mode": reg.get("simulation_mode"),
                                "float32": True,
                            })
                        else:
                            raw = modbus_server.read_registers(slave_id, func_code, read_start, 1)
                            v = raw[0] if raw else None
                            values.append({
                                "slave_id": slave_id,
                                "register_type": reg_type,
                                "address": addr_start,
                                "value": (
                                    bool(v) if isinstance(v, bool)
                                    else (int(v) if v is not None else None)
                                ),
                                "simulation_mode": reg.get("simulation_mode"),
                            })
                except Exception as e:
                    values.append({
                        "slave_id": slave_id,
                        "register_type": reg_type,
                        "address": addr_start,
                        "value": f"ERR: {e}",
                        "simulation_mode": reg.get("simulation_mode"),
                    })

            return {"success": True, "server_id": server_id, "values": values}
        except Exception as e:
            logger.error("Error in live_values_handler: %s", e)
            return {"success": False, "message": str(e)}

    # ── Existing handlers (unchanged) ─────────────────────────────────────────

    def configure_server_handler(self, config: Union[ServerConfig, DetailedServerConfig]):
        """
        Configure Modbus server instances and slaves.

        This endpoint accepts two formats:

        1. Simplified format (settings.json style):
           - instances: Number of Modbus server instances to create
           - slaves: Number of slaves per server instance
           - ip: IP address to bind to
           - port: Base port (each instance gets port + instance_id)
           - identity: Modbus identity information
           - register_sizes: Default register sizes for each type (co, di, hr, ir)

        2. Detailed format (same as get-server-config returns):
           - servers: List of server configurations with individual settings
           - slaves: List of slave configurations with individual register sizes
        """
        try:
            if isinstance(config, DetailedServerConfig):
                servers = [server.model_dump() for server in config.servers]
                slaves = [slave.model_dump() for slave in config.slaves]
            else:
                servers = []
                slaves = []

                for server_id in range(config.instances):
                    servers.append({
                        "server_id": server_id,
                        "ip": config.ip,
                        "port": config.port + server_id,
                        "vendor_name": config.identity.VendorName,
                        "product_code": config.identity.ProductCode,
                        "version": config.identity.MajorMinorRevision,
                        "zero_based": config.zero_based
                    })

                    for slave_id in range(config.slaves):
                        slaves.append({
                            "server_id": server_id,
                            "slave_id": slave_id,
                            "co_size": config.register_sizes.co,
                            "di_size": config.register_sizes.di,
                            "hr_size": config.register_sizes.hr,
                            "ir_size": config.register_sizes.ir
                        })

            result = self.database.save_server_config(servers, slaves)

            if not result["success"]:
                return {"success": False, "message": result["errors"]}

            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                if isinstance(config, DetailedServerConfig):
                    return {
                        "success": True,
                        "message": f"Configuration updated: {len(servers)} server(s) with {len(slaves)} slave(s). Modbus servers restarted."
                    }
                else:
                    return {
                        "success": True,
                        "message": f"Created {config.instances} server(s) with {config.slaves} slave(s) each. Modbus servers restarted."
                    }
            else:
                if isinstance(config, DetailedServerConfig):
                    return {
                        "success": True,
                        "message": f"Configuration saved: {len(servers)} server(s) with {len(slaves)} slave(s). Restart application to apply changes."
                    }
                else:
                    return {
                        "success": True,
                        "message": f"Configuration saved: {config.instances} server(s) with {config.slaves} slave(s) each. Restart application to apply changes."
                    }

        except Exception as e:
            logger.error(f"Error configuring server: {e}")
            return {"success": False, "message": str(e)}

    def get_server_config_handler(self):
        """
        Get current server and slave configuration from database.

        Returns the current configuration of all Modbus server instances and their slaves.
        """
        try:
            servers = self.database.get_servers()
            slaves = self.database.get_slaves()
            return {
                "success": True,
                "servers": servers,
                "slaves": slaves
            }
        except Exception as e:
            logger.error(f"Error getting server config: {e}")
            return {"success": False, "message": str(e)}

    def configure_registers_handler(self, config: RegisterConfig):
        """
        Configure register simulation settings.

        Allows configuration of individual registers or ranges with various simulation modes:
        - random: Random values within a range
        - static: Fixed value
        - sine: Sine wave pattern
        - ramp: Linear ramp between min and max
        - equation: Custom equation-based simulation
        - square: Square wave (for coils/discrete inputs)
        """
        try:
            result = self.database.save_registers(config.registers)

            if not result["success"]:
                return {"success": False, "message": result["errors"]}

            return {"success": True, "message": "Registers configured."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_registers_handler(self):
        """
        Get all configured register simulation settings.

        Returns all register configurations currently stored in the database.
        """
        try:
            registers = self.database.get_registers()
            if registers:
                return {"success": True, "registers": registers}
            return {"success": False, "message": "No registers found."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_context_handler(self, server_id: int = Query(..., description="Server ID to get context for")):
        """Get Modbus server context for a specific server instance."""
        try:
            self.modbus_server = self.modbus_servers.get(server_id)
            if not self.modbus_server:
                return {"success": False, "message": "Server not found."}

            context = self.modbus_server.get_context()

            return {"success": True, "context": context}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Per-rule register management ──────────────────────────────────────────

    def update_rule_handler(self, rule_id: int, rule: SingleRegisterRule):
        """Update an existing register rule by id."""
        try:
            result = self.database.update_register(rule_id, rule.model_dump())
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            if not result["updated"]:
                return {"success": False, "message": f"Rule {rule_id} not found."}
            return {"success": True, "message": f"Rule {rule_id} updated."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def update_server_handler(self, server_id: int, server: ServerItem):
        """Update an existing server entry."""
        try:
            data = server.model_dump()
            data["server_id"] = server_id
            result = self.database.upsert_server(data)
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                msg = f"Server {server_id} updated and Modbus servers restarted."
            else:
                msg = f"Server {server_id} updated. Restart application to apply."
            return {"success": True, "message": msg}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def update_slave_handler(self, server_id: int, slave_id: int, slave: SlaveItem):
        """Update an existing slave's register sizes."""
        try:
            data = slave.model_dump()
            data["server_id"] = server_id
            data["slave_id"] = slave_id
            result = self.database.upsert_slave(data)
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                msg = f"Slave {server_id}/{slave_id} updated and Modbus servers restarted."
            else:
                msg = f"Slave {server_id}/{slave_id} updated. Restart application to apply."
            return {"success": True, "message": msg}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def delete_slave_handler(self, server_id: int, slave_id: int):
        """Delete a slave from a server."""
        try:
            result = self.database.delete_slave(server_id, slave_id)
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            if not result["deleted"]:
                return {"success": False, "message": f"Slave {server_id}/{slave_id} not found."}
            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                msg = f"Slave {server_id}/{slave_id} deleted and Modbus servers restarted."
            else:
                msg = f"Slave {server_id}/{slave_id} deleted. Restart application to apply."
            return {"success": True, "message": msg}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def add_rule_handler(self, rule: SingleRegisterRule):
        """Add a single register simulation rule without replacing existing ones."""
        try:
            result = self.database.add_register(rule.model_dump())
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            return {"success": True, "id": result["id"], "message": f"Rule {result['id']} added."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def delete_rule_handler(self, rule_id: int):
        """Delete a single register rule by its database id."""
        try:
            result = self.database.delete_register(rule_id)
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            if not result["deleted"]:
                return {"success": False, "message": f"Rule {rule_id} not found."}
            return {"success": True, "message": f"Rule {rule_id} deleted."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Per-server management ─────────────────────────────────────────────────

    def add_server_handler(self, server: ServerItem):
        """Add or update a single server entry."""
        try:
            result = self.database.upsert_server(server.model_dump())
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                msg = f"Server {server.server_id} saved and Modbus servers restarted."
            else:
                msg = f"Server {server.server_id} saved. Restart application to apply."
            return {"success": True, "message": msg}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def delete_server_handler(self, server_id: int):
        """Delete a server and its slave configurations."""
        try:
            result = self.database.delete_server(server_id)
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            if not result["deleted"]:
                return {"success": False, "message": f"Server {server_id} not found."}
            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                msg = f"Server {server_id} deleted and Modbus servers restarted."
            else:
                msg = f"Server {server_id} deleted. Restart application to apply."
            return {"success": True, "message": msg}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Import / Export ───────────────────────────────────────────────────────

    def export_handler(self, sections: str = Query("servers,slaves,registers", description="Comma-separated sections to export")):
        """Export configuration as JSON. Use ?sections= to limit: servers, slaves, registers."""""
        try:
            wanted = {s.strip() for s in sections.split(",")}
            payload = {}
            if "servers"   in wanted: payload["servers"]   = self.database.get_servers()
            if "slaves"    in wanted: payload["slaves"]    = self.database.get_slaves()
            if "registers" in wanted: payload["registers"] = self.database.get_registers()
            return JSONResponse(
                content=payload,
                headers={"Content-Disposition": 'attachment; filename="modsim-config.json"'},
            )
        except Exception as e:
            return {"success": False, "message": str(e)}

    def restart_handler(self):
        """Restart all running Modbus servers."""
        try:
            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                return {"success": True, "message": "Modbus servers restarted."}
            return {"success": False, "message": "No server manager available — restart the application manually."}
        except Exception as e:
            logger.error("Error in restart_handler: %s", e)
            return {"success": False, "message": str(e)}

    def import_handler(self, payload: ImportPayload):
        """Import configuration in one of two modes.

        - mode="merge" (default): upsert servers/slaves by id and register rules
          by their natural key. Anything not named in the payload is left as-is,
          so this adds to (or syncs with) the running configuration.
        - mode="replace": wipe and replace each supplied section wholesale.

        Either way, only sections present in the payload are touched — omit
        'servers'/'slaves' to import only registers, and vice versa.
        """
        try:
            mode = (payload.mode or "merge").lower()
            if mode not in ("merge", "replace"):
                return {"success": False, "message": f"Unknown import mode '{payload.mode}'."}

            registers = list(payload.registers)
            for reg in registers:
                if isinstance(reg, dict):
                    reg.pop("id", None)

            if mode == "replace":
                return self._import_replace(list(payload.servers), list(payload.slaves), registers)
            return self._import_merge(list(payload.servers), list(payload.slaves), registers)
        except Exception as e:
            logger.error("Error in import_handler: %s", e)
            return {"success": False, "message": str(e)}

    def _import_replace(self, servers, slaves, registers):
        """Original behaviour: replace each supplied section wholesale."""
        parts = []
        restarted = False

        if servers or slaves:
            result = self.database.save_server_config(servers, slaves)
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            parts.append(f"{len(servers)} server(s), {len(slaves)} slave(s)")
            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                restarted = True

        if registers:
            reg_result = self.database.save_registers(registers)
            if not reg_result["success"]:
                return {"success": False, "message": reg_result["errors"]}
            parts.append(f"{len(registers)} register rule(s)")

        if not parts:
            return {"success": False, "message": "Payload contained no recognisable sections."}

        suffix = " Modbus servers restarted." if restarted else ""
        return {"success": True, "message": "Replaced " + ", ".join(parts) + "." + suffix}

    def _import_merge(self, servers, slaves, registers):
        """Additive import: upsert servers/slaves by id and rules by natural key."""
        parts = []
        restarted = False

        for server in servers:
            result = self.database.upsert_server(server)
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
        for slave in slaves:
            result = self.database.upsert_slave(slave)
            if not result["success"]:
                return {"success": False, "message": result["errors"]}
        if servers or slaves:
            parts.append(f"{len(servers)} server(s), {len(slaves)} slave(s)")
            if self.server_manager:
                self.server_manager.restart_modbus_servers()
                restarted = True

        if registers:
            added = updated = 0
            for reg in registers:
                result = self.database.upsert_register(reg)
                if not result["success"]:
                    return {"success": False, "message": result["errors"]}
                if result["action"] == "added":
                    added += 1
                else:
                    updated += 1
            parts.append(f"{added} rule(s) added, {updated} updated")

        if not parts:
            return {"success": False, "message": "Payload contained no recognisable sections."}

        suffix = " Modbus servers restarted." if restarted else ""
        return {"success": True, "message": "Merged " + ", ".join(parts) + "." + suffix}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format=("%(asctime)s - %(levelname)-8s - %(name)-20s:%(lineno)5d - %(message)s"),
    )
    parser = argparse.ArgumentParser(description="modSim Web Interface")
    parser.add_argument("--debug", "-d", action="store_true", help="Debugging enable")
    parser.add_argument("--port", "-p", default=8000, type=int, help="Web server port number")
    args = parser.parse_args()

    server = WebServer(args.port, None, {}, debug=args.debug)
    server.start()
    server.join()
