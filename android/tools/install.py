#!/usr/bin/env python3
"""Install this Android-only prototype and provision only account_2 + Massive over adb stdin."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PACKAGE='com.cyno.marketmonitor'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--serial')
    parser.add_argument('--apk',type=Path,default=ROOT/'android/app/build/outputs/apk/debug/app-debug.apk')
    parser.add_argument('--credentials',type=Path,default=ROOT/'config/credentials.json')
    args=parser.parse_args()
    adb=shutil.which('adb') or str(Path.home()/'Library/Android/sdk/platform-tools/adb')
    devices=subprocess.check_output([adb,'devices'],text=True).splitlines()[1:]
    connected=[line.split()[0] for line in devices if line.strip().endswith('\tdevice')]
    serial=args.serial or (connected[0] if len(connected)==1 else None)
    if not serial or serial not in connected:
        raise SystemExit('Connect one Android device and allow USB debugging, or pass --serial.')
    if not args.apk.is_file():
        raise SystemExit('Build the APK first: android/tools/build.sh')
    # Do not print credentials, write a host staging file, or package them into the APK.
    try:
        source=json.loads(args.credentials.read_text())
        account=next(item for item in source['longbridge']['accounts'] if item['id']=='account_2')
        selected={'longbridge':{'accounts':[{key:account[key] for key in ('id','app_key','app_secret','access_token')}]},'massive':{'api_key':source['massive']['api_key']}}
        payload=json.dumps(selected).encode()
    except (OSError,ValueError,KeyError,StopIteration):
        raise SystemExit('Account 2 or Massive credentials are unavailable.') from None
    base=[adb,'-s',serial]
    subprocess.run(base+['install','--no-incremental','-r',str(args.apk)],check=True)
    subprocess.run(base+['shell','am','force-stop',PACKAGE],check=True)
    subprocess.run(base+['shell','run-as',PACKAGE,'mkdir','-p','files'],check=True)
    subprocess.run(base+['exec-in','run-as',PACKAGE,'tee','files/provision.json'],input=payload,stdout=subprocess.DEVNULL,check=True)
    subprocess.run(base+['shell','am','start','-n',PACKAGE+'/.MainActivity'],check=True)
    print('Installed. Account 2 + Massive provisioned privately; Mac service unchanged.')

if __name__=='__main__':
    main()
