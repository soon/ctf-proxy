import re


def find_body_flags(body: str, pattern: str) -> list[tuple[int, str]]:
    flags = []
    for match in re.finditer(pattern, body):
        flags.append((match.start(), match.group(0)))
    return flags
