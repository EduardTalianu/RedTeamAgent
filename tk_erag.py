#!/usr/bin/env python3
"""
Tkinter chat client for EragAPI — works with the server.
Handles streaming responses and provides local curl execution capability.
"""
import datetime
import json
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import requests
import re

DEFAULT_SERVER = "http://127.0.0.1:11436"


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


def local_curl(cmd_line: str) -> str:
    """Run curl command locally and return the output."""
    try:
        # Ensure the command starts with curl
        if not cmd_line.strip().startswith("curl"):
            cmd_line = "curl " + cmd_line
        
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
        self.curl_enabled = False
        self.is_sending = False
        
        # Build the interface
        self._build_widgets()
        
        # Welcome message
        self._print_message(
            "Welcome! Select a model and start chatting.\n"
            "Click 'Enable Curl' to allow the AI to execute local curl commands.\n",
            "system"
        )
    
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
        
        # Buttons frame
        buttons_frame = ttk.Frame(input_frame)
        buttons_frame.pack(side="right", padx=(5, 0))
        
        # Send button
        self.send_button = ttk.Button(
            buttons_frame,
            text="Send",
            command=self.send_message,
            state="normal"
        )
        self.send_button.pack(fill="x", pady=(0, 3))
        
        # Curl tool button
        self.curl_button = ttk.Button(
            buttons_frame,
            text="Enable Curl",
            command=self.toggle_curl_tool
        )
        self.curl_button.pack(fill="x", pady=(0, 3))
        
        # Clear chat button
        ttk.Button(
            buttons_frame,
            text="Clear Chat",
            command=self.clear_chat
        ).pack(fill="x", pady=(0, 3))
        
        # Save chat button
        ttk.Button(
            buttons_frame,
            text="Save Chat",
            command=self.save_chat
        ).pack(fill="x")
    
    def _populate_models(self):
        """Populate the model dropdown with available models."""
        model_list = []
        for provider, models in self.models.items():
            for model in models:
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
    
    def toggle_curl_tool(self):
        """Toggle the curl tool on/off."""
        self.curl_enabled = not self.curl_enabled
        if self.curl_enabled:
            self.curl_button.config(text="Disable Curl")
            self._print_message(
                "[Curl tool ENABLED - AI can now execute local curl commands]\n", 
                "system"
            )
        else:
            self.curl_button.config(text="Enable Curl")
            self._print_message(
                "[Curl tool DISABLED]\n", 
                "system"
            )
    
    def clear_chat(self):
        """Clear the chat display and history."""
        if messagebox.askyesno("Clear Chat", "Clear all conversation history?"):
            self.chat_display.configure(state="normal")
            self.chat_display.delete("1.0", "end")
            self.chat_display.configure(state="disabled")
            self.history.clear()
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
    
    def detect_curl_request(self, text: str):
        """Detect if the AI is requesting to execute a curl command."""
        # Look for curl commands in the AI's response
        curl_patterns = [
            r'curl\s+["\']?https?://[^\s"\']+',  # curl http://...
            r'curl\s+-[A-Za-z]\s+',  # curl with flags
            r'`curl\s+[^`]+`',  # curl in backticks
        ]
        
        for pattern in curl_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0).strip('`')
        return None
    
    def send_message(self):
        """Send a message to the AI."""
        if self.is_sending:
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
        
        # If curl is enabled, add a system message to inform the AI
        if self.curl_enabled and len(self.history) == 1:  # First message
            system_msg = (
                "You can execute curl commands to fetch data from URLs. "
                "When you need to fetch information from a URL, simply include "
                "a curl command in your response and it will be executed automatically."
            )
            self.history.insert(0, {"role": "system", "content": system_msg})
        
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
            
            # Check if AI wants to execute curl (if curl is enabled)
            if self.curl_enabled:
                curl_cmd = self.detect_curl_request(ai_response)
                if curl_cmd:
                    self._execute_curl_for_ai(curl_cmd, ai_response)
                else:
                    # Just add the response to history
                    self.history.append({"role": "assistant", "content": ai_response})
            else:
                self.history.append({"role": "assistant", "content": ai_response})
            
        except requests.exceptions.Timeout:
            self._print_message("\n[Error: Request timed out]\n", "error")
        except requests.exceptions.RequestException as e:
            self._print_message(f"\n[Error: {str(e)}]\n", "error")
        except Exception as e:
            self._print_message(f"\n[Unexpected error: {str(e)}]\n", "error")
        finally:
            # Re-enable send button
            self.is_sending = False
            self.send_button.config(state="normal", text="Send")
    
    def _execute_curl_for_ai(self, curl_cmd: str, ai_response: str):
        """Execute a curl command requested by the AI and feed results back."""
        self._print_message(f"\n[Executing curl command: {curl_cmd}]\n", "system")
        
        # Execute the curl command
        curl_output = local_curl(curl_cmd)
        
        # Display the curl output (truncated if too long)
        display_output = curl_output[:500] + "..." if len(curl_output) > 500 else curl_output
        self._print_message(f"[Curl output: {display_output}]\n", "system")
        
        # Add the AI's response to history
        self.history.append({"role": "assistant", "content": ai_response})
        
        # Add curl results as a follow-up message and get AI to process it
        curl_result_msg = f"The curl command returned:\n{curl_output}"
        self.history.append({"role": "user", "content": curl_result_msg})
        
        # Ask AI to process the curl results
        self._print_message("AI (processing curl results): ", "assistant")
        
        # Make another API call to process the curl results
        threading.Thread(target=self._call_api, daemon=True).start()


# ---------- Main ----------
if __name__ == "__main__":
    app = ChatGUI()
    app.mainloop()