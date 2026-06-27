import http.client
import json
import subprocess

try:
    conn = http.client.HTTPConnection('127.0.0.1', 8000, timeout=10)
    conn.request('GET', '/api/devices/')
    resp = conn.getresponse()
    body = resp.read().decode()
    data = json.loads(body)
    ips = [d['ip_address'] for d in data[:20]]
    print('sample_count=', len(ips))
    for ip in ips:
        try:
            p = subprocess.run(['ping', '-n', '1', ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
            ok = p.returncode == 0
            print(ip, 'reachable' if ok else 'unreachable')
        except Exception as e:
            print(ip, 'error', str(e))
    conn.close()
except Exception as e:
    print('failed to fetch devices:', e)
