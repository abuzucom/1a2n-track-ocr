#include "result_json.h"

String jsonEscape(const String &input) {
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

String buildResultJson(const String &track, float confidence, const char *playerId,
                        const String &captureId, const char *token) {
    String body = String("{\"player_id\":\"") + jsonEscape(String(playerId)) +
                  "\",\"capture_id\":\"" + jsonEscape(captureId) +
                  "\",\"track\":\"" + jsonEscape(track) +
                  "\",\"confidence\":" + String(confidence, 4);
    if (token != nullptr) {
        body += ",\"token\":\"" + jsonEscape(String(token)) + "\"";
    }
    body += "}";
    return body;
}
