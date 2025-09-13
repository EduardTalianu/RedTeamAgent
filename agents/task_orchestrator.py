"""
Core task orchestration components for managing agent relationships and hierarchies.
"""

import uuid
from enum import auto, Enum
from typing import List, Dict, Optional
import matplotlib.pyplot as plt
import networkx as nx

class Direction(Enum):
    """Directions for task relationships."""
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()

def get_reverse_direction(direction: Direction) -> Optional[Direction]:
    """Get the reverse direction for a given direction."""
    if direction == Direction.UP:
        return Direction.DOWN
    elif direction == Direction.DOWN:
        return Direction.UP
    elif direction == Direction.LEFT:
        return Direction.RIGHT
    elif direction == Direction.RIGHT:
        return Direction.LEFT
    else:
        return None

class Node:
    """Base class for nodes in the task hierarchy."""
    def __init__(self):
        unique_id = uuid.uuid4().int
        self.id = unique_id & 0xFFFFFFFF

class TaskRelationManager:
    """Manages relationships between tasks/agents in a hierarchical structure."""
    
    def __init__(self):
        self.task_registry = {}
        self.relationships = {}

    def _get_task_from_id(self, task_id: int) -> Optional[Node]:
        """Get task object from ID."""
        if task_id in self.task_registry:
            return self.task_registry[task_id]
        return None

    def _get_task_id(self, task: Node) -> Optional[int]:
        """Get task ID from task object."""
        if task:
            task_id = task.id
            if task_id not in self.task_registry:
                self.task_registry[task_id] = task
            return task_id
        return None

    def add_task(self, task: Node) -> int:
        """Register a new task."""
        task_id = self._get_task_id(task)
        if task_id not in self.relationships:
            self.relationships[task_id] = {
                Direction.UP: None,
                Direction.DOWN: None,
                Direction.LEFT: None,
                Direction.RIGHT: None
            }
        return task_id

    def set_relationship(self, from_task: Node, direction: Direction, to_task: Node = None):
        """Set a relationship between two tasks."""
        from_id = self._get_task_id(from_task)
        to_id = self._get_task_id(to_task) if to_task else None

        if from_id not in self.relationships:
            self.add_task(from_task)
        if to_task and to_id not in self.relationships:
            self.add_task(to_task)

        self.relationships[from_id][direction] = to_id
        if to_id is not None:
            reverse_dir = get_reverse_direction(direction)
            self.relationships[to_id][reverse_dir] = from_id

    def get_neighbors(self, task: Node) -> Dict[Direction, Optional[int]]:
        """Get all neighbors of a task."""
        task_id = self._get_task_id(task)
        return self.relationships.get(task_id, {})

    def get_direction_neighbors(self, task: Node, direction: Direction) -> Optional[int]:
        """Get neighbor in a specific direction."""
        task_id = self._get_task_id(task)
        return self.relationships.get(task_id, {}).get(direction)

    def get_task_chain(self, start_task: Node, direction: Direction) -> List[int]:
        """Get a chain of tasks in a specific direction."""
        chain = []
        current_id = self._get_task_id(start_task)
        while current_id:
            chain.append(current_id)
            current_id = self.relationships.get(current_id, {}).get(direction)
        return chain

    def add_sub_tasks(self, current_task: Node, sub_tasks: List[Node]):
        """Add subtasks to a task."""
        if not sub_tasks:
            return
            
        # Find available direction (DOWN or RIGHT)
        available_direction = None
        for direction in [Direction.DOWN, Direction.RIGHT]:
            if not self.get_direction_neighbors(current_task, direction):
                available_direction = direction
                break
        
        if available_direction:
            # Set relationships for each subtask
            for i, subtask in enumerate(sub_tasks):
                if i == 0:
                    # First subtask connects to parent
                    self.set_relationship(current_task, available_direction, subtask)
                else:
                    # Subsequent subtasks connect to previous subtask
                    self.set_relationship(sub_tasks[i-1], available_direction, subtask)

    def remove_node(self, task: Node):
        """Remove a task and its relationships."""
        task_id = self._get_task_id(task)
        if task_id not in self.relationships:
            return
            
        # Remove relationships
        for direction, neighbor_id in self.relationships[task_id].items():
            if neighbor_id is not None:
                reverse_dir = get_reverse_direction(direction)
                if neighbor_id in self.relationships:
                    self.relationships[neighbor_id][reverse_dir] = None
        
        # Remove from registry and relationships
        del self.relationships[task_id]
        if task_id in self.task_registry:
            del self.task_registry[task_id]

    def draw_graph(self, output_file: str = "task_graph.png") -> str:
        """Generate a visual graph of tasks using NetworkX and Matplotlib."""
        G = nx.DiGraph()
        
        # Add nodes
        for task_id in self.task_registry:
            task = self._get_task_from_id(task_id)
            label = f"Task {task_id}"
            if hasattr(task, 'name'):
                label = f"{task.name}"
            elif hasattr(task, 'abstract'):
                label = f"{task.abstract[:20]}..."
            G.add_node(task_id, label=label)
        
        # Add edges
        for task_id in self.task_registry:
            relations = self.relationships.get(task_id, {})
            for direction, neighbor_id in relations.items():
                if neighbor_id is not None:
                    G.add_edge(task_id, neighbor_id, direction=direction.name)
        
        # Draw the graph
        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(G, seed=42)
        nx.draw(G, pos, with_labels=True, node_size=2000, node_color='skyblue', 
                font_size=10, font_weight='bold', arrows=True)
        
        edge_labels = {(u, v): d['direction'] for u, v, d in G.edges(data=True)}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
        
        plt.title("Task Relationship Graph")
        plt.savefig(output_file)
        plt.close()
        return output_file