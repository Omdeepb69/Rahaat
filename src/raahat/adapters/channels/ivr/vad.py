"""Voice Activity Detection (VAD) detectors for speech segmentation."""
from __future__ import annotations

import math
import struct
from typing import Protocol

from raahat.infrastructure.speech import AudioInput


class VADDetector(Protocol):
    """Protocol for detecting presence of human voice activity in audio."""

    def detect_speech(self, audio: AudioInput) -> bool: ...


class EnergyVADDetector:
    """Lightweight pure-Python energy-based VAD detector.

    Computes Root Mean Square (RMS) amplitude of 16-bit linear PCM audio.
    Used for local testing and as a fallback when ML models are unavailable.
    """

    def __init__(self, rms_threshold: float = 300.0) -> None:
        self.rms_threshold = rms_threshold

    def detect_speech(self, audio: AudioInput) -> bool:
        if not audio.audio_bytes:
            return False

        # In testing, string/mock payloads might be passed as bytes
        if len(audio.audio_bytes) < 4:
            return False

        try:
            # Assume 16-bit signed PCM (little-endian, 2 bytes per sample)
            num_samples = len(audio.audio_bytes) // 2
            if num_samples == 0:
                return False
            samples = struct.unpack(f"<{num_samples}h", audio.audio_bytes[: num_samples * 2])
            sum_squares = sum(s * s for s in samples)
            rms = math.sqrt(sum_squares / num_samples)
            return bool(rms >= self.rms_threshold)
        except Exception:
            # Fallback byte energy calculation if audio is not valid raw PCM
            non_zeros = sum(1 for b in audio.audio_bytes if b != 0)
            return non_zeros > (len(audio.audio_bytes) * 0.1)


class SileroVADDetector:
    """Silero VAD adapter with automatic fallback to EnergyVADDetector."""

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = threshold
        self._energy_fallback = EnergyVADDetector()
        self._model = None
        self._available = False

        try:
            import torch  # noqa: F401
            # Silero model loading would happen here if weights are present
            # For now, mark unavailable to safely use energy fallback unless torch model injected
        except ImportError:
            self._available = False

    def detect_speech(self, audio: AudioInput) -> bool:
        if not self._available or self._model is None:
            return self._energy_fallback.detect_speech(audio)

        # Implementation would call torch silero model on waveform
        return self._energy_fallback.detect_speech(audio)
