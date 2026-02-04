import yfinance as yf
import pandas as pd
import requests
import os
import json
from datetime import datetime, timedelta, timezone

# --- [0] 기본 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 웹훅 설정
QQQ_WEBHOOK = os.environ.get("WEBHOOK_QQQ")       
SIGNAL_WEBHOOK = os.environ.get("WEBHOOK_SIGNAL") 
RSI_WEBHOOK = os.environ.get("WEBHOOK_RSI")       

# 파라미터
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

# --- [1] 파일 처리 함수 ---
def get_file_content(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_file_content(filename, content):
    path = os.path.join(BASE_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def calculate_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / (ema_down + 1e-10)
    return 100 - (100 / (1 + rs))

# --- [2] QQQ 감시 ---
def check_qqq_realtime_alert():
    print("\n📡 [Realtime] QQQ 감시 중...")
    try:
        data = yf.download(QQQ_TICKER, period="2y", interval="1d", progress=False)
        df = data['Close'].copy().dropna()
        if isinstance(df, pd.DataFrame): df = df.iloc[:, 0]

        curr_price = float(df.iloc[-1])
        ma120 = float(df.rolling(window=MA_SHORT).mean().iloc[-1])
        ma233 = float(df.rolling(window=MA_LONG).mean().iloc[-1])
        rsi = float(calculate_rsi(df).iloc[-1])
        target_ma = max(ma120, ma233)
        last_date = df.index[-1].strftime("%Y-%m-%d")

        state_file = "qqq_alert_state.txt"
        last_state = get_file_content(state_file)
        
        is_buy_zone = (curr_price < target_ma) and (rsi < QQQ_RSI_THRESHOLD)

        if is_buy_zone and last_state != "BUY":
            msg = {
                "content": "🚨 **[TQQQ 매수 기회 발생]**",
                "embeds": [{
                    "title": "진입 조건 충족",
                    "description": f"• 가격: `${curr_price:.2f}`\n• RSI: `{rsi:.2f}`\n• 기준일: {last_date}",
                    "color": 15158332
                }]
            }
            if SIGNAL_WEBHOOK: requests.post(SIGNAL_WEBHOOK, json=msg)
            save_file_content(state_file, "BUY")
            print("  => 🚨 매수 신호 전송")

        elif not is_buy_zone and last_state == "BUY":
            msg = {
                "content": "🟢 **[TQQQ 매수 구간 종료]**",
                "embeds": [{"description": f"회복 완료. RSI: `{rsi:.2f}`", "color": 3066993}]
            }
            if SIGNAL_WEBHOOK: requests.post(SIGNAL_WEBHOOK, json=msg)
            save_file_content(state_file, "NORMAL")
            print("  => 🟢 회복 신호 전송")

    except Exception as e:
        print(f"❌ QQQ 에러: {e}")

# --- [3] 우량주 스캐너 (중복 방지 강화) ---
def check_watchlist_realtime_alert():
    print("\n🔭 [Realtime] 우량주 스캐너 감시 중...")
    
    state_file = "scanner_state.json"
    prev_content = get_file_content(state_file)
    try:
        prev_detected = json.loads(prev_content) if prev_content else {}
    except:
        prev_detected = {}

    try:
        raw_data = yf.download(WATCHLIST, period="1y", interval="1d", progress=False)
        if len(WATCHLIST) == 1:
            closes = pd.DataFrame({WATCHLIST[0]: raw_data['Close']})
        else:
            closes = raw_data['Close']
        
        current_detected = {}
        
        for ticker in WATCHLIST:
            try:
                if ticker not in closes.columns: continue
                series = closes[ticker].dropna()
                if len(series) < 30: continue
                
                rsi = float(calculate_rsi(series).iloc[-1])
                price = float(series.iloc[-1])
                
                if rsi < SCANNER_RSI_THRESHOLD:
                    t_info = yf.Ticker(ticker).info
                    if t_info.get('marketCap', 0) >= MARKET_CAP_LIMIT and \
                       t_info.get('profitMargins', 0) >= PROFIT_MARGIN_LIMIT:
                        current_detected[ticker] = {"price": price, "rsi": rsi}
            except: continue

        # 신규 진입 (이번엔 있고, 지난번엔 없던 것)
        new_tickers = [t for t in current_detected if t not in prev_detected]
        
        if new_tickers:
            desc_list = []
            for t in new_tickers:
                data = current_detected[t]
                desc_list.append(f"• **{t}**: RSI `{data['rsi']:.2f}` (${data['price']:.2f})")
            
            msg = {
                "content": "⚡ **[신규 과매도 우량주 포착]**",
                "embeds": [{"description": "\n".join(desc_list), "color": 16711680}]
            }
            if RSI_WEBHOOK: requests.post(RSI_WEBHOOK, json=msg)
            print(f"  => 🚨 신규 알림: {new_tickers}")

        # 회복 (지난번엔 있고, 이번엔 없는 것)
        recovered_tickers = [t for t in prev_detected if t not in current_detected]
        if recovered_tickers:
            msg = {
                "content": "🛁 **[우량주 과매도 해소]**",
                "embeds": [{"description": f"조건 이탈: **{', '.join(recovered_tickers)}**", "color": 3447003}]
            }
            if RSI_WEBHOOK: requests.post(RSI_WEBHOOK, json=msg)
            print(f"  => 🟢 회복 알림: {recovered_tickers}")

        # ★ 상태 저장 (핵심)
        save_file_content(state_file, json.dumps(current_detected))

    except Exception as e:
        print(f"❌ 스캐너 에러: {e}")

# --- [4] 정기 브리핑 ---
def send_daily_qqq_briefing(today_str):
    print(f"\n📅 [Schedule] 정기 브리핑...")
    try:
        data = yf.download(QQQ_TICKER, period="1y", progress=False)
        df = data['Close'].iloc[:, 0]
        price = float(df.iloc[-1])
        rsi = float(calculate_rsi(df).iloc[-1])
        
        payload = {
            "content": f"🌙 **[{today_str}] QQQ 마감 브리핑**",
            "embeds": [{"description": f"Close: `${price:.2f}`\nRSI: `{rsi:.2f}`", "color": 3447003}]
        }
        if QQQ_WEBHOOK: requests.post(QQQ_WEBHOOK, json=payload)
    except Exception as e:
        print(f"❌ 브리핑 에러: {e}")

# --- [Main] ---
def main():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    today_str = now.strftime("%Y-%m-%d")
    current_hour = now.hour
    
    print(f"▶️ 실행: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    check_qqq_realtime_alert()
    check_watchlist_realtime_alert()

    # 밤 11시에만 브리핑 (미국장 시작 전후)
    if current_hour == 23:
        log_file = "last_daily_briefing.txt"
        last_run = get_file_content(log_file)
        if last_run != today_str:
            send_daily_qqq_briefing(today_str)
            save_file_content(log_file, today_str)

if __name__ == "__main__":
    main()
