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

    def generate_value(self, mode, config, register_type, address, slave_id, server_id, float32=False):
        """Generate a simulated value based on the mode and configuration.

        When float32=True the return value is a Python float (caller is
        responsible for encoding it as two 16-bit registers).
        """
        is_boolean = register_type in ("co", "di")
        reg_key = f"{server_id}_{slave_id}_{register_type}_{address}"

        try:
            if mode == "random":
                raw = self._generate_random(is_boolean, config, float32)
            elif mode == "static":
                raw = self._generate_static(is_boolean, config, float32)
            elif mode == "equation":
                raw = self._generate_equation(is_boolean, config, address, slave_id, server_id, reg_key, float32)
            elif mode == "ramp":
                raw = self._generate_ramp(is_boolean, config, reg_key, float32)
            elif mode == "sine":
                raw = self._generate_sine(is_boolean, config, reg_key, float32)
            elif mode == "square":
                raw = self._generate_square(is_boolean, config, reg_key, float32)
            else:
                logger.warning(f"Unknown simulation mode: {mode}, defaulting to random")
                raw = self._generate_random(is_boolean, config, float32)
        except Exception as e:
            logger.error(f"Error generating value for mode {mode}: {e}")
            raw = self._generate_random(is_boolean, config, float32)

        return raw

    def _generate_random(self, is_boolean, config, float32=False):
        if is_boolean:
            return random.choice([True, False])
        min_val = config.get("min", 0)
        max_val = config.get("max", 500)
        if float32:
            return random.uniform(min_val, max_val)
        return random.randint(int(min_val), int(max_val))

    def _generate_static(self, is_boolean, config, float32=False):
        value = config.get("value", 0)
        if is_boolean:
            return bool(value)
        return float(value) if float32 else int(value)

    def _generate_equation(self, is_boolean, config, address, slave_id, server_id, reg_key, float32=False):
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
            return float(result) if float32 else int(result)
        except Exception as e:
            logger.error(f"Error evaluating equation '{equation}': {e}")
            return self._generate_random(is_boolean, config, float32)

    def _generate_ramp(self, is_boolean, config, reg_key, float32=False):
        min_val = config.get("min", 0)
        max_val = config.get("max", 100)
        step = config.get("step", 1)

        counter = self.get_register_counter(reg_key)
        value = min_val + (counter * step)

        if value > max_val:
            self.register_counters[reg_key] = 0
            value = min_val
        else:
            self.increment_register_counter(reg_key)

        if is_boolean:
            return bool(value % 2)
        return float(value) if float32 else int(value)

    def _generate_sine(self, is_boolean, config, reg_key, float32=False):
        amplitude = config.get("amplitude", 100)
        offset = config.get("offset", 0)
        period = config.get("period", 60)

        counter = self.increment_register_counter(reg_key)
        value = amplitude * math.sin(2 * math.pi * counter / period) + offset

        if is_boolean:
            return value > offset
        return float(value) if float32 else int(value)

    def _generate_square(self, is_boolean, config, reg_key, float32=False):
        high_value = config.get("high", 100)
        low_value = config.get("low", 0)
        period = config.get("period", 10)
        duty_cycle = config.get("duty_cycle", 0.5)

        counter = self.get_register_counter(reg_key)
        cycle_position = (counter % period) / period
        value = high_value if cycle_position < duty_cycle else low_value

        self.increment_register_counter(reg_key)

        if is_boolean:
            return bool(value)
        return float(value) if float32 else int(value)
