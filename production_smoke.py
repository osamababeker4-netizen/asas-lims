#!/usr/bin/env python3
import json
import time
import urllib.error
import urllib.request

API='https://asas-lims-api.onrender.com'
ORIGIN='https://osamababeker4-netizen.github.io'

def request(req, attempts=6):
    last=None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, dict(response.headers), response.read()
        except Exception as error:
            last=error
            if i+1<attempts:
                time.sleep(min(20, 3*(i+1)))
    raise last

status, headers, body = request(urllib.request.Request(API+'/api/health', headers={'User-Agent':'ASAS-LIMS-Acceptance/10.2.17'}))
payload=json.loads(body.decode('utf-8'))
assert status == 200, (status, payload)
assert payload.get('status') == 'ok', payload
assert payload.get('database') == 'ready', payload
assert payload.get('service') == 'asas-lims', payload

preflight=urllib.request.Request(
    API+'/api/auth/login',
    method='OPTIONS',
    headers={
        'Origin': ORIGIN,
        'Access-Control-Request-Method':'POST',
        'Access-Control-Request-Headers':'content-type,authorization',
        'User-Agent':'ASAS-LIMS-Acceptance/10.2.17'
    }
)
status, headers, body = request(preflight)
assert status == 204, status
assert headers.get('Access-Control-Allow-Origin') == ORIGIN, headers
print(json.dumps({'production_api':'pass','database':'ready','cors':'pass','version':payload.get('version')}, ensure_ascii=False))
