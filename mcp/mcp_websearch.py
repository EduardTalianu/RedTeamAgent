# mcp_websearch.py - Fixed version with proper directory handling
import requests
import re
import os
import datetime
from typing import Dict, Any, Optional
from mcp_base import MCPTool

class McpWebsearch(MCPTool):
    """Fixed web search tool with proper directory creation."""
    
    def __init__(self):
        super().__init__()
        self.friendly_name = "Web Search"
        self.max_results = 5
        self.snippet_length = 2000
        
        # Create results directory with proper path handling
        self.results_dir = self._ensure_results_dir()
        
        # User agent for requests
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    
    def _ensure_results_dir(self):
        """Ensure results directory exists with proper Windows path handling."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            base_results_dir = os.path.join(script_dir, "..", "results")
            results_dir = os.path.join(base_results_dir, "websearch")
            
            # Create the directory if it doesn't exist
            os.makedirs(results_dir, exist_ok=True)
            
            # Test write permissions
            test_file = os.path.join(results_dir, "test_write.tmp")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                print(f"Web Search results directory ready: {results_dir}")
                return results_dir
            except Exception as e:
                print(f"Cannot write to results directory {results_dir}: {e}")
                # Fallback to temp directory
                import tempfile
                fallback_dir = os.path.join(tempfile.gettempdir(), "erag_websearch")
                os.makedirs(fallback_dir, exist_ok=True)
                print(f"Using fallback directory: {fallback_dir}")
                return fallback_dir
                
        except Exception as e:
            print(f"Error setting up results directory: {e}")
            import tempfile
            return tempfile.gettempdir()
    
    def get_description(self) -> str:
        return "Search the web for current information using DuckDuckGo with enhanced error handling."
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect web search requests in various formats."""
        
        # Check for XML format first (most specific)
        xml_patterns = [
            r'<tool>\s*<name>web[_ ]search</name>\s*<parameters>\s*<query>(.*?)</query>\s*</parameters>\s*</tool>',
            r'<tool>\s*<n>web[_ ]search</n>\s*<parameters>\s*<query>(.*?)</query>\s*</parameters>\s*</tool>',
            r'```xml.*?<tool>.*?<name>web[_ ]search</name>.*?<query>(.*?)</query>.*?</tool>.*?```'
        ]
        
        for pattern in xml_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                query = match.group(1).strip()
                if query:
                    print(f"Web Search detected XML query: {query}")
                    return {"query": query}
        
        # Check for text patterns (less specific)
        text_patterns = [
            r'search\s+for\s+(.+?)(?:\n|$|\.|,)',
            r'look\s+up\s+(.+?)(?:\n|$|\.|,)',
            r'find\s+information\s+about\s+(.+?)(?:\n|$|\.|,)',
            r'google\s+(.+?)(?:\n|$|\.|,)',
        ]
        
        for pattern in text_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
                if len(query) > 2 and len(query) < 200:  # Reasonable query length
                    print(f"Web Search detected text query: {query}")
                    return {"query": query}
        
        return None
    
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute web search with enhanced error handling."""
        query = params.get("query", "").strip()
        if not query:
            return "Error: Search query is required"
        
        print(f"Executing web search for: {query}")
        
        try:
            results = self._search_duckduckgo(query)
            if not results:
                return f"No search results found for: {query}"
            
            # Format results for LLM
            formatted_results = self._format_results(query, results)
            
            # Save to file with proper error handling
            self._safe_save_results(query, formatted_results)
            
            return formatted_results
            
        except Exception as e:
            error_msg = f"Search error: {str(e)}"
            print(error_msg)
            return error_msg
    
    def _search_duckduckgo(self, query: str) -> list:
        """Search using DuckDuckGo with retries and better error handling."""
        try:
            headers = {'User-Agent': self.user_agent}
            url = "https://html.duckduckgo.com/html/"
            
            # Try the search with timeout and retries
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    response = requests.post(
                        url, 
                        data={'q': query}, 
                        headers=headers, 
                        timeout=15,
                        allow_redirects=True
                    )
                    response.raise_for_status()
                    
                    # Parse results
                    results = self._parse_results(response.text)
                    if results:
                        print(f"Found {len(results)} results for query: {query}")
                        return results
                    else:
                        print(f"No results found in response for query: {query}")
                        return []
                        
                except requests.exceptions.Timeout:
                    print(f"Timeout on attempt {attempt + 1} for query: {query}")
                    if attempt < max_retries - 1:
                        continue
                    raise Exception("Search request timed out after retries")
                except requests.exceptions.RequestException as e:
                    print(f"Request error on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        continue
                    raise Exception(f"Search request failed: {e}")
                    
        except Exception as e:
            raise Exception(f"DuckDuckGo search failed: {str(e)}")
    
    def _parse_results(self, html_content: str) -> list:
        """Parse DuckDuckGo results with fallback methods."""
        results = []
        
        try:
            # Try BeautifulSoup first
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")
            
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
                    
        except ImportError:
            # Fallback to regex parsing
            print("BeautifulSoup not available, using regex parsing")
            results = self._parse_with_regex(html_content)
        except Exception as e:
            print(f"BeautifulSoup parsing failed: {e}, trying regex")
            results = self._parse_with_regex(html_content)
        
        return results
    
    def _parse_with_regex(self, html_content: str) -> list:
        """Fallback regex parsing for DuckDuckGo results."""
        results = []
        
        # Enhanced regex patterns for DuckDuckGo results
        link_patterns = [
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
            r'href="([^"]+)"[^>]*class="result__a"[^>]*>([^<]+)</a>'
        ]
        
        for pattern in link_patterns:
            matches = re.findall(pattern, html_content)
            for url, title in matches:
                if url.startswith('http') and title.strip():
                    results.append({
                        'title': title.strip(),
                        'url': url,
                        'snippet': ""  # Regex parsing doesn't easily get snippets
                    })
                    
                    if len(results) >= self.max_results:
                        break
            
            if results:  # If we found results with this pattern, stop
                break
        
        return results
    
    def _format_results(self, query: str, results: list) -> str:
        """Format search results for display."""
        if not results:
            return f"No results found for: {query}"
        
        lines = [f"Web Search Results for '{query}' ({len(results)} results):\n"]
        
        for i, result in enumerate(results, 1):
            title = result.get('title', 'No title')
            url = result.get('url', 'No URL')
            snippet = result.get('snippet', '').strip()
            
            lines.append(f"{i}. {title}")
            
            # Add snippet if available
            if snippet:
                # Truncate snippet if too long
                if len(snippet) > self.snippet_length:
                    snippet = snippet[:self.snippet_length] + "..."
                lines.append(f"   {snippet}")
            
            lines.append(f"   URL: {url}")
            lines.append("")  # Empty line between results
        
        return "\n".join(lines)
    
    def _safe_save_results(self, query: str, results: str):
        """Save search results with comprehensive error handling."""
        try:
            # Create safe filename
            safe_query = re.sub(r'[^\w\s-]', '', query).strip()
            safe_query = re.sub(r'[-\s]+', '-', safe_query)
            safe_query = safe_query[:30]  # Limit length
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"websearch_{timestamp}_{safe_query}.txt"
            filepath = os.path.join(self.results_dir, filename)
            
            # Ensure the directory still exists
            os.makedirs(self.results_dir, exist_ok=True)
            
            with open(filepath, 'w', encoding='utf-8', errors='ignore') as f:
                f.write(f"Web Search Results\n")
                f.write(f"Query: {query}\n")
                f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(results)
            
            print(f"Results saved to: {filepath}")
            
        except Exception as e:
            print(f"Error saving search results: {e}")
            # Try alternative location
            try:
                import tempfile
                temp_file = os.path.join(tempfile.gettempdir(), f"websearch_{timestamp}.txt")
                with open(temp_file, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(results)
                print(f"Results saved to temp location: {temp_file}")
            except Exception as e2:
                print(f"Failed to save to temp location: {e2}")
    
    def get_system_prompt(self) -> str:
        """Return system prompt for web search tool."""
        return (
            f"You have access to {self.friendly_name}. {self.description} "
            "Use this tool to find current information not in your training data.\n\n"
            "To use web search, include this EXACT XML format in your response:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>web_search</name>\n"
            "  <parameters>\n"
            "    <query>your search terms</query>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Examples:\n"
            "- Domain research: <tool><name>web_search</name><parameters><query>site:example.com OR \"example.com\"</query></parameters></tool>\n"
            "- Security search: <tool><name>web_search</name><parameters><query>\"target.com\" security vulnerabilities</query></parameters></tool>\n"
            "- Technology info: <tool><name>web_search</name><parameters><query>company technology stack information</query></parameters></tool>\n\n"
            "The search will return up to 5 relevant results with titles, snippets, and URLs. "
            f"Results are saved to: {self.results_dir}"
        )