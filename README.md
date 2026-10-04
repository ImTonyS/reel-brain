# Reel Brain

Scrolling reels in bed isn't wasted time, it's research that disappears. Reel Brain turns it into something you keep.

Share any Instagram reel to a Telegram bot. It watches the video (keyframes + audio, any language), decides what it is, and files it where you work:

- **Knowledge** (tips, how-tos, language lessons): a distilled note with key points and one concrete action, grouped by theme on a learning canvas.
- **Visual inspiration** (design, typography, editing): keyframes + "what stands out / what to steal" on your inspiration board.
- **AI-generated video references**: their own board.

Over time it shows you your taste: *"4th time you save serif text behind a subject, that's your style."* Add a note when sharing (or reply to the bot's card) and it centers the analysis on what you cared about.

Today the destination is an Obsidian vault. The agent stays the same; only the destination changes (Notion, Pinterest, Maps…).

## How it works
1. `yt-dlp` downloads the reel anonymously (never uses your Instagram session).
2. `ffmpeg` extracts scene-change keyframes and the audio.
3. OpenAI: `gpt-4o-mini-transcribe` for speech, `gpt-5-mini` vision + structured outputs to classify and distill.
4. The result is written into the vault (markdown notes + Obsidian canvas) and a tag-frequency taste profile.

## Run
```
pip install yt-dlp openai "python-telegram-bot[job-queue]"
cp .env.example .env   # OPENAI_API_KEY, TELEGRAM_TOKEN, OWNER_CHAT_ID, VAULT_DIR
python3 bot.py
```
`/gusto` shows your taste profile, `/preguntar` answers from what you saved.

Built at DevDay Exchange Community Hack Day: Taipei (2026-10-04).
