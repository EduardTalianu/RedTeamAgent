#!/usr/bin/env python3
"""
Tkinter chat client for EragAPI — works with the server.
Handles streaming responses and provides plugin support for tools.
"""
import datetime
import importlib.util
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import requests
import re

DEFAULT_SERVER = "http://127.0.0.1:11436"
TOOLS_DIR = "tools"

# ---------- helpers ----------
def get_models(server: str) -> dict:
    """Fetch available models from the server."""
    try:
        resp = requests.get(f"{server}/api/models", timeout=5)
        resp.raise_for_status()
        return resp.json()["models"]
    except Exception as e:
        print(f"Warning: Cannot fetch model list: {e}")
        # Return default models if server is not accessible
        return {
            "groq": ["mixtral-8x7b-32768", "llama-3.1-70b-versatile"],
            "gemini": ["gemini-pro"],
            "ollama": ["llama2"]
        }

def parse_sse_response(response):
    """
    Parse SSE (Server-Sent Events) response from the streaming endpoint.
    Yields text content from the stream.
    """
    buffer = ""
    
    for line in response.iter_lines():
        if not line:
            continue
            
        line = line.decode('utf-8') if isinstance(line, bytes) else line
        
        # First, check if this looks like a raw ChatCompletionChunk string
        if "ChatCompletionChunk" in line:
            # Extract the actual chunk object from the string representation
            try:
                # Find the JSON-like content within the string
                import re
                # Look for content field in the delta
                content_match = re.search(r"content='([^']*)'", line)
                if content_match and content_match.group(1):
                    yield content_match.group(1)
                continue
            except:
                pass
        
        # Handle SSE format: "data: ..."
        if line.startswith("data: "):
            data = line[6:]  # Remove "data: " prefix
            
            if data.strip() == "[DONE]":
                break
                
            # First check if it's a raw Python object string (like ChatCompletionChunk)
            if "ChatCompletionChunk" in data:
                try:
                    import re
                    content_match = re.search(r"content='([^']*)'", data)
                    if content_match and content_match.group(1):
                        yield content_match.group(1)
                except:
                    pass
                continue
                
            try:
                # Try to parse as JSON (OpenAI/Groq format)
                chunk = json.loads(data)
                
                # Handle different response formats
                if "choices" in chunk:
                    # OpenAI/Groq format
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if "content" in delta and delta["content"]:
                        yield delta["content"]
                elif "text" in chunk:
                    # Simple text format
                    yield chunk["text"]
                elif "message" in chunk:
                    # Possible error or info message
                    yield chunk["message"]
                else:
                    # Fallback: yield the raw data if it's not empty
                    if data.strip() and data.strip() != "{}":
                        yield data
            except json.JSONDecodeError:
                # If not JSON, treat as plain text
                if data.strip():
                    yield data
        else:
            # Sometimes the server sends raw content without SSE format
            # Try to extract content from ChatCompletionChunk objects
            if "ChatCompletionChunk" in line:
                try:
                    import re
                    content_match = re.search(r"content='([^']*)'", line)
                    if content_match and content_match.group(1):
                        yield content_match.group(1)
                except:
                    pass

# ---------- Tool Loading System ----------
class ToolLoader:
    """Dynamically loads tools from the tools directory."""
    
    @staticmethod
    def load_tools():
        """Load all available tools from the tools directory."""
        tools = {}
        
        # Get the directory where the script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        tools_path = os.path.join(script_dir, TOOLS_DIR)
        
        # Ensure tools directory exists
        if not os.path.exists(tools_path):
            print(f"Creating tools directory at: {tools_path}")
            os.makedirs(tools_path)
            return tools
        
        print(f"Looking for tools in: {tools_path}")
        
        # Load all Python files in tools directory (except __init__.py)
        for filename in os.listdir(tools_path):
            if filename.endswith('.py') and filename != '__init__.py':
                tool_name = filename[:-3]  # Remove .py extension
                try:
                    # Import the module
                    module_path = os.path.join(tools_path, filename)
                    print(f"Loading tool from: {module_path}")
                    
                    spec = importlib.util.spec_from_file_location(tool_name, module_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Get the tool class (assumed to be the same name as the file)
                    class_name = tool_name.capitalize()
                    if hasattr(module, class_name):
                        tool_class = getattr(module, class_name)
                        tool_instance = tool_class()
                        tools[tool_name] = tool_instance
                        print(f"Successfully loaded tool: {tool_name} ({class_name})")
                    else:
                        print(f"Error: Class {class_name} not found in {filename}")
                except Exception as e:
                    print(f"Error loading tool {tool_name}: {e}")
        
        print(f"Total tools loaded: {len(tools)}")
        return tools

# ---------- GUI ----------
class ChatGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EragAPI Chat — Tkinter Client")
        self.geometry("900x700")
        
        # Configuration
        self.server = DEFAULT_SERVER
        self.models = get_models(self.server)
        self.history = []  # Chat history for the API
        self.is_sending = False
        self.conversation_ended = False  # Track if conversation has been ended
        self.checked_domains = set()  # Track domains that have been checked
        self.server_process = None  # Track the server process
        
        # Load tools
        print("Loading tools...")
        self.tools = ToolLoader.load_tools()
        print(f"Available tools: {list(self.tools.keys())}")
        self.tool_buttons = {}  # Store tool buttons for state management
        
        # Build the interface
        self._build_widgets()
        
        # Welcome message
        welcome_msg = "Welcome! Select a model and start chatting.\n"
        if self.tools:
            welcome_msg += "Available tools: " + ", ".join([tool.name for tool in self.tools.values()]) + "\n"
            welcome_msg += "Enable tools to allow the AI to use them.\n"
        welcome_msg += "Click 'Start Server' to launch the EragAPI server.\n"
        self._print_message(welcome_msg, "system")
    
    def _build_widgets(self):
        """Build the GUI widgets."""
        
        # === Top Frame (Model Selection and Settings) ===
        top_frame = ttk.Frame(self, padding="5")
        top_frame.pack(side="top", fill="x")
        
        # Model selection
        ttk.Label(top_frame, text="Model:").pack(side="left", padx=(0, 5))
        
        self.model_var = tk.StringVar()
        self.model_combo = ttk.Combobox(
            top_frame, 
            textvariable=self.model_var,
            state="readonly", 
            width=40
        )
        self._populate_models()
        self.model_combo.pack(side="left", padx=(0, 5))
        
        # Refresh models button
        ttk.Button(
            top_frame, 
            text="↻", 
            width=3,
            command=self._refresh_models
        ).pack(side="left", padx=(0, 10))
        
        # Separator
        ttk.Separator(top_frame, orient="vertical").pack(
            side="left", fill="y", padx=10
        )
        
        # Temperature control
        ttk.Label(top_frame, text="Temperature:").pack(side="left", padx=(0, 5))
        self.temp_var = tk.DoubleVar(value=0.7)
        temp_scale = ttk.Scale(
            top_frame, 
            from_=0, 
            to=2,
            variable=self.temp_var,
            orient="horizontal", 
            length=120
        )
        temp_scale.pack(side="left", padx=(0, 5))
        
        self.temp_label = ttk.Label(top_frame, text="0.7", width=4)
        self.temp_label.pack(side="left", padx=(0, 10))
        temp_scale.configure(
            command=lambda v: self.temp_label.config(text=f"{float(v):.1f}")
        )
        
        # Max tokens control
        ttk.Label(top_frame, text="Max Tokens:").pack(side="left", padx=(0, 5))
        self.max_tokens_var = tk.IntVar(value=1000)
        ttk.Spinbox(
            top_frame, 
            from_=100, 
            to=4000,
            textvariable=self.max_tokens_var,
            width=8
        ).pack(side="left")
        
        # === Tools Frame (New row for tools) ===
        tools_frame = ttk.Frame(self, padding="5")
        tools_frame.pack(side="top", fill="x")
        
        # Tools label
        ttk.Label(tools_frame, text="Tools:", font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=(0, 10))
        
        # Tool buttons container
        tools_container = ttk.Frame(tools_frame)
        tools_container.pack(side="left", fill="x", expand=True)
        
        # Add tool buttons
        print(f"Creating buttons for {len(self.tools)} tools")
        for tool_name, tool in self.tools.items():
            print(f"Creating button for tool: {tool_name} ({tool.name})")
            btn = ttk.Button(
                tools_container,
                text=f"Enable {tool.name}",
                command=lambda t=tool: self.toggle_tool(t)
            )
            btn.pack(side="left", padx=2)
            self.tool_buttons[tool_name] = btn
        
        # User action buttons container
        actions_container = ttk.Frame(tools_frame)
        actions_container.pack(side="right")
        
        # Start server button
        self.start_server_button = ttk.Button(
            actions_container,
            text="Start Server",
            command=self.start_server
        )
        self.start_server_button.pack(side="right", padx=2)
        
        # Clear chat button
        ttk.Button(
            actions_container,
            text="Clear Chat",
            command=self.clear_chat
        ).pack(side="right", padx=2)
        
        # Save chat button
        ttk.Button(
            actions_container,
            text="Save Chat",
            command=self.save_chat
        ).pack(side="right", padx=2)
        
        # === Chat Display Area ===
        chat_frame = ttk.Frame(self)
        chat_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Use ScrolledText for better text handling
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap="word",
            state="disabled",
            height=25,
            width=80,
            font=("Consolas", 10)
        )
        self.chat_display.pack(fill="both", expand=True)
        
        # Configure text tags for different message types
        self.chat_display.tag_config("user", foreground="#0066cc")
        self.chat_display.tag_config("assistant", foreground="#008800")
        self.chat_display.tag_config("system", foreground="#666666", font=("Consolas", 9, "italic"))
        self.chat_display.tag_config("error", foreground="#cc0000")
        self.chat_display.tag_config("server", foreground="#0066cc", font=("Consolas", 9, "bold"))
        
        # === Input Area ===
        input_frame = ttk.Frame(self)
        input_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        
        # Text input
        self.input_text = tk.Text(
            input_frame, 
            height=3, 
            wrap="word",
            font=("Consolas", 10)
        )
        self.input_text.pack(side="left", fill="both", expand=True)
        
        # Bind Enter key to send (Shift+Enter for new line)
        self.input_text.bind("<Return>", self._on_enter_key)
        self.input_text.bind("<Shift-Return>", lambda e: None)
        
        # Send button
        self.send_button = ttk.Button(
            input_frame,
            text="Send",
            command=self.send_message,
            state="normal",
            width=10
        )
        self.send_button.pack(side="right", padx=(5, 0))
    
    def _populate_models(self):
        """Populate the model dropdown with available models."""
        model_list = []
        for provider, models in self.models.items():
            for model in models:
                # Filter out models that don't support chat completions
                if "whisper" not in model.lower():
                    model_list.append(f"{provider}-{model}")
        
        if not model_list:
            model_list = ["groq-mixtral-8x7b-32768"]
        
        self.model_combo["values"] = model_list
        if model_list:
            self.model_var.set(model_list[0])
    
    def _refresh_models(self):
        """Refresh the list of available models from the server."""
        self.models = get_models(self.server)
        self._populate_models()
        self._print_message("[Models list refreshed]\n", "system")
    
    def _print_message(self, text: str, tag: str = ""):
        """Print a message to the chat display."""
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", text, tag)
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")
    
    def _on_enter_key(self, event):
        """Handle Enter key press in input field."""
        if event.state & 0x0001:  # Shift is pressed
            return None
        self.send_message()
        return "break"
    
    def start_server(self):
        """Start the EragAPI server."""
        if self.server_process and self.server_process.poll() is None:
            self._print_message("[Server is already running]\n", "server")
            return
        
        # Get the path to eragAPI.py (same directory as this script)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        server_script = os.path.join(script_dir, "eragAPI.py")
        
        if not os.path.exists(server_script):
            self._print_message(f"[Error: eragAPI.py not found at {server_script}]\n", "error")
            return
        
        # Command to start the server
        command = [sys.executable, server_script, "serve"]
        
        self._print_message(f"[Starting server with command: {' '.join(command)}]\n", "server")
        
        try:
            # Start the server process
            self.server_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Start a thread to read and display server output
            def read_server_output():
                for line in self.server_process.stdout:
                    self._print_message(f"[SERVER] {line.strip()}\n", "server")
                
                # When the process ends
                self._print_message("[Server process ended]\n", "server")
                self.server_process = None
            
            threading.Thread(target=read_server_output, daemon=True).start()
            
            # Update button text
            self.start_server_button.config(text="Server Running")
            
            # Try to refresh models after a short delay
            self.after(2000, self._refresh_models)
            
        except Exception as e:
            self._print_message(f"[Error starting server: {str(e)}]\n", "error")
    
    def toggle_tool(self, tool):
        """Toggle a tool on/off."""
        tool.enabled = not tool.enabled
        button = self.tool_buttons[tool.__class__.__name__.lower()]
        
        if tool.enabled:
            button.config(text=f"Disable {tool.name}")
            self._print_message(f"[{tool.name} ENABLED]\n", "system")
        else:
            button.config(text=f"Enable {tool.name}")
            self._print_message(f"[{tool.name} DISABLED]\n", "system")
    
    def clear_chat(self):
        """Clear the chat display and history."""
        if messagebox.askyesno("Clear Chat", "Clear all conversation history?"):
            self.chat_display.configure(state="normal")
            self.chat_display.delete("1.0", "end")
            self.chat_display.configure(state="disabled")
            self.history.clear()
            self.conversation_ended = False
            self.checked_domains.clear()
            self._print_message("Chat cleared. Starting fresh!\n", "system")
    
    def save_chat(self):
        """Save the chat to a text file."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"chat_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(self.chat_display.get("1.0", "end"))
                messagebox.showinfo("Saved", f"Chat saved to:\n{filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save chat:\n{str(e)}")
    
    def detect_end_conversation(self, text: str):
        """Detect if the AI is requesting to end the conversation."""
        # Look for the end conversation command
        end_patterns = [
            r'END_CONVERSATION',
            r'END\ CONVERSATION',
            r'CONVERSATION\ ENDED',
            r'NO\ FURTHER\ INVESTIGATION\ NEEDED',
            r'NO\ VULNERABILITIES\ FOUND'
        ]
        
        for pattern in end_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def send_message(self):
        """Send a message to the AI."""
        if self.is_sending or self.conversation_ended:
            return
        
        if not self.model_var.get():
            messagebox.showwarning("No Model", "Please select a model first.")
            return
        
        user_message = self.input_text.get("1.0", "end").strip()
        if not user_message:
            return
        
        # Clear input and update UI
        self.input_text.delete("1.0", "end")
        self.is_sending = True
        self.send_button.config(state="disabled", text="Sending...")
        
        # Display user message
        self._print_message(f"You: {user_message}\n", "user")
        
        # Add to history
        self.history.append({"role": "user", "content": user_message})
        
        # Add system messages for enabled tools
        if len(self.history) == 1:  # First message
            # Create a summary of enabled tools with their proper system prompts
            enabled_tools = []
            detailed_tool_instructions = []
            
            for tool_name, tool in self.tools.items():
                if tool.enabled:
                    enabled_tools.append(f"- {tool.name}: {tool.description}")
                    
                    # Get the detailed system prompt from the tool
                    if hasattr(tool, 'get_system_prompt'):
                        detailed_tool_instructions.append(tool.get_system_prompt())
            
            if enabled_tools:
                # Add general tool summary
                tool_summary = {
                    "role": "system",
                    "content": "You have access to the following tools:\n" + "\n".join(enabled_tools) + 
                            "\n\nEach tool has specific usage instructions that will be provided separately."
                }
                self.history.insert(0, tool_summary)
                
                # Add detailed instructions for each enabled tool
                for instruction in detailed_tool_instructions:
                    detailed_instruction = {
                        "role": "system",
                        "content": instruction
                    }
                    self.history.insert(-1, detailed_instruction)  # Insert before user message
        
        # Start background thread for API call
        threading.Thread(target=self._call_api, daemon=True).start()
    
    def _call_api(self):
        """Make API call to the server (runs in background thread)."""
        try:
            model = self.model_var.get()
            url = f"{self.server}/api/chat"
            
            payload = {
                "model": model,
                "messages": self.history,
                "temperature": self.temp_var.get(),
                "max_tokens": self.max_tokens_var.get(),
                "stream": True
            }
            
            # Make the request
            response = requests.post(
                url, 
                json=payload, 
                stream=True,
                timeout=60
            )
            response.raise_for_status()
            
            # Display AI response
            self._print_message("AI: ", "assistant")
            
            full_response = []
            for chunk in parse_sse_response(response):
                if chunk:
                    self._print_message(chunk, "assistant")
                    full_response.append(chunk)
            
            self._print_message("\n", "assistant")
            
            # Join the full response
            ai_response = "".join(full_response)
            
            # Check if AI wants to end the conversation
            if self.detect_end_conversation(ai_response):
                self._print_message("\n[Conversation ended by AI - no further investigation needed]\n", "system")
                self.conversation_ended = True
                self.history.append({"role": "assistant", "content": ai_response})
            else:
                # Check if AI wants to use any enabled tool
                tool_used = False
                for tool_name, tool in self.tools.items():
                    if tool.enabled:
                        command = tool.detect_request(ai_response)
                        if command:
                            # Execute the tool
                            self._execute_tool_for_ai(tool, command, ai_response)
                            tool_used = True
                            break
                
                # If no tool was used, just add the response to history
                if not tool_used:
                    self.history.append({"role": "assistant", "content": ai_response})
            
        except requests.exceptions.Timeout:
            self._print_message("\n[Error: Request timed out]\n", "error")
        except requests.exceptions.RequestException as e:
            self._print_message(f"\n[Error: {str(e)}]\n", "error")
        except Exception as e:
            self._print_message(f"\n[Unexpected error: {str(e)}]\n", "error")
        finally:
            # Re-enable send button if conversation hasn't ended
            if not self.conversation_ended:
                self.is_sending = False
                self.send_button.config(state="normal", text="Send")
    
    def _execute_tool_for_ai(self, tool, command, ai_response: str):
        """Execute a tool command requested by the AI and feed results back."""
        # Handle different types of commands
        if command == "LIST_COMMANDS":
            self._print_message(f"\n[Listing available {tool.name} commands]\n", "system")
            tool_output = tool.execute(command)
        elif isinstance(command, dict):
            # New format with parsed parameters
            self._print_message(f"\n[Executing {tool.name} with command ID {command.get('command_id', 'unknown')} on target: {command.get('target', 'unknown')}]\n", "system")
            tool_output = tool.execute(command)
        elif isinstance(command, str) and command.startswith("CURL_COMMAND_"):
            # Handle basic detection that wasn't properly parsed - try to extract from AI response
            self._print_message(f"\n[Detected curl command request, parsing AI response...]\n", "system")
            
            # Try to extract command_id and target from the AI response text
            import re
            
            # Look for patterns like "command ID 2" or "command_id: 2"
            id_patterns = [
                r'command\s+id\s+(\d+)',
                r'command_id:\s*(\d+)',
                r'command\s+(\d+)',
                r'id\s+(\d+)'
            ]
            
            command_id = None
            for pattern in id_patterns:
                match = re.search(pattern, ai_response, re.IGNORECASE)
                if match:
                    try:
                        command_id = int(match.group(1))
                        break
                    except:
                        continue
            
            # Look for URL patterns
            url_patterns = [
                r'https?://[^\s]+',
                r'target:\s*(https?://[^\s]+)',
                r'url:\s*(https?://[^\s]+)'
            ]
            
            target_url = None
            for pattern in url_patterns:
                match = re.search(pattern, ai_response, re.IGNORECASE)
                if match:
                    if pattern.startswith('target:') or pattern.startswith('url:'):
                        target_url = match.group(1)
                    else:
                        target_url = match.group(0)
                    break
            
            if command_id and target_url:
                parsed_command = {
                    'command_id': command_id,
                    'target': target_url
                }
                self._print_message(f"[Parsed: command_id={command_id}, target={target_url}]\n", "system")
                tool_output = tool.execute(parsed_command)
            else:
                tool_output = f"Could not parse command from AI response. Please use proper XML format:\n```xml\n<tool>\n  <name>curl</name>\n  <parameters>\n    <command_id>2</command_id>\n    <target>https://example.com</target>\n  </parameters>\n</tool>\n```"
        else:
            # Legacy format
            self._print_message(f"\n[Executing {tool.name} with command: {command}]\n", "system")
            tool_output = tool.execute(command)
        
        # Truncate output if it's too large (over 2000 characters)
        if len(tool_output) > 2000:
            tool_output = tool_output[:2000] + "\n\n[Output truncated due to size limitations]"
        
        # Display the tool output
        self._print_message(f"[{tool.name} output: {tool_output}]\n", "system")
        
        # Add the AI's response to history
        self.history.append({"role": "assistant", "content": ai_response})
        
        # Add tool results as a follow-up message and get AI to process it
        tool_result_msg = f"The {tool.name} tool was executed with the following result:\n{tool_output}"
        self.history.append({"role": "user", "content": tool_result_msg})
        
        # Ask AI to process the tool results
        self._print_message(f"AI (processing {tool.name} results): ", "assistant")
        
        # Make another API call to process the tool results
        threading.Thread(target=self._call_api, daemon=True).start()


# ---------- Main ----------
if __name__ == "__main__":
    print("Starting EragAPI Chat Client...")
    app = ChatGUI()
    app.mainloop()