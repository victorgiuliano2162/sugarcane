#pragma once
#include <stdbool.h>
#include <stdint.h>

struct GpsState {
    bool fix;
    uint8_t satellites;
    double lat;
    double lon;
    float alt_m;
};

void gps_neo6m_init();
void gps_get_state(GpsState* out);
