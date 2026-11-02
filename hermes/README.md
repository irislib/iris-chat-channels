# Iris Chat for Hermes

[Iris Chat](https://irischat.org) is Signal-like messaging for people and agents,
without phone numbers or signup.
Iris uses Nostr Double Ratchet for end-to-end encryption and supports nearby
messaging over local networks and Bluetooth.

This native channel connects one approved Iris contact to your existing Hermes
model and tools. Text replies, seen receipts and typing are supported.

```sh
hermes plugins install irislib/iris-chat-channels/hermes --ref 202a422c81eec3246bf19cb45657fc3513c2ac9a --enable
hermes gateway setup
```

Choose Iris Chat, then run `hermes gateway run` or restart your gateway.

Requires Hermes 0.22.5+, Python 3.9+, macOS/Linux, and the Iris CLI (tested with
2026.10.30). Setup creates a separate local agent identity; it never needs your
personal secret key. Keep the private Iris state directory across updates.

## Permissions and data

- Invokes the installed `iris` CLI with argument lists, without a shell. It does
  not download software. The CLI creates and stores its own keys, message history
  and service state in the dedicated `iris-channel` directory inside the selected
  Hermes profile. The plugin stores contact policy and delivery state beside it;
  it never reads another application's login credentials or imports your keys.
- Starts a background Iris service when needed, reuses an existing service for
  that profile, and stops only the service it started. Iris contacts its configured
  message servers and transports to exchange encrypted messages. Plaintext chat
  requests and replies pass through Hermes and its configured model provider.
- Managed containers can instead use the fixed loopback bridge at
  `http://127.0.0.1:8765`, keeping Iris keys in a separate container.
- No telemetry, self-updater, additional contacts, groups or attachment downloads.
  The agent keeps its normal permissions; the plugin is not filesystem isolation.
  Only one gateway should use an identity at a time. Keep profiles, invites and
  transport logs private.
