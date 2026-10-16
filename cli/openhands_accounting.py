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


_POLICY_REGISTERED = False


def register_policy_task_tool():
    """Expose logical roles only; stock SDK still owns task execution and history."""
    global _POLICY_REGISTERED
    from openhands.tools.task import TaskToolSet
    from openhands.tools.task.definition import TaskAction, TaskObservation
    from openhands.sdk.tool import register_tool
    from openhands.sdk.tool.tool import ToolExecutor
    from pydantic import ConfigDict

    class RoleTaskAction(TaskAction):
        model_config = ConfigDict(extra='forbid')

    class CheckedExecutor(ToolExecutor):
        def __init__(self, delegate, bindings):
            self.delegate = delegate
            self.bindings = dict(bindings)
            self.tasks = {}

        def __call__(self, action, conversation=None):
            if action.subagent_type not in self.bindings or (
                action.resume is not None and self.tasks.get(action.resume) != action.subagent_type
            ):
                return TaskObservation.from_text(text='Role or resume is outside the approved Flow roster.',
                    task_id='rejected', subagent=action.subagent_type, status='error', is_error=True)
            mapped = action.model_copy(update={'subagent_type': self.bindings[action.subagent_type]})
            result = self.delegate(mapped, conversation)
            if not result.is_error:
                self.tasks[result.task_id] = action.subagent_type
            return result

        def close(self):
            self.delegate.close()

    class FlowPolicyTaskToolSet(TaskToolSet):
        name = "flow_policy_task_tool_set"
        @classmethod
        def create(cls, conv_state, confirmation_handler=None, sub_agent_scope=None, bindings=None):
            # Keep SDK confirmation propagation and accounting identity behavior.
            # Create stock tools, then narrow the public action and executor.
            tools = TaskToolSet.create(conv_state, confirmation_handler, sub_agent_scope)
            from types import MethodType
            def generate_ids(manager):
                identifier = uuid4()
                return f'task_{identifier.hex}', identifier
            checked = []
            for tool in tools:
                tool.executor._manager._generate_ids = MethodType(generate_ids, tool.executor._manager)
                checked.append(tool.model_copy(update={
                    'executor': CheckedExecutor(tool.executor, bindings or {}),
                    'action_type': RoleTaskAction,
                    'description': ('Delegate work to an approved Flow role. Provider/model are fixed by policy; '
                                    'no provider/profile overrides are accepted. Roles: ' + ', '.join(sorted(bindings or {})))
                }))
            return checked

    if not _POLICY_REGISTERED:
        register_tool(FlowPolicyTaskToolSet.name, FlowPolicyTaskToolSet)
        _POLICY_REGISTERED = True
    return FlowPolicyTaskToolSet.name
