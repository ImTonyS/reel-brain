"""Writes a processed reel into Tony's Obsidian vault: inspo board + canvas, or a knowledge note."""
import json
import os
import re
import shutil
import unicodedata
from datetime import date, datetime
from pathlib import Path

VAULT = Path(os.getenv("VAULT_DIR", "~/second-brain")).expanduser()
INSPO_MD = "01-YOU/marketing/inspo.md"
CANVAS = "01-YOU/marketing/inspo.canvas"
CAPTURAS = "01-YOU/marketing/inspo-capturas"
PROFILE_MD = "01-YOU/marketing/perfil-de-gusto.md"
KNOWLEDGE = "08-KNOWLEDGE"
LEARN_CANVAS = "08-KNOWLEDGE/reels-aprendizaje.canvas"

AUTO_X, AUTO_Y = -900, 1100  # canvas area below the hand-made zones


def slug(text, n=40):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:n].strip("-") or "reel"


def _cell(text):
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def write_visual(item, signals):
    today = date.today().isoformat()
    base = f"{today}-reel-{slug(item['meta'].get('handle') or item['title'], 24)}"
    dest = VAULT / CAPTURAS
    names = []
    for i, f in enumerate(item["best_frames"], 1):
        name = f"{base}-{i}.jpg"
        shutil.copy(f, dest / name)
        names.append(name)

    who = item["meta"].get("handle") or item["meta"].get("uploader")
    embeds = " ".join(f"![[{n}\\|120]]" for n in names)
    que_es = f"**{_cell(item['title'])}** — reel de @{who} ([link]({item['url']})) {embeds}"
    steal = f"**Candidato (auto, Tony decide):** {_cell(item['what_to_steal'])}"
    if signals:
        steal += " · " + " ".join(_cell(s) for s in signals)
    liked = _cell(item['what_stands_out'])
    if item.get("note"):
        liked = f"**Tony:** {_cell(item['note'])} · {liked}"
    row = f"| {today} | {que_es} | {liked} | {steal} |"

    path = VAULT / INSPO_MD
    lines = path.read_text().split("\n")
    header = next(i for i, l in enumerate(lines) if l.startswith("| Fecha"))
    lines.insert(header + 2, row)  # newest first, right under the separator
    path.write_text("\n".join(lines))

    node = _add_to_canvas(item, names, today)
    return {"kind": "visual", "row": row, "node": node}


def _add_to_canvas(item, names, today):
    path = VAULT / CANVAS
    canvas = json.loads(path.read_text())
    nodes = canvas["nodes"]
    if not any(n["id"] == "reels-header" for n in nodes):
        nodes.append({"id": "reels-header", "type": "text", "x": AUTO_X, "y": AUTO_Y,
                      "width": 520, "height": 120,
                      "text": "## Desde reels (auto)\nLo que mandas al bot cae aquí. Tu gusto: [[01-YOU/marketing/perfil-de-gusto]]"})
        nodes.append({"id": "reels-profile", "type": "file", "file": PROFILE_MD,
                      "x": AUTO_X + 560, "y": AUTO_Y, "width": 520, "height": 420})
    auto = [n for n in nodes if n["id"].startswith("reel-")]
    y = max([n["y"] + n["height"] for n in auto], default=AUTO_Y + 440) + 40
    rid = f"reel-{datetime.now():%H%M%S}"
    nodes.append({"id": rid, "type": "text", "x": AUTO_X, "y": y, "width": 380, "height": 360,
                  "text": f"**{item['title']} ({today})**\n{item['what_stands_out']}\n\n"
                          f"**Qué me robo (candidato):** {item['what_to_steal']}\n\n[reel]({item['url']})"
                          + (f"\n\n**Mi nota:** {item['note']}" if item.get("note") else "")})
    for i, n in enumerate(names):
        nodes.append({"id": f"{rid}-img{i}", "type": "file", "file": f"{CAPTURAS}/{n}",
                      "x": AUTO_X + 400 + i * 220, "y": y, "width": 200, "height": 356})
    path.write_text(json.dumps(canvas, ensure_ascii=False, indent="\t"))
    return rid


def write_knowledge(item, signals):
    today = date.today().isoformat()
    name = f"{today[:4]}-reel-{slug(item['title'])}.md"
    who = item["meta"].get("handle") or item["meta"].get("uploader")
    tags = ", ".join(["knowledge", "reel"] + [slug(t, 30) for t in item["themes"]])
    points = "\n".join(f"- {p}" for p in item["key_points"])
    themes = " · ".join(item["themes"])
    body = f"""---
date: {today}
type: knowledge
status: inbox
tags: [{tags}]
source: {item['url']}
ai-first: true
confidence: medium
last-updated: {today}
---

# {item['title']}

## For future Claude
Reel de Instagram de @{who} que [[01-YOU/identity|Tony]] guardó el {today}, destilado automáticamente por reel-brain (idioma original: {item['language']}). Temas: {themes}. Fuente: {item['url']}

## Resumen
{item['summary']}

## Puntos clave
{points}

## Acción
{item['action'] or '_Ninguna concreta._'}
{f"{chr(10)}## Mi nota{chr(10)}{item['note']}{chr(10)}" if item.get('note') else ''}

## Patrón
{chr(10).join('- ' + s for s in signals) or '_Primera vez con estos temas._'}

## Relacionado
[[01-YOU/marketing/perfil-de-gusto]] · [[06-LOG/Daily/{today}]]
"""
    (VAULT / KNOWLEDGE / name).write_text(body)
    _add_to_learn_canvas(item, name)
    return {"kind": "knowledge", "file": f"{KNOWLEDGE}/{name}"}


def _add_to_learn_canvas(item, name):
    """Content-only board for knowledge reels: one card per note, grouped in columns by theme."""
    path = VAULT / LEARN_CANVAS
    canvas = json.loads(path.read_text()) if path.exists() else {"nodes": [], "edges": []}
    nodes = canvas["nodes"]
    if not nodes:
        nodes.append({"id": "learn-title", "type": "text", "x": 0, "y": -200, "width": 600, "height": 140,
                      "text": "# Lo que estoy aprendiendo (reels)\nCada reel informativo que mando al bot cae aquí como nota, agrupado por tema. Solo contenido, nada de cómo está grabado."})
    theme = (item["themes"] or ["otros"])[0]
    cols = [n for n in nodes if n["id"].startswith("theme-")]
    col = next((n for n in cols if n["text"] == f"## {theme}"), None)
    if not col:
        col = {"id": f"theme-{len(cols)}", "type": "text", "x": len(cols) * 460, "y": 0,
               "width": 420, "height": 80, "text": f"## {theme}"}
        nodes.append(col)
    below = [n for n in nodes if n.get("col") == col["id"]]
    y = max([n["y"] + n["height"] for n in below], default=col["y"] + col["height"]) + 30
    nodes.append({"id": f"learn-{datetime.now():%H%M%S}", "type": "file",
                  "file": f"{KNOWLEDGE}/{name}", "x": col["x"], "y": y, "width": 420, "height": 400,
                  "col": col["id"]})
    path.write_text(json.dumps(canvas, ensure_ascii=False, indent="\t"))


def write_profile(p):
    today = date.today().isoformat()

    def block(pairs, label):
        rows = []
        for tag, n in pairs[:12]:
            mark = " — **patrón**" if n >= 3 else ""
            ex = "; ".join(p["examples"].get(tag, [])[-3:])
            rows.append(f"- **{tag}** ×{n}{mark} · {ex}")
        return "\n".join(rows) or f"_Aún no hay {label}._"

    body = f"""---
date: {today}
type: identity
status: active
tags: [identity, contenido, gusto, inspiracion, auto]
ai-first: true
last-updated: {today}
---

# Perfil de gusto (auto)

## For future Claude
Generado por reel-brain a partir de los reels que [[01-YOU/identity|Tony]] le manda al bot y de las entradas de [[01-YOU/marketing/inspo]]. Se reescribe solo en cada reel; no editar a mano. Lo que aparece 3+ veces es patrón **candidato**: Tony decide si entra a su sistema.

Total guardado: {p['total']}

## Tu estilo visual
{block(p['styles'], 'estilos')}

## Lo que estás aprendiendo
{block(p['themes'], 'temas')}
"""
    (VAULT / PROFILE_MD).write_text(body)


def add_note(ref, note):
    """Attach a note sent later (reply to the bot's card) to what was already saved."""
    if ref["kind"] == "knowledge":
        path = VAULT / ref["file"]
        text = path.read_text()
        marker = "## Relacionado"
        path.write_text(text.replace(marker, f"## Mi nota\n{note}\n\n{marker}", 1))
        return
    md = VAULT / INSPO_MD
    row = ref["row"]
    parts = row.split(" | ")
    parts[2] = f"**Tony:** {_cell(note)} · {parts[2]}"
    new_row = " | ".join(parts)
    md.write_text(md.read_text().replace(row, new_row, 1))
    ref["row"] = new_row
    cpath = VAULT / CANVAS
    canvas = json.loads(cpath.read_text())
    for n in canvas["nodes"]:
        if n["id"] == ref["node"]:
            n["text"] += f"\n\n**Mi nota:** {note}"
    cpath.write_text(json.dumps(canvas, ensure_ascii=False, indent="\t"))
