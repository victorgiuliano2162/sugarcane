#pragma once
#include <stdint.h>
#include <stdbool.h>

void wifi_init_auto();
inline void wifi_init_sta() { wifi_init_auto(); }
const char* wifi_get_mode_str();
int8_t wifi_get_rssi();
const char* wifi_get_ip_str();
