"""Playback lifecycle only; subprocesses are mocked and never emit audio."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from data_service.alerts.sound import AlertSound


def test_playback_is_serial_and_keeps_direction(monkeypatch):
    async def scenario():
        sound = AlertSound()
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def spawn(*args, **kwargs):
            calls.append(args)
            process = SimpleNamespace(returncode=None)
            async def communicate():
                if len(calls) == 1:
                    started.set(); await release.wait()
                process.returncode = 0
                return b'', b''
            process.communicate = communicate
            return process
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
        worker = asyncio.create_task(sound.run())
        try:
            sound.play('up'); sound.play('down')
            await started.wait()
            assert len(calls) == 1
            release.set()
            await sound.queue.join()
            assert [call[1].rsplit('/', 1)[-1] for call in calls] == ['up.wav'] * 4 + ['down.wav'] * 4
            assert sound.state()['error'] is None
        finally:
            worker.cancel(); await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['spawn', 'exit'])
def test_playback_failure_is_visible_and_next_sound_can_play(monkeypatch, failure):
    async def scenario():
        sound = AlertSound()
        process = SimpleNamespace(returncode=None, wait=AsyncMock())
        def terminate(): process.returncode = -15
        process.terminate = Mock(side_effect=terminate)
        async def communicate():
            process.returncode = 1
            return b'', b'audio output failed'
        process.communicate = communicate
        good = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b'', b'')))
        spawn = AsyncMock(side_effect=[OSError('player missing') if failure == 'spawn' else process] + [good] * 4)
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
        worker = asyncio.create_task(sound.run())
        try:
            sound.play('up'); await sound.queue.join()
            assert sound.state()['error'].startswith('Could not play alert sound:')
            sound.play('down'); await sound.queue.join()
            assert sound.state()['error'] is None and spawn.await_count == 5
        finally:
            worker.cancel(); await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(scenario())


def test_shutdown_stops_current_playback(monkeypatch):
    async def scenario():
        sound = AlertSound()
        started = asyncio.Event()
        process = SimpleNamespace(returncode=None, wait=AsyncMock())
        def terminate(): process.returncode = -15
        process.terminate = Mock(side_effect=terminate)
        async def communicate():
            started.set(); await asyncio.Event().wait()
        process.communicate = communicate
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', AsyncMock(return_value=process))
        worker = asyncio.create_task(sound.run())
        sound.play('up'); await started.wait()
        worker.cancel(); await asyncio.gather(worker, return_exceptions=True)
        process.terminate.assert_called_once(); process.wait.assert_awaited_once()
        assert sound.queue.empty()
    asyncio.run(scenario())
