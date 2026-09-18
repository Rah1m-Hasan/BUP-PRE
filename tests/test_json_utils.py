def test_extract_plain_json():
    from app.utils.json_utils import extract_json

    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    from app.utils.json_utils import extract_json

    text = 'Here you go:\n```json\n{"a": 2}\n```\nDone.'
    assert extract_json(text) == {"a": 2}


def test_extract_json_with_prose():
    from app.utils.json_utils import extract_json

    text = 'Sure! {"interpretations": [{"x": 1}]} thanks.'
    out = extract_json(text)
    assert out == {"interpretations": [{"x": 1}]}


def test_extract_invalid_returns_none():
    from app.utils.json_utils import extract_json

    assert extract_json("nothing here") is None
    assert extract_json("") is None


def test_extract_handles_nested_braces():
    from app.utils.json_utils import extract_json

    text = 'prefix {"a": {"b": 1}, "c": [1,2]} suffix'
    out = extract_json(text)
    assert out == {"a": {"b": 1}, "c": [1, 2]}


def test_extract_strips_think_blocks():
    from app.utils.json_utils import extract_json

    text = (
        "<think>The user wants solar reduction...\nLet me parse...\n</think>\n"
        '{"interpretations": [{"note_index": 0}]}'
    )
    assert extract_json(text) == {"interpretations": [{"note_index": 0}]}


def test_extract_handles_think_then_prose_json():
    from app.utils.json_utils import extract_json

    text = '<think>reasoning here</think>Sure! {"a": 1} thanks.'
    assert extract_json(text) == {"a": 1}


def test_extract_handles_multiline_think():
    from app.utils.json_utils import extract_json

    text = "<think>line1\nline2\nline3</think>" '{"interpretations": [], "ok": true}'
    assert extract_json(text) == {"interpretations": [], "ok": True}


def test_extract_handles_no_think():
    from app.utils.json_utils import extract_json

    assert extract_json('{"x": 1}') == {"x": 1}
