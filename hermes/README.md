# Iris Chat for Hermes

[Iris Chat](https://irischat.org) is Signal-like messaging for people and agents,
without phone numbers or signup.
Iris uses Nostr Double Ratchet for end-to-end encryption and supports nearby
messaging over local networks and Bluetooth.

This native channel connects one approved Iris contact to your existing Hermes
model and tools. Text replies, seen receipts and typing are supported.

```sh
hermes plugins install irislib/iris-chat-channels/hermes --ref 155313526f82dc148aaa208bf94600b59f16db63 --enable
hermes gateway setup
```

Choose Iris Chat, then run `hermes gateway run` or restart your gateway.

Requires Hermes 0.22.5+, Python 3.9+, and macOS/Linux. Setup reuses Iris or
offers to install the tested CLI release for you, with no PATH changes or
administrator access. Automatic installation supports Apple Silicon/Intel Macs
and x86_64 Linux; other systems need a compatible Iris CLI. Setup creates a separate local agent identity; it never needs your
personal secret key. Keep the private Iris state directory across updates.

## Permissions and data

- Invokes the `iris` CLI with argument lists, without a shell. With your
  confirmation, setup downloads Iris 2026.10.30 from its tagged GitHub release,
  verifies the bundled SHA-256, and saves it in the channel folder. Existing
  installations are reused and never upgraded automatically. Gateway startup
  never downloads software. The CLI creates and stores its own keys, message history
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
