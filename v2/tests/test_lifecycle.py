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
