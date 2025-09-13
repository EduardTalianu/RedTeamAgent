"""
Main entry point for the Tkinter EragAPI application with Task Orchestrator.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import subprocess
import threading
import datetime

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Add mcp directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mcp'))

from agents import TaskRelationManager, AgentRegistry
from gui import ChatTab, TaskOrchestratorTab
from tool_loader import ToolLoader
from mcp_agent_creator import McpAgentCreator

class MainApplication(tk.Tk):
    """Main application class."""
    
    def __init__(self):
        super().__init__()
        self.title("EragAPI Chat with Task Orchestrator")
        self.geometry("1200x800")
        
        # Initialize components
        self.trm = TaskRelationManager()
        self.agent_registry = AgentRegistry()
        self.agent_registry.set_default_trm(self.trm)
        self.server_process = None
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        
        # Create tabs
        self.chat_tab = ChatTab(self.notebook)
        self.task_tab = TaskOrchestratorTab(self.notebook, self.trm)
        
        # Connect chat tab with task orchestrator
        self.chat_tab.set_task_orchestrator(self.task_tab)
        
        self.notebook.add(self.chat_tab, text="Chat")
        self.notebook.add(self.task_tab, text="Task Orchestrator")
        
        # Add menu bar
        self._create_menu_bar()
        
        # Load tools
        self._load_tools()
        
        # Welcome message
        self.chat_tab._print_message(
            "Welcome to EragAPI Chat with Task Orchestrator!\n"
            "Use the Chat tab to communicate with the LLM.\n"
            "The Task Orchestrator tab shows agent hierarchies and status.\n"
            "Click 'Start Server' in the Chat tab to begin.\n",
            "system"
        )
    
    def _create_menu_bar(self):
        """Create the application menu bar."""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Save Chat", command=self.save_chat)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.quit)
        
        # Server menu
        server_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Server", menu=server_menu)
        server_menu.add_command(label="Start Server", command=self.start_server)
        server_menu.add_command(label="Stop Server", command=self.stop_server)
        
        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Refresh Tools", command=self.refresh_tools)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)
    
    def _load_tools(self):
        """Load available tools."""
        # Load regular tools
        tools = ToolLoader.load_tools()
        
        # Add the agent creator tool, passing the tools dictionary
        agent_creator = McpAgentCreator(task_orchestrator=self.task_tab, tools=tools)
        agent_creator.enabled = True
        tools['mcp_agent_creator'] = agent_creator
        
        # Set tools in chat tab
        self.chat_tab.set_tools(tools)
        
        # Add tool buttons to the chat tab
        for tool_name, tool in tools.items():
            display_name = getattr(tool, 'friendly_name', tool_name)
            btn = ttk.Button(
                self.chat_tab.tools_container,
                text=f"Disable {display_name}",
                command=lambda t=tool: self.chat_tab.toggle_tool(t)
            )
            btn.pack(side="left", padx=2)
            self.chat_tab.tool_buttons[tool_name] = btn
    
    def refresh_tools(self):
        """Refresh the list of available tools."""
        # Clear existing buttons
        for widget in self.chat_tab.tools_container.winfo_children():
            widget.destroy()
        
        # Reload tools
        self._load_tools()
    
    def start_server(self):
        """Start the EragAPI server."""
        if self.server_process and self.server_process.poll() is None:
            self.chat_tab._print_message("[Server is already running]\n", "server")
            return
        
        # Get the path to eragAPI.py
        script_dir = os.path.dirname(os.path.abspath(__file__))
        server_script = os.path.join(script_dir, "eragAPI.py")
        
        if not os.path.exists(server_script):
            self.chat_tab._print_message(f"[Error: eragAPI.py not found at {server_script}]\n", "error")
            return
        
        # Command to start the server
        command = [sys.executable, server_script, "serve"]
        
        self.chat_tab._print_message(f"[Starting server with command: {' '.join(command)}]\n", "server")
        
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
                    self.chat_tab._print_message(f"[SERVER] {line.strip()}\n", "server")
                
                # When the process ends
                self.chat_tab._print_message("[Server process ended]\n", "server")
                self.server_process = None
            
            threading.Thread(target=read_server_output, daemon=True).start()
            
            # Try to refresh models after a short delay
            self.after(2000, self.chat_tab._refresh_models)
            
        except Exception as e:
            self.chat_tab._print_message(f"[Error starting server: {str(e)}]\n", "error")
    
    def stop_server(self):
        """Stop the EragAPI server."""
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
            self.chat_tab._print_message("[Server stopped]\n", "server")
        else:
            self.chat_tab._print_message("[Server is not running]\n", "server")
    
    def save_chat(self):
        """Save the chat to a file."""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"chat_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
        )
        if filename:
            if self.chat_tab.save_chat(filename):
                messagebox.showinfo("Saved", f"Chat saved to:\n{filename}")
            else:
                messagebox.showerror("Error", "Failed to save chat.")
    
    def show_about(self):
        """Show the about dialog."""
        about_text = """EragAPI Chat with Task Orchestrator
        
A Tkinter-based client for EragAPI with integrated task orchestration.

Features:
- Chat interface with LLM
- Task orchestrator with agent hierarchies
- Real-time agent status monitoring
- Visual task relationship graphs

Version: 1.0"""
        messagebox.showinfo("About", about_text)
    
    def quit(self):
        """Quit the application."""
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
        super().quit()

if __name__ == "__main__":
    app = MainApplication()
    app.mainloop()