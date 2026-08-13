// TFLite-Micro interpreter for the on-device character classifier.

#pragma once

#include <Arduino.h>

// Loads the embedded model (ocr_model.h) and allocates the interpreter.
// Returns false, leaving on-device OCR disabled for the rest of this
// run, if no model is embedded (g_model_len == 0), the model's schema
// version does not match this library, tensor allocation fails, or the
// model's input/output shape does not match what this firmware expects.
bool initOndeviceOcr();

bool ondeviceOcrReady();

// Segments roiRgb565 into characters and classifies each one. Returns
// an empty string if initOndeviceOcr() has not succeeded; only call
// this after checking ondeviceOcrReady().
String runOndeviceOcr(const uint8_t *roiRgb565, int width, int height);
