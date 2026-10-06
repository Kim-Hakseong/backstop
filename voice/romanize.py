"""Hangul -> Revised-Romanization, for feeding a Korean prompt transcript to an
English phonemizer.

ZipVoice tokenizes the prompt transcript with espeak-ng (English) plus a Chinese
lexicon. Hangul hits neither: every syllable is dropped as OOV, the prompt token
count collapses to zero, and the duration predictor then asks for a ~5-minute
attention matrix and the process is OOM-killed. Romanizing first keeps the token
count proportional to the prompt audio.

The output is a phonetic approximation, not orthography. Liaison and the common
nasalization rules are applied because they change how a syllable sounds; the
rarer sandhi rules are not. Hand-written romanization always wins over this.
"""

CHO = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "",
       "j", "jj", "ch", "k", "t", "p", "h"]
JUNG = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae",
        "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
JONG = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "p", "l", "l",
        "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t"]

# final consonant -> onset it becomes when the next syllable starts with a vowel
LIAISON = {1: "g", 2: "kk", 3: "ks", 4: "n", 5: "nj", 6: "n", 7: "d", 8: "r",
           9: "lg", 10: "lm", 11: "lb", 12: "ls", 13: "lt", 14: "lp", 15: "r",
           16: "m", 17: "b", 18: "ps", 19: "s", 20: "ss", 22: "j", 23: "ch",
           24: "k", 25: "t", 26: "p", 27: ""}

# obstruent finals assimilate before a nasal onset: 먹는 -> meongneun
NASALIZE = {"k": "ng", "t": "n", "p": "m"}

BASE, LAST = 0xAC00, 0xD7A3


def _decompose(ch):
    code = ord(ch) - BASE
    return code // 588, (code // 28) % 21, code % 28


def romanize(text):
    """Romanize the Hangul in `text`, leaving every other character as-is."""
    out = []
    chars = list(text)
    for i, ch in enumerate(chars):
        if not (BASE <= ord(ch) <= LAST):
            out.append(ch)
            continue

        cho, jung, jong = _decompose(ch)
        syllable = CHO[cho] + JUNG[jung]

        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        nxt_cho = _decompose(nxt)[0] if nxt and BASE <= ord(nxt) <= LAST else None

        if jong == 0:
            out.append(syllable)
        elif nxt_cho == 11 and jong in LIAISON:
            # next syllable starts with the silent ieung: the final slides over
            out.append(syllable)
            chars[i + 1] = nxt  # unchanged; the onset is emitted below
            out.append(LIAISON[jong] + "-")
        else:
            final = JONG[jong]
            if nxt_cho in (2, 6) and final in NASALIZE:  # onset n / m
                final = NASALIZE[final]
            out.append(syllable + final)

    return "".join(out).replace("-", "")


if __name__ == "__main__":
    import sys
    print(romanize(sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read().strip()))
