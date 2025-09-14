# mcp_curl.py - Simplified curl tool
import subprocess
import re
import os
import datetime
from typing import Dict, Any, Optional
from mcp_base import MCPTool

class McpCurl(MCPTool):
    """Simplified curl tool for HTTP requests and basic security testing."""
    
    def __init__(self):
        super().__init__()
        self.friendly_name = "Curl"
        self.default_timeout = 30
        
        # Create results directory
        self.results_dir = os.path.join("results", "curl")
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Common curl commands
        self.predefined_commands = {
            1: {"name": "Basic GET", "template": "curl -s {target}"},
            2: {"name": "Headers Only", "template": "curl -s -I {target}"},
            3: {"name": "Verbose", "template": "curl -v {target}"},
            4: {"name": "Follow Redirects", "template": "curl -s -L {target}"},
            5: {"name": "With User-Agent", "template": "curl -s -H 'User-Agent: Mozilla/5.0' {target}"},
            6: {"name": "POST Request", "template": "curl -s -X POST -d '{data}' {target}"},
            7: {"name": "JSON POST", "template": "curl -s -X POST -H 'Content-Type: application/json' -d '{data}' {target}"},
            8: {"name": "Basic Auth", "template": "curl -s -u '{auth}' {target}"}
        }
    
    def get_description(self) -> str:
        return "Execute curl commands for HTTP requests, API testing, and basic reconnaissance."
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect curl command requests."""
        
        # Check for XML format
        xml_match = re.search(r'<tool>\s*<n>curl</n>\s*<parameters>(.*?)</parameters>\s*</tool>', 
                             text, re.IGNORECASE | re.DOTALL)
        if xml_match:
            params_text = xml_match.group(1)
            params = {}
            
            # Extract common parameters
            target_match = re.search(r'<target>(.*?)</target>', params_text, re.DOTALL)
            if target_match:
                params["target"] = target_match.group(1).strip()
            
            # Check for command_id (predefined command)
            cmd_id_match = re.search(r'<command_id>(\d+)</command_id>', params_text)
            if cmd_id_match:
                params["command_id"] = int(cmd_id_match.group(1))
                params["command_type"] = "predefined"
            else:
                # Check for raw command
                raw_match = re.search(r'<raw_command>(.*?)</raw_command>', params_text, re.DOTALL)
                if raw_match:
                    params["raw_command"] = raw_match.group(1).strip()
                    params["command_type"] = "raw"
            
            # Optional parameters
            data_match = re.search(r'<data>(.*?)</data>', params_text, re.DOTALL)
            if data_match:
                params["data"] = data_match.group(1).strip()
            
            auth_match = re.search(r'<auth>(.*?)</auth>', params_text, re.DOTALL)
            if auth_match:
                params["auth"] = auth_match.group(1).strip()
            
            if "target" in params:
                return params
        
        # Check for direct curl commands
        curl_match = re.search(r'curl\s+.*?(https?://[^\s]+)', text, re.IGNORECASE)
        if curl_match:
            return {
                "target": curl_match.group(1),
                "raw_command": text.strip(),
                "command_type": "raw"
            }
        
        return None
    
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute curl command."""
        target = params.get("target", "").strip()
        if not target:
            return "Error: Target URL is required"
        
        command_type = params.get("command_type", "predefined")
        
        try:
            if command_type == "predefined":
                result = self._execute_predefined_command(params)
            else:
                result = self._execute_raw_command(params)
            
            # Save results
            self._save_results(target, result)
            
            return result
            
        except Exception as e:
            return f"Curl execution error: {str(e)}"
    
    def _execute_predefined_command(self, params: Dict[str, Any]) -> str:
        """Execute a predefined curl command."""
        command_id = params.get("command_id", 1)
        target = params["target"]
        data = params.get("data", "")
        auth = params.get("auth", "")
        
        if command_id not in self.predefined_commands:
            return f"Error: Invalid command ID {command_id}"
        
        cmd_info = self.predefined_commands[command_id]
        command_template = cmd_info["template"]
        
        # Replace placeholders
        command = command_template.replace("{target}", target)
        if "{data}" in command:
            command = command.replace("{data}", data if data else "")
        if "{auth}" in command:
            command = command.replace("{auth}", auth if auth else "user:pass")
        
        return self._run_curl_command(command, cmd_info["name"])
    
    def _execute_raw_command(self, params: Dict[str, Any]) -> str:
        """Execute a raw curl command."""
        raw_command = params.get("raw_command", "")
        target = params["target"]
        
        if raw_command:
            # Use the provided raw command
            command = raw_command
        else:
            # Default to basic GET
            command = f"curl -s {target}"
        
        return self._run_curl_command(command, "Raw Command")
    
    def _run_curl_command(self, command: str, command_name: str) -> str:
        """Run the actual curl command."""
        try:
            # Add insecure flag for HTTPS if not present
            if "https://" in command and "-k" not in command and "--insecure" not in command:
                command = command.replace("curl", "curl -k", 1)
            
            # Split command for subprocess
            cmd_parts = command.split()
            
            # Execute command
            result = subprocess.run(
                cmd_parts,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.default_timeout,
                text=True
            )
            
            # Format output
            output = []
            output.append(f"CURL COMMAND: {command_name}")
            output.append(f"Command: {command}")
            output.append(f"Return Code: {result.returncode}")
            output.append("-" * 50)
            
            if result.stdout:
                output.append("STDOUT:")
                output.append(result.stdout)
            
            if result.stderr:
                output.append("STDERR:")
                output.append(result.stderr)
            
            return "\n".join(output)
            
        except subprocess.TimeoutExpired:
            return f"TIMEOUT: Command exceeded {self.default_timeout} seconds"
        except FileNotFoundError:
            return "ERROR: curl command not found. Please install curl."
        except Exception as e:
            return f"ERROR: {str(e)}"
    
    def _save_results(self, target: str, result: str):
        """Save curl results to file."""
        try:
            # Create safe filename
            safe_target = re.sub(r'[^\w.-]', '_', target.replace('https://', '').replace('http://', ''))
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"curl_{timestamp}_{safe_target[:30]}.txt"
            filepath = os.path.join(self.results_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Curl Execution Results\n")
                f.write(f"Target: {target}\n")
                f.write(f"Timestamp: {datetime.datetime.now().isoformat()}\n")
                f.write("=" * 50 + "\n\n")
                f.write(result)
            
        except Exception as e:
            print(f"Error saving curl results: {e}")
    
    def get_system_prompt(self) -> str:
        """Return system prompt for curl tool."""
        commands_list = []
        for cmd_id, cmd_info in self.predefined_commands.items():
            commands_list.append(f"{cmd_id}. {cmd_info['name']}: {cmd_info['template']}")
        
        commands_text = "\n".join(commands_list)
        
        return (
            f"You have access to {self.friendly_name}. {self.description} "
            "Use this for HTTP requests, API testing, and basic reconnaissance.\n\n"
            "To use curl, include this XML in your response:\n"
            "```xml\n"
            "<tool>\n"
            "  <n>curl</n>\n"
            "  <parameters>\n"
            "    <command_id>2</command_id>\n"
            "    <target>https://example.com</target>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            f"Available predefined commands:\n{commands_text}\n\n"
            "For custom commands, use raw_command instead:\n"
            "```xml\n"
            "<tool>\n"
            "  <n>curl</n>\n"
            "  <parameters>\n"
            "    <raw_command>curl -v -H 'Accept: application/json'</raw_command>\n"
            "    <target>https://api.example.com</target>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Examples:\n"
            "- Get headers: command_id=2, target=https://example.com\n"
            "- Verbose output: command_id=3, target=https://example.com\n"
            "- POST data: command_id=6, target=https://api.com, data={\"key\":\"value\"}\n\n"
            "Results are automatically saved to results/curl/ directory."
        )