# mcp_curl.py
import subprocess
import re
import xml.etree.ElementTree as ET
import os
import datetime
import shlex
from typing import Dict, Any, List, Optional, Tuple
from mcp_base import MCPTool

class McpCurl(MCPTool):
    """MCP-compliant curl tool with proper command execution and results saving."""
    
    def __init__(self):
        super().__init__()
        self.friendly_name = "Curl"
        # Create results directory structure
        self.results_dir = "results"
        self.curl_results_dir = os.path.join(self.results_dir, "curl")
        os.makedirs(self.curl_results_dir, exist_ok=True)
    
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
        
        # Strip any extra whitespace or newlines from the target
        target = target.strip()
        
        if command_type == "raw":
            result = self._execute_raw_command(params)
        elif command_type == "predefined":
            result = self._execute_predefined_command(params)
        else:
            return f"Invalid command type: {command_type}"
        
        # Save results to file
        self._save_curl_result(target, result)
        
        return result
    
    def _execute_raw_command(self, params: Dict[str, Any]) -> str:
        """Execute raw curl command with proper quoting."""
        raw_command = params.get("raw_command", "")
        target = params.get("target", "")
        timeout = params.get("timeout", 30)
        
        # Strip any extra whitespace or newlines from the target
        target = target.strip()
        
        # Build command list instead of string to avoid shell interpretation issues
        if '{target}' in raw_command:
            cmd_str = raw_command.replace('{target}', target)
        elif target not in raw_command:
            cmd_str = f"{raw_command} {target}"
        else:
            cmd_str = raw_command
        
        # Use shlex.split to properly handle quotes
        try:
            cmd_list = shlex.split(cmd_str)
        except ValueError as e:
            return f"Command parsing error: {str(e)}"
        
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
        """Execute predefined curl command with proper quoting."""
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
        
        # Use shlex.split to properly handle quotes
        try:
            cmd_list = shlex.split(cmd_str)
        except ValueError as e:
            return f"Command parsing error: {str(e)}"
        
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
            },
            3: {
                "name": "Follow Redirects",
                "template": "curl -L {target}",
                "description": "Follow redirects"
            },
            4: {
                "name": "Verbose Output",
                "template": "curl -v {target}",
                "description": "Verbose output"
            },
            5: {
                "name": "POST Request",
                "template": "curl -X POST -d '{data}' {target}",
                "description": "POST request with data"
            },
            6: {
                "name": "With Headers",
                "template": "curl -H 'Content-Type: application/json' {target}",
                "description": "Request with custom headers"
            },
            7: {
                "name": "With Authentication",
                "template": "curl -u 'user:pass' {target}",
                "description": "Basic authentication"
            },
            8: {
                "name": "Save to File",
                "template": "curl -o output.txt {target}",
                "description": "Save response to file"
            }
        }
        return commands.get(command_id)
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text is requesting a curl operation."""
        # Check for XML tool format first
        if '<tool>' in text and '<name>curl</name>' in text:
            # Extract parameters from XML
            try:
                # Try to extract the XML block
                xml_pattern = r'```xml\s*\n*\s*(<tool>.*?</tool>)\s*\n*\s*```'
                match = re.search(xml_pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    xml_str = match.group(1)
                else:
                    # Try without code block
                    simple_pattern = r'(<tool>.*?</tool>)'
                    match = re.search(simple_pattern, text, re.IGNORECASE | re.DOTALL)
                    if match:
                        xml_str = match.group(1)
                    else:
                        # Try without proper tags
                        fallback_pattern = r'<tool>.*?</tool>'
                        match = re.search(fallback_pattern, text, re.IGNORECASE | re.DOTALL)
                        if match:
                            xml_str = match.group(0)
                        else:
                            return None
                
                return self._parse_tool_command(xml_str)
            except Exception as e:
                print(f"Error parsing XML: {str(e)}")
                return None
        
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
    
    def _parse_tool_command(self, xml_str: str) -> Optional[Dict[str, Any]]:
        """Parse an XML tool command and extract parameters."""
        try:
            root = ET.fromstring(xml_str)
            
            # Validate the tool name
            tool_name = root.find('name')
            if tool_name is None or tool_name.text.lower() != 'curl':
                return None
                
            # Extract and validate parameters
            params = {"command": "raw", "target": ""}
            params_elem = root.find('parameters')
            if params_elem is not None:
                # Extract target
                target_elem = params_elem.find('target')
                if target_elem is not None and target_elem.text:
                    params["target"] = target_elem.text.strip()
                
                # Extract raw_command
                raw_command_elem = params_elem.find('raw_command')
                if raw_command_elem is not None and raw_command_elem.text:
                    params["raw_command"] = raw_command_elem.text.strip()
                
                # Extract command_id
                command_id_elem = params_elem.find('command_id')
                if command_id_elem is not None and command_id_elem.text:
                    try:
                        params["command_id"] = int(command_id_elem.text.strip())
                        params["command"] = "predefined"
                    except ValueError:
                        pass
                
                # Extract timeout
                timeout_elem = params_elem.find('timeout')
                if timeout_elem is not None and timeout_elem.text:
                    try:
                        params["timeout"] = float(timeout_elem.text.strip())
                    except ValueError:
                        pass
                
                # Extract data
                data_elem = params_elem.find('data')
                if data_elem is not None and data_elem.text:
                    params["data"] = data_elem.text.strip()
                
                # Extract auth
                auth_elem = params_elem.find('auth')
                if auth_elem is not None and auth_elem.text:
                    params["auth"] = auth_elem.text.strip()
                
                # If we have a target, return the params
                if params["target"]:
                    return params
                        
            return None
                        
        except Exception as e:
            print(f"Error parsing XML: {str(e)}")
            return None
    
    def _extract_url(self, text: str) -> str:
        """Extract URL from text."""
        url_pattern = r'https?://[^\s]+'
        match = re.search(url_pattern, text)
        return match.group(0) if match else ""
    
    def _save_curl_result(self, target: str, result: str):
        """Save curl result to a file in the results/curl/ directory."""
        try:
            # Create a safe filename from the target URL
            safe_target = re.sub(r'[^\w\s-]', '', target).strip()
            safe_target = re.sub(r'[-\s]+', '-', safe_target)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"curl_{timestamp}_{safe_target[:50]}.txt"
            filepath = os.path.join(self.curl_results_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Tool: Curl\n")
                f.write(f"Target: {target}\n")
                f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(result)
            
            print(f"Curl result saved to: {filepath}")
        except Exception as e:
            print(f"Error saving curl result: {str(e)}")
    
    def get_system_prompt(self) -> str:
        """Return the system prompt for this tool."""
        return (
            f"You have access to {self.name}. {self.description} "
            "When you need to execute curl commands, use the following XML format:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>curl</name>\n"
            "  <parameters>\n"
            "    <command>raw</command>\n"
            "    <raw_command>curl -I</raw_command>\n"
            "    <target>https://example.com</target>\n"
            "    <timeout>30</timeout>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Alternatively, you can use predefined commands:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>curl</name>\n"
            "  <parameters>\n"
            "    <command>predefined</command>\n"
            "    <command_id>2</command_id>\n"
            "    <target>https://example.com</target>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Available predefined commands:\n"
            "1. Basic GET: curl {target}\n"
            "2. Headers Only: curl -I {target}\n"
            "3. Follow Redirects: curl -L {target}\n"
            "4. Verbose Output: curl -v {target}\n"
            "5. POST Request: curl -X POST -d '{data}' {target}\n"
            "6. With Headers: curl -H 'Content-Type: application/json' {target}\n"
            "7. With Authentication: curl -u 'user:pass' {target}\n"
            "8. Save to File: curl -o output.txt {target}\n\n"
            "Only use this format when you actually want to execute the tool. "
            "The curl results will be automatically executed and provided back to you. "
            "All results are saved to the results/curl/ directory for later reference."
        )