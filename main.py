import yfinance as yf
import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime, timedelta, timezone

# --- [설정값] ---
DISCORD_WEBHOOK_URL = os.environ.get("WEBHOOK_QQQ") # GitHub Secrets에 저장필요
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
    # 1. 한국 시간 설정
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    today_str = now_kst.strftime("%Y-%m-%d")

    print(f"🚀 {today_str} QQQ 전략 분석 시작...")

    # 2. 데이터 가져오기 (이평선 계산을 위해 충분한 데이터 확보)
    data = yf.download(TARGET_TICKER, period="2y")
    if data.empty:
        print("데이터를 가져오지 못했습니다.")
        return

    # 데이터 정리 (Multi-index 제거 및 종가 추출)
    df = data['Close'].to_frame()
    df.columns = ['Close']

    # 3. 지표 계산
    df['MA120'] = df['Close'].rolling(window=MA_SHORT).mean()
    df['MA233'] = df['Close'].rolling(window=MA_LONG).mean()
    df['RSI'] = calculate_rsi(df['Close'], RSI_PERIOD)

    # 4. 조건 검사 (가장 최근 데이터 기준)
    last_row = df.iloc[-1]
    curr_price = last_row['Close']
    ma120 = last_row['MA120']
    ma233 = last_row['MA233']
    rsi = last_row['RSI']

    # 조건 1: 주가가 120일선 또는 233일선보다 낮은가?
    is_under_ma = curr_price < max(ma120, ma233)
    # 조건 2: RSI가 40 미만인가?
    is_low_rsi = rsi < RSI_THRESHOLD

    print(f"현재가: {curr_price:.2f}, MA120: {ma120:.2f}, MA233: {ma233:.2f}, RSI: {rsi:.2f}")

    # 5. 디스코드 전송
    if is_under_ma and is_low_rsi:
        send_discord(today_str, curr_price, rsi, ma120, ma233)
    else:
        print("💡 매수 조건이 충족되지 않았습니다.")

def send_discord(date, price, rsi, ma120, ma233):
    if not DISCORD_WEBHOOK_URL:
        print("웹훅 URL이 없습니다.")
        return

    # 모바일 알림창 요약
    content = f"❗ **[{date}] TQQQ 매수 신호 발생!**"

    # 상세 카드 내용 (요청하신 굵은 글씨 스타일)
    description = (
        f"• **QQQ 현재가: ${price:.2f}**\n"
        f"• **RSI 지수: {rsi:.2f}**\n\n"
        f"**[이동평균선 정보]**\n"
        f"• MA120: ${ma120:.2f}\n"
        f"• MA233: ${ma233:.2f}\n\n"
        f"👉 **지금 TQQQ 분할 매수를 고려하세요!**"
    )

    payload = {
        "content": content,
        "embeds": [{
            "title": "📈 QQQ 기술적 분석 알림",
            "description": description,
            "color": 15158332,
            "footer": {"text": "KNU 야수 스케줄러"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)
    print("✅ 디스코드 알림 전송 완료")

if __name__ == "__main__":
    main()
