#!/usr/bin/env python3
"""
Web search tool plugin for EragAPI Chat Client.
Allows the AI to search the web using DuckDuckGo with Google fallback.
"""

import re
import time
import random
import requests
from bs4 import BeautifulSoup

# Try to import DuckDuckGo search
try:
    from duckduckgo_search import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False
    print("Warning: duckduckgo-search not available. Install with: pip install duckduckgo-search==3.8.5")

# Try to import Google search
try:
    from googlesearch import search as google_search
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    print("Warning: googlesearch-python not available. Install with: pip install googlesearch-python")

class Web_search:
    """Web search tool implementation."""
    
    def __init__(self):
        self.name = "Web Search"
        self.description = "Search the web for information using DuckDuckGo with Google fallback."
        self.enabled = False  # This attribute is required by the GUI
        self.max_results = 5  # Limit results to avoid too much data
        self.last_query = None  # Store the last query for debugging
        self.last_results = None  # Store the last results for debugging
        self.last_search_time = 0  # Track last search time for rate limiting
        self.min_search_interval = 5  # Minimum seconds between searches (rate limiting)
        self.retry_count = 2  # Number of retries for failed searches
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
        ]
    
    def detect_request(self, text: str):
        """Detect if the AI is requesting to search the web."""
        # Pattern 1: Look for explicit search commands
        search_patterns = [
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
        
        for pattern in search_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
                # Clean up the query
                query = re.sub(r'[^\w\s]', '', query)
                if query and len(query) > 2:  # Ensure query is meaningful
                    return query
        
        # Pattern 2: Look for questions that might need web search
        question_patterns = [
            r'can\s+you\s+(?:search|find|look\s+up)\s+(?:for\s+)?(.+)',
            r'i\s+(?:need|want)\s+(?:information|to\s+know)\s+about\s+(.+)',
            r'tell\s+me\s+about\s+(.+)'
        ]
        
        for pattern in question_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                query = match.group(1).strip()
                # Clean up the query
                query = re.sub(r'[^\w\s]', '', query)
                if query and len(query) > 2:  # Ensure query is meaningful
                    return query
        
        return None
    
    def execute(self, query: str) -> str:
        """Execute a web search and return formatted results."""
        self.last_query = query  # Store for debugging
        
        # Rate limiting - wait if needed
        current_time = time.time()
        time_since_last_search = current_time - self.last_search_time
        if time_since_last_search < self.min_search_interval:
            wait_time = self.min_search_interval - time_since_last_search
            time.sleep(wait_time)
        
        self.last_search_time = time.time()
        
        # Try DuckDuckGo first if available
        if DUCKDUCKGO_AVAILABLE:
            for attempt in range(self.retry_count):
                try:
                    result = self._search_duckduckgo(query)
                    if result and not result.startswith("Error"):
                        self.last_results = result
                        return result
                except Exception as e:
                    print(f"DuckDuckGo search attempt {attempt + 1} failed: {str(e)}")
                    if attempt < self.retry_count - 1:
                        time.sleep(2)  # Wait before retrying
        
        # If DuckDuckGo fails or not available, try Google if available
        if GOOGLE_AVAILABLE:
            for attempt in range(self.retry_count):
                try:
                    result = self._search_google(query)
                    if result and not result.startswith("Error"):
                        self.last_results = result
                        return result
                except Exception as e:
                    print(f"Google search attempt {attempt + 1} failed: {str(e)}")
                    if attempt < self.retry_count - 1:
                        time.sleep(2)  # Wait before retrying
        
        # If all else fails, return an error
        return f"Error: All search methods failed for query: {query}"
    
    def _search_duckduckgo(self, query: str) -> str:
        """Search using DuckDuckGo."""
        try:
            with DDGS() as ddgs:
                # Use the correct API for the pinned version
                results = list(ddgs.text(query, max_results=self.max_results))
            
            if not results:
                return f"No search results found for: {query}"
            
            # Format the results
            formatted_results = [f"Web Search Results for '{query}':\n"]
            
            for i, result in enumerate(results, 1):
                # In version 3.8.5, results are dictionaries with 'title', 'body', and 'href'
                title = result.get('title', 'No title')
                snippet = result.get('body', 'No description available')
                link = result.get('href', '#')
                
                # Truncate long snippets
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                
                formatted_results.append(f"{i}. {title}\n")
                formatted_results.append(f"   {snippet}\n")
                formatted_results.append(f"   URL: {link}\n\n")
            
            return "\n".join(formatted_results)
            
        except Exception as e:
            return f"Error during DuckDuckGo search: {str(e)}"
    
    def _search_google(self, query: str) -> str:
        """Search using Google as a fallback."""
        try:
            # Get random user agent
            headers = {'User-Agent': random.choice(self.user_agents)}
            
            # Perform Google search - only get URLs
            links = list(google_search(query, num_results=self.max_results, 
                                     stop=self.max_results, pause=2.0, 
                                     headers=headers))
            
            if not links:
                return f"No search results found for: {query}"
            
            # Format the results
            formatted_results = [f"Web Search Results for '{query}':\n"]
            
            for i, url in enumerate(links, 1):
                title = "No title"
                snippet = "No description available"
                
                # Try to fetch the page to get title and snippet
                try:
                    response = requests.get(url, headers=headers, timeout=5)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Get title
                    if soup.title and soup.title.string:
                        title = soup.title.string
                    
                    # Try to get a snippet from meta description or first paragraph
                    meta_desc = soup.find('meta', attrs={'name': 'description'})
                    if meta_desc and meta_desc.get('content'):
                        snippet = meta_desc.get('content')
                    else:
                        first_p = soup.find('p')
                        if first_p:
                            snippet = first_p.get_text()
                    
                    # Truncate long snippets
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."
                        
                except Exception as e:
                    print(f"Error fetching page content for {url}: {str(e)}")
                    # Keep default title and snippet
                
                formatted_results.append(f"{i}. {title}\n")
                formatted_results.append(f"   {snippet}\n")
                formatted_results.append(f"   URL: {url}\n\n")
            
            return "\n".join(formatted_results)
            
        except Exception as e:
            return f"Error during Google search: {str(e)}"
    
    def get_system_prompt(self) -> str:
        """Return the system prompt for this tool."""
        return (
            f"You have access to {self.name}. {self.description} "
            "When you need to search the web for current information, include your search query in your response. "
            "For example: 'Let me search for the latest Python version' or 'I should look up information about quantum computing'. "
            "The search results will be automatically executed and provided back to you. "
            "Use this tool when you need up-to-date information or specific facts not in your training data. "
            "The tool will return a formatted list of search results with titles, snippets, and URLs. "
            "You can then use this information to answer the user's question. "
            "Be specific with your search queries to get the most relevant results. "
            "Note: The tool has built-in rate limiting and will automatically retry if a search fails."
        )
    
    def test_search(self, query: str) -> dict:
        """Test method to verify the search functionality works."""
        print(f"Testing web search with query: {query}")
        result = self.execute(query)
        
        return {
            "query": query,
            "result": result,
            "last_results": self.last_results
        }

# Test the tool directly
if __name__ == "__main__":
    ws = Web_search()
    print(ws.test_search("latest Python version"))