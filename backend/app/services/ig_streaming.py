from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncIterator

from app.services.ig_client import IGClient, IGClientError


class IGStreamingError(IGClientError):
    status_code = 502
    message = "IG streaming request failed"


@dataclass(frozen=True)
class StreamingPriceTick:
    bid: Decimal
    offer: Decimal
    mid: Decimal
    update_time: datetime


class IGStreamingClient:
    def __init__(self, client: IGClient | None = None) -> None:
        self.client = client or IGClient()

    async def stream_market_prices(self, epic: str) -> AsyncIterator[StreamingPriceTick]:
        try:
            from lightstreamer.client import LightstreamerClient, Subscription
        except ImportError as exc:
            raise IGStreamingError("Install lightstreamer-client-lib to enable IG streaming") from exc

        session = self.client.get_streaming_session()
        if not session.account_id or not session.lightstreamer_endpoint:
            raise IGStreamingError("IG login did not return streaming connection details")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[StreamingPriceTick | Exception] = asyncio.Queue()

        class PriceListener:
            bid: Decimal | None = None
            offer: Decimal | None = None

            def onItemUpdate(self, update) -> None:  # noqa: N802 - Lightstreamer callback name.
                bid = _decimal_or_existing(update.getValue("BID"), self.bid)
                offer = _decimal_or_existing(update.getValue("OFFER"), self.offer)
                if bid is None or offer is None:
                    return

                self.bid = bid
                self.offer = offer
                mid = (bid + offer) / Decimal("2")
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    StreamingPriceTick(
                        bid=bid,
                        offer=offer,
                        mid=mid,
                        update_time=datetime.now(timezone.utc),
                    ),
                )

            def onSubscriptionError(self, code, message) -> None:  # noqa: N802 - Lightstreamer callback name.
                loop.call_soon_threadsafe(queue.put_nowait, IGStreamingError(f"IG stream subscription failed: {code} {message}"))

        ls_client = LightstreamerClient(session.lightstreamer_endpoint, "DEFAULT")
        ls_client.connectionDetails.setUser(session.account_id)
        ls_client.connectionDetails.setPassword(f"CST-{session.cst}|XST-{session.security_token}")

        subscription = Subscription("MERGE", [f"MARKET:{epic}"], ["BID", "OFFER"])
        subscription.setDataAdapter("QUOTE_ADAPTER")
        subscription.setRequestedSnapshot("yes")
        subscription.addListener(PriceListener())
        ls_client.subscribe(subscription)

        try:
            await asyncio.to_thread(ls_client.connect)
            while True:
                tick = await queue.get()
                if isinstance(tick, Exception):
                    raise tick
                yield tick
        finally:
            await asyncio.to_thread(ls_client.disconnect)


def _decimal_or_existing(value: str | None, existing: Decimal | None) -> Decimal | None:
    if value in {None, ""}:
        return existing
    try:
        return Decimal(str(value))
    except Exception:
        return existing
