#include "uploader.h"

#include <HTTPClient.h>

static const char *BOUNDARY = "----1a2nTrackOcrBoundary";

bool uploadFrame(const uint8_t *jpegData, size_t jpegLen, const char *playerId,
                  const char *backendUrl) {
    String preamble = String("--") + BOUNDARY + "\r\n" +
                       "Content-Disposition: form-data; name=\"player_id\"\r\n\r\n" +
                       playerId + "\r\n" +
                       "--" + BOUNDARY + "\r\n" +
                       "Content-Disposition: form-data; name=\"file\"; filename=\"roi.jpg\"\r\n" +
                       "Content-Type: image/jpeg\r\n\r\n";
    String closing = String("\r\n--") + BOUNDARY + "--\r\n";

    size_t totalLen = preamble.length() + jpegLen + closing.length();
    uint8_t *body = (uint8_t *)malloc(totalLen);
    if (body == nullptr) {
        Serial.println("uploadFrame: failed to allocate request body");
        return false;
    }
    memcpy(body, preamble.c_str(), preamble.length());
    memcpy(body + preamble.length(), jpegData, jpegLen);
    memcpy(body + preamble.length() + jpegLen, closing.c_str(), closing.length());

    HTTPClient http;
    http.begin(String(backendUrl) + "/frame");
    http.addHeader("Content-Type", String("multipart/form-data; boundary=") + BOUNDARY);
    int statusCode = http.POST(body, totalLen);
    http.end();
    free(body);

    if (statusCode != 200) {
        Serial.printf("uploadFrame: backend returned status %d\n", statusCode);
        return false;
    }
    return true;
}
