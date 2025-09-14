# mcp_agent_creator.py - Simplified for generic agents

import sys
import os
import xml.etree.ElementTree as ET
import re
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_base import MCPTool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class McpAgentCreator(MCPTool):
    """Simplified agent creator for generic agents - only creates agents with instructions."""
    
    def __init__(self, task_orchestrator=None, tools=None):
        super().__init__()
        self.task_orchestrator = task_orchestrator
        self.tools = tools or {}
        self.friendly_name = "Agent Creator"
    
    def set_tools(self, tools: Dict[str, Any]):
        """Update the tools dictionary."""
        self.tools = tools or {}
        print(f"DEBUG: Agent Creator tools updated: {list(self.tools.keys())}")
    
    def get_description(self) -> str:
        return "Create generic agents with specific task instructions from the orchestrator."
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect agent creation requests - now looks for any agent XML."""
        patterns = [
            r'```xml\s*(<agent>.*?</agent>)\s*```',
            r'(<agent>.*?</agent>)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return {"agent_xml": match.group(1)}
        
        return None
    
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute generic agent creation."""
        if not self.task_orchestrator:
            return "Error: Task orchestrator not available"
        
        agent_xml = params.get("agent_xml", "")
        if not agent_xml:
            return "Error: No agent XML provided"
        
        try:
            # Parse XML
            root = ET.fromstring(agent_xml)
            
            # Extract basic info - check both 'name' and 'n' elements
            name = root.findtext('name', '').strip() or root.findtext('n', '').strip()
            description = root.findtext('description', '').strip()
            
            # Extract instructions - this is the key part
            instructions_elem = root.find('instructions')
            if instructions_elem is not None:
                instructions = instructions_elem.text.strip() if instructions_elem.text else ""
            else:
                # If no explicit instructions, build from the XML content
                instructions = self._build_instructions_from_xml(root)
            
            # Validate required fields
            if not name:
                return "Error: Agent name is required in either <name> or <n> element"
            
            if not instructions:
                return "Error: Agent instructions are required in <instructions> element or as task parameters"
            
            # Generate description if missing
            if not description:
                description = f"Generic agent to execute: {instructions[:100]}..."
            
            # Create the generic agent
            agent = self._create_generic_agent(name, description, instructions)
            
            if agent:
                # Start agent execution
                agent.execute()
                return self._create_agent_summary(agent, instructions)
            else:
                return "Error: Failed to create generic agent"
                
        except ET.ParseError as e:
            return f"Error parsing agent XML: {str(e)}\n\nPlease use correct XML format with <agent><name>...</name><instructions>...</instructions></agent> or <agent><n>...</n><instructions>...</instructions></agent>"
        except Exception as e:
            return f"Error creating agent: {str(e)}"
    
    def _build_instructions_from_xml(self, root) -> str:
        """Build instructions from XML if not explicitly provided."""
        # Try to extract meaningful instructions from various XML structures
        
        # Check for task element
        task_elem = root.find('task')
        if task_elem is not None and task_elem.text:
            return task_elem.text.strip()
        
        # Check for objective element
        objective_elem = root.find('objective')
        if objective_elem is not None and objective_elem.text:
            return objective_elem.text.strip()
        
        # Check for parameters and build instructions
        params_elem = root.find('parameters')
        if params_elem is not None:
            param_text = []
            for param in params_elem:
                if param.text:
                    param_text.append(f"{param.tag}: {param.text.strip()}")
            
            if param_text:
                base_instruction = f"Complete the following task with these parameters:\n" + "\n".join(param_text)
                return base_instruction
        
        # Fallback to description
        description = root.findtext('description', '').strip()
        if description:
            return f"Task: {description}"
        
        return ""
    
    def _create_generic_agent(self, name: str, description: str, instructions: str):
        """Create a generic agent with instructions."""
        if not self.task_orchestrator:
            raise Exception("Task orchestrator not available")
        
        # Import agent registry
        from agents import agent_registry
        
        # Get current model from orchestrator
        if hasattr(self.task_orchestrator, 'model_var'):
            model = self.task_orchestrator.model_var.get()
        else:
            model = "moonshot-v1-32k"
        
        # Select relevant tools (exclude agent creator itself)
        relevant_tools = {k: v for k, v in self.tools.items() if k != 'mcp_agent_creator' and getattr(v, 'enabled', True)}
        
        # Create generic agent
        agent = agent_registry.create_agent(
            name=name,
            description=description,
            instructions=instructions,
            tools=relevant_tools,
            model=model
        )
        
        return agent
    
    def _create_agent_summary(self, agent, instructions: str) -> str:
        """Create agent creation summary."""
        summary_lines = [
            f"✓ Generic Agent '{agent.name}' created successfully",
            f"  • Agent ID: {agent.id}",
            f"  • Description: {agent.description}",
            f"  • Instructions: {instructions[:200]}{'...' if len(instructions) > 200 else ''}",
        ]
        
        # List available tools
        tools_available = getattr(agent, 'tools', {})
        if tools_available:
            tool_names = [getattr(tool, 'friendly_name', name) for name, tool in tools_available.items()]
            summary_lines.append(f"  • Available Tools: {', '.join(tool_names)}")
        
        summary_lines.extend([
            "",
            "The agent is now executing the task with complete autonomy.",
            "It will use available tools as needed to complete the instructions.",
            "Please wait for the agent to finish and provide results..."
        ])
        
        return "\n".join(summary_lines)
    
    def get_system_prompt(self) -> str:
        """System prompt for generic agent creation."""
        
        # Build available tools list
        tool_descriptions = []
        for tool_name, tool in self.tools.items():
            if tool_name != 'mcp_agent_creator' and getattr(tool, 'enabled', True):
                display_name = getattr(tool, 'friendly_name', tool_name)
                description = getattr(tool, 'description', 'No description')
                tool_descriptions.append(f"  • {display_name}: {description}")
        
        tools_text = "\n".join(tool_descriptions) if tool_descriptions else "  • No additional tools available"
        
        return f"""You have access to the {self.friendly_name}. {self.description}

AVAILABLE TOOLS FOR AGENTS:
{tools_text}

SIMPLIFIED AGENT CREATION:
All agents are now generic and task-agnostic. The only difference is the instructions you provide.

CORRECT XML FORMAT:
```xml
<agent>
  <name>Descriptive Agent Name</name>
  <description>Brief description of what this agent will do</description>
  <instructions>
    Detailed step-by-step instructions for the agent to follow.
    
    Be specific about:
    - What information to gather
    - Which tools to use and how
    - What analysis to perform
    - What format for results
    - Any specific requirements
  </instructions>
</agent>
```

EXAMPLES:

IP RANGE ANALYSIS:
```xml
<agent>
  <name>BCR IP Range Analyst</name>
  <description>Analyze IP ranges and network information for bcr.ro</description>
  <instructions>
    Your task is to find detailed IP range and network information for bcr.ro domain.
    
    Steps to follow:
    1. Use the Web Search tool to search for "bcr.ro IP range netblock CIDR ASN"
    2. Search for "bcr.ro network information hosting provider"  
    3. Use the Curl tool to get HTTP headers from https://bcr.ro
    4. Analyze the results to identify:
       - IP addresses associated with bcr.ro
       - Network ranges (CIDR blocks)
       - ASN (Autonomous System Number)
       - Hosting provider information
       - Geographic location of servers
    5. Provide a comprehensive report with all findings
  </instructions>
</agent>
```

PASSIVE RECONNAISSANCE:
```xml
<agent>
  <name>Domain Reconnaissance Specialist</name>
  <description>Perform comprehensive passive reconnaissance on a target domain</description>
  <instructions>
    Conduct thorough passive reconnaissance on bcr.ro domain.
    
    Execute these tasks systematically:
    1. Search for general domain information using: "site:bcr.ro"
    2. Look for exposed files: "site:bcr.ro filetype:pdf OR filetype:doc OR filetype:txt"
    3. Search for security-related information: "bcr.ro security vulnerability breach"
    4. Find technology stack info: "bcr.ro technology stack framework"
    5. Use curl to analyze HTTP headers and response from https://bcr.ro
    6. Compile all findings into a structured reconnaissance report
    
    Focus on publicly available information only.
  </instructions>
</agent>
```

KEY PRINCIPLES:
✓ All agents are generic and multipurpose
✓ Specialization comes from your instructions
✓ Be specific and detailed in instructions
✓ Agents will use tools autonomously based on instructions
✓ Each agent works independently with full tool access

The agent will receive your instructions and execute them systematically using available tools."""