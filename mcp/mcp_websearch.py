# mcp_websearch.py
import requests
import json
import re
import xml.etree.ElementTree as ET
import os
import time
import datetime
from typing import Dict, Any, List, Optional, Tuple
from mcp_base import MCPTool

class McpWebsearch(MCPTool):
    """MCP-compliant web search tool with XML parsing support and results saving."""
    
    def __init__(self):
        super().__init__()
        self.api_key = None  # Set your API key here
        self.search_engine = "duckduckgo"  # or "google", "bing"
        self.friendly_name = "Web Search"  # User-friendly name for the tool
        self.max_results = 5
        self.last_query = None
        self.last_results = None
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.96 Safari/537.36'
        ]
        # Create results directory structure
        self.results_dir = "results"
        self.websearch_results_dir = os.path.join(self.results_dir, "websearch")
        os.makedirs(self.websearch_results_dir, exist_ok=True)
        # Set snippet length for LLM (5000 characters as requested)
        self.llm_snippet_length = 5000
    
    def get_description(self) -> str:
        return "Search the web for information using various search engines."
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query"
                },
                "engine": {
                    "type": "string",
                    "description": "Search engine to use",
                    "enum": ["duckduckgo", "google", "bing"],
                    "default": "duckduckgo"
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                },
                "region": {
                    "type": "string",
                    "description": "Region for search results",
                    "default": "us-en"
                }
            },
            "required": ["query"]
        }
    
    def get_capabilities(self) -> List[str]:
        return [
            "web_search",
            "information_retrieval",
            "real_time_data",
            "news_search",
            "image_search",
            "video_search"
        ]
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text is requesting a web search, including XML format."""
        # First try to detect XML format
        xml_pattern = r'```xml\s*\n*\s*(<tool>.*?</tool>)\s*\n*\s*```'
        match = re.search(xml_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(1))
        
        # Try simple format without code block
        simple_pattern = r'(<tool>.*?</tool>)'
        match = re.search(simple_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(0))
        
        # Try XML without proper tags
        fallback_pattern = r'<tool>.*?</tool>'
        match = re.search(fallback_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(0))
        
        # Then try simple text patterns
        search_patterns = [
            r'search\s+for\s+(.+)',
            r'find\s+information\s+about\s+(.+)',
            r'look\s+up\s+(.+)',
            r'what\s+is\s+(.+)',
            r'who\s+is\s+(.+)',
            r'google\s+(.+)'
        ]
        
        for pattern in search_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return {
                    "query": match.group(1).strip(),
                    "engine": "duckduckgo",
                    "num_results": 5
                }
        
        return None
    
    def _parse_tool_command(self, xml_str: str) -> Optional[Dict[str, Any]]:
        """Parse an XML tool command and extract parameters."""
        try:
            root = ET.fromstring(xml_str)
            
            # Validate the tool name - accept both "web_search" and "web search"
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
                    # Try alternative format: <parameter_name>query</parameter_name><value>value</value>
                    param_names = params_elem.findall('parameter_name')
                    param_values = params_elem.findall('value')
                    
                    for i, name_elem in enumerate(param_names):
                        if i < len(param_values) and name_elem.text and name_elem.text.lower() == 'query':
                            query = param_values[i].text.strip() if param_values[i] else ""
                            break
                    
                    # Another alternative format: <parameter name="query">value</parameter>
                    param_elems = params_elem.findall('parameter')
                    for param in param_elems:
                        if param.get('name', '').lower() == 'query' and param.text:
                            query = param.text.strip()
                            break
                
                if query and len(query) > 2:
                    return {
                        "query": query,
                        "engine": "duckduckgo",
                        "num_results": 5
                    }
                        
            return None
                        
        except Exception as e:
            print(f"Error parsing XML: {str(e)}")
            return None
    
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute web search with MCP parameters."""
        query = params.get("query", "")
        engine = params.get("engine", "duckduckgo")
        num_results = params.get("num_results", 5)
        region = params.get("region", "us-en")
        
        if not query:
            return "Error: Query parameter is required"
        
        self.last_query = query
        
        if engine == "duckduckgo":
            search_results = self._search_duckduckgo(query, num_results)
        elif engine == "google":
            search_results = self._search_google(query, num_results, region)
        elif engine == "bing":
            search_results = self._search_bing(query, num_results, region)
        else:
            return f"Unsupported search engine: {engine}"
        
        # Format results for LLM (with truncated snippets)
        llm_result = self._format_results_for_llm(query, search_results)
        
        # Format results for file saving (with full snippets)
        file_result = self._format_results_for_file(query, search_results)
        
        # Save full results to file
        self._save_results(query, file_result)
        
        # Return truncated results to LLM
        return llm_result
    
    def _search_duckduckgo(self, query: str, num_results: int) -> list:
        """Search using DuckDuckGo HTML scraping (no API key needed)."""
        try:
            headers = {'User-Agent': self.user_agents[0]}
            url = "https://html.duckduckgo.com/html/"
            resp = requests.post(url, data={'q': query}, headers=headers, timeout=8)
            resp.raise_for_status()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            
            # Find result elements
            anchors = soup.select("a.result__a")
            if not anchors:
                anchors = [a for a in soup.find_all("a", href=True) 
                          if a['href'].startswith("http") and a.get_text().strip()]
            
            for a in anchors[:num_results]:
                title = a.get_text().strip()
                href = a['href']
                snippet = ""
                
                # Try to find a sibling snippet
                parent = a.find_parent()
                if parent:
                    para = parent.find("a", class_="result__snippet") or \
                           parent.find("div", class_="result__snippet") or \
                           parent.find("p")
                    if para:
                        snippet = para.get_text().strip()
                
                results.append({'title': title, 'snippet': snippet, 'url': href})
            
            # Deduplicate results
            seen = set()
            final_results = []
            for r in results:
                if r['url'] not in seen:
                    seen.add(r['url'])
                    final_results.append(r)
            
            self.last_results = final_results
            return final_results
            
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def _search_google(self, query: str, num_results: int, region: str) -> list:
        """Search using Google (requires API key)."""
        if not self.api_key:
            print("Google search requires an API key")
            return []
        
        try:
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                "key": self.api_key,
                "cx": "YOUR_SEARCH_ENGINE_ID",  # Set your search engine ID
                "q": query,
                "num": num_results,
                "gl": region.split("-")[0]
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if "items" in data:
                for item in data["items"]:
                    results.append({
                        'title': item['title'],
                        'snippet': item.get('snippet', ''),
                        'url': item['link']
                    })
            
            self.last_results = results
            return results
            
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def _search_bing(self, query: str, num_results: int, region: str) -> list:
        """Search using Bing (requires API key)."""
        if not self.api_key:
            print("Bing search requires an API key")
            return []
        
        try:
            url = "https://api.bing.microsoft.com/v7.0/search"
            headers = {"Ocp-Apim-Subscription-Key": self.api_key}
            params = {
                "q": query,
                "count": num_results,
                "mkt": region
            }
            
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if "webPages" in data and "value" in data["webPages"]:
                for item in data["webPages"]["value"]:
                    results.append({
                        'title': item['name'],
                        'snippet': item.get('snippet', ''),
                        'url': item['url']
                    })
            
            self.last_results = results
            return results
            
        except Exception as e:
            print(f"Search error: {str(e)}")
            return []
    
    def _format_results_for_llm(self, query: str, results: list) -> str:
        """Format search results for LLM (with truncated snippets)."""
        lines = [f"Web Search Results for '{query}':\n"]
        for i, r in enumerate(results[:self.max_results], 1):
            lines.append(f"{i}. {r.get('title', 'No title')}\n")
            snippet = r.get('snippet') or ""
            # Truncate snippet to first 5000 characters for LLM
            if len(snippet) > self.llm_snippet_length:
                snippet = snippet[:self.llm_snippet_length] + "..."
            lines.append(f"   {snippet}\n")
            lines.append(f"   URL: {r.get('url', '')}\n\n")
        return "\n".join(lines)
    
    def _format_results_for_file(self, query: str, results: list) -> str:
        """Format search results for file saving (with full snippets)."""
        lines = [f"Web Search Results for '{query}':\n"]
        for i, r in enumerate(results[:self.max_results], 1):
            lines.append(f"{i}. {r.get('title', 'No title')}\n")
            snippet = r.get('snippet') or ""
            # Use full snippet for file saving
            lines.append(f"   {snippet}\n")
            lines.append(f"   URL: {r.get('url', '')}\n\n")
        return "\n".join(lines)
    
    def _save_results(self, query: str, result: str):
        """Save results to a file in the results/websearch directory."""
        try:
            # Create a safe filename from the query
            safe_query = re.sub(r'[^\w\s-]', '', query).strip()
            safe_query = re.sub(r'[-\s]+', '-', safe_query)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"websearch_{timestamp}_{safe_query[:50]}.txt"
            filepath = os.path.join(self.websearch_results_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Tool: Web Search\n")
                f.write(f"Query: {query}\n")
                f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(result)
            
            print(f"Websearch results saved to: {filepath}")
        except Exception as e:
            print(f"Error saving websearch results: {str(e)}")
    
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
            "Examples:\n"
            "1. To search for the latest Python version:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>web_search</name>\n"
            "  <parameters>\n"
            "    <query>latest Python version 2023</query>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "2. To find information about a recent event:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>web_search</name>\n"
            "  <parameters>\n"
            "    <query>latest AI breakthroughs 2023</query>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Only use this format when you actually want to execute the tool. "
            "Do not include it in your thinking process or examples unless you want it to be executed. "
            "The search results will be automatically executed and provided back to you. "
            "Use this tool when you need up-to-date information or specific facts not in your training data. "
            "The tool will return a formatted list of search results with titles, snippets (first 5000 characters), and URLs. "
            "You can then use this information to answer the user's question. "
            "Be specific with your search queries to get the most relevant results. "
            "Note: The tool uses DuckDuckGo by default which doesn't require an API key. "
            "All results are saved to the results/websearch/ directory with full snippets for later reference."
        )