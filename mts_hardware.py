"""RFSoC4x2 bridge using AMD/Xilinx RFSoC-MTS, with deliberate TX enable.

Only this module imports pynq/rfsoc_mts. All waveform generation is standalone.
"""
from importlib.metadata import distribution
from pathlib import Path
import os
import numpy as np
from waveforms import to_dac_int16, DAC_FS_HZ


class MTSHardware:
    def __init__(self):
        self.overlay = None
        self._loaded = False
        self._tx_programmed = False
        self._tx_running = False

    @staticmethod
    def overlay_paths():
        # Resolve pip's installed package location, even if a git checkout
        # happens to shadow the imported Python module.
        base = Path(distribution("rfsoc-mts").locate_file("rfsoc_mts"))
        paths = {name: base / name for name in ("mts.bit", "mts.hwh", "ddr4.dtbo")}
        missing = [str(p) for p in paths.values() if not p.is_file()]
        if missing:
            raise FileNotFoundError("Required installed MTS files missing: " + ", ".join(missing))
        return paths

    def load(self):
        if os.environ.get("BOARD", "") != "RFSoC4x2":
            raise RuntimeError("Run this only on the RFSoC4x2 with its PYNQ image (BOARD=RFSoC4x2)")
        from rfsoc_mts import mtsOverlay
        paths = self.overlay_paths()
        self.overlay = mtsOverlay(str(paths["mts.bit"]))
        self.overlay.dac_enable.off()
        self._loaded = True
        self._tx_programmed = False
        self._tx_running = False
        print("Loaded:", paths["mts.bit"])
        print("DAC RAM length:", self.ram_samples, "samples")
        print("Nominal DAC sample rate:", DAC_FS_HZ / 1e9, "GS/s")
        print("CAUTION: Both DAC_A and DAC_B carry the SAME waveform in MTS!")
        return self.overlay

    @property
    def ram_samples(self):
        if not self._loaded:
            raise RuntimeError("Call hardware.load() first")
        return len(self.overlay.dac_player)

    def write(self, samples):
        if not self._loaded:
            raise RuntimeError("Call hardware.load() first")
        data = to_dac_int16(samples)
        if len(data) != self.ram_samples:
            raise ValueError(f"Expected {self.ram_samples} DAC samples, got {len(data)}")
        self.stop()
        self.overlay.dac_player[:] = data
        self._tx_programmed = True
        print("Wrote", len(data), "DAC samples (TX still OFF).")
        return data

    def start(self, *, confirm_hardware_ready=False):
        if not self._loaded or not self._tx_programmed:
            raise RuntimeError("Load overlay and write the DAC waveform first")
        if not confirm_hardware_ready:
            raise RuntimeError("For output, call start(confirm_hardware_ready=True) after verifying levels/cables")
        self.overlay.dac_enable.on()
        self._tx_running = True
        print("DAC playback ON: BOTH DAC_A and DAC_B; the waveform loops continuously")

    def stop(self):
        if self._loaded:
            self.overlay.dac_enable.off()
            self._tx_running = False

    def capture_internal(self, n_samples=8192, *, confirm_hardware_ready=False):
        if not self._loaded or not self._tx_programmed:
            raise RuntimeError("Load the overlay and DAC waveform before capturing")
        if not confirm_hardware_ready:
            raise RuntimeError("Capture retriggers DAC playback. Confirm safe RF wiring first")
        max_len = min(len(self.overlay.adc_capture_chA),
                      len(self.overlay.adc_capture_chB),
                      len(self.overlay.adc_capture_chC))
        if not isinstance(n_samples, int) or not 1 <= n_samples <= max_len:
            raise ValueError(f"Capture length must lie within 1..{max_len}")
        capture = np.zeros((3, n_samples), dtype=np.int16)
        self.overlay.internal_capture(capture)
        self._tx_running = True  # internal_capture calls trigger_capture, enabling DAC playback
        return capture
