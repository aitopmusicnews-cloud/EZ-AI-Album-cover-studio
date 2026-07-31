from __future__ import annotations

import numpy as np
import soundfile as sf

from app.audio_analysis import AudioAnalyzer


def _write_tone(path, amplitude: float, seconds: float = 2.0, sr: int = 22050) -> None:
    t = np.arange(int(seconds * sr), dtype=np.float32) / sr
    # Pulse-modulated tone gives the beat/onset code some movement while keeping
    # the amplitude comparison deterministic.
    carrier = np.sin(2 * np.pi * 220 * t)
    pulse = 0.55 + 0.45 * (np.sin(2 * np.pi * 2 * t) > 0).astype(np.float32)
    sf.write(path, (amplitude * carrier * pulse).astype(np.float32), sr)


def test_loudness_uses_original_amplitude_not_normalized_waveform(tmp_path):
    quiet = tmp_path / "quiet.wav"
    loud = tmp_path / "loud.wav"
    _write_tone(quiet, 0.08)
    _write_tone(loud, 0.8)

    analyzer = AudioAnalyzer(max_seconds=10)
    quiet_signal = analyzer.analyze(quiet)
    loud_signal = analyzer.analyze(loud)

    assert loud_signal["loudness_dbfs"] > quiet_signal["loudness_dbfs"] + 12
    assert loud_signal["energy"] > quiet_signal["energy"]
    assert 55 <= loud_signal["tempo_bpm"] <= 210
    assert "tempo_confidence" in loud_signal
    assert "genre_confidence" in loud_signal
