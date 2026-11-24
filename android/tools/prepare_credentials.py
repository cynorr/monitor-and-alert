#!/usr/bin/env python3
"""User-authorized private APK defaults. Never print secrets or include account_1 / Schwab."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def main():
    source=json.loads((ROOT/'config/credentials.json').read_text())
    account=next(a for a in source['longbridge']['accounts'] if a['id']=='account_2')
    value={'longbridge':{'accounts':[{k:account[k] for k in ('id','app_key','app_secret','access_token')}]},'massive':{'api_key':source['massive']['api_key']}}
    path=ROOT/'android/app/src/main/assets/provision.json'
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as f:
        json.dump(value,f)
    print('Private APK defaults prepared: account_2 + Massive only; values hidden.')

if __name__=='__main__':
    main()
