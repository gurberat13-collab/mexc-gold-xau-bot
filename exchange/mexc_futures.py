from __future__ import annotations

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
        if resolved and resolved in symbols:
            return resolved

        # Try fuzzy match
        for s in symbols:
            if candidate in s or s in candidate:
                return s

        # Last resort: try without _USDT formatting  
        if candidate.endswith("_USDT"):
            return candidate[:-5]
        
        return candidate  # Return as-is, let API decide

    def _get_with_symbol_fallback(self, path_template: str, symbol: str, params: dict[str, Any] | None = None) -> Any:
        """Try API call with symbol, fall back to alternative formats on 404."""
        failed_symbols = set()
        
        # Try original symbol first
        try:
            return self._get(path_template.format(symbol=symbol), params=params)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                failed_symbols.add(symbol)
            else:
                raise

        # Try without _USDT
        if symbol.endswith("_USDT"):
            alt_symbol = symbol[:-5]
            if alt_symbol != symbol and alt_symbol not in failed_symbols:
                try:
                    return self._get(path_template.format(symbol=alt_symbol), params=params)
                except requests.HTTPError:
                    failed_symbols.add(alt_symbol)

        # Try with _USDT
        if not symbol.endswith("_USDT"):
            alt_symbol = f"{symbol}_USDT"
            if alt_symbol not in failed_symbols:
                try:
                    return self._get(path_template.format(symbol=alt_symbol), params=params)
                except requests.HTTPError:
                    failed_symbols.add(alt_symbol)

        # Last resort: use resolver
        resolved = self._resolve_symbol(symbol)
        if resolved and resolved not in failed_symbols:
            try:
                return self._get(path_template.format(symbol=resolved), params=params)
            except requests.HTTPError:
                pass

        # If all failed, raise 404 for the original symbol
        raise requests.HTTPError(f"404 Client Error: Not Found for url: {path_template.format(symbol=symbol)}")

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
        
        data = self._get_with_symbol_fallback("/api/v1/contract/ticker/{symbol}", symbol)
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
