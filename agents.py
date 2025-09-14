"""
Enhanced agent system with streaming support and improved rate limiting.
Includes better model selection and conversation management.
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


class StreamingGenericAgent(BaseAgent):
    """
    Enhanced generic agent with streaming support and improved rate limiting.
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
        self.tools = {k: v for k, v in tools.items() if k != 'mcp_agent_creator'}
        self.server_url = server_url
        self.model = self._select_best_model(model)
        
        # Enhanced limits and settings
        self.max_iterations = 25  # Increased from 15
        self.api_timeout = 60     # Increased timeout
        self.use_streaming = True  # Enable streaming by default
        self.max_tokens_per_request = 1500  # Reasonable chunk size
        
        # Track tool usage and streaming
        self.tools_used = []
        self.tool_results = []
        self.streaming_chunks = []
        
        # Rate limiting protection
        self.last_api_call = 0
        self.min_api_interval = 2  # Minimum 2 seconds between API calls
        self.rate_limit_backoff = 5  # Start with 5 second backoff
        self.max_backoff = 300  # Max 5 minute backoff
        
        # Initialize conversation with enhanced system prompt
        self._initialize_enhanced_conversation()
    
    def _select_best_model(self, requested_model: str) -> str:
        """Select the best available model with fallback options."""
        # Model priority order (from fastest/cheapest to most capable)
        model_priorities = [
            "groq-llama-3.1-8b-instant",    # Fast and efficient
            "groq-gemma2-9b-it",            # Good balance
            "groq-llama-3.1-70b-versatile", # More capable but slower
            "groq-mixtral-8x7b-32768",      # Fallback
            "groq-llama2-70b-4096"          # Last resort
        ]
        
        # If requested model is in our priority list, use it
        if any(requested_model.endswith(model.split('-', 1)[1]) for model in model_priorities):
            return requested_model
        
        # Otherwise, default to the first (fastest) option
        print(f"Agent {self.name}: Using default model instead of {requested_model}")
        return model_priorities[0]
    
    def _initialize_enhanced_conversation(self):
        """Initialize agent with comprehensive system prompt."""
        system_prompt = self._build_comprehensive_system_prompt()
        initial_task = self._build_detailed_task_message()
        
        self.conversation_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_task}
        ]
    
    def _build_comprehensive_system_prompt(self) -> str:
        """Build comprehensive system prompt with streaming awareness."""
        # Build detailed tools description
        tools_descriptions = []
        for tool_name, tool in self.tools.items():
            if getattr(tool, 'enabled', True):
                display_name = getattr(tool, 'friendly_name', tool_name)
                description = getattr(tool, 'description', 'No description')
                system_prompt = getattr(tool, 'get_system_prompt', lambda: '')()
                
                tools_descriptions.append(f"=== {display_name} ===")
                tools_descriptions.append(f"Description: {description}")
                if system_prompt:
                    tools_descriptions.append(f"Usage:\n{system_prompt}")
                tools_descriptions.append("")
        
        tools_text = "\n".join(tools_descriptions) if tools_descriptions else "No tools available"
        
        # Task-specific guidance
        task_guidance = self._get_enhanced_task_guidance()
        
        return f"""You are {self.name}, a specialized AI agent with streaming capabilities.

AGENT DETAILS:
- Name: {self.name}
- Description: {self.description}  
- Task Type: {self.task_type}
- Task Parameters: {json.dumps(self.task_params, indent=2)}
- Streaming Mode: Enabled (you can think and act incrementally)

MISSION:
Complete your assigned task systematically using available tools.
Work step-by-step, use tools when needed, and provide comprehensive results.

AVAILABLE TOOLS:
{tools_text}

TASK-SPECIFIC GUIDANCE:
{task_guidance}

STREAMING WORKFLOW:
1. Analyze the task and plan your approach
2. Use tools systematically to gather information
3. Process each tool result before moving to the next step
4. Provide incremental updates on your progress
5. Compile comprehensive final results

TOOL USAGE RULES:
- Use tools with their exact XML format
- Wait for tool results before proceeding
- Use multiple tools if needed for complete analysis
- Provide clear analysis of each tool result

RESPONSE STYLE:
- Be systematic and thorough
- Explain your reasoning at each step
- Provide clear summaries and conclusions
- Use professional security/analysis terminology when appropriate"""

    def _get_enhanced_task_guidance(self) -> str:
        """Get enhanced task-specific guidance."""
        guidance_map = {
            "web_search": """
WEB SEARCH STRATEGY:
1. Start with broad reconnaissance queries
2. Use site-specific searches (site:target.com)
3. Search for security-related information
4. Look for technology stack information
5. Search for company/organization details
6. Compile comprehensive intelligence profile

SEARCH QUERY EXAMPLES:
- General: "target.com" information company
- Security: "target.com" security vulnerabilities incidents
- Technical: "target.com" technology stack infrastructure
- Files: site:target.com filetype:pdf OR filetype:doc
- Subdomains: "target.com" subdomain enumeration""",
            
            "data_analysis": """
DATA ANALYSIS STRATEGY:
1. Identify the data type (URL, domain, IP, etc.)
2. Use appropriate analysis tools (curl for web analysis)
3. Examine HTTP headers, responses, and security indicators
4. Look for technology fingerprints and configurations
5. Analyze security posture and potential issues
6. Provide actionable intelligence and recommendations

ANALYSIS FOCUS AREAS:
- HTTP response headers and security headers
- Server technology and versions
- SSL/TLS configuration
- Content and structure analysis
- Security indicators and potential vulnerabilities""",
            
            "content_creation": """
CONTENT CREATION STRATEGY:
1. Research the topic thoroughly using web search
2. Gather multiple perspectives and authoritative sources
3. Structure content logically and professionally
4. Include specific examples and evidence
5. Provide actionable recommendations
6. Format for the intended audience

CONTENT TYPES:
- Security assessment reports
- Technical analysis summaries  
- Intelligence briefings
- Recommendation documents"""
        }
        
        return guidance_map.get(self.task_type, "Complete the assigned task using available tools systematically.")
    
    def _build_detailed_task_message(self) -> str:
        """Build detailed initial task message."""
        if self.task_type == "web_search":
            query = self.task_params.get('query', '')
            return f"""TASK: Comprehensive Web Search and Intelligence Gathering

Target Query: "{query}"

OBJECTIVES:
1. Perform systematic web reconnaissance
2. Gather company/organization information
3. Identify technology stack and infrastructure
4. Look for security-related information
5. Compile comprehensive intelligence report

APPROACH:
Use multiple targeted searches with the Web Search tool to gather comprehensive information. Start broad, then get specific based on initial findings."""

        elif self.task_type == "data_analysis":
            data = self.task_params.get('data', '')
            analysis_type = self.task_params.get('analysis_type', 'general')
            return f"""TASK: Technical Data Analysis

Target: {data}
Analysis Type: {analysis_type}

OBJECTIVES:
1. Perform technical analysis of the target
2. Gather HTTP headers and server information
3. Identify technology stack and configurations
4. Assess security posture
5. Provide actionable intelligence

APPROACH:
Use the Curl tool to gather technical information, then analyze the results systematically."""

        elif self.task_type == "content_creation":
            topic = self.task_params.get('topic', '')
            content_type = self.task_params.get('content_type', 'report')
            return f"""TASK: Content Creation

Topic: {topic}
Content Type: {content_type}

OBJECTIVES:
1. Research the topic comprehensively
2. Gather authoritative information
3. Create well-structured content
4. Include specific examples and evidence
5. Provide actionable insights

APPROACH:
Use web search to gather comprehensive information, then create detailed, professional content."""

        return f"Complete the {self.task_type} task with the provided parameters."
    
    def _execute_task(self) -> Dict[str, Any]:
        """Execute task with streaming support."""
        print(f"Agent {self.name} starting execution with streaming...")
        
        if not self._check_server_health():
            raise Exception("API server is not available")
        
        # Run enhanced streaming conversation loop
        final_result = self._run_streaming_conversation_loop()
        
        return {
            "task_type": self.task_type,
            "task_params": self.task_params,
            "agent_name": self.name,
            "final_result": final_result,
            "conversation_length": len(self.conversation_history),
            "tools_used": self.tools_used,
            "tool_results": self.tool_results,
            "streaming_chunks": len(self.streaming_chunks)
        }
    
    def _run_streaming_conversation_loop(self) -> str:
        """Enhanced streaming conversation loop."""
        iteration = 0
        last_response = ""
        consecutive_errors = 0
        
        while iteration < self.max_iterations:
            iteration += 1
            print(f"Agent {self.name} - Iteration {iteration}")
            
            # Rate limiting protection
            self._enforce_rate_limiting()
            
            try:
                # Make streaming API call
                response = self._make_streaming_api_call()
                if not response:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        print(f"Agent {self.name} - Too many consecutive errors, stopping")
                        break
                    continue
                
                # Reset error counter on success
                consecutive_errors = 0
                self.rate_limit_backoff = 5  # Reset backoff
                
                print(f"Agent {self.name} - Response length: {len(response)}")
                self.conversation_history.append({"role": "assistant", "content": response})
                last_response = response
                
                # Process tool usage
                tool_used = self._process_tool_usage_with_streaming(response)
                
                # Check for completion
                if self._check_task_completion(response, iteration, tool_used):
                    print(f"Agent {self.name} completed task at iteration {iteration}")
                    break
                
            except Exception as e:
                consecutive_errors += 1
                error_msg = f"Error in iteration {iteration}: {str(e)}"
                print(f"Agent {self.name} error: {error_msg}")
                
                # Handle rate limiting
                if "rate limit" in str(e).lower() or "429" in str(e):
                    self._handle_rate_limiting()
                    continue
                
                if consecutive_errors >= 3:
                    print(f"Agent {self.name} - Too many errors, stopping")
                    break
                
                # Add error context to conversation
                self.conversation_history.append({
                    "role": "user", 
                    "content": f"Error occurred: {error_msg}. Please continue with available information or adjust your approach."
                })
        
        return last_response or "Task execution completed"
    
    def _enforce_rate_limiting(self):
        """Enforce rate limiting between API calls."""
        current_time = time.time()
        time_since_last = current_time - self.last_api_call
        
        if time_since_last < self.min_api_interval:
            sleep_time = self.min_api_interval - time_since_last
            print(f"Agent {self.name} - Rate limiting: sleeping {sleep_time:.1f}s")
            time.sleep(sleep_time)
    
    def _handle_rate_limiting(self):
        """Handle rate limiting with exponential backoff."""
        print(f"Agent {self.name} - Rate limited, backing off for {self.rate_limit_backoff}s")
        time.sleep(self.rate_limit_backoff)
        
        # Exponential backoff
        self.rate_limit_backoff = min(self.rate_limit_backoff * 2, self.max_backoff)
    
    def _make_streaming_api_call(self) -> Optional[str]:
        """Make streaming API call with better error handling."""
        payload = {
            "model": self.model,
            "messages": self.conversation_history,
            "temperature": 0.7,
            "max_tokens": self.max_tokens_per_request,
            "stream": self.use_streaming
        }
        
        try:
            self.last_api_call = time.time()
            print(f"Agent {self.name} - Making streaming API call with {len(self.conversation_history)} messages")
            
            if self.use_streaming:
                return self._handle_streaming_response(payload)
            else:
                return self._handle_non_streaming_response(payload)
            
        except requests.exceptions.Timeout:
            raise Exception("API call timed out")
        except requests.exceptions.ConnectionError:
            raise Exception("Cannot connect to API server")
        except Exception as e:
            raise Exception(f"API call failed: {str(e)}")
    
    def _handle_streaming_response(self, payload: Dict) -> str:
        """Handle streaming API response."""
        try:
            response = requests.post(
                f"{self.server_url}/api/chat",
                json=payload,
                timeout=self.api_timeout,
                stream=True,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code != 200:
                raise Exception(f"API returned status {response.status_code}: {response.text}")
            
            # Collect streaming chunks
            full_content = ""
            chunk_count = 0
            
            for line in response.iter_lines():
                if line:
                    line_text = line.decode('utf-8')
                    if line_text.startswith('data: '):
                        data_text = line_text[6:]  # Remove 'data: ' prefix
                        
                        if data_text == '[DONE]':
                            break
                        
                        try:
                            chunk_data = json.loads(data_text)
                            if 'choices' in chunk_data and chunk_data['choices']:
                                delta = chunk_data['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    full_content += content
                                    chunk_count += 1
                                    
                                    # Store chunk for analysis
                                    self.streaming_chunks.append({
                                        'content': content,
                                        'timestamp': time.time(),
                                        'chunk_number': chunk_count
                                    })
                        except json.JSONDecodeError:
                            continue  # Skip malformed chunks
            
            print(f"Agent {self.name} - Received {chunk_count} streaming chunks, total length: {len(full_content)}")
            return full_content.strip() if full_content else None
            
        except Exception as e:
            print(f"Agent {self.name} - Streaming error: {e}")
            # Fallback to non-streaming
            payload["stream"] = False
            return self._handle_non_streaming_response(payload)
    
    def _handle_non_streaming_response(self, payload: Dict) -> str:
        """Handle non-streaming API response."""
        response = requests.post(
            f"{self.server_url}/api/chat",
            json=payload,
            timeout=self.api_timeout,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code != 200:
            raise Exception(f"API returned status {response.status_code}: {response.text}")
        
        data = response.json()
        return self._extract_content(data)
    
    def _extract_content(self, response_data: Dict) -> str:
        """Extract content from API response."""
        try:
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
                if key in response_data and response_data[key]:
                    return response_data[key]
            
            return str(response_data)
            
        except Exception as e:
            raise Exception(f"Could not extract content from response: {e}")
    
    def _process_tool_usage_with_streaming(self, response: str) -> bool:
        """Process tool usage with streaming awareness."""
        tool_used = False
        
        # Check each available tool
        for tool_name, tool in self.tools.items():
            if not getattr(tool, 'enabled', True):
                continue
            
            try:
                command = tool.detect_request(response)
                if command:
                    print(f"Agent {self.name} - Detected {tool_name} usage: {command}")
                    
                    # Execute tool with better error handling
                    tool_result = self._execute_tool_safely(tool, command, tool_name)
                    
                    # Track tool usage
                    self.tools_used.append({
                        "tool_name": tool_name,
                        "command": command,
                        "iteration": len(self.conversation_history),
                        "timestamp": time.time()
                    })
                    
                    self.tool_results.append({
                        "tool_name": tool_name,
                        "result": tool_result,
                        "iteration": len(self.conversation_history),
                        "timestamp": time.time()
                    })
                    
                    # Add result to conversation
                    display_name = getattr(tool, 'friendly_name', tool_name)
                    tool_message = f"Tool '{display_name}' executed successfully.\n\nResults:\n{tool_result}"
                    self.conversation_history.append({"role": "user", "content": tool_message})
                    
                    tool_used = True
                    break  # Only process one tool per iteration
                    
            except Exception as e:
                print(f"Agent {self.name} - Tool {tool_name} error: {e}")
                self._handle_tool_error(tool_name, str(e))
                tool_used = True
                break
        
        return tool_used
    
    def _execute_tool_safely(self, tool, command: Dict[str, Any], tool_name: str) -> str:
        """Execute tool with comprehensive error handling."""
        try:
            result = tool.execute(command)
            print(f"Agent {self.name} - Tool {tool_name} executed successfully")
            return result
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            print(f"Agent {self.name} - {error_msg}")
            raise Exception(error_msg)
    
    def _handle_tool_error(self, tool_name: str, error: str):
        """Handle tool execution errors gracefully."""
        display_name = getattr(self.tools.get(tool_name), 'friendly_name', tool_name)
        error_message = f"Tool '{display_name}' encountered an error: {error}\n\nPlease continue with alternative approaches or available information."
        self.conversation_history.append({"role": "user", "content": error_message})
    
    def _check_task_completion(self, response: str, iteration: int, tool_used: bool) -> bool:
        """Check if task is completed with improved heuristics."""
        response_lower = response.lower()
        
        # Strong completion indicators
        strong_indicators = [
            "task completed", "analysis complete", "report complete",
            "reconnaissance complete", "findings summary", "final report",
            "comprehensive analysis complete", "investigation complete"
        ]
        
        # Weak completion indicators (need multiple or context)
        weak_indicators = [
            "conclusion", "summary", "final results", "completed successfully",
            "no further action needed", "task finished"
        ]
        
        # Check for strong indicators
        if any(indicator in response_lower for indicator in strong_indicators):
            return True
        
        # Check for weak indicators with context
        weak_count = sum(1 for indicator in weak_indicators if indicator in response_lower)
        if weak_count >= 2:  # Multiple weak indicators
            return True
        
        # Consider iteration count and tool usage
        if iteration >= 15 and not tool_used:  # Many iterations without recent tool use
            return True
        
        if iteration >= 20:  # Force completion at high iteration count
            return True
        
        # Check response length - very short responses might indicate completion
        if len(response.strip()) < 100 and iteration > 5:
            return True
        
        return False
    
    def _check_server_health(self) -> bool:
        """Check if server is available with retry."""
        for attempt in range(3):
            try:
                response = requests.get(f"{self.server_url}/health", timeout=10)
                if response.status_code == 200:
                    return True
            except Exception as e:
                if attempt < 2:  # Retry
                    time.sleep(2)
                    continue
                print(f"Server health check failed after {attempt + 1} attempts: {e}")
        return False


class EnhancedAgentOrchestrator:
    """Enhanced orchestrator with better resource management."""
    
    def __init__(self):
        self.agents: Dict[int, BaseAgent] = {}
        self.callbacks: List[Callable] = []
        self.max_concurrent_agents = 3  # Reduced to prevent resource exhaustion
        self.agent_cleanup_threshold = 20
    
    def add_callback(self, callback: Callable):
        """Add callback for agent updates."""
        self.callbacks.append(callback)
    
    def create_agent(
        self,
        task_type: str,
        task_params: Dict[str, Any],
        tools: Dict[str, Any],
        **kwargs
    ) -> StreamingGenericAgent:
        """Create enhanced streaming agent."""
        
        # Check concurrent agents limit
        running_agents = self.get_running_agents()
        if len(running_agents) >= self.max_concurrent_agents:
            raise Exception(f"Maximum concurrent agents ({self.max_concurrent_agents}) reached. Please wait for completion.")
        
        # Cleanup old agents if needed
        if len(self.agents) > self.agent_cleanup_threshold:
            self.cleanup_old_agents(self.agent_cleanup_threshold // 2)
        
        agent = StreamingGenericAgent(
            task_type=task_type,
            task_params=task_params,
            tools=tools,
            **kwargs
        )
        
        self.agents[agent.id] = agent
        agent.add_callback(self._on_agent_update)
        
        print(f"Created streaming agent {agent.id}: {agent.name} for {task_type}")
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
        print(f"Stopped {len(self.get_running_agents())} running agents")
    
    def cleanup_old_agents(self, keep_count: int = 10):
        """Clean up old agents to prevent memory issues."""
        if len(self.agents) > keep_count:
            # Keep most recent agents
            sorted_agents = sorted(self.agents.items(), key=lambda x: x[1].id, reverse=True)
            agents_to_keep = dict(sorted_agents[:keep_count])
            removed_count = len(self.agents) - len(agents_to_keep)
            self.agents = agents_to_keep
            print(f"Cleaned up {removed_count} old agents")
    
    def get_agent_statistics(self) -> Dict[str, int]:
        """Get statistics about agents."""
        return {
            "total": len(self.agents),
            "running": len(self.get_running_agents()),
            "completed": len(self.get_completed_agents()),
            "failed": len(self.get_failed_agents()),
            "pending": len([a for a in self.agents.values() if a.status == AgentStatus.PENDING])
        }
    
    def _on_agent_update(self, agent: BaseAgent):
        """Handle agent status updates."""
        print(f"Agent {agent.id} ({agent.name}) status: {agent.status}")
        
        # Notify callbacks
        for callback in self.callbacks:
            try:
                callback(agent)
            except Exception as e:
                print(f"Error in orchestrator callback: {e}")


class StreamingAgentRegistry:
    """Enhanced registry for streaming agent creation."""
    
    def __init__(self):
        self.orchestrator = EnhancedAgentOrchestrator()
    
    def create_agent(
        self,
        task_type: str,
        task_params: Dict[str, Any],
        tools: Dict[str, Any] = None,
        **kwargs
    ) -> StreamingGenericAgent:
        """Create a new streaming agent."""
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
agent_registry = StreamingAgentRegistry()