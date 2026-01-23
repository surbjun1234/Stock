import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta, timezone

# --- [웹훅 설정] ---
# 1. QQQ 매일 현황 보고용
QQQ_WEBHOOK = os.environ.get("WEBHOOK_QQQ")
# 2. TQQQ 매수 신호용
SIGNAL_WEBHOOK = os.environ.get("WEBHOOK_SIGNAL")
# 3. 우량주 스캐너용 (RSI 25 & 수익성 좋은 기업)
RSI_WEBHOOK = os.environ.get("WEBHOOK_RSI")

# --- [전략 설정값] ---

# [전략 1] QQQ 감시 (TQQQ 매수용)
QQQ_TICKER = "QQQ"
MA_SHORT = 120
MA_LONG = 233
QQQ_RSI_THRESHOLD = 40  # QQQ는 변동성이 적으므로 40 유지

# [전략 2] 슈퍼 우량주 스캐너 설정
SCANNER_RSI_THRESHOLD = 25        # 🔥 RSI 25 미만 (매우 엄격한 과매도 기준)
MARKET_CAP_LIMIT = 200_000_000_000 # 시총 2000억 달러 이상 (약 260조 원)
PROFIT_MARGIN_LIMIT = 0.2         # 순이익률 20% 이상 (돈 잘 버는 회사만)

# 검사할 주요 우량주 리스트 (Big Tech & Blue Chip)
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "LLY", 
    "AVGO", "JPM", "WMT", "XOM", "V", "UNH", "MA", "PG", "JNJ", "COST", "HD", 
    "ABBV", "ORCL", "BAC", "KO", "CRM", "NFLX", "CVX", "MRK", "AMD", "PEP", 
    "ADBE", "LIN", "TMO", "MCD", "CSCO", "ACN", "ABT", "DHR", "DIS", "NKE",
    "TM", "NVO", "ASML", "SAP", "AZN", "BABA", "PDD"
]

def calculate_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# --- [기능 1] QQQ 전략 분석 ---
def run_qqq_strategy(today_str):
    print("🚀 [1/2] QQQ 전략 분석 시작...")
    data = yf.download(QQQ_TICKER, period="2y", progress=False)
    if data.empty: return

    if isinstance(data.columns, pd.MultiIndex):
        df = data['Close'].iloc[:, 0].to_frame()
    else:
        df = data[['Close']].copy()
    
    df.columns = ['Close']
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')

    df['MA120'] = df['Close'].rolling(window=MA_SHORT).mean()
    df['MA233'] = df['Close'].rolling(window=MA_LONG).mean()
    df['RSI'] = calculate_rsi(df['Close'], 14)

    last_row = df.iloc[-1]
    curr_price = float(last_row['Close'])
    ma120 = float(last_row['MA120'])
    ma233 = float(last_row['MA233'])
    rsi = float(last_row['RSI'])
    target_ma = max(ma120, ma233)

    # 1. 일일 보고 (QQQ 현황)
    if QQQ_WEBHOOK:
        payload = {
            "content": f"📅 **{today_str} QQQ 일일 현황**",
            "embeds": [{
                "description": f"Price: `${curr_price:.2f}`\nRSI: `{rsi:.2f}`\nMA120: `${ma120:.2f}`",
                "color": 3447003 # 파란색
            }]
        }
        requests.post(QQQ_WEBHOOK, json=payload)

    # 2. 매수 신호 (TQQQ 진입)
    if curr_price < target_ma and rsi < QQQ_RSI_THRESHOLD:
        if SIGNAL_WEBHOOK:
            payload = {
                "content": "🚨 **[TQQQ 매수 신호] 조건 충족!**",
                "embeds": [{
                    "title": "🎯 진입 타이밍 발견",
                    "description": f"• 주가 < 이평선 (${target_ma:.2f})\n• RSI < {QQQ_RSI_THRESHOLD} (현재 {rsi:.2f})\n👉 **매수 추천**",
                    "color": 15158332 # 빨간색
                }]
            }
            requests.post(SIGNAL_WEBHOOK, json=payload)
            print("✅ TQQQ 매수 신호 전송됨")

# --- [기능 2] 우량주 스캐너 (RSI 25 & Margin 20%) ---
def run_scanner(today_str):
    print(f"🔭 [2/2] 슈퍼 우량주 스캐너 가동 (RSI < {SCANNER_RSI_THRESHOLD})...")
    data = yf.download(WATCHLIST, period="6mo", progress=False)
    if data.empty: return

    if isinstance(data.columns, pd.MultiIndex):
        closes = data['Close']
    else:
        closes = data['Close'].to_frame()

    found_list = []

    for ticker in WATCHLIST:
        try:
            if ticker not in closes.columns: continue
            series = closes[ticker].dropna()
            if len(series) < 15: continue

            rsi_series = calculate_rsi(series)
            current_rsi = rsi_series.iloc[-1]
            current_price = series.iloc[-1]

            # 필터 1: RSI 25 미만 (초과매도)
            if current_rsi < SCANNER_RSI_THRESHOLD:
                print(f"Candidate found: {ticker} (RSI {current_rsi:.2f})")
                
                # 필터 2: 재무 정보 (시총 & 순이익률)
                try:
                    ticker_obj = yf.Ticker(ticker)
                    info = ticker_obj.info
                    
                    cap = info.get('marketCap', 0)
                    margin = info.get('profitMargins', 0)
                    
                    # 시총 2000억불 & 순이익률 20%
                    if cap >= MARKET_CAP_LIMIT and margin >= PROFIT_MARGIN_LIMIT:
                        found_list.append({
                            'ticker': ticker,
                            'price': current_price,
                            'rsi': current_rsi,
                            'cap': cap,
                            'margin': margin
                        })
                        print(f"👉 Confirmed: {ticker} (Margin: {margin*100:.1f}%)")
                except Exception as e:
                    print(f"Info fetch fail for {ticker}: {e}")

        except Exception as e:
            print(f"Error {ticker}: {e}")

    # 결과 전송
    if found_list and RSI_WEBHOOK:
        description = ""
        for s in found_list:
            description += (
                f"**{s['ticker']}** (${s['price']:.2f})\n"
                f"**RSI: {s['rsi']:.2f}** (Extreme Oversold)\n"
                f"-------------------\n"
            )

        payload = {
            "content": f"📡 **[{today_str}]  대형주 과매도 알림 **",
            "embeds": [{
                "description": description,
                "color": 16711680, # 진한 빨간색 (긴급)
            }]
        }
        requests.post(RSI_WEBHOOK, json=payload)
        print(f"✅ 스캐너 알림 전송됨 ({len(found_list)}개)")
    else:
        print("💡 스캐너: 조건에 맞는 종목 없음")

def main():
    kst = timezone(timedelta(hours=9))
    today_str = datetime.now(kst).strftime("%Y-%m-%d")
    
    run_qqq_strategy(today_str)
    print("-" * 30)
    run_scanner(today_str)

if __name__ == "__main__":
    main()
