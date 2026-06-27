import sqlite3
import os
from datetime import datetime

path = os.path.abspath("netpulse.db")
conn = sqlite3.connect(path)
cur = conn.cursor()
cur.execute(
    "INSERT INTO alert (severity, message, created_at, resolved) VALUES (?, ?, ?, ?)",
    (
        "critical",
        "Simulated high-latency alert created for UI verification.",
        datetime.utcnow().isoformat(),
        0,
    ),
)
conn.commit()
print("INSERTED", cur.lastrowid)
conn.close()
