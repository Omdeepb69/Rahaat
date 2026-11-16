"""Deterministic extraction of operational facts from report text.

Keyword and pattern rules over English, Hindi, Malayalam and Konkani (native
script and common romanisations). Each finding carries the exact text that
triggered it so an operator can see why it was raised.

Design constraints:

* A rule can assert that something is present. It never asserts absence: a
  negated phrase ("nobody is trapped") produces no finding, leaving the fact
  unknown, because an unknown never lowers triage priority and a mis-parsed
  negation must not either.
* No confidence value is attached. These rules are not calibrated.
* Location phrases are extracted as text to look up, never mapped to a place.

Konkani coverage is limited to a short list of common words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

EXTRACTOR_NAME = "rules"
EXTRACTOR_VERSION = "2026.11"


@dataclass(frozen=True)
class Finding:
    attribute: str
    value: Any
    matched_text: str
    note: Optional[str] = None


@dataclass(frozen=True)
class LocationMention:
    phrase: str
    relation: Optional[str]  # near | behind | opposite | in_front_of | at | None
    matched_text: str


@dataclass
class RuleExtraction:
    findings: list[Finding] = field(default_factory=list)
    location_mentions: list[LocationMention] = field(default_factory=list)
    category: Optional[str] = None
    category_matched_text: Optional[str] = None

    def values(self, attribute: str) -> list[Any]:
        return [f.value for f in self.findings if f.attribute == attribute]


def _terms(*groups: str) -> tuple[str, ...]:
    out: list[str] = []
    for group in groups:
        out.extend(t.strip() for t in group.split("|") if t.strip())
    return tuple(out)


TRAPPED = _terms(
    "trapped|stranded|stuck|cannot get out|can't get out|unable to leave|marooned|cut off",
    "फंसे|फँसे|फंसा|फंसी|फंस गए|बचाओ|निकल नहीं",
    "phanse|phase|fase|fanse|phans gaye|bachao|bacha lo",
    "കുടുങ്ങി|കുടുങ്ങിക്കിടക്കു|ഒറ്റപ്പെട്ടു|രക്ഷിക്കണം|രക്ഷിക്കൂ|പുറത്തിറങ്ങാൻ കഴിയ",
    "kudungi|rakshikkanam|rakshikku",
    "आडकल्यात|आडकलां|वाचयात",
)
MEDICAL = _terms(
    "injured|injury|bleeding|unconscious|heart attack|chest pain|breathing|medical|doctor|ambulance"
    "|patient|fracture|drowning|drowned|seizure|dialysis|oxygen|insulin|in labour|in labor",
    "घायल|चोट|बीमार|बेहोश|खून|डॉक्टर|एम्बुलेंस|मरीज|सांस|ऑक्सीजन|दवा",
    "ghayal|chot|bimar|behosh|khoon|mareez|saans|dawai",
    "പരിക്ക്|രോഗി|ബോധം|രക്തം|ഡോക്ടർ|ആംബുലൻസ്|ശ്വാസം|ഓക്സിജൻ|മരുന്ന്|അസുഖം",
    "दुयेंत|दोतोर",
)
LIFE_THREATENING = _terms(
    "unconscious|not breathing|heart attack|bleeding heavily|severe bleeding|drowning|seizure"
    "|बेहोश|सांस नहीं|behosh|ബോധം ഇല്ല|ശ്വാസം കിട്ടുന്നില്ല"
)
VULNERABLE = {
    "elderly": _terms(
        "elderly|old man|old woman|senior citizen|aged|bedridden|grandmother|grandfather",
        "बुजुर्ग|बूढ़े|बूढ़ी|वृद्ध|buzurg|boodhe|budhe",
        "പ്രായമായ|വൃദ്ധ|കിടപ്പുരോഗി|അമ്മൂമ്മ|അപ്പൂപ്പൻ",
        "जाण्टे|जाण्टीं",
    ),
    "children": _terms(
        "child|children|baby|infant|toddler|kids|newborn",
        "बच्चे|बच्चा|बच्ची|शिशु|bacche|bachche|baccha",
        "കുട്ടി|കുട്ടികൾ|കുഞ്ഞ്|കുഞ്ഞുങ്ങൾ",
        "भुरगीं|भुरगो|भुरगें",
    ),
    "pregnant": _terms("pregnant|गर्भवती|garbhvati|ഗർഭിണി|गुरवार"),
    "disabled": _terms(
        "disabled|wheelchair|paralysed|paralyzed|cannot walk|blind|विकलांग|दिव्यांग|ഭിന്നശേഷി|തളർന്ന"
    ),
}
WATER_RISING = _terms(
    "water is rising|water rising|rising water|water level rising|level is rising|rising fast"
    "|keeps rising|water coming in|water is entering|water entering|water entered|water has entered",
    "पानी बढ़|पानी चढ़|पानी घुस|पानी भर रहा|जलस्तर बढ़",
    "paani badh|pani badh|paani chadh|pani chadh|paani ghus|pani ghus|paani bhar raha",
    "വെള്ളം കയറു|വെള്ളം ഉയരു|വെള്ളം കൂടു|ജലനിരപ്പ് ഉയരു|വെള്ളം കയറി",
    "vellam kayaru|vellam uyaru|vellam koodu",
    "उदक वाडटा|उदक चडटा|उदक भितर",
)
WATER_FALLING = _terms(
    "water is receding|water receding|water level falling|water is going down|water has gone down",
    "पानी घट|पानी उतर|पानी कम हो",
    "paani ghat|pani ghat|paani utar|pani utar",
    "വെള്ളം കുറയു|വെള്ളം ഇറങ്ങു|വെള്ളം താഴു",
    "उदक देंवता|उदक उणें",
)
WATER_ENTERED_HOME = _terms(
    "water entered our house|water has entered|water inside the house|water in the house"
    "|water entered the house|house is flooded|home is flooded|flooded house",
    "घर में पानी|घर के अंदर पानी|ghar mein paani|ghar me pani|ghar mein pani",
    "വീട്ടിൽ വെള്ളം|വീടിനുള്ളിൽ വെള്ളം|veettil vellam",
    "घरांत उदक",
)
FLOOR = {
    "roof": _terms(
        "on the roof|rooftop|on roof|terrace|छत पर|chhat par|chat par|മേൽക്കൂര|ടെറസ്|terrasil|पाख्यार"
    ),
    "first": _terms("first floor|1st floor|upstairs|पहली मंजिल|ഒന്നാം നില|മുകളിലത്തെ നില"),
    "second": _terms("second floor|2nd floor|दूसरी मंजिल|രണ്ടാം നില"),
    "ground": _terms("ground floor|भूतल|निचली मंजिल|താഴത്തെ നില"),
}
HAZARDS = {
    "electrical": _terms(
        "live wire|electric shock|electrocution|power line|transformer|current in the water"
        "|करंट|बिजली का तार|current aa raha|വൈദ്യുതി|ഷോക്ക്|ലൈൻ കമ്പി"
    ),
    "landslide": _terms(
        "landslide|landslip|mudslide|hill collapsed|भूस्खलन|पहाड़ खिसक|bhuskhalan|ഉരുൾപൊട്ടൽ|മണ്ണിടിച്ചിൽ|urulpottal|दरड"
    ),
    "fire": _terms("fire broke|on fire|caught fire|burning|आग लग|aag lag|തീപിടി|തീ പിടി|उजो"),
    "structural_collapse": _terms(
        "collapsed|collapse|wall fell|roof fell|building fell|दीवार गिर|मकान गिर|छत गिर|deewar gir"
        "|makan gir|ഇടിഞ്ഞു|തകർന്നു|ഇടിഞ്ഞുവീണ"
    ),
    "gas_leak": _terms("gas leak|smell of gas|गैस लीक|gas leak ho|ഗ്യാസ് ചോർ"),
    "strong_current": _terms("strong current|fast flowing|swept away|washed away|बह गए|बहाव|ഒഴുക്കിൽ|ഒലിച്ചുപോയി"),
    "road_blocked": _terms(
        "road is blocked|road blocked|road submerged|road washed|bridge washed|bridge collapsed"
        "|रास्ता बंद|सड़क बंद|पुल टूट|rasta band|sadak band|റോഡ് തകർ|റോഡ് മുങ്ങി|പാലം തകർ|रस्तो बंद"
    ),
}
NEEDS = {
    "rescue_boat": _terms("boat|नाव|naav|nav chahiye|ബോട്ട്|വള്ളം|होडें|व्हडें"),
    "evacuation": _terms("evacuate|evacuation|rescue us|need rescue|get us out|निकालो|nikalo|ഒഴിപ്പിക്ക|രക്ഷിക്ക"),
    "medical": _terms("ambulance|doctor|medicine|first aid|एम्बुलेंस|दवा|dawai|ആംബുലൻസ്|മരുന്ന്|वखद"),
    "food_water": _terms(
        "food|drinking water|no water to drink|खाना|भोजन|पीने का पानी|khana|peene ka paani"
        "|ഭക്ഷണം|കുടിവെള്ളം|जेवण|पियेवपाचें उदक"
    ),
    "shelter": _terms("shelter|relief camp|nowhere to stay|राहत शिविर|आश्रय|ക്യാമ്പ്|അഭയം|आलाशिरो"),
}
CATEGORY_TERMS = (
    ("landslide", HAZARDS["landslide"]),
    ("fire", HAZARDS["fire"]),
    ("building_collapse", HAZARDS["structural_collapse"]),
    (
        "flood",
        _terms(
            "flood|flooded|flooding|water logging|waterlogging|inundat|submerged|बाढ़|जलभराव|baadh|baarh"
            "|വെള്ളപ്പൊക്കം|പ്രളയം|വെള്ളം കയറി|vellapokkam|pralayam|हुंवार|पूर आयला"
        )
        + WATER_RISING
        + WATER_ENTERED_HOME,
    ),
    ("cyclone", _terms("cyclone|storm surge|चक्रवात|തൂഫാൻ|ചുഴലിക്കാറ്റ്|वादळ")),
    (
        "infrastructure",
        HAZARDS["road_blocked"] + _terms("power outage|no electricity|bridge damaged|dam|बांध टूट|അണക്കെട്ട്"),
    ),
    ("medical", LIFE_THREATENING),
    ("stranded", TRAPPED),
)

_NEGATION = re.compile(
    r"\b(no|not|nobody|no one|none|never|without|isn't|aren't|wasn't|don't|doesn't|nahi|nahin|na)\b"
    r"|नहीं|ना |न |ഇല്ല|അല്ല|ना$",
    re.IGNORECASE,
)

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "सात": 7,
    "आठ": 8, "नौ": 9, "दस": 10,
    "ഒരു": 1, "രണ്ട്": 2, "രണ്ടു": 2, "മൂന്ന്": 3, "മൂന്നു": 3, "നാല്": 4, "നാലു": 4,
    "അഞ്ച്": 5, "അഞ്ചു": 5, "ആറ്": 6, "ആറു": 6, "ഏഴ്": 7, "ഏഴു": 7, "എട്ട്": 8, "എട്ടു": 8,
    "ഒമ്പത്": 9, "പത്ത്": 10, "പത്തു": 10,
    # Konkani forms not shared with Hindi.
    "दोन": 2, "स": 6,
}
_PEOPLE_UNITS = (
    r"people|persons|person|members|adults|of us|family members|villagers|residents|passengers"
    r"|log|logon|लोग|लोगों|सदस्य|जन|जण|लोक"
    r"|പേർ|പേര്|പേരുണ്ട്|ആളുകൾ|ആൾക്കാർ|per|peru|aalukal"
)
_NUM = r"(\d{1,4})"
_NUMWORD = "|".join(sorted((re.escape(w) for w in _NUMBER_WORDS), key=len, reverse=True))
_PEOPLE_DIGITS = re.compile(rf"{_NUM}\s*(?:{_PEOPLE_UNITS})", re.IGNORECASE)
_PEOPLE_WORDS = re.compile(rf"(?<!\w)({_NUMWORD})\s+(?:{_PEOPLE_UNITS})", re.IGNORECASE)
_WE_ARE = re.compile(rf"\bwe are {_NUM}\b|\bhum {_NUM}\b|\b{_NUM} of us\b", re.IGNORECASE)

_DEPTH_UNITS = re.compile(
    r"(\d+(?:\.\d+)?)\s*(feet|foot|ft|फीट|फुट|അടി|adi|meters|metres|meter|metre|मीटर|മീറ്റർ|cm|centimet(?:er|re)s?|inches|inch|इंच)"
    r"(?![a-z])",
    re.IGNORECASE,
)
_DEPTH_FACTORS = {
    "feet": 30.48, "foot": 30.48, "ft": 30.48, "फीट": 30.48, "फुट": 30.48, "അടി": 30.48, "adi": 30.48,
    "meters": 100.0, "metres": 100.0, "meter": 100.0, "metre": 100.0, "मीटर": 100.0, "മീറ്റർ": 100.0,
    "cm": 1.0, "inches": 2.54, "inch": 2.54, "इंच": 2.54,
}
# Body-referenced depths are coarse estimates for an adult of average height.
_BODY_DEPTH = (
    (_terms("neck deep|up to the neck|up to our necks|गले तक|gale tak|കഴുത്തറ്റം|കഴുത്തുവരെ"), 140.0),
    (_terms("chest deep|up to the chest|छाती तक|seene tak|നെഞ്ചറ്റം|നെഞ്ചുവരെ"), 120.0),
    (_terms("waist deep|up to the waist|कमर तक|kamar tak|അരയറ്റം|അരവരെ|അരയ്ക്കൊപ്പം"), 100.0),
    (_terms("knee deep|up to the knee|घुटने तक|ghutne tak|മുട്ടറ്റം|മുട്ടുവരെ|മുട്ടോളം"), 50.0),
    (_terms("ankle deep|टखने तक|കണങ്കാൽ"), 15.0),
)

# Location relations. English and romanised forms precede the place; Hindi,
# Malayalam and Konkani postpositions follow it.
_PRE_RELATIONS = (
    ("near", r"near(?: to| the)?|close to|next to|beside|nearby|adjacent to"),
    ("behind", r"behind(?: the)?|back of|at the back of"),
    ("opposite", r"opposite(?: to| the)?|across from|facing"),
    ("in_front_of", r"in front of|front of"),
    ("at", r"at(?: the)?|in(?: the)?|inside(?: the)?"),
)
_POST_RELATIONS = (
    ("near", r"के पास|के नज़दीक|के नजदीक|के बगल|ke paas|ke pass|ke nazdeek|ke bagal"
             r"|ന് സമീപം|നു സമീപം|ന്റെ അടുത്ത്|ന് അടുത്ത്|നടുത്ത്|സമീപം|അടുത്ത്|aduthu|sameepam|लागीं|lagim"),
    ("behind", r"के पीछे|ke peeche|ke piche|ന് പിന്നിൽ|ന്റെ പിന്നിൽ|പിന്നിൽ|പുറകിൽ|pinnil|फाटल्यान|fattlean"),
    ("opposite", r"के सामने वाली|ന് എതിർവശത്ത്|എതിർവശത്ത്|എതിരെ|ethirvasam"),
    ("in_front_of", r"के सामने|के आगे|ke saamne|ke samne|ന് മുന്നിൽ|ന്റെ മുന്നിൽ|മുന്നിൽ|munnil|मुखार|mukhar"),
)
_STOP_AT = re.compile(
    r"[,.;:!?\n।]| and | but | we | please | there | our | with | water | है | हैं | और "
    r"| हम | കൂടെ | ഞങ്ങൾ | വെള്ളം ",
    re.IGNORECASE,
)
_PLACE_HINT = re.compile(
    r"bridge|school|college|temple|church|mosque|masjid|hospital|clinic|station|junction|road|street"
    r"|market|bazaar|bus stand|bus stop|jetty|canal|river|ward|colony|nagar|panchayat|office|bank"
    r"|tower|gate|circle|chowk|mandir|gurudwara|chapel|convent|ground|stadium|dam|ferry|post office"
    r"|पुल|स्कूल|विद्यालय|मंदिर|मस्जिद|चर्च|अस्पताल|स्टेशन|चौक|बाजार|नदी|कॉलोनी|नगर"
    r"|പാലം|സ്കൂൾ|ക്ഷേത്രം|അമ്പലം|പള്ളി|ആശുപത്രി|സ്റ്റേഷൻ|ജംഗ്ഷൻ|കവല|റോഡ്|ചന്ത|മാർക്കറ്റ്|പുഴ|കടവ്"
    r"|इगर्ज|देवूळ|साकव|शाळा|बाजार|न्हंय",
    re.IGNORECASE,
)
_GENERIC_PLACES = frozenset(
    {"house", "home", "the house", "our house", "my house", "roof", "the roof", "water", "here",
     "there", "danger", "trouble", "need", "front", "area", "village", "our village", "घर", "വീട്"}
)


_FILLER_WORDS = frozenset(
    "hai hain raha rahi rahe tha thi aur hum ham log pani paani badh ghar mein me ka ki ke the is a"
    " है हैं रहा रही रहे था थी और हम लोग पानी बढ़ घर में का की के एक"
    " ഞങ്ങൾ വെള്ളം വീട്ടിൽ ഒരു ഉണ്ട് ആണ്".split()
)


def _find(text: str, lowered: str, terms: tuple[str, ...]) -> Optional[tuple[int, str]]:
    """First non-negated occurrence of any term: (index, matched text)."""
    best: Optional[tuple[int, str]] = None
    for term in terms:
        needle = term.lower()
        start = 0
        while True:
            idx = lowered.find(needle, start)
            if idx == -1:
                break
            start = idx + len(needle)
            if needle.isascii() and needle[0].isalnum():
                before = lowered[idx - 1] if idx > 0 else " "
                after = lowered[idx + len(needle)] if idx + len(needle) < len(lowered) else " "
                if before.isalnum() or (after.isalnum() and len(needle) <= 5):
                    continue
            if _is_negated(lowered, idx, idx + len(needle)):
                continue
            if best is None or idx < best[0]:
                best = (idx, text[idx : idx + len(needle)])
            break
    return best


def _is_negated(lowered: str, start: int, end: int) -> bool:
    """True if a negation word sits within a short window around the match."""
    clause_start = max(
        lowered.rfind(".", 0, start), lowered.rfind(",", 0, start), lowered.rfind("।", 0, start)
    )
    before = lowered[max(clause_start + 1, start - 28) : start]
    clause_end = min(
        (i for i in (lowered.find(".", end), lowered.find(",", end), lowered.find("।", end)) if i != -1),
        default=len(lowered),
    )
    after = lowered[end : min(clause_end, end + 18)]
    return bool(_NEGATION.search(before) or _NEGATION.search(after))


def _clean_place(raw: str) -> str:
    cut = _STOP_AT.search(raw + " ")
    phrase = raw[: cut.start()] if cut else raw
    phrase = re.sub(r"\s+", " ", phrase).strip(" -'\"")
    words = phrase.split(" ")
    return " ".join(words[:6])


def _location_mentions(text: str) -> list[LocationMention]:
    mentions: list[LocationMention] = []
    seen: set[str] = set()

    def add(phrase: str, relation: Optional[str], matched: str) -> None:
        phrase = phrase.strip()
        key = phrase.lower()
        if len(phrase) < 3 or key in seen or key in _GENERIC_PLACES:
            return
        # "at"/"in" are too common to trust unless the phrase names a kind of place.
        if relation == "at" and not _PLACE_HINT.search(phrase):
            return
        seen.add(key)
        mentions.append(LocationMention(phrase=phrase, relation=relation, matched_text=matched.strip()))

    for relation, pattern in _PRE_RELATIONS:
        for match in re.finditer(rf"(?<!\w)(?:{pattern})\s+([^\n]{{3,80}})", text, re.IGNORECASE):
            add(_clean_place(match.group(1)), relation, match.group(0)[:100])

    for relation, pattern in _POST_RELATIONS:
        for match in re.finditer(rf"([^\n,.;।]{{3,60}}?)\s*(?:{pattern})", text, re.IGNORECASE):
            words = match.group(1).strip().split(" ")[-4:]
            while words and words[0].lower() in _FILLER_WORDS:
                words = words[1:]
            add(" ".join(words), relation, match.group(0)[:100])

    return mentions


def extract(text: str) -> RuleExtraction:
    result = RuleExtraction()
    if not text or not text.strip():
        return result
    lowered = text.lower()

    def assert_true(attribute: str, terms: tuple[str, ...]) -> None:
        hit = _find(text, lowered, terms)
        if hit:
            result.findings.append(Finding(attribute, True, hit[1]))

    assert_true("trapped_status", TRAPPED)
    assert_true("medical_emergency", MEDICAL)

    critical = _find(text, lowered, LIFE_THREATENING)
    if critical:
        result.findings.append(Finding("life_threatening_medical", True, critical[1]))

    for group, terms in VULNERABLE.items():
        hit = _find(text, lowered, terms)
        if hit:
            result.findings.append(Finding("vulnerable_persons", group, hit[1]))

    rising = _find(text, lowered, WATER_RISING)
    falling = _find(text, lowered, WATER_FALLING)
    if rising:
        result.findings.append(Finding("water_level_trend", "rising", rising[1]))
    elif falling:
        result.findings.append(Finding("water_level_trend", "falling", falling[1]))

    entered = _find(text, lowered, WATER_ENTERED_HOME)
    if entered:
        result.findings.append(Finding("water_entering_occupied_floor", True, entered[1]))

    for floor, terms in FLOOR.items():
        hit = _find(text, lowered, terms)
        if hit:
            result.findings.append(Finding("current_floor", floor, hit[1]))
            break

    depth = _DEPTH_UNITS.search(text)
    if depth and _depth_context(lowered, depth.start()):
        factor = _DEPTH_FACTORS.get(depth.group(2).lower(), _DEPTH_FACTORS.get(depth.group(2)))
        if factor is None and depth.group(2).lower().startswith("centim"):
            factor = 1.0
        if factor is not None:
            result.findings.append(
                Finding("water_depth_cm", round(float(depth.group(1)) * factor, 1), depth.group(0))
            )
    else:
        for terms, centimetres in _BODY_DEPTH:
            hit = _find(text, lowered, terms)
            if hit:
                result.findings.append(
                    Finding(
                        "water_depth_cm",
                        centimetres,
                        hit[1],
                        note="approximate; converted from a body-height description",
                    )
                )
                break

    count = _people_count(text)
    if count:
        result.findings.append(Finding("people_count", count[0], count[1]))

    for hazard, terms in HAZARDS.items():
        hit = _find(text, lowered, terms)
        if hit:
            result.findings.append(Finding("hazard", hazard, hit[1]))

    for need, terms in NEEDS.items():
        hit = _find(text, lowered, terms)
        if hit:
            result.findings.append(Finding("relief_need", need, hit[1]))

    for category, terms in CATEGORY_TERMS:
        hit = _find(text, lowered, terms)
        if hit:
            result.category, result.category_matched_text = category, hit[1]
            break

    result.location_mentions = _location_mentions(text)
    return result


def _depth_context(lowered: str, index: int) -> bool:
    """A measurement counts as water depth only if water is mentioned nearby."""
    window = lowered[max(0, index - 60) : index + 40]
    return any(
        w in window
        for w in ("water", "flood", "deep", "पानी", "paani", "pani", "വെള്ളം", "vellam", "उदक", "udok")
    )


def _people_count(text: str) -> Optional[tuple[int, str]]:
    for pattern in (_PEOPLE_DIGITS, _WE_ARE):
        match = pattern.search(text)
        if match:
            digits = next(g for g in match.groups() if g)
            value = int(digits)
            if 0 < value <= 5000:
                return value, match.group(0)
    match = _PEOPLE_WORDS.search(text)
    if match:
        word = match.group(1).lower()
        value = _NUMBER_WORDS.get(word) or _NUMBER_WORDS.get(match.group(1))
        if value:
            return value, match.group(0)
    return None
