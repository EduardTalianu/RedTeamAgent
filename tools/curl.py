import re
import subprocess
import xml.etree.ElementTree as ET

class Curl:
    """Curl tool implementation."""
    
    def __init__(self):
        self.name = "Curl"  # This is what the GUI displays
        self.enabled = False  # This is required by the GUI
        self.description = "Execute curl commands to fetch data from the web."
    
    def detect_request(self, text: str):
        """Detect if the AI is requesting to execute a curl command using XML format."""
        # Look for structured XML tool invocation
        xml_pattern = r'```xml\s*\n*\s*(<tool>.*?</tool>)\s*\n*\s*```'
        match = re.search(xml_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(1))
        
        # Fallback to simpler format without code block
        simple_pattern = r'(<tool>.*?</tool>)'
        match = re.search(simple_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(0))
        
        # Try to detect XML without proper tags
        fallback_pattern = r'<tool>.*?</tool>'
        match = re.search(fallback_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(0))
        
        return None
    
    def _parse_tool_command(self, xml_str: str):
        """Parse an XML tool command and extract parameters."""
        try:
            root = ET.fromstring(xml_str)
            
            # Validate the tool name - accept both "curl" and "Curl"
            tool_name = root.find('name')
            if tool_name is None or tool_name.text.lower() != 'curl':
                return None
                
            # Extract parameters
            params = {}
            params_elem = root.find('parameters')
            if params_elem is not None:
                # Handle the format: <parameter_name>name</parameter_name><parameter_value>value</parameter_value>
                param_names = params_elem.findall('parameter_name')
                param_values = params_elem.findall('parameter_value')
                
                for i, name_elem in enumerate(param_names):
                    if i < len(param_values) and name_elem.text:
                        param_name = name_elem.text.strip()
                        param_value = param_values[i].text.strip() if param_values[i] else ""
                        params[param_name] = param_value
                
                # Also handle the format: <parameter name="name">value</parameter>
                param_elems = params_elem.findall('parameter')
                for param in param_elems:
                    param_name = param.get('name', '').strip()
                    if param_name and param.text:
                        params[param_name] = param.text.strip()
                
                # Also handle direct parameter tags: <url>, <options>, <flag>, <option>, <command>
                for child in params_elem:
                    if child.tag in ['url', 'options', 'flag', 'option', 'command'] and child.text:
                        params[child.tag] = child.text.strip()
            
            # Build the curl command
            command_parts = ['curl']
            
            # Add -k option first (to ignore SSL certificate errors)
            command_parts.append('-k')
            
            # Add options/flags if present
            if 'options' in params:
                options = params['options']
                if options:
                    # Split options by space but preserve quoted parts
                    import shlex
                    try:
                        command_parts.extend(shlex.split(options))
                    except:
                        # Fallback to simple split
                        command_parts.extend(options.split())
            
            # Add flag if present (like -I for headers)
            if 'flag' in params:
                flag = params['flag']
                if flag:
                    command_parts.append(flag)
            
            # Add option if present (like -I for headers)
            if 'option' in params:
                option = params['option']
                if option:
                    command_parts.append(option)
            
            # Add header parameter if present
            if 'header' in params and params['header'].lower() == 'true':
                command_parts.append('-I')
            
            # Add URL if present
            if 'url' in params:
                url = params['url']
                if url:
                    command_parts.append(url)
            elif 'command' in params:
                # If there's a full command parameter, use it instead
                command = params['command']
                if command:
                    if not command.strip().startswith('curl'):
                        return command  # Return the command as is if it doesn't start with curl
                    else:
                        return command  # Return the full curl command
            
            # Join the command parts
            command = ' '.join(command_parts)
            return command if len(command) > 4 else None  # Minimum length is "curl X"
                    
        except Exception as e:
            print(f"Error parsing XML: {str(e)}")
        
        return None
    
    def execute(self, cmd_line: str) -> str:
        """Run curl command locally and return the output."""
        try:
            # Ensure the command starts with curl
            if not cmd_line.strip().startswith("curl"):
                cmd_line = "curl " + cmd_line
            
            # Add -k option if not present (to ignore SSL certificate errors)
            if "-k" not in cmd_line and "--insecure" not in cmd_line:
                # Insert -k after curl and before other options
                parts = cmd_line.split(maxsplit=1)
                if len(parts) == 1:
                    cmd_line = "curl -k"
                else:
                    cmd_line = "curl -k " + parts[1]
            
            print(f"Executing: {cmd_line}")
            
            # Use subprocess with bytes output to avoid encoding issues
            result = subprocess.run(
                cmd_line, 
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
            
            return output
        except subprocess.TimeoutExpired:
            return "[curl error] Command timed out after 30 seconds"
        except Exception as e:
            return f"[curl error] {str(e)}"
    
    def get_system_prompt(self) -> str:
        """Return the system prompt for this tool."""
        return (
            f"You have access to {self.name}. {self.description} "
            "When you need to execute a curl command, use the following XML format:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>curl</name>\n"
            "  <parameters>\n"
            "    <url>the URL to fetch</url>\n"
            "    <option>curl flags (e.g., -I for headers)</option>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Alternatively, you can use these formats:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>curl</name>\n"
            "  <parameters>\n"
            "    <url>the URL to fetch</url>\n"
            "    <flag>curl flags (e.g., -I for headers)</flag>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Or:\n"
            "```xml\n"
            "<tool>\n"
            "  <name>curl</name>\n"
            "  <parameters>\n"
            "    <parameter_name>url</parameter_name>\n"
            "    <parameter_value>the URL to fetch</parameter_value>\n"
            "    <parameter_name>option</parameter_name>\n"
            "    <parameter_value>-I</parameter_value>\n"
            "  </parameters>\n"
            "</tool>\n"
            "```\n\n"
            "Only use this format when you actually want to execute the tool. "
            "Do not include it in your thinking process or examples unless you want it to be executed. "
            "The curl output will be automatically executed and provided back to you. "
            "Keep curl commands simple and use common APIs or websites. "
            "For HTTP headers, use the -I option. "
            "Note: All curl commands will be executed with -k (insecure) option to ignore SSL certificate errors."
        )