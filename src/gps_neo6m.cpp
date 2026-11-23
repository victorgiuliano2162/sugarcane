#include "gps_neo6m.h"
#include <cstdlib>
#include <cstring>
#include <cmath>
#include "driver/uart.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"

static const char* TAG = "GPS_NEO6M";

#ifndef CONFIG_SUGARCANE_GPS_UART_RX_GPIO
#define CONFIG_SUGARCANE_GPS_UART_RX_GPIO 18
#endif

#ifndef CONFIG_SUGARCANE_GPS_UART_TX_GPIO
#define CONFIG_SUGARCANE_GPS_UART_TX_GPIO 17
#endif

static const uart_port_t GPS_UART_NUM = UART_NUM_2;
static const int GPS_UART_BAUD = 9600;
static const int GPS_BUF_SIZE = 512;

static GpsState s_gps_state = { false, 0, 0.0, 0.0, 0.0f };
static SemaphoreHandle_t s_gps_mutex = NULL;

// Converte coordenada NMEA (ddmm.mmmm ou dddmm.mmmm) para graus decimais
static double nmea_to_decimal(const char* val, const char* hemi) {
    if (!val || !*val || !hemi || !*hemi) return 0.0;
    double raw = strtod(val, nullptr);
    int degrees = (int)(raw / 100.0);
    double minutes = raw - (degrees * 100.0);
    double dec = (double)degrees + (minutes / 60.0);
    if (hemi[0] == 'S' || hemi[0] == 'W') {
        dec = -dec;
    }
    return dec;
}

static bool validate_nmea_checksum(const char* sentence) {
    if (!sentence || sentence[0] != '$') return false;
    const char* star = strchr(sentence, '*');
    if (!star || strlen(star) < 3) return false;

    uint8_t calc = 0;
    for (const char* p = sentence + 1; p < star; p++) {
        calc ^= (uint8_t)(*p);
    }
    uint8_t expected = (uint8_t)strtol(star + 1, nullptr, 16);
    return calc == expected;
}

static void parse_gga(char* line) {
    // Campos GGA: $GxGGA,time,lat,N/S,lon,E/W,fix_quality,num_sats,hdop,alt,M,...
    char* fields[15] = {nullptr};
    int idx = 0;
    char* p = line;
    fields[idx++] = p;
    while (*p && idx < 15) {
        if (*p == ',' || *p == '*') {
            *p = '\0';
            fields[idx++] = p + 1;
        }
        p++;
    }

    if (idx < 10) return;

    int fix_quality = fields[6] ? atoi(fields[6]) : 0;
    int sats = fields[7] ? atoi(fields[7]) : 0;
    bool has_fix = (fix_quality > 0) && fields[2] && *fields[2] && fields[4] && *fields[4];

    double lat = has_fix ? nmea_to_decimal(fields[2], fields[3]) : 0.0;
    double lon = has_fix ? nmea_to_decimal(fields[4], fields[5]) : 0.0;
    float alt = (has_fix && fields[9] && *fields[9]) ? strtof(fields[9], nullptr) : 0.0f;

    if (s_gps_mutex && xSemaphoreTake(s_gps_mutex, pdMS_TO_TICKS(50)) == pdTRUE) {
        s_gps_state.fix = has_fix;
        s_gps_state.satellites = (sats >= 0 && sats <= 255) ? (uint8_t)sats : 0;
        if (has_fix) {
            s_gps_state.lat = lat;
            s_gps_state.lon = lon;
            s_gps_state.alt_m = alt;
        }
        xSemaphoreGive(s_gps_mutex);
    }
}

static void gps_task(void* pvParameters) {
    uint8_t* rx_buf = (uint8_t*)malloc(GPS_BUF_SIZE);
    char line_buf[128];
    size_t line_pos = 0;

    if (!rx_buf) {
        ESP_LOGE(TAG, "Falha ao alocar buffer RX para UART GPS.");
        vTaskDelete(NULL);
        return;
    }

    while (true) {
        int len = uart_read_bytes(GPS_UART_NUM, rx_buf, GPS_BUF_SIZE - 1, pdMS_TO_TICKS(200));
        for (int i = 0; i < len; i++) {
            char c = (char)rx_buf[i];
            if (c == '\r') continue;
            if (c == '\n') {
                line_buf[line_pos] = '\0';
                if (line_pos > 10 && validate_nmea_checksum(line_buf)) {
                    if (strncmp(line_buf + 3, "GGA,", 4) == 0) {
                        parse_gga(line_buf);
                    }
                }
                line_pos = 0;
            } else if (line_pos < sizeof(line_buf) - 1) {
                line_buf[line_pos++] = c;
            } else {
                line_pos = 0;
            }
        }
    }
}

void gps_neo6m_init() {
    if (!s_gps_mutex) {
        s_gps_mutex = xSemaphoreCreateMutex();
    }

    uart_config_t uart_config = {};
    uart_config.baud_rate = GPS_UART_BAUD;
    uart_config.data_bits = UART_DATA_8_BITS;
    uart_config.parity = UART_PARITY_DISABLE;
    uart_config.stop_bits = UART_STOP_BITS_1;
    uart_config.flow_ctrl = UART_HW_FLOWCTRL_DISABLE;
    uart_config.source_clk = UART_SCLK_DEFAULT;

    esp_err_t err = uart_driver_install(GPS_UART_NUM, GPS_BUF_SIZE * 2, 0, 0, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Falha ao instalar driver UART GPS: %s", esp_err_to_name(err));
        return;
    }

    uart_param_config(GPS_UART_NUM, &uart_config);
    uart_set_pin(GPS_UART_NUM, CONFIG_SUGARCANE_GPS_UART_TX_GPIO, CONFIG_SUGARCANE_GPS_UART_RX_GPIO,
                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    xTaskCreatePinnedToCore(gps_task, "gps_task", 3072, NULL, 2, NULL, 0);
    ESP_LOGI(TAG, "Receptor GPS NEO-6M inicializado (UART%d, RX=%d, TX=%d, %d bps).",
             (int)GPS_UART_NUM, CONFIG_SUGARCANE_GPS_UART_RX_GPIO, CONFIG_SUGARCANE_GPS_UART_TX_GPIO, GPS_UART_BAUD);
}

void gps_get_state(GpsState* out) {
    if (!out) return;
    if (s_gps_mutex && xSemaphoreTake(s_gps_mutex, pdMS_TO_TICKS(50)) == pdTRUE) {
        *out = s_gps_state;
        xSemaphoreGive(s_gps_mutex);
    } else {
        *out = { false, 0, 0.0, 0.0, 0.0f };
    }
}
