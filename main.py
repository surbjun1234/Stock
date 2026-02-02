import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime, timedelta, timezone

# --- [0] 경로 설정 (스케줄러 실행 시 경로 오류 방지) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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

# --- [3] 파일 입출력 함수 (절대 경로 적용) ---
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
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

# --- [4] 핵심 기능: QQQ 매수/회복 감지 ---
def check_qqq_buy_signal(today_str):
    print("⚡ [Real-time] QQQ 매수 신호 체크 중...", flush=True)
    try:
        # 이평선 계산을 위해 충분한 기간(2y) 확보
        data = yf.download(QQQ_TICKER, period="2y", interval="1d", progress=False)
        if data.empty: 
            print("❌ QQQ 데이터를 불러올 수 없습니다.")
            return

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
        target_ma = max(ma120, ma233) 

        # 상태 파일 확인
        state_file = "qqq_signal_state.txt"
        last_state_str = get_file_content(state_file)

        # ★ 매수 조건: (가격 < 높은 이평선) AND (RSI < 40)
        is_buy_condition = (curr_price < target_ma) and (rsi < QQQ_RSI_THRESHOLD)

        # [A] 매수 조건 충족 시
        if is_buy_condition:
            expected_state = f"SENT_{today_str}"
            
            if last_state_str != expected_state:
                if SIGNAL_WEBHOOK:
                    msg = {
                        "content": "🚨 **[TQQQ 매수 기회 발생]**",
                        "embeds": [{
                            "title": "진입 조건 충족 (Price < MA & RSI < 40)",
                            "description": (
                                f"• **현재가**: `${curr_price:.2f}`\n"
                                f"• **RSI**: `{rsi:.2f}` (기준 {QQQ_RSI_THRESHOLD})\n"
                                f"----------------------\n"
                                f"• **MA{MA_SHORT}**: `${ma120:.2f}`\n"
                                f"• **MA{MA_LONG}**: `${ma233:.2f}`\n"
                                f"👉 현재가가 주요 이평선보다 낮습니다."
                            ),
                            "color": 15158332 # 빨강
                        }]
                    }
                    requests.post(SIGNAL_WEBHOOK, json=msg)
                    print(f"✅ 매수 알림 전송: Price ${curr_price} < MA ${target_ma}")
                
                save_file_content(state_file, expected_state)
            else:
                print("ℹ️ 오늘 이미 매수 신호를 보냈으므로 생략합니다.")

        # [B] 매수 조건 해제 (회복) 시
        else:
            if last_state_str.startswith("SENT"):
                print("✅ RSI/주가가 정상화되었습니다.")
                if SIGNAL_WEBHOOK:
                    msg = {
                        "content": "🟢 **[매수 구간 종료]** 신호 해제",
                        "embeds": [{
                            "description": f"주가가 이평선 위로 회복했거나 RSI가 안정되었습니다.\n• 현재가: ${curr_price:.2f}\n• RSI: {rsi:.2f}",
                            "color": 3066993 # 초록
                        }]
                    }
                    requests.post(SIGNAL_WEBHOOK, json=msg)
                
                save_file_content(state_file, "NORMAL")
            else:
                print(f"특이사항 없음 (Price: {curr_price:.2f} > MA: {target_ma:.2f} or RSI Safe)")
                
    except Exception as e:
        print(f"❌ QQQ 체크 중 에러 발생: {e}")

# --- [5] 핵심 기능: 11시 정기 브리핑 ---
def run_daily_briefing(today_str):
    print(f"📅 [Daily] 11시 정기 브리핑 시작 ({today_str})", flush=True)
    
    # 1. QQQ 현황 브리핑
    try:
        # [수정] 233일선 계산을 위해 기간을 2y로 늘림
        data = yf.download(QQQ_TICKER, period="2y", progress=False)
        
        if not data.empty:
            if isinstance(data.columns, pd.MultiIndex):
                df = data['Close'].iloc[:, 0].to_frame()
            else:
                df = data[['Close']].copy()
            df.columns = ['Close']
            
            # 지표 계산 추가
            df['MA120'] = df['Close'].rolling(window=MA_SHORT).mean()
            df['MA233'] = df['Close'].rolling(window=MA_LONG).mean()
            rsi_series = calculate_rsi(df['Close'])
            
            # 마지막 값 추출
            last_row = df.iloc[-1]
            price = float(last_row['Close'])
            ma120 = float(last_row['MA120'])
            ma233 = float(last_row['MA233'])
            rsi = float(rsi_series.iloc[-1])
            
            if QQQ_WEBHOOK:
                payload = {
                    "content": f"🌙 **[{today_str}] 오늘장 QQQ 브리핑**",
                    "embeds": [{
                        "title": "QQQ 마감 현황",
                        "description": (
                            f"• **Close**: `${price:.2f}`\n"
                            f"• **RSI**: `{rsi:.2f}`\n"
                            f"----------------------\n"
                            f"• **MA{MA_SHORT}**: `${ma120:.2f}`\n"
                            f"• **MA{MA_LONG}**: `${ma233:.2f}`"
                        ),
                        "color": 3447003
                    }]
                }
                requests.post(QQQ_WEBHOOK, json=payload)
    except Exception as e:
        print(f"❌ QQQ 브리핑 데이터 에러: {e}")

    # 2. 우량주 스캐너
    print("🔭 우량주 스캔 시작...", flush=True)
    try:
        data = yf.download(WATCHLIST, period="6mo", progress=False)
        if data.empty:
            print("❌ 우량주 데이터 다운로드 실패")
            return

        if isinstance(data.columns, pd.MultiIndex):
            closes = data['Close']
        else:
            closes = pd.DataFrame(data['Close']) if 'Close' in data else data

        found_list = []
        for ticker in WATCHLIST:
            try:
                if ticker not in closes.columns: continue
                series = closes[ticker].dropna()
                if len(series) < 15: continue
                
                current_rsi = calculate_rsi(series).iloc[-1]
                current_price = series.iloc[-1]

                if current_rsi < SCANNER_RSI_THRESHOLD:
                    try:
                        t_info = yf.Ticker(ticker).info
                        if t_info.get('marketCap', 0) >= MARKET_CAP_LIMIT and \
                           t_info.get('profitMargins', 0) >= PROFIT_MARGIN_LIMIT:
                            found_list.append(f"**{ticker}** (${current_price:.2f}) | RSI: {current_rsi:.2f}")
                    except: 
                        pass 
            except: 
                pass

        if found_list:
            print(f"💎 발견된 우량주: {len(found_list)}개")
            if RSI_WEBHOOK:
                desc = "\n".join(found_list)
                requests.post(RSI_WEBHOOK, json={
                    "content": "💎 **오늘의 과매도 우량주 발견**",
                    "embeds": [{"description": desc, "color": 16711680}]
                })
        else:
            print("💡 조건(RSI < 25)을 만족하는 우량주가 없습니다.")
            
    except Exception as e:
        print(f"❌ 우량주 스캔 중 치명적 에러: {e}")

# --- [Main] 실행 진입점 ---
def main():
    try:
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst)
        today_str = now.strftime("%Y-%m-%d")
        current_hour = now.hour
        
        print(f"현재 시간(KST): {now.strftime('%Y-%m-%d %H:%M')}", flush=True)

        # [Step 1] 매수 신호 체크
        check_qqq_buy_signal(today_str)

        # [Step 2] 정기 보고 (23시 대 실행)
        daily_log_file = "last_daily_run.txt"
        last_run_date = get_file_content(daily_log_file)

        if current_hour == 23:
            if last_run_date != today_str:
                run_daily_briefing(today_str)
                save_file_content(daily_log_file, today_str)
                print("✅ 오늘의 정기 보고를 완료하고 기록했습니다.")
            else:
                print("📅 오늘의 정기 보고는 이미 완료되었습니다.")
        else:
            print(f"💤 정기 보고 시간이 아닙니다 (현재 {current_hour}시 / 예정 23시)")
            
    except Exception as e:
        print(f"❌ 메인 루프 에러: {e}")

if __name__ == "__main__":
    main()
