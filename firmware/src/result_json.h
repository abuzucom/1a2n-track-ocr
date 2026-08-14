// Builds the on-device result JSON body, shared by both transports.
//
// The WiFi uploader and the BLE transport send the same document over
// different wires. Building it in one place is what keeps them from
// drifting: a change to escaping or field names in one would otherwise
// leave the other producing a body the backend parses differently.

#pragma once

#include <Arduino.h>

// Escape a string for embedding in a JSON string literal.
String jsonEscape(const String &input);

// Serialize one on-device OCR result. Matches the OndeviceResult model
// in server/ingest.py. `token` is optional: the BLE transport carries
// the bearer token in the body, since it has no HTTP headers, while the
// WiFi uploader sends it as an Authorization header and passes nullptr
// here.
String buildResultJson(const String &track, float confidence, const char *playerId,
                        const String &captureId, const char *token);
