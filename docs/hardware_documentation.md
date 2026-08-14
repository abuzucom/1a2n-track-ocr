# W11 Hardware Documentation

Reference material for the W11 ESP32-S3 Mini Module (board, antenna, and
camera) used by this project. Sourced from the FCC filing for FCC ID
`2BRTY-W11-V02`, the Meshnology wiki/GitHub docs, and vendor schematics.

## File manifest

| File | Source | What it is |
|---|---|---|
| `W11-mainboard-schematic-v0.1.pdf` | Vendor schematic (rev v0.1, dated 2025-10-16) | Schematic of the W11 mini module mainboard: ESP32-S3R8 MCU, SPI flash, crystal, antenna matching network, USB, boot/reset buttons, RGB LED, test points, board-to-board connectors. |
| `W11-expansion-board-schematic.pdf` | Vendor schematic ("W11 ESP32S3 Exp. v0.1", rev 0.1, dated 2025-11-23, designer Linus.Liao) | Schematic of the W11 expansion/carrier board: camera connector and power (LDO chain), SD card slot, PDM microphone, board-to-board connector pinout to the mainboard. |
| `W11-fcc-external-photos-dimensions.pdf` | FCC filing, FCC ID 2BRTY-W11-V02 ("External Photos") | Photographs of the assembled module's exterior. |
| `W11-fcc-internal-photos-teardown.pdf` | FCC filing, FCC ID 2BRTY-W11-V02 ("Internal Photos") | Teardown photographs with components labeled, including the antenna labeled "2.4G ANT". |
| `W11-fcc-rf-exposure-evaluation.pdf` | FCC filing, FCC ID 2BRTY-W11-V02 | RF exposure/SAR evaluation report per KDB 447498 D01 and 47 CFR 2.1091. |
| `W11-fcc-test-report-BKC26042109DE-1.pdf` | FCC filing, test report BKC26042109DE-1, Shenzhen BKC Testing Co., Ltd | Full FCC compliance test report. Confirms applicant (Shenzhen Qianhai Linghangwan Technology Co., Ltd), manufacturer (Shenzhen Makerfire Technology Co., Ltd), product name "ESP32-S3 Mini Module", model number W11-V0.2. |
| `antenna-BW2.4FNX42-12B1L60-fcc-filing.pdf` | Vendor datasheet (Bat Wireless, dated 2025-04-14), pulled from the FCC filing | Datasheet for a Bat Wireless BW2.4FNX42-12B1L60 2.4GHz FPC antenna. The physical antenna on the board is unmarked; this datasheet is a close match, not a confirmed exact part number. |
| `ESP32-S3-Mini-Module-product-specification-v0.1.8.pdf` | Vendor product specification, version 0.1.8, dated 2026-07-27 | Product specification for the "ESP32-S3 Mini Module" (the mainboard). Change log back to version 0.1.0 (2025-12-17). Version 0.1.8 adds RF compliance, antenna integration, RF exposure, and testing sections per FCC KDB 996369 D03. |
| `ESP32-S3-series-datasheet-v2.2.pdf` | Espressif, ESP32-S3 Series Datasheet, version 2.2 | Chip datasheet for the ESP32-S3 series, covering all package variants including ESP32-S3R8, the variant on this board. Xtensa LX7 dual-core, 45 GPIOs, 2.4GHz Wi-Fi 802.11b/g/n, Bluetooth 5 (LE). |

## Confirmed facts

- **FCC ID:** 2BRTY-W11-V02
- **Model number:** W11-V0.2
- **Product name:** ESP32-S3 Mini Module
- **Manufacturer:** Shenzhen Makerfire Technology Co., Ltd
- **Applicant of record:** Shenzhen Qianhai Linghangwan Technology Co., Ltd
- **MCU:** ESP32-S3R8 (R8 suffix: 8MB integrated PSRAM)
- **SPI flash:** Winbond W25Q128JWUIQ (128Mbit / 16MB, QFN package)
- **Crystal:** 40MHz, +/-10ppm
- **RGB status LED:** GPIO48 through a TZ-H1010-RGB addressable LED (single-wire data, WS2812-style)
- **Buttons:** SW1 (EN/reset, tied to CHIP_PU) and SW2 (GPIO0/boot), both SKTAAAE010 tactile switches
- **Debug test points:** TP1 (EN), TP2 (EN), TP3 (MTDO), TP4 (MTDI), TP5 (MTCK), TP6 (MTMS), TP7 (TX), TP8 (RX)
- **Antenna feed:** RF_IN through an LNA-style matching network (L1, L2, C9, C10) to an IPEX/board antenna connector labeled ANT1/ANT_ID on the mainboard
- **USB:** direct VBUS/D+/D-/GND breakout on connector J3 on the mainboard
- **Board-to-board connectors:** mainboard uses a DF40C-30DP-0.4V(51) connector (J2/J-series), mates with the expansion board's DF40HC(3.0)-30DS-0.4V(51) connector (JA3)

### Radios

The ESP32-S3R8 supports 2.4GHz Wi-Fi 802.11b/g/n and Bluetooth 5 (LE)
(`ESP32-S3-series-datasheet-v2.2.pdf`). The manufacturer's product
specification documents Wi-Fi only. That is a gap in the vendor document,
not a limitation of the module.

Both radios share the single antenna feed described above, so they contend
for one front end. The antenna is specified for Wi-Fi, which is a labeling
choice rather than an electrical limit: Wi-Fi occupies 2400 to 2483.5MHz
and Bluetooth LE occupies 2402 to 2480MHz, so BLE falls entirely inside
the band the antenna and its matching network are already tuned for. BLE
also uses 1 to 2MHz channels against 802.11's 20MHz, so it tolerates a
weaker signal.

The firmware selects one radio at build time; it does not run both. See
`docs/ble_transport.md`.

### Mainboard, from the official product specification

- **Wireless:** Wi-Fi 802.11b/g/n (2.4GHz, up to 150Mbps), Station/SoftAP/Station+SoftAP modes, WPA3/WPA2-PSK. This document covers Wi-Fi only and does not describe the chip's Bluetooth 5 (LE) support; for that see the Espressif datasheet and "Radios" below.
- **Sensors, standard on-board:** temperature sensor (+/-0.1C, -40C to 125C), inertial sensor (accelerometer +/-2g to 16g, gyroscope +/-16 to +/-2048 deg/s), wired via GPIO4 (SCL), GPIO5 (SDA), GPIO6 (INT)
- **Battery voltage monitor:** GPIO2 (ADC)
- **Debug test point pin mapping:** TP1 GND, TP2 EN/CHIP_PU, TP3 MTDO/GPIO40, TP4 MTDI/GPIO41, TP5 MTCK/GPIO39, TP6 MTMS/GPIO42, TP7 TX0/GPIO43, TP8 RX0/GPIO44, TP9 USB D+/GPIO20, TP10 USB D-/GPIO19
- **Power:** USB-C 5V/2A, 3.7V LiPo (300-2000mAh), or external 3.3-5V DC (up to 2A peak). Active mode ~120mA typical, light sleep ~15mA (Wi-Fi standby), deep sleep ~8uA, sleep ~1uA.
- **Security:** AES-128/256, SHA-256, RSA-2048 hardware encryption, secure boot, flash encryption, unique device ID, tamper-detect auto-erase
- **Storage:** external SD card up to 128GB over SPI

### Expansion board

- **Camera interface:** DVP parallel interface on the board-to-board connector: DVP_VSYNC (IO38), DVP_HREF (IO47), DVP_Y9 (IO48), DVP_PCLK (IO13), DVP_Y8/Y7/Y6/Y5/Y4/Y3/Y2 (IO11/IO12/IO14/IO16/IO18/IO17/IO15), camera I2C on CAM_SDA (IO40) / CAM_SCL (IO39)
- **Camera power:** LDO chain from 3.7-5V input to 3.3V, 2.8V (AVDD), and 1.3V (DVDD/IOVDD) rails
- **Microphone:** MSM261D3526H1CPM PDM microphone on PDM_CLK (IO42) / PDM_DATA (IO41)
- **SD card:** SD_CS (D2), SCK (D8), MISO (D9), MOSI (D10), XMCLK on IO10
- **User LED:** USER_LED on IO21
- **Board-to-board connector:** JA3, DF40HC(3.0)-30DS-0.4V(51), 30-position

## Antenna type and connector

The manufacturer's product specification (section 2.2.4, "Antenna Design
and Cabling Specifications") states: "On-board antenna specifications: FPC
antenna, gain 4.07 dBi; external antenna uses a standard IPEX 1.0
connector." This matches the Bat Wireless BW2.4FNX42-12B1L60 datasheet
(FPC antenna, IPEX-1 connector, gain up to 4.07 dBi at 2500MHz) and the
FCC teardown's "2.4G ANT" label. The antenna is an on-board 2.4GHz FPC
antenna on an IPEX-1 connector. The vendor part number is not stamped on
the physical antenna.

## Open questions

- **Antenna connector, wiki vs. datasheet:** the Meshnology wiki page
  describes an SMA whip antenna. The manufacturer's product specification
  and the FCC teardown both describe an on-board FPC antenna on an IPEX-1
  connector. Use the product specification and FCC filing for the antenna
  connector/type.

## Additional specs, from the Meshnology wiki page

- **SoC:** ESP32-S3 dual-core 32-bit LX7 @ up to 240MHz, integrated NPU, INT8/FP16 AI inference. Matches the official product spec.
- **Memory:** 512KB SRAM (on-die), 8MB PSRAM, 16MB SPI NOR flash with OTA support. Matches the official product spec and the W25Q128JWUIQ flash on the schematic.
- **Camera sensor:** OV5640, DVP interface, JPEG capture up to UXGA resolution, PSRAM-buffered. Source: wiki page only. The official product specification does not name a camera sensor part number. Not confirmed against a camera datasheet.
- **Other on-board peripherals:** QMI8658C 6-axis IMU, temperature/humidity sensor, 20-channel 12-bit ADC, 3x SPI, 3x UART (2Mbps max), 2x I2S audio ports
- **Power:** USB Type-C (5V/1A), 3.7V lithium battery with charge management, or 3.3-5V external DC. Sleep current <=1uA.
- **Form factor:** 24.54 x 17.78 x 4.50mm (mainboard module)
