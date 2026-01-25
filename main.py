import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta, timezone

# --- [1] 웹훅 설정 (Secrets에서 가져옴) ---
QQQ_WEBHOOK = os.environ.get("WEBHOOK_QQQ")       # 11시 현황 브리핑용
SIGNAL_WEBHOOK = os.environ.get("WEBHOOK_SIGNAL") # 실시간 매수/회복 알림용
RSI_WEBHOOK = os.environ.get("WEBHOOK_RSI")       # 11시 우량주 스캐너용

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

# --- [3] 파일 입출력 함수 (상태 저장용) ---
def get_file_content(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return f.read().strip()
    return ""

def save_file_content(filename, content):
    with open(filename, "w") as f:
        f.write(content)

def calculate_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# --- [4] 핵심 기능: QQQ 매수/회복 감지 ---
def check_qqq_buy_signal(today_str):
    print("⚡ [Real-time] QQQ 매수 신호 체크 중...")
    data = yf.download(QQQ_TICKER, period="1y", interval="1d", progress=False)
    if data.empty: return

    # 데이터 정리
    if isinstance(data.columns, pd.MultiIndex):
        df = data['Close'].iloc[:, 0].to_frame()
    else:
        df = data[['Close']].copy()
    df.columns = ['Close']
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
    
    # 지표 계산
    df['MA120'] = df['Close'].rolling(window=MA_SHORT).mean()
    df['MA233'] = df['Close'].rolling(window=MA_LONG).mean()
    df['RSI'] = calculate_rsi(df['Close'], 14)

    last_row = df.iloc[-1]
    curr_price = float(last_row['Close'])
    ma120 = float(last_row['MA120'])
    ma233 = float(last_row['MA233'])
    rsi = float(last_row['RSI'])
    target_ma = max(ma120, ma233) # 120일선, 233일선 중 더 높은 가격 기준

    # 상태 파일 확인
    state_file = "qqq_signal_state.txt"
    last_state_str = get_file_content(state_file)

    # ★ 매수 조건: (가격 < 이평선) AND (RSI < 40)
    is_buy_condition = (curr_price < target_ma) and (rsi < QQQ_RSI_THRESHOLD)

    # [A] 매수 조건 충족 시
    if is_buy_condition:
        # 오늘 날짜로 보낸 기록이 없으면 보냄 (날짜가 바뀌면 다시 보냄)
        expected_state = f"SENT_{today_str}"
        
        if last_state_str != expected_state:
            if SIGNAL_WEBHOOK:
                msg = {
                    "content": "🚨 **[TQQQ 매수 기회 발생]**",
                    "embeds": [{
                        "title": "진입 조건 충족",
                        "description": f"• 현재가: ${curr_price:.2f}\n• 이평선: ${target_ma:.2f}\n• RSI: {rsi:.2f} (기준 {QQQ_RSI_THRESHOLD})\n👉 매수 구간입니다.",
                        "color": 15158332 # 빨강
                    }]
                }
                requests.post(SIGNAL_WEBHOOK, json=msg)
                print("✅ 매수 알림 전송 완료")
            
            # 상태 저장: 'SENT_2024-01-01' 형식
            save_file_content(state_file, expected_state)
        else:
            print("ℹ️ 오늘 이미 매수 신호를 보냈으므로 생략합니다.")

    # [B] 매수 조건 해제 (회복) 시
    else:
        # 이전에 신호를 보낸 상태였다면 -> 회복 알림 발송 & 리셋
        if last_state_str.startswith("SENT"):
            print("✅ RSI/주가가 정상화되었습니다.")
            if SIGNAL_WEBHOOK:
                msg = {
                    "content": "🟢 **[매수 구간 종료]** 신호 해제",
                    "embeds": [{
                        "description": f"현재 RSI: {rsi:.2f} / 주가: ${curr_price:.2f}\n정상 범위로 회복되었습니다.",
                        "color": 3066993 # 초록
                    }]
                }
                requests.post(SIGNAL_WEBHOOK, json=msg)
            
            # 상태 리셋
            save_file_content(state_file, "NORMAL")
        else:
            print(f"특이사항 없음 (Price: {curr_price:.2f}, RSI: {rsi:.2f})")

# --- [5] 핵심 기능: 11시 정기 브리핑 ---
def run_daily_briefing(today_str):
    print(f"📅 [Daily] 11시 정기 브리핑 시작 ({today_str})")
    
    # 1. QQQ 현황
    data = yf.download(QQQ_TICKER, period="6mo", progress=False)
    if not data.empty:
        if isinstance(data.columns, pd.MultiIndex):
            closes = data['Close'].iloc[:, 0]
        else:
            closes = data['Close']
        rsi = calculate_rsi(closes).iloc[-1]
        price = closes.iloc[-1]
        
        if QQQ_WEBHOOK:
            payload = {
                "content": f"🌙 **[{today_str}] 오늘장 QQQ 브리핑**",
                "embeds": [{"description": f"Price: `${price:.2f}`\nRSI: `{rsi:.2f}`", "color": 3447003}]
            }
            requests.post(QQQ_WEBHOOK, json=payload)

    # 2. 우량주 스캐너
    print("🔭 우량주 스캔 시작...")
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
            
            current_rsi = calculate_rsi(series).iloc[-1]
            current_price = series.iloc[-1]

            if current_rsi < SCANNER_RSI_THRESHOLD:
                # 재무 정보 확인 (시총 & 이익률)
                try:
                    t_info = yf.Ticker(ticker).info
                    if t_info.get('marketCap', 0) >= MARKET_CAP_LIMIT and \
                       t_info.get('profitMargins', 0) >= PROFIT_MARGIN_LIMIT:
                        found_list.append(f"**{ticker}** (${current_price:.2f}) | RSI: {current_rsi:.2f}")
                except: pass
        except: pass

    if found_list and RSI_WEBHOOK:
        desc = "\n".join(found_list)
        requests.post(RSI_WEBHOOK, json={
            "content": "💎 **오늘의 과매도 우량주 발견**",
            "embeds": [{"description": desc, "color": 16711680}]
        })
    else:
        print("💡 스캔 결과 없음")

# --- [Main] 실행 진입점 ---
def main():
    # 한국 시간 설정
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    today_str = now.strftime("%Y-%m-%d")
    current_hour = now.hour
    
    print(f"현재 시간(KST): {now.strftime('%H:%M')}")

    # [Step 1] 매수 신호 체크 (매번 실행)
    check_qqq_buy_signal(today_str)

    # [Step 2] 정기 보고 (밤 11시에 한 번만)
    # 23시라면 11시 5분이든 50분이든 상관없이 체크
    daily_log_file = "last_daily_run.txt"
    last_run_date = get_file_content(daily_log_file)

    if current_hour == 23:
        if last_run_date != today_str:
            # 아직 오늘 날짜 도장이 없으면 -> 실행 후 도장 찍기
            run_daily_briefing(today_str)
            save_file_content(daily_log_file, today_str)
        else:
            print("📅 오늘의 정기 보고는 이미 완료되었습니다.")
    else:
        print("💤 정기 보고 시간이 아닙니다 (23:00 예정)")

if __name__ == "__main__":
    main()
