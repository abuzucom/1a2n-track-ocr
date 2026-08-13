// Uploads to the backend: a JPEG ROI crop to /frame, or an on-device
// OCR result to /result.

#pragma once

#include <Arduino.h>

bool uploadFrame(const uint8_t *jpegData, size_t jpegLen, const char *playerId,
                  const String &captureId, const char *backendUrl);

bool uploadResult(const String &track, const char *playerId, const String &captureId,
                   const char *backendUrl);
