# mcp_agent_creator.py - Enhanced version with better task planning and tool awareness
import sys
import os
import xml.etree.ElementTree as ET
import re
from typing import Dict, Any, List, Optional

# Add current directory to path to import mcp_base
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_base import MCPTool

# Add parent directory to path to import agents
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class McpAgentCreator(MCPTool):
    """Enhanced MCP tool for creating specialized agents with better task planning."""
    
    def __init__(self, task_orchestrator=None, tools=None):
        super().__init__()
        self.task_orchestrator = task_orchestrator
        self.tools = tools or {}
        self.friendly_name = "Agent Creator"
        
        # Task type definitions with better descriptions
        self.task_types = {
            "web_search": {
                "description": "Search the web for information, perform OSINT, domain research",
                "required_params": ["query"],
                "optional_params": ["num_results", "search_type"],
                "recommended_tools": ["mcp_websearch"],
                "example_queries": [
                    "site:target.com filetype:pdf",
                    "\"target.com\" security vulnerabilities",
                    "target.com subdomain enumeration"
                ]
            },
            "data_analysis": {
                "description": "Analyze domains, URLs, perform technical reconnaissance",
                "required_params": ["data"],
                "optional_params": ["analysis_type"],
                "recommended_tools": ["mcp_curl"],
                "example_data": [
                    "https://target.com",
                    "target.com",
                    "192.168.1.1"
                ]
            },
            "content_creation": {
                "description": "Create reports, documentation, analysis summaries",
                "required_params": ["topic"],
                "optional_params": ["content_type", "format"],
                "recommended_tools": ["mcp_websearch"],
                "example_topics": [
                    "Security assessment report for target.com",
                    "Technical analysis summary",
                    "Reconnaissance findings compilation"
                ]
            },
            "calculation": {
                "description": "Perform calculations, data processing, numerical analysis",
                "required_params": ["expression"],
                "optional_params": ["precision"],
                "recommended_tools": [],
                "example_expressions": [
                    "subnet calculations",
                    "statistical analysis",
                    "risk scoring"
                ]
            }
        }
    
    def set_tools(self, tools: Dict[str, Any]):
        """Update the tools dictionary after initialization."""
        self.tools = tools or {}
        print(f"DEBUG: Agent Creator tools updated: {list(self.tools.keys())}")
    
    def get_description(self) -> str:
        return "Create specialized agents with proper task planning and tool integration for complex operations."
    
    def detect_request(self, text: str) -> Optional[Dict[str, Any]]:
        """Enhanced detection for agent creation requests."""
        # Look for agent XML blocks with various formats
        patterns = [
            r'```xml\s*(<agent>.*?</agent>)\s*```',  # In code block
            r'(<agent>.*?</agent>)'  # Direct XML
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return {"agent_xml": match.group(1)}
        
        # Look for explicit agent creation requests without XML
        creation_patterns = [
            r'create.*?agent.*?to\s+(.+?)(?:\n|$|\.|,)',
            r'need.*?agent.*?for\s+(.+?)(?:\n|$|\.|,)',
            r'agent.*?should\s+(.+?)(?:\n|$|\.|,)',
        ]
        
        for pattern in creation_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                task_description = match.group(1).strip()
                # Try to infer task type and create XML
                suggested_xml = self._suggest_agent_xml(task_description)
                if suggested_xml:
                    return {"agent_xml": suggested_xml}
        
        return None
    
    def _suggest_agent_xml(self, task_description: str) -> Optional[str]:
        """Suggest agent XML based on task description."""
        task_lower = task_description.lower()
        
        # Determine task type based on keywords
        if any(word in task_lower for word in ['search', 'find', 'research', 'osint', 'recon']):
            task_type = "web_search"
            query = task_description
        elif any(word in task_lower for word in ['analyze', 'curl', 'http', 'domain', 'url']):
            task_type = "data_analysis"
            # Try to extract domain/URL from description
            url_match = re.search(r'(https?://[^\s]+|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', task_description)
            data = url_match.group(1) if url_match else task_description
        elif any(word in task_lower for word in ['create', 'write', 'report', 'document']):
            task_type = "content_creation"
            topic = task_description
        else:
            return None  # Can't determine task type
        
        # Create suggested XML
        if task_type == "web_search":
            return f"""<agent>
  <type>web_search</type>
  <name>Research Agent</name>
  <description>Research and gather information about the specified topic</description>
  <parameters>
    <query>{query}</query>
  </parameters>
</agent>"""
        elif task_type == "data_analysis":
            return f"""<agent>
  <type>data_analysis</type>
  <name>Analysis Agent</name>
  <description>Analyze the specified target or data</description>
  <parameters>
    <data>{data}</data>
    <analysis_type>technical</analysis_type>
  </parameters>
</agent>"""
        elif task_type == "content_creation":
            return f"""<agent>
  <type>content_creation</type>
  <name>Content Agent</name>
  <description>Create content about the specified topic</description>
  <parameters>
    <topic>{topic}</topic>
    <content_type>report</content_type>
  </parameters>
</agent>"""
        
        return None
    
    def execute(self, params: Dict[str, Any]) -> str:
        """Execute enhanced agent creation."""
        agent_xml = params.get("agent_xml", "")
        if not agent_xml:
            return "Error: No agent XML provided"
        
        try:
            # Parse XML
            root = ET.fromstring(agent_xml)
            
            # Extract agent parameters with better validation
            agent_type = root.findtext('type', '').strip()
            name = root.findtext('name', '').strip()
            description = root.findtext('description', '').strip()
            
            # Extract task parameters
            task_params = {}
            params_elem = root.find('parameters')
            if params_elem is not None:
                for param in params_elem:
                    if param.text:
                        task_params[param.tag] = param.text.strip()
            
            # Validate and enhance parameters
            validation_result = self._validate_and_enhance_agent_params(
                agent_type, name, description, task_params
            )
            
            if validation_result["error"]:
                return f"Error: {validation_result['error']}"
            
            # Use validated parameters
            agent_type = validation_result["agent_type"]
            name = validation_result["name"]
            description = validation_result["description"]
            task_params = validation_result["task_params"]
            
            # Create the agent with enhanced tools
            agent = self._create_enhanced_agent(agent_type, name, description, task_params)
            
            if agent:
                # Start agent execution
                agent.execute()
                
                # Provide detailed creation summary
                summary = self._create_agent_summary(agent, task_params)
                return summary
            else:
                return f"Error: Failed to create agent of type '{agent_type}'"
                
        except ET.ParseError as e:
            return f"Error parsing agent XML: {str(e)}\n\nPlease use the correct XML format as shown in the examples."
        except Exception as e:
            return f"Error creating agent: {str(e)}"
    
    def _validate_and_enhance_agent_params(
        self, 
        agent_type: str, 
        name: str, 
        description: str, 
        task_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and enhance agent parameters."""
        
        # Validate agent type
        if not agent_type or agent_type not in self.task_types:
            return {"error": f"Invalid or missing agent type. Must be one of: {', '.join(self.task_types.keys())}"}
        
        task_def = self.task_types[agent_type]
        
        # Check required parameters
        for required_param in task_def["required_params"]:
            if required_param not in task_params or not task_params[required_param]:
                return {"error": f"Missing required parameter '{required_param}' for {agent_type} agent"}
        
        # Generate better name if not provided
        if not name:
            name = f"{agent_type.replace('_', ' ').title()} Agent"
        
        # Generate better description if not provided
        if not description:
            if agent_type == "web_search":
                query = task_params.get("query", "specified topic")
                description = f"Search for information about: {query}"
            elif agent_type == "data_analysis":
                data = task_params.get("data", "provided data")
                description = f"Analyze and investigate: {data}"
            elif agent_type == "content_creation":
                topic = task_params.get("topic", "specified topic")
                description = f"Create content about: {topic}"
            else:
                description = task_def["description"]
        
        # Enhance task parameters with intelligent defaults
        enhanced_params = self._enhance_task_params(agent_type, task_params)
        
        return {
            "error": None,
            "agent_type": agent_type,
            "name": name,
            "description": description,
            "task_params": enhanced_params
        }
    
    def _enhance_task_params(self, agent_type: str, task_params: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance task parameters with intelligent defaults and suggestions."""
        enhanced = task_params.copy()
        
        if agent_type == "web_search":
            query = enhanced.get("query", "")
            
            # Enhance search queries for better results
            if any(domain_indicator in query.lower() for domain_indicator in ['.com', '.org', '.net', '.ro']):
                # Looks like a domain - enhance for reconnaissance
                if "recon" in query.lower() or "passive" in query.lower():
                    base_domain = re.search(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', query)
                    if base_domain:
                        domain = base_domain.group(1)
                        enhanced["search_suggestions"] = [
                            f'site:{domain}',
                            f'"{domain}" security',
                            f'"{domain}" subdomains',
                            f'"{domain}" technology stack'
                        ]
            
        elif agent_type == "data_analysis":
            data = enhanced.get("data", "")
            
            # Determine analysis type if not specified
            if not enhanced.get("analysis_type"):
                if re.match(r'^https?://', data):
                    enhanced["analysis_type"] = "web_analysis"
                elif re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', data):
                    enhanced["analysis_type"] = "domain_analysis"
                elif re.match(r'^\d+\.\d+\.\d+\.\d+$', data):
                    enhanced["analysis_type"] = "ip_analysis"
                else:
                    enhanced["analysis_type"] = "general_analysis"
        
        return enhanced
    
    def _create_enhanced_agent(
        self, 
        agent_type: str, 
        name: str, 
        description: str, 
        task_params: Dict[str, Any]
    ):
        """Create enhanced agent with proper tool selection."""
        if not self.task_orchestrator:
            raise Exception("Task orchestrator not available")
        
        # Import agent registry
        from agents import agent_registry
        
        # Get current model from orchestrator if available
        model = "groq-gemma2-9b-it"  # Default
        if hasattr(self.task_orchestrator, 'model_var'):
            model = self.task_orchestrator.model_var.get() or model
        
        # Select relevant tools for this agent type
        relevant_tools = self._select_relevant_tools(agent_type)
        
        # Create agent using enhanced system
        agent = agent_registry.create_agent(
            task_type=agent_type,
            task_params=task_params,
            tools=relevant_tools,
            name=name,
            description=description,
            model=model,
            server_url=getattr(self.task_orchestrator, 'server_url', 'http://127.0.0.1:11436')
        )
        
        return agent
    
    def _select_relevant_tools(self, agent_type: str) -> Dict[str, Any]:
        """Select relevant tools for the agent type."""
        task_def = self.task_types.get(agent_type, {})
        recommended_tools = task_def.get("recommended_tools", [])
        
        # Start with all enabled tools
        relevant_tools = {}
        for tool_name, tool in self.tools.items():
            if getattr(tool, 'enabled', True) and tool_name != 'mcp_agent_creator':
                # Include tool if it's recommended or if no specific recommendations
                if not recommended_tools or tool_name in recommended_tools:
                    relevant_tools[tool_name] = tool
        
        # Always include websearch and curl as they're fundamental
        if not relevant_tools:
            for tool_name in ['mcp_websearch', 'mcp_curl']:
                if tool_name in self.tools:
                    relevant_tools[tool_name] = self.tools[tool_name]
        
        print(f"Selected tools for {agent_type} agent: {list(relevant_tools.keys())}")
        return relevant_tools
    
    def _create_agent_summary(self, agent, task_params: Dict[str, Any]) -> str:
        """Create detailed agent creation summary."""
        summary_lines = [
            f"✓ Agent '{agent.name}' created successfully",
            f"  • Agent ID: {agent.id}",
            f"  • Task Type: {agent.task_type}",
            f"  • Description: {agent.description}",
        ]
        
        if task_params:
            summary_lines.append("  • Parameters:")
            for key, value in task_params.items():
                if key == "search_suggestions":
                    summary_lines.append(f"    - Suggested searches: {', '.join(value)}")
                else:
                    summary_lines.append(f"    - {key}: {value}")
        
        # List available tools
        tools_available = getattr(agent, 'tools', {})
        if tools_available:
            tool_names = [getattr(tool, 'friendly_name', name) for name, tool in tools_available.items()]
            summary_lines.append(f"  • Available Tools: {', '.join(tool_names)}")
        
        summary_lines.extend([
            "",
            "The agent is now working on the task with its own independent conversation context.",
            "It will use the available tools systematically to complete the assigned work.",
            "Please wait for the agent to finish and provide results..."
        ])
        
        return "\n".join(summary_lines)
    
    def get_system_prompt(self) -> str:
        """Enhanced system prompt with better examples and guidance."""
        
        # Build available tools list
        tool_descriptions = []
        for tool_name, tool in self.tools.items():
            if tool_name != 'mcp_agent_creator' and getattr(tool, 'enabled', True):
                display_name = getattr(tool, 'friendly_name', tool_name)
                description = getattr(tool, 'description', 'No description')
                tool_descriptions.append(f"  • {display_name}: {description}")
        
        tools_text = "\n".join(tool_descriptions) if tool_descriptions else "  • No additional tools available"
        
        # Build task types documentation
        task_types_doc = []
        for task_type, info in self.task_types.items():
            task_types_doc.append(f"• {task_type}: {info['description']}")
            task_types_doc.append(f"  Required: {', '.join(info['required_params'])}")
            if info['optional_params']:
                task_types_doc.append(f"  Optional: {', '.join(info['optional_params'])}")
        
        task_types_text = "\n".join(task_types_doc)
        
        return f"""You have access to the {self.friendly_name}. {self.description}

AVAILABLE TOOLS FOR AGENTS:
{tools_text}

SUPPORTED AGENT TYPES:
{task_types_text}

When you need to create a specialized agent, use this exact XML format:

PASSIVE RECONNAISSANCE EXAMPLE:
```xml
<agent>
  <type>web_search</type>
  <name>Passive Recon Agent</name>
  <description>Perform passive reconnaissance on bcr.ro domain</description>
  <parameters>
    <query>site:bcr.ro OR "bcr.ro" filetype:pdf OR filetype:doc</query>
  </parameters>
</agent>
```

TECHNICAL ANALYSIS EXAMPLE:
```xml
<agent>
  <type>data_analysis</type>
  <name>HTTP Analysis Agent</name>
  <description>Analyze HTTP headers and response from bcr.ro</description>
  <parameters>
    <data>https://bcr.ro</data>
    <analysis_type>web_analysis</analysis_type>
  </parameters>
</agent>
```

CONTENT CREATION EXAMPLE:
```xml
<agent>
  <type>content_creation</type>
  <name>Report Generator</name>
  <description>Create comprehensive reconnaissance report</description>
  <parameters>
    <topic>BCR.ro security assessment and reconnaissance findings</topic>
    <content_type>security_report</content_type>
  </parameters>
</agent>
```

IMPORTANT FEATURES:
✓ Each agent has completely independent conversation context
✓ Agents receive proper tool instructions and access
✓ Systematic task execution with multiple tool usage
✓ Comprehensive result analysis and reporting
✓ All results saved to results/agents/ directory

CREATE AGENTS FOR COMPLEX TASKS:
1. Break down complex requests into specific agent tasks
2. Use multiple agents for comprehensive analysis
3. Each agent specializes in one aspect of the work
4. Wait for agent completion before creating more

The Agent Creator will validate parameters, select appropriate tools, and provide detailed status updates."""