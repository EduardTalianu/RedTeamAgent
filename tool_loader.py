"""
Tool loading system for the application.
"""

import os
import sys
import importlib.util
from typing import Dict, Any

TOOLS_DIR = "tools"
MCP_DIR = "mcp"

class ToolLoader:
    """Dynamically loads tools from both legacy tools directory and MCP directory."""
    
    @staticmethod
    def load_tools() -> Dict[str, Any]:
        """Load all available tools from both tools and mcp directories."""
        tools = {}
        
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Add mcp directory to Python path temporarily
        mcp_path = os.path.join(script_dir, MCP_DIR)
        if mcp_path not in sys.path:
            sys.path.insert(0, mcp_path)
        
        # Load legacy tools from tools directory
        tools_path = os.path.join(script_dir, TOOLS_DIR)
        if os.path.exists(tools_path):
            print(f"Looking for legacy tools in: {tools_path}")
            for filename in os.listdir(tools_path):
                if filename.endswith('.py') and filename != '__init__.py':
                    tool_name = filename[:-3]  # Remove .py extension
                    try:
                        # Import the module
                        module_path = os.path.join(tools_path, filename)
                        print(f"Loading legacy tool from: {module_path}")
                        
                        spec = importlib.util.spec_from_file_location(tool_name, module_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Get the tool class (assumed to be the same name as the file)
                        class_name = tool_name.capitalize()
                        if hasattr(module, class_name):
                            tool_class = getattr(module, class_name)
                            tool_instance = tool_class()
                            # Enable tools by default
                            tool_instance.enabled = True
                            tools[tool_name] = tool_instance
                            print(f"Successfully loaded legacy tool: {tool_name} ({class_name})")
                        else:
                            print(f"Error: Class {class_name} not found in {filename}")
                    except Exception as e:
                        print(f"Error loading legacy tool {tool_name}: {e}")
        
        # Load MCP tools from mcp directory
        if os.path.exists(mcp_path):
            print(f"Looking for MCP tools in: {mcp_path}")
            for filename in os.listdir(mcp_path):
                if filename.endswith('.py') and filename != '__init__.py' and filename.startswith('mcp_'):
                    # Skip non-tool files
                    if filename in ['mcp_base.py', 'mcp_registry.py']:
                        continue
                    tool_name = filename[:-3]  # Remove .py extension
                    try:
                        # Import the module
                        module_path = os.path.join(mcp_path, filename)
                        print(f"Loading MCP tool from: {module_path}")
                        
                        spec = importlib.util.spec_from_file_location(tool_name, module_path)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Get the tool class (assumed to be the same name as the file, capitalized)
                        class_name = ''.join(word.capitalize() for word in tool_name.split('_'))
                        if hasattr(module, class_name):
                            tool_class = getattr(module, class_name)
                            tool_instance = tool_class()
                            # Enable tools by default
                            tool_instance.enabled = True
                            tools[tool_name] = tool_instance
                            print(f"Successfully loaded MCP tool: {tool_name} ({class_name})")
                        else:
                            print(f"Error: Class {class_name} not found in {filename}")
                    except Exception as e:
                        print(f"Error loading MCP tool {tool_name}: {e}")
        
        print(f"Total tools loaded: {len(tools)}")
        return tools