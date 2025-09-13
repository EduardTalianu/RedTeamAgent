"""
Chat interface components for the GUI.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import datetime
import threading
import requests
import json
import re
from typing import Dict, List, Optional, Any
import xml.etree.ElementTree as ET

class ChatTab(ttk.Frame):
    """Chat interface tab for the application."""
    
    def __init__(self, parent, server_url: str = "http://127.0.0.1:11436"):
        super().__init__(parent)
        self.server_url = server_url
        self.models = {}
        self.history = []
        self.is_sending = False
        self.conversation_ended = False
        self.tools = {}
        self.tool_buttons = {}
        self.task_orchestrator = None  # Will be set by the main application
        
        self._build_widgets()
        self._refresh_models()
    
    def set_task_orchestrator(self, task_orchestrator):
        """Set the task orchestrator reference."""
        self.task_orchestrator = task_orchestrator
        
        # Update the agent creator tool with the task orchestrator
        if 'mcp_agent_creator' in self.tools:
            self.tools['mcp_agent_creator'].task_orchestrator = task_orchestrator
    
    def _build_widgets(self):
        """Build the chat interface widgets."""
        
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
        
        # === Tools Frame ===
        tools_frame = ttk.Frame(self, padding="5")
        tools_frame.pack(side="top", fill="x")
        
        # Tools label
        ttk.Label(tools_frame, text="Tools:", font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=(0, 10))
        
        # Tool buttons container
        self.tools_container = ttk.Frame(tools_frame)
        self.tools_container.pack(side="left", fill="x", expand=True)
        
        # User action buttons container
        actions_container = ttk.Frame(tools_frame)
        actions_container.pack(side="right")
        
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
        
        # Chat display
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame,
            wrap="word",
            state="disabled",
            height=25,
            width=80,
            font=("Consolas", 10)
        )
        self.chat_display.pack(fill="both", expand=True)
        
        # Configure text tags
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
        
        # Bind Enter key
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
        """Populate the model dropdown."""
        model_list = []
        for provider, models in self.models.items():
            for model in models:
                if "whisper" not in model.lower():
                    model_list.append(f"{provider}-{model}")
        
        if not model_list:
            model_list = ["groq-mixtral-8x7b-32768"]
        
        self.model_combo["values"] = model_list
        if model_list:
            self.model_var.set(model_list[0])
    
    def _refresh_models(self):
        """Refresh the list of available models."""
        try:
            resp = requests.get(f"{self.server_url}/api/models", timeout=5)
            resp.raise_for_status()
            self.models = resp.json()["models"]
            self._populate_models()
            self._print_message("[Models list refreshed]\n", "system")
        except Exception as e:
            print(f"Warning: Cannot fetch model list: {e}")
    
    def _print_message(self, text: str, tag: str = ""):
        """Print a message to the chat display."""
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", text, tag)
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")
    
    def _on_enter_key(self, event):
        """Handle Enter key press."""
        if event.state & 0x0001:  # Shift is pressed
            return None
        self.send_message()
        return "break"
    
    def send_message(self):
        """Send a message to the LLM."""
        if self.is_sending or self.conversation_ended:
            return
        
        if not self.model_var.get():
            self._print_message("[Please select a model first]\n", "error")
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
        
        # Add system messages for enabled tools and agents
        if len(self.history) == 1:  # First message
        # Create a summary of enabled tools with their proper system prompts
            enabled_tools = []
            detailed_tool_instructions = []
            
            for tool_name, tool in self.tools.items():
                if tool.enabled:
                    # Get display name - use friendly_name if available
                    display_name = getattr(tool, 'friendly_name', tool_name)
                    enabled_tools.append(f"- {display_name}: {getattr(tool, 'description', 'No description')}")
                    
                    # Get the detailed system prompt from the tool
                    if hasattr(tool, 'get_system_prompt'):
                        detailed_tool_instructions.append(tool.get_system_prompt())
            
            # Build the orchestrator system prompt
            orchestrator_prompt = (
                "You are a TASK ORCHESTRATOR. Your primary role is to create and manage specialized agents to perform tasks, "
                "NOT to perform tasks yourself.\n\n"
                "CRITICAL RULES:\n"
                "1. NEVER perform tasks directly yourself - always create agents to do the work.\n"
                "2. Analyze each user request and determine what agents are needed.\n"
                "3. Create appropriate agents for each component of the task.\n"
                "4. Wait for agent results before providing your final response.\n"
                "5. When an agent completes, ANALYZE the results and provide a summary to the user.\n"
                "6. If further analysis is needed, create additional agents.\n"
                "7. Your value is in coordination and delegation, not execution.\n"
                "8. ONCE A TASK IS COMPLETED AND YOU HAVE PROVIDED A SUMMARY, DO NOT CREATE MORE AGENTS UNLESS THE USER ASKS FOR MORE.\n\n"
                "WHEN TO CREATE AGENTS:\n"
                "- For ANY data gathering (web searches, API calls, reconnaissance)\n"
                "- For ANY data analysis or processing\n"
                "- For ANY content creation or writing tasks\n"
                "- For ANY calculations or technical operations\n"
                "- For ANY task that takes more than a few seconds\n"
                "- For ANY multi-step process\n"
                "- For ANY task requiring specialized knowledge\n\n"
                "IMPORTANT: When you have completed the task and provided a summary to the user, "
                "consider the task finished. Do not continue creating agents unless the user explicitly asks for more.\n"
                "If you determine that further investigation would not yield additional useful information, "
                "clearly state this conclusion and consider the task complete."
                "CRITICAL STOPPING CONDITION:\n"
                "If you have analyzed agent results and provided a comprehensive summary, "
                "conclude with 'TASK COMPLETE' and do NOT create additional agents.\n"
                "Stop creating agents when:\n"
                "- You have sufficient information to answer the user's question\n"
                "- Multiple agents have completed similar tasks\n" 
                "- You have provided a complete analysis or summary\n"
            )
            
            # Add tools information if available
            if enabled_tools:
                orchestrator_prompt += (
                    "\n\nAVAILABLE TOOLS:\n"
                    "You have access to these tools:\n"
                    + "\n".join(enabled_tools) + "\n\n"
                    "Use the Agent Creator tool to create specialized agents for tasks.\n"
                )
            
            # Add to history as system message
            self.history.insert(0, {"role": "system", "content": orchestrator_prompt})
            
            # Add detailed instructions for each enabled tool
            for instruction in detailed_tool_instructions:
                self.history.insert(-1, {"role": "system", "content": instruction})
        
        # Start background thread for API call
        threading.Thread(target=self._call_api, daemon=True).start()
    
    def _call_api(self):
        """Make API call to the server."""
        try:
            model = self.model_var.get()
            url = f"{self.server_url}/api/chat"
            
            payload = {
                "model": model,
                "messages": self.history,
                "temperature": self.temp_var.get(),
                "max_tokens": self.max_tokens_var.get(),
                "stream": True
            }
            
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
            for chunk in self._parse_sse_response(response):
                if chunk:
                    self._print_message(chunk, "assistant")
                    full_response.append(chunk)
            
            self._print_message("\n", "assistant")
            
            # Join the full response
            ai_response = "".join(full_response)
            
            # Check if AI is performing tasks directly instead of creating agents
            if self._is_direct_task_execution(ai_response):
                # Remind the AI to create agents
                self._print_message("[Orchestrator Reminder: Please create agents to perform tasks rather than doing them directly]\n", "system")
                reminder_message = (
                    "Remember: You are a task orchestrator. Please create specialized agents to perform tasks "
                    "instead of doing them directly. Use the Agent Creator tool to delegate work."
                )
                self.history.append({"role": "system", "content": reminder_message})
                
                # Ask AI to try again with agent creation
                self._print_message("AI (rethinking with agent creation): ", "assistant")
                threading.Thread(target=self._call_api, daemon=True).start()
                return
            
            # Add the AI's response to history
            self.history.append({"role": "assistant", "content": ai_response})
            
            # Check for tool usage (including agent creation)
            tool_used = False
            for tool_name, tool in self.tools.items():
                if tool.enabled:
                    command = tool.detect_request(ai_response)
                    if command:
                        # Execute the tool
                        self._execute_tool_for_ai(tool, command, ai_response)
                        tool_used = True
                        break
            
            # If no tool was used, remind the AI to create agents
            if not tool_used:
                self._print_message("[Orchestrator Reminder: Please create agents to handle this task]\n", "system")
                reminder_message = (
                    "You are a task orchestrator. Please create specialized agents to perform this task "
                    "instead of providing information directly. Use the Agent Creator tool."
                )
                self.history.append({"role": "system", "content": reminder_message})
                
                # Ask AI to try again with agent creation
                self._print_message("AI (rethinking with agent creation): ", "assistant")
                threading.Thread(target=self._call_api, daemon=True).start()
                return
            
        except requests.exceptions.Timeout:
            self._print_message("\n[Error: Request timed out]\n", "error")
        except requests.exceptions.RequestException as e:
            self._print_message(f"\n[Error: {str(e)}]\n", "error")
        except Exception as e:
            self._print_message(f"\n[Unexpected error: {str(e)}]\n", "error")
        finally:
            self.is_sending = False
            self.send_button.config(state="normal", text="Send")
    
    def _parse_sse_response(self, response):
        """Parse SSE response from the streaming endpoint."""
        for line in response.iter_lines():
            if not line:
                continue
                
            line = line.decode('utf-8') if isinstance(line, bytes) else line
            
            if line.startswith("data: "):
                data = line[6:]
                
                if data.strip() == "[DONE]":
                    break
                    
                try:
                    chunk = json.loads(data)
                    if "choices" in chunk:
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield delta["content"]
                except json.JSONDecodeError:
                    if data.strip():
                        yield data
    
    def _is_direct_task_execution(self, response: str) -> bool:
        """Check if the AI is performing tasks directly instead of creating agents."""
        # Patterns that indicate direct task execution
        direct_execution_patterns = [
            r"I'll perform",
            r"I will do",
            r"Let me gather",
            r"I found that",
            r"Here's the information",
            r"The results show",
            r"Based on my analysis",
            r"I can tell you that",
            r"After checking",
            r"I discovered",
            r"My research shows"
        ]
        
        # Check if response contains direct execution patterns
        for pattern in direct_execution_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                # Also check if there are no agent creation requests
                agent_creator_tool = self.tools.get('mcp_agent_creator')
                if agent_creator_tool and agent_creator_tool.enabled:
                    if not agent_creator_tool.detect_request(response):
                        # Make sure this isn't a response analyzing agent results
                        analysis_patterns = [
                            r"Agent.*completed",
                            r"Based on the agent's results",
                            r"The agent found",
                            r"According to the agent",
                            r"passive reconnaissance has not revealed",
                            r"we can conclude that",
                            r"further agents are not needed"
                        ]
                        
                        is_analysis = any(re.search(p, response, re.IGNORECASE) for p in analysis_patterns)
                        
                        if not is_analysis:
                            return True
        
        return False
    
    def _execute_tool_for_ai(self, tool, command, ai_response: str):
        """Execute a tool command requested by the AI and feed results back."""
        # Get display name - use friendly_name if available
        display_name = getattr(tool, 'friendly_name', tool.name)
        
        # Handle different types of commands
        if command == "LIST_COMMANDS":
            self._print_message(f"\n[Listing available {display_name} commands]\n", "system")
            tool_output = tool.execute(command)
        elif isinstance(command, dict):
            # New format with parsed parameters (MCP format)
            self._print_message(f"\n[Executing {display_name} with parameters]\n", "system")
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
            self._print_message(f"\n[Executing {display_name} with command: {command}]\n", "system")
            tool_output = tool.execute(command)
        
        # Truncate output if it's too large (over 2000 characters)
        if len(tool_output) > 2000:
            tool_output = tool_output[:2000] + "\n\n[Output truncated due to size limitations]"
        
        # Display the tool output
        self._print_message(f"[{display_name} output: {tool_output}]\n", "system")
        
        # Add the AI's response to history
        self.history.append({"role": "assistant", "content": ai_response})
        
        # Special handling for agent creator tool - wait for agents to complete
        if tool.__class__.__name__ == 'McpAgentCreator':
            # Extract agent ID from the result
            import re
            agent_id_match = re.search(r'Agent ID: (\d+)', tool_output)
            if agent_id_match:
                agent_id = int(agent_id_match.group(1))
                # Don't add tool results as a follow-up message for agent creator
                # Instead, wait for the agent to complete and then continue
                self._wait_for_agent_and_continue(agent_id)
                return
            else:
                # If no agent ID was found, add tool results as a follow-up message
                tool_result_msg = f"The {display_name} tool was executed with the following result:\n{tool_output}"
                self.history.append({"role": "user", "content": tool_result_msg})
        else:
            # Add tool results as a follow-up message and get AI to process it
            tool_result_msg = f"The {display_name} tool was executed with the following result:\n{tool_output}"
            self.history.append({"role": "user", "content": tool_result_msg})
        
        # Ask AI to process the tool results
        self._print_message(f"AI (processing {display_name} results): ", "assistant")
        threading.Thread(target=self._call_api, daemon=True).start()
    
    def _wait_for_agent_and_continue(self, agent_id):
        """Wait for a specific agent to complete and then continue the conversation."""
        if not self.task_orchestrator:
            self._print_message("[Error: Task orchestrator not available]\n", "error")
            return
        
        # Get the agent from the task orchestrator
        agent = self.task_orchestrator.agents.get(agent_id)
        if not agent:
            self._print_message(f"[Error: Agent {agent_id} not found]\n", "error")
            return
        
        # Wait for the agent to complete in a separate thread
        def wait_for_agent():
            import time
            
            # Wait for the agent to complete
            while agent.status in ['PENDING', 'WORKING']:
                time.sleep(0.5)
            
            # Add agent result to conversation
            if agent.status == 'SUCCESS':
                # Format the agent results in a readable way with proper type checking
                result_message = f"Agent {agent.name} completed successfully."
                
                if agent.result:
                    if isinstance(agent.result, dict):
                        # Handle different types of results
                        if 'results' in agent.result:
                            results_data = agent.result['results']
                            if isinstance(results_data, list):
                                # Handle list of results (e.g., web search results)
                                formatted_results = []
                                for i, result in enumerate(results_data, 1):
                                    if isinstance(result, dict):
                                        title = result.get('title', 'No title')
                                        url = result.get('url', 'No URL')
                                        snippet = result.get('snippet', 'No snippet')
                                        formatted_results.append(f"{i}. {title}")
                                        if url:
                                            formatted_results.append(f"   URL: {url}")
                                        if snippet:
                                            formatted_results.append(f"   Snippet: {snippet}")
                                        formatted_results.append("")
                                    else:
                                        formatted_results.append(f"{i}. {str(result)}")
                                
                                if formatted_results:
                                    result_text = "\n".join(formatted_results)
                                    result_message = f"Agent {agent.name} completed with results:\n{result_text}"
                            elif isinstance(results_data, dict):
                                # Handle dictionary of results (e.g., DNS analysis results)
                                formatted_results = []
                                for key, value in results_data.items():
                                    formatted_results.append(f"{key}: {value}")
                                
                                if formatted_results:
                                    result_text = "\n".join(formatted_results)
                                    result_message = f"Agent {agent.name} completed with results:\n{result_text}"
                            else:
                                # Handle string or other types
                                result_message = f"Agent {agent.name} completed with results:\n{str(results_data)}"
                        
                        # Add conclusions if available
                        if 'conclusions' in agent.result and isinstance(agent.result['conclusions'], list):
                            conclusions = "\n".join([f"• {conclusion}" for conclusion in agent.result['conclusions']])
                            result_message += f"\n\nKey Conclusions:\n{conclusions}"
                    else:
                        # Handle non-dictionary results
                        result_message = f"Agent {agent.name} completed with result: {str(agent.result)}"
                
                self.history.append({"role": "system", "content": result_message})
                self._print_message(f"[Agent {agent.name} completed]\n", "system")
                
                # Add a user message with specific instructions for analyzing the results
                analysis_instruction = (
                    f"Please analyze the results from the {agent.name} and provide a summary "
                    f"of the findings. If additional agents are needed to gather more information "
                    f"or perform further analysis, please create them."
                )
                self.history.append({"role": "user", "content": analysis_instruction})
            else:
                error_message = f"Agent {agent.name} failed: {agent.error or 'Unknown error'}"
                self.history.append({"role": "system", "content": error_message})
                self._print_message(f"[Agent {agent.name} failed: {agent.error or 'Unknown error'}]\n", "error")
                
                # Add a user message with instructions for handling the error
                error_instruction = (
                    f"The {agent.name} failed. Please analyze the error and determine if "
                    f"the task can be retried with different parameters, if a different "
                    f"type of agent should be created, or if the task is impossible."
                )
                self.history.append({"role": "user", "content": error_instruction})
            
            # Ask AI to process the agent results
            self._print_message("AI (processing agent results): ", "assistant")
            
            # Make another API call to process the agent results
            self.is_sending = True
            self.send_button.config(state="disabled", text="Processing...")
            threading.Thread(target=self._call_api, daemon=True).start()
        
        threading.Thread(target=wait_for_agent, daemon=True).start()
    
    def set_tools(self, tools: Dict[str, Any]):
        """Set available tools."""
        self.tools = tools
        
        # Update the agent creator tool with the task orchestrator
        if 'mcp_agent_creator' in tools and self.task_orchestrator:
            tools['mcp_agent_creator'].task_orchestrator = self.task_orchestrator
    
    def toggle_tool(self, tool):
        """Toggle a tool on/off."""
        tool.enabled = not tool.enabled
        button = self.tool_buttons[tool.__class__.__name__.lower()]
        
        display_name = getattr(tool, 'friendly_name', tool.name)
        
        if tool.enabled:
            button.config(text=f"Disable {display_name}")
            self._print_message(f"[{display_name} ENABLED]\n", "system")
        else:
            button.config(text=f"Enable {display_name}")
            self._print_message(f"[{display_name} DISABLED]\n", "system")
    
    def clear_chat(self):
        """Clear the chat display and history."""
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self.history.clear()
        self.conversation_ended = False
        self._print_message("Chat cleared. Starting fresh!\n", "system")
    
    def save_chat(self, filename: str = None):
        """Save the chat to a file."""
        if filename is None:
            from tkinter import filedialog
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                initialfile=f"chat_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
            )
            if not filename:
                return False
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.chat_display.get("1.0", "end"))
            return True
        except Exception as e:
            print(f"Error saving chat: {e}")
            return False