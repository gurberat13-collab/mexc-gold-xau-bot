from dataclasses import dataclass
import requests
import pandas as pd


@dataclass
class TickerSnapshot:
    symbol: str
    last_price: float
    funding_rate: float = 0.0


class MEXCFuturesClient:
    BASE_URL = "https://contract.mexc.com"

    def _get(self, path: str, params: dict | None = None):
        r = requests.get(f"{self.BASE_URL}{path}", params=params or {}, timeout=15)
        r.raise_for_status()
        payload = r.json()
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

<<<<<<< HEAD
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        response = self.session.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RuntimeError(f"MEXC API error: {payload}")
        return payload.get("data", payload)

    def _get_contract_symbols(self) -> list[str]:
        """Get all available contract symbols from MEXC API."""
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
        return symbols

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

        fallback_map = {
            "XAU": "XAUT_USDT",
            "GOLD": "XAUT_USDT",
            "NASDAQ": "NAS100_USDT",
            "NAS100": "NAS100_USDT",
        }
        if candidate in fallback_map and fallback_map[candidate] in symbols:
            return fallback_map[candidate]

        for s in symbols:
            if candidate in s or s in candidate:
                return s

        return None

    def _get_with_symbol_fallback(self, path_template: str, symbol: str, params: dict[str, Any] | None = None) -> Any:
        """Try API call with symbol, fall back to resolved symbol on 404."""
        try:
            return self._get(path_template.format(symbol=symbol), params=params)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                alt = self._resolve_symbol(symbol)
                if alt and alt != symbol:
                    return self._get(path_template.format(symbol=alt), params=params)
            raise

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
        symbol = self._resolve_symbol(symbol) or symbol
        data = self._get_with_symbol_fallback("/api/v1/contract/ticker/{symbol}", symbol)
        last_price = float(data["lastPrice"])
        bid = float(data.get("bid1", last_price))
        ask = float(data.get("ask1", last_price))
        spread_pct = max((ask - bid) / last_price, 0.0) if last_price else 0.0
        funding = self.get_funding_rate(symbol)
        return MarketSnapshot(symbol, last_price, bid, ask, funding, spread_pct)

    def get_funding_rate(self, symbol: str) -> float:
        symbol = self._resolve_symbol(symbol) or symbol
        data = self._get_with_symbol_fallback("/api/v1/contract/funding_rate/{symbol}", symbol)
        return float(data.get("fundingRate", 0.0))

    def get_klines(self, symbol: str, interval: str = "Min15", limit: int = 120) -> pd.DataFrame:
        symbol = self._resolve_symbol(symbol) or symbol
        data = self._get_with_symbol_fallback(
            "/api/v1/contract/kline/{symbol}",
            symbol,
=======
    def get_klines(self, symbol: str, interval: str = "Min15", limit: int = 180) -> pd.DataFrame:
        data = self._get(
            f"/api/v1/contract/kline/{symbol}",
>>>>>>> f657e539f3915fc9fb7757478b59d4812e4a5043
            params={"interval": interval, "limit": limit},
        )

        df = pd.DataFrame(
            {
                "time": pd.to_datetime(data["time"], unit="s", utc=True),
                "open": pd.to_numeric(data["open"]),
                "high": pd.to_numeric(data["high"]),
                "low": pd.to_numeric(data["low"]),
                "close": pd.to_numeric(data["close"]),
                "vol": pd.to_numeric(data["vol"]),
                "amount": pd.to_numeric(data["amount"]),
            }
        )
        return df.sort_values("time").reset_index(drop=True)

    def get_funding_rate(self, symbol: str) -> float:
        try:
            data = self._get(f"/api/v1/contract/funding_rate/{symbol}")
            if isinstance(data, dict):
                return float(data.get("fundingRate", 0.0) or 0.0)
            return 0.0
        except Exception:
            return 0.0

    def get_ticker(self, symbol: str) -> TickerSnapshot:
        """
        Önce resmi ticker endpoint'ini dener.
        404 veya başka hata olursa son fiyatı klinedan üretir.
        """
        try:
            data = self._get(f"/api/v1/contract/ticker/{symbol}")

            # endpoint bazen dict, bazen farklı format dönebilir
            if isinstance(data, dict):
                last_price = float(
                    data.get("lastPrice")
                    or data.get("last_price")
                    or data.get("fairPrice")
                    or data.get("indexPrice")
                    or 0.0
                )
            else:
                last_price = 0.0

            funding_rate = self.get_funding_rate(symbol)
            return TickerSnapshot(symbol=symbol, last_price=last_price, funding_rate=funding_rate)

        except Exception:
            # fallback: son kapanıştan fiyat al
            df = self.get_klines(symbol, interval="Min1", limit=5)
            if df is None or df.empty:
                # son çare
                df = self.get_klines(symbol, interval="Min15", limit=5)

            if df is None or df.empty:
                raise RuntimeError(f"{symbol} için ne ticker ne de kline verisi alınabildi.")

            last_price = float(df.iloc[-1]["close"])
            funding_rate = self.get_funding_rate(symbol)
            return TickerSnapshot(symbol=symbol, last_price=last_price, funding_rate=funding_rate)
