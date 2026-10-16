"""Play short alert sounds from the backend, independently of browsers."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)
SOUNDS = Path(__file__).with_name('sounds')


class AlertSound:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.error = None

    def play(self, direction):
        self.queue.put_nowait(direction)

    def state(self):
        return {'enabled': True, 'error': self.error}

    async def run(self):
        while True:
            direction = await self.queue.get()
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
            except (OSError, RuntimeError) as error:
                self.error = 'Could not play alert sound: ' + str(error)
                log.error('%s', self.error)
            else:
                self.error = None
            finally:
                self.queue.task_done()
