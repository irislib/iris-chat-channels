import { resolve } from 'node:path';
import { homedir } from 'node:os';
import { IrisChannel } from '../common/channel.mjs';
import { readJson, writeJson } from '../common/setup.mjs';

export default async function irisPlugin({ client, directory }, options = {}) {
  const stateDir = resolve(options.stateDir ?? process.env.IRIS_OPENCODE_STATE_DIR ?? `${homedir()}/.local/share/iris-channels/opencode`);
  const config = await readJson(`${stateDir}/opencode.json`);
  // Installing the package alone never opens a private channel into an arbitrary project.
  if (!config?.enabled || resolve(config.directory) !== resolve(directory)) return {};
  const permissions = new Map();
  let session;
  let disposed = false;
  const unwrap = result => {
    if (result.error || !result.data) throw new Error('OpenCode request failed.');
    return result.data;
  };
  const getSession = async () => {
    if (session) return session;
    const saved = await readJson(`${stateDir}/session.json`);
    if (saved?.id) {
      session = unwrap(await client.session.get({ path: { id: saved.id } }));
    } else {
      session = unwrap(await client.session.create({ body: { title: 'Iris Chat' } }));
      await writeJson(`${stateDir}/session.json`, { id: session.id });
    }
    return session;
  };
  const channel = new IrisChannel({ stateDir, bridgeUrl: config.bridgeUrl }, {
    report: message => { void client.app.log({ body: { service: 'iris-chat', level: 'warn', message } }).catch(() => {}); },
    handle: async job => {
      const current = await getSession();
      const result = unwrap(await client.session.prompt({ path: { id: current.id }, body: { parts: [{ type: 'text', text: job.text }] } }));
      if (result.info?.error) throw new Error('OpenCode could not complete the task.');
      return result.parts.filter(part => part.type === 'text' && !part.synthetic).map(part => part.text).join('\n');
    },
    control: async job => {
      if (job.text.trim() === '/stop') {
        if (session) await client.session.abort({ path: { id: session.id } });
        await channel.send(`control:${job.id}`, 'Stopped the current Iris task.');
        return true;
      }
      const match = /^\/(approve|deny)\s+(\S+)\s*$/.exec(job.text);
      if (!match) return false;
      const permission = permissions.get(match[2]);
      if (!permission || permission.sessionID !== session?.id) {
        await channel.send(`control:${job.id}`, 'That approval request is no longer pending.');
        return true;
      }
      unwrap(await client.postSessionIdPermissionsPermissionId({ path: { id: session.id, permissionID: permission.id },
        body: { response: match[1] === 'approve' ? 'once' : 'reject' } }));
      permissions.delete(permission.id);
      await channel.send(`control:${job.id}`, match[1] === 'approve' ? 'Approved this one request.' : 'Denied this request.');
      return true;
    },
  });
  // Defer server calls until plugin initialization has finished to avoid re-entering host startup.
  const startup = new Promise(resolveStart => setTimeout(resolveStart, 0)).then(async () => {
    if (!disposed) await channel.start();
  }).catch(() => { console.error('Iris Chat could not start. Check pairing and the selected project.'); });
  return {
    event: async ({ event }) => {
      if (!session || disposed) return;
      if (event.type === 'permission.asked' && event.properties.sessionID === session.id) {
        const request = event.properties;
        permissions.set(request.id, request);
        await channel.send(`permission:${request.id}`, `Permission requested: ${request.permission}\n${(request.patterns ?? []).join('\n')}\nReply /approve ${request.id} or /deny ${request.id}. Approval applies once.`).catch(() => {});
      }
      if (event.type === 'permission.replied') permissions.delete(event.properties.requestID);
    },
    dispose: async () => {
      disposed = true;
      await startup;
      if (session && channel.busy) await client.session.abort({ path: { id: session.id } }).catch(() => {});
      await channel.stop();
    },
  };
}
