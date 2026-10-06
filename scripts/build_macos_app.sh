#!/bin/zsh
set -eu
cd "$(dirname "$0")/.."
npm run build --prefix ui
cd macos
../.venv/bin/python setup.py py2app --alias --dist-dir ../dist
cd ..
rm -f 'dist/Market Monitor.app/Contents/Resources/up.wav' 'dist/Market Monitor.app/Contents/Resources/down.wav'
cp macos/sounds/up.wav macos/sounds/down.wav 'dist/Market Monitor.app/Contents/Resources/'
codesign --force --sign - --identifier local.cyno.MarketMonitor --requirements '=designated => identifier "local.cyno.MarketMonitor"' 'dist/Market Monitor.app'
