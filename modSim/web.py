import argparse
from pydantic import BaseModel
import logging
import threading

import uvicorn
from fastapi import FastAPI

logger = logging.getLogger(__name__)

logging.getLogger("asyncio").setLevel(logging.WARNING)

class ServerConfig(BaseModel):
    ip: str
    port: int
    identity: dict  # Modbus identity as a dictionary

    class Config:
        json_schema_extra = {
            "example": {
                "ip": "0.0.0.0",
                "port": 502,
                "identity": {
                    "VendorName": "ModbusSimulator",
                    "ProductCode": "MSIM",
                    "MajorMinorRevision": "1.0"
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
                        "simulate": True
                    },
                    {
                        "server_id": 0,
                        "slave_id": 1,
                        "register_type": "hr",
                        "address": 0,
                        "address_end": 50,
                        "simulate": True
                    },
                    {
                        "server_id": 0,
                        "slave_id": 1,
                        "register_type": "co",
                        "register_size": 200,
                        "simulate": True
                    }
                ]
            }
        }

class WebServer(threading.Thread):
    """Web interface Server"""

    def __init__(self, port, database, modbus_servers, debug=False):
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

    def configure_server_handler(self, config: ServerConfig):
        try:
            raise NotImplementedError("Configure server handler not implemented.")
            self.database.save_settings({
                "ip": config.ip,
                "port": config.port,
                "identity": config.identity
            })
            self.settings = self.database.get_settings()
            self.restart_server()
            return {"success": True, "message": "Server configuration updated and server restarted."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_server_config_handler(self):
        try:
            config = [s.getDetails() for s in self.modbus_servers.values()]
            return {"success": True, "config": config}
        except Exception as e:
            return {"success": False, "message": str(e)}
        
    def configure_registers_handler(self, config: RegisterConfig):
        try:
            # Save registers to the database
            result = self.database.save_registers(config.registers)

            if not result["success"]:
                return {"success": False, "message": result["errors"]}
            
            return {"success": True, "message": "Registers configured."}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_registers_handler(self):
        try:
            registers = self.database.get_registers()
            if registers:
                return {"success": True, "registers": registers}
            return {"success": False, "message": "No registers found."}
        except Exception as e:
            return {"success": False, "message": str(e)}
        
    def get_context_handler(self, server_id: int):
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
