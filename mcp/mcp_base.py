# mcp_base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
import re

class MCPTool(ABC):
    def __init__(self):
        self.name = self.__class__.__name__.lower()
        self.enabled = False
        self.description = self.get_description()
        self.version = "1.0"
        self.friendly_name = self.name  # Default friendly name
    
    @abstractmethod
    def get_description(self) -> str:
        """Return a description of the tool."""
        pass
    
    @abstractmethod
    def get_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool's parameters."""
        pass
    
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute the tool with the given parameters."""
        pass
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if the text is requesting this tool and return parameters if so."""
        return None
    
    def get_capabilities(self) -> List[str]:
        """Return a list of capabilities this tool provides."""
        return []
    
    def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate parameters against the schema."""
        return True, "Validation passed"