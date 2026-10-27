# RFSoC4x2 General Radar Waveform Controller

**Version 0.1 — configurable real-DAC TX + loopback capture using AMD/Xilinx RFSoC-MTS.** A software foundation for a later FPGA-based FMCW radar, **not** a turnkey 5.5 GHz RF transmitter or calibrated radar.

## What you can change without Vivado

Open `General_Radar_RFSoC4x2.ipynb`, or edit the JSON configurations. Available:

- Waveform: `tone`, `chirp` (up-sweep), `triangle` (up/down chirp), `pulse`, `custom` (`.npy` or `.csv`). Example: `example_complex_envelope.npy` with `custom_format=complex_envelope`.
- Desired RF carrier in `carrier_hz` (used to **plan** external mixing when `rf_mode=external_mixer`).
- Chirp bandwidth `bandwidth_hz` and active duration `chirp_duration_s` (`null` = entire DAC RAM period).
- Amplitude and phase, external IF center, sideband selection, custom waveform file.
- Python controls to load the existing overlay, write samples, **explicitly** turn TX on/off, and acquire ADC samples.

The notebook uses the package already installed on your board, rather than copying MTS source/bitstream. Both outputs DAC_A **and** DAC_B share the same waveform in the existing MTS design.

## Setup (GitHub workflow, recommended)

On your **PC**: unzip this folder, create an **empty** GitHub repository under your account (e.g. `rfsoc-general-radar`), and from inside this project directory execute:

```bash
git init -b main
git add .
git commit -m "Initial configurable RFSoC waveform controller"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

If Git asks for GitHub authentication, use the login flow / credentials required by your Git configuration (not your GitHub account password). Alternatively, upload the files with GitHub's web interface. Then on the **RFSoC4x2** Jupyter terminal:

```bash
cd /home/xilinx/jupyter_notebooks
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
```

When you update it on your PC, use `git pull` in this directory on the board. **Never push the AMD RFSoC-MTS installation or vendor bitstreams into this repository.**

If you prefer a one-time upload, copy the ZIP through JupyterLab's Upload option, then:

```bash
cd /home/xilinx/jupyter_notebooks
unzip RFSoC4x2_GeneralRadar.zip
```

Run the notebook from the new folder, **not** from inside the original `RFSoC-MTS/` source tree. Shut down all other Jupyter kernels before loading `mts.bit` (the MTS driver modifies PL DDR4 device tree/ZOCL).

## Choose loopback first

`config_loopback.json`:

- `rf_mode=direct`, `carrier_hz=300e6`, `bandwidth_hz=200e6` -> DAC analog IF 200–400 MHz.
- Wire one path (reference RFSoC4x2 notebook: DAC_A to ADC_B) using rated DC blocks and enough RF attenuation after checking the board documentation and output/input levels.
- **Both DAC SMA outputs may become active**; leave unconnected paths terminated or otherwise safely handled.
- In notebook, set `ENABLE_TRANSMISSION = True` explicitly to play; also set `CAPTURE_RX = True` when ready.
- ADC capture returns **three internal streams**, not a guaranteed mapping to the SMA labels. Identify your cable's capture stream with an injected tone using the original MTS notebook.

## Then use an external C-band RF front end

`config_cband.json` requests:

- `carrier_hz = 5.5e9`, `bandwidth_hz = 400e6`, `if_center_hz = 300e6`, `rf_mode = external_mixer`, `sideband = upper`.
- **Actual DAC output:** a 100–500 MHz analog IF chirp.
- **External LO:** 5.2 GHz, yielding the upper sideband at 5.3–5.7 GHz after external upconversion and RF filtering.
- For reception, use an RF mixer/downconverter referenced coherently to TX so ADC captures a supported IF. No Python command in this package programs an external LO, controls external PA/LNA, or guarantees compliance with RF emissions rules.

The external mixer generates an **unwanted lower sideband** too: you must filter it. The 400 MHz analog IF and C-band RF bands must both be within the real hardware's filters and power budget; samples passing a software check does **not** certify RF compatibility.

## Hardware limits and time/range measurements

- **4 GS/s is an assumed fixed design sample rate** per MTS documentation. Changing the JSON sample rate is rejected; require a different bitstream to reconfigure RFDC.
- Actual DAC RAM depth is read at runtime from `len(overlay.dac_player)`. The waveform **loops** at that memory period. Requesting longer chirps than available memory produces an explicit error, not an incomplete chirp.
- Real-valued DAC samples only. `custom_format=complex_envelope` maps user complex-envelope `.npy` samples to a **real IF carrier** using `Re{x(t) exp(j 2pi f_IF t)}`. It does not expose two independent I/Q physical DACs.
- Physical RX capture throughput, order of samples, sample alignment/ADC decimation and RX SMA-to-stream mapping must be verified experimentally before using a chirp's beat for absolute range.
- MTS internal capture **restarts DAC playback as part of triggering**. It is not a calibrated radar time-zero, and simultaneous continuous TX and synchronized RX require future hardware work.
- Cable loopback delay is **one-way** `L/(VF*c)`, while monostatic radar round trip is `2R/c`. The measured total also includes fixed TX/RX chain delays. Use different coax lengths to remove fixed offsets. The optional notebook dechirp demonstration is deliberately disabled until sample alignment and stream ordering have been checked.
- For a 400 MHz chirp in a 16 us RAM period, `K = 25e12 Hz/s`. A 1 m cable (VF=0.66) gives a nominal IF beat around 126 kHz, but an MTS record may require explicit timing alignment, and short records limit FFT resolution.

## Test without board

From your PC or board:

```bash
python -m unittest discover -s tests -v
python preview.py config_loopback.json
python preview.py config_cband.json
```

`preview.py` uses a **fictitious 16,384-sample RAM just to preview**. Actual hardware memory depth is measured by the notebook.

## Files

- `waveforms.py`: waveform types, parameter and IF/RF frequency validation, DAC sample conversion.
- `mts_hardware.py`: PYNQ MTS overlay, RAM playback and raw ADC captures.
- `processing.py`: raw ADC spectrum, experimental circular delay correlation, analytic-signal digital dechirp and beat/range helpers (**requires RX/TX alignment and calibration**).
- `General_Radar_RFSoC4x2.ipynb`: primary user interface.
- `config_loopback.json`, `config_cband.json`: editable use cases.
- `vivado/ARCHITECTURE.md`: next-step FPGA design contract (no fabricated bitstream).

Hardware source: https://github.com/Xilinx/RFSoC-MTS (AMD/Xilinx, MIT License). This code has been syntax-tested and its waveform routines unit-tested **offline**; it has **not** been run on your physical RFSoC4x2 yet.
