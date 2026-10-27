# Future custom Vivado FMCW overlay (design specification, not built yet)

The bundled Python project **actually operates** the existing AMD/Xilinx RFSoC-MTS overlay. This document is a design plan for the next hardware version; no `.bit` file is supplied here.

## Why upgrade the overlay?

1. The MTS RAM is finite and broadcasts the same waveform to both DAC outputs.
2. The MTS capture is a demonstration, not a continuously streaming synchronized radar receiver.
3. Its RFDC configuration and sample clock are fixed at build time; a Python variable cannot freely change an RFDC clock or make RF hardware work at 5.5 GHz.
4. Stable chirp start / ADC capture timestamps, continuous chirps, decimation, and channel-selective processing require new PL infrastructure.

## Proposed hardware blocks

```text
Python (PS)
  | AXI-Lite parameter registers / status
  v
Sequencer + trigger -----------------------------------+
  |                                                      |
  v                                                      v
NCO phase increment ramp -> phase accumulator -> DDS   ADC RFDC
  |                         (multiple parallel lanes)     |
  v                                                      v
DAC RFDC -> RF front end -> target -> RX front end -> Digital downconversion
                                                         |
                                                         v
                                             optional digital dechirp
                                                         |
                                                         v
                                              LPF / decimation
                                                         |
                                                         v
                                                    AXI DMA
                                                         |
                                                         v
                                                      DDR/PS
```

For a zero-to-B/centered LFM in complex digital baseband:

- `phase[n+1] = phase[n] + tuning_word[n]`
- `tuning_word[n+1] = tuning_word[n] + slope_word`
- `s[n] = cos(phase[n]) + j sin(phase[n])`
- `K = B/T`; tuning word `round((f_instantaneous/Fs) * 2^N)`, slope word `round((K/Fs^2) * 2^N)` with enough fractional bits and parallel lane correction.

**Important:** 4 GS/s DAC does not mean a 4 GHz PL logic clock. RFDC generally accepts several samples per parallel AXI-stream clock, so a genuine implementation must compute multiple consecutive samples per PL cycle (or use appropriate Xilinx IP), and handle samples-per-clock, clock-domain crossings, reset and FIFO sizing.

## Register/interface contract (proposed)

| Register | Purpose |
|---|---|
| `WAVEFORM_MODE` | tone, chirp, triangle, samples DMA |
| `F_START_WORD` | digital instantaneous start frequency |
| `F_STEP_WORD` | increment per DAC sample |
| `SAMPLES_PER_CHIRP` | chirp length |
| `CHIRPS_PER_FRAME` | number of repetitions |
| `TX_GAIN` | digital amplitude |
| `TX_ENABLE` | hardware TX enable |
| `RX_TRIGGER_OFFSET` | programmable capture start offset |
| `RX_CAPTURE_SAMPLES` | acquisition length |
| `STATUS` | armed/active/overrun/underrun |

An external LO, TX PA, LNA, duplexer/isolation, bandpass filters, clock reference, and antenna are outside the FPGA. For coherent FMCW, TX and RX mixers should share a coherent LO/reference and the RX IF must fit inside the analog ADC bandwidth. Physical RF emissions require legal/regulatory and laboratory checks.

## Planned incremental changes

1. Keep RFSoC-MTS bitstream; prove 1 TX/1 RX waveforms and raw capture at IF.
2. Add deterministic chirp/capture markers; characterize TX/RX fixed latency with two cable lengths.
3. Replace DAC BRAM replay with a programmable, **parallel** NCO/phase generator.
4. Add synchronized, long-form ADC DMA capture and calibration metadata.
5. Add complex DDC, digital dechirp and optional filtering/decimation in PL.
6. Add separate TX channels only when required.

Sources: https://github.com/Xilinx/RFSoC-MTS ; RF Data Converter product documentation PG269.
