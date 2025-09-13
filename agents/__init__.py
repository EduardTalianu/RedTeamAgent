"""
Initialization file for the agents package.
"""

from .task_orchestrator import TaskRelationManager, Direction
from .agent_registry import AgentRegistry, agent_registry, register_default_agents
from .task_agents import BaseAgent, GenericAgent, AgentStatus

# Initialize default agents
register_default_agents()

# Export the main classes
__all__ = [
    'TaskRelationManager',
    'Direction',
    'AgentRegistry',
    'agent_registry',
    'BaseAgent',
    'GenericAgent',
    'AgentStatus'
]