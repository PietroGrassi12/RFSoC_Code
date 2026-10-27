"""Hardware-independent real DAC waveform generation and external RF planning.

This software NEVER changes the RFSoC DAC/ADC sample rate, hardware NCO, or LO.
The current MTS overlay plays real int16 samples at a fixed nominal 4 GS/s.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np

DAC_FS_HZ = 4_000_000_000.0
DAC_MAX_CODE = 16383  # Nominal 14-bit signed code used by the MTS example.
WAVEFORM_TYPES = {"tone", "chirp", "triangle", "pulse", "custom"}
RF_MODES = {"direct", "external_mixer"}


@dataclass
class RadarConfig:
    waveform: str = "chirp"
    rf_mode: str = "direct"  # direct: RF center equals DAC center; external_mixer: RF = LO +/- IF
    carrier_hz: float = 300e6  # Actual desired RF center (at DAC for direct mode)
    bandwidth_hz: float = 200e6  # Chirp sweep bandwidth; must be 0 for a tone
    chirp_duration_s: float | None = None  # None = one full DAC RAM period
    amplitude: float = 0.15  # Fraction of DAC full scale
    phase_rad: float = 0.0
    if_center_hz: float = 300e6  # Used only when rf_mode == external_mixer
    sideband: str = "upper"  # upper: f_RF = f_LO + f_IF; lower: f_RF = f_LO - f_IF
    custom_file: str | None = None
    custom_format: str = "dac_samples"  # dac_samples, complex_envelope
    sample_rate_hz: float = DAC_FS_HZ  # Fixed by the supplied MTS bitstream

    @classmethod
    def read_json(cls, filename):
        values = json.loads(Path(filename).read_text(encoding="utf-8"))
        unknown = set(values) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Unknown configuration keys: {sorted(unknown)}")
        return cls(**values)


def rf_plan(config: RadarConfig):
    """Calculate IF and (if needed) theoretical external mixer LO.

    The LO is NEVER actually configured by this program. Real mixers create
    both sidebands; the RF frontend MUST filter the unwanted image.
    """
    if config.waveform not in WAVEFORM_TYPES:
        raise ValueError(f"waveform must be one of {sorted(WAVEFORM_TYPES)}")
    if config.rf_mode not in RF_MODES:
        raise ValueError(f"rf_mode must be one of {sorted(RF_MODES)}")
    if config.sideband not in ("upper", "lower"):
        raise ValueError("sideband must be 'upper' or 'lower'")
    fs = float(config.sample_rate_hz)
    if not np.isclose(fs, DAC_FS_HZ):
        raise ValueError("MTS overlay uses a fixed nominal 4 GS/s: do not change sample_rate_hz in software")
    amp = float(config.amplitude)
    if not np.isfinite(amp) or not (0 <= amp <= 1):
        raise ValueError("amplitude must be between 0 and 1")
    fc = float(config.carrier_hz)
    b = float(config.bandwidth_hz)
    if not np.isfinite(fc) or fc <= 0 or not np.isfinite(b) or b < 0:
        raise ValueError("carrier_hz must be positive and bandwidth_hz nonnegative")
    if config.waveform in ("tone", "pulse") and b != 0:
        raise ValueError("Set bandwidth_hz=0 for a tone or pulse")
    if config.waveform in ("chirp", "triangle") and b <= 0:
        raise ValueError("Chirps require bandwidth_hz > 0")
    if_center = fc if config.rf_mode == "direct" else float(config.if_center_hz)
    if config.rf_mode == "external_mixer":
        lo = fc - if_center if config.sideband == "upper" else fc + if_center
        if lo <= 0:
            raise ValueError("Calculated LO must be positive")
    else:
        lo = None
    low = if_center - b / 2
    high = if_center + b / 2
    # 'custom' in raw DAC format is user-provided and has independent spectral limits.
    if config.waveform != "custom" or config.custom_format == "complex_envelope":
        if low <= 0 or high >= fs / 2:
            raise ValueError(
                f"DAC IF spectrum [{low / 1e6:.2f}, {high / 1e6:.2f}] MHz must lie strictly within (0, Fs/2)"
            )
    if config.waveform == "custom" and config.custom_format not in ("dac_samples", "complex_envelope"):
        raise ValueError("custom_format must be dac_samples or complex_envelope")
    return {
        "rf_center_hz": fc,
        "if_center_hz": if_center,
        "if_start_hz": low,
        "if_stop_hz": high,
        "lo_hz": lo,
        "rf_mode": config.rf_mode,
        "sideband": config.sideband,
        "sample_rate_hz": fs,
    }


def generate(config: RadarConfig, ram_samples: int, base_directory="."):
    """Return one full DAC RAM period of normalized, real-valued samples.

    For chirp/triangle/pulse, if chirp_duration_s is shorter than the RAM
    period, the rest of the RAM period is zero-padded. Playback loops forever
    until the caller disables the DAC. For custom signals shorter than the
    buffer, the remaining positions are zero, not repeated.
    """
    plan = rf_plan(config)
    if ram_samples < 1:
        raise ValueError("ram_samples must be >= 1")
    fs = plan["sample_rate_hz"]
    if config.chirp_duration_s is None:
        n_active = ram_samples
    else:
        duration = float(config.chirp_duration_s)
        if not np.isfinite(duration) or duration <= 0:
            raise ValueError("chirp_duration_s must be positive, or null to use the full RAM period")
        n_active = int(round(duration * fs))
        if n_active < 1 or n_active > ram_samples:
            raise ValueError(
                f"Requested {n_active} samples ({duration * 1e6:.3f} us), "
                f"but this overlay's DAC RAM holds only {ram_samples} samples "
                f"({ram_samples / fs * 1e6:.3f} us). "
                "Use a shorter duration or rebuild the Vivado overlay."
            )

    result = np.zeros(ram_samples, dtype=np.float64)
    if config.waveform == "custom":
        if not config.custom_file:
            raise ValueError("custom_file must be set for waveform=custom")
        path = Path(base_directory) / config.custom_file
        if path.suffix.lower() == ".npy":
            samples = np.load(path, allow_pickle=False)
        elif path.suffix.lower() == ".csv":
            samples = np.loadtxt(path, delimiter=",")
        else:
            raise ValueError("custom_file must be a .npy or .csv file")
        samples = np.asarray(samples)
        if samples.ndim != 1 or samples.size == 0 or samples.size > n_active:
            raise ValueError("Custom waveform must be 1-D, nonempty and fit in the requested duration")
        if not np.all(np.isfinite(samples)) or np.max(np.abs(samples)) > 1.0 + 1e-12:
            raise ValueError("Custom waveform must be finite and normalized to magnitude <= 1")
        if config.custom_format == "dac_samples":
            if np.iscomplexobj(samples):
                raise ValueError("dac_samples must be real. Use complex_envelope for complex samples")
            result[: samples.size] = float(config.amplitude) * samples.real
        else:
            t = np.arange(samples.size, dtype=np.float64) / fs
            result[: samples.size] = float(config.amplitude) * np.real(
                samples * np.exp(1j * (2 * np.pi * plan["if_center_hz"] * t + config.phase_rad))
            )
        return result, plan

    n = np.arange(n_active, dtype=np.float64)
    t = n / fs
    freq = plan["if_center_hz"]
    b = float(config.bandwidth_hz)
    if config.waveform in ("tone", "pulse"):
        phase = 2 * np.pi * freq * t + float(config.phase_rad)
    elif config.waveform == "chirp":
        duration = n_active / fs
        start = freq - b / 2
        k = b / duration
        phase = 2 * np.pi * (start * t + 0.5 * k * t * t) + config.phase_rad
    elif config.waveform == "triangle":
        duration = n_active / fs
        half = duration / 2
        start = freq - b / 2
        k = b / half
        # Integrate frequency on both halves, ensuring phase continuity.
        phase_cycles = np.where(
            t < half,
            start * t + 0.5 * k * t * t,
            start * half + 0.5 * k * half * half
            + (start + b) * (t - half) - 0.5 * k * (t - half) ** 2,
        )
        phase = 2 * np.pi * phase_cycles + config.phase_rad
    else:
        raise AssertionError("Unexpected waveform")

    result[:n_active] = float(config.amplitude) * np.cos(phase)
    return result, plan


def to_dac_int16(samples):
    samples = np.asarray(samples)
    if samples.ndim != 1 or np.iscomplexobj(samples) or not np.all(np.isfinite(samples)):
        raise ValueError("DAC requires finite, real, 1-D samples")
    if np.max(np.abs(samples)) > 1 + 1e-12:
        raise ValueError("Samples must be in [-1, 1]")
    return np.rint(samples * DAC_MAX_CODE).astype(np.int16)


def describe(config, plan, ram_samples):
    fs = plan["sample_rate_hz"]
    lines = [
        f"Waveform: {config.waveform}; nominal Fs: {fs / 1e9:.3f} GS/s",
        f"Target RF carrier: {plan['rf_center_hz'] / 1e6:.3f} MHz",
        f"DAC IF center: {plan['if_center_hz'] / 1e6:.3f} MHz",
        f"DAC IF interval: {plan['if_start_hz'] / 1e6:.3f} - {plan['if_stop_hz'] / 1e6:.3f} MHz",
        f"RAM period: {ram_samples / fs * 1e6:.3f} us ({ram_samples} samples, repeats)",
        f"Amplitude: {config.amplitude:.3f} of DAC full scale",
    ]
    if plan["lo_hz"] is None:
        lines.append("RF plan: direct DAC output; verify actual analog filtering and supported RF band")
    else:
        lines.append(f"RF plan: EXTERNAL LO = {plan['lo_hz'] / 1e9:.6f} GHz, {config.sideband} sideband")
        lines.append("External LO / mixers / filters must be configured physically; Python does NOT set their frequency")
    if config.waveform in ("chirp", "triangle"):
        lines.append(f"Chirp bandwidth: {config.bandwidth_hz / 1e6:.3f} MHz")
        if config.chirp_duration_s is not None:
            lines.append(f"Programmed active duration: {config.chirp_duration_s * 1e6:.3f} us, then silence until RAM repeats")
    return "\n".join(lines)
