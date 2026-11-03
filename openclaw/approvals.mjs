import { createApproverRestrictedNativeApprovalCapability } from 'openclaw/plugin-sdk/approval-runtime';
import { createChannelApprovalNativeRuntimeAdapter, resolveApprovalOverGateway } from 'openclaw/plugin-sdk/approval-handler-runtime';
import { maybeOwner } from './identity.mjs';

const ownerOf = cfg => maybeOwner(cfg.channels?.iris?.owner);
const enabled = ({ cfg, accountId }) => (!accountId || accountId === 'default') &&
  cfg.channels?.iris?.enabled === true && Boolean(ownerOf(cfg));

function origin({ cfg, request, approvalKind }) {
  const source = request.request;
  const owner = ownerOf(cfg);
  if (approvalKind !== 'exec' || !owner || source.turnSourceChannel !== 'iris' ||
      (source.turnSourceAccountId && source.turnSourceAccountId !== 'default') ||
      maybeOwner(source.turnSourceTo) !== owner) return null;
  return { to: owner };
}

function prompt({ view, request }) {
  // The gateway alone decides which grants exist. Keep non-shell and wider
  // grants (e.g. standing automation grants) out of the chat interface.
  const choices = [];
  const offered = new Set(view.actions.map(action => action.decision));
  if (offered.has('allow-once')) choices.push('allow once');
  if (offered.has('deny')) choices.push('deny');
  const permanent = offered.has('allow-always') && view.host === 'gateway' && view.cwd &&
    !request.request.scope && !request.request.automation;
  if (permanent) choices.push('always allow');
  const details = [view.commandText, ...view.metadata.map(item => item.label + ': ' + item.value),
    view.warningText, permanent ? 'Always allow applies to this command and its arguments in this folder.' : '']
    .filter(Boolean).join('\n');
  return { key: 'openclaw:' + request.id, details, choices };
}

export const irisApprovals = createApproverRestrictedNativeApprovalCapability({
  channel: 'iris', channelLabel: 'Iris', listAccountIds: () => ['default'],
  hasApprovers: enabled, isNativeDeliveryEnabled: enabled,
  isExecAuthorizedSender: params => enabled(params) && maybeOwner(params.senderId) === ownerOf(params.cfg),
  isPluginAuthorizedSender: () => false,
  resolveNativeDeliveryMode: () => 'channel', requireMatchingTurnSourceChannel: true,
  resolveOriginTarget: origin,
  nativeRuntime: createChannelApprovalNativeRuntimeAdapter({
    eventKinds: ['exec'],
    availability: { isConfigured: enabled, shouldHandle: params => Boolean(origin(params)) },
    presentation: {
      buildPendingPayload: prompt,
      buildResolvedResult: () => ({ kind: 'none' }),
      buildExpiredResult: () => ({ kind: 'none' }),
    },
    transport: {
      prepareTarget: ({ context, plannedTarget }) => context?.owner === plannedTarget.target.to
        ? { dedupeKey: context.owner, target: context.owner } : null,
      deliverPending: async ({ context, request, pendingPayload }) => {
        context.assertActive();
        await context.client.call('approval', pendingPayload);
        context.requests.set(pendingPayload.key, { id: request.id, choices: pendingPayload.choices, expires: request.expiresAtMs });
        return pendingPayload.key;
      },
    },
    observe: { onFinalized: ({ context, request }) => context?.requests.delete('openclaw:' + request.id) },
  }),
});

export async function reviewReply(job, ctx, account) {
  const reply = job.approval_reply;
  if (!reply && !/^\/approve(?:\s|$)/i.test(job.text.trim())) return false;
  const pending = account.requests.get(reply?.key);
  const label = { 'allow-once': 'allow once', 'allow-always': 'always allow', deny: 'deny' }[reply?.decision];
  let text = 'Reply to a pending permission request with one of the choices it offers.';
  if (pending && pending.expires > Date.now() && pending.choices.includes(label)) {
    try {
      const result = await resolveApprovalOverGateway({ cfg: ctx.cfg, channel: 'iris', accountId: 'default',
        senderId: job.owner, approvalKind: 'exec', approvalId: pending.id, decision: reply.decision });
      if (result?.applied || result?.approval?.decision === reply.decision) {
        text = { 'allow-once': 'Allowed once.', 'allow-always': 'Always allowed for this command in this folder.', deny: 'Denied.' }[reply.decision];
      } else {
        text = 'That request is no longer pending.';
      }
    } catch {
      text = 'The decision could not be confirmed. Check the OpenClaw approval queue.';
    }
  }
  await account.client.call('send', { key: 'decision:' + job.id, text });
  return true;
}
