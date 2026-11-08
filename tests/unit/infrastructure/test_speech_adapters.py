"""Unit tests for SpeechRecognizer and TTSSynthesizer infrastructure adapters."""
from __future__ import annotations

import pytest

from raahat.infrastructure.speech import (
    AudioInput,
    MockSpeechRecognizer,
    MockTTSSynthesizer,
    PiperTTS,
    PrismaRecognizer,
    SpeechRecognizer,
    SynthesisInput,
    SynthesisOutput,
    Transcript,
    TTSSynthesizer,
    WhisperRecognizer,
)


class DummyWhisperModel:
    """Mock whisper model instance."""

    def __init__(self, transcript_text: str = "madhav nagar near bus stop", language: str = "hi") -> None:
        self.text = transcript_text
        self.language = language

    def transcribe(self, audio_data: object, **kwargs: object) -> dict[str, object]:
        return {
            "text": self.text,
            "language": self.language,
            "segments": [
                {
                    "text": self.text,
                    "avg_logprob": -0.15,
                    "start": 0.0,
                    "end": 2.5,
                }
            ],
        }


class DummyPrismaHttpClient:
    """Mock http client for Prisma API."""

    def __init__(self, response_data: dict[str, object]) -> None:
        self.response_data = response_data
        self.calls: list[dict[str, object]] = []

    async def post(self, url: str, **kwargs: object) -> dict[str, object]:
        self.calls.append({"url": url, **kwargs})
        return self.response_data


class DummyPiperVoice:
    """Mock Piper voice instance."""

    def __init__(self, return_bytes: bytes = b"RIFF1234WAVEfmt ") -> None:
        self.return_bytes = return_bytes

    def synthesize(self, text: str, buf: object) -> None:
        if hasattr(buf, "write"):
            buf.write(self.return_bytes)


@pytest.mark.asyncio
async def test_speech_recognizer_protocol_mock() -> None:
    recognizer: SpeechRecognizer = MockSpeechRecognizer(default_text="hello world", default_confidence=0.99)
    audio = AudioInput(audio_bytes=b"\xff\xff\xff\xff", sample_rate=16000)
    result = await recognizer.transcribe(audio, language_hint="hi")

    assert isinstance(result, Transcript)
    assert result.text == "hello world"
    assert result.confidence == 0.99
    assert result.language == "hi"


@pytest.mark.asyncio
async def test_whisper_recognizer_without_installed_package() -> None:
    # If whisper is not installed, it should raise RuntimeError on transcription attempt
    recognizer = WhisperRecognizer(model_name="base")
    audio = AudioInput(audio_bytes=b"\x00\x00" * 16000, sample_rate=16000)

    with pytest.raises(RuntimeError, match="WhisperRecognizer requires 'openai-whisper'"):
        await recognizer.transcribe(audio)


@pytest.mark.asyncio
async def test_whisper_recognizer_with_allow_fallback() -> None:
    # When allow_fallback=True, should fallback to acoustic transcription without crashing
    recognizer = WhisperRecognizer(model_name="base", allow_fallback=True)
    audio = AudioInput(audio_bytes=b"Help! Family trapped on roof near Bund Garden Pune", sample_rate=16000)

    result = await recognizer.transcribe(audio, language_hint="hi")
    assert "Help! Family trapped" in result.text
    assert result.confidence >= 0.8
    assert result.language == "hi"


@pytest.mark.asyncio
async def test_whisper_recognizer_with_fallback_recognizer() -> None:
    custom_fallback = MockSpeechRecognizer(default_text="custom fallback transcript", default_confidence=0.91)
    recognizer = WhisperRecognizer(model_name="base", fallback_recognizer=custom_fallback)
    audio = AudioInput(audio_bytes=b"\xff\xff\xff\xff", sample_rate=16000)

    result = await recognizer.transcribe(audio)
    assert result.text == "custom fallback transcript"
    assert result.confidence == 0.91


@pytest.mark.asyncio
async def test_whisper_recognizer_with_model_instance() -> None:
    dummy_model = DummyWhisperModel(transcript_text="kaloor stadium junction", language="ml")
    recognizer = WhisperRecognizer(model_instance=dummy_model)
    audio = AudioInput(audio_bytes=b"\x00\x00" * 16000, sample_rate=16000)

    result = await recognizer.transcribe(audio, language_hint="ml")

    assert result.text == "kaloor stadium junction"
    assert result.language == "ml"
    assert len(result.segments) == 1
    assert result.segments[0].end_ms == 2500
    assert result.confidence > 0.8


@pytest.mark.asyncio
async def test_prisma_recognizer_without_api_key() -> None:
    recognizer = PrismaRecognizer(api_key=None, default_language="hi")
    audio = AudioInput(audio_bytes=b"some_audio", sample_rate=16000)
    result = await recognizer.transcribe(audio)

    assert result.text == ""
    assert result.confidence == 0.0
    assert result.language == "hi"


@pytest.mark.asyncio
async def test_prisma_recognizer_with_mock_client() -> None:
    mock_response = {
        "transcript": "pani ghar ke andar aa gaya hai",
        "confidence": 0.92,
        "language": "hi",
        "words": [
            {"word": "pani", "start_time": 0.1, "end_time": 0.4, "confidence": 0.95},
            {"word": "ghar", "start_time": 0.5, "end_time": 0.8, "confidence": 0.90},
        ],
    }
    client = DummyPrismaHttpClient(mock_response)
    recognizer = PrismaRecognizer(http_client=client, default_language="hi")
    audio = AudioInput(audio_bytes=b"raw_bytes_123", sample_rate=8000)

    result = await recognizer.transcribe(audio, language_hint="hi")

    assert result.text == "pani ghar ke andar aa gaya hai"
    assert result.confidence == 0.92
    assert len(result.segments) == 2
    assert result.segments[0].text == "pani"
    assert result.segments[0].start_ms == 100
    assert result.segments[1].end_ms == 800
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_piper_tts_synthesizer_protocol() -> None:
    mock_tts: TTSSynthesizer = MockTTSSynthesizer(sample_rate=16000)
    req = SynthesisInput(text="Aapki madad ke liye team bheji ja rahi hai", language="hi")
    output = await mock_tts.synthesize(req)

    assert isinstance(output, SynthesisOutput)
    assert output.sample_rate == 16000
    assert b"Aapki madad" in output.audio_bytes


@pytest.mark.asyncio
async def test_piper_tts_without_installed_package() -> None:
    piper = PiperTTS(model_path="/tmp/hindi_piper.onnx")
    req = SynthesisInput(text="namaste")

    with pytest.raises(RuntimeError, match="PiperTTS requires 'piper-tts'"):
        await piper.synthesize(req)


@pytest.mark.asyncio
async def test_piper_tts_with_mock_voice() -> None:
    dummy_voice = DummyPiperVoice(return_bytes=b"RIFFWAVE_SYNTH_AUDIO")
    piper = PiperTTS(voice_instance=dummy_voice, sample_rate=22050)
    req = SynthesisInput(text="kripya apna sthan batayein")

    output = await piper.synthesize(req)

    assert output.audio_bytes == b"RIFFWAVE_SYNTH_AUDIO"
    assert output.encoding == "wav"
    assert output.sample_rate == 22050
