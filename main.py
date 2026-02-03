import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta, timezone

# --- [0] 경로 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- [1] 웹훅 설정 ---
QQQ_WEBHOOK = os.environ.get("WEBHOOK_QQQ")       
SIGNAL_WEBHOOK = os.environ.get("WEBHOOK_SIGNAL") 
RSI_WEBHOOK = os.environ.get("WEBHOOK_RSI")       

# --- [2] 전략 설정값 ---
QQQ_TICKER = "QQQ"
MA_SHORT = 120
MA_LONG = 233
QQQ_RSI_THRESHOLD = 40  
SCANNER_RSI_THRESHOLD = 25       
MARKET_CAP_LIMIT = 200_000_000_000 
PROFIT_MARGIN_LIMIT = 0.2         

WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "LLY", 
    "AVGO", "JPM", "WMT", "XOM", "V", "UNH", "MA", "PG", "JNJ", "COST", "HD", 
    "ABBV", "ORCL", "BAC", "KO", "CRM", "NFLX", "CVX", "MRK", "AMD", "PEP", 
    "ADBE", "LIN", "TMO", "MCD", "CSCO", "ACN", "ABT", "DHR", "DIS", "NKE",
    "TM", "NVO", "ASML", "SAP", "AZN", "BABA", "PDD"
]

# --- [3] 유틸리티 함수 ---
def get_file_content(filename):
    file_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return f.read().strip()
    return ""

def save_file_content(filename, content):
    file_path = os.path.join(BASE_DIR, filename)
    with open(file_path, "w") as f:
        f.write(content)

def calculate_rsi(series, period=14):
    """Wilder's Smoothing 방식의 RSI 계산"""
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    # EMA 대신 Wilder's 방식에 가까운 연산 사용
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / (ema_down + 1e-10) # 0 나누기 방지
    return 100 - (100 / (1 + rs))

# --- [4] QQQ 매수/회복 감지 로직 ---
def check_qqq_buy_signal(today_str):
    print("⚡ [Real-time] QQQ 매수 신호 체크 중...", flush=True)
    try:
        data = yf.download(QQQ_TICKER, period="2y", interval="1d", progress=False)
        if data.empty: return

        # 최신 종가 데이터 추출 (MultiIndex 대응)
        df = data['Close'].copy()
        if isinstance(df, pd.DataFrame):
            df = df.iloc[:, 0]
        
        df = df.dropna()
        ma120 = df.rolling(window=MA_SHORT).mean().iloc[-1]
        ma233 = df.rolling(window=MA_LONG).mean().iloc[-1]
        rsi = calculate_rsi(df).iloc[-1]
        curr_price = df.iloc[-1]
        target_ma = max(ma120, ma233)

        state_file = "qqq_signal_state.txt"
        last_state_str = get_file_content(state_file)
        is_buy_condition = (curr_price < target_ma) and (rsi < QQQ_RSI_THRESHOLD)

        if is_buy_condition:
            expected_state = f"SENT_{today_str}"
            if last_state_str != expected_state:
                if SIGNAL_WEBHOOK:
                    msg = {
                        "content": "🚨 **[TQQQ 매수 기회 발생]**",
                        "embeds": [{
                            "title": "진입 조건 충족",
                            "description": f"• **현재가**: `${curr_price:.2f}`\n• **RSI**: `{rsi:.2f}`\n• **Target MA**: `${target_ma:.2f}`",
                            "color": 15158332
                        }]
                    }
                    requests.post(SIGNAL_WEBHOOK, json=msg)
                save_file_content(state_file, expected_state)
        else:
            if last_state_str.startswith("SENT"):
                if SIGNAL_WEBHOOK:
                    requests.post(SIGNAL_WEBHOOK, json={"content": "🟢 **[매수 구간 종료]**"})
                save_file_content(state_file, "NORMAL")
    except Exception as e:
        print(f"❌ QQQ 체크 에러: {e}")

# --- [5] 정기 브리핑 및 우량주 스캐너 ---
def run_daily_briefing(today_str):
    print(f"📅 [Daily] 11시 정기 브리핑 시작 ({today_str})", flush=True)
    
    # 1. QQQ 현황
    try:
        data = yf.download(QQQ_TICKER, period="2y", progress=False)
        df_close = data['Close'].dropna()
        if isinstance(df_close, pd.DataFrame): df_close = df_close.iloc[:, 0]
        
        price = df_close.iloc[-1]
        rsi = calculate_rsi(df_close).iloc[-1]
        ma120 = df_close.rolling(window=MA_SHORT).mean().iloc[-1]
        ma233 = df_close.rolling(window=MA_LONG).mean().iloc[-1]

        if QQQ_WEBHOOK:
            payload = {
                "content": f"🌙 **[{today_str}] 오늘장 QQQ 브리핑**",
                "embeds": [{"title": "QQQ 마감", "description": f"• Price: `${price:.2f}`\n• RSI: `{rsi:.2f}`\n• MA233: `${ma233:.2f}`", "color": 3447003}]
            }
            requests.post(QQQ_WEBHOOK, json=payload)
    except Exception as e:
        print(f"❌ QQQ 브리핑 에러: {e}")

    # 2. 우량주 스캐너 (RSI 값 갱신 문제 해결 핵심부)
    print("🔭 우량주 스캔 시작...", flush=True)
    try:
        # 다수 종목 다운로드
        raw_data = yf.download(WATCHLIST, period="1y", progress=False)
        closes = raw_data['Close']

        found_list = []
        for ticker in WATCHLIST:
            try:
                if ticker not in closes.columns: continue
                
                # 개별 종목 데이터 추출 및 결측치 제거
                series = closes[ticker].dropna()
                if len(series) < 30: continue # 데이터 부족 시 패스

                # RSI 계산 및 최신값 추출
                rsi_series = calculate_rsi(series)
                current_rsi = float(rsi_series.iloc[-1])
                current_price = float(series.iloc[-1])
                
                # 로그 출력으로 값 갱신 확인 가능
                print(f"🔍 {ticker}: RSI {current_rsi:.2f} (날짜: {series.index[-1].date()})")

                if current_rsi < SCANNER_RSI_THRESHOLD:
                    t_info = yf.Ticker(ticker).info
                    if t_info.get('marketCap', 0) >= MARKET_CAP_LIMIT and \
                       t_info.get('profitMargins', 0) >= PROFIT_MARGIN_LIMIT:
                        found_list.append(f"**{ticker}** (${current_price:.2f}) | RSI: `{current_rsi:.2f}`")
            except:
                continue

        if found_list and RSI_WEBHOOK:
            requests.post(RSI_WEBHOOK, json={
                "content": "💎 **과매도 우량주 발견**",
                "embeds": [{"description": "\n".join(found_list), "color": 16711680}]
            })
    except Exception as e:
        print(f"❌ 스캐너 에러: {e}")

# --- [Main] ---
def main():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    today_str = now.strftime("%Y-%m-%d")
    
    check_qqq_buy_signal(today_str)

    if now.hour == 23:
        log_file = "last_daily_run.txt"
        if get_file_content(log_file) != today_str:
            run_daily_briefing(today_str)
            save_file_content(log_file, today_str)

if __name__ == "__main__":
    main()
