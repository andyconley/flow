"""Exercise security-sensitive peers without an HTTP listener or credentials."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]

class NativeDependencySecurity(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node') and (ROOT/'runtime/adapters/node_modules').is_dir(), 'locked native adapter dependencies required')
    def test_uri_body_parser_and_mcp_peer_integration(self):
        result=subprocess.run(['node',str(Path(__file__).with_name('dependency_security_smoke.cjs')),str(ROOT/'runtime/adapters')],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('"mcpInMemoryHandshake":"passed"',result.stdout)
        self.assertIn('"networkListener":false',result.stdout)

if __name__=='__main__':unittest.main()
