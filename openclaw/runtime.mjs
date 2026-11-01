import { createHash, randomUUID } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import { dispatchInboundDirectDm } from 'openclaw/plugin-sdk/channel-inbound';
import { sanitizeAssistantVisibleText } from 'openclaw/plugin-sdk/text-chunking';
import { IrisClient } from './client.mjs';
import { maybeOwner, normalizeOwner } from './identity.mjs';

let active;
const identity = { key: 'iris-public-key', normalizeEntry: maybeOwner, normalizeSubject: maybeOwner,
  sensitivity: 'pii', entryIdPrefix: 'iris-owner' };

export async function startAccount(ctx) {
  const client = new IrisClient(ctx.account);
  const jobs = new Map();
  let typing;
  const assertActive = () => { if (ctx.abortSignal.aborted) throw new Error('Iris channel stopped.'); };
  const warn = () => ctx.log?.warn?.('Iris transport is recovering. No task is replayed automatically.');
  try {
    const health = await client.open();
    if (health.owner !== ctx.account.owner || !health.ready) throw new Error('Iris pairing does not match this channel. Run openclaw iris setup.');
    const channelRuntime = ctx.channelRuntime;
    if (!channelRuntime?.inbound?.ingress?.resolveStable) throw new Error('Iris requires OpenClaw 2026.10.9 channel ingress.');
    active = { client, owner: health.owner, assertActive };
    ctx.setStatus({ accountId: 'default', running: true, connected: true, lifecycle: 'ready', lastError: null });
    typing = setInterval(() => { if (jobs.size) client.call('typing', { active: true }).catch(() => {}); }, 5000);

    const processJob = async job => {
      if (job.owner !== ctx.account.owner) throw new Error('Iris contact policy changed.');
      if (job.interrupted) {
        await client.call('send', { key: 'recovery:'+job.id, text: job.pending_reply || 'My previous task was interrupted. I did not repeat it automatically. Send a new message to continue.' });
        await client.call('finish', { id: job.id });
        return;
      }
      const resolveIngress = contextBinding => channelRuntime.inbound.ingress.resolveStable({
        channelId: 'iris', accountId: 'default', identity, cfg: ctx.cfg,
        subject: { stableId: job.owner }, conversation: { kind: 'direct', id: job.owner },
        contextBinding, dmPolicy: 'allowlist', allowFrom: [ctx.account.owner], useDefaultPairingStore: false,
        command: { modeWhenAccessGroupsOff: 'configured' },
      });
      const access = await resolveIngress();
      if (!access.senderAccess.allowed) throw new Error('Iris sender is not authorized.');
      assertActive();
      await client.call('seen', { id: job.id }).catch(() => {});
      await client.call('typing', { active: true }).catch(() => {});
      let sequence = 0;
      await dispatchInboundDirectDm({
        channelRuntime, cfg: ctx.cfg, channel: 'iris', channelLabel: 'Iris Chat', accountId: 'default',
        peer: { kind: 'direct', id: job.owner }, senderId: job.owner, senderAddress: 'iris:'+job.owner,
        recipientAddress: 'iris:default', conversationLabel: 'Approved Iris contact', rawBody: job.text,
        messageId: job.id, timestamp: job.created * 1000,
        commandAuthorized: access.commandAccess?.authorized,
        resolveChannelIngress: async binding => { assertActive(); return resolveIngress(binding); },
        deliver: async payload => {
          assertActive();
          if (payload.mediaUrl || payload.mediaUrls?.length) throw new Error('Iris currently supports text only.');
          const text = sanitizeAssistantVisibleText(payload.text ?? '');
          if (!text.trim()) return;
          const key = 'reply:'+job.id+':'+sequence+++':'+createHash('sha256').update(text).digest('hex');
          await client.call('send', { key, text });
        },
        onRecordError: warn, onDispatchError: warn,
      });
      await client.call('finish', { id: job.id });
    };

    while (!ctx.abortSignal.aborted) {
      try {
        if (jobs.size < 16) {
          const job = await client.call('receive', { active: [...jobs.keys()] });
          if (job) {
            const promise = processJob(job).catch(warn).finally(async () => {
              jobs.delete(job.id);
              if (!jobs.size) await client.call('typing', { active: false }).catch(() => {});
            });
            jobs.set(job.id, promise);
          }
        }
      } catch { warn(); }
      await delay(2000, undefined, { signal: ctx.abortSignal }).catch(() => {});
    }
  } finally {
    clearInterval(typing);
    if (active?.client === client) active = undefined;
    await Promise.allSettled(jobs.values());
    await client.call('typing', { active: false }).catch(() => {});
    await client.close();
    ctx.setStatus({ accountId: 'default', running: false, connected: false });
  }
}

export async function sendOutbound(params) {
  const current = active;
  if (!current || normalizeOwner(params.to) !== current.owner) throw new Error('Only the approved Iris contact is allowed; the gateway must be online.');
  current.assertActive();
  params.assertDirectAdapterHandoff?.();
  params.onPlatformSendDispatch?.();
  const result = await current.client.call('send', { key: 'outbound:'+randomUUID(), text: params.text });
  return { channel: 'iris', to: current.owner, messageId: result.message_id };
}
