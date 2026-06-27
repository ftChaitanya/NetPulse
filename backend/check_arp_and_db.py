import subprocess
import sqlite3
from pathlib import Path

print('ARP output:')
try:
    out = subprocess.check_output(['arp', '-a'], text=True, stderr=subprocess.STDOUT)
    print(out)
except Exception as e:
    print('arp error', repr(e))

print('--- DB rows ---')
if Path('netpulse.db').exists():
    conn = sqlite3.connect('netpulse.db')
    cur = conn.cursor()
    try:
        for row in cur.execute('SELECT id, ip_address, mac_address, vendor, hostname, status FROM device LIMIT 20'):
            print(row)
    except Exception as e:
        print('db error', repr(e))
    conn.close()
else:
    print('DB missing')
