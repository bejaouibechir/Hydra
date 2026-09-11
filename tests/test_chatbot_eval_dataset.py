from scripts.generate_chatbot_eval_dataset import DEFAULT_OUTPUT, _json_text, build_dataset
from scripts.validate_chatbot_eval_dataset import EXPECTED_DISTRIBUTION, validate_dataset


def test_evaluation_dataset_is_synchronised() -> None:
    assert DEFAULT_OUTPUT.read_text(encoding="utf-8") == _json_text(build_dataset())


def test_evaluation_dataset_has_expected_distribution_and_valid_sources() -> None:
    assert validate_dataset() == EXPECTED_DISTRIBUTION


def test_evaluation_dataset_is_not_an_astro_public_asset() -> None:
    dataset = build_dataset()

    assert dataset["publishWithAstro"] is False
    assert dataset["totalCases"] == 100
