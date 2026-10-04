"""One-time: turns the existing rows of inspo.md into library entries, so the taste profile starts with history."""
import json
import sys

import env  # noqa: F401
import library
import pipeline
import vault

user = sys.argv[1]
md = (vault.VAULT / vault.INSPO_MD).read_text()
rows = [l for l in md.split("\n") if l.startswith("| 20")]
resp = pipeline.client.chat.completions.create(
    model=pipeline.ANALYSIS_MODEL,
    messages=[{"role": "system", "content":
               "For each inspiration-board row, return title (short, Spanish), kind (visual|knowledge|other), "
               "style_tags (2-5 short visual-style tags in Spanish, consistent wording across rows so repeats match, "
               "e.g. the same tag every time the same technique appears) and themes (1-3 Spanish topic tags). Use a SMALL shared vocabulary: at most 12 distinct style tags across ALL rows, broad enough to repeat (e.g. \"texto detrás del sujeto\", \"tipografía grotesca neutra\", \"plano fijo\", \"collage de fotogramas\", \"serif de contraste\"). Identical technique = identical tag string."},
              {"role": "user", "content": "\n".join(rows)}],
    response_format={"type": "json_schema", "json_schema": {"name": "rows", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["rows"],
        "properties": {"rows": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["date", "title", "kind", "style_tags", "themes"],
            "properties": {"date": {"type": "string"}, "title": {"type": "string"},
                           "kind": {"type": "string", "enum": ["visual", "knowledge", "other"]},
                           "style_tags": {"type": "array", "items": {"type": "string"}},
                           "themes": {"type": "array", "items": {"type": "string"}}}}}}}}},
)
for r in json.loads(resp.choices[0].message.content)["rows"]:
    library.add(user, {**r, "seed": True, "url": "", "summary": "", "key_points": [], "action": "",
                       "what_stands_out": "", "what_to_steal": "", "place_name": "", "place_city": ""})
p = library.profile(user)
vault.write_profile(p)
print(json.dumps(p["styles"][:15], ensure_ascii=False))
