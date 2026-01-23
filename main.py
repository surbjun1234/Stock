import yfinance as yf
import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime, timedelta, timezone

# --- [설정값] ---
# GitHub Secrets에 'WEBHOOK_QQQ'라는 이름으로 등록해야 합니다.
DISCORD_WEBHOOK_URL = os.environ.get("WEBHOOK_QQQ") 
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
    # 1. 한국 시간 설정 (KST)
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    today_str = now_kst.strftime("%Y-%m-%d")

    print(f"🚀 {today_str} QQQ 전략 분석 시작 (조건: MA 120/233 AND RSI < {RSI_THRESHOLD})")

    # 2. 데이터 다운로드
    data = yf.download(TARGET_TICKER, period="2y")
    if data.empty:
        print("❌ 데이터를 가져오지 못했습니다.")
        return

    # 3. 데이터 정리 (yfinance 최신 버전 멀티인덱스 대응)
    if isinstance(data.columns, pd.MultiIndex):
        df = data['Close'].iloc[:, 0].to_frame()
    else:
        df = data[['Close']].copy()
    
    df.columns = ['Close']
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')

    # 4. 지표 계산
    df['MA120'] = df['Close'].rolling(window=MA_SHORT).mean()
    df['MA233'] = df['Close'].rolling(window=MA_LONG).mean()
    df['RSI'] = calculate_rsi(df['Close'], RSI_PERIOD)

    # 5. 최신 데이터 추출
    last_row = df.iloc[-1]
    curr_price = float(last_row['Close'])
    ma120 = float(last_row['MA120'])
    ma233 = float(last_row['MA233'])
    rsi = float(last_row['RSI'])

    # --- [매수 신호 판정] ---
    # 조건 1: 이평선 기준 (120일선 또는 233일선 중 높은 선보다 주가가 낮은지)
    target_ma = max(ma120, ma233)
    is_under_ma = curr_price < target_ma
    
    # 조건 2: RSI 기준
    is_low_rsi = rsi < RSI_THRESHOLD

    print(f"📊 분석 결과: 현재가 ${curr_price:.2f} / 기준선 ${target_ma:.2f} / RSI {rsi:.2f}")

    # 6. AND 조건 만족 시 알림 전송
    if is_under_ma and is_low_rsi:
        send_discord(today_str, curr_price, rsi, ma120, ma233)
    else:
        print("💡 조건이 충족되지 않아 알림을 보내지 않았습니다.")

def send_discord(date, price, rsi, ma120, ma233):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ 디스코드 웹훅 URL이 설정되지 않았습니다.")
        return

    content = f"❗ **[{date}] TQQQ 강력 매수 신호 발생!**"

    description = (
        f"**[시장 상태 분석]**\n"
        f"• **QQQ 현재가:** `${price:.2f}`\n"
        f"• **RSI 지수:** `{rsi:.2f}` (기준: {RSI_THRESHOLD} 미만)\n\n"
        f"**[이동평균선 정보]**\n"
        f"• MA120: `${ma120:.2f}`\n"
        f"• MA233: `${ma233:.2f}`\n\n"
        f"✅ **장기 추세선 이탈과 과매도 구간이 겹쳤습니다.**\n"
        f"👉 **TQQQ 50,000원 분할 매수를 추천합니다!**"
    )

    payload = {
        "content": content,
        "embeds": [{
            "title": "📈 QQQ 기술적 분석 알림 (AND 전략)",
            "description": description,
            "color": 15158332,
            "footer": {"text": "TQQQ Sniper Bot"}
        }]
    }
    requests.post(DISCORD_WEBHOOK_URL, json=payload)
    print("✅ 디스코드 알림이 성공적으로 전송되었습니다.")

if __name__ == "__main__":
    main()
