"""Replay normalized native events through the actual pinned adapter definitions."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from poc.codex_adapter_guard import guarded_source
from poc.runtime_env import node_binary

ROOT = Path(__file__).resolve().parents[1]


class CommandClassificationTests(unittest.TestCase):
    def test_real_event_handler_keeps_exits_separate_from_tool_failure(self):
        source = guarded_source((ROOT/'runtime/adapters/node_modules/@agentclientprotocol/codex-acp/dist/index.js').read_text())
        marker = 'if (process.argv.includes("--version")) {'
        self.assertEqual(source.count(marker), 1)
        # Remove only the executable entrypoint. No Codex subprocess or inference.
        definitions = source.split(marker)[0]+'\nexport {CodexEventHandler, AcpToolCallRenderer, CommandReporter};\n'
        program = r'''
import {CodexEventHandler,AcpToolCallRenderer,CommandReporter} from './adapter.mjs';
const handler=Object.create(CodexEventHandler.prototype);
handler.renderer=new AcpToolCallRenderer({airClient:false,air:{},terminalOutputKey:()=>null});
handler.agentMessagePhases=new Map();
handler.commands=new CommandReporter();
handler.sessionState={clientCapabilities:{airClient:false,air:{}}};
const cases = [
 {id:'red',type:'commandExecution',status:'failed',command:'pytest -q',commandActions:[],exitCode:1,aggregatedOutput:'2 failed, 2 passed'},
 {id:'green',type:'commandExecution',status:'completed',command:'pytest -q',commandActions:[],exitCode:0,aggregatedOutput:'4 passed'},
 {id:'shell-denial',type:'commandExecution',status:'failed',command:'pytest -q',commandActions:[],exitCode:1,aggregatedOutput:'ls: Operation not permitted'},
 {id:'permission',type:'commandExecution',status:'failed',command:'pytest -q',commandActions:[],exitCode:1,aggregatedOutput:"PermissionError: [Errno 1] Operation not permitted: '/fixture'"},
 {id:'unknown-exit',type:'commandExecution',status:'failed',command:'pytest -q',commandActions:[],exitCode:null,aggregatedOutput:'transport failed'},
 {id:'edit',type:'fileChange',status:'failed',changes:[]},
 {id:'declined',type:'commandExecution',status:'declined',command:'fixture',commandActions:[],exitCode:1,aggregatedOutput:'opaque'},
 {id:'interrupted',type:'commandExecution',status:'interrupted',command:'fixture',commandActions:[],exitCode:1,aggregatedOutput:'opaque'}
];
const output=[];
for(const item of cases){
 await handler.createItemEvent({item});
 output.push(await handler.completeItemEvent({item}));
}
// Terminal commands retain their exit metadata AND raw output.
output.push(handler.renderer.render({toolCallId:'terminal',report:'complete',status:'failed',
 standard:{commandEnd:{output:'1 failed',exitCode:1,nativeStatus:'failed',terminal:true,streamed:false}}}));
console.log(JSON.stringify(output));
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'adapter.mjs').write_text(definitions)
            (root/'replay.mjs').write_text(program)
            result = subprocess.run([str(node_binary()), str(root/'replay.mjs')],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
        events = json.loads(result.stdout)
        for index in (0, 1, 2, 8):
            self.assertEqual(events[index]['status'], 'completed')
        self.assertEqual(events[0]['rawOutput']['exit_code'], 1)
        self.assertEqual(events[0]['rawOutput']['output'], '2 failed, 2 passed')
        self.assertEqual(events[0]['rawOutput']['goose.native.commandResult']['native_status'], 'failed')
        self.assertEqual(events[2]['rawOutput']['output'], 'ls: Operation not permitted')
        self.assertNotIn('goose.native.boundary', events[2]['rawOutput'])
        self.assertEqual(events[3]['status'], 'failed')
        self.assertEqual(events[3]['rawOutput']['goose.native.boundary']['code'], 'EPERM')
        self.assertEqual(events[4]['status'], 'failed')
        self.assertEqual(events[5]['status'], 'failed')
        self.assertEqual(events[6]['status'], 'failed')
        self.assertEqual(events[6]['rawOutput']['goose.native.boundary']['source'], 'codex_command_status')
        self.assertEqual(events[7]['status'], 'failed')
        self.assertEqual(events[8]['_meta']['terminal_exit']['exit_code'], 1)
        self.assertEqual(events[8]['rawOutput']['output'], '1 failed')
