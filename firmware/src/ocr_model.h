// Placeholder: no trained model exists yet. Generate a real version with
// ml/export_model_header.py once ml/convert.py has produced a real
// firmware/models/ocr_model.tflite trained on real hardware captures.
// g_model_len == 0 tells ondevice_ocr.cpp's initOndeviceOcr() to skip
// on-device inference at runtime rather than fail to load a model. Since
// g_model_len is a compile-time constant 0 here, the compiler also
// proves that branch always taken and dead-code-eliminates the
// interpreter setup code entirely from this placeholder build; that
// code path is only actually compiled once a real model exists.

#pragma once

alignas(16) const unsigned char g_model[] = {0};
const int g_model_len = 0;
