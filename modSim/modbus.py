""" Handles Modbus objects """
import copy
import logging
import threading
import random

from pymodbus import ModbusDeviceIdentification
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusDeviceContext,
)
from pymodbus.server import StartTcpServer

logger = logging.getLogger(__name__)


def buildModbusContext(numberOfSlaves, registerSizes=None):
    """
    Build the modbus context.
    Using address 0 to match Modbus protocol where client addresses start at 0.
    Note: We allocate registerSize + 1 to work around pymodbus address validation.

    Args:
        numberOfSlaves: Number of slave devices
        registerSizes: Dict with keys 'co', 'di', 'hr', 'ir' specifying size for each type.
                      If None, defaults to 100 for all types.
    """
    if registerSizes is None:
        registerSizes = {'co': 100, 'di': 100, 'hr': 100, 'ir': 100}

    slaves = {}

    baseDataStore = ModbusDeviceContext(
        di=ModbusSequentialDataBlock(0, [False] * (registerSizes.get('di', 100) + 1)),
        co=ModbusSequentialDataBlock(0, [False] * (registerSizes.get('co', 100) + 1)),
        hr=ModbusSequentialDataBlock(0, [0] * (registerSizes.get('hr', 100) + 1)),
        ir=ModbusSequentialDataBlock(0, [0] * (registerSizes.get('ir', 100) + 1))
    )

    # Create datastores for slaves
    for slave in range(numberOfSlaves):
        slaves[slave] = copy.deepcopy(baseDataStore)

    context = ModbusServerContext(devices=slaves, single=False)

    return context


class Server(threading.Thread):
    """Modbus Server"""

    def __init__(self, serverId, address="0.0.0.0", port=502, identity={}, numberOfSlaves=1, numberOfRegisters=100, registerSizes=None):
        super().__init__(name="mod_server", daemon=True)
        self._stop_event = threading.Event()
        self.serverId = serverId
        self.address = address
        self.port = port
        self.identity = identity
        self.numberOfRegisters = numberOfRegisters
        self.registerSizes = registerSizes if registerSizes else {
            'co': numberOfRegisters,
            'di': numberOfRegisters,
            'hr': numberOfRegisters,
            'ir': numberOfRegisters
        }
        self.running = False
        self.regiser_type_map = {
            "all": 0,
            "co": 1,
            "hr": 3,
            "di": 2,
            "ir": 4
        }

        # Build the context
        self.context = buildModbusContext(numberOfSlaves, self.registerSizes)

    def getDetails(self):
        """Get the server details"""
        return {
            "server_id": self.serverId,
            "address": self.address,
            "port": self.port,
            "identity": self.identity,
            "number_of_registers": self.numberOfRegisters,
            "register_sizes": self.registerSizes,
            "running": self.running
        }

    def __str__(self):
        return f"Modbus Server {self.serverId} on {self.address}:{self.port}"

    def get_context(self, slave=None):
        """Get the modbus context"""
        if slave is None:
            return self.context

        return self.context[slave]

    def get_coils(self, slave=0):
        """Get the coils"""
        return self.context[slave].getValues(1, 0, count=100)

    def set_coil(self, address, value, slave=0):
        """Set a single coil"""
        self.context[slave].setValues(1, address, [value])

    def set_coils(self, values: list, slave=0):
        """Set the coils"""
        self.context[slave].setValues(1, 0, values)

    def get_holding_registers(self, slave=0):
        """Get the holding registers"""
        return self.context[slave].getValues(3, 0, count=100)

    def set_holding_register(self, address, value, slave=0):
        """Set a single holding register"""
        self.context[slave].setValues(3, address, [value])

    def set_holding_registers(self, values: list, slave=0):
        """Set the holding registers"""
        self.context[slave].setValues(3, 0, values)

    def get_discrete_inputs(self, slave=0):
        """Get the discrete inputs"""
        return self.context[slave].getValues(2, 0, count=100)

    def set_discrete_input(self, address, value, slave=0):
        """Set a single discrete input"""
        self.context[slave].setValues(2, address, [value])

    def set_discrete_inputs(self, values: list, slave=0):
        """Set the discrete inputs"""
        self.context[slave].setValues(2, 0, values)

    def get_input_registers(self, slave=0):
        """Get the input registers"""
        return self.context[slave].getValues(4, 0, count=100)

    def set_input_register(self, address, value, slave=0):
        """Set a single input register"""
        self.context[slave].setValues(4, address, [value])

    def set_input_registers(self, values: list, slave=0):
        """Set the input registers"""
        self.context[slave].setValues(4, 0, values)

    def run(self):
        """Start the Modbus server"""
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
        """ When called, sets the stop event """
        self._stop_event.set()
        self.running = False
        logger.info("Modbus server stopped")

    def stopped(self):
        """ Returns true when stop is called """
        return self._stop_event.is_set()

    def restart(self):
        """Restart the server"""
        self.stop()
        self.run()

    def is_running(self):
        """Check if the server is running"""
        return self.running

    def simulate(self, registers):
        """Simulate registers with random values.

        Each item in `registers` is expected to be a dict with keys like:
        {
            "server_id": <int>,
            "slave_id": <int>,
            "register_type": "co"|"di"|"hr"|"ir"|"all",
            "address": <int>,
            "address_end": <int|None>,  # Optional: end address for range
            "register_size": <int|None>,  # Optional: override register size
            "simulate": <bool>
        }
        """
        # Map: name -> Modbus function-code group
        register_type_map = {"all": 0, "co": 1, "di": 2, "hr": 3, "ir": 4}

        for reg in registers:
            if not reg.get("simulate"):
                continue
            # If server_id is None, apply to all servers; otherwise match specific server
            reg_server_id = reg.get("server_id")
            if reg_server_id is not None and reg_server_id != self.serverId:
                continue

            slave_id = reg.get("slave_id")
            if slave_id not in self.context.device_ids():
                logger.warning(
                    "Slave ID %s not in context; skipping.", slave_id)
                continue

            reg_type_key = reg.get("register_type")
            if reg_type_key not in register_type_map:
                logger.warning("Unsupported register type: %r; skipping.",
                               reg_type_key)
                continue

            # Get register size (use override if provided, otherwise use configured size)
            register_size_override = reg.get("register_size")

            # Helper to generate a block of values
            def _gen_block(kind, count):
                if kind in ("di", "co"):
                    return [random.choice([True, False]) for _ in range(count)]
                return [random.randrange(0, 500) for _ in range(count)]

            # Write a full block for the given kind
            def _write_full(kind):
                code = register_type_map[kind]
                # Use override size if provided, otherwise use configured size for this type
                size = register_size_override if register_size_override is not None else self.registerSizes.get(kind, self.numberOfRegisters)
                values = _gen_block(kind, size)
                self.context[slave_id].setValues(code, 0, values)

            # Handle "all" by writing every kind
            if reg_type_key == "all":
                for kind in ("co", "di", "hr", "ir"):
                    _write_full(kind)
                continue

            # Handle a specific kind
            reg_type_code = register_type_map[reg_type_key]
            addr_start = int(reg.get("address", 0))
            addr_end = reg.get("address_end")

            # Get the max size for this register type
            max_size = register_size_override if register_size_override is not None else self.registerSizes.get(reg_type_key, self.numberOfRegisters)

            # Handle range simulation
            if addr_end is not None:
                addr_end = int(addr_end)
                if 0 <= addr_start < max_size and 0 <= addr_end < max_size and addr_start <= addr_end:
                    count = addr_end - addr_start + 1
                    values = _gen_block(reg_type_key, count)
                    self.context[slave_id].setValues(reg_type_code, addr_start, values)
                else:
                    logger.warning(
                        "Address range %s..%s out of range 0..%s for slave %s (%s).",
                        addr_start,
                        addr_end,
                        max_size - 1,
                        slave_id,
                        reg_type_key
                    )
            # Handle single address simulation
            elif 0 <= addr_start < max_size:
                value = (_gen_block(reg_type_key, 1)[0])
                self.context[slave_id].setValues(reg_type_code, addr_start, [value])
            else:
                logger.warning(
                    "Address %s out of range 0..%s for slave %s (%s).",
                    addr_start,
                    max_size - 1,
                    slave_id,
                    reg_type_key
                )
