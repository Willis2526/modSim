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

        # Start Modbus server
        instanceNumber = 0
        self.modbus_servers = {}

        while instanceNumber < self.settings["modbus"]["instances"]:
            port = self.settings["modbus"]["port"] + instanceNumber
            self.modbus_servers[instanceNumber] = ModbusServer(
                instanceNumber,
                self.settings["modbus"]["ip"],
                port,
                self.settings["modbus"]["identity"],
                self.settings["modbus"]["slaves"],
                self.settings["modbus"]["registers"]
            )
            self.modbus_servers[instanceNumber].start()
            instanceNumber += 1

        if self.settings["modbus"].get("config"):
            if self.settings["modbus"]["config"].get("registers"):
                try:
                    # Expand register configs that don't have server_id to all servers
                    # First, collect all server_ids that have explicit configs
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
                        for server_id in range(self.settings["modbus"]["instances"]):
                            if server_id not in explicit_server_ids:
                                expanded_config = reg_config.copy()
                                expanded_config["server_id"] = server_id
                                expanded_registers.append(expanded_config)

                    result = self.database.save_registers(expanded_registers)

                    if not result["success"]:
                        logger.error("Failed to config registers: {}".format(result["errors"]))
                    else:
                        logger.debug("Registers configured successfully.")

                except Exception as e:
                    logger.error("Error configuring registers: {}".format(str(e)))

        # Start the web server
        self.web_server = WebServer(
            self.settings["web"]["port"],
            database=self.database,
            modbus_servers=self.modbus_servers,
        )
        self.web_server.start()

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
