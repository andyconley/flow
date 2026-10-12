"""Live stock classifier/profile-switch acceptance on existing local Ollama.

Both profiles use the same existing model over its supported native/compatible
endpoints. This validates routing mechanics, not comparative model quality.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
settings = tempfile.TemporaryDirectory(prefix='flow-routing-settings-')
os.environ['OH_PERSISTENCE_DIR'] = settings.name
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from openhands_config import select
from openhands_runtime import build_agent
from openhands.sdk import Conversation
from openhands.sdk.tool.builtins.classify_and_switch_llm import ClassifyAndSwitchLLMTool, ClassifyAndSwitchLLMAction


def main():
    with tempfile.TemporaryDirectory(prefix='flow-routing-') as directory:
        root = Path(directory)
        (root / '.flow/agents').mkdir(parents=True)
        (root / '.flow/agents/coordinator.md').write_text('# Coordinator\nRoute the supplied task using the configured categories.\n')
        (root / '.flow/runtime.toml').write_text('''default_profile="local"
[profiles.local]
kind="local"
model="ollama_chat/gemma4-26b-dev:latest"
base_url="http://localhost:11434"
max_input_tokens=65536
max_output_tokens=8192
[profiles.compatible]
kind="local"
model="openai/gemma4-26b-dev:latest"
base_url="http://localhost:11434/v1"
max_input_tokens=65536
max_output_tokens=8192
[roles.coordinator]
specialists=[]
tools=[]
[roles.coordinator.model_routing]
classifier_profile="local"
[[roles.coordinator.model_routing.categories]]
description="Implementing code and automated tests"
profile="compatible"
[[roles.coordinator.model_routing.categories]]
description="Writing meeting notes without code"
profile="local"
''')
        agent = build_agent(select(root, 'implement', 'coordinator'), root)
        tool = next(t for t in agent.tools if t.name == ClassifyAndSwitchLLMTool.__name__)
        conversation = Conversation(agent=agent, workspace=root, persistence_dir=root / '.flow/history', visualizer=None)
        try:
            conversation.send_message('Implement a Python sum_numbers function and automated unit tests. This is a coding task.')
            observation = ClassifyAndSwitchLLMTool.create(**tool.params)[0].executor(ClassifyAndSwitchLLMAction(), conversation)
            result = {'error': observation.is_error, 'chosen_class': observation.chosen_class,
                      'selected_profile': observation.model, 'active_model': conversation.agent.llm.model,
                      'active_base_url': conversation.agent.llm.base_url,
                      'usage_ids': list(conversation.conversation_stats.usage_to_metrics)}
            print(json.dumps(result, indent=2))
            assert not observation.is_error and observation.model == 'compatible', observation
            assert conversation.agent.llm.model == 'openai/gemma4-26b-dev:latest'
            assert conversation.agent.llm.base_url == 'http://localhost:11434/v1'
        finally:
            conversation.close()

if __name__ == '__main__':
    main()
