#!/usr/bin/env python3
"""
Web search tool plugin for EragAPI Chat Client.
(Placeholder implementation - not functional yet)
"""

class Web_search:
    """Web search tool implementation (placeholder)."""
    
    def __init__(self):
        self.name = "Web Search"
        self.description = "Search the web for information."
        self.enabled = False
    
    def detect_request(self, text: str):
        """Detect if the AI is requesting to search the web."""
        # Placeholder implementation
        return None
    
    def execute(self, query: str) -> str:
        """Execute a web search (placeholder)."""
        # Placeholder implementation
        return "[Web search not implemented yet]"
    
    def get_system_prompt(self) -> str:
        """Return the system prompt for this tool."""
        return (
            f"You have access to {self.name}. {self.description} "
            "When you need to search the web for information, include a search query in your response. "
            "The search results will be automatically executed and provided back to you."
        )