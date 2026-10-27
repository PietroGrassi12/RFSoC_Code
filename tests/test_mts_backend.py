import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mts_hardware import MTSHardware


class FakePin:
    def __init__(self):
        self.is_on = False
    def on(self):
        self.is_on = True
    def off(self):
        self.is_on = False


class FakeOverlay:
    def __init__(self):
        self.dac_enable = FakePin()
        self.dac_player = np.zeros(4096, dtype=np.int16)
        self.adc_capture_chA = np.zeros(1024, dtype=np.int16)
        self.adc_capture_chB = np.zeros(1024, dtype=np.int16)
        self.adc_capture_chC = np.zeros(1024, dtype=np.int16)
    def internal_capture(self, capture):
        self.dac_enable.on()
        capture[:] = 42


class TestMTSFakeBackend(unittest.TestCase):
    def setUp(self):
        self.hw = MTSHardware()
        self.hw.overlay = FakeOverlay()
        self.hw._loaded = True

    def test_write_start_stop(self):
        self.hw.write(np.ones(self.hw.ram_samples) * .1)
        self.assertFalse(self.hw.overlay.dac_enable.is_on)
        with self.assertRaises(RuntimeError):
            self.hw.start()
        self.hw.start(confirm_hardware_ready=True)
        self.assertTrue(self.hw.overlay.dac_enable.is_on)
        self.hw.stop()
        self.assertFalse(self.hw.overlay.dac_enable.is_on)

    def test_capture_requires_explicit_confirmation(self):
        self.hw.write(np.ones(self.hw.ram_samples) * .1)
        with self.assertRaises(RuntimeError):
            self.hw.capture_internal(128)
        data = self.hw.capture_internal(128, confirm_hardware_ready=True)
        self.assertEqual(data.shape, (3,128))
        self.assertTrue(np.all(data == 42))


if __name__ == '__main__':
    unittest.main()
