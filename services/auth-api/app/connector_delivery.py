"""The one outbound POST: a signed delivery to the endpoint an operator declared (ADR 0238).

The worker's second pass. Each iteration of the loop claims at most ONE due
delivery (`connector_claim_delivery`), and this module sends it: the canonical
body, three headers, and a signature under the connector's DERIVED key
(`connector_signature.derive`, ADR 0237). A 2xx is `delivered`; any other
status and every transport failure is an attempt that failed, retried by the
substrate at the connector's fixed backoff until `max + 1` attempts and then
`dead` (D1800). At-least-once: a lease that expires mid-send is claimed again
and the receiver may see the same `X-Apg-Delivery` twice -- which is what the
id is for.

**Its own transport row** (D1791). The loop's `workflow_worker.py` reaches
exactly one address, built from three constants a proof binds to the deploy's
own; a delivery goes to an operator's URL. So the POST lives here, under a row
that says so, and `workflow_worker.py`'s row stays true.

**No redirect is followed.** Rig 34b measured `urllib`'s default opener
following a 301/302/303 as a bodiless GET that still carries `X-Apg-
Signature`, and reporting the redirected page's 200 as the answer (D1812): a
signed delivery could be steered to an address nobody declared and counted
delivered. `_Refuse` returns `None` from `redirect_request`, so a 3xx is the
attempt's own result, `http_3xx`.

**The URL, the payload and the key appear in no record, no log line and no
error.** The endpoint is held in a local for one attempt and deleted in a
`finally`; an error is one of seven fixed tokens and never an exception's
text, because an exception's text names the host it failed to reach.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from app import connector_signature

#: How long one attempt may take, connect and read together. The lease is this
#: plus the loop's margin, so a worker that dies mid-send leaves a delivery
#: another claim takes after at most that long.
DELIVERY_TIMEOUT_SECONDS = 10

#: Where a REHEARSAL's delivery is sent instead of the connector's endpoint
#: (D1801): the discard port inside the container, refused on every
#: deployment -- measured in rig 34b as `connect_failed`.
REHEARSAL_ENDPOINT = "http://127.0.0.1:9/"

USER_AGENT = "agentic-postgres-connector/1"

#: The only words `last_error` can hold, besides `http_<3 digits>` (D1800).
ERROR_TOKENS = ("timeout", "connect_failed", "tls_failed", "dns_failed", "unknown")


class _Refuse(urllib.request.HTTPRedirectHandler):
    """A redirect handler that follows nothing: a 3xx is the answer."""

    def redirect_request(self, *arguments: Any, **options: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_Refuse)


def body(delivery: Any) -> bytes:
    """The canonical body: sorted keys, no whitespace, UTF-8.

    Canonical because the receiver verifies the signature over the BYTES it
    received, and a body re-serialized on the way would be a body nobody
    signed.
    """
    return json.dumps(
        {
            "delivery_id": str(delivery.delivery_id),
            "event": delivery.event_name,
            "version": delivery.event_version,
            "event_id": str(delivery.event_id),
            "emitted_at": delivery.emitted_at.isoformat(),
            "payload": delivery.payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def headers(delivery: Any, key_hex: str, payload: bytes, *, now: int) -> dict[str, str]:
    """The three `X-Apg-*` headers over `payload`, signed at `now`."""
    digest = connector_signature.sign(key_hex, now, str(delivery.delivery_id), payload)
    return {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Apg-Delivery": str(delivery.delivery_id),
        "X-Apg-Event": f"{delivery.event_name}@{delivery.event_version}",
        "X-Apg-Signature": connector_signature.header(now, digest),
    }


def error_token(exc: BaseException) -> str:
    """A transport failure's fixed token, from its MEASURED type (D1813).

    `URLError` carries the cause in `.reason`; a READ timeout arrives as a
    bare `TimeoutError`. `ssl.SSLError` is checked before the `OSError` family
    because it is one. A DNS failure is `socket.gaierror`, recognised by its
    class name: `socket` is a transport name this service does not grant, and
    the check needs the type, not the module.
    """
    cause: Any = exc
    if isinstance(exc, urllib.error.URLError) and not isinstance(exc, urllib.error.HTTPError):
        cause = exc.reason
    if isinstance(cause, ssl.SSLError):
        return "tls_failed"
    if isinstance(cause, TimeoutError):
        return "timeout"
    if type(cause).__name__ == "gaierror":
        return "dns_failed"
    if isinstance(cause, ConnectionError):
        return "connect_failed"
    return "unknown"


def _post(
    url: str, request_headers: dict[str, str], payload: bytes, *, timeout: float
) -> tuple[int | None, str | None]:
    """**The ONE place this module reaches a network.**

    `(status, None)` for any HTTP response, a 2xx included; `(None, token)`
    for a transport failure. No exception text leaves this function.
    """
    if not url.startswith(("http://", "https://")):
        # The manifest's schema admits nothing else (D1786); a value that got
        # past it is reported, never opened as a `file:` or custom scheme.
        return None, "unknown"
    request = urllib.request.Request(  # noqa: S310 -- http(s) only, checked above
        url, data=payload, headers=request_headers, method="POST"
    )
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return int(response.status), None
    except urllib.error.HTTPError as exc:
        return int(exc.code), None
    except (OSError, ValueError) as exc:
        return None, error_token(exc)


async def deliver(
    delivery: Any,
    *,
    repository: Any,
    key_master_hex: str,
    holder: str,
    clock: Any = time.time,
) -> str:
    """Send one claimed delivery and record the attempt. Returns the new status.

    The endpoint is a rehearsal's discard port or the connector's own, held in
    a local for this attempt and deleted on every path out.
    """
    key = connector_signature.derive(key_master_hex, delivery.connector_name)
    payload = body(delivery)
    signed = headers(delivery, key, payload, now=int(clock()))
    endpoint = REHEARSAL_ENDPOINT if delivery.rehearsal else delivery.endpoint
    try:
        if endpoint is None:
            # An enabled outbound connector has an endpoint (`enable` refuses
            # one without); a delivery claimed without one is reported as the
            # attempt's failure rather than guessed at.
            status, error = None, "unknown"
        else:
            status, error = await asyncio.to_thread(
                _post, endpoint, signed, payload, timeout=DELIVERY_TIMEOUT_SECONDS
            )
    finally:
        del endpoint
        del key
    delivered = status is not None and 200 <= status < 300
    if status is not None and not delivered:
        error = f"http_{status:03d}"
    return await repository.finish_delivery(
        delivery_id=delivery.delivery_id,
        holder=holder,
        delivered=delivered,
        status=status,
        error=error,
    )


__all__ = [
    "DELIVERY_TIMEOUT_SECONDS",
    "ERROR_TOKENS",
    "REHEARSAL_ENDPOINT",
    "USER_AGENT",
    "body",
    "deliver",
    "error_token",
    "headers",
]
