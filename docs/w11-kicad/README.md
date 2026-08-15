# W11 KiCad Schematic Reconstruction

This directory contains an editable KiCad 10 reconstruction of the W11
mainboard and expansion-board vendor schematics. It preserves the visible
component references, values, DNP status, functional pin names, and named
net connectivity from these source files:

- `../W11-mainboard-schematic-v0.1.pdf`
- `../W11-expansion-board-schematic.pdf`

## Files

| File | Purpose |
|---|---|
| `w11-schematics.kicad_pro` | KiCad project settings |
| `w11-schematics.kicad_sch` | Editable schematic with 121 physical components |
| `w11.kicad_sym` | Project-local generic reconstruction symbols |
| `sym-lib-table` | Project symbol-library registration |
| `parts.csv` | Reviewed vendor-reference, value, and net source table |
| `w11-schematics.pdf` | KiCad-generated black-and-white A0 plot |
| `w11-schematics-bom.csv` | KiCad-generated grouped bill of materials |
| `generate_schematic.py` | Deterministic native KiCad schematic generator |

## Reference Handling

The mainboard keeps the vendor reference designators. The expansion board
reuses references such as `U1`, `R1`, and `C1`, which cannot remain unique
inside one flat KiCad project. Its KiCad references therefore add an `X`
prefix, for example `XU1`; the `VendorRef` property and BOM retain `U1`.

The project-local block symbols keep every reviewed pin and named net
editable without claiming package-specific symbol geometry that the PDFs
do not provide. Footprints are assigned only where the source identifies
a package and a matching KiCad footprint is available.

## Limits

This is a source-derived documentation artifact, not manufacturing
authority. The vendor PDFs do not provide an electronic netlist, original
CAD source, stackup, placement, or complete footprint data. Connector pin
assignments follow legible labels in the PDFs and the independently
documented pin map in `../hardware_documentation.md`.

Verify every net, footprint, and rating against physical hardware before
using this reconstruction for manufacture or modification. The source PDFs
remain authoritative where this project differs.

## Regeneration

Run from the repository root with KiCad 10 on `PATH`:

```powershell
$fields = @(
  "Board"
  "VendorRef"
  "Reference"
  "Value"
  "Footprint"
  "Description"
  "QUANTITY"
  "DNP"
) -join ","
$labels = @(
  "Board"
  "Vendor Ref"
  "KiCad Ref"
  "Value"
  "Footprint"
  "Description"
  "Qty"
  "DNP"
) -join ","
python docs/w11-kicad/generate_schematic.py
kicad-cli sym upgrade --force `
  docs/w11-kicad/w11.kicad_sym
kicad-cli sch upgrade --force `
  docs/w11-kicad/w11-schematics.kicad_sch
kicad-cli sch erc --exit-code-violations `
  --output $env:TEMP\w11-schematics-erc.rpt `
  docs/w11-kicad/w11-schematics.kicad_sch
kicad-cli sch export pdf --black-and-white `
  --output docs/w11-kicad/w11-schematics.pdf `
  docs/w11-kicad/w11-schematics.kicad_sch
kicad-cli sch export bom `
  --output docs/w11-kicad/w11-schematics-bom.csv `
  --fields $fields `
  --labels $labels `
  --group-by "Board,Value,Footprint,Description,DNP" `
  docs/w11-kicad/w11-schematics.kicad_sch
```
