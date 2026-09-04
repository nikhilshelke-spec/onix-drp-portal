import os
import json
import secrets
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ACCESS_FILE = os.path.join(DATA_DIR, "access_control.json")

OWNER_EMAIL = "nikhil.shelke@onixnet.com"
ALLOWED_EMPLOYEE_DOMAINS = ["@onixnet.com", "@onixnet.us"]
EMPLOYEE_ACCESS_TOKEN = "emp-onix-drp-2026"

def _load():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(ACCESS_FILE):
        _save({"leaders": {}, "editors": {}, "employee_token": EMPLOYEE_ACCESS_TOKEN})
    with open(ACCESS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if "editors" not in data:
            data["editors"] = {}
        if "leaders" not in data:
            data["leaders"] = {}
        return data

def _save(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ACCESS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def get_employee_token():
    data = _load()
    return data.get("employee_token", EMPLOYEE_ACCESS_TOKEN)

# ─── EDITOR (Full Access / Email Dispatcher) ─────────────────────────────────

def add_editor(email):
    email = email.strip().lower()
    data = _load()
    editors = data.get("editors", {})
    for token, info in editors.items():
        if info.get("email") == email:
            return token
    token = secrets.token_urlsafe(20)
    editors[token] = {
        "email": email,
        "role": "editor",
        "added_at": datetime.now().isoformat(),
        "added_by": OWNER_EMAIL
    }
    data["editors"] = editors
    _save(data)
    return token

def remove_editor(email):
    email = email.strip().lower()
    data = _load()
    editors = data.get("editors", {})
    to_remove = [tok for tok, info in editors.items() if info.get("email") == email]
    for tok in to_remove:
        del editors[tok]
    data["editors"] = editors
    _save(data)

def get_all_editors():
    data = _load()
    return [
        {"email": info["email"], "token": tok, "added_at": info.get("added_at", "")}
        for tok, info in data.get("editors", {}).items()
    ]

def validate_editor_token(token):
    data = _load()
    info = data.get("editors", {}).get(token)
    if info:
        return info.get("email")
    return None

# ─── LEADER (Executive / View-Only Emails) ───────────────────────────────────

def add_leader(email):
    email = email.strip().lower()
    data = _load()
    leaders = data.get("leaders", {})
    for token, info in leaders.items():
        if info.get("email") == email:
            return token
    token = secrets.token_urlsafe(20)
    leaders[token] = {
        "email": email,
        "role": "leader",
        "added_at": datetime.now().isoformat(),
        "added_by": OWNER_EMAIL
    }
    data["leaders"] = leaders
    _save(data)
    return token

def remove_leader(email):
    email = email.strip().lower()
    data = _load()
    leaders = data.get("leaders", {})
    to_remove = [tok for tok, info in leaders.items() if info.get("email") == email]
    for tok in to_remove:
        del leaders[tok]
    data["leaders"] = leaders
    _save(data)

def get_all_leaders():
    data = _load()
    return [
        {"email": info["email"], "token": tok, "added_at": info.get("added_at", "")}
        for tok, info in data.get("leaders", {}).items()
    ]

def validate_leader_token(token):
    data = _load()
    info = data.get("leaders", {}).get(token)
    if info:
        return info.get("email")
    return None

# ─── EMPLOYEE (Directory & Action Plan) ───────────────────────────────────────

def validate_employee_token(token):
    return token == get_employee_token()

def is_allowed_employee_domain(email):
    email_lower = email.strip().lower()
    return any(email_lower.endswith(domain) for domain in ALLOWED_EMPLOYEE_DOMAINS)
