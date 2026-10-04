"""Reel -> frames + audio -> OpenAI (transcribe + vision + classify)."""
import base64
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yt_dlp
from openai import OpenAI

ANALYSIS_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
TRANSCRIBE_MODEL = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
MAX_SECONDS = int(os.getenv("MAX_SECONDS", "180"))
MAX_FRAMES = 6

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or "missing")

IG_RE = re.compile(r"https?://(www\.)?instagram\.com/(reel|reels|p|tv)/([A-Za-z0-9_-]+)")


def clean_url(text):
    m = IG_RE.search(text or "")
    return f"https://www.instagram.com/reel/{m.group(3)}/" if m else None


def download(url, workdir, use_cookies=False):
    opts = {"outtmpl": str(workdir / "video.%(ext)s"), "quiet": True, "no_warnings": True, "noprogress": True,
            "format": "mp4/bestvideo+bestaudio/best", "merge_output_format": "mp4"}
    # Anonymous first; when Instagram rate-limits, retry logged in with browser cookies.
    attempts = [None]  # anonymous only: never touch the user's Instagram account
    for browser in attempts:
        try_opts = dict(opts, **({"cookiesfrombrowser": (browser,)} if browser else {}))
        try:
            with yt_dlp.YoutubeDL(try_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if (info.get("duration") or 0) > MAX_SECONDS:
                    raise ValueError(f"El video dura más de {MAX_SECONDS // 60} min.")
                ydl.download([url])
            break
        except ValueError:
            raise
        except Exception as e:
            last = e
    else:
        raise RuntimeError("Instagram no soltó el video (límite de descargas). Intenta en un rato.") from last
    video = next(workdir.glob("video.*"))
    return video, {
        "uploader": info.get("uploader") or info.get("channel") or "",
        "handle": info.get("channel") or info.get("uploader") or "",
        "caption": (info.get("description") or "")[:1500],
        "duration": info.get("duration"),
    }


def duration_of(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def extract_frames(video, workdir):
    """Scene-change frames; falls back to evenly spaced ones for static videos."""
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf",
                    "select='gt(scene,0.3)',scale=720:-2,format=yuvj420p", "-vsync", "vfr",
                    "-frames:v", str(MAX_FRAMES), str(workdir / "scene_%02d.jpg")])
    frames = sorted(workdir.glob("scene_*.jpg"))
    if len(frames) < 3:
        dur = max(duration_of(video), 1)
        for i in range(4):
            t = dur * (i + 0.5) / 4
            out = workdir / f"even_{i:02d}.jpg"
            subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=720:-2,format=yuvj420p", str(out)])
        frames += sorted(workdir.glob("even_*.jpg"))
    return frames[:MAX_FRAMES]


def transcribe(video, workdir):
    audio = workdir / "audio.mp3"
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
                        "-ar", "16000", "-b:a", "48k", str(audio)])
    if r.returncode != 0 or not audio.exists():
        return ""
    for model in (TRANSCRIBE_MODEL, "whisper-1"):
        try:
            with open(audio, "rb") as f:
                return client.audio.transcriptions.create(model=model, file=f).text
        except Exception as e:  # model name drift, try the stable one
            last = e
    print("transcribe failed:", last)
    return ""


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["visual", "knowledge", "place", "other"]},
        "board": {"type": "string", "enum": ["inspo", "ai_video", "none"]},
        "title": {"type": "string"},
        "language": {"type": "string"},
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "action": {"type": "string"},
        "what_stands_out": {"type": "string"},
        "what_to_steal": {"type": "string"},
        "style_tags": {"type": "array", "items": {"type": "string"}},
        "themes": {"type": "array", "items": {"type": "string"}},
        "best_frames": {"type": "array", "items": {"type": "integer"}},
        "place_name": {"type": "string"},
        "place_city": {"type": "string"},
    },
    "required": ["kind", "board", "title", "language", "summary", "key_points", "action",
                 "what_stands_out", "what_to_steal", "style_tags", "themes",
                 "best_frames", "place_name", "place_city"],
}

SYSTEM = """You turn an Instagram reel someone saved into something they can use.
Output in Spanish (Mexico), terse, plain language, no emojis, no jargon.

kind:
- visual: the value is how it looks (art, design, typography, editing, framing, color, thumbnails, mood). Saved as inspiration.
- knowledge: the value is information (tips, data, how-to, explanation, language lessons). If it TEACHES something, it is knowledge even if it is nicely designed. Visual is only when the person would save it for how it looks.
- place: the value is a specific place to go (restaurant, cafe, spot).
- other: none of the above.

board (where a visual reel is filed):
- ai_video: the video itself is AI-generated (the user note says so, or it is clearly AI-made). Saved as reference for making AI content.
- inspo: any other visual reference.
- none: not visual.

Fields:
- title: short, concrete.
- summary: 1-2 sentences.
- key_points: for knowledge, the actual tips/facts (max 5). Otherwise the concrete visual details.
- action: ONE concrete thing to do with this, phrased as an instruction. For visual: how to use this look in your own content (never "copy the object shown"). Empty if none.
- what_stands_out: visual kind only: what makes it look good (composition, type, color, motion). For any other kind: empty string. Never describe how a knowledge/place reel is filmed.
- what_to_steal: visual kind only: the reusable visual recipe, as a candidate idea. Otherwise empty string.
- style_tags: visual kind only, 2-5 short visual-style tags in Spanish. For any other kind: empty list.
- themes: 1-3 short topic tags in Spanish.
REUSE a tag from the existing vocabulary ONLY when that exact technique is clearly visible in the frames; otherwise create a new precise tag. A wrong reused tag is worse than a new one.
- best_frames: indices (0-based) of the 1-3 most representative frames.
- place_name / place_city: only for place, else empty.
Read on-screen text and burned-in subtitles from the frames; many reels have no speech.
If user_note is present, it is what the person cared about in this reel: center the analysis on it."""


def analyze(frames, transcript, meta, vocab, note=""):
    content = [{"type": "text", "text": json.dumps({
        "uploader": meta.get("uploader"),
        "caption": meta.get("caption"),
        "transcript": transcript[:6000],
        "existing_style_tags": vocab.get("style_tags", []),
        "existing_themes": vocab.get("themes", []),
        "frame_count": len(frames),
        "user_note": note,
    }, ensure_ascii=False)}]
    for f in frames:
        b64 = base64.b64encode(Path(f).read_bytes()).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    resp = client.chat.completions.create(
        model=ANALYSIS_MODEL,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "reel", "schema": SCHEMA, "strict": True}},
        reasoning_effort="minimal",
    )
    return json.loads(resp.choices[0].message.content)


def process(url, vocab, note="", workdir=None, use_cookies=True):
    workdir = Path(workdir or tempfile.mkdtemp(prefix="reel-"))
    video, meta = download(url, workdir, use_cookies)
    frames = extract_frames(video, workdir)
    transcript = transcribe(video, workdir)
    result = analyze(frames, transcript, meta, vocab, note)
    best = [frames[i] for i in result["best_frames"] if 0 <= i < len(frames)] or frames[:2]
    return {**result, "url": url, "meta": meta, "transcript": transcript, "frames": frames,
            "best_frames": best[:3], "workdir": workdir, "note": note}


def ask(question, saved):
    """Answer from what the user saved, citing the reel."""
    notes = [{k: e.get(k) for k in ("title", "summary", "key_points", "action", "what_to_steal",
                                    "themes", "url", "date")} for e in saved[-80:]]
    resp = client.chat.completions.create(
        model=ANALYSIS_MODEL,
        messages=[{"role": "system", "content":
                   "Answer in Spanish (Mexico), short and plain, using ONLY the saved reels below. "
                   "Cite the reel title and its url for each fact. If nothing matches, say so."},
                  {"role": "user", "content": json.dumps({"question": question, "saved_reels": notes},
                                                         ensure_ascii=False)}],
    )
    return resp.choices[0].message.content
