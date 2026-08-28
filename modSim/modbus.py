"""Handles Modbus objects"""
import asyncio
import logging
import struct
import threading

from pymodbus import ModbusDeviceIdentification
from pymodbus.datastore import ModbusServerContext
from pymodbus.server import ModbusTcpServer
from pymodbus.simulator.simdata import SimData, DataType
from pymodbus.simulator.simdevice import SimDevice
from pymodbus.simulator.simcore import SimCore
from modSim.simulator import SimulationEngine

logger = logging.getLogger(__name__)

_BITS_FC = frozenset((1, 2, 5, 15))
_FC_BLOCK = {1: 'c', 2: 'd', 3: 'h', 4: 'i', 5: 'c', 15: 'c'}


class _SimContext(ModbusServerContext):
    """Multi-slave context built on SimCore/SimRuntime.

    Subclasses ModbusServerContext so pymodbus's server treats it as a
    ready-made context (the `not simdevices` branch) without wrapping it
    in a second SimCore. __init__ intentionally does NOT call
    super().__init__() to avoid the ModbusServerContext deprecation log.
    """

    simdevices = []     # falsy → server skips SimCore wrapping
    old_simulator = True  # → server uses this context object directly

    def __init__(self, devices: list[SimDevice]):
        self._simcore = SimCore(devices)
        self._runtimes = self._simcore.devices  # {slave_id: SimRuntime}

    def device_ids(self) -> list:
        return list(self._runtimes.keys())

    async def async_getValues(self, device_id: int, func_code: int, address: int, count: int = 1):
        return await self._simcore.async_getValues(device_id, func_code, address, count)

    async def async_setValues(self, device_id: int, func_code: int, address: int, values):
        return await self._simcore.async_setValues(device_id, func_code, address, values)


def _build_slave_simdevice(slave_id: int, co_size=100, di_size=100,
                            hr_size=100, ir_size=100) -> SimDevice:
    """Build one SimDevice for a single slave."""
    return SimDevice(slave_id, simdata=(
        [SimData(0, count=max(co_size, 1), values=False, datatype=DataType.BITS)],
        [SimData(0, count=max(di_size, 1), values=False, datatype=DataType.BITS)],
        [SimData(0, count=max(hr_size, 1), values=0,     datatype=DataType.REGISTERS)],
        [SimData(0, count=max(ir_size, 1), values=0,     datatype=DataType.REGISTERS)],
    ))


def buildModbusContext(slaves, register_sizes=None):
    """Build a _SimContext with one SimDevice per slave.

    `slaves` may be either:
      - an int N (legacy): create slave ids 0..N-1, all using `register_sizes`; or
      - a list of slave dicts, each with a `slave_id` and optional per-slave
        `co_size`/`di_size`/`hr_size`/`ir_size` (falling back to `register_sizes`).

    The list form preserves the actual slave ids from the configuration, so a
    server can expose non-zero / non-contiguous ids (e.g. slaves 1 and 2 with no
    slave 0) rather than always 0..N-1.
    """
    if register_sizes is None:
        register_sizes = {"co": 100, "di": 100, "hr": 100, "ir": 100}
    if isinstance(slaves, int):
        slaves = [{"slave_id": i} for i in range(slaves)]
    devices = [
        _build_slave_simdevice(
            s["slave_id"],
            co_size=s.get("co_size", register_sizes.get("co", 100)),
            di_size=s.get("di_size", register_sizes.get("di", 100)),
            hr_size=s.get("hr_size", register_sizes.get("hr", 100)),
            ir_size=s.get("ir_size", register_sizes.get("ir", 100)),
        )
        for s in slaves
    ]
    return _SimContext(devices)


def _ctx_write(runtime, fc: int, address: int, values):
    """Write values directly into a SimRuntime block."""
    block_key = _FC_BLOCK.get(fc, 'h')
    start, _, registers, _ = runtime.block[block_key]
    offset = address - start
    if fc in _BITS_FC:
        for i, v in enumerate(values):
            a = offset + i
            word = a // 16
            bit  = a % 16
            if word >= len(registers):
                continue
            if v:
                registers[word] |= (1 << bit)
            else:
                registers[word] &= ~(1 << bit)
    else:
        for i, v in enumerate(values):
            idx = offset + i
            if 0 <= idx < len(registers):
                registers[idx] = int(v)


def _ctx_read(runtime, fc: int, address: int, count: int = 1):
    """Read values directly from a SimRuntime block."""
    block_key = _FC_BLOCK.get(fc, 'h')
    start, _, registers, _ = runtime.block[block_key]
    offset = address - start
    if fc in _BITS_FC:
        result = []
        for i in range(count):
            a = offset + i
            word = a // 16
            bit  = a % 16
            if word >= len(registers):
                result.append(False)
            else:
                result.append(bool(registers[word] & (1 << bit)))
        return result
    else:
        return list(registers[offset:offset + count])


class Server(threading.Thread):
    """Modbus Server"""

    def __init__(self, server_id, address="0.0.0.0", port=502, identity={},
                 number_of_slaves=1, number_of_registers=100, register_sizes=None,
                 zero_based=True, slaves=None):
        super().__init__(name="mod_server", daemon=True)
        self._stop_event = threading.Event()
        self._loop = None            # event loop owned by this thread
        self._async_server = None    # pymodbus ModbusTcpServer instance
        self.serverId = server_id
        # When False, register-rule addresses are treated as 1-based: address N
        # maps to 0-based datastore offset N-1 (the Modbus wire is always 0-based).
        self.zero_based = zero_based
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
        # Prefer an explicit slave spec (real ids + per-slave sizes); fall back
        # to the legacy count, which yields slave ids 0..number_of_slaves-1.
        self.context = buildModbusContext(
            slaves if slaves is not None else number_of_slaves,
            self.registerSizes,
        )

    def getDetails(self):
        return {
            "server_id": self.serverId,
            "address": self.address,
            "port": self.port,
            "identity": self.identity,
            "number_of_registers": self.numberOfRegisters,
            "register_sizes": self.registerSizes,
            "zero_based": self.zero_based,
            "running": self.running,
        }

    def __str__(self):
        return f"Modbus Server {self.serverId} on {self.address}:{self.port}"

    def get_context(self, slave=None):
        if slave is None:
            return self.context
        return self.context._runtimes.get(slave)

    def read_registers(self, slave_id, fc, address, count=1):
        """Read values from a slave's register space."""
        runtime = self.context._runtimes.get(slave_id)
        if runtime is None:
            return []
        return _ctx_read(runtime, fc, address, count)

    def write_registers(self, slave_id, fc, address, values):
        """Write values into a slave's register space."""
        runtime = self.context._runtimes.get(slave_id)
        if runtime is None:
            return
        _ctx_write(runtime, fc, address, values)

    def write_float_registers(self, slave_id, address, float_values, fc=3):
        """Encode each float32 as two big-endian uint16 words and write to HR/IR."""
        words = []
        for v in float_values:
            hi, lo = struct.unpack('>HH', struct.pack('>f', float(v)))
            words.extend([hi, lo])
        self.write_registers(slave_id, fc, address, words)

    def read_float_registers(self, slave_id, address, count=1, fc=3):
        """Read count float32 values (2 raw registers each) from HR/IR."""
        raw = self.read_registers(slave_id, fc, address, count * 2)
        result = []
        for i in range(count):
            hi, lo = raw[i * 2], raw[i * 2 + 1]
            result.append(struct.unpack('>f', struct.pack('>HH', hi, lo))[0])
        return result

    def run(self):
        ident = ModbusDeviceIdentification()
        ident.VendorName = self.identity.get("vendor", "Pymodbus")
        ident.ProductCode = self.identity.get("product", "PM")
        ident.VendorUrl = self.identity.get("vendor_url", "")
        ident.ProductName = self.identity.get("product_name", "Pymodbus Server")
        ident.ModelName = self.identity.get("model_name", "Pymodbus Server")
        ident.MajorMinorRevision = self.identity.get("revision", "1.0")

        # Own the event loop for this thread so stop() can shut the server
        # (and free the listening socket) down cleanly from another thread.
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve(ident))
        except Exception as e:
            logger.error("Modbus server on %s:%d stopped with error: %s",
                         self.address, self.port, e)
        finally:
            self.running = False
            self._async_server = None
            self._loop.close()
            self._loop = None
            logger.info("Modbus server on %s:%d exited", self.address, self.port)

    async def _serve(self, ident):
        self._async_server = ModbusTcpServer(
            self.context,
            identity=ident,
            address=(self.address, self.port),
        )
        logger.info("Modbus server started on %s:%d", self.address, self.port)
        self.running = True
        await self._async_server.serve_forever()

    def stop(self):
        """Shut the TCP server down and release the listening socket.

        Runs the async shutdown on the server's own loop from the calling
        thread and waits for it, so the port is free before any replacement
        server tries to bind it.
        """
        self._stop_event.set()
        srv = self._async_server
        loop = self._loop
        if srv is not None and loop is not None and loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(srv.shutdown(), loop)
                fut.result(timeout=5)
            except Exception as e:
                logger.warning("Error shutting down modbus server on %s:%d: %s",
                               self.address, self.port, e)
        self.running = False
        logger.info("Modbus server on %s:%d stop requested", self.address, self.port)

    def stopped(self):
        return self._stop_event.is_set()

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
            runtime = self.context._runtimes.get(slave_id)
            if runtime is None:
                logger.warning("Slave ID %s not in context; skipping.", slave_id)
                continue

            reg_type_key = reg.get("register_type")
            if reg_type_key not in register_type_map:
                logger.warning("Unsupported register type: %r; skipping.", reg_type_key)
                continue

            simulation_mode = reg.get("simulation_mode", "random")
            simulation_config = reg.get("simulation_config", {})
            register_size_override = reg.get("register_size")
            use_float32 = bool(simulation_config.get("float32", False))

            def _gen_value(kind, addr):
                return self.simulation_engine.generate_value(
                    simulation_mode, simulation_config, kind,
                    addr, slave_id, self.serverId, float32=use_float32,
                )

            def _gen_block(kind, count, start_addr=0):
                return [_gen_value(kind, start_addr + i) for i in range(count)]

            def _write_full(kind):
                fc = register_type_map[kind]
                size = (register_size_override if register_size_override is not None
                        else self.registerSizes.get(kind, self.numberOfRegisters))
                if use_float32 and kind in ("hr", "ir"):
                    float_count = size // 2
                    self.write_float_registers(slave_id, 0, _gen_block(kind, float_count, 0), fc=fc)
                else:
                    _ctx_write(runtime, fc, 0, _gen_block(kind, size, 0))

            if reg_type_key == "all":
                for kind in ("co", "di", "hr", "ir"):
                    _write_full(kind)
                continue

            reg_type_code = register_type_map[reg_type_key]
            # For 1-based servers, shift the datastore write target down by one;
            # generation (and equation `address`) keeps the user-facing address.
            addr_offset = 0 if self.zero_based else 1
            addr_start = int(reg.get("address", 0))
            addr_end = reg.get("address_end")
            write_start = addr_start - addr_offset
            max_size = (register_size_override if register_size_override is not None
                        else self.registerSizes.get(reg_type_key, self.numberOfRegisters))

            is_numeric = reg_type_key in ("hr", "ir")

            if addr_end is not None:
                addr_end = int(addr_end)
                write_end = addr_end - addr_offset
                if 0 <= write_start < max_size and 0 <= write_end < max_size and write_start <= write_end:
                    if use_float32 and is_numeric:
                        # addr_start..addr_end are physical registers; each float32 = 2 registers
                        float_count = (write_end - write_start + 1) // 2
                        floats = _gen_block(reg_type_key, float_count, addr_start)
                        self.write_float_registers(slave_id, write_start, floats, fc=reg_type_code)
                    else:
                        values = _gen_block(reg_type_key, write_end - write_start + 1, addr_start)
                        _ctx_write(runtime, reg_type_code, write_start, values)
                else:
                    logger.warning(
                        "Address range %s..%s out of range for slave %s (%s), %s-based.",
                        addr_start, addr_end, slave_id, reg_type_key,
                        "0" if self.zero_based else "1",
                    )
            elif 0 <= write_start < max_size:
                if use_float32 and is_numeric:
                    self.write_float_registers(slave_id, write_start, [_gen_value(reg_type_key, addr_start)], fc=reg_type_code)
                else:
                    _ctx_write(runtime, reg_type_code, write_start, [_gen_value(reg_type_key, addr_start)])
            else:
                logger.warning(
                    "Address %s out of range for slave %s (%s), %s-based.",
                    addr_start, slave_id, reg_type_key,
                    "0" if self.zero_based else "1",
                )
