import yfinance as yf
import pandas as pd
import requests
import os
import json
from datetime import datetime, timedelta, timezone

# --- [0] 기본 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 웹훅 (Secrets)
QQQ_WEBHOOK = os.environ.get("WEBHOOK_QQQ")       # 11시 브리핑용
SIGNAL_WEBHOOK = os.environ.get("WEBHOOK_SIGNAL") # QQQ/우량주 실시간 알림용
# (RSI_WEBHOOK을 따로 안 쓰신다면 SIGNAL_WEBHOOK으로 통합해도 됩니다)

# 전략 파라미터
QQQ_TICKER = "QQQ"
MA_SHORT = 120
MA_LONG = 233
QQQ_RSI_THRESHOLD = 40       # QQQ 매수 기준
SCANNER_RSI_THRESHOLD = 25   # 우량주 과매도 기준
MARKET_CAP_LIMIT = 200_000_000_000 
PROFIT_MARGIN_LIMIT = 0.2         

WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B", "LLY", 
    "AVGO", "JPM", "WMT", "XOM", "V", "UNH", "MA", "PG", "JNJ", "COST", "HD", 
    "ABBV", "ORCL", "BAC", "KO", "CRM", "NFLX", "CVX", "MRK", "AMD", "PEP", 
    "ADBE", "LIN", "TMO", "MCD", "CSCO", "ACN", "ABT", "DHR", "DIS", "NKE",
    "TM", "NVO", "ASML", "SAP", "AZN", "BABA", "PDD"
]

# --- [1] 파일 및 계산 함수 ---
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

# --- [2] 기능 1: QQQ 실시간 감시 (매수/회복 알림) ---
def check_qqq_realtime_alert():
    print("\n📡 [Realtime] QQQ 매수/회복 감시 중...")
    try:
        # 데이터 확보
        data = yf.download(QQQ_TICKER, period="2y", interval="1d", progress=False)
        df = data['Close'].copy().dropna()
        if isinstance(df, pd.DataFrame): df = df.iloc[:, 0]

        # 지표 계산
        curr_price = float(df.iloc[-1])
        ma120 = float(df.rolling(window=MA_SHORT).mean().iloc[-1])
        ma233 = float(df.rolling(window=MA_LONG).mean().iloc[-1])
        rsi = float(calculate_rsi(df).iloc[-1])
        target_ma = max(ma120, ma233)

        # 상태 파일 확인
        state_file = "qqq_alert_state.txt"
        last_state = get_file_content(state_file) # "BUY" or "NORMAL"
        
        # 조건 판별
        is_buy_zone = (curr_price < target_ma) and (rsi < QQQ_RSI_THRESHOLD)

        # 1) 진입 알림 (Normal -> Buy)
        if is_buy_zone and last_state != "BUY":
            msg = {
                "content": "🚨 **[TQQQ 매수 기회 발생]**",
                "embeds": [{
                    "title": "진입 조건 충족 (Price < MA & RSI < 40)",
                    "description": f"• 가격: `${curr_price:.2f}`\n• RSI: `{rsi:.2f}`\n• MA기준: `${target_ma:.2f}`",
                    "color": 15158332 # 빨강
                }]
            }
            if SIGNAL_WEBHOOK: requests.post(SIGNAL_WEBHOOK, json=msg)
            save_file_content(state_file, "BUY")
            print("  => 🚨 매수 신호 전송 완료")

        # 2) 회복 알림 (Buy -> Normal)
        elif not is_buy_zone and last_state == "BUY":
            msg = {
                "content": "🟢 **[TQQQ 매수 구간 종료]**",
                "embeds": [{
                    "description": f"주가가 회복되었거나 RSI가 안정화되었습니다.\n• 현재가: `${curr_price:.2f}`\n• RSI: `{rsi:.2f}`",
                    "color": 3066993 # 초록
                }]
            }
            if SIGNAL_WEBHOOK: requests.post(SIGNAL_WEBHOOK, json=msg)
            save_file_content(state_file, "NORMAL")
            print("  => 🟢 회복 신호 전송 완료")
            
        else:
            print(f"  => 상태 변화 없음 (Current: {'BUY Zone' if is_buy_zone else 'Safe Zone'})")

    except Exception as e:
        print(f"❌ QQQ 감시 에러: {e}")

# --- [3] 기능 2: 우량주 스캐너 실시간 감시 (진입/이탈 알림) ---
def check_watchlist_realtime_alert():
    print("\n🔭 [Realtime] 우량주 스캐너 감시 중...")
    try:
        raw_data = yf.download(WATCHLIST, period="1y", interval="1d", progress=False)
        closes = raw_data['Close']
        
        # 이번 실행에서 조건에 맞는 종목들 찾기
        current_detected = {}
        
        for ticker in WATCHLIST:
            try:
                series = closes[ticker].dropna()
                if len(series) < 30: continue
                
                rsi = float(calculate_rsi(series).iloc[-1])
                price = float(series.iloc[-1])
                
                # 조건 체크 (RSI < 25)
                if rsi < SCANNER_RSI_THRESHOLD:
                    t_info = yf.Ticker(ticker).info
                    if t_info.get('marketCap', 0) >= MARKET_CAP_LIMIT and \
                       t_info.get('profitMargins', 0) >= PROFIT_MARGIN_LIMIT:
                        current_detected[ticker] = {"price": price, "rsi": rsi}
            except: continue

        # 이전 상태 불러오기 (JSON)
        state_file = "scanner_state.json"
        prev_content = get_file_content(state_file)
        prev_detected = json.loads(prev_content) if prev_content else {}

        # A. 신규 진입 (New Entry)
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
            if SIGNAL_WEBHOOK: requests.post(SIGNAL_WEBHOOK, json=msg)
            print(f"  => 🚨 신규 종목 알림: {new_tickers}")

        # B. 회복/이탈 (Recovery)
        recovered_tickers = [t for t in prev_detected if t not in current_detected]
        if recovered_tickers:
            msg = {
                "content": "🛁 **[우량주 과매도 해소/이탈]**",
                "embeds": [{"description": f"다음 종목들이 조건에서 벗어났습니다:\n**{', '.join(recovered_tickers)}**", "color": 3447003}]
            }
            if SIGNAL_WEBHOOK: requests.post(SIGNAL_WEBHOOK, json=msg)
            print(f"  => 🟢 회복 종목 알림: {recovered_tickers}")

        # 상태 저장 (항상 최신 상태로 갱신)
        save_file_content(state_file, json.dumps(current_detected))
        
        if not new_tickers and not recovered_tickers:
            print("  => 특이사항 없음 (상태 유지)")

    except Exception as e:
        print(f"❌ 스캐너 에러: {e}")

# --- [4] 기능 3: 11시 정기 브리핑 (단순 보고) ---
def send_daily_qqq_briefing(today_str):
    print(f"\n📅 [Schedule] 11시 정기 브리핑 작성 중... ({today_str})")
    try:
        data = yf.download(QQQ_TICKER, period="2y", progress=False)
        df = data['Close'].dropna()
        if isinstance(df, pd.DataFrame): df = df.iloc[:, 0]
        
        price = float(df.iloc[-1])
        rsi = float(calculate_rsi(df).iloc[-1])
        ma120 = float(df.rolling(window=MA_SHORT).mean().iloc[-1])
        ma233 = float(df.rolling(window=MA_LONG).mean().iloc[-1])
        
        # 알림 내용 (매수 추천 아님, 단순 현황판)
        payload = {
            "content": f"🌙 **[{today_str}] 오늘장 QQQ 마감 현황**",
            "embeds": [{
                "title": "Daily Briefing",
                "description": (
                    f"• **Close**: `${price:.2f}`\n"
                    f"• **RSI**: `{rsi:.2f}`\n"
                    f"----------------\n"
                    f"• **MA{MA_SHORT}**: `${ma120:.2f}`\n"
                    f"• **MA{MA_LONG}**: `${ma233:.2f}`"
                ),
                "color": 3447003 # 파랑
            }]
        }
        if QQQ_WEBHOOK: requests.post(QQQ_WEBHOOK, json=payload)
        print("  => ✅ 정기 브리핑 전송 완료")
        
    except Exception as e:
        print(f"❌ 브리핑 생성 에러: {e}")

# --- [Main] 실행 컨트롤 타워 ---
def main():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    today_str = now.strftime("%Y-%m-%d")
    current_hour = now.hour
    
    print(f"▶️ 실행 시간: {now.strftime('%Y-%m-%d %H:%M:%S')} (KST)")

    # 1. 실시간 감시 (무조건 실행)
    #    - 상태 변화(진입/회복)가 있을 때만 알림이 감
    check_qqq_realtime_alert()
    check_watchlist_realtime_alert()

    # 2. 정기 브리핑 (23시에만, 하루 한 번)
    #    - 상태와 상관없이 무조건 현황 보고
    if current_hour == 23:
        log_file = "last_daily_briefing.txt"
        last_run = get_file_content(log_file)
        
        if last_run != today_str:
            send_daily_qqq_briefing(today_str)
            save_file_content(log_file, today_str)
        else:
            print("\nℹ️ 오늘의 정기 브리핑은 이미 발송되었습니다.")
    else:
        print(f"\n💤 정기 브리핑 시간이 아닙니다. (현재 {current_hour}시 / 예정 23시)")

if __name__ == "__main__":
    main()
