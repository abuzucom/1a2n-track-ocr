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

static char classifyPatch(const uint8_t *patch) {
    float scale = inputTensor->params.scale;
    int zeroPoint = inputTensor->params.zero_point;
    for (int i = 0; i < PATCH_SIZE * PATCH_SIZE; i++) {
        float normalized = patch[i] / 255.0f;
        inputTensor->data.int8[i] = (int8_t)(normalized / scale + zeroPoint);
    }

    if (interpreter->Invoke() != kTfLiteOk) {
        return '\0';
    }

    int bestIndex = 0;
    int8_t bestValue = outputTensor->data.int8[0];
    for (int i = 1; i < CHARSET_SIZE; i++) {
        if (outputTensor->data.int8[i] > bestValue) {
            bestValue = outputTensor->data.int8[i];
            bestIndex = i;
        }
    }
    return CHARSET[bestIndex];
}

String runOndeviceOcr(const uint8_t *roiRgb565, int width, int height) {
    String track;
    if (!ready) {
        return track;
    }

    std::vector<SegmentedChar> chars = segmentAndExtract(roiRgb565, width, height, PATCH_SIZE);
    for (const auto &segmented : chars) {
        char classified = classifyPatch(segmented.patch.data());
        if (classified != '\0') {
            track += classified;
        }
    }
    return track;
}
