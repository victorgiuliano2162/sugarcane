#pragma once
#include <cstdint>
#include <cstddef>

struct InferenceRequest {
    uint8_t* image_buffer;
    size_t image_size;
    int ws_fd;
};

void web_server_start();
void web_server_send_ws_text(int fd, const char* text);