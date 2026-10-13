"""Convert any browser recording (webm / mp4 / ogg / wav) to 16 kHz mono float audio.

Uses the ffmpeg binary bundled with the `imageio-ffmpeg` pip package,
so nobody has to install ffmpeg on Windows by hand.
"""
import subprocess

import numpy as np

SAMPLE_RATE = 16000


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"  # fall back to a system ffmpeg (Colab has one)


def to_16k_mono(audio_bytes: bytes) -> np.ndarray:
    """Returns a float32 numpy array at 16 kHz, mono."""
    cmd = [
        _ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
        "-i", "pipe:0",
        "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "f32le", "pipe:1",
    ]
    proc = subprocess.run(cmd, input=audio_bytes, capture_output=True)
    if proc.returncode != 0:
        raise ValueError(f"Could not read audio: {proc.stderr.decode(errors='ignore')[:300]}")
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size < SAMPLE_RATE * 0.3:  # under 0.3 s
        raise ValueError("Audio is too short")
    return audio
