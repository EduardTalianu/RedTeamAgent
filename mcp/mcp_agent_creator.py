# mcp_agent_creator.py
import sys
import os
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple
# Add current directory to path to import mcp_base
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_base import MCPTool
# Add parent directory to path to import agents
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class McpAgentCreator(MCPTool):
    """MCP tool for creating agents in the task orchestrator."""
    
    def __init__(self, task_orchestrator=None, tools=None):
        super().__init__()
        self.task_orchestrator = task_orchestrator
        self.tools = tools  # Store the tools dictionary
        self.friendly_name = "Agent Creator"
        # Get the orchestrator's model if available
        self.orchestrator_model = getattr(task_orchestrator, 'current_model', None) if task_orchestrator else None
    
    def get_description(self) -> str:
        return "Create specialized agents to perform tasks in the task orchestrator."
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_xml": {
                    "type": "string",
                    "description": "XML string defining the agent to create. Example: <agent><type>web_search</type><name>Search Agent</name><description>Search for information</description><parameters><query>search query</query></parameters></agent>"
                }
            },
            "required": ["agent_xml"]
        }
    
    def get_capabilities(self) -> List[str]:
        return [
            "agent_creation",
            "task_orchestration"
        ]
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text is requesting agent creation."""
        # Look for XML agent blocks in code blocks
        xml_blocks = []
        
        # Check for code block wrapped XML
        import re
        code_blocks = re.findall(r'```xml\s*(<agent>.*?</agent>)\s*```', text, re.DOTALL)
        xml_blocks.extend(code_blocks)
        
        # Check for direct XML without code blocks
        direct_xml = re.findall(r'(<agent>.*?</agent>)', text, re.DOTALL)
        xml_blocks.extend(direct_xml)
        
        if xml_blocks:
            return {"agent_xml": xml_blocks[0]}  # Return the first agent found
        
        return None
    
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute agent creation."""
        agent_xml = params.get("agent_xml", "")
        if not agent_xml:
            return "Error: No agent XML provided"
        try:
            root = ET.fromstring(agent_xml)
            agent_type   = root.findtext('type')
            name         = root.findtext('name')
            description  = root.findtext('description')
            # NEW: optional orchestrator context
            orch_prompt  = root.findtext('orchestrator_prompt') or ""
            parameters = {}
            params_elem = root.find('parameters')
            if params_elem is not None:
                for param in params_elem:
                    parameters[param.tag] = param.text
            agent = self._create_agent(
                agent_type,
                name,
                description,
                parameters,
                orchestrator_prompt=orch_prompt
            )
            if agent:
                agent.execute()
                return f"Agent '{name}' created and executed successfully. Agent ID: {agent.id}"
            else:
                return f"Error: Failed to create agent of type '{agent_type}'"
        except ET.ParseError as e:
            return f"Error parsing agent XML: {str(e)}"
        except Exception as e:
            # Print the full exception for debugging
            import traceback
            print(f"DEBUG: Exception in agent creation: {str(e)}")
            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            return f"Error creating agent: {str(e)}"
    
    def _create_agent(
        self,
        agent_type: str,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        **kwargs
    ) -> Optional["GenericAgent"]:
        """Create a generic agent of the specified type."""
        if not self.task_orchestrator:
            raise Exception("Task orchestrator not available")
        
        if not self.tools:
            raise Exception("Tools not available")
        
        # Import the GenericAgent class
        from agents.task_agents import GenericAgent
        
        # Create the generic agent with the orchestrator's model
        agent = GenericAgent(
            task_type=agent_type,
            task_params=parameters,
            tools=self.tools,
            name=name,
            description=description,
            trm=self.task_orchestrator.trm,
            # NEW: give the agent its initial prompt / context
            orchestrator_prompt=kwargs.get("orchestrator_prompt", ""),
            server_url="http://127.0.0.1:11436",
            # NEW: pass the orchestrator's model
            orchestrator_model=self.orchestrator_model
        )
        
        # Add to task orchestrator
        self.task_orchestrator.add_agent(agent)
        
        return agent
    
    def get_system_prompt(self) -> str:
        return (
            f"You have access to {self.name}. {self.description} "
            "When you need to create a specialized agent to perform a task, use the following XML format:\n"
            "```xml\n"
            "<agent>\n"
            "  <type>web_search|data_analysis|content_creation|calculation</type>\n"
            "  <name>Descriptive agent name</name>\n"
            "  <description>Detailed description of what the agent should do</description>\n"
            "  <parameters>\n"
            "    <query>Search query (for web_search)</query>\n"
            "    <data>Input data (for data_analysis)</data>\n"
            "    <analysis_type>Type of analysis (for data_analysis)</analysis_type>\n"
            "    <content_type>Type of content to create (for content_creation)</content_type>\n"
            "    <topic>Topic for content creation (for content_creation)</topic>\n"
            "    <expression>Mathematical expression (for calculation)</expression>\n"
            "  </parameters>\n"
            "</agent>\n"
            "```\n\n"
            "IMPORTANT: The agents you create will use the same model as the orchestrator to ensure consistency. "
            "For Groq, please use 'groq-gemma2-9b-it'. "
            "For example, a web_search agent will use the MCP web search tool, and a data_analysis agent "
            "with analysis_type=dns will use the MCP curl tool for DNS lookups.\n\n"
            "Create only ONE agent at a time. Wait for the agent to complete before creating another agent.\n\n"
            "Examples:\n"
            "1. To create a web search agent:\n"
            "```xml\n"
            "<agent>\n"
            "  <type>web_search</type>\n"
            "  <name>Passive Reconnaissance Agent</name>\n"
            "  <description>Gather information about a website</description>\n"
            "  <parameters>\n"
            "    <query>site:example.com</query>\n"
            "  </parameters>\n"
            "</agent>\n"
            "```\n\n"
            "2. To create a DNS analysis agent:\n"
            "```xml\n"
            "<agent>\n"
            "  <type>data_analysis</type>\n"
            "  <name>DNS Analysis Agent</name>\n"
            "  <description>Analyze DNS records for a domain</description>\n"
            "  <parameters>\n"
            "    <data>example.com</data>\n"
            "    <analysis_type>dns</analysis_type>\n"
            "  </parameters>\n"
            "</agent>\n"
            "```\n\n"
            "The agent will be created and executed automatically. "
            "You will receive the agent's results when it completes. "
            "Use this tool when you need to delegate complex tasks to specialized agents."
        )