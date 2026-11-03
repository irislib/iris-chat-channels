import { createChatChannelPlugin } from 'openclaw/plugin-sdk/channel-core';
import { createChannelMessageAdapterFromOutbound } from 'openclaw/plugin-sdk/channel-outbound';
import { chunkTextForOutbound, sanitizeAssistantVisibleText } from 'openclaw/plugin-sdk/text-chunking';
import { irisApprovals } from './approvals.mjs';
import { normalizeOwner, maybeOwner } from './identity.mjs';

export function resolveAccount(cfg, accountId = 'default') {
  if (accountId && accountId !== 'default') throw new Error('Iris currently supports one identity per OpenClaw profile.');
  const section = cfg.channels?.iris ?? {};
  const configured = Boolean(maybeOwner(section.owner) && (section.stateDir || section.bridgeUrl));
  return { ...section, accountId: 'default', enabled: section.enabled === true, configured,
    owner: maybeOwner(section.owner), name: 'Iris Chat' };
}

const outbound = {
  deliveryMode: 'direct', textChunkLimit: 12000, chunker: chunkTextForOutbound,
  sanitizeText: ({ text }) => sanitizeAssistantVisibleText(text),
  deliveryCapabilities: { durableFinal: { text: true, messageSendingHooks: true } },
  async sendText(params) {
    const { sendOutbound } = await import('./runtime.mjs');
    return sendOutbound(params);
  },
};

export const irisPlugin = createChatChannelPlugin({
  base: {
    id: 'iris',
    meta: { id: 'iris', label: 'Iris Chat', selectionLabel: 'Iris Chat',
      docsPath: 'https://github.com/irislib/iris-chat-channels', blurb: 'Private messages with your agent.' },
    capabilities: { chatTypes: ['direct'], media: false },
    reload: { configPrefixes: ['channels.iris'] },
    config: {
      listAccountIds: cfg => cfg.channels?.iris ? ['default'] : [],
      defaultAccountId: () => 'default', resolveAccount,
      inspectAccount: (cfg, id) => { const a = resolveAccount(cfg, id); return { accountId: a.accountId, enabled: a.enabled, configured: a.configured }; },
      isEnabled: a => a.enabled, isConfigured: a => a.configured,
      describeAccount: a => ({ accountId: a.accountId, name: a.name, enabled: a.enabled, configured: a.configured }),
      resolveAllowFrom: ({ cfg }) => { const owner = resolveAccount(cfg).owner; return owner ? [owner] : []; },
      resolveDefaultTo: ({ cfg }) => resolveAccount(cfg).owner ?? undefined,
    },
    approvalCapability: irisApprovals,
    setup: { validateInput: () => 'Run openclaw iris setup to create and pair a dedicated identity.' },
    messaging: { targetPrefixes: ['iris'], normalizeTarget: value => maybeOwner(value) ?? undefined,
      inferTargetChatType: ({ to }) => maybeOwner(to) ? 'direct' : undefined,
      targetResolver: { looksLikeId: value => Boolean(maybeOwner(value)), hint: '<approved Iris npub or hex ID>' } },
    message: createChannelMessageAdapterFromOutbound({ id: 'iris', outbound }),
    status: {
      defaultRuntime: { accountId: 'default', running: false, connected: false },
      buildAccountSnapshot: ({ account, runtime }) => ({ accountId: account.accountId, enabled: account.enabled,
        configured: account.configured, running: runtime?.running ?? false, connected: runtime?.connected ?? false,
        lastError: runtime?.lastError ?? null }),
    },
    gateway: { startAccount: async ctx => (await import('./runtime.mjs')).startAccount(ctx) },
  },
  security: { dm: { channelKey: 'iris', resolvePolicy: () => 'allowlist',
    resolveAllowFrom: account => account.owner ? [account.owner] : [], defaultPolicy: 'allowlist', normalizeEntry: normalizeOwner } },
  outbound,
});
