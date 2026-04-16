"""Finance tools — stock prices, market data, and analysis via free APIs.

Data sources (all free, no API key required):
- Yahoo Finance (via query endpoints)
- Exchange rate data
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from kira.core.models import ToolContext, ToolResult, ToolSchema
from kira.tools.registry import Tool, ToolRegistry

logger = logging.getLogger(__name__)

YF_BASE = "https://query1.finance.yahoo.com/v8/finance"


class StockPriceTool(Tool):
    schema = ToolSchema(
        name="stock_price",
        description=(
            "Get the current stock price, daily change, volume, and key stats for a ticker. "
            "Works for stocks (AAPL, MSFT), ETFs (SPY, QQQ), crypto (BTC-USD, ETH-USD), "
            "forex (EURUSD=X), and indices (^GSPC for S&P 500, ^DJI for Dow)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol (e.g., AAPL, BTC-USD, ^GSPC, EURUSD=X)",
                },
            },
            "required": ["ticker"],
        },
        timeout_seconds=15,
        category="finance",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        ticker = arguments["ticker"].upper().strip()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{YF_BASE}/chart/{ticker}",
                    params={"interval": "1d", "range": "5d"},
                    headers={
                        "User-Agent": "Mozilla/5.0",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            chart = data.get("chart", {}).get("result", [])
            if not chart:
                return ToolResult(success=False, output=f"Ticker not found: {ticker}")

            meta = chart[0].get("meta", {})
            price = meta.get("regularMarketPrice", 0)
            prev_close = meta.get("chartPreviousClose", meta.get("previousClose", 0))
            currency = meta.get("currency", "USD")
            exchange = meta.get("exchangeName", "?")
            name = meta.get("shortName", meta.get("symbol", ticker))
            volume = meta.get("regularMarketVolume", 0)

            change = price - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            # Get 5-day price history
            closes = chart[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            timestamps = chart[0].get("timestamp", [])
            history_lines = []
            if closes and timestamps:
                from datetime import datetime

                for ts, c in zip(timestamps[-5:], closes[-5:]):
                    if c is not None:
                        dt = datetime.fromtimestamp(ts).strftime("%m/%d")
                        history_lines.append(f"  {dt}: {currency} {c:.2f}")

            direction = "+" if change >= 0 else ""
            output = (
                f"{name} ({ticker})\n"
                f"  Price: {currency} {price:.2f}\n"
                f"  Change: {direction}{change:.2f} ({direction}{change_pct:.2f}%)\n"
                f"  Previous Close: {currency} {prev_close:.2f}\n"
            )
            if volume:
                output += f"  Volume: {volume:,}\n"
            output += f"  Exchange: {exchange}\n"

            if history_lines:
                output += "\n  5-Day History:\n" + "\n".join(history_lines)

            return ToolResult(
                success=True,
                output=output,
                outcome={
                    "ticker": ticker,
                    "price": price,
                    "change_pct": round(change_pct, 2),
                    "currency": currency,
                },
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output=f"Failed to fetch {ticker}: HTTP {e.response.status_code}",
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to fetch {ticker}: {e}")


class StockDetailTool(Tool):
    schema = ToolSchema(
        name="stock_detail",
        description=(
            "Get detailed financial information for a stock: market cap, P/E ratio, "
            "52-week range, dividend yield, EPS, sector, and more. "
            "Use this for fundamental analysis."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol (e.g., AAPL, TSLA)",
                },
            },
            "required": ["ticker"],
        },
        timeout_seconds=15,
        category="finance",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        ticker = arguments["ticker"].upper().strip()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
                    params={"modules": "price,summaryDetail,defaultKeyStatistics,assetProfile"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                data = resp.json()

            result = data.get("quoteSummary", {}).get("result", [])
            if not result:
                return ToolResult(success=False, output=f"No data for: {ticker}")

            modules = result[0]
            price_data = modules.get("price", {})
            summary = modules.get("summaryDetail", {})
            key_stats = modules.get("defaultKeyStatistics", {})
            profile = modules.get("assetProfile", {})

            def fmt(d, key, fallback="N/A"):
                val = d.get(key, {})
                if isinstance(val, dict):
                    return val.get("fmt", val.get("raw", fallback))
                return val or fallback

            lines = [
                f"{fmt(price_data, 'longName', ticker)} ({ticker})",
                f"  Sector: {profile.get('sector', 'N/A')} / {profile.get('industry', 'N/A')}",
                f"  Market Cap: {fmt(price_data, 'marketCap')}",
                f"  Price: {fmt(price_data, 'regularMarketPrice')}",
                f"  P/E Ratio: {fmt(summary, 'trailingPE')}",
                f"  Forward P/E: {fmt(summary, 'forwardPE')}",
                f"  EPS (TTM): {fmt(key_stats, 'trailingEps')}",
                f"  52-Week Range: {fmt(summary, 'fiftyTwoWeekLow')} - {fmt(summary, 'fiftyTwoWeekHigh')}",
                f"  50-Day Avg: {fmt(summary, 'fiftyDayAverage')}",
                f"  200-Day Avg: {fmt(summary, 'twoHundredDayAverage')}",
                f"  Dividend Yield: {fmt(summary, 'dividendYield')}",
                f"  Beta: {fmt(key_stats, 'beta')}",
                f"  Avg Volume: {fmt(summary, 'averageVolume')}",
            ]

            # Business summary
            biz_summary = profile.get("longBusinessSummary", "")
            if biz_summary:
                # Truncate to first 300 chars
                if len(biz_summary) > 300:
                    biz_summary = biz_summary[:300] + "..."
                lines.append(f"\n  About: {biz_summary}")

            return ToolResult(
                success=True,
                output="\n".join(lines),
                outcome={
                    "ticker": ticker,
                    "market_cap": fmt(price_data, "marketCap"),
                    "pe_ratio": fmt(summary, "trailingPE"),
                },
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ToolResult(success=False, output=f"Ticker not found: {ticker}")
            return ToolResult(success=False, output=f"Failed: HTTP {e.response.status_code}")
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to fetch details for {ticker}: {e}")


class MarketOverviewTool(Tool):
    schema = ToolSchema(
        name="market_overview",
        description=(
            "Get a snapshot of major market indices and their performance. "
            "Shows S&P 500, Dow Jones, NASDAQ, Russell 2000, VIX, "
            "gold, oil, Bitcoin, and major forex pairs."
        ),
        parameters={
            "type": "object",
            "properties": {},
        },
        timeout_seconds=20,
        category="finance",
    )

    TICKERS = [
        ("^GSPC", "S&P 500"),
        ("^DJI", "Dow Jones"),
        ("^IXIC", "NASDAQ"),
        ("^RUT", "Russell 2000"),
        ("^VIX", "VIX (Fear Index)"),
        ("GC=F", "Gold"),
        ("CL=F", "Crude Oil"),
        ("BTC-USD", "Bitcoin"),
        ("ETH-USD", "Ethereum"),
        ("EURUSD=X", "EUR/USD"),
        ("GBPUSD=X", "GBP/USD"),
        ("JPY=X", "USD/JPY"),
    ]

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        try:
            # Fetch each ticker individually (Yahoo batch endpoint is unreliable)
            results = []
            async with httpx.AsyncClient(timeout=15.0) as client:
                for ticker, name in self.TICKERS:
                    try:
                        resp = await client.get(
                            f"{YF_BASE}/chart/{ticker}",
                            params={"interval": "1d", "range": "1d"},
                            headers={"User-Agent": "Mozilla/5.0"},
                        )
                        if resp.status_code != 200:
                            results.append(f"  {name}: unavailable")
                            continue

                        data = resp.json()
                        chart = data.get("chart", {}).get("result", [])
                        if not chart:
                            results.append(f"  {name}: no data")
                            continue

                        meta = chart[0].get("meta", {})
                        price = meta.get("regularMarketPrice", 0)
                        prev = meta.get("chartPreviousClose", 0)
                        currency = meta.get("currency", "USD")

                        if prev:
                            change = price - prev
                            pct = (change / prev) * 100
                            direction = "+" if change >= 0 else ""
                            results.append(
                                f"  {name:20s} {price:>10,.2f} {currency}  {direction}{pct:.2f}%"
                            )
                        else:
                            results.append(f"  {name:20s} {price:>10,.2f} {currency}")
                    except Exception:
                        results.append(f"  {name}: error")

            output = "Market Overview\n" + "=" * 50 + "\n" + "\n".join(results)

            return ToolResult(
                success=True,
                output=output,
                outcome={"market_checked": True},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Market overview failed: {e}")


class StockScreenerTool(Tool):
    schema = ToolSchema(
        name="stock_screener",
        description=(
            "Analyze whether a stock might be a good trade based on fundamental "
            "and technical indicators. Fetches price history, key ratios, and "
            "provides a structured analysis. NOT financial advice."
        ),
        parameters={
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Ticker symbol to analyze",
                },
            },
            "required": ["ticker"],
        },
        timeout_seconds=20,
        category="finance",
    )

    async def execute(self, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        ticker = arguments["ticker"].upper().strip()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Get 3-month price history
                chart_resp = await client.get(
                    f"{YF_BASE}/chart/{ticker}",
                    params={"interval": "1d", "range": "3mo"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                chart_resp.raise_for_status()
                chart_data = chart_resp.json()

                # Get fundamentals
                detail_resp = await client.get(
                    f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
                    params={"modules": "price,summaryDetail,defaultKeyStatistics"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                detail_resp.raise_for_status()
                detail_data = detail_resp.json()

            # Parse chart
            chart = chart_data.get("chart", {}).get("result", [])
            if not chart:
                return ToolResult(success=False, output=f"No data for {ticker}")

            meta = chart[0].get("meta", {})
            closes = chart[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            volumes = chart[0].get("indicators", {}).get("quote", [{}])[0].get("volume", [])

            # Clean nulls
            closes = [c for c in closes if c is not None]
            volumes = [v for v in volumes if v is not None]

            price = meta.get("regularMarketPrice", 0)
            currency = meta.get("currency", "USD")
            name = meta.get("shortName", ticker)

            # Parse fundamentals
            result = detail_data.get("quoteSummary", {}).get("result", [{}])[0]
            summary = result.get("summaryDetail", {})
            key_stats = result.get("defaultKeyStatistics", {})

            def raw(d, key, default=None):
                val = d.get(key, {})
                if isinstance(val, dict):
                    return val.get("raw", default)
                return val if val else default

            pe = raw(summary, "trailingPE")
            forward_pe = raw(summary, "forwardPE")
            beta = raw(key_stats, "beta")
            dividend_yield = raw(summary, "dividendYield")
            fifty_two_low = raw(summary, "fiftyTwoWeekLow")
            fifty_two_high = raw(summary, "fiftyTwoWeekHigh")

            # Technical analysis
            analysis = [f"Analysis: {name} ({ticker}) @ {currency} {price:.2f}\n"]
            analysis.append("=" * 50)

            # Price vs moving averages
            if len(closes) >= 50:
                ma50 = sum(closes[-50:]) / 50
                analysis.append(
                    f"\n  50-Day MA: {currency} {ma50:.2f} {'(above)' if price > ma50 else '(below)'}"
                )
            if len(closes) >= 20:
                ma20 = sum(closes[-20:]) / 20
                analysis.append(
                    f"  20-Day MA: {currency} {ma20:.2f} {'(above)' if price > ma20 else '(below)'}"
                )

            # Volatility (standard deviation of daily returns)
            if len(closes) >= 20:
                returns = [
                    (closes[i] - closes[i - 1]) / closes[i - 1]
                    for i in range(1, len(closes))
                    if closes[i - 1]
                ]
                if returns:
                    avg_return = sum(returns) / len(returns)
                    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns)
                    daily_vol = variance**0.5
                    annual_vol = daily_vol * (252**0.5)
                    analysis.append(f"  Annualized Volatility: {annual_vol:.1%}")

            # 52-week position
            if fifty_two_low and fifty_two_high:
                range_pct = (price - fifty_two_low) / (fifty_two_high - fifty_two_low) * 100
                analysis.append(
                    f"\n  52-Week Range: {currency} {fifty_two_low:.2f} - {currency} {fifty_two_high:.2f}"
                )
                analysis.append(f"  Position in Range: {range_pct:.0f}% from low")

            # Volume trend
            if len(volumes) >= 20:
                avg_vol = sum(volumes[-20:]) / 20
                recent_vol = volumes[-1] if volumes else 0
                vol_ratio = recent_vol / avg_vol if avg_vol else 0
                analysis.append(f"\n  Avg Volume (20d): {avg_vol:,.0f}")
                analysis.append(f"  Latest Volume: {recent_vol:,.0f} ({vol_ratio:.1f}x avg)")

            # Fundamentals
            analysis.append("\n  Fundamentals:")
            if pe:
                assessment = "expensive" if pe > 30 else "moderate" if pe > 15 else "cheap"
                analysis.append(f"  P/E Ratio: {pe:.1f} ({assessment})")
            if forward_pe:
                analysis.append(f"  Forward P/E: {forward_pe:.1f}")
            if beta:
                risk = "high risk" if beta > 1.5 else "moderate" if beta > 1 else "low risk"
                analysis.append(f"  Beta: {beta:.2f} ({risk})")
            if dividend_yield:
                analysis.append(f"  Dividend Yield: {dividend_yield:.2%}")

            # 3-month performance
            if closes:
                three_mo_return = (price - closes[0]) / closes[0] * 100
                direction = "+" if three_mo_return >= 0 else ""
                analysis.append(f"\n  3-Month Return: {direction}{three_mo_return:.1f}%")

            analysis.append("\n  DISCLAIMER: This is data analysis, not financial advice.")

            return ToolResult(
                success=True,
                output="\n".join(analysis),
                outcome={
                    "ticker": ticker,
                    "price": price,
                    "pe_ratio": pe,
                    "analyzed": True,
                },
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Analysis failed for {ticker}: {e}")


def register(registry: ToolRegistry):
    registry.register(StockPriceTool())
    registry.register(StockDetailTool())
    registry.register(MarketOverviewTool())
    registry.register(StockScreenerTool())
