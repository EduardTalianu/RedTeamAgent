#!/usr/bin/env python3
"""
Robust web search tool for LLM integration.
Tries: duckduckgo_search (DDGS / ddg), then DuckDuckGo HTML scrape, then googlesearch fallback.
Returns a formatted string (suitable for LLM) and keeps structured results in self.last_results.
"""

import re
import time
import random
import requests
from bs4 import BeautifulSoup
import importlib
import traceback

# Optional imports (set flags)
try:
    from duckduckgo_search import DDGS, ddg  # newer versions may expose ddg
    DUCKDUCKGO_AVAILABLE = True
except Exception:
    try:
        # try to import just ddg if present
        from duckduckgo_search import ddg
        DDGS = None
        DUCKDUCKGO_AVAILABLE = True
    except Exception:
        DUCKDUCKGO_AVAILABLE = False

try:
    from googlesearch import search as google_search
    GOOGLE_AVAILABLE = True
except Exception:
    google_search = None
    GOOGLE_AVAILABLE = False

class Web_search:
    def __init__(self):
        self.name = "Web Search"
        self.description = "Search the web using DuckDuckGo (preferred) with Google fallback."
        self.max_results = 5
        self.last_query = None
        self.last_results = None   # list of dicts: {title, snippet, url}
        self.last_search_time = 0
        self.min_search_interval = 1.0
        self.retry_count = 2
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36'
        ]

    def detect_request(self, text: str):
        # same detection patterns as before
        patterns = [
            r'search\s+(?:for\s+)?["\']?(.+?)["\']?(?:\s+on\s+the\s+web|\s+online)?',
            r'look\s+up\s+["\']?(.+?)["\']?',
            r'find\s+(?:information\s+)?(?:about|on)\s+["\']?(.+?)["\']?',
            r'what\s+(?:is|are)\s+["\']?(.+?)["\']?',
            r'who\s+is\s+["\']?(.+?)["\']?',
            r'when\s+(?:did|was)\s+["\']?(.+?)["\']?',
            r'where\s+(?:is|are)\s+["\']?(.+?)["\']?',
            r'why\s+(?:is|are)\s+["\']?(.+?)["\']?',
            r'how\s+(?:to|do|does|did)\s+["\']?(.+?)["\']?'
        ]
        for p in patterns:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                q = re.sub(r'[^\w\s]', '', m.group(1)).strip()
                if q and len(q) > 2:
                    return q
        return None

    def execute(self, query: str) -> str:
        self.last_query = query
        # simple rate limiting
        now = time.time()
        if now - self.last_search_time < self.min_search_interval:
            time.sleep(self.min_search_interval - (now - self.last_search_time))
        self.last_search_time = time.time()

        errors = []

        # Try DuckDuckGo library(s)
        if DUCKDUCKGO_AVAILABLE:
            for attempt in range(self.retry_count):
                try:
                    results = self._search_duckduckgo(query)
                    if results:
                        self.last_results = results
                        return self._format_results(query, results)
                except Exception as e:
                    errors.append(f"DuckDuckGo attempt {attempt+1} error: {e}")
                    time.sleep(0.5)

        # Try DuckDuckGo HTML scrape (best-effort)
        try:
            results = self._search_ddg_html(query)
            if results:
                self.last_results = results
                return self._format_results(query, results)
        except Exception as e:
            errors.append(f"DDG HTML scrape error: {e}")

        # Google fallback (best-effort)
        if GOOGLE_AVAILABLE:
            for attempt in range(self.retry_count):
                try:
                    results = self._search_google(query)
                    if results:
                        self.last_results = results
                        return self._format_results(query, results)
                except Exception as e:
                    errors.append(f"Google attempt {attempt+1} error: {e}")
                    time.sleep(0.5)

        # nothing worked
        err_text = "\n".join(errors) if errors else "No methods available (no network or no packages installed)."
        return f"Error: All search methods failed for query: {query}\nDetails:\n{err_text}"

    def _search_duckduckgo(self, query: str):
        """Try DDGS() generator or ddg() function depending on availability."""
        out = []
        # prefer DDGS context manager if available
        try:
            if 'DDGS' in globals() and DDGS is not None:
                with DDGS() as ddgs:
                    gen = ddgs.text(query, max_results=self.max_results)
                    for r in gen:
                        title = r.get('title') or r.get('headline') or ''
                        snippet = r.get('body') or r.get('snippet') or ''
                        href = r.get('href') or r.get('url') or r.get('link') or ''
                        out.append({'title': title.strip(), 'snippet': snippet.strip(), 'url': href})
            else:
                # try ddg() function (returns a list of dicts)
                raw = ddg(query, max_results=self.max_results)
                for r in raw:
                    title = r.get('title') or r.get('headline') or ''
                    snippet = r.get('body') or r.get('snippet') or ''
                    href = r.get('href') or r.get('url') or r.get('link') or ''
                    out.append({'title': title.strip(), 'snippet': snippet.strip(), 'url': href})
        except Exception as e:
            # bubble up to allow retries / fallbacks
            raise

        # filter empty URLs and deduplicate
        final = []
        seen = set()
        for item in out:
            u = (item.get('url') or '').strip()
            if not u or u in seen:
                continue
            seen.add(u)
            final.append({
                'title': item.get('title') or u,
                'snippet': item.get('snippet') or '',
                'url': u
            })
        return final

    def _search_ddg_html(self, query: str):
        """Best-effort scraping of DuckDuckGo HTML results (no client lib needed)."""
        headers = {'User-Agent': random.choice(self.user_agents)}
        url = "https://html.duckduckgo.com/html/"
        resp = requests.post(url, data={'q': query}, headers=headers, timeout=8)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        # Try a few strategies to find anchors that look like results
        # 1) anchors with class result__a
        anchors = soup.select("a.result__a")
        if not anchors:
            anchors = [a for a in soup.find_all("a", href=True) if a['href'].startswith("http") and a.get_text().strip()]
        for a in anchors[: self.max_results]:
            title = a.get_text().strip()
            href = a['href']
            snippet = ""
            # try to find a sibling snippet
            parent = a.find_parent()
            if parent:
                para = parent.find("a", class_="result__snippet") or parent.find("div", class_="result__snippet") or parent.find("p")
                if para:
                    snippet = para.get_text().strip()
            results.append({'title': title, 'snippet': snippet, 'url': href})
        # dedupe
        seen = set()
        final = []
        for r in results:
            if r['url'] not in seen:
                seen.add(r['url'])
                final.append(r)
        return final

    def _search_google(self, query: str):
        """Use googlesearch.search as fallback. The googlesearch API is fragile; handle multiple signatures."""
        out = []
        # try typical signatures
        links = None
        try:
            # common signature: search(query, num=10, stop=None, pause=2.0)
            links = list(google_search(query, num=self.max_results, stop=self.max_results, pause=2.0))
        except TypeError:
            try:
                # another variant: search(query, num_results=10)
                links = list(google_search(query, num_results=self.max_results))
            except Exception:
                # last resort: try with only query and pause
                links = list(google_search(query, pause=2.0))
        # if links is None or empty, return empty
        if not links:
            return []
        # links may already be strings (urls)
        for url in links[: self.max_results]:
            title = "No title"
            snippet = ""
            try:
                resp = requests.get(url, headers={'User-Agent': random.choice(self.user_agents)}, timeout=5)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "html.parser")
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()
                meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
                if meta and meta.get("content"):
                    snippet = meta.get("content").strip()
                else:
                    p = soup.find("p")
                    if p:
                        snippet = p.get_text().strip()[:300]
            except Exception:
                # keep defaults
                pass
            out.append({'title': title, 'snippet': snippet, 'url': url})
        return out

    def _format_results(self, query: str, results: list) -> str:
        lines = [f"Web Search Results for '{query}':\n"]
        for i, r in enumerate(results[: self.max_results], 1):
            lines.append(f"{i}. {r.get('title', 'No title')}\n")
            snippet = r.get('snippet') or ""
            if len(snippet) > 300:
                snippet = snippet[:300] + "..."
            lines.append(f"   {snippet}\n")
            lines.append(f"   URL: {r.get('url', '')}\n\n")
        return "\n".join(lines)


# simple local test runner when executed directly
if __name__ == "__main__":
    w = Web_search()
    print(w.execute("latest Python version"))
