from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests


@dataclass
class MarketSnapshot:
    symbol: str
    last_price: float
    bid: float
    ask: float
    funding_rate: float
    spread_pct: float


class MexcFuturesClient:
    base_url = "https://contract.mexc.com"

    def __init__(self, timeout: int = 10):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "mexc-futures-paper-bot/1.0"})
        self.timeout = timeout

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(f"MEXC API error: {payload}")
        return payload.get("data", payload)

    def _get_contract_symbols(self) -> list[str]:
        """Get all available contract symbols from MEXC API. Returns safe fallback on error."""
        try:
            data = self._get("/api/v1/contract/detail")
            symbols = []
            if isinstance(data, list):
                for item in data:
                    s = item.get("symbol")
                    if s:
                        symbols.append(s.upper())
            elif isinstance(data, dict):
                s = data.get("symbol")
                if s:
                    symbols.append(s.upper())
            if symbols:
                return symbols
        except Exception as e:
            pass  # Fall through to default
        
        # Default fallback symbols if API fails
        return ["XAUT_USDT", "XAUT", "NAS100_USDT", "NAS100"]

    def _resolve_symbol(self, symbol: str) -> str | None:
        """Resolve a symbol to its actual contract name on MEXC."""
        candidate = symbol.upper()
        if not candidate:
            return None

        symbols = self._get_contract_symbols()
        if candidate in symbols:
            return candidate

        if candidate.endswith("_USDT"):
            short = candidate.replace("_USDT", "")
            if short in symbols:
                return short
        else:
            long = f"{candidate}_USDT"
            if long in symbols:
                return long

        # Explicit fallback map for known aliases
        fallback_map = {
            "XAU": "XAUT",
            "XAUT": "XAUT",
            "GOLD": "XAUT",
            "NASDAQ": "NAS100",
            "NAS100": "NAS100",
        }
        resolved = fallback_map.get(candidate)
        if resolved:
            if resolved in symbols:
                return resolved
            resolved_long = f"{resolved}_USDT"
            if resolved_long in symbols:
                return resolved_long

        # Try fuzzy match
        for s in symbols:
            if candidate in s or s in candidate:
                return s

        # Last resort: try without _USDT formatting  
        if candidate.endswith("_USDT"):
            return candidate[:-5]
        
        return candidate  # Return as-is, let API decide

    def _symbol_candidates(self, symbol: str) -> list[str]:
        candidate = symbol.upper().strip()
        if not candidate:
            return []

        candidates: list[str] = []
        seen: set[str] = set()

        def add(value: str | None) -> None:
            if not value:
                return
            normalized = value.upper().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)

        add(candidate)
        if candidate.endswith("_USDT"):
            add(candidate[:-5])
        else:
            add(f"{candidate}_USDT")

        resolved = self._resolve_symbol(candidate)
        add(resolved)
        if resolved:
            if resolved.endswith("_USDT"):
                add(resolved[:-5])
            else:
                add(f"{resolved}_USDT")

        return candidates

    def _request_with_symbol_fallback(self, symbol: str, fetcher: Callable[[str], Any]) -> Any:
        last_exc: requests.HTTPError | None = None

        for candidate in self._symbol_candidates(symbol):
            try:
                return fetcher(candidate)
            except requests.HTTPError as exc:
                last_exc = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code == 404:
                    continue
                raise

        if last_exc is not None:
            raise last_exc
        raise ValueError(f"Unable to resolve contract symbol for {symbol}")

    def _get_with_symbol_fallback(self, path_template: str, symbol: str, params: dict[str, Any] | None = None) -> Any:
        """Try API call with symbol, fall back to alternative formats on 404."""
        return self._request_with_symbol_fallback(
            symbol,
            lambda candidate: self._get(path_template.format(symbol=candidate), params=params),
        )

    def get_contract_info(self, symbol: str) -> dict[str, Any]:
        data = self._get("/api/v1/contract/detail")
        if isinstance(data, list):
            for item in data:
                if item.get("symbol") == symbol:
                    return item
        elif isinstance(data, dict) and data.get("symbol") == symbol:
            return data
        raise ValueError(f"Contract info not found for {symbol}")

    def get_ticker(self, symbol: str) -> MarketSnapshot:
        # Try to resolve symbol first, but don't fail if we can't
        resolved = self._resolve_symbol(symbol)
        if resolved:
            symbol = resolved
        
        data = self._request_with_symbol_fallback(
            symbol,
            lambda candidate: self._get("/api/v1/contract/ticker", params={"symbol": candidate}),
        )
        last_price = float(data.get("lastPrice", data.get("last_price", 0)))
        bid = float(data.get("bid1", last_price))
        ask = float(data.get("ask1", last_price))
        spread_pct = max((ask - bid) / last_price, 0.0) if last_price else 0.0
        funding = self.get_funding_rate(symbol)
        return MarketSnapshot(symbol, last_price, bid, ask, funding, spread_pct)

    def get_funding_rate(self, symbol: str) -> float:
        resolved = self._resolve_symbol(symbol)
        if resolved:
            symbol = resolved
        
        try:
            data = self._get_with_symbol_fallback("/api/v1/contract/funding_rate/{symbol}", symbol)
            return float(data.get("fundingRate", 0.0))
        except Exception:
            return 0.0

    def get_klines(self, symbol: str, interval: str = "Min15", limit: int = 120) -> pd.DataFrame:
        resolved = self._resolve_symbol(symbol)
        if resolved:
            symbol = resolved
        
        data = self._get_with_symbol_fallback(
            "/api/v1/contract/kline/{symbol}",
            symbol,
            params={"interval": interval, "limit": limit},
        )
        df = pd.DataFrame(
            {
                "time": pd.to_datetime(data["time"], unit="s", utc=True),
                "open": pd.to_numeric(data["open"]),
                "close": pd.to_numeric(data["close"]),
                "high": pd.to_numeric(data["high"]),
                "low": pd.to_numeric(data["low"]),
                "volume": pd.to_numeric(data["vol"]),
                "amount": pd.to_numeric(data["amount"]),
            }
        )
        return df.sort_values("time").reset_index(drop=True)
