"""Tests for the SimulationEngine class"""
import pytest
import math
from modSim.simulator import SimulationEngine


class TestSimulationEngine:
    """Test cases for SimulationEngine"""

    def test_init(self):
        """Test SimulationEngine initialization"""
        engine = SimulationEngine()
        assert engine.counter == 0
        assert engine.register_counters == {}

    def test_increment_counter(self):
        """Test global counter increment"""
        engine = SimulationEngine()
        engine.increment_counter()
        assert engine.counter == 1
        engine.increment_counter()
        assert engine.counter == 2

    def test_get_register_counter_new(self):
        """Test getting counter for new register"""
        engine = SimulationEngine()
        key = "0_0_hr_100"
        counter = engine.get_register_counter(key)
        assert counter == 0
        assert key in engine.register_counters

    def test_get_register_counter_existing(self):
        """Test getting counter for existing register"""
        engine = SimulationEngine()
        key = "0_0_hr_100"
        engine.register_counters[key] = 5
        counter = engine.get_register_counter(key)
        assert counter == 5

    def test_increment_register_counter(self):
        """Test register-specific counter increment"""
        engine = SimulationEngine()
        key = "0_0_hr_100"
        counter = engine.increment_register_counter(key)
        assert counter == 1
        counter = engine.increment_register_counter(key)
        assert counter == 2

    # Random Mode Tests
    def test_generate_random_boolean(self):
        """Test random mode for boolean registers"""
        engine = SimulationEngine()
        value = engine._generate_random(True, {})
        assert isinstance(value, bool)

    def test_generate_random_integer(self):
        """Test random mode for integer registers"""
        engine = SimulationEngine()
        value = engine._generate_random(False, {})
        assert isinstance(value, int)
        assert 0 <= value <= 500

    def test_generate_random_with_custom_range(self):
        """Test random mode with custom min/max"""
        engine = SimulationEngine()
        config = {"min": 100, "max": 200}
        value = engine._generate_random(False, config)
        assert isinstance(value, int)
        assert 100 <= value <= 200

    # Static Mode Tests
    def test_generate_static_boolean(self):
        """Test static mode for boolean registers"""
        engine = SimulationEngine()
        value = engine._generate_static(True, {"value": 1})
        assert value is True
        value = engine._generate_static(True, {"value": 0})
        assert value is False

    def test_generate_static_integer(self):
        """Test static mode for integer registers"""
        engine = SimulationEngine()
        config = {"value": 42}
        value = engine._generate_static(False, config)
        assert value == 42

    def test_generate_static_default(self):
        """Test static mode with default value"""
        engine = SimulationEngine()
        value = engine._generate_static(False, {})
        assert value == 0

    # Equation Mode Tests
    def test_generate_equation_simple(self):
        """Test equation mode with simple expression"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"equation": "x * 2"}
        value = engine._generate_equation(False, config, 100, 0, 0, reg_key)
        assert value == 0  # First call, x=0
        value = engine._generate_equation(False, config, 100, 0, 0, reg_key)
        assert value == 2  # Second call, x=1

    def test_generate_equation_with_address(self):
        """Test equation mode using address variable"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"equation": "x + address"}
        value = engine._generate_equation(False, config, 100, 0, 0, reg_key)
        assert value == 100  # x=0, address=100

    def test_generate_equation_with_math(self):
        """Test equation mode with math functions"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"equation": "sin(0) + 10"}
        value = engine._generate_equation(False, config, 100, 0, 0, reg_key)
        assert value == 10

    def test_generate_equation_boolean(self):
        """Test equation mode for boolean registers"""
        engine = SimulationEngine()
        reg_key = "0_0_co_50"
        config = {"equation": "x > 5"}
        value = engine._generate_equation(True, config, 50, 0, 0, reg_key)
        assert value is False  # x=0
        # Call 6 more times to get x > 5
        for _ in range(6):
            value = engine._generate_equation(True, config, 50, 0, 0, reg_key)
        assert value is True

    def test_generate_equation_invalid(self):
        """Test equation mode with invalid expression"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"equation": "invalid_function()"}
        value = engine._generate_equation(False, config, 100, 0, 0, reg_key)
        # Should fallback to random
        assert isinstance(value, int)

    def test_generate_equation_complex(self):
        """Test equation mode with complex expression"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"equation": "sin(x / 10) * 100 + address"}
        value = engine._generate_equation(False, config, 100, 0, 0, reg_key)
        expected = int(math.sin(0 / 10) * 100 + 100)
        assert value == expected

    # Ramp Mode Tests
    def test_generate_ramp_basic(self):
        """Test ramp mode basic functionality"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"min": 0, "max": 10, "step": 2}

        values = []
        for _ in range(7):
            values.append(engine._generate_ramp(False, config, reg_key))

        assert values == [0, 2, 4, 6, 8, 10, 0]  # Should wrap

    def test_generate_ramp_boolean(self):
        """Test ramp mode for boolean registers"""
        engine = SimulationEngine()
        reg_key = "0_0_co_50"
        config = {"min": 0, "max": 10, "step": 1}

        values = []
        for _ in range(5):
            values.append(engine._generate_ramp(True, config, reg_key))

        # Boolean should alternate based on odd/even
        assert values[0] is False  # 0 % 2 = 0
        assert values[1] is True   # 1 % 2 = 1
        assert values[2] is False  # 2 % 2 = 0

    def test_generate_ramp_default_config(self):
        """Test ramp mode with default configuration"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        value = engine._generate_ramp(False, {}, reg_key)
        assert value == 0  # First value should be min (default 0)

    # Sine Mode Tests
    def test_generate_sine_basic(self):
        """Test sine mode basic functionality"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"amplitude": 100, "offset": 200, "period": 60}

        # Test a few values
        value1 = engine._generate_sine(False, config, reg_key)
        value2 = engine._generate_sine(False, config, reg_key)

        assert isinstance(value1, int)
        assert isinstance(value2, int)
        # Values should be in expected range
        assert 100 <= value1 <= 300
        assert 100 <= value2 <= 300

    def test_generate_sine_boolean(self):
        """Test sine mode for boolean registers"""
        engine = SimulationEngine()
        reg_key = "0_0_co_50"
        config = {"amplitude": 100, "offset": 0, "period": 20}

        value = engine._generate_sine(True, config, reg_key)
        assert isinstance(value, bool)

    def test_generate_sine_full_cycle(self):
        """Test sine mode completes a full cycle"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"amplitude": 100, "offset": 0, "period": 10}

        values = []
        for _ in range(10):
            values.append(engine._generate_sine(False, config, reg_key))

        # Should have both positive and negative values in a cycle
        assert max(values) > 50
        assert min(values) < -50

    # Square Mode Tests
    def test_generate_square_basic(self):
        """Test square mode basic functionality"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"high": 100, "low": 0, "period": 10, "duty_cycle": 0.5}

        values = []
        for _ in range(10):
            values.append(engine._generate_square(False, config, reg_key))

        # First half should be high, second half low
        assert values[0] == 100
        assert values[4] == 100
        assert values[5] == 0
        assert values[9] == 0

    def test_generate_square_boolean(self):
        """Test square mode for boolean registers"""
        engine = SimulationEngine()
        reg_key = "0_0_co_50"
        config = {"high": 1, "low": 0, "period": 10, "duty_cycle": 0.5}

        values = []
        for _ in range(10):
            values.append(engine._generate_square(True, config, reg_key))

        assert values[0] is True
        assert values[4] is True
        assert values[5] is False

    def test_generate_square_custom_duty_cycle(self):
        """Test square mode with custom duty cycle"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"
        config = {"high": 100, "low": 0, "period": 10, "duty_cycle": 0.3}

        values = []
        for _ in range(10):
            values.append(engine._generate_square(False, config, reg_key))

        # 30% duty cycle = 3 high, 7 low
        high_count = sum(1 for v in values if v == 100)
        assert high_count == 3

    # Integration Tests
    def test_generate_value_all_modes(self):
        """Test generate_value method with all modes"""
        engine = SimulationEngine()

        modes = ["random", "static", "equation", "ramp", "sine", "square"]
        configs = [
            {},
            {"value": 42},
            {"equation": "x + 10"},
            {"min": 0, "max": 100, "step": 5},
            {"amplitude": 100, "offset": 0, "period": 60},
            {"high": 100, "low": 0, "period": 10, "duty_cycle": 0.5}
        ]

        for mode, config in zip(modes, configs):
            value = engine.generate_value(mode, config, "hr", 100, 0, 0)
            assert isinstance(value, int)

    def test_generate_value_unknown_mode(self):
        """Test generate_value with unknown mode"""
        engine = SimulationEngine()
        value = engine.generate_value("unknown", {}, "hr", 100, 0, 0)
        # Should fallback to random
        assert isinstance(value, int)

    def test_multiple_registers_independent_counters(self):
        """Test that different registers have independent counters"""
        engine = SimulationEngine()

        reg_key1 = "0_0_hr_100"
        reg_key2 = "0_0_hr_200"

        config = {"equation": "x"}

        # Generate values for register 1
        value1 = engine._generate_equation(False, config, 100, 0, 0, reg_key1)
        value1 = engine._generate_equation(False, config, 100, 0, 0, reg_key1)

        # Generate values for register 2
        value2 = engine._generate_equation(False, config, 200, 0, 0, reg_key2)

        # Register 1 should be at counter 1 (second call)
        # Register 2 should be at counter 0 (first call)
        assert value1 == 1
        assert value2 == 0

    def test_generate_value_boolean_types(self):
        """Test generate_value correctly identifies boolean types"""
        engine = SimulationEngine()

        # Test coils
        value = engine.generate_value("static", {"value": 1}, "co", 0, 0, 0)
        assert isinstance(value, bool)

        # Test discrete inputs
        value = engine.generate_value("static", {"value": 0}, "di", 0, 0, 0)
        assert isinstance(value, bool)

        # Test holding registers
        value = engine.generate_value("static", {"value": 42}, "hr", 0, 0, 0)
        assert isinstance(value, int)

        # Test input registers
        value = engine.generate_value("static", {"value": 42}, "ir", 0, 0, 0)
        assert isinstance(value, int)

    def test_equation_security(self):
        """Test that equation mode blocks unsafe operations"""
        engine = SimulationEngine()
        reg_key = "0_0_hr_100"

        # Try to use __import__ (should fail and fallback to random)
        config = {"equation": "__import__('os')"}
        value = engine._generate_equation(False, config, 100, 0, 0, reg_key)
        assert isinstance(value, int)  # Should fallback to random

        # Try to use open (should fail)
        config = {"equation": "open('file.txt')"}
        value = engine._generate_equation(False, config, 100, 0, 0, reg_key)
        assert isinstance(value, int)
