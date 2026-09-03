from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingOptions:
    capitalization: bool = True
    punctuation: bool = True


class TextProcessor:
    def process(self, text: str, options: ProcessingOptions) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return ""
        if options.capitalization:
            normalized = normalized[0].upper() + normalized[1:]
        if options.punctuation and normalized[-1] not in ".!?":
            normalized += "."
        return normalized
