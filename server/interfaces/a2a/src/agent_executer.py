import json
import logging

from pydantic import BaseModel
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    InternalError,
    Part,
    DataPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_parts_message, new_agent_text_message
from a2a.utils.errors import ServerError

from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)

from interfaces.a2a.src.agent import BLOOAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BLOOAgentExecutor(AgentExecutor):
    """BLOO AgentExecutor."""

    def __init__(self):
        self.agent = BLOOAgent()

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> list[dict]:
        if not context.task_id or not context.context_id:
            raise ValueError("RequestContext must have task_id and context_id")
        if not context.message:
            raise ValueError("RequestContext must have a message")

        # updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        # if not context.current_task:
        #     await updater.submit()
        # await updater.start_work()

        query = context.get_user_input()
        request_method = context.call_context.state.get("method", "message/send")

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if not context.current_task:
            await updater.submit()
        await updater.start_work()

        try:
            if request_method == "message/stream":
                async for item in self.agent.astream(query, context.context_id):
                    is_task_complete = item["is_task_complete"]
                    require_user_input = item["require_user_input"]
                    parts = [Part(root=TextPart(text=item["content"]))]

                    if not is_task_complete and not require_user_input:
                        await updater.update_status(
                            TaskState.working,
                            message=updater.new_agent_message(parts),
                        )
                    elif require_user_input:
                        await updater.update_status(
                            TaskState.input_required,
                            message=updater.new_agent_message(parts),
                        )
                        break
                    else:
                        await updater.add_artifact(
                            parts,
                            name="scheduling_result",
                        )
                        await updater.complete()
                        break
            else:
                # result = await self.agent.ainvoke(query)
                result = ["disco"]

                if isinstance(result, list):
                    for item in result:
                        parts = []

                        if isinstance(item, dict):
                            parts = [Part(root=DataPart(data=item))]
                        elif isinstance(item, BaseModel):
                            parts = [Part(root=DataPart(data=item.json_model_dump()))]
                        else:
                            parts = [Part(root=TextPart(text=str(item)))]
                            
                        if parts:
                            await event_queue.enqueue_event(new_agent_parts_message(parts))
                        
                elif isinstance(result, dict):
                    parts = [Part(root=DataPart(data=result))]
                    await event_queue.enqueue_event(new_agent_parts_message(parts))
                elif isinstance(item, BaseModel):
                    parts = [Part(root=DataPart(data=item.json_model_dump()))]
                    await event_queue.enqueue_event(new_agent_parts_message(parts))
                else:
                    parts = [Part(root=TextPart(text=str(result)))]
                    await event_queue.enqueue_event(new_agent_parts_message(parts))
            
            # async for item in self.agent.stream(query, context.context_id):
            #     is_task_complete = item["is_task_complete"]
            #     require_user_input = item["require_user_input"]
            #     parts = [Part(root=TextPart(text=item["content"]))]

            #     if not is_task_complete and not require_user_input:
            #         await updater.update_status(
            #             TaskState.working,
            #             message=updater.new_agent_message(parts),
            #         )
            #     elif require_user_input:
            #         await updater.update_status(
            #             TaskState.input_required,
            #             message=updater.new_agent_message(parts),
            #         )
            #         break
            #     else:
            #         await updater.add_artifact(
            #             parts,
            #             name="scheduling_result",
            #         )
            #         await updater.complete()
            #         break

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            raise ServerError(error=InternalError()) from e

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())
