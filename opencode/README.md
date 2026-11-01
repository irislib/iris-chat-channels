# Iris Chat for OpenCode

Control a dedicated OpenCode session from [Iris Chat](https://irischat.org): Signal-like messaging over Nostr Double Ratchet, without phone numbers or signup.

```sh
npx --package @irislib/opencode-iris-chat@0.2.0 iris-opencode-setup /path/to/project
```

Add to that project's `opencode.json`, then start OpenCode there:

```json
{"plugin": ["@irislib/opencode-iris-chat@0.2.0"]}
```

Requires OpenCode 1.19.5, Node 22+, Python 3.9+, macOS/Linux (or WSL), and the [Iris CLI](https://irischat.org/#command-line-interface). Setup asks for your public Iris ID and an invite from your app. No personal secret key is needed. Keep Iris online for first contact.

Only the paired project and contact can start tasks. OpenCode retains its model and tool permissions. Reply `/approve ID` or `/deny ID` to a pending permission prompt; approval applies once. `/stop` cancels the current Iris task. Other OpenCode sessions are not forwarded.

Text, seen receipts, and typing while busy are supported. Interrupted tasks are reported without automatically repeating tools. Preserve `~/.local/share/iris-channels/opencode` across updates. For another project, choose a separate `IRIS_OPENCODE_STATE_DIR` during both setup and OpenCode startup; one process may own each profile.

The plugin runs the installed Iris CLI and a Python transport. Iris holds its own identity and history in the selected profile. Messages are decrypted for OpenCode and its configured model provider; encryption does not hide prompts from that provider. The plugin does not isolate agent tools from your computer. Use a separate container or machine when needed. No groups, attachments, telemetry, or automatic plugin downloads.

[Source and releases](https://github.com/irislib/iris-chat-channels) · [Iris Chat](https://irischat.org)
