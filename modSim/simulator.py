"""Simulation engine for different register simulation modes"""
import math
import random
import logging

logger = logging.getLogger(__name__)


class SimulationEngine:
    """Handles different simulation modes for register values"""

    def __init__(self):
        self.counter = 0
        self.register_counters = {}  # Track individual counters per register

    def increment_counter(self):
        """Increment global counter"""
        self.counter += 1

    def get_register_counter(self, key):
        """Get or initialize counter for specific register"""
        if key not in self.register_counters:
            self.register_counters[key] = 0
        return self.register_counters[key]

    def increment_register_counter(self, key):
        """Increment counter for specific register"""
        if key not in self.register_counters:
            self.register_counters[key] = 0
        self.register_counters[key] += 1
        return self.register_counters[key]

    def generate_value(self, mode, config, register_type, address, slave_id, server_id):
        """
        Generate a simulated value based on the mode and configuration.

        Args:
            mode: Simulation mode (random, static, equation, ramp, sine, square)
            config: Configuration dict with mode-specific parameters
            register_type: Type of register (co, di, hr, ir)
            address: Register address
            slave_id: Slave ID
            server_id: Server ID

        Returns:
            Simulated value (bool for co/di, int for hr/ir)
        """
        is_boolean = register_type in ("co", "di")

        # Create unique key for this register
        reg_key = f"{server_id}_{slave_id}_{register_type}_{address}"

        try:
            if mode == "random":
                return self._generate_random(is_boolean, config)
            elif mode == "static":
                return self._generate_static(is_boolean, config)
            elif mode == "equation":
                return self._generate_equation(is_boolean, config, address, slave_id, server_id, reg_key)
            elif mode == "ramp":
                return self._generate_ramp(is_boolean, config, reg_key)
            elif mode == "sine":
                return self._generate_sine(is_boolean, config, reg_key)
            elif mode == "square":
                return self._generate_square(is_boolean, config, reg_key)
            else:
                logger.warning(f"Unknown simulation mode: {mode}, defaulting to random")
                return self._generate_random(is_boolean, config)
        except Exception as e:
            logger.error(f"Error generating value for mode {mode}: {e}")
            return self._generate_random(is_boolean, config)

    def _generate_random(self, is_boolean, config):
        """Generate random value"""
        if is_boolean:
            return random.choice([True, False])
        min_val = config.get("min", 0)
        max_val = config.get("max", 500)
        return random.randint(min_val, max_val)

    def _generate_static(self, is_boolean, config):
        """Generate static value"""
        value = config.get("value", 0)
        if is_boolean:
            return bool(value)
        return int(value)

    def _generate_equation(self, is_boolean, config, address, slave_id, server_id, reg_key):
        """Generate value from equation"""
        equation = config.get("equation", "x")

        # Get counter for this specific register
        x = self.get_register_counter(reg_key)

        # Safe namespace for equation evaluation
        safe_namespace = {
            'x': x,
            'address': address,
            'slave_id': slave_id,
            'server_id': server_id,
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'asin': math.asin,
            'acos': math.acos,
            'atan': math.atan,
            'atan2': math.atan2,
            'sinh': math.sinh,
            'cosh': math.cosh,
            'tanh': math.tanh,
            'sqrt': math.sqrt,
            'abs': abs,
            'pow': pow,
            'exp': math.exp,
            'log': math.log,
            'log10': math.log10,
            'floor': math.floor,
            'ceil': math.ceil,
            'round': round,
            'min': min,
            'max': max,
            'pi': math.pi,
            'e': math.e,
            '__builtins__': {}  # Disable builtins for security
        }

        try:
            result = eval(equation, safe_namespace)
            self.increment_register_counter(reg_key)

            if is_boolean:
                return bool(result)
            return int(result)
        except Exception as e:
            logger.error(f"Error evaluating equation '{equation}': {e}")
            return self._generate_random(is_boolean, config)

    def _generate_ramp(self, is_boolean, config, reg_key):
        """Generate ramp value"""
        min_val = config.get("min", 0)
        max_val = config.get("max", 100)
        step = config.get("step", 1)

        counter = self.get_register_counter(reg_key)
        value = min_val + (counter * step)

        # Wrap around when exceeding max
        if value > max_val:
            self.register_counters[reg_key] = 0
            value = min_val
        else:
            self.increment_register_counter(reg_key)

        if is_boolean:
            return bool(value % 2)
        return int(value)

    def _generate_sine(self, is_boolean, config, reg_key):
        """Generate sine wave value"""
        amplitude = config.get("amplitude", 100)
        offset = config.get("offset", 0)
        period = config.get("period", 60)  # Period in simulation cycles

        counter = self.increment_register_counter(reg_key)
        value = amplitude * math.sin(2 * math.pi * counter / period) + offset

        if is_boolean:
            return value > offset
        return int(value)

    def _generate_square(self, is_boolean, config, reg_key):
        """Generate square wave value"""
        high_value = config.get("high", 100)
        low_value = config.get("low", 0)
        period = config.get("period", 10)  # Period in simulation cycles
        duty_cycle = config.get("duty_cycle", 0.5)  # 0.0 to 1.0

        counter = self.get_register_counter(reg_key)
        cycle_position = (counter % period) / period

        value = high_value if cycle_position < duty_cycle else low_value

        self.increment_register_counter(reg_key)

        if is_boolean:
            return bool(value)
        return int(value)
