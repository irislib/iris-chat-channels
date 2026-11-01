import { createHash } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { IrisClient } from '../openclaw/client.mjs';

/** One approved conversation. Host adapters own model execution and permissions. */
export class IrisChannel {
  constructor(account, { handle, control, report = () => {} }) {
    this.client = new IrisClient(account);
    this.handle = handle;
    this.control = control;
    this.report = report;
    this.pending = new Map();
    this.queue = [];
    this.stopped = false;
    this.busy = false;
  }

  async start() {
    const health = await this.client.open();
    if (!health.ready || !/^[a-f0-9]{64}$/.test(health.owner)) {
      await this.client.close();
      throw new Error('Iris is not paired and ready. Run the Iris setup command.');
    }
    this.owner = health.owner;
    this.loop = this.receive();
  }

  async send(key, text) {
    if (!text?.trim()) return;
    const digest = createHash('sha256').update(text).digest('hex');
    return this.client.call('send', { key: `${key}:${digest}`, text });
  }

  async receive() {
    while (!this.stopped) {
      try {
        if (this.pending.size < 16) {
          const job = await this.client.call('receive', { active: [...this.pending.keys()] });
          if (job) {
            if (job.owner !== this.owner) throw new Error('Iris contact changed; restart the channel.');
            this.pending.set(job.id, job);
            if (job.interrupted) {
              await this.send(`recovery:${job.id}`, 'My previous task was interrupted. I did not repeat it automatically. Send a new message to continue.');
              await this.finish(job);
            } else if (this.control && await this.control(job)) {
              await this.finish(job);
            } else {
              this.queue.push(job);
            }
          }
        }
        if (!this.busy && this.queue.length) this.processing = this.process(this.queue.shift());
        if (this.busy) await this.client.call('typing', { active: true });
      } catch {
        this.report('Iris is waiting for transport recovery; tasks are not replayed.');
      }
      await delay(1000);
    }
  }

  async finish(job) {
    await this.client.call('finish', { id: job.id });
    this.pending.delete(job.id);
  }

  async process(job) {
    this.busy = true;
    try {
      await this.client.call('seen', { id: job.id });
      await this.client.call('typing', { active: true });
      const text = await this.handle(job);
      if (this.stopped) return;
      await this.send(`reply:${job.id}`, text || 'The task ended without a text reply. Check the agent session.');
      await this.finish(job);
    } catch {
      // Leave an uncertain task claimed. Restart reports interruption instead of rerunning tools.
      this.report('Iris task or delivery failed; inspect the agent session. No automatic retry.');
    } finally {
      this.busy = false;
      await this.client.call('typing', { active: false }).catch(() => {});
    }
  }

  async stop() {
    this.stopped = true;
    await this.loop;
    await this.client.call('typing', { active: false }).catch(() => {});
    await this.client.close();
  }
}
