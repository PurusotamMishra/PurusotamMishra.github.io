from typing import AsyncGenerator
from core.engine.registry import WorkflowRegistry
from utils.config import generate_workflow_id

class WorkflowExecutor:
    def __init__(self, registry: WorkflowRegistry):
        self.registry = registry
    
    async def execute(
        self,
        workflow_name: str,
        input_data: dict,
        stream: bool = False
    ) -> AsyncGenerator[dict, None]:
        """Execute workflow by name."""
        
        workflow_id = generate_workflow_id()
        input_data["workflow_id"] = workflow_id

        workflow = self.registry.get_workflow(workflow_name)        
        workflow_cls = self.registry.workflows[workflow_name]()
        initial_state = workflow_cls.get_initial_state(input_data)
        print("#########")
        print(initial_state)
        print(type(initial_state))
        print("#########")
        
        config = {"configurable": {"thread_id": workflow_id}}
        
        if stream:
            async for state_update in workflow.astream(initial_state, config=config):
                if state_update.get("response"):
                    yield state_update.get("response")
        else:
            result = workflow.ainvoke(initial_state, config=config)
            yield result