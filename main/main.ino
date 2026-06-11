#include <avr/io.h>
#include <util/delay.h>
#include <avr/interrupt.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "HX711.h"

// ── 핀 정의
#define TRIG_PIN      7  // PD7
#define ECHO_PIN      8  // PB0
#define LED_RED       11 // PB3 (빨간 LED)
#define LED_GREEN     12 // PB4 (초록 LED)
#define LED_YELLOW    13 // PB5 (노란 LED)
#define BTN_CONFIRM   2  // PD2 (확인 버튼, 기존 SWITCH_PIN)
#define BTN_INBOUND   9  // PB1 (입고 버튼)
#define BTN_OUTBOUND  10 // PB2 (출고 버튼)
#define BUZZER_PIN    3  // PD3
#define DHT_PIN       4  // PD4

// ── OLED (I2C 레지스터 직접 제어용 설정)
#define OLED_ADDR     0x78 // 0x3C << 1 (AVR TWI 7비트 주소 정렬)

// ── 상태 머신 정의
typedef enum {
    S_IDLE,                 // 대기 상태
    S_WAIT_INPUT,           // 입고 요청 전송 후 라즈베리파이의 INPUT 대기
    S_1,                    // 카메라 가동 및 날짜 스캔 대기 (초록 LED ON)
    S_2,                    // 날짜 확인 후 무게 변동 측정 대기 (OLED에 카운트 및 무게 변화 실시간 표기)
    S_3,                    // 무게 측정 완료 및 확인 대기 상태
    S_WAIT_COUNT,           // 확인 버튼 전송 후 라즈베리파이 수량 피드백 대기
    S_4,                    // 최종 수량 표시 상태 (입고 버튼 누르면 S_7 진입)
    S_5,                    // FIFO 불일치 시 어플 접속 알림 대기 상태
    S_6,                    // 어플 접속 완료, DB 수정 대기 (OLED에 n개 삭제 안내)
    S_7,                    // 입고 완료 후 평균 무게 갱신 대기 상태 (Pi 응답 후 S_IDLE 복귀)
    S_OUTBOUND_WAIT_INPUT,  // 출고 초기 패킷 송신 후 대기 상태
    S_OUTBOUND_1,           // 출고 물건 제거(REMOVE ITEM) 대기 상태
    S_OUTBOUND_WAIT_RESULT  // 출고 최종 무게 송신 후 분석 결과 대기 상태
} State;

// ── 무게센서 객체 (Arduino HX711 라이브러리 C++ API)
HX711 scale;

// ── 전역 변수
State         currentState    = S_IDLE;
int           confirm_n       = 0;   // INBOUND CONFIRM 시 삭제 필요 개수
bool          oledReady       = true; // TWI 가동 시 기본 True
bool          oledActive      = false;
unsigned long oledClearAt     = 0;
unsigned long lastDhtSent     = 0;
const unsigned char CMD_BUFFER_SIZE = 32;

int           current_count   = 0;
float         base_weight     = 0.0f;
float         measured_weight = 0.0f;
bool          isFifoStatus    = true;
int           display_position = 0;

// 아두이노 내부의 타이머 카운터를 모사하기 위한 간이 소프트웨어 타이머 카운트
volatile unsigned long _millis_counter = 0;

// ── 프로토타입 선언
void  init_system(void);
float readDistance(void);
void  handlePiCmd(const char* cmd);
void  trimCommand(char* cmd);
void  beep(int ms);
void  showOledLayout(const char* status_msg, const char* weight_msg, int count);
void  showOled(const char* msg);

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
    OLED_command(0x14); // Enable Charge Pump
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

// OLED 듀얼 레이아웃 제어 함수
// - status_msg: OLED 중간 상단(Page 2)에 출력할 상태 문자열
// - weight_msg: OLED 중간 하단(Page 4)에 출력할 무게 문자열 (NULL 또는 빈 문자열인 경우 status_msg가 Page 3 중앙에 세로 배치)
// - count: 우측 상단(Page 0)에 괄호 [count] 형태로 작게 띄울 수량 값
void showOledLayout(const char* status_msg, const char* weight_msg, int count) {
    OLED_clear();

    // 1. 우측 상단 수량 카운팅 출력 (S_2, S_3, S_4, S_5 단계에서만 상시 표시)
    if (currentState == S_2 || currentState == S_3 || currentState == S_4 || currentState == S_5) {
        char count_buf[16];
        sprintf(count_buf, "[%d]", count);
        OLED_set_cursor(0, 100); // 우측 상단 배치
        for (int i = 0; count_buf[i] != '\0'; i++) {
            uint8_t c = (uint8_t)count_buf[i];
            if (c < 0x20 || c > 0x7E) c = 0x20;
            const uint8_t *glyph = font5x8[c - 0x20];
            for (int j = 0; j < 5; j++) OLED_data(glyph[j]);
            OLED_data(0x00);
        }
    }

    // 2. 메인 상태/기능 텍스트 출력
    if (status_msg && status_msg[0] != '\0') {
        // 하단 무게 텍스트가 없으면 단일 텍스트이므로 Page 3 (세로 중간 정중앙)에 배치
        if (!weight_msg || weight_msg[0] == '\0') {
            OLED_set_cursor(3, 0);
        } else {
            OLED_set_cursor(2, 0); // 상단 배치
        }
        for (int i = 0; status_msg[i] != '\0' && i < 21; i++) {
            uint8_t c = (uint8_t)status_msg[i];
            if (c < 0x20 || c > 0x7E) c = 0x20;
            const uint8_t *glyph = font5x8[c - 0x20];
            for (int j = 0; j < 5; j++) OLED_data(glyph[j]);
            OLED_data(0x00);
        }
    }

    // 3. 하단 무게 텍스트 출력 (Page 4 배치)
    if (weight_msg && weight_msg[0] != '\0') {
        OLED_set_cursor(4, 0);
        for (int i = 0; weight_msg[i] != '\0' && i < 21; i++) {
            uint8_t c = (uint8_t)weight_msg[i];
            if (c < 0x20 || c > 0x7E) c = 0x20;
            const uint8_t *glyph = font5x8[c - 0x20];
            for (int j = 0; j < 5; j++) OLED_data(glyph[j]);
            OLED_data(0x00);
        }
    }

    oledClearAt = _millis_counter;
    oledActive  = true;
}

// 기존 showOled 호환용 래퍼 함수
void showOled(const char* msg) {
    showOledLayout(msg, "", 0);
}

// 온습도 DHT22 센서 순수 C 제어 함수
void DHT22_start(void) {
    DDRD |= (1 << DHT_PIN);   // Output
    PORTD &= ~(1 << DHT_PIN); // Low
    _delay_ms(2);             // DHT22는 기동 신호로 최소 1ms 필요
    PORTD |= (1 << DHT_PIN);  // High
    _delay_us(30);
    DDRD &= ~(1 << DHT_PIN);  // Input
    PORTD |= (1 << DHT_PIN);  // Pull-up
}

bool DHT22_read(float *temperature, float *humidity) {
    uint8_t bits[5] = {0,0,0,0,0};
    uint8_t i, j = 0;

    DHT22_start();

    // Response 대기
    uint16_t timeout = 0;
    while (PIND & (1 << DHT_PIN)) {
        if (++timeout > 10000) return false;
    }
    timeout = 0;
    while (!(PIND & (1 << DHT_PIN))) {
        if (++timeout > 10000) return false;
    }
    timeout = 0;
    while (PIND & (1 << DHT_PIN)) {
        if (++timeout > 10000) return false;
    }

    // 40비트 데이터 수신
    for (j = 0; j < 5; j++) {
        for (i = 0; i < 8; i++) {
            timeout = 0;
            while (!(PIND & (1 << DHT_PIN))) {
                if (++timeout > 10000) return false;
            }
            _delay_us(30);
            if (PIND & (1 << DHT_PIN)) {
                bits[j] |= (1 << (7 - i));
            }
            timeout = 0;
            while (PIND & (1 << DHT_PIN)) {
                if (++timeout > 10000) return false;
            }
        }
    }

    // 체크섬 검증 및 변환
    if (((bits[0] + bits[1] + bits[2] + bits[3]) & 0xFF) == bits[4]) {
        int16_t raw_humidity = (bits[0] << 8) | bits[1];
        int16_t raw_temperature = ((bits[2] & 0x7F) << 8) | bits[3];
        if (bits[2] & 0x80) {
            raw_temperature = -raw_temperature;
        }
        *humidity = (float)raw_humidity / 10.0f;
        *temperature = (float)raw_temperature / 10.0f;
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
    // 출력: TRIG_PIN(PD7), BUZZER_PIN(PD3)
    DDRD |= (1 << TRIG_PIN) | (1 << BUZZER_PIN);
    // 출력: LED_RED(PB3), LED_GREEN(PB4), LED_YELLOW(PB5)
    DDRB |= (1 << (LED_RED - 8)) | (1 << (LED_GREEN - 8)) | (1 << (LED_YELLOW - 8));
    
    // 입력 풀업: BTN_CONFIRM(PD2)
    DDRD &= ~(1 << BTN_CONFIRM);
    PORTD |= (1 << BTN_CONFIRM);

    // 입력: ECHO_PIN(PB0)
    DDRB &= ~(1 << (ECHO_PIN - 8));

    // 입력 풀업: BTN_INBOUND(PB1, 핀 9), BTN_OUTBOUND(PB2, 핀 10)
    DDRB &= ~((1 << (BTN_INBOUND - 8)) | (1 << (BTN_OUTBOUND - 8)));
    PORTB |= (1 << (BTN_INBOUND - 8)) | (1 << (BTN_OUTBOUND - 8));

    // 타이머0 설정 (millis 카운터용)
    TCCR0B |= (1 << CS01) | (1 << CS00); // Prescaler 64
    TIMSK0 |= (1 << TOIE0);
    sei(); // 전역 인터럽트 허용

    TWI_init();
    OLED_init();
    OLED_clear();
    showOledLayout("Ready", "", 0);

    // 무게센서 초기화
    scale.begin(5, 6); // DT=5, SCK=6
    scale.set_scale(3379.0f);
    scale.tare();
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
    
    unsigned long lastWeightUpdate = 0;

    while (1) {
        // ── ① Pi 명령 수신 및 파싱
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

        // ── ③ 입고 버튼 (BTN_INBOUND: 핀 9, PB1) 처리
        if (!(PINB & (1 << (BTN_INBOUND - 8)))) {
            _delay_ms(20);
            if (!(PINB & (1 << (BTN_INBOUND - 8)))) {
                beep(100);
                while (!(PINB & (1 << (BTN_INBOUND - 8)))); // 떼어질 때까지 대기
                
                if (currentState == S_IDLE) {
                    currentState = S_WAIT_INPUT;
                    UART_print("INBOUND_REQ\n");
                } else if (currentState == S_4) {
                    PORTB &= ~(1 << (LED_RED - 8)); // 입고 완료 시 RED LED 해제
                    PORTB &= ~(1 << (LED_GREEN - 8));
                    currentState = S_7;
                    showOledLayout("Updating...", "", 0);
                    UART_print("INBOUND_END\n");
                } else {
                    // 진행 상태(S_WAIT_INPUT, S_1, S_2, S_3, S_5)에서 누르면 강제 취소
                    currentState = S_IDLE;
                    PORTB &= ~(1 << (LED_GREEN - 8));
                    showOledLayout("Cancelled", "", 0);
                    UART_print("INBOUND_CANCEL\n");
                }
            }
        }

        // ── ④ 출고 버튼 (BTN_OUTBOUND: 핀 10, PB2) 처리
        if (!(PINB & (1 << (BTN_OUTBOUND - 8)))) {
            _delay_ms(20);
            if (!(PINB & (1 << (BTN_OUTBOUND - 8)))) {
                beep(100);
                while (!(PINB & (1 << (BTN_OUTBOUND - 8)))); // 떼어질 때까지 대기
                
                if (currentState == S_IDLE) {
                    currentState = S_OUTBOUND_WAIT_INPUT;
                    float w_init = scale.get_units(10);
                    if (w_init < 0) w_init = 0;
                    float d_init = readDistance();
                    
                    char out_buf[48];
                    sprintf(out_buf, "OUTBOUND_REQ:W:%.1f,D:%.1f\n", w_init, d_init);
                    UART_print(out_buf);
                } else if (currentState == S_OUTBOUND_1) {
                    currentState = S_OUTBOUND_WAIT_RESULT;
                    float w_final = scale.get_units(10);
                    if (w_final < 0) w_final = 0;
                    float d_final = readDistance();
                    
                    char out_buf[48];
                    sprintf(out_buf, "OUTBOUND_FINAL:W:%.1f,D:%.1f\n", w_final, d_final);
                    UART_print(out_buf);
                }
            }
        }

        // ── ⑤ 확인 버튼 (BTN_CONFIRM: 핀 2, PD2) 처리
        if (!(PIND & (1 << BTN_CONFIRM))) {
            _delay_ms(20);
            if (!(PIND & (1 << BTN_CONFIRM))) {
                beep(100);
                while (!(PIND & (1 << BTN_CONFIRM))); // 떼어질 때까지 대기
                
                if (currentState == S_3) {
                    currentState = S_WAIT_COUNT;
                    char out_buf[32];
                    sprintf(out_buf, "CONFIRM_WEIGHT:%.1f\n", measured_weight);
                    UART_print(out_buf);
                }
            }
        }

        // ── ⑥ 무게 실시간 계측 및 안정화 (S_2 상태)
        if (currentState == S_2) {
            if (_millis_counter - lastWeightUpdate > 250) { // 초당 4회 리프레시
                lastWeightUpdate = _millis_counter;
                float current_weight = HX711_get_units(&scale, 3);
                if (current_weight < 0) current_weight = 0;
                
                float diff = fabs(current_weight - base_weight);
                if (diff < 0) diff = 0;

                const char* status = isFifoStatus ? "FIFO" : "CONFIRM";
                char weight_buf[32];
                sprintf(weight_buf, "Weight: %.1fg", diff);
                showOledLayout(status, weight_buf, current_count);

                // 무게 안정화 판별 (비차단식 구조)
                static float last_stable_weight = -999.0f;
                static unsigned long stable_start_time = 0;

                if (diff > 5.0f) { // 5g 이상의 변동이 생겼을 때
                    if (fabs(diff - last_stable_weight) < 2.0f) { // 무게 차가 2g 이내면
                        if (stable_start_time == 0) {
                            stable_start_time = _millis_counter;
                        } else if (_millis_counter - stable_start_time > 1000) { // 1초간 유지되면
                            measured_weight = diff;
                            currentState = S_3;
                            
                            sprintf(weight_buf, "Weight: %.1fg", measured_weight);
                            showOledLayout(status, weight_buf, current_count);
                            beep(150);
                            
                            stable_start_time = 0;
                            last_stable_weight = -999.0f;
                        }
                    } else {
                        last_stable_weight = diff;
                        stable_start_time = 0;
                    }
                } else {
                    stable_start_time = 0;
                    last_stable_weight = -999.0f;
                }
            }
        }

        // ── ⑦ S_4에서 추가 입고 자동 감지 (입고버튼 없이 다음 물건 자동 루프)
        if (currentState == S_4) {
            if (_millis_counter - lastWeightUpdate > 250) {
                lastWeightUpdate = _millis_counter;
                float current_weight = HX711_get_units(&scale, 3);
                if (current_weight < 0) current_weight = 0;

                // 이미 올려진 누적 무게 대비 10g 이상 증가하면 새 물건으로 판단
                if (current_weight - (base_weight + measured_weight) > 10.0f) {
                    base_weight += measured_weight;
                    measured_weight = 0;
                    currentState = S_2;
                    const char* status = isFifoStatus ? "FIFO" : "CONFIRM";
                    showOledLayout(status, "Weight: 0.0g", current_count);
                }
            }
        }

        // ── ⑧ OLED 자동 소등 (S_IDLE 상태에서만 3초 후 자동 소등)
        if (currentState == S_IDLE && oledActive && _millis_counter - oledClearAt > 3000) {
            OLED_clear();
            oledActive = false;
        }

        // ── ⑨ 온습도 30초 주기 전송 (S_IDLE 상태에서만 전송)
        if (currentState == S_IDLE && _millis_counter - lastDhtSent > 30000) {
            float temp, hum;
            if (DHT22_read(&temp, &hum)) {
                char out_buf[48];
                sprintf(out_buf, "ENV:T:%.1f,H:%.1f\n", temp, hum);
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

void handlePiCmd(const char* cmd) {
    if (strcmp(cmd, "LED_Y:1") == 0) {
        PORTB |= (1 << (LED_YELLOW - 8));
    }
    else if (strcmp(cmd, "LED_Y:0") == 0) {
        PORTB &= ~(1 << (LED_YELLOW - 8));
    }
    else if (strcmp(cmd, "LED_R:0") == 0) {
        PORTB &= ~(1 << (LED_RED - 8));
    }
    else if (strcmp(cmd, "LED_R:1") == 0) {
        PORTB |= (1 << (LED_RED - 8));
    }
    else if (strcmp(cmd, "INPUT_OK") == 0) {
        if (currentState == S_WAIT_INPUT) {
            currentState = S_1;
            PORTB |= (1 << (LED_GREEN - 8)); // Green LED ON
            showOledLayout("INPUT", "", 0);
        }
    }
    else if (strncmp(cmd, "START_COUNT:", 12) == 0) {
        current_count = atoi(cmd + 12);
    }
    else if (strcmp(cmd, "PROGRESS:0") == 0) {
        currentState = S_IDLE;
        PORTB &= ~(1 << (LED_GREEN - 8)); // Green LED OFF
        showOledLayout("Scan Failed", "", 0);
        beep(150);
        _delay_ms(100);
        beep(150);
    }
    else if (strncmp(cmd, "PROGRESS:1,FIFO:", 16) == 0) {
        if (currentState == S_1) {
            int is_fifo = cmd[16] - '0';
            PORTB &= ~(1 << (LED_GREEN - 8)); // Green LED OFF
            isFifoStatus = is_fifo;
            
            if (is_fifo) {
                // FIFO 위치 파싱 (예: PROGRESS:1,FIFO:1,POS:2)
                display_position = 0;
                char* pos_ptr = strstr(cmd, ",POS:");
                if (pos_ptr) {
                    display_position = atoi(pos_ptr + 5);
                }
                HX711_tare(&scale, 5);
                base_weight = 0;
                measured_weight = 0;
                currentState = S_2;
                char status_buf[32];
                sprintf(status_buf, "FIFO (Pos: %d)", display_position);
                showOledLayout(status_buf, "Weight: 0.0g", current_count);
            } else {
                // CONFIRM 상태인 경우 S_5(어플 접속 대기)로 이동
                char* n_ptr = strstr(cmd, ",N:");
                confirm_n = n_ptr ? atoi(n_ptr + 3) : 0;
                currentState = S_5;
                showOledLayout("CONNECT APP", "CONFIRM", current_count);
            }
        }
    }
    else if (strcmp(cmd, "APP_CONNECTED") == 0) {
        if (currentState == S_5) {
            currentState = S_6;
            char weight_buf[22];
            sprintf(weight_buf, "DEL: %d item(s)", confirm_n);
            showOledLayout("CONFIRM", weight_buf, current_count);
            beep(100);
        }
    }
    else if (strncmp(cmd, "INBOUND_DB_DONE:", 16) == 0) {
        if (currentState == S_6) {
            display_position = atoi(cmd + 16);
            isFifoStatus = true;
            HX711_tare(&scale, 5);
            base_weight = 0;
            measured_weight = 0;
            currentState = S_2;
            char status_buf[32];
            sprintf(status_buf, "FIFO (Pos: %d)", display_position);
            showOledLayout(status_buf, "Weight: 0.0g", current_count);
            beep(100);
        }
    }
    else if (strcmp(cmd, "INBOUND_COMPLETE") == 0) {
        if (currentState == S_7) {
            currentState = S_IDLE;
            showOledLayout("Inbound Done", "", 0);
            beep(100);
        }
    }
    else if (strncmp(cmd, "COUNT:", 6) == 0) {
        if (currentState == S_WAIT_COUNT) {
            current_count = atoi(cmd + 6);
            currentState = S_4;
            char weight_buf[32];
            sprintf(weight_buf, "Weight: %.1fg", measured_weight);
            showOledLayout("Success", weight_buf, current_count);
            beep(150);
        }
    }
    else if (strcmp(cmd, "REMOVE_ITEM") == 0) {
        if (currentState == S_OUTBOUND_WAIT_INPUT) {
            currentState = S_OUTBOUND_1;
            showOledLayout("REMOVE ITEM", "", 0);
        }
    }
    else if (strcmp(cmd, "OUTBOUND_FIFO_OK") == 0) {
        if (currentState == S_OUTBOUND_WAIT_RESULT) {
            PORTB &= ~(1 << (LED_RED - 8)); // RED LED OFF
            currentState = S_IDLE;
            showOledLayout("Outbound Done", "", 0);
            beep(150);
        }
    }
    else if (strncmp(cmd, "OUTBOUND_CONFIRM_ERR:", 21) == 0) {
        if (currentState == S_OUTBOUND_WAIT_RESULT) {
            int del_count = atoi(cmd + 21);
            PORTB |= (1 << (LED_RED - 8)); // RED LED ON
            currentState = S_IDLE;
            char weight_buf[22];
            sprintf(weight_buf, "DEL: %d item(s)", del_count);
            showOledLayout("CONFIRM", weight_buf, 0);
            beep(150);
            _delay_ms(100);
            beep(150);
        }
    }
    else if (strcmp(cmd, "BUZZER") == 0) {
        beep(300);
    }
    else if (strncmp(cmd, "OLED:", 5) == 0) {
        showOledLayout(cmd + 5, "", 0);
    }
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