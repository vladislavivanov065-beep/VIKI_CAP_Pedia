from apps.assistant import redaction


def test_redact_replaces_urls():
    result = redaction.redact("Ссылка: https://cardspro.com/ru/terms здесь")

    assert "https://cardspro.com/ru/terms" not in result.text
    assert "[XXX1]" in result.text
    assert result.tokens == ["https://cardspro.com/ru/terms"]


def test_redact_replaces_money_with_leading_and_trailing_dollar_sign():
    result = redaction.redact("Issue 20$, fee $0.25 и decline fee 0.5$")

    assert result.tokens == ["20$", "$0.25", "0.5$"]
    assert "20$" not in result.text
    assert "0.25" not in result.text


def test_redact_replaces_percentages():
    result = redaction.redact("Комиссия 1.2%, порог 15%")

    assert result.tokens == ["1.2%", "15%"]


def test_redact_replaces_thousands_separated_limits():
    result = redaction.redact("Лимит: 30,000 в день, 1,000,000 в месяц")

    assert result.tokens == ["30,000", "1,000,000"]


def test_redact_replaces_long_numbers_but_leaves_short_ones():
    result = redaction.redact("BIN 493711, минимум 0, максимум 10, счёт 52489710")

    assert result.tokens == ["493711", "52489710"]
    assert "0" in result.text
    assert "10" in result.text


def test_redact_leaves_list_markers_alone():
    result = redaction.redact("1. Первый пункт\n2. Второй пункт")

    assert result.tokens == []
    assert result.text == "1. Первый пункт\n2. Второй пункт"


def test_redact_replaces_alphanumeric_product_codes():
    result = redaction.redact("Код продукта: E0000037, второй: C0000017")

    assert result.tokens == ["E0000037", "C0000017"]


def test_redact_replaces_address_lines():
    text = "Hong Kong Card\nAddress: Room 11114, 11/F, YF Life Tower\nPost code: 999077"

    result = redaction.redact(text)

    assert "Room 11114" not in result.text
    assert "999077" not in result.text
    assert "[XXX2]" in result.text
    assert "[XXX3]" in result.text


def test_redact_replaces_russian_address_labels():
    result = redaction.redact("Адрес: ул. Ленина, д. 1\nИндекс: 123456")

    assert "Ленина" not in result.text
    assert "123456" not in result.text


def test_redact_replaces_country_names_in_english_and_russian():
    result = redaction.redact("Singapore, Сингапур, Russia, Россия запрещены")

    assert result.tokens == ["Singapore", "Сингапур", "Russia", "Россия"]


def test_redact_replaces_common_region_abbreviations():
    result = redaction.redact("SG | VISA | HK card, MC UK, US gas stations, USA only")

    assert "SG" not in result.text
    assert " HK " not in result.text
    assert "MC UK" not in result.text
    assert "US gas" not in result.text
    assert "USA only" not in result.text


def test_redact_does_not_touch_merchant_or_brand_names():
    text = "Alipay, Amazon, Uber, Apple Pay, Google Pay, Starbucks, McDonald's"

    result = redaction.redact(text)

    assert result.text == text
    assert result.tokens == []


def test_redact_respects_custom_terms_setting(settings):
    settings.LOCAL_AI_REDACTED_TERMS = "CardsPro,Capitalist"

    result = redaction.redact("Работаем через CardsPro и Capitalist.")

    assert "CardsPro" not in result.text
    assert "Capitalist" not in result.text
    assert set(result.tokens) == {"CardsPro", "Capitalist"}


def test_redact_placeholders_are_indexed_in_order_of_appearance():
    result = redaction.redact("493711 потом 537958 потом https://example.com")

    assert result.text == "[XXX1] потом [XXX2] потом [XXX3]"
    assert result.tokens == ["493711", "537958", "https://example.com"]


def test_restore_round_trips_to_the_original_text():
    original = "Лимит 30,000, страна Singapore, ссылка https://cardspro.com/ru/terms"

    result = redaction.redact(original)
    restored = redaction.restore(result.text, result.tokens)

    assert restored == original


def test_restore_only_replaces_placeholders_actually_present():
    result = redaction.redact("493711 и 537958 и 100045")

    # Simulates a ChatGPT response that only echoes some of the tokens.
    partial_response = f"Первое значение: {result.text.split()[0]}"
    restored = redaction.restore(partial_response, result.tokens)

    assert restored == "Первое значение: 493711"


def test_restore_leaves_an_out_of_range_placeholder_untouched():
    restored = redaction.restore("см. [XXX7]", tokens=["only one token"])

    assert restored == "см. [XXX7]"


def test_restore_leaves_text_without_placeholders_unchanged():
    assert redaction.restore("обычный текст без плейсхолдеров", tokens=["x"]) == (
        "обычный текст без плейсхолдеров"
    )
