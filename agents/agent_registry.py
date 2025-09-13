"""
Registry for managing agent types and creation.
"""

from typing import Dict, Type, Any, Optional
from .task_agents import BaseAgent, GenericAgent
from .task_orchestrator import TaskRelationManager

class AgentRegistry:
    """Registry for agent types and creation."""
    
    def __init__(self):
        self._agent_types: Dict[str, Type[BaseAgent]] = {}
        self._default_trm: Optional[TaskRelationManager] = None
    
    def register_agent_type(self, name: str, agent_class: Type[BaseAgent]):
        """Register a new agent type."""
        self._agent_types[name] = agent_class
    
    def get_agent_type(self, name: str) -> Optional[Type[BaseAgent]]:
        """Get agent class by name."""
        return self._agent_types.get(name)
    
    def list_agent_types(self) -> list:
        """List all registered agent types."""
        return list(self._agent_types.keys())
    
    def set_default_trm(self, trm: TaskRelationManager):
        """Set default TaskRelationManager for agents."""
        self._default_trm = trm
    
    def create_agent(self, agent_type: str, **kwargs) -> Optional[BaseAgent]:
        """Create an agent instance of the specified type."""
        agent_class = self.get_agent_type(agent_type)
        if not agent_class:
            return None
        
        # Use default TRM if not provided
        if 'trm' not in kwargs and self._default_trm:
            kwargs['trm'] = self._default_trm
        
        return agent_class(**kwargs)
    
    def create_agent_from_config(self, config: Dict[str, Any]) -> Optional[BaseAgent]:
        """Create an agent from a configuration dictionary."""
        agent_type = config.get('type')
        if not agent_type:
            return None
        
        # Extract agent-specific parameters
        agent_params = {k: v for k, v in config.items() if k != 'type'}
        
        return self.create_agent(agent_type, **agent_params)

# Global registry instance
agent_registry = AgentRegistry()

# Register default agent types
def register_default_agents():
    """Register default agent types."""
    # Register the generic agent for all task types
    agent_registry.register_agent_type('generic', GenericAgent)

# Initialize default agents
register_default_agents()