#include <avr/io.h>
#include <util/delay.h>
#include <avr/interrupt.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "HX711.h"

// ── 핀 정의 (ATmega328P BCM 핀에 대응하는 AVR 포트 하드코딩용)
#define TRIG_PIN     7  // PD7
#define ECHO_PIN     8  // PB0
#define LED_RED      12 // PB4
#define LED_YELLOW   13 // PB5
#define SWITCH_PIN   2  // PD2
#define BUZZER_PIN   3  // PD3

#define DHT_PIN      4  // PD4

// ── OLED (I2C 레지스터 직접 제어용 설정)
#define OLED_ADDR     0x78 // 0x3C << 1 (AVR TWI 7비트 주소 정렬)

// ── 상태
typedef enum { IDLE, WEIGHT_READY } State;

// ── 무게센서 구조체 선언 (C 스타일)
HX711_t scale;

// ── 전역 변수
State         currentState    = IDLE;
bool          isDoorOpen      = false;
bool          oledReady       = true; // TWI 가동 시 기본 True
bool          oledActive      = false;
unsigned long oledClearAt     = 0;
unsigned long lastDhtSent     = 0;
unsigned long lastDoorChange  = 0;
const unsigned long DOOR_MIN_MS  = 1000;
unsigned long lastDistRead   = 0;
const unsigned char CMD_BUFFER_SIZE = 32;
const unsigned long CLOSE_WEIGHT_SETTLE_MS = 800;
const float DOOR_CLOSED_MAX_CM = 20.0f;
const float DOOR_OPEN_MIN_CM   = 30.0f;
const unsigned long DIST_INTERVAL = 200;

// 아두이노 내부의 타이머 카운터를 모사하기 위한 간이 소프트웨어 타이머 카운트
volatile unsigned long _millis_counter = 0;

// ── 프로토타입 선언
void  init_system(void);
float readDistance(void);
void  sendCloseWeight(void);
void  handlePiCmd(const char* cmd);
void  trimCommand(char* cmd);
void  beep(int ms);

// ── 순수 C 언어 전용 TWI(I2C) 및 OLED low-level 제어 함수
void TWI_init(void) {
    TWSR = 0x00; // Prescaler = 1
    TWBR = 0x48; // SCL 주소 클럭 설정 (100kHz)
}

void TWI_start(void) {
    TWCR = (1<<TWINT)|(1<<TWSTA)|(1<<TWEN);
    while (!(TWCR & (1<<TWINT)));
}

void TWI_stop(void) {
    TWCR = (1<<TWINT)|(1<<TWEN)|(1<<TWSTO);
}

void TWI_write(uint8_t data) {
    TWDR = data;
    TWCR = (1<<TWINT)|(1<<TWEN);
    while (!(TWCR & (1<<TWINT)));
}

void OLED_command(uint8_t cmd) {
    TWI_start();
    TWI_write(OLED_ADDR);
    TWI_write(0x00); // Command 모드 스트림
    TWI_write(cmd);
    TWI_stop();
}

void OLED_data(uint8_t data) {
    TWI_start();
    TWI_write(OLED_ADDR);
    TWI_write(0x40); // Data 모드 스트림
    TWI_write(data);
    TWI_stop();
}

void OLED_init(void) {
    _delay_ms(100);
    OLED_command(0xAE); // Display OFF
    OLED_command(0xD5); // Set Display Clock Divide Ratio
    OLED_command(0x80);
    OLED_command(0xA8); // Set Multiplex Ratio
    OLED_command(0x3F); // 64 MUX
    OLED_command(0xD3); // Set Display Offset
    OLED_command(0x00);
    OLED_command(0x40); // Set Display Start Line = 0
    OLED_command(0x8D); // Charge Pump Setting
    OLED_command(0x14); // Enable Charge Pump (critical — display stays blank without this)
    OLED_command(0x20); // Set Memory Addressing Mode
    OLED_command(0x10); // Page Addressing Mode
    OLED_command(0xA1); // Set Segment Re-map
    OLED_command(0xC8); // Set COM Output Scan Direction
    OLED_command(0xDA); // Set COM Pins Hardware Configuration
    OLED_command(0x12);
    OLED_command(0x81); // Set Contrast Control
    OLED_command(0xCF);
    OLED_command(0xD9); // Set Pre-charge Period
    OLED_command(0xF1);
    OLED_command(0xDB); // Set VCOMH Deselect Level
    OLED_command(0x40);
    OLED_command(0xA4); // Output follows RAM content
    OLED_command(0xA6); // Normal Display (not inverted)
    OLED_command(0x2E); // Deactivate Scroll
    OLED_command(0xAF); // Display ON
}

void OLED_clear(void) {
    for (uint8_t page = 0; page < 8; page++) {
        OLED_command(0xB0 + page);
        OLED_command(0x00);
        OLED_command(0x10);
        for (uint8_t i = 0; i < 128; i++) {
            OLED_data(0x00);
        }
    }
}

// ASCII 5x8 bitmap font (space=0x20 to tilde=0x7E)
static const uint8_t font5x8[][5] = {
    {0x00,0x00,0x00,0x00,0x00}, // 0x20 space
    {0x00,0x00,0x5F,0x00,0x00}, // !
    {0x00,0x07,0x00,0x07,0x00}, // "
    {0x14,0x7F,0x14,0x7F,0x14}, // #
    {0x24,0x2A,0x7F,0x2A,0x12}, // $
    {0x23,0x13,0x08,0x64,0x62}, // %
    {0x36,0x49,0x55,0x22,0x50}, // &
    {0x00,0x05,0x03,0x00,0x00}, // '
    {0x00,0x1C,0x22,0x41,0x00}, // (
    {0x00,0x41,0x22,0x1C,0x00}, // )
    {0x08,0x2A,0x1C,0x2A,0x08}, // *
    {0x08,0x08,0x3E,0x08,0x08}, // +
    {0x00,0x50,0x30,0x00,0x00}, // ,
    {0x08,0x08,0x08,0x08,0x08}, // -
    {0x00,0x60,0x60,0x00,0x00}, // .
    {0x20,0x10,0x08,0x04,0x02}, // /
    {0x3E,0x51,0x49,0x45,0x3E}, // 0
    {0x00,0x42,0x7F,0x40,0x00}, // 1
    {0x42,0x61,0x51,0x49,0x46}, // 2
    {0x21,0x41,0x45,0x4B,0x31}, // 3
    {0x18,0x14,0x12,0x7F,0x10}, // 4
    {0x27,0x45,0x45,0x45,0x39}, // 5
    {0x3C,0x4A,0x49,0x49,0x30}, // 6
    {0x01,0x71,0x09,0x05,0x03}, // 7
    {0x36,0x49,0x49,0x49,0x36}, // 8
    {0x06,0x49,0x49,0x29,0x1E}, // 9
    {0x00,0x36,0x36,0x00,0x00}, // :
    {0x00,0x56,0x36,0x00,0x00}, // ;
    {0x00,0x08,0x14,0x22,0x41}, // <
    {0x14,0x14,0x14,0x14,0x14}, // =
    {0x41,0x22,0x14,0x08,0x00}, // >
    {0x02,0x01,0x51,0x09,0x06}, // ?
    {0x32,0x49,0x79,0x41,0x3E}, // @
    {0x7E,0x11,0x11,0x11,0x7E}, // A
    {0x7F,0x49,0x49,0x49,0x36}, // B
    {0x3E,0x41,0x41,0x41,0x22}, // C
    {0x7F,0x41,0x41,0x22,0x1C}, // D
    {0x7F,0x49,0x49,0x49,0x41}, // E
    {0x7F,0x09,0x09,0x01,0x01}, // F
    {0x3E,0x41,0x41,0x51,0x32}, // G
    {0x7F,0x08,0x08,0x08,0x7F}, // H
    {0x00,0x41,0x7F,0x41,0x00}, // I
    {0x20,0x40,0x41,0x3F,0x01}, // J
    {0x7F,0x08,0x14,0x22,0x41}, // K
    {0x7F,0x40,0x40,0x40,0x40}, // L
    {0x7F,0x02,0x04,0x02,0x7F}, // M
    {0x7F,0x04,0x08,0x10,0x7F}, // N
    {0x3E,0x41,0x41,0x41,0x3E}, // O
    {0x7F,0x09,0x09,0x09,0x06}, // P
    {0x3E,0x41,0x51,0x21,0x5E}, // Q
    {0x7F,0x09,0x19,0x29,0x46}, // R
    {0x46,0x49,0x49,0x49,0x31}, // S
    {0x01,0x01,0x7F,0x01,0x01}, // T
    {0x3F,0x40,0x40,0x40,0x3F}, // U
    {0x1F,0x20,0x40,0x20,0x1F}, // V
    {0x7F,0x20,0x18,0x20,0x7F}, // W
    {0x63,0x14,0x08,0x14,0x63}, // X
    {0x03,0x04,0x78,0x04,0x03}, // Y
    {0x61,0x51,0x49,0x45,0x43}, // Z
    {0x00,0x00,0x7F,0x41,0x41}, // [
    {0x02,0x04,0x08,0x10,0x20}, /* \ */
    {0x41,0x41,0x7F,0x00,0x00}, // ]
    {0x04,0x02,0x01,0x02,0x04}, // ^
    {0x40,0x40,0x40,0x40,0x40}, // _
    {0x00,0x01,0x02,0x04,0x00}, // `
    {0x20,0x54,0x54,0x54,0x78}, // a
    {0x7F,0x48,0x44,0x44,0x38}, // b
    {0x38,0x44,0x44,0x44,0x20}, // c
    {0x38,0x44,0x44,0x48,0x7F}, // d
    {0x38,0x54,0x54,0x54,0x18}, // e
    {0x08,0x7E,0x09,0x01,0x02}, // f
    {0x08,0x14,0x54,0x54,0x3C}, // g
    {0x7F,0x08,0x04,0x04,0x78}, // h
    {0x00,0x44,0x7D,0x40,0x00}, // i
    {0x20,0x40,0x44,0x3D,0x00}, // j
    {0x00,0x7F,0x10,0x28,0x44}, // k
    {0x00,0x41,0x7F,0x40,0x00}, // l
    {0x7C,0x04,0x18,0x04,0x78}, // m
    {0x7C,0x08,0x04,0x04,0x78}, // n
    {0x38,0x44,0x44,0x44,0x38}, // o
    {0x7C,0x14,0x14,0x14,0x08}, // p
    {0x08,0x14,0x14,0x18,0x7C}, // q
    {0x7C,0x08,0x04,0x04,0x08}, // r
    {0x48,0x54,0x54,0x54,0x20}, // s
    {0x04,0x3F,0x44,0x40,0x20}, // t
    {0x3C,0x40,0x40,0x20,0x7C}, // u
    {0x1C,0x20,0x40,0x20,0x1C}, // v
    {0x3C,0x40,0x30,0x40,0x3C}, // w
    {0x44,0x28,0x10,0x28,0x44}, // x
    {0x0C,0x50,0x50,0x50,0x3C}, // y
    {0x44,0x64,0x54,0x4C,0x44}, // z
    {0x00,0x08,0x36,0x41,0x00}, // {
    {0x00,0x00,0x7F,0x00,0x00}, // |
    {0x00,0x41,0x36,0x08,0x00}, // }
    {0x08,0x04,0x08,0x10,0x08}, // ~
};

void OLED_set_cursor(uint8_t page, uint8_t col) {
    OLED_command(0xB0 + page);
    OLED_command(col & 0x0F);
    OLED_command(0x10 | (col >> 4));
}

void showOled(const char* msg) {
    OLED_clear();
    OLED_set_cursor(3, 0); // center vertically (page 3 of 8)

    for (int i = 0; msg[i] != '\0' && i < 21; i++) {
        uint8_t c = (uint8_t)msg[i];
        if (c < 0x20 || c > 0x7E) c = 0x20;
        const uint8_t *glyph = font5x8[c - 0x20];
        for (int j = 0; j < 5; j++) OLED_data(glyph[j]);
        OLED_data(0x00); // 1px spacing between chars
    }
    oledClearAt = _millis_counter;
    oledActive  = true;
}

// 온습도 DHT11 센서 순수 C 제어 함수
void DHT11_start(void) {
    DDRD |= (1 << DHT_PIN);   // Output
    PORTD &= ~(1 << DHT_PIN); // Low
    _delay_ms(18);
    PORTD |= (1 << DHT_PIN);  // High
    _delay_us(30);
    DDRD &= ~(1 << DHT_PIN);  // Input
}

bool DHT11_read_raw(uint8_t *data) {
    uint8_t bits[5] = {0,0,0,0,0};
    uint8_t i, j = 0;

    DHT11_start();

    // Response 대기
    _delay_us(40);
    if ((PIND & (1 << DHT_PIN))) return false;
    _delay_us(80);
    if (!(PIND & (1 << DHT_PIN))) return false;
    _delay_us(80);

    // 40비트 데이터 수신
    for (j = 0; j < 5; j++) {
        for (i = 0; i < 8; i++) {
            while (!(PIND & (1 << DHT_PIN))); // Low 구간 대기
            _delay_us(30);
            if (PIND & (1 << DHT_PIN)) {
                bits[j] |= (1 << (7 - i));
            }
            while ((PIND & (1 << DHT_PIN))); // High 구간 대기
        }
    }

    if ((bits[0] + bits[1] + bits[2] + bits[3]) == bits[4]) {
        data[0] = bits[0]; // 습도 정수부
        data[1] = bits[2]; // 온도 정수부
        return true;
    }
    return false;
}

// 타이머 인터럽트를 이용한 전역 시스템 millisecond 계산 매커니즘
ISR(TIMER0_OVF_vect) {
    _millis_counter++;
}

void init_system(void) {
    // UART 초기화 (9600 Baud)
    UBRR0H = 0x00;
    UBRR0L = 0x67; // 16MHz 기준 9600 셋팅
    UCSR0B = (1 << RXEN0) | (1 << TXEN0);
    UCSR0C = (3 << UCSZ00);

    // GPIO 방향 및 초기 풀업 설정
    DDRD |= (1 << TRIG_PIN) | (1 << BUZZER_PIN);
    DDRB |= (1 << (LED_RED - 8)) | (1 << (LED_YELLOW - 8)); // PB4, PB5
    DDRD &= ~(1 << SWITCH_PIN);
    PORTD |= (1 << SWITCH_PIN); // Switch Pull-up
    DDRB &= ~(1 << (ECHO_PIN - 8)); // PB0 Input

    // 타이머0 설정 (millis 카운터용)
    TCCR0B |= (1 << CS01) | (1 << CS00); // Prescaler 64
    TIMSK0 |= (1 << TOIE0);
    sei(); // 전역 인터럽트 허용

    TWI_init();
    OLED_init();
    OLED_clear();
    showOled("Ready");

    // 순수 C 기반 무게센서 초기화 호출
    HX711_init(&scale, 5, 6); // DT=5, SCK=6
    HX711_set_scale(&scale, 20.0f);
    HX711_tare(&scale, 10);
}

// UART C 표준 문자열 송수신 함수들
void UART_print(const char* str) {
    while (*str) {
        while (!(UCSR0A & (1 << UDRE0)));
        UDR0 = *str++;
    }
}

bool UART_available(void) {
    return (UCSR0A & (1 << RXC0));
}

char UART_read(void) {
    while (!(UCSR0A & (1 << RXC0)));
    return UDR0;
}

// ──────────────────────────────────────────
int main(void) {
    init_system();

    while (1) {
        // ── ② 초음파 문 열림 감지
        if (_millis_counter - lastDistRead > DIST_INTERVAL) {
            lastDistRead = _millis_counter;
            float dist = readDistance();
            bool nextDoorOpen = isDoorOpen;

            if (dist == 0) nextDoorOpen = true;
            else if (dist < DOOR_CLOSED_MAX_CM) nextDoorOpen = false;
            else if (dist > DOOR_OPEN_MIN_CM) nextDoorOpen = true;

            if (nextDoorOpen != isDoorOpen && _millis_counter - lastDoorChange > DOOR_MIN_MS) {
                bool wasDoorOpen = isDoorOpen;
                isDoorOpen = nextDoorOpen;
                lastDoorChange = _millis_counter;
                if (isDoorOpen) UART_print("DOOR:1\n");
                else UART_print("DOOR:0\n");

                if (isDoorOpen) PORTB |= (1 << (LED_YELLOW - 8));
                else PORTB &= ~(1 << (LED_YELLOW - 8));

                if (wasDoorOpen && !isDoorOpen) {
                    sendCloseWeight();
                }
            }
        }

        // ── ⑤ Pi 명령 수신
        if (UART_available()) {
            char cmd[CMD_BUFFER_SIZE];
            uint8_t idx = 0;
            while (idx < CMD_BUFFER_SIZE - 1) {
                char c = UART_read();
                if (c == '\n' || c == '\r') break;
                cmd[idx++] = c;
            }
            cmd[idx] = '\0';
            trimCommand(cmd);
            if (cmd[0] != '\0') {
                handlePiCmd(cmd);
            }
        }

        // ── ⑨ WEIGHT_READY 스위치 + 무게 + 온습도 처리
        if (currentState == WEIGHT_READY && isDoorOpen) {
            if (!(PIND & (1 << SWITCH_PIN))) { // Switch LOW 체크
                float w = HX711_get_units(&scale, 5);
                if (w < 0) w = 0;
                
                uint8_t dht_data[2];
                char out_buf[64];
                beep(150);

                if (DHT11_read_raw(dht_data)) {
                    sprintf(out_buf, "SWITCH:%.1f,T:%d.0,H:%d.0\n", w, dht_data[1], dht_data[0]);
                } else {
                    sprintf(out_buf, "SWITCH:%.1f,T:-99,H:-99\n", w);
                }
                UART_print(out_buf);
                currentState = IDLE;
                _delay_ms(600);
            }
        }

        // ── OLED 자동 소등
        if (oledActive && _millis_counter - oledClearAt > 3000) {
            OLED_clear();
            oledActive = false;
        }

        // ── 온습도 30초 주기 전송
        if (_millis_counter - lastDhtSent > 30000) {
            uint8_t dht_data[2];
            if (DHT11_read_raw(dht_data)) {
                char out_buf[48];
                sprintf(out_buf, "TEMP:%d.0,HUM:%d.0\n", dht_data[1], dht_data[0]);
                UART_print(out_buf);
            }
            lastDhtSent = _millis_counter;
        }
    }
    return 0;
}

// ──────────────────────────────────────────
float readDistance(void) {
    PORTD &= ~(1 << TRIG_PIN);
    _delay_us(2);
    PORTD |= (1 << TRIG_PIN);
    _delay_us(10);
    PORTD &= ~(1 << TRIG_PIN);

    uint32_t count = 0;
    uint32_t max_loops = 500000; 

    // Echo 핀 High 대기
    while (!(PINB & (1 << (ECHO_PIN - 8)))) {
        if (++count > max_loops) return 0;
    }
    
    count = 0;
    // Echo 핀 Low 될 때까지 폭 측정
    while ((PINB & (1 << (ECHO_PIN - 8)))) {
        if (++count > max_loops) return 0;
    }

    return (float)count * 0.034f / 2.0f; 
}

void sendCloseWeight(void) {
    _delay_ms(CLOSE_WEIGHT_SETTLE_MS);
    float w = HX711_get_units(&scale, 10);
    if (w < 0) w = 0;

    char out_buf[32];
    sprintf(out_buf, "CLOSE_WEIGHT:%.1f\n", w);
    UART_print(out_buf);
}

void handlePiCmd(const char* cmd) {
    if      (strcmp(cmd, "LED_Y:1") == 0) PORTB |= (1 << (LED_YELLOW - 8));
    else if (strcmp(cmd, "LED_Y:0") == 0) PORTB &= ~(1 << (LED_YELLOW - 8));
    else if (strcmp(cmd, "LED_R:1") == 0) PORTB |= (1 << (LED_RED - 8));
    else if (strcmp(cmd, "LED_R:0") == 0) PORTB &= ~(1 << (LED_RED - 8));
    else if (strcmp(cmd, "BUZZER") == 0)  beep(300);
    else if (strcmp(cmd, "SCAN_FAIL") == 0) showOled("ScanFailed");
    else if (strcmp(cmd, "STATE:WEIGHT_READY") == 0) currentState = WEIGHT_READY;
    else if (strcmp(cmd, "STATE:IDLE") == 0) currentState = IDLE;
    else if (strncmp(cmd, "OLED:", 5) == 0) showOled(cmd + 5);
}

void trimCommand(char* cmd) {
    char* start = cmd;
    while (*start == ' ' || *start == '\t' || *start == '\r' || *start == '\n') start++;
    if (start != cmd) {
        char* dst = cmd;
        while ((*dst++ = *start++));
    }
    char* end = cmd;
    while (*end) end++;
    while (end > cmd) {
        char c = *(end - 1);
        if (c != ' ' && c != '\t' && c != '\r' && c != '\n') break;
        *(--end) = '\0';
    }
}

void beep(int ms) {
    PORTD |= (1 << BUZZER_PIN);
    for(int i=0; i<ms; i++) _delay_ms(1);
    PORTD &= ~(1 << BUZZER_PIN);
}