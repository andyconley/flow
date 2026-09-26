"""S2b: deny the manager call after action 2; resume in answer mode from action 2's checkpoint."""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(__file__))
exec(open(os.path.join(os.path.dirname(__file__), "spike_expansion.py")).read().split("with tempfile.TemporaryDirectory() as ck:")[0])
with tempfile.TemporaryDirectory() as ck:
    env = {"execution_protocol_version": 8, "attempt_id": "spike2", "checkpoint_dir": ck, "roster": ROSTER,
           "job_contract": {"producer_instance_ids": ["test-engineer-1"], "verifier_instance_ids": ["reviewer-1"]}}
    p = launch({"protocol_version": 8, "type": "start", "envelope": env, "task": "Analyze fixture"})
    calls, actions, denied = 0, [], None
    for _ in range(40):
        e = json.loads(p.stdout.readline())
        if e["type"] == "manager_request":
            if len(actions) == 2:
                denied = e; break
            calls += 1; answer(p, e, rounds_to_finish=5)
        elif e["type"] == "propose_action":
            actions.append((e, calls))
            p.stdin.write(json.dumps({"protocol_version": 8, "type": "action_result", "action_id": e["action_id"], "result": {"summary": "Fixture analyzed"}}) + "\n"); p.stdin.flush()
        else:
            print("unexpected", e["type"]); break
    kill(p)
    a2, committed = actions[1]
    r = launch({"protocol_version": 8, "type": "resume", "envelope": env, "task": "Analyze fixture",
                "resume": {"kind": "answer", "checkpoint_id": a2["checkpoint_id"], "request_id": "flow-magentic-action-2",
                           "action_id": a2["action_id"], "manager_calls_committed": committed, "replans_committed": 0,
                           "result": {"summary": "Fixture analyzed"}}})
    e = json.loads(r.stdout.readline()); kill(r)
    print("S2b denied:", ident(denied), "replayed:", ident(e) if e["type"] == "manager_request" else e, "identical:", e.get("call_id") == denied["call_id"])
