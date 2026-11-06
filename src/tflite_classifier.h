#pragma once
#include <cstdint>

bool classifier_init();
bool classifier_run(uint32_t decode_time_ms);
int8_t* classifier_get_input_ptr();
const char* classifier_get_json_results();