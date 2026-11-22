"""Darmowe, publiczne źródła inwestycyjne i parsery RSS/Atom/sitemap."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from bs4 import BeautifulSoup


PUBLIC_RSS_FEEDS = [
    {"name": "Strefa Inwestorów", "url": "https://strefainwestorow.pl/rss.xml"},
    {"name": "Bankier.pl — Giełda", "url": "https://www.bankier.pl/rss/gielda.xml"},
    {"name": "GPW — Aktualności", "url": "https://www.gpw.pl/rss-news"},
    {"name": "GPW — Komunikaty prasowe", "url": "https://www.gpw.pl/rss-press-releases"},
    {"name": "Blog Humanista na giełdzie", "url": "https://feeds.feedburner.com/HumanistaNaGiedzie"},
]

# Sitemap Strefy Inwestorów uzupełnia RSS o publiczne podstrony i artykuły.
PUBLIC_SITEMAPS = [
    {"name": "Strefa Inwestorów — mapa strony", "url": "https://strefainwestorow.pl/sitemap.xml"},
]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, *names: str) -> str:
    wanted = set(names)
    for child in element.iter():
        if _local_name(child.tag) in wanted:
            value = " ".join(part.strip() for part in child.itertext() if part.strip())
            if value:
                return value
    return ""


def parse_feed(xml_content: bytes, base_url: str) -> list[dict[str, str]]:
    """Read RSS 2.0, RDF RSS, or Atom entries into a shared simple shape."""
    root = ET.fromstring(xml_content)
    entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    results = []
    for entry in entries:
        title = _child_text(entry, "title")
        link = ""
        for node in entry:
            if _local_name(node.tag) != "link":
                continue
            link = (node.attrib.get("href") or "" if node.attrib.get("rel", "alternate") == "alternate" else "")
            link = link or (node.text or "").strip()
            if link:
                break
        if not link:
            continue
        description = _child_text(entry, "description", "summary", "content", "encoded")
        clean_description = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
        results.append({
            "url": urljoin(base_url, link.strip()),
            "title": BeautifulSoup(title, "html.parser").get_text(" ", strip=True),
            "description": clean_description[:4000],
        })
    return results


def parse_sitemap(xml_content: bytes, base_url: str) -> tuple[list[str], list[str]]:
    """Return page URLs and nested sitemap URLs from a sitemap XML document."""
    root = ET.fromstring(xml_content)
    root_name = _local_name(root.tag)
    pages: list[str] = []
    nested: list[str] = []
    for child in root:
        child_name = _local_name(child.tag)
        loc = next((n.text.strip() for n in child if _local_name(n.tag) == "loc" and n.text and n.text.strip()), "")
        if not loc:
            continue
        absolute = urljoin(base_url, loc)
        if child_name == "sitemap":
            nested.append(absolute)
        elif child_name == "url":
            pages.append(absolute)
    if root_name not in {"sitemapindex", "urlset"}:
        return [], []
    return pages, nested
