#pragma once
#include <stdint.h>
#include <stddef.h>

struct InferenceRequest {
    uint8_t* image_buffer;
    size_t image_size;
    int ws_fd;
};

void web_server_start();
void web_server_send_ws_text(int fd, const char* text);
void web_server_broadcast_ws_text(const char* text);
