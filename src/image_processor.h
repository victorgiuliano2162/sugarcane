#pragma once
#include <cstdint>
#include <cstddef>

bool process_jpeg(uint8_t* jpeg_buffer, size_t jpeg_size, int8_t* target_tensor);