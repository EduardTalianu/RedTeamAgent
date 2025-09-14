# mcp_websearch.py - Simplified web search tool
import requests
import re
import os
import datetime
from typing import Dict, Any, Optional
from mcp_base import MCPTool

class McpWebsearch(MCPTool):
    """Simplified web search tool using DuckDuckGo."""
    
    def __init__(self):
        super().__init__()
        self.friendly_name = "Web Search"
        self.max_results = 5
        self.snippet_length = 2000  # Reasonable length for LLM
        
        # Create results directory
        self.results_dir = os.path.join("results", "websearch")
        os.makedirs(self.results_dir, exist_ok=True)
        
        # User agent for requests
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    
    def get_description(self) -> str:
        return "Search the web for current information using DuckDuckGo."
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect web search requests in various formats."""
        
        # Check for XML format first
        xml_match = re.search(r'<tool>\s*<name>web[_ ]search</name>\s*<parameters>\s*<query>(.*?)</query>\s*</parameters>\s*</tool>', 
                             text, re.IGNORECASE | re.DOTALL)
        if xml_match:
            return {"query": xml_match.group(1).strip()}
        
        # Check for simple XML format
        simple_xml = re.search(r'```xml.*?<tool>.*?<name>web[_ ]search</name>.*?<query>(.*?)</query>.*?</tool>.*?```', 
                              text, re.IGNORECASE | re.DOTALL)
        if simple_xml:
            return {"query": simple_xml.group(1).strip()}
        
        # Check for text patterns
        patterns = [
            r'search\s+for\s+(.+?)(?:\n|$|\.|,)',
            r'look\s+up\s+(.+?)(?:\n|$|\.|,)',
            r'find\s+information\s+about\s+(.+?)(?:\n|$|\.|,)',
            r'google\s+(.+?)(?:\n|$|\.|,)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
                if len(query) > 2:  # Avoid very short queries
                    return {"query": query}
        
        return None
    
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute web search."""
        query = params.get("query", "").strip()
        if not query:
            return "Error: Search query is required"
        
        try:
            results = self._search_duckduckgo(query)
            if not results:
                return f"No search results found for: {query}"
            
            # Format results for LLM
            formatted_results = self._format_results(query, results)
            
            # Save to file
            self._save_results(query, formatted_results)
            
            return formatted_results
            
        except Exception as e:
            return f"Search error: {str(e)}"
    
    def _search_duckduckgo(self, query: str) -> list:
        """Search using DuckDuckGo HTML interface."""
        try:
            headers = {'User-Agent': self.user_agent}
            url = "https://html.duckduckgo.com/html/"
            
            response = requests.post(url, data={'q': query}, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse results using BeautifulSoup if available, otherwise regex
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "html.parser")
                return self._parse_with_bs4(soup)
            except ImportError:
                # Fallback to regex parsing
                return self._parse_with_regex(response.text)
                
        except Exception as e:
            raise Exception(f"DuckDuckGo search failed: {str(e)}")
    
    def _parse_with_bs4(self, soup):
        """Parse DuckDuckGo results using BeautifulSoup."""
        results = []
        
        # Find result links
        for link in soup.select("a.result__a"):
            title = link.get_text().strip()
            url = link.get('href', '')
            
            if not url.startswith('http'):
                continue
                
            # Find snippet
            snippet = ""
            parent = link.find_parent()
            if parent:
                snippet_elem = parent.find("a", class_="result__snippet")
                if snippet_elem:
                    snippet = snippet_elem.get_text().strip()
            
            results.append({
                'title': title,
                'url': url,
                'snippet': snippet
            })
            
            if len(results) >= self.max_results:
                break
        
        return results
    
    def _parse_with_regex(self, html_content):
        """Fallback regex parsing for DuckDuckGo results."""
        results = []
        
        # Regex patterns for DuckDuckGo results
        link_pattern = r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>'
        matches = re.findall(link_pattern, html_content)
        
        for url, title in matches[:self.max_results]:
            if url.startswith('http'):
                results.append({
                    'title': title.strip(),
                    'url': url,
                    'snippet': ""  # Regex parsing doesn't easily get snippets
                })
        
        return results
    
    def _format_results(self, query: str, results: list) -> str:
        """Format search results for display."""
        if not results:
            return f"No results found for: {query}"
        
        lines = [f"Web Search Results for '{query}':\n"]
        
        for i, result in enumerate(results, 1):
            lines.append(f"{i}. {result.get('title', 'No title')}")
            
            # Add snippet if available
            snippet = result.get('snippet', '').strip()
            if snippet:
                # Truncate snippet if too long
                if len(snippet) > self.snippet_length:
                    snippet = snippet[:self.snippet_length] + "..."
                lines.append(f"   {snippet}")
            
            lines.append(f"   URL: {result.get('url', 'No URL')}")
            lines.append("")  # Empty line between results
        
        return "\n".join(lines)
    
    def _save_results(self, query: str, results: str):
        """Save search results to file."""
        try:
            # Create safe filename
            safe_query = re.sub(r'[^\w\s-]', '', query).strip()
            safe_query = re.sub(r'[-\s]+', '-', safe_query)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"websearch_{timestamp}_{safe_query[:30]}.txt"
            filepath = os.path.join(self.results_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Web Search Results\n")
                f.write(f"Query: {query}\n")
                f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(results)
            
        except Exception as e:
            print(f"Error saving search results: {e}")
    
    def get_system_prompt(self) -> str:
        """Return system prompt for web search tool."""
        return (
            f"You have access to {self.friendly_name}. {self.description} "
            "Use this tool to find current information not in your training data.\n\n"
            "To use web search, include this XML in your response:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>web_search</name>\n"
            "  <parameters>\n"
            "    <query>your search terms</query>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Examples:\n"
            "- Latest news: <tool><name>web_search</name><parameters><query>latest AI news 2024</query></parameters></tool>\n"
            "- Research topic: <tool><name>web_search</name><parameters><query>renewable energy trends</query></parameters></tool>\n"
            "- Find information: <tool><name>web_search</name><parameters><query>Python 3.12 new features</query></parameters></tool>\n\n"
            "The search will return up to 5 relevant results with titles, snippets, and URLs. "
            "Results are automatically saved to the results/websearch/ directory for reference."
        )