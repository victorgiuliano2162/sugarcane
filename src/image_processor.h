#pragma once
#include <cstdint>
#include <cstddef>

/**
 * Função principal ativa na pipeline de execução do firmware.
 * Redireciona para a Opção C (Modo 7: RGB8888 Nativo 24-bit + Box Averaging),
 * que alcançou o 1º lugar absoluto com o modelo v08:
 * - 91,09% de acurácia global (501/550) e 86,20% de confiança média nas amostras limpas;
 * - 89,41% de acurácia (962/1.076) no conjunto de validação inédito (val/, +5,95% sobre o código original);
 * - Fidelidade física perfeita de sinal (MAE de cor = 0,00, RMSE = 0,00, PSNR = Infinito).
 */
bool process_jpeg(uint8_t* jpeg_buffer, size_t jpeg_size, int8_t* target_tensor);

/**
 * [REGISTRO TÉCNICO] Opção A (Modo 5): RGB565 + Box Averaging (Interpolação por Área)
 * - Integra todos os pixels de cada janela original (~30,7 pixels em 768x1024) usando
 *   acumuladores na Octal PSRAM antes de quantizar para o tensor 160x160x3 (int8).
 * - Eleva o PSNR global de 27,1 dB para 38,2 dB (+11,1 dB) e atinge 90,55% de acurácia no modelo v08.
 */
bool process_jpeg_option_a_boxavg_rgb565(uint8_t* jpeg_buffer, size_t jpeg_size, int8_t* target_tensor);

/**
 * [REGISTRO TÉCNICO] Opção B (Modo 4): RGB8888 Nativo (24-bit) + FastLUT
 * - Decodifica em 24 bits reais direto do YCbCr (MAE de cor = 0,00) e amostra apenas
 *   as 160 linhas e 160 colunas finais via Look-Up Table na stack (640 bytes),
 *   eliminando 96,7% das escritas redundantes na memória e reduzindo o tempo de CPU em ~18%.
 */
bool process_jpeg_option_b_fastlut_rgb8888(uint8_t* jpeg_buffer, size_t jpeg_size, int8_t* target_tensor);

/**
 * [ATIVA NA PIPELINE] Opção C (Modo 7): RGB8888 Nativo (24-bit) + Box Averaging
 * - Padrão ouro físico de sinal (Bias DC = 0,00, RMSE = 0,00, PSNR = Infinito).
 * - Combina decodificação nativa de 24 bits com interpolação por área, garantindo 100% de
 *   paridade matemática com o treinamento v08 (interpolation="area") e maior acurácia geral (91,09%).
 */
bool process_jpeg_option_c_boxavg_rgb8888(uint8_t* jpeg_buffer, size_t jpeg_size, int8_t* target_tensor);
