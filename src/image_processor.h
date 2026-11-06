#pragma once
#include <cstdint>
#include <cstddef>

/**
 * Função principal ativa na pipeline de execução do firmware.
 * Redireciona para a Opção A (RGB565 + Box Averaging / Interpolação por Área),
 * priorizando a máxima acurácia global (82,73%) e a detecção de lesões finas
 * nas classes críticas (ex: smut e Pokkah Boeng).
 */
bool process_jpeg(uint8_t* jpeg_buffer, size_t jpeg_size, int8_t* target_tensor);

/**
 * [ATIVA NA PIPELINE] Opção A (Modo 5): RGB565 + Box Averaging (Interpolação por Área)
 * - Integra todos os pixels de cada janela original (~30,7 pixels em 768x1024) usando
 *   acumuladores na Octal PSRAM antes de quantizar para o tensor 160x160x3 (int8).
 * - Eleva o PSNR global de 27,1 dB para 38,2 dB (+11,1 dB) e atinge 82,73% de acurácia.
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
 * [REGISTRO TÉCNICO] Opção C (Modo 7): RGB8888 Nativo (24-bit) + Box Averaging
 * - Padrão ouro físico de sinal (Bias DC = 0,00, RMSE = 0,00, PSNR = Infinito).
 * - Combina decodificação nativa de 24 bits com interpolação por área, ideal para
 *   paridade matemática caso a rede passe por fine-tuning com cv2.INTER_AREA / PIL.Image.BOX.
 */
bool process_jpeg_option_c_boxavg_rgb8888(uint8_t* jpeg_buffer, size_t jpeg_size, int8_t* target_tensor);
