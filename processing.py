"""Offline analysis helpers; not a calibrated FMCW ranging implementation."""
import numpy as np


def spectrum_real(samples, sample_rate_hz):
    """Frequency and normalized, windowed spectrum of a real ADC stream."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim != 1 or x.size < 4:
        raise ValueError("Expected at least 4 real ADC samples")
    x = x - x.mean()
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size)))
    db = 20 * np.log10(np.maximum(spec, 1e-14) / max(np.max(spec), 1e-14))
    f = np.fft.rfftfreq(len(x), d=1 / float(sample_rate_hz))
    return f, db


def circular_delay(tx, rx, sample_rate_hz):
    """Diagnostic periodic correlation, NOT calibrated absolute time-of-flight.

    Requires matching sample rates, a common time ordering, and equal length
    representing one whole DAC RAM period. Delay is ambiguous modulo period.
    """
    tx = np.asarray(tx, dtype=np.float64)
    rx = np.asarray(rx, dtype=np.float64)
    if tx.ndim != 1 or tx.size != rx.size or tx.size < 2:
        raise ValueError("TX and RX must have the same nonzero 1-D length")
    tx = tx - tx.mean()
    rx = rx - rx.mean()
    if np.max(np.abs(tx)) == 0 or np.max(np.abs(rx)) == 0:
        raise ValueError("Constant waveform: correlation cannot estimate delay")
    corr = np.fft.ifft(np.fft.fft(rx) * np.conj(np.fft.fft(tx)))
    lag = int(np.argmax(np.abs(corr)))
    if lag > len(tx) // 2:
        lag -= len(tx)
    return lag, lag / sample_rate_hz


def analytic_signal(samples):
    """Hilbert/analytic representation of a *real* IF waveform (NumPy only).

    Useful for offline digital dechirping when TX/RX IF bands are strictly
    within (0, Fs/2). Edge artifacts are expected near record boundaries.
    """
    samples = np.asarray(samples, dtype=np.float64)
    if samples.ndim != 1 or samples.size < 4:
        raise ValueError("Expected at least 4 real IF samples")
    n = samples.size
    weights = np.zeros(n)
    weights[0] = 1
    if n % 2 == 0:
        weights[n//2] = 1
        weights[1:n//2] = 2
    else:
        weights[1:(n+1)//2] = 2
    return np.fft.ifft(np.fft.fft(samples) * weights)


def digital_dechirp(tx_if_real, rx_if_real):
    """Beat = analytic(RX) * conj(analytic(TX)).

    REQUIRES matching, phase-coherent sample rates, time-aligned TX reference,
    and same IF (external RF mixers must also be coherent). No self-calibration.
    """
    tx = np.asarray(tx_if_real, dtype=np.float64)
    rx = np.asarray(rx_if_real, dtype=np.float64)
    if tx.shape != rx.shape or tx.ndim != 1:
        raise ValueError("Time-aligned TX and RX records must have identical 1-D shapes")
    return analytic_signal(rx) * np.conj(analytic_signal(tx))


def beat_peak_hz(beat, fs, *, min_abs_hz=0, nfft_factor=8, edge_fraction=0.05):
    """Estimate signed dominant beat frequency (proof-of-concept only)."""
    b = np.asarray(beat, dtype=np.complex128)
    n = b.size
    trim = int(edge_fraction * n)
    if 2 * trim >= n - 4:
        raise ValueError("Not enough samples after discarding edge transients")
    b = b[trim:n-trim] if trim else b
    nfft = 2 ** int(np.ceil(np.log2(max(32, int(nfft_factor * b.size)))))
    freq = np.fft.fftfreq(nfft, d=1 / fs)
    spectrum = np.abs(np.fft.fft(b * np.hanning(b.size), n=nfft))
    spectrum[np.abs(freq) < min_abs_hz] = 0
    return float(freq[int(np.argmax(spectrum))])


def delay_from_beat(beat_hz, bandwidth_hz, sweep_duration_s):
    """Return measured delay magnitude; upchirp: beat ~ -K*tau in RX*conj(TX)."""
    if bandwidth_hz <= 0 or sweep_duration_s <= 0:
        raise ValueError("Valid positive bandwidth and sweep duration required")
    slope = bandwidth_hz / sweep_duration_s
    return abs(beat_hz) / slope


def range_from_beat(beat_hz, bandwidth_hz, sweep_duration_s, *, geometry="radar", vf=1.0):
    """One-way cable length or round-trip monostatic radar range.

    Returns distance with no correction of hardware/analog delays.
    """
    c = 299_792_458.0
    tau = delay_from_beat(beat_hz, bandwidth_hz, sweep_duration_s)
    if geometry == "radar":
        return c * tau / 2
    if geometry == "cable":
        if not 0 < vf <= 1:
            raise ValueError("Cable velocity factor must be in (0, 1]")
        return vf * c * tau
    raise ValueError("geometry must be 'radar' or 'cable'")
