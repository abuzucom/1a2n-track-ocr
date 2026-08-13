#include "ondevice_ocr.h"

#include <Chirale_TensorFlowLite.h>
#include "tensorflow/lite/micro/all_ops_resolver.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/schema/schema_generated.h"

#include "char_segment.h"
#include "charset.h"
#include "ocr_model.h"

static const int PATCH_SIZE = 24;

// Sized generously against the Phase 4 smoke-test model (~30KB, tiny
// 2-conv-layer CNN). Needs re-checking once a real trained model exists:
// AllocateTensors() fails loudly if this is too small, so undersizing
// is caught at startup, not silently wrong.
static const int TENSOR_ARENA_SIZE = 60 * 1024;

alignas(16) static uint8_t tensorArena[TENSOR_ARENA_SIZE];

static const tflite::Model *model = nullptr;
static tflite::MicroInterpreter *interpreter = nullptr;
static TfLiteTensor *inputTensor = nullptr;
static TfLiteTensor *outputTensor = nullptr;
static bool ready = false;

bool initOndeviceOcr() {
    if (g_model_len == 0) {
        Serial.println("no on-device OCR model embedded, skipping on-device inference");
        return false;
    }

    model = tflite::GetModel(g_model);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        Serial.println("on-device OCR model schema version mismatch, skipping");
        return false;
    }

    static tflite::AllOpsResolver resolver;
    static tflite::MicroInterpreter staticInterpreter(model, resolver, tensorArena, TENSOR_ARENA_SIZE);
    interpreter = &staticInterpreter;

    if (interpreter->AllocateTensors() != kTfLiteOk) {
        Serial.println("on-device OCR AllocateTensors failed (tensor arena too small?), skipping");
        return false;
    }

    inputTensor = interpreter->input(0);
    outputTensor = interpreter->output(0);

    bool inputShapeOk = inputTensor->dims->size == 4 &&
                         inputTensor->dims->data[1] == PATCH_SIZE &&
                         inputTensor->dims->data[2] == PATCH_SIZE;
    if (!inputShapeOk) {
        Serial.println("on-device OCR model input shape does not match PATCH_SIZE, skipping");
        return false;
    }

    if (outputTensor->dims->size == 0) {
        Serial.println("on-device OCR model output has no dimensions, skipping");
        return false;
    }
    int outputSize = outputTensor->dims->data[outputTensor->dims->size - 1];
    if (outputSize != CHARSET_SIZE) {
        Serial.println("on-device OCR model output size does not match CHARSET_SIZE, skipping");
        return false;
    }

    ready = true;
    Serial.println("on-device OCR model ready");
    return true;
}

bool ondeviceOcrReady() {
    return ready;
}

// classified is set to '\0' if inference failed for this patch, in
// which case *confidence is left unset and the caller must not use it.
static void classifyPatch(const uint8_t *patch, char *classified, float *confidence) {
    float scale = inputTensor->params.scale;
    int zeroPoint = inputTensor->params.zero_point;
    float invScale = 1.0f / (255.0f * scale);
    for (int i = 0; i < PATCH_SIZE * PATCH_SIZE; i++) {
        inputTensor->data.int8[i] = (int8_t)(patch[i] * invScale + zeroPoint);
    }

    if (interpreter->Invoke() != kTfLiteOk) {
        *classified = '\0';
        return;
    }

    int bestIndex = 0;
    int8_t bestValue = outputTensor->data.int8[0];
    for (int i = 1; i < CHARSET_SIZE; i++) {
        if (outputTensor->data.int8[i] > bestValue) {
            bestValue = outputTensor->data.int8[i];
            bestIndex = i;
        }
    }
    *classified = CHARSET[bestIndex];

    float outputScale = outputTensor->params.scale;
    int outputZeroPoint = outputTensor->params.zero_point;
    *confidence = (bestValue - outputZeroPoint) * outputScale;
}

OndeviceResult runOndeviceOcr(const uint8_t *roiRgb565, int width, int height) {
    OndeviceResult result = {String(), 0.0f};
    if (!ready) {
        return result;
    }

    std::vector<SegmentedChar> chars = segmentAndExtract(roiRgb565, width, height, PATCH_SIZE);
    result.track.reserve(chars.size());
    float minConfidence = 1.0f;
    for (const auto &segmented : chars) {
        char classified;
        float confidence;
        classifyPatch(segmented.patch.data(), &classified, &confidence);
        if (classified == '\0') {
            continue;
        }
        result.track += classified;
        if (confidence < minConfidence) {
            minConfidence = confidence;
        }
    }
    result.confidence = result.track.length() > 0 ? minConfidence : 0.0f;
    return result;
}
