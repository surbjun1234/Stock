import yfinance as yf
import pandas as pd
import requests
import os
import json
from datetime import datetime, timedelta, timezone

# --- [0] 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 웹훅 (Github Secrets)
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

# --- [1] 파일 관리 함수 ---
def get_file_content(filename):
    path = os.path.join(BASE_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except:
            return ""
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

# --- [2] QQQ 감시 (중복 방지 적용) ---
def check_qqq_realtime_alert():
    print("\n📡 [QQQ] 상태 확인 중...")
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

        # 이전 상태 읽기
        state_file = "qqq_alert_state.txt"
        last_state = get_file_content(state_file) # "BUY" or "NORMAL"

        is_buy_zone = (curr_price < target_ma) and (rsi < QQQ_RSI_THRESHOLD)

        # 1) 진입: 이전엔 안 샀는데(NORMAL/Empty), 지금 조건 맞음(BUY) -> 알림 O
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
            print("  => 🚨 매수 신호 전송 (상태 저장됨)")

        # 2) 유지: 이전에 샀고(BUY), 지금도 조건 맞음(BUY) -> 알림 X (무시)
        elif is_buy_zone and last_state == "BUY":
            print("  => 🔒 이미 매수 신호 보냄. 중복 전송 안 함.")

        # 3) 회복: 이전에 샀는데(BUY), 이제 조건 끝남(NORMAL) -> 알림 O
        elif not is_buy_zone and last_state == "BUY":
            msg = {
                "content": "🟢 **[TQQQ 매수 구간 종료]**",
                "embeds": [{"description": f"회복 완료. RSI: `{rsi:.2f}`", "color": 3066993}]
            }
            if SIGNAL_WEBHOOK: requests.post(SIGNAL_WEBHOOK, json=msg)
            save_file_content(state_file, "NORMAL")
            print("  => 🟢 회복 신호 전송 (상태 저장됨)")
            
        else:
            print("  => 특이사항 없음")

    except Exception as e:
        print(f"❌ QQQ 에러: {e}")

# --- [3] 우량주 스캐너 (중복 방지 핵심) ---
def check_watchlist_realtime_alert():
    print("\n🔭 [Scanner] 우량주 감시 중...")
    
    # 1. 파일에서 '이미 보낸 목록' 불러오기
    state_file = "scanner_state.json"
    prev_content = get_file_content(state_file)
    try:
        prev_detected = json.loads(prev_content) if prev_content else {}
    except:
        prev_detected = {}

    try:
        # 데이터 다운로드
        raw_data = yf.download(WATCHLIST, period="1y", interval="1d", progress=False)
        if len(WATCHLIST) == 1:
            closes = pd.DataFrame({WATCHLIST[0]: raw_data['Close']})
        else:
            closes = raw_data['Close']
        
        current_detected = {}
        
        # 종목별 체크
        for ticker in WATCHLIST:
            try:
                if ticker not in closes.columns: continue
                series = closes[ticker].dropna()
                if len(series) < 30: continue
                
                rsi = float(calculate_rsi(series).iloc[-1])
                price = float(series.iloc[-1])
                
                # RSI 25 미만일 때만 목록에 담음
                if rsi < SCANNER_RSI_THRESHOLD:
                    t_info = yf.Ticker(ticker).info
                    if t_info.get('marketCap', 0) >= MARKET_CAP_LIMIT and \
                       t_info.get('profitMargins', 0) >= PROFIT_MARGIN_LIMIT:
                        current_detected[ticker] = {"price": price, "rsi": rsi}
            except: continue

        # 2. 알림 로직: "장부에 없던 놈"만 골라낸다
        # prev_detected에 이미 키가 있다면, 값(가격)이 달라져도 무시함
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
            print(f"  => 🚨 신규 발견 전송: {new_tickers}")
        else:
            print("  => 🔒 신규 종목 없음 (기존 감지 종목은 무시)")

        # 3. 회복 알림: "장부에 있었는데 없어진 놈"
        recovered_tickers = [t for t in prev_detected if t not in current_detected]
        
        if recovered_tickers:
            msg = {
                "content": "🛁 **[우량주 과매도 해소]**",
                "embeds": [{"description": f"조건 이탈: **{', '.join(recovered_tickers)}**", "color": 3447003}]
            }
            if RSI_WEBHOOK: requests.post(RSI_WEBHOOK, json=msg)
            print(f"  => 🟢 회복 알림 전송: {recovered_tickers}")

        # 4. 현재 상태를 파일로 저장 (다음 실행을 위해)
        save_file_content(state_file, json.dumps(current_detected))

    except Exception as e:
        print(f"❌ 스캐너 에러: {e}")

# --- [Main] ---
def main():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    today_str = now.strftime("%Y-%m-%d")
    current_hour = now.hour
    
    print(f"▶️ 실행: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    check_qqq_realtime_alert()
    check_watchlist_realtime_alert()

    # 밤 11시에만 브리핑
    if current_hour == 23:
        log_file = "last_daily_briefing.txt"
        last_run = get_file_content(log_file)
        if last_run != today_str:
            # 브리핑 함수는 생략됨(이전과 동일하게 사용하거나 필요시 복구)
            save_file_content(log_file, today_str)

if __name__ == "__main__":
    main()
