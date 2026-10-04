"""Run one reel end to end without Telegram: python3 try.py <url> [user]"""
import json
import sys
import time

import env  # noqa: F401
import library
import pipeline
import vault

url, user = pipeline.clean_url(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else "cli")
t0 = time.time()
item = pipeline.process(url, library.vocab(user))
library.add(user, {k: item[k] for k in ("url", "kind", "title", "style_tags", "themes")} | {"date": "cli"})
sig = library.signals(user, item)
print(json.dumps({k: v for k, v in item.items() if k not in ("frames", "best_frames", "workdir", "transcript")},
                 ensure_ascii=False, indent=1))
print("transcript:", item["transcript"][:300])
print("signals:", sig, f"\n{time.time() - t0:.1f}s")
if "--write" in sys.argv:
    (vault.write_visual if item["kind"] == "visual" else vault.write_knowledge)(item, sig)
    vault.write_profile(library.profile(user))
    print("escrito en", vault.VAULT)
