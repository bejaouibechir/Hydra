# -*- coding: utf-8 -*-
"""
tests/test_dsl_version_check.py — Lecture tolerante du champ `version`.

Le contrat, issu de la Regle 3.2 : le moteur LIT la version du format, AVERTIT
quand elle differe, et n'ECHOUE JAMAIS. Refuser un manifeste serait une rupture
au sens SemVer, reservee a une version MAJEURE.

Ces tests fixent ce contrat pour qu'il ne derive pas : ni vers le silence
d'avant, ni vers un refus premature.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from hydra_etl import DSL_VERSION
from hydra_etl.internal.dsl_version import check_dsl_version, parse_version


class TestParseVersion:
    @pytest.mark.parametrize(
        "raw,expected",
        [("1.0", (1, 0)), ("2.10.3", (2, 10, 3)), (" 1.0 ", (1, 0)), (1.0, (1, 0))],
    )
    def test_reads_a_number(self, raw, expected):
        assert parse_version(raw) == expected

    @pytest.mark.parametrize("raw", ["abc", "", "  ", None, "1.x"])
    def test_returns_none_when_not_a_number(self, raw):
        assert parse_version(raw) is None


class TestSilentCases:
    def test_current_version_says_nothing(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert check_dsl_version({"version": DSL_VERSION}, "sources.yaml") == DSL_VERSION
        assert caplog.records == []

    def test_missing_field_says_nothing(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert check_dsl_version({"sources": {}}, "sources.yaml") is None
        assert caplog.records == []

    def test_non_mapping_is_ignored(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert check_dsl_version(["not", "a", "mapping"], "x.yaml") is None
        assert caplog.records == []


class TestWarningCases:
    def test_older_version_warns_without_failing(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = check_dsl_version({"version": "0.9"}, "sources.yaml")
        assert result == "0.9"
        assert len(caplog.records) == 1
        assert "older" in caplog.text

    def test_newer_version_warns_without_failing(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = check_dsl_version({"version": "2.0"}, "workflow.yaml")
        assert result == "2.0"
        assert "newer" in caplog.text

    def test_unreadable_version_warns_without_failing(self, caplog):
        with caplog.at_level(logging.WARNING):
            result = check_dsl_version({"version": "abc"}, "pipeline.yaml")
        assert result == "abc"
        assert "Unrecognized" in caplog.text

    def test_the_file_name_appears_in_the_message(self, caplog):
        with caplog.at_level(logging.WARNING):
            check_dsl_version({"version": "3.1"}, "destinations.yaml")
        assert "destinations.yaml" in caplog.text

    def test_messages_are_in_english(self, caplog):
        """Regle -2 : ces avertissements atteignent l'utilisateur."""
        with caplog.at_level(logging.WARNING):
            check_dsl_version({"version": "9.9"}, "sources.yaml")
        assert not any(c in caplog.text for c in "àâçéèêëîïôùûü")


class TestNeverRaises:
    @pytest.mark.parametrize(
        "payload",
        [{"version": "0.1"}, {"version": "99.99"}, {"version": ""},
         {"version": None}, {"version": 1.0}, {"version": ["1.0"]}, {}],
    )
    def test_no_payload_raises(self, payload):
        check_dsl_version(payload, "any.yaml")


class TestWiredIntoTheLoaders:
    """Le controle doit etre branche la ou les manifestes sont reellement lus."""

    ROOT = Path(__file__).resolve().parents[1]

    def test_job_executor_calls_it(self):
        src = (self.ROOT / "hydra_etl" / "internal" / "runner" / "executor.py").read_text(
            encoding="utf-8"
        )
        assert "check_dsl_version" in src

    def test_workflow_parser_calls_it(self):
        src = (self.ROOT / "hydra_etl" / "workflow" / "parser.py").read_text(encoding="utf-8")
        assert "check_dsl_version" in src

    def test_a_job_with_an_odd_version_still_runs(self, tmp_path, caplog):
        """Le cas qui compte : l'utilisateur ne doit pas etre bloque."""
        job = tmp_path / "job"
        job.mkdir()
        (tmp_path / "in.csv").write_text("id,amount\n1,10\n", encoding="utf-8")
        (job / "sources.yaml").write_text(
            'version: "42.7"\nsources:\n  s:\n    type: csv\n    extract:\n'
            f'      table: {tmp_path / "in.csv"}\n',
            encoding="utf-8",
        )
        (job / "transformations.yaml").write_text(
            'version: "1.0"\nsteps: []\n', encoding="utf-8"
        )
        (job / "destinations.yaml").write_text(
            'version: "1.0"\ndestinations:\n  d:\n    type: csv\n    load:\n'
            f'      table: {tmp_path / "out.csv"}\n      mode: replace\n',
            encoding="utf-8",
        )
        (job / "pipeline.yaml").write_text(
            'version: "1.0"\npipeline:\n  from: s\n  to: d\n', encoding="utf-8"
        )

        from hydra_etl.internal.runner.executor import JobExecutor

        with caplog.at_level(logging.WARNING):
            result = JobExecutor(job_dir=job, root_dir=tmp_path).run()

        assert result.success, f"le job aurait du s'executer : {result.error}"
        assert (tmp_path / "out.csv").exists()
        assert "42.7" in caplog.text
