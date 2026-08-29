"""Password rules — hardened over artikBroker's 6-character minimum. NIST 800-63B
favors length over forced complexity classes and advises against forced periodic
rotation (it pushes users toward predictable increments), so this policy does neither."""
from __future__ import annotations

MIN_LENGTH = 12

# A small bundled list of the most common passwords — not exhaustive, just blocks
# the obviously-guessable ones (full breach-corpus checking is out of scope here).
_COMMON_PASSWORDS = {
    "password", "password123", "123456789012", "qwertyuiop12", "letmein12345",
    "welcome12345", "administrator", "changeme1234", "iloveyou1234", "princess123",
    "sunshine1234", "dragon123456", "football1234", "baseball1234", "trustno1234",
    "master123456", "monkey123456", "shadow123456", "superman1234", "abc123456789",
}


def validate_password(pw: str, *, email: str = "", username: str = "") -> list[str]:
    """Returns a list of human-readable problems; empty list = acceptable."""
    problems: list[str] = []
    pw = pw or ""
    if len(pw) < MIN_LENGTH:
        problems.append(f"Password must be at least {MIN_LENGTH} characters.")
    lowered = pw.lower()
    if lowered in _COMMON_PASSWORDS:
        problems.append("That password is too common — choose something less guessable.")
    local_part = (email or "").split("@")[0].lower()
    if local_part and len(local_part) >= 4 and local_part in lowered:
        problems.append("Password must not contain your email address.")
    if username and len(username) >= 4 and username.lower() in lowered:
        problems.append("Password must not contain your username.")
    return problems
