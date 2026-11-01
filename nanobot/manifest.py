"""Channel discovery stays dependency-free; the runtime is loaded on demand."""
from nanobot.channels.contracts import ChannelFieldSpec, ChannelSetupSpec
from nanobot.channels.plugin import ChannelPlugin

PLUGIN = ChannelPlugin(
    name="iris",
    display_name="Iris Chat",
    runtime="nanobot.channels.iris.runtime:IrisChannel",
    setup=ChannelSetupSpec(fields={
        "stateDir": ChannelFieldSpec(kind="string", default=""),
    }),
)
