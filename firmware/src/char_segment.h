// On-device character segmentation for the track-name ROI. There is no
// Tesseract on-device (that is the reason for training a small model at
// all), so this implements its own binarize + projection-profile
// segmentation, separate from ml/prepare_chars.py's Tesseract-based
// segmentation used for training data. The two segmentation methods are
// not guaranteed to produce identical box placement; this is a real
// train/inference distribution risk, not just a style difference.

#pragma once

#include <stdint.h>
#include <vector>

struct CharBox {
    int left;
    int top;
    int right;
    int bottom;
};

struct SegmentedChar {
    CharBox box;
    std::vector<uint8_t> patch; // patchSize * patchSize grayscale, row-major
};

// Binarizes the RGB565 ROI (Otsu threshold on luminance, minority class
// treated as ink), segments left-to-right character boxes via a
// column-projection profile with gap merging, tightens each box's
// vertical extent to its own ink, and extracts a resized grayscale patch
// per box, all from one luminance pass (segmentation and patch
// extraction each need the same luminance buffer; computing it once
// here avoids recomputing it per character).
std::vector<SegmentedChar> segmentAndExtract(const uint8_t *roiRgb565, int width, int height,
                                              int patchSize);
