#pragma once
#include <cstdint>

bool classifier_init();
bool classifier_run(uint32_t decode_time_ms);
int8_t* classifier_get_input_ptr();
const char* classifier_get_json_results();

// ============================================================================
// [IMPLEMENTAÇÃO: OTIMIZAÇÃO SRAM INTERNA + FORK-JOIN DUAL-CORE ESP-NN (v08)]
// Ativa o worker Dual-Core nativo do esp-nn (esp_nn_dual_core_enable).
// IMPORTANTE: Deve ser chamado a partir da task/núcleo que executa a inferência
// (Core 1), para que o esp-nn fixe o worker auxiliar no núcleo oposto (Core 0).
// ============================================================================
void classifier_enable_dual_core();
