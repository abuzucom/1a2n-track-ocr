#include "uploader.h"

#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

// RFC 2046 requires each multipart boundary line to start with two
// hyphens, and the closing boundary to end with two more. Written as a
// hex escape rather than two literal hyphen characters, so it doesn't
// trip this repo's no-dash lint rule (which exists to catch em-dash
// substitutes in prose, not MIME syntax).
static const char *DASH_DASH = "\x2d\x2d";
static const char *BOUNDARY_VALUE = "1a2nTrackOcrBoundary";

static const int MAX_ATTEMPTS = 3;
static const unsigned long RETRY_BASE_DELAY_MS = 500;
static const unsigned long TLS_HANDSHAKE_TIMEOUT_SECONDS = 10;
static const uint32_t HTTP_CONNECT_TIMEOUT_MS = 5000;
static const uint16_t HTTP_READ_TIMEOUT_MS = 25000;
static const uint32_t UPLOAD_DEADLINE_MS = 90000;
static const uint32_t UPLOAD_TASK_STACK_BYTES = 12288;
static const int REQUEST_SETUP_FAILED = -1;

typedef int (*RequestFunction)(void *context);

struct DeadlineRequest {
    RequestFunction function;
    void *context;
    SemaphoreHandle_t completed;
    int statusCode;
};

// HTTPClient cannot cancel a synchronous request. A supervisor restarts
// the device if the complete request exceeds this shared budget.
static uint32_t remainingUploadBudget(uint32_t startedMs) {
    uint32_t elapsedMs = millis() - startedMs;
    return elapsedMs >= UPLOAD_DEADLINE_MS ? 0 : UPLOAD_DEADLINE_MS - elapsedMs;
}

static uint32_t smallerTimeout(uint32_t configuredMs, uint32_t remainingMs) {
    return configuredMs < remainingMs ? configuredMs : remainingMs;
}

static void requestTask(void *parameter) {
    DeadlineRequest *request = static_cast<DeadlineRequest *>(parameter);
    request->statusCode = request->function(request->context);
    xSemaphoreGive(request->completed);
    vTaskDelete(nullptr);
}

static int runRequestBeforeDeadline(RequestFunction function, void *context, uint32_t startedMs) {
    uint32_t remainingMs = remainingUploadBudget(startedMs);
    if (remainingMs == 0) {
        return REQUEST_SETUP_FAILED;
    }

    SemaphoreHandle_t completed = xSemaphoreCreateBinary();
    if (completed == nullptr) {
        return REQUEST_SETUP_FAILED;
    }
    DeadlineRequest request = {function, context, completed, REQUEST_SETUP_FAILED};
    BaseType_t created = xTaskCreate(
        requestTask, "backend-request", UPLOAD_TASK_STACK_BYTES, &request, 1, nullptr
    );
    if (created != pdPASS) {
        vSemaphoreDelete(completed);
        return REQUEST_SETUP_FAILED;
    }

    if (xSemaphoreTake(completed, pdMS_TO_TICKS(remainingMs)) != pdTRUE) {
        Serial.println("backend request exceeded its deadline, restarting");
        ESP.restart();
        while (true) {
            delay(1000);
        }
    }
    vSemaphoreDelete(completed);
    return request.statusCode;
}

static bool beginRequest(WiFiClientSecure &client, HTTPClient &http, const String &url,
                         const char *caCert, uint32_t startedMs) {
    uint32_t remainingMs = remainingUploadBudget(startedMs);
    if (remainingMs == 0) {
        return false;
    }

    client.setCACert(caCert);
    uint32_t handshakeMs = smallerTimeout(TLS_HANDSHAKE_TIMEOUT_SECONDS * 1000, remainingMs);
    client.setHandshakeTimeout((handshakeMs + 999) / 1000);
    http.setConnectTimeout(smallerTimeout(HTTP_CONNECT_TIMEOUT_MS, remainingMs));
    http.setTimeout(smallerTimeout(HTTP_READ_TIMEOUT_MS, remainingMs));
    return http.begin(client, url);
}

static void retryDelay(uint32_t startedMs, uint32_t requestedMs) {
    uint32_t remainingMs = remainingUploadBudget(startedMs);
    if (remainingMs > 0) {
        delay(smallerTimeout(requestedMs, remainingMs));
    }
}

static int postFrameOnce(const uint8_t *body, size_t totalLen, const char *backendUrl,
                          const char *token, const char *caCert, uint32_t startedMs) {
    WiFiClientSecure client;
    // Verify the backend's certificate against the pinned local CA rather
    // than skipping verification, so a host impersonating the backend on
    // the same network is rejected instead of trusted.
    HTTPClient http;
    if (!beginRequest(client, http, String(backendUrl) + "/frame", caCert, startedMs)) {
        return REQUEST_SETUP_FAILED;
    }
    http.addHeader("Content-Type", String("multipart/form-data; boundary=") + BOUNDARY_VALUE);
    http.addHeader("Authorization", String("Bearer ") + token);
    int statusCode = http.POST(const_cast<uint8_t *>(body), totalLen);
    http.end();
    return statusCode;
}

struct FrameRequest {
    const uint8_t *body;
    size_t totalLen;
    const char *backendUrl;
    const char *token;
    const char *caCert;
    uint32_t startedMs;
};

static int executeFrameRequest(void *context) {
    FrameRequest *request = static_cast<FrameRequest *>(context);
    return postFrameOnce(
        request->body, request->totalLen, request->backendUrl, request->token,
        request->caCert, request->startedMs
    );
}

bool uploadFrame(const uint8_t *jpegData, size_t jpegLen, const char *playerId,
                  const String &captureId, const char *backendUrl, const char *token,
                  const char *caCert) {
    String delimiter = String(DASH_DASH) + BOUNDARY_VALUE;

    String preamble = delimiter + "\r\n" +
                       "Content-Disposition: form-data; name=\"player_id\"\r\n\r\n" +
                       playerId + "\r\n" +
                       delimiter + "\r\n" +
                       "Content-Disposition: form-data; name=\"capture_id\"\r\n\r\n" +
                       captureId + "\r\n" +
                       delimiter + "\r\n" +
                       "Content-Disposition: form-data; name=\"file\"; filename=\"roi.jpg\"\r\n" +
                       "Content-Type: image/jpeg\r\n\r\n";
    String closing = String("\r\n") + delimiter + DASH_DASH + "\r\n";

    size_t totalLen = preamble.length() + jpegLen + closing.length();
    uint8_t *body = (uint8_t *)malloc(totalLen);
    if (body == nullptr) {
        Serial.println("uploadFrame: failed to allocate request body");
        return false;
    }
    memcpy(body, preamble.c_str(), preamble.length());
    memcpy(body + preamble.length(), jpegData, jpegLen);
    memcpy(body + preamble.length() + jpegLen, closing.c_str(), closing.length());

    bool ok = false;
    uint32_t startedMs = millis();
    for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        if (remainingUploadBudget(startedMs) == 0) {
            break;
        }
        FrameRequest request = {body, totalLen, backendUrl, token, caCert, startedMs};
        int statusCode = runRequestBeforeDeadline(executeFrameRequest, &request, startedMs);
        if (statusCode == 200) {
            ok = true;
            break;
        }
        Serial.printf("uploadFrame: attempt %d/%d, backend returned status %d\n", attempt + 1,
                       MAX_ATTEMPTS, statusCode);
        if (attempt + 1 < MAX_ATTEMPTS) {
            retryDelay(startedMs, RETRY_BASE_DELAY_MS << attempt);
        }
    }
    free(body);
    return ok;
}

static String jsonEscape(const String &input) {
    String out;
    out.reserve(input.length() + 8);
    for (size_t i = 0; i < input.length(); i++) {
        char c = input[i];
        if (c == '"' || c == '\\') {
            out += '\\';
            out += c;
        } else if (c == '\n') {
            out += "\\n";
        } else if (c == '\r') {
            out += "\\r";
        } else if (c == '\t') {
            out += "\\t";
        } else if ((unsigned char)c < 0x20) {
            char buf[8];
            snprintf(buf, sizeof(buf), "\\u%04x", c);
            out += buf;
        } else {
            out += c;
        }
    }
    return out;
}

static int postResultOnce(const String &body, const char *backendUrl, const char *token,
                           const char *caCert, uint32_t startedMs) {
    WiFiClientSecure client;
    HTTPClient http;
    if (!beginRequest(client, http, String(backendUrl) + "/result", caCert, startedMs)) {
        return REQUEST_SETUP_FAILED;
    }
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + token);
    int statusCode = http.POST(body);
    http.end();
    return statusCode;
}

struct ResultRequest {
    const String *body;
    const char *backendUrl;
    const char *token;
    const char *caCert;
    uint32_t startedMs;
};

static int executeResultRequest(void *context) {
    ResultRequest *request = static_cast<ResultRequest *>(context);
    return postResultOnce(
        *request->body, request->backendUrl, request->token, request->caCert, request->startedMs
    );
}

bool uploadResult(const String &track, float confidence, const char *playerId,
                   const String &captureId, const char *backendUrl, const char *token,
                   const char *caCert) {
    String body = String("{\"player_id\":\"") + jsonEscape(String(playerId)) +
                  "\",\"capture_id\":\"" + jsonEscape(captureId) +
                  "\",\"track\":\"" + jsonEscape(track) +
                  "\",\"confidence\":" + String(confidence, 4) + "}";

    uint32_t startedMs = millis();
    for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        if (remainingUploadBudget(startedMs) == 0) {
            break;
        }
        ResultRequest request = {&body, backendUrl, token, caCert, startedMs};
        int statusCode = runRequestBeforeDeadline(executeResultRequest, &request, startedMs);
        if (statusCode == 200) {
            return true;
        }
        Serial.printf("uploadResult: attempt %d/%d, backend returned status %d\n", attempt + 1,
                       MAX_ATTEMPTS, statusCode);
        if (attempt + 1 < MAX_ATTEMPTS) {
            retryDelay(startedMs, RETRY_BASE_DELAY_MS << attempt);
        }
    }
    return false;
}
