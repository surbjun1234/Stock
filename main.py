import yfinance as yf
import pandas as pd
import requests
import os
import json
from datetime import datetime, timedelta, timezone

# --- [0] 경로 및 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 웹훅 설정
QQQ_WEBHOOK = os.environ.get("WEBHOOK_QQQ")       
SIGNAL_WEBHOOK = os.environ.get("WEBHOOK_SIGNAL") 
RSI_WEBHOOK = os.environ.get("WEBHOOK_RSI")       

# 전략 설정
QQQ_TICKER = "QQQ"
MA_SHORT, MA_LONG = 120, 233
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
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def save_file_content(filename, content):
    file_path = os.path.join(BASE_DIR, filename)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

def calculate_rsi(series, period=14):
    delta = series.diff()
    up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / (ema_down + 1e-10)
    return 100 - (100 / (1 + rs))

# --- [4] 핵심 기능: 우량주 추적 스캐너 ---
def run_stock_scanner(today_str):
    print("\n" + "="*50)
    print(f"🔭 [우량주 추적 스캐너] {today_str}")
    print("="*50)
    
    try:
        # 데이터 일괄 다운로드
        raw_data = yf.download(WATCHLIST, period="1y", interval="1d", progress=False)
        closes = raw_data['Close']
        
        # 현재 조건 충족하는 종목 리스트 추출
        current_detected = {}
        
        for ticker in WATCHLIST:
            try:
                series = closes[ticker].dropna()
                if len(series) < 30: continue
                
                rsi = float(calculate_rsi(series).iloc[-1])
                price = float(series.iloc[-1])
                dt_str = series.index[-1].strftime('%m/%d')

                # 디버그 로그
                status_icon = "🔥" if rsi < SCANNER_RSI_THRESHOLD else "⚪"
                print(f"  {status_icon} {ticker:5}: RSI {rsi:5.2f} | Price ${price:8.2f} | 날짜 {dt_str}", end="")

                if rsi < SCANNER_RSI_THRESHOLD:
                    t_info = yf.Ticker(ticker).info
                    m_cap = t_info.get('marketCap', 0)
                    p_margin = t_info.get('profitMargins', 0)

                    if m_cap >= MARKET_CAP_LIMIT and p_margin >= PROFIT_MARGIN_LIMIT:
                        current_detected[ticker] = {"price": price, "rsi": rsi}
                        print(" -> [조건 일치]")
                    else:
                        print(f" -> [제외] 시총/이익률 미달")
                else:
                    print("") # 줄바꿈
            except: continue

        # 이전 상태 불러오기 (JSON 형식)
        state_file = "scanner_state.txt"
        prev_state_str = get_file_content(state_file)
        prev_detected = json.loads(prev_state_str) if prev_state_str else {}

        # 1. 신규 진입 종목 알림
        new_items = [t for t in current_detected if t not in prev_detected]
        if new_items:
            msg_content = "🚨 **[신규 과매도 우량주 발견]**\n"
            for t in new_items:
                msg_content += f"• **{t}**: RSI `{current_detected[t]['rsi']:.2f}` ($ {current_detected[t]['price']:.2f})\n"
            if RSI_WEBHOOK:
                requests.post(RSI_WEBHOOK, json={"content": msg_content})
            print(f"  📢 신규 알림 전송: {new_items}")

        # 2. 이탈(회복) 종목 알림
        recovered_items = [t for t in prev_detected if t not in current_detected]
        if recovered_items:
            msg_content = "🟢 **[우량주 과매도 구간 종료]**\n"
            for t in recovered_items:
                msg_content += f"• **{t}**: 기준치 회복 또는 조건 이탈\n"
            if RSI_WEBHOOK:
                requests.post(RSI_WEBHOOK, json={"content": msg_content})
            print(f"  📢 회복 알림 전송: {recovered_items}")

        # 현재 상태 저장
        save_file_content(state_file, json.dumps(current_detected))

    except Exception as e:
        print(f"❌ 스캐너 에러: {e}")

# --- [5] QQQ 실시간 체크 ---
def check_qqq_buy_signal(today_str):
    print("\n📡 [QQQ 실시간 감시]")
    try:
        data = yf.download(QQQ_TICKER, period="2y", interval="1d", progress=False)
        df = data['Close'].copy().dropna()
        if isinstance(df, pd.DataFrame): df = df.iloc[:, 0]
        
        curr_price = float(df.iloc[-1])
        ma120 = float(df.rolling(window=MA_SHORT).mean().iloc[-1])
        ma233 = float(df.rolling(window=MA_LONG).mean().iloc[-1])
        rsi = float(calculate_rsi(df).iloc[-1])
        target_ma = max(ma120, ma233)

        state_file = "qqq_signal_state.txt"
        last_state = get_file_content(state_file)
        is_buy = (curr_price < target_ma) and (rsi < QQQ_RSI_THRESHOLD)

        if is_buy:
            if last_state != f"SENT_{today_str}":
                if SIGNAL_WEBHOOK:
                    requests.post(SIGNAL_WEBHOOK, json={"content": f"🚨 **[TQQQ 매수 기회]**\n가격: `${curr_price:.2f}` / RSI: `{rsi:.2f}`"})
                save_file_content(state_file, f"SENT_{today_str}")
        elif last_state.startswith("SENT"):
            if SIGNAL_WEBHOOK:
                requests.post(SIGNAL_WEBHOOK, json={"content": "🟢 **[TQQQ 매수 구간 종료]**"})
            save_file_content(state_file, "NORMAL")
    except Exception as e:
        print(f"❌ QQQ 체크 에러: {e}")

# --- [Main] ---
def main():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    today_str = now.strftime("%Y-%m-%d")

    # 1. QQQ는 실행할 때마다 체크
    check_qqq_buy_signal(today_str)

    # 2. 우량주 스캐너 실행 (23시 정기 실행 또는 필요시 수정)
    # 팁: 테스트를 위해 아래 hour 조건을 지우면 실행 때마다 즉시 확인합니다.
    if now.hour == 23:
        run_stock_scanner(today_str)
    else:
        print(f"\n💤 현재 {now.hour}시입니다. 스캐너는 23시에 작동합니다.")

if __name__ == "__main__":
    main()
