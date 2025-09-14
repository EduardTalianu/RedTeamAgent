# agents.py - Redesigned with single generic agent type

import threading
import time
import uuid
import requests
import json
import re
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
from moonshot_client import MoonshotClient

class AgentStatus:
    """Agent status constants."""
    PENDING = "PENDING"
    RUNNING = "RUNNING" 
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class BaseAgent:
    """Base class for all agents."""
    
    def __init__(self, name: str, description: str = ""):
        self.id = uuid.uuid4().int & 0xFFFFFFFF
        self.name = name
        self.description = description
        self.status = AgentStatus.PENDING
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None
        self.callbacks: List[Callable] = []
        
        # Each agent has independent conversation history
        self.conversation_history: List[Dict[str, str]] = []
    
    def __str__(self):
        return f"Agent {self.id}: {self.name} [{self.status}]"
    
    def add_callback(self, callback: Callable):
        """Add callback for status updates."""
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
        if status == AgentStatus.RUNNING:
            self.start_time = time.time()
        elif status in [AgentStatus.COMPLETED, AgentStatus.FAILED]:
            self.end_time = time.time()
        self._notify_callbacks()
    
    def get_execution_time(self) -> Optional[float]:
        """Get execution time in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None
    
    def execute(self) -> threading.Thread:
        """Execute agent in separate thread."""
        def _execute():
            try:
                self.set_status(AgentStatus.RUNNING)
                result = self._execute_task()
                self.result = result
                self.set_status(AgentStatus.COMPLETED)
            except Exception as e:
                self.error = str(e)
                self.set_status(AgentStatus.FAILED)
                print(f"Agent {self.name} failed: {e}")
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=_execute, daemon=True)
        thread.start()
        return thread
    
    def _execute_task(self) -> Any:
        """Override in subclasses."""
        raise NotImplementedError


class GenericAgent(BaseAgent):
    """Single generic agent that can handle any task based on orchestrator instructions."""
    
    def __init__(
        self,
        name: str,
        description: str,
        instructions: str,
        tools: Dict[str, Any],
        model: str = "moonshot-v1-32k",
        **kwargs
    ):
        super().__init__(name=name, description=description)
        
        # Store the specific instructions from orchestrator
        self.instructions = instructions
        self.tools = {k: v for k, v in tools.items() if k != 'mcp_agent_creator'}
        self.model = model
        
        # Initialize Moonshot client
        self.client = MoonshotClient(model=model)
        
        # Track tool usage
        self.tools_used = []
        self.tool_results = []
        
        # Initialize conversation with orchestrator's instructions
        self._initialize_conversation()

    def _initialize_conversation(self):
        """Initialize agent with generic system prompt and specific instructions."""
        system_prompt = self._build_generic_system_prompt()
        
        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self.instructions}
        ]
    
    def _build_generic_system_prompt(self) -> str:
        """Build completely generic system prompt."""
        # Build tools description
        tools_descriptions = []
        for tool_name, tool in self.tools.items():
            if getattr(tool, 'enabled', True):
                display_name = getattr(tool, 'friendly_name', tool_name)
                description = getattr(tool, 'description', 'No description')
                system_prompt = getattr(tool, 'get_system_prompt', lambda: '')()
                
                tools_descriptions.append(f"=== {display_name} ===")
                tools_descriptions.append(f"Description: {description}")
                if system_prompt:
                    tools_descriptions.append(f"Usage Instructions:\n{system_prompt}")
                tools_descriptions.append("")
        
        tools_text = "\n".join(tools_descriptions) if tools_descriptions else "No tools available"
        
        return f"""You are {self.name}, a versatile AI agent capable of handling any task.

AGENT DETAILS:
- Name: {self.name}
- Description: {self.description}
- Mission: Complete the specific task assigned by the orchestrator

AVAILABLE TOOLS:
{tools_text}

EXECUTION GUIDELINES:
1. Analyze the task instructions provided by the orchestrator
2. Break down complex tasks into manageable steps
3. Use available tools systematically to gather information or perform actions
4. Be thorough and methodical in your approach
5. Provide clear updates on your progress
6. Deliver comprehensive results

TOOL USAGE RULES:
- Use tools by including their exact XML format in your responses
- Wait for tool results before proceeding to next steps
- Use multiple tools if needed to complete the task thoroughly
- Analyze all tool results and incorporate findings into your work

RESPONSE FORMAT:
- Explain your approach to the task
- Use tools with proper XML syntax when needed
- Analyze and synthesize information from multiple sources
- Provide clear, actionable results
- Summarize key findings and conclusions

You will receive specific task instructions from the orchestrator. Execute them systematically using the available tools and your analytical capabilities."""

    def _execute_task(self) -> Dict[str, Any]:
        """Execute the agent's task with tool integration."""
        print(f"Agent {self.name} starting execution...")
        
        # Run conversation loop
        final_result = self._run_conversation_loop()
        
        return {
            "agent_name": self.name,
            "instructions": self.instructions,
            "final_result": final_result,
            "conversation_length": len(self.conversation_history),
            "tools_used": self.tools_used,
            "tool_results": self.tool_results
        }
    
    def _run_conversation_loop(self) -> str:
        """Run conversation loop with tool integration."""
        max_iterations = 15
        iteration = 0
        last_response = ""
        
        while iteration < max_iterations:
            iteration += 1
            print(f"Agent {self.name} - Iteration {iteration}")
            
            try:
                response = self._make_api_call()
                if not response:
                    break
                
                print(f"Agent {self.name} response length: {len(response)}")
                self.conversation_history.append({"role": "assistant", "content": response})
                last_response = response
                
                # Process tool usage
                tool_used = self._process_tool_usage(response)
                
                # Check for completion
                completion_indicators = [
                    "task completed", "analysis complete", "report complete",
                    "findings summary", "conclusion", "final results",
                    "task finished", "no further action needed", "complete"
                ]
                
                response_lower = response.lower()
                task_seems_complete = any(indicator in response_lower for indicator in completion_indicators)
                
                if not tool_used and (task_seems_complete or iteration > 10):
                    print(f"Agent {self.name} completed task (iteration {iteration})")
                    break
                
            except Exception as e:
                error_msg = f"Error in iteration {iteration}: {str(e)}"
                print(f"Agent {self.name} error: {error_msg}")
                self.conversation_history.append({"role": "user", "content": f"Error occurred: {error_msg}. Please continue with available information."})
                continue
        
        return last_response or "Task execution completed"
    
    def _process_tool_usage(self, response: str) -> bool:
        """Process tool usage in agent response."""
        tool_used = False
        
        # Check each available tool
        for tool_name, tool in self.tools.items():
            if not getattr(tool, 'enabled', True):
                continue
            
            try:
                command = tool.detect_request(response)
                if command:
                    print(f"Agent {self.name} - Detected {tool_name} usage: {command}")
                    
                    # Execute tool
                    tool_result = tool.execute(command)
                    print(f"Agent {self.name} - Tool {tool_name} result length: {len(str(tool_result))}")
                    
                    # Track tool usage
                    self.tools_used.append({
                        "tool_name": tool_name,
                        "command": command,
                        "iteration": len(self.conversation_history)
                    })
                    self.tool_results.append({
                        "tool_name": tool_name,
                        "result": tool_result,
                        "iteration": len(self.conversation_history)
                    })
                    
                    # Add tool result to conversation
                    display_name = getattr(tool, 'friendly_name', tool_name)
                    tool_message = f"Tool '{display_name}' executed successfully.\n\nResults:\n{tool_result}"
                    self.conversation_history.append({"role": "user", "content": tool_message})
                    
                    tool_used = True
                    break
                        
            except Exception as e:
                print(f"Agent {self.name} - Tool {tool_name} error: {e}")
                error_message = f"Tool '{tool_name}' encountered an error: {str(e)}\nPlease continue with available information."
                self.conversation_history.append({"role": "user", "content": error_message})
                tool_used = True
                break
        
        return tool_used
    
    def _make_api_call(self) -> Optional[str]:
        """Call Moonshot API directly."""
        payload = {
            "messages": self.conversation_history,
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": False
        }
        
        try:
            print(f"Agent {self.name} - Making API call with {len(self.conversation_history)} messages")
            response = self.client.chat(**payload)
            
            if not response:
                raise Exception("Empty response from API")
            
            return response
            
        except Exception as e:
            raise Exception(f"API call failed: {str(e)}")


class EnhancedAgentOrchestrator:
    """Enhanced orchestrator with generic agent management."""
    
    def __init__(self):
        self.agents: Dict[int, BaseAgent] = {}
        self.callbacks: List[Callable] = []
        self.max_concurrent_agents = 5
    
    def add_callback(self, callback: Callable):
        """Add callback for agent updates."""
        self.callbacks.append(callback)
    
    def create_agent(
        self,
        name: str,
        description: str,
        instructions: str,
        tools: Dict[str, Any],
        **kwargs
    ) -> GenericAgent:
        """Create and register a new generic agent."""
        
        # Check concurrent agents limit
        running_agents = self.get_running_agents()
        if len(running_agents) >= self.max_concurrent_agents:
            raise Exception(f"Maximum concurrent agents ({self.max_concurrent_agents}) reached.")
        
        agent = GenericAgent(
            name=name,
            description=description,
            instructions=instructions,
            tools=tools,
            **kwargs
        )
        
        self.agents[agent.id] = agent
        agent.add_callback(self._on_agent_update)
        
        print(f"Created generic agent {agent.id}: {agent.name}")
        return agent
    
    def get_agent(self, agent_id: int) -> Optional[BaseAgent]:
        """Get agent by ID."""
        return self.agents.get(agent_id)
    
    def list_agents(self) -> List[BaseAgent]:
        """Get list of all agents."""
        return sorted(self.agents.values(), key=lambda x: x.id, reverse=True)
    
    def get_running_agents(self) -> List[BaseAgent]:
        """Get list of currently running agents."""
        return [agent for agent in self.agents.values() if agent.status == AgentStatus.RUNNING]
    
    def stop_all_agents(self):
        """Stop all running agents."""
        for agent in self.get_running_agents():
            agent.set_status(AgentStatus.FAILED)
            agent.error = "Stopped by orchestrator"
    
    def _on_agent_update(self, agent: BaseAgent):
        """Handle agent status updates."""
        print(f"Agent {agent.id} ({agent.name}) status: {agent.status}")
        
        # Cleanup if too many agents
        if len(self.agents) > 100:
            self._cleanup_old_agents(50)
        
        # Notify callbacks
        for callback in self.callbacks:
            try:
                callback(agent)
            except Exception as e:
                print(f"Error in orchestrator callback: {e}")
    
    def _cleanup_old_agents(self, max_agents: int):
        """Clean up old agents."""
        if len(self.agents) > max_agents:
            sorted_agents = sorted(self.agents.items(), key=lambda x: x[1].id, reverse=True)
            agents_to_keep = dict(sorted_agents[:max_agents])
            removed_count = len(self.agents) - len(agents_to_keep)
            self.agents = agents_to_keep
            print(f"Cleaned up {removed_count} old agents")


class EnhancedAgentRegistry:
    """Registry for generic agent creation."""
    
    def __init__(self):
        self.orchestrator = EnhancedAgentOrchestrator()
    
    def create_agent(
        self,
        name: str,
        description: str,
        instructions: str,
        tools: Dict[str, Any] = None,
        **kwargs
    ) -> GenericAgent:
        """Create a new generic agent."""
        if 'model' not in kwargs:
            raise ValueError("Model must be provided for agent creation")
        
        return self.orchestrator.create_agent(
            name=name,
            description=description,
            instructions=instructions,
            tools=tools or {},
            **kwargs
        )
    
    def get_orchestrator(self) -> EnhancedAgentOrchestrator:
        """Get the orchestrator instance."""
        return self.orchestrator

# Global registry instance
agent_registry = EnhancedAgentRegistry()