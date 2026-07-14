"""Ethnic name database for misclassification detection.

Methodology (important):
  * Surname alone is NEVER enough for high confidence on ambiguous names
    (e.g. Gill, Perera, Silva) that appear across multiple ethnic groups.
  * First names are scored together with surnames. Anglo first names
    (Amy, John, …) tank confidence for weak/ambiguous Indian surnames.
  * Hispanic first names (Alberto, Carlos, …) with Luso/Hispanic-overlapping
    surnames (Perera, Silva, …) prefer Hispanic / low Indian confidence.
  * Distinctive high-confidence Indian surnames (Patel, Singh, …) stay strong
    unless the first name strongly contradicts.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


