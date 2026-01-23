import yfinance as yf
import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime, timedelta, timezone

# --- [설정값] ---
# GitHub Secrets에 등록한 이름과 동일해야 합니다.
DISCORD_WEBHOOK_URL = os.environ.get("WEBHOOK_QQQ") 
TARGET_TICKER = "QQQ"
MA_SHORT = 120
MA_LONG = 233
RSI_PERIOD = 14
RSI_THRESHOLD = 40 # 35에서 40으로 상향 조정

def calculate_rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=period - 1, adjust=False).mean()
    ema_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ema_up / ema_down
    return 100 - (100 / (1 + rs))

def main():
    # 1. 한국 시간 설정
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    today_str = now_kst.strftime("%Y-%m-%d")

    print(f"🚀 {today_str} 전략 분석 시작 (조건: MA 120/233 AND RSI < {RSI_THRESHOLD})")

    # 2. 데이터 가져오기 (충분한 계산을 위해 2년치 데이터)
    data = yf.download(TARGET_TICKER, period="2y")
    if data.empty:
        print("데이터를 가져오지 못했습니다.")
        return

    # 데이터 정리
    df = data['Close'].to_frame()
    df.columns = ['Close']

    # 3. 기술적 지표 계산
    df['MA120'] = df['Close'].rolling(window=MA_SHORT).mean()
    df['MA233'] = df['Close'].rolling(window=MA_LONG).mean()
    df['RSI'] = calculate_rsi(df['Close'], RSI_PERIOD)

    # 4. 최신 데이터 추출
    last_row = df.iloc[-1]
    curr_price = last_row['Close']
    ma120 = last_row['MA120']
    ma233 = last_row['MA233']
    rsi = last_row['RSI']

    # --- [핵심 조건 검사: AND] ---
    # 조건 A: 이평선 이탈 (120일선 또는 233일선보다 낮음)
    is_under_ma = curr_price < max(ma120, ma233)
    # 조건 B: RSI 40 미만
    is_low_rsi = rsi < RSI_THRESHOLD

    print(f"> 현재가: ${curr_price:.2f}")
    print(f"> 기준 이평선(Max): ${max(ma120, ma233):.2f} (MA120: {ma120:.2f}, MA233: {ma233:.2f})")
    print(f"> 현재 RSI: {rsi:.2f}")

    # 5. 두 조건 모두 만족 시 디스코드 전송
    if is_under_ma and is_low_rsi:
        send_discord(today_str, curr_price, rsi, ma120, ma233)
    else:
        print("💡 매수 조건이 충족되지 않았습니다. (알림 미전송)")

def send_discord(date, price, rsi, ma120, ma233):
    if not DISCORD_WEBHOOK_URL:
        print("웹훅 URL이 설정되지 않았습니다.")
        return

    content = f"❗ **[{date}] TQQQ 강력 매수 신호 발생! (5만원 투자)**"

    description = (
        f"**[시장 상태 분석]**\n"
        f"• **QQQ 현재가:** `${price:.2f}`\n"
        f"• **RSI 지수:** `{rsi:.2f}` (기준: {RSI_THRESHOLD} 미만)\n\n"
        f"**[이동평균선 정보]**\n"
        f"• MA120: `${ma120:.2f}`\n"
        f"• MA233: `${ma233:.2f}`\n\n"
        f"✅ **장기 추세선 아래 + 공포 구간(RSI 40)**이 겹쳤습니다.\n"
        f"👉 **TQQQ 50,000원 매수**를 진행하세요!"
    )

    payload = {
        "content": content,
        "embeds": [{
            "title": "📈 QQQ 기술적 분석 알림 (AND 전략)",
            "description": description,
            "color": 15158332, # 빨간색 계열
            "footer": {"text": "TQQQ Sniper Scheduler"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)
    print("✅ 디스코드 알림 전송 완료")

if __name__ == "__main__":
    main()
