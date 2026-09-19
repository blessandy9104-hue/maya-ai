"""Shared fixture constants for Maya evaluation scripts.

Only constants that are byte-identical across at least two scripts live
here. Scenario event streams differ deliberately between scripts (different
cutoffs and phrasings), so each script keeps its own.
"""

# Marie Curie bibliography shared by the head-tail and societal-collision
# simulations (result JSON "sources" plus numbered Markdown reference lines).
MARIE_CURIE_SOURCES = [
    "https://www.nobelprize.org/prizes/physics/1903/marie-curie/biographical/",
    "https://www.nobelprize.org/stories/women-who-changed-science/marie-curie/",
    "https://institut-curie.org/legacy-marie-curie-perpetuating-spirit-pioneer",
    "https://www.britannica.com/biography/Marie-Curie",
]

MARIE_CURIE_REFERENCE_LINES = [
    "[1] Nobel Prize, Marie Curie — Biographical: https://www.nobelprize.org/prizes/physics/1903/marie-curie/biographical/",
    "[2] Nobel Prize, Women Who Changed Science: Marie Curie: https://www.nobelprize.org/stories/women-who-changed-science/marie-curie/",
    "[3] Institut Curie, The legacy of Marie Curie: https://institut-curie.org/legacy-marie-curie-perpetuating-spirit-pioneer",
    "[4] Encyclopaedia Britannica, Marie Curie: https://www.britannica.com/biography/Marie-Curie",
]

# NASA Apollo 13 bibliography shared by the forward and reverse holdouts.
NASA_APOLLO13_SOURCES = [
    "https://www.nasa.gov/missions/apollo/apollo-13-mission-details/",
    "https://www.nasa.gov/history/detailed-chronology-of-events-surrounding-the-apollo-13-accident/",
]

NASA_APOLLO13_SOURCE_LINES = [
    "[1] NASA, Apollo 13: Mission Details — https://www.nasa.gov/missions/apollo/apollo-13-mission-details/",
    "[2] NASA History Office, Detailed Chronology of Events Surrounding the Apollo 13 Accident — https://www.nasa.gov/history/detailed-chronology-of-events-surrounding-the-apollo-13-accident/",
]
