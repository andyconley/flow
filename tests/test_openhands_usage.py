"""Accounting integration with combined SQLite reports and native precedence."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import usage_store
from openhands_usage import harvest_project, reporting_rows
from normalize import normalize_all
from cost import summary_rows, sessions_rows, active_rows, trend_rows


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run_dir = self.root / '.flow/runs/accounting'
        self.run_dir.mkdir(parents=True)
        store = self.root / 'usage.db'
        usage_store.ensure_store(store)
        self.conn = sqlite3.connect(store)
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.parent = str(uuid4())
        self.child = str(uuid4())
        self.run = {'work_id': 'accounting', 'runtime': 'openhands', 'sessions': {
            'define:business-analyst': {'conversation_id': self.parent, 'role': 'business-analyst',
                'stage': 'define', 'profile': 'local', 'provider': 'local',
                'metrics_observed_at': '2026-10-12T10:00:00+00:00'}}}
        self.write_run()

    def write_run(self):
        (self.run_dir / 'run.json').write_text(json.dumps(self.run))

    def snapshot(self, session_id, metrics, parent=None, provider='local'):
        directory = self.run_dir / 'openhands' / self.parent.replace('-', '')
        if parent:
            directory = directory / 'subagents' / session_id.replace('-', '')
        directory.mkdir(parents=True, exist_ok=True)
        agent = {'acp_server': 'codex'} if provider == 'codex' else {'llm': {'model': 'openai/test'}}
        (directory / 'base_state.json').write_text(json.dumps({'id': session_id, 'agent': agent,
                                                            'stats': {'usage_to_metrics': metrics}}))

    def metric(self, n=1, model='openai/test', response_id='response', cost=0):
        return {'model_name': model, 'costs': [{'cost': cost, 'model': model, 'timestamp': 1791799200+i} for i in range(n)],
                'token_usages': [{'model': model, 'prompt_tokens': 100, 'completion_tokens': 20,
                                 'cache_read_tokens': 25, 'cache_write_tokens': 0, 'reasoning_tokens': 0,
                                 'context_window': 65536, 'response_id': response_id} for _ in range(n)]}

    def harvest(self):
        result = harvest_project(self.conn, self.root)
        self.assertFalse(result['failures'], result)
        norm = normalize_all(self.conn)
        self.assertFalse(norm['failures'], norm)
        return result

    def test_parent_child_rollups_reimports_resume_and_new_session(self):
        self.snapshot(self.parent, {'flow-business-analyst': self.metric(), 'task:task_00000001': self.metric(2)})
        self.snapshot(self.child, {'flow-test-engineer': self.metric(2)}, parent=self.parent)
        self.assertEqual(self.harvest()['turns'], 3)
        self.assertEqual(self.harvest()['turns'], 0)
        self.assertEqual(summary_rows(self.conn, None)[0]['fresh_input_tokens'], 225)
        self.assertEqual(sessions_rows(self.conn, None, None)[0]['turns'] + sessions_rows(self.conn, None, None)[1]['turns'], 3)
        self.snapshot(self.child, {'flow-test-engineer': self.metric(3)}, parent=self.parent)
        self.assertEqual(self.harvest()['turns'], 1)
        self.assertEqual(summary_rows(self.conn, None)[0]['output_tokens'], 80)
        self.run['prior_sessions'] = list(self.run['sessions'].values())
        old = self.parent
        self.parent = str(uuid4())
        self.run['sessions']['define:business-analyst']['conversation_id'] = self.parent
        # deepcopy because the prior reference must remain a historical identity.
        self.run['prior_sessions'][0] = {**self.run['prior_sessions'][0], 'conversation_id': old}
        self.write_run()
        self.snapshot(self.parent, {'flow-business-analyst': self.metric()})
        self.harvest()
        self.assertEqual(summary_rows(self.conn, None)[0]['output_tokens'], 100)
        attribution = reporting_rows(self.conn)
        self.assertTrue(any(r['role'] == 'test-engineer' and r['parent_session_id'] == old for r in attribution))
        self.assertTrue(all(r['actual_billed_cost'] is None for r in attribution))
        self.assertTrue(all(r['pricing_status'] == 'unknown_pricing' and r['sdk_reported_cost'] == 0 and r['sdk_estimated_cost'] is None for r in attribution))
        self.assertTrue(trend_rows(self.conn, None, 'day'))
        self.assertIsInstance(active_rows(self.conn, 60), list)

    def test_native_transcript_precedence_is_identity_based_and_order_independent(self):
        native = str(uuid4())
        self.snapshot(self.parent, {'acp': self.metric(response_id=native)}, provider='codex')
        self.harvest()
        self.assertEqual(summary_rows(self.conn, None)[0]['output_tokens'], 20)
        with self.conn:
            self.conn.execute("INSERT INTO session(harness,session_id,cwd) VALUES('codex',?,?)", (native,str(self.root)))
            sid = self.conn.execute('SELECT id FROM session').fetchone()[0]
            payload = {'payload': {'type': 'token_count', 'info': {'last_token_usage': {'input_tokens': 100,'cached_input_tokens':25,'output_tokens':20}}}}
            self.conn.execute('INSERT INTO turn_raw(session_row_id,natural_turn_id,turn_seq,ts,model,payload,source_path,source_line_no,collector_version) VALUES(?,?,?,?,?,?,?,?,?)',
                              (sid,'native-turn',0,'2026-10-12T10:00:00+00:00','gpt-native',json.dumps(payload),'native.jsonl',1,1))
        self.harvest()
        rows = summary_rows(self.conn,None)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['harness'],'codex')
        self.assertEqual(rows[0]['output_tokens'],20)
        self.assertEqual(reporting_rows(self.conn)[0]['token_source'],'native_transcript')
        self.assertEqual(reporting_rows(self.conn)[0]['pricing_status'],'subscription_not_measured')
        # An unrelated native session must not hide SDK usage.
        with self.conn:
            self.conn.execute('UPDATE session SET session_id=?',(str(uuid4()),))
        self.assertEqual(sum(r['output_tokens'] for r in summary_rows(self.conn,None)),40)
        # Rebuild only SDK test rows, leaving the native transcript present:
        # this exercises the opposite collection order against the same views.
        with self.conn:
            self.conn.execute('UPDATE session SET session_id=?',(native,))
            self.conn.execute('DELETE FROM sdk_turn_norm')
            self.conn.execute('DELETE FROM sdk_turn_raw')
            self.conn.execute('DELETE FROM sdk_session')
        self.harvest()
        self.assertEqual(len(summary_rows(self.conn,None)),1)
        self.assertEqual(summary_rows(self.conn,None)[0]['harness'],'codex')
        self.assertEqual(summary_rows(self.conn,None)[0]['output_tokens'],20)

    def test_positive_sdk_estimate_and_raw_correction_recompute(self):
        self.snapshot(self.parent, {'flow-business-analyst': self.metric(cost=.2)})
        self.harvest()
        self.assertEqual(reporting_rows(self.conn)[0]['sdk_estimated_cost'],.2)
        metric = self.metric(cost=.2); metric['token_usages'][0]['prompt_tokens'] = 125
        self.snapshot(self.parent, {'flow-business-analyst': metric})
        self.harvest()
        self.assertEqual(summary_rows(self.conn,None)[0]['fresh_input_tokens'],100)

    def test_projection_retained_after_snapshot_unavailable_and_no_outcome_duplicate(self):
        self.run['sessions']['define:business-analyst']['metrics_by_usage'] = {'flow-business-analyst': self.metric()}
        self.write_run()
        (self.run_dir/'define-business-analyst-outcome.json').write_text(json.dumps(self.run))
        self.assertEqual(self.harvest()['turns'],1)
        self.assertEqual(self.harvest()['turns'],0)
        self.assertEqual(summary_rows(self.conn,None)[0]['turns'],1)

    def test_committed_acceptance_fixtures_keep_native_cache_and_ollama64k_semantics(self):
        fixtures = Path(__file__).resolve().parents[1] / "docs/acceptance"
        for name, provider in (("ollama-64k", "local"), ("codex-native", "codex"), ("claude-native", "claude")):
            with self.subTest(fixture=name):
                metric = json.loads((fixtures/name/"result.json").read_text())["metrics"]
                if provider != "local":
                    for usage in metric["token_usages"]:
                        usage["response_id"] = "fixture-" + name
                self.run["sessions"]["define:business-analyst"]["provider"] = provider
                self.run["sessions"]["define:business-analyst"]["metrics_by_usage"] = {"flow-business-analyst": metric}
                self.write_run()
                self.harvest()
                rows = summary_rows(self.conn, None)
                self.assertEqual(sum(r["fresh_input_tokens"] for r in rows), sum(u["prompt_tokens"] for u in metric["token_usages"]))
                self.assertEqual(sum(r["output_tokens"] for r in rows), sum(u["completion_tokens"] for u in metric["token_usages"]))
                self.assertEqual(sum(r["cache_read_tokens"] for r in rows), sum(u["cache_read_tokens"] for u in metric["token_usages"]))
                self.assertEqual(sum(r["cache_write_tokens"] for r in rows), sum(u["cache_write_tokens"] for u in metric["token_usages"]))
                self.assertTrue(all(r["actual_billed_cost"] is None for r in reporting_rows(self.conn)))
                if name == "ollama-64k":
                    self.assertEqual(self.conn.execute("SELECT MAX(context_window) FROM sdk_turn_norm").fetchone()[0], 65536)
                    self.assertTrue(all(r["timestamp_basis"] == "observation" for r in reporting_rows(self.conn)))
                with self.conn:
                    self.conn.execute("DELETE FROM sdk_turn_norm")
                    self.conn.execute("DELETE FROM sdk_turn_raw")
                    self.conn.execute("DELETE FROM sdk_session")

    def test_cumulative_snapshot_is_replaced_not_summed_and_calls_are_unknown(self):
        ref = self.run["sessions"]["define:business-analyst"]
        metric = self.metric(2)
        metric["accumulated_token_usage"] = {"model": "openai/test", "prompt_tokens": 200, "completion_tokens": 40, "cache_read_tokens": 50, "cache_write_tokens": 0, "context_window": 65536}
        metric["token_usages"] = []
        metric["accumulated_cost"] = 0
        metric["costs"] = []
        ref["metrics_by_usage"] = {"flow-business-analyst": metric}
        self.write_run();self.harvest()
        self.assertEqual(summary_rows(self.conn,None)[0]["fresh_input_tokens"],150)
        self.assertIsNone(summary_rows(self.conn,None)[0]["turns"])
        self.assertIsNone(reporting_rows(self.conn)[0]["sdk_calls"])
        self.assertIsNone(self.conn.execute("SELECT context_window FROM sdk_turn_norm").fetchone()[0])
        metric["accumulated_token_usage"]["prompt_tokens"] = 300
        ref["metrics_observed_at"] = "2026-10-12T11:00:00+00:00"
        self.write_run();self.harvest()
        self.assertEqual(summary_rows(self.conn,None)[0]["fresh_input_tokens"],250)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sdk_turn_raw").fetchone()[0],1)
        self.assertEqual(self.conn.execute("SELECT ts FROM sdk_turn_norm").fetchone()[0],ref["metrics_observed_at"])
        self.assertEqual(self.harvest()["turns"],0)
        # When the full SDK call history becomes available, it supersedes the
        # aggregate read projection without deleting its raw source record.
        ref["metrics_by_usage"] = {"flow-business-analyst": self.metric(3)}
        self.write_run();self.harvest()
        self.assertEqual(summary_rows(self.conn,None)[0]["fresh_input_tokens"],225)
        self.assertEqual(summary_rows(self.conn,None)[0]["turns"],3)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sdk_turn_raw").fetchone()[0],4)
        self.assertEqual(len(reporting_rows(self.conn)),1)
