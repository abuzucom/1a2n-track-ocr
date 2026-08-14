#include "ble_transport.h"

#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLESecurity.h>
#include <BLEServer.h>
#include <BLEUtils.h>

#include "result_json.h"

// Matched by SERVICE_UUID, RESULT_CHAR_UUID, and ACK_CHAR_UUID in
// server/ble_bridge.py.
static const char *SERVICE_UUID = "5b9d1a70-3f4c-4a21-9c86-0e7b1d2f8a41";
static const char *RESULT_CHAR_UUID = "5b9d1a71-3f4c-4a21-9c86-0e7b1d2f8a41";
static const char *ACK_CHAR_UUID = "5b9d1a72-3f4c-4a21-9c86-0e7b1d2f8a41";

// Frame header: sequence number then total message length, both
// unsigned 16-bit little endian, followed by this packet's chunk.
static const size_t FRAME_HEADER_BYTES = 4;

// Matches MAX_MESSAGE_BYTES in server/ble_bridge.py. A result JSON runs
// a few hundred bytes; anything past this would be dropped there.
static const size_t MAX_MESSAGE_BYTES = 1024;

// Requested ATT MTU. The central may negotiate lower, which is why the
// chunk size is taken from the negotiated value rather than this one.
static const uint16_t REQUESTED_MTU = 247;

// Ceiling on one packet's payload, and the size of the stack buffer the
// framer builds into. The ATT maximum of 517 leaves 510 usable, so this
// is never the binding limit; it is here so the buffer cannot overrun
// if a central negotiates something unexpected.
static const uint16_t MAX_CHUNK_BYTES = 512;

// Three bytes of every ATT packet are notification overhead.
static const uint16_t ATT_NOTIFY_OVERHEAD = 3;

// Fallback when the negotiated MTU is unavailable. The BLE 4.0 default
// ATT MTU is 23, which every central supports.
static const uint16_t MINIMUM_ATT_MTU = 23;

static const int MAX_ATTEMPTS = 3;
static const unsigned long RETRY_BASE_DELAY_MS = 500;
static const unsigned long ACK_TIMEOUT_MS = 2000;
static const unsigned long ACK_POLL_INTERVAL_MS = 10;

// Results that could not be delivered wait here. Track changes are
// edge-triggered: main.cpp only sends when the ROI hash changes, so a
// result dropped while the laptop is out of range leaves the overlay on
// the previous track until the next change, which can be many minutes.
// Fixed capacity, oldest evicted first.
static const size_t PENDING_CAPACITY = 8;

static BLEServer *bleServer = nullptr;
static BLECharacteristic *resultCharacteristic = nullptr;
static bool centralConnected = false;
static uint16_t peerConnId = 0;
static volatile uint16_t lastAckedSeq = 0;
static volatile bool ackReceived = false;
static uint16_t nextSeq = 1;

static String pendingBodies[PENDING_CAPACITY];
static size_t pendingHead = 0;
static size_t pendingCount = 0;

// Only the stack-independent overloads are used here. The parameterized
// ones differ between the Bluedroid and NimBLE builds of this library,
// and the connection id is available from the server either way.
class ServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer *server) override {
        centralConnected = true;
        peerConnId = server->getConnId();
        Serial.println("BLE: central connected");
    }

    void onDisconnect(BLEServer *server) override {
        centralConnected = false;
        Serial.println("BLE: central disconnected, advertising again");
        // Without this the rig is invisible after the first disconnect,
        // and only a power cycle brings it back.
        server->startAdvertising();
    }
};

class AckCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *characteristic) override {
        String value = characteristic->getValue();
        if (value.length() < 2) {
            return;
        }
        lastAckedSeq = (uint8_t)value[0] | ((uint16_t)(uint8_t)value[1] << 8);
        ackReceived = true;
    }
};

// Name the rig for the host's Bluetooth menu. Derived from the BLE MAC
// so two rigs flashed from the same config.h still show as two distinct
// rows; without that they would be indistinguishable at pairing time.
static String deviceName() {
    String mac = BLEDevice::getAddress().toString();
    mac.replace(":", "");
    mac.toUpperCase();
    if (mac.length() >= 6) {
        return String("OCR-") + mac.substring(mac.length() - 6);
    }
    return String("OCR-") + mac;
}

bool bleTransportBegin(uint32_t passkey) {
    // The stack has to be up before getAddress() can report the MAC the
    // name is derived from, so init with a placeholder and advertise the
    // real name in the scan response below.
    if (!BLEDevice::init("OCR")) {
        Serial.println("BLE: stack init failed");
        return false;
    }
    BLEDevice::setMTU(REQUESTED_MTU);

    String name = deviceName();

    // Require LE Secure Connections with a passkey, and bond, so the
    // link is encrypted and reconnects are silent. This replaces the TLS
    // that Caddy provides on the WiFi path. These are static methods;
    // the bool overload of setAuthenticationMode is used because it is
    // the one both the Bluedroid and NimBLE builds provide.
    BLESecurity::setPassKey(true, passkey);
    BLESecurity::setAuthenticationMode(true, true, true);  // bonding, MITM, SC
    BLESecurity::setCapability(ESP_IO_CAP_OUT);
    BLESecurity::setKeySize();
    BLESecurity::setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
    BLESecurity::setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);

    bleServer = BLEDevice::createServer();
    if (bleServer == nullptr) {
        Serial.println("BLE: failed to create GATT server");
        return false;
    }
    bleServer->setCallbacks(new ServerCallbacks());

    BLEService *service = bleServer->createService(SERVICE_UUID);
    resultCharacteristic = service->createCharacteristic(
        RESULT_CHAR_UUID, BLECharacteristic::PROPERTY_NOTIFY
    );
    resultCharacteristic->setAccessPermissions(
        ESP_GATT_PERM_READ_ENCRYPTED | ESP_GATT_PERM_WRITE_ENCRYPTED
    );
    resultCharacteristic->addDescriptor(new BLE2902());

    BLECharacteristic *ackCharacteristic = service->createCharacteristic(
        ACK_CHAR_UUID, BLECharacteristic::PROPERTY_WRITE
    );
    ackCharacteristic->setAccessPermissions(
        ESP_GATT_PERM_READ_ENCRYPTED | ESP_GATT_PERM_WRITE_ENCRYPTED
    );
    ackCharacteristic->setCallbacks(new AckCallbacks());

    service->start();

    // The 128-bit service UUID takes 18 of the advertising packet's 31
    // bytes, leaving no room for the name, so the name goes in the scan
    // response. The bridge filters on the UUID; the pairing menus and
    // bleak both read the scan response, so the name still shows.
    BLEAdvertising *advertising = BLEDevice::getAdvertising();
    advertising->addServiceUUID(SERVICE_UUID);
    advertising->setScanResponse(true);
    BLEAdvertisementData scanResponse;
    scanResponse.setName(name);
    advertising->setScanResponseData(scanResponse);
    BLEDevice::startAdvertising();

    Serial.printf("BLE: advertising as %s\n", name.c_str());
    return true;
}

bool bleTransportConnected() {
    return centralConnected;
}

static uint16_t chunkSize() {
    uint16_t mtu = MINIMUM_ATT_MTU;
    if (bleServer != nullptr && centralConnected) {
        uint16_t negotiated = bleServer->getPeerMTU(peerConnId);
        if (negotiated >= MINIMUM_ATT_MTU) {
            mtu = negotiated;
        }
    }
    uint16_t usable = mtu - ATT_NOTIFY_OVERHEAD - FRAME_HEADER_BYTES;
    return usable > MAX_CHUNK_BYTES ? MAX_CHUNK_BYTES : usable;
}

// Notify one message as framed chunks and wait for the central's ack.
static bool notifyFramed(const String &body, uint16_t seq) {
    size_t total = body.length();
    uint16_t payloadPerPacket = chunkSize();
    uint8_t packet[FRAME_HEADER_BYTES + MAX_CHUNK_BYTES];

    ackReceived = false;
    for (size_t offset = 0; offset < total; offset += payloadPerPacket) {
        size_t take = total - offset;
        if (take > payloadPerPacket) {
            take = payloadPerPacket;
        }
        packet[0] = (uint8_t)(seq & 0xff);
        packet[1] = (uint8_t)(seq >> 8);
        packet[2] = (uint8_t)(total & 0xff);
        packet[3] = (uint8_t)(total >> 8);
        memcpy(packet + FRAME_HEADER_BYTES, body.c_str() + offset, take);
        resultCharacteristic->setValue(packet, FRAME_HEADER_BYTES + take);
        resultCharacteristic->notify();
        delay(10);
    }

    unsigned long startMs = millis();
    while (millis() - startMs < ACK_TIMEOUT_MS) {
        if (ackReceived && lastAckedSeq == seq) {
            return true;
        }
        delay(ACK_POLL_INTERVAL_MS);
    }
    return false;
}

static void enqueuePending(const String &body) {
    if (pendingCount == PENDING_CAPACITY) {
        // Drop the oldest: the newest track is the one on screen now.
        pendingHead = (pendingHead + 1) % PENDING_CAPACITY;
        pendingCount--;
        Serial.println("BLE: pending queue full, dropping oldest result");
    }
    size_t tail = (pendingHead + pendingCount) % PENDING_CAPACITY;
    pendingBodies[tail] = body;
    pendingCount++;
    Serial.printf("BLE: queued result, %u pending\n", (unsigned)pendingCount);
}

// Send one already-built body, retrying with a doubling backoff. Does
// not queue: callers decide what an undelivered body means.
static bool sendBody(const String &body) {
    if (!centralConnected) {
        return false;
    }
    if (body.length() > MAX_MESSAGE_BYTES) {
        Serial.printf("BLE: refusing to send %u byte message, over the cap\n",
                       (unsigned)body.length());
        return false;
    }

    for (int attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
        if (notifyFramed(body, nextSeq)) {
            nextSeq++;
            return true;
        }
        Serial.printf("BLE: attempt %d/%d, no ack for seq %u\n", attempt + 1, MAX_ATTEMPTS,
                       (unsigned)nextSeq);
        if (!centralConnected) {
            break;
        }
        if (attempt + 1 < MAX_ATTEMPTS) {
            delay(RETRY_BASE_DELAY_MS << attempt);
        }
    }
    nextSeq++;
    return false;
}

bool sendResultBle(const String &track, float confidence, const char *playerId,
                    const String &captureId, const char *token) {
    // The token travels in the body: BLE has no headers to put it in.
    // The link is encrypted and bonded, and the backend still checks the
    // token against the claimed player_id.
    String body = buildResultJson(track, confidence, playerId, captureId, token);

    if (sendBody(body)) {
        return true;
    }
    enqueuePending(body);
    return false;
}

void bleTransportFlushPending() {
    if (pendingCount == 0 || !centralConnected) {
        return;
    }
    Serial.printf("BLE: flushing %u pending result(s)\n", (unsigned)pendingCount);
    while (pendingCount > 0 && centralConnected) {
        if (!sendBody(pendingBodies[pendingHead])) {
            return;
        }
        pendingBodies[pendingHead] = String();
        pendingHead = (pendingHead + 1) % PENDING_CAPACITY;
        pendingCount--;
    }
}
