import html
import os
import random
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from .http import Http


@dataclass
class Article:
    title: str
    language: str
    url: str
    canonical_url: str
    text: str
    markdown_path: Path


def load_article(path: Path) -> Article:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"Article Markdown does not exist: {path}")
    raw = path.read_text(encoding="utf-8")
    metadata, body = {}, raw
    if raw.startswith("---\n") and "\n---\n" in raw[4:]:
        header, body = raw[4:].split("\n---\n", 1)
        for line in header.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip().lower()] = value.strip().strip("\"'")
    heading = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    title = metadata.get("title") or (heading.group(1).strip() if heading else path.stem.replace("-", " "))
    language = metadata.get("language") or metadata.get("lang") or ""
    if language not in {"es", "en"}:
        lowered = f" {body.lower()} "
        es_score = sum(lowered.count(f" {word} ") for word in ("de", "la", "que", "para", "con", "una", "los"))
        en_score = sum(lowered.count(f" {word} ") for word in ("the", "and", "that", "for", "with", "your", "from"))
        language = "es" if es_score > en_score else "en"
    text = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    text = re.sub(r"!?(\[([^]]+)\])\([^)]+\)", r"\2", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 100:
        raise RuntimeError(f"Article Markdown contains insufficient content: {path}")
    source = metadata.get("url") or path.as_uri()
    return Article(title, language, source, source, text, path)


def _locations(xml: bytes) -> tuple[list[str], bool]:
    root = ElementTree.fromstring(xml)
    locations = []
    for node in root.iter():
        if node.tag.endswith("loc") and node.text:
            locations.append(node.text.strip())
        elif node.tag.endswith("link") and node.get("href"):
            locations.append(node.get("href").strip())
    return locations, root.tag.endswith("sitemapindex")


def discover_urls(sitemap: str, language: str, http: Http, depth: int = 0) -> list[str]:
    if depth > 2:
        return []
    locations, is_index = _locations(http.request("GET", sitemap).content)
    if is_index:
        result = []
        preferred = [u for u in locations if language in urlparse(u).path.lower()]
        for child in preferred or locations:
            result.extend(discover_urls(child, language, http, depth + 1))
        return result
    urls = []
    for url in locations:
        path = urlparse(url).path.lower()
        if "/blog/" not in path or path.rstrip("/").endswith("/blog"):
            continue
        
        match = re.match(r"^/([a-z]{2}(-[a-z]+)?)/", path)
        if match:
            url_lang = match.group(1)
            if url_lang != language:
                parsed = urlparse(url)
                new_path = parsed.path.replace(f"/{url_lang}/", f"/{language}/", 1)
                url = parsed._replace(path=new_path).geturl()
        urls.append(url)
    return sorted(list(set(urls)))


def fetch_article(workdir: Path, http: Http | None = None, chooser=random.choice) -> Article:
    http = http or Http()
    language = chooser(["es", "en"])
    base = os.getenv("ARTICLE_BASE_URL") or "https://inmibot.es"
    default = urljoin(base.rstrip("/") + "/", "sitemap.xml")
    sitemap = os.getenv(f"ARTICLE_SITEMAP_URL_{language.upper()}") or default
    urls = sorted(set(discover_urls(sitemap, language, http)))
    if not urls:
        raise RuntimeError(f"No published {language} blog articles found in {sitemap}")
    url = chooser(urls)
    soup = BeautifulSoup(http.request("GET", url).text, "html.parser")
    canonical = soup.select_one('link[rel="canonical"]')
    canonical_url = urljoin(url, canonical.get("href")) if canonical and canonical.get("href") else url
    root = soup.find("article") or soup.find("main")
    if not root:
        raise RuntimeError(f"No main/article content found at {url}")
    for unwanted in root.select("nav, footer, aside, script, style, form, .share, .related"):
        unwanted.decompose()
    heading = root.find("h1") or soup.find("h1")
    title = heading.get_text(" ", strip=True) if heading else ""
    parts = []
    for node in root.find_all(["h2", "h3", "p", "li"]):
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True))
        if len(text) >= 20:
            parts.append(("## " if node.name in {"h2", "h3"} else "") + text)
    body = "\n\n".join(parts)
    if not title or len(body) < 200:
        raise RuntimeError(f"Article extraction yielded insufficient content at {url}")
    path = workdir / "article.md"
    safe_title = title.replace('"', "'")
    path.write_text(
        f'---\ntitle: "{safe_title}"\nlanguage: {language}\nurl: "{canonical_url}"\n---\n\n# {title}\n\n{body}\n',
        encoding="utf-8",
    )
    return Article(html.unescape(title), language, url, canonical_url, body, path)
