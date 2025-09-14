"""
Enhanced agent system with proper tool integration and conversation management.
Fixes the issues with tool detection and usage.
"""

import threading
import time
import uuid
import requests
import json
import re
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime


class AgentStatus:
    """Agent status constants."""
    PENDING = "PENDING"
    RUNNING = "RUNNING" 
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BaseAgent:
    """Enhanced base class for all agents."""
    
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


class EnhancedGenericAgent(BaseAgent):
    """
    Enhanced generic agent with proper tool integration and conversation management.
    """
    
    def __init__(
        self,
        task_type: str,
        task_params: Dict[str, Any],
        tools: Dict[str, Any],
        name: str = None,
        description: str = None,
        server_url: str = "http://127.0.0.1:11436",
        model: str = "groq-gemma2-9b-it"
    ):
        if name is None:
            name = f"{task_type.replace('_', ' ').title()} Agent"
        if description is None:
            description = f"Specialized agent to perform {task_type} tasks"
            
        super().__init__(name=name, description=description)
        
        self.task_type = task_type
        self.task_params = task_params
        self.tools = {k: v for k, v in tools.items() if k != 'mcp_agent_creator'}  # Exclude agent creator
        self.server_url = server_url
        self.model = model
        
        # Track tool usage
        self.tools_used = []
        self.tool_results = []
        
        # Initialize conversation with enhanced system prompt
        self._initialize_enhanced_conversation()
    
    def _initialize_enhanced_conversation(self):
        """Initialize agent with comprehensive system prompt and task instructions."""
        system_prompt = self._build_enhanced_system_prompt()
        initial_task = self._build_detailed_task_message()
        
        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_task}
        ]
    
    def _build_enhanced_system_prompt(self) -> str:
        """Build comprehensive system prompt with tool awareness."""
        # Build detailed tools description
        tools_descriptions = []
        for tool_name, tool in self.tools.items():
            if getattr(tool, 'enabled', True):
                display_name = getattr(tool, 'friendly_name', tool_name)
                description = getattr(tool, 'description', 'No description')
                
                # Get tool's system prompt for usage instructions
                system_prompt = getattr(tool, 'get_system_prompt', lambda: '')()
                
                tools_descriptions.append(f"=== {display_name} ===")
                tools_descriptions.append(f"Description: {description}")
                if system_prompt:
                    tools_descriptions.append(f"Usage Instructions:\n{system_prompt}")
                tools_descriptions.append("")
        
        tools_text = "\n".join(tools_descriptions) if tools_descriptions else "No tools available"
        
        # Task-specific guidance
        task_guidance = self._get_task_specific_guidance()
        
        return f"""You are {self.name}, a specialized AI agent.

AGENT DETAILS:
- Name: {self.name}
- Description: {self.description}  
- Task Type: {self.task_type}
- Task Parameters: {json.dumps(self.task_params, indent=2)}

MISSION:
You must complete your assigned task step-by-step using the available tools.
Work systematically and use tools when appropriate to gather information or perform actions.

AVAILABLE TOOLS:
{tools_text}

TASK-SPECIFIC GUIDANCE:
{task_guidance}

IMPORTANT RULES:
1. Use tools by including their exact XML format in your responses
2. Wait for tool results before proceeding to next steps
3. Be systematic and thorough in your approach
4. Provide clear summaries of your findings
5. Complete the task fully before concluding
6. Use multiple tools if needed to gather comprehensive information

RESPONSE FORMAT:
- Explain what you're doing
- Use tools with proper XML syntax
- Analyze tool results
- Provide clear conclusions and next steps"""

    def _get_task_specific_guidance(self) -> str:
        """Get task-specific guidance for different task types."""
        guidance_map = {
            "web_search": """
For web search tasks:
1. Start with broad search terms, then refine as needed
2. Use multiple search queries to get comprehensive information
3. Analyze search results and extract key information
4. Look for authoritative sources and recent information
5. Summarize findings with sources

Example workflow for domain reconnaissance:
- Search for basic domain information
- Search for security-related information
- Search for technology stack information
- Compile comprehensive intelligence report""",
            
            "data_analysis": """
For data analysis tasks:
1. First understand the data structure and content
2. Use appropriate analysis tools based on data type
3. Look for patterns, trends, and anomalies
4. Provide statistical insights where relevant
5. Present findings in clear, actionable format

For domain analysis:
- Use curl to gather HTTP headers and response information
- Analyze DNS information if available
- Check for security headers and configurations""",
            
            "content_creation": """
For content creation tasks:
1. Research the topic thoroughly using web search
2. Gather multiple perspectives and sources
3. Structure content logically
4. Include relevant examples and details
5. Ensure accuracy and completeness""",
            
            "calculation": """
For calculation tasks:
1. Break down complex problems into steps
2. Show your work clearly
3. Verify results when possible
4. Explain the methodology used"""
        }
        
        return guidance_map.get(self.task_type, "Complete the assigned task using available tools as needed.")
    
    def _build_detailed_task_message(self) -> str:
        """Build detailed initial task message."""
        base_message = f"Your task is to perform a {self.task_type} operation."
        
        if self.task_type == "web_search":
            query = self.task_params.get('query', '')
            base_message = f"""Your task is to perform comprehensive web search and analysis.

Search Query: "{query}"

Please perform the following steps:
1. Search for general information about the query
2. If it's a domain/website, search for security-related information
3. Look for any technical details or background information
4. Compile a comprehensive report with your findings

Use the Web Search tool multiple times with different search terms to gather complete information."""

        elif self.task_type == "data_analysis":
            data = self.task_params.get('data', '')
            analysis_type = self.task_params.get('analysis_type', 'general')
            base_message = f"""Your task is to perform data analysis.

Data: {data}
Analysis Type: {analysis_type}

Please analyze the provided data systematically:
1. If it's a URL/domain, use curl to gather HTTP information
2. Analyze the response headers, status codes, and content
3. Look for security indicators and technical details
4. Provide comprehensive analysis and recommendations

Use the Curl tool to gather technical information about the target."""

        elif self.task_type == "content_creation":
            topic = self.task_params.get('topic', '')
            content_type = self.task_params.get('content_type', 'general')
            base_message = f"""Your task is to create content.

Topic: {topic}
Content Type: {content_type}

Please create comprehensive content:
1. Research the topic using web search
2. Gather current information and multiple perspectives  
3. Structure the content appropriately
4. Include relevant details and examples
5. Ensure accuracy and completeness"""

        return base_message
    
    def _execute_task(self) -> Dict[str, Any]:
        """Execute the agent's task with proper tool integration."""
        print(f"Agent {self.name} starting execution...")
        
        if not self._check_server_health():
            raise Exception("API server is not available")
        
        # Run enhanced conversation loop
        final_result = self._run_enhanced_conversation_loop()
        
        return {
            "task_type": self.task_type,
            "task_params": self.task_params,
            "agent_name": self.name,
            "final_result": final_result,
            "conversation_length": len(self.conversation_history),
            "tools_used": self.tools_used,
            "tool_results": self.tool_results
        }
    
    def _run_enhanced_conversation_loop(self) -> str:
        """Enhanced conversation loop with better tool integration."""
        max_iterations = 15  # Increased for complex tasks
        iteration = 0
        last_response = ""
        
        while iteration < max_iterations:
            iteration += 1
            print(f"Agent {self.name} - Iteration {iteration}")
            
            # Make API call
            try:
                response = self._make_api_call()
                if not response:
                    break
                
                print(f"Agent {self.name} response length: {len(response)}")
                print(f"Agent {self.name} response preview: {response[:300]}...")
                
                self.conversation_history.append({"role": "assistant", "content": response})
                last_response = response
                
                # Process tool usage
                tool_used = self._process_tool_usage(response)
                
                # Check for completion indicators
                completion_indicators = [
                    "task completed", "analysis complete", "report complete",
                    "findings summary", "conclusion", "final results",
                    "task finished", "no further action needed"
                ]
                
                response_lower = response.lower()
                task_seems_complete = any(indicator in response_lower for indicator in completion_indicators)
                
                if not tool_used:
                    if task_seems_complete or iteration > 10:
                        # Agent indicates completion or max iterations reached
                        print(f"Agent {self.name} completed task (iteration {iteration})")
                        break
                    else:
                        # Encourage tool usage if not used in early iterations
                        if iteration <= 3:
                            encouragement = self._get_tool_usage_encouragement()
                            print(f"Agent {self.name} - Encouraging tool usage")
                            self.conversation_history.append({"role": "user", "content": encouragement})
                        else:
                            # Let agent continue naturally
                            continue
                
            except Exception as e:
                error_msg = f"Error in iteration {iteration}: {str(e)}"
                print(f"Agent {self.name} error: {error_msg}")
                self.conversation_history.append({"role": "user", "content": f"Error occurred: {error_msg}. Please continue with available information."})
                continue
        
        return last_response or "Task execution completed"
    
    def _get_tool_usage_encouragement(self) -> str:
        """Get task-specific encouragement to use tools."""
        if self.task_type == "web_search":
            query = self.task_params.get('query', 'your assigned topic')
            return f"""You need to use the Web Search tool to gather information about "{query}". 

Please use this exact format:
```xml
<tool>
  <name>web_search</name>
  <parameters>
    <query>{query}</query>
  </parameters>
</tool>
```

Start by searching for general information, then refine your searches based on what you find."""
        
        elif self.task_type == "data_analysis":
            data = self.task_params.get('data', '')
            if 'http' in data or '.' in data:  # Looks like a URL/domain
                return f"""You need to use the Curl tool to analyze "{data}". 

Please use this exact format:
```xml
<tool>
  <n>curl</n>
  <parameters>
    <command_id>2</command_id>
    <target>{data}</target>
  </parameters>
</tool>
```

This will get HTTP headers and basic information about the target."""
        
        return """You have tools available to help complete your task. Please use the appropriate tools with their exact XML format as shown in the system instructions."""
    
    def _process_tool_usage(self, response: str) -> bool:
        """Process tool usage in agent response with enhanced detection."""
        tool_used = False
        
        # Check each available tool
        for tool_name, tool in self.tools.items():
            if not getattr(tool, 'enabled', True):
                continue
            
            try:
                # Use tool's detection method
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
                    break  # Only process one tool per iteration
                    
            except Exception as e:
                print(f"Agent {self.name} - Tool {tool_name} error: {e}")
                error_message = f"Tool '{tool_name}' encountered an error: {str(e)}\nPlease continue with available information."
                self.conversation_history.append({"role": "user", "content": error_message})
                tool_used = True  # Still counts as tool usage attempt
                break
        
        return tool_used
    
    def _make_api_call(self) -> Optional[str]:
        """Make API call with enhanced error handling."""
        payload = {
            "model": self.model,
            "messages": self.conversation_history,
            "temperature": 0.7,
            "max_tokens": 2000,  # Increased for detailed responses
            "stream": False
        }
        
        try:
            print(f"Agent {self.name} - Making API call with {len(self.conversation_history)} messages")
            
            response = requests.post(
                f"{self.server_url}/api/chat",
                json=payload,
                timeout=45,  # Increased timeout
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status {response.status_code}: {response.text}")
            
            data = response.json()
            content = self._extract_content(data)
            
            if not content or content.strip() == "":
                raise Exception("Empty response from API")
            
            return content
            
        except requests.exceptions.Timeout:
            raise Exception("API call timed out after 45 seconds")
        except requests.exceptions.ConnectionError:
            raise Exception("Cannot connect to API server")
        except json.JSONDecodeError:
            raise Exception("Invalid JSON response from API")
        except Exception as e:
            raise Exception(f"API call failed: {str(e)}")
    
    def _extract_content(self, response_data: Dict) -> str:
        """Extract content from API response with better error handling."""
        try:
            # Try different response formats
            if "choices" in response_data and len(response_data["choices"]) > 0:
                choice = response_data["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    content = choice["message"]["content"]
                    if content:
                        return content
            
            if "message" in response_data:
                if isinstance(response_data["message"], str):
                    return response_data["message"]
                elif "content" in response_data["message"]:
                    return response_data["message"]["content"]
            
            # Try other common keys
            for key in ["content", "response", "text"]:
                if key in response_data and response_data[key]:
                    return response_data[key]
            
            # If all else fails, convert to string
            return str(response_data)
            
        except Exception as e:
            raise Exception(f"Could not extract content from response: {e}")
    
    def _check_server_health(self) -> bool:
        """Check if server is available."""
        try:
            response = requests.get(f"{self.server_url}/health", timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Server health check failed: {e}")
            return False


class EnhancedAgentOrchestrator:
    """Enhanced orchestrator with better agent management."""
    
    def __init__(self):
        self.agents: Dict[int, BaseAgent] = {}
        self.callbacks: List[Callable] = []
        self.max_concurrent_agents = 5  # Limit concurrent agents
    
    def add_callback(self, callback: Callable):
        """Add callback for agent updates."""
        self.callbacks.append(callback)
    
    def create_agent(
        self,
        task_type: str,
        task_params: Dict[str, Any],
        tools: Dict[str, Any],
        **kwargs
    ) -> EnhancedGenericAgent:
        """Create and register a new enhanced agent."""
        
        # Check concurrent agents limit
        running_agents = self.get_running_agents()
        if len(running_agents) >= self.max_concurrent_agents:
            raise Exception(f"Maximum concurrent agents ({self.max_concurrent_agents}) reached. Please wait for some agents to complete.")
        
        agent = EnhancedGenericAgent(
            task_type=task_type,
            task_params=task_params,
            tools=tools,
            **kwargs
        )
        
        self.agents[agent.id] = agent
        
        # Add callback to notify orchestrator of agent updates
        agent.add_callback(self._on_agent_update)
        
        print(f"Created agent {agent.id}: {agent.name} for {task_type}")
        return agent
    
    def get_agent(self, agent_id: int) -> Optional[BaseAgent]:
        """Get agent by ID."""
        return self.agents.get(agent_id)
    
    def list_agents(self) -> List[BaseAgent]:
        """Get list of all agents sorted by creation time."""
        return sorted(self.agents.values(), key=lambda x: x.id, reverse=True)
    
    def get_running_agents(self) -> List[BaseAgent]:
        """Get list of currently running agents."""
        return [agent for agent in self.agents.values() if agent.status == AgentStatus.RUNNING]
    
    def get_completed_agents(self) -> List[BaseAgent]:
        """Get list of completed agents."""
        return [agent for agent in self.agents.values() if agent.status == AgentStatus.COMPLETED]
    
    def get_failed_agents(self) -> List[BaseAgent]:
        """Get list of failed agents."""
        return [agent for agent in self.agents.values() if agent.status == AgentStatus.FAILED]
    
    def stop_all_agents(self):
        """Stop all running agents."""
        for agent in self.get_running_agents():
            agent.set_status(AgentStatus.FAILED)
            agent.error = "Stopped by orchestrator"
    
    def cleanup_old_agents(self, max_agents: int = 50):
        """Clean up old agents to prevent memory issues."""
        if len(self.agents) > max_agents:
            # Keep most recent agents
            sorted_agents = sorted(self.agents.items(), key=lambda x: x[1].id, reverse=True)
            agents_to_keep = dict(sorted_agents[:max_agents])
            removed_count = len(self.agents) - len(agents_to_keep)
            self.agents = agents_to_keep
            print(f"Cleaned up {removed_count} old agents")
    
    def get_agent_statistics(self) -> Dict[str, int]:
        """Get statistics about agents."""
        stats = {
            "total": len(self.agents),
            "running": len(self.get_running_agents()),
            "completed": len(self.get_completed_agents()),
            "failed": len(self.get_failed_agents()),
            "pending": len([a for a in self.agents.values() if a.status == AgentStatus.PENDING])
        }
        return stats
    
    def _on_agent_update(self, agent: BaseAgent):
        """Handle agent status updates."""
        print(f"Agent {agent.id} ({agent.name}) status changed to: {agent.status}")
        
        # Cleanup if too many agents
        if len(self.agents) > 100:
            self.cleanup_old_agents(50)
        
        # Notify orchestrator callbacks
        for callback in self.callbacks:
            try:
                callback(agent)
            except Exception as e:
                print(f"Error in orchestrator callback: {e}")


class EnhancedAgentRegistry:
    """Enhanced registry for agent creation with better management."""
    
    def __init__(self):
        self.orchestrator = EnhancedAgentOrchestrator()
    
    def create_agent(
        self,
        task_type: str,
        task_params: Dict[str, Any],
        tools: Dict[str, Any] = None,
        **kwargs
    ) -> EnhancedGenericAgent:
        """Create a new enhanced agent."""
        return self.orchestrator.create_agent(
            task_type=task_type,
            task_params=task_params,
            tools=tools or {},
            **kwargs
        )
    
    def get_orchestrator(self) -> EnhancedAgentOrchestrator:
        """Get the orchestrator instance."""
        return self.orchestrator


# Global enhanced registry instance
agent_registry = EnhancedAgentRegistry()