#!/usr/bin/env python3
"""
Improved EragAPI Chat Application with Fixed Agent Orchestration.
Addresses the loop issues, tool awareness, and result management.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import os
import sys
import subprocess
import threading
import datetime
import requests
import json
import re
import importlib.util
from typing import Dict, List, Optional, Any

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our improved agent system
from agents import agent_registry, BaseAgent, AgentStatus


class ToolLoader:
    """Enhanced tool loader for MCP tools."""
    
    @staticmethod
    def load_tools() -> Dict[str, Any]:
        """Load MCP tools from mcp directory."""
        tools = {}
        script_dir = os.path.dirname(os.path.abspath(__file__))
        mcp_path = os.path.join(script_dir, 'mcp')
        
        if not os.path.exists(mcp_path):
            print(f"MCP directory not found: {mcp_path}")
            return tools
        
        # Add mcp directory to Python path
        if mcp_path not in sys.path:
            sys.path.insert(0, mcp_path)
        
        print(f"Loading MCP tools from: {mcp_path}")
        
        for filename in os.listdir(mcp_path):
            if filename.endswith('.py') and filename.startswith('mcp_') and filename != 'mcp_base.py':
                tool_name = filename[:-3]  # Remove .py
                try:
                    module_path = os.path.join(mcp_path, filename)
                    spec = importlib.util.spec_from_file_location(tool_name, module_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Find tool class (capitalize each word)
                    class_name = ''.join(word.capitalize() for word in tool_name.split('_'))
                    if hasattr(module, class_name):
                        tool_class = getattr(module, class_name)
                        tool_instance = tool_class()
                        tool_instance.enabled = True
                        tools[tool_name] = tool_instance
                        print(f"Loaded MCP tool: {tool_name}")
                    else:
                        print(f"Class {class_name} not found in {filename}")
                        
                except Exception as e:
                    print(f"Error loading tool {tool_name}: {e}")
        
        print(f"Total tools loaded: {len(tools)}")
        return tools


class ImprovedChatInterface(ttk.Frame):
    """Improved chat interface with fixed orchestrator logic."""
    
    def __init__(self, parent, server_url: str = "http://127.0.0.1:11436"):
        super().__init__(parent)
        self.server_url = server_url
        self.models = {}
        self.conversation_history = []
        self.tools = {}
        self.tool_buttons = {}
        self.is_sending = False
        self.waiting_for_agent = False  # Track if we're waiting for agent completion
        self.current_agent_id = None
        
        # Create results directory
        self.results_dir = os.path.join("results", "agents")
        os.makedirs(self.results_dir, exist_ok=True)
        
        self.orchestrator = agent_registry.get_orchestrator()
        self.orchestrator.add_callback(self._on_agent_update)
        
        self._build_interface()
        self._refresh_models()
        self._load_tools()
    
    def _build_interface(self):
        """Build the improved interface."""
        
        # === Top Controls ===
        controls_frame = ttk.Frame(self, padding="5")
        controls_frame.pack(fill="x")
        
        # Model selection
        ttk.Label(controls_frame, text="Model:").pack(side="left", padx=(0, 5))
        self.model_var = tk.StringVar(value="groq-gemma2-9b-it")
        self.model_combo = ttk.Combobox(controls_frame, textvariable=self.model_var, width=30)
        self.model_combo.pack(side="left", padx=(0, 5))
        
        ttk.Button(controls_frame, text="↻", command=self._refresh_models, width=3).pack(side="left", padx=(0, 10))
        
        # Settings
        ttk.Label(controls_frame, text="Temp:").pack(side="left", padx=(0, 5))
        self.temp_var = tk.DoubleVar(value=0.7)
        temp_scale = ttk.Scale(controls_frame, from_=0, to=2, variable=self.temp_var, orient="horizontal", length=100)
        temp_scale.pack(side="left", padx=(0, 5))
        
        self.temp_label = ttk.Label(controls_frame, text="0.7", width=4)
        self.temp_label.pack(side="left", padx=(0, 10))
        temp_scale.configure(command=lambda v: self.temp_label.config(text=f"{float(v):.1f}"))
        
        # Max tokens
        ttk.Label(controls_frame, text="Max Tokens:").pack(side="left", padx=(0, 5))
        self.max_tokens_var = tk.IntVar(value=1500)
        ttk.Spinbox(controls_frame, from_=100, to=4000, textvariable=self.max_tokens_var, width=6).pack(side="left")
        
        # Status indicator
        self.status_label = ttk.Label(controls_frame, text="Ready", foreground="green")
        self.status_label.pack(side="right", padx=(10, 0))
        
        # === Tools Frame ===
        tools_frame = ttk.Frame(self, padding="5")
        tools_frame.pack(fill="x")
        
        ttk.Label(tools_frame, text="Available Tools:", font=("TkDefaultFont", 9, "bold")).pack(side="left", padx=(0, 10))
        self.tools_container = ttk.Frame(tools_frame)
        self.tools_container.pack(side="left", fill="x", expand=True)
        
        # Action buttons
        actions_frame = ttk.Frame(tools_frame)
        actions_frame.pack(side="right")
        
        ttk.Button(actions_frame, text="Clear", command=self.clear_chat).pack(side="left", padx=2)
        ttk.Button(actions_frame, text="Save", command=self.save_chat).pack(side="left", padx=2)
        ttk.Button(actions_frame, text="Stop Agents", command=self.stop_all_agents).pack(side="left", padx=2)
        
        # === Main Content Area ===
        content_frame = ttk.Frame(self)
        content_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create notebook for chat and agents
        self.notebook = ttk.Notebook(content_frame)
        self.notebook.pack(fill="both", expand=True)
        
        # Chat tab
        chat_frame = ttk.Frame(self.notebook)
        self.notebook.add(chat_frame, text="Chat")
        
        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, wrap="word", state="disabled", height=20,
            font=("Consolas", 10)
        )
        self.chat_display.pack(fill="both", expand=True)
        
        # Configure text tags
        self.chat_display.tag_config("user", foreground="#0066cc")
        self.chat_display.tag_config("assistant", foreground="#008800")
        self.chat_display.tag_config("system", foreground="#666666", font=("Consolas", 9, "italic"))
        self.chat_display.tag_config("error", foreground="#cc0000")
        self.chat_display.tag_config("agent_update", foreground="#9900cc", font=("Consolas", 9, "italic"))
        
        # Agents tab
        agents_frame = ttk.Frame(self.notebook)
        self.notebook.add(agents_frame, text="Agents")
        
        # Agent list
        columns = ("id", "name", "type", "status", "duration")
        self.agent_tree = ttk.Treeview(agents_frame, columns=columns, show="headings", height=10)
        self.agent_tree.heading("id", text="ID")
        self.agent_tree.heading("name", text="Name")
        self.agent_tree.heading("type", text="Type") 
        self.agent_tree.heading("status", text="Status")
        self.agent_tree.heading("duration", text="Duration")
        
        self.agent_tree.column("id", width=80)
        self.agent_tree.column("name", width=200)
        self.agent_tree.column("type", width=120)
        self.agent_tree.column("status", width=100)
        self.agent_tree.column("duration", width=80)
        
        scrollbar_agents = ttk.Scrollbar(agents_frame, orient="vertical", command=self.agent_tree.yview)
        self.agent_tree.configure(yscrollcommand=scrollbar_agents.set)
        
        self.agent_tree.pack(side="left", fill="both", expand=True)
        scrollbar_agents.pack(side="right", fill="y")
        
        # Agent details
        self.agent_details = scrolledtext.ScrolledText(agents_frame, wrap="word", width=40, height=10)
        self.agent_details.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        self.agent_tree.bind("<<TreeviewSelect>>", self._on_agent_select)
        
        # === Input Area ===
        input_frame = ttk.Frame(self)
        input_frame.pack(fill="x", padx=5, pady=5)
        
        self.input_text = tk.Text(input_frame, height=3, wrap="word", font=("Consolas", 10))
        self.input_text.pack(side="left", fill="both", expand=True)
        self.input_text.bind("<Return>", self._on_enter_key)
        
        self.send_button = ttk.Button(input_frame, text="Send", command=self.send_message, width=10)
        self.send_button.pack(side="right", padx=(5, 0))
        
        # Welcome message
        self._print_message("Welcome to Improved EragAPI Chat with Enhanced Agent Orchestration!\n", "system")
        self._print_message("The orchestrator will analyze your requests and create specialized agents with proper tool access.\n", "system")
        
    def _load_tools(self):
        """Load and setup tools."""
        self.tools = ToolLoader.load_tools()
        
        # Pass tools to agent creator if it exists
        if 'mcp_agent_creator' in self.tools:
            self.tools['mcp_agent_creator'].task_orchestrator = self
            self.tools['mcp_agent_creator'].set_tools(self.tools)
        
        # Create tool toggle buttons
        for tool_name, tool in self.tools.items():
            if tool_name != 'mcp_agent_creator':  # Don't show agent creator as toggleable
                display_name = getattr(tool, 'friendly_name', tool_name)
                btn = ttk.Button(
                    self.tools_container, 
                    text=f"{display_name} ✓",
                    command=lambda t=tool, tn=tool_name: self._toggle_tool(t, tn)
                )
                btn.pack(side="left", padx=2)
                self.tool_buttons[tool_name] = btn
        
        self._print_message(f"[Loaded {len(self.tools)} tools: {', '.join([getattr(tool, 'friendly_name', name) for name, tool in self.tools.items()])}]\n", "system")
    
    def _toggle_tool(self, tool, tool_name):
        """Toggle tool enabled/disabled."""
        tool.enabled = not tool.enabled
        display_name = getattr(tool, 'friendly_name', tool_name)
        btn = self.tool_buttons[tool_name]
        
        if tool.enabled:
            btn.config(text=f"{display_name} ✓")
            self._print_message(f"[{display_name} ENABLED]\n", "system")
        else:
            btn.config(text=f"{display_name} ✗")
            self._print_message(f"[{display_name} DISABLED]\n", "system")
    
    def _refresh_models(self):
        """Refresh available models."""
        try:
            resp = requests.get(f"{self.server_url}/api/models", timeout=5)
            resp.raise_for_status()
            self.models = resp.json()["models"]
            
            model_list = []
            for provider, models in self.models.items():
                for model in models:
                    if "whisper" not in model.lower():
                        model_list.append(f"{provider}-{model}")
            
            if model_list:
                self.model_combo["values"] = model_list
                if not self.model_var.get() or self.model_var.get() not in model_list:
                    self.model_var.set(model_list[0])
            
            self._print_message("[Models refreshed]\n", "system")
        except Exception as e:
            print(f"Could not refresh models: {e}")
    
    def _print_message(self, text: str, tag: str = ""):
        """Print message to chat display."""
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", text, tag)
        self.chat_display.configure(state="disabled")
        self.chat_display.see("end")
    
    def _on_enter_key(self, event):
        """Handle Enter key."""
        if event.state & 0x0001:  # Shift+Enter
            return None
        if not self.is_sending:
            self.send_message()
        return "break"
    
    def send_message(self):
        """Send message to orchestrator with improved logic."""
        if self.is_sending or self.waiting_for_agent:
            return
            
        user_message = self.input_text.get("1.0", "end").strip()
        if not user_message:
            return
        
        self.input_text.delete("1.0", "end")
        self.is_sending = True
        self.send_button.config(state="disabled", text="Thinking...")
        self.status_label.config(text="Processing...", foreground="orange")
        
        self._print_message(f"You: {user_message}\n", "user")
        self.conversation_history.append({"role": "user", "content": user_message})
        
        # Add orchestrator system prompt on first message
        if len(self.conversation_history) == 1:
            system_prompt = self._build_enhanced_orchestrator_prompt()
            self.conversation_history.insert(0, {"role": "system", "content": system_prompt})
        
        threading.Thread(target=self._call_orchestrator_api, daemon=True).start()
    
    def _build_enhanced_orchestrator_prompt(self) -> str:
        """Build enhanced orchestrator system prompt with tool awareness."""
        enabled_tools = []
        for tool_name, tool in self.tools.items():
            if tool.enabled and tool_name != 'mcp_agent_creator':
                display_name = getattr(tool, 'friendly_name', tool_name)
                description = getattr(tool, 'description', 'No description')
                enabled_tools.append(f"- {display_name}: {description}")
        
        tools_text = "\n".join(enabled_tools) if enabled_tools else "- No tools available"
        
        return f"""You are a TASK ORCHESTRATOR for specialized agent creation and management.

CORE RESPONSIBILITIES:
1. Analyze user requests and create appropriate specialized agents
2. Each agent gets independent conversation context and tool access
3. Wait for agent completion before responding to user
4. Provide comprehensive analysis of agent results
5. Create additional agents if needed based on results

AVAILABLE TOOLS FOR AGENTS:
{tools_text}

AGENT CREATION RULES:
- Use the Agent Creator tool with proper XML format
- Create task-specific agents (web_search, data_analysis, content_creation, etc.)
- Provide detailed parameters and clear instructions
- One agent per task, wait for completion before creating more
- Pass relevant tool access to each agent

EXAMPLE AGENT CREATION:
For passive reconnaissance on a domain, create a web_search agent:
```xml
<agent>
  <type>web_search</type>
  <name>Domain Reconnaissance Agent</name>
  <description>Gather publicly available information about the target domain</description>
  <parameters>
    <query>site:target.com OR "target.com" filetype:pdf OR filetype:doc reconnaissance</query>
  </parameters>
</agent>
```

TASK ANALYSIS GUIDELINES:
- Break complex tasks into multiple specialized agents
- For reconnaissance: use web search, then analysis, then reporting
- For research: use web search with multiple specific queries
- For technical analysis: use appropriate analysis tools
- Always provide actionable intelligence from results

RESPONSE FORMAT:
1. Acknowledge the task
2. Create appropriate agent(s)
3. Wait for results
4. Analyze and summarize findings
5. Suggest next steps if needed

Never perform tasks yourself - always delegate to specialized agents."""

    def _call_orchestrator_api(self):
        """Call API for orchestrator with improved error handling."""
        try:
            payload = {
                "model": self.model_var.get(),
                "messages": self.conversation_history,
                "temperature": self.temp_var.get(),
                "max_tokens": self.max_tokens_var.get(),
                "stream": False
            }
            
            response = requests.post(f"{self.server_url}/api/chat", json=payload, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            ai_response = self._extract_content(data)
            
            self._print_message(f"Orchestrator: {ai_response}\n", "assistant")
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            
            # Process tool requests (should only be Agent Creator)
            agent_created = self._process_agent_creation(ai_response)
            
            if not agent_created:
                # No agent creation detected - orchestrator provided direct response
                self.is_sending = False
                self.send_button.config(state="normal", text="Send")
                self.status_label.config(text="Ready", foreground="green")
            
        except Exception as e:
            self._print_message(f"[Orchestrator Error: {str(e)}]\n", "error")
            self.is_sending = False
            self.send_button.config(state="normal", text="Send")
            self.status_label.config(text="Error", foreground="red")
    
    def _extract_content(self, response_data: Dict) -> str:
        """Extract content from API response."""
        if "choices" in response_data and len(response_data["choices"]) > 0:
            choice = response_data["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"]
        
        if "message" in response_data:
            if isinstance(response_data["message"], str):
                return response_data["message"]
            elif "content" in response_data["message"]:
                return response_data["message"]["content"]
        
        for key in ["content", "response", "text"]:
            if key in response_data:
                return response_data[key]
        
        return str(response_data)
    
    def _process_agent_creation(self, ai_response: str) -> bool:
        """Process agent creation requests from orchestrator."""
        agent_creator = self.tools.get('mcp_agent_creator')
        if not agent_creator or not agent_creator.enabled:
            return False
        
        command = agent_creator.detect_request(ai_response)
        if not command:
            return False
        
        try:
            self._print_message(f"[Creating specialized agent...]\n", "agent_update")
            
            tool_result = agent_creator.execute(command)
            self._print_message(f"[Agent Creator: {tool_result}]\n", "agent_update")
            
            # Extract agent ID and wait for completion
            agent_id_match = re.search(r'Agent ID: (\d+)', tool_result)
            if agent_id_match:
                agent_id = int(agent_id_match.group(1))
                self.current_agent_id = agent_id
                self.waiting_for_agent = True
                self.status_label.config(text="Agent Working...", foreground="blue")
                threading.Thread(target=self._wait_for_agent_completion, args=(agent_id,), daemon=True).start()
                return True
            
        except Exception as e:
            self._print_message(f"[Error creating agent: {str(e)}]\n", "error")
            import traceback
            traceback.print_exc()
        
        return False
    
    def _wait_for_agent_completion(self, agent_id: int):
        """Wait for agent completion with enhanced monitoring."""
        agent = self.orchestrator.get_agent(agent_id)
        if not agent:
            self._print_message(f"[Error: Agent {agent_id} not found]\n", "error")
            self._reset_sending_state()
            return
        
        self._print_message(f"[Agent '{agent.name}' is working on the task...]\n", "agent_update")
        
        # Wait for completion with timeout
        max_wait_time = 180  # 3 minutes max
        wait_time = 0
        
        while agent.status in [AgentStatus.PENDING, AgentStatus.RUNNING] and wait_time < max_wait_time:
            threading.Event().wait(1)  # Better than time.sleep
            wait_time += 1
            
            # Update status every 30 seconds
            if wait_time % 30 == 0:
                self._print_message(f"[Agent '{agent.name}' still working... ({wait_time}s elapsed)]\n", "agent_update")
        
        # Process results
        self._process_agent_results(agent)
        
        # Save agent results
        self._save_agent_results(agent)
        
        # Reset state and continue orchestrator conversation
        self.waiting_for_agent = False
        self.current_agent_id = None
        
        # Continue orchestrator conversation with results
        self._continue_orchestrator_with_results(agent)
    
    def _process_agent_results(self, agent: BaseAgent):
        """Process and display agent results."""
        if agent.status == AgentStatus.COMPLETED:
            self._print_message(f"[✓ Agent '{agent.name}' completed successfully]\n", "agent_update")
            
            if agent.result:
                final_result = agent.result.get('final_result', 'No result provided')
                # Truncate very long results for display
                if len(final_result) > 1000:
                    display_result = final_result[:1000] + "... (truncated, full results saved)"
                else:
                    display_result = final_result
                
                self._print_message(f"Agent Results Summary:\n{display_result}\n\n", "system")
            
        elif agent.status == AgentStatus.FAILED:
            self._print_message(f"[✗ Agent '{agent.name}' failed: {agent.error or 'Unknown error'}]\n", "error")
            
        else:
            # Timeout
            self._print_message(f"[⚠ Agent '{agent.name}' timed out after 3 minutes]\n", "error")
    
    def _save_agent_results(self, agent: BaseAgent):
        """Save agent results to file."""
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = re.sub(r'[^\w\s-]', '', agent.name).strip()
            safe_name = re.sub(r'[-\s]+', '-', safe_name)
            filename = f"agent_{timestamp}_{agent.id}_{safe_name}.json"
            filepath = os.path.join(self.results_dir, filename)
            
            # Prepare comprehensive agent data
            agent_data = {
                "agent_info": {
                    "id": agent.id,
                    "name": agent.name,
                    "description": agent.description,
                    "status": agent.status,
                    "start_time": agent.start_time,
                    "end_time": agent.end_time,
                    "execution_time": agent.get_execution_time(),
                    "error": agent.error
                },
                "task_details": {
                    "task_type": getattr(agent, 'task_type', 'unknown'),
                    "task_params": getattr(agent, 'task_params', {})
                },
                "conversation_history": getattr(agent, 'conversation_history', []),
                "results": agent.result,
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(agent_data, f, indent=2, ensure_ascii=False)
            
            self._print_message(f"[Agent results saved to: {filename}]\n", "system")
            
        except Exception as e:
            self._print_message(f"[Error saving agent results: {e}]\n", "error")
    
    def _continue_orchestrator_with_results(self, agent: BaseAgent):
        """Continue orchestrator conversation with agent results."""
        if agent.status == AgentStatus.COMPLETED and agent.result:
            final_result = agent.result.get('final_result', 'No result')
            result_message = (
                f"Agent '{agent.name}' has completed successfully.\n\n"
                f"Task: {getattr(agent, 'task_type', 'unknown')}\n"
                f"Results:\n{final_result}\n\n"
                f"Please analyze these results and provide a comprehensive summary to the user. "
                f"If additional information is needed, create more specialized agents."
            )
        elif agent.status == AgentStatus.FAILED:
            result_message = (
                f"Agent '{agent.name}' failed with error: {agent.error or 'Unknown error'}\n\n"
                f"Please either:\n"
                f"1. Create a different type of agent to accomplish the task, or\n"
                f"2. Inform the user about the limitation and suggest alternatives."
            )
        else:
            result_message = (
                f"Agent '{agent.name}' timed out or encountered issues.\n\n"
                f"Please inform the user and suggest alternative approaches."
            )
        
        self.conversation_history.append({"role": "system", "content": result_message})
        
        # Continue orchestrator processing
        self.send_button.config(text="Analyzing...")
        threading.Thread(target=self._call_orchestrator_api, daemon=True).start()
    
    def _reset_sending_state(self):
        """Reset sending state."""
        self.is_sending = False
        self.waiting_for_agent = False
        self.current_agent_id = None
        self.send_button.config(state="normal", text="Send")
        self.status_label.config(text="Ready", foreground="green")
    
    def _on_agent_update(self, agent: BaseAgent):
        """Handle agent status updates."""
        self._update_agent_tree()
        
        # Update details if this agent is selected
        selected = self.agent_tree.selection()
        if selected:
            item = selected[0]
            agent_id_str = self.agent_tree.item(item, "values")[0]
            if str(agent.id) == agent_id_str:
                self._show_agent_details(agent)
        
        # Update status in chat if this is the current agent
        if agent.id == self.current_agent_id:
            status_msg = f"[Agent '{agent.name}': {agent.status}]\n"
            self._print_message(status_msg, "agent_update")
    
    def _update_agent_tree(self):
        """Update the agent tree view."""
        for item in self.agent_tree.get_children():
            self.agent_tree.delete(item)
        
        for agent in self.orchestrator.list_agents():
            duration = ""
            if agent.get_execution_time():
                duration = f"{agent.get_execution_time():.1f}s"
            elif agent.status == AgentStatus.RUNNING and agent.start_time:
                import time
                current_duration = time.time() - agent.start_time
                duration = f"{current_duration:.1f}s"
            
            self.agent_tree.insert("", "end", values=(
                agent.id,
                agent.name,
                getattr(agent, 'task_type', 'Unknown'),
                agent.status,
                duration
            ))
    
    def _on_agent_select(self, event):
        """Handle agent selection."""
        selected = self.agent_tree.selection()
        if selected:
            item = selected[0]
            agent_id = int(self.agent_tree.item(item, "values")[0])
            agent = self.orchestrator.get_agent(agent_id)
            if agent:
                self._show_agent_details(agent)
    
    def _show_agent_details(self, agent: BaseAgent):
        """Show enhanced agent details."""
        self.agent_details.delete("1.0", "end")
        
        details = f"Agent Details\n{'='*30}\n\n"
        details += f"ID: {agent.id}\n"
        details += f"Name: {agent.name}\n"
        details += f"Description: {agent.description}\n"
        details += f"Status: {agent.status}\n"
        
        if hasattr(agent, 'task_type'):
            details += f"Task Type: {agent.task_type}\n"
        
        if hasattr(agent, 'task_params'):
            details += f"Parameters: {json.dumps(agent.task_params, indent=2)}\n"
        
        if agent.start_time:
            start_time = datetime.datetime.fromtimestamp(agent.start_time)
            details += f"Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if agent.end_time:
            end_time = datetime.datetime.fromtimestamp(agent.end_time)
            details += f"Ended: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            if agent.get_execution_time():
                details += f"Duration: {agent.get_execution_time():.2f}s\n"
        
        if hasattr(agent, 'conversation_history') and agent.conversation_history:
            details += f"\nConversation Length: {len(agent.conversation_history)} messages\n"
            
            # Show last few messages
            details += "\nRecent Messages:\n"
            for msg in agent.conversation_history[-3:]:
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:100]
                if len(msg.get('content', '')) > 100:
                    content += "..."
                details += f"  {role}: {content}\n"
        
        if agent.result:
            details += f"\nResult Summary:\n"
            result_str = json.dumps(agent.result, indent=2)
            if len(result_str) > 500:
                details += result_str[:500] + "...\n(truncated - see full results in saved file)"
            else:
                details += result_str
        
        if agent.error:
            details += f"\nError:\n{agent.error}\n"
        
        self.agent_details.insert("1.0", details)
    
    def stop_all_agents(self):
        """Stop all running agents."""
        running_agents = self.orchestrator.get_running_agents()
        if running_agents:
            for agent in running_agents:
                agent.set_status(AgentStatus.FAILED)
                agent.error = "Manually stopped by user"
            self._print_message(f"[Stopped {len(running_agents)} running agents]\n", "system")
        else:
            self._print_message("[No running agents to stop]\n", "system")
        
        self._reset_sending_state()
    
    def clear_chat(self):
        """Clear chat and reset all state."""
        self.chat_display.configure(state="normal")
        self.chat_display.delete("1.0", "end")
        self.chat_display.configure(state="disabled")
        self.conversation_history.clear()
        self.stop_all_agents()
        self._print_message("Chat cleared and all agents stopped!\n", "system")
    
    def save_chat(self):
        """Save chat with enhanced information."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"chat_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
        )
        if filename:
            try:
                if filename.endswith('.json'):
                    # Save as structured JSON
                    chat_data = {
                        "conversation_history": self.conversation_history,
                        "agents": [
                            {
                                "id": agent.id,
                                "name": agent.name,
                                "status": agent.status,
                                "result": agent.result,
                                "error": agent.error
                            }
                            for agent in self.orchestrator.list_agents()
                        ],
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                    
                    with open(filename, "w", encoding="utf-8") as f:
                        json.dump(chat_data, f, indent=2, ensure_ascii=False)
                else:
                    # Save as text
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(f"EragAPI Chat Session - {datetime.datetime.now().isoformat()}\n")
                        f.write("="*60 + "\n\n")
                        f.write(self.chat_display.get("1.0", "end"))
                        
                        # Add agent summary
                        agents = self.orchestrator.list_agents()
                        if agents:
                            f.write("\n\nAgent Summary:\n")
                            f.write("-" * 20 + "\n")
                            for agent in agents:
                                f.write(f"Agent {agent.id}: {agent.name} [{agent.status}]\n")
                                if agent.result:
                                    final_result = agent.result.get('final_result', '')
                                    if final_result:
                                        f.write(f"  Result: {final_result[:200]}{'...' if len(final_result) > 200 else ''}\n")
                                f.write("\n")
                
                messagebox.showinfo("Saved", f"Chat saved to:\n{filename}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save: {e}")
    
    # Method for agent creator tool compatibility
    def add_agent(self, agent: BaseAgent):
        """Add agent to orchestrator (for tool compatibility)."""
        self._update_agent_tree()


class MainApplication(tk.Tk):
    """Improved main application."""
    
    def __init__(self):
        super().__init__()
        self.title("Enhanced EragAPI Chat with Fixed Agent Orchestration")
        self.geometry("1400x900")
        
        self.server_process = None
        
        # Create main interface
        self.chat_interface = ImprovedChatInterface(self)
        self.chat_interface.pack(fill="both", expand=True)
        
        # Create menu
        self._create_menu()
        
        # Bind close event
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Try to refresh models on startup
        self.after(1000, self.chat_interface._refresh_models)
    
    def _create_menu(self):
        """Create enhanced application menu."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Chat", command=self.chat_interface.save_chat)
        file_menu.add_command(label="Clear Chat", command=self.chat_interface.clear_chat)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Server menu  
        server_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Server", menu=server_menu)
        server_menu.add_command(label="Start Server", command=self.start_server)
        server_menu.add_command(label="Stop Server", command=self.stop_server)
        server_menu.add_separator()
        server_menu.add_command(label="Refresh Models", command=self.chat_interface._refresh_models)
        
        # Agents menu
        agents_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Agents", menu=agents_menu)
        agents_menu.add_command(label="Stop All Agents", command=self.chat_interface.stop_all_agents)
        agents_menu.add_command(label="View Results Folder", command=self.open_results_folder)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
        help_menu.add_command(label="Troubleshooting", command=self.show_troubleshooting)
    
    def start_server(self):
        """Start EragAPI server with enhanced monitoring."""
        if self.server_process and self.server_process.poll() is None:
            self.chat_interface._print_message("[Server is already running]\n", "system")
            return
        
        # Check if port is already in use
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', 11436))
            sock.close()
            if result == 0:
                self.chat_interface._print_message("[Port 11436 is already in use. Server may already be running elsewhere.]\n", "system")
                self.chat_interface._print_message("[Try using the existing server or stop it first.]\n", "system")
                self.chat_interface._refresh_models()
                return
        except:
            pass
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        server_script = os.path.join(script_dir, "eragAPI.py")
        
        if not os.path.exists(server_script):
            self.chat_interface._print_message(f"[eragAPI.py not found at {server_script}]\n", "error")
            return
        
        try:
            self.server_process = subprocess.Popen(
                [sys.executable, server_script, "serve"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=script_dir
            )
            
            self.chat_interface._print_message("[Starting server...]\n", "system")
            
            # Monitor server output
            def monitor_server():
                try:
                    for line in self.server_process.stdout:
                        line = line.strip()
                        if line:
                            self.chat_interface._print_message(f"[SERVER] {line}\n", "system")
                            
                            if "Application startup complete" in line:
                                def delayed_refresh():
                                    import time
                                    time.sleep(2)
                                    try:
                                        self.chat_interface._refresh_models()
                                    except:
                                        pass
                                threading.Thread(target=delayed_refresh, daemon=True).start()
                    
                    self.chat_interface._print_message("[Server process ended]\n", "system")
                    self.server_process = None
                except Exception as e:
                    self.chat_interface._print_message(f"[Error monitoring server: {e}]\n", "error")
            
            threading.Thread(target=monitor_server, daemon=True).start()
            
        except Exception as e:
            self.chat_interface._print_message(f"[Error starting server: {e}]\n", "error")
    
    def stop_server(self):
        """Stop server and all agents."""
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
            self.chat_interface._print_message("[Server stopped]\n", "system")
        else:
            self.chat_interface._print_message("[Server not running]\n", "system")
        
        # Also stop all agents
        self.chat_interface.stop_all_agents()
    
    def open_results_folder(self):
        """Open the results folder in file explorer."""
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
        try:
            if os.name == 'nt':  # Windows
                os.startfile(results_dir)
            elif os.name == 'posix':  # Linux/Mac
                subprocess.run(['xdg-open', results_dir])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open results folder: {e}")
    
    def show_about(self):
        """Show enhanced about dialog."""
        about_text = """Enhanced EragAPI Chat Application

Features:
✓ Fixed orchestrator loop issues
✓ Enhanced agent creation with tool awareness  
✓ Independent agent conversation contexts
✓ Comprehensive results saving and analysis
✓ Real-time agent monitoring and status updates
✓ Multi-tool integration (Web Search, Curl, etc.)
✓ Improved error handling and timeout management

Version: 2.1 (Enhanced & Fixed)

The orchestrator now properly:
- Analyzes requests and creates appropriate agents
- Waits for agent completion before responding
- Provides comprehensive result analysis
- Saves all agent data to results/agents/
- Avoids infinite feedback loops"""
        messagebox.showinfo("About", about_text)
    
    def show_troubleshooting(self):
        """Show troubleshooting information."""
        troubleshooting_text = """Troubleshooting Guide

Common Issues:

1. Agent Creation Loop:
   - Fixed in this version
   - Orchestrator now waits for agent completion

2. Agents Not Using Tools:
   - Ensure tools are enabled (green checkmarks)
   - Check results/agents/ for detailed logs
   - Agents now receive proper tool instructions

3. Server Connection Issues:
   - Use "Start Server" from Server menu
   - Check that port 11436 is not blocked
   - Verify API keys are set in environment

4. Missing Results:
   - Results are saved to results/agents/
   - Use "View Results Folder" from Agents menu
   - Each agent execution is logged separately

5. Performance Issues:
   - Stop unused agents with "Stop All Agents"
   - Clear chat periodically
   - Reduce max tokens if responses are slow

For more help, check the console output or log files."""
        messagebox.showinfo("Troubleshooting", troubleshooting_text)
    
    def on_closing(self):
        """Handle application closing."""
        # Stop all agents and server
        self.chat_interface.stop_all_agents()
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
        
        # Save current state if there's conversation history
        if self.chat_interface.conversation_history:
            if messagebox.askyesno("Save Session", "Do you want to save the current chat session?"):
                self.chat_interface.save_chat()
        
        self.quit()


if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()