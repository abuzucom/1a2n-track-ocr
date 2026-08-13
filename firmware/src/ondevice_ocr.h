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

struct OndeviceResult {
    String track;
    // Dequantized softmax value (0-1) of the least-confident classified
    // character. The weakest character, not the average, sets how much
    // to trust the whole string: one bad glyph makes the track wrong
    // regardless of how confident the rest were.
    float confidence;
};

// Segments roiRgb565 into characters and classifies each one. Returns
// an empty track if initOndeviceOcr() has not succeeded (only call this
// after checking ondeviceOcrReady()) or if segmentation found no
// characters at all, which means the ROI's text was not found, not
// misread (e.g. the unit is on a screen without a track field).
OndeviceResult runOndeviceOcr(const uint8_t *roiRgb565, int width, int height);
