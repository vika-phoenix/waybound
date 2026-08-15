"""
Strip contact details out of messages between a guide and a traveller.

Kavkazland earns nothing on a trip arranged off-platform, and the traveller
loses everything the platform provides — payment protection, a refund if the
guide cancels, someone to call when it goes wrong. The usual first step is one
message carrying a phone number or a Telegram handle.

This does not stop two determined people; nothing does, and they meet in person
anyway. It stops the casual exchange, which is most of it, and it makes the
rule visible rather than implied. Upwork and Airbnb both do exactly this.

Deliberately not filtered: ordinary numbers. A guide writing "we start at 07:30"
or "the hut is at 2400m" must not have it mangled, so patterns require enough
digits, or a scheme, to be unambiguous.
"""
import re

REDACTED = '[contact details removed — please keep arrangements on Kavkazland]'

_PATTERNS = [
    # Email, including the "name (at) domain dot com" dodge.
    re.compile(r'\b[\w.+-]+\s*(?:@|\(at\)|\[at\]|\s+at\s+)\s*[\w-]+(?:\s*(?:\.|\(dot\)|\s+dot\s+)\s*[\w-]+)+\b', re.I),
    # Messenger handles and links.
    re.compile(r'\b(?:t\.me|telegram\.me|wa\.me|api\.whatsapp\.com|instagram\.com|vk\.com|facebook\.com|m\.me)/\S+', re.I),
    re.compile(r'(?:telegram|whatsapp|viber|signal|insta(?:gram)?|вотсап|ватсап|телеграм|вайбер)\s*[:\-–]?\s*@?[\w.+]{3,}', re.I),
    re.compile(r'(?<![\w/])@[A-Za-z][\w]{4,}\b'),
    # Phone numbers: 9+ digits allowing spaces, dashes, brackets. Requires
    # either a leading + or enough digits that it cannot be a price or an
    # altitude.
    re.compile(r'\+\d[\d\s().-]{7,}\d'),
    re.compile(r'(?<![\d.,])\d[\d\s().-]{8,}\d(?![\d.,])'),
]


def scrub(text):
    """Return (clean_text, was_changed)."""
    if not text:
        return text, False
    out = text
    for pattern in _PATTERNS:
        out = pattern.sub(REDACTED, out)
    # Collapse runs of the notice so a message full of numbers is not absurd.
    out = re.sub(r'(?:%s\s*){2,}' % re.escape(REDACTED), REDACTED + ' ', out)
    return out, out != text
