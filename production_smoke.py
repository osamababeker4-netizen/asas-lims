#!/usr/bin/env python3
import json
import os
import time
import urllib.request

API='https://asas-lims-api.onrender.com'
PAGES='https://osamababeker4-netizen.github.io/asas-lims/'
ORIGIN='https://osamababeker4-netizen.github.io'
EXPECTED_VERSION='10.4.0-operational-workspace'
STRICT_PRODUCTION=os.environ.get('GITHUB_REF') == 'refs/heads/main'

def once(req):
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.status, dict(response.headers), response.read()

def retry(check, attempts=18, delay=10):
    last=None
    for i in range(attempts):
        try:
            value=check()
            if value is not None:
                return value
        except Exception as error:
            last=error
        if i+1<attempts:
            time.sleep(delay)
    if last:
        raise last
    raise AssertionError('production acceptance timed out')

def health_check():
    status, headers, body=once(urllib.request.Request(API+'/api/health', headers={'User-Agent':'ASAS-LIMS-Acceptance/10.4.0'}))
    payload=json.loads(body.decode('utf-8'))
    if status != 200 or payload.get('status') != 'ok' or payload.get('database') != 'ready' or payload.get('service') != 'asas-lims':
        return None
    if STRICT_PRODUCTION and payload.get('version') != EXPECTED_VERSION:
        return None
    return payload

payload=retry(health_check)

preflight=urllib.request.Request(
    API+'/api/auth/login',
    method='OPTIONS',
    headers={
        'Origin': ORIGIN,
        'Access-Control-Request-Method':'POST',
        'Access-Control-Request-Headers':'content-type,authorization',
        'User-Agent':'ASAS-LIMS-Acceptance/10.4.0'
    }
)
status, headers, body=once(preflight)
cors_headers={str(k).lower():v for k,v in headers.items()}
assert status == 204, status
assert cors_headers.get('access-control-allow-origin') == ORIGIN, headers

pages_state='not-required-on-pr'
if STRICT_PRODUCTION:
    def pages_check():
        status, headers, body=once(urllib.request.Request(PAGES, headers={'Cache-Control':'no-cache','User-Agent':'ASAS-LIMS-Acceptance/10.4.0'}))
        text=body.decode('utf-8','replace')
        if status == 200 and 'مساحة العمل التنفيذية' in text and '10-4-1-login-label' in text:
            return 'current'
        return None
    pages_state=retry(pages_check)

print(json.dumps({
    'production_api':'pass',
    'database':'ready',
    'cors':'pass',
    'version':payload.get('version'),
    'pages':pages_state,
    'strict_production':STRICT_PRODUCTION
}, ensure_ascii=False))
