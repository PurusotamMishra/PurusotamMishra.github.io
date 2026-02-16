import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InternalError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message

from a2a.utils.errors import ServerError
import sys
sys.path.append("/app/server")
from agent.agent import BLOOAgent

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
        try:
            result = await self.agent.invoke(query)
            print(f"result: {result}")
            # import json
            event_queue.enqueue_event(new_agent_text_message("result is random thing"))
            
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
