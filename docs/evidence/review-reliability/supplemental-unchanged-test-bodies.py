"""Supplement unchanged assertions through already-ready SDK, no dependency install.

The original aggregate skip records are retained. Only obsolete wheelhouse skip
wrappers are unwrapped for these four named local-fixture tests; no assertions,
production code, network restrictions or credential behavior change.
"""
import inspect,os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
from tests.test_flow import FlowCliTests
import importlib.util
spec=importlib.util.spec_from_file_location('offline_route_probe',Path.cwd()/'cli/openhands_provision.py')
sys.path.insert(0,str(Path.cwd()/'cli'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert module.ready(os.environ['FLOW_PYTHON']), 'Existing pinned interpreter must already be SDK-ready'
names=['test_install_command_release_converts_from_develop','test_install_release_cleans_up_source_old_symlink_leftover','test_install_command_develop_converts_from_release','test_update_apply_in_release_mode_swaps_and_records_version']
for name in names:
 method=getattr(FlowCliTests,name)
 assert getattr(method,'__unittest_skip__',False)
 original=inspect.unwrap(method)
 assert original is not method
 setattr(FlowCliTests,name,original)
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(['tests.test_flow.FlowCliTests.'+n for n in names]))
raise SystemExit(not result.wasSuccessful())
