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
import xml.etree.ElementTree as ET

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
        self.enabled = False  # This is required by the GUI
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
        """Detect if the AI is requesting to execute a web search using XML format."""
        # Look for structured XML tool invocation
        xml_pattern = r'```xml\s*\n*\s*(<tool>.*?</tool>)\s*\n*\s*```'
        match = re.search(xml_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(1))
        
        # Fallback to simpler format without code block
        simple_pattern = r'(<tool>.*?</tool>)'
        match = re.search(simple_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(0))
        
        # Try to detect XML without proper tags
        fallback_pattern = r'<tool>.*?</tool>'
        match = re.search(fallback_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(0))
        
        return None
    
    def _parse_tool_command(self, xml_str: str):
        """Parse an XML tool command and extract parameters."""
        try:
            root = ET.fromstring(xml_str)
            
            # Validate the tool name - accept both "web_search" and "Web Search"
            tool_name = root.find('name')
            if tool_name is None or tool_name.text.lower() not in ['web_search', 'web search']:
                return None
                
            # Extract and validate parameters
            query = None
            params_elem = root.find('parameters')
            if params_elem is not None:
                # Try the expected format: <query>value</query>
                query_elem = params_elem.find('query')
                if query_elem is not None and query_elem.text:
                    query = query_elem.text.strip()
                else:
                    # Try alternative format: <parameter_name>query</parameter_name><parameter_value>value</parameter_value>
                    param_names = params_elem.findall('parameter_name')
                    param_values = params_elem.findall('parameter_value')
                    
                    if param_names and not param_values:
                        # Handle case where query is directly in parameter_name
                        if len(param_names) == 1:
                            query = param_names[0].text.strip()
                    else:
                        for i, name_elem in enumerate(param_names):
                            if i < len(param_values) and name_elem.text and name_elem.text.lower() == 'query':
                                query = param_values[i].text.strip()
                                break
                    
                    # Another alternative format: <parameter name="query">value</parameter>
                    param_elems = params_elem.findall('parameter')
                    for param in param_elems:
                        if param.get('name', '').lower() == 'query' and param.text:
                            query = param.text.strip()
                            break
                    
                    # Yet another alternative: <parameter_name>actual query text</parameter_name>
                    if not query and param_names:
                        for name_elem in param_names:
                            if name_elem.text and name_elem.text.lower() not in ['query', 'command']:
                                query = name_elem.text.strip()
                                break
            
            if query and len(query) > 2:
                return query
                    
        except Exception as e:
            print(f"Error parsing XML: {str(e)}")
        
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
    
    def get_system_prompt(self) -> str:
        """Return the system prompt for this tool."""
        return (
            f"You have access to {self.name}. {self.description} "
            "When you need to search the web for current information, use the following XML format:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>web_search</name>\n"
            "  <parameters>\n"
            "    <query>your search query</query>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Only use this format when you actually want to execute the tool. "
            "Do not include it in your thinking process or examples unless you want it to be executed. "
            "The search results will be automatically executed and provided back to you. "
            "Use this tool when you need up-to-date information or specific facts not in your training data. "
            "The tool will return a formatted list of search results with titles, snippets, and URLs. "
            "You can then use this information to answer the user's question. "
            "Be specific with your search queries to get the most relevant results. "
            "Note: The tool has built-in rate limiting and will automatically retry if a search fails."
        )

# simple local test runner when executed directly
if __name__ == "__main__":
    w = Web_search()
    print(w.execute("latest Python version"))