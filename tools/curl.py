#!/usr/bin/env python3
"""
Curl tool plugin for EragAPI Chat Client.
Allows the AI to execute local curl commands.
"""
import re
import subprocess

class Curl:
    """Curl tool implementation."""
    
    def __init__(self):
        self.name = "Curl"
        self.description = "Execute curl commands to fetch data from the web."
        self.enabled = False
    
    def detect_request(self, text: str):
        """Detect if the AI is requesting to execute a curl command."""
        # Look for curl commands in the AI's response
        
        # Pattern 1: Look for curl commands in code blocks
        code_block_pattern = r'```(?:bash)?\s*\n?(curl[^\n`]+)\n?```'
        match = re.search(code_block_pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: Look for inline curl commands
        inline_pattern = r'(curl\s+[^\s`]+(?:\s+[^\s`]+)*)'
        match = re.search(inline_pattern, text, re.IGNORECASE)
        if match:
            cmd = match.group(1).strip()
            # Remove trailing punctuation
            cmd = cmd.rstrip('.,;:')
            return cmd
        
        return None
    
    def execute(self, cmd_line: str) -> str:
        """Run curl command locally and return the output."""
        try:
            # Ensure the command starts with curl
            if not cmd_line.strip().startswith("curl"):
                cmd_line = "curl " + cmd_line
            
            # Add -k option if not present
            if "-k" not in cmd_line and "--insecure" not in cmd_line:
                # Insert -k after curl and before other options
                parts = cmd_line.split(maxsplit=1)
                if len(parts) == 1:
                    cmd_line = "curl -k"
                else:
                    cmd_line = "curl -k " + parts[1]
            
            print(f"Executing: {cmd_line}")
            
            result = subprocess.run(
                cmd_line, 
                shell=True, 
                text=True, 
                capture_output=True, 
                timeout=30
            )
            
            output = result.stdout if result.stdout else result.stderr
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
            "When you need to fetch information from a URL, include a curl command in your response. "
            "For example: 'curl https://api.example.com/data' or 'curl -H \"Accept: application/json\" https://api.example.com'. "
            "The curl output will be automatically executed and provided back to you. "
            "Keep curl commands simple and use common APIs or websites. "
            "For HTML pages, you'll receive a truncated version focusing on the title and beginning of the content. "
            "Note: All curl commands will be executed with -k (insecure) option."
        )