import tempfile,unittest
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from poc.workflow import build
from poc.contracts import digest_tree

class Harness:
 def __init__(self,status='completed'):self.calls=0;self.status=status;self.reviews=0
 def implement(self,s):self.calls+=1;return {'status':self.status,'coverage':{'passed':True}}
 def reconcile(self,s):return {'status':'blocked','reason':'unknown writer; no blind retry'}
 def review(self,s):self.reviews+=1;return {'passed':True,'candidate':digest_tree(s['workspace'])}

class WorkflowTests(unittest.TestCase):
 def run_graph(self,h,checker,approved='digest'):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
  state={'job_id':'test','inputs':'digest','approved':approved,'workspace':tmp.name,'attempt':0}
  saver=SqliteSaver.from_conn_string(':memory:')
  self.addCleanup(saver.__exit__,None,None,None);cp=saver.__enter__()
  return build(h,checker).compile(checkpointer=cp),state
 def test_auto_accept(self):
  h=Harness();g,s=self.run_graph(h,lambda p:{'passed':True})
  self.assertEqual(g.invoke(s,{'configurable':{'thread_id':'auto'}})['phase'],'reviewed-and-ready');self.assertEqual(h.calls,1)
 def test_correction_bound(self):
  h=Harness();g,s=self.run_graph(h,lambda p:{'passed':False})
  self.assertEqual(g.invoke(s,{'configurable':{'thread_id':'bound'}})['phase'],'blocked');self.assertEqual(h.calls,4)
 def test_uncertain_does_not_resubmit(self):
  h=Harness('uncertain');g,s=self.run_graph(h,lambda p:{'passed':True})
  self.assertEqual(g.invoke(s,{'configurable':{'thread_id':'uncertain'}})['phase'],'blocked');self.assertEqual(h.calls,1)
 def test_approval_digest(self):
  h=Harness();g,s=self.run_graph(h,lambda p:{'passed':True},'old');c={'configurable':{'thread_id':'approval'}}
  self.assertIn('__interrupt__',g.invoke(s,c));self.assertEqual(h.calls,0)
  self.assertEqual(g.invoke(Command(resume='wrong'),c)['phase'],'blocked');self.assertEqual(h.calls,0)
 def test_stale_review_rejected(self):
  h=Harness();h.review=lambda s:{'passed':True,'candidate':'stale'}
  g,s=self.run_graph(h,lambda p:{'passed':True})
  self.assertEqual(g.invoke(s,{'configurable':{'thread_id':'stale'}})['phase'],'blocked')
if __name__=='__main__':unittest.main()
