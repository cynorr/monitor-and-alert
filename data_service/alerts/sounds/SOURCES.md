# Alert audio sources

- `up.wav`, `down.wav`: existing project directional alert tones, retained and trimmed at both ends with FFmpeg `silenceremove`, threshold `-50dB`.
- `urgent.wav`: Kenney **Interface Sounds 1.0**, original `Audio/error_008.ogg`, converted to mono 44.1kHz WAV and trimmed at both ends at `-50dB`. Source: https://kenney.nl/assets/interface-sounds . CC0; original license included in `Kenney-License.txt`.

Preparation filter: `silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse`. Internal pauses are retained. FFmpeg is a preparation tool only; runtime playback uses the existing system player.
