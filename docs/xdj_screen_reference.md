# XDJ Screen Reference

Screen layout notes for the Pioneer XDJ-1000 and XDJ-1000MK2, from manual
diagrams. Defines the firmware's ROI (region of interest) placement for
the camera-based OCR pipeline. See the plan at
`C:\Users\jtaya\.claude\plans\let-s-plan-it-out-enumerated-lerdorf.md` and
the project memory `project_xdj_ocr_architecture.md`.

## Source manuals

- `XDJ-1000MK2-manual-en.pdf`: official XDJ-1000MK2 manual, English.
- `XDJ-1000-manual-older-edition.pdf`: an older-edition XDJ-1000 manual,
  English content. The downloaded filename was Russian; renamed for
  clarity. Predates features like HOT CUE AUTO LOAD present in the newer
  manual pages.
- Newer-edition XDJ-1000 manual pages (Normal playback screen, touch
  keys, Performance screen, BROWSE screen) were supplied as pasted images,
  not files. No corresponding PDF exists in this folder for those.

## Fonts

The track-name field uses a distinct display/geometric sans-serif.
Working assumption: EuroSans Pro, unconfirmed. See the plan's "On-device
OCR" section for the Coda substitute used for synthetic training data.

Other UI chrome on the same screen (button labels: BROWSE, TAG LIST,
INFO, MENU, PERFORM; numeric displays) uses Arial, a different typeface.
Train and evaluate the character classifier against the track-name
field's font only. A field added later (BPM, key, track number) needs
its own font check.

## Normal playback screen, labeled elements (1-24)

24 labeled UI elements. Relevant ones:

- **5, Track names:** the track name text field, e.g. "Around Summer".
  Top info bar, right of a music-note (eighth note) icon, left of the
  browse/tag/info/menu/perform tab row. Background color is configurable
  via rekordbox or the unit; do not assume a fixed background
  color/contrast for OCR preprocessing. The music-note icon also precedes
  track entries in the BROWSE list (see below); use it as a visual anchor
  when calibrating the ROI and as a check that the crop frames a track
  field.
- **8, Key:** small text field (e.g. "Em"), top-right of the info bar,
  next to a musical-key icon. Not a track/artist field. Sits immediately
  right of the track name field; use as a second anchor point.
- **1, Player number (1-4):** bottom-left. Not the track field.
- **24, Track number display:** bottom-left, track number (01-999). Not
  the track name/title text.
- **16, BPM display / 15, Playing speed / 12, Time display:** numeric
  fields, not OCR targets.

No artist field exists in this 24-element diagram. Only "Track names"
(item 5) carries track text.

## Normal playback screen, touch keys (1-15)

Same screen, labels the touchable controls. Second real example: "Rising
up (Piatto remix)". The track field includes parenthetical remix/version
tags as part of the string. Do not assume the field is always two
dash-separated components.

- **7, INFO (LINK INFO):** opens a track-details screen with more
  metadata, possibly a real artist field. Requires an active touch on the
  unit; out of scope for the passive-camera OCR approach.

The rest of the touch keys (SLIP, USB, LINK, rekordbox, BROWSE, TAG LIST,
MENU, PERFORM, MEMORY, DELETE, CUE/LOOP CALL, BEAT SYNC, NEEDLE SEARCH)
are playback controls, not OCR targets.

## Performance screen

Reached via the PERFORM touch key (item 9 above). Replaces the top info
bar with the waveform/phase-meter/master-player display and a grid of
HOT CUE/BEAT JUMP/BEAT LOOP pads. The track name field is not present.
Only the track number ("02" in the manual's example) appears, at
bottom-left. Labeled elements are playback pad controls (HOT CUE/BEAT
JUMP mode toggle, HOT CUE DELETE/CALL, HOT CUE BANK, A-D/E-H hot cue
pads, BEAT LOOP pads), not text fields.

DJs use this screen during a set. When the unit is on this screen, the
camera has no track name to OCR until it switches back to Normal
playback. The capture pipeline must treat "ROI text not found" as a
distinct state from a misread, and hold the last known good `track`
value. See the plan's Phase 7.

## File browser (BROWSE) screen

Not an OCR capture target; a track list, not the currently-playing
display. Real filenames from the manual's example list: `Firefly
(Christian Nielsen Remix)`, `Media`, `Isolation Feat KnowKontrol`,
`Around Summer`, `Jupiter Rising (Circus Recordings)`, `One of These
Days`, `Big`.

None follow a clean "Artist - Title" pattern. No separate artist column;
track/folder names sit next to a note icon. The artist-splitting
heuristic (leading "Artist - Title" pattern in `track`) applies to a
minority of real tracks. "Feat" credits and parenthetical remix/label
tags are at least as common as a dash-separated artist prefix. Use these
as test cases for the artist-splitting logic and for checking the
on-device model's training data variety.

The category header above the list reads "TRACK" wrapped in full-width
CJK lenticular brackets (U+3010 before, U+3011 after), not ASCII `[`/`]`.
Not an OCR target. See the font/character-set note in the plan's
"On-device OCR" section.

## XDJ-1000MK2 screen layout

The XDJ-1000MK2 manual's Normal playback screen and Performance screen
pages match the XDJ-1000's: one "Track names" field, no artist field,
same Performance-screen gap. The older-edition XDJ-1000 manual confirms
the same field (labeled item 3 there; that edition has fewer total
labeled elements).

Artist metadata exists inside rekordbox's internal library/tag-list data
(from ID3 tags), used for browse categories and playlists. It is not
displayed as a field on the Normal playback or Performance screens.

Both the XDJ-1000 and XDJ-1000MK2 use the same single-track-field ROI and
parsing design. A two-deck view, if one exists, would be in rekordbox's
own PC/mobile software or on a different Pioneer unit; that needs its own
manual or screenshot to confirm before designing around it.
