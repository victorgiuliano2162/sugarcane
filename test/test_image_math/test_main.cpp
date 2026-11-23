#include <unity.h>
#include <stdint.h>

static int8_t quantize_box_channel(uint32_t sum, uint16_t count) {
    if (count == 0) return -128;
    uint16_t half_c = count >> 1;
    uint8_t val = (uint8_t)((sum + half_c) / count);
    return (int8_t)((int)val - 128);
}

void test_box_average_rounding_and_zero_point() {
    TEST_ASSERT_EQUAL_INT8(-128, quantize_box_channel(0, 0));
    TEST_ASSERT_EQUAL_INT8(-128, quantize_box_channel(0, 4));
    TEST_ASSERT_EQUAL_INT8(0, quantize_box_channel(128 * 4, 4));
    TEST_ASSERT_EQUAL_INT8(127, quantize_box_channel(255 * 9, 9));
    // (10 + 1) / 3 = 3 -> 3 - 128 = -125
    TEST_ASSERT_EQUAL_INT8(-125, quantize_box_channel(10, 3));
}

void setUp(void) {}
void tearDown(void) {}

extern "C" void app_main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_box_average_rounding_and_zero_point);
    UNITY_END();
}
