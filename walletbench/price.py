"""MAZA price discovery for the wallet - DISPLAY ONLY (not coin policy).

Payu directive (2026-11-25): "have Maza price discovery come from freixlite
and coinmarketcap info if needed". The whole policy, in order:

  1. PRIMARY - FreiXLite. FreiXLite is FreiExchange's Litecoin venue
     ("Litecoin Trading from FreiExchange"), served by FreiExchange's
     documented public v2 API (api.freiexchange.com), which also carries
     the BTC venue's pairs. FreiXLite's own market list holds exactly one
     MAZA market, MAZA/LTC. Among the MAZA markets the API returns, the
     pair with the largest 24h base volume wins. Base volume is in MAZA
     for every MAZA pair, so the numbers compare directly. A pair with
     zero 24h volume is a stale quote, not a market: on 2026-11-25
     MAZA_BTC still printed a last price (0.00000002) although nothing
     had traded. Such a pair never wins while any MAZA pair is trading.
     (CoinMarketCap lists that MAZA/BTC pair as MAZA's only market -
     market-pairs endpoint, 2026-11-25 - so its own quote rests on a
     market that is not trading. That is why it is the fallback here,
     never the first choice.)
  2. USD LEG - CoinMarketCap. FreiXLite quotes only in BTC and LTC, so the
     dollar figure is `last x CoinMarketCap's USD price for the quote
     currency`.
  3. FALLBACK ("if needed") - when FreiXLite is unreachable or has no
     trading MAZA pair, CoinMarketCap's own MAZA quote in USD.
  4. UNAVAILABLE - otherwise `price` is null and the wallet hides the line.
     A wallet never shows a number it could not source.

A value survives a failed refresh (labelled stale by its age) for at most
MAX_AGE_S; after that it is dropped rather than shown as current.

Arithmetic is Decimal end to end; values cross the wire as decimal strings.
This module makes NO decision about coins (fees, confirmations, derivation):
it is a display feed behind the bench token. The APK never talks to either
source - this service is the only outbound caller.
"""

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.client import HTTPException
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from . import config
from .addrcheck import MAZA_ADDRESS_VERSIONS

BASE_SYMBOL = "MAZA"
# Inherited address versions (D18, chainparams.cpp:171 / :297) - a testnet
# bench must never quote a price, because testnet coins have no market.
MAINNET_ADDRESS_VERSION = MAZA_ADDRESS_VERSIONS[0]
TESTNET_ADDRESS_VERSION = MAZA_ADDRESS_VERSIONS[1]

# CoinMarketCap asset ids. FreiXLite's /v2/assets publishes the same ids as
# each asset's unified_cryptoasset_id (MAZA 164, BTC 1, LTC 2).
CMC_IDS: Dict[str, int] = {"MAZA": 164, "BTC": 1, "LTC": 2}

EXCHANGE_SUMMARY_URL = "https://api.freiexchange.com/v2/summary"
CMC_OFFICIAL_URL = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest"
CMC_WEB_URL = "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/detail"

# FreiXLite allows 600 requests per minute per IP; one per minute is polite.
EXCHANGE_TTL_S = 60
# CoinMarketCap's official free tier is credit-metered: refresh rarely.
CMC_TTL_S = 600
# Older than this the wallet labels the price stale (15 minutes).
STALE_AFTER_S = 900
# Older than this a cached value is no longer served at all (24 hours).
MAX_AGE_S = 24 * 3600
FETCH_TIMEOUT_S = 4
MAX_BODY_BYTES = 2 * 1024 * 1024
# Upstream garbage rejection (display-feed input validation, NOT coin
# policy): a positive number beyond this bound is nonsense for both
# sources' formats, and quantizing it to the 8-dp wire form would
# overflow the decimal context. Capped values never reach text().
PARSE_VALUE_CAP = Decimal("1e15")
USER_AGENT = ("maza-wallet-bench/1.0 "
              "(price display; github.com/SamiAhmed7777/maza-mobile-wallet)")


# Neither source redirects in normal operation, and a redirect is never
# followed: urllib would replay the request headers - the CoinMarketCap key
# among them - to whatever host and scheme the redirect names. A 3xx is an
# answer like any other status (http_302), not an instruction.
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# The one opener fetch_json goes through. Tests replace `price._open`.
_open = urllib.request.build_opener(_NoRedirect).open


class Pair(NamedTuple):
    """One validated exchange market row."""
    name: str          # "MAZA_LTC"
    base: str          # "MAZA"
    quote: str         # "LTC"
    last: Decimal      # last traded price, in `quote`
    base_volume: Decimal  # 24h volume, in `base`


def _positive(value: Any) -> Optional[Decimal]:
    """Decimal from a JSON number or numeric string; None unless finite
    and strictly positive. Booleans and NaN/inf never become money."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and 0 < number <= PARSE_VALUE_CAP else None


def _non_negative(value: Any) -> Optional[Decimal]:
    """Like _positive but zero is a valid volume (it is the signal that a
    market did not trade)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() and 0 <= number <= PARSE_VALUE_CAP else None


def text(value: Decimal) -> str:
    """Wire form: 8 decimal places, HALF_UP - the wallet's own display
    precision - as a decimal string, never a float."""
    return format(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP), "f")


def parse_pairs(payload: Any, base: str = BASE_SYMBOL) -> List[Pair]:
    """Trading markets for `base`, best 24h volume first.

    Only well-formed rows with a strictly positive 24h base volume count:
    a zero-volume row is a stale quote (see the module docstring) and a
    malformed row is not trusted. Ties break by name so the result is
    deterministic.
    """
    if not isinstance(payload, list):
        return []
    pairs: List[Pair] = []
    for row in payload:
        if not isinstance(row, dict) or row.get("base_currency") != base:
            continue
        quote = row.get("quote_currency")
        if not isinstance(quote, str) or not quote:
            continue
        quote = quote.upper()
        last = _positive(row.get("last_price"))
        volume = _non_negative(row.get("base_volume"))
        if last is None or volume is None or volume <= 0:
            continue
        name = row.get("trading_pairs")
        if not isinstance(name, str) or not name:
            name = f"{base}_{quote}"
        pairs.append(Pair(name, base, quote, last, volume))
    pairs.sort(key=lambda pair: (-pair.base_volume, pair.name))
    return pairs


def parse_cmc_official(payload: Any) -> Dict[str, Decimal]:
    """{symbol: usd} from the official quotes/latest response."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {}
    quotes: Dict[str, Decimal] = {}
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        quote = entry.get("quote")
        usd = quote.get("USD") if isinstance(quote, dict) else None
        price = _positive(usd.get("price")) if isinstance(usd, dict) else None
        symbol = entry.get("symbol")
        if isinstance(symbol, str) and price is not None:
            quotes[symbol.upper()] = price
    return quotes


def parse_cmc_web(payload: Any) -> Dict[str, Decimal]:
    """{symbol: usd} from ONE data-api detail response (the keyless feed
    CoinMarketCap's own site reads)."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return {}
    stats = data.get("statistics")
    price = _positive(stats.get("price")) if isinstance(stats, dict) else None
    symbol = data.get("symbol")
    if isinstance(symbol, str) and price is not None:
        return {symbol.upper(): price}
    return {}


def _pull(request: urllib.request.Request, timeout: float,
          box: Dict[str, Any]) -> None:
    """Worker body of fetch_json: one GET and its body. Every outcome is
    written to `box` as ok / raw / reason. It runs off the caller's
    thread, so a trickling upstream holds the CALLER for at most
    `timeout`."""
    try:
        with _open(request, timeout=timeout) as response:
            raw = bytearray()
            deadline = time.monotonic() + timeout
            # read1 takes what ONE socket read brought. read(n) would
            # wait for all n bytes, and the idle timer restarts at every
            # byte - so a socket timeout alone bounds nothing.
            while len(raw) < MAX_BODY_BYTES:
                if time.monotonic() >= deadline:
                    box.update(ok=False, raw=None, reason="timeout")
                    return
                chunk = response.read1(min(65536, MAX_BODY_BYTES - len(raw)))
                if not chunk:
                    break
                raw += chunk
            box.update(ok=True, raw=bytes(raw), reason="")
    except urllib.error.HTTPError as exc:
        # The error carries the response's file object. Close it here
        # instead of leaving that to the garbage collector: the keyless
        # CoinMarketCap feed answers 429 under load, so this runs.
        with exc:
            box.update(ok=False, raw=None, reason="http_%d" % exc.code)
    except urllib.error.URLError as exc:
        box.update(ok=False, raw=None, reason=(
            "timeout" if isinstance(exc.reason, (TimeoutError, socket.timeout))
            else "unreachable"))
    except (TimeoutError, socket.timeout):
        box.update(ok=False, raw=None, reason="timeout")
    except (OSError, HTTPException, ValueError):
        box.update(ok=False, raw=None, reason="unreachable")


def fetch_json(url: str, timeout: float = FETCH_TIMEOUT_S,
               headers: Optional[Dict[str, str]] = None
               ) -> Tuple[bool, Any, str]:
    """GET `url` -> (ok, decoded JSON | None, reason), within `timeout`.

    The WHOLE exchange - connecting, headers and body - is bounded by
    `timeout`: it runs on a worker the caller waits for at most that
    long, and the worker itself stops reading at a deadline of its own.
    A socket timeout alone would bound only the idle gaps, so an
    upstream dripping one byte at a time could hold a plain read for as
    long as it liked.

    A redirect is never followed (neither source redirects in normal
    operation): urllib would replay the request headers to whatever host
    and scheme the redirect names. It is reported like any other status.

    `reason` is always a FIXED short code (timeout / unreachable /
    bad_json / http_<status>) - never the body and never a header
    value: the CoinMarketCap key rides a request header and must not
    reach a log line.
    """
    request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    box: Dict[str, Any] = {}
    worker = threading.Thread(target=_pull, args=(request, timeout, box),
                              name="price-fetch", daemon=True)
    worker.start()
    worker.join(timeout)
    if "ok" not in box:
        # Still working at the deadline. It is not waited for: a daemon,
        # it ends on its own socket timeout.
        return False, None, "timeout"
    if not box["ok"]:
        return False, None, box["reason"]
    try:
        return True, json.loads(box["raw"].decode("utf-8")), ""
    except (ValueError, UnicodeDecodeError):
        return False, None, "bad_json"


def cmc_quotes(api_key: str, timeout: float = FETCH_TIMEOUT_S,
               fetch: Optional[Callable[..., Tuple[bool, Any, str]]] = None,
               mono: Callable[[], float] = time.monotonic
               ) -> Tuple[Dict[str, Decimal], str, str]:
    """USD quotes -> ({symbol: usd}, mode, reason).

    mode is "official" when an API key is configured (the documented API;
    the key rides the X-CMC_PRO_API_KEY header, never a URL) or "web" -
    CoinMarketCap's public JSON feed, which needs no key but can be changed
    or gated by them at any time. `reason` names what failed, if anything.
    """
    get = fetch or fetch_json
    if api_key:
        ids = ",".join(str(cmc_id) for cmc_id in CMC_IDS.values())
        ok, payload, reason = get(
            f"{CMC_OFFICIAL_URL}?id={ids}&convert=USD", timeout,
            {"X-CMC_PRO_API_KEY": api_key})
        quotes = parse_cmc_official(payload) if ok else {}
        if quotes:
            return quotes, "official", ""
        return {}, "official", reason or "no_quote"
    quotes: Dict[str, Decimal] = {}
    reason = ""
    answered = set()
    # Three small requests share ONE bounded budget so a dead upstream can
    # never hold a caller for three full timeouts.
    deadline = mono() + 2 * timeout
    for symbol, cmc_id in CMC_IDS.items():
        left = deadline - mono()
        if left <= 0:
            reason = reason or "timeout"
            break
        ok, payload, why = get(f"{CMC_WEB_URL}?id={cmc_id}", min(timeout, left), {})
        if not ok:
            reason = why
            continue
        got = parse_cmc_web(payload)
        if not got:
            reason = "no_quote"
            continue
        quotes.update(got)
        answered.update(got)
    if quotes:
        # Some symbols answered and some did not: the rates that came are
        # good, and the gap is named - a clean "ok" would hide it.
        gap = [symbol for symbol in CMC_IDS if symbol not in answered]
        return quotes, "web", "partial" if gap else ""
    return {}, "web", reason or "no_quote"


def _exchange_fetch() -> Tuple[bool, Any, str]:
    return fetch_json(EXCHANGE_SUMMARY_URL)


def _cmc_fetch() -> Tuple[Dict[str, Decimal], str, str]:
    return cmc_quotes(config.cmc_api_key())


def _result(usd: Optional[Decimal], source: str, pair: Optional[Pair],
            quote_usd: Optional[Decimal], at: float, now: float,
            attempts: List[str]) -> Dict[str, Any]:
    age = int(now - at)
    return {
        "price": {
            "usd": text(usd) if usd is not None else None,
            "source": source,
            "pair": pair.name if pair else None,
            "last": text(pair.last) if pair else None,
            "quote": pair.quote if pair else None,
            "quote_usd": text(quote_usd) if quote_usd is not None else None,
            "updated_at": int(at),
            "age_s": age,
            "stale": age > STALE_AFTER_S,
        },
        "attempts": attempts,
    }


def _spawn_thread(work: Callable[[], None]) -> None:
    """How serve() starts its round in production: a daemon thread."""
    threading.Thread(target=work, name="price-refresh", daemon=True).start()


class PriceCache:
    """Thread-safe snapshot cache with single-flight refresh.

    The lock guards bookkeeping only, never a network call. One caller
    at a time runs a refresh round (an upstream is never hammered by a
    burst of requests - FreiXLite bans abusive polling) and holds nothing
    while it fetches; what it brings back is swapped in under the lock.
    So every reader is answered from what the cache holds: `snapshot()`
    waits only for a round it starts itself, and `serve()` - the request
    path - never waits at all.
    """

    def __init__(self,
                 exchange_fetch: Optional[Callable[..., Tuple[bool, Any, str]]] = None,
                 cmc_fetch: Optional[Callable[..., Tuple[Dict[str, Decimal], str, str]]] = None,
                 clock: Callable[[], float] = time.time,
                 spawn: Optional[Callable[[Callable[[], None]], None]] = None
                 ) -> None:
        self._exchange_fetch = exchange_fetch or _exchange_fetch
        self._cmc_fetch = cmc_fetch or _cmc_fetch
        self._clock = clock
        # How serve() starts the round it elects: a daemon thread unless a
        # test hands in its own.
        self._spawn = spawn or _spawn_thread
        self._lock = threading.Lock()
        self._refreshing = False
        self._exchange_at = 0.0
        self._exchange_try = 0.0
        self._pairs: List[Pair] = []
        self._exchange_reason = "not_fetched"
        # Each dollar rate's OWN fetch time (symbol -> when that rate was
        # fetched): a rate kept through a partial answer keeps its age.
        self._cmc_at: Dict[str, float] = {}
        self._cmc_try = 0.0
        self._cmc: Dict[str, Decimal] = {}
        self._cmc_reason = "not_fetched"
        self._cmc_mode = "none"

    @staticmethod
    def _overdue(now: float, stamp: float, ttl: float) -> bool:
        """True `ttl` seconds after the last attempt. A stamp from the
        FUTURE counts too: the clock stepped backwards, and nothing
        measured against that clock can be trusted - so it is fetched
        again."""
        elapsed = now - stamp
        return elapsed < 0 or elapsed >= ttl

    @staticmethod
    def _held(now: float, at: float) -> bool:
        """A value younger than MAX_AGE_S. A stamp from the future is NOT
        held: after a backwards clock step an old quote would otherwise
        read as brand new, so it is dropped instead - never shown as
        fresh."""
        return bool(at) and 0 <= now - at <= MAX_AGE_S

    def _due_locked(self, now: float) -> bool:
        return (self._overdue(now, self._exchange_try, EXCHANGE_TTL_S)
                or self._overdue(now, self._cmc_try, CMC_TTL_S))

    def _elect(self) -> bool:
        """True when the caller may run a refresh round: a TTL has
        expired and no round is running (single flight)."""
        with self._lock:
            if self._refreshing or not self._due_locked(self._clock()):
                return False
            self._refreshing = True
            return True

    def snapshot(self) -> Dict[str, Any]:
        """Current answer, refreshing first when a TTL has expired. Waits
        for a round it starts itself - bounded by the fetch timeouts -
        and never behind another caller's: while one runs, this answers
        from what is held."""
        if self._elect():
            self._round()
        with self._lock:
            return self._build_locked()

    def refresh(self) -> Dict[str, Any]:
        """The refresher's call: a round when a TTL has expired, then the
        count-only PRICE_REFRESH line for what that round fetched."""
        fetched, reasons = False, None
        if self._elect():
            fetched, reasons = self._round()
        with self._lock:
            snapshot = self._build_locked()
            # The reason fields come from the round's own swap (read under
            # the lock that made them), never from a later round that may
            # have run in between: one line, one round.
            exchange_reason, cmc_reason, cmc_mode = reasons or (
                self._exchange_reason, self._cmc_reason, self._cmc_mode)
        if fetched:
            found = snapshot.get("price") or {}
            _log_refresh(exchange_reason or "ok", cmc_reason or "ok",
                         cmc_mode, found.get("source") or "none",
                         bool(found.get("stale")))
        return snapshot

    def serve(self) -> Dict[str, Any]:
        """The request path's answer: what the cache holds, right now.

        When a TTL has expired, ONE background round is started - and
        this caller still does not wait for it: an upstream that hangs
        must never delay a wallet request. Until the round lands the
        answer is the previous one, its age telling the truth; a cache
        that holds nothing yet answers `price: null` (fail closed). If
        the round cannot be started, the election is released at once -
        otherwise no refresh could ever run again.
        """
        with self._lock:
            answer = self._build_locked()
            start = not self._refreshing and self._due_locked(self._clock())
            if start:
                self._refreshing = True
        if start:
            try:
                self._spawn(self._warm)
            except Exception as exc:
                # The round never started, so its own finally never runs:
                # the election is released HERE or no refresh - not even
                # the refresher's - could ever run again. The caller is
                # still answered from what the cache holds.
                with self._lock:
                    self._refreshing = False
                try:
                    print(f"PRICE_REFRESH spawn error="
                          f"{type(exc).__name__}", flush=True)
                except Exception:
                    pass        # observability must not break a request
        return answer

    def _warm(self) -> None:
        """The round serve() started, off the request. An upstream fault
        is caught inside the round; this catch is for a bug in the round
        itself, logged by class name only, like the refresher's."""
        try:
            self._round()
        except Exception as exc:
            print(f"PRICE_REFRESH refresher error={type(exc).__name__}",
                  flush=True)

    def _round(self) -> Tuple[bool, Tuple[str, str, str]]:
        """One refresh round, for a caller that won the election.

        The TTL stamps move first (under the lock, from the last ATTEMPT:
        a dead upstream is retried once per TTL, not on every request);
        the fetches then run with NO lock held, so a slow upstream never
        blocks a reader; what came back is swapped in under the lock.
        Returns whether anything was fetched, and the reason fields as
        that same lock hold left them. The election ends on every exit.
        """
        try:
            with self._lock:
                now = self._clock()
                exchange_due = self._overdue(now, self._exchange_try,
                                             EXCHANGE_TTL_S)
                cmc_due = self._overdue(now, self._cmc_try, CMC_TTL_S)
                if exchange_due:
                    self._exchange_try = now
                if cmc_due:
                    self._cmc_try = now
            exchange = self._fetch_exchange() if exchange_due else None
            cmc = self._fetch_cmc() if cmc_due else None
            with self._lock:
                fetched = self._swap_locked(now, exchange, cmc)
                reasons = (self._exchange_reason, self._cmc_reason,
                           self._cmc_mode)
            return fetched, reasons
        finally:
            with self._lock:
                self._refreshing = False

    def _fetch_exchange(self) -> Tuple[List[Pair], str]:
        try:
            ok, payload, reason = self._exchange_fetch()
            return parse_pairs(payload) if ok else [], reason
        except Exception as exc:  # one source must not starve the other
            return [], "error_" + type(exc).__name__

    def _fetch_cmc(self) -> Tuple[Dict[str, Decimal], str, str]:
        try:
            return self._cmc_fetch()
        except Exception as exc:  # class name only, never the message
            return {}, "none", "error_" + type(exc).__name__

    def _swap_locked(self, now: float,
                     exchange: Optional[Tuple[List[Pair], str]],
                     cmc: Optional[Tuple[Dict[str, Decimal], str, str]]
                     ) -> bool:
        """Put one round's answers where the readers look. `None` means
        the source was not due, so its bookkeeping is not touched."""
        fetched = False
        if exchange is not None:
            fetched = True
            pairs, reason = exchange
            if pairs:
                self._pairs, self._exchange_at, self._exchange_reason = (
                    pairs, now, "")
            else:
                # Keep the previous pairs on a failed or empty refresh - the
                # age tells the truth, and MAX_AGE_S eventually drops them.
                self._exchange_reason = reason or "no_trading_pair"
        if cmc is not None:
            fetched = True
            quotes, mode, reason = cmc
            if quotes:
                # A partial upstream success (one symbol's request died)
                # must not throw away the other symbols' rates - and must
                # not make them young either: the rates that came are
                # overlaid, each getting its OWN fetch time and the others
                # keeping theirs. A rate older than MAX_AGE_S is never used
                # again, however many partial answers arrive after it (the
                # read decides - see _build_locked).
                for symbol, rate in quotes.items():
                    self._cmc[symbol] = rate
                    self._cmc_at[symbol] = now
                # "" when every symbol answered, "partial" when some did
                # not: the rates that came are good and the gap is named.
                self._cmc_reason, self._cmc_mode = reason, mode
            else:
                self._cmc_reason, self._cmc_mode = reason or "no_quote", mode
        return fetched

    def _build_locked(self) -> Dict[str, Any]:
        now = self._clock()
        attempts = [
            "freixlite:" + (self._exchange_reason or "ok"),
            "coinmarketcap:" + (self._cmc_reason or "ok"),
        ]
        pairs_live = self._held(now, self._exchange_at)
        if pairs_live:
            # 1 + 2: the venue's price, converted through the dollar leg.
            # A pair whose quote currency has no LIVE dollar price is
            # skipped in favour of a trading pair that can be priced.
            for pair in self._pairs:
                leg_at = self._cmc_at.get(pair.quote, 0.0)
                if not self._held(now, leg_at):
                    continue
                # The product of two capped values can still exceed the
                # cap: treat that like a missing dollar leg (skip the
                # pair) instead of ever quantizing an absurd number.
                converted = pair.last * self._cmc[pair.quote]
                if converted > PARSE_VALUE_CAP:
                    continue
                # The age is that of the oldest input this answer used:
                # the pair, and THAT rate's own fetch time.
                return _result(converted,
                               "freixlite", pair, self._cmc[pair.quote],
                               min(self._exchange_at, leg_at),
                               now, attempts)
            # No dollar leg at all: quote the best trading pair in its own
            # currency rather than inventing a conversion.
            return _result(None, "freixlite", self._pairs[0], None,
                           self._exchange_at, now, attempts)
        # 3: nothing usable from the venue - CoinMarketCap's own quote.
        maza_at = self._cmc_at.get(BASE_SYMBOL, 0.0)
        if self._held(now, maza_at):
            return _result(self._cmc[BASE_SYMBOL], "coinmarketcap", None,
                           None, maza_at, now, attempts)
        # 4: no source. Never a number.
        return {"price": None, "reason": "; ".join(attempts),
                "attempts": attempts}


_log_lock = threading.Lock()
_log_seq = 0


def _log_refresh(exchange: str, cmc: str, mode: str, source: str,
                 stale: bool) -> None:
    """Count-only PRICE_REFRESH line (same discipline as WATCH_IMPORT):
    fixed reason codes and a source name - never a price, a key or a URL."""
    global _log_seq
    with _log_lock:
        _log_seq += 1
        try:
            print(f"PRICE_REFRESH seq={_log_seq} exchange={exchange} "
                  f"cmc={cmc} mode={mode} source={source} "
                  f"stale={1 if stale else 0}", flush=True)
        except Exception:
            # Observability only - a closed stdout must not break a refresh.
            pass


_default = PriceCache()
_refresher_lock = threading.Lock()
_refresher_started = False
_stop = threading.Event()


def current() -> Dict[str, Any]:
    """The request path's answer (PriceCache.serve): what the cache
    holds - never a wait on the network."""
    return _default.serve()


def start_refresher(interval: float = 15.0) -> None:
    """Keep the process-wide cache warm OFF the request path (daemon
    thread, idempotent). A request never waits for a fetch (see
    PriceCache.serve): one that finds an expired TTL is answered from
    what is held and starts a round in the background. The refresher is
    what keeps that the rare case - it refreshes before a TTL runs out,
    so a wallet is normally answered fresh."""
    global _refresher_started
    with _refresher_lock:
        if _refresher_started:
            return
        _refresher_started = True
    _stop.clear()

    def loop() -> None:
        while True:
            try:
                _default.refresh()
            except Exception as exc:  # keep warming; class name only
                print(f"PRICE_REFRESH refresher error={type(exc).__name__}",
                      flush=True)
            if _stop.wait(interval):
                return

    threading.Thread(target=loop, name="price-refresher", daemon=True).start()


if __name__ == "__main__":
    # Ops probe: prints the live answer as JSON (makes the real calls,
    # and waits for them).
    print(json.dumps(_default.snapshot(), indent=2))
