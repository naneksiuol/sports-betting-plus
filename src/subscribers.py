import json
from pathlib import Path

SUBSCRIBERS_FILE = Path(__file__).parent.parent / "data" / "subscribers.json"


def load_subscribers() -> list[str]:
    if not SUBSCRIBERS_FILE.exists():
        return []
    try:
        return json.loads(SUBSCRIBERS_FILE.read_text())
    except Exception:
        return []


def save_subscribers(emails: list[str]):
    SUBSCRIBERS_FILE.write_text(json.dumps(sorted(set(emails)), indent=2))


def add_subscriber(email: str) -> tuple[bool, str]:
    email = email.strip().lower()
    if not email or "@" not in email:
        return False, "Invalid email address."
    subs = load_subscribers()
    if email in subs:
        return False, f"{email} is already subscribed."
    subs.append(email)
    save_subscribers(subs)
    return True, f"✅ {email} added."


def remove_subscriber(email: str) -> tuple[bool, str]:
    subs = load_subscribers()
    if email not in subs:
        return False, f"{email} not found."
    subs.remove(email)
    save_subscribers(subs)
    return True, f"🗑️ {email} removed."
