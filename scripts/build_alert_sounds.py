"""Prepare the three short alert patterns; runtime only needs the generated WAVs.

Usage: .venv/bin/python scripts/build_alert_sounds.py /path/to/kenney_interface-sounds.zip
Source and license: data_service/alerts/sounds/SOURCES.md
"""
from __future__ import annotations

import math
from pathlib import Path
import subprocess
import sys
import wave
import zipfile

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_service.alerts.sound import SOUNDS, TONE_SECONDS, beat_offsets

RATE = 44100


def sample(archive, name):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-ac', '1', '-ar', str(RATE),
                          '-f', 'f32le', 'pipe:1'], input=archive.read(name), capture_output=True, check=True).stdout
    values = np.frombuffer(raw, dtype='<f4').copy()
    audible = np.flatnonzero(np.abs(values) > .003)
    values = values[audible[0]:audible[-1] + 1]
    size = round(TONE_SECONDS * RATE)
    # Keep each complete short sound, fitting it into the common beat duration.
    values = np.interp(np.linspace(0, len(values) - 1, size), np.arange(len(values)), values)
    return values / np.max(np.abs(values)) * .42


def build(source):
    size = round(TONE_SECONDS * RATE)
    t = np.arange(size) / RATE
    up = np.sin(2 * math.pi * 740 * t) + .08 * np.sin(2 * math.pi * 1480 * t)
    up *= .32
    with zipfile.ZipFile(source) as archive:
        tones = {'up': up, 'down': sample(archive, 'Audio/minimize_008.ogg'),
                 'urgent': sample(archive, 'Audio/error_004.ogg')}
    for kind, tone in tones.items():
        # Short fades prevent clicks at both ends of a beat.
        fade = round(.008 * RATE)
        tone[:fade] *= np.linspace(0, 1, fade)
        tone[-fade:] *= np.linspace(1, 0, fade)
        offsets = beat_offsets(kind)
        values = np.zeros(round((offsets[-1] + TONE_SECONDS) * RATE))
        for offset in offsets:
            start = round(offset * RATE)
            values[start:start + size] = tone
        with wave.open(str(SOUNDS / (kind + '.wav')), 'wb') as output:
            output.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            output.writeframes((values * 32767).astype('<i2').tobytes())
        print(f'{kind}: {len(offsets)} tones, {len(values) / RATE:.2f}s')


if __name__ == '__main__':
    build(sys.argv[1])
