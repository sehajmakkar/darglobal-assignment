"""Turning CMS content into plain text for RAG.

Three shapes show up in DarGlobal's Strapi data:
- HTML strings (blog/press bodies, some descriptions) → `html_to_text`
- Strapi "blocks" rich text (insights: [{type: paragraph, children: [{text}]}]) → `blocks_to_text`
- arbitrary nested page-builder JSON (one-off templates) → `cms_text`
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from html import unescape

from selectolax.lexbor import LexborHTMLParser, LexborNode

from dgbot.domain.text import clean_text, dedupe_lines

_BLOCK_TAGS = frozenset(
    {"p", "div", "section", "article", "br", "tr", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}
)
_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})  # rendered like blocks
_DROP_TAGS = ("script", "style", "noscript", "iframe", "svg", "img", "video", "picture")


def html_to_text(html: str | None) -> str | None:
    """HTML → readable text: paragraphs as blank-line breaks, list items as '- item'."""
    if not html or not html.strip():
        return None
    if "<" not in html:  # plain text, but may still carry entities ("A &amp; B")
        return clean_text(unescape(html))
    tree = LexborHTMLParser(html)
    for tag in _DROP_TAGS:
        for node in tree.css(tag):
            node.decompose()
    root = tree.body or tree.root
    if root is None:
        return None
    parts: list[str] = []
    _walk(root, parts)
    return clean_text(unescape("".join(parts)))  # CMS bodies are sometimes double-encoded


def _walk(node: LexborNode, parts: list[str]) -> None:
    for child in node.iter(include_text=True):
        tag = child.tag
        if tag == "-text":
            parts.append(child.text(deep=False) or "")
            continue
        if tag == "li":
            parts.append("\n- ")
            _walk(child, parts)
            parts.append("\n")
        elif tag in _HEADINGS or tag in _BLOCK_TAGS:
            parts.append("\n\n")
            _walk(child, parts)
            parts.append("\n\n")
        else:
            _walk(child, parts)


def blocks_to_text(blocks: object) -> str | None:
    """Strapi v4 rich-text blocks → text (paragraphs, headings, lists)."""
    if not isinstance(blocks, list):
        return None
    out: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "list":
            out.append("\n".join(f"- {_inline(item)}" for item in block.get("children") or []))
        else:
            out.append(_inline(block))
    return clean_text("\n\n".join(p for p in out if p.strip()))


def _inline(node: object) -> str:
    if isinstance(node, dict):
        if "text" in node and isinstance(node["text"], str):
            return node["text"]
        return "".join(_inline(c) for c in node.get("children") or [])
    return ""


# ── generic page-builder text ────────────────────────────────────────────────

# Keys whose string values are human-readable content.
_CONTENT_KEY = re.compile(
    r"(title|heading|subheading|description|content|text|name|value|question|answer|"
    r"summary|body|paragraph|location|label_?text|caption_?text|info|detail|point|feature)",
    re.I,
)
# Subtrees that are never content: site chrome, SEO, media, links, versioning.
_SKIP_KEY = re.compile(
    r"^(globalData|SEO|seo|meta.*|localizations|versions|image|images|.*Image.*|.*image|"
    r"bgImage|.*Thumbnail.*|HeroBanner.*|logo|icon.*|video.*|file|brochure.*|"
    r"socialLinks|.*[Uu]rl|href|link|Link|slug|uniqueSlug|locale|vuid|id|"
    r"createdAt|updatedAt|publishedAt|ButtonTheme|target|events|isMobile|formats|"
    r"thankyou.*|leadForm.*|form.*|.*Form)$"
)
_MIN_LEN = 3


def cms_text(data: object, *, max_depth: int = 12) -> str | None:
    """All human-readable strings from nested CMS JSON, in document order, deduped."""
    lines = dedupe_lines([line for line in _strings(data, max_depth) if len(line) >= _MIN_LEN])
    return clean_text("\n".join(lines))


def _strings(node: object, depth: int, key: str = "") -> Iterator[str]:
    if depth < 0:
        return
    if isinstance(node, dict):
        if "mime" in node or "formats" in node:  # a media object
            return
        for k, v in node.items():
            if _SKIP_KEY.match(k):
                continue
            yield from _strings(v, depth - 1, k)
    elif isinstance(node, list):
        if node and isinstance(node[0], dict) and "type" in node[0] and "children" in node[0]:
            text = blocks_to_text(node)
            if text:
                yield from text.split("\n")
            return
        for item in node:
            yield from _strings(item, depth - 1, key)
    elif isinstance(node, str) and _CONTENT_KEY.search(key):
        text = html_to_text(node) if "<" in node else clean_text(node)
        if text and not text.startswith(("http://", "https://", "/")):
            yield from (line for line in text.split("\n") if line.strip())
