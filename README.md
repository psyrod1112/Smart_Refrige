# 스마트 냉장고 시스템

FIFO 원칙 기반의 식품 관리 시스템. 아두이노 센서 → 라즈베리파이 서버 → Flutter 앱으로 이어지는 IoT 파이프라인.

---

## 시스템 구성

```
[아두이노]  ──시리얼(9600baud)──▶  [라즈베리파이 Flask :5000]
  무게 센서                              │
  거리 센서                         ┌────┴────┐
  DHT 온습도                       카메라 OCR  SQLite DB
  LED (노랑/빨강)                  (Roboflow)
                                        │
                                   HTTP REST API
                                        │
                                  [Flutter 앱]
                                  Android / iOS
```

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 자동 유통기한 인식 | 카메라로 제품을 촬영하면 Roboflow OCR이 유통기한 날짜를 추출 |
| FIFO 자동 판별 | 거리 센서로 꺼낸 위치를 감지해 순서 위반 여부 자동 감지 |
| 수량 자동 계산 | 무게 변화량 ÷ 단위 무게로 꺼낸 개수 추산 |
| 유통기한 임박 알림 | 3일 이내 식품 발생 시 FCM 푸시 알림 (매일 09:00, 15:00) |
| 앱 수동 등록 | OCR 실패 시 앱에서 직접 이름·유통기한 입력 |
| 온습도 모니터링 | DHT 센서 실시간 조회 |

---

## 디렉토리 구조

```
Smart_Refrige/
├── NEWCODES/               # 라즈베리파이 서버
│   ├── main.py             # Flask API + 아두이노 시리얼 리스너
│   ├── camera.py           # Roboflow OCR 유통기한 파싱
│   ├── database.py         # SQLite CRUD
│   ├── fcm.py              # FCM HTTP v1 푸시 알림
│   └── fridge.db           # SQLite 데이터베이스 (자동 생성)
└── Front_Flutter/          # Flutter 모바일 앱
    └── lib/
        ├── main.dart
        ├── models/         # FoodItem, SlotStatus
        ├── providers/      # FoodProvider (상태 관리)
        ├── screens/        # 홈, 로그인, 메인, 설정
        └── services/       # api_service.dart, notification_service.dart
```

---

## 라즈베리파이 서버 실행

### 의존성 설치

```bash
pip install flask pyserial apscheduler picamera2 opencv-python requests \
            google-auth google-auth-httplib2
```

### 환경 변수 설정

```bash
export FCM_PROJECT_ID="your-firebase-project-id"
export FCM_SERVICE_ACCOUNT="firebase_service_account.json"  # 기본값
```

### 실행

```bash
cd NEWCODES
python main.py
```

서버는 `0.0.0.0:5000`에서 시작됩니다. 아두이노 포트는 `main.py` 상단의 `SERIAL_PORT` 변수로 변경하세요 (`/dev/ttyACM0` 또는 `/dev/ttyUSB0`).

---

## Flutter 앱 실행

기본 API 주소는 `http://192.168.137.97:5000`입니다. 라즈베리파이 IP가 다르면 빌드 시 주입하세요.

```bash
cd Front_Flutter
flutter pub get
flutter run --dart-define=API_BASE_URL=http://<라즈베리파이IP>:5000
```

---

## REST API 요약

| Method | Path | 설명 |
|--------|------|------|
| GET | `/foods` | 식품 목록 + 슬롯 상태 |
| POST | `/foods` | 앱 수동 식품 등록 |
| PATCH | `/foods/<id>` | 식품 정보 수정 |
| GET | `/environment` | 온습도 조회 |
| GET | `/dashboard` | 요약 정보 |
| GET | `/expiring?days=3` | 유통기한 임박 목록 |
| POST | `/scan/start` | 카메라 스캔 시작 |
| POST | `/inbound/manual` | 앱 수동 유통기한 입력 |
| POST | `/inbound/app_done` | 앱 입고 처리 완료 |
| POST | `/outbound/confirm` | 출고 확정 |
| POST | `/slot/resolve` | FIFO 오류 상태 해제 |
| POST | `/app/connect` | 앱 접속 알림 |
| POST | `/fcm/token` | FCM 토큰 등록 |

---

## 아두이노 ↔ 라즈베리파이 시리얼 프로토콜

**아두이노 → 라즈베리파이**

| 메시지 | 설명 |
|--------|------|
| `READY` | 아두이노 부팅 완료 |
| `INBOUND_REQ` | 입고 요청 |
| `INBOUND_CANCEL` | 입고 취소 |
| `CONFIRM_WEIGHT:<g>` | 입고 무게 확정 |
| `INBOUND_END` | 입고 세션 종료 |
| `OUTBOUND_REQ:W:<g>,D:<cm>` | 출고 감지 시작 (초기값) |
| `OUTBOUND_FINAL:W:<g>,D:<cm>` | 출고 감지 종료 (최종값) |
| `ENV:T:<°C>,H:<%>` | 온습도 데이터 |

**라즈베리파이 → 아두이노**

| 메시지 | 설명 |
|--------|------|
| `LED_Y:1/0` | 노란 LED (유통기한 임박) |
| `LED_R:0` | 빨간 LED 끄기 |
| `PROGRESS:1,FIFO:1,POS:<n>` | 스캔 성공, FIFO 정상, 진열 위치 |
| `PROGRESS:0` | 스캔 실패 |
| `OUTBOUND_FIFO_OK` | 출고 FIFO 정상 |
| `OUTBOUND_CONFIRM_ERR:<n>` | 출고 FIFO 위반, n개 |
| `INBOUND_DB_DONE:<pos>` | 앱 DB 수정 완료, 진열 위치 |
| `APP_CONNECTED` | 앱 접속 확인 |
| `DHT_REQ` | 온습도 즉시 읽기 요청 |
