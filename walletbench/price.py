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


def fetch_json(url: str, timeout: float = FETCH_TIMEOUT_S,
               headers: Optional[Dict[str, str]] = None
               ) -> Tuple[bool, Any, str]:
    """GET `url` -> (ok, decoded JSON | None, reason).

    `reason` is always a FIXED short code (timeout / unreachable / bad_json
    / http_<status>) - never the body and never a header value: the
    CoinMarketCap key rides a request header and must not reach a log line.
    """
    request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES)
    except urllib.error.HTTPError as exc:
        # The error carries the response's file object. Close it here
        # instead of leaving that to the garbage collector: the keyless
        # CoinMarketCap feed answers 429 under load, so this runs.
        with exc:
            return False, None, "http_%d" % exc.code
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            return False, None, "timeout"
        return False, None, "unreachable"
    except (TimeoutError, socket.timeout):
        return False, None, "timeout"
    except (OSError, HTTPException, ValueError):
        return False, None, "unreachable"
    try:
        return True, json.loads(raw.decode("utf-8")), ""
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
    if quotes:
        return quotes, "web", ""
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


class PriceCache:
    """Thread-safe snapshot cache with single-flight refresh.

    One caller refreshes under the lock; concurrent callers wait on the
    same lock and reuse the result - an upstream is never hammered by a
    burst of requests (FreiXLite bans abusive polling).
    """

    def __init__(self,
                 exchange_fetch: Optional[Callable[..., Tuple[bool, Any, str]]] = None,
                 cmc_fetch: Optional[Callable[..., Tuple[Dict[str, Decimal], str, str]]] = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._exchange_fetch = exchange_fetch or _exchange_fetch
        self._cmc_fetch = cmc_fetch or _cmc_fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._exchange_at = 0.0
        self._exchange_try = 0.0
        self._pairs: List[Pair] = []
        self._exchange_reason = "not_fetched"
        self._cmc_at = 0.0
        self._cmc_try = 0.0
        self._cmc: Dict[str, Decimal] = {}
        self._cmc_reason = "not_fetched"
        self._cmc_mode = "none"

    def snapshot(self) -> Dict[str, Any]:
        """Current answer, refreshing first when a TTL has expired."""
        with self._lock:
            self._refresh_locked()
            return self._build_locked()

    def refresh(self) -> Dict[str, Any]:
        """TTL check + the count-only PRICE_REFRESH line. The background
        refresher calls this so requests find a warm cache."""
        fetched = False
        with self._lock:
            fetched = self._refresh_locked()
            snapshot = self._build_locked()
            # The reason fields are read under the lock they belong to: a
            # concurrent refresh between the release and the log must not
            # mix two rounds' reasons into one line.
            exchange_reason = self._exchange_reason
            cmc_reason = self._cmc_reason
            cmc_mode = self._cmc_mode
        if fetched:
            found = snapshot.get("price") or {}
            _log_refresh(exchange_reason or "ok", cmc_reason or "ok",
                         cmc_mode, found.get("source") or "none",
                         bool(found.get("stale")))
        return snapshot

    def _refresh_locked(self) -> bool:
        """True when at least one source was fetched in this call.

        The TTL is measured from the last ATTEMPT, not the last success:
        a dead upstream is retried once per TTL, not on every request."""
        now = self._clock()
        fetched = False
        if now - self._exchange_try >= EXCHANGE_TTL_S:
            fetched = True
            self._exchange_try = now
            try:
                ok, payload, reason = self._exchange_fetch()
                pairs = parse_pairs(payload) if ok else []
            except Exception as exc:  # one source must not starve the other
                pairs, reason = [], "error_" + type(exc).__name__
            if pairs:
                self._pairs, self._exchange_at, self._exchange_reason = (
                    pairs, now, "")
            else:
                # Keep the previous pairs on a failed or empty refresh - the
                # age tells the truth, and MAX_AGE_S eventually drops them.
                self._exchange_reason = reason or "no_trading_pair"
        if now - self._cmc_try >= CMC_TTL_S:
            fetched = True
            self._cmc_try = now
            try:
                quotes, mode, reason = self._cmc_fetch()
            except Exception as exc:  # class name only, never the message
                quotes, mode, reason = {}, "none", "error_" + type(exc).__name__
            if quotes:
                # A partial upstream success (one symbol's request died)
                # must not throw away the other symbols' still-fresh rates:
                # overlay the new answers on the previous set while that set
                # is inside the display window; beyond it, replace wholesale.
                merged = (dict(self._cmc)
                          if self._cmc_at and now - self._cmc_at <= MAX_AGE_S
                          else {})
                merged.update(quotes)
                self._cmc, self._cmc_at, self._cmc_reason, self._cmc_mode = (
                    merged, now, "", mode)
            else:
                self._cmc_reason, self._cmc_mode = reason or "no_quote", mode
        return fetched

    def _build_locked(self) -> Dict[str, Any]:
        now = self._clock()
        attempts = [
            "freixlite:" + (self._exchange_reason or "ok"),
            "coinmarketcap:" + (self._cmc_reason or "ok"),
        ]
        pairs_live = bool(self._exchange_at) and now - self._exchange_at <= MAX_AGE_S
        usd_leg_live = bool(self._cmc_at) and now - self._cmc_at <= MAX_AGE_S
        if pairs_live:
            # 1 + 2: the venue's price, converted through the dollar leg.
            # A pair whose quote currency has no dollar price is skipped in
            # favour of a trading pair that can be priced.
            for pair in self._pairs:
                if usd_leg_live and pair.quote in self._cmc:
                    # The product of two capped values can still exceed the
                    # cap: treat that like a missing dollar leg (skip the
                    # pair) instead of ever quantizing an absurd number.
                    converted = pair.last * self._cmc[pair.quote]
                    if converted > PARSE_VALUE_CAP:
                        continue
                    return _result(converted,
                                   "freixlite", pair, self._cmc[pair.quote],
                                   min(self._exchange_at, self._cmc_at),
                                   now, attempts)
            # No dollar leg at all: quote the best trading pair in its own
            # currency rather than inventing a conversion.
            return _result(None, "freixlite", self._pairs[0], None,
                           self._exchange_at, now, attempts)
        # 3: nothing usable from the venue - CoinMarketCap's own quote.
        if usd_leg_live and BASE_SYMBOL in self._cmc:
            return _result(self._cmc[BASE_SYMBOL], "coinmarketcap", None,
                           None, self._cmc_at, now, attempts)
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
    """The process-wide answer (see PriceCache.snapshot)."""
    return _default.snapshot()


def start_refresher(interval: float = 15.0) -> None:
    """Keep the process-wide cache warm OFF the request path (daemon
    thread, idempotent): an upstream that hangs must never delay a wallet
    request. Without it the first request after each TTL performs the
    refresh itself, bounded by FETCH_TIMEOUT_S."""
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
    # Ops probe: prints the live answer as JSON (makes the real calls).
    print(json.dumps(current(), indent=2))
