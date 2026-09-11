import json

from scripts.validate_chatbot_dsl_examples import DEFAULT_CORPUS, validate_corpus


def test_static_chatbot_corpus_is_valid() -> None:
    valid_count, invalid_count = validate_corpus(DEFAULT_CORPUS)

    assert valid_count == 30
    assert invalid_count == 10


def test_static_chatbot_corpus_is_directly_json_importable_by_astro() -> None:
    document = json.loads(DEFAULT_CORPUS.read_text(encoding="utf-8"))

    assert document["runtime"] == "astro-static-github-pages"
    assert len(document["examples"]) == 40
    assert all("question" in example for example in document["examples"])
    assert all("answer" in example for example in document["examples"])
