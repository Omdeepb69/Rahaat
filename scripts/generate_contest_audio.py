#!/usr/bin/env python3
"""Generate or synthesize contest demonstration audio clips for Gnani AI Challenge.

Generates 4 targeted emergency distress clips highlighting:
1. Code-mixed Hinglish (P0 Flood rescue)
2. Hindi Medical Emergency (Elderly trapped + oxygen)
3. Malayalam Regional Distress (Alappuzha flood)
4. Marathi Regional Distress (Pune flood)

Can generate synthetic acoustic speech waveforms with ambient background rain/water noise,
or use Gnani Timbre TTS when GNANI_API_KEY_TTS_STT is provided.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import struct
import sys
import wave
from pathlib import Path

# Allow importing project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "demo" / "audio" / "contest_showcase"

CLIPS = [
    {
        "filename": "01_hinglish_noisy_flood.wav",
        "language": "hi-en",
        "text": "Sir please jaldi boat bhejiye, Bund Garden bridge ke pass ground floor pura doob chuka hai, teen log trapped hain!",
        "noise_type": "flood_rain",
        "duration_sec": 7.5,
    },
    {
        "filename": "02_hindi_medical_p0.wav",
        "language": "hi-IN",
        "text": "Hum Shaniwar Wada ke paas phanse hain, paani 5 feet badh raha hai, buzug mahila hain jinhe oxygen chahiye, turant rescue team bhejo!",
        "noise_type": "rain",
        "duration_sec": 8.0,
    },
    {
        "filename": "03_malayalam_alappuzha_boat.wav",
        "language": "ml-IN",
        "text": "Alappuzha boat jetty aduth vellam keri, naalu per ottappettu, vegam boat ayakkumo!",
        "noise_type": "water",
        "duration_sec": 6.5,
    },
    {
        "filename": "04_marathi_shaniwar_wada.wav",
        "language": "mr-IN",
        "text": "Shaniwar Wada javal khup pani vadhalay, aamhi chhatavar aahot, char loka aahot, lavkar madat pathva!",
        "noise_type": "storm",
        "duration_sec": 7.0,
    },
]


def _synthesize_acoustic_with_noise(
    path: Path,
    duration_sec: float,
    sample_rate: int = 16000,
    noise_level: float = 0.15,
) -> None:
    """Generate a realistic speech-like acoustic pattern with background rain/water noise.

    Speech frequencies modulated across vowel formants (200Hz - 2500Hz) with
    pink/brownian water noise background.
    """
    total_samples = int(duration_sec * sample_rate)
    samples: list[int] = []

    # Brownian / pink noise state for rain/water simulation
    brown_noise = 0.0

    for i in range(total_samples):
        t = i / float(sample_rate)

        # 1. Rhythmic speech envelope (syllable pacing: ~3.5 Hz)
        syllable_env = max(0.0, math.sin(2 * math.pi * 3.5 * t)) ** 1.5

        # 2. Formant harmonics simulating human vocal tract
        f0 = 140.0 + 30.0 * math.sin(2 * math.pi * 0.8 * t)  # Pitch modulation
        f1 = 550.0  # First formant (vowel 'a' / 'aa')
        f2 = 1750.0 # Second formant
        speech_val = (
            0.5 * math.sin(2 * math.pi * f0 * t)
            + 0.3 * math.sin(2 * math.pi * f1 * t)
            + 0.2 * math.sin(2 * math.pi * f2 * t)
        ) * syllable_env

        # 3. Ambient flood water / heavy rain background noise
        white = (random.random() * 2.0 - 1.0)
        brown_noise = (brown_noise + (0.02 * white)) / 1.02
        water_noise = brown_noise * noise_level

        # Mixed signal
        mixed = (speech_val * 0.75 + water_noise) * 0.8
        clamped = max(-1.0, min(1.0, mixed))
        sample_16bit = int(clamped * 30000)
        samples.append(sample_16bit)

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        packed = struct.pack(f"<{len(samples)}h", *samples)
        wf.writeframes(packed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate contest showcase audio clips")
    parser.add_argument("--use-timbre", action="store_true", help="Synthesize using Gnani Timbre TTS API if key present")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    api_key = os.getenv("GNANI_API_KEY_TTS_STT") or os.getenv("GNANI_API_KEY")

    for clip in CLIPS:
        filename = str(clip["filename"])
        dest = OUTPUT_DIR / filename
        lang = str(clip["language"])
        print(f"Generating {filename} ({lang}) …")

        if args.use_timbre and api_key:
            # Call Gnani Timbre TTS
            try:
                import httpx

                headers = {"X-API-Key-ID": api_key, "Content-Type": "application/json"}
                payload = {
                    "text": str(clip["text"]),
                    "model": "timbre-v3.0",
                    "voice": "Shivani",
                    "language": lang,
                    "audio_config": {"sample_rate": 16000, "container": "wav"},
                }
                res = httpx.post("https://api.vachana.ai/api/v1/tts/inference", json=payload, headers=headers, timeout=30)
                if res.status_code == 200:
                    dest.write_bytes(res.content)
                    print(f"  ✔ Synthesized via Gnani Timbre: {dest.name}")
                    continue
                else:
                    print(f"  ⚠ Timbre returned {res.status_code}, falling back to acoustic generation")
            except Exception as e:
                print(f"  ⚠ Timbre failed ({e}), falling back to acoustic generation")

        # Standard acoustic generation with background flood/water noise
        _synthesize_acoustic_with_noise(
            dest,
            duration_sec=float(str(clip["duration_sec"])),
            sample_rate=16000,
        )
        print(f"  ✔ Created acoustic simulation: {dest.name}")

    print("\nAll contest showcase audio clips generated at:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
