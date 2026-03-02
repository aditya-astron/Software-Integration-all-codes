import os, sqlite3, time, json, threading

DB_PATH = os.getenv("OFFLINE_DB", "/app/spool/telemetry_queue.db")
_LOCK = threading.Lock()

def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.execute("""
      CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        payload TEXT NOT NULL,
        ts INTEGER NOT NULL,
        sent INTEGER NOT NULL DEFAULT 0
      )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_sent ON queue(sent, id)")
    c.commit()
    return c

_CONN = _conn()

def enqueue(topic: str, payload: dict):
    row = (topic, json.dumps(payload, separators=(",", ":")), int(time.time() * 1000))
    with _LOCK:
        _CONN.execute("INSERT INTO queue(topic, payload, ts, sent) VALUES(?,?,?,0)", row)
        _CONN.commit()

def fetch_unsent(limit=500):
    with _LOCK:
        cur = _CONN.execute(
            "SELECT id, topic, payload, ts FROM queue WHERE sent=0 ORDER BY id ASC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()

def mark_sent(ids):
    if not ids:
        return
    with _LOCK:
        _CONN.executemany("UPDATE queue SET sent=1 WHERE id=?", [(i,) for i in ids])
        _CONN.commit()

def backlog_count():
    with _LOCK:
        cur = _CONN.execute("SELECT COUNT(*) FROM queue WHERE sent=0")
        return cur.fetchone()[0]
