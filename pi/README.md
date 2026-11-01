# Iris Chat for Pi

Use [Iris Chat](https://irischat.org) as a private interface to Pi: Signal-like messaging over Nostr Double Ratchet, without phone numbers or signup.

```sh
npm install --prefix "$HOME/.local/share/iris-channels/packages" https://github.com/irislib/iris-chat-channels/releases/download/v0.2.0/iris-pi-0.2.0.tgz
"$HOME/.local/share/iris-channels/packages/node_modules/.bin/iris-pi-setup"
pi install "$HOME/.local/share/iris-channels/packages/node_modules/@irislib/pi-iris-chat"
IRIS_PI_STATE_DIR="$HOME/.local/share/iris-channels/pi" pi
```

Review the [release checksums](https://github.com/irislib/iris-chat-channels/releases/tag/v0.2.0) before installation. The package is also prepared for npm publication as `@irislib/pi-iris-chat`.

Requires Pi 1.4.0, Node 22+, Python 3.9+, macOS/Linux (or WSL), and the [Iris CLI](https://irischat.org/#command-line-interface). Setup asks for your public Iris ID and an invite from your app. Keep Iris online for first contact; never enter your personal secret key.

Only the explicitly selected Pi process connects. Run `/iris` in Pi to check its status. Use a dedicated Pi session for remote work; keep it running in your terminal or tmux. Incoming messages wait for an existing terminal turn to finish. `/stop` in Iris cancels the active Iris task.

The paired contact uses Pi's existing model and tools. Text, seen receipts, and typing while busy are supported; the final answer is sent after Pi settles its automatic continuations. Keep the private state directory across updates. One process may own a profile. Interrupted tasks are reported without automatically repeating tools.

The extension runs the installed Iris CLI and a Python transport. Iris stores its own keys and history in the selected profile. Pi and its configured model provider receive plaintext prompts; the extension does not restrict Pi's filesystem or network permissions. No groups, attachments, telemetry, or automatic plugin downloads.

[Source and releases](https://github.com/irislib/iris-chat-channels) · [Iris Chat](https://irischat.org)
