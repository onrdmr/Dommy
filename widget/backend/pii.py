"""Hafif PII maskeleme. wahaChat.py post_process desenine dayanır.

ERP kendi verisi olduğu için agresif değil; yine de DOM bağlamından kazara
sızabilecek telefon/e-posta gibi alanları model çağrısından önce maskeler.
İhtiyaca göre genişletin.
"""
import re

_PATTERNS = [
    (re.compile(r"[\w.\-]+@[\w.\-]+\.\w+"), "[email]"),
    (re.compile(r"\+?\d[\d\s\-()]{8,}\d"), "[tel]"),
]


def mask(text: str) -> str:
    if not text:
        return text
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text
