# mcp_base.py - Simplified MCP base class
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class MCPTool(ABC):
    """Simplified base class for MCP tools."""
    
    def __init__(self):
        self.name = self.__class__.__name__.lower()
        self.enabled = False
        self.description = self.get_description()
        self.friendly_name = self.name  # Default friendly name
    
    @abstractmethod
    def get_description(self) -> str:
        """Return a brief description of what this tool does."""
        pass
    
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute the tool with given parameters and return result as string."""
        pass
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Detect if the text contains a request for this tool.
        Return parameters dictionary if detected, None otherwise.
        """
        return None
    
    def get_system_prompt(self) -> str:
        """
        Return system prompt explaining how to use this tool.
        Override in subclasses for tool-specific instructions.
        """
        return f"You have access to {self.friendly_name}: {self.description}"