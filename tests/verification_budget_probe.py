#!/usr/bin/env python3
"""Read-only SDK budget inspection with canned metrics. Never dispatches a model."""
import dataclasses
import hashlib
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace
os.environ.setdefault('LITELLM_LOCAL_MODEL_COST_MAP', 'True')
os.environ.setdefault('OPENHANDS_SUPPRESS_BANNER', '1')

from openhands.sdk.conversation.impl.local_conversation import LocalConversation
from openhands.sdk.llm import LLM
from openhands.sdk.llm.call_context import LLMCallContext
from openhands.tools.task.definition import TaskAction
from litellm.llms.ollama.chat.transformation import OllamaChatConfig, _done_chunk_usage


def main():
    def cost_guard(cost, generated):
        metrics = SimpleNamespace(accumulated_cost=cost,
            accumulated_token_usage=SimpleNamespace(completion_tokens=generated))
        state = SimpleNamespace(max_budget_per_run=0.01,
            conversation_stats=SimpleNamespace(get_combined_metrics=lambda: metrics))
        return LocalConversation._budget_exceeded_detail(state)
    mapping = OllamaChatConfig().map_openai_params(
        {'max_completion_tokens': 8192}, {}, 'gemma4-26b-dev:latest', False)
    zero_price = cost_guard(0.0, 40001)
    priced = cost_guard(0.02, 1)
    assert zero_price is None
    assert priced is not None
    assert mapping['num_predict'] == 8192
    assert _done_chunk_usage({'done': False, 'eval_count': 40001, 'prompt_eval_count': 10}) is None
    assert _done_chunk_usage({'done': True, 'prompt_eval_count': 10}) is None
    results = {
        'kind': 'read_only_sdk_inspection_and_canned_metrics', 'model_dispatches': 0,
        'cost_guard_at_40001_generated_tokens_and_zero_cost': zero_price,
        'cost_guard_at_one_generated_token_and_cost_above_dollar_limit': priced,
        'per_request_mapping': mapping, 'five_per_request_caps': 5 * mapping['num_predict'],
        'default_iteration_limit': inspect.signature(LocalConversation.__init__).parameters['max_iteration_per_run'].default,
        'default_request_retries': LLM.model_fields['num_retries'].default,
        'call_context_fields': [f.name for f in dataclasses.fields(LLMCallContext)],
        'task_max_turns_description': TaskAction.model_fields['max_turns'].description,
        'missing_final_provider_usage': 'unknown; no exact completion count available',
        'interpretation': 'Cost, iteration and per-request output controls do not establish a shared generated-token ceiling. No live trial is authorized by these observations.'}
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
