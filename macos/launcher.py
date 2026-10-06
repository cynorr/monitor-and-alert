"""One Python process: Cocoa on main, existing Workbench asyncio loop on a thread."""
from pathlib import Path
import asyncio
import logging
import locale
import os
import threading
import webbrowser
import sys
import objc
import time
import signal

import AppKit
import Foundation
from PyObjCTools import AppHelper

PROJECT = Path(Foundation.NSBundle.mainBundle().objectForInfoDictionaryKey_('MarketMonitorProjectPath'))
# Finder launch has the C locale; the external workspace/credential labels use UTF-8.
locale.setlocale(locale.LC_CTYPE, 'en_US.UTF-8')
sys.path.insert(0, str(PROJECT))
from data_service.alerts.macos import MacNotifications
from data_service.__main__ import main
URL = 'http://127.0.0.1:8765'
NOTIFICATION_CHECK = '--notification-check' in sys.argv


class AppDelegate(Foundation.NSObject, protocols=[objc.protocolNamed('NSApplicationDelegate')]):
    def applicationDidFinishLaunching_(self, notification):
        self.bridge = MacNotifications(URL)
        self.timer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(5, self, 'refresh:', None, True)
        self.quitting = False
        self.worker = threading.Thread(target=self.serve, name='Workbench')
        self.worker.start()
        self.bridge.request_settings(False)

    def refresh_(self, timer):
        self.bridge.refresh()

    def open_(self, sender):
        webbrowser.open(URL)

    def settings_(self, sender):
        self.bridge.request_settings()

    def quit_(self, sender):
        AppKit.NSApplication.sharedApplication().terminate_(None)

    def applicationShouldTerminate_(self, app):
        if not self.worker.is_alive():
            return AppKit.NSTerminateNow
        self.quitting = True
        self.bridge.stop()
        return AppKit.NSTerminateLater

    def serve(self):
        os.chdir(PROJECT)
        try:
            if NOTIFICATION_CHECK:
                # Bounded native delivery check; never opens credentials, broker or runtime databases.
                for direction in ('up', 'down'):
                    self.bridge.send(dict(id='notification-check-' + direction, direction=direction,
                                          symbol='CHECK.US', price_cents=1000, quote_time=int(time.time())))
                    time.sleep(2)
                def delivered(items):
                    print('Notification check:', self.bridge.status(), 'delivered=', len(items), flush=True)
                    for direction in ('up', 'down'):
                        self.bridge.remove('notification-check-' + direction)
                AppHelper.callAfter(self.bridge.center.getDeliveredNotificationsWithCompletionHandler_, delivered)
                return
            result = main(['serve', '--runtime', str(PROJECT / 'runtime')], notifier=self.bridge)
            if result:
                AppHelper.callAfter(self.failed_, 'Workbench could not start. Check runtime/macos.log; quit any existing service using this runtime.')
        except asyncio.CancelledError:
            pass
        except Exception:
            logging.exception('Workbench stopped')
            AppHelper.callAfter(self.failed_, 'Workbench stopped. Check runtime/macos.log.')
        finally:
            if self.quitting:
                AppHelper.callAfter(AppKit.NSApplication.sharedApplication().replyToApplicationShouldTerminate_, True)

    def failed_(self, message):
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_('Market Monitor')
        alert.setInformativeText_(message)
        alert.runModal()
        AppKit.NSApplication.sharedApplication().terminate_(None)


(PROJECT / 'runtime').mkdir(exist_ok=True)
logging.basicConfig(filename=PROJECT / 'runtime' / 'macos.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
app = AppKit.NSApplication.sharedApplication()
app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
delegate = AppDelegate.alloc().init()
app.setDelegate_(delegate)
menu = AppKit.NSMenu.alloc().init()
item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_('Market Monitor', None, '')
submenu = AppKit.NSMenu.alloc().initWithTitle_('Market Monitor')
for title, action, shortcut in [('Open Workbench', 'open:', 'o'), ('Notification Settings', 'settings:', ''), ('Quit Market Monitor', 'quit:', 'q')]:
    entry = submenu.addItemWithTitle_action_keyEquivalent_(title, action, shortcut)
    entry.setTarget_(delegate)
item.setSubmenu_(submenu)
menu.addItem_(item)
app.setMainMenu_(menu)
signal.signal(signal.SIGTERM, lambda *_: AppHelper.callAfter(app.terminate_, None))
AppHelper.runEventLoop()
