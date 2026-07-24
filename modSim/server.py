import json
import time
import os
import logging

from modSim.database import Database
from modSim.modbus import Server as ModbusServer
from modSim.utils import SignalHandler
from modSim.web import WebServer

logger = logging.getLogger(__name__)

class Server:
    def __init__(self):
        self.signal_handler = SignalHandler()
        self.database = Database()
        self.settings_file = "settings.json"

        # Load initial settings from JSON file or create defaults
        self.settings = self.load_settings()

        # Initialize database with default config if empty
        self._initialize_database_from_settings()

        # Start Modbus servers from database configuration
        self.modbus_servers = {}
        self._start_modbus_servers()

        # Start the web server
        self.web_server = WebServer(
            self.settings["web"]["port"],
            database=self.database,
            modbus_servers=self.modbus_servers,
            server_manager=self
        )
        self.web_server.start()

    def _initialize_database_from_settings(self):
        """Initialize database with default configuration from settings.json if database is empty"""
        servers = self.database.get_servers()

        # If database is empty, populate from settings.json
        if not servers:
            logger.info("Database empty, initializing from settings.json")

            # Create server configurations
            default_servers = []
            default_slaves = []
            default_registers = []

            instances = self.settings["modbus"].get("instances", 1)
            base_port = self.settings["modbus"].get("port", 502)
            ip = self.settings["modbus"].get("ip", "0.0.0.0")
            identity = self.settings["modbus"].get("identity", {})
            num_slaves = self.settings["modbus"].get("slaves", 1)
            register_sizes = self.settings["modbus"].get("register_sizes", {})

            for server_id in range(instances):
                default_servers.append({
                    "server_id": server_id,
                    "ip": ip,
                    "port": base_port + server_id,
                    "vendor_name": identity.get("VendorName", "ModbusSimulator"),
                    "product_code": identity.get("ProductCode", "MSIM"),
                    "version": identity.get("MajorMinorRevision", "1.0"),
                    "zero_based": self.settings["modbus"].get("zero_based", True)
                })

                # Create slaves for this server
                for slave_id in range(num_slaves):
                    default_slaves.append({
                        "server_id": server_id,
                        "slave_id": slave_id,
                        "co_size": register_sizes.get("co", 100),
                        "di_size": register_sizes.get("di", 100),
                        "hr_size": register_sizes.get("hr", 100),
                        "ir_size": register_sizes.get("ir", 100)
                    })

            # Save server and slave configuration
            result = self.database.save_server_config(default_servers, default_slaves)
            if not result["success"]:
                logger.error(f"Failed to save server config: {result['errors']}")
            else:
                logger.debug("Server configuration saved to database")

            # Handle register configuration from settings
            if self.settings["modbus"].get("config", {}).get("registers"):
                try:
                    # Expand register configs that don't have server_id to all servers
                    explicit_server_ids = set()
                    explicit_configs = []
                    default_configs = []

                    for reg_config in self.settings["modbus"]["config"]["registers"]:
                        if "server_id" in reg_config:
                            explicit_server_ids.add(reg_config["server_id"])
                            explicit_configs.append(reg_config)
                        else:
                            default_configs.append(reg_config)

                    # Apply default configs to servers that don't have explicit configs
                    expanded_registers = explicit_configs.copy()
                    for reg_config in default_configs:
                        for server_id in range(instances):
                            if server_id not in explicit_server_ids:
                                expanded_config = reg_config.copy()
                                expanded_config["server_id"] = server_id
                                expanded_registers.append(expanded_config)

                    result = self.database.save_registers(expanded_registers)
                    if not result["success"]:
                        logger.error(f"Failed to config registers: {result['errors']}")
                    else:
                        logger.debug("Registers configured successfully.")
                except Exception as e:
                    logger.error(f"Error configuring registers: {str(e)}")

    def _start_modbus_servers(self):
        """Start Modbus servers based on database configuration"""
        servers = self.database.get_servers()

        for server_config in servers:
            server_id = server_config["server_id"]
            slaves = self.database.get_slaves(server_id)

            # Build register_sizes dict from first slave (assuming all slaves have same sizes)
            register_sizes = None
            if slaves:
                first_slave = slaves[0]
                register_sizes = {
                    "co": first_slave["co_size"],
                    "di": first_slave["di_size"],
                    "hr": first_slave["hr_size"],
                    "ir": first_slave["ir_size"]
                }

            identity = {
                "VendorName": server_config["vendor_name"],
                "ProductCode": server_config["product_code"],
                "MajorMinorRevision": server_config["version"]
            }

            self.modbus_servers[server_id] = ModbusServer(
                server_id,
                server_config["ip"],
                server_config["port"],
                identity,
                len(slaves),  # number of slaves (legacy count; slaves= below wins)
                100,  # deprecated registers parameter (kept for compatibility)
                register_sizes,
                zero_based=server_config.get("zero_based", True),
                slaves=slaves,  # real slave ids + per-slave register sizes
            )
            self.modbus_servers[server_id].start()
            logger.info(f"Started Modbus server {server_id} on {server_config['ip']}:{server_config['port']} with {len(slaves)} slave(s)")

    def restart_modbus_servers(self):
        """Stop and restart all Modbus servers with current database configuration"""
        logger.info("Restarting Modbus servers...")

        # Stop existing servers and wait for their threads to fully exit so
        # the listening sockets are released before we rebind the same ports.
        for server in self.modbus_servers.values():
            server.stop()
            server.join(timeout=10)
            if server.is_alive():
                logger.warning("Modbus server %s thread did not exit within timeout",
                               server.serverId)

        self.modbus_servers.clear()

        # Start servers with new configuration
        self._start_modbus_servers()

        logger.info("Modbus servers restarted successfully")

    def load_settings(self):
        """
        Load settings from the settings.json file. If the file does not exist,
        create it with default values and return those values.
        """
        if os.path.exists(self.settings_file):
            with open(self.settings_file, "r") as file:
                return json.load(file)
        
        # Default settings
        default_settings = {
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
                    "registers": [{
                        "slave_id": 0,
                        "register_type": "all",
                        "simulate": True
                    }]
                }
            },
            "web": {
                "port": 8000
            }
        }
        
        # Save default settings to a file
        self.save_settings(default_settings)
        return default_settings

    def save_settings(self, settings):
        """Save settings to the settings.json file."""
        with open(self.settings_file, "w") as file:
            json.dump(settings, file, indent=4)

    def stop_servers(self):
        """Stop all servers."""
        for server in self.modbus_servers.values():
            server.stop()
        self.web_server.stop()

    def run(self):
        """ Main loop """
        while not self.signal_handler.stop:
            for server in self.modbus_servers.values():
                server.simulate(self.database.get_registers())
            time.sleep(1)

        self.stop_servers()

if __name__ == "__main__":
    server = Server()
    server.run()
