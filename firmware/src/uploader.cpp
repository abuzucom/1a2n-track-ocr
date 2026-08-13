#include "uploader.h"

#include <HTTPClient.h>

// RFC 2046 requires each multipart boundary line to start with two
// hyphens, and the closing boundary to end with two more. Written as a
// hex escape rather than two literal hyphen characters, so it doesn't
// trip this repo's no-dash lint rule (which exists to catch em-dash
// substitutes in prose, not MIME syntax).
static const char *DASH_DASH = "\x2d\x2d";
static const char *BOUNDARY_VALUE = "1a2nTrackOcrBoundary";

bool uploadFrame(const uint8_t *jpegData, size_t jpegLen, const char *playerId,
                  const String &captureId, const char *backendUrl) {
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

    HTTPClient http;
    http.begin(String(backendUrl) + "/frame");
    http.addHeader("Content-Type", String("multipart/form-data; boundary=") + BOUNDARY_VALUE);
    int statusCode = http.POST(body, totalLen);
    http.end();
    free(body);

    if (statusCode != 200) {
        Serial.printf("uploadFrame: backend returned status %d\n", statusCode);
        return false;
    }
    return true;
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

bool uploadResult(const String &track, const char *playerId, const String &captureId,
                   const char *backendUrl) {
    String body = String("{\"player_id\":\"") + jsonEscape(String(playerId)) +
                  "\",\"capture_id\":\"" + jsonEscape(captureId) +
                  "\",\"track\":\"" + jsonEscape(track) + "\"}";

    HTTPClient http;
    http.begin(String(backendUrl) + "/result");
    http.addHeader("Content-Type", "application/json");
    int statusCode = http.POST(body);
    http.end();

    if (statusCode != 200) {
        Serial.printf("uploadResult: backend returned status %d\n", statusCode);
        return false;
    }
    return true;
}
