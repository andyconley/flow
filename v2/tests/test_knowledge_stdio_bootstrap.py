"""Regression: package directory readable, its parent intentionally unreadable."""
import os,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path

@unittest.skipUnless(sys.platform=='darwin','macOS sandbox regression')
class KnowledgeStdioBootstrapTests(unittest.TestCase):
 def test_direct_package_bootstrap_without_parent_read_grant(self):
  with tempfile.TemporaryDirectory() as temporary:
   root=Path(temporary).resolve();package=root/'denied-parent/poc';runtime=package/'knowledge_runtime';runtime.mkdir(parents=True)
   (package/'__init__.py').write_text('');(runtime/'__init__.py').write_text('')
   (runtime/'server.py').write_text('class Server:\n def run(self,**kwargs): print("MCP_PACKAGE_LOADED")\nmcp=Server()\n')
   shutil.copyfile(Path(__file__).resolve().parents[1]/'poc/knowledge_runtime/stdio.py',runtime/'stdio.py')
   scope=root/'scope.sb';scope.write_text('(version 1)\n(allow default)\n(deny file-read* (subpath "'+str(package.parent)+'"))\n(allow file-read* (subpath "'+str(package)+'"))\n')
   env=dict(os.environ);env.pop('PYTHONPATH',None)
   result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(scope),sys.executable,str(runtime/'stdio.py'),str(root/'knowledge')],cwd=root,env=env,text=True,capture_output=True,timeout=10)
   self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'MCP_PACKAGE_LOADED')
