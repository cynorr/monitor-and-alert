"""The small UserNotifications bridge. All Cocoa calls run on the app main thread."""
from __future__ import annotations

import logging
import webbrowser
import objc
import asyncio
from datetime import datetime
from threading import Lock

import AppKit
import Foundation
import UserNotifications as UN
from PyObjCTools import AppHelper

from ..calendar import ET

log = logging.getLogger(__name__)


class NotificationDelegate(Foundation.NSObject, protocols=[objc.protocolNamed('UNUserNotificationCenterDelegate')]):
    def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, center, notification, completion):
        completion(UN.UNNotificationPresentationOptionBanner | UN.UNNotificationPresentationOptionList | UN.UNNotificationPresentationOptionSound)

    def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(self, center, response, completion):
        event_id = response.notification().request().identifier()
        action = response.actionIdentifier()
        if action in ('CLOSE', UN.UNNotificationDismissActionIdentifier):
            self.bridge.acknowledge(event_id)
        elif action in ('OPEN', UN.UNNotificationDefaultActionIdentifier):
            self.bridge.open_event(event_id)
        completion()


class MacNotifications:
    def __init__(self, url):
        self.url, self.engine, self.loop = url, None, None
        self.ready, self.pending_open, self.pending_close = False, None, []
        self.shutdown_requested = False
        self.lock = Lock()
        self.value = dict(available=True, authorization='not_determined', sound=False, error=None)
        self.center = UN.UNUserNotificationCenter.currentNotificationCenter()
        self.delegate = NotificationDelegate.alloc().init()
        self.delegate.bridge = self
        self.center.setDelegate_(self.delegate)
        actions = [UN.UNNotificationAction.actionWithIdentifier_title_options_('OPEN', 'Open', UN.UNNotificationActionOptionForeground),
                   UN.UNNotificationAction.actionWithIdentifier_title_options_('CLOSE', 'Close', 0)]
        category = UN.UNNotificationCategory.categoryWithIdentifier_actions_intentIdentifiers_options_(
            'PRICE_ALERT', actions, [], UN.UNNotificationCategoryOptionCustomDismissAction)
        self.center.setNotificationCategories_(Foundation.NSSet.setWithObject_(category))
        self.refresh()

    def bind(self, engine, loop):
        with self.lock:
            self.engine, self.loop = engine, loop
            pending, self.pending_close = self.pending_close, []
        for event_id in pending:
            self.acknowledge(event_id)
        if self.shutdown_requested:
            self.stop()

    def stop(self):
        self.shutdown_requested = True
        if self.loop:
            def cancel_serve():
                for task in asyncio.all_tasks(self.loop):
                    if task.get_coro().__qualname__ == 'run':
                        task.cancel()
            self.loop.call_soon_threadsafe(cancel_serve)

    def open_workbench(self):
        AppHelper.callAfter(self._ready)

    def _ready(self):
        self.ready = True
        webbrowser.open(self.url + ('/#alert=' + self.pending_open if self.pending_open else ''))
        self.pending_open = None

    def open_event(self, event_id):
        if self.ready:
            webbrowser.open(self.url + '/#alert=' + event_id)
        else:
            self.pending_open = event_id

    def status(self):
        with self.lock:
            return dict(self.value)

    def set_error(self, error):
        with self.lock:
            self.value['error'] = error
        if error:
            log.warning('%s', error)

    def refresh(self):
        def received(settings):
            names = {0: 'not_determined', 1: 'denied', 2: 'authorized', 3: 'provisional', 4: 'ephemeral'}
            with self.lock:
                self.value.update(authorization=names.get(settings.authorizationStatus(), 'unknown'),
                                  sound=settings.soundSetting() == UN.UNNotificationSettingEnabled,
                                  alerts=settings.alertSetting() == UN.UNNotificationSettingEnabled)
        self.center.getNotificationSettingsWithCompletionHandler_(received)

    def request_settings(self, open_settings=True):
        AppHelper.callAfter(self._request_settings, open_settings)

    def _request_settings(self, open_settings):
        if self.status()['authorization'] == 'not_determined':
            def completed(granted, error):
                if error:
                    self.set_error('Notification permission request failed: ' + error.localizedDescription())
                AppHelper.callAfter(self.refresh)
            self.center.requestAuthorizationWithOptions_completionHandler_(UN.UNAuthorizationOptionAlert | UN.UNAuthorizationOptionSound, completed)
        elif open_settings:
            AppKit.NSWorkspace.sharedWorkspace().openURL_(Foundation.NSURL.URLWithString_('x-apple.systempreferences:com.apple.Notifications-Settings.extension'))
            self.refresh()

    def send(self, event):
        AppHelper.callAfter(self._send, event)

    def _send(self, event):
        self.refresh()
        content = UN.UNMutableNotificationContent.alloc().init()
        arrow = '↑─' if event['direction'] == 'up' else '↓─'
        content.setTitle_(f"{event['symbol'].removesuffix('.US')}  {arrow}  {event['price_cents'] / 100:.2f}")
        stamp = datetime.fromtimestamp(event['quote_time'], ET).strftime('%Y-%m-%d %H:%M:%S ET')
        content.setBody_(stamp)
        content.setCategoryIdentifier_('PRICE_ALERT')
        content.setSound_(UN.UNNotificationSound.soundNamed_(event['direction'] + '.wav'))
        content.setUserInfo_({'event_id': event['id']})
        request = UN.UNNotificationRequest.requestWithIdentifier_content_trigger_(event['id'], content, None)
        def completed(error):
            if error:
                self.set_error('Notification delivery failed: ' + error.localizedDescription())
            else:
                self.set_error(None)
        self.center.addNotificationRequest_withCompletionHandler_(request, completed)

    def remove(self, event_id):
        AppHelper.callAfter(self.center.removeDeliveredNotificationsWithIdentifiers_, [event_id])
        AppHelper.callAfter(self.center.removePendingNotificationRequestsWithIdentifiers_, [event_id])

    def acknowledge(self, event_id):
        def perform():
            try:
                self.engine.acknowledge(event_id)
            except Exception:
                self.set_error('Could not close alert; please close it in Workbench')
                log.exception('Native alert close failed')
        with self.lock:
            if not self.loop or not self.engine:
                self.pending_close.append(event_id)
                return
            loop = self.loop
        loop.call_soon_threadsafe(perform)
