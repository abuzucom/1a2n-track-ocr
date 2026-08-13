#include "char_segment.h"

#include <algorithm>

static const int MAX_CHARS = 48;
static const int MIN_GAP_PX = 2;
static const int MIN_CHAR_WIDTH_PX = 2;

static uint8_t luminance565(uint16_t pixel) {
    uint8_t r5 = (pixel >> 11) & 0x1F;
    uint8_t g6 = (pixel >> 5) & 0x3F;
    uint8_t b5 = pixel & 0x1F;
    uint8_t r8 = (uint8_t)((r5 * 255) / 31);
    uint8_t g8 = (uint8_t)((g6 * 255) / 63);
    uint8_t b8 = (uint8_t)((b5 * 255) / 31);
    return (uint8_t)((r8 * 299 + g8 * 587 + b8 * 114) / 1000);
}

static void buildLuminance(const uint8_t *roiRgb565, int width, int height, uint8_t *out) {
    // esp32-camera RGB565 frames are big-endian per pixel.
    for (int i = 0; i < width * height; i++) {
        uint16_t pixel = (roiRgb565[i * 2] << 8) | roiRgb565[i * 2 + 1];
        out[i] = luminance565(pixel);
    }
}

static int otsuThreshold(const uint8_t *luminance, int count) {
    int histogram[256] = {0};
    for (int i = 0; i < count; i++) {
        histogram[luminance[i]]++;
    }

    long sumAll = 0;
    for (int level = 0; level < 256; level++) {
        sumAll += (long)level * histogram[level];
    }

    long weightBackground = 0;
    long sumBackground = 0;
    float maxVariance = 0.0f;
    int bestThreshold = 0;

    for (int level = 0; level < 256; level++) {
        weightBackground += histogram[level];
        if (weightBackground == 0) {
            continue;
        }
        long weightForeground = count - weightBackground;
        if (weightForeground == 0) {
            break;
        }
        sumBackground += (long)level * histogram[level];
        float meanBackground = (float)sumBackground / weightBackground;
        float meanForeground = (float)(sumAll - sumBackground) / weightForeground;
        float diff = meanBackground - meanForeground;
        float variance = (float)weightBackground * (float)weightForeground * diff * diff;
        if (variance > maxVariance) {
            maxVariance = variance;
            bestThreshold = level;
        }
    }
    return bestThreshold;
}

static std::vector<CharBox> findBoxes(const uint8_t *luminance, int width, int height,
                                       int threshold, bool inkIsAbove) {
    auto isInk = [&](int x, int y) {
        uint8_t value = luminance[y * width + x];
        return inkIsAbove ? value > threshold : value <= threshold;
    };

    std::vector<int> columnInk(width, 0);
    for (int x = 0; x < width; x++) {
        int count = 0;
        for (int y = 0; y < height; y++) {
            if (isInk(x, y)) {
                count++;
            }
        }
        columnInk[x] = count;
    }

    std::vector<CharBox> boxes;
    int runStart = -1;
    int lastActiveX = -1;
    for (int x = 0; x <= width && (int)boxes.size() < MAX_CHARS; x++) {
        bool active = x < width && columnInk[x] > 0;
        if (active) {
            if (runStart == -1) {
                runStart = x;
            } else if (lastActiveX >= 0 && x - lastActiveX > MIN_GAP_PX) {
                if (lastActiveX - runStart + 1 >= MIN_CHAR_WIDTH_PX) {
                    boxes.push_back({runStart, 0, lastActiveX + 1, height});
                }
                runStart = x;
            }
            lastActiveX = x;
        } else if (runStart != -1 && (x == width || x - lastActiveX > MIN_GAP_PX)) {
            if (lastActiveX - runStart + 1 >= MIN_CHAR_WIDTH_PX) {
                boxes.push_back({runStart, 0, lastActiveX + 1, height});
            }
            runStart = -1;
        }
    }

    for (auto &box : boxes) {
        int top = height;
        int bottom = 0;
        for (int x = box.left; x < box.right; x++) {
            for (int y = 0; y < height; y++) {
                if (isInk(x, y)) {
                    top = std::min(top, y);
                    bottom = std::max(bottom, y + 1);
                }
            }
        }
        if (top < bottom) {
            box.top = top;
            box.bottom = bottom;
        }
    }

    return boxes;
}

static void extractPatch(const uint8_t *luminance, int width, int height, const CharBox &box,
                          uint8_t *out, int patchSize) {
    int boxWidth = std::max(1, box.right - box.left);
    int boxHeight = std::max(1, box.bottom - box.top);

    for (int py = 0; py < patchSize; py++) {
        int srcY = box.top + (py * boxHeight) / patchSize;
        srcY = std::min(srcY, height - 1);
        for (int px = 0; px < patchSize; px++) {
            int srcX = box.left + (px * boxWidth) / patchSize;
            srcX = std::min(srcX, width - 1);
            out[py * patchSize + px] = luminance[srcY * width + srcX];
        }
    }
}

std::vector<SegmentedChar> segmentAndExtract(const uint8_t *roiRgb565, int width, int height,
                                              int patchSize) {
    std::vector<SegmentedChar> result;
    if (width <= 0 || height <= 0) {
        return result;
    }

    std::vector<uint8_t> luminance(width * height);
    buildLuminance(roiRgb565, width, height, luminance.data());

    int threshold = otsuThreshold(luminance.data(), width * height);
    long aboveCount = 0;
    for (int i = 0; i < width * height; i++) {
        if (luminance[i] > threshold) {
            aboveCount++;
        }
    }
    bool inkIsAbove = aboveCount < (width * height - aboveCount);

    std::vector<CharBox> boxes = findBoxes(luminance.data(), width, height, threshold, inkIsAbove);

    result.reserve(boxes.size());
    for (const auto &box : boxes) {
        SegmentedChar segmented;
        segmented.box = box;
        segmented.patch.resize((size_t)patchSize * patchSize);
        extractPatch(luminance.data(), width, height, box, segmented.patch.data(), patchSize);
        result.push_back(std::move(segmented));
    }
    return result;
}
