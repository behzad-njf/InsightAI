"""Sample LLM JSON for answer-generation tests."""

from __future__ import annotations

import json

CLASSROOM_ANSWER_LLM_JSON = json.dumps(
    {
        "answer": (
            "There are 2 children enrolled in Room A (classroom_id 10) "
            "and 1 child in Room B (classroom_id 20)."
        ),
        "summary_bullets": [
            "Room A (id 10): 2 children",
            "Room B (id 20): 1 child",
        ],
        "row_count_cited": 2,
        "truncation_noted": False,
        "caveats": "",
    }
)
