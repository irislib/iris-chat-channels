import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

export class IrisClient {
  constructor(account) {
    this.account = account;
    this.pending = new Map();
    this.sequence = 0;
    if (account.bridgeUrl && account.bridgeUrl !== 'http://127.0.0.1:8765') throw new Error('Iris managed transport must use its isolated loopback endpoint.');
  }

  async open() {
    if (!this.account.bridgeUrl) {
      this.child = spawn(this.account.pythonPath ?? 'python3', [fileURLToPath(new URL('../hermes/transport.py', import.meta.url)),
        'stdio', '--state', this.account.stateDir, '--binary', this.account.irisPath ?? 'iris'], { stdio: ['pipe', 'pipe', 'ignore'] });
      this.lines = createInterface({ input: this.child.stdout });
      this.lines.on('line', line => {
        try {
          const response = JSON.parse(line);
          const pending = this.pending.get(response.id);
          if (pending) {
            clearTimeout(pending.timer); this.pending.delete(response.id);
            response.ok ? pending.resolve(response.result) : pending.reject(new Error('Iris operation failed; inspect channel diagnostics.'));
          }
        } catch { this.failPending(); }
      });
      this.child.on('error', () => this.failPending());
      this.child.on('exit', () => this.failPending());
    }
    return this.call('health');
  }

  failPending() {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timer);
      pending.reject(new Error('Iris transport exited. Check Python 3, iris, and the channel pairing.'));
    }
    this.pending.clear();
  }

  async call(op, data = {}) {
    if (this.account.bridgeUrl) {
      const response = await fetch(this.account.bridgeUrl+'/channel/'+op, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), signal: AbortSignal.timeout(55000), redirect: 'error',
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error('Iris bridge operation failed; check transport diagnostics.');
      return result.result;
    }
    if (!this.child || this.child.exitCode !== null || this.child.killed) throw new Error('Iris transport is not running.');
    const id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new Error('Iris operation timed out; delivery may be unconfirmed.')); }, 60000);
      this.pending.set(id, { resolve, reject, timer });
      this.child.stdin.write(JSON.stringify({ id, op, data })+'\n', error => {
        if (error) { clearTimeout(timer); this.pending.delete(id); reject(new Error('Iris transport closed.')); }
      });
    });
  }

  async close() {
    if (this.child && this.child.exitCode === null && !this.child.killed) {
      this.child.stdin.end();
      const timer = setTimeout(() => this.child.kill('SIGTERM'), 10000);
      await new Promise(resolve => this.child.once('exit', resolve));
      clearTimeout(timer);
    }
    this.lines?.close();
    this.failPending();
  }
}
