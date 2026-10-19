"""Independent backend playback; each alert plays its original sound four times."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)
SOUNDS = Path(__file__).with_name('sounds')


class AlertSound:
    def __init__(self):
        self.tasks = {}
        self.error = None
        self.on_change = lambda: None

    def play(self, symbol, direction):
        task = asyncio.create_task(self._play(direction))
        self.tasks[task] = symbol
        self.on_change()

    def state(self):
        return {'enabled': True, 'error': self.error, 'playing': sorted(set(self.tasks.values()))}

    async def _play(self, direction):
        try:
            for _ in range(4):
                process = await asyncio.create_subprocess_exec(
                    '/usr/bin/afplay', str(SOUNDS / (direction + '.wav')),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                try:
                    _, stderr = await process.communicate()
                finally:
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
