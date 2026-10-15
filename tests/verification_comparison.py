#!/usr/bin/env python3
"""Deterministic scripted probes of frozen cases; never live-model trials.

Each arm runs in a fresh process importing its own source. The independent
correctness script stays outside the disposable worker workspace. Model utility
metrics remain unknown. Usage: --baseline /path/to/v0.44.4 --output /path/raw.json
"""
from argparse import ArgumentParser, Namespace
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / 'tests/fixtures/verification-evaluation/v1/cases.json'


def driver(source, case, work):
    sys.path.insert(0, str(source / 'cli'))
    import openhands_flow as flow
    import runstate
    modern = hasattr(flow, 'check')
    subprocess.run(['git', 'init', '-q', str(work)], check=True)
    args = Namespace(project_root=work, work_id='trial', stage=None, disposition=[])
    for name, content in case['files'].items():
        (work / name).write_text(content)
    sequence = 0

    def setup(work_id):
        args.work_id = work_id
        flow.initialize(args)
        directory = work / '.flow/runs' / work_id
        for name in ('requirements.md', 'acceptance-criteria.md'):
            (directory / name).write_text(case['task'])
        args.stage = 'define'; flow.approve(args)
        flow._transition(work, work_id, 'start-plan')
        for name in ('plan.md', 'handoff.md', 'validation-plan.md'):
            (directory / name).write_text(case['task'])
        (directory / 'verification-plan.json').write_text(json.dumps({
            'schema_version': 1, 'repair_limit': 2, 'evaluation_inputs': ['check.py'],
            'checks': [{'id': 'behavior', 'criterion': case['criterion'], 'argv': [sys.executable, 'check.py']}]}))
        args.stage = 'plan'; flow.approve(args)
        flow._transition(work, work_id, 'start-implementation')
        for name in ('implementation-evidence.md', 'handback.md'):
            (directory / name).write_text('Scripted fixture evidence, not agent performance.')
        return directory

    directory = setup('trial')

    def capture():
        nonlocal sequence
        sequence += 1
        if modern:
            return flow.check(Namespace(**{**vars(args), 'check_id': 'behavior', 'session_id': f'scripted-{sequence}',
                'assignment_id': 'frozen-fixture', 'environment': 'scripted Python fixture', 'timeout': 5}))
        result = subprocess.run([sys.executable, 'check.py'], cwd=work, capture_output=True, timeout=5,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        log = directory / f'baseline-check-{sequence}.log'
        log.write_bytes(result.stdout + result.stderr)
        return {'exit_code': result.returncode, 'status': 'passed' if result.returncode == 0 else 'failed',
                'log': {'path': log.relative_to(work).as_posix()}}

    def fix():
        (work / 'subject.py').write_text('def add(a, b):\n    return a + b\n')

    def handoff():
        args.stage = 'implement'
        try:
            flow.approve(args)
            return {'advanced': True}
        except ValueError as exc:
            return {'advanced': False, 'reason': str(exc)}

    def independent():
        # The executable evaluator is deliberately outside the worker tree.
        evaluator = work.parent / 'independent.py'
        evaluator.write_text('import sys\nsys.path.insert(0, sys.argv[1])\n' + case['external'])
        result = subprocess.run([sys.executable, str(evaluator), str(work)], capture_output=True, timeout=5,
                                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        return {'passed': result.returncode == 0, 'exit_code': result.returncode,
                'evaluator_sha256': hashlib.sha256(case['external'].encode()).hexdigest(),
                'stdout': result.stdout.decode(errors='replace'), 'stderr': result.stderr.decode(errors='replace')}

    def repair():
        if not modern:
            return {'status': 'unbounded_scripted_retry'}
        proof = directory / f'failure-{sequence}.md'
        proof.write_text(f'Actual failed check {sequence}; repair only the frozen behavior.')
        return flow.repair(Namespace(**{**vars(args), 'check_id': 'behavior', 'specialist': 'lead-developer',
            'scope': 'frozen failed behavior only', 'reason': 'recorded fixture failure',
            'failure_evidence': proof.relative_to(work).as_posix()}))

    result = {'case': case['id'], 'contract': 'candidate' if modern else 'baseline'}
    if case['id'] in ('ordinary', 'stale'):
        fix(); result['check'] = capture()
        if case['id'] == 'stale':
            (work / 'subject.py').write_text('def add(a, b):\n    return a - b\n')
        result['handoff'] = handoff()
        result['external'] = independent()
    elif case['id'] == 'adversarial':
        (work / 'subject.py').write_text('def move(position, force, dt, goal):\n    return goal\n')
        (work / 'check.py').write_text('assert True\n')
        result['check'] = capture(); result['handoff'] = handoff(); result['external'] = independent()
        # Implementation-only shortcut passes the original example but fails
        # unseen force/dt and zero-force cases. It is caught by external review.
        for name, content in case['files'].items():
            (work / name).write_text(content)
        directory = setup('shortcut')
        result['implementation_shortcut'] = {'external_required': True}
        (work / 'subject.py').write_text('def move(position, force, dt, goal):\n    return 0.5\n')
        result['implementation_shortcut']['check'] = capture()
        result['implementation_shortcut']['handoff'] = handoff()
        result['implementation_shortcut']['external'] = independent()
        result['implementation_shortcut']['approved_sample_passed'] = subprocess.run(
            [sys.executable, 'check.py'], cwd=work, capture_output=True,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}).returncode == 0
    else:
        result['initial_failure'] = capture()
        repair()
        (work / 'check.py').write_text('from subject import add\nassert add(2, 3) == 5\n')
        fix(); result['repaired_check'] = capture()
        if modern:
            import verification
            proof = directory / 'equivalence.md'
            proof.write_text('Import spelling fixed, exact assertion retained.\n' + json.dumps({
                'before': result['initial_failure']['log'], 'after': result['repaired_check']['log']}))
            verification.review_change(work, runstate.status(args.work_id, work), 'independent-fixture-reviewer',
                'external-review-session', 'Only the misspelled import changed; addition assertion is unchanged.',
                proof.relative_to(work).as_posix(), 'equivalent')
        result['handoff'] = handoff(); result['external'] = independent()
        # A separate subcase starts with the frozen correct import repair and
        # persistent product failure; it does not change the accepted criterion.
        (work / 'subject.py').write_text('def add(a, b):\n    return a - b\n')
        directory = setup('persistent')
        capture()
        statuses = []
        for _ in range(3):
            allocated = repair()
            statuses.append(allocated.get('status', allocated.get('state')))
            if allocated.get('status') == 'blocked':
                break
            captured = capture()
            if modern and runstate.status(args.work_id, work)['state'] == 'blocked':
                # Resume proves the counter survives, but cannot buy a third repair.
                flow._transition(work, args.work_id, 'resume')
        result['repair_allocations'] = statuses
        result['persistent_state'] = runstate.status(args.work_id, work)['state']
    # The external reviewer never accepts a shortcut, even if a handoff advances.
    result['external_acceptance_recommendation'] = bool(result['handoff']['advanced'] and result['external']['passed'])
    result['aggregate_generated_tokens'] = None
    result['model_cost'] = None
    result['human_review_seconds'] = None
    result['recorded_artifacts'] = {
        p.relative_to(work).as_posix(): p.read_text()
        for p in sorted((work / '.flow/runs').rglob('*'))
        if p.is_file() and (p.suffix == '.log' or p.name in {'verification.json', 'verification-plan.json', 'events.jsonl'}
                            or p.name.startswith('failure-') or p.name == 'equivalence.md')}
    return result


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--driver-source', type=Path)
    parser.add_argument('--case')
    parser.add_argument('--work', type=Path)
    args = parser.parse_args()
    frozen = json.loads(FIXTURE.read_text())
    freeze = json.loads((REPO / 'docs/evidence/verification-v1/freeze.json').read_text())
    for path, expected in freeze['files'].items():
        if hashlib.sha256((REPO / path).read_bytes()).hexdigest() != expected:
            raise SystemExit('Frozen evaluation changed; separate approval required')
    if args.driver_source:
        print(json.dumps(driver(args.driver_source, next(c for c in frozen['cases'] if c['id'] == args.case), args.work)))
        return
    observations = []
    for repeat in range(frozen['repetitions']):
        arms = [('baseline', args.baseline), ('candidate', REPO)]
        if repeat % 2:
            arms.reverse()
        for case in frozen['cases']:
            for arm, source in arms:
                with tempfile.TemporaryDirectory(prefix='flow-frozen-comparison-') as temp:
                    work = Path(temp) / 'worker'; work.mkdir()
                    clock = time.monotonic()
                    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--driver-source', str(source),
                        '--case', case['id'], '--work', str(work)], capture_output=True, text=True, timeout=120,
                        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
                    if proc.returncode:
                        raise SystemExit(proc.stderr + proc.stdout)
                    row = json.loads(proc.stdout)
                    expected_handoff = case['id'] in ('ordinary', 'repair') if arm == 'candidate' else True
                    if row['handoff']['advanced'] != expected_handoff:
                        raise SystemExit(f"Unexpected {arm} gate result for {case['id']}: {row}")
                    if row['external']['passed'] != (case['id'] in ('ordinary', 'repair')):
                        raise SystemExit(f"External evaluator disagrees with frozen {case['id']} outcome")
                    if case['id'] == 'adversarial' and (row['implementation_shortcut']['external']['passed']
                            or not row['implementation_shortcut']['approved_sample_passed']):
                        raise SystemExit('Shortcut control did not expose the intended coverage gap')
                    if case['id'] == 'repair' and arm == 'candidate' and row['repair_allocations'][-1] != 'blocked':
                        raise SystemExit('Candidate allowed a third repair allocation')
                    row.update(arm=arm, repeat=repeat + 1, scripted_wall_seconds=round(time.monotonic() - clock, 3))
                    observations.append(row)
    output = {'kind': 'deterministic_scripted_probes', 'live_model_runs': 0,
              'fixture_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
              'baseline': frozen['baseline'], 'candidate_diff_required': True, 'observations': observations,
              'behavioral_gain_claim': None}
    output['source_files'] = {
        arm: {name: hashlib.sha256((source / name).read_bytes()).hexdigest() if (source / name).is_file() else None
              for name in ('cli/openhands_flow.py', 'cli/runstate.py', 'cli/verification.py', 'cli/delivery_control.py')}
        for arm, source in (('baseline', args.baseline), ('candidate', REPO))}
    output['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'kind': output['kind'], 'observations': len(observations), 'live_model_runs': 0}))


if __name__ == '__main__':
    main()
