"""Only the changed playback lifecycle. No audio or credentials."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from data_service.alerts.sound import AlertSound


def test_symbols_play_independently_four_times_and_publish_playing_state(monkeypatch):
    async def scenario():
        sound = AlertSound()
        release = asyncio.Event()
        calls, changes = [], []
        sound.on_change = lambda: changes.append(sound.state()['playing'])
        async def spawn(*args, **kwargs):
            calls.append(args[1].rsplit('/', 1)[-1])
            process = SimpleNamespace(returncode=None)
            async def communicate():
                await release.wait()
                process.returncode = 0
                return b'', b''
            process.communicate = communicate
            return process
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
        sound.play('A.US','up'); sound.play('B.US','urgent')
        await asyncio.sleep(0)
        assert calls == ['up.wav', 'urgent.wav']
        assert sound.state()['playing'] == ['A.US','B.US']
        release.set()
        await asyncio.gather(*list(sound.tasks))
        assert calls.count('up.wav') == calls.count('urgent.wav') == 4
        assert not sound.state()['playing'] and changes[-1] == []
    asyncio.run(scenario())


@pytest.mark.parametrize('failure', ['spawn','exit'])
def test_failure_stops_flashing_reports_error_and_later_alert_plays(monkeypatch, failure):
    async def scenario():
        sound = AlertSound()
        bad = SimpleNamespace(returncode=1, communicate=AsyncMock(return_value=(b'',b'output failed')))
        good = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b'',b'')))
        spawn = AsyncMock(side_effect=[OSError('missing') if failure == 'spawn' else bad] + [good]*4)
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
        sound.play('A.US','up'); await asyncio.gather(*list(sound.tasks))
        assert sound.error and not sound.state()['playing']
        sound.play('B.US','down'); await asyncio.gather(*list(sound.tasks))
        assert sound.error is None and spawn.await_count == 5
    asyncio.run(scenario())


def test_shutdown_terminates_all_playbacks(monkeypatch):
    async def scenario():
        sound = AlertSound()
        processes = []
        async def spawn(*args, **kwargs):
            process = SimpleNamespace(returncode=None, wait=AsyncMock())
            def terminate(): process.returncode = -15
            process.terminate = Mock(side_effect=terminate)
            async def communicate(): await asyncio.Event().wait()
            process.communicate = communicate
            processes.append(process)
            return process
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
        sound.play('A.US','up'); sound.play('B.US','down')
        await asyncio.sleep(0)
        await sound.close()
        assert len(processes) == 2 and not sound.tasks
        for process in processes:
            process.terminate.assert_called_once()
            process.wait.assert_awaited_once()
    asyncio.run(scenario())
