#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <HX711.h>
#include <DHT.h>
#include <Servo.h>
#include <avr/pgmspace.h>

// ── 핀 정의
#define TRIG_PIN      7
#define ECHO_PIN      8
#define LED_RED       12
#define LED_YELLOW    13
#define HX711_DT      5
#define HX711_SCK     6
#define SWITCH_PIN    2
#define INPUT_SWITCH  10
#define OUTPUT_SWITCH 11
#define BUZZER_PIN    3
#define DHT_PIN       4
#define DHT_TYPE      DHT11
#define SERVO_PIN     9

// ── OLED
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_ADDR     0x3C

// ── 상태
enum State { IDLE, WEIGHT_READY };

// ── 객체
Adafruit_SSD1306 oled(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);
HX711  scale;
DHT    dht(DHT_PIN, DHT_TYPE);
Servo  doorServo;

// ── 전역 변수
State         currentState     = IDLE;
bool          isDoorOpen       = false;
bool          oledReady        = false;
bool          oledActive       = false;
unsigned long oledClearAt      = 0;
unsigned long lastDhtSent      = 0;
unsigned long lastDoorChange   = 0;
unsigned long lastDistRead     = 0;

const unsigned long DOOR_MIN_MS          = 1000;
const unsigned long CLOSE_WEIGHT_SETTLE  = 800;
const unsigned long DIST_INTERVAL        = 200;
const unsigned long DHT_INTERVAL         = 30000;
const float         DOOR_CLOSED_MAX_CM   = 5.0f;
const float         DOOR_OPEN_MIN_CM     = 10.0f;
const byte          CMD_BUF_SIZE         = 32;

// ── 프로토타입
void  setup();
void  loop();
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

  pinMode(TRIG_PIN,      OUTPUT);
  pinMode(ECHO_PIN,      INPUT);
  pinMode(LED_RED,       OUTPUT);
  pinMode(LED_YELLOW,    OUTPUT);
  pinMode(SWITCH_PIN,    INPUT_PULLUP);
  pinMode(INPUT_SWITCH,  INPUT_PULLUP);
  pinMode(OUTPUT_SWITCH, INPUT_PULLUP);
  pinMode(BUZZER_PIN,    OUTPUT);

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
  Serial.println(F("[LOG] Servo attached pos=0"));

  Serial.println(F("[LOG] setup done"));
}

// ──────────────────────────────────────────
void loop() {
  // TODO: 여기에 로직 작성
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
  delay(CLOSE_WEIGHT_SETTLE);
  if (!scale.is_ready()) {
    Serial.println(F("[LOG] HX711 not ready"));
    return;
  }
  float w = scale.get_units(10);
  if (w < 0) w = 0;
  Serial.print(F("[LOG] close weight=")); Serial.print(w, 1); Serial.println(F("g"));
  Serial.print(F("CLOSE_WEIGHT:")); Serial.println(w, 1);
}

void handlePiCmd(const char* cmd) {
  Serial.print(F("[RX] ")); Serial.println(cmd);
  if      (strcmp_P(cmd, PSTR("LED_R:1")) == 0)             digitalWrite(LED_RED,    HIGH);
  else if (strcmp_P(cmd, PSTR("LED_R:0")) == 0)             digitalWrite(LED_RED,    LOW);
  else if (strcmp_P(cmd, PSTR("LED_Y:1")) == 0)             digitalWrite(LED_YELLOW, HIGH);
  else if (strcmp_P(cmd, PSTR("LED_Y:0")) == 0)             digitalWrite(LED_YELLOW, LOW);
  else if (strcmp_P(cmd, PSTR("BUZZER")) == 0)              beep(300);
  else if (strcmp_P(cmd, PSTR("DOOR:OPEN")) == 0)           openDoor();
  else if (strcmp_P(cmd, PSTR("DOOR:CLOSE")) == 0)          closeDoor();
  else if (strcmp_P(cmd, PSTR("SCAN_FAIL")) == 0)           showOled(F("ScanFailed"));
  else if (strcmp_P(cmd, PSTR("STATE:WEIGHT_READY")) == 0) {
    currentState = WEIGHT_READY;
    Serial.println(F("[LOG] state=WEIGHT_READY"));
  }
  else if (strcmp_P(cmd, PSTR("STATE:IDLE")) == 0) {
    currentState = IDLE;
    Serial.println(F("[LOG] state=IDLE"));
  }
  else if (strncmp_P(cmd, PSTR("OLED:"), 5) == 0)           showOled(cmd + 5);
}

void trimCommand(char* cmd) {
  char* start = cmd;
  while (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n') start++;
  if (start != cmd) { char* d = cmd; while ((*d++ = *start++)) {} }
  char* end = cmd;
  while (*end) end++;
  while (end > cmd) {
    char c = *(end - 1);
    if (c != ' ' && c != '\t' && c != '\r' && c != '\n') break;
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
  Serial.println(F("[LOG] servo opening"));
  for (int pos = 0; pos <= 90; pos++) { doorServo.write(pos); delay(10); }
  Serial.println(F("[LOG] door open 90deg"));
}

void closeDoor() {
  Serial.println(F("[LOG] servo closing"));
  for (int pos = 90; pos >= 0; pos--) { doorServo.write(pos); delay(10); }
  Serial.println(F("[LOG] door closed 0deg"));
}
