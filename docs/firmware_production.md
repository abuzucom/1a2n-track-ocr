# Firmware Production Provisioning

The default `w11-esp32s3` environment is for development. It does not
enable Secure Boot or flash encryption. Never place a production rig on
an untrusted network or expose it physically with that build.

The `w11-esp32s3-production` environment enables ESP32-S3 Secure Boot V2
and AES-256 flash encryption in release mode. Building it is safe:

```powershell
pio run -e w11-esp32s3-production
```

Building does not burn eFuses. Flashing and first boot can burn
irreversible eFuses. The production environment disables PlatformIO's
normal upload path so an ordinary `pio run -t upload` cannot provision a
device accidentally.

## Signing

The pinned PlatformIO Arduino builder does not sign its output. Sign both
the bootloader and application with `espsecure.py` on a controlled
provisioning workstation. Keep the RSA-3072 Secure Boot key outside the
repository and expose only its path through `SECURE_BOOT_SIGNING_KEY`.

```powershell
$python = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
$espsecure = "$env:USERPROFILE\.platformio\packages\tool-esptoolpy\espsecure.py"
$build = ".pio\build\w11-esp32s3-production"
$key = $env:SECURE_BOOT_SIGNING_KEY

& $python $espsecure sign-data --version 2 --keyfile $key "$build\bootloader.bin"
& $python $espsecure sign-data --version 2 --keyfile $key "$build\firmware.bin"
& $python $espsecure verify-signature --version 2 --keyfile $key "$build\bootloader.bin"
& $python $espsecure verify-signature --version 2 --keyfile $key "$build\firmware.bin"
```

Do not use the pre-signing `firmware.factory.bin`. Recreate any combined
image only after signing each component.

## Provisioning Boundary

Before any write, identify the board and inspect its current state with
read-only commands:

```powershell
$python = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
$esptool = "$env:USERPROFILE\.platformio\packages\tool-esptoolpy\esptool.py"
$espefuse = "$env:USERPROFILE\.platformio\packages\tool-esptoolpy\espefuse.py"

& $python $esptool --chip esp32s3 --port COM_PORT get-security-info
& $python $espefuse --chip esp32s3 --port COM_PORT summary
```

Provision only through an approved runbook that verifies the board's
identity, uses per-device backend credentials, records the signing-key
identifier, and requires explicit operator confirmation before eFuse or
flash writes. Follow Espressif's Secure Boot V2 and flash-encryption
guides for those irreversible steps. This repository intentionally does
not provide an automatic eFuse-burning command.

After provisioning, repeat the read-only checks and confirm Secure Boot,
release-mode flash encryption, disabled plaintext UART flash reads, and
the expected application signature.
