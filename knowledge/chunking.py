import re

BLANK_LINES = re.compile(r"\n{3,}")
SENTENCE_BREAKS = ("\n\n", ". ", "! ", "? ", "\n")


def split_text(text: str, size: int, overlap: int) -> list[str]:
    if size < 1:
        raise ValueError("size must be positive.")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be between 0 and size.")
    text = BLANK_LINES.sub("\n\n", text.replace("\r\n", "\n")).strip()
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + size, length)
        if end < length:
            window = text[start:end]
            cut = max(
                window.rfind(marker) + (len(marker) - 1) if marker in window else -1
                for marker in SENTENCE_BREAKS
            )
            if cut >= size // 2:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        next_start = max(end - overlap, start + 1)
        while next_start < end and not text[next_start - 1].isspace():
            next_start += 1
        start = next_start
    return chunks
