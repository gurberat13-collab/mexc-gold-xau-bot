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

    def get_klines(self, symbol: str, interval: str = "Min15", limit: int = 180) -> pd.DataFrame:
        data = self._get(
            f"/api/v1/contract/kline/{symbol}",
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
