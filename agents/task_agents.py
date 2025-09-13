"""
Agent classes for task execution.
"""

import threading
import time
import os
import json
import requests
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

# ------------------------------------------------------------------
#  GenericAgent – now with *private* memory per agent
# ------------------------------------------------------------------
class GenericAgent(BaseAgent):
    """
    Generic agent that executes tasks using MCP tools with proper MCP command formatting.
    Each instance carries its OWN conversation history (isolated context).
    """

    def __init__(
        self,
        task_type: str,
        task_params: Dict[str, Any],
        tools: Dict[str, Any],
        name: str = None,
        description: str = None,
        trm: TaskRelationManager = None,
        orchestrator_prompt: str = "",
        server_url: str = "http://127.0.0.1:11436",
        orchestrator_model: str = None  # NEW: Pass the orchestrator's model
    ):
        # --- defaults -------------------------------------------------
        if name is None:
            name = f"{task_type.replace('_', ' ').title()} Agent"
        if description is None:
            description = f"Agent to perform {task_type} task"
        # --- base init -------------------------------------------------
        super().__init__(name=name, description=description, trm=trm)
        self.task_type = task_type
        self.task_params = task_params
        self.tools = tools
        self.server_url = server_url
        # --- per-agent memory -----------------------------------------
        self.history: List[Dict[str, str]] = []
        self.orchestrator_prompt = orchestrator_prompt
        # --- Use orchestrator's model if provided --------------------
        self.orchestrator_model = orchestrator_model

    # ================================================================
    #  MAIN ENTRY – now starts a *private* chat loop
    # ================================================================
    def _execute_task(self, **kwargs) -> Dict[str, Any]:
        # 1.  Seed isolated history
        self.history = [
            {"role": "system", "content": self._build_agent_system_prompt()},
            {"role": "user",   "content": self.orchestrator_prompt or "Please perform your assigned task."}
        ]

        # 2.  Run the agent's own LLM loop
        final_answer = self._agent_chat_loop()

        # 3.  Return only the distilled result to the orchestrator
        return {
            "task_type": self.task_type,
            "agent_name": self.name,
            "final_answer": final_answer,
            "agent_history_length": len(self.history)
        }

    # ----------------------------------------------------------------
    #  Private helpers
    # ----------------------------------------------------------------
    def _build_agent_system_prompt(self) -> str:
        return (
            f"You are a specialised agent: {self.name}\n"
            f"Description: {self.description}\n"
            f"Task type: {self.task_type}\n"
            f"Parameters: {self.task_params}\n\n"
            "Carry out the task step-by-step. "
            "You may use any tools available to you. "
            "When you are finished, return ONLY the final answer or summary."
        )

    def _pick_model(self) -> str:
        # Use the orchestrator's model if available, otherwise fall back to default
        if self.orchestrator_model:
            return self.orchestrator_model
        
        # Use a valid default model instead of the decommissioned one
        return self.task_params.get("model", "groq-gemma2-9b-it")

    # ================================================================
    #  AGENT-CHAT-LOOP  (mirrors ChatTab but isolated)
    # ================================================================
    def _agent_chat_loop(self) -> str:
        """
        Keep chatting with the LLM (and tools) until the agent decides it is done.
        Returns the final textual answer.
        """
        # Check server health before starting
        if not self._check_server_health():
            raise Exception("API server is not healthy or not running")
        
        while True:
            # ---- send current private history -----------------------
            payload = {
                "model": self._pick_model(),
                "messages": self.history,
                "temperature": 0.7,
                "max_tokens": 1500,
                "stream": False
            }
            
            # Debug: Print the payload
            print(f"DEBUG: Sending payload to API: {json.dumps(payload, indent=2)}")
            
            # Retry mechanism
            max_retries = 3
            retry_delay = 1  # seconds
            
            for attempt in range(max_retries):
                try:
                    resp = requests.post(
                        f"{self.server_url}/api/chat", 
                        json=payload, 
                        timeout=60,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    # Debug: Print the response status and content
                    print(f"DEBUG: Response status: {resp.status_code}")
                    print(f"DEBUG: Response headers: {dict(resp.headers)}")
                    
                    # Print the first 1000 characters of the response content
                    response_text = resp.text
                    print(f"DEBUG: Response content (first 1000 chars): {response_text[:1000]}")
                    
                    # If status code is not 200, print more detailed error information
                    if resp.status_code != 200:
                        print(f"DEBUG: Full response content: {response_text}")
                        if attempt < max_retries - 1:
                            print(f"DEBUG: Retrying in {retry_delay} seconds...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            continue
                        else:
                            raise Exception(f"API returned status {resp.status_code}: {response_text}")
                    
                    # Parse the JSON response
                    try:
                        response_data = resp.json()
                        print(f"DEBUG: Parsed JSON keys: {list(response_data.keys())}")
                    except json.JSONDecodeError as e:
                        print(f"DEBUG: JSON decode error: {str(e)}")
                        print(f"DEBUG: Response text was: {response_text}")
                        raise Exception(f"Failed to decode JSON response: {str(e)}")
                    
                    # Try to extract the response content in different possible formats
                    ai_reply = None
                    
                    # Format 1: OpenAI-style with "choices"
                    if "choices" in response_data and len(response_data["choices"]) > 0:
                        choice = response_data["choices"][0]
                        if "message" in choice and "content" in choice["message"]:
                            ai_reply = choice["message"]["content"]
                        elif "text" in choice:
                            ai_reply = choice["text"]
                        elif "delta" in choice and "content" in choice["delta"]:
                            ai_reply = choice["delta"]["content"]
                    
                    # Format 2: Direct "message" field
                    elif "message" in response_data:
                        message = response_data["message"]
                        if isinstance(message, str):
                            ai_reply = message
                        elif isinstance(message, dict) and "content" in message:
                            ai_reply = message["content"]
                    
                    # Format 3: Direct "content" field
                    elif "content" in response_data:
                        ai_reply = response_data["content"]
                    
                    # Format 4: Direct "text" field
                    elif "text" in response_data:
                        ai_reply = response_data["text"]
                    
                    # Format 5: Direct "response" field
                    elif "response" in response_data:
                        ai_reply = response_data["response"]
                    
                    # Format 6: Direct "answer" field
                    elif "answer" in response_data:
                        ai_reply = response_data["answer"]
                    
                    # If we still don't have a reply, look for any string field
                    if ai_reply is None:
                        for key, value in response_data.items():
                            if isinstance(value, str) and len(value) > 10:  # Assume longer strings are more likely to be the response
                                ai_reply = value
                                print(f"DEBUG: Using field '{key}' as response content")
                                break
                    
                    if ai_reply is None:
                        print(f"DEBUG: Could not extract response from: {response_data}")
                        raise Exception(f"Could not extract response from API: {response_data}")
                    
                    print(f"DEBUG: Extracted response: {ai_reply[:100]}...")
                    
                    self.history.append({"role": "assistant", "content": ai_reply})

                    # ---- tool-use detection ---------------------------------
                    # Build a tiny registry on the fly (tools already injected)
                    tool_used = False
                    for tool_name, tool in self.tools.items():
                        if not tool.enabled:
                            continue
                        cmd = tool.detect_request(ai_reply)
                        if cmd:
                            tool_used = True
                            tool_out = tool.execute(cmd)
                            # Truncate oversized returns
                            if len(tool_out) > 2000:
                                tool_out = tool_out[:2000] + "\n[truncated]"
                            self.history.append({"role": "system", "content": f"Tool result:\n{tool_out}"})
                            break

                    if not tool_used:           # Natural stop – no more tools requested
                        return ai_reply
                        
                except requests.exceptions.RequestException as e:
                    print(f"DEBUG: Request exception: {str(e)}")
                    if attempt < max_retries - 1:
                        print(f"DEBUG: Retrying in {retry_delay} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        raise Exception(f"Connection to API server failed: {str(e)}")
                except Exception as e:
                    print(f"DEBUG: General exception: {str(e)}")
                    raise Exception(f"Error in agent chat loop: {str(e)}")

    def _check_server_health(self):
        """Check if the server is healthy."""
        try:
            resp = requests.get(f"{self.server_url}/health", timeout=5)
            return resp.status_code == 200
        except:
            return False
    
    # ----------------------------------------------------------------
    #  Legacy file-saving helper (unchanged behaviour)
    # ----------------------------------------------------------------
    def _save_results_to_file(self, result: Dict[str, Any]) -> str:
        results_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "agents")
        os.makedirs(results_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"agent_{self.id}_{timestamp}.json"
        filepath = os.path.join(results_dir, filename)

        start_str = None
        end_str   = None
        if self.start_time:
            start_str = datetime.fromtimestamp(self.start_time).isoformat()
        if self.end_time:
            end_str   = datetime.fromtimestamp(self.end_time).isoformat()

        data_to_save = {
            "agent_id": self.id,
            "agent_name": self.name,
            "agent_description": self.description,
            "task_type": self.task_type,
            "task_params": self.task_params,
            "status": self.status,
            "progress": self.progress,
            "start_time": start_str,
            "end_time": end_str,
            "execution_time": self.get_execution_time(),
            "result": result,
            "agent_history": self.history          # NEW: full private context saved
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        return filepath