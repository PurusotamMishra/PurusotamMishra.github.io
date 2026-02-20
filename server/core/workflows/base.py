from abc import ABC, abstractmethod
from langgraph.graph import StateGraph

class BaseWorkflow(ABC):
    name: str
    description: str
    
    @abstractmethod
    def build_graph(self) -> StateGraph:
        """Build and return the LangGraph StateGraph."""
        pass

    @abstractmethod
    def get_initial_state(self, input_data: dict) -> dict:
        """Convert input to initial workflow state."""
        pass