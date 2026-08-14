// Captures the configured ROI on a timer, hashes it to detect a change,
// and on change, uploads it as JPEG to the backend's /frame endpoint
// and, if a model is embedded, also runs on-device OCR and POSTs the
// result to /result. The JPEG upload always runs regardless of whether
// on-device OCR is available; see initOndeviceOcr()'s doc comment for
// what makes it unavailable.

#include <Arduino.h>
#include <WiFi.h>
#include <string.h>
#include "esp_camera.h"
#include "img_converters.h"
#include "camera_pins.h"
#include "config.h"
#include "ondevice_ocr.h"
#include "uploader.h"

static const uint8_t JPEG_QUALITY = 80;
static const unsigned long WIFI_CONNECT_TIMEOUT_MS = 20000;
static const unsigned long WIFI_RECONNECT_TIMEOUT_MS = 10000;

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
    // The frame descriptor is trusted for the memcpy below, so confirm it
    // actually describes its own buffer first. A short or truncated DMA
    // transfer would otherwise read past the end of fb->buf.
    if (fb->format != PIXFORMAT_RGB565 ||
        fb->len < (size_t)fb->width * fb->height * bytesPerPixel) {
        return false;
    }
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

static void connectWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.printf("connecting to WiFi \"%s\"", WIFI_SSID);

    unsigned long startMs = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - startMs > WIFI_CONNECT_TIMEOUT_MS) {
            halt("WiFi connect timed out, halting");
        }
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\nWiFi connected, IP %s\n", WiFi.localIP().toString().c_str());
}

// Called at the top of every loop() iteration. WiFi drops are expected
// over a long-running deployment; unlike the initial connect in
// setup(), this never halts. It blocks the current iteration up to
// WIFI_RECONNECT_TIMEOUT_MS trying to get back online, then gives up
// and lets the caller skip this capture cycle, retrying on the next
// one instead.
static bool ensureWiFiConnected() {
    if (WiFi.status() == WL_CONNECTED) {
        return true;
    }

    Serial.println("WiFi disconnected, reconnecting");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long startMs = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - startMs > WIFI_RECONNECT_TIMEOUT_MS) {
            Serial.println("WiFi reconnect timed out, will retry next cycle");
            return false;
        }
        delay(500);
    }
    Serial.printf("WiFi reconnected, IP %s\n", WiFi.localIP().toString().c_str());
    return true;
}

static bool uploadRoiChange() {
    // One ID per capture, shared between the /frame and /result POSTs
    // below, so the backend's arbiter can pair the Tesseract and
    // on-device results for the same ROI without needing to guess from
    // arrival order.
    String captureId = String(millis());

    uint8_t *jpegBuf = nullptr;
    size_t jpegLen = 0;
    bool ok = fmt2jpg(
        roiBuffer, (size_t)ROI_WIDTH * ROI_HEIGHT * 2, ROI_WIDTH, ROI_HEIGHT,
        PIXFORMAT_RGB565, JPEG_QUALITY, &jpegBuf, &jpegLen
    );
    if (!ok) {
        Serial.println("JPEG encode failed, skipping upload");
        return false;
    }

    bool frameUploaded = uploadFrame(
        jpegBuf, jpegLen, PLAYER_ID, captureId, BACKEND_URL, BACKEND_TOKEN, BACKEND_CA_CERT
    );
    free(jpegBuf);
    if (!frameUploaded) {
        Serial.println("frame upload failed");
        return false;
    }

    if (ondeviceOcrReady()) {
        OndeviceResult result = runOndeviceOcr(roiBuffer, ROI_WIDTH, ROI_HEIGHT);
        // An empty track means segmentation found no characters (ROI
        // text not present, e.g. the unit is on a screen with no track
        // field), not a misread; there is nothing useful to upload.
        if (result.track.length() > 0 &&
            !uploadResult(result.track, result.confidence, PLAYER_ID, captureId, BACKEND_URL,
                           BACKEND_TOKEN, BACKEND_CA_CERT)) {
            Serial.println("on-device result upload failed");
        }
    }
    return true;
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

    connectWiFi();
    initOndeviceOcr();

    Serial.println("camera ready");
}

void loop() {
    unsigned long now = millis();
    if (now - lastCaptureMs < CAPTURE_INTERVAL_MS) {
        delay(100);
        return;
    }
    lastCaptureMs = now;

    if (!ensureWiFiConnected()) {
        return;
    }

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
        if (uploadRoiChange()) {
            lastRoiHash = roiHash;
        }
    }
}
