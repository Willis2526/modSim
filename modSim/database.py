import sqlite3
import os
import json
import logging

logger = logging.getLogger("DatabaseLogger")

class Database:
    def __init__(self, db_path="settings.db"):
        self.db_path = db_path
        self._initialize_database()

    def _initialize_database(self):
        try:
            if not os.path.exists(self.db_path):
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
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
                            simulate INTEGER NOT NULL       -- Whether the register is simulated (0 or 1)
                        )
                        """
                    )
                    conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")

    def get_registers(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT server_id, slave_id, register_type, address, address_end, register_size, simulate FROM registers")
                results = cursor.fetchall()
                return [
                    {
                        "server_id": row[0],
                        "slave_id": row[1],
                        "register_type": row[2],
                        "address": row[3],
                        "address_end": row[4],
                        "register_size": row[5],
                        "simulate": bool(row[6])
                    }
                    for row in results
                ]
        except sqlite3.Error as e:
            logger.error(f"Error fetching registers: {e}")
            return []

    def save_registers(self, registers):
        try:
            with sqlite3.connect(self.db_path) as conn:
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

                    if slave_id is None:
                        errors.append("Missing slave_id")

                    if not register_type:
                        errors.append("Missing register_type")

                    if errors:
                         return {"success": False, "errors": errors}

                    cursor.execute(
                        """
                        INSERT INTO registers (server_id, slave_id, register_type, address, address_end, register_size, simulate)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (server_id, slave_id, register_type, address, address_end, register_size, simulate)
                    )

                conn.commit()
                return {"success": True, "errors": []}
            
        except sqlite3.Error as e:
            logger.error(f"Error saving registers: {e}")
            return {"success": False, "errors": [str(e)]}
