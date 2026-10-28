# Alert sound patterns

Updated: 2026-10-26. These three WAVs contain the complete two-burst pattern; the backend plays each file once.

- `up.wav`: project-generated, steady 740Hz sine beep with a subtle second harmonic; two short beeps per burst.
- `down.wav`: Kenney **Interface Sounds 1.0**, `Audio/minimize_008.ogg`; three short descending tones per burst.
- `urgent.wav`: same pack, `Audio/error_004.ogg`; four short urgent tones per burst. Both up/down urgent alerts use this sound while preserving their direction in unread state.
- Source: [Kenney Interface Sounds](https://kenney.nl/assets/interface-sounds). CC0; the original license is retained in `Kenney-License.txt`. No network or FFmpeg is required at runtime.

Preparation: download the official archive and run `.venv/bin/python scripts/build_alert_sounds.py /path/to/kenney_interface-sounds.zip`. FFmpeg decodes the two source samples; silence is trimmed, the complete short sample fitted to 140ms, amplitude normalized and 8ms endpoint fades applied. The up tone is synthesized locally. All output is mono 44.1kHz PCM WAV.

`data_service/alerts/sound.py::beat_offsets` is the single timing source for preparation and playback feedback: 280ms between beat starts, 650ms between bursts, two bursts. Total durations are 1.49s / 2.05s / 2.61s. The frontend receives pulse timestamps from the same playback task and animates the common row wave; it never plays browser audio.
