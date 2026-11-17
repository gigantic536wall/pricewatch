import httpx
import pytest
import respx

from pricewatch.config import Settings
from pricewatch.fetch import Fetcher, FetchError

SHOP = "https://shop.example"


class RecordingFetcher(Fetcher):
    """Records waits instead of sleeping, so tests run instantly."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.waits: list[float] = []

    async def _sleep(self, seconds: float) -> None:
        self.waits.append(round(seconds, 1))


def make_fetcher(**overrides) -> RecordingFetcher:
    settings = Settings(per_host_delay=overrides.pop("per_host_delay", 0.0), max_concurrency=5, **overrides)
    return RecordingFetcher(settings, client=httpx.AsyncClient(), backoff=1.0)


@respx.mock
async def test_returns_html():
    respx.get(f"{SHOP}/robots.txt").respond(404)
    respx.get(f"{SHOP}/p/1").respond(200, text="<h1>ok</h1>")
    async with make_fetcher() as f:
        assert await f.get(f"{SHOP}/p/1") == "<h1>ok</h1>"


@respx.mock
async def test_robots_txt_is_respected_and_cached():
    robots = respx.get(f"{SHOP}/robots.txt").respond(200, text="User-agent: *\nDisallow: /private/\n")
    page = respx.get(f"{SHOP}/private/p").respond(200, text="secret")
    respx.get(f"{SHOP}/p/2").respond(200, text="ok")
    async with make_fetcher() as f:
        with pytest.raises(FetchError, match="robots.txt"):
            await f.get(f"{SHOP}/private/p")
        assert await f.get(f"{SHOP}/p/2") == "ok"
    assert not page.called
    assert robots.call_count == 1


@respx.mock
async def test_robots_txt_forbidden_blocks_everything():
    respx.get(f"{SHOP}/robots.txt").respond(403)
    async with make_fetcher() as f:
        with pytest.raises(FetchError, match="robots.txt"):
            await f.get(f"{SHOP}/p/1")


@respx.mock
async def test_robots_can_be_ignored_for_own_sites():
    respx.get(f"{SHOP}/p/1").respond(200, text="ok")
    async with make_fetcher(respect_robots_txt=False) as f:
        assert await f.get(f"{SHOP}/p/1") == "ok"


@respx.mock
async def test_retries_429_using_retry_after():
    respx.get(f"{SHOP}/robots.txt").respond(404)
    route = respx.get(f"{SHOP}/p/1")
    route.side_effect = [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, text="ok")]
    async with make_fetcher() as f:
        assert await f.get(f"{SHOP}/p/1") == "ok"
        assert f.waits == [7.0]


@respx.mock
async def test_gives_up_after_max_attempts_with_backoff():
    respx.get(f"{SHOP}/robots.txt").respond(404)
    route = respx.get(f"{SHOP}/p/1").respond(503)
    async with make_fetcher() as f:
        with pytest.raises(FetchError, match="HTTP 503") as err:
            await f.get(f"{SHOP}/p/1")
        assert err.value.retryable
        assert f.waits == [1.0, 2.0]
    assert route.call_count == 3


@respx.mock
async def test_does_not_retry_404():
    respx.get(f"{SHOP}/robots.txt").respond(404)
    route = respx.get(f"{SHOP}/gone").respond(404)
    async with make_fetcher() as f:
        with pytest.raises(FetchError, match="HTTP 404"):
            await f.get(f"{SHOP}/gone")
    assert route.call_count == 1


@respx.mock
async def test_retries_network_errors():
    respx.get(f"{SHOP}/robots.txt").respond(404)
    route = respx.get(f"{SHOP}/p/1")
    route.side_effect = [httpx.ConnectTimeout("slow"), httpx.Response(200, text="ok")]
    async with make_fetcher() as f:
        assert await f.get(f"{SHOP}/p/1") == "ok"


@respx.mock
async def test_waits_between_requests_to_the_same_host():
    respx.get(f"{SHOP}/robots.txt").respond(200, text="User-agent: *\nCrawl-delay: 5\n")
    respx.get(f"{SHOP}/a").respond(200, text="a")
    respx.get(f"{SHOP}/b").respond(200, text="b")
    async with make_fetcher(per_host_delay=2.0) as f:
        await f.get(f"{SHOP}/a")
        await f.get(f"{SHOP}/b")
        # Crawl-delay (5 s) is longer than our own delay (2 s), so it wins.
        assert len(f.waits) == 1 and 4.5 <= f.waits[0] <= 5.0


async def test_rejects_non_http_urls():
    async with make_fetcher() as f:
        with pytest.raises(FetchError, match="http"):
            await f.get("file:///etc/passwd")
