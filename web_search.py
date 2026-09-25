"""Small, opt-in web search and page text fetcher."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import List
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


USER_AGENT = "DeepDeep/1.0 (local assistant)"
MAX_RESULTS = 5
MAX_PAGE_BYTES = 400_000
MAX_PAGE_TEXT = 6_000
CONNECTIVITY_TIMEOUT = 3


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


def _request(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=10) as response:
        return response.read(MAX_PAGE_BYTES)


def bing_is_available() -> bool:
    """Return whether the Bing search endpoint can be reached."""
    try:
        request = Request(
            "https://www.bing.com/search?q=DeepDeep",
            headers={"User-Agent": USER_AGENT},
        )
        with urlopen(request, timeout=CONNECTIVITY_TIMEOUT) as response:
            return 200 <= response.status < 400
    except OSError:
        return False


def search(query: str, limit: int = MAX_RESULTS) -> list[dict[str, str]]:
    """Search Bing's HTML results page and return title, URL, and snippet."""
    parser = _BingSearchParser()
    parser.feed(_request(f"https://www.bing.com/search?q={quote_plus(query)}").decode("utf-8", "ignore"))
    return parser.results[:limit]


class _BingSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.field: str | None = None
        self.result_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "li" and "b_algo" in classes:
            self.current = {"title": "", "url": "", "snippet": ""}
            self.result_depth = 1
        elif self.current and tag == "li":
            self.result_depth += 1
        elif self.current and tag == "h2":
            self.field = "title"
        elif self.current and tag == "a" and self.field == "title":
            self.current["url"] = attributes.get("href", "")
        elif self.current and tag == "p":
            self.field = "snippet"

    def handle_endtag(self, tag: str) -> None:
        if self.current and tag == "li":
            self.result_depth -= 1
            if self.result_depth == 0:
                self.results.append(self.current)
                self.current = None
        elif tag in {"a", "h2", "p"}:
            self.field = None

    def handle_data(self, data: str) -> None:
        if self.current and self.field:
            self.current[self.field] += " ".join(data.split())


def fetch_text(url: str) -> str:
    """Fetch a page and return a bounded, readable text representation."""
    raw = _request(url)
    parser = _TextParser()
    parser.feed(raw.decode("utf-8", "ignore"))
    return " ".join(parser.parts)[:MAX_PAGE_TEXT]


def collect(query: str, limit: int = MAX_RESULTS) -> list[dict[str, str]]:
    """Search and fetch pages, retaining results whose pages can be read."""
    results = search(query, limit)
    collected = []
    for result in results:
        try:
            text = fetch_text(result["url"])
        except (OSError, ValueError):
            text = ""
        result = {**result, "text": text or result["snippet"]}
        collected.append(result)
    return collected
