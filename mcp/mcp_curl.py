# mcp_curl.py
import re
import subprocess
import os
import datetime
import json
import urllib.parse
import shlex
from typing import Dict, Any, List, Optional, Tuple
from mcp_base import MCPTool

class McpCurl(MCPTool):
    """MCP-compliant curl tool for web requests and security testing."""
    
    def __init__(self):
        super().__init__()
        self.friendly_name = "Curl"  # User-friendly name for the tool
    
    def get_description(self) -> str:
        return "Execute curl commands for web requests, security testing, and API interaction."
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The curl command to execute",
                    "enum": ["raw", "predefined"]
                },
                "raw_command": {
                    "type": "string",
                    "description": "Custom curl command (if command is 'raw')"
                },
                "command_id": {
                    "type": "integer",
                    "description": "ID of predefined command (if command is 'predefined')"
                },
                "target": {
                    "type": "string",
                    "description": "Target URL or endpoint"
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds",
                    "default": 30
                },
                "data": {
                    "type": "string",
                    "description": "Data to send with the request"
                },
                "auth": {
                    "type": "string",
                    "description": "Authentication token or credentials"
                }
            },
            "required": ["command", "target"]
        }
    
    def get_capabilities(self) -> List[str]:
        return [
            "http_request",
            "https_request",
            "ftp_request",
            "file_download",
            "api_interaction",
            "security_testing",
            "header_analysis",
            "cookie_handling",
            "proxy_support"
        ]
    
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute curl command with MCP parameters."""
        # Validate parameters
        is_valid, error_msg = self.validate_params(params)
        if not is_valid:
            return f"Parameter validation failed: {error_msg}"
        
        command_type = params.get("command")
        target = params.get("target", "")
        timeout = params.get("timeout", 30)
        
        # Add -k option by default for HTTPS URLs to ignore SSL certificate issues
        if target.startswith("https://"):
            if command_type == "raw":
                raw_command = params.get("raw_command", "")
                if "-k" not in raw_command and "--insecure" not in raw_command:
                    params["raw_command"] = f"{raw_command} -k"
            elif command_type == "predefined":
                # For predefined commands, we'll handle it in the execution method
                pass
        
        if command_type == "raw":
            return self._execute_raw_command(params)
        elif command_type == "predefined":
            return self._execute_predefined_command(params)
        else:
            return f"Invalid command type: {command_type}"
    
    def _execute_raw_command(self, params: Dict[str, Any]) -> str:
        """Execute raw curl command."""
        raw_command = params.get("raw_command", "")
        target = params.get("target", "")
        timeout = params.get("timeout", 30)
        
        # Strip any extra whitespace or newlines from the target
        target = target.strip()
        
        # Build command list instead of string to avoid shell interpretation issues
        if '{target}' in raw_command:
            cmd_str = raw_command.replace('{target}', target)
            cmd_list = shlex.split(cmd_str)
        elif target not in raw_command:
            cmd_str = f"{raw_command} {target}"
            cmd_list = shlex.split(cmd_str)
        else:
            cmd_list = shlex.split(raw_command)
        
        # Add -k option if it's an HTTPS URL and not already present
        if target.startswith("https://") and "-k" not in cmd_list and "--insecure" not in cmd_list:
            # Insert -k after the curl command
            if len(cmd_list) > 0 and cmd_list[0] == "curl":
                cmd_list.insert(1, "-k")
        
        try:
            result = subprocess.run(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True
            )
            
            output = result.stdout if result.stdout else result.stderr
            return self._format_response(" ".join(cmd_list), output, result.returncode, timeout)
            
        except subprocess.TimeoutExpired:
            return f"CURL EXECUTION TIMEOUT after {timeout}s"
        except Exception as e:
            return f"CURL EXECUTION ERROR: {str(e)}"
    
    def _execute_predefined_command(self, params: Dict[str, Any]) -> str:
        """Execute predefined curl command."""
        command_id = params.get("command_id")
        target = params.get("target", "")
        timeout = params.get("timeout", 30)
        data = params.get("data", "")
        auth = params.get("auth", "")
        
        # Strip any extra whitespace or newlines from the target
        target = target.strip()
        
        # Get command template
        command_info = self._get_command_by_id(command_id)
        if not command_info:
            return f"Error: Command ID {command_id} not found"
        
        # Build command
        command_template = command_info['template']
        cmd_str = command_template.format(target=target)
        
        # Handle replacements
        if data:
            cmd_str = cmd_str.replace('{data}', data)
            cmd_str = cmd_str.replace('YOUR_DATA', data)
        
        if auth:
            cmd_str = cmd_str.replace('YOUR_TOKEN', auth)
            cmd_str = cmd_str.replace('user:pass', auth)
        
        # Split command into list
        cmd_list = shlex.split(cmd_str)
        
        # Add -k option if it's an HTTPS URL and not already present
        if target.startswith("https://") and "-k" not in cmd_list and "--insecure" not in cmd_list:
            # Insert -k after the curl command
            if len(cmd_list) > 0 and cmd_list[0] == "curl":
                cmd_list.insert(1, "-k")
        
        try:
            result = subprocess.run(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                text=True
            )
            
            output = result.stdout if result.stdout else result.stderr
            return self._format_response(" ".join(cmd_list), output, result.returncode, timeout)
            
        except subprocess.TimeoutExpired:
            return f"CURL EXECUTION TIMEOUT after {timeout}s"
        except Exception as e:
            return f"CURL EXECUTION ERROR: {str(e)}"
    
    def _format_response(self, command: str, output: str, return_code: int, timeout: int) -> str:
        """Format the response with metadata."""
        response = f"CURL EXECUTION {'SUCCESS' if return_code == 0 else 'COMPLETED'}\n"
        response += f"Command: {command}\n"
        response += f"Return Code: {return_code}\n"
        response += f"Timeout: {timeout}s\n"
        response += f"{'='*50}\n"
        response += output
        return response
    
    def _get_command_by_id(self, command_id: int) -> Optional[Dict[str, Any]]:
        """Get command definition by ID."""
        # This would load from a commands file
        # For now, return a simple example
        commands = {
            1: {
                "name": "Basic GET",
                "template": "curl {target}",
                "description": "Basic HTTP GET request"
            },
            2: {
                "name": "Headers Only",
                "template": "curl -I {target}",
                "description": "Get headers only"
            }
        }
        return commands.get(command_id)
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text is requesting a curl operation."""
        # Check for XML tool format first
        if '<tool>' in text and '<name>curl</name>' in text:
            # Extract parameters from XML
            # Note: 're' is already imported at the top of the file
            
            # Try to extract raw_command
            raw_command_match = re.search(r'<raw_command>(.*?)</raw_command>', text, re.DOTALL)
            raw_command = raw_command_match.group(1).strip() if raw_command_match else ""
            
            # Try to extract target
            target_match = re.search(r'<target>(.*?)</target>', text, re.DOTALL)
            target = target_match.group(1).strip() if target_match else ""
            
            if target:
                return {
                    "command": "raw",
                    "raw_command": raw_command,
                    "target": target
                }
        
        # Check for raw command pattern
        if re.search(r'curl\s+.*https?://', text, re.IGNORECASE):
            return {
                "command": "raw",
                "raw_command": text.strip(),
                "target": self._extract_url(text)
            }
        
        # Check for predefined command pattern
        if re.search(r'curl\s+command\s+(\d+)', text, re.IGNORECASE):
            match = re.search(r'curl\s+command\s+(\d+)', text, re.IGNORECASE)
            if match:
                return {
                    "command": "predefined",
                    "command_id": int(match.group(1)),
                    "target": self._extract_url(text)
                }
        
        return None
    
    def _extract_url(self, text: str) -> str:
        """Extract URL from text."""
        url_pattern = r'https?://[^\s]+'
        match = re.search(url_pattern, text)
        return match.group(0) if match else ""