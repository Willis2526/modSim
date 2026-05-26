"""Integration tests: real Modbus TCP server + real pymodbus client."""
import math
import struct
import time
import pytest
from pymodbus.client import ModbusTcpClient
from modSim.modbus import Server, _ctx_write, _ctx_read

_HOST = "127.0.0.1"
_PORT = 15030  # high port to avoid conflicts


def _wait_for_server(host, port, timeout=5.0):
    """Poll until the server accepts a TCP connection or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        c = ModbusTcpClient(host, port=port, timeout=1)
        if c.connect():
            c.close()
            return True
        time.sleep(0.1)
    return False


@pytest.fixture(scope="module")
def modbus_server():
    """Start a Modbus TCP server for the module and shut it down after."""
    srv = Server(
        server_id=0,
        address=_HOST,
        port=_PORT,
        number_of_slaves=2,
        register_sizes={"co": 100, "di": 100, "hr": 100, "ir": 100},
    )
    srv.start()
    assert _wait_for_server(_HOST, _PORT), "Modbus server did not start in time"
    yield srv


@pytest.fixture()
def client(modbus_server):
    """Fresh client connection per test, closed after."""
    c = ModbusTcpClient(_HOST, port=_PORT, timeout=3)
    assert c.connect(), "Could not connect to Modbus server"
    yield c
    c.close()


# Holding registers (FC 3)

class TestHoldingRegisters:
    def test_read_single(self, modbus_server, client):
        modbus_server.write_registers(0, 3, 10, [999])
        result = client.read_holding_registers(10, count=1, device_id=0)
        assert not result.isError()
        assert result.registers == [999]

    def test_read_multiple(self, modbus_server, client):
        modbus_server.write_registers(0, 3, 0, [10, 20, 30, 40, 50])
        result = client.read_holding_registers(0, count=5, device_id=0)
        assert not result.isError()
        assert result.registers == [10, 20, 30, 40, 50]

    def test_read_max_value(self, modbus_server, client):
        modbus_server.write_registers(0, 3, 5, [65535])
        result = client.read_holding_registers(5, count=1, device_id=0)
        assert not result.isError()
        assert result.registers[0] == 65535

    def test_read_zero(self, modbus_server, client):
        modbus_server.write_registers(0, 3, 20, [0])
        result = client.read_holding_registers(20, count=1, device_id=0)
        assert not result.isError()
        assert result.registers[0] == 0

    def test_write_then_read_multiple_slaves(self, modbus_server, client):
        modbus_server.write_registers(0, 3, 0, [111])
        modbus_server.write_registers(1, 3, 0, [222])
        r0 = client.read_holding_registers(0, count=1, device_id=0)
        r1 = client.read_holding_registers(0, count=1, device_id=1)
        assert not r0.isError() and not r1.isError()
        assert r0.registers[0] == 111
        assert r1.registers[0] == 222


# Input registers (FC 4)

class TestInputRegisters:
    def test_read_single(self, modbus_server, client):
        modbus_server.write_registers(0, 4, 7, [4567])
        result = client.read_input_registers(7, count=1, device_id=0)
        assert not result.isError()
        assert result.registers[0] == 4567

    def test_read_range(self, modbus_server, client):
        values = list(range(100, 110))
        modbus_server.write_registers(0, 4, 50, values)
        result = client.read_input_registers(50, count=10, device_id=0)
        assert not result.isError()
        assert result.registers == values

    def test_independent_from_holding(self, modbus_server, client):
        modbus_server.write_registers(0, 3, 30, [1111])
        modbus_server.write_registers(0, 4, 30, [2222])
        hr = client.read_holding_registers(30, count=1, device_id=0)
        ir = client.read_input_registers(30, count=1, device_id=0)
        assert not hr.isError() and not ir.isError()
        assert hr.registers[0] == 1111
        assert ir.registers[0] == 2222


# Coils (FC 1)

class TestCoils:
    def test_read_single_true(self, modbus_server, client):
        modbus_server.write_registers(0, 1, 0, [True])
        result = client.read_coils(0, count=1, device_id=0)
        assert not result.isError()
        assert result.bits[0] is True

    def test_read_single_false(self, modbus_server, client):
        modbus_server.write_registers(0, 1, 1, [False])
        result = client.read_coils(1, count=1, device_id=0)
        assert not result.isError()
        assert result.bits[0] is False

    def test_read_pattern(self, modbus_server, client):
        pattern = [True, False, True, True, False, False, True, False]
        modbus_server.write_registers(0, 1, 0, pattern)
        result = client.read_coils(0, count=8, device_id=0)
        assert not result.isError()
        assert list(result.bits[:8]) == pattern

    def test_cross_word_boundary(self, modbus_server, client):
        modbus_server.write_registers(0, 1, 15, [True])
        modbus_server.write_registers(0, 1, 16, [True])
        r15 = client.read_coils(15, count=1, device_id=0)
        r16 = client.read_coils(16, count=1, device_id=0)
        assert not r15.isError() and not r16.isError()
        assert r15.bits[0] is True
        assert r16.bits[0] is True


# Discrete inputs (FC 2)

class TestDiscreteInputs:
    def test_read_true(self, modbus_server, client):
        modbus_server.write_registers(0, 2, 5, [True])
        result = client.read_discrete_inputs(5, count=1, device_id=0)
        assert not result.isError()
        assert result.bits[0] is True

    def test_read_multiple(self, modbus_server, client):
        pattern = [False, True, False, True]
        modbus_server.write_registers(0, 2, 10, pattern)
        result = client.read_discrete_inputs(10, count=4, device_id=0)
        assert not result.isError()
        assert list(result.bits[:4]) == pattern

    def test_independent_from_coils(self, modbus_server, client):
        modbus_server.write_registers(0, 1, 20, [True])
        modbus_server.write_registers(0, 2, 20, [False])
        co = client.read_coils(20, count=1, device_id=0)
        di = client.read_discrete_inputs(20, count=1, device_id=0)
        assert not co.isError() and not di.isError()
        assert co.bits[0] is True
        assert di.bits[0] is False


# Simulation engine integration

class TestSimulationIntegration:
    def test_static_simulation_readable(self, modbus_server, client):
        regs = [{
            "server_id": 0, "slave_id": 0, "register_type": "hr",
            "address": 80, "address_end": 84,
            "simulate": True, "simulation_mode": "static",
            "simulation_config": {"value": 7777},
        }]
        modbus_server.simulate(regs)
        result = client.read_holding_registers(80, count=5, device_id=0)
        assert not result.isError()
        assert result.registers == [7777] * 5

    def test_ramp_simulation_increases(self, modbus_server, client):
        regs = [{
            "server_id": 0, "slave_id": 0, "register_type": "ir",
            "address": 90, "address_end": None,
            "simulate": True, "simulation_mode": "ramp",
            "simulation_config": {"min": 0, "max": 1000, "step": 10},
        }]
        modbus_server.simulation_engine.register_counters = {}
        modbus_server.simulate(regs)
        v1 = client.read_input_registers(90, count=1, device_id=0)
        modbus_server.simulate(regs)
        v2 = client.read_input_registers(90, count=1, device_id=0)
        assert not v1.isError() and not v2.isError()
        assert v2.registers[0] > v1.registers[0]

    def test_direct_write_visible_to_client(self, modbus_server, client):
        runtime = modbus_server.context._runtimes[0]
        _ctx_write(runtime, 3, 99, [12345])
        result = client.read_holding_registers(99, count=1, device_id=0)
        assert not result.isError()
        assert result.registers[0] == 12345

    def test_client_read_matches_direct_read(self, modbus_server, client):
        modbus_server.write_registers(0, 3, 60, [100, 200, 300])
        client_result = client.read_holding_registers(60, count=3, device_id=0)
        direct_result = modbus_server.read_registers(0, 3, 60, 3)
        assert not client_result.isError()
        assert client_result.registers == direct_result


# Float registers (float32 encoded across two consecutive HR/IR)

def _decode_float(hi, lo):
    return struct.unpack('>f', struct.pack('>HH', hi, lo))[0]


class TestFloatRegisters:
    def test_write_read_single_float_direct(self, modbus_server):
        """Write a float via helper, read back raw words, decode, compare."""
        modbus_server.write_float_registers(0, 0, [3.14])
        result = modbus_server.read_float_registers(0, 0, count=1)
        assert math.isclose(result[0], 3.14, rel_tol=1e-6)

    def test_write_read_single_float_via_client(self, modbus_server, client):
        """Client reads the two raw registers and we decode them client-side."""
        modbus_server.write_float_registers(0, 2, [1234.5678])
        raw = client.read_holding_registers(2, count=2, device_id=0)
        assert not raw.isError()
        value = _decode_float(raw.registers[0], raw.registers[1])
        assert math.isclose(value, 1234.5678, rel_tol=1e-6)

    def test_write_multiple_floats(self, modbus_server, client):
        """Three floats packed into six consecutive registers."""
        floats = [0.0, -1.5, 65535.0]
        modbus_server.write_float_registers(0, 10, floats)
        raw = client.read_holding_registers(10, count=6, device_id=0)
        assert not raw.isError()
        decoded = [_decode_float(raw.registers[i * 2], raw.registers[i * 2 + 1])
                   for i in range(3)]
        for expected, actual in zip(floats, decoded):
            assert math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-9)

    def test_float_zero(self, modbus_server, client):
        modbus_server.write_float_registers(0, 20, [0.0])
        raw = client.read_holding_registers(20, count=2, device_id=0)
        assert not raw.isError()
        assert raw.registers == [0, 0]
        assert _decode_float(raw.registers[0], raw.registers[1]) == 0.0

    def test_float_negative(self, modbus_server, client):
        modbus_server.write_float_registers(0, 22, [-273.15])
        raw = client.read_holding_registers(22, count=2, device_id=0)
        assert not raw.isError()
        value = _decode_float(raw.registers[0], raw.registers[1])
        assert math.isclose(value, -273.15, rel_tol=1e-6)

    def test_float_max_positive(self, modbus_server, client):
        """float32 max finite value."""
        f32_max = 3.4028234663852886e+38
        modbus_server.write_float_registers(0, 24, [f32_max])
        result = modbus_server.read_float_registers(0, 24, count=1)
        assert math.isclose(result[0], f32_max, rel_tol=1e-6)

    def test_float_in_input_registers(self, modbus_server, client):
        """Float32 works in input registers (FC 4) too."""
        modbus_server.write_float_registers(0, 30, [42.0], fc=4)
        raw = client.read_input_registers(30, count=2, device_id=0)
        assert not raw.isError()
        value = _decode_float(raw.registers[0], raw.registers[1])
        assert math.isclose(value, 42.0, rel_tol=1e-6)

    def test_read_float_helper_multiple(self, modbus_server):
        """read_float_registers returns the right number of floats."""
        floats = [1.1, 2.2, 3.3]
        modbus_server.write_float_registers(0, 40, floats)
        result = modbus_server.read_float_registers(0, 40, count=3)
        assert len(result) == 3
        for expected, actual in zip(floats, result):
            assert math.isclose(actual, expected, rel_tol=1e-6)

    def test_floats_independent_across_slaves(self, modbus_server, client):
        """Same address on slave 0 and slave 1 hold independent floats."""
        modbus_server.write_float_registers(0, 50, [111.0])
        modbus_server.write_float_registers(1, 50, [222.0])
        r0 = client.read_holding_registers(50, count=2, device_id=0)
        r1 = client.read_holding_registers(50, count=2, device_id=1)
        assert not r0.isError() and not r1.isError()
        v0 = _decode_float(r0.registers[0], r0.registers[1])
        v1 = _decode_float(r1.registers[0], r1.registers[1])
        assert math.isclose(v0, 111.0, rel_tol=1e-6)
        assert math.isclose(v1, 222.0, rel_tol=1e-6)


# ── Float simulation mode ─────────────────────────────────────────────────────

class TestFloatSimulation:
    def test_static_float_sim(self, modbus_server, client):
        """simulation_config float32=True with static mode writes a real float."""
        regs = [{
            "server_id": 0, "slave_id": 0, "register_type": "hr",
            "address": 60, "address_end": 61,
            "simulate": True, "simulation_mode": "static",
            "simulation_config": {"value": 98.6, "float32": True},
        }]
        modbus_server.simulate(regs)
        raw = client.read_holding_registers(60, count=2, device_id=0)
        assert not raw.isError()
        value = _decode_float(raw.registers[0], raw.registers[1])
        assert math.isclose(value, 98.6, rel_tol=1e-6)

    def test_sine_float_sim_is_fractional(self, modbus_server, client):
        """Sine with float32=True preserves the fractional part."""
        regs = [{
            "server_id": 0, "slave_id": 0, "register_type": "hr",
            "address": 62, "address_end": 63,
            "simulate": True, "simulation_mode": "sine",
            "simulation_config": {"amplitude": 1.5, "offset": 0.0, "period": 4, "float32": True},
        }]
        modbus_server.simulation_engine.register_counters = {}
        modbus_server.simulate(regs)
        raw = client.read_holding_registers(62, count=2, device_id=0)
        assert not raw.isError()
        value = _decode_float(raw.registers[0], raw.registers[1])
        # First tick: sin(0) = 0 — second tick should be non-zero
        modbus_server.simulate(regs)
        raw2 = client.read_holding_registers(62, count=2, device_id=0)
        value2 = _decode_float(raw2.registers[0], raw2.registers[1])
        # At least one value should have a fractional component
        assert not (value == int(value) and value2 == int(value2)), \
            "Expected fractional float values from sine simulation"

    def test_ramp_float_sim_increases(self, modbus_server, client):
        """Ramp with float32=True produces increasing float values."""
        regs = [{
            "server_id": 0, "slave_id": 0, "register_type": "ir",
            "address": 64, "address_end": 65,
            "simulate": True, "simulation_mode": "ramp",
            "simulation_config": {"min": 0.5, "max": 100.5, "step": 0.5, "float32": True},
        }]
        modbus_server.simulation_engine.register_counters = {}
        modbus_server.simulate(regs)
        r1 = client.read_input_registers(64, count=2, device_id=0)
        modbus_server.simulate(regs)
        r2 = client.read_input_registers(64, count=2, device_id=0)
        assert not r1.isError() and not r2.isError()
        v1 = _decode_float(r1.registers[0], r1.registers[1])
        v2 = _decode_float(r2.registers[0], r2.registers[1])
        assert v2 > v1

    def test_random_float_sim_in_range(self, modbus_server, client):
        """Random with float32=True stays within the configured range."""
        regs = [{
            "server_id": 0, "slave_id": 0, "register_type": "hr",
            "address": 66, "address_end": 67,
            "simulate": True, "simulation_mode": "random",
            "simulation_config": {"min": 10.0, "max": 20.0, "float32": True},
        }]
        for _ in range(5):
            modbus_server.simulate(regs)
            raw = client.read_holding_registers(66, count=2, device_id=0)
            assert not raw.isError()
            value = _decode_float(raw.registers[0], raw.registers[1])
            assert 10.0 <= value <= 20.0

    def test_float32_false_gives_integer(self, modbus_server, client):
        """Without float32, static sim writes an integer (truncates fraction)."""
        regs = [{
            "server_id": 0, "slave_id": 0, "register_type": "hr",
            "address": 70, "address_end": 70,
            "simulate": True, "simulation_mode": "static",
            "simulation_config": {"value": 42.9},   # no float32 flag
        }]
        modbus_server.simulate(regs)
        raw = client.read_holding_registers(70, count=1, device_id=0)
        assert not raw.isError()
        assert raw.registers[0] == 42  # fractional part truncated

