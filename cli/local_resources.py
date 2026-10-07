"""Read-only local-agent resource observations and experimental stop policy.

Percentage availability is diagnostic only; unknown pressure is never critical.
"""
from dataclasses import dataclass
import re

PRESSURE_NAMES = {1: 'normal', 2: 'warning', 4: 'critical'}
MIB = 1024 * 1024
CUMULATIVE_VM = ('Pages compressed', 'Pages decompressed', 'Pageins', 'Pageouts', 'Swapins', 'Swapouts')
GAUGE_VM = ('Pages free', 'Pages active', 'Pages inactive', 'Pages speculative', 'Pages wired down',
            'Pages purgeable', 'Pages used by compressor', 'Pages stored in compressor')

def parse_vm_stat(text):
    size = re.search(r'page size of (\d+) bytes', text)
    if not size:
        raise ValueError('VM page size missing')
    counters = {}
    for line in text.splitlines():
        match = re.match(r'\s*"?([^":]+)"?:\s*(\d+)\.?\s*$', line)
        if match:
            counters[match.group(1).strip()] = int(match.group(2))
    for source, target in [('Pages occupied by compressor', 'Pages used by compressor'), ('Compressions', 'Pages compressed'), ('Decompressions', 'Pages decompressed')]:
        if source in counters:
            counters[target] = counters[source]
    required = ('Pages free', 'Pages wired down', 'Pages used by compressor', *CUMULATIVE_VM)
    if any(name not in counters for name in required):
        raise ValueError('Required VM counters missing')
    return {'page_size': int(size.group(1)), 'pages': counters,
            'bytes': {name: value * int(size.group(1)) for name, value in counters.items()}}

def interval_rates(before, after):
    seconds = after['monotonic'] - before['monotonic']
    if seconds <= 0:
        return {'seconds': seconds, 'valid': False}
    result = {'seconds': seconds, 'valid': True, 'vm': {}, 'gauges': {}}
    for name in CUMULATIVE_VM:
        delta = after['vm']['bytes'][name] - before['vm']['bytes'][name]
        result['vm'][name] = {'delta_bytes': delta if delta >= 0 else None,
                              'bytes_per_second': delta / seconds if delta >= 0 else None,
                              'counter_reset': delta < 0}
    for name in GAUGE_VM:
        if name in before['vm']['bytes'] and name in after['vm']['bytes']:
            result['gauges'][name] = {'delta_bytes': after['vm']['bytes'][name] - before['vm']['bytes'][name]}
    result['swap_usage_delta_mib'] = after['swap_used_mib'] - before['swap_used_mib']
    return result

def allocation_error(error):
    if not error:
        return False
    return bool(re.search(r'(?:^|:\s)(?:MemoryError|std::bad_alloc)\b|out of memory|'
                          r'failed to allocate|cannot allocate memory|allocation failed|'
                          r'requires more .*memory|not enough .*memory', error, re.I))

@dataclass(frozen=True)
class Thresholds:
    warning_seconds: float = 30.0
    paging_window_seconds: float = 30.0
    min_swapout_bytes: int = 64 * MIB
    min_positive_intervals: int = 3
    recent_growth_seconds: float = 10.0
    service_floor_seconds: float = 2.0
    service_baseline_multiplier: float = 10.0
    service_slow_samples: int = 3
    missing_pressure_samples: int = 3

class PressurePolicy:
    def __init__(self, baseline_service_latency, thresholds=Thresholds()):
        self.thresholds = thresholds
        self.baseline_service_latency = baseline_service_latency
        self.warning_since = None
        self.history = []
        self.slow_service_count = 0
        self.missing_count = 0

    def observe(self, sample, model_errors=()):
        t = self.thresholds
        now = sample['monotonic']
        level = sample.get('pressure_raw')
        note = {'action': 'continue', 'reason': None,
                'pressure': PRESSURE_NAMES.get(level, 'unknown'),
                'low_availability_diagnostic': sample.get('availability_percent') is not None and sample['availability_percent'] < 20,
                'warning_elapsed_seconds': 0.0}
        if level == 4:
            return {**note, 'action': 'stop', 'reason': 'Kernel critical memory pressure'}
        if any(allocation_error(error) for error in model_errors):
            return {**note, 'action': 'stop', 'reason': 'Recorded model/runtime allocation error'}
        if level not in PRESSURE_NAMES or sample.get('telemetry_incomplete', False):
            self.missing_count += 1
            self.warning_since = None
            self.history = []
            self.slow_service_count = 0
            note['telemetry_diagnostic'] = 'Pressure telemetry unavailable or incomplete'
            note['missing_samples'] = self.missing_count
            return note
        self.missing_count = 0
        if level == 1:
            self.warning_since = None
            self.history = []
            self.slow_service_count = 0
            return note
        if self.warning_since is None:
            self.warning_since = now
        self.history.append(sample)
        while len(self.history) > 1 and self.history[1]['monotonic'] <= now - t.paging_window_seconds:
            self.history.pop(0)
        elapsed = now - self.warning_since
        note['warning_elapsed_seconds'] = elapsed
        latency = sample.get('service_latency_seconds')
        limit = max(t.service_floor_seconds, (self.baseline_service_latency or 0) * t.service_baseline_multiplier)
        service_slow = sample.get('service_timeout', False) or (latency is not None and latency > limit)
        self.slow_service_count = self.slow_service_count + 1 if service_slow else 0
        note['service_slow_samples'] = self.slow_service_count
        note['service_latency_threshold_seconds'] = limit
        if elapsed < t.warning_seconds:
            return note
        if self.slow_service_count >= t.service_slow_samples:
            return {**note, 'action': 'stop', 'reason': 'Sustained kernel warning plus repeated local service responsiveness loss'}
        if len(self.history) < 2:
            return note
        anchor = self.history[0]
        delta = sample['vm']['bytes']['Swapouts'] - anchor['vm']['bytes']['Swapouts']
        positive = []
        for before, after in zip(self.history, self.history[1:]):
            if after['vm']['bytes']['Swapouts'] > before['vm']['bytes']['Swapouts']:
                positive.append(after['monotonic'])
        note['window_swapout_growth_bytes'] = max(0, delta)
        note['positive_swapout_intervals'] = len(positive)
        note['window_seconds'] = now - anchor['monotonic']
        note['swap_usage_growth_mib'] = sample['swap_used_mib'] - anchor['swap_used_mib']
        if (delta >= t.min_swapout_bytes and len(positive) >= t.min_positive_intervals
                and positive[-1] >= now - t.recent_growth_seconds):
            return {**note, 'action': 'stop', 'reason': 'Sustained kernel warning plus continuing swap-out growth'}
        return note

import json
import platform
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone


def _command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=2)
        return {'command': args, 'stdout': result.stdout, 'stderr': result.stderr,
                'exit_code': result.returncode}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'command': args, 'stdout': '', 'stderr': str(exc), 'exit_code': None}


def collect_sample(endpoint='http://127.0.0.1:11434'):
    """Observe OS and Ollama health without sending inference or changing state."""
    sample = {'monotonic': time.monotonic(), 'utc': datetime.now(timezone.utc).isoformat(),
              'platform': platform.system(), 'pressure_raw': None,
              'vm': {'bytes': {}, 'pages': {}, 'page_size': None},
              'swap_used_mib': None, 'telemetry_incomplete': True, 'raw': {}}
    if sample['platform'] == 'Darwin':
        for key, args in [('kernel', ['sysctl', '-n', 'kern.memorystatus_vm_pressure_level']),
                          ('vm_stat', ['vm_stat']), ('swapusage', ['sysctl', 'vm.swapusage'])]:
            sample['raw'][key] = _command(args)
        try:
            raw = sample['raw']
            if any(row['exit_code'] != 0 for row in raw.values()):
                raise ValueError('OS observation command failed')
            sample['pressure_raw'] = int(raw['kernel']['stdout'].strip())
            sample['vm'] = parse_vm_stat(raw['vm_stat']['stdout'])
            used = re.search(r'used\s*=\s*([\d.]+)([MG])', raw['swapusage']['stdout'])
            if used is None:
                raise ValueError('Swap usage missing')
            sample['swap_used_mib'] = float(used.group(1)) * (1024 if used.group(2) == 'G' else 1)
            sample['telemetry_incomplete'] = sample['pressure_raw'] not in PRESSURE_NAMES
        except (ValueError, KeyError) as exc:
            sample['telemetry_diagnostic'] = str(exc)
    else:
        sample['telemetry_diagnostic'] = 'Kernel pressure collection unsupported on this platform'
    sample['pressure_name'] = PRESSURE_NAMES.get(sample['pressure_raw'], 'unknown')
    started = time.monotonic()
    try:
        with urllib.request.urlopen(endpoint.rstrip('/') + '/api/ps', timeout=2) as response:
            sample['models'] = json.load(response).get('models', [])
        sample['service_timeout'] = False
    except Exception as exc:
        sample['models'] = []
        sample['service_timeout'] = True
        sample['service_error'] = f'{type(exc).__name__}: {exc}'
    sample['service_latency_seconds'] = time.monotonic() - started
    sample['gpu_residency_estimate'] = [
        {key: model.get(key) for key in ('model', 'name', 'size', 'size_vram', 'context_length')}
        for model in sample['models']]
    sample['collection_seconds'] = time.monotonic() - sample['monotonic']
    return sample


class ResourcePressureError(RuntimeError):
    """Observed resource distress requires cancellation/backoff before another call."""


class ResourceMonitor:
    """Background observer; callback receives (sample, decision).

    A stop decision is latched. The caller owns cancellation of in-flight inference;
    check() prevents subsequent calls. No automatic unload, restart or replay occurs.
    """
    def __init__(self, endpoint='http://127.0.0.1:11434', interval_seconds=5,
                 callback=None, thresholds=Thresholds(), collector=None):
        if interval_seconds <= 0:
            raise ValueError('Resource sampling interval must be positive')
        self.endpoint = endpoint
        self.interval_seconds = interval_seconds
        self.callback = callback
        self.collector = collector or (lambda: collect_sample(endpoint))
        self.policy = PressurePolicy(None, thresholds)
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self.last_sample = None
        self.last_decision = None
        self.stop_reason = None
        self.observer_error = None

    def observe(self, sample, model_errors=()):
        with self._lock:
            if self.policy.baseline_service_latency is None and not sample.get('service_timeout'):
                self.policy.baseline_service_latency = sample.get('service_latency_seconds')
            decision = self.policy.observe(sample, model_errors)
            if self.last_sample is not None and not sample.get('telemetry_incomplete') and not self.last_sample.get('telemetry_incomplete'):
                sample['interval_rates'] = interval_rates(self.last_sample, sample)
            self.last_sample, self.last_decision = sample, decision
            if decision['action'] == 'stop' and self.stop_reason is None:
                self.stop_reason = decision['reason']
        if self.callback:
            self.callback(sample, decision)
        return decision

    def record_error(self, error):
        detail = f'{type(error).__name__}: {error}' if isinstance(error, BaseException) else str(error)
        if allocation_error(detail):
            with self._lock:
                self.stop_reason = self.stop_reason or 'Recorded model/runtime allocation error'
        self.check()

    def check(self):
        with self._lock:
            reason = self.stop_reason
        if reason:
            raise ResourcePressureError(reason)

    def _run(self):
        while not self._done.is_set():
            try:
                self.observe(self.collector())
            except Exception as exc:
                self.observer_error = f'{type(exc).__name__}: {exc}'
            if self.stop_reason:
                return
            self._done.wait(self.interval_seconds)

    def start(self):
        if self._thread is not None:
            raise RuntimeError('Resource monitor already started')
        self.observe(self.collector())
        self.check()
        self._thread = threading.Thread(target=self._run, name='flow-local-resources', daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._done.set()
        if self._thread is not None:
            self._thread.join(timeout=8)

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
