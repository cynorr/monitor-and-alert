"""Local development app: source/runtime remain in the fixed project directory."""
from pathlib import Path
from setuptools import setup

root = Path(__file__).resolve().parents[1]
setup(name='Market Monitor', app=[str(root / 'macos' / 'launcher.py')],
      data_files=[('', [str(p) for p in (root / 'macos' / 'sounds').glob('*.wav')])],
      options={'py2app': {'argv_emulation': False, 'plist': {
          'CFBundleIdentifier': 'local.cyno.MarketMonitor', 'CFBundleName': 'Market Monitor',
          'CFBundleDisplayName': 'Market Monitor', 'CFBundleShortVersionString': '1.0.0',
          'LSMinimumSystemVersion': '26.0', 'MarketMonitorProjectPath': str(root)}}})
