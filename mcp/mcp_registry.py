# mcp_registry.py
from typing import Dict, List, Type, Tuple
from mcp_base import MCPTool
import re

class MCPRegistry:
    """Registry for MCP tools."""
    
    def __init__(self):
        self.tools: Dict[str, MCPTool] = {}
        self.tool_classes: Dict[str, Type[MCPTool]] = {}
    
    def register_tool(self, tool_class: Type[MCPTool]) -> None:
        """Register a tool class."""
        tool_instance = tool_class()
        self.tools[tool_instance.name] = tool_instance
        self.tool_classes[tool_instance.name] = tool_class
        print(f"Registered MCP tool: {tool_instance.name}")
    
    def get_tool(self, name: str) -> MCPTool:
        """Get a tool instance by name."""
        return self.tools.get(name)
    
    def list_tools(self) -> List[str]:
        """List all registered tool names."""
        return list(self.tools.keys())
    
    def get_tool_schemas(self) -> Dict[str, Dict]:
        """Get schemas for all registered tools."""
        return {name: tool.get_schema() for name, tool in self.tools.items()}
    
    def detect_tool_request(self, text: str) -> Tuple[Optional[MCPTool], Optional[Dict]]:
        """Detect which tool is being requested and extract parameters."""
        for tool in self.tools.values():
            params = tool.detect_request(text)
            if params:
                return tool, params
        return None, None