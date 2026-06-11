#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <HX711.h>
#include <DHT.h>
#include <Servo.h>
#include <avr/pgmspace.h>

// ── 핀 정의
#define TRIG_PIN    7
#define ECHO_PIN    8
#define LED_RED     12
#define LED_YELLOW  13
#define HX711_DT    5
#define HX711_SCK   6
#define SWITCH_PIN1  2
#define SWITCH_PIN   2
#define INPUT_SWITCH  10
#define OUTPUT_SWITCH 11
#define BUZZER_PIN  3
#define DHT_PIN     4
#define DHT_TYPE    DHT11
#define SERVO_PIN   9

// ── OLED
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_ADDR     0x3C

// ── 상태
enum State { IDLE, WEIGHT_READY };

// ── 객체
Adafruit_SSD1306 oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
HX711 scale;
DHT   dht(DHT_PIN, DHT_TYPE);
Servo doorServo;

// ── 전역 변수
State        currentState    = IDLE;
bool         isDoorOpen      = false;
bool         oledReady       = false;
bool         oledActive      = false;
unsigned long oledClearAt    = 0;
unsigned long lastDhtSent    = 0;
unsigned long lastDoorChange = 0;
const unsigned long DOOR_MIN_MS  = 1000;
unsigned long lastDistRead   = 0;
const byte CMD_BUFFER_SIZE = 32;
const unsigned long CLOSE_WEIGHT_SETTLE_MS = 800;
const float DOOR_CLOSED_MAX_CM = 5.0f;
const float DOOR_OPEN_MIN_CM   = 10.0f;
const unsigned long DIST_INTERVAL = 200;  // 초음파는 200ms마다만 읽기

// ── 프로토타입
float readDistance();
void  sendCloseWeight();
void  handlePiCmd(const char* cmd);
void  showOled(const char* msg);
void  showOled(const __FlashStringHelper* msg);
void  trimCommand(char* cmd);
void  beep(int ms);
void  openDoor();
void  closeDoor();

// ──────────────────────────────────────────
void setup() {
  Serial.begin(9600);
  Serial.setTimeout(50);

  pinMode(TRIG_PIN,   OUTPUT);
  pinMode(ECHO_PIN,   INPUT);
  pinMode(LED_RED,    OUTPUT);
  pinMode(LED_YELLOW, OUTPUT);
  pinMode(SWITCH_PIN, INPUT_PULLUP);
  pinMode(BUZZER_PIN, OUTPUT);

  Wire.begin();
  delay(100);
  oledReady = oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  if (oledReady) {
    oled.clearDisplay();
    oled.setTextColor(SSD1306_WHITE);
    showOled(F("Ready"));
  }
  Serial.print(F("[LOG] OLED ")); Serial.println(oledReady ? F("OK") : F("FAIL"));

  scale.begin(HX711_DT, HX711_SCK);
  scale.set_scale(3379.f);
  scale.tare();
  Serial.println(F("[LOG] HX711 tare OK"));

  dht.begin();
  Serial.println(F("[LOG] DHT begin"));

  doorServo.attach(SERVO_PIN);
  doorServo.write(0);
  Serial.println(F("[LOG] Servo attached, pos=0 (closed)"));
  Serial.println(F("[LOG] setup done"));
}

// ──────────────────────────────────────────
void loop() {

  // ── ② 초음파 → 문 열림 감지 (200ms 간격) ─
  if (millis() - lastDistRead > DIST_INTERVAL) {
    lastDistRead = millis();
    float dist   = readDistance();
    bool  nextDoorOpen = isDoorOpen;

    if (dist == 0) {
      nextDoorOpen = true;
    } else if (dist < DOOR_CLOSED_MAX_CM) {
      nextDoorOpen = false;
    } else if (dist > DOOR_OPEN_MIN_CM) {
      nextDoorOpen = true;
    }

    if (nextDoorOpen != isDoorOpen && millis() - lastDoorChange > DOOR_MIN_MS) {
      bool wasDoorOpen = isDoorOpen;
      isDoorOpen     = nextDoorOpen;
      lastDoorChange = millis();
      Serial.print(F("[LOG] door "));
      Serial.print(isDoorOpen ? F("OPEN") : F("CLOSE"));
      Serial.print(F(" dist="));
      Serial.print(dist, 1);
      Serial.println(F("cm"));
      if (isDoorOpen) {
        Serial.println(F("DOOR:1"));
      } else {
        Serial.println(F("DOOR:0"));
      }
      digitalWrite(LED_YELLOW, isDoorOpen ? HIGH : LOW);
      if (wasDoorOpen && !isDoorOpen) {
        sendCloseWeight();
      }
    }
  }

  // ── ⑤ Pi 명령 수신 ──────────────────────
  if (Serial.available()) {
    char cmd[CMD_BUFFER_SIZE];
    size_t len = Serial.readBytesUntil('\n', cmd, CMD_BUFFER_SIZE - 1);
    cmd[len] = '\0';
    trimCommand(cmd);
    if (cmd[0] != '\0') {
      handlePiCmd(cmd);
    }
  }

  // ── ⑨ WEIGHT_READY → 스위치 감지 + 무게 + 온습도 전송 ──
  if (currentState == WEIGHT_READY && isDoorOpen) {
    if (digitalRead(SWITCH_PIN) == LOW) {
      float w = scale.get_units(5);
      if (w < 0) w = 0;
      float t = dht.readTemperature();
      float h = dht.readHumidity();
      beep(150);
      Serial.print(F("[LOG] switch w="));
      Serial.print(w, 1);
      Serial.print(F("g t="));
      Serial.print(isnan(t) ? -99.0f : t, 1);
      Serial.print(F(" h="));
      Serial.println(isnan(h) ? -99.0f : h, 1);
      // 온습도 유효하면 같이 전송, 아니면 기본값 -99
      if (!isnan(t) && !isnan(h)) {
        Serial.print(F("SWITCH:"));
        Serial.print(w, 1);
        Serial.print(F(",T:"));
        Serial.print(t, 1);
        Serial.print(F(",H:"));
        Serial.println(h, 1);
      } else {
        Serial.print(F("SWITCH:"));
        Serial.print(w, 1);
        Serial.println(F(",T:-99,H:-99"));
      }
      currentState = IDLE;
      Serial.println(F("[LOG] state=IDLE"));
      delay(600);
    }
  }

  // ── OLED 3초 후 자동 지우기 ──────────────
  if (oledReady && oledActive && millis() - oledClearAt > 3000) {
    oled.clearDisplay();
    oled.display();
    oledActive = false;
  }

  // ── 온습도 30초마다 전송 ─────────────────
  if (millis() - lastDhtSent > 30000) {
    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t) && !isnan(h)) {
      Serial.print(F("TEMP:"));
      Serial.print(t, 1);
      Serial.print(F(",HUM:"));
      Serial.println(h, 1);
    }
    lastDhtSent = millis();
  }
}

// ──────────────────────────────────────────
float readDistance() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long dur = pulseIn(ECHO_PIN, HIGH, 30000);
  if (dur == 0) return 0;
  return dur * 0.034f / 2.0f;
}

void sendCloseWeight() {
  delay(CLOSE_WEIGHT_SETTLE_MS);
  if (!scale.is_ready()) {
    Serial.println(F("[LOG] HX711 not ready, skip close weight"));
    return;
  }

  float w = scale.get_units(10);
  if (w < 0) w = 0;

  Serial.print(F("[LOG] close weight="));
  Serial.print(w, 1);
  Serial.println(F("g"));
  Serial.print(F("CLOSE_WEIGHT:"));
  Serial.println(w, 1);
}

void handlePiCmd(const char* cmd) {
  Serial.print(F("[RX] ")); Serial.println(cmd);
  if      (strcmp_P(cmd, PSTR("LED_Y:1")) == 0)            digitalWrite(LED_YELLOW, HIGH);
  else if (strcmp_P(cmd, PSTR("LED_Y:0")) == 0)            digitalWrite(LED_YELLOW, LOW);
  else if (strcmp_P(cmd, PSTR("LED_R:1")) == 0)            digitalWrite(LED_RED,    HIGH);
  else if (strcmp_P(cmd, PSTR("LED_R:0")) == 0)            digitalWrite(LED_RED,    LOW);
  else if (strcmp_P(cmd, PSTR("BUZZER")) == 0)             beep(300);
  else if (strcmp_P(cmd, PSTR("SCAN_FAIL")) == 0)          showOled(F("ScanFailed"));
  else if (strcmp_P(cmd, PSTR("STATE:WEIGHT_READY")) == 0) {
    currentState = WEIGHT_READY;
    Serial.println(F("[LOG] state=WEIGHT_READY"));
  }
  else if (strcmp_P(cmd, PSTR("STATE:IDLE")) == 0) {
    currentState = IDLE;
    Serial.println(F("[LOG] state=IDLE"));
  }
  else if (strcmp_P(cmd, PSTR("DOOR:OPEN")) == 0)           openDoor();
  else if (strcmp_P(cmd, PSTR("DOOR:CLOSE")) == 0)          closeDoor();
  else if (strncmp_P(cmd, PSTR("OLED:"), 5) == 0)          showOled(cmd + 5);
}

void trimCommand(char* cmd) {
  char* start = cmd;
  while (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n') {
    start++;
  }

  if (start != cmd) {
    char* dst = cmd;
    while ((*dst++ = *start++)) {}
  }

  char* end = cmd;
  while (*end) {
    end++;
  }

  while (end > cmd) {
    char c = *(end - 1);
    if (c != ' ' && c != '\t' && c != '\r' && c != '\n') {
      break;
    }
    *(--end) = '\0';
  }
}

void showOled(const __FlashStringHelper* msg) {
  if (!oledReady) return;
  oled.clearDisplay();
  oled.setTextSize(2);
  oled.setCursor(0, 20);
  oled.println(msg);
  oled.display();
  oledClearAt = millis();
  oledActive  = true;
}

void showOled(const char* msg) {
  if (!oledReady) return;
  oled.clearDisplay();
  oled.setTextSize(2);
  oled.setCursor(0, 20);
  oled.println(msg);
  oled.display();
  oledClearAt = millis();
  oledActive  = true;
}

void beep(int ms) {
  tone(BUZZER_PIN, 1000, ms);
}

void openDoor() {
  Serial.println(F("[LOG] servo opening door"));
  for (int pos = 0; pos <= 90; pos++) {
    doorServo.write(pos);
    delay(10);
  }
  Serial.println(F("[LOG] servo door open (90deg)"));
}

void closeDoor() {
  Serial.println(F("[LOG] servo closing door"));
  for (int pos = 90; pos >= 0; pos--) {
    doorServo.write(pos);
    delay(10);
  }
  Serial.println(F("[LOG] servo door closed (0deg)"));
}
