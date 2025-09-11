import re
import subprocess
import os
import datetime
import hashlib
import json
import urllib.parse

class Curl:
    """Curl tool implementation with predefined commands and smart file naming."""
    
    def __init__(self):
        self.name = "Curl"  # This is what the GUI displays
        self.enabled = False  # This is required by the GUI
        self.description = "Execute predefined curl commands to fetch data from the web and save results to disk."
        
        # Set up results directory
        self.results_dir = "results"
        self._ensure_results_directory()
        
        # Load predefined commands
        self.commands = self._load_commands()
    
    def _ensure_results_directory(self):
        """Create the results directory if it doesn't exist."""
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
            print(f"Created results directory: {self.results_dir}")
    
    def _load_commands(self):
        """Load predefined curl commands from JSON file."""
        try:
            # Get the directory where the script is located
            script_dir = os.path.dirname(os.path.abspath(__file__))
            commands_file = os.path.join(script_dir, "curl_commands.json")
            
            if os.path.exists(commands_file):
                with open(commands_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('commands', [])
            else:
                print(f"Warning: curl_commands.json not found at {commands_file}")
                return []
        except Exception as e:
            print(f"Error loading curl commands: {str(e)}")
            return []
    
    def _get_command_by_id(self, command_id):
        """Get a command definition by ID."""
        for cmd in self.commands:
            if cmd.get('id') == command_id:
                return cmd
        return None
    
    def _generate_filename(self, command_info: dict, target_url: str) -> str:
        """Generate a descriptive filename for the curl result."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Get command info
        command_name = command_info.get('name', 'unknown').lower().replace(' ', '_')
        output_type = command_info.get('output_type', 'response')
        category = command_info.get('category', 'general')
        
        # Parse and clean the target URL
        try:
            parsed_url = urllib.parse.urlparse(target_url)
            domain = parsed_url.netloc or 'unknown'
            path = parsed_url.path.strip('/')
            
            # Clean domain name (remove www, ports, etc.)
            domain = re.sub(r'^www\.', '', domain)
            domain = re.sub(r':\d+$', '', domain)  # Remove port
            domain = re.sub(r'[^\w\-\.]', '_', domain)
            
            # Clean and shorten path
            if path:
                path = re.sub(r'[^\w\-_/]', '_', path)
                path = path.replace('/', '_')
                path = path[:30]  # Limit length
                url_part = f"{domain}_{path}"
            else:
                url_part = domain
                
        except Exception:
            url_part = "unknown_url"
        
        # Create descriptive filename
        # Format: timestamp_category_commandname_domain_outputtype
        filename = f"{timestamp}_{category}_{command_name}_{url_part}_{output_type}"
        
        # Clean up the filename
        filename = re.sub(r'[^\w\-_]', '_', filename)
        filename = re.sub(r'_{2,}', '_', filename)  # Replace multiple underscores with single
        filename = filename[:200]  # Limit total length
        
        return filename
    
    def _save_result(self, command_info: dict, target_url: str, full_command: str, output: str, return_code: int, stderr: str = "") -> str:
        """Save the curl result to disk with descriptive naming and return the file path."""
        try:
            filename = self._generate_filename(command_info, target_url)
            
            # Save the raw output
            output_file = os.path.join(self.results_dir, f"{filename}.txt")
            with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                f.write(output)
            
            # Save metadata as JSON
            metadata = {
                "timestamp": datetime.datetime.now().isoformat(),
                "command_id": command_info.get('id'),
                "command_name": command_info.get('name'),
                "command_description": command_info.get('description'),
                "category": command_info.get('category'),
                "output_type": command_info.get('output_type'),
                "target_url": target_url,
                "full_command": full_command,
                "return_code": return_code,
                "stderr": stderr,
                "output_file": output_file,
                "output_size": len(output.encode('utf-8'))
            }
            
            metadata_file = os.path.join(self.results_dir, f"{filename}_metadata.json")
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            return output_file
            
        except Exception as e:
            print(f"Error saving curl result: {str(e)}")
            return None
    
    def detect_request(self, text: str):
        """Detect if the AI is requesting to execute a curl command or list commands."""
        # Check if LLM is asking for the command list
        list_patterns = [
            r'list.*curl.*commands',
            r'show.*available.*commands',
            r'what.*curl.*commands',
            r'available.*curl.*options'
        ]
        
        for pattern in list_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return "LIST_COMMANDS"
        
        # Look for XML tool usage
        xml_pattern = r'```xml\s*\n*\s*(<tool>.*?</tool>)\s*\n*\s*```'
        match = re.search(xml_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_xml_command(match.group(1))
        
        # Fallback to simpler format without code block
        simple_pattern = r'(<tool>.*?</tool>)'
        match = re.search(simple_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_xml_command(match.group(0))
        
        # Look for curl tool usage - this should be handled by the main framework
        # We keep this simple pattern matching for basic detection
        curl_patterns = [
            r'curl.*command.*(\d+)',
            r'use.*curl.*(\d+)',
            r'execute.*curl.*(\d+)'
        ]
        
        for pattern in curl_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    command_id = int(match.group(1))
                    # This is just basic detection - the actual parsing happens in the main framework
                    return f"CURL_COMMAND_{command_id}"
                except:
                    pass
        
        return None
    
    def _parse_xml_command(self, xml_str: str):
        """Parse XML command and extract parameters."""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_str)
            
            # Check if this is a curl command
            name_elem = root.find('name')
            if name_elem is None:
                name_elem = root.find('n')  # Alternative short form
            
            if name_elem is None or name_elem.text.lower() not in ['curl', 'curl']:
                return None
            
            # Extract parameters
            params_elem = root.find('parameters')
            if params_elem is not None:
                command_id_elem = params_elem.find('command_id')
                target_elem = params_elem.find('target')
                
                if command_id_elem is not None and target_elem is not None:
                    try:
                        result = {
                            'command_id': int(command_id_elem.text.strip()),
                            'target': target_elem.text.strip()
                        }
                        
                        # Add optional parameters if present
                        data_elem = params_elem.find('data')
                        if data_elem is not None and data_elem.text:
                            result['data'] = data_elem.text.strip()
                        
                        auth_elem = params_elem.find('auth')
                        if auth_elem is not None and auth_elem.text:
                            result['auth'] = auth_elem.text.strip()
                        
                        return result
                        
                    except (ValueError, AttributeError) as e:
                        print(f"Invalid parameters: {e}")
                        return None
                        
        except Exception as e:
            print(f"Error parsing XML: {str(e)}")
        
        return None
    
    def execute(self, params) -> str:
        """Execute a predefined curl command with the given parameters or list commands."""
        # Handle command list request
        if params == "LIST_COMMANDS":
            return self.list_available_commands()
        
        # Handle simple string commands from basic detection
        if isinstance(params, str) and params.startswith("CURL_COMMAND_"):
            return "Please use the proper tool format with command_id and target parameters."
        
        # Handle curl command execution with proper parameters
        try:
            command_id = params['command_id']
            target = params['target']
            data = params.get('data', '')
            auth = params.get('auth', '')
            
            # Get the command definition
            command_info = self._get_command_by_id(command_id)
            if not command_info:
                return f"Error: Command ID {command_id} not found. Use command IDs 1-{len(self.commands)}."
            
            # Build the curl command from template
            command_template = command_info['template']
            full_command = command_template.format(target=target)
            
            # Handle special replacements for data and auth
            if data and '{data}' in full_command:
                full_command = full_command.replace('{data}', data)
            elif data and 'YOUR_DATA' in full_command:
                full_command = full_command.replace('YOUR_DATA', data)
            elif data and '"test": "data"' in full_command:
                full_command = full_command.replace('"test": "data"', data)
            
            if auth and 'YOUR_TOKEN' in full_command:
                full_command = full_command.replace('YOUR_TOKEN', auth)
            elif auth and 'user:pass' in full_command:
                full_command = full_command.replace('user:pass', auth)
            
            print(f"Executing command {command_id} ({command_info['name']}): {full_command}")
            
            # Execute the curl command
            result = subprocess.run(
                full_command, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                timeout=30
            )
            
            # Get the output as bytes and decode with error handling
            stdout = result.stdout
            stderr = result.stderr
            
            # Try to decode with utf-8, fallback to latin1 if that fails
            try:
                stdout_text = stdout.decode('utf-8', errors='replace')
            except:
                stdout_text = stdout.decode('latin1')
                
            try:
                stderr_text = stderr.decode('utf-8', errors='replace')
            except:
                stderr_text = stderr.decode('latin1')
            
            output = stdout_text if stdout_text else stderr_text
            if not output:
                output = f"Command executed with return code: {result.returncode}"
            
            # Save the result to disk
            saved_file = self._save_result(command_info, target, full_command, output, result.returncode, stderr_text)
            
            # Add file save information to the output
            result_summary = f"Command: {command_info['name']} (ID: {command_id})\n"
            result_summary += f"Target: {target}\n"
            result_summary += f"Category: {command_info['category']}\n"
            result_summary += f"Return Code: {result.returncode}\n\n"
            
            if saved_file:
                file_info = f"[Result saved to: {saved_file}]\n\n"
                return result_summary + file_info + output
            else:
                return result_summary + "[Warning: Could not save result to disk]\n\n" + output
            
        except subprocess.TimeoutExpired:
            error_msg = "[curl error] Command timed out after 30 seconds"
            command_info = self._get_command_by_id(params.get('command_id', 0)) or {}
            self._save_result(command_info, params.get('target', ''), 'timeout', error_msg, -1, "Timeout")
            return error_msg
        except Exception as e:
            error_msg = f"[curl error] {str(e)}"
            command_info = self._get_command_by_id(params.get('command_id', 0)) or {}
            self._save_result(command_info, params.get('target', ''), 'error', error_msg, -1, str(e))
            return error_msg
    
    def list_available_commands(self) -> str:
        """List all available predefined curl commands."""
        if not self.commands:
            return "No curl commands available. Please check curl_commands.json file."
        
        output = "Available Curl Commands:\n"
        output += "=" * 50 + "\n\n"
        
        # Group commands by category
        categories = {}
        for cmd in self.commands:
            category = cmd.get('category', 'general')
            if category not in categories:
                categories[category] = []
            categories[category].append(cmd)
        
        for category, cmds in sorted(categories.items()):
            output += f"{category.upper()} COMMANDS:\n"
            output += "-" * 30 + "\n"
            
            for cmd in sorted(cmds, key=lambda x: x['id']):
                output += f"ID {cmd['id']:2d}: {cmd['name']}\n"
                output += f"      {cmd['description']}\n"
                output += f"      Output: {cmd['output_type']}\n\n"
        
        return output
    
    def get_system_prompt(self) -> str:
        """Return the system prompt for this tool."""
        return (
            f"You have access to {self.name}. {self.description} "
            f"There are {len(self.commands)} predefined curl commands available. "
            "When you need to make an HTTP request, specify the command ID and target URL. "
            "Common command IDs:\n"
            "- 1: Basic GET request\n"
            "- 2: Get headers only (-I)\n"
            "- 3: Verbose output (-v)\n"
            "- 5: JSON API request\n"
            "- 6: POST JSON data\n"
            "- 13: Bearer token auth\n\n"
            "If you need to see all available commands, ask me to list them first. "
            "Results are automatically saved with descriptive filenames based on command type, target domain, and timestamp."
        )