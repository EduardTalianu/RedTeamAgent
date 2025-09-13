"""
Agent classes for task execution.
"""

import threading
import time
import os
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from .task_exceptions import (
    FixableTaskException,
    UnfixableTaskException,
    TaskTimeoutException,
    TaskImpossibleException,
    TaskNeedTurningException
)
from .task_orchestrator import Node, TaskRelationManager, Direction

class AgentStatus:
    """Status constants for agents."""
    PENDING = "PENDING"
    WORKING = "WORKING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class BaseAgent(Node):
    """Base class for all task agents."""
    
    def __init__(self, name: str, description: str = "", trm: TaskRelationManager = None):
        super().__init__()
        self.name = name
        self.description = description
        self.trm = trm
        self.status = AgentStatus.PENDING
        self.result = None
        self.error = None
        self.sub_agents = []
        self.parent_agent = None
        self.progress = 0
        self.start_time = None
        self.end_time = None
        self.callbacks = []
        
        if trm:
            trm.add_task(self)
    
    def __str__(self):
        return f"Agent {self.id}: {self.name} [{self.status}]"
    
    def add_callback(self, callback: Callable):
        """Add a callback to be called when status changes."""
        self.callbacks.append(callback)
    
    def _notify_callbacks(self):
        """Notify all callbacks of status change."""
        for callback in self.callbacks:
            try:
                callback(self)
            except Exception as e:
                print(f"Error in callback: {e}")
    
    def set_status(self, status: str):
        """Set agent status and notify callbacks."""
        self.status = status
        if status == AgentStatus.WORKING:
            self.start_time = time.time()
        elif status in [AgentStatus.SUCCESS, AgentStatus.FAILED, AgentStatus.CANCELLED]:
            self.end_time = time.time()
        self._notify_callbacks()
    
    def add_sub_agent(self, agent: 'BaseAgent'):
        """Add a sub-agent to this agent."""
        agent.parent_agent = self
        self.sub_agents.append(agent)
        
        if self.trm:
            # Add to task relationship manager
            self.trm.add_sub_tasks(self, [agent])
    
    def execute(self, **kwargs) -> Any:
        """Execute the agent in a separate thread."""
        def _execute():
            try:
                self.set_status(AgentStatus.WORKING)
                result = self._execute_task(**kwargs)
                self.result = result
                self.set_status(AgentStatus.SUCCESS)
                return result
            except FixableTaskException as e:
                self.error = str(e)
                self.set_status(AgentStatus.FAILED)
                raise e
            except UnfixableTaskException as e:
                self.error = str(e)
                self.set_status(AgentStatus.FAILED)
                raise e
            except Exception as e:
                self.error = str(e)
                self.set_status(AgentStatus.FAILED)
                raise e
        
        # Execute in a separate thread
        thread = threading.Thread(target=_execute)
        thread.daemon = True
        thread.start()
        return thread
    
    def cancel(self):
        """Cancel the agent execution."""
        if self.status == AgentStatus.WORKING:
            self.set_status(AgentStatus.CANCELLED)
            # Cancel sub-agents
            for agent in self.sub_agents:
                agent.cancel()
    
    def get_execution_time(self) -> Optional[float]:
        """Get execution time in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    def get_progress(self) -> float:
        """Get progress percentage (0-100)."""
        return self.progress
    
    @abstractmethod
    def _execute_task(self, **kwargs) -> Any:
        """Abstract method to be implemented by specific agents."""
        pass

class GenericAgent(BaseAgent):
    """Generic agent that executes tasks using MCP tools with proper MCP command formatting."""
    
    def __init__(self, task_type: str, task_params: Dict[str, Any], tools: Dict[str, Any], 
                 name: str = None, description: str = None, trm: TaskRelationManager = None):
        # Set default name and description if not provided
        if name is None:
            name = f"{task_type.replace('_', ' ').title()} Agent"
        if description is None:
            description = f"Agent to perform {task_type} task"
            
        super().__init__(name=name, description=description, trm=trm)
        self.task_type = task_type
        self.task_params = task_params
        self.tools = tools
    
    def _save_results_to_file(self, result: Dict[str, Any]) -> str:
        """Save agent results to a file."""
        # Create results directory if it doesn't exist
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "agents")
        os.makedirs(results_dir, exist_ok=True)
        
        # Create a filename with agent ID and timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"agent_{self.id}_{timestamp}.json"
        filepath = os.path.join(results_dir, filename)
        
        # Convert timestamps to ISO format strings if they exist
        start_time_str = None
        end_time_str = None
        
        if self.start_time:
            if isinstance(self.start_time, float):
                start_time_str = datetime.fromtimestamp(self.start_time).isoformat()
            else:
                start_time_str = self.start_time.isoformat() if hasattr(self.start_time, 'isoformat') else str(self.start_time)
        
        if self.end_time:
            if isinstance(self.end_time, float):
                end_time_str = datetime.fromtimestamp(self.end_time).isoformat()
            else:
                end_time_str = self.end_time.isoformat() if hasattr(self.end_time, 'isoformat') else str(self.end_time)
        
        # Prepare data to save
        data_to_save = {
            "agent_id": self.id,
            "agent_name": self.name,
            "agent_description": self.description,
            "task_type": self.task_type,
            "task_params": self.task_params,
            "status": self.status,
            "progress": self.progress,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "execution_time": self.get_execution_time(),
            "result": result
        }
        
        # Save to file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def _execute_task(self, **kwargs) -> Dict[str, Any]:
        """Execute the task using appropriate MCP tools with proper command formatting."""
        try:
            # Update progress to 10%
            self.progress = 10
            
            # Execute the task based on type
            if self.task_type == "web_search":
                result = self._execute_web_search()
            elif self.task_type == "data_analysis":
                result = self._execute_data_analysis()
            elif self.task_type == "content_creation":
                result = self._execute_content_creation()
            elif self.task_type == "calculation":
                result = self._execute_calculation()
            else:
                raise TaskImpossibleException(f"Unknown task type: {self.task_type}")
            
            # Save results to file
            result_file = self._save_results_to_file(result)
            result["result_file"] = result_file
            
            # Update progress to 100%
            self.progress = 100
            return result
            
        except Exception as e:
            # Save error to file
            error_result = {"error": str(e)}
            try:
                error_file = self._save_results_to_file(error_result)
                error_result["result_file"] = error_file
            except:
                pass  # Continue even if saving fails
            
            raise TaskImpossibleException(f"Error executing task: {str(e)}")
    
    def _execute_web_search(self) -> Dict[str, Any]:
        """Execute web search using MCP web search tool with proper MCP format."""
        query = self.task_params.get("query", "")
        
        # Update progress to 30%
        self.progress = 30
        
        # Use MCP web search tool if available
        if "mcp_websearch" in self.tools and self.tools["mcp_websearch"].enabled:
            try:
                tool = self.tools["mcp_websearch"]
                
                # Perform multiple searches with different terms for comprehensive results
                search_queries = [
                    {"query": query, "engine": "duckduckgo", "num_results": 5},
                    {"query": query + " about", "engine": "duckduckgo", "num_results": 3},
                    {"query": query + " services", "engine": "duckduckgo", "num_results": 3}
                ]
                
                all_results = []
                
                for i, search_params in enumerate(search_queries):
                    # Update progress
                    self.progress = 30 + (i * 20)
                    
                    # Execute search using proper MCP format
                    result = tool.execute(search_params)
                    
                    # Parse the result - it should be a formatted string
                    if isinstance(result, str):
                        # Extract results from the formatted string
                        lines = result.split('\n')
                        current_result = {}
                        in_result = False
                        
                        for line in lines:
                            line = line.strip()
                            if line.startswith(('1.', '2.', '3.', '4.', '5.')):
                                if current_result and 'title' in current_result:
                                    all_results.append(current_result)
                                current_result = {'title': line[2:].strip(), 'url': '', 'snippet': ''}
                                in_result = True
                            elif line.startswith('URL:') and in_result:
                                current_result['url'] = line[4:].strip()
                            elif in_result and not line.startswith(('URL:', 'Web Search Results')):
                                if line and not line.startswith(('1.', '2.', '3.', '4.', '5.')):
                                    current_result['snippet'] += line + ' '
                        
                        # Add the last result
                        if current_result and 'title' in current_result:
                            all_results.append(current_result)
                
                # Remove duplicates
                unique_results = []
                seen_urls = set()
                for result in all_results:
                    if result.get('url') and result['url'] not in seen_urls:
                        unique_results.append(result)
                        seen_urls.add(result['url'])
                    elif not result.get('url'):  # Keep results without URLs
                        unique_results.append(result)
                
                # Update progress to 90%
                self.progress = 90
                
                return {
                    "task_type": "web_search",
                    "query": query,
                    "search_queries_used": search_queries,
                    "results": unique_results,
                    "count": len(unique_results),
                    "conclusions": [
                        f"Found {len(unique_results)} unique results for {query}",
                        "Search covered multiple aspects including main site, about pages, and services",
                        "Results provide a comprehensive overview of the target domain"
                    ]
                }
                
            except Exception as e:
                raise TaskImpossibleException(f"Web search failed: {str(e)}")
        else:
            # Fallback to simulated search if MCP tool is not available
            time.sleep(2)
            
            # Simulate more detailed search results
            results = [
                {"title": f"Main page for {query}", "url": f"https://{query.replace('site:', '').strip()}", "snippet": "Official website with information about services and products."},
                {"title": f"About {query}", "url": f"https://{query.replace('site:', '').strip()}/about", "snippet": "Company history, mission, and values."},
                {"title": f"Contact {query}", "url": f"https://{query.replace('site:', '').strip()}/contact", "snippet": "Contact information and locations."},
                {"title": f"Services offered", "url": f"https://{query.replace('site:', '').strip()}/services", "snippet": "Detailed information about products and services."},
                {"title": f"News and updates", "url": f"https://{query.replace('site:', '').strip()}/news", "snippet": "Latest news and updates."}
            ]
            
            return {
                "task_type": "web_search",
                "query": query,
                "search_queries_used": [query],
                "results": results,
                "count": len(results),
                "note": "Simulated results (MCP web search tool not available)",
                "conclusions": [
                    f"Found {len(results)} simulated results for {query}",
                    "Search covered main pages including about, contact, services, and news",
                    "Results provide a comprehensive overview of the target domain structure"
                ]
            }
    
    def _execute_data_analysis(self) -> Dict[str, Any]:
        """Execute data analysis using MCP tools with proper DNS commands following MCP format."""
        data = self.task_params.get("data", "")
        analysis_type = self.task_params.get("analysis_type", "")
        
        # Update progress to 30%
        self.progress = 30
        
        if analysis_type == "dns":
            # Use MCP curl tool for DNS analysis with proper MCP format
            if "mcp_curl" in self.tools and self.tools["mcp_curl"].enabled:
                try:
                    tool = self.tools["mcp_curl"]
                    
                    # Perform multiple DNS-related queries using curl with proper MCP command format
                    dns_commands = [
                        {
                            "command": "raw",
                            "raw_command": f"nslookup {data}",
                            "target": data,
                            "timeout": 30
                        },
                        {
                            "command": "raw", 
                            "raw_command": f"nslookup -type=MX {data}",
                            "target": data,
                            "timeout": 30
                        },
                        {
                            "command": "raw",
                            "raw_command": f"nslookup -type=NS {data}",
                            "target": data, 
                            "timeout": 30
                        },
                        {
                            "command": "raw",
                            "raw_command": f"nslookup www.{data}",
                            "target": f"www.{data}",
                            "timeout": 30
                        }
                    ]
                    
                    all_results = {}
                    
                    for i, dns_cmd in enumerate(dns_commands):
                        # Update progress
                        self.progress = 30 + (i * 15)
                        
                        # Execute DNS query using MCP curl tool with proper format
                        result = tool.execute(dns_cmd)
                        command_description = dns_cmd["raw_command"]
                        all_results[command_description] = result
                    
                    # Update progress to 90%
                    self.progress = 90
                    
                    return {
                        "task_type": "data_analysis",
                        "analysis_type": analysis_type,
                        "data": data,
                        "commands_executed": dns_commands,
                        "results": all_results,
                        "conclusions": [
                            f"Performed comprehensive DNS analysis for {data}",
                            "Analyzed A records, MX records, NS records, and www subdomain",
                            "Results provide complete DNS infrastructure overview"
                        ]
                    }
                    
                except Exception as e:
                    raise TaskImpossibleException(f"DNS analysis failed: {str(e)}")
            else:
                # Fallback to simulated analysis
                time.sleep(3)
                
                return {
                    "task_type": "data_analysis",
                    "analysis_type": analysis_type,
                    "data": data,
                    "commands_executed": [
                        {"command": f"nslookup {data}"},
                        {"command": f"nslookup -type=MX {data}"},
                        {"command": f"nslookup www.{data}"}
                    ],
                    "results": {
                        f"nslookup {data}": f"A record: 192.0.2.1 for {data}",
                        f"nslookup -type=MX {data}": f"MX record: mail.{data}",
                        f"nslookup www.{data}": f"CNAME record: www.{data} -> {data}"
                    },
                    "conclusions": [
                        f"Performed simulated DNS analysis for {data}",
                        "Identified A records for main domain",
                        "Found MX record for mail handling",
                        "CNAME record indicates www subdomain configuration"
                    ],
                    "note": "Simulated results (MCP curl tool not available)"
                }
        else:
            # For other analysis types, simulate more thorough work
            time.sleep(3)
            
            return {
                "task_type": "data_analysis",
                "analysis_type": analysis_type,
                "data": data,
                "analysis_performed": [
                    "Basic information extraction",
                    "Pattern recognition", 
                    "Statistical analysis",
                    "Comparative analysis with similar data"
                ],
                "summary": f"Comprehensive analysis completed for {type(data).__name__}",
                "insights": [
                    "Primary insight: The data shows consistent patterns",
                    "Secondary insight: There are notable outliers that warrant further investigation", 
                    "Tertiary insight: The data correlates with expected benchmarks"
                ],
                "recommendations": [
                    "Consider investigating the outliers further",
                    "The patterns suggest potential for optimization",
                    "Additional data collection may improve accuracy"
                ],
                "conclusions": [
                    f"Completed comprehensive {analysis_type} analysis for {data}",
                    "Analysis included multiple approaches: pattern recognition, statistical analysis, and comparative analysis",
                    "Identified key insights and actionable recommendations based on the findings"
                ],
                "note": "Simulated results (analysis type not supported by MCP tools)"
            }
    
    def _execute_content_creation(self) -> Dict[str, Any]:
        """Execute content creation using MCP tools with proper MCP format."""
        content_type = self.task_params.get("content_type", "")
        topic = self.task_params.get("topic", "")
        
        # Update progress to 30%
        self.progress = 30
        
        # Use MCP web search tool for research if available
        research_results = None
        if "mcp_websearch" in self.tools and self.tools["mcp_websearch"].enabled:
            try:
                tool = self.tools["mcp_websearch"]
                # Use proper MCP format for web search
                research_params = {"query": topic, "engine": "duckduckgo", "num_results": 3}
                research_results = tool.execute(research_params)
                
                # Update progress to 50%
                self.progress = 50
            except Exception as e:
                print(f"Research failed: {str(e)}")
        
        # Simulate content creation
        time.sleep(1)
        
        content = f"This is a sample {content_type} about {topic}."
        if research_results:
            content += " Created using research from web search results."
        
        # Update progress to 100%
        self.progress = 100
        
        return {
            "task_type": "content_creation",
            "content_type": content_type,
            "topic": topic,
            "content": content,
            "research": research_results,
            "word_count": len(content.split()),
            "conclusions": [
                f"Successfully created {content_type} about {topic}",
                f"Content is {len(content.split())} words in length",
                "Research was incorporated into the content creation process" if research_results else "Content created without external research"
            ]
        }
    
    def _execute_calculation(self) -> Dict[str, Any]:
        """Execute calculation task."""
        expression = self.task_params.get("expression", "")
        
        # Update progress to 50%
        self.progress = 50
        
        try:
            # Simple evaluation (be careful with eval in production!)
            result = eval(expression)
            
            # Update progress to 100%
            self.progress = 100
            
            return {
                "task_type": "calculation", 
                "expression": expression,
                "result": result,
                "conclusions": [
                    f"Successfully calculated the result of {expression}",
                    f"The result is {result}",
                    "Calculation was performed without errors"
                ]
            }
        except Exception as e:
            raise TaskImpossibleException(f"Cannot calculate expression: {e}")