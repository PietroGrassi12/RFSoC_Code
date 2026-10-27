import sys
import unittest
from pathlib import Path
from dataclasses import replace
import tempfile
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from waveforms import RadarConfig, generate, rf_plan, to_dac_int16, DAC_FS_HZ
from processing import circular_delay, digital_dechirp, beat_peak_hz, range_from_beat


class TestWaveforms(unittest.TestCase):
    def test_if_plan_c_band(self):
        cfg = RadarConfig(waveform="chirp", rf_mode="external_mixer", carrier_hz=5.5e9,
                          bandwidth_hz=400e6, if_center_hz=300e6)
        plan = rf_plan(cfg)
        self.assertEqual(plan["lo_hz"], 5.2e9)
        self.assertEqual(plan["if_start_hz"], 100e6)
        self.assertEqual(plan["if_stop_hz"], 500e6)

    def test_tone_frequency_and_codes(self):
        fs = DAC_FS_HZ
        cfg = RadarConfig(waveform="tone", carrier_hz=250e6, bandwidth_hz=0, amplitude=.3)
        sig, _ = generate(cfg, 8192)
        self.assertAlmostEqual(float(np.max(sig)), .3, places=10)
        peak_f = np.fft.rfftfreq(len(sig), 1/fs)[np.argmax(np.abs(np.fft.rfft(sig)))]
        self.assertAlmostEqual(peak_f, 250e6, places=3)
        self.assertEqual(to_dac_int16(sig).dtype, np.int16)

    def test_chirp_samples_and_silence(self):
        cfg = RadarConfig(waveform="chirp", carrier_hz=300e6, bandwidth_hz=400e6,
                          chirp_duration_s=1e-6, amplitude=.2)
        sig, _ = generate(cfg, 8192)
        self.assertEqual(len(sig), 8192)
        self.assertTrue(np.all(sig[4000:] == 0))
        self.assertTrue(np.max(np.abs(sig[:4000])) <= .20000001)

    def test_duration_too_long_rejected(self):
        cfg = RadarConfig(waveform="chirp", carrier_hz=300e6, bandwidth_hz=200e6,
                          chirp_duration_s=100e-6)
        with self.assertRaisesRegex(ValueError, "RAM"):
            generate(cfg, 16384)

    def test_if_nyquist_rejected(self):
        cfg = RadarConfig(waveform="chirp", carrier_hz=1.9e9, bandwidth_hz=400e6)
        with self.assertRaises(ValueError):
            rf_plan(cfg)

    def test_triangle(self):
        cfg = RadarConfig(waveform="triangle", carrier_hz=250e6, bandwidth_hz=200e6)
        signal, _ = generate(cfg, 16384)
        self.assertEqual(len(signal), 16384)
        self.assertTrue(np.isfinite(signal).all())

    def test_custom_complex_envelope(self):
        with tempfile.TemporaryDirectory() as d:
            np.save(Path(d)/"iq.npy", np.ones(100, dtype=np.complex64))
            cfg = RadarConfig(waveform="custom", carrier_hz=300e6, bandwidth_hz=0,
                              custom_file="iq.npy", custom_format="complex_envelope")
            signal, _ = generate(cfg, 1024, d)
            self.assertTrue(np.any(signal[:100] != 0))
            self.assertTrue(np.all(signal[100:] == 0))

    def test_digital_dechirp_synthetic_delay(self):
        fs = DAC_FS_HZ
        cfg = RadarConfig(waveform="chirp", carrier_hz=300e6, bandwidth_hz=400e6)
        tx, _ = generate(cfg, 65536)
        delay_samples = 200
        rx = np.roll(tx, delay_samples)
        beat = digital_dechirp(tx, rx)
        f = beat_peak_hz(beat, fs)
        expected = -400e6 / (len(tx) / fs) * delay_samples / fs
        self.assertLess(abs(f - expected), 7e4)
        estimated_m = range_from_beat(f, 400e6, len(tx) / fs, geometry="cable", vf=.66)
        self.assertAlmostEqual(estimated_m, .66 * 299792458 * delay_samples / fs, delta=.5)

    def test_circular_shift(self):
        rng = np.random.default_rng(44)
        tx = rng.normal(size=2048)
        rx = np.roll(tx, 37)
        lag, _ = circular_delay(tx, rx, 4e9)
        self.assertEqual(lag, 37)


if __name__ == "__main__":
    unittest.main()
