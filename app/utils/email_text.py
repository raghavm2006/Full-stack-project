"""Remove common quoted-reply sections before extracting new requests."""
import re


def current_message_text(text):
    lines = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*(On .+ wrote:|-{2,}\s*Original Message\s*-{2,})\s*$", line, re.I):
            break
        if not line.lstrip().startswith(">"):
            lines.append(line)
    return "\n".join(lines)
