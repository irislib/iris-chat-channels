# Iris Chat for nanobot

Connect nanobot to [Iris Chat](https://irischat.org), Signal-like messaging over Nostr Double Ratchet without phone numbers or signup.

Install into the same Python environment as nanobot:

```sh
python -m pip install 'https://github.com/irislib/iris-chat-channels/releases/download/v0.2.0/iris_nanobot-0.2.0-py3-none-any.whl#sha256=19718be71b8f41f925ee40a091e23c880b22351fa236fb9d96f6e0ca81829e5c'
python -m nanobot.channels.iris.setup --state "$HOME/.local/share/iris-channels/nanobot"
```

Add to your nanobot configuration, using the absolute state path printed by setup:

```json
{"channels": {"iris": {"enabled": true, "stateDir": "/absolute/path/to/iris-profile", "streaming": false}}}
```

Start or restart `nanobot gateway --foreground`. The channel is discovered natively; no core patch is required. Requires nanobot 0.4.0, its supported Python version, macOS/Linux (or WSL), and the [Iris CLI](https://irischat.org/#command-line-interface).

Setup asks for your public Iris ID and an invite from your app. Keep Iris online for first contact; never enter your personal secret key. Only that contact can send tasks or receive replies. The channel supports text, seen receipts, and typing while busy. Incoming messages are processed one at a time. Remote tool approval and cancellation while a turn is running are not supported; use nanobot's normal controls.

Preserve the private state directory across updates. One gateway may use each profile. Interrupted turns are reported without rerunning tools. Iris stores its own keys and history locally; nanobot and its configured model receive plaintext prompts. This channel does not isolate agent tools from your computer. No groups, attachments, telemetry, or automatic plugin downloads.

[Source and releases](https://github.com/irislib/iris-chat-channels) · [Iris Chat](https://irischat.org)
