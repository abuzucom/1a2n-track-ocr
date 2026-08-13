// Uploads a JPEG ROI crop to the backend's /frame endpoint.

#pragma once

#include <Arduino.h>

bool uploadFrame(const uint8_t *jpegData, size_t jpegLen, const char *playerId,
                  const char *backendUrl);
