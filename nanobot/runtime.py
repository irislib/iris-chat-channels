"""One approved Iris conversation; nanobot owns model, tools, and sessions."""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import uuid
from pathlib import Path
from typing import Any

from nanobot.bus.events import OutboundMessage
from nanobot.bus.outbound_events import ProgressEvent, TurnEndEvent
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import Base

from .transport import Client, owner_hex


class IrisConfig(Base):
    enabled: bool = False
    state_dir: str = ""
    streaming: bool = False


class IrisChannel(BaseChannel):
    name = "iris"
    display_name = "Iris Chat"
    show_reasoning = False

    def __init__(self, config: dict[str, Any], bus: MessageBus):
        parsed = IrisConfig.model_validate(config)
        super().__init__(parsed, bus)
        if not parsed.state_dir:
            raise ValueError("Pair Iris first and configure channels.iris.stateDir.")
        self.client = Client(str(Path(parsed.state_dir).expanduser()))
        self.owner: str | None = None
        self.pending: str | None = None
        self._closed = False

    def is_allowed(self, sender_id: str) -> bool:
        try:
            return self.owner is not None and owner_hex(sender_id) == self.owner
        except ValueError:
            return False

    def progress_transport_defaults(self) -> tuple[bool, bool]:
        return False, False

    async def start(self) -> None:
        health = await self.client.open()
        self.owner = owner_hex(health["owner"])
        if not health["ready"]:
            await self.client.close()
            raise RuntimeError("Iris is not ready. Check the paired profile.")
        self._running = True
        try:
            while self._running:
                try:
                    if self.pending is None:
                        job = await self.client.call("receive", active=[])
                        if job:
                            if job["owner"] != self.owner:
                                raise ValueError("Iris contact changed; restart the channel.")
                            if job["interrupted"]:
                                await self.client.call("send", key="recovery:" + job["id"],
                                    text="My previous task was interrupted. I did not repeat it automatically. Send a new message to continue.")
                                await self.client.call("finish", id=job["id"])
                            else:
                                self.pending = job["id"]
                                await self.client.call("seen", id=job["id"])
                                await self.client.call("typing", active=True)
                                await self._handle_message(sender_id=self.owner, chat_id=self.owner,
                                    content=job["text"], metadata={"message_id": job["id"]}, is_dm=True)
                    if self.pending:
                        await self.client.call("typing", active=True)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.logger.warning("Iris is waiting for recovery; no task is replayed.")
                await asyncio.sleep(1)
        finally:
            await self.stop()

    async def stop(self) -> None:
        self._running = False
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            await self.client.call("typing", active=False)
        await self.client.close()

    async def send(self, msg: OutboundMessage) -> None:
        if not self.is_allowed(msg.chat_id):
            raise ValueError("Only the approved Iris contact can receive messages.")
        if msg.media:
            raise ValueError("Iris currently supports text replies only.")
        if isinstance(msg.event, ProgressEvent):
            return
        if msg.content.strip():
            anchor = msg.delivery_id or msg.reply_to or self.pending or str(uuid.uuid4())
            digest = hashlib.sha256(msg.content.encode()).hexdigest()
            await self.client.call("send", key=f"reply:{anchor}:{digest}", text=msg.content)
        origin = msg.metadata.get("message_id") or msg.metadata.get("origin_message_id") or msg.reply_to
        if origin == self.pending and self.pending and (msg.content.strip() or isinstance(msg.event, TurnEndEvent)):
            await self.client.call("finish", id=self.pending)
            self.pending = None
            await self.client.call("typing", active=False)

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return IrisConfig().model_dump(by_alias=True)
