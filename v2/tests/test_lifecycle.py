import subprocess,time,unittest
from poc.lifecycle import ProcessScope

class LifecycleTests(unittest.TestCase):
 def test_cancel_tracks_child_in_different_process_group(self):
  # Child deliberately setsid; a root-process-group-only check would miss it.
  import sys
  script='import subprocess,time; subprocess.Popen(["/bin/sleep","60"],start_new_session=True); time.sleep(60)'
  child=subprocess.Popen([sys.executable,'-c',script],start_new_session=True)
  scope=ProcessScope(child.pid)
  try:
   deadline=time.monotonic()+3
   while len(scope.known)<2 and time.monotonic()<deadline:time.sleep(.05);scope.observe()
   self.assertGreaterEqual(len(scope.known),2)
   result=scope.stop();child.wait(timeout=5)
   self.assertFalse(result['signal_errors'])
   # Reap/exit propagation is asynchronous; wait without resubmitting work.
   deadline=time.monotonic()+3
   while scope.observe() and time.monotonic()<deadline:time.sleep(.05)
   self.assertFalse(scope.observe())
  finally:
   if child.poll() is None:scope.stop();child.wait(timeout=5)

 def test_snapshot_ignores_zombies_and_keeps_live_identity(self):
  from unittest.mock import patch
  from poc.lifecycle import snapshot
  rows = '100 1 Z Tue Nov 3 04:27:08 2026\n101 1 S Tue Nov 3 04:27:09 2026\n'
  with patch('poc.lifecycle.subprocess.check_output', return_value=rows):
   self.assertEqual(snapshot(), {101: {'parent': 1, 'birth': 'Tue Nov 3 04:27:09 2026'}})

 def test_pid_reuse_does_not_authorize_cancellation(self):
  from unittest.mock import patch
  original = {100: {'parent': 1, 'birth': 'original'}}
  reused = {100: {'parent': 1, 'birth': 'new'}}
  with patch('poc.lifecycle.snapshot', side_effect=[original, reused, reused, reused]), patch('poc.lifecycle.os.kill') as kill, patch('poc.lifecycle.time.sleep'):
   scope = ProcessScope(100)
   self.assertEqual(scope.stop()['alive'], [])
   kill.assert_not_called()
