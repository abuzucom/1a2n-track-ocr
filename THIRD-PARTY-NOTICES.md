# Third-party notices

The MIT license in `LICENSE` covers this repository's source code only.
The third-party material below remains the property of its owners, under
the terms noted.

## Reference documents in docs/

`docs/` holds manufacturer and regulatory documents used to build this
project. This repository's license grants no rights in them.

### Player manuals

`docs/XDJ-1000MK2-manual-en.pdf` and
`docs/XDJ-1000-manual-older-edition.pdf` are copyright AlphaTheta
Corporation (formerly Pioneer DJ Corporation). Retained for reference
because the screen layout they document is what this project reads.
`docs/xdj_screen_reference.md` records the extracted facts. Obtain
current versions from the manufacturer's support site.

### Chip and module documentation

`docs/ESP32-S3-series-datasheet-v2.2.pdf` and
`docs/ESP32-S3-Mini-Module-product-specification-v0.1.8.pdf` are
copyright Espressif Systems.

### Board schematics

`docs/W11-mainboard-schematic-v0.1.pdf` and
`docs/W11-expansion-board-schematic.pdf` are the W11 board vendor's
documents, retained for the pin map recorded in
`docs/hardware_documentation.md`.

### FCC filings

`docs/W11-fcc-*.pdf` and `docs/antenna-BW2.4FNX42-12B1L60-fcc-filing.pdf`
are filings published in the FCC's public equipment authorization
database.

## Fonts

`ml/fonts/Coda-Regular.ttf` and `ml/fonts/Coda-ExtraBold.ttf` are Coda by
Vernon Adams, licensed under the SIL Open Font License 1.1. The license
text ships alongside them in `ml/fonts/OFL.txt`. Used by `ml/synth.py` to
render synthetic training characters.

## Build and runtime dependencies

Not vendored into this repository. Fetched by PlatformIO and pip at
build time, and listed here because the firmware links one of them
statically.

| Dependency | License |
|---|---|
| arduino-esp32 core (via pioarduino platform-espressif32) | LGPL-2.1-or-later |
| esp32-camera (Espressif) | Apache-2.0 |
| Chirale_TensorFlowLite (TensorFlow Lite Micro) | Apache-2.0 |
| TensorFlow | Apache-2.0 |
| Tesseract OCR engine | Apache-2.0 |
| pytesseract | Apache-2.0 |
| OpenCV (opencv-python-headless) | Apache-2.0 |
| python-multipart | Apache-2.0 |
| FastAPI | MIT |
| pytest | MIT |
| Pillow | MIT-CMU |
| uvicorn | BSD-3-Clause |

### Note on the Arduino ESP32 core

The firmware statically links the Arduino ESP32 core, which is
LGPL-2.1-or-later. Distributing this project's source imposes no
obligation. Distributing a compiled firmware binary invokes LGPL section
6, which requires giving recipients what they need to relink the binary
against a modified core. Publishing the firmware source, as this
repository does, satisfies that.
