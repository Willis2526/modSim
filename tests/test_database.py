"""Tests for the Database class"""
import pytest
import os
import tempfile
import json
from modSim.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = Database(db_path)
    yield db
    # Cleanup - retry a few times on Windows to handle file locking
    if os.path.exists(db_path):
        import time
        for attempt in range(5):
            try:
                os.remove(db_path)
                break
            except PermissionError:
                if attempt < 4:
                    time.sleep(0.1)
                else:
                    # Give up after 5 attempts - file will be cleaned up by temp dir cleanup
                    pass


class TestDatabase:
    """Test cases for Database class"""

    def test_init_creates_database(self, temp_db):
        """Test database initialization creates file"""
        assert os.path.exists(temp_db.db_path)

    def test_init_creates_table(self, temp_db):
        """Test database initialization creates registers table"""
        import sqlite3
        with sqlite3.connect(temp_db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='registers'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == 'registers'

    def test_get_registers_empty(self, temp_db):
        """Test getting registers from empty database"""
        registers = temp_db.get_registers()
        assert registers == []

    def test_save_registers_single(self, temp_db):
        """Test saving a single register"""
        register = {
            "server_id": 0,
            "slave_id": 1,
            "register_type": "hr",
            "address": 100,
            "simulate": True
        }
        result = temp_db.save_registers([register])
        assert result["success"] is True
        assert result["errors"] == []

    def test_save_and_get_registers(self, temp_db):
        """Test saving and retrieving registers"""
        registers_to_save = [
            {
                "server_id": 0,
                "slave_id": 1,
                "register_type": "hr",
                "address": 100,
                "simulate": True
            },
            {
                "server_id": 0,
                "slave_id": 1,
                "register_type": "co",
                "address": 50,
                "simulate": False
            }
        ]

        temp_db.save_registers(registers_to_save)
        retrieved = temp_db.get_registers()

        assert len(retrieved) == 2
        assert retrieved[0]["slave_id"] == 1
        assert retrieved[0]["register_type"] == "hr"
        assert retrieved[0]["address"] == 100
        assert retrieved[0]["simulate"] is True
        assert retrieved[1]["register_type"] == "co"
        assert retrieved[1]["simulate"] is False

    def test_save_registers_with_defaults(self, temp_db):
        """Test saving registers with default values"""
        register = {
            "slave_id": 1,
            "register_type": "hr"
        }
        result = temp_db.save_registers([register])
        assert result["success"] is True

        retrieved = temp_db.get_registers()
        assert len(retrieved) == 1
        assert retrieved[0]["address"] == 0
        assert retrieved[0]["simulate"] is False
        assert retrieved[0]["simulation_mode"] == "random"
        assert retrieved[0]["simulation_config"] == {}

    def test_save_registers_with_simulation_mode(self, temp_db):
        """Test saving registers with simulation mode and config"""
        register = {
            "slave_id": 0,
            "register_type": "hr",
            "address": 200,
            "simulate": True,
            "simulation_mode": "sine",
            "simulation_config": {
                "amplitude": 100,
                "offset": 200,
                "period": 60
            }
        }

        temp_db.save_registers([register])
        retrieved = temp_db.get_registers()

        assert len(retrieved) == 1
        assert retrieved[0]["simulation_mode"] == "sine"
        assert retrieved[0]["simulation_config"]["amplitude"] == 100
        assert retrieved[0]["simulation_config"]["offset"] == 200
        assert retrieved[0]["simulation_config"]["period"] == 60

    def test_save_registers_with_range(self, temp_db):
        """Test saving registers with address range"""
        register = {
            "slave_id": 0,
            "register_type": "hr",
            "address": 0,
            "address_end": 50,
            "simulate": True
        }

        temp_db.save_registers([register])
        retrieved = temp_db.get_registers()

        assert len(retrieved) == 1
        assert retrieved[0]["address"] == 0
        assert retrieved[0]["address_end"] == 50

    def test_save_registers_with_custom_size(self, temp_db):
        """Test saving registers with custom register size"""
        register = {
            "slave_id": 0,
            "register_type": "hr",
            "address": 0,
            "register_size": 200,
            "simulate": True
        }

        temp_db.save_registers([register])
        retrieved = temp_db.get_registers()

        assert len(retrieved) == 1
        assert retrieved[0]["register_size"] == 200

    def test_save_registers_without_server_id(self, temp_db):
        """Test saving registers without server_id (defaults to None)"""
        register = {
            "slave_id": 0,
            "register_type": "hr",
            "simulate": True
        }

        temp_db.save_registers([register])
        retrieved = temp_db.get_registers()

        assert len(retrieved) == 1
        assert retrieved[0]["server_id"] is None

    def test_save_registers_replaces_existing(self, temp_db):
        """Test that save_registers replaces existing data"""
        # First save
        temp_db.save_registers([
            {"slave_id": 0, "register_type": "hr", "address": 100, "simulate": True}
        ])

        # Second save
        temp_db.save_registers([
            {"slave_id": 1, "register_type": "co", "address": 200, "simulate": False}
        ])

        retrieved = temp_db.get_registers()
        assert len(retrieved) == 1
        assert retrieved[0]["slave_id"] == 1
        assert retrieved[0]["address"] == 200

    def test_save_registers_missing_slave_id(self, temp_db):
        """Test saving registers without required slave_id"""
        register = {
            "register_type": "hr",
            "simulate": True
        }

        result = temp_db.save_registers([register])
        assert result["success"] is False
        assert "Missing slave_id" in result["errors"]

    def test_save_registers_missing_register_type(self, temp_db):
        """Test saving registers without required register_type"""
        register = {
            "slave_id": 0,
            "simulate": True
        }

        result = temp_db.save_registers([register])
        assert result["success"] is False
        assert "Missing register_type" in result["errors"]

    def test_save_multiple_registers(self, temp_db):
        """Test saving multiple registers at once"""
        registers = [
            {"slave_id": 0, "register_type": "hr", "address": i, "simulate": True}
            for i in range(10)
        ]

        result = temp_db.save_registers(registers)
        assert result["success"] is True

        retrieved = temp_db.get_registers()
        assert len(retrieved) == 10

    def test_save_registers_with_all_modes(self, temp_db):
        """Test saving registers with different simulation modes"""
        registers = [
            {
                "slave_id": 0,
                "register_type": "hr",
                "address": 100,
                "simulate": True,
                "simulation_mode": "random",
                "simulation_config": {"min": 0, "max": 100}
            },
            {
                "slave_id": 0,
                "register_type": "hr",
                "address": 200,
                "simulate": True,
                "simulation_mode": "static",
                "simulation_config": {"value": 42}
            },
            {
                "slave_id": 0,
                "register_type": "hr",
                "address": 300,
                "simulate": True,
                "simulation_mode": "equation",
                "simulation_config": {"equation": "x * 2"}
            },
            {
                "slave_id": 0,
                "register_type": "hr",
                "address": 400,
                "simulate": True,
                "simulation_mode": "ramp",
                "simulation_config": {"min": 0, "max": 100, "step": 5}
            },
            {
                "slave_id": 0,
                "register_type": "hr",
                "address": 500,
                "simulate": True,
                "simulation_mode": "sine",
                "simulation_config": {"amplitude": 100, "offset": 0, "period": 60}
            },
            {
                "slave_id": 0,
                "register_type": "hr",
                "address": 600,
                "simulate": True,
                "simulation_mode": "square",
                "simulation_config": {"high": 100, "low": 0, "period": 10}
            }
        ]

        result = temp_db.save_registers(registers)
        assert result["success"] is True

        retrieved = temp_db.get_registers()
        assert len(retrieved) == 6

        modes = [r["simulation_mode"] for r in retrieved]
        assert "random" in modes
        assert "static" in modes
        assert "equation" in modes
        assert "ramp" in modes
        assert "sine" in modes
        assert "square" in modes

    def test_simulation_config_json_serialization(self, temp_db):
        """Test that simulation_config is properly serialized/deserialized"""
        complex_config = {
            "nested": {
                "value": 123,
                "list": [1, 2, 3],
                "bool": True
            },
            "string": "test"
        }

        register = {
            "slave_id": 0,
            "register_type": "hr",
            "address": 100,
            "simulate": True,
            "simulation_config": complex_config
        }

        temp_db.save_registers([register])
        retrieved = temp_db.get_registers()

        assert retrieved[0]["simulation_config"] == complex_config

    def test_empty_simulation_config(self, temp_db):
        """Test handling of empty simulation_config"""
        register = {
            "slave_id": 0,
            "register_type": "hr",
            "address": 100,
            "simulate": True,
            "simulation_config": None
        }

        temp_db.save_registers([register])
        retrieved = temp_db.get_registers()

        assert retrieved[0]["simulation_config"] == {}

    def test_register_type_values(self, temp_db):
        """Test different register type values"""
        register_types = ["co", "di", "hr", "ir", "all"]

        for i, reg_type in enumerate(register_types):
            temp_db.save_registers([
                {"slave_id": 0, "register_type": reg_type, "address": i * 100, "simulate": True}
            ])
            retrieved = temp_db.get_registers()
            assert retrieved[0]["register_type"] == reg_type

    def test_simulate_boolean_conversion(self, temp_db):
        """Test that simulate field is properly converted to boolean"""
        # Test with integer values
        temp_db.save_registers([
            {"slave_id": 0, "register_type": "hr", "address": 0, "simulate": 1}
        ])
        retrieved = temp_db.get_registers()
        assert retrieved[0]["simulate"] is True

        temp_db.save_registers([
            {"slave_id": 0, "register_type": "hr", "address": 0, "simulate": 0}
        ])
        retrieved = temp_db.get_registers()
        assert retrieved[0]["simulate"] is False

        # Test with boolean values
        temp_db.save_registers([
            {"slave_id": 0, "register_type": "hr", "address": 0, "simulate": True}
        ])
        retrieved = temp_db.get_registers()
        assert retrieved[0]["simulate"] is True

    def test_multiple_server_ids(self, temp_db):
        """Test registers with different server IDs"""
        registers = [
            {"server_id": 0, "slave_id": 0, "register_type": "hr", "simulate": True},
            {"server_id": 1, "slave_id": 0, "register_type": "hr", "simulate": True},
            {"server_id": None, "slave_id": 0, "register_type": "hr", "simulate": True}
        ]

        temp_db.save_registers(registers)
        retrieved = temp_db.get_registers()

        assert len(retrieved) == 3
        server_ids = [r["server_id"] for r in retrieved]
        assert 0 in server_ids
        assert 1 in server_ids
        assert None in server_ids


class TestServerZeroBased:
    """Persistence of the per-server zero_based addressing flag."""

    def test_default_is_zero_based(self, temp_db):
        temp_db.upsert_server({"server_id": 0, "port": 502})
        row = temp_db.get_servers()[0]
        assert row["zero_based"] is True

    def test_upsert_one_based(self, temp_db):
        temp_db.upsert_server({"server_id": 0, "port": 502, "zero_based": False})
        row = temp_db.get_servers()[0]
        assert row["zero_based"] is False

    def test_save_server_config_round_trip(self, temp_db):
        temp_db.save_server_config(
            [{"server_id": 0, "port": 502, "zero_based": False},
             {"server_id": 1, "port": 503, "zero_based": True}],
            [{"server_id": 0, "slave_id": 0}, {"server_id": 1, "slave_id": 0}],
        )
        by_id = {s["server_id"]: s for s in temp_db.get_servers()}
        assert by_id[0]["zero_based"] is False
        assert by_id[1]["zero_based"] is True

    def test_migration_adds_column_to_legacy_db(self, temp_db):
        """A pre-existing servers table without zero_based is migrated in place."""
        import sqlite3
        # Drop and recreate the servers table in the legacy (pre-flag) shape
        with sqlite3.connect(temp_db.db_path) as conn:
            conn.execute("DROP TABLE servers")
            conn.execute(
                "CREATE TABLE servers (server_id INTEGER PRIMARY KEY, ip TEXT, "
                "port INTEGER, vendor_name TEXT, product_code TEXT, version TEXT)"
            )
            conn.execute("INSERT INTO servers VALUES (0,'0.0.0.0',502,'V','P','1.0')")
            conn.commit()
        # Re-open: initialization should ALTER TABLE ADD COLUMN zero_based
        migrated = Database(temp_db.db_path)
        row = migrated.get_servers()[0]
        assert row["zero_based"] is True


class TestUpsertRegister:
    """upsert_register matches on the natural key for idempotent merge imports."""

    def _rule(self, **over):
        rule = {"slave_id": 0, "register_type": "hr", "address": 17,
                "address_end": None, "simulate": True,
                "simulation_mode": "sine", "simulation_config": {"offset": 480}}
        rule.update(over)
        return rule

    def test_insert_when_absent(self, temp_db):
        res = temp_db.upsert_register(self._rule())
        assert res["success"] and res["action"] == "added"
        assert len(temp_db.get_registers()) == 1

    def test_update_when_key_matches(self, temp_db):
        temp_db.upsert_register(self._rule(simulation_config={"offset": 480}))
        res = temp_db.upsert_register(self._rule(simulation_config={"offset": 500}))
        assert res["success"] and res["action"] == "updated"
        regs = temp_db.get_registers()
        assert len(regs) == 1
        assert regs[0]["simulation_config"]["offset"] == 500

    def test_different_address_inserts_new(self, temp_db):
        temp_db.upsert_register(self._rule(address=17))
        temp_db.upsert_register(self._rule(address=18))
        assert len(temp_db.get_registers()) == 2

    def test_null_server_id_and_address_end_match(self, temp_db):
        """A rule with NULL server_id / address_end still matches itself (IS NULL)."""
        temp_db.upsert_register(self._rule(server_id=None, address_end=None))
        res = temp_db.upsert_register(self._rule(server_id=None, address_end=None,
                                                 simulation_config={"offset": 12}))
        assert res["action"] == "updated"
        assert len(temp_db.get_registers()) == 1

    def test_address_end_distinguishes_rules(self, temp_db):
        """Same start address but different address_end are distinct rules."""
        temp_db.upsert_register(self._rule(address=17, address_end=None))
        temp_db.upsert_register(self._rule(address=17, address_end=20))
        assert len(temp_db.get_registers()) == 2
