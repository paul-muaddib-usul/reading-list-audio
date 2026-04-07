# Listen

Convert an article into an audiobook-style MP3 for mobile listening.

**Usage:** `/listen <file path or URL>`

## Input handling

- **File path** (PDF, txt, md, html): Extract text directly using `~/utilities/article-to-audio/article_to_audio.py`
- **URL**: Fetch the page with WebFetch, save the article text to a temp file, then run the script on it. If WebFetch fails (paywall), ask the user for a downloaded file instead.

## Steps

1. **Determine input type** from the argument: file path or URL.

2. **If URL**: Use WebFetch to pull the article text. Extract only the article body (no nav, ads, footers, related articles). Save cleaned text to `/tmp/article_for_audio.txt`.

3. **If file path** (or after saving URL text): Run the conversion script:
   ```bash
   python3 ~/utilities/article-to-audio/article_to_audio.py "<input_file>" --publish --title "<article title>"
   ```
   The `--publish` flag uploads the MP3 to GitHub releases and adds it to the podcast RSS feed automatically.

4. **If the extracted text looks incomplete** (PDF from web page with images, paywall truncation): Read the file directly using the Read tool to extract the full text, clean it for narration (remove page numbers, URLs, ADVERTISEMENT markers, image captions, cartoon descriptions, newsletter signups, "Read More" sections, author bios), write the clean text to `/tmp/article_for_audio.txt`, then run the script on that file.

5. **Report results**: Show the file path, duration, size, and Google Drive link.

## Narration cleanup rules

Strip these from the text before audio generation:
- Page numbers, timestamps, URLs
- "ADVERTISEMENT", "Save this story", "Sign up", newsletter prompts
- Image/cartoon captions ("Cartoon by...", "Photograph by...")
- Navigation elements ("Read More", "New Yorker Favorites", etc.)
- Author bios at end of article
- Any non-article content (sidebars, related stories)

## Voice

Default voice: `en-US-AndrewNeural` (warm, natural, good for long-form narration).

Other good options the user can request:
- `en-US-ChristopherNeural` — authoritative, news style
- `en-US-BrianNeural` — casual, approachable
- `en-US-AvaNeural` — female, expressive

## Podcast Feed

The RSS feed URL is:
```
https://gist.githubusercontent.com/paul-muaddib-usul/da237a8f710c1f2dbb372ea27652de0b/raw/podcast_feed.xml
```

Audio files are hosted as GitHub release assets on `paul-muaddib-usul/reading-list-audio`.

The `--publish` flag handles everything: uploads MP3 to GitHub, updates the RSS feed. New episodes appear automatically in any podcast app subscribed to the feed.

## Notes

- The script chunks long text (~4000 chars per chunk) and concatenates with ffmpeg to handle articles of any length
- `--publish` uploads to GitHub releases and updates the RSS feed
- `--upload` uploads to Google Drive (optional, in addition to publish)
- Compatible with any podcast app: Apple Podcasts, Pocket Casts, Overcast, Castro, etc.
