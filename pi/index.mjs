import { resolve } from 'node:path';
import { IrisChannel } from '../common/channel.mjs';

export default function irisExtension(pi) {
  let channel;
  let waiting;
  let answer = '';
  pi.on('session_start', async (_event, ctx) => {
    const stateDir = process.env.IRIS_PI_STATE_DIR;
    if (!stateDir) return;
    channel = new IrisChannel({ stateDir: resolve(stateDir), bridgeUrl: process.env.IRIS_PI_BRIDGE_URL }, {
      report: message => ctx.ui.notify(message, 'warning'),
      handle: async job => {
        // A terminal run already in progress retains its response and privacy.
        while (!ctx.isIdle()) {
          if (channel.stopped) throw new Error('Session closed.');
          await new Promise(resolveWait => setTimeout(resolveWait, 250));
        }
        answer = '';
        return new Promise((resolveReply, rejectReply) => {
          waiting = { resolve: resolveReply, reject: rejectReply };
          try { pi.sendUserMessage(job.text, { expandPromptTemplates: false }); }
          catch (error) { waiting = undefined; rejectReply(error); }
        });
      },
      control: async job => {
        if (job.text.trim() !== '/stop') return false;
        if (waiting) await ctx.abort();
        await channel.send(`control:${job.id}`, 'Stopped the current Iris task.');
        return true;
      },
    });
    await channel.start();
  });
  pi.on('agent_end', async event => {
    if (!waiting) return;
    const last = event.messages.filter(message => message.role === 'assistant').at(-1);
    if (last?.stopReason === 'error' || last?.stopReason === 'aborted') {
      waiting.resolve(last.stopReason === 'aborted' ? 'Task stopped.' : 'The model could not complete the task. Check the Pi session.');
      waiting = undefined;
      return;
    }
    answer = (last?.content ?? []).filter(part => part.type === 'text').map(part => part.text).join('\n');
  });
  pi.on('agent_settled', async () => {
    if (!waiting) return;
    waiting.resolve(answer);
    waiting = undefined;
  });
  pi.on('session_shutdown', async () => {
    if (channel) channel.stopped = true;
    if (waiting) { waiting.reject(new Error('Pi session closed.')); waiting = undefined; }
    await channel?.stop();
    channel = undefined;
  });
  pi.registerCommand('iris', {
    description: 'Show Iris Chat connection status',
    handler: async (_args, ctx) => ctx.ui.notify(channel ? 'Iris Chat is connected to this session.' : 'Set IRIS_PI_STATE_DIR to a paired Iris profile before starting Pi.', 'info'),
  });
}
