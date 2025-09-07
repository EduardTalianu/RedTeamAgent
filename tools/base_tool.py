import re
import xml.etree.ElementTree as ET

class BaseTool:
    """Base class for all tools."""
    
    def __init__(self):
        self.name = self.__class__.__name__.lower()
        self.enabled = False
    
    def detect_request(self, text: str):
        """Detect if the AI is requesting to use this tool using XML format."""
        # Look for structured XML tool invocation
        xml_pattern = r'```xml\s*\n*\s*(<tool>.*?</tool>)\s*\n*\s*```'
        match = re.search(xml_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(1))
        
        # Fallback to simpler format without code block
        simple_pattern = r'(<tool>.*?</tool>)'
        match = re.search(simple_pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            return self._parse_tool_command(match.group(0))
        
        return None
    
    def _parse_tool_command(self, xml_str: str):
        """Parse an XML tool command and extract parameters."""
        try:
            root = ET.fromstring(xml_str)
            
            # Validate the tool name
            tool_name = root.find('name')
            if tool_name is None or tool_name.text.lower() != self.name:
                return None
                
            # Extract parameters
            parameters = {}
            params_elem = root.find('parameters')
            if params_elem is not None:
                for child in params_elem:
                    parameters[child.tag] = child.text
                
                return self._validate_parameters(parameters)
                
        except ET.ParseError:
            pass
        
        return None
    
    def _validate_parameters(self, parameters: dict):
        """Validate and extract parameters. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _validate_parameters")
    
    def execute(self, parameters):
        """Execute the tool with the given parameters. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement execute")
    
    def get_system_prompt(self) -> str:
        """Return the system prompt for this tool. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement get_system_prompt")