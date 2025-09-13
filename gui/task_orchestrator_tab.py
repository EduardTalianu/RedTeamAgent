"""
Task orchestrator tab for visualizing agent hierarchy and status.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import sys
import os
from datetime import datetime
from PIL import Image, ImageTk
from typing import Dict, List, Optional, Any

class TaskOrchestratorTab(ttk.Frame):
    """Task orchestrator tab for visualizing agent hierarchy."""
    
    def __init__(self, parent, trm):
        super().__init__(parent)
        self.trm = trm
        self.agents: Dict[int, Any] = {}
        
        self._build_widgets()
        
        # Register for task updates
        if hasattr(trm, 'add_callback'):
            trm.add_callback(self._on_task_update)
    
    def _build_widgets(self):
        """Build the task orchestrator widgets."""
        # Create main frame
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # Create left frame for agent list
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        # Create right frame for agent details
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        # Agent list
        ttk.Label(left_frame, text="Agents", font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(0, 5))
        
        # Create treeview for agent list
        columns = ("id", "name", "type", "status", "progress")
        self.agent_tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=15)
        
        # Define headings
        self.agent_tree.heading("id", text="ID")
        self.agent_tree.heading("name", text="Name")
        self.agent_tree.heading("type", text="Type")
        self.agent_tree.heading("status", text="Status")
        self.agent_tree.heading("progress", text="Progress")
        
        # Define columns
        self.agent_tree.column("id", width=50)
        self.agent_tree.column("name", width=150)
        self.agent_tree.column("type", width=100)
        self.agent_tree.column("status", width=100)
        self.agent_tree.column("progress", width=100)
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=self.agent_tree.yview)
        self.agent_tree.configure(yscrollcommand=scrollbar.set)
        
        # Pack treeview and scrollbar
        self.agent_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind selection event
        self.agent_tree.bind("<<TreeviewSelect>>", self.on_agent_select)
        
        # Agent details
        ttk.Label(right_frame, text="Agent Details", font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(0, 5))
        
        # Create text widget for agent details
        self.agent_details = scrolledtext.ScrolledText(right_frame, wrap="word", height=20, width=50)
        self.agent_details.pack(fill="both", expand=True)
        
        # Configure text tags
        self.agent_details.tag_config("heading", font=("TkDefaultFont", 10, "bold"))
        self.agent_details.tag_config("label", font=("TkDefaultFont", 9, "bold"))
        
        # Buttons frame
        buttons_frame = ttk.Frame(right_frame)
        buttons_frame.pack(fill="x", pady=(10, 0))
        
        # Refresh button
        ttk.Button(buttons_frame, text="Refresh", command=self.refresh_agents).pack(side="left", padx=(0, 5))
        
        # Visualize button
        ttk.Button(buttons_frame, text="Visualize Graph", command=self.visualize_graph).pack(side="left")
        
        # Open results button
        ttk.Button(buttons_frame, text="Open Results File", command=self.open_results_file).pack(side="left")
        
        # Start update loop
        self.update_agents()
    
    def add_agent(self, agent):
        """Add an agent to the orchestrator."""
        self.agents[agent.id] = agent
        
        # Add callback to update UI when agent status changes
        agent.add_callback(self.update_agent_ui)
        
        # Update UI immediately
        self.update_agent_ui(agent)
    
    def update_agents(self):
        """Update the agent list and details."""
        # Update agent tree
        for item in self.agent_tree.get_children():
            self.agent_tree.delete(item)
        
        for agent_id, agent in self.agents.items():
            self.agent_tree.insert("", "end", values=(
                agent.id,
                agent.name,
                agent.task_type,
                agent.status,
                f"{agent.progress}%" if agent.progress else "0%"
            ))
        
        # Schedule next update
        self.after(1000, self.update_agents)
    
    def update_agent_ui(self, agent):
        """Update the UI for a specific agent."""
        # Update agent tree
        for item in self.agent_tree.get_children():
            if self.agent_tree.item(item, "values")[0] == agent.id:
                self.agent_tree.item(item, values=(
                    agent.id,
                    agent.name,
                    agent.task_type,
                    agent.status,
                    f"{agent.progress}%" if agent.progress else "0%"
                ))
                break
        
        # Update details if this agent is selected
        selected_items = self.agent_tree.selection()
        if selected_items:
            selected_id = self.agent_tree.item(selected_items[0], "values")[0]
            if selected_id == agent.id:
                self.show_agent_details(agent)
    
    def on_agent_select(self, event):
        """Handle agent selection."""
        selected_items = self.agent_tree.selection()
        if selected_items:
            selected_id = self.agent_tree.item(selected_items[0], "values")[0]
            agent = self.agents.get(selected_id)
            if agent:
                self.show_agent_details(agent)
    
    def show_agent_details(self, agent):
        """Show details for a specific agent."""
        # Clear details
        self.agent_details.config(state="normal")
        self.agent_details.delete("1.0", "end")
        
        # Add agent details
        self.agent_details.insert("end", f"Agent Details\n", "heading")
        self.agent_details.insert("end", "\n")
        
        self.agent_details.insert("end", "ID: ", "label")
        self.agent_details.insert("end", f"{agent.id}\n")
        
        self.agent_details.insert("end", "Name: ", "label")
        self.agent_details.insert("end", f"{agent.name}\n")
        
        self.agent_details.insert("end", "Description: ", "label")
        self.agent_details.insert("end", f"{agent.description}\n")
        
        self.agent_details.insert("end", "Type: ", "label")
        self.agent_details.insert("end", f"{agent.task_type}\n")
        
        self.agent_details.insert("end", "Status: ", "label")
        self.agent_details.insert("end", f"{agent.status}\n")
        
        self.agent_details.insert("end", "Progress: ", "label")
        self.agent_details.insert("end", f"{agent.progress}%\n")
        
        if agent.start_time:
            self.agent_details.insert("end", "Started: ", "label")
            if isinstance(agent.start_time, float):
                start_time_str = datetime.fromtimestamp(agent.start_time).strftime("%Y-%m-%d %H:%M:%S")
                self.agent_details.insert("end", f"{start_time_str}\n")
            else:
                start_time_str = agent.start_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(agent.start_time, 'strftime') else str(agent.start_time)
                self.agent_details.insert("end", f"{start_time_str}\n")
        
        if agent.end_time:
            self.agent_details.insert("end", "Ended: ", "label")
            if isinstance(agent.end_time, float):
                end_time_str = datetime.fromtimestamp(agent.end_time).strftime("%Y-%m-%d %H:%M:%S")
                self.agent_details.insert("end", f"{end_time_str}\n")
            else:
                end_time_str = agent.end_time.strftime("%Y-%m-%d %H:%M:%S") if hasattr(agent.end_time, 'strftime') else str(agent.end_time)
                self.agent_details.insert("end", f"{end_time_str}\n")
        
        if agent.get_execution_time():
            self.agent_details.insert("end", "Execution Time: ", "label")
            self.agent_details.insert("end", f"{agent.get_execution_time():.2f} seconds\n")
        
        self.agent_details.insert("end", "\nTask Parameters\n", "heading")
        self.agent_details.insert("end", "\n")
        
        for key, value in agent.task_params.items():
            self.agent_details.insert("end", f"{key}: ", "label")
            self.agent_details.insert("end", f"{value}\n")
        
        if agent.result:
            self.agent_details.insert("end", "\nResults\n", "heading")
            self.agent_details.insert("end", "\n")
            
            # Format results for better readability
            if isinstance(agent.result, dict):
                for key, value in agent.result.items():
                    if key == "result_file":
                        continue  # Skip file path in main display
                    
                    self.agent_details.insert("end", f"{key}: ", "label")
                    if key == "results" and isinstance(value, list):
                        self.agent_details.insert("end", f"\n")
                        for i, item in enumerate(value, 1):
                            self.agent_details.insert("end", f"  {i}. ", "label")
                            if isinstance(item, dict):
                                for k, v in item.items():
                                    self.agent_details.insert("end", f"{k}: {v}\n")
                            else:
                                self.agent_details.insert("end", f"{item}\n")
                    elif key == "conclusions" and isinstance(value, list):
                        self.agent_details.insert("end", f"\n")
                        for i, conclusion in enumerate(value, 1):
                            self.agent_details.insert("end", f"  {i}. {conclusion}\n")
                    else:
                        self.agent_details.insert("end", f"{value}\n")
            else:
                self.agent_details.insert("end", f"{agent.result}\n")
            
            # Show results file path if available
            if isinstance(agent.result, dict) and "result_file" in agent.result:
                self.agent_details.insert("end", "\nResults File: ", "label")
                self.agent_details.insert("end", f"{agent.result['result_file']}\n")
        
        if agent.error:
            self.agent_details.insert("end", "\nError\n", "heading")
            self.agent_details.insert("end", "\n")
            self.agent_details.insert("end", f"{agent.error}\n")
        
        self.agent_details.config(state="disabled")
        
    def refresh_agents(self):
        """Refresh the agent list."""
        # This is handled by the update_agents loop
        pass
    
    def visualize_graph(self):
        """Generate and display the task relationship graph."""
        if not self.agents:
            messagebox.showinfo("No Agents", "Please create some agents first.")
            return
        
        try:
            # Generate the graph
            graph_file = self.trm.draw_graph()
            
            # Display the graph
            img = Image.open(graph_file)
            img = ImageTk.PhotoImage(img)
            
            # Create a new window to display the graph
            graph_window = tk.Toplevel(self)
            graph_window.title("Task Relationship Graph")
            
            label = ttk.Label(graph_window, image=img)
            label.image = img  # Keep a reference
            label.pack(padx=10, pady=10)
            
            ttk.Button(graph_window, text="Close", command=graph_window.destroy).pack(pady=5)
            
        except Exception as e:
            messagebox.showerror("Error", f"Could not display graph: {str(e)}")
    
    def open_results_file(self):
        """Open the results file for the selected agent."""
        selected_items = self.agent_tree.selection()
        if not selected_items:
            messagebox.showinfo("Info", "Please select an agent first.")
            return
        
        selected_id = self.agent_tree.item(selected_items[0], "values")[0]
        agent = self.agents.get(selected_id)
        if not agent or not agent.result:
            messagebox.showinfo("Info", "No results available for this agent.")
            return
        
        # Get results file path
        result_file = None
        if isinstance(agent.result, dict) and "result_file" in agent.result:
            result_file = agent.result["result_file"]
        
        if not result_file or not os.path.exists(result_file):
            messagebox.showinfo("Info", "No results file available for this agent.")
            return
        
        # Open the file with the default application
        try:
            if sys.platform == "win32":
                os.startfile(result_file)
            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", result_file])
            else:  # Linux
                subprocess.run(["xdg-open", result_file])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open file: {str(e)}")
    
    def _on_task_update(self, task):
        """Handle task updates from TRM."""
        if hasattr(task, 'id') and task.id in self.agents:
            self.update_agent_ui(task)
    
    def log_message(self, message: str, tag: str = ""):
        """Log a message to the execution log (not used in this version)."""
        # This method is kept for compatibility but not used in the simplified UI
        pass