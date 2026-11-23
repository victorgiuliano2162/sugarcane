#include "wifi_setup.h"
#include <cstdio>
#include <cstring>
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "mdns.h"
#include "esp_sntp.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#ifndef CONFIG_SUGARCANE_WIFI_STA_SSID
#define CONFIG_SUGARCANE_WIFI_STA_SSID ""
#endif
#ifndef CONFIG_SUGARCANE_WIFI_STA_PASS
#define CONFIG_SUGARCANE_WIFI_STA_PASS ""
#endif
#ifndef CONFIG_SUGARCANE_WIFI_AP_SSID
#define CONFIG_SUGARCANE_WIFI_AP_SSID "Sugarcane-AI-AP"
#endif
#ifndef CONFIG_SUGARCANE_WIFI_AP_PASS
#define CONFIG_SUGARCANE_WIFI_AP_PASS ""
#endif

#define WIFI_AP_MAX_CONN 4
#define WIFI_NVS_NAMESPACE "wifi_cfg"

static char s_sta_ssid[33] = CONFIG_SUGARCANE_WIFI_STA_SSID;
static char s_sta_pass[65] = CONFIG_SUGARCANE_WIFI_STA_PASS;
static char s_ap_ssid[33]  = CONFIG_SUGARCANE_WIFI_AP_SSID;
static char s_ap_pass[65]  = CONFIG_SUGARCANE_WIFI_AP_PASS;

static const char* TAG = "WIFI";
static EventGroupHandle_t wifi_event_group;
const int WIFI_CONNECTED_BIT = BIT0;

static char s_current_mode[16] = "DISCONNECTED";
static char s_current_ip[32] = "0.0.0.0";
static int8_t s_current_rssi = 0;
static esp_netif_t* s_sta_netif = NULL;
static esp_netif_t* s_ap_netif = NULL;
static int s_sta_retry_count = 0;
static bool s_sta_was_connected = false;
static bool s_sntp_started = false;

static void start_softap();

static void init_sntp_once() {
    if (s_sntp_started) return;
    s_sntp_started = true;
    esp_sntp_setoperatingmode(ESP_SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_setservername(1, "a.st1.ntp.br");
    esp_sntp_init();
    ESP_LOGI(TAG, "SNTP inicializado para sincronizacao de horario.");
}

const char* wifi_get_mode_str() {
    return s_current_mode;
}

int8_t wifi_get_rssi() {
    if (strcmp(s_current_mode, "STA") == 0) {
        wifi_ap_record_t ap_info;
        if (esp_wifi_sta_get_ap_info(&ap_info) == ESP_OK) {
            s_current_rssi = ap_info.rssi;
        }
    } else {
        s_current_rssi = 0;
    }
    return s_current_rssi;
}

const char* wifi_get_ip_str() {
    return s_current_ip;
}

static void start_mdns() {
    esp_err_t err = mdns_init();
    if (err == ESP_OK) {
        mdns_hostname_set("sugarcane");
        mdns_instance_name_set("Sugarcane AI ESP32-S3 Edge");
        mdns_service_add("Sugarcane-Web", "_http", "_tcp", 80, NULL, 0);
        mdns_service_add("Sugarcane-WS", "_ws", "_tcp", 80, NULL, 0);
        ESP_LOGI(TAG, "mDNS iniciado: acesse http://sugarcane.local");
    } else {
        ESP_LOGW(TAG, "mDNS falhou: %s", esp_err_to_name(err));
    }
}

static void event_handler(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        s_sta_retry_count++;
        if (s_sta_was_connected && s_sta_retry_count >= 5) {
            ESP_LOGW(TAG, "STA desconectado apos %d tentativas. Acionando fallback SoftAP...", s_sta_retry_count);
            strcpy(s_current_mode, "DISCONNECTED");
            s_sta_was_connected = false;
            start_softap();
        } else {
            ESP_LOGW(TAG, "Tentando reconectar a rede STA (%d)...", s_sta_retry_count);
            esp_wifi_connect();
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
        snprintf(s_current_ip, sizeof(s_current_ip), IPSTR, IP2STR(&event->ip_info.ip));
        strcpy(s_current_mode, "STA");
        s_sta_retry_count = 0;
        s_sta_was_connected = true;
        ESP_LOGI(TAG, "Modo Station (STA) conectado! IP: %s", s_current_ip);
        init_sntp_once();
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void load_wifi_credentials_from_nvs() {
    nvs_handle_t nvs;
    if (nvs_open(WIFI_NVS_NAMESPACE, NVS_READONLY, &nvs) != ESP_OK) {
        return;
    }

    size_t len = sizeof(s_sta_ssid);
    nvs_get_str(nvs, "sta_ssid", s_sta_ssid, &len);

    len = sizeof(s_sta_pass);
    nvs_get_str(nvs, "sta_pass", s_sta_pass, &len);

    len = sizeof(s_ap_ssid);
    nvs_get_str(nvs, "ap_ssid", s_ap_ssid, &len);

    len = sizeof(s_ap_pass);
    nvs_get_str(nvs, "ap_pass", s_ap_pass, &len);

    nvs_close(nvs);
}

static void start_softap() {
    ESP_LOGW(TAG, "Iniciando modo SoftAP autonomo: SSID '%s'...", s_ap_ssid);

    esp_wifi_disconnect();
    esp_wifi_stop();

    if (!s_ap_netif) {
        s_ap_netif = esp_netif_create_default_wifi_ap();
    }

    wifi_config_t ap_config = {};
    strncpy((char*)ap_config.ap.ssid, s_ap_ssid, sizeof(ap_config.ap.ssid) - 1);
    ap_config.ap.ssid_len = strlen(s_ap_ssid);
    ap_config.ap.channel = 6;
    ap_config.ap.max_connection = WIFI_AP_MAX_CONN;

    if (strlen(s_ap_pass) >= 8) {
        strncpy((char*)ap_config.ap.password, s_ap_pass, sizeof(ap_config.ap.password) - 1);
        ap_config.ap.authmode = WIFI_AUTH_WPA2_PSK;
    } else {
        ap_config.ap.authmode = WIFI_AUTH_OPEN;
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &ap_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    // Desativa economia de energia para máxima vazão
    esp_wifi_set_ps(WIFI_PS_NONE);

    strcpy(s_current_mode, "SoftAP");
    strcpy(s_current_ip, "192.168.4.1");
    s_current_rssi = 0;

    printf("\n=======================================================\n");
    printf(" MODO SOFTAP ATIVADO!\n");
    printf(" Conecte seu celular/PC no Wi-Fi: %s\n", s_ap_ssid);
    printf(" Acesse o Dashboard em: http://%s ou http://sugarcane.local\n", s_current_ip);
    printf("=======================================================\n\n");
}

void wifi_init_auto() {
    load_wifi_credentials_from_nvs();

    wifi_event_group = xEventGroupCreate();
    esp_netif_init();
    esp_event_loop_create_default();
    s_sta_netif = esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);

    esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL, NULL);
    esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &event_handler, NULL, NULL);

    if (strlen(s_sta_ssid) == 0) {
        ESP_LOGW(TAG, "Nenhum SSID STA configurado (NVS ou Kconfig). Iniciando em SoftAP.");
        start_softap();
        start_mdns();
        return;
    }

    wifi_config_t sta_config = {};
    strncpy((char*)sta_config.sta.ssid, s_sta_ssid, sizeof(sta_config.sta.ssid) - 1);
    strncpy((char*)sta_config.sta.password, s_sta_pass, sizeof(sta_config.sta.password) - 1);
    sta_config.sta.threshold.authmode = (strlen(s_sta_pass) > 0) ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;

    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_config(WIFI_IF_STA, &sta_config);
    esp_wifi_start();

    // Desativa Modem Sleep para evitar latências no rádio
    esp_wifi_set_ps(WIFI_PS_NONE);

    ESP_LOGI(TAG, "Tentando conectar ao Wi-Fi '%s' por 5 segundos...", s_sta_ssid);

    // Aguarda até 5 segundos por conexão STA
    EventBits_t bits = xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT,
        pdFALSE,
        pdFALSE,
        pdMS_TO_TICKS(5000)
    );

    if (bits & WIFI_CONNECTED_BIT) {
        printf("\n=======================================================\n");
        printf(" MODO STATION (STA) CONECTADO COM SUCESSO!\n");
        printf(" Endereco IP: %s\n", s_current_ip);
        printf(" Acesse o Dashboard em: http://%s ou http://sugarcane.local\n", s_current_ip);
        printf("=======================================================\n\n");
    } else {
        // Fallback automático para SoftAP
        start_softap();
    }

    start_mdns();
}
