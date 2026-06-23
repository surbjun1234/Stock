# Stock: 대형주 과매도 알림 및 주식 필터링 시스템

## 프로젝트 개요

`Stock` 프로젝트는 주요 대형주 및 ETF(QQQ)의 과매도 상태를 감지하고, 특정 기준(시가총액, 영업이익률)에 따라 주식을 필터링하여 사용자에게 알림을 제공하는 자동화된 시스템입니다. 이 시스템은 시장의 잠재적인 매수 기회를 포착하고, 관심 종목을 효율적으로 관리하는 데 도움을 줍니다.

## 주요 기능

*   **QQQ 과매도 알림**: QQQ ETF의 RSI(Relative Strength Index) 지표를 분석하여 과매도 상태를 감지하고, 설정된 웹훅을 통해 실시간 알림을 전송합니다.
*   **대형주 스캐너**: 시가총액 및 영업이익률 기준을 충족하는 대형주 목록을 스캔하고, RSI 지표를 활용하여 과매도 상태의 종목을 식별합니다.
*   **맞춤형 워치리스트**: 사용자가 지정한 워치리스트에 포함된 종목들에 대한 RSI 기반 과매도 알림을 제공합니다.
*   **자동화된 데이터 수집**: `yfinance` 라이브러리를 활용하여 주식 데이터를 자동으로 수집하고 분석합니다.
*   **웹훅 통합**: Discord와 같은 메시징 플랫폼에 분석 결과를 전송하여 사용자에게 신속하게 정보를 전달합니다.

## 사용 기술

*   **Python**: 핵심 로직 구현
*   **`yfinance`**: 주식 데이터 수집
*   **`pandas`**: 데이터 처리 및 분석
*   **`requests`**: 웹훅을 통한 알림 전송
*   **`json`**: 데이터 직렬화/역직렬화
*   **GitHub Actions**: 스케줄링된 작업 실행 (예상)

## 설치 및 실행 방법

1.  **레포지토리 클론**: 
    ```bash
    git clone https://github.com/surbjun1234/Stock.git
    cd Stock
    ```

2.  **의존성 설치**: 
    ```bash
    pip install -r requirements.txt
    ```

3.  **환경 변수 설정**: 
    `WEBHOOK_QQQ`, `WEBHOOK_SIGNAL`, `WEBHOOK_RSI` 환경 변수에 Discord 웹훅 URL을 설정해야 합니다. 이는 GitHub Secrets를 통해 관리하는 것이 권장됩니다.

4.  **실행**: 
    ```bash
    python main.py
    ```
    이 스크립트는 주로 GitHub Actions와 같은 CI/CD 환경에서 주기적으로 실행되도록 설계되었습니다.

## 파일 구조

```
Stock/
├── README.md
├── main.py                 # 핵심 로직 및 스캐너 구현
├── requirements.txt        # Python 의존성 목록
├── last_daily_briefing.txt # 일일 브리핑 결과 저장 (예상)
├── last_daily_run.txt      # 마지막 실행 시간 기록 (예상)
├── qqq_alert_state.txt     # QQQ 알림 상태 기록 (예상)
└── scanner_state.json      # 스캐너 상태 및 결과 저장 (예상)
```

## 기여

이 프로젝트에 기여하고 싶으시다면, Pull Request를 통해 코드 개선이나 새로운 기능 제안을 해주세요.

## 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다. 자세한 내용은 `LICENSE` 파일을 참조하세요. (현재 `LICENSE` 파일은 없지만, 추가될 수 있습니다.)
