"""Private state stays untracked without touching project Git configuration."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from poc.artifacts import Artifacts


class StateIgnoreTests(unittest.TestCase):
    def test_generated_state_is_ignored_and_user_ignore_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            subprocess.run(['git','init','-q',str(project)],check=True)
            exclude = project/'.git/info/exclude'; before = exclude.read_bytes()
            artifacts = Artifacts(project,'fixture')
            artifacts.publish('contexts','project',{'fixture':True})
            result = subprocess.run(['git','-C',str(project),'status','--porcelain'],
                                    capture_output=True,text=True,check=True,
                                    env={**os.environ,'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1'})
            self.assertEqual(result.stdout,'')
            self.assertEqual(exclude.read_bytes(),before)
            ignore = project/'.glg/.gitignore'
            self.assertEqual(ignore.read_text(),'*\n')
            ignore.write_text('# user-owned\n*\n')
            artifacts.publish('contexts','another',{'fixture':True})
            self.assertEqual(ignore.read_text(),'# user-owned\n*\n')
