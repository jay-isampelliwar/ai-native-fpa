"""Find a news page's preview image the way chat apps do, by reading its og:image tag, opening only public web addresses."""

import asyncio
import ipaddress
import logging
import re
import socket
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import get_settings


SAFE_SCHEMES = ("http", "https")

MAX_REDIRECTS = 3

USER_AGENT = "Mozilla/5.0 (compatible; ai-native-fpa-preview/1.0)"

META_TAG = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)

ATTRIBUTE = re.compile(r"""([a-zA-Z:_-]+)\s*=\s*("([^"]*)"|'([^']*)')""")

IMAGE_KEYS = ("og:image:secure_url", "og:image", "og:image:url", "twitter:image", "twitter:image:src")

log = logging.getLogger(__name__)


async def is_public(url: str) -> bool:

    """Say whether a link is http or https and every address its host resolves to is on the public internet."""

    parsed = urlparse(url)

    if parsed.scheme not in SAFE_SCHEMES or not parsed.hostname:
        return False

    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)

    except OSError:
        return False

    addresses = {ipaddress.ip_address(info[4][0]) for info in infos}

    return bool(addresses) and all(address.is_global for address in addresses)


def image_from_html(
    html: str,
    page_url: str,
    ) -> str | None:

    """Pick the page's preview image from its meta tags, preferring og:image, as a full http or https link."""

    found: dict[str, str] = {}

    for tag in META_TAG.findall(html):

        attributes = {match[0].lower(): match[2] or match[3] for match in ATTRIBUTE.findall(tag)}

        key = (attributes.get("property") or attributes.get("name") or "").lower()

        if key in IMAGE_KEYS and attributes.get("content") and key not in found:
            found[key] = unescape(attributes["content"].strip())

    for key in IMAGE_KEYS:

        if key not in found:
            continue

        image = urljoin(page_url, found[key])

        if urlparse(image).scheme in SAFE_SCHEMES:
            return image

    return None


async def read_head(
    client: httpx.AsyncClient,
    url: str,
    ) -> tuple[str | None, str | None]:

    """Read the start of one page and return its text, or the next link when it redirects."""

    limit = get_settings().WEB_PREVIEW_MAX_BYTES

    async with client.stream("GET", url) as response:

        if response.is_redirect:
            return None, urljoin(url, response.headers.get("location", ""))

        if response.status_code != 200 or "html" not in response.headers.get("content-type", ""):
            return None, None

        chunks: list[bytes] = []
        size = 0

        async for chunk in response.aiter_bytes():

            chunks.append(chunk)
            size += len(chunk)

            if size >= limit:
                break

    return b"".join(chunks)[:limit].decode(response.encoding or "utf-8", errors="replace"), None


async def preview_image(
    client: httpx.AsyncClient,
    url: str,
    ) -> str | None:

    """Follow up to three redirects, checking each address is public, and return the page's preview image or None."""

    for _ in range(MAX_REDIRECTS + 1):

        if not await is_public(url):
            return None

        html, next_url = await read_head(client, url)

        if html is not None:
            return image_from_html(html, url)

        if not next_url:
            return None

        url = next_url

    return None


async def add_images(
    results: list[dict[str, object]],
    seconds: float,
    ) -> None:

    """Look up every result's preview image at once within the time given, setting image to None for any that fail or run late."""

    for result in results:
        result["image"] = None

    if seconds <= 0 or not results:
        return

    async def one(result: dict[str, object]) -> None:

        """Set one result's image, logging and moving on when its page cannot be read."""

        try:
            result["image"] = await preview_image(client, str(result["url"]))

        except (httpx.HTTPError, UnicodeError, ValueError):
            log.info("no preview image for %s", result.get("site"))

    async with httpx.AsyncClient(timeout=seconds, headers={"User-Agent": USER_AGENT}, follow_redirects=False) as client:

        try:

            async with asyncio.timeout(seconds):
                await asyncio.gather(*(one(result) for result in results))

        except TimeoutError:
            log.info("preview images ran out of time")
