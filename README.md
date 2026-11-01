# Iris Chat channels for Hermes and OpenClaw

Chat with your existing agent in [Iris](https://iris.to). These are native
gateway plugins: your agent keeps its model, tools, sessions, and permissions.
No Docker, Ollama, hosted model account, or Iris provider signup is required.

The plugin creates a separate persistent Iris identity for the agent, pairs it
with one person, and brings the transport online with the agent's gateway. It
shows typing while processing and clears it on completion, failure, and stop.

## Before installing

- An existing working **Hermes 0.22.5** or **OpenClaw 2026.10.9** installation.
  These are the host versions tested for this release. OpenClaw's plugin API is
  experimental; newer hosts need a compatibility check before updating.
- macOS or Linux (including WSL), Python 3.9+, and the **Iris CLI 2026.10.30** or
  a compatible release. Follow the [Iris CLI installation guide](https://github.com/irislib/iris-chat-rs/blob/main/docs/agents.md#install),
  then check `iris --version`. Both `iris` and `python3` must be available to the
  gateway service, not just your interactive terminal.
- Your Iris public user ID (`npub…`) and a private personal invite link copied
  from Iris. Keep your Iris app online during first contact. Never enter your
  secret key; it is not needed.

## Hermes

```sh
hermes plugins install irislib/iris-chat-channels/hermes --ref e52a5a95c770472d45e8ff3a9b706faab28ecf7e --enable
hermes gateway setup
```

Choose **Iris Chat**. Setup asks for your public user ID and invite, verifies that
they identify the same person, and saves the connection. Then start the gateway
with `hermes gateway run`, or restart your existing Hermes gateway service.

## OpenClaw

```sh
openclaw plugins install git:github.com/irislib/iris-chat-channels@v0.1.0
openclaw iris setup
```

OpenClaw asks you to trust this third-party package and its channel capability.
For a noninteractive install after reviewing it, append
`--force --accept-capabilities` to the install command. These are OpenClaw's
normal source-trust and capability-consent flags.

Setup asks for your public user ID and invite, verifies the contact, and adds
only the Iris channel configuration. Then start with `openclaw gateway run`, or
restart your existing gateway service.

If Git installation is unavailable, download the OpenClaw `.tgz` from
[Releases](https://github.com/irislib/iris-chat-channels/releases), verify its
published SHA-256, and pass the local archive path to `openclaw plugins install`.

## Your first conversation

The agent introduces itself when its gateway starts. Send a task in that Iris
chat. Incoming text goes through the agent's normal gateway and reply path;
this plugin does not run another CLI chat session or pick a different model.

Typing means the agent is processing, including time spent using tools. The
indicator refreshes during long turns and is explicitly stopped afterward. If
the process or network disappears, Iris expires it rather than leaving it on.
No periodic “thinking…” messages are added.

## Restarting and updating

Rerun setup safely: an existing identity and approved contact are reused without
accepting another invite or queuing another introduction. Stop/start the normal
agent gateway to stop/start the Iris channel. A service already running for the
same profile is reused and is not stopped by the plugin.

Identity, message history, and transport state live outside the plugin install:

- Hermes: `iris-channel` inside the selected Hermes profile directory.
- OpenClaw: `iris-channel` inside the selected OpenClaw state directory.

Back up that directory privately. Keep it when updating or removing the plugin.
Plugin updates do not update the Iris CLI or your model. A different approved
contact requires a deliberate new setup/profile; changing a message or tool
argument cannot change the stored contact policy.

Completed transport deliveries are deduplicated across restarts. A task claimed
but not handed off when the transport stopped is reported as interrupted, not
automatically executed again. Once handed off, the native agent gateway owns its
queue, session history, and run recovery. An uncertain send is checked against
Iris history instead of being blindly resent.

## What is supported

This first release supports one agent identity and one approved direct contact
per profile, incoming text, text replies, explicit seen acknowledgements, typing,
and text sends through the hosts' normal delivery interfaces. Hermes also
registers an outbound sender for scheduled delivery to that same contact.
Groups, additional contacts, automatic attachment downloads, and rich message
controls are not enabled. Queued/sent is not proof of recipient delivery; Iris
`received` and `seen` receipts are the confirmation.

Plugins run with the host agent's permissions. A normal local installation is
**not a filesystem or network isolation boundary**, and an agent with unrestricted
terminal access under the same OS user can access that user's files. For the
separate-container setup that keeps Iris keys outside the coding agent, use
[iris-agent-dockers](https://github.com/irislib/iris-agent-dockers). It uses these
same native plugins with a fixed-contact transport in a separate container.

## Troubleshooting

- **Iris command missing:** install the CLI and check the gateway service's PATH.
  OpenClaw can set `channels.iris.irisPath` and `channels.iris.pythonPath` to
  explicit executable paths.
- **No Iris option in Hermes:** run `hermes plugins list` and
  `hermes plugins doctor iris-chat-channel`, then enable the plugin and rerun
  `hermes gateway setup`.
- **OpenClaw install blocked:** review its source/capability prompt; do not
  change a general installation policy to make this plugin load.
- **Paired but no reply:** keep both Iris endpoints online, check the gateway
  logs and selected model, and use `openclaw channels status` or
  `hermes gateway status`. A running transport alone does not prove the model
  can complete a task.
- **Identity already in use:** stop the other gateway using this same Iris
  state directory. Each gateway/profile needs its own identity.

The dedicated directory's `transport.log` is private. Do not attach it, profiles,
invites, message histories, or host configuration to public issues. Share version
numbers and the error category instead.

## Development and verification

The shared transport is `hermes/transport.py` (Python standard library). Hermes
uses it in process; OpenClaw uses it over a private child-process pipe. The
managed-container variant uses a fixed loopback endpoint and the same operations.
No network listener is opened by the ordinary local plugins.

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.mjs
```

The three Hermes runtime tests require the real Hermes host. Run the full suite
inside that host with this repository on `PYTHONPATH`. `tests/gateway_e2e.py`
additionally runs each actual gateway with an installed plugin, a local test
model, and a local transport fixture. It must run in a disposable container with
network disabled and a temporary host profile; it checks inbound routing, model
execution, one final reply, typing refresh, and typing cleanup. It does not claim
to reproduce the upstream agent binaries or test a real model's reasoning.

`python3 scripts/package.py` packages committed source into deterministic
archives and writes checksums. It includes no profiles, local settings, logs,
test state, or dependencies. The archives record their source commit; the host
agents supply their own plugin SDKs.

Both hosts support external channels, so this integration needs no core patch.
See [Hermes platform plugins](https://hermes-agent.nousresearch.com/docs/developer-guide/adding-platform-adapters)
and [OpenClaw channel plugins](https://docs.openclaw.ai/plugins/sdk-channel-plugins).
Catalog listing is separate from publishing this repository.
