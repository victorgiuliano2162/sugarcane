#include "image_processor.h"
#include "JPEGDEC.h"

static JPEGDEC jpeg;
static int8_t* out_tensor = nullptr;
static int original_w = 0;
static int original_h = 0;
const int TARGET_W = 160;
const int TARGET_H = 160;
const int CHANNELS = 3;

static int JPEGDraw(JPEGDRAW* pDraw) {
    if (!out_tensor) return 0;
    
    for (int y = 0; y < pDraw->iHeight; y++) {
        for (int x = 0; x < pDraw->iWidth; x++) {
            uint32_t src_x = pDraw->x + x;
            uint32_t src_y = pDraw->y + y;
            
            uint32_t dst_x = (src_x * TARGET_W) / original_w;
            uint32_t dst_y = (src_y * TARGET_H) / original_h;

            if (dst_x < TARGET_W && dst_y < TARGET_H) {
                uint16_t pixel = pDraw->pPixels[y * pDraw->iWidth + x];
                
                uint8_t r = (pixel & 0xF800) >> 8;
                uint8_t g = (pixel & 0x07E0) >> 3;
                uint8_t b = (pixel & 0x001F) << 3;

                int index = ((dst_y * TARGET_W) + dst_x) * CHANNELS;
                
                out_tensor[index + 0] = (int8_t)((int)r - 128);
                out_tensor[index + 1] = (int8_t)((int)g - 128);
                out_tensor[index + 2] = (int8_t)((int)b - 128);
            }
        }
    }
    return 1;
}

bool process_jpeg(uint8_t* jpeg_buffer, size_t jpeg_size, int8_t* target_tensor) {
    out_tensor = target_tensor;
    if (jpeg.openRAM(jpeg_buffer, jpeg_size, JPEGDraw)) {
        original_w = jpeg.getWidth();
        original_h = jpeg.getHeight();
        jpeg.setPixelType(RGB565_LITTLE_ENDIAN);
        jpeg.decode(0, 0, 0);
        jpeg.close();
        return true;
    }
    return false;
}