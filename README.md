# Reading List Audio

Convert articles to audiobook-style MP3s, publish them to a private podcast feed, and listen on your phone.

## What it does

- Takes a PDF, text file, HTML, or URL
- Extracts and cleans the article text for narration
- Generates a single-voice MP3 with [edge-tts](https://github.com/rany2/edge-tts) (free, no API key)
- Uploads to GitHub releases
- Updates an RSS feed (hosted on a public Gist)
- New episodes appear automatically in any podcast app subscribed to the feed

## Files

- `article_to_audio.py` — main script
- `skills/listen.md` — Claude Code slash command (`/listen`)

## Dependencies

```bash
brew install ffmpeg pipx
pipx install edge-tts
pipx inject edge-tts browser-cookie3 requests trafilatura beautifulsoup4
```

## Usage

```bash
# Local file
./article_to_audio.py ~/Downloads/article.pdf --publish

# URL (uses your browser cookies for paywalled sites)
./article_to_audio.py "https://www.newyorker.com/magazine/..." --publish

# With custom voice
./article_to_audio.py article.pdf -v en-US-ChristopherNeural --publish
```

Flags:
- `--publish` — upload to GitHub releases and update RSS feed
- `--upload` — also upload to Google Drive
- `--voice` — pick an edge-tts voice (default: `en-US-AndrewNeural`)
- `--title` — custom episode title
- `--raw` — skip narration cleanup

## URL fetching

The script fetches URLs in this order:
1. Plain HTTP fetch (works for non-paywalled sites)
2. Browser cookie extraction (Chrome → Safari → Firefox → Edge) — works for sites you're logged into

## RSS feed

The feed lives in a public GitHub Gist. Subscribe to it in any podcast app:

```
https://gist.githubusercontent.com/paul-muaddib-usul/da237a8f710c1f2dbb372ea27652de0b/raw/podcast_feed.xml
```

**Apple Podcasts:** Library → ⋯ → Follow a Show by URL → paste the feed URL.

## Claude Code skill

The `/listen` slash command lives in `skills/listen.md`. To install:

```bash
cp skills/listen.md ~/.claude/commands/listen.md
```

Then in Claude Code: `/listen ~/Downloads/article.pdf`
