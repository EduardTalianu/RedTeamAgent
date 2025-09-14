# main.py - Fixed version with proper Moonshot integration
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import os
import sys
import subprocess
import threading
import datetime
import requests  # Added for direct API calls
import json
import re
import importlib.util
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import our improved agent system
from agents import agent_registry, BaseAgent, AgentStatus
from moonshot_client import MoonshotClient


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
    
    def __init__(self, parent):
        super().__init__(parent)
        self.models = []  # Will be populated dynamically
        self.conversation_history = []
        self.tools = {}
        self.tool_buttons = {}
        self.is_sending = False
        self.waiting_for_agent = False  # Track if we're waiting for agent completion
        self.current_agent_id = None
        
        # Create results directory
        self.results_dir = os.path.join("results", "agents")
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Create Moonshot client
        self.client = MoonshotClient()
        
        self.orchestrator = agent_registry.get_orchestrator()
        self.orchestrator.add_callback(self._on_agent_update)
        
        self._build_interface()
        self._load_tools()
        self._refresh_models()  # Fetch models from API
    
    def _refresh_models(self):
        try:
            models = self.client.list_models()          # ← real call
            if models:                                  # ← we got 12
                self.models = models
                self.model_combo["values"] = self.models
                if not self.model_var.get() or self.model_var.get() not in self.models:
                    self.model_var.set(self.models[0])
                self._print_message(f"[Models refreshed: {len(self.models)} models loaded]\n", "system")
                return                                  # ← SUCCESS: leave early
        except Exception as e:
            print(f"Could not refresh models: {e}")
            # self._print_message(f"[Error refreshing models: {str(e)}]\n", "error")
            # ↓↓↓  REMOVE THESE LINES – they overwrite the real list  ↓↓↓
            # self.models = [
            #     "moonshot-v1-8k",
            #     "moonshot-v1-32k",
            #     "moonshot-v1-128k",
            #     "moonshot-v1-auto"
            # ]
            # self.model_combo["values"] = self.models
            # if not self.model_var.get() or self.model_var.get() not in self.models:
            #     self.model_var.set("moonshot-v1-32k")
    
    def _build_interface(self):
        """Build the improved interface."""
        
        # === Top Controls ===
        controls_frame = ttk.Frame(self, padding="5")
        controls_frame.pack(fill="x")
        
        # Model selection
        ttk.Label(controls_frame, text="Model:").pack(side="left", padx=(0, 5))
        self.model_var = tk.StringVar(value="moonshot-v1-32k-chat")  # Default value
        self.model_combo = ttk.Combobox(controls_frame, textvariable=self.model_var, width=30)
        self.model_combo.pack(side="left", padx=(0, 5))
        
        # Add refresh button
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
        self._print_message("Welcome to Enhanced Moonshot Chat with Agent Orchestration!\n", "system")
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
        """Build system prompt for generic agent orchestration."""
        enabled_tools = []
        for tool_name, tool in self.tools.items():
            if tool.enabled and tool_name != 'mcp_agent_creator':
                display_name = getattr(tool, 'friendly_name', tool_name)
                description = getattr(tool, 'description', 'No description')
                enabled_tools.append(f"- {display_name}: {description}")
        
        tools_text = "\n".join(enabled_tools) if enabled_tools else "- No tools available"
        
        return f"""You are a TASK ORCHESTRATOR for generic agent creation and management.

    CORE RESPONSIBILITIES:
    1. Analyze user requests and create generic agents with specific instructions
    2. All agents are identical - only the instructions you provide make them different
    3. Wait for agent completion before responding to user
    4. Provide comprehensive analysis of agent results
    5. Create additional agents if needed based on results

    AVAILABLE TOOLS FOR AGENTS:
    {tools_text}

    GENERIC AGENT PRINCIPLES:
    - There is only ONE type of agent - a generic, multipurpose agent
    - Agents are specialized ONLY through the detailed instructions you provide
    - Each agent gets complete tool access and works independently
    - Instructions should be step-by-step and specific about tool usage

    AGENT CREATION FORMAT:
    ```xml
    <agent>
    <n>Descriptive Agent Name</n>
    <description>Brief description of agent's purpose</description>
    <instructions>
        Detailed step-by-step instructions for the agent.
        
        Be very specific about:
        - What information to gather
        - Which tools to use and how to use them
        - What searches to perform
        - What analysis to conduct
        - How to format results
    </instructions>
    </agent>
    ```

    EXAMPLE FOR IP RANGE ANALYSIS:
    ```xml
    <agent>
    <n>Network Analysis Agent</n>
    <description>Find IP ranges and network details for target domain</description>
    <instructions>
        Your mission is to find comprehensive network information for bcr.ro.
        
        Execute these steps:
        1. Use Web Search tool to search: "bcr.ro IP range CIDR netblock ASN"
        2. Search for: "bcr.ro hosting provider network information"
        3. Search for: "bcr.ro server locations IP addresses"
        4. Use Curl tool to get headers from https://bcr.ro and analyze server details
        5. Compile all findings into a detailed network intelligence report
        
        Focus on: IP ranges, CIDR blocks, ASN numbers, hosting providers, geographic locations.
    </instructions>
    </agent>
    ```

    EXAMPLE FOR PASSIVE RECONNAISSANCE:
    ```xml
    <agent>
    <n>Reconnaissance Agent</n>
    <description>Perform passive information gathering on target domain</description>
    <instructions>
        Conduct comprehensive passive reconnaissance on bcr.ro.
        
        Tasks to complete:
        1. Web Search: "site:bcr.ro" to find all indexed pages
        2. Web Search: "site:bcr.ro filetype:pdf OR filetype:doc" for documents
        3. Web Search: "bcr.ro employees contacts directory"
        4. Web Search: "bcr.ro technology stack framework server"
        5. Use Curl to analyze https://bcr.ro headers and response
        6. Create comprehensive reconnaissance report with all findings
        
        Gather only publicly available information.
    </instructions>
    </agent>
    ```

    INSTRUCTION GUIDELINES:
    - Be extremely detailed and specific in your instructions
    - Tell agents exactly which tools to use and how
    - Specify the exact search terms to use
    - Define the expected output format
    - Break complex tasks into clear sequential steps

    ERROR HANDLING:
    - If agent creation fails, analyze the error and correct the XML format
    - Ensure instructions are clear and actionable
    - Always wait for agent completion before responding

    RESPONSE WORKFLOW:
    1. Acknowledge user request
    2. Create agent with detailed, specific instructions
    3. Wait for agent completion
    4. Analyze and summarize results
    5. Create additional agents if more information needed

    Never perform tasks yourself - always create agents with comprehensive instructions."""

    def _call_orchestrator_api(self):
        """Call Moonshot API for orchestrator with improved error handling."""
        try:
            # Update model from UI selection
            self.client.model = self.model_var.get()
            
            payload = {
                "messages": self.conversation_history,
                "temperature": self.temp_var.get(),
                "max_tokens": self.max_tokens_var.get(),
                "stream": False
            }
            
            response = self.client.chat(**payload)
            
            self._print_message(f"Orchestrator: {response}\n", "assistant")
            self.conversation_history.append({"role": "assistant", "content": response})
            
            # Process tool requests (should only be Agent Creator)
            agent_created = self._process_agent_creation(response)
            
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
        """Process agent creation requests with enhanced error handling."""
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
            
            # CHECK FOR ERRORS - This is the key addition
            if "Error:" in tool_result or "Missing required parameter" in tool_result:
                # Agent creation failed - add error to conversation for orchestrator to see
                error_message = (
                    f"AGENT CREATION FAILED: {tool_result}\n\n"
                    f"ERROR CORRECTION REQUIRED:\n"
                    f"The agent creation failed due to incorrect parameters. "
                    f"Please create a corrected agent using proper parameter format:\n\n"
                    f"For IP range analysis of bcr.ro, use data_analysis agent:\n"
                    f'<agent>\n'
                    f'  <type>data_analysis</type>\n'
                    f'  <n>IP Analysis Agent</n>\n'
                    f'  <description>Analyze IP range for bcr.ro</description>\n'
                    f'  <parameters>\n'
                    f'    <data>bcr.ro</data>\n'
                    f'    <analysis_type>ip_analysis</analysis_type>\n'
                    f'  </parameters>\n'
                    f'</agent>\n\n'
                    f"CRITICAL: data_analysis agents require <data>target</data> parameter, not target_domain!"
                )
                
                # Add to conversation so orchestrator can see the error and retry
                self.conversation_history.append({"role": "user", "content": error_message})
                
                # Continue orchestrator processing to handle the error
                self.send_button.config(text="Correcting...")
                threading.Thread(target=self._call_orchestrator_api, daemon=True).start()
                return True
            
            # Extract agent ID and wait for completion (existing code)
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
            # Ensure the results directory exists
            os.makedirs(self.results_dir, exist_ok=True)
            
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
        self.title("Enhanced Moonshot Chat with Agent Orchestration")
        self.geometry("1400x900")
        
        # Create main interface
        self.chat_interface = ImprovedChatInterface(self)
        self.chat_interface.pack(fill="both", expand=True)
        
        # Create menu
        self._create_menu()
        
        # Bind close event
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    
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
        
        # Model menu
        model_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Model", menu=model_menu)
        model_menu.add_command(label="Refresh Models", command=self.chat_interface._refresh_models)
        
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
   - Fixed: Now uses direct Moonshot API connection
   - Check that MOONSHOT_API_KEY is set in .env file
   - Verify API key is valid

4. Missing Results:
   - Results are saved to results/agents/
   - Use "View Results Folder" from Agents menu
   - Each agent execution is logged separately

5. Performance Issues:
   - Stop unused agents with "Stop All Agents"
   - Clear chat periodically
   - Reduce max tokens if responses are slow

6. Model Loading Issues:
   - Use the refresh button (↻) to reload models
   - Check your internet connection
   - Verify MOONSHOT_API_KEY is correct

For more help, check the console output or log files."""
        messagebox.showinfo("Troubleshooting", troubleshooting_text)
    
    def on_closing(self):
        """Handle application closing."""
        # Stop all agents
        self.chat_interface.stop_all_agents()
        
        # Save current state if there's conversation history
        if self.chat_interface.conversation_history:
            if messagebox.askyesno("Save Session", "Do you want to save the current chat session?"):
                self.chat_interface.save_chat()
        
        self.quit()


if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()