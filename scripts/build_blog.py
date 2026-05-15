#!/usr/bin/env python3
import base64
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import shutil
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BLOG_DIR = REPO_ROOT / "blog"
CACHE_PATH = BLOG_DIR / "data" / "posts-cache.json"
CANONICAL_BASE = "https://mbt.ph0.nexus/blog"
BLOG_PUBLIC_BASE = "https://blog.ph0.nexus"
RSS_URL = "https://blog.ph0.nexus/rss.xml"
API_URL = "https://blog.ph0.nexus/api/posts.json"
MAX_POSTS = 25
YOUTUBE_ID_LENGTH = 11


def normalize_public_url(url: str) -> str:
    """Map dev/local blog URLs to the public blog host."""
    value = (url or "").strip()
    if not value:
        return BLOG_PUBLIC_BASE

    value = re.sub(
        r"^https?://(?:localhost|127\.0\.0\.1)(?::\d+)?/",
        f"{BLOG_PUBLIC_BASE}/",
        value,
        flags=re.IGNORECASE,
    )
    return value


def normalize_post(post: dict) -> dict:
    post = dict(post)
    post["source_url"] = normalize_public_url(post.get("source_url", ""))
    if post.get("id") and (not post["source_url"] or post["source_url"] == BLOG_PUBLIC_BASE):
        post["source_url"] = f"{BLOG_PUBLIC_BASE}/post/{post['id']}"

    normalized_links = []
    for link in post.get("links", []):
        if isinstance(link, dict):
            normalized_links.append(
                {
                    "label": str(link.get("label") or "Related link"),
                    "url": normalize_public_url(str(link.get("url") or "")),
                }
            )
        else:
            normalized_links.append(
                {"label": "Related link", "url": normalize_public_url(str(link))}
            )
    post["links"] = normalized_links
    return post


def slugify(text: str) -> str:
    base = text.strip().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or "post"


def _is_public_post_id(value: str) -> bool:
    return bool(value) and len(value) == YOUTUBE_ID_LENGTH and re.fullmatch(r"[A-Za-z0-9_-]{11}", value)


def _timestamp_ms(iso_value: str) -> int:
    try:
        parsed = dt.datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        return int(parsed.timestamp() * 1000)
    except Exception:
        return int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)


def _id_from_seed(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    encoded = base64.urlsafe_b64encode(digest[:8]).decode("ascii").rstrip("=")
    return encoded[:YOUTUBE_ID_LENGTH]


def generate_public_id(title: str, taken: set[str], timestamp_iso: str) -> str:
    """Derive id from timestamp + title; bump timestamp on rare collisions."""
    title_norm = title.strip().lower()
    base_ms = _timestamp_ms(timestamp_iso)
    for offset in range(128):
        seed = f"{base_ms + offset}:{title_norm}"
        candidate = _id_from_seed(seed)
        if _is_public_post_id(candidate) and candidate not in taken:
            return candidate
    raise RuntimeError("Could not allocate a unique public post id")


def public_post_id(post: dict) -> str:
    """Stable mirror path segment from seeded Nexus post id."""
    value = str(post.get("id", "")).strip()
    if _is_public_post_id(value):
        return value
    title = str(post.get("title", "Untitled"))
    ts = str(post.get("created_at") or post.get("published_at") or dt.datetime.now(dt.timezone.utc).isoformat())
    return generate_public_id(title, set(), ts)


def post_path_segment(post: dict) -> str:
    post_id = public_post_id(post)
    published_raw = str(post.get("published_at") or post.get("created_at") or "")
    try:
        published_dt = dt.datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
    except Exception:
        published_dt = dt.datetime.now(dt.timezone.utc)
    return f"{published_dt:%Y/%m/%y-%m-%d}/{post_id}"


def fetch_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "PH0NetBlogSync/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - trusted URL
        return resp.read().decode("utf-8", errors="replace")


def parse_rfc2822_date(value: str) -> str:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    except Exception:
        return dt.datetime.now(dt.timezone.utc).isoformat()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_rss(xml_text: str):
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")
    posts = []
    for item in items[:MAX_POSTS]:
        title = (item.findtext("title") or "Untitled").strip()
        link = (item.findtext("link") or "").strip()
        desc = item.findtext("description") or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or ""
        pub = item.findtext("pubDate") or ""
        summary = strip_html(desc)[:240]
        published_at = parse_rfc2822_date(pub) if pub else dt.datetime.now(dt.timezone.utc).isoformat()
        posts.append(
            {
                "id": "",
                "title": title,
                "source_url": link,
                "summary": summary,
                "published_at": published_at,
                "created_at": published_at,
                "content_html": desc.strip(),
                "links": [],
                "video_embed_url": "",
            }
        )
    return posts


def parse_api(json_text: str):
    raw = json.loads(json_text)
    items = raw["posts"] if isinstance(raw, dict) and "posts" in raw else raw
    posts = []
    for item in items[:MAX_POSTS]:
        title = str(item.get("title", "Untitled")).strip()
        post_id = str(item.get("id") or "").strip()
        source_url = str(item.get("url") or item.get("source_url") or "").strip()
        summary = strip_html(str(item.get("summary") or item.get("excerpt") or ""))[:240]
        content_html = str(item.get("content_html") or item.get("content") or "")
        published_at = str(item.get("published_at") or item.get("published") or dt.datetime.now(dt.timezone.utc).isoformat())
        created_at = str(item.get("created_at") or published_at)
        posts.append(
            {
                "id": post_id,
                "title": title,
                "source_url": source_url,
                "summary": summary,
                "published_at": published_at,
                "created_at": created_at,
                "content_html": content_html,
                "links": item.get("links") or [],
                "video_embed_url": item.get("video_embed_url") or item.get("video_url") or "",
            }
        )
    return posts


def load_cached_posts():
    if not CACHE_PATH.exists():
        return []
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8-sig"))
        return payload.get("posts", [])
    except Exception:
        return []


def save_cache(posts, source: str):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_synced_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": source,
        "posts": posts,
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def fmt_date(iso_value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return "Unknown date"


def render_blog_index(posts, source: str, last_synced: str):
    cards = []
    for post in posts:
        cards.append(
            f"""
      <article class="project-card">
        <h3 class="card-title">{html.escape(post['title'])}</h3>
        <p class="card-description">{html.escape(post.get('summary', ''))}</p>
        <p class="section-subtitle">Published: {fmt_date(post.get('published_at', ''))}</p>
        <a class="card-link" href="./{html.escape(post_path_segment(post))}/index.html">
          <span>Read Post</span>
          <svg viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
      </article>"""
        )

    if not cards:
        cards.append(
            """
      <article class="project-card">
        <h3 class="card-title">No posts yet</h3>
        <p class="card-description">No synced posts are available right now. Check back soon.</p>
      </article>"""
        )

    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PH0Net | Blog</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700&family=Rajdhani:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../static/css/cyberpunk.css">
  <link rel="canonical" href="{CANONICAL_BASE}/">
</head>
<body>
  <header class="site-header">
    <nav class="navbar">
      <a href="../index.html" class="brand-link">
        <img src="../static/images/PH0LogoV7 Clear MAIN.png" alt="PH0Net" class="brand-logo">
        <span class="brand-text">PH0NET</span>
      </a>
      <ul class="nav-links">
        <li><a href="../index.html" class="nav-link">Home</a></li>
        <li><a href="../projects.html" class="nav-link">Projects</a></li>
        <li><a href="../about.html" class="nav-link">About</a></li>
        <li><a href="../contact.html" class="nav-link">Contact</a></li>
        <li><a href="./index.html" class="nav-link active">Blog</a></li>
      </ul>
    </nav>
  </header>
  <section class="page-header">
    <h1 class="page-title">Blog</h1>
    <p class="page-subtitle">Synced from blog.ph0.nexus</p>
  </section>
  <section class="projects-section">
    <div class="section-header">
      <span class="section-label">Last Synced</span>
      <p class="section-subtitle">{html.escape(last_synced)} UTC ({html.escape(source)})</p>
    </div>
    <div class="projects-grid">
{''.join(cards)}
    </div>
  </section>
  <footer class="site-footer">
    <div class="footer-content">
      <div class="footer-brand">
        <img src="../static/images/PH0LogoV7 Clear MAIN.png" alt="PH0Net" class="footer-logo">
        <p class="footer-text">&copy; 2026 PH0Net | Created by <a href="../about.html">MichaelBTryin</a></p>
      </div>
    </div>
  </footer>
</body>
</html>"""
    (BLOG_DIR / "index.html").write_text(html_text, encoding="utf-8")


def cleanup_stale_post_dirs(active_paths: set[str]) -> None:
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    protected = {"data"}
    for index_file in BLOG_DIR.rglob("index.html"):
        rel = index_file.parent.relative_to(BLOG_DIR).as_posix()
        if rel in protected:
            continue
        if rel not in active_paths:
            shutil.rmtree(index_file.parent, ignore_errors=True)


def render_post(post):
    segment = post_path_segment(post)
    post_dir = BLOG_DIR / segment
    post_dir.mkdir(parents=True, exist_ok=True)
    canonical = f"{CANONICAL_BASE}/{segment}/"
    body_html = post.get("content_html") or f"<p>{html.escape(post.get('summary', ''))}</p>"
    extra_links = []
    for link in post.get("links", []):
        if isinstance(link, dict):
            label = html.escape(str(link.get("label") or "Related link"))
            href = html.escape(str(link.get("url") or "#"))
        else:
            label = "Related link"
            href = html.escape(str(link))
        extra_links.append(f'<li><a class="card-link" href="{href}" target="_blank" rel="noopener noreferrer">{label}</a></li>')

    video_embed = ""
    if post.get("video_embed_url"):
        video_embed = f"""
      <div style="margin-top:1rem; position:relative; padding-bottom:56.25%; height:0; overflow:hidden; border-radius:8px; border:1px solid rgba(255,255,255,0.1);">
        <iframe src="{html.escape(post['video_embed_url'])}" title="Embedded video" allowfullscreen
          style="position:absolute; top:0; left:0; width:100%; height:100%; border:0;"></iframe>
      </div>"""

    links_html = ""
    if extra_links:
        links_html = f"""
      <ul style="margin-top:1rem;">
        {''.join(extra_links)}
      </ul>"""
    post_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PH0Net Blog | {html.escape(post['title'])}</title>
  <meta name="description" content="{html.escape(post.get('summary', ''))}">
  <link rel="canonical" href="{canonical}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;600;700&family=Rajdhani:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="../../../../static/css/cyberpunk.css">
</head>
<body>
  <header class="site-header">
    <nav class="navbar">
      <a href="../../../../index.html" class="brand-link">
        <img src="../../../../static/images/PH0LogoV7 Clear MAIN.png" alt="PH0Net" class="brand-logo">
        <span class="brand-text">PH0NET</span>
      </a>
      <ul class="nav-links">
        <li><a href="../../../index.html" class="nav-link active">Blog</a></li>
      </ul>
    </nav>
  </header>
  <section class="page-header">
    <h1 class="page-title">{html.escape(post['title'])}</h1>
    <p class="page-subtitle">Published: {fmt_date(post.get('published_at', ''))}</p>
  </section>
  <section class="projects-section">
    <article class="project-card" style="max-width: 900px; margin: 0 auto;">
      <div class="card-description">{body_html}</div>
      {video_embed}
      {links_html}
      <p style="margin-top: 1rem;">
        <a class="card-link" href="{html.escape(post.get('source_url', BLOG_PUBLIC_BASE))}" target="_blank" rel="noopener noreferrer">
          <span>View Original on blog.ph0.nexus</span>
          <svg viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </a>
      </p>
    </article>
  </section>
</body>
</html>"""
    (post_dir / "index.html").write_text(post_html, encoding="utf-8")


def main():
    BLOG_DIR.mkdir(parents=True, exist_ok=True)
    posts = []
    source = "cache"
    errors = []

    local_posts_path = os.getenv("NEXUS_BLOG_LOCAL_POSTS", "").strip()
    if local_posts_path and Path(local_posts_path).exists():
        raw = json.loads(Path(local_posts_path).read_text(encoding="utf-8-sig"))
        items = raw.get("posts", raw) if isinstance(raw, dict) else raw
        published = [p for p in items if isinstance(p, dict) and p.get("status") == "published"]
        posts = parse_api(json.dumps({"posts": published}, ensure_ascii=True))
        source = "local"
    else:
        try:
            api_text = fetch_text(API_URL)
            posts = parse_api(api_text)
            source = "api"
        except Exception as exc:
            errors.append(f"api fetch failed: {exc}")
            try:
                rss_text = fetch_text(RSS_URL)
                posts = parse_rss(rss_text)
                source = "rss"
            except Exception as rss_exc:
                errors.append(f"rss fetch failed: {rss_exc}")
                posts = load_cached_posts()
                source = "cache"

    taken_ids: set[str] = set()
    dedup: dict[str, dict] = {}
    for post in posts:
        normalized = normalize_post(post)
        title = str(normalized.get("title", "Untitled"))
        timestamp_iso = str(
            normalized.get("created_at") or normalized.get("published_at") or dt.datetime.now(dt.timezone.utc).isoformat()
        )
        post_id = str(normalized.get("id", "")).strip()
        if not _is_public_post_id(post_id) or post_id in taken_ids:
            post_id = generate_public_id(title, taken_ids, timestamp_iso)
        normalized["id"] = post_id
        dedup[post_id] = normalized
        taken_ids.add(post_id)
    posts = list(dedup.values())[:MAX_POSTS]

    if source in {"api", "rss", "local"} and posts:
        save_cache(posts, source)

    last_synced = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    render_blog_index(posts, source, last_synced)
    active_ids = {post_path_segment(post) for post in posts}
    for post in posts:
        render_post(post)
    cleanup_stale_post_dirs(active_ids)

    if errors:
        print("Warnings:")
        for err in errors:
            print(f" - {err}")
    print(f"Built blog with {len(posts)} post(s) from {source}.")


if __name__ == "__main__":
    main()

