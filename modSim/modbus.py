""" Handles Modbus objects """
import logging
import math
import threading

from pymodbus import ModbusDeviceIdentification
from pymodbus.datastore import ModbusServerContext
from pymodbus.datastore.context import ExcCodes, ModbusSimulatorContext
from pymodbus.server import StartTcpServer
from modSim.simulator import SimulationEngine

logger = logging.getLogger(__name__)

_BITS_FC = frozenset((1, 2, 5, 15))


class _SimContext(ModbusServerContext):
    """Multi-slave context built on ModbusSimulatorContext per slave.

    Subclasses ModbusServerContext so pymodbus 3.13's server uses it
    directly (via the `not simdevices` branch) instead of wrapping it in
    SimCore, which only accepts SimDevice objects.  __init__ intentionally
    does NOT call super().__init__() to avoid the deprecation log warning.
    """

    simdevices = []  # falsy → server skips the SimCore wrapping path

    def __init__(self, devices: dict):
        # devices: {slave_id (int): ModbusSimulatorContext}
        # Deliberately skip super().__init__() — it logs a deprecation warning
        # and its validation logic is not needed here.
        self._devices = devices

    def device_ids(self) -> list:
        return list(self._devices.keys())

    def _get_device(self, device_id: int):
        if device_id in self._devices:
            return self._devices[device_id]
        return next(iter(self._devices.values()), None)

    async def async_getValues(self, device_id: int, func_code: int, address: int, count: int = 1):
        dev = self._get_device(device_id)
        if dev is None:
            return ExcCodes.ILLEGAL_ADDRESS
        return await dev.async_OLD_getValues(func_code, address, count)

    async def async_setValues(self, device_id: int, func_code: int, address: int, values):
        dev = self._get_device(device_id)
        if dev is None:
            return ExcCodes.ILLEGAL_ADDRESS
        return await dev.async_OLD_setValues(func_code, address, values)


def _build_slave_context(co_size=100, di_size=100, hr_size=100, ir_size=100):
    """Build one ModbusSimulatorContext for a single slave."""
    co_cells = math.ceil(max(co_size, 1) / 16)
    di_cells = math.ceil(max(di_size, 1) / 16)
    ir_cells = max(ir_size, 1)
    hr_cells = max(hr_size, 1)
    total = co_cells + di_cells + ir_cells + hr_cells

    config = {
        "setup": {
            "co size": co_cells,
            "di size": di_cells,
            "ir size": ir_cells,
            "hr size": hr_cells,
            "shared blocks": False,
            "defaults": {
                "value": {
                    "bits": 0, "uint16": 0, "uint32": 0,
                    "float32": 0.0, "string": " ",
                },
                "action": {
                    "bits": None, "uint16": None, "uint32": None,
                    "float32": None, "string": None,
                },
            },
            "type exception": False,
        },
        "invalid": [],
        "write": [[0, total - 1]],
        "bits": [[0, co_cells + di_cells - 1]],
        "uint16": [[co_cells + di_cells, total - 1]],
        "uint32": [],
        "float32": [],
        "string": [],
        "repeat": [],
    }
    return ModbusSimulatorContext(config, None)


def buildModbusContext(number_of_slaves, register_sizes=None):
    """Build a ModbusServerContext with one ModbusSimulatorContext per slave."""
    if register_sizes is None:
        register_sizes = {"co": 100, "di": 100, "hr": 100, "ir": 100}

    slaves = {}
    for slave_id in range(number_of_slaves):
        slaves[slave_id] = _build_slave_context(
            co_size=register_sizes.get("co", 100),
            di_size=register_sizes.get("di", 100),
            hr_size=register_sizes.get("hr", 100),
            ir_size=register_sizes.get("ir", 100),
        )
    return _SimContext(slaves)


def _ctx_write(slave_ctx, fc, address, values):
    """Write values directly into a ModbusSimulatorContext registers list."""
    if fc in _BITS_FC:
        for i, v in enumerate(values):
            addr = address + i
            real = slave_ctx.fc_offset[fc] + addr // 16
            bit = addr % 16
            if real >= len(slave_ctx.registers):
                continue
            if v:
                slave_ctx.registers[real].value |= (1 << bit)
            else:
                slave_ctx.registers[real].value &= ~(1 << bit)
    else:
        for i, v in enumerate(values):
            real = slave_ctx.fc_offset[fc] + address + i
            if real >= len(slave_ctx.registers):
                continue
            slave_ctx.registers[real].value = int(v)


def _ctx_read(slave_ctx, fc, address, count=1):
    """Read values directly from a ModbusSimulatorContext registers list."""
    result = []
    if fc in _BITS_FC:
        for i in range(count):
            addr = address + i
            real = slave_ctx.fc_offset[fc] + addr // 16
            bit = addr % 16
            if real >= len(slave_ctx.registers):
                result.append(False)
            else:
                result.append(bool(slave_ctx.registers[real].value & (1 << bit)))
    else:
        for i in range(count):
            real = slave_ctx.fc_offset[fc] + address + i
            if real >= len(slave_ctx.registers):
                result.append(0)
            else:
                result.append(slave_ctx.registers[real].value)
    return result


class Server(threading.Thread):
    """Modbus Server"""

    def __init__(self, server_id, address="0.0.0.0", port=502, identity={},
                 number_of_slaves=1, number_of_registers=100, register_sizes=None):
        super().__init__(name="mod_server", daemon=True)
        self._stop_event = threading.Event()
        self.serverId = server_id
        self.address = address
        self.port = port
        self.identity = identity
        self.numberOfRegisters = number_of_registers
        self.registerSizes = register_sizes if register_sizes else {
            "co": number_of_registers,
            "di": number_of_registers,
            "hr": number_of_registers,
            "ir": number_of_registers,
        }
        self.running = False
        self.regiser_type_map = {"all": 0, "co": 1, "hr": 3, "di": 2, "ir": 4}
        self.simulation_engine = SimulationEngine()
        self.context = buildModbusContext(number_of_slaves, self.registerSizes)

    def getDetails(self):
        return {
            "server_id": self.serverId,
            "address": self.address,
            "port": self.port,
            "identity": self.identity,
            "number_of_registers": self.numberOfRegisters,
            "register_sizes": self.registerSizes,
            "running": self.running,
        }

    def __str__(self):
        return f"Modbus Server {self.serverId} on {self.address}:{self.port}"

    def get_context(self, slave=None):
        if slave is None:
            return self.context
        return self.context._devices.get(slave)

    def read_registers(self, slave_id, fc, address, count=1):
        """Read values from a slave's register space."""
        slave_ctx = self.context._devices.get(slave_id)
        if slave_ctx is None:
            return []
        return _ctx_read(slave_ctx, fc, address, count)

    def write_registers(self, slave_id, fc, address, values):
        """Write values into a slave's register space."""
        slave_ctx = self.context._devices.get(slave_id)
        if slave_ctx is None:
            return
        _ctx_write(slave_ctx, fc, address, values)

    def run(self):
        ident = ModbusDeviceIdentification()
        ident.VendorName = self.identity.get("vendor", "Pymodbus")
        ident.ProductCode = self.identity.get("product", "PM")
        ident.VendorUrl = self.identity.get("vendor_url", "")
        ident.ProductName = self.identity.get("product_name", "Pymodbus Server")
        ident.ModelName = self.identity.get("model_name", "Pymodbus Server")
        ident.MajorMinorRevision = self.identity.get("revision", "1.0")

        logger.info("Modbus server started on %s:%d", self.address, self.port)
        self.running = True

        StartTcpServer(
            context=self.context,
            identity=ident,
            address=(self.address, self.port),
        )

    def stop(self):
        self._stop_event.set()
        self.running = False
        logger.info("Modbus server stopped")

    def stopped(self):
        return self._stop_event.is_set()

    def restart(self):
        self.stop()
        self.run()

    def is_running(self):
        return self.running

    def simulate(self, registers):
        """Simulate registers using configurable simulation modes.

        Each item in `registers` is a dict with keys:
          server_id, slave_id, register_type, address, address_end,
          simulate, simulation_mode, simulation_config
        """
        register_type_map = {"all": 0, "co": 1, "di": 2, "hr": 3, "ir": 4}

        for reg in registers:
            if not reg.get("simulate"):
                continue

            reg_server_id = reg.get("server_id")
            if reg_server_id is not None and reg_server_id != self.serverId:
                continue

            slave_id = reg.get("slave_id")
            slave_ctx = self.context._devices.get(slave_id)
            if slave_ctx is None:
                logger.warning("Slave ID %s not in context; skipping.", slave_id)
                continue

            reg_type_key = reg.get("register_type")
            if reg_type_key not in register_type_map:
                logger.warning("Unsupported register type: %r; skipping.", reg_type_key)
                continue

            simulation_mode = reg.get("simulation_mode", "random")
            simulation_config = reg.get("simulation_config", {})
            register_size_override = reg.get("register_size")

            def _gen_block(kind, count, start_addr=0):
                return [
                    self.simulation_engine.generate_value(
                        simulation_mode, simulation_config, kind,
                        start_addr + i, slave_id, self.serverId,
                    )
                    for i in range(count)
                ]

            def _write_full(kind):
                fc = register_type_map[kind]
                size = (register_size_override if register_size_override is not None
                        else self.registerSizes.get(kind, self.numberOfRegisters))
                values = _gen_block(kind, size, 0)
                _ctx_write(slave_ctx, fc, 0, values)

            if reg_type_key == "all":
                for kind in ("co", "di", "hr", "ir"):
                    _write_full(kind)
                continue

            reg_type_code = register_type_map[reg_type_key]
            addr_start = int(reg.get("address", 0))
            addr_end = reg.get("address_end")
            max_size = (register_size_override if register_size_override is not None
                        else self.registerSizes.get(reg_type_key, self.numberOfRegisters))

            if addr_end is not None:
                addr_end = int(addr_end)
                if 0 <= addr_start < max_size and 0 <= addr_end < max_size and addr_start <= addr_end:
                    values = _gen_block(reg_type_key, addr_end - addr_start + 1, addr_start)
                    _ctx_write(slave_ctx, reg_type_code, addr_start, values)
                else:
                    logger.warning(
                        "Address range %s..%s out of range 0..%s for slave %s (%s).",
                        addr_start, addr_end, max_size - 1, slave_id, reg_type_key,
                    )
            elif 0 <= addr_start < max_size:
                value = self.simulation_engine.generate_value(
                    simulation_mode, simulation_config,
                    reg_type_key, addr_start, slave_id, self.serverId,
                )
                _ctx_write(slave_ctx, reg_type_code, addr_start, [value])
            else:
                logger.warning(
                    "Address %s out of range 0..%s for slave %s (%s).",
                    addr_start, max_size - 1, slave_id, reg_type_key,
                )
