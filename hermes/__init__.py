def register(ctx):
    from .adapter import register as register_channel
    register_channel(ctx)
