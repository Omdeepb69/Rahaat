"""Speech infrastructure package."""
from .mock import MockSpeechRecognizer
from .protocol import (
    AudioInput,
    SpeechRecognizer,
    Transcript,
    TranscriptSegment,
)

__all__ = [
    "AudioInput",
    "MockSpeechRecognizer",
    "SpeechRecognizer",
    "Transcript",
    "TranscriptSegment",
]
