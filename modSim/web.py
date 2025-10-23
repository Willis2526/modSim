import argparse
from pydantic import BaseModel
import logging
import threading
from typing import Union

import uvicorn
from fastapi import FastAPI, Query

logger = logging.getLogger(__name__)

logging.getLogger("asyncio").setLevel(logging.WARNING)

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
    identity: ModbusIdentity = ModbusIdentity()
    register_sizes: RegisterSizes = RegisterSizes()

    class Config:
        json_schema_extra = {
            "example": {
                "ip": "0.0.0.0",
                "port": 502,
                "instances": 2,
                "slaves": 3,
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

    class Config:
        json_schema_extra = {
            "example": {
                "server_id": 0,
                "ip": "0.0.0.0",
                "port": 502,
                "vendor_name": "ModbusSimulator",
                "product_code": "MSIM",
                "version": "1.0"
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

class WebServer(threading.Thread):
    """Web interface Server"""

    def __init__(self, port, database, modbus_servers, server_manager=None, debug=False):
        super().__init__()
        self._stop_event = threading.Event()
        self.app = FastAPI(
            title="modSim",
            description="A configurable modbus simulator.",
            version="0.0.1",
            license_info={
                "name": "Apache 2.0",
                "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
            },
            openapi_url="/api/v1/openapi.json",
            docs_url="/api/v1/docs",
        )
        self.daemon = True
        self.database = database
        self.modbus_servers = modbus_servers
        self.server_manager = server_manager
        self.debug = debug
        self.port = port

        # Setup endpoints
        self.app.add_api_route(
            path="/configure-server",
            endpoint=self.configure_server_handler,
            methods=["POST"],
            include_in_schema=True,
        )
        self.app.add_api_route(
            path="/get-server-config",
            endpoint=self.get_server_config_handler,
            methods=["GET"],
            include_in_schema=True,
        )
        self.app.add_api_route(
            path="/configure-registers",
            endpoint=self.configure_registers_handler,
            methods=["POST"],
            include_in_schema=True,
        )
        self.app.add_api_route(
            path="/get-registers",
            endpoint=self.get_registers_handler,
            methods=["GET"],
            include_in_schema=True,
        )
        self.app.add_api_route(
            path="/get-context",
            endpoint=self.get_context_handler,
            methods=["GET"],
            include_in_schema=True,
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
        """When called, sets the stop event"""
        self._stop_event.set()
        logger.info("Web server stopped")

    def stopped(self):
        """Returns true when stop is called"""
        return self._stop_event.is_set()

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
            # Check which format was provided
            if isinstance(config, DetailedServerConfig):
                # Detailed format: convert Pydantic models to dictionaries
                servers = [server.model_dump() for server in config.servers]
                slaves = [slave.model_dump() for slave in config.slaves]
            else:
                # Simplified format: expand into detailed server and slave configurations
                servers = []
                slaves = []

                for server_id in range(config.instances):
                    servers.append({
                        "server_id": server_id,
                        "ip": config.ip,
                        "port": config.port + server_id,
                        "vendor_name": config.identity.VendorName,
                        "product_code": config.identity.ProductCode,
                        "version": config.identity.MajorMinorRevision
                    })

                    # Create slaves for this server
                    for slave_id in range(config.slaves):
                        slaves.append({
                            "server_id": server_id,
                            "slave_id": slave_id,
                            "co_size": config.register_sizes.co,
                            "di_size": config.register_sizes.di,
                            "hr_size": config.register_sizes.hr,
                            "ir_size": config.register_sizes.ir
                        })

            # Validate and save configuration to database
            result = self.database.save_server_config(servers, slaves)

            if not result["success"]:
                return {"success": False, "message": result["errors"]}

            # Restart Modbus servers with new configuration
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
            # Save registers to the database
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

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format=("%(asctime)s - %(levelname)-8s - %(name)-20s:%(lineno)5d - %(message)s"),
    )
    # Parse the arguments for the options
    parser = argparse.ArgumentParser(description="PLC MQTT Web Interface")
    parser.add_argument("--debug", "-d", action="store_true", help="Debugging enable")
    parser.add_argument("--port", "-p", default=5000, type=int, help="Web server port number")
    args = parser.parse_args()

    server = WebServer(args.port, None, num_relays=args.num_relays, debug=args.debug)
    server.start()
    server.join()
