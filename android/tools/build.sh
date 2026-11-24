#!/bin/sh
set -eu
ANDROID_PROJECT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
export JAVA_HOME="${JAVA_HOME:-/Applications/Android Studio.app/Contents/jbr/Contents/Home}"
export GRADLE_USER_HOME="$ANDROID_PROJECT/.tools/gradle-home"
cd "$ANDROID_PROJECT"
if [ ! -f app/src/main/assets/seed.zip ]; then
    ../.venv/bin/python tools/prepare_seed.py
fi
../.venv/bin/python tools/prepare_reference.py
../.venv/bin/python tools/prepare_credentials.py
./gradlew :app:assembleDebug :app:testDebugUnitTest --console=plain "$@"
mkdir -p output
cp app/build/outputs/apk/debug/app-debug.apk output/market-monitor-0.1.0.apk
printf 'APK: %s/output/market-monitor-0.1.0.apk\n' "$ANDROID_PROJECT"
