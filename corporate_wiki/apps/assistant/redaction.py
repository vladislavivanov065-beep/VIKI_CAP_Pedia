"""Best-effort anonymization of an article's text before it's sent to
OpenAI (see apps.assistant.services and apps.assistant.chunking_remote) --
card BINs, tariffs/limits, links, addresses and country names are the
kind of operational detail that shouldn't end up sitting in a third
party's request logs just because an admin asked a question or the local
AI needed help finding sentence boundaries.

redact() replaces every match with an *indexed* placeholder
("[XXX1]", "[XXX2]", ...), not a single repeated "XXX" -- restore() needs
each placeholder in a response to map back to a specific original value
unambiguously, including when a response mentions more than one of them.
The mapping only ever lives in memory for the duration of one request;
nothing is persisted.

This is pattern/dictionary matching, not a real NER model -- it catches
the shapes of data this project's articles actually contain (see the
tests), not every conceivable way to write a phone number or address.
Redacting something it doesn't need to, in doubt, is unfortunately not
possible to fully rule out, but it fails toward *over*-redaction (a
merchant name that happens to look like a country, a version-looking
string) rather than under it: nothing stops it from also being wrong the
other way on text shapes nobody has tested it against, so this is a
mitigation, not a guarantee -- don't paste something you can't afford to
leak and rely on this alone.

Deliberately NOT redacted: ordinary merchant/brand names ("Apple Pay",
"Uber", "Amazon"). They're public, and an article about which merchants
are supported becomes useless if they all turn into "[XXX7]". A vendor
name that's actually confidential (e.g. an infrastructure partner, not a
supported merchant) won't be caught by any pattern here -- add it to
LOCAL_AI_REDACTED_TERMS (settings) for an exact-match redaction instead.
"""

from __future__ import annotations

import dataclasses
import re

from django.conf import settings

# Card BIN / product / MCC-code-shaped digit runs, and anything else that's
# just a long number (limits, post codes) -- deliberately broad ("прятать
# все цифры"): a bare 1-3 digit number (list markers, small counts) is left
# alone, everything else numeric is treated as potentially sensitive.
_LONG_NUMBER_RE = re.compile(r"\b\d{4,}(?:[,.]\d+)*\b")
_THOUSANDS_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b")
# The $ can come before ("$0.25") or after ("20$", common in casual/RU
# usage) the amount.
_MONEY_RE = re.compile(r"\$\s?\d+(?:[.,]\d+)*|\d+(?:[.,]\d+)*\s?\$")
_PERCENT_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s?%")
# Alphanumeric product/BIN codes ("E0000000", "C0000017", "E0W00009").
_CODE_RE = re.compile(r"\b[A-Za-z]{1,3}\d[\dA-Za-z]{4,}\b")
_URL_RE = re.compile(r"https?://\S+")
# A line introduced by an explicit "Address:"/"Адрес:"/"Post code:" label --
# free-form addresses with no such label won't be caught (see module
# docstring: this is pattern matching, not NER).
_ADDRESS_LINE_RE = re.compile(r"^[ \t]*(address|адрес|post code|индекс)[ \t]*:.*$")

_PATTERN_PARTS = [
    _URL_RE.pattern,
    _ADDRESS_LINE_RE.pattern,
    _MONEY_RE.pattern,
    _THOUSANDS_RE.pattern,
    _PERCENT_RE.pattern,
    _CODE_RE.pattern,
    _LONG_NUMBER_RE.pattern,
]


def _custom_terms() -> list[str]:
    raw = getattr(settings, "LOCAL_AI_REDACTED_TERMS", "")
    return [term.strip() for term in raw.split(",") if term.strip()]


def _build_pattern() -> re.Pattern[str]:
    parts = list(_PATTERN_PARTS)
    custom = sorted(_custom_terms(), key=len, reverse=True)
    if custom:
        parts.append(r"\b(?:" + "|".join(re.escape(term) for term in custom) + r")\b")
    countries = sorted(_COUNTRY_NAMES, key=len, reverse=True)
    parts.append(r"\b(?:" + "|".join(re.escape(name) for name in countries) + r")\b")
    return re.compile("|".join(f"(?:{part})" for part in parts), re.IGNORECASE | re.MULTILINE)


@dataclasses.dataclass
class Redaction:
    text: str
    tokens: list[str]


def redact(text: str) -> Redaction:
    """Replaces every sensitive-looking span with an indexed placeholder,
    in the order they appear. tokens[i] is the original text that
    "[XXX{i+1}]" stands in for -- pass both to restore() afterwards.
    """
    tokens: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"[XXX{len(tokens)}]"

    redacted_text = _build_pattern().sub(_replace, text)
    return Redaction(text=redacted_text, tokens=tokens)


_PLACEHOLDER_RE = re.compile(r"\[XXX(\d+)\]")


def restore(text: str, tokens: list[str]) -> str:
    """Inverse of redact(): replaces every "[XXX{i}]" placeholder still
    present in `text` with tokens[i-1]. A placeholder with no matching
    token (out of range -- shouldn't happen with a response derived from
    redact()'s own output, but this is talking to an external API) is left
    as-is rather than raising, so a malformed response degrades to a
    visible "[XXX7]" instead of a crash.
    """

    def _replace(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        if 0 <= index < len(tokens):
            return tokens[index]
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, text)


_COUNTRY_NAMES = {
    # English + Russian names, plus a few common abbreviations/territories
    # that show up in card-BIN/geo contexts even though they aren't UN
    # member states (Hong Kong, Macau, Taiwan).
    "Afghanistan",
    "Афганистан",
    "Albania",
    "Албания",
    "Algeria",
    "Алжир",
    "Andorra",
    "Андорра",
    "Angola",
    "Ангола",
    "Argentina",
    "Аргентина",
    "Armenia",
    "Армения",
    "Australia",
    "Австралия",
    "Austria",
    "Австрия",
    "Azerbaijan",
    "Азербайджан",
    "Bahamas",
    "Багамы",
    "Багамские острова",
    "Bahrain",
    "Бахрейн",
    "Bangladesh",
    "Бангладеш",
    "Barbados",
    "Барбадос",
    "Belarus",
    "Беларусь",
    "Белоруссия",
    "Belgium",
    "Бельгия",
    "Belize",
    "Белиз",
    "Benin",
    "Бенин",
    "Bhutan",
    "Бутан",
    "Bolivia",
    "Боливия",
    "Bosnia and Herzegovina",
    "Босния и Герцеговина",
    "Botswana",
    "Ботсвана",
    "Brazil",
    "Бразилия",
    "Brunei",
    "Бруней",
    "Bulgaria",
    "Болгария",
    "Burkina Faso",
    "Буркина-Фасо",
    "Burundi",
    "Бурунди",
    "Cambodia",
    "Камбоджа",
    "Cameroon",
    "Камерун",
    "Canada",
    "Канада",
    "Cape Verde",
    "Кабо-Верде",
    "Central African Republic",
    "Центральноафриканская Республика",
    "Chad",
    "Чад",
    "Chile",
    "Чили",
    "China",
    "Китай",
    "Colombia",
    "Колумбия",
    "Comoros",
    "Коморы",
    "Congo",
    "Конго",
    "Costa Rica",
    "Коста-Рика",
    "Croatia",
    "Хорватия",
    "Cuba",
    "Куба",
    "Cyprus",
    "Кипр",
    "Czech Republic",
    "Czechia",
    "Чехия",
    "Democratic Republic of the Congo",
    "Демократическая Республика Конго",
    "Denmark",
    "Дания",
    "Djibouti",
    "Джибути",
    "Dominica",
    "Доминика",
    "Dominican Republic",
    "Доминиканская Республика",
    "Ecuador",
    "Эквадор",
    "Egypt",
    "Египет",
    "El Salvador",
    "Сальвадор",
    "Equatorial Guinea",
    "Экваториальная Гвинея",
    "Eritrea",
    "Эритрея",
    "Estonia",
    "Эстония",
    "Eswatini",
    "Свазиленд",
    "Эсватини",
    "Ethiopia",
    "Эфиопия",
    "Fiji",
    "Фиджи",
    "Finland",
    "Финляндия",
    "France",
    "Франция",
    "Gabon",
    "Габон",
    "Gambia",
    "Гамбия",
    "Georgia",
    "Грузия",
    "Germany",
    "Германия",
    "Ghana",
    "Гана",
    "Greece",
    "Греция",
    "Grenada",
    "Гренада",
    "Guatemala",
    "Гватемала",
    "Guinea",
    "Гвинея",
    "Guinea-Bissau",
    "Гвинея-Бисау",
    "Guyana",
    "Гайана",
    "Haiti",
    "Гаити",
    "Honduras",
    "Гондурас",
    "Hong Kong",
    "HK",
    "Гонконг",
    "Hungary",
    "Венгрия",
    "Iceland",
    "Исландия",
    "India",
    "Индия",
    "Indonesia",
    "Индонезия",
    "Iran",
    "Иран",
    "Iraq",
    "Ирак",
    "Ireland",
    "Ирландия",
    "Israel",
    "Израиль",
    "Italy",
    "Италия",
    "Ivory Coast",
    "Côte d'Ivoire",
    "Кот-д’Ивуар",
    "Кот-д'Ивуар",
    "Jamaica",
    "Ямайка",
    "Japan",
    "Япония",
    "Jordan",
    "Иордания",
    "Kazakhstan",
    "Казахстан",
    "Kenya",
    "Кения",
    "Kiribati",
    "Кирибати",
    "Kosovo",
    "Косово",
    "Kuwait",
    "Кувейт",
    "Kyrgyzstan",
    "Киргизия",
    "Кыргызстан",
    "Laos",
    "Лаос",
    "Latvia",
    "Латвия",
    "Lebanon",
    "Ливан",
    "Lesotho",
    "Лесото",
    "Liberia",
    "Либерия",
    "Libya",
    "Ливия",
    "Liechtenstein",
    "Лихтенштейн",
    "Lithuania",
    "Литва",
    "Luxembourg",
    "Люксембург",
    "Macau",
    "Macao",
    "Макао",
    "Madagascar",
    "Мадагаскар",
    "Malawi",
    "Малави",
    "Malaysia",
    "Малайзия",
    "Maldives",
    "Мальдивы",
    "Mali",
    "Мали",
    "Malta",
    "Мальта",
    "Mauritania",
    "Мавритания",
    "Mauritius",
    "Маврикий",
    "Mexico",
    "Мексика",
    "Moldova",
    "Молдова",
    "Monaco",
    "Монако",
    "Mongolia",
    "Монголия",
    "Montenegro",
    "Черногория",
    "Morocco",
    "Марокко",
    "Mozambique",
    "Мозамбик",
    "Myanmar",
    "Мьянма",
    "Namibia",
    "Намибия",
    "Nauru",
    "Науру",
    "Nepal",
    "Непал",
    "Netherlands",
    "Нидерланды",
    "New Zealand",
    "Новая Зеландия",
    "Nicaragua",
    "Никарагуа",
    "Niger",
    "Нигер",
    "Nigeria",
    "Нигерия",
    "North Korea",
    "Северная Корея",
    "North Macedonia",
    "Северная Македония",
    "Norway",
    "Норвегия",
    "Oman",
    "Оман",
    "Pakistan",
    "Пакистан",
    "Palau",
    "Палау",
    "Palestine",
    "Палестина",
    "Panama",
    "Панама",
    "Papua New Guinea",
    "Папуа — Новая Гвинея",
    "Paraguay",
    "Парагвай",
    "Peru",
    "Перу",
    "Philippines",
    "Филиппины",
    "Poland",
    "Польша",
    "Portugal",
    "Португалия",
    "Qatar",
    "Катар",
    "Romania",
    "Румыния",
    "Russia",
    "Russian Federation",
    "Россия",
    "Российская Федерация",
    "Rwanda",
    "Руанда",
    "Saint Lucia",
    "Сент-Люсия",
    "Samoa",
    "Самоа",
    "San Marino",
    "Сан-Марино",
    "Saudi Arabia",
    "Саудовская Аравия",
    "Senegal",
    "Сенегал",
    "Serbia",
    "Сербия",
    "Seychelles",
    "Сейшелы",
    "Sierra Leone",
    "Сьерра-Леоне",
    "Singapore",
    "SG",
    "Сингапур",
    "Slovakia",
    "Словакия",
    "Slovenia",
    "Словения",
    "Solomon Islands",
    "Соломоновы Острова",
    "Somalia",
    "Сомали",
    "South Africa",
    "Южно-Африканская Республика",
    "ЮАР",
    "South Korea",
    "Южная Корея",
    "South Sudan",
    "Южный Судан",
    "Spain",
    "Испания",
    "Sri Lanka",
    "Шри-Ланка",
    "Sudan",
    "Судан",
    "Suriname",
    "Суринам",
    "Sweden",
    "Швеция",
    "Switzerland",
    "Швейцария",
    "Syria",
    "Сирия",
    "Taiwan",
    "Тайвань",
    "Tajikistan",
    "Таджикистан",
    "Tanzania",
    "Танзания",
    "Thailand",
    "Таиланд",
    "Timor-Leste",
    "Восточный Тимор",
    "Togo",
    "Того",
    "Tonga",
    "Тонга",
    "Trinidad and Tobago",
    "Тринидад и Тобаго",
    "Tunisia",
    "Тунис",
    "Turkey",
    "Türkiye",
    "Турция",
    "Turkmenistan",
    "Туркменистан",
    "Tuvalu",
    "Тувалу",
    "Uganda",
    "Уганда",
    "Ukraine",
    "Украина",
    "United Arab Emirates",
    "UAE",
    "Объединённые Арабские Эмираты",
    "ОАЭ",
    "United Kingdom",
    "UK",
    "Великобритания",
    "United States",
    "United States of America",
    "USA",
    "US",
    "США",
    "Соединённые Штаты Америки",
    "Uruguay",
    "Уругвай",
    "Uzbekistan",
    "Узбекистан",
    "Vanuatu",
    "Вануату",
    "Vatican",
    "Ватикан",
    "Venezuela",
    "Венесуэла",
    "Vietnam",
    "Вьетнам",
    "Yemen",
    "Йемен",
    "Zambia",
    "Замбия",
    "Zimbabwe",
    "Зимбабве",
}
