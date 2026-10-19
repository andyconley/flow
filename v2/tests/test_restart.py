"""Restart the real durable graph after process death during external submission."""
import multiprocessing,os,tempfile,unittest
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from poc.workflow import build

class CrashHarness:
 def __init__(self,marker,crash):self.marker=Path(marker);self.crash=crash
 def implement(self,s):
  if self.marker.exists():return {'status':'uncertain'}
  self.marker.write_text('one external submission')
  if self.crash:os._exit(73)
  raise AssertionError('first process must crash')
 def reconcile(self,s):return {'status':'blocked','reason':'external submission exists; must reconcile'}
 def review(self,s):raise AssertionError('unreconciled work cannot be reviewed')

def crash_run(root):
 with SqliteSaver.from_conn_string(str(Path(root)/'graph.sqlite')) as saver:
  graph=build(CrashHarness(Path(root)/'intent',True),lambda p:{'passed':True}).compile(checkpointer=saver)
  graph.invoke({'job_id':'crash','inputs':'digest','approved':'digest','workspace':root,'attempt':0},{'configurable':{'thread_id':'crash'}})

class RestartTests(unittest.TestCase):
 def test_fresh_process_restart_blocks_duplicate_submission(self):
  with tempfile.TemporaryDirectory() as root:
   process=multiprocessing.get_context('fork').Process(target=crash_run,args=(root,));process.start();process.join(10)
   if process.is_alive():process.terminate();process.join();self.fail('crash fixture did not finish')
   self.assertEqual(process.exitcode,73)
   with SqliteSaver.from_conn_string(str(Path(root)/'graph.sqlite')) as saver:
    graph=build(CrashHarness(Path(root)/'intent',False),lambda p:{'passed':True}).compile(checkpointer=saver)
    result=graph.invoke(None,{'configurable':{'thread_id':'crash'}})
   self.assertEqual(result['phase'],'blocked');self.assertEqual((Path(root)/'intent').read_text(),'one external submission')
