// Phase 1: camera bring-up. Captures the configured ROI on a timer,
// hashes it to detect a change, and logs to serial. No OCR, no network.

#include <Arduino.h>
#include <string.h>
#include "esp_camera.h"
#include "camera_pins.h"
#include "config.h"

static const framesize_t FRAME_SIZE = FRAMESIZE_VGA;
static const int FRAME_WIDTH = 640;
static const int FRAME_HEIGHT = 480;

static uint8_t *roiBuffer = nullptr;
static uint32_t lastRoiHash = 0;
static unsigned long lastCaptureMs = 0;

static uint32_t fnv1aHash(const uint8_t *data, size_t len) {
    uint32_t hash = 2166136261u;
    for (size_t i = 0; i < len; i++) {
        hash ^= data[i];
        hash *= 16777619u;
    }
    return hash;
}

static bool cropRoi(const camera_fb_t *fb, uint8_t *out) {
    if (ROI_X < 0 || ROI_Y < 0 || ROI_WIDTH <= 0 || ROI_HEIGHT <= 0 ||
        ROI_X + ROI_WIDTH > (int)fb->width || ROI_Y + ROI_HEIGHT > (int)fb->height) {
        return false;
    }
    const size_t bytesPerPixel = 2; // RGB565
    const size_t rowBytes = ROI_WIDTH * bytesPerPixel;
    const size_t srcStride = fb->width * bytesPerPixel;
    for (int row = 0; row < ROI_HEIGHT; row++) {
        const uint8_t *srcRow = fb->buf + (ROI_Y + row) * srcStride + ROI_X * bytesPerPixel;
        memcpy(out + row * rowBytes, srcRow, rowBytes);
    }
    return true;
}

static void halt(const char *message) {
    Serial.println(message);
    while (true) {
        delay(1000);
    }
}

static bool initCamera() {
    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_RGB565;
    config.frame_size = FRAME_SIZE;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("camera init failed: 0x%x\n", err);
        return false;
    }
    return true;
}

void setup() {
    Serial.begin(115200);
    delay(1000);

    if (ROI_X + ROI_WIDTH > FRAME_WIDTH || ROI_Y + ROI_HEIGHT > FRAME_HEIGHT) {
        halt("ROI in config.h does not fit within the frame, halting");
    }

    roiBuffer = (uint8_t *)ps_malloc((size_t)ROI_WIDTH * ROI_HEIGHT * 2);
    if (roiBuffer == nullptr) {
        halt("failed to allocate ROI buffer, halting");
    }

    if (!initCamera()) {
        halt("camera init failed, halting");
    }

    Serial.println("camera ready");
}

void loop() {
    unsigned long now = millis();
    if (now - lastCaptureMs < CAPTURE_INTERVAL_MS) {
        delay(100);
        return;
    }
    lastCaptureMs = now;

    camera_fb_t *fb = esp_camera_fb_get();
    if (fb == nullptr) {
        Serial.println("frame capture failed");
        return;
    }
    Serial.printf("captured frame: %dx%d, %d bytes\n", fb->width, fb->height, fb->len);

    if (!cropRoi(fb, roiBuffer)) {
        Serial.println("ROI crop failed, frame too small for configured ROI");
        esp_camera_fb_return(fb);
        return;
    }
    esp_camera_fb_return(fb);

    uint32_t roiHash = fnv1aHash(roiBuffer, (size_t)ROI_WIDTH * ROI_HEIGHT * 2);
    if (roiHash != lastRoiHash) {
        Serial.printf("ROI changed: hash 0x%08x\n", roiHash);
        lastRoiHash = roiHash;
    }
}
