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
    """Lightweight music feature analyzer.

    Technical values are deterministic measurements. Genre and mood are heuristic
    estimates and therefore include confidence values rather than pretending to be
    definitive labels.
    """

    def __init__(self, max_seconds: int = 180):
        self.max_seconds = max_seconds

    def analyze(self, path: str | Path) -> dict[str, Any]:
        try:
            raw, sr = librosa.load(path, sr=22050, mono=True, duration=self.max_seconds)
            if raw.size < sr:
                raise AnalysisError("MP3 is too short to analyze reliably.")

            # Remove long digital-silence edges, but retain the original amplitude.
            # The previous implementation normalized before measuring RMS, which
            # made quiet and loud masters look misleadingly similar.
            trimmed, _ = librosa.effects.trim(raw, top_db=45)
            if trimmed.size >= sr:
                raw = trimmed

            peak = float(np.max(np.abs(raw)))
            analysis_y = librosa.util.normalize(raw) if peak > 1e-9 else raw.copy()

            rms_frames = librosa.feature.rms(y=raw, frame_length=2048, hop_length=512)[0]
            nonzero_rms = rms_frames[rms_frames > 1e-8]
            if nonzero_rms.size:
                rms_mean = float(np.mean(nonzero_rms))
                rms_p90 = float(np.percentile(nonzero_rms, 90))
                rms_p10 = float(np.percentile(nonzero_rms, 10))
            else:
                rms_mean = rms_p90 = rms_p10 = 1e-8

            loudness_dbfs = float(20.0 * np.log10(max(rms_p90, 1e-8)))
            quiet_dbfs = float(20.0 * np.log10(max(rms_p10, 1e-8)))
            dynamic_range_db = max(0.0, loudness_dbfs - quiet_dbfs)

            onset_envelope = librosa.onset.onset_strength(y=analysis_y, sr=sr)
            beat_tempo, beat_frames = librosa.beat.beat_track(
                y=analysis_y,
                sr=sr,
                onset_envelope=onset_envelope,
                units="frames",
            )
            tempo = float(np.ravel(np.asarray(beat_tempo))[0]) if np.size(beat_tempo) else 0.0
            if not np.isfinite(tempo) or tempo <= 0:
                tempo_array = librosa.feature.tempo(
                    onset_envelope=onset_envelope,
                    sr=sr,
                    aggregate=np.median,
                )
                tempo = float(np.ravel(tempo_array)[0]) if np.size(tempo_array) else 0.0
            tempo = self._normalize_tempo(tempo)

            duration = float(librosa.get_duration(y=raw, sr=sr))
            beat_count = int(np.size(beat_frames))
            beat_density = beat_count / max(duration, 1.0)
            onset_strength = float(np.mean(onset_envelope)) if onset_envelope.size else 0.0

            stft = np.abs(librosa.stft(analysis_y, n_fft=2048, hop_length=512))
            power = stft ** 2
            centroid = float(np.mean(librosa.feature.spectral_centroid(S=stft, sr=sr)))
            bandwidth = float(np.mean(librosa.feature.spectral_bandwidth(S=stft, sr=sr)))
            rolloff = float(np.mean(librosa.feature.spectral_rolloff(S=stft, sr=sr, roll_percent=0.85)))
            flatness = float(np.mean(librosa.feature.spectral_flatness(S=power)))
            zcr = float(np.mean(librosa.feature.zero_crossing_rate(analysis_y)))
            contrast = librosa.feature.spectral_contrast(S=stft, sr=sr)
            contrast_mean = [round(float(x), 4) for x in np.mean(contrast, axis=1)]

            frequencies = librosa.fft_frequencies(sr=sr, n_fft=2048)
            spectrum = np.median(stft, axis=1)
            dominant_frequencies = self._dominant_frequencies(frequencies, spectrum)
            bass_mask = frequencies <= 250
            low_mid_mask = (frequencies > 250) & (frequencies <= 1000)
            total_power = max(float(np.sum(power)), 1e-9)
            bass_ratio = float(np.sum(power[bass_mask]) / total_power)
            low_mid_ratio = float(np.sum(power[low_mid_mask]) / total_power)

            harmonic, percussive = librosa.effects.hpss(analysis_y)
            harmonic_rms = float(np.mean(librosa.feature.rms(y=harmonic)[0]))
            percussive_rms = float(np.mean(librosa.feature.rms(y=percussive)[0]))
            harmonic_ratio = harmonic_rms / max(harmonic_rms + percussive_rms, 1e-9)

            # Chroma CENS is more resistant to dynamics/timbre than direct STFT
            # chroma and produces better key estimates on mastered mixes.
            chroma = librosa.feature.chroma_cens(y=harmonic, sr=sr)
            chroma_mean = np.median(chroma, axis=1)
            key, scale, key_confidence = self._detect_key(chroma_mean)

            energy = self._energy_score(
                loudness_dbfs=loudness_dbfs,
                onset_strength=onset_strength,
                beat_density=beat_density,
                dynamic_range_db=dynamic_range_db,
            )
            genre, style_tags, genre_confidence, genre_candidates = self._infer_genre(
                tempo=tempo,
                energy=energy,
                centroid=centroid,
                flatness=flatness,
                zcr=zcr,
                bass_ratio=bass_ratio,
                harmonic_ratio=harmonic_ratio,
                beat_density=beat_density,
            )
            mood = self._infer_mood(
                tempo=tempo,
                energy=energy,
                centroid=centroid,
                scale=scale,
                key_confidence=key_confidence,
                harmonic_ratio=harmonic_ratio,
            )

            return {
                "tempo_bpm": round(tempo, 2),
                "tempo_confidence": round(self._tempo_confidence(onset_envelope, beat_frames), 4),
                "energy": round(energy, 4),
                "loudness_dbfs": round(loudness_dbfs, 2),
                "rms_mean": round(rms_mean, 6),
                "dynamic_range_db": round(dynamic_range_db, 2),
                "spectral": {
                    "centroid_hz": round(centroid, 2),
                    "bandwidth_hz": round(bandwidth, 2),
                    "rolloff_hz": round(rolloff, 2),
                    "flatness": round(flatness, 5),
                    "zero_crossing_rate": round(zcr, 5),
                    "contrast": contrast_mean,
                    "bass_ratio": round(bass_ratio, 4),
                    "low_mid_ratio": round(low_mid_ratio, 4),
                    "harmonic_ratio": round(harmonic_ratio, 4),
                    "onset_strength": round(onset_strength, 4),
                    "beat_density_hz": round(beat_density, 4),
                },
                "key": key,
                "scale": scale,
                "key_confidence": round(key_confidence, 4),
                "dominant_frequencies_hz": dominant_frequencies,
                "inferred_genre": genre,
                "genre_confidence": round(genre_confidence, 4),
                "genre_candidates": genre_candidates,
                "style_tags": style_tags,
                "mood": mood,
                "duration_seconds_analyzed": round(duration, 2),
                "sample_rate": sr,
                "analysis_note": (
                    "BPM, loudness and spectral values are measured from the audio. "
                    "Genre and mood are heuristic estimates and include confidence scores."
                ),
            }
        except AnalysisError:
            raise
        except Exception as exc:
            raise AnalysisError(f"Audio analysis failed: {exc}") from exc

    @staticmethod
    def _detect_key(chroma: np.ndarray) -> tuple[str, str, float]:
        if not np.any(chroma) or np.isnan(chroma).any():
            return "C", "major", 0.0
        chroma = chroma / max(float(np.linalg.norm(chroma)), 1e-9)
        scores: list[tuple[float, int, str]] = []
        for root in range(12):
            major = np.roll(_MAJOR_PROFILE, root)
            minor = np.roll(_MINOR_PROFILE, root)
            major = major / np.linalg.norm(major)
            minor = minor / np.linalg.norm(minor)
            scores.append((float(np.dot(chroma, major)), root, "major"))
            scores.append((float(np.dot(chroma, minor)), root, "minor"))
        scores.sort(reverse=True, key=lambda item: item[0])
        best, root, scale = scores[0]
        second = scores[1][0]
        margin = max(0.0, best - second)
        confidence = float(np.clip(margin / 0.12, 0.0, 1.0))
        return _NOTES[root], scale, confidence

    @staticmethod
    def _dominant_frequencies(frequencies: np.ndarray, spectrum: np.ndarray) -> list[float]:
        if not np.any(spectrum):
            return []
        # Local spectral peaks are more meaningful than simply taking adjacent FFT bins.
        interior = spectrum[1:-1]
        peak_indices = np.where((interior > spectrum[:-2]) & (interior >= spectrum[2:]))[0] + 1
        if peak_indices.size == 0:
            peak_indices = np.argsort(spectrum)[::-1]
        else:
            peak_indices = peak_indices[np.argsort(spectrum[peak_indices])[::-1]]
        selected: list[float] = []
        for index in peak_indices:
            frequency = float(frequencies[index])
            if frequency < 40 or frequency > 12000:
                continue
            if any(abs(frequency - existing) < max(35.0, existing * 0.06) for existing in selected):
                continue
            selected.append(frequency)
            if len(selected) == 5:
                break
        return [round(value, 2) for value in selected]

    @staticmethod
    def _normalize_tempo(tempo: float) -> float:
        if not np.isfinite(tempo) or tempo <= 0:
            return 0.0
        # Beat trackers often return a musically equivalent half/double tempo.
        # Keep the value in a useful broad listening range without forcing genres.
        while tempo < 55:
            tempo *= 2.0
        while tempo > 210:
            tempo /= 2.0
        return float(tempo)

    @staticmethod
    def _tempo_confidence(onset_envelope: np.ndarray, beat_frames: np.ndarray) -> float:
        if onset_envelope.size == 0 or np.size(beat_frames) < 3:
            return 0.0
        frames = np.asarray(beat_frames, dtype=int).ravel()
        frames = frames[(frames >= 0) & (frames < onset_envelope.size)]
        if frames.size < 3:
            return 0.0
        beat_strength = float(np.mean(onset_envelope[frames]))
        background = float(np.mean(onset_envelope)) + 1e-9
        regularity = 1.0
        intervals = np.diff(frames)
        if intervals.size > 1 and float(np.mean(intervals)) > 0:
            cv = float(np.std(intervals) / np.mean(intervals))
            regularity = float(np.clip(1.0 - cv, 0.0, 1.0))
        return float(np.clip((beat_strength / background - 1.0) / 2.5, 0.0, 1.0) * 0.55 + regularity * 0.45)

    @staticmethod
    def _energy_score(
        *, loudness_dbfs: float, onset_strength: float, beat_density: float, dynamic_range_db: float
    ) -> float:
        loudness_component = float(np.clip((loudness_dbfs + 32.0) / 24.0, 0.0, 1.0))
        onset_component = float(np.clip(onset_strength / 2.5, 0.0, 1.0))
        rhythm_component = float(np.clip(beat_density / 2.4, 0.0, 1.0))
        compression_component = float(np.clip((18.0 - dynamic_range_db) / 18.0, 0.0, 1.0))
        return float(np.clip(
            0.48 * loudness_component
            + 0.24 * onset_component
            + 0.18 * rhythm_component
            + 0.10 * compression_component,
            0.0,
            1.0,
        ))

    @staticmethod
    def _infer_genre(
        *,
        tempo: float,
        energy: float,
        centroid: float,
        flatness: float,
        zcr: float,
        bass_ratio: float,
        harmonic_ratio: float,
        beat_density: float,
    ) -> tuple[str, list[str], float, list[dict[str, float | str]]]:
        def near(value: float, center: float, width: float) -> float:
            return float(np.clip(1.0 - abs(value - center) / width, 0.0, 1.0))

        half_tempo = tempo / 2.0 if tempo >= 120 else tempo
        scores = {
            "ambient": 0.34 * (1.0 - energy) + 0.28 * (1.0 - min(beat_density / 1.5, 1.0)) + 0.20 * (1.0 - min(centroid / 4000, 1.0)) + 0.18 * harmonic_ratio,
            "hip-hop / trap": 0.34 * min(bass_ratio / 0.34, 1.0) + 0.24 * near(half_tempo, 78, 34) + 0.18 * energy + 0.14 * (1.0 - min(centroid / 5000, 1.0)) + 0.10 * min(beat_density / 2.2, 1.0),
            "R&B / soul": 0.28 * near(tempo, 92, 38) + 0.25 * harmonic_ratio + 0.18 * min(bass_ratio / 0.30, 1.0) + 0.17 * (1.0 - abs(energy - 0.48)) + 0.12 * (1.0 - min(zcr / 0.12, 1.0)),
            "electronic / dance": 0.30 * near(tempo, 126, 25) + 0.24 * energy + 0.18 * min(centroid / 4200, 1.0) + 0.14 * min(flatness / 0.10, 1.0) + 0.14 * min(beat_density / 2.3, 1.0),
            "rock / alternative": 0.28 * energy + 0.22 * min(zcr / 0.12, 1.0) + 0.20 * min(centroid / 3600, 1.0) + 0.16 * near(tempo, 128, 55) + 0.14 * (1.0 - harmonic_ratio),
            "acoustic / singer-songwriter": 0.30 * harmonic_ratio + 0.24 * (1.0 - min(flatness / 0.08, 1.0)) + 0.20 * (1.0 - energy) + 0.14 * (1.0 - min(centroid / 3500, 1.0)) + 0.12 * near(tempo, 92, 50),
            "pop": 0.27 * near(tempo, 116, 36) + 0.23 * (1.0 - abs(energy - 0.62)) + 0.18 * harmonic_ratio + 0.17 * min(beat_density / 2.2, 1.0) + 0.15 * (1.0 - min(flatness / 0.14, 1.0)),
            "cinematic / experimental": 0.24 * (1.0 - near(tempo, 115, 50)) + 0.22 * abs(harmonic_ratio - 0.5) + 0.18 * min(flatness / 0.12, 1.0) + 0.18 * (1.0 - min(beat_density / 1.8, 1.0)) + 0.18,
        }
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_name, top_score = ranked[0]
        second_score = ranked[1][1]
        confidence = float(np.clip(0.35 + (top_score - second_score) * 1.8, 0.35, 0.88))

        tags = {
            "ambient": ["spacious", "atmospheric", "slow-evolving"],
            "hip-hop / trap": ["bass-forward", "rhythmic", "modern urban"],
            "R&B / soul": ["warm", "groove-led", "smooth"],
            "electronic / dance": ["synthetic", "kinetic", "club-oriented"],
            "rock / alternative": ["driving", "textured", "anthemic"],
            "acoustic / singer-songwriter": ["organic", "intimate", "warm"],
            "pop": ["melodic", "polished", "immediate"],
            "cinematic / experimental": ["textural", "dramatic", "unconventional"],
        }[top_name]
        candidates = [
            {"label": name, "score": round(float(score), 4)} for name, score in ranked[:3]
        ]
        return top_name, tags, confidence, candidates

    @staticmethod
    def _infer_mood(
        *, tempo: float, energy: float, centroid: float, scale: str, key_confidence: float, harmonic_ratio: float
    ) -> dict[str, float | str]:
        mode_weight = 0.28 * float(np.clip(key_confidence, 0.0, 1.0))
        tonal_component = mode_weight if scale == "major" else -mode_weight
        tempo_component = float(np.clip((tempo - 105.0) / 150.0, -0.18, 0.20))
        brightness_component = float(np.clip((centroid - 2300.0) / 9000.0, -0.12, 0.12))
        warmth_component = float(np.clip((harmonic_ratio - 0.5) * 0.12, -0.06, 0.06))
        valence = float(np.clip(tonal_component + tempo_component + brightness_component + warmth_component, -1.0, 1.0))
        if valence >= 0.27 and energy >= 0.58:
            label = "uplifting and energetic"
        elif valence >= 0.20:
            label = "warm and hopeful"
        elif valence <= -0.27 and energy >= 0.58:
            label = "dark and intense"
        elif valence <= -0.20:
            label = "melancholic and restrained"
        elif energy >= 0.67:
            label = "urgent and restless"
        elif energy <= 0.32:
            label = "calm and atmospheric"
        else:
            label = "balanced and introspective"
        confidence = float(np.clip(0.35 + key_confidence * 0.25 + abs(valence) * 0.25 + abs(energy - 0.5) * 0.15, 0.35, 0.9))
        return {
            "label": label,
            "valence": round(valence, 4),
            "energy": round(energy, 4),
            "confidence": round(confidence, 4),
        }
