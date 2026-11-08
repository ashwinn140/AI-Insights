"""Independent AI Insights authentication, isolated on its own persistent volume."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

DB = Path(os.environ.get("AI_AUTH_DB", "/ai-data/auth.sqlite3"))
COMPANIES = {"NG", "NCS"}
LOBS = {"AE", "AI", "OE", "OI"}

def connection():
    DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB), timeout=10)
    db.row_factory = sqlite3.Row
    return db

def initialize():
    with connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL, password_hash TEXT NOT NULL,
            companies TEXT NOT NULL, lobs TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            failed INTEGER NOT NULL DEFAULT 0, locked_until INTEGER NOT NULL DEFAULT 0
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
            expires_at INTEGER NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY, event TEXT NOT NULL, user_id INTEGER,
            created_at INTEGER NOT NULL
        )""")

def password_hash(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return salt.hex() + ":" + key.hex()

def password_valid(password, stored):
    try:
        salt, expected = stored.split(":", 1)
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False

def bootstrap_status():
    """Diagnostic status only: never disclose email, password, or password length."""
    email = os.getenv("AI_BOOTSTRAP_EMAIL", "").strip().lower()
    password = os.getenv("AI_BOOTSTRAP_PASSWORD", "")
    with connection() as db:
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return "existing_account"
    if not email or "@" not in email:
        return "missing_or_invalid_bootstrap_email"
    if len(password) < 14:
        return "bootstrap_password_below_minimum_14_characters"
    return "ready"

def provision_initial_admin():
    """One-time bootstrap only, from private Railway variables, never HTTP."""
    email = os.getenv("AI_BOOTSTRAP_EMAIL", "").strip().lower()
    password = os.getenv("AI_BOOTSTRAP_PASSWORD", "")
    if not email or len(password) < 14 or "@" not in email:
        return False
    with connection() as db:
        if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return False
        db.execute("""INSERT INTO users
            (email,name,password_hash,companies,lobs)
            VALUES (?,?,?,?,?)""",
            (email, "AI Insights Administrator", password_hash(password),
             "NG,NCS", "AE,AI,OE,OI"))
        db.execute("INSERT INTO audit(event,created_at) VALUES (?,?)",
                   ("bootstrap_admin", int(time.time())))
    return True

def authenticate(email, password):
    email = (email or "").strip().lower()
    now = int(time.time())
    with connection() as db:
        user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user or not user["active"] or user["locked_until"] > now:
            # Constant-cost unknown-user check
            hashlib.scrypt(b"dummy", salt=b"0"*16, n=2**14, r=8, p=1)
            return None
        if not password_valid(password, user["password_hash"]):
            fails = user["failed"] + 1
            db.execute("UPDATE users SET failed=?,locked_until=? WHERE id=?",
                       (fails, now+900 if fails >= 5 else 0, user["id"]))
            return None
        db.execute("UPDATE users SET failed=0,locked_until=0 WHERE id=?", (user["id"],))
        raw = secrets.token_urlsafe(40)
        db.execute("DELETE FROM sessions WHERE expires_at<?", (now,))
        db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (?,?,?)",
                   (hashlib.sha256(raw.encode()).hexdigest(), user["id"], now+12*3600))
        db.execute("INSERT INTO audit(event,user_id,created_at) VALUES (?,?,?)",
                   ("login", user["id"], now))
        return raw

def session_user(token):
    if not token:
        return None
    with connection() as db:
        row = db.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=? AND s.expires_at>? AND u.active=1""",
            (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if not row:
            return None
        companies = set(row["companies"].split(",")) & COMPANIES
        lobs = set(row["lobs"].split(",")) & LOBS
        if not companies or not lobs:
            return None
        return {"id":row["id"],"email":row["email"],"name":row["name"],
                "companies":sorted(companies),"lobs":sorted(lobs)}

def logout(token):
    if token:
        with connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?",
                       (hashlib.sha256(token.encode()).hexdigest(),))
