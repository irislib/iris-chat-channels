# Iris Chat channels for Hermes and OpenClaw

[Iris Chat](https://irischat.org) is Signal-like messaging for people and agents,
without phone numbers or signup. It uses Nostr Double Ratchet for end-to-end
encryption and supports nearby messaging over local networks and Bluetooth.
These native plugins connect your existing agent, model, and tools.

## Hermes

```sh
hermes plugins install irislib/iris-chat-channels/hermes --ref 202a422c81eec3246bf19cb45657fc3513c2ac9a --enable
hermes gateway setup
```

Choose **Iris Chat**, then run `hermes gateway run` or restart your gateway service.

## OpenClaw

```sh
openclaw plugins install git:github.com/irislib/iris-chat-channels@v0.1.1
openclaw iris setup
```

Run `openclaw gateway run` or restart your gateway service. Review OpenClaw's
plugin trust prompt; for a noninteractive install after review, append
`--force --accept-capabilities` to the install command.

## Setup

Requires macOS/Linux (including WSL), Python 3.9+, and the
[Iris CLI](https://github.com/irislib/iris-chat-rs/blob/main/docs/agents.md#install)
on your gateway's PATH. Tested with **Hermes 0.22.5**, **OpenClaw 2026.10.9**, and
**Iris CLI 2026.10.30**. Check compatibility before upgrading the hosts.

Setup asks for your Iris public user ID (`npub…`) and private invite link,
creates a separate agent identity, and verifies the contact. Your secret key is
never needed. Keep Iris online during first contact; the agent introduces itself
when the gateway starts. Send it a task in that chat.

## Behavior and privacy

- One approved direct contact per profile. Text, seen receipts, and typing are
  supported; groups and attachments are not. Typing stays on while processing
  and clears afterward. `received` or `seen` confirms delivery; `sent` alone does not.
- Rerunning setup preserves the identity and contact without another introduction.
  Back up the private `iris-channel` directory inside your Hermes/OpenClaw profile
  and retain it across plugin updates. Keep profiles, invites, and logs out of public issues.
- Plugins use the agent's existing permissions. For filesystem/network isolation
  and Iris keys kept outside the agent, use
  [iris-agent-dockers](https://github.com/irislib/iris-agent-dockers).

## Troubleshooting

For Hermes, run `hermes plugins doctor iris-chat-channel` and `hermes gateway status`.
For OpenClaw, run `openclaw channels status`. Check gateway logs, model availability,
and that `iris` and `python3` are on the service's PATH. Only one gateway may use
an Iris identity at a time.

The plugin runs the installed Iris CLI and, when needed, its background service.
Iris stores its own keys and history in the dedicated profile and connects to its
configured message servers/transports. No telemetry or automatic software downloads.
See [permissions and data](https://github.com/irislib/iris-chat-channels/blob/main/hermes/README.md#permissions-and-data) for details.

## Development

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.mjs
```

Hermes runtime tests require the real host. See [gateway_e2e.py](tests/gateway_e2e.py)
for full gateway checks with an offline fixture. [package.py](scripts/package.py)
builds deterministic archives from committed source; downloads and checksums are
in [Releases](https://github.com/irislib/iris-chat-channels/releases).
