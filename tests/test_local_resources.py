"""Deterministic resource policy regressions from corrected local-model POC."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from local_resources import (CUMULATIVE_VM, MIB, PressurePolicy, ResourceMonitor,
                             ResourcePressureError, collect_sample, interval_rates,
                             parse_vm_stat)


def sample(t=0, level=1, swap=0, latency=.01, timeout=False):
    return {'monotonic': t, 'pressure_raw': level, 'availability_percent': 1,
            'vm': {'bytes': {key: swap if key == 'Swapouts' else 0 for key in CUMULATIVE_VM}},
            'swap_used_mib': 2000, 'service_latency_seconds': latency,
            'service_timeout': timeout, 'telemetry_incomplete': False}


class PressureTests(unittest.TestCase):
    def test_low_percentage_never_stops_normal_pressure(self):
        p = PressurePolicy(.01)
        for t in range(100):
            self.assertEqual(p.observe(sample(t, swap=t * 100 * MIB))['action'], 'continue')

    def test_critical_and_allocation_immediate(self):
        self.assertEqual(PressurePolicy(.01).observe(sample(level=4))['action'], 'stop')
        self.assertEqual(PressurePolicy(.01).observe(sample(), ['failed to allocate buffer'])['action'], 'stop')

    def test_warning_swap_requires_sustained_recent_growth(self):
        p = PressurePolicy(.01)
        for t in (0, 10, 20):
            self.assertEqual(p.observe(sample(t, 2, t * 3 * MIB))['action'], 'continue')
        self.assertEqual(p.observe(sample(30, 2, 90 * MIB))['action'], 'stop')

    def test_old_swap_burst_or_warning_alone_not_distress(self):
        p = PressurePolicy(.01)
        for t in (0, 10, 20, 30, 40, 50):
            self.assertEqual(p.observe(sample(t, 2, 100 * MIB))['action'], 'continue')

    def test_warning_slow_service_then_normal_resets(self):
        p = PressurePolicy(.01)
        for t in (0, 10, 20):
            self.assertEqual(p.observe(sample(t, 2, latency=3))['action'], 'continue')
        self.assertEqual(p.observe(sample(30, 2, latency=3))['action'], 'stop')
        self.assertEqual(p.observe(sample(31, 1))['action'], 'continue')
        self.assertEqual(p.observe(sample(32, 2, latency=3))['action'], 'continue')

    def test_unknown_pressure_never_invents_stop(self):
        p = PressurePolicy(.01)
        for t in range(10):
            self.assertEqual(p.observe(sample(t, None, latency=10))['action'], 'continue')

    def test_counter_reset_and_zero_interval(self):
        rates = interval_rates(sample(0, swap=100), sample(5, swap=1))
        self.assertTrue(rates['vm']['Swapouts']['counter_reset'])
        self.assertIsNone(rates['vm']['Swapouts']['bytes_per_second'])
        self.assertFalse(interval_rates(sample(), sample())['valid'])

    def test_parse_mac_vm_aliases_and_page_size(self):
        text = 'Mach Virtual Memory Statistics: (page size of 16384 bytes)\n'
        for key in ('Pages free', 'Pages wired down', 'Pages occupied by compressor',
                    'Compressions', 'Decompressions', 'Pageins', 'Pageouts', 'Swapins', 'Swapouts'):
            text += f'{key}: 2.\n'
        vm = parse_vm_stat(text)
        self.assertEqual(vm['bytes']['Pages compressed'], 32768)
        with self.assertRaises(ValueError):
            parse_vm_stat('missing counters')

    def test_stop_latched_and_callback_has_observed_sample(self):
        seen = []
        monitor = ResourceMonitor(callback=lambda s, d: seen.append((s, d)))
        monitor.observe(sample(level=4))
        monitor.observe(sample())
        with self.assertRaises(ResourcePressureError):
            monitor.check()
        self.assertEqual(len(seen), 2)
        with self.assertRaises(ResourcePressureError):
            ResourceMonitor().record_error(MemoryError())

    def test_unsupported_platform_diagnostic_no_os_commands(self):
        with patch('local_resources.platform.system', return_value='Linux'), \
                patch('local_resources._command') as command, \
                patch('local_resources.urllib.request.urlopen', side_effect=OSError('offline')):
            result = collect_sample()
        command.assert_not_called()
        self.assertTrue(result['telemetry_incomplete'])
        self.assertEqual(PressurePolicy(.01).observe(result)['action'], 'continue')


if __name__ == '__main__':
    unittest.main()
