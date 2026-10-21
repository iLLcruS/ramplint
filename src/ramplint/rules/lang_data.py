"""Language subtag data for RL604 valid-lang."""

from __future__ import annotations

# ISO 639-1 two-letter language codes, including the deprecated ones that are
# still in the IANA registry (in, iw, ji, jw, mo).
# fmt: off
_TWO_LETTER_CODES = """
aa ab ae af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co
cr cs cu cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl
gn gu gv ha he hi ho hr ht hu hy hz ia id ie ig ii ik in io is it iu iw ja ji
jv jw ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg li ln lo lt lu lv
mg mh mi mk ml mn mo mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or
os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg sh si sk sl sm sn so sq sr
ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo
wa wo xh yi yo za zh zu
"""
# fmt: on
TWO_LETTER_LANGUAGES = frozenset(_TWO_LETTER_CODES.split())

#: Common mistakes: country codes and language names used as language codes.
SUGGESTIONS = {
    # country codes
    "ua": "uk", "gr": "el", "cz": "cs", "jp": "ja", "dk": "da", "cn": "zh",
    "us": "en", "gb": "en",
    "kz": "kk", "by": "be", "rs": "sr", "al": "sq", "ge": "ka",
    "il": "he", "ir": "fa", "vn": "vi", "md": "ro", "at": "de",
    # language names
    "english": "en", "russian": "ru", "ukrainian": "uk", "romanian": "ro",
    "german": "de", "french": "fr", "spanish": "es", "italian": "it",
    "portuguese": "pt", "polish": "pl", "dutch": "nl", "czech": "cs",
    "greek": "el", "turkish": "tr", "chinese": "zh", "japanese": "ja",
    "korean": "ko", "arabic": "ar", "hebrew": "he", "hindi": "hi",
    "bulgarian": "bg", "hungarian": "hu", "swedish": "sv", "danish": "da",
    "norwegian": "nb", "finnish": "fi", "estonian": "et",
}  # fmt: skip
