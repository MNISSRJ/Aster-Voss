"""Fetch readable article text for on-demand Radar questions."""
from __future__ import annotations

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAX_HTML_BYTES = 1_500_000
MAX_ARTICLE_CHARS = 12_000
USER_AGENT = "Aster-Voss-ArticleReader/1.0"


class _ArticleParser(HTMLParser):
    _SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "button"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.body = []
        self.article = []
        self.main = []
        self.stack = []
        self.skip_depth = 0
        self.article_depth = 0
        self.main_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        skipped = self.skip_depth > 0 or tag in self._SKIP
        self.stack.append((tag, skipped))
        if skipped:
            self.skip_depth += 1
        if tag == "article":
            self.article_depth += 1
        if tag == "main":
            self.main_depth += 1

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, -1, -1):
            stack_tag, skipped = self.stack[index]
            if stack_tag == tag:
                removed = self.stack[index:]
                del self.stack[index:]
                self.skip_depth -= sum(1 for _, was_skipped in removed if was_skipped)
                self.article_depth -= sum(1 for name, _ in removed if name == "article")
                self.main_depth -= sum(1 for name, _ in removed if name == "main")
                self.skip_depth = max(0, self.skip_depth)
                self.article_depth = max(0, self.article_depth)
                self.main_depth = max(0, self.main_depth)
                break

    def handle_data(self, data):
        value = " ".join(data.split())
        if not value or self.skip_depth:
            return
        self.body.append(value)
        if self.main_depth:
            self.main.append(value)
        if self.article_depth:
            self.article.append(value)


def extract_article_text(markup: str) -> str:
    parser = _ArticleParser()
    try:
        parser.feed(markup or "")
        parser.close()
    except Exception:
        pass
    choices = (parser.article, parser.main, parser.body)
    text = next((" ".join(parts) for parts in choices if len(" ".join(parts)) >= 300), "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:MAX_ARTICLE_CHARS]


def _validate_public_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("unsupported article URL")
    host = parsed.hostname.rstrip(".").lower()
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("non-public article host")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        addresses = {
            ipaddress.ip_address(result[4][0])
            for result in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
        }
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("non-public article address")


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        _validate_public_url(newurl)
        return super().redirect_request(request, response, code, message, headers, newurl)


def fetch_article_text(url: str) -> str:
    """Fetch a public HTML article on demand; return empty text on unsupported/unavailable sources."""
    try:
        _validate_public_url(url)
        opener = urllib.request.build_opener(_SafeRedirectHandler())
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
        with opener.open(request, timeout=7) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "html" not in content_type:
                return ""
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_HTML_BYTES:
                return ""
            markup = response.read(MAX_HTML_BYTES + 1)
            if len(markup) > MAX_HTML_BYTES:
                return ""
            charset = response.headers.get_content_charset() or "utf-8"
            return extract_article_text(markup.decode(charset, errors="replace"))
    except (OSError, ValueError, urllib.error.URLError, UnicodeError, OverflowError):
        return ""
