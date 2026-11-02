# Iris Chat agent channels

[Iris Chat](https://irischat.org) is Signal-like messaging without phone numbers or signup. It uses Nostr Double Ratchet for end-to-end encryption and supports nearby messaging over local networks and Bluetooth. These native plugins connect your existing agent, model, and tools.

## Install

### OpenClaw

```sh
openclaw plugins install clawhub:@irislib/openclaw-iris-chat
openclaw iris setup
```

[ClawHub listing](https://clawhub.ai/irislib/plugins/openclaw-iris-chat). Run `openclaw gateway run` or restart your gateway. Review the plugin trust prompt.

### Hermes

```sh
hermes plugins install irislib/iris-chat-channels/hermes --ref 202a422c81eec3246bf19cb45657fc3513c2ac9a --enable
hermes gateway setup
```

Choose Iris Chat, then run `hermes gateway run` or restart your gateway.

### All platforms

| Platform | Install and setup | Package source | Tested host |
| --- | --- | --- | --- |
| OpenClaw | [Commands above](#openclaw) | [ClawHub](https://clawhub.ai/irislib/plugins/openclaw-iris-chat) | 2026.10.9 |
| Hermes | [Channel guide](https://github.com/irislib/iris-chat-channels/blob/main/hermes/README.md) | Pinned GitHub source | 0.22.5 |
| OpenCode | [Project channel](https://github.com/irislib/iris-chat-channels/blob/main/opencode/README.md) | [npm](https://www.npmjs.com/package/@irislib/opencode-iris-chat) | 1.19.5 |
| Pi | [Session extension](https://github.com/irislib/iris-chat-channels/blob/main/pi/README.md) | [npm](https://www.npmjs.com/package/@irislib/pi-iris-chat) | 1.4.0 |
| nanobot | [Native channel package](https://github.com/irislib/iris-chat-channels/blob/main/nanobot/README.md) | Release wheel | 0.4.0 |
| ZeroClaw | [WASM channel and bridge](https://github.com/irislib/iris-chat-channels/blob/main/zeroclaw/README.md) | Release archives | 0.8.7 |

Requires macOS/Linux (including WSL), Python, and the [Iris CLI](https://irischat.org/#command-line-interface) on the agent's PATH. Tested with Iris CLI 2026.10.30. Follow each guide for host-specific requirements.

Setup asks for your public Iris ID (`npub…`) and an invite link from your app. It creates a separate agent identity; never enter your personal secret key. Keep Iris online for first contact, then send tasks in the resulting chat.

## Behavior and privacy

One approved direct contact per profile. Text, seen receipts, and typing are supported; groups and attachments are not. Typing stays on while working and clears afterward. Interrupted tasks are reported without automatically repeating their tools.

Keep the private Iris state directory across updates, and let only one agent process use each profile. Keep profiles, invites, and logs out of public issues. Iris encrypts transport; the agent and its configured model provider receive plaintext prompts. Each host retains its normal tool permissions. For filesystem/network isolation, see [iris-agent-dockers](https://github.com/irislib/iris-agent-dockers).

The plugins run the installed Iris CLI and a Python transport, with no telemetry or self-updater. Iris connects to its configured message servers/transports and stores its own keys and history locally. See [permissions and data](https://github.com/irislib/iris-chat-channels/blob/main/hermes/README.md#permissions-and-data).

## Development

[Tests and pinned hosts](https://github.com/irislib/iris-chat-channels/blob/main/tests/README.md) · [Releases and checksums](https://github.com/irislib/iris-chat-channels/releases) · [Iris Chat](https://irischat.org)
