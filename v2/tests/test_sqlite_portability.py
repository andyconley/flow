"""Read-only SQLite URIs work without SQLITE_USE_URI being a build default."""
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from poc import glg, history, monitoring


class SQLitePortabilityTests(unittest.TestCase):
    def test_all_readers_explicitly_enable_encoded_read_only_uris(self):
        with tempfile.TemporaryDirectory(prefix='sqlite-#%?-') as directory:
            root=Path(directory);project=root/'project';project.mkdir()
            key=hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:16]
            database=root/'state'/key/'work/workflow.sqlite';database.parent.mkdir(parents=True)
            with sqlite3.connect(database) as connection:
                connection.execute('CREATE TABLE checkpoints(thread_id,checkpoint_ns,checkpoint_id,type,checkpoint)')
                connection.execute('CREATE TABLE sessions(id,name)')
            before=database.read_bytes();original=sqlite3.connect;observed=[]
            def portable(path,*args,**kwargs):
                if isinstance(path,str) and path.startswith('file:'):
                    observed.append(kwargs.get('uri'))
                    if kwargs.get('uri') is not True:
                        raise sqlite3.OperationalError('URI parsing is disabled by this SQLite build')
                return original(path,*args,**kwargs)
            with patch('sqlite3.connect',side_effect=portable):
                with glg.checkpoint_snapshot(database) as saver:
                    self.assertEqual(saver.conn.execute('SELECT count(*) FROM checkpoints').fetchone()[0],0)
                history.current_runs(project,root/'state')
                monitoring.report(database=database)
            self.assertEqual(observed,[True,True,True])
            self.assertEqual(database.read_bytes(),before)
