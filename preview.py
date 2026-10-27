"""Offline-only preview: python preview.py config_cband.json"""
from pathlib import Path
import sys
import numpy as np
import matplotlib.pyplot as plt
from waveforms import RadarConfig, generate, describe
from processing import spectrum_real

config_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config_loopback.json")
config = RadarConfig.read_json(config_file)
# Preview value only: real MTS memory length is read later from the board.
n = 16384
waveform, plan = generate(config, n, config_file.parent)
print(describe(config, plan, n))
fig, ax = plt.subplots(2, 1, figsize=(9, 5))
t = np.arange(n) / config.sample_rate_hz
ax[0].plot(t[:min(n, 4000)] * 1e6, waveform[:min(n, 4000)])
ax[0].set(xlabel="Time [us]", ylabel="DAC amplitude")
ax[0].grid(True)
f, d = spectrum_real(waveform, config.sample_rate_hz)
ax[1].plot(f / 1e6, d)
ax[1].set(xlim=(0, min(1000, config.sample_rate_hz / 2e6)), ylim=(-100, 5),
          xlabel="DAC frequency [MHz]", ylabel="Relative magnitude [dB]")
ax[1].grid(True)
fig.tight_layout()
plt.show()
