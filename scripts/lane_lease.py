"""Reserve a durable lane before dispatch. An uncertain write is read back."""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from five_minute_handoff import LANES, TITLE, ACTIVE, parse_slot, choose_lane

REPO='dulnasavin/Repository-name-crypto-tracker-Private-Yes'


def contents(lane, method='GET', payload=None):
    path='https://api.github.com/repos/'+REPO+'/contents/five_minute/lanes/'+lane+'.json'
    if method=='GET':
        path+='?ref=runtime-data'
    request=urllib.request.Request(path,method=method,
        data=json.dumps(payload).encode() if payload else None,
        headers={'Authorization':'Bearer '+os.environ['PRIVATE_DATA_TOKEN'],
                 'Accept':'application/vnd.github+json','Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=15) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if method=='GET' and error.code==404:
            return None
        raise


def saved(lane):
    item=contents(lane)
    return (json.loads(base64.b64decode(item['content'])),item['sha']) if item else (None,None)


def reserve(runs,slot,owner,now):
    augmented={'workflow_runs':list(runs['workflow_runs'])}
    states={}
    for lane in LANES:
        previous,sha=saved(lane)
        states[lane]=sha
        if not previous:
            continue
        prior=parse_slot(previous['slot_utc'])
        if previous['slot_utc']==slot and previous['dispatcher_run_id']==owner:
            return lane
        completed=any(run['status']=='completed' and
            run.get('display_title')==f"Crypto Logger | {lane} | {previous['slot_utc']}"
            for run in runs['workflow_runs'])
        # Collector startup rejects stale slots and rechecks ownership. An
        # active Actions run independently holds the lane after this timeout.
        if not completed and now < prior+timedelta(minutes=20):
            augmented['workflow_runs'].append({'status':'pending',
                'display_title':f"Crypto Logger | {lane} | {previous['slot_utc']}"})
    lane=choose_lane(augmented,slot)
    claim={'lane':lane,'slot_utc':slot,'dispatcher_run_id':owner}
    payload={'message':f'Reserve {lane} for {slot}','branch':'runtime-data',
             'content':base64.b64encode(json.dumps(claim).encode()).decode()}
    if states[lane]:
        payload['sha']=states[lane]
    try:
        contents(lane,'PUT',payload)
    except (OSError,TimeoutError):
        if saved(lane)[0]!=claim:
            raise
    if saved(lane)[0]!=claim:
        raise ValueError('Lane ownership changed before dispatch')
    return lane


if __name__=='__main__':
    slot=os.environ['SLOT_UTC']
    now=datetime.now(timezone.utc)
    if sys.argv[1]=='reserve':
        print(reserve(json.loads(Path(sys.argv[2]).read_text()),slot,os.environ['GITHUB_RUN_ID'],now))
    else:
        lane=os.environ['LANE']
        if lane not in LANES or saved(lane)[0]!={'lane':lane,'slot_utc':slot,
                'dispatcher_run_id':os.environ['CLAIM_RUN_ID']}:
            raise ValueError('Lane lease is owned by another slot')
        if now >= parse_slot(slot)+timedelta(minutes=5):
            raise ValueError('Expired slot, record as missed')
