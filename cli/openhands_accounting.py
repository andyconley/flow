"""Pinned SDK task identity compatibility, without changing task execution."""
from uuid import uuid4

from openhands.tools.task.definition import TaskAction
from pydantic import ConfigDict, Field


class RoleTaskAction(TaskAction):
    """Stable SDK action identity for persisted checked-dispatch events.

    `subagent_type` has no generic default: the stock SDK default of
    "general-purpose" is not a configured Flow roster target, so letting a
    caller omit it just defers a rejection to execution time. Requiring it
    here fails fast, at the schema the coordinator model actually sees.
    """
    model_config = ConfigDict(extra="forbid")
    subagent_type: str = Field(
        description="Role or role--provider target from the approved Flow roster. Required; no generic default.",
    )


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
    from openhands.tools.task.definition import TaskObservation
    from openhands.sdk.tool import register_tool
    from openhands.sdk.tool.tool import ToolExecutor

    class CheckedExecutor(ToolExecutor):
        def __init__(self, delegate, bindings):
            self.delegate = delegate
            self.bindings = dict(bindings)
            self.tasks = {}
            self.task_routes = {}

        def __call__(self, action, conversation=None):
            if action.subagent_type not in self.bindings or (
                action.resume is not None and self.tasks.get(action.resume) != action.subagent_type
            ):
                return TaskObservation.from_text(text='Role or resume is outside the approved Flow roster.',
                    task_id='rejected', subagent=action.subagent_type, status='error', is_error=True)
            binding = self.bindings[action.subagent_type]
            routes = binding if isinstance(binding, dict) else {'primary': binding}
            route = self.task_routes.get(action.resume, routes['primary'])
            lock = None
            if routes.get('local') and route == routes['primary']:
                import fcntl
                from pathlib import Path
                directory = Path.home() / '.flow/state'
                directory.mkdir(parents=True, exist_ok=True)
                lock = (directory / 'openhands-local-worker.lock').open('a')
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    lock.close()
                    lock = None
                    return TaskObservation.from_text(text='Local worker slot is busy; no model was started. Choose another listed provider target or retry later.',
                        task_id='rejected', subagent=action.subagent_type, status='error', is_error=True)
            mapped = action.model_copy(update={'subagent_type': route})
            try:
                result = self.delegate(mapped, conversation)
            finally:
                if lock is not None:
                    lock.close()
            from openhands.sdk import TextContent
            result = result.model_copy(update={'content': [*result.content, TextContent(text=
                f"Selected target: {action.subagent_type}; profile: {routes.get('profile', route)}; "
                f"provider: {routes.get('provider', 'bound SDK factory')}; model: {routes.get('model', 'factory default')}")]})
            if not result.is_error:
                self.tasks[result.task_id] = action.subagent_type
                self.task_routes[result.task_id] = route
            else:
                result = result.model_copy(update={'content': [*result.content, TextContent(text=
                    'Execution failed. Inspect any partial edits before retrying or choosing another listed provider target; '
                    'no automatic replay was performed.')]})
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
                    'description': ('Delegate work to an approved role/provider target. Choose a listed target; '
                                    'role-only names use configured preferences. After failure inspect partial edits '
                                    'before choosing another provider. Targets: ' + ', '.join(sorted(bindings or {})))
                }))
            return checked

    if not _POLICY_REGISTERED:
        register_tool(FlowPolicyTaskToolSet.name, FlowPolicyTaskToolSet)
        _POLICY_REGISTERED = True
    return FlowPolicyTaskToolSet.name
