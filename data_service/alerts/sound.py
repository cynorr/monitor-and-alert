"""Backend audio and beat feedback for each independent alert."""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)
SOUNDS = Path(__file__).with_name('sounds')
TONE_SECONDS, BEAT_SECONDS, BURST_GAP, BURSTS = .14, .28, .65, 2
COUNTS = {'up': 2, 'down': 3, 'urgent': 4}


def beat_offsets(kind):
    count = COUNTS[kind]
    segment = (count - 1) * BEAT_SECONDS + TONE_SECONDS + BURST_GAP
    return [burst * segment + beat * BEAT_SECONDS for burst in range(BURSTS) for beat in range(count)]


class AlertSound:
    def __init__(self):
        self.tasks = {}
        self.error = None
        self.on_change = lambda: None

    def play(self, symbol, direction, level, fired_at):
        notice = {'symbol': symbol, 'fired_at': fired_at, 'pulse_at': 0}
        task = asyncio.create_task(self._play('urgent' if level == 2 else direction, notice))
        self.tasks[task] = notice

    def state(self):
        latest = {}
        for notice in self.tasks.values():
            symbol = notice['symbol']
            if symbol not in latest or notice['fired_at'] >= latest[symbol]['fired_at']:
                latest[symbol] = dict(notice)
        return {'enabled': True, 'error': self.error, 'playing': list(latest.values())}

    async def _beats(self, kind, notice):
        loop = asyncio.get_running_loop()
        start = loop.time()
        for offset in beat_offsets(kind):
            await asyncio.sleep(max(0, start + offset - loop.time()))
            notice['pulse_at'] = time.time()
            self.on_change()

    async def _play(self, kind, notice):
        try:
            process = await asyncio.create_subprocess_exec(
                '/usr/bin/afplay', str(SOUNDS / (kind + '.wav')),
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
            beats = asyncio.create_task(self._beats(kind, notice))
            try:
                _, stderr = await process.communicate()
            finally:
                beats.cancel()
                await asyncio.gather(beats, return_exceptions=True)
                if process.returncode is None:
                    process.terminate()
                    await process.wait()
            if process.returncode:
                raise RuntimeError(f"exit {process.returncode}: {stderr.decode().strip()}")
            self.error = None
        except (OSError, RuntimeError) as error:
            self.error = 'Could not play alert sound: ' + str(error)
            log.error('%s', self.error)
        finally:
            self.tasks.pop(asyncio.current_task(), None)
            self.on_change()

    async def close(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
