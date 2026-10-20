// Transparent adapter transport with private, bounded server-side tool evidence.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn } from 'node:child_process';

const [directory, adapter, ...args] = process.argv.slice(2);
const FRAME_LIMIT = 256 * 1024;
const FILE_LIMIT = 16 * 1024 * 1024;
let fd, written = 0, disabled = false, pending = Buffer.alloc(0), dropping = false;
function save(record) {
  if (disabled) return;
  try {
    const line = JSON.stringify(record) + '\n';
    if (written + Buffer.byteLength(line) > FILE_LIMIT - 1024) {
      fs.writeSync(fd, JSON.stringify({type:'capture_stopped', reason:'file_limit'}) + '\n');
      disabled = true;
      return;
    }
    fs.writeSync(fd, line);
    written += Buffer.byteLength(line);
  } catch {
    disabled = true;
    process.stderr.write('ACP evidence capture unavailable; transport continues.\n');
  }
}
try {
  fs.mkdirSync(directory, {recursive:true, mode:0o700});
  fs.chmodSync(directory, 0o700);
  fd = fs.openSync(path.join(directory, `${process.pid}-${crypto.randomUUID()}.jsonl`), 'wx', 0o600);
  save({type:'capture_started', version:1, frame_limit:FRAME_LIMIT, file_limit:FILE_LIMIT});
} catch {
  disabled = true;
  process.stderr.write('ACP evidence capture unavailable; transport continues.\n');
}
function frame(bytes) {
  if (!bytes.length) return;
  try {
    const message = JSON.parse(bytes.toString('utf8'));
    const update = message.params?.update?.sessionUpdate;
    if (message.method === 'session/update' && ['tool_call', 'tool_call_update'].includes(update)) {
      save({type:'server_tool_frame', frame:message});
    }
  } catch { save({type:'capture_gap', reason:'invalid_json'}); }
}
function capture(chunk) {
  if (disabled) return;
  // Buffer at most one bounded line, including when a provider emits no newline.
  let offset = 0;
  while (offset < chunk.length) {
    const newline = chunk.indexOf(10, offset);
    const end = newline < 0 ? chunk.length : newline;
    if (!dropping) {
      if (pending.length + end - offset > FRAME_LIMIT) {
        pending = Buffer.alloc(0); dropping = true;
        save({type:'capture_gap', reason:'frame_limit'});
      } else pending = Buffer.concat([pending, chunk.subarray(offset, end)]);
    }
    if (newline < 0) break;
    if (!dropping) frame(pending);
    pending = Buffer.alloc(0); dropping = false; offset = newline + 1;
  }
}
const child = spawn(process.execPath, [adapter, ...args], {stdio:['pipe','pipe','inherit']});
process.stdin.pipe(child.stdin);
child.stdin.on('error', error => { if (error.code !== 'EPIPE') process.stderr.write('ACP adapter input closed.\n'); });
child.stdout.on('data', capture);
child.stdout.pipe(process.stdout);
for (const signal of ['SIGINT','SIGTERM','SIGHUP']) process.on(signal, () => child.kill(signal));
child.on('error', () => { save({type:'capture_stopped', reason:'adapter_spawn_error'}); process.exitCode = 1; });
child.on('close', (code, signal) => {
  if (!dropping && pending.length) frame(pending);
  save({type:'adapter_closed', code, signal});
  if (fd !== undefined) fs.closeSync(fd);
  process.stdin.unpipe(child.stdin); process.stdin.destroy();
  if (signal) {
    process.removeAllListeners(signal);
    process.kill(process.pid, signal);
  } else process.exitCode = code ?? 1;
});
