"""Speech infrastructure package."""
from .mock import MockSpeechRecognizer
from .piper_tts import MockTTSSynthesizer, PiperTTS
from .prisma import PrismaRecognizer
from .protocol import (
    AudioInput,
    SpeechRecognizer,
    SynthesisInput,
    SynthesisOutput,
    Transcript,
    TranscriptSegment,
    TTSSynthesizer,
)
from .whisper import WhisperRecognizer

__all__ = [
    "AudioInput",
    "MockSpeechRecognizer",
    "MockTTSSynthesizer",
    "PiperTTS",
    "PrismaRecognizer",
    "SpeechRecognizer",
    "SynthesisInput",
    "SynthesisOutput",
    "Transcript",
    "TranscriptSegment",
    "TTSSynthesizer",
    "WhisperRecognizer",
]
