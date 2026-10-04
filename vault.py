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
    row = f"| {today} | {que_es} | {_cell(item['what_stands_out'])} | {steal} |"

    path = VAULT / INSPO_MD
    lines = path.read_text().split("\n")
    header = next(i for i, l in enumerate(lines) if l.startswith("| Fecha"))
    lines.insert(header + 2, row)  # newest first, right under the separator
    path.write_text("\n".join(lines))

    _add_to_canvas(item, names, today)
    return names


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
                          f"**Qué me robo (candidato):** {item['what_to_steal']}\n\n[reel]({item['url']})"})
    for i, n in enumerate(names):
        nodes.append({"id": f"{rid}-img{i}", "type": "file", "file": f"{CAPTURAS}/{n}",
                      "x": AUTO_X + 400 + i * 220, "y": y, "width": 200, "height": 356})
    path.write_text(json.dumps(canvas, ensure_ascii=False, indent="\t"))


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

## Patrón
{chr(10).join('- ' + s for s in signals) or '_Primera vez con estos temas._'}

## Relacionado
[[01-YOU/marketing/perfil-de-gusto]] · [[06-LOG/Daily/{today}]]
"""
    (VAULT / KNOWLEDGE / name).write_text(body)
    return name


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
