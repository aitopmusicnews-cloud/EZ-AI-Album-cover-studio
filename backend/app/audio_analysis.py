from __future__ import annotations

from pathlib import Path
from typing import Any

import librosa
import numpy as np

from .errors import AnalysisError


_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NOTES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]


class AudioAnalyzer:
    def __init__(self, max_seconds: int = 180):
        self.max_seconds = max_seconds

    def analyze(self, path: str | Path) -> dict[str, Any]:
        try:
            y, sr = librosa.load(path, sr=22050, mono=True, duration=self.max_seconds)
            if y.size < sr:
                raise AnalysisError("MP3 is too short to analyze reliably.")
            y = librosa.util.normalize(y)

            tempo_array = librosa.feature.tempo(y=y, sr=sr, aggregate=np.median)
            tempo = float(np.ravel(tempo_array)[0]) if np.size(tempo_array) else 0.0
            rms_frames = librosa.feature.rms(y=y)[0]
            rms = float(np.mean(rms_frames))
            loudness_db = float(librosa.amplitude_to_db(np.array([max(rms, 1e-8)]), ref=1.0)[0])
            energy = float(np.clip((loudness_db + 60.0) / 60.0, 0.0, 1.0))

            stft = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
            power = stft ** 2
            centroid = float(np.mean(librosa.feature.spectral_centroid(S=stft, sr=sr)))
            bandwidth = float(np.mean(librosa.feature.spectral_bandwidth(S=stft, sr=sr)))
            rolloff = float(np.mean(librosa.feature.spectral_rolloff(S=stft, sr=sr, roll_percent=0.85)))
            flatness = float(np.mean(librosa.feature.spectral_flatness(S=power)))
            zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))
            contrast = librosa.feature.spectral_contrast(S=stft, sr=sr)
            contrast_mean = [round(float(x), 4) for x in np.mean(contrast, axis=1)]

            frequencies = librosa.fft_frequencies(sr=sr, n_fft=2048)
            spectrum = np.mean(stft, axis=1)
            dominant_frequencies = self._dominant_frequencies(frequencies, spectrum)
            bass_mask = frequencies <= 250
            bass_ratio = float(np.sum(power[bass_mask]) / max(np.sum(power), 1e-9))

            chroma = librosa.feature.chroma_stft(S=power, sr=sr)
            chroma_mean = np.mean(chroma, axis=1)
            key, scale, key_confidence = self._detect_key(chroma_mean)

            genre, style_tags = self._infer_genre(
                tempo=tempo,
                energy=energy,
                centroid=centroid,
                flatness=flatness,
                zcr=zcr,
                bass_ratio=bass_ratio,
            )
            mood = self._infer_mood(
                tempo=tempo,
                energy=energy,
                centroid=centroid,
                scale=scale,
            )
            duration = float(librosa.get_duration(y=y, sr=sr))
            return {
                "tempo_bpm": round(tempo, 2),
                "energy": round(energy, 4),
                "loudness_dbfs": round(loudness_db, 2),
                "spectral": {
                    "centroid_hz": round(centroid, 2),
                    "bandwidth_hz": round(bandwidth, 2),
                    "rolloff_hz": round(rolloff, 2),
                    "flatness": round(flatness, 5),
                    "zero_crossing_rate": round(zcr, 5),
                    "contrast": contrast_mean,
                    "bass_ratio": round(bass_ratio, 4),
                },
                "key": key,
                "scale": scale,
                "key_confidence": round(key_confidence, 4),
                "dominant_frequencies_hz": dominant_frequencies,
                "inferred_genre": genre,
                "style_tags": style_tags,
                "mood": mood,
                "duration_seconds_analyzed": round(duration, 2),
                "sample_rate": sr,
            }
        except AnalysisError:
            raise
        except Exception as exc:
            raise AnalysisError(f"Audio analysis failed: {exc}") from exc

    @staticmethod
    def _detect_key(chroma: np.ndarray) -> tuple[str, str, float]:
        if not np.any(chroma):
            return "C", "major", 0.0
        chroma = chroma / max(float(np.sum(chroma)), 1e-9)
        scores: list[tuple[float, int, str]] = []
        for root in range(12):
            major = np.roll(_MAJOR_PROFILE, root)
            minor = np.roll(_MINOR_PROFILE, root)
            scores.append((float(np.corrcoef(chroma, major)[0, 1]), root, "major"))
            scores.append((float(np.corrcoef(chroma, minor)[0, 1]), root, "minor"))
        scores.sort(reverse=True, key=lambda item: item[0])
        best, root, scale = scores[0]
        second = scores[1][0]
        confidence = float(np.clip((best - second + 0.2) / 0.4, 0.0, 1.0))
        return _NOTES[root], scale, confidence

    @staticmethod
    def _dominant_frequencies(frequencies: np.ndarray, spectrum: np.ndarray) -> list[float]:
        candidates = np.argsort(spectrum)[::-1]
        selected: list[float] = []
        for index in candidates:
            frequency = float(frequencies[index])
            if frequency < 40 or frequency > 12000:
                continue
            if any(abs(frequency - existing) < max(30.0, existing * 0.08) for existing in selected):
                continue
            selected.append(frequency)
            if len(selected) == 5:
                break
        return [round(value, 2) for value in selected]

    @staticmethod
    def _infer_genre(
        *, tempo: float, energy: float, centroid: float, flatness: float, zcr: float, bass_ratio: float
    ) -> tuple[str, list[str]]:
        if tempo < 90 and energy < 0.45 and zcr < 0.08:
            return "ambient", ["spacious", "atmospheric", "slow-evolving"]
        if bass_ratio > 0.36 and 65 <= tempo <= 110:
            return "hip-hop / trap", ["bass-heavy", "rhythmic", "urban"]
        if tempo >= 112 and centroid > 2400 and flatness > 0.04:
            return "electronic / dance", ["synthetic", "kinetic", "club-oriented"]
        if energy > 0.62 and zcr > 0.08:
            return "rock / alternative", ["driving", "distorted", "anthemic"]
        if flatness < 0.035 and centroid < 2300 and energy < 0.58:
            return "acoustic / singer-songwriter", ["organic", "intimate", "warm"]
        if 90 <= tempo <= 138 and energy >= 0.42:
            return "pop", ["melodic", "polished", "immediate"]
        return "cinematic / experimental", ["textural", "dramatic", "unconventional"]

    @staticmethod
    def _infer_mood(*, tempo: float, energy: float, centroid: float, scale: str) -> dict[str, float | str]:
        tempo_component = float(np.clip((tempo - 90.0) / 80.0, -0.35, 0.35))
        brightness_component = float(np.clip((centroid - 2200.0) / 5000.0, -0.2, 0.2))
        tonal_component = 0.28 if scale == "major" else -0.28
        valence = float(np.clip(tonal_component + tempo_component + brightness_component, -1.0, 1.0))
        if valence >= 0.3 and energy >= 0.58:
            label = "uplifting and energetic"
        elif valence >= 0.25:
            label = "warm and hopeful"
        elif valence <= -0.3 and energy >= 0.58:
            label = "dark and intense"
        elif valence <= -0.3:
            label = "melancholic and restrained"
        elif energy >= 0.66:
            label = "urgent and restless"
        elif energy <= 0.34:
            label = "calm and atmospheric"
        else:
            label = "balanced and introspective"
        return {"label": label, "valence": round(valence, 4), "energy": round(energy, 4)}
