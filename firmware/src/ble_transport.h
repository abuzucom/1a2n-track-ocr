// Sends on-device OCR results to the backend over Bluetooth LE.
//
// The rig is the GATT peripheral and the host running the server is the
// central, so one laptop serves several rigs. BLE carries results only,
// never frames: a ROI JPEG is tens of KB against BLE's throughput of
// tens of KB per second. A rig built for this transport therefore needs
// a real model in ocr_model.h, since nothing else produces a track.
//
// Wire contract with server/ble_bridge.py. The service and
// characteristic UUIDs and the frame header below are matched there;
// changing either side alone breaks every flashed rig.

#pragma once

#include <Arduino.h>

// Start advertising and wait for nothing: the central connects when it
// is ready. Returns false if the BLE stack failed to start, which is
// fatal for this build.
bool bleTransportBegin(uint32_t passkey);

// True while a central is connected and subscribed to results.
bool bleTransportConnected();

// Send one result, or queue it if the central is away. Returns true if
// it was delivered now; a queued result is not a failure, and is
// flushed by bleTransportFlushPending.
bool sendResultBle(const String &track, float confidence, const char *playerId,
                    const String &captureId, const char *token);

// Deliver whatever queued up while disconnected, oldest first. Cheap to
// call every loop iteration; does nothing when the queue is empty.
void bleTransportFlushPending();
