"""Core accounting tests. No credentials, network, or private fixture needed."""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest

from data_service.holdings import build, read_rules, trades, stock_positions, holding_days, value_positions


def activity(oid, side, qty, price, day, *, aid=None, symbol='XYZ'):
    return {'id': aid or oid, 'external_reference_id': oid,
            'symbol': {'id': symbol, 'symbol': symbol, 'type': {'code': 'cs'}, 'currency': {'code': 'USD'}}, 'option_symbol': None,
            'type': side, 'units': D(qty) * (1 if side == 'BUY' else -1),
            'price': D(price), 'trade_date': day + 'T00:00:00Z'}


def order(oid, side, qty, price, day):
    return {'brokerage_order_id': oid, 'universal_symbol': {'id': 'XYZ', 'symbol': 'XYZ', 'type': {'code': 'cs'}, 'currency': {'code': 'USD'}},
            'option_symbol': None, 'filled_quantity': qty, 'execution_price': price,
            'action': side, 'time_executed': day + 'T00:00:00Z'}


def snapshot(activities, quantity, orders=()):
    return {'positions': {'results': [{'instrument': {'id': 'XYZ', 'symbol': 'XYZ', 'kind': 'stock'},
                                     'units': quantity, 'price': '12', 'currency': 'USD'}],
                          'data_freshness': {'as_of': '2026-09-17T08:00:00Z'}},
            'activities': activities, 'orders': list(orders),
            'account': {'balance': {'total': {'amount': '1000'}}}, 'cash': '400',
            'fetched_at': '2026-09-17T08:01:00Z', 'source_timestamps': {}}


class AccountingTests(unittest.TestCase):
    def test_etf_uses_same_sequences_and_contributes_to_market_value(self):
        raw = snapshot([activity('b', 'BUY', '1200', '7', '2026-09-24')], '1200')
        raw['positions']['results'][0]['instrument']['kind'] = 'etf'
        raw['positions']['results'][0]['price'] = '7.51'
        result = build(raw, [])
        self.assertEqual(result['holdings'][0]['kind'], 'etf')
        self.assertEqual(result['funds']['stock_market_value'], D('9012'))
        self.assertEqual(result['holdings'][0]['sequences'][0]['held_quantity'], D(1200))

    def test_two_partial_sales_and_remaining_position(self):
        raw = snapshot([activity('b', 'BUY', '100', '10', '2026-09-01'),
                        activity('s1', 'SELL', '25', '15', '2026-09-03'),
                        activity('s2', 'SELL', '25', '8', '2026-09-04')], '50')
        result = build(raw, [])
        s, = result['holdings'][0]['sequences']
        self.assertEqual((s['sold_quantity'], s['held_quantity']), (D(50), D(50)))
        self.assertEqual((s['realized_pnl'], s['realized_pnl_percent']), (D(75), D(15)))
        self.assertEqual((s['unrealized_pnl'], s['unrealized_pnl_percent']), (D(100), D(20)))
        self.assertEqual((s['total_pnl'], s['total_pnl_percent']), (D(100), D(20)))
        self.assertEqual(s['market_value'], D(600))
        self.assertEqual(s['sold_percent'], D(50))
        self.assertEqual(result['summary']['pnl'], D(100))
        self.assertEqual(result['summary']['pnl_percent'], D(20))
        self.assertEqual(s['holding_days'], 16)
        self.assertEqual(set(result['funds']), {'stock_market_value', 'account_total', 'cash'})

    def test_market_value_preserves_fractional_cent_for_display(self):
        raw = snapshot([activity('b', 'BUY', '150', '90.96', '2026-09-18')], '150')
        raw['positions']['results'][0]['price'] = '92.2905'
        sequence, = build(raw, [])['holdings'][0]['sequences']
        self.assertEqual(sequence['market_value'], D('13843.575'))

    def test_same_id_fills_merge_but_different_orders_stay_separate(self):
        raw = snapshot([activity('b', 'BUY', '40', '10', '2026-09-01', aid='fill1'),
                        activity('b', 'BUY', '60', '12', '2026-09-01', aid='fill2'),
                        activity('other', 'BUY', '10', '9', '2026-09-02')], '110')
        result = build(raw, [])['holdings'][0]['sequences']
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['buy_price'], D('11.2'))
        self.assertEqual(result[0]['buys'][0]['activity_ids'], ['fill1', 'fill2'])

    def test_cumulative_order_replaces_activity_instead_of_adding(self):
        raw = snapshot([activity('b', 'BUY', '40', '10', '2026-09-01')], '100',
                       [order('b', 'BUY', '100', '11.2', '2026-09-01')])
        s, = build(raw, [])['holdings'][0]['sequences']
        self.assertEqual((s['buy_quantity'], s['buy_price']), (D(100), D('11.2')))

    def test_order_only_sell_fills_activity_delay(self):
        raw = snapshot([activity('b', 'BUY', '400', '34.855', '2026-09-09')], '200',
                       [order('s', 'SELL', '200', '31.285', '2026-09-16')])
        s, = build(raw, [])['holdings'][0]['sequences']
        self.assertEqual(s['realized_pnl'], D('-714'))
        self.assertEqual(s['held_quantity'], D(200))

    def test_manual_new_buy_sell_preserves_original_holding(self):
        raw = snapshot([activity('old', 'BUY', '20', '100', '2026-07-01'),
                        activity('new', 'BUY', '4', '90', '2026-08-12'),
                        activity('s', 'SELL', '4', '80', '2026-08-24')], '20')
        rules = [{'ticker': 'XYZ', 'buys': ['new'], 'sells': ['s']}]
        result = build(raw, rules)
        old, = result['holdings'][0]['sequences']
        self.assertEqual((old['held_quantity'], old['buy_price']), (D(20), D(100)))
        self.assertEqual(old['buy_ids'], ['old'])
        self.assertEqual(result['summary']['pnl'], old['total_pnl'])
        self.assertNotIn('closed_on', old)
        with self.assertRaisesRegex(ValueError, 'Ambiguous sell'):
            build(raw, [])

    def test_same_day_explicit_sequence_preserves_other_buy(self):
        raw = snapshot([activity('sell', 'SELL', '300', '51.03', '2026-09-14'),
                        activity('a', 'BUY', '300', '51.0299', '2026-09-14'),
                        activity('b', 'BUY', '300', '51.4', '2026-09-14')], '300')
        rules = [{'ticker': 'XYZ', 'buys': ['a'], 'sells': ['sell']}]
        b, = build(raw, rules)['holdings'][0]['sequences']
        self.assertEqual(b['buy_ids'], ['b'])
        self.assertEqual(b['buy_price'], D('51.4'))
        self.assertEqual(b['held_quantity'], D(300))

    def test_merged_buys_have_weighted_entry_price(self):
        raw = snapshot([activity('a', 'BUY', '5', '10', '2026-06-01'),
                        activity('b', 'BUY', '10', '20', '2026-06-01'),
                        activity('c', 'BUY', '10', '30', '2026-06-15')], '25')
        s, = build(raw, [{'ticker': 'XYZ', 'buys': ['a', 'b', 'c'], 'sells': []}])['holdings'][0]['sequences']
        self.assertEqual((s['buy_price'], s['opened_on']), (D(22), '2026-06-01'))

    def test_prior_closed_episode_and_unheld_symbol_are_ignored(self):
        raw = snapshot([activity('old', 'BUY', '100', '10', '2026-08-01'),
                        activity('closed', 'SELL', '100', '11', '2026-08-02'),
                        activity('current', 'BUY', '50', '12', '2026-09-01'),
                        activity('unrelated', 'BUY', '5', '1', '2026-09-01', symbol='OTHER')], '50')
        s, = build(raw, [])['holdings'][0]['sequences']
        self.assertEqual(s['buy_ids'], ['current'])
        self.assertNotIn('unrelated', trades(raw, stock_positions(raw)))

    def test_conflicting_or_reused_sell_fails(self):
        raw = snapshot([activity('a', 'BUY', '20', '10', '2026-09-01'),
                        activity('b', 'BUY', '4', '11', '2026-09-02'),
                        activity('s', 'SELL', '10', '12', '2026-09-03')], '14')
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            build(raw, [{'ticker': 'XYZ', 'buys': ['b'], 'sells': ['s']}])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            build(raw, [{'ticker': 'XYZ', 'buys': ['a'], 'sells': ['s']},
                        {'ticker': 'XYZ', 'buys': ['b'], 'sells': ['s']}])

    def test_missing_buy_origin_fails(self):
        with self.assertRaisesRegex(ValueError, 'quantity mismatch'):
            build(snapshot([activity('s', 'SELL', '10', '12', '2026-09-01')], '20'), [])

    def test_missing_sale_cannot_make_recent_buy_look_like_entire_holding(self):
        raw = snapshot([activity('old', 'BUY', '20', '10', '2026-08-01'),
                        activity('new', 'BUY', '20', '11', '2026-09-01')], '20')
        with self.assertRaisesRegex(ValueError, 'quantity mismatch'):
            build(raw, [])

    def test_short_holding_days_skip_only_weekends_then_return_to_calendar_days(self):
        self.assertEqual(holding_days('2026-10-02', '2026-10-02'), 0)
        self.assertEqual(holding_days('2026-10-02', '2026-10-05'), 1)
        self.assertEqual(holding_days('2026-10-02', '2026-10-09'), 5)
        self.assertEqual(holding_days('2026-10-02', '2026-10-10'), 8)
        # A weekday holiday still counts; no exchange calendar is involved.
        self.assertEqual(holding_days('2026-09-04', '2026-09-07'), 1)

    def test_closed_today_is_found_from_fills_without_any_current_position(self):
        raw = snapshot([activity('b', 'BUY', '100', '10', '2026-09-14')], '0',
                       [order('s', 'SELL', '100', '9', '2026-09-17')])
        raw['positions']['results'] = []
        base = build(raw, [])
        s, = base['holdings'][0]['sequences']
        self.assertTrue(s['closed_today'])
        self.assertEqual((s['market_value'], s['total_pnl'], s['total_pnl_percent']), (D(0), D(-100), D(-10)))
        self.assertEqual(s['holding_days'], 3)
        quotes = {'XYZ.US': {'Intraday': {'timestamp': 100, 'last_price': 11, 'prev_close': 9.5, 'trade_session': 'Intraday'}}}
        current = value_positions(base, quotes)
        self.assertEqual(current['holdings'][0]['sequences'][0]['day_pnl'], D(-50))
        self.assertEqual(current['summary'], {'pnl': D(0), 'pnl_percent': None, 'day_pnl': D(-50)})
        self.assertEqual(current['funds']['account_total'], D(400))
        self.assertEqual(value_positions(base, quotes, '2026-09-18')['holdings'], [])

    def test_closed_today_group_and_open_group_of_same_ticker_reconcile(self):
        raw = snapshot([activity('old', 'BUY', '20', '10', '2026-09-14'),
                        activity('closed', 'SELL', '20', '8', '2026-09-17'),
                        activity('new', 'BUY', '10', '11', '2026-09-17')], '10')
        rules = [{'ticker': 'XYZ', 'buys': ['old'], 'sells': ['closed']}]
        result = build(raw, rules)
        old, new = result['holdings'][0]['sequences']
        self.assertTrue(old['closed_today'])
        self.assertFalse(new['closed_today'])
        self.assertEqual(result['summary']['pnl'], D(10))
        self.assertEqual(new['holding_days'], 0)

    def test_sold_only_previous_day_is_not_retained(self):
        raw = snapshot([activity('b', 'BUY', '10', '10', '2026-09-14'),
                        activity('s', 'SELL', '10', '9', '2026-09-16')], '0')
        self.assertEqual(build(raw, [])['holdings'], [])

    def test_multiple_flat_episodes_closed_today_survive_without_old_history(self):
        raw = snapshot([activity('old', 'BUY', '5', '1', '2026-08-01'),
                        activity('old-sell', 'SELL', '5', '2', '2026-08-02'),
                        activity('a', 'BUY', '10', '10', '2026-09-14'),
                        activity('b', 'BUY', '20', '11', '2026-09-17'),
                        activity('sa', 'SELL', '10', '9', '2026-09-17'),
                        activity('sb', 'SELL', '20', '12', '2026-09-17')], '0')
        rules = [{'ticker': 'XYZ', 'buys': ['a'], 'sells': ['sa']},
                 {'ticker': 'XYZ', 'buys': ['b'], 'sells': ['sb']}]
        rows = build(raw, rules)['holdings'][0]['sequences']
        self.assertEqual([s['buy_ids'] for s in rows], [['a'], ['b']])
        self.assertTrue(all(s['closed_today'] for s in rows))

    def test_missing_buy_or_ambiguous_closed_sell_is_not_guessed(self):
        raw = snapshot([activity('s', 'SELL', '10', '9', '2026-09-17')], '0')
        with self.assertRaisesRegex(ValueError, 'quantity mismatch'):
            build(raw, [])
        raw['activities'] = [activity('a', 'BUY', '10', '10', '2026-09-17'),
                             activity('b', 'BUY', '10', '11', '2026-09-17'),
                             activity('s', 'SELL', '20', '9', '2026-09-17')]
        with self.assertRaisesRegex(ValueError, 'Ambiguous sell'):
            build(raw, [])

    def test_txt_supports_comments_spaces_and_merged_buy_alias(self):
        raw = snapshot([activity('a', 'BUY', '10', '10', '2026-09-01'),
                        activity('b', 'BUY', '10', '12', '2026-09-02'),
                        activity('s', 'SELL', '5', '15', '2026-09-03')], '15')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'merge_buys.txt').write_text('# XYZ\na  b\n')
            (folder / 'sequences.txt').write_text('b\ts  # can reference either merged buy\n')
            rules = read_rules(raw, folder)
            s, = build(raw, rules)['holdings'][0]['sequences']
            self.assertEqual((s['buy_price'], s['realized_pnl']), (D(11), D(20)))
            (folder / 'sequences.txt').write_text('missing s\n')
            with self.assertRaises(KeyError):
                read_rules(raw, folder)
