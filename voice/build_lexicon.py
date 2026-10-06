"""Turn the shipped pinyin.raw into a lexicon this checkpoint can actually read.

The model does not tokenize a syllable whole. Its vocabulary holds toned finals
("ong4", "in1", "e5") and bare letters, so 重 is `z h ong4`, not `zhong4`. Feed
it whole syllables and every Chinese character is dropped as out-of-vocabulary,
which is silent: the text becomes empty, the duration predictor extrapolates
from nothing, and generation returns a fraction of a second of noise.

pinyin.raw also carries a log probability in column two, which the lexicon
loader reads as a phoneme and rejects one warning at a time -- tens of thousands
of them. It is dropped here.

The split is derived from tokens.txt rather than a hand-written pinyin table, so
it stays correct if the vocabulary changes: take the longest suffix that is a
real token, and emit whatever letters precede it one at a time.
"""

import os
import sys


def load_tokens(path):
    tokens = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            symbol = line.split("\t")[0]
            if symbol:
                tokens.add(symbol)
    return tokens


def split_syllable(syllable, tokens):
    """`zhong4` -> ['z', 'h', 'ong4'], or None if it cannot be spelled."""
    for cut in range(len(syllable)):
        head, tail = syllable[:cut], syllable[cut:]
        if tail in tokens and all(c in tokens for c in head):
            return list(head) + [tail]
    return None


def main():
    model_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    tokens = load_tokens(os.path.join(model_dir, "tokens.txt"))
    source = os.path.join(model_dir, "pinyin.raw")
    target = os.path.join(model_dir, "lexicon.txt")

    written = skipped = 0
    with open(source, encoding="utf-8") as src, \
            open(target, "w", encoding="utf-8") as dst:
        for line in src:
            fields = line.split()
            if len(fields) < 3:
                continue
            word, syllables = fields[0], fields[2:]  # column 2 is a log prob

            phonemes = []
            for syllable in syllables:
                pieces = split_syllable(syllable, tokens)
                if pieces is None:
                    phonemes = None
                    break
                phonemes.extend(pieces)

            if phonemes is None:
                skipped += 1
                continue
            dst.write(word + " " + " ".join(phonemes) + "\n")
            written += 1

    print(f"wrote {target}: {written} entries, {skipped} unspellable")
    return 0


if __name__ == "__main__":
    sys.exit(main())
