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
        columns = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
        if "role" not in columns:
            db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer'")
        db.execute("""CREATE TABLE IF NOT EXISTS classifications (
            id INTEGER PRIMARY KEY, company_name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            industry TEXT NOT NULL, confidence TEXT NOT NULL, source TEXT NOT NULL,
            approved INTEGER NOT NULL DEFAULT 0, updated_by INTEGER,
            updated_at INTEGER NOT NULL
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
        db.execute("UPDATE users SET role='admin' WHERE email=?", (email,))
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
                "companies":sorted(companies),"lobs":sorted(lobs), "role":row["role"]}

def logout(token):
    if token:
        with connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?",
                       (hashlib.sha256(token.encode()).hexdigest(),))

def ensure_bootstrap_admin_role():
    """One-time migration of original sole bootstrap user; no privilege escalation on later users."""
    email = os.getenv("AI_BOOTSTRAP_EMAIL", "").strip().lower()
    if not email:
        return
    with connection() as db:
        rows = db.execute("SELECT id,email,role FROM users LIMIT 2").fetchall()
        if len(rows)==1 and rows[0]["email"]==email and rows[0]["role"]=="viewer":
            db.execute("UPDATE users SET role='admin' WHERE id=?", (rows[0]["id"],))

def list_users():
    with connection() as db:
        return [dict(id=r["id"],email=r["email"],name=r["name"],role=r["role"],
                     companies=r["companies"].split(","),lobs=r["lobs"].split(","),
                     active=bool(r["active"])) for r in db.execute(
            "SELECT id,email,name,role,companies,lobs,active FROM users ORDER BY id")]

def add_user(actor, email, name, password, role, companies, lobs):
    import re
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\\s]+@[^@\\s]+\\.[^@\\s]+", email) or len(email)>254:
        raise ValueError("Invalid email")
    if not 14<=len(password)<=256:
        raise ValueError("Password must contain 14 to 256 characters")
    if role not in ("admin","viewer"):
        raise ValueError("Invalid role")
    if not companies or not lobs or not set(companies)<=COMPANIES or not set(lobs)<=LOBS:
        raise ValueError("Invalid company/department permissions")
    with connection() as db:
        try:
            cursor=db.execute("""INSERT INTO users(email,name,password_hash,role,companies,lobs)
                VALUES (?,?,?,?,?,?)""",(email,name[:100],password_hash(password),role,
                ",".join(sorted(set(companies))),",".join(sorted(set(lobs)))))
        except sqlite3.IntegrityError:
            raise ValueError("Email already exists")
        db.execute("INSERT INTO audit(event,user_id,created_at) VALUES (?,?,?)",
                   ("user_created_by_"+str(actor),cursor.lastrowid,int(time.time())))
        return cursor.lastrowid

def edit_user(actor, uid, active=None, companies=None, lobs=None, role=None):
    with connection() as db:
        user=db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        if not user:
            raise ValueError("User not found")
        if uid==actor and (active is False or role=="viewer"):
            raise ValueError("Cannot revoke your own administrator access")
        if role is not None and role not in ("admin","viewer"):
            raise ValueError("Invalid role")
        if companies is not None and (not companies or not set(companies)<=COMPANIES):
            raise ValueError("Invalid companies")
        if lobs is not None and (not lobs or not set(lobs)<=LOBS):
            raise ValueError("Invalid departments")
        newrole=role if role is not None else user["role"]
        newactive=int(active) if active is not None else user["active"]
        if user["role"]=="admin" and (newrole!="admin" or not newactive):
            count=db.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
            if count<=1:
                raise ValueError("Cannot disable the last administrator")
        db.execute("""UPDATE users SET role=?,active=?,companies=?,lobs=? WHERE id=?""",
                   (newrole,newactive,
                    ",".join(sorted(set(companies))) if companies is not None else user["companies"],
                    ",".join(sorted(set(lobs))) if lobs is not None else user["lobs"],uid))
        db.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
        db.execute("INSERT INTO audit(event,user_id,created_at) VALUES (?,?,?)",
                   ("user_updated_by_"+str(actor),uid,int(time.time())))

def reset_password(actor, uid, password):
    if not 14<=len(password)<=256:
        raise ValueError("Password must contain 14 to 256 characters")
    with connection() as db:
        if not db.execute("SELECT 1 FROM users WHERE id=?",(uid,)).fetchone():
            raise ValueError("User not found")
        db.execute("UPDATE users SET password_hash=?,failed=0,locked_until=0 WHERE id=?",
                   (password_hash(password),uid))
        db.execute("DELETE FROM sessions WHERE user_id=?",(uid,))
        db.execute("INSERT INTO audit(event,user_id,created_at) VALUES (?,?,?)",
                   ("password_reset_by_"+str(actor),uid,int(time.time())))

def audit_events(limit=100):
    with connection() as db:
        return [dict(r) for r in db.execute(
            "SELECT event,user_id,created_at FROM audit ORDER BY id DESC LIMIT ?",(min(limit,200),))]

def classification_list(term="",limit=200):
    term=(term or "").strip()
    with connection() as db:
        return [dict(r) for r in db.execute("""SELECT id,company_name,industry,confidence,source,
            approved,updated_at FROM classifications
            WHERE company_name LIKE ? ORDER BY company_name LIMIT ?""",
            ("%"+term+"%",min(limit,500)))]

def classification_save(actor,company_name,industry,confidence,source,approved):
    company_name=company_name.strip()
    industry=industry.strip()
    source=source.strip()
    if not 2<=len(company_name)<=200 or not 2<=len(industry)<=100 or not 3<=len(source)<=500:
        raise ValueError("Company, industry and evidence source are required")
    if confidence not in ("low","medium","high"):
        raise ValueError("Invalid confidence")
    with connection() as db:
        previous=db.execute("SELECT approved FROM classifications WHERE company_name=? COLLATE NOCASE",
                            (company_name,)).fetchone()
        if previous and previous["approved"] and not approved:
            raise ValueError("Approved classifications cannot be downgraded without explicit review")
        db.execute("""INSERT INTO classifications
            (company_name,industry,confidence,source,approved,updated_by,updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(company_name) DO UPDATE SET industry=excluded.industry,
                confidence=excluded.confidence,source=excluded.source,approved=excluded.approved,
                updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
            (company_name,industry,confidence,source,int(bool(approved)),actor,int(time.time())))
        db.execute("INSERT INTO audit(event,user_id,created_at) VALUES (?,?,?)",
                   ("classification_saved_by_"+str(actor),actor,int(time.time())))
