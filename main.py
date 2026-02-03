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
MARKET_CAP_LIMIT = 200_000_000_000 # 2000억 달러
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
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / (ema_down + 1e-10)
    return 100 - (100 / (1 + rs))

# --- [4] QQQ 매수/회복 감지 ---
def check_qqq_buy_signal(today_str):
    print("\n" + "="*50)
    print(f"📡 [QQQ 실시간 감시] {today_str}")
    print("="*50)
    try:
        data = yf.download(QQQ_TICKER, period="2y", interval="1d", progress=False)
        if data.empty:
            print("❌ [오류] QQQ 데이터를 가져오지 못했습니다.")
            return

        df = data['Close'].copy()
        if isinstance(df, pd.DataFrame): df = df.iloc[:, 0]
        df = df.dropna()

        curr_price = float(df.iloc[-1])
        last_date = df.index[-1].strftime('%Y-%m-%d')
        ma120 = float(df.rolling(window=MA_SHORT).mean().iloc[-1])
        ma233 = float(df.rolling(window=MA_LONG).mean().iloc[-1])
        rsi = float(calculate_rsi(df).iloc[-1])
        target_ma = max(ma120, ma233)

        print(f"  > 기준 날짜: {last_date}")
        print(f"  > 현재가: ${curr_price:.2f} (MA기준선: ${target_ma:.2f})")
        print(f"  > RSI: {rsi:.2f} (매수기준: {QQQ_RSI_THRESHOLD})")

        state_file = "qqq_signal_state.txt"
        last_state_str = get_file_content(state_file)
        is_buy_condition = (curr_price < target_ma) and (rsi < QQQ_RSI_THRESHOLD)

        if is_buy_condition:
            print("  ⚠️ [BUY] 매수 조건 충족!")
            expected_state = f"SENT_{today_str}"
            if last_state_str != expected_state:
                if SIGNAL_WEBHOOK:
                    msg = {
                        "content": "🚨 **[TQQQ 매수 기회]**",
                        "embeds": [{
                            "title": "진입 조건 충족",
                            "description": f"기준일: {last_date}\n가 격: `${curr_price:.2f}`\nRSI: `{rsi:.2f}`",
                            "color": 15158332
                        }]
                    }
                    requests.post(SIGNAL_WEBHOOK, json=msg)
                save_file_content(state_file, expected_state)
        else:
            print("  ✅ [SAFE] 현재 매수 구간이 아닙니다.")
            if last_state_str.startswith("SENT"):
                print("  🔄 [INFO] 매수 구간 종료 감지 -> 상태 초기화")
                if SIGNAL_WEBHOOK:
                    requests.post(SIGNAL_WEBHOOK, json={"content": "🟢 **[매수 구간 종료]**"})
                save_file_content(state_file, "NORMAL")
    except Exception as e:
        print(f"❌ [QQQ 에러] {e}")

# --- [5] 정기 브리핑 및 우량주 스캐너 ---
def run_daily_briefing(today_str):
    print("\n" + "="*50)
    print(f"🔭 [우량주 스캐너] {today_str} 실행")
    print("="*50)
    
    # 1. 우량주 스캔
    try:
        raw_data = yf.download(WATCHLIST, period="1y", progress=False)
        closes = raw_data['Close']
        found_list = []

        for ticker in WATCHLIST:
            try:
                if ticker not in closes.columns:
                    print(f"  [-] {ticker:5}: 데이터 없음 (Skipped)")
                    continue
                
                series = closes[ticker].dropna()
                if len(series) < 30:
                    print(f"  [-] {ticker:5}: 데이터 부족 (Length: {len(series)})")
                    continue

                rsi_series = calculate_rsi(series)
                curr_rsi = float(rsi_series.iloc[-1])
                curr_price = float(series.iloc[-1])
                dt_str = series.index[-1].strftime('%m/%d')

                # 디버그: 모든 종목의 RSI 출력
                status_icon = "🔥" if curr_rsi < SCANNER_RSI_THRESHOLD else "⚪"
                print(f"  {status_icon} {ticker:5}: RSI {curr_rsi:5.2f} | Price {curr_price:8.2f} | 날짜 {dt_str}", end="")

                if curr_rsi < SCANNER_RSI_THRESHOLD:
                    # 조건 충족 시 추가 정보 확인
                    t_info = yf.Ticker(ticker).info
                    m_cap = t_info.get('marketCap', 0)
                    p_margin = t_info.get('profitMargins', 0)
                    
                    if m_cap >= MARKET_CAP_LIMIT and p_margin >= PROFIT_MARGIN_LIMIT:
                        print(" -> [PASS]")
                        found_list.append(f"**{ticker}** (${curr_price:.2f}) | RSI: `{curr_rsi:.2f}`")
                    else:
                        print(f" -> [FAIL] 시총:${m_cap/1e9:.0f}B, 이익률:{p_margin*100:.1f}%")
                else:
                    print("") # 줄바꿈

            except Exception as e:
                print(f" -> [ERROR] {e}")
                continue

        if found_list:
            print(f"\n✅ 스캔 완료: {len(found_list)}개 종목 발견")
            if RSI_WEBHOOK:
                requests.post(RSI_WEBHOOK, json={
                    "content": f"💎 **[{today_str}] 오늘의 과매도 우량주**",
                    "embeds": [{"description": "\n".join(found_list), "color": 16711680}]
                })
        else:
            print("\n💡 조건에 맞는 종목이 없습니다.")

    except Exception as e:
        print(f"❌ [스캐너 치명적 에러] {e}")

# --- [Main] ---
def main():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    today_str = now.strftime("%Y-%m-%d")
    
    print(f"\n▶️ 스크립트 실행 시작: {now.strftime('%Y-%m-%d %H:%M:%S')} (KST)")
    
    check_qqq_buy_signal(today_str)

    # 23시(오후 11시)에 브리핑 실행
    if now.hour == 23:
        log_file = "last_daily_run.txt"
        if get_file_content(log_file) != today_str:
            run_daily_briefing(today_str)
            save_file_content(log_file, today_str)
        else:
            print(f"\nℹ️ {today_str} 브리핑은 이미 오늘 실행되었습니다.")
    else:
        print(f"\n💤 현재 {now.hour}시입니다. 정기 브리핑은 23시에 실행됩니다.")

if __name__ == "__main__":
    main()
