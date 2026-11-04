"""Generate fake values for every anonymize strategy."""

from __future__ import annotations

import calendar
import itertools
import random
import re
from typing import Iterator

from .errors import DumpFormatError
from .profile import Rule

_LOWER = "abcdefghijklmnopqrstuvwxyz"
_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_DIGITS = "0123456789"
_ID_ALPHABET = _LOWER + _DIGITS
_HEX = "0123456789abcdefABCDEF"
_HEX_LOWER = _DIGITS + "abcdef"
_BCRYPT = "./" + _UPPER + _LOWER + _DIGITS
_BASE64 = _UPPER + _LOWER + _DIGITS + "+/"

_DATE_PREFIX = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_TEXT_MAX = 200
_REROLLS = 20
_MAX_GROWTH = 64

_GROWABLE = frozenset({"name", "text", "email", "phone", "digits", "id", "password"})


class Faker:
    """Produce fake values that fit the profile's strategies and column widths."""

    def __init__(
        self, rng: random.Random | None = None, email_tld: str = "invalid"
    ) -> None:
        self.rng = rng if rng is not None else random.Random()
        self.email_tld = email_tld
        self._used: dict[str, set[str]] = {}

    def fake(
        self,
        rule: Rule,
        original: str,
        *,
        key: str,
        max_len: int | None = None,
    ) -> str | None:
        """Return a replacement for ``original``; ``None`` means SQL NULL.

        ``original`` is never NULL or empty (the caller guarantees that) and
        ``key`` ("table.column") namespaces the in-memory unique-value sets.
        """
        strategy = rule.strategy
        if strategy == "null":
            return None
        if strategy == "empty":
            return ""

        if not rule.unique:
            return self._fit(self._generate(strategy, original, 0), max_len, strategy)

        used = self._used.setdefault(key, set())
        value = self._unique(strategy, original, key, used, max_len)
        used.add(value)
        return value

    # -- generation ---------------------------------------------------------

    def _generate(self, strategy: str, original: str, extra: int) -> str:
        if strategy == "name":
            return self._name(extra)
        if strategy == "text":
            return self._text(original, extra)
        if strategy == "email":
            return self._email(extra)
        if strategy == "phone":
            return "0" + self._digit_string(9 + extra)
        if strategy == "digits":
            return self._same_length(original, extra, self._digit_string)
        if strategy == "id":
            return self._same_length(
                original, extra, lambda n: self._pick(_ID_ALPHABET, n)
            )
        if strategy == "date":
            return self._date(original)
        if strategy == "ip":
            return f"192.0.2.{self.rng.randint(1, 254)}"
        if strategy == "json":
            return "[]" if original.lstrip().startswith("[") else "{}"
        if strategy == "password":
            return self._password(original, extra)
        raise DumpFormatError(f"unknown strategy {strategy!r}")

    def _pick(self, alphabet: str, length: int) -> str:
        return "".join(self.rng.choice(alphabet) for _ in range(length))

    def _digit_string(self, length: int) -> str:
        return self._pick(_DIGITS, length)

    def _same_length(self, original: str, extra: int, build) -> str:
        length = len(original) + extra
        value = build(length)
        if length != len(original):
            return value
        for _ in range(5):
            if value != original:
                break
            value = build(length)
        return value

    def _name(self, extra: int) -> str:
        words = [
            self.rng.choice(_UPPER) + self._pick(_LOWER, self.rng.randint(2, 9))
            for _ in range(self.rng.randint(1, 3))
        ]
        if extra:
            words[-1] += self._pick(_LOWER, extra)
        return " ".join(words)

    def _text(self, original: str, extra: int) -> str:
        target = min(len(original), _TEXT_MAX) + extra
        words: list[str] = []
        length = 0
        while length < target:
            word = self._pick(_LOWER, self.rng.randint(2, 8))
            words.append(word)
            length += len(word) + (1 if len(words) > 1 else 0)
        return " ".join(words)

    def _email(self, extra: int) -> str:
        local = self._pick(_LOWER, self.rng.randint(6, 12) + extra)
        domain = self._pick(_LOWER, self.rng.randint(4, 10))
        return f"{local}@{domain}.{self.email_tld}"

    def _date(self, original: str) -> str:
        match = _DATE_PREFIX.match(original)
        if match:
            year, month, day = match.groups()
            if (year, month, day) == ("0000", "00", "00"):
                return original
            rest = original[match.end() :]
        else:
            rest = ""
        fake_year = self.rng.randint(1950, 2005)
        fake_month = self.rng.randint(1, 12)
        fake_day = self.rng.randint(1, calendar.monthrange(fake_year, fake_month)[1])
        return f"{fake_year:04d}-{fake_month:02d}-{fake_day:02d}{rest}"

    def _password(self, original: str, extra: int) -> str:
        cut = original.rfind("$")
        if cut >= 0:
            prefix, rest = original[: cut + 1], original[cut + 1 :]
        else:
            prefix, rest = "", original

        length = len(rest) + extra
        if length == 0:
            return prefix

        alphabet = self._password_alphabet(rest)
        body = self._pick(alphabet, length)
        for _ in range(5):
            if body != rest:
                break
            body = self._pick(alphabet, length)
        return prefix + body

    @staticmethod
    def _password_alphabet(rest: str) -> str:
        if rest and all(char in _HEX for char in rest):
            return _HEX_LOWER
        if rest and all(char in _BCRYPT for char in rest):
            return _BCRYPT
        return _BASE64

    # -- width fitting ------------------------------------------------------

    def _fit(self, value: str | None, max_len: int | None, strategy: str) -> str | None:
        if value is None or max_len is None or len(value) <= max_len:
            return value
        if strategy == "email":
            return self._fit_email(value, max_len)
        return value[:max_len]

    def _fit_email(self, value: str, max_len: int) -> str:
        local, _, domain = value.partition("@")
        suffix = "." + self.email_tld
        if domain.endswith(suffix):
            domain = domain[: -len(suffix)]
        else:
            suffix = ""
        budget = max_len - len(suffix) - 1
        if budget < 2:
            return value[:max_len]
        domain_len = max(1, min(len(domain), budget - 1))
        local_len = budget - domain_len
        return local[:local_len] + "@" + domain[:domain_len] + suffix

    # -- uniqueness ---------------------------------------------------------

    def _unique(
        self,
        strategy: str,
        original: str,
        key: str,
        used: set[str],
        max_len: int | None,
    ) -> str:
        extra = 0
        while True:
            for _ in range(_REROLLS):
                value = self._fit(
                    self._generate(strategy, original, extra), max_len, strategy
                )
                if value not in used:
                    return value

            if strategy not in _GROWABLE or extra >= _MAX_GROWTH:
                value = self._enumerate_unused(
                    strategy, original, used, max_len, extra
                )
                if value is not None:
                    return value
                raise DumpFormatError(
                    f"cannot generate a unique value for {key!r}: out of space"
                )

            if (
                max_len is not None
                and self._nominal_length(strategy, original, extra + 1) > max_len
            ):
                value = self._enumerate_unused(
                    strategy, original, used, max_len, extra
                )
                if value is not None:
                    return value
                raise DumpFormatError(
                    f"cannot generate a unique value for {key!r}: out of space"
                )

            extra += 1

    def _nominal_length(self, strategy: str, original: str, extra: int) -> int:
        if strategy in ("digits", "id"):
            return len(original) + extra
        if strategy == "phone":
            return 10 + extra
        if strategy == "password":
            return len(original) + extra
        if strategy == "email":
            return 12 + len(self.email_tld) + extra
        if strategy == "name":
            return 3 + extra
        if strategy == "text":
            return min(len(original), _TEXT_MAX) + extra
        return 0

    def _enumerate_unused(
        self,
        strategy: str,
        original: str,
        used: set[str],
        max_len: int | None,
        extra: int,
    ) -> str | None:
        candidates = self._enumerate(strategy, original, max_len, extra)
        if candidates is None:
            return None
        free: list[str] = []
        for candidate in candidates:
            value = self._fit(candidate, max_len, strategy)
            if value not in used:
                free.append(value)
        if not free:
            return None
        return self.rng.choice(free)

    def _enumerate(
        self, strategy: str, original: str, max_len: int | None, extra: int
    ) -> Iterator[str] | None:
        if strategy == "digits":
            length = len(original) + extra
            if max_len is not None:
                length = min(length, max_len)
            if length < 1 or length > 4:
                return None
            return (str(number).zfill(length) for number in range(10**length))
        if strategy == "id":
            length = len(original) + extra
            if max_len is not None:
                length = min(length, max_len)
            if length < 1 or length > 3:
                return None
            return (
                "".join(chars)
                for chars in itertools.product(_ID_ALPHABET, repeat=length)
            )
        if strategy == "ip":
            return (f"192.0.2.{number}" for number in range(1, 255))
        return None
