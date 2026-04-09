from stitch.api.llm_suggestions import parse_llm_suggestion_response


def test_parse_llm_suggestion_response_accepts_code_fenced_json():
    parsed = parse_llm_suggestion_response(
        '```json\n{"name":"basin","value":"Songliao"}\n```',
        requested_field="basin",
    )

    assert parsed.name == "basin"
    assert parsed.value == "Songliao"
