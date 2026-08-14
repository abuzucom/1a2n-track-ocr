#!/usr/bin/env python3
"""Generate the editable W11 KiCad schematic from the reviewed parts table."""

from __future__ import annotations

import csv
import re
import uuid
from dataclasses import dataclass
from operator import sub
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PARTS_PATH = ROOT / "parts.csv"
OUTPUT_PATH = ROOT / "w11-schematics.kicad_sch"
SYMBOL_LIBRARY_PATH = ROOT / "w11.kicad_sym"
PROJECT_NAME = "w11-schematics"
SECTIONS = ("Mainboard Core", "Mainboard Power", "Expansion Board")
SECTION_X = {"Mainboard Core": 80.01, "Mainboard Power": 359.41, "Expansion Board": 640.08}
NAMESPACE = uuid.UUID("6dbf951b-814f-4c5e-a3a8-8d70229a9f30")


@dataclass(frozen=True)
class Part:
    section: str
    vendor_ref: str
    reference: str
    value: str
    footprint: str
    description: str
    pins: tuple[tuple[str, str], ...]


def make_uuid(key: str) -> str:
    """Return a deterministic UUID for a generated schematic object."""
    return str(uuid.uuid5(NAMESPACE, key))


def coordinate(value: float) -> str:
    """Return a coordinate without losing KiCad's 1.27mm grid precision."""
    return f"{value:.3f}"


def snap_to_grid(value: float) -> float:
    """Snap a coordinate to KiCad's 1.27mm connection grid."""
    return round(value / 1.27) * 1.27


def escape(value: str) -> str:
    """Escape text for KiCad's quoted S-expression strings."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def project_reference(section: str, vendor_ref: str) -> str:
    """Keep mainboard refs and namespace expansion-board duplicates."""
    if section == "Expansion Board":
        return f"X{vendor_ref}"
    return vendor_ref


def parse_pins(raw_pins: str) -> tuple[tuple[str, str], ...]:
    """Parse semicolon-separated pin-number to net assignments."""
    pins = []
    for assignment in raw_pins.split(";"):
        number, net = assignment.split("=", maxsplit=1)
        pins.append((number.strip(), net.strip()))
    return tuple(pins)


def load_parts() -> list[Part]:
    """Load and validate the reviewed component source table."""
    parts = []
    with open(PARTS_PATH, newline="", encoding="ascii") as handle:
        for row in csv.DictReader(handle):
            section = row["section"]
            vendor_ref = row["reference"]
            if section not in SECTIONS or not re.fullmatch(r"[A-Z]+[0-9]+", vendor_ref):
                raise ValueError(f"invalid component identity: {section} {vendor_ref}")
            parts.append(
                Part(
                    section,
                    vendor_ref,
                    project_reference(section, vendor_ref),
                    row["value"],
                    row["footprint"],
                    row["description"],
                    parse_pins(row["pins"]),
                )
            )
    references = [part.reference for part in parts]
    if len(references) != len(set(references)):
        raise ValueError("generated project references are not unique")
    return parts


def effects(size: float = 1.27, *, hidden: bool = False) -> str:
    """Return standard KiCad text effects."""
    hide = "\n\t\t\t(hide yes)" if hidden else ""
    return f"(effects\n\t\t\t(font (size {size} {size})){hide}\n\t\t)"


def library_property(name: str, value: str, x: float, y: float, hidden: bool = False) -> str:
    """Return one property inside an embedded symbol definition."""
    return (
        f'\t\t\t(property "{name}" "{escape(value)}"\n'
        f"\t\t\t\t(at {x:.2f} {y:.2f} 0)\n\t\t\t\t{effects(hidden=hidden)}\n\t\t\t)"
    )


def pin_offset(index: int, count: int) -> float:
    """Return a centered 2.54mm pin-grid offset."""
    last_index = sub(count, 1)
    return (index + -(last_index / 2)) * 2.54


def library_symbol(pin_count: int, *, embedded: bool) -> str:
    """Return an embedded generic block symbol for one pin count."""
    symbol_name = f"W11:Block{pin_count}" if embedded else f"Block{pin_count}"
    half_height = max(3.81, sub(pin_count, 1) * 1.27 + 2.54)
    pins = []
    for index in range(pin_count):
        y = pin_offset(index, pin_count)
        pins.append(
            "\n".join(
                [
                    "\t\t\t\t(pin passive line",
                    f"\t\t\t\t\t(at -12.7 {y:.2f} 0)",
                    "\t\t\t\t\t(length 2.54)",
                    f'\t\t\t\t\t(name "P{index + 1}" {effects(0.8)})',
                    f'\t\t\t\t\t(number "{index + 1}" {effects(0.8)})',
                    "\t\t\t\t)",
                ]
            )
        )
    properties = [
        library_property("Reference", "U", 0, sub(0, half_height + 2.54)),
        library_property("Value", f"Block{pin_count}", 0, half_height + 2.54),
        library_property("Footprint", "", 0, 0, True),
        library_property("Datasheet", "", 0, 0, True),
        library_property("Description", "W11 PDF reconstruction block", 0, 0, True),
    ]
    return "\n".join(
        [
            f'\t\t(symbol "{symbol_name}"',
            "\t\t\t(pin_names (offset 0.508) (hide yes))",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            *properties,
            f'\t\t\t(symbol "Block{pin_count}_0_1"',
            f"\t\t\t\t(rectangle (start -10.16 {-half_height:.2f})",
            f"\t\t\t\t\t(end 10.16 {half_height:.2f})",
            "\t\t\t\t\t(stroke (width 0.254) (type default))",
            "\t\t\t\t\t(fill (type background)))",
            "\t\t\t)",
            f'\t\t\t(symbol "Block{pin_count}_1_1"',
            *pins,
            "\t\t\t)",
            "\t\t\t(embedded_fonts no)",
            "\t\t)",
        ]
    )


def instance_property(name: str, value: str, x: float, y: float, hidden: bool = False) -> str:
    """Return one property on a placed symbol."""
    return (
        f'\t\t(property "{name}" "{escape(value)}"\n'
        f"\t\t\t(at {x:.2f} {y:.2f} 0)\n\t\t\t{effects(hidden=hidden)}\n\t\t)"
    )


def symbol_instance(part: Part, x: float, y: float, root_uuid: str) -> str:
    """Return a placed component with BOM and provenance properties."""
    pin_count = len(part.pins)
    half_height = max(3.81, sub(pin_count, 1) * 1.27 + 2.54)
    dnp = "yes" if "DNP" in part.value or part.value == "NC" else "no"
    properties = [
        instance_property("Reference", part.reference, x, sub(y, half_height + 2.54)),
        instance_property("Value", part.value, x, y + half_height + 2.54),
        instance_property("Footprint", part.footprint, x, y, True),
        instance_property("Datasheet", "", x, y, True),
        instance_property("Description", part.description, x, y, True),
        instance_property("Board", part.section, x, y, True),
        instance_property("VendorRef", part.vendor_ref, x, y, True),
        instance_property("Source", "Vendor PDF reconstruction", x, y, True),
    ]
    pins = [
        f'\t\t(pin "{index + 1}" (uuid "{make_uuid(f"{part.reference}:pin:{index + 1}")}"))'
        for index in range(pin_count)
    ]
    return "\n".join(
        [
            "\t(symbol",
            f'\t\t(lib_id "W11:Block{pin_count}")',
            f"\t\t(at {coordinate(x)} {coordinate(y)} 0)",
            "\t\t(unit 1)",
            "\t\t(exclude_from_sim no)",
            "\t\t(in_bom yes)",
            "\t\t(on_board yes)",
            f"\t\t(dnp {dnp})",
            f'\t\t(uuid "{make_uuid(f"{part.reference}:symbol")}")',
            *properties,
            *pins,
            "\t\t(instances",
            f'\t\t\t(project "{PROJECT_NAME}"',
            f'\t\t\t\t(path "/{root_uuid}"',
            f'\t\t\t\t\t(reference "{part.reference}")',
            "\t\t\t\t\t(unit 1)",
            "\t\t\t\t)",
            "\t\t\t)",
            "\t\t)",
            "\t)",
        ]
    )


def pin_connections(part: Part, x: float, y: float) -> list[str]:
    """Return labels or no-connect markers at every generated pin."""
    connections = []
    for index, (_number, net) in enumerate(part.pins):
        pin_x = sub(x, 12.7)
        pin_y = y + pin_offset(index, len(part.pins))
        key = f"{part.reference}:connection:{index + 1}"
        if net in {"NC", "DNP"}:
            connections.append(
                f'\t(no_connect (at {coordinate(pin_x)} {coordinate(pin_y)}) '
                f'(uuid "{make_uuid(key)}"))'
            )
            continue
        connections.append(
            "\n".join(
                [
                    f'\t(global_label "{escape(net)}"',
                    "\t\t(shape passive)",
                    f"\t\t(at {coordinate(pin_x)} {coordinate(pin_y)} 180)",
                    "\t\t(fields_autoplaced yes)",
                    f"\t\t{effects(0.8)}",
                    f'\t\t(uuid "{make_uuid(key)}")',
                    '\t\t(property "Intersheetrefs" "${INTERSHEET_REFS}"',
                    f"\t\t\t(at {coordinate(pin_x)} {coordinate(pin_y)} 0)",
                    f"\t\t\t{effects(0.8, hidden=True)}",
                    "\t\t)",
                    "\t)",
                ]
            )
        )
    return connections


def offsheet_marker(reference: str, net: str, x: float, y: float, root_uuid: str) -> str:
    """Return one non-BOM block marking a source net that leaves the page."""
    properties = [
        instance_property("Reference", reference, x, sub(y, 6.35)),
        instance_property("Value", "External endpoint", x, y + 6.35),
        instance_property("Footprint", "", x, y, True),
        instance_property("Datasheet", "", x, y, True),
        instance_property("Description", f"Offsheet endpoint for {net}", x, y, True),
    ]
    return "\n".join(
        [
            "\t(symbol",
            '\t\t(lib_id "W11:Block1")',
            f"\t\t(at {coordinate(x)} {coordinate(y)} 0)",
            "\t\t(unit 1)",
            "\t\t(exclude_from_sim yes)",
            "\t\t(in_bom no)",
            "\t\t(on_board no)",
            "\t\t(dnp no)",
            f'\t\t(uuid "{make_uuid(f"{reference}:symbol")}")',
            *properties,
            f'\t\t(pin "1" (uuid "{make_uuid(f"{reference}:pin:1")}"))',
            "\t\t(instances",
            f'\t\t\t(project "{PROJECT_NAME}"',
            f'\t\t\t\t(path "/{root_uuid}" (reference "{reference}") (unit 1))',
            "\t\t\t)",
            "\t\t)",
            "\t)",
        ]
    )


def offsheet_endpoints(parts: list[Part]) -> tuple[list[str], list[str]]:
    """Add visible non-BOM mates for nets represented by only one pin."""
    net_counts: dict[str, int] = {}
    for part in parts:
        for _number, net in part.pins:
            if net not in {"NC", "DNP"}:
                net_counts[net] = net_counts.get(net, 0) + 1
    singletons = sorted(net for net, count in net_counts.items() if count == 1)
    instances = []
    connections = []
    root_uuid = make_uuid("root")
    x = 1080.77
    for index, net in enumerate(singletons, start=1):
        y = snap_to_grid(60 + sub(index, 1) * 17.78)
        reference = f"#EXT{index:02d}"
        instances.append(offsheet_marker(reference, net, x, y, root_uuid))
        marker = Part("", reference, reference, "", "", "", (("1", net),))
        connections.extend(pin_connections(marker, x, y))
    return instances, connections


def schematic_text(value: str, x: float, y: float, size: float, key: str) -> str:
    """Return an editable schematic text note."""
    return "\n".join(
        [
            f'\t(text "{escape(value)}"',
            "\t\t(exclude_from_sim no)",
            f"\t\t(at {coordinate(x)} {coordinate(y)} 0)",
            f"\t\t{effects(size)}",
            f'\t\t(uuid "{make_uuid(key)}")',
            "\t)",
        ]
    )


def layout_parts(parts: list[Part]) -> tuple[list[str], list[str]]:
    """Place all sections in fixed columns on an A0 drawing sheet."""
    instances = []
    connections = []
    for section in SECTIONS:
        cursor_y = 55.88
        x = SECTION_X[section]
        for part in [candidate for candidate in parts if candidate.section == section]:
            height = max(12.7, sub(len(part.pins), 1) * 2.54 + 7.62)
            if cursor_y + height > 800.0:
                x = snap_to_grid(x + 74.93)
                cursor_y = 55.88
            center_y = snap_to_grid(cursor_y + height / 2)
            root_uuid = make_uuid("root")
            instances.append(symbol_instance(part, x, center_y, root_uuid))
            connections.extend(pin_connections(part, x, center_y))
            cursor_y += height + 5.08
    return instances, connections


def build_schematic(parts: list[Part]) -> str:
    """Return a complete native KiCad 10 schematic document."""
    root_uuid = make_uuid("root")
    pin_counts = sorted({len(part.pins) for part in parts})
    definitions = [library_symbol(pin_count, embedded=True) for pin_count in pin_counts]
    instances, connections = layout_parts(parts)
    endpoint_instances, endpoint_connections = offsheet_endpoints(parts)
    instances.extend(endpoint_instances)
    connections.extend(endpoint_connections)
    notes = [
        schematic_text("W11 ESP32-S3 PDF Reconstruction", 25, 15, 3.0, "title"),
        schematic_text(
            "Source: vendor schematic PDFs in docs/. Verify against hardware before manufacture.",
            25,
            23,
            1.5,
            "warning",
        ),
        schematic_text("External and test endpoints", 1040, 38, 2.0, "external-endpoints"),
    ]
    for section in SECTIONS:
        notes.append(schematic_text(section, sub(SECTION_X[section], 25), 38, 2.0, section))
    return "\n".join(
        [
            "(kicad_sch",
            "\t(version 20250114)",
            '\t(generator "w11_pdf_reconstruction")',
            '\t(generator_version "1.0")',
            f'\t(uuid "{root_uuid}")',
            '\t(paper "A0")',
            "\t(lib_symbols",
            *definitions,
            "\t)",
            *notes,
            *connections,
            *instances,
            "\t(sheet_instances",
            '\t\t(path "/" (page "1"))',
            "\t)",
            "\t(embedded_fonts no)",
            ")",
            "",
        ]
    )


def build_symbol_library(parts: list[Part]) -> str:
    """Return the project-local symbol library used by ERC and editing."""
    definitions = [
        library_symbol(pin_count, embedded=False)
        for pin_count in sorted({len(part.pins) for part in parts})
    ]
    return "\n".join(
        [
            "(kicad_symbol_lib",
            "\t(version 20231120)",
            '\t(generator "w11_pdf_reconstruction")',
            *definitions,
            ")",
            "",
        ]
    )


def main() -> None:
    """Generate the schematic deterministically."""
    parts = load_parts()
    OUTPUT_PATH.write_text(build_schematic(parts), encoding="ascii", newline="\n")
    SYMBOL_LIBRARY_PATH.write_text(
        build_symbol_library(parts),
        encoding="ascii",
        newline="\n",
    )
    print(f"wrote {OUTPUT_PATH} with {len(parts)} components")


if __name__ == "__main__":
    main()
