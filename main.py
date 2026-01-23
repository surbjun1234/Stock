import yfinance as yf
import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime, timedelta, timezone

# --- [설정값] ---
# GitHub Secrets에 각각 등록해야 합니다.
QQQ_WEBHOOK = os.environ.get("WEBHOOK_QQQ")     # 매일 현황 보고용
SIGNAL_WEBHOOK = os.environ.get("WEBHOOK_SIGNAL") # 매수 신호 발생용

TARGET_TICKER = "QQQ"
MA_SHORT = 120
MA_LONG = 233
RSI_PERIOD = 14
RSI_THRESHOLD = 40

def calculate_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

def main():
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    today_str = now_kst.strftime("%Y-%m-%d")

    print(f"🚀 {today_str} 전략 분석 시작...")

    # 1. 데이터 다운로드
    data = yf.download(TARGET_TICKER, period="2y")
    if data.empty: return

    # 2. 데이터 정리
    if isinstance(data.columns, pd.MultiIndex):
        df = data['Close'].iloc[:, 0].to_frame()
    else:
        df = data[['Close']].copy()
    
    df.columns = ['Close']
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')

    # 3. 지표 계산
    df['MA120'] = df['Close'].rolling(window=MA_SHORT).mean()
    df['MA233'] = df['Close'].rolling(window=MA_LONG).mean()
    df['RSI'] = calculate_rsi(df['Close'], RSI_PERIOD)

    last_row = df.iloc[-1]
    curr_price = float(last_row['Close'])
    ma120 = float(last_row['MA120'])
    ma233 = float(last_row['MA233'])
    rsi = float(last_row['RSI'])
    target_ma = max(ma120, ma233)

    # 4. [매일 실행] QQQ 채널에 현황 보고
    send_daily_report(today_str, curr_price, rsi, ma120, ma233)

    # 5. [조건 만족 시] SIGNAL 채널에 매수 신호 전송
    if curr_price < target_ma and rsi < RSI_THRESHOLD:
        send_buy_signal(today_str, curr_price, rsi, ma120, ma233)
    else:
        print("💡 매수 조건은 아닙니다.")

def send_daily_report(date, price, rsi, ma120, ma233):
    if not QQQ_WEBHOOK: return
    
    payload = {
        "content": f"📅 **{date} QQQ 일일 현황 보고**",
        "embeds": [{
            "title": "🔍 현재 시장 지표",
            "description": (
                f"• 현재가: `${price:.2f}`\n"
                f"• RSI: `{rsi:.2f}`\n"
                f"• MA120: `${ma120:.2f}`\n"
                f"• MA233: `${ma233:.2f}`"
            ),
            "color": 3447003 # 파란색
        }]
    }
    requests.post(QQQ_WEBHOOK, json=payload)
    print("✅ 일일 현황 보고 완료")

def send_buy_signal(date, price, rsi, ma120, ma233):
    if not SIGNAL_WEBHOOK: return
    
    payload = {
        "content": "🚨 **[TQQQ 매수 저격] 신호 발생!**",
        "embeds": [{
            "title": "🎯 지금이 매수 타이밍입니다!",
            "description": (
                f"🔥 **조건 충족 (AND)**\n"
                f"• 주가 < 이평선 (기준: ${max(ma120, ma233):.2f})\n"
                f"• RSI < {RSI_THRESHOLD} (현재: {rsi:.2f})\n\n"
                f"👉 **TQQQ 50,000원 매수를 진행하세요!**"
            ),
            "color": 15158332 # 빨간색
        }]
    }
    requests.post(SIGNAL_WEBHOOK, json=payload)
    print("✅ 매수 신호 전송 완료")

if __name__ == "__main__":
    main()
