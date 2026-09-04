from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingOptions:
    capitalization: bool = True
    punctuation: bool = True
    normalize_whitespace: bool = True


class TextProcessor:
    def process(self, text: str, options: ProcessingOptions) -> str:
        normalized = re.sub(r"\s+", " ", text).strip() if options.normalize_whitespace else text
        if not normalized:
            return ""
        if options.capitalization and options.normalize_whitespace:
            normalized = normalized[0].upper() + normalized[1:]
        if options.punctuation and options.normalize_whitespace and normalized[-1].isalnum():
            normalized += "."
        return normalized
