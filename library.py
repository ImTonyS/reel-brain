"""Everything a user has saved, plus the taste profile computed from it."""
import json
import threading
from collections import Counter
from datetime import date
from pathlib import Path

DB = Path(__file__).parent / "data" / "library.json"
_lock = threading.Lock()


def _load():
    return json.loads(DB.read_text()) if DB.exists() else {}


def _save(db):
    DB.parent.mkdir(exist_ok=True)
    DB.write_text(json.dumps(db, ensure_ascii=False, indent=1))


def entries(user):
    return _load().get(str(user), [])


def add(user, item):
    with _lock:
        db = _load()
        db.setdefault(str(user), []).append(item)
        _save(db)


def vocab(user):
    es = entries(user)
    return {"style_tags": sorted({t for e in es for t in e.get("style_tags", [])}),
            "themes": sorted({t for e in es for t in e.get("themes", [])})}


def count_today(user):
    today = date.today().isoformat()
    return sum(1 for e in entries(user) if e.get("date") == today and not e.get("seed"))


def profile(user):
    es = entries(user)
    styles = Counter(t for e in es if e["kind"] == "visual" for t in e.get("style_tags", []))
    themes = Counter(t for e in es if e["kind"] != "visual" for t in e.get("themes", []))
    examples = {}
    for e in es:
        for t in e.get("style_tags", []) + e.get("themes", []):
            examples.setdefault(t, []).append(e["title"])
    return {"total": len(es), "styles": styles.most_common(), "themes": themes.most_common(),
            "examples": examples}


def signals(user, item):
    """What this new reel changed in the profile: the 'pattern detected' moment."""
    p = profile(user)
    styles, themes = dict(p["styles"]), dict(p["themes"])
    out = []
    for t in item.get("style_tags", []):
        n = styles.get(t, 0)
        if n >= 3:
            out.append(f"{n}a vez que guardas «{t}». Ya es parte de tu estilo.")
        elif n == 2:
            out.append(f"2a vez con «{t}». Una más y es patrón.")
    for t in item.get("themes", []):
        n = themes.get(t, 0)
        if n >= 3 and item["kind"] != "visual":
            out.append(f"Llevas {n} reels sobre «{t}». Es algo que estás trabajando.")
    return out
