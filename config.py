"""
Configuration settings for the simplified EragAPI application.
"""

import os

# Server Configuration
DEFAULT_SERVER_URL = "http://127.0.0.1:11436"
DEFAULT_MODEL = "groq-gemma2-9b-it"
API_TIMEOUT = 60

# GUI Configuration
WINDOW_SIZE = "1400x800"
CHAT_FONT = ("Consolas", 10)
SYSTEM_FONT = ("Consolas", 9, "italic")

# Agent Configuration
MAX_AGENT_ITERATIONS = 10
AGENT_API_TIMEOUT = 60
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1500

# Tool Configuration
TOOLS_DIRECTORY = "mcp"
RESULTS_DIRECTORY = "results"

# File Paths
def get_results_dir():
    """Get or create results directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, RESULTS_DIRECTORY)
    os.makedirs(results_dir, exist_ok=True)
    return results_dir

def get_tools_dir():
    """Get tools directory path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, TOOLS_DIRECTORY)

# Color Scheme
COLORS = {
    "user": "#0066cc",
    "assistant": "#008800", 
    "system": "#666666",
    "error": "#cc0000",
    "success": "#00cc00"
}

# Available Models (fallback if server is unavailable)
FALLBACK_MODELS = [
    "groq-gemma2-9b-it",
    "groq-mixtral-8x7b-32768",
    "groq-llama2-70b-4096"
]

# Agent Types and Descriptions
AGENT_TYPES = {
    "web_search": {
        "description": "Search the web for information",
        "required_params": ["query"],
        "optional_params": ["num_results", "region"]
    },
    "data_analysis": {
        "description": "Analyze data or perform calculations",
        "required_params": ["data"],
        "optional_params": ["analysis_type", "output_format"]
    },
    "content_creation": {
        "description": "Create written content",
        "required_params": ["topic"],
        "optional_params": ["content_type", "length", "style"]
    },
    "calculation": {
        "description": "Perform mathematical calculations",
        "required_params": ["expression"],
        "optional_params": ["precision", "units"]
    },
    "general": {
        "description": "General purpose task execution",
        "required_params": [],
        "optional_params": ["instructions"]
    }
}

# Tool Settings
TOOL_SETTINGS = {
    "web_search": {
        "max_results": 5,
        "snippet_length": 5000,
        "default_engine": "duckduckgo"
    },
    "curl": {
        "default_timeout": 30,
        "max_redirects": 5,
        "user_agent": "EragAPI-SimplifiedClient/2.0"
    }
}