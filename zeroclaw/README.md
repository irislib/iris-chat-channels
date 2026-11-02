# Iris Chat for ZeroClaw

Connect ZeroClaw to [Iris Chat](https://irischat.org): Signal-like messaging over Nostr Double Ratchet, without phone numbers or signup.

Download [`iris-zeroclaw-0.2.0.zip`](https://github.com/irislib/iris-chat-channels/releases/download/v0.2.0/iris-zeroclaw-0.2.0.zip) and [`iris-zeroclaw-bridge-0.2.1.tgz`](https://github.com/irislib/iris-chat-channels/releases/download/v0.2.1/iris-zeroclaw-bridge-0.2.1.tgz), verify [`SHA256SUMS`](https://github.com/irislib/iris-chat-channels/releases/download/v0.2.0/SHA256SUMS), for the component and [bridge checksums](https://github.com/irislib/iris-chat-channels/releases/download/v0.2.1/SHA256SUMS), then extract each into its own directory. The component stays at 0.2.0; the bridge setup is updated to 0.2.1. From the bridge directory:

```sh
zeroclaw plugin install /path/to/component-package
python3 zeroclaw/setup.py --state "$HOME/.local/share/iris-channels/zeroclaw"
```

Merge the configuration printed by setup into `config.toml`, and add `plugin.iris` to the `channels` list of the existing agent you want to connect. Preserve that agent's normal permissions and model. Then keep both processes running, for example in separate tmux panes:

```sh
python3 zeroclaw/bridge.py --state "$HOME/.local/share/iris-channels/zeroclaw"
zeroclaw daemon
```

Requires a ZeroClaw 0.8.7 build with WASM plugins, Python 3.9+, macOS/Linux (or WSL). Setup reuses Iris or offers to install the tested CLI release for you, with no administrator access or PATH changes. Automatic installation supports Apple Silicon/Intel Macs and x86_64 Linux; other systems need a compatible [Iris CLI](https://irischat.org/#command-line-interface). Setup asks for your public Iris ID and an invite from your app. Keep Iris online for first contact; never enter your personal secret key.

The WASM component grants no general filesystem access. Its `config_read` and `http_client` permissions reach only the separately granted loopback host. The Python bridge runs Iris and owns the paired identity, history, and delivery journal. Loopback access covers every port on that host under ZeroClaw's policy, so use a dedicated network namespace/container if you need stronger separation. Never publish port 8765 or share it with untrusted processes.

Only the paired contact is accepted by the bridge, component, and ZeroClaw peer policy. Text replies, seen receipts, and typing are supported. No groups or attachments. Remote approval dialogs are unsupported; ZeroClaw retains its normal approval policy. Incoming tasks run one at a time. Preserve the private state directory; interrupted tasks are reported without repeating their tools.

Messages are decrypted for ZeroClaw and its model provider. The channel does not restrict the agent's own tools. No telemetry or automatic updates. The component release is unsigned and includes its SHA-256. Keep your signature-verification policy; strict installations must sign it with a publisher key you explicitly trust.

For source builds, see [the component](plugin/README.md). [Source and releases](https://github.com/irislib/iris-chat-channels) · [Iris Chat](https://irischat.org)

During setup only, an approved CLI download comes from a tagged GitHub release and is checked against a bundled SHA-256. The CLI location is saved in the channel folder for future starts. Existing identities and installations are preserved; runtime never downloads software.
