"""Spike: are Magentic manager calls replayed with identical call_ids after a restore or a fresh restart?

S2: run to action 1, answer it, answer following manager calls, stop at the Nth post-action manager call
    (as if Flow denied it), kill. Resume in answer mode from action 1's checkpoint with the manager count
    committed at proposal time. Compare the re-issued manager call identities with the originals.
S3: fresh start twice; compare the first planning-phase manager call identities.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

REPO = Path("/Users/andyconley/src/flow")
PY = os.environ["FLOW_MAF_PYTHON"]
ROSTER = [{"assignment_id": "test", "definition_digest": "test-definition", "instance_id": "test-engineer-1",
           "role": "test-engineer", "provider": "local-stub", "model": "fake", "capabilities": ["read"]},
          {"assignment_id": "review", "definition_digest": "review-definition", "instance_id": "reviewer-1",
           "role": "quality-reviewer", "provider": "local-stub", "model": "fake", "capabilities": ["read"]}]


def launch(payload):
    p = subprocess.Popen([PY, "-m", "runtime.maf_runner.delivery_lead"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, cwd=REPO)
    p.stdin.write(json.dumps(payload) + "\n"); p.stdin.flush(); return p


def answer(p, event, rounds_to_finish=3):
    phase = event["phase"]
    text = {"facts": "Fixture facts", "plan": "- Ask specialist", "final": "Done"}.get(phase)
    if phase == "progress":
        done = event["manager_round"] >= rounds_to_finish
        text = json.dumps({"is_request_satisfied": {"reason": "done" if done else "pending", "answer": done},
                           "is_in_loop": {"reason": "no", "answer": False},
                           "is_progress_being_made": {"reason": "yes", "answer": True},
                           "next_speaker": {"reason": "best", "answer": "test-engineer-1"},
                           "instruction_or_question": {"reason": "task", "answer": "Analyze fixture"}})
    p.stdin.write(json.dumps({"protocol_version": 8, "type": "manager_response", "call_id": event["call_id"], "text": text}) + "\n")
    p.stdin.flush()


def kill(p):
    p.kill(); p.wait(timeout=10)
    for pipe in (p.stdin, p.stdout, p.stderr):
        pipe and pipe.close()


ident = lambda e: (e["sequence"], e["phase"], e["manager_round"], e["prompt_digest"][:12], e["call_id"][:12])

with tempfile.TemporaryDirectory() as ck:
    env = {"execution_protocol_version": 8, "attempt_id": "spike", "checkpoint_dir": ck, "roster": ROSTER,
           "job_contract": {"producer_instance_ids": ["test-engineer-1"], "verifier_instance_ids": ["reviewer-1"]}}
    # ---- S2 ----
    first = launch({"protocol_version": 8, "type": "start", "envelope": env, "task": "Analyze fixture"})
    calls, proposal, after = 0, None, []
    STOP_AFTER = 2  # post-action manager calls answered before the "denied" one
    for _ in range(40):
        e = json.loads(first.stdout.readline())
        if e["type"] == "manager_request":
            if proposal is None:
                calls += 1; answer(first, e)
            else:
                after.append(e)
                if len(after) > STOP_AFTER:
                    break  # the denied call: never answered
                answer(first, e)
        elif e["type"] == "propose_action" and proposal is None:
            proposal = e
            first.stdin.write(json.dumps({"protocol_version": 8, "type": "action_result", "action_id": e["action_id"],
                                          "result": {"summary": "Fixture analyzed"}}) + "\n"); first.stdin.flush()
        else:
            print("S2 unexpected before stop:", e["type"]); break
    kill(first)
    resumed = launch({"protocol_version": 8, "type": "resume", "envelope": env, "task": "Analyze fixture",
                      "resume": {"kind": "answer", "checkpoint_id": proposal["checkpoint_id"], "request_id": "flow-magentic-action-1",
                                 "action_id": proposal["action_id"], "manager_calls_committed": calls, "replans_committed": 0,
                                 "result": {"summary": "Fixture analyzed"}}})
    replay = []
    for _ in range(len(after)):
        e = json.loads(resumed.stdout.readline())
        if e["type"] != "manager_request":
            print("S2 resume got", e); break
        replay.append(e)
        if len(replay) < len(after):
            answer(resumed, e)
    kill(resumed)
    print("S2 original post-action calls:", [ident(e) for e in after])
    print("S2 replayed calls:            ", [ident(e) for e in replay])
    print("S2 identical call_ids:", [a["call_id"] == b["call_id"] for a, b in zip(after, replay)])

import shutil
with tempfile.TemporaryDirectory() as ck:
    runs = []
    for _ in range(2):
        shutil.rmtree(ck); os.mkdir(ck)
        env = {"execution_protocol_version": 8, "attempt_id": "spike-fresh", "checkpoint_dir": ck, "roster": ROSTER,
               "job_contract": {"producer_instance_ids": ["test-engineer-1"], "verifier_instance_ids": ["reviewer-1"]}}
        p = launch({"protocol_version": 8, "type": "start", "envelope": env, "task": "Analyze fixture"})
        seen = []
        for _ in range(3):
            e = json.loads(p.stdout.readline())
            if e["type"] != "manager_request":
                break
            seen.append(e); answer(p, e)
        kill(p); runs.append(seen)
    print("S3 fresh-start identical call_ids:", [a["call_id"] == b["call_id"] for a, b in zip(*runs)], "prompt digests equal:", [a["prompt_digest"] == b["prompt_digest"] for a, b in zip(*runs)])
