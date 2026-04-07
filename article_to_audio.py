#!/Users/ali.musa/.local/pipx/venvs/edge-tts/bin/python
"""Convert articles (PDF, text, markdown, HTML) to audiobook-style MP3.

Usage:
    python3 article_to_audio.py <input_file_or_url> [--output FILE] [--voice VOICE] [--upload]

Examples:
    python3 article_to_audio.py ~/Downloads/article.pdf
    python3 article_to_audio.py https://example.com/article
    python3 article_to_audio.py ~/Downloads/article.pdf --voice en-US-ChristopherNeural
    python3 article_to_audio.py ~/Downloads/article.pdf --upload
    python3 article_to_audio.py article.txt --output ~/Downloads/my_audio.mp3
"""

import argparse
import asyncio
import glob
import json
import os
import re
import subprocess
import sys
import tempfile


# -- Defaults --
DEFAULT_VOICE = "en-US-AndrewNeural"
EDGE_TTS_BIN = os.path.expanduser("~/.local/bin/edge-tts")
GDRIVE_CLI = os.path.expanduser("~/utilities/google-workspace-cli/google_workspace_cli.py")
CHUNK_SIZE = 4000  # chars per TTS chunk
GITHUB_REPO = "paul-muaddib-usul/reading-list-audio"
GIST_ID = "da237a8f710c1f2dbb372ea27652de0b"


def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _extract_article_text(html: str) -> str:
    """Extract article body from raw HTML."""
    # Prefer trafilatura — best at finding article body
    try:
        import trafilatura
        text = trafilatura.extract(html, include_comments=False,
                                    include_tables=False)
        if text and len(text) > 200:
            return text
    except ImportError:
        pass

    # Fallback: BeautifulSoup
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        article = soup.find("article") or soup.find("main") or soup
        return article.get_text(separator="\n\n", strip=True)
    except ImportError:
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text)


def fetch_url_plain(url: str) -> str:
    """Fetch a URL with no auth — works for non-paywalled sites."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "-A", USER_AGENT, url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout:
            return _extract_article_text(result.stdout)
    except subprocess.TimeoutExpired:
        pass
    return ""


def fetch_url_with_browser_cookies(url: str) -> str:
    """Fetch a URL using cookies from local browsers (Chrome, Safari, Firefox).

    Works for sites where you're already logged in. Tries each browser in turn.
    """
    try:
        import browser_cookie3
        import requests
    except ImportError:
        return ""

    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    # Strip www. for cookie matching
    cookie_domain = domain.replace("www.", "")

    browsers = [
        ("Chrome", browser_cookie3.chrome),
        ("Safari", browser_cookie3.safari),
        ("Firefox", browser_cookie3.firefox),
        ("Edge", browser_cookie3.edge),
    ]

    for name, loader in browsers:
        try:
            cj = loader(domain_name=cookie_domain)
            if not list(cj):
                continue
            r = requests.get(url, cookies=cj,
                             headers={"User-Agent": USER_AGENT},
                             timeout=30, allow_redirects=True)
            if r.status_code == 200 and r.text:
                text = _extract_article_text(r.text)
                if text and len(text) > 500:
                    print(f"  Fetched via {name} cookies")
                    return text
        except Exception:
            continue

    return ""


def fetch_url(url: str) -> str:
    """Fetch article text. Tries plain fetch, then browser cookies."""
    # Try plain fetch first
    text = fetch_url_plain(url)
    if text and len(text) > 500 and "subscribe" not in text.lower()[:500]:
        return text

    # Fall back to browser cookies for paywalled content
    print("  Plain fetch insufficient, trying browser cookies...")
    cookie_text = fetch_url_with_browser_cookies(url)
    if cookie_text and len(cookie_text) > 500:
        return cookie_text

    # Return whatever the plain fetch got, even if short
    return text


def extract_text_from_pdf(path: str) -> str:
    """Extract text from PDF. Tries pdftotext first, falls back to pdfplumber."""
    # Try pdftotext (poppler)
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0 and len(result.stdout.strip()) > 500:
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try pdfplumber
    try:
        import pdfplumber
        text_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    # Try PyPDF2
    try:
        from PyPDF2 import PdfReader
        reader = PdfReader(path)
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n\n".join(text_parts)
    except ImportError:
        pass

    print("Error: No PDF reader available. Install pdftotext, pdfplumber, or PyPDF2.")
    sys.exit(1)


def extract_text_from_html(path: str) -> str:
    """Extract text from HTML file."""
    try:
        from bs4 import BeautifulSoup
        with open(path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        # Remove script, style, nav, footer elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n\n", strip=True)
    except ImportError:
        # Fallback: crude tag stripping
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text


def extract_text(path: str) -> str:
    """Extract text from a file based on extension."""
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(path)
    elif ext in (".html", ".htm"):
        return extract_text_from_html(path)
    elif ext in (".txt", ".md", ".markdown", ".text"):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        # Try reading as plain text
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


def clean_for_narration(text: str) -> str:
    """Clean extracted text for audiobook narration."""
    # Remove common web artifacts
    patterns_to_remove = [
        r"ADVERTISEMENT",
        r"Save this story",
        r"Open cartoon gallery.*",
        r"Cartoon by [\w\s]+\.?",
        r"Get our .* newsletter.*",
        r"Sign up.*newsletter.*",
        r"By signing up.*",
        r"SIGN UP",
        r"https?://\S+",
        r"\d+/\d+$",  # page numbers like 1/45
        r"^\d{1,2}/\d{1,2}/\d{2,4},\s*\d+:\d+\s*(AM|PM).*$",  # timestamps
    ]
    for pattern in patterns_to_remove:
        text = re.sub(pattern, "", text, flags=re.MULTILINE | re.IGNORECASE)

    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove leading/trailing whitespace from each line
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)

    return text.strip()


def split_into_chunks(text: str, max_chars: int = CHUNK_SIZE) -> list[str]:
    """Split text into chunks at paragraph boundaries."""
    chunks = []
    current = ""
    for para in text.split("\n\n"):
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current += "\n\n" + para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def generate_audio(text: str, output_path: str, voice: str = DEFAULT_VOICE) -> bool:
    """Generate MP3 from text using edge-tts, chunking for long texts."""
    chunks = split_into_chunks(text)
    print(f"Generating audio: {len(chunks)} chunks, voice: {voice}")

    part_files = []
    tmpdir = tempfile.mkdtemp(prefix="article_audio_")

    try:
        for i, chunk in enumerate(chunks):
            part_file = os.path.join(tmpdir, f"part_{i:03d}.mp3")
            chunk_file = os.path.join(tmpdir, f"chunk_{i:03d}.txt")

            with open(chunk_file, "w", encoding="utf-8") as f:
                f.write(chunk)

            result = subprocess.run(
                [EDGE_TTS_BIN, "--voice", voice, "--file", chunk_file,
                 "--write-media", part_file],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode != 0:
                print(f"  Error on chunk {i+1}: {result.stderr[:200]}")
                return False

            part_files.append(part_file)
            pct = int((i + 1) / len(chunks) * 100)
            print(f"  [{pct:3d}%] Chunk {i+1}/{len(chunks)}")

        # Concatenate with ffmpeg
        list_file = os.path.join(tmpdir, "parts.txt")
        with open(list_file, "w") as f:
            for pf in part_files:
                f.write(f"file '{pf}'\n")

        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", list_file, "-c", "copy", output_path],
            capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            print(f"  ffmpeg error: {result.stderr[:200]}")
            return False

        return True

    finally:
        # Cleanup temp files
        for f in glob.glob(os.path.join(tmpdir, "*")):
            os.remove(f)
        os.rmdir(tmpdir)


def upload_to_drive(file_path: str, name: str = None) -> dict | None:
    """Upload file to Google Drive. Returns file metadata or None."""
    if not os.path.exists(GDRIVE_CLI):
        print("Google Workspace CLI not found, skipping upload.")
        return None

    if name is None:
        name = os.path.basename(file_path)

    result = subprocess.run(
        ["python3", GDRIVE_CLI, "drive-upload", file_path,
         "--name", name, "--mime-type", "audio/mpeg"],
        capture_output=True, text=True, timeout=120,
        cwd=os.path.dirname(GDRIVE_CLI)
    )

    if result.returncode != 0:
        print(f"Upload failed: {result.stderr[:200]}")
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Upload output: {result.stdout}")
        return None


def publish_to_feed(mp3_path: str, title: str, description: str = "") -> str | None:
    """Upload MP3 as GitHub release and add episode to RSS feed."""
    import xml.etree.ElementTree as ET
    from email.utils import formatdate
    from time import time

    # Generate episode tag
    ep_num = f"ep-{int(time())}"
    mp3_name = os.path.basename(mp3_path)

    # Upload as GitHub release
    print("  Uploading to GitHub...")
    result = subprocess.run(
        ["gh", "release", "create", ep_num, mp3_path,
         "--title", title, "--notes", description,
         "--repo", GITHUB_REPO],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"  Release failed: {result.stderr[:200]}")
        return None

    mp3_url = f"https://github.com/{GITHUB_REPO}/releases/download/{ep_num}/{mp3_name}"
    file_size = str(os.path.getsize(mp3_path))
    duration = str(int(get_duration(mp3_path)))

    # Fetch current RSS feed from gist
    result = subprocess.run(
        ["gh", "gist", "view", GIST_ID, "--raw"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  Could not fetch feed: {result.stderr[:200]}")
        return mp3_url

    feed_xml = result.stdout

    # Insert new item before </channel>
    new_item = f"""    <item>
      <title>{title}</title>
      <description>{description}</description>
      <enclosure url="{mp3_url}" length="{file_size}" type="audio/mpeg"/>
      <pubDate>{formatdate(localtime=True)}</pubDate>
      <itunes:duration>{duration}</itunes:duration>
      <guid>{ep_num}</guid>
    </item>
  </channel>"""

    feed_xml = feed_xml.replace("  </channel>", new_item)

    # Write updated feed and push to gist
    feed_path = "/tmp/podcast_feed.xml"
    with open(feed_path, "w") as f:
        f.write(feed_xml)

    result = subprocess.run(
        ["gh", "gist", "edit", GIST_ID, feed_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  Feed update failed: {result.stderr[:200]}")
    else:
        print("  Feed updated")

    return mp3_url


def get_duration(file_path: str) -> float:
    """Get audio duration in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", file_path],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def main():
    parser = argparse.ArgumentParser(
        description="Convert articles to audiobook-style MP3"
    )
    parser.add_argument("input", help="Path to article file (PDF, txt, md, html) or URL")
    parser.add_argument("--output", "-o", help="Output MP3 path (default: ~/Downloads/<name>.mp3)")
    parser.add_argument("--voice", "-v", default=DEFAULT_VOICE,
                        help=f"Edge TTS voice (default: {DEFAULT_VOICE})")
    parser.add_argument("--upload", "-u", action="store_true",
                        help="Upload to Google Drive after generating")
    parser.add_argument("--publish", "-p", action="store_true",
                        help="Publish to podcast feed (GitHub + RSS)")
    parser.add_argument("--title", "-t", help="Episode title (default: derived from filename)")
    parser.add_argument("--raw", action="store_true",
                        help="Skip narration cleanup (use text as-is)")
    args = parser.parse_args()

    input_val = args.input
    is_input_url = is_url(input_val)

    if is_input_url:
        input_path = None
        url = input_val
    else:
        input_path = os.path.expanduser(input_val)
        if not os.path.exists(input_path):
            print(f"Error: File not found: {input_path}")
            sys.exit(1)

    # Determine output path
    if args.output:
        output_path = os.path.expanduser(args.output)
    elif is_input_url:
        # Derive name from URL slug
        from urllib.parse import urlparse
        slug = urlparse(url).path.rstrip("/").split("/")[-1] or "article"
        base = re.sub(r"[^\w\s-]", "", slug).strip()[:80]
        output_path = os.path.expanduser(f"~/Downloads/{base}.mp3")
    else:
        base = os.path.splitext(os.path.basename(input_path))[0]
        base = re.sub(r"[^\w\s-]", "", base).strip()[:80]
        output_path = os.path.expanduser(f"~/Downloads/{base}.mp3")

    # Extract text
    if is_input_url:
        print(f"Fetching article from: {url}")
        text = fetch_url(url)
        if not text or len(text) < 200:
            print("Error: Could not fetch article. It may be paywalled.")
            print("Try downloading the page as PDF and passing the file path instead.")
            sys.exit(1)
    else:
        print(f"Extracting text from: {input_path}")
        text = extract_text(input_path)

    if not text or len(text) < 100:
        print("Error: Could not extract enough text from file.")
        sys.exit(1)

    # Clean for narration
    if not args.raw:
        text = clean_for_narration(text)

    word_count = len(text.split())
    print(f"Text extracted: {word_count:,} words")

    # Generate audio
    if not generate_audio(text, output_path, args.voice):
        print("Error: Audio generation failed.")
        sys.exit(1)

    # Report results
    duration = get_duration(output_path)
    size_mb = os.path.getsize(output_path) / 1024 / 1024
    print(f"\nDone: {output_path}")
    print(f"Duration: {duration/60:.0f} min | Size: {size_mb:.1f} MB | Words: {word_count:,}")

    # Upload to Google Drive if requested
    if args.upload:
        print("\nUploading to Google Drive...")
        name = os.path.basename(output_path)
        result = upload_to_drive(output_path, name)
        if result:
            print(f"Uploaded: {result.get('webViewLink', 'OK')}")

    # Publish to podcast feed if requested
    if args.publish:
        title = args.title or os.path.splitext(os.path.basename(output_path))[0].replace("_", " ").replace("-", " ").title()
        print(f"\nPublishing to podcast feed: {title}")
        mp3_url = publish_to_feed(output_path, title)
        if mp3_url:
            print(f"Episode live: {mp3_url}")

    return output_path


if __name__ == "__main__":
    main()
