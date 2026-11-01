import { defineChannelPluginEntry } from 'openclaw/plugin-sdk/core';
import { irisPlugin } from './channel.mjs';

export default defineChannelPluginEntry({
  id: 'iris-chat-channel', name: 'Iris Chat', description: 'Private Iris Chat channel.', plugin: irisPlugin,
  registerCliMetadata(api) {
    api.registerCli(async ({ program }) => {
      program.command('iris').description('Set up the Iris Chat channel')
        .command('setup').description('Create a dedicated identity and pair your Iris contact')
        .action(async () => { const { setup } = await import('./setup.mjs'); await setup(api); });
    }, { descriptors: [{ name: 'iris', description: 'Set up the Iris Chat channel', hasSubcommands: true }] });
  },
});
