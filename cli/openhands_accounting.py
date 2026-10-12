"""Pinned SDK task identity compatibility, without changing task execution."""
from uuid import uuid4

_REGISTERED = False


def register_accounting_task_tool():
    global _REGISTERED
    from openhands.tools.task import TaskToolSet
    from openhands.sdk.tool import register_tool
    from types import MethodType

    class AccountingTaskToolSet(TaskToolSet):
        @classmethod
        def create(cls, conv_state, confirmation_handler=None, sub_agent_scope=None):
            tools = TaskToolSet.create(conv_state, confirmation_handler, sub_agent_scope)
            # SDK 1.54 derives ids from len(manager._tasks), which resets on a
            # fresh process and overwrites persisted task: metrics. Keep its
            # executor/manager, cumulative replacement, and same-process resume;
            # change only identity generation on this tool's manager instance.
            def generate_ids(manager):
                identifier = uuid4()
                return f"task_{identifier.hex}", identifier
            for tool in tools:
                tool.executor._manager._generate_ids = MethodType(generate_ids, tool.executor._manager)
            return tools

    name = TaskToolSet.name
    if not _REGISTERED:
        register_tool(name, AccountingTaskToolSet)
        _REGISTERED = True
    return name
