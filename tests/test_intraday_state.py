from datetime import date, datetime
from unittest.mock import Mock

import pytest

from data_service.calendar import ET, TradingCalendar
from data_service.charts import ChartCache
from data_service.intraday_state import IntradayState
from data_service.intraday_state.engine import load_config
from data_service.store import Bar, BarStore


@pytest.fixture(scope='module')
def calendar():
    return TradingCalendar(date(2026, 10, 16))


@pytest.fixture
def state(tmp_path, calendar):
    day = date(2026, 10, 16)
    opened, _ = calendar.session(day)
    now = [opened + 60]
    store = BarStore(tmp_path / 'bars.sqlite3', calendar, {'TEST.US'})
    rows = [Bar('TEST.US', '1d', calendar.grid(d, '1d')[0][0], 102, 105, 100, 102, 1000)
            for d in calendar.previous_days(day, 25)]
    store.upsert(rows, opened)
    charts = ChartCache(store, calendar, ready=lambda *_: True)
    charts.apply_candle('TEST.US', '1d', {'time': calendar.grid(day, '1d')[0][0],
                         'open': 100, 'high': 110, 'low': 100, 'close': 102, 'volume': 100})
    sound = Mock()
    value = IntradayState(charts, notify=sound.play, clock=lambda: now[0])
    value.scope({'TEST.US'}, set())
    yield value, now, sound
    store.close()


def tick(value, price, *, source='push', timestamp=None):
    value.quote('TEST.US', {'trade_session': 'Intraday', 'timestamp': timestamp or int(value.now()),
                           'last_price': price, 'source': source})


def test_candidate_gate_thresholds_reentry_and_silent_downgrade(state):
    value, now, sound = state
    tick(value, 101)
    tick(value, 103)
    assert value.values['TEST.US']['up_adr'] == pytest.approx(.6)
    assert value.values['TEST.US']['state'] == 'up-notice'
    tick(value, 104)
    tick(value, 105)
    assert [call.args[1] for call in sound.play.call_args_list] == ['up', 'urgent']
    tick(value, 104); tick(value, 103)
    assert sound.play.call_count == 2
    tick(value, 105)
    assert sound.play.call_args.args == ('TEST.US', 'urgent') and sound.play.call_count == 3
    # A large rise from LOD below open remains outside candidate notifications.
    value.charts.active['TEST.US', '1d'].update(open=108)
    tick(value, 106)
    assert value.values['TEST.US']['state'] == 'neutral' and sound.play.call_count == 3


def test_holdings_risk_above_open_dominates_up_and_unmasking_is_silent(state):
    value, now, sound = state
    value.scope(set(), {'TEST.US'})
    value.charts.active['TEST.US', '1d']['high'] = 112
    tick(value, 112)
    tick(value, 108)
    row = value.values['TEST.US']
    assert row['above_open'] and row['up_level'] == 2 and row['state'] == 'down-notice'
    tick(value, 106)
    assert value.values['TEST.US']['state'] == 'down-urgent'
    assert [call.args[1] for call in sound.play.call_args_list] == ['down', 'urgent']
    # Up was already urgent before the warning; exposing its color is not a new crossing.
    tick(value, 110)
    assert value.values['TEST.US']['state'] == 'up-urgent'
    assert sound.play.call_count == 2


def test_ema_recross_repeats_without_manual_reset_or_cooldown(state):
    value, now, sound = state
    tick(value, 101); tick(value, 102.2)
    tick(value, 101); tick(value, 102.2)
    assert [call.args[1] for call in sound.play.call_args_list] == ['up', 'up']


def test_restart_snapshot_and_extended_do_not_replay_and_adr_is_fixed(state):
    value, now, sound = state
    tick(value, 105)
    assert value.values['TEST.US']['state'] == 'up-urgent' and not sound.play.called
    old = value.values['TEST.US']['adr20']
    value.charts.store.db.execute('UPDATE bars SET high=110')
    value.charts.store.revisions['TEST.US', '1d'] += 1
    tick(value, 104)
    assert value.values['TEST.US']['adr20'] == old
    value.reset(); tick(value, 105)
    assert not sound.play.called
    tick(value, 100, source='snapshot')
    assert value.values['TEST.US']['price'] == 105
    value.quote('TEST.US', {'trade_session': 'Post', 'timestamp': now[0], 'last_price': 90})
    assert value.values['TEST.US']['price'] == 105
    now[0] = value.calendar.session(value.day)[1]
    value.tick()
    assert value.state()['symbols'] == {} and not sound.play.called


def test_rank_promotes_immediately_but_demotes_at_five_minute_boundary(state):
    value, now, sound = state
    tick(value, 101)
    tick(value, 105)
    assert value.values['TEST.US']['rank'][0] == 3
    tick(value, 101)
    assert value.values['TEST.US']['state'] == 'neutral'
    assert value.values['TEST.US']['rank'][0] == 3
    now[0] = value.calendar.session(value.day)[0] + 300
    value.tick()
    assert value.values['TEST.US']['rank'][0] == 1


def test_scope_removal_clears_symbol_and_does_not_leave_rearm_state(state):
    value, now, sound = state
    tick(value, 103)
    value.scope(set(), set())
    tick(value, 105)
    assert not value.values and not sound.play.called


def add_volume(value, day, tf, minute, volume):
    opened, closed = value.calendar.session(day)
    value.charts.store.upsert([Bar('TEST.US', tf, opened + minute * 60,
                                   100, 105, 100, 102, volume)], closed)


def test_cumulative_largest_first_missing_small_bars_and_partial_history(state):
    value, now, _ = state
    for day in value.calendar.previous_days(date(2026, 10, 16)):
        # The first three 5m bars are deliberately absent; the official 15m covers them.
        for tf, minute, volume in [('15m', 0, 300), ('5m', 15, 100), ('5m', 20, 100), ('5m', 25, 100)]:
            add_volume(value, day, tf, minute, volume)
    day = date(2026, 10, 16)
    for tf, minute, volume in [('15m', 0, 600), ('5m', 15, 200), ('5m', 20, 200)]:
        add_volume(value, day, tf, minute, volume)
    opened, _ = value.calendar.session(day)
    now[0] = opened + 26 * 60
    for tf, minute, volume in [('5m', 25, 40), ('15m', 15, 440)]:
        value.charts.apply_candle('TEST.US', tf, {'time': opened + minute * 60,
             'open': 100, 'high': 105, 'low': 100, 'close': 102, 'volume': volume})
    tick(value, 103); value.tick()
    cumulative, local = (value.values['TEST.US'][key] for key in ('cum_vol', 'local_vol'))
    assert cumulative['actual'] == 1040 and cumulative['average'] == 520
    assert cumulative['samples'] == 5 and cumulative['ratio'] == 2
    assert local['window'] == '15m' and local['actual'] == 440 and local['average'] == 220
    assert local['ratio'] == 2


def test_volume_window_switches_at_fifteen_and_missing_day_is_not_zero(state):
    value, now, _ = state
    day = date(2026, 10, 16)
    previous = value.calendar.previous_days(day)[-1]
    add_volume(value, previous, '5m', 0, 100)
    opened, _ = value.calendar.session(day)
    value.charts.apply_candle('TEST.US', '5m', {'time': opened, 'open': 100, 'high': 105, 'low': 100, 'close': 102, 'volume': 40})
    tick(value, 103); value.tick()
    row = value.values['TEST.US']
    assert row['cum_vol']['samples'] == 1 and row['cum_vol']['average'] == 20
    assert row['cum_vol']['ratio'] == 2 and row['local_vol']['window'] == '5m'
    now[0] = opened + 900
    value.tick()
    assert value.values['TEST.US']['local_vol']['window'] == '15m'
    assert value.values['TEST.US']['local_vol']['ratio'] is None


def test_historical_half_day_is_skipped_at_missing_afternoon_and_dst_aligns(state):
    value, _, _ = state
    half = date(2026, 11, 27)
    opened, closed = value.calendar.session(half)
    assert value.volume.historical('TEST.US', opened, opened + 4 * 3600) is None
    for day in (date(2026, 10, 30), date(2026, 11, 2)):
        add_volume(value, day, '5m', 0, 100)
    result = value.volume.comparison('TEST.US', date(2026, 11, 3), 0, 60, 40)
    assert result['samples'] == 2 and result['average'] == 20 and result['ratio'] == 2


def test_quote_at_boundary_cannot_freeze_the_previous_volume_rank(state):
    value, now, _ = state
    opened, _ = value.calendar.session(date(2026, 10, 16))
    tick(value, 103); value.tick()
    value.values['TEST.US']['cum_vol'] = {'ratio': 3.1}
    now[0] = opened + 300
    # The price callback gets there before the background volume calculation.
    tick(value, 104)
    value.tick()
    assert value.values['TEST.US']['rank'][1] == 0


def test_data_service_forwards_quotes_and_resets_automatic_baselines(state, tmp_path):
    from data_service.config import Ticker
    from data_service.service import DataService
    value, now, sound = state
    service = DataService([Ticker('TEST.US', 'TEST', 'focus')], tmp_path / 'service', clock=lambda: now[0])
    service.intraday = value
    try:
        service.apply_quote('TEST.US', {'trade_session': 'Intraday', 'timestamp': now[0], 'last_price': 101})
        service.apply_quote('TEST.US', {'trade_session': 'Intraday', 'timestamp': now[0], 'last_price': 103})
        assert value.state()['symbols']['TEST.US']['state'] == 'up-notice'
        assert sound.play.call_args.args == ('TEST.US', 'up')
        service.reset_realtime()
        assert not value.state()['symbols']
        service.apply_quote('TEST.US', {'trade_session': 'Intraday', 'timestamp': now[0], 'last_price': 105})
        assert sound.play.call_count == 1
    finally:
        service.store.close()


def test_config_rejects_reversed_thresholds(tmp_path):
    import json
    config = load_config()
    config['down_urgent'] = .5
    path = tmp_path / 'config.json'; path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='down thresholds'):
        load_config(path)
