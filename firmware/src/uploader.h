// Uploads to the backend: a JPEG ROI crop to /frame, or an on-device
// OCR result to /result.

#pragma once

#include <Arduino.h>

// Both send `Authorization: Bearer <token>`; the backend rejects the
// upload with 401 without it. Retries with a doubling backoff (see
// uploader.cpp) on failure, so a transient WiFi or backend hiccup does
// not silently drop a capture.
bool uploadFrame(const uint8_t *jpegData, size_t jpegLen, const char *playerId,
                  const String &captureId, const char *backendUrl, const char *token);

bool uploadResult(const String &track, float confidence, const char *playerId,
                   const String &captureId, const char *backendUrl, const char *token);
