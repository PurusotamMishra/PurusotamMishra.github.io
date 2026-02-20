from importlib import import_module
from typing import Dict, Type, List
from langgraph.graph.state import CompiledStateGraph
from core.workflows.base import BaseWorkflow

BASE_WORKFLOW_PATH = "core.workflows"


class WorkflowRegistry:
    workflows: Dict[str, Type[BaseWorkflow]] = {}
    compiled_graphs: Dict[str, CompiledStateGraph] = {}
    
    @classmethod
    def register(cls, name: str):
        """Decorator to register workflows."""
        def decorator(workflow_cls):
            cls.workflows[name] = workflow_cls
            return workflow_cls
        return decorator
    
    @classmethod
    def get_workflow(cls, name: str) -> CompiledStateGraph:
        """Get compiled workflow graph by name."""
        if name not in cls.compiled_graphs:
            workflow_path = f"{BASE_WORKFLOW_PATH}.{name}.workflow"
            module = import_module(workflow_path)
            class_name = ""
            for part in name.split("_"):
                class_name += part.capitalize()
            class_name += "Workflow"
            workflow_class = getattr(module, class_name)
            workflow = workflow_class()
            cls.compiled_graphs[name] = workflow.build_graph()
        return cls.compiled_graphs[name]
    
    @classmethod
    def list_workflows(cls) -> List[str]:
        """List available workflow names."""
        return list(cls.workflows.keys())