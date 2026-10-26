"""Transactional local queue and attempt budget; no secrets in SQLite."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3

from .summary import local_time


class Outbox:
    def __init__(self, root):
        self.path = Path(root) / "state" / "notifications.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, account TEXT NOT NULL,
                    day TEXT NOT NULL, destination TEXT NOT NULL,
                    title TEXT NOT NULL, content TEXT NOT NULL, created REAL NOT NULL,
                    expires REAL NOT NULL, ready REAL NOT NULL, state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, reason TEXT NOT NULL DEFAULT '',
                    short_code TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS attempts (day TEXT PRIMARY KEY, count INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS control (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(str(self.path), timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, key, kind, account, destination, message, now, expires):
        with self.connect() as db:
            cursor = db.execute("""INSERT INTO messages
                (id,kind,account,day,destination,title,content,created,expires,ready,state)
                VALUES(?,?,?,?,?,?,?,?,?,?,'pending') ON CONFLICT(id) DO UPDATE SET
                destination=excluded.destination,title=excluded.title,content=excluded.content,
                created=excluded.created,expires=excluded.expires,ready=excluded.ready,state='pending',reason=''
                WHERE messages.state='rebuild' AND messages.attempts=0""",
                (key, kind, account, message["day"], destination, message["title"],
                 message["content"], now, expires, now))
            return cursor.rowcount == 1

    def contains(self, key):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM messages WHERE id=? AND state<>'rebuild'", (key,)).fetchone() is not None

    def control(self, key):
        with self.connect() as db:
            row = db.execute("SELECT value FROM control WHERE key=?", (key,)).fetchone()
            return row[0] if row else ""

    def set_control(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO control VALUES(?,?)", (key, str(value)))

    def maintain(self, now, destination, account, enabled):
        # Called only under the root dispatcher lease; an active POST cannot be misclassified.
        with self.connect() as db:
            db.execute("UPDATE messages SET state='unknown',reason=? WHERE state='submitting'",
                       ("上次提交中断，结果未知；不会自动重发",))
            db.execute("UPDATE messages SET state='expired',reason='消息已过期' WHERE state IN ('pending','rebuild') AND expires<=?", (now,))
            # Before the first POST, a privacy/destination change can safely rebuild
            # today's payload from a fresh query. Already attempted reports remain deduplicated.
            db.execute("""UPDATE messages SET state='rebuild',reason='配置变化，待重新核验'
                WHERE state='pending' AND kind='daily' AND attempts=0 AND destination<>?
                AND account=? AND ?=1""", (destination, account, int(enabled)))
            db.execute("""UPDATE messages SET state='superseded',reason='账号、Token 或通知开关已变化'
                WHERE state IN ('pending','rebuild') AND ((destination<>? AND state<>'rebuild') OR
                (kind='daily' AND (account<>? OR ?=0)))""", (destination, account, int(enabled)))
            db.execute("UPDATE messages SET content='' WHERE created<? AND state NOT IN ('pending','rebuild')", (now - 7 * 86400,))
            db.execute("DELETE FROM attempts WHERE day<?", (local_time(now - 400 * 86400).date().isoformat(),))

    def claim(self, now, *, kind=None):
        day = local_time(now).date().isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT * FROM messages WHERE state='pending' AND ready<=? AND expires>?
                AND (? IS NULL OR kind=?) ORDER BY created LIMIT 1""", (now, now, kind, kind)).fetchone()
            if row is None:
                return None
            count = db.execute("SELECT count FROM attempts WHERE day=?", (day,)).fetchone()
            if count and count[0] >= 100:
                db.execute("UPDATE messages SET state='failed',reason='本机每日发送尝试已达100次' WHERE id=?", (row["id"],))
                return None
            last = db.execute("SELECT value FROM control WHERE key='last_attempt'").fetchone()
            if last and now - float(last[0]) < 30:
                return None
            db.execute("INSERT INTO attempts VALUES(?,1) ON CONFLICT(day) DO UPDATE SET count=count+1", (day,))
            db.execute("INSERT OR REPLACE INTO control VALUES('last_attempt',?)", (str(now),))
            db.execute("UPDATE messages SET state='submitting',attempts=attempts+1 WHERE id=?", (row["id"],))
            return {**dict(row), "attempts": row["attempts"] + 1}

    def finish(self, message, outcome, now):
        state, ready = outcome["state"], now
        if state == "retry":
            delay = 60 if message["attempts"] == 1 else 300
            state = "pending" if message["attempts"] < 3 and now + delay < message["expires"] else "failed"
            ready = now + delay
        with self.connect() as db:
            db.execute("UPDATE messages SET state=?,ready=?,reason=?,short_code=? WHERE id=?",
                       (state, ready, outcome["reason"], outcome.get("short_code", ""), message["id"]))
            if outcome.get("blocked"):
                db.execute("INSERT OR REPLACE INTO control VALUES('blocked',?)", (outcome["reason"],))

    def clear_pending(self):
        with self.connect() as db:
            db.execute("UPDATE messages SET state='superseded',reason='用户清空待发消息' WHERE state IN ('pending','rebuild')")

    def status(self, now):
        with self.connect() as db:
            rows = db.execute("SELECT kind,day,title,state,attempts,reason,short_code,created FROM messages ORDER BY created DESC LIMIT 5").fetchall()
            count = db.execute("SELECT count FROM attempts WHERE day=?", (local_time(now).date().isoformat(),)).fetchone()
            pending = db.execute("SELECT count(*) FROM messages WHERE state IN ('pending','rebuild')").fetchone()[0]
        return {"recent": [dict(row) for row in rows], "attempts_today": count[0] if count else 0,
                "pending": pending, "blocked": self.control("blocked")}
