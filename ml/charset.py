"""Character class vocabulary for the on-device OCR model.

Fixed order: train.py and convert.py both import this so the class
index never drifts between training and firmware inference. Extend
only when real captures show a character not covered here; do not
guess a full Unicode range up front.
"""

CHARSET = [
    " ",
    *"ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    *"abcdefghijklmnopqrstuvwxyz",
    *"0123456789",
    "-", "(", ")", ".", "'", "&", "!", "/", ":", "%",
]

CHAR_TO_INDEX = {char: index for index, char in enumerate(CHARSET)}

# Fixed square input size (pixels) for every character patch, real or
# synthetic. Both prepare_chars.py and synth.py resize to this on write,
# so train.py never has to resize and the model's input shape is fixed.
PATCH_SIZE = 24

