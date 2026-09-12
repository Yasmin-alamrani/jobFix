"""Does a piece of text claim anything the CV does not already say?

Tailoring has a model rewrite parts of a real person's CV, and the one outcome
this app cannot allow is a tailored CV that says something the original did not.
The prompt asks for that. This module is what *enforces* it: every proposed edit
is checked here before the user sees it, and a saved version is checked again as
a whole before it is stored. The prompt is the request; this is the guarantee.

What it checks, against the part of the CV an edit changes:

  numbers     any figure, date, percentage or spelled-out quantity ("tripled",
              "hundreds") the source does not contain. Arabic-Indic digits are
              normalised first, so a figure cannot slip past in another script.
  named       a tool, employer, product, credential or acronym -- recognised by
              shape: internal capitals (PostgreSQL), all caps (AWS), code
              punctuation (C++, Node.js, CI/CD), a digit (EC2), or a capital
              letter mid-sentence (Google).
  job terms   a word lifted from the job description that the source does not
              use. This is the fabrication a tailoring model is most drawn to:
              the posting asks for "microservices", so the bullet grows the word.
  claims      leadership verbs -- led, managed, mentored, owned, founded -- that
              the source does not support.
  new nouns   any other new word that is not ordinary phrasing and is not shaped
              like a verb or adverb. Facts live in nouns; "built fintech systems"
              claims fintech whether or not the posting mentioned it. In Arabic,
              where word shape does not separate verbs from nouns, every new word
              outside a short list of common verbs and stopwords counts.

What it cannot see, stated plainly: *meaning*. "Helped build the payouts API"
rewritten as "Built the payouts API" passes, because every word in it is either
already in the source or ordinary phrasing. Inflation of that kind is judged by
the person reading the diff, which is why every edit is shown as one and nothing
is applied until they accept it. This module guarantees that no new *fact* -- a
number, a named thing, a domain term, a leadership claim -- gets in. It does not
pretend to guarantee tone.

**Scope matters.** An edit is checked against the part of the CV it changes,
not the whole CV. "8,000 merchants" appearing under one role does not license
putting it under another -- that attaches a real achievement to the wrong job,
which is fabrication even though every character of it is "in the CV".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# The only text an edit may introduce that the CV does not contain: a slot for
# the user to fill with their own real figure, or delete.
PLACEHOLDER = re.compile(r"\[add [^\[\]\n]{1,40}\]", re.IGNORECASE)

_DIGIT_MAP = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹’‘", "01234567890123456789''"
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# A word, keeping the punctuation that is part of a technical name: C++, C#,
# Node.js, CI/CD, e-commerce. Must end on a word character, + or #, so the full
# stop after "Node.js." is not swallowed.
_TOKEN = re.compile(r"[^\W_](?:[\w+#.\-/']*[\w+#])?")
_PARTS = re.compile(r"[-/.']")
# After one of these (or at the very start), a capital letter is the start of a
# sentence or a bullet, not the sign of a proper noun.
_SENTENCE_BREAK = set("\n.!?:;•·–—-(|\"'")

STOPWORDS = frozenset("""
a an the and or but nor so yet for of in on at to from by with without within
into onto over under about above below across after before during through
throughout between among per via as than then that this these those which who
whom whose what when where while whilst how why its it their they them there
here our we us my i me you your he she his her be is are was were been being am
has have had having do does did doing done not no also both each either neither
all any some many more most much few less least other another such same only
just very too up down out off again further once can could will would shall
should may might must well even ever &
في من على إلى الى عن مع و أو ثم هذا هذه ذلك التي الذي الذين كان كانت تم لقد قد
كل بعض عند حتى بين خلال بعد قبل
""".split())

# Ordinary resume phrasing: verbs, connectives, and generic nouns and
# adjectives. A rewrite may introduce these freely even when the job description
# uses them, because none of them asserts a skill, a tool or a domain.
#
# What is deliberately absent is as important as what is here. No domain terms
# (payments, compliance, security, cloud, data, analytics, microservices), which
# are claims of experience. No leadership verbs (led, managed, owned), which are
# checked separately as claims. Adding a word to this list is a decision that it
# can never be a fabrication in any CV, and should be made that carefully.
PHRASING = STOPWORDS | frozenset("""
achieve achieved achieving accelerate accelerated adapt adapted address
addressed analyse analysed analyze analyzed apply applied assess assessed assist
assisted automate automated build building built collaborate collaborated
collaborating communicate communicated complete completed configure configured
contribute contributed contributing coordinate coordinated create created
creating cut debug debugged define defined deliver delivered delivering deploy
deployed design designed designing develop developed developing document
documented drive drove driven enable enabled enhance enhanced ensure ensured
ensuring establish established evaluate evaluated execute executed expand
expanded facilitate facilitated fix fixed focus focused handle handled help
helped helping identify identified implement implemented implementing improve
improved improving increase increased integrate integrated introduce introduced
investigate investigated launch launched maintain maintained maintaining migrate
migrated minimise minimised minimize minimized modernise modernised modernize
modernized monitor monitored optimise optimised optimize optimized organise
organised organize organized perform performed plan planned prepare prepared
present presented prioritise prioritised prioritize prioritized produce produced
provide provided reduce reduced reducing refactor refactored release released
replace replaced report reported research researched resolve resolved
restructure restructured review reviewed revamp revamped run ran scale scaled
ship shipped simplify simplified solve solved standardise standardised
standardize standardized streamline streamlined strengthen strengthened support
supported supporting test tested translate translated troubleshoot troubleshot
update updated upgrade upgraded use used using work worked working write wrote
written make made making take took taken serve served found find set grew
won sold taught kept held brought began gave met sent spent chose
ability accuracy approach areas availability business capability capabilities
change changes clear clean code codebase complex component components consistent
core critical cross-functional customer customers daily delivery detail detailed
effective effectively efficiency efficient efficiently end-to-end environment
existing experience external feature features faster fast flow functionality goal
goals high impact improvement improvements internal issue issues key large level
maintainable measurable multiple new operational outcome outcomes overall part
performance practices process processes product production products project
projects quality quickly range reliable reliability reporting requests
requirement requirements responsible responsibility result results robust
scalable scalability scope service services significant significantly smooth
solution solutions stable stakeholder stakeholders standard standards strategy
strong successful successfully system systems task tasks team teams technical
time timely tool tools user users various workflow workflows weekly monthly
bug bugs error errors
تطوير تصميم تحسين تنفيذ دعم عمل العمل بناء تحليل إنشاء تسليم ترحيل أتمتة مراجعة
تسريع تبسيط توثيق اختبار صيانة
""".split())

SPELLED_NUMBERS = frozenset("""
two three four five six seven eight nine ten eleven twelve fifteen twenty
thirty forty fifty hundred hundreds thousand thousands million millions billion
billions dozen dozens double doubled doubling triple tripled tripling halved
percent
""".split())

# Leadership claims, as (prefixes, exact words). "led" is exact because as a
# prefix it would catch "ledger"; "found" is absent because "found and fixed a
# bug" is not a claim to have founded anything.
_CLAIMS: dict[str, tuple[tuple[str, ...], frozenset[str]]] = {
    "leadership": (("lead", "قاد", "قياد"), frozenset({"led"})),
    "management": (("manag", "ادار"), frozenset()),
    "mentoring": (("mentor",), frozenset()),
    "supervision": (("supervis", "اشراف", "اشرف"), frozenset()),
    "ownership": ((), frozenset({"owned", "owner", "owners", "owning", "ownership"})),
    "founding": ((), frozenset({"founded", "founder", "co-founded", "cofounded",
                                "co-founder", "cofounder"})),
    "spearheading": (("spearhead",), frozenset()),
    "heading": ((), frozenset({"headed"})),
    "directing": ((), frozenset({"directed"})),
}


_ARABIC = re.compile(r"[\u0600-\u06FF]")
_AR_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})
_AR_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال", "و", "ف", "ب", "ك", "ل")
_AR_SUFFIXES = ("ات", "ون", "ين", "ها", "هم", "ه", "ي")


def _is_arabic(word: str) -> bool:
    return bool(_ARABIC.search(word))


def _ar_norm(word: str) -> str:
    return word.translate(_AR_LETTERS)


def _arabic_stem(word: str) -> str:
    """Strip one common prefix and one common suffix.

    Arabic attaches "and", "the", "for" and plural endings to the word itself,
    so "للمدفوعات" and "المدفوعات" are the same word to a reader and different
    strings to Python. Deliberately light -- a real stemmer would also merge
    words that mean different things, and merging is what lets a fabrication
    pass as "already in the CV".
    """
    w = _ar_norm(word)
    for prefix in _AR_PREFIXES:
        if w.startswith(prefix) and len(w) - len(prefix) >= 3:
            w = w[len(prefix):]
            break
    for suffix in _AR_SUFFIXES:
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[: -len(suffix)]
            break
    return w


# Arabic entries in PHRASING, normalised the same way tokens are before lookup.
_AR_PHRASING = frozenset(_ar_norm(w) for w in PHRASING if _ARABIC.search(w))


@dataclass(frozen=True)
class Finding:
    kind: str       # number | named | job_term | new_term | claim | unsupported
    token: str
    message: str


def normalise(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").translate(_DIGIT_MAP)


def _strip_placeholders(text: str) -> str:
    return PLACEHOLDER.sub(" ", normalise(text))


def numbers(text: str) -> set[str]:
    """Every figure in the text, normalised: "1,200" and "1200" are the same."""
    return {
        m.group(0).replace(",", "").rstrip(".")
        for m in _NUMBER.finditer(_strip_placeholders(text))
    }


def tokens(text: str) -> list[tuple[str, bool]]:
    """(token, at_sentence_start) for every word in the text, placeholders removed."""
    clean = _strip_placeholders(text)
    out = []
    for match in _TOKEN.finditer(clean):
        before = clean[: match.start()].rstrip(" \t")
        out.append((match.group(0), not before or before[-1] in _SENTENCE_BREAK))
    return out


def _base(token: str) -> str:
    return token.lower().removesuffix("'s")


def vocabulary(text: str) -> set[str]:
    """Lower-cased words, plus compound parts and Arabic stems, for presence checks."""
    vocab: set[str] = set()
    for token, _ in tokens(text):
        low = _base(token)
        vocab.add(low)
        vocab.update(part for part in _PARTS.split(low) if part)
        if _is_arabic(low):
            vocab.update({_ar_norm(low), _arabic_stem(low)})
    return vocab


def _variants(low: str):
    yield low
    if low.endswith("y"):
        yield low[:-1] + "ies"
    if low.endswith("ies"):
        yield low[:-3] + "y"
    if low.endswith("es"):
        yield low[:-2]
    if low.endswith("s"):
        yield low[:-1]
    yield low + "s"
    yield low + "es"


def present(low: str, vocab: set[str]) -> bool:
    """Whether a word is in the vocabulary, allowing for plurals and compounds.

    "APIs" is present when the CV says "API"; "cross-functional" is present
    when it says "cross functional". Without this, ordinary inflection would
    read as fabrication and the check would reject honest rewrites.
    """
    if _is_arabic(low):
        return _ar_norm(low) in vocab or _arabic_stem(low) in vocab
    if any(v in vocab for v in _variants(low)):
        return True
    parts = [p for p in _PARTS.split(low) if p]
    return len(parts) > 1 and all(any(v in vocab for v in _variants(p)) for p in parts)


def _is_numeric(token: str) -> bool:
    return all(c.isdigit() or c in ".,-/%" for c in token)


def is_named(token: str, at_sentence_start: bool) -> bool:
    """Whether a token has the shape of a proper name rather than a word."""
    if any(c in "+#/." for c in token):
        return True                     # C++, C#, CI/CD, Node.js
    if any(c.isdigit() for c in token):
        return True                     # EC2, S3, Web3
    if any(c.isupper() for c in token[1:]):
        return True                     # AWS, PostgreSQL, iOS
    return token[0].isupper() and not at_sentence_start   # Google, mid-sentence


def _inflected(low: str) -> bool:
    """A word shaped like a verb or adverb: "engineered", "orchestrating", "rapidly".

    This is the line between phrasing and fact. Facts in a CV live in nouns --
    in "built X", the X is the claim -- while verbs and adverbs describe how.
    So a new word of this shape is read as phrasing, and any other new word as
    a new fact. It is a heuristic over English morphology and says nothing
    about Arabic, which is handled separately.
    """
    return len(low) > 4 and low.endswith(("ed", "ing", "ly"))


_VERB_PREFIXES = ("re-", "co-", "re", "co")


def _is_phrasing(low: str) -> bool:
    """PHRASING, extended to prefixed and compound forms of what is in it.

    "rebuilt" and "rewrote" are irregular, so they are not verb-shaped, and they
    are not in the list -- but "built" and "wrote" are, and the prefix changes
    nothing about whether the word asserts a fact. "reconciliation" does not
    qualify: what is left after "re" is not a phrasing word.
    """
    if low in PHRASING:
        return True
    for prefix in _VERB_PREFIXES:
        rest = low[len(prefix):]
        if low.startswith(prefix) and len(rest) >= 3 and (rest in PHRASING or _inflected(rest)):
            return True
    parts = [p for p in _PARTS.split(low) if p]
    return len(parts) > 1 and all(p in PHRASING or _inflected(p) for p in parts)


def _claim_keys(low: str) -> tuple[str, ...]:
    return (low, _ar_norm(low), _arabic_stem(low)) if _is_arabic(low) else (low,)


def _claim_group(low: str) -> str | None:
    for group, (prefixes, exact) in _CLAIMS.items():
        for key in _claim_keys(low):
            if key in exact or any(key.startswith(p) for p in prefixes):
                return group
    return None


def _claim_supported(group: str, vocab: set[str]) -> bool:
    prefixes, exact = _CLAIMS[group]
    return any(w in exact or any(w.startswith(p) for p in prefixes) for w in vocab)


def _message(kind: str, token: str, elsewhere: bool, where: str) -> str:
    moved = (
        " It does appear elsewhere in your CV, but not here, so putting it here "
        "would attach it to the wrong place."
    )
    if kind == "number":
        return f"Adds the figure {token}, which {where} does not contain." + (
            moved if elsewhere else " Use [add number] and fill in the real one."
        )
    if kind == "named":
        return f"Adds “{token}”, which {where} does not mention." + (
            moved if elsewhere else " It is not in your CV at all."
        )
    if kind == "job_term":
        return (
            f"Brings in “{token}” from the job description; {where} does not "
            "mention it." + (moved if elsewhere else " That makes it a gap, not an edit.")
        )
    if kind == "new_term":
        return f"Adds “{token}”, which {where} does not mention." + (
            moved if elsewhere else " Tailoring can only reword what is already there."
        )
    if kind == "claim":
        return f"“{token}” claims a leadership role that {where} does not describe."
    return f"“{token}” does not appear in {where}."


def introduced(
    text: str,
    *,
    scope: str,
    whole: str | None = None,
    job_terms: set[str] | frozenset[str] = frozenset(),
    where: str = "your CV",
    strict: bool = False,
) -> list[Finding]:
    """Everything `text` asserts that `scope` does not.

    `scope` is the part of the CV being edited; `whole` is the entire CV, used
    only to say whether a flagged item exists elsewhere -- which changes the
    advice, never the verdict. `strict` refuses any non-stopword that is not in
    scope, for short fields like a skill name where "ordinary phrasing" does not
    exist and every word is a claim.
    """
    whole = scope if whole is None else whole
    scope_vocab, whole_vocab = vocabulary(scope), vocabulary(whole)
    scope_numbers, whole_numbers = numbers(scope), numbers(whole)
    job_set = set(job_terms)

    found: list[Finding] = []
    seen: set[tuple[str, str]] = set()

    def flag(kind: str, token: str, elsewhere: bool) -> None:
        key = (kind, token.lower())
        if key not in seen:
            seen.add(key)
            found.append(Finding(kind, token, _message(kind, token, elsewhere, where)))

    for figure in sorted(numbers(text) - scope_numbers):
        flag("number", figure, figure in whole_numbers)

    for token, at_start in tokens(text):
        if _is_numeric(token):
            continue                        # handled as a number above
        low = _base(token)
        if present(low, scope_vocab):
            continue
        elsewhere = present(low, whole_vocab)

        if low in SPELLED_NUMBERS:
            flag("number", token, elsewhere)
            continue
        group = _claim_group(low)
        if group is not None:
            if not _claim_supported(group, scope_vocab):
                flag("claim", token, elsewhere)
            continue
        if is_named(token, at_start):
            flag("named", token, elsewhere)
            continue
        # At the start of a sentence a capital proves nothing, so a word there is
        # read as a name unless it is ordinary phrasing or shaped like a verb.
        # This is what stops "Microsoft built the payouts API" -- and "Rain" from
        # another role opening a bullet here -- passing as plain prose.
        if at_start and token[0].isupper() and not _is_phrasing(low) and not _inflected(low):
            flag("named", token, elsewhere)
            continue
        if strict:
            if low not in STOPWORDS:
                flag("unsupported", token, elsewhere)
            continue

        # Arabic has no reliable verb/noun signal in a word's shape, so a new
        # Arabic word must be ordinary phrasing or it is treated as new content.
        if _is_arabic(low):
            if _ar_norm(low) not in _AR_PHRASING:
                flag("job_term" if present(low, job_set) else "new_term", token, elsewhere)
            continue

        if _is_phrasing(low) or len(low) < 3:
            continue
        if present(low, job_set):
            flag("job_term", token, elsewhere)
            continue
        # A new noun is a new fact: "fintech", "throughput", "the ledger". A new
        # verb or adverb is how the fact is told, and may pass.
        if not _inflected(low):
            flag("new_term", token, elsewhere)

    return found
