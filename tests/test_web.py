"""Tests for the WebServer API endpoints"""
import pytest
import tempfile
import os
from fastapi.testclient import TestClient
from modSim.web import WebServer
from modSim.database import Database


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = Database(db_path)
    yield db
    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def mock_modbus_servers():
    """Create mock modbus servers for testing"""
    class MockModbusServer:
        def __init__(self, server_id):
            self.server_id = server_id

        def getDetails(self):
            return {
                "server_id": self.server_id,
                "ip": "0.0.0.0",
                "port": 502 + self.server_id,
                "slaves": 1,
                "identity": {
                    "VendorName": "ModbusSimulator",
                    "ProductCode": "MSIM",
                    "MajorMinorRevision": "1.0"
                }
            }

        def get_context(self):
            return {
                "slaves": {
                    0: {
                        "co": [False] * 100,
                        "di": [False] * 100,
                        "hr": [0] * 100,
                        "ir": [0] * 100
                    }
                }
            }

    return {0: MockModbusServer(0), 1: MockModbusServer(1)}


@pytest.fixture
def web_server(temp_db, mock_modbus_servers):
    """Create a WebServer instance for testing"""
    server = WebServer(port=8000, database=temp_db, modbus_servers=mock_modbus_servers)
    return server


@pytest.fixture
def client(web_server):
    """Create a test client for the web server"""
    return TestClient(web_server.app)


class TestWebServerEndpoints:
    """Test cases for WebServer API endpoints"""

    def test_get_server_config_success(self, client):
        """Test getting server configuration"""
        response = client.get("/get-server-config")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "servers" in data
        assert "slaves" in data

    def test_configure_registers_success(self, client):
        """Test configuring registers successfully"""
        register_config = {
            "registers": [
                {
                    "slave_id": 0,
                    "register_type": "hr",
                    "address": 100,
                    "simulate": True
                }
            ]
        }

        response = client.post("/configure-registers", json=register_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Registers configured."

    def test_configure_registers_with_simulation_mode(self, client):
        """Test configuring registers with simulation mode"""
        register_config = {
            "registers": [
                {
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
            ]
        }

        response = client.post("/configure-registers", json=register_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

    def test_configure_registers_multiple(self, client):
        """Test configuring multiple registers"""
        register_config = {
            "registers": [
                {"slave_id": 0, "register_type": "hr", "address": i, "simulate": True}
                for i in range(10)
            ]
        }

        response = client.post("/configure-registers", json=register_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

    def test_configure_registers_missing_slave_id(self, client):
        """Test configuring registers with missing slave_id"""
        register_config = {
            "registers": [
                {
                    "register_type": "hr",
                    "address": 100,
                    "simulate": True
                }
            ]
        }

        response = client.post("/configure-registers", json=register_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False

    def test_configure_registers_missing_register_type(self, client):
        """Test configuring registers with missing register_type"""
        register_config = {
            "registers": [
                {
                    "slave_id": 0,
                    "address": 100,
                    "simulate": True
                }
            ]
        }

        response = client.post("/configure-registers", json=register_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False

    def test_get_registers_empty(self, client):
        """Test getting registers when database is empty"""
        response = client.get("/get-registers")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert data["message"] == "No registers found."

    def test_get_registers_success(self, client):
        """Test getting registers after configuration"""
        # First configure some registers
        register_config = {
            "registers": [
                {"slave_id": 0, "register_type": "hr", "address": 100, "simulate": True},
                {"slave_id": 0, "register_type": "co", "address": 50, "simulate": False}
            ]
        }
        client.post("/configure-registers", json=register_config)

        # Now get the registers
        response = client.get("/get-registers")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "registers" in data
        assert len(data["registers"]) == 2

    def test_get_registers_with_simulation_modes(self, client):
        """Test getting registers with various simulation modes"""
        register_config = {
            "registers": [
                {
                    "slave_id": 0,
                    "register_type": "hr",
                    "address": 100,
                    "simulate": True,
                    "simulation_mode": "sine",
                    "simulation_config": {"amplitude": 100}
                },
                {
                    "slave_id": 0,
                    "register_type": "hr",
                    "address": 200,
                    "simulate": True,
                    "simulation_mode": "equation",
                    "simulation_config": {"equation": "x * 2"}
                }
            ]
        }
        client.post("/configure-registers", json=register_config)

        response = client.get("/get-registers")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        registers = data["registers"]
        assert len(registers) == 2
        assert registers[0]["simulation_mode"] == "sine"
        assert registers[1]["simulation_mode"] == "equation"

    def test_get_context_success(self, client):
        """Test getting modbus context for a server"""
        response = client.get("/get-context?server_id=0")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "context" in data

    def test_get_context_invalid_server(self, client):
        """Test getting context for non-existent server"""
        response = client.get("/get-context?server_id=999")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert data["message"] == "Server not found."

    def test_configure_server_success(self, client):
        """Test configure-server endpoint with valid configuration"""
        server_config = {
            "ip": "0.0.0.0",
            "port": 502,
            "instances": 1,
            "slaves": 1,
            "identity": {
                "VendorName": "TestVendor",
                "ProductCode": "TEST",
                "MajorMinorRevision": "2.0"
            },
            "register_sizes": {
                "co": 100,
                "di": 100,
                "hr": 100,
                "ir": 100
            }
        }

        response = client.post("/configure-server", json=server_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "server" in data["message"].lower()

    def test_configure_server_multiple_instances(self, client):
        """Test configure-server with multiple server instances"""
        server_config = {
            "ip": "0.0.0.0",
            "port": 502,
            "instances": 2,
            "slaves": 1,
            "identity": {
                "VendorName": "TestVendor",
                "ProductCode": "TEST",
                "MajorMinorRevision": "1.0"
            },
            "register_sizes": {
                "co": 100,
                "di": 100,
                "hr": 100,
                "ir": 100
            }
        }

        response = client.post("/configure-server", json=server_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify configuration was saved (2 servers, 1 slave each = 2 slaves total)
        response = client.get("/get-server-config")
        data = response.json()
        assert data["success"] is True
        assert len(data["servers"]) == 2
        assert len(data["slaves"]) == 2
        assert data["servers"][0]["port"] == 502
        assert data["servers"][1]["port"] == 503  # Auto-incremented port

    def test_configure_server_multiple_slaves(self, client):
        """Test configure-server with multiple slaves per server"""
        server_config = {
            "ip": "0.0.0.0",
            "port": 502,
            "instances": 1,
            "slaves": 3,
            "identity": {
                "VendorName": "TestVendor",
                "ProductCode": "TEST",
                "MajorMinorRevision": "1.0"
            },
            "register_sizes": {
                "co": 200,
                "di": 200,
                "hr": 200,
                "ir": 200
            }
        }

        response = client.post("/configure-server", json=server_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify configuration was saved (1 server with 3 slaves)
        response = client.get("/get-server-config")
        data = response.json()
        assert data["success"] is True
        assert len(data["servers"]) == 1
        assert len(data["slaves"]) == 3
        # All slaves should have the same register sizes
        assert data["slaves"][0]["co_size"] == 200
        assert data["slaves"][1]["co_size"] == 200
        assert data["slaves"][2]["co_size"] == 200

    def test_configure_server_zero_instances(self, client):
        """Test configure-server with zero instances"""
        server_config = {
            "ip": "0.0.0.0",
            "port": 502,
            "instances": 0,
            "slaves": 1
        }

        response = client.post("/configure-server", json=server_config)
        assert response.status_code == 200

        # Should create 0 servers successfully (edge case)
        data = response.json()
        assert data["success"] is True

    def test_configure_server_zero_slaves(self, client):
        """Test configure-server with zero slaves"""
        server_config = {
            "ip": "0.0.0.0",
            "port": 502,
            "instances": 1,
            "slaves": 0
        }

        response = client.post("/configure-server", json=server_config)
        assert response.status_code == 200

        # Should create servers with 0 slaves successfully (edge case)
        data = response.json()
        assert data["success"] is True

    def test_configure_server_missing_port(self, client):
        """Test configure-server with missing port (should use default)"""
        server_config = {
            "instances": 1,
            "slaves": 1
        }

        response = client.post("/configure-server", json=server_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify default port was used
        response = client.get("/get-server-config")
        data = response.json()
        assert data["servers"][0]["port"] == 502  # Default port

    def test_configure_server_default_values(self, client):
        """Test configure-server with minimal config (should use defaults)"""
        server_config = {}

        response = client.post("/configure-server", json=server_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify default values were applied
        response = client.get("/get-server-config")
        data = response.json()
        assert data["success"] is True
        assert data["servers"][0]["ip"] == "0.0.0.0"
        assert data["servers"][0]["port"] == 502
        assert data["servers"][0]["vendor_name"] == "ModbusSimulator"
        assert data["slaves"][0]["co_size"] == 100
        assert data["slaves"][0]["di_size"] == 100
        assert data["slaves"][0]["hr_size"] == 100
        assert data["slaves"][0]["ir_size"] == 100

    def test_configure_server_updates_existing(self, client):
        """Test that configure-server replaces existing configuration"""
        # First configuration
        server_config1 = {
            "ip": "0.0.0.0",
            "port": 502,
            "instances": 1,
            "slaves": 1,
            "identity": {
                "VendorName": "Vendor1",
                "ProductCode": "V1",
                "MajorMinorRevision": "1.0"
            },
            "register_sizes": {
                "co": 100,
                "di": 100,
                "hr": 100,
                "ir": 100
            }
        }
        client.post("/configure-server", json=server_config1)

        # Second configuration
        server_config2 = {
            "ip": "127.0.0.1",
            "port": 503,
            "instances": 1,
            "slaves": 2,
            "identity": {
                "VendorName": "Vendor2",
                "ProductCode": "V2",
                "MajorMinorRevision": "2.0"
            },
            "register_sizes": {
                "co": 200,
                "di": 200,
                "hr": 200,
                "ir": 200
            }
        }
        client.post("/configure-server", json=server_config2)

        # Verify only second configuration exists
        response = client.get("/get-server-config")
        data = response.json()
        assert len(data["servers"]) == 1
        assert data["servers"][0]["ip"] == "127.0.0.1"
        assert data["servers"][0]["port"] == 503
        assert data["servers"][0]["vendor_name"] == "Vendor2"
        assert len(data["slaves"]) == 2  # 2 slaves now
        assert data["slaves"][0]["co_size"] == 200
        assert data["slaves"][1]["co_size"] == 200

    def test_configure_registers_with_all_modes(self, client):
        """Test configuring registers with all simulation modes"""
        register_config = {
            "registers": [
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
                    "register_type": "co",
                    "address": 50,
                    "simulate": True,
                    "simulation_mode": "square",
                    "simulation_config": {"high": 1, "low": 0, "period": 10}
                }
            ]
        }

        response = client.post("/configure-registers", json=register_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify all modes were saved
        response = client.get("/get-registers")
        data = response.json()
        modes = [r["simulation_mode"] for r in data["registers"]]
        assert "random" in modes
        assert "static" in modes
        assert "equation" in modes
        assert "ramp" in modes
        assert "sine" in modes
        assert "square" in modes

    def test_configure_registers_with_address_range(self, client):
        """Test configuring registers with address range"""
        register_config = {
            "registers": [
                {
                    "slave_id": 0,
                    "register_type": "hr",
                    "address": 0,
                    "address_end": 50,
                    "simulate": True
                }
            ]
        }

        response = client.post("/configure-registers", json=register_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify range was saved
        response = client.get("/get-registers")
        data = response.json()
        assert data["registers"][0]["address"] == 0
        assert data["registers"][0]["address_end"] == 50

    def test_configure_registers_with_custom_size(self, client):
        """Test configuring registers with custom register size"""
        register_config = {
            "registers": [
                {
                    "slave_id": 0,
                    "register_type": "hr",
                    "register_size": 200,
                    "simulate": True
                }
            ]
        }

        response = client.post("/configure-registers", json=register_config)
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify custom size was saved
        response = client.get("/get-registers")
        data = response.json()
        assert data["registers"][0]["register_size"] == 200

    def test_api_endpoints_exist(self, client):
        """Test that all required API endpoints exist"""
        # Get OpenAPI schema
        response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200

        schema = response.json()
        paths = schema["paths"]

        # Check all required endpoints exist
        assert "/configure-server" in paths
        assert "/get-server-config" in paths
        assert "/configure-registers" in paths
        assert "/get-registers" in paths
        assert "/get-context" in paths

    def test_register_update_replaces_existing(self, client):
        """Test that configuring registers replaces existing configuration"""
        # First configuration
        register_config1 = {
            "registers": [
                {"slave_id": 0, "register_type": "hr", "address": 100, "simulate": True}
            ]
        }
        client.post("/configure-registers", json=register_config1)

        # Second configuration
        register_config2 = {
            "registers": [
                {"slave_id": 1, "register_type": "co", "address": 200, "simulate": False}
            ]
        }
        client.post("/configure-registers", json=register_config2)

        # Verify only second configuration exists
        response = client.get("/get-registers")
        data = response.json()
        assert len(data["registers"]) == 1
        assert data["registers"][0]["slave_id"] == 1
        assert data["registers"][0]["address"] == 200
