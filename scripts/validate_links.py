#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINKS_PATH = ROOT / "static" / "data" / "links.json"
HTML_FILES = list(ROOT.glob("*.html"))


def main() -> int:
    links = json.loads(LINKS_PATH.read_text(encoding="utf-8-sig"))
    known = set(links.keys())
    errors = []

    for path in HTML_FILES:
        text = path.read_text(encoding="utf-8")
        keys = re.findall(r'data-link-key="([^"]+)"', text)
        for key in keys:
            if key not in known:
                errors.append(f"{path.name}: unknown data-link-key '{key}'")

        # Hardcoded external URLs should be minimized unless the anchor is keyed.
        anchor_tags = re.findall(r"<a\\s+[^>]*>", text)
        for tag in anchor_tags:
            href_match = re.search(r'href="(https?://[^"]+)"', tag)
            if not href_match:
                continue
            url = href_match.group(1)
            if 'data-link-key="' in tag:
                continue
            if "fonts.googleapis.com" in url or "fonts.gstatic.com" in url:
                continue
            if "mbt.ph0.nexus/blog/" in url:
                continue
            if "blog.ph0.nexus" in url:
                continue
            errors.append(f"{path.name}: hardcoded external URL '{url}' should use data-link-key")

    if errors:
        print("Link validation failed:")
        for err in errors:
            print(f" - {err}")
        return 1

    print("Link validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
