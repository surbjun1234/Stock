import yfinance as yf
import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime, timedelta, timezone

# --- [설정값] ---
# 신호가 올 때 보낼 전용 웹훅 (GitHub Secrets에 등록 필수)
SIGNAL_WEBHOOK_URL = os.environ.get("WEBHOOK_SIGNAL") 
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

    data = yf.download(TARGET_TICKER, period="2y")
    if data.empty:
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
    df['RSI'] = calculate_rsi(df['Close'], RSI_PERIOD)

    last_row = df.iloc[-1]
    curr_price = float(last_row['Close'])
    ma120 = float(last_row['MA120'])
    ma233 = float(last_row['MA233'])
    rsi = float(last_row['RSI'])

    # 판정 조건
    target_ma = max(ma120, ma233)
    is_under_ma = curr_price < target_ma
    is_low_rsi = rsi < RSI_THRESHOLD

    print(f"현재가: ${curr_price:.2f} / 기준선: ${target_ma:.2f} / RSI: {rsi:.2f}")

    # --- [매수 신호 발생 시에만 전용 방으로 전송] ---
    if is_under_ma and is_low_rsi:
        send_discord_signal(today_str, curr_price, rsi, ma120, ma233)
    else:
        print("💡 매수 조건이 아닙니다. 조용히 넘어갑니다.")

def send_discord_signal(date, price, rsi, ma120, ma233):
    if not SIGNAL_WEBHOOK_URL:
        print("⚠️ 전용 웹훅 URL이 설정되지 않았습니다.")
        return

    content = f"🚨 **[TQQQ 매수 신호] 지금 사격 개시!**"

    description = (
        f"📅 **날짜:** {date}\n"
        f"💰 **QQQ 현재가:** `${price:.2f}`\n"
        f"📉 **RSI 지수:** `{rsi:.2f}`\n\n"
        f"**[기술적 분석 결과]**\n"
        f"• MA120: `${ma120:.2f}`\n"
        f"• MA233: `${ma233:.2f}`\n\n"
        f"🔥 **장기 추세선 하단 및 과매도 조건 동시 충족!**\n"
        f"👉 **TQQQ 50,000원 즉시 매수를 고려하세요.**"
    )

    payload = {
        "content": content,
        "embeds": [{
            "title": "🎯 매수 저격 알림 (TQQQ Sniper)",
            "description": description,
            "color": 15158332, # 붉은색
            "footer": {"text": "이 알림은 조건 충족 시에만 발송됩니다."}
        }]
    }
    requests.post(SIGNAL_WEBHOOK_URL, json=payload)
    print("✅ 매수 신호 전송 완료!")

if __name__ == "__main__":
    main()
