import sqlite3
import os
import json
import logging

logger = logging.getLogger("DatabaseLogger")

class Database:
    def __init__(self, db_path="settings.db"):
        self.db_path = db_path
        self._initialize_database()

    def _get_connection(self):
        """Get a database connection with foreign keys enabled"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _initialize_database(self):
        try:
            conn = sqlite3.connect(self.db_path)
            try:
                cursor = conn.cursor()

                # Enable foreign keys
                cursor.execute("PRAGMA foreign_keys = ON")

                # Create servers table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS servers (
                        server_id INTEGER PRIMARY KEY,
                        ip TEXT NOT NULL DEFAULT '0.0.0.0',
                        port INTEGER NOT NULL,
                        vendor_name TEXT DEFAULT 'ModbusSimulator',
                        product_code TEXT DEFAULT 'MSIM',
                        version TEXT DEFAULT '1.0',
                        zero_based INTEGER NOT NULL DEFAULT 1
                    )
                    """
                )

                # Migrate older databases that predate the zero_based column
                cursor.execute("PRAGMA table_info(servers)")
                server_columns = {row[1] for row in cursor.fetchall()}
                if "zero_based" not in server_columns:
                    cursor.execute(
                        "ALTER TABLE servers ADD COLUMN zero_based INTEGER NOT NULL DEFAULT 1"
                    )

                # Create slaves table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS slaves (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id INTEGER NOT NULL,
                        slave_id INTEGER NOT NULL,
                        co_size INTEGER DEFAULT 100,
                        di_size INTEGER DEFAULT 100,
                        hr_size INTEGER DEFAULT 100,
                        ir_size INTEGER DEFAULT 100,
                        UNIQUE(server_id, slave_id),
                        FOREIGN KEY (server_id) REFERENCES servers(server_id) ON DELETE CASCADE
                    )
                    """
                )

                # Create registers table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS registers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id INTEGER NULL,         -- Server ID
                        slave_id INTEGER NOT NULL,      -- Slave ID associated with the register
                        register_type TEXT NOT NULL,    -- Type of register (e.g., 'hr', 'ir', 'co', 'di')
                        address INTEGER NOT NULL,       -- Start address of the register (or 0 for all)
                        address_end INTEGER NULL,       -- End address for range simulation (NULL for single address)
                        register_size INTEGER NULL,     -- Size of register type (NULL to use server default)
                        simulate INTEGER NOT NULL,      -- Whether the register is simulated (0 or 1)
                        simulation_mode TEXT DEFAULT 'random',  -- Simulation mode: random, static, equation, ramp, sine, square
                        simulation_config TEXT NULL     -- JSON config for simulation mode parameters
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")

    def get_registers(self):
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id, server_id, slave_id, register_type, address, address_end, "
                    "register_size, simulate, simulation_mode, simulation_config FROM registers"
                )
                results = cursor.fetchall()
                return [
                    {
                        "id": row[0],
                        "server_id": row[1],
                        "slave_id": row[2],
                        "register_type": row[3],
                        "address": row[4],
                        "address_end": row[5],
                        "register_size": row[6],
                        "simulate": bool(row[7]),
                        "simulation_mode": row[8] if row[8] else "random",
                        "simulation_config": json.loads(row[9]) if row[9] else {}
                    }
                    for row in results
                ]
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error fetching registers: {e}")
            return []

    def add_register(self, rule: dict) -> dict:
        """Insert a single register rule. Returns {"success": bool, "id": int|None, "errors": list}"""
        errors = []
        slave_id = rule.get("slave_id")
        register_type = rule.get("register_type")
        if slave_id is None:
            errors.append("Missing slave_id")
        if not register_type:
            errors.append("Missing register_type")
        if errors:
            return {"success": False, "id": None, "errors": errors}
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                sim_config = rule.get("simulation_config") or {}
                cursor.execute(
                    """INSERT INTO registers
                       (server_id, slave_id, register_type, address, address_end,
                        register_size, simulate, simulation_mode, simulation_config)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rule.get("server_id", None),
                        slave_id,
                        register_type,
                        rule.get("address", 0),
                        rule.get("address_end", None),
                        rule.get("register_size", None),
                        int(rule.get("simulate", False)),
                        rule.get("simulation_mode", "random"),
                        json.dumps(sim_config),
                    )
                )
                new_id = cursor.lastrowid
                conn.commit()
                return {"success": True, "id": new_id, "errors": []}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error adding register: {e}")
            return {"success": False, "id": None, "errors": [str(e)]}

    def update_register(self, rule_id: int, rule: dict) -> dict:
        """Update an existing register rule by its primary key id."""
        errors = []
        slave_id = rule.get("slave_id")
        register_type = rule.get("register_type")
        if slave_id is None:
            errors.append("Missing slave_id")
        if not register_type:
            errors.append("Missing register_type")
        if errors:
            return {"success": False, "updated": False, "errors": errors}
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                sim_config = rule.get("simulation_config") or {}
                cursor.execute(
                    """UPDATE registers SET
                       server_id=?, slave_id=?, register_type=?, address=?, address_end=?,
                       register_size=?, simulate=?, simulation_mode=?, simulation_config=?
                       WHERE id=?""",
                    (
                        rule.get("server_id", None),
                        slave_id,
                        register_type,
                        rule.get("address", 0),
                        rule.get("address_end", None),
                        rule.get("register_size", None),
                        int(rule.get("simulate", False)),
                        rule.get("simulation_mode", "random"),
                        json.dumps(sim_config),
                        rule_id,
                    )
                )
                conn.commit()
                return {"success": True, "updated": cursor.rowcount > 0, "errors": []}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error updating register {rule_id}: {e}")
            return {"success": False, "updated": False, "errors": [str(e)]}

    def delete_register(self, rule_id: int) -> dict:
        """Delete one register rule by its primary key id."""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM registers WHERE id = ?", (rule_id,))
                conn.commit()
                return {"success": True, "deleted": cursor.rowcount > 0, "errors": []}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error deleting register {rule_id}: {e}")
            return {"success": False, "deleted": False, "errors": [str(e)]}

    def upsert_server(self, server: dict) -> dict:
        """Insert or replace one server row."""
        server_id = server.get("server_id")
        port = server.get("port")
        if server_id is None:
            return {"success": False, "errors": ["Missing server_id"]}
        if port is None:
            return {"success": False, "errors": ["Missing port"]}
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO servers
                       (server_id, ip, port, vendor_name, product_code, version, zero_based)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        server_id,
                        server.get("ip", "0.0.0.0"),
                        port,
                        server.get("vendor_name", "ModbusSimulator"),
                        server.get("product_code", "MSIM"),
                        server.get("version", "1.0"),
                        int(server.get("zero_based", True)),
                    )
                )
                conn.commit()
                return {"success": True, "errors": []}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error upserting server {server_id}: {e}")
            return {"success": False, "errors": [str(e)]}

    def upsert_slave(self, slave: dict) -> dict:
        """Insert or replace one slave row."""
        server_id = slave.get("server_id")
        slave_id = slave.get("slave_id")
        if server_id is None:
            return {"success": False, "errors": ["Missing server_id"]}
        if slave_id is None:
            return {"success": False, "errors": ["Missing slave_id"]}
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO slaves
                       (server_id, slave_id, co_size, di_size, hr_size, ir_size)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        server_id, slave_id,
                        slave.get("co_size", 100),
                        slave.get("di_size", 100),
                        slave.get("hr_size", 100),
                        slave.get("ir_size", 100),
                    )
                )
                conn.commit()
                return {"success": True, "errors": []}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error upserting slave {server_id}/{slave_id}: {e}")
            return {"success": False, "errors": [str(e)]}

    def delete_server(self, server_id: int) -> dict:
        """Delete a server and its slaves (CASCADE). Register rules with this server_id remain."""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM servers WHERE server_id = ?", (server_id,))
                conn.commit()
                return {"success": True, "deleted": cursor.rowcount > 0, "errors": []}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error deleting server {server_id}: {e}")
            return {"success": False, "deleted": False, "errors": [str(e)]}

    def delete_slave(self, server_id: int, slave_id: int) -> dict:
        """Delete a slave by server_id and slave_id."""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM slaves WHERE server_id = ? AND slave_id = ?",
                    (server_id, slave_id)
                )
                conn.commit()
                return {"success": True, "deleted": cursor.rowcount > 0, "errors": []}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error deleting slave {server_id}/{slave_id}: {e}")
            return {"success": False, "deleted": False, "errors": [str(e)]}

    def save_registers(self, registers):
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                # Clear existing registers
                cursor.execute("DELETE FROM registers")
                # Insert new registers

                errors = []

                for reg in registers:
                    server_id = reg.get("server_id", None)
                    slave_id = reg.get("slave_id")
                    register_type = reg.get("register_type")
                    address = reg.get("address", 0)
                    address_end = reg.get("address_end", None)
                    register_size = reg.get("register_size", None)
                    simulate = int(reg.get("simulate", False))
                    simulation_mode = reg.get("simulation_mode", "random")
                    simulation_config = reg.get("simulation_config", {})
                    # Convert None to empty dict
                    if simulation_config is None:
                        simulation_config = {}

                    if slave_id is None:
                        errors.append("Missing slave_id")

                    if not register_type:
                        errors.append("Missing register_type")

                    if errors:
                         return {"success": False, "errors": errors}

                    cursor.execute(
                        """
                        INSERT INTO registers (server_id, slave_id, register_type, address, address_end, register_size, simulate, simulation_mode, simulation_config)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (server_id, slave_id, register_type, address, address_end, register_size, simulate, simulation_mode, json.dumps(simulation_config))
                    )

                conn.commit()
                return {"success": True, "errors": []}
            finally:
                conn.close()

        except sqlite3.Error as e:
            logger.error(f"Error saving registers: {e}")
            return {"success": False, "errors": [str(e)]}

    def get_servers(self):
        """Get all server configurations"""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT server_id, ip, port, vendor_name, product_code, version, zero_based FROM servers ORDER BY server_id")
                results = cursor.fetchall()
                return [
                    {
                        "server_id": row[0],
                        "ip": row[1],
                        "port": row[2],
                        "vendor_name": row[3],
                        "product_code": row[4],
                        "version": row[5],
                        "zero_based": bool(row[6])
                    }
                    for row in results
                ]
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error fetching servers: {e}")
            return []

    def get_slaves(self, server_id=None):
        """Get slave configurations, optionally filtered by server_id"""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                if server_id is not None:
                    cursor.execute(
                        "SELECT server_id, slave_id, co_size, di_size, hr_size, ir_size FROM slaves WHERE server_id = ? ORDER BY slave_id",
                        (server_id,)
                    )
                else:
                    cursor.execute("SELECT server_id, slave_id, co_size, di_size, hr_size, ir_size FROM slaves ORDER BY server_id, slave_id")
                results = cursor.fetchall()
                return [
                    {
                        "server_id": row[0],
                        "slave_id": row[1],
                        "co_size": row[2],
                        "di_size": row[3],
                        "hr_size": row[4],
                        "ir_size": row[5]
                    }
                    for row in results
                ]
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error fetching slaves: {e}")
            return []

    def save_server_config(self, servers, slaves):
        """Save complete server and slave configuration, replacing existing"""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                errors = []

                # Validate servers first
                for server in servers:
                    server_id = server.get("server_id")
                    if server_id is None:
                        errors.append("Missing server_id in server config")

                    port = server.get("port")
                    if port is None:
                        errors.append(f"Missing port for server {server_id if server_id is not None else 'unknown'}")

                # Validate slaves
                for slave in slaves:
                    server_id = slave.get("server_id")
                    slave_id = slave.get("slave_id")

                    if server_id is None:
                        errors.append("Missing server_id in slave config")
                    if slave_id is None:
                        errors.append("Missing slave_id in slave config")

                # If there are validation errors, return before modifying database
                if errors:
                    return {"success": False, "errors": errors}

                # Clear existing slaves first, then servers
                # (Doing slaves first to avoid foreign key issues)
                cursor.execute("DELETE FROM slaves")
                logger.debug("Deleted all slaves")
                cursor.execute("DELETE FROM servers")
                logger.debug("Deleted all servers")

                # Insert servers
                for server in servers:
                    server_id = server.get("server_id")
                    ip = server.get("ip", "0.0.0.0")
                    port = server.get("port")
                    vendor_name = server.get("vendor_name", "ModbusSimulator")
                    product_code = server.get("product_code", "MSIM")
                    version = server.get("version", "1.0")
                    zero_based = int(server.get("zero_based", True))

                    cursor.execute(
                        """
                        INSERT INTO servers (server_id, ip, port, vendor_name, product_code, version, zero_based)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (server_id, ip, port, vendor_name, product_code, version, zero_based)
                    )

                # Insert slaves
                for slave in slaves:
                    server_id = slave.get("server_id")
                    slave_id = slave.get("slave_id")
                    co_size = slave.get("co_size", 100)
                    di_size = slave.get("di_size", 100)
                    hr_size = slave.get("hr_size", 100)
                    ir_size = slave.get("ir_size", 100)

                    logger.debug(f"Inserting slave: server_id={server_id}, slave_id={slave_id}")
                    cursor.execute(
                        """
                        INSERT INTO slaves (server_id, slave_id, co_size, di_size, hr_size, ir_size)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (server_id, slave_id, co_size, di_size, hr_size, ir_size)
                    )

                conn.commit()
                return {"success": True, "errors": []}
            finally:
                conn.close()
        except sqlite3.Error as e:
            logger.error(f"Error saving server config: {e}")
            return {"success": False, "errors": [str(e)]}
