"""Local Ollama adapter behavior for ordinary and structured-verifier calls."""

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from local_worker import call_local  # noqa: E402
from verifier_contracts import VERIFIER_OUTPUT_SCHEMA  # noqa: E402


ENVELOPE = {"provider": "ollama", "model": "local-model", "instructions": "verify", "task": "task", "attempt_id": "a"}


def payload(content, model="local-model"):
    return {"model": model, "message": {"role": "assistant", "content": content}}


class _Response:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, _limit):
        return self.body


class OllamaRequestBodyTests(unittest.TestCase):
    def sent_body(self, *, structured):
        sent, timeouts = [], []

        class Opener:
            def open(self, request, timeout):
                sent.append(json.loads(request.data))
                timeouts.append(timeout)
                return _Response(json.dumps(payload("{}")).encode())

        with patch("local_worker.urllib.request.build_opener", return_value=Opener()), \
             patch.dict("os.environ", {}, clear=False):
            os.environ.pop("FLOW_OLLAMA_URL", None)
            call_local(ENVELOPE, structured_verifier=structured)
        return sent[0], timeouts[0]

    def test_only_a_structured_verifier_call_requests_constrained_json(self):
        structured, structured_timeout = self.sent_body(structured=True)
        ordinary, ordinary_timeout = self.sent_body(structured=False)
        self.assertEqual(structured["format"], VERIFIER_OUTPUT_SCHEMA)
        self.assertNotIn("format", ordinary)
        self.assertIsNone(structured_timeout)
        self.assertIsNone(ordinary_timeout)


class StructuredVerifierAdapterTests(unittest.TestCase):
    def call(self, response, *, structured):
        return call_local(ENVELOPE, transport=lambda _: response, structured_verifier=structured)

    def test_ordinary_calls_keep_existing_refusals_and_bound(self):
        with self.assertRaisesRegex(RuntimeError, "empty response"):
            self.call(payload(""), structured=False)
        with self.assertRaisesRegex(RuntimeError, "different model"):
            self.call(payload("ok", model="other"), structured=False)
        self.assertEqual(len(self.call(payload("x" * 5000), structured=False)["output"]), 4096)

    def test_received_empty_content_is_a_completed_observation(self):
        result = self.call(payload(""), structured=True)
        self.assertEqual((result["status"], result["output"]), ("completed", ""))
        self.assertEqual(result["output_sha256"], hashlib.sha256(b"").hexdigest())

    def test_reported_model_is_retained_for_flow_binding_check(self):
        self.assertEqual(self.call(payload("ok", model="other"), structured=True)["model"], "other")
        self.assertEqual(self.call(payload("ok", model=None), structured=True)["model"], "unreported")

    def test_output_is_not_cut_at_the_ordinary_bound(self):
        text = "x" * 20000
        result = self.call(payload(text), structured=True)
        self.assertEqual(result["output"], text)
        self.assertEqual(result["output_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(len(self.call(payload("x" * 70000), structured=True)["output"]), 64 * 1024)


class RetainedProfileWorkerTests(unittest.TestCase):
    def test_profile_sends_measured_options_and_observes_real_exchange(self):
        sent, events = [], []
        class Opener:
            def open(self, request, timeout):
                sent.append((json.loads(request.data), timeout))
                return _Response(json.dumps(payload('x' * 5000)).encode())
        with patch('local_worker.urllib.request.build_opener', return_value=Opener()):
            result = call_local(ENVELOPE, local_agent_profile={}, observer=events.append)
        self.assertEqual(sent[0][0]['options'], {'num_ctx': 12288, 'num_predict': 2048, 'temperature': 0, 'seed': 42})
        self.assertEqual(sent[0][1], 600)
        self.assertEqual(len(result['output']), 5000)
        self.assertEqual([event['type'] for event in events], ['model_request', 'model_send', 'model_response'])

    def test_oversize_context_denied_without_transport(self):
        from execution_contracts import ContractError
        events = []
        with patch('local_worker.urllib.request.build_opener') as opener:
            with self.assertRaises(ContractError):
                call_local({**ENVELOPE, 'task': 'x' * 40000}, local_agent_profile={}, observer=events.append)
        opener.assert_not_called()
        self.assertEqual(events[0]['type'], 'context_denied')


class WorkerResourceMonitorTests(unittest.TestCase):
    def test_monitor_stops_after_success_and_refuses_pressure_before_send(self):
        class Monitor:
            def __init__(self, callback, blocked=False):
                self.callback, self.blocked, self.stopped = callback, blocked, False
            def start(self):
                self.callback({'pressure': 'normal'}, {'action': 'continue'})
            def check(self):
                if self.blocked:
                    raise RuntimeError('critical pressure')
            def record_error(self, error):
                pass
            def stop(self):
                self.stopped = True
        monitors, events = [], []
        def factory(callback):
            monitor = Monitor(callback)
            monitors.append(monitor)
            return monitor
        class Opener:
            def open(self, request, timeout):
                return _Response(json.dumps(payload('ok')).encode())
        with patch('local_worker.urllib.request.build_opener', return_value=Opener()):
            call_local(ENVELOPE, resource_monitor_factory=factory, observer=events.append)
        self.assertTrue(monitors[0].stopped)
        self.assertEqual(events[0]['type'], 'resource_sample')
        events.clear()
        blocked = Monitor(lambda *args: None, blocked=True)
        with patch('local_worker.urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(RuntimeError, 'critical pressure'):
                call_local(ENVELOPE, resource_monitor_factory=lambda callback: blocked, observer=events.append)
        self.assertTrue(blocked.stopped)
        self.assertNotIn('model_send', [event['type'] for event in events])
        opener.return_value.open.assert_not_called()


class NativeConversationTransportTests(unittest.TestCase):
    def test_native_roles_content_and_exact_context_preview(self):
        from runner_limits import resolve_local_agent_budget
        sent, events = [], []
        messages = [{'role': 'user', 'content': 'Original "quoted" task: café'},
                    {'role': 'assistant', 'content': 'Observed producer result'},
                    {'role': 'user', 'content': 'Current stock phase request'},
                    {'role': 'system', 'content': 'Flow authority note'}]
        class Opener:
            def open(self, request, timeout):
                sent.append(request.data)
                return _Response(json.dumps(payload('actual model response')).encode())
        with patch('local_worker.urllib.request.build_opener', return_value=Opener()):
            call_local(ENVELOPE, chat_messages=messages,
                       local_agent_profile=resolve_local_agent_budget(), observer=events.append)
        body=json.loads(sent[0])
        self.assertEqual(body['messages'], [{'role':'system','content':'verify'},*messages])
        self.assertNotIn('format',body)
        observed=next(event for event in events if event['type']=='model_request')
        self.assertEqual(observed['request'],body)
        self.assertEqual(body['options']['num_ctx'],12288)
        self.assertEqual(body['options']['num_predict'],2048)
        self.assertEqual(body['messages'][1]['content'],messages[0]['content'])

    def test_native_conversation_is_profile_only_and_validated_before_io(self):
        from execution_contracts import ContractError
        from runner_limits import resolve_local_agent_budget
        with patch('local_worker.urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(ContractError,'retained local profile'):
                call_local(ENVELOPE,chat_messages=[{'role':'user','content':'task'}])
            with self.assertRaisesRegex(ContractError,'role/content'):
                call_local(ENVELOPE,local_agent_profile=resolve_local_agent_budget(),
                           chat_messages=[{'role':'invalid','content':'task'}])
            opener.assert_not_called()

    def test_context_guard_counts_actual_native_messages_not_serialized_envelope_task(self):
        from execution_contracts import ContractError
        from runner_limits import resolve_local_agent_budget
        with patch('local_worker.urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(ContractError,'context reserve'):
                call_local(ENVELOPE,local_agent_profile=resolve_local_agent_budget(),
                           chat_messages=[{'role':'user','content':'x'*40000}])
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
