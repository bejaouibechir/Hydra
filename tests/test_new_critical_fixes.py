"""
Tests couvrant les lacunes critiques identifiées lors de la revue de code :
  1. Signature apply_step() avec context (Liskov)
  2. apply_pipeline() retourne StepResult
  3. CastOp alias (integer, string, boolean)
  4. Parsers destination et transform accessibles (non en backup/)
  5. Edge cases : batch vide, 0 lignes après transform, batch_size=1
  6. Destination parser : LoadMode + validation upsert/key
  7. Transform parser : opérations inconnues, step malformé
"""

from __future__ import annotations

import pytest
import pandas as pd

from internal.engines.pandas_engine import PandasEngine
from internal.transform.engine_interface import StepResult, TransformEngine


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture
def engine():
    return PandasEngine()


@pytest.fixture
def df_simple():
    return pd.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "price": [10.0, 20.0, 30.0]})


# ═══════════════════════════════════════════════════════════════
# 1. SIGNATURE apply_step() — paramètre context (Liskov)
# ═══════════════════════════════════════════════════════════════

class TestApplyStepContext:
    """apply_step() doit accepter context= sans TypeError."""

    def test_apply_step_accepts_context_none(self, engine, df_simple):
        result = engine.apply_step(df_simple, {"select": {"columns": ["id"]}}, context=None)
        assert isinstance(result, StepResult)

    def test_apply_step_accepts_context_dict(self, engine, df_simple):
        result = engine.apply_step(
            df_simple,
            {"select": {"columns": ["id"]}},
            context={"job_id": "test-42", "run": 1},
        )
        assert isinstance(result, StepResult)
        assert list(result.output.columns) == ["id"]

    def test_apply_step_context_does_not_alter_output(self, engine, df_simple):
        """context ne doit pas modifier le résultat."""
        without = engine.apply_step(df_simple, {"select": {"columns": ["id", "name"]}})
        with_ctx = engine.apply_step(
            df_simple, {"select": {"columns": ["id", "name"]}}, context={"x": 99}
        )
        pd.testing.assert_frame_equal(without.output, with_ctx.output)

    def test_interface_signature_matches_implementation(self):
        """PandasEngine respecte le contrat TransformEngine (Liskov)."""
        import inspect
        abs_sig = inspect.signature(TransformEngine.apply_step)
        impl_sig = inspect.signature(PandasEngine.apply_step)
        assert "context" in abs_sig.parameters
        assert "context" in impl_sig.parameters


# ═══════════════════════════════════════════════════════════════
# 2. apply_pipeline() retourne StepResult
# ═══════════════════════════════════════════════════════════════

class TestApplyPipelineReturnsStepResult:

    def test_returns_step_result(self, engine, df_simple):
        result = engine.apply_pipeline(df_simple, [{"select": {"columns": ["id"]}}])
        assert isinstance(result, StepResult)

    def test_output_is_dataframe(self, engine, df_simple):
        result = engine.apply_pipeline(df_simple, [{"select": {"columns": ["id"]}}])
        assert isinstance(result.output, pd.DataFrame)

    def test_stats_contains_steps(self, engine, df_simple):
        result = engine.apply_pipeline(
            df_simple,
            [{"select": {"columns": ["id"]}}, {"rename": {"mapping": {"id": "pk"}}}],
        )
        assert "steps" in result.stats
        assert len(result.stats["steps"]) == 2

    def test_pipeline_accepts_context(self, engine, df_simple):
        result = engine.apply_pipeline(
            df_simple,
            [{"select": {"columns": ["id"]}}],
            context={"job_id": "ctx-test"},
        )
        assert isinstance(result, StepResult)
        assert list(result.output.columns) == ["id"]

    def test_pipeline_interface_signature_matches(self):
        import inspect
        abs_sig = inspect.signature(TransformEngine.apply_pipeline)
        impl_sig = inspect.signature(PandasEngine.apply_pipeline)
        assert "context" in abs_sig.parameters
        assert "context" in impl_sig.parameters


# ═══════════════════════════════════════════════════════════════
# 3. CastOp alias (integer → int, string → str, boolean → bool)
# ═══════════════════════════════════════════════════════════════

class TestCastOpAliases:

    @pytest.fixture
    def parser(self):
        from internal.parser.transform import TransformParser
        return TransformParser()

    def test_alias_integer(self, parser):
        cfg = parser.parse({"steps": [{"cast": {"mapping": {"id": "integer"}}}]})
        assert cfg.steps[0].params.mapping["id"] == "int"

    def test_alias_string(self, parser):
        cfg = parser.parse({"steps": [{"cast": {"mapping": {"name": "string"}}}]})
        assert cfg.steps[0].params.mapping["name"] == "str"

    def test_alias_boolean(self, parser):
        cfg = parser.parse({"steps": [{"cast": {"mapping": {"active": "boolean"}}}]})
        assert cfg.steps[0].params.mapping["active"] == "bool"

    def test_canonical_types_still_work(self, parser):
        cfg = parser.parse({"steps": [{"cast": {"mapping": {"x": "int", "y": "float", "z": "str"}}}]})
        assert cfg.steps[0].params.mapping == {"x": "int", "y": "float", "z": "str"}

    def test_invalid_type_raises(self, parser):
        with pytest.raises(Exception, match="invalide"):
            parser.parse({"steps": [{"cast": {"mapping": {"x": "bigint"}}}]})

    def test_alias_executed_correctly_by_engine(self, engine):
        """Cast via alias 'integer' produit bien une colonne entière."""
        df = pd.DataFrame({"val": ["1", "2", "3"]})
        result = engine.apply_step(df, {"cast": {"mapping": {"val": "int"}}})
        assert str(result.output["val"].dtype) in ("Int64", "int64")


# ═══════════════════════════════════════════════════════════════
# 4. Parsers destination et transform : accessibles hors backup/
# ═══════════════════════════════════════════════════════════════

class TestParsersAccessibility:

    def test_destination_parser_importable(self):
        from internal.parser.destination import DestinationParser, LoadMode
        assert DestinationParser is not None
        assert LoadMode.UPSERT.value == "upsert"

    def test_transform_parser_importable(self):
        from internal.parser.transform import TransformParser
        assert TransformParser is not None

    def test_destination_parser_not_from_backup(self):
        import internal.parser.destination as mod
        assert "backup" not in mod.__file__

    def test_transform_parser_not_from_backup(self):
        import internal.parser.transform as mod
        assert "backup" not in mod.__file__


# ═══════════════════════════════════════════════════════════════
# 5. Edge cases : batch vide, 0 lignes après filter, batch_size=1
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_filter_produces_empty_dataframe(self, engine, df_simple):
        """Filter qui ne garde aucune ligne → DataFrame vide, pas d'erreur."""
        result = engine.apply_step(df_simple, {"filter": {"expr": "id > 9999"}})
        assert isinstance(result.output, pd.DataFrame)
        assert len(result.output) == 0

    def test_pipeline_with_empty_result(self, engine, df_simple):
        """Pipeline complet avec résultat vide."""
        result = engine.apply_pipeline(
            df_simple,
            [{"filter": {"expr": "id > 9999"}}, {"select": {"columns": ["id"]}}],
        )
        assert isinstance(result.output, pd.DataFrame)
        assert len(result.output) == 0

    def test_single_row_dataframe(self, engine):
        """batch_size=1 : DataFrame d'une seule ligne."""
        df = pd.DataFrame({"a": [42], "b": ["hello"]})
        result = engine.apply_pipeline(df, [{"select": {"columns": ["a"]}}])
        assert len(result.output) == 1
        assert list(result.output.columns) == ["a"]

    def test_select_deduplicates_columns(self, engine, df_simple):
        """select avec colonnes en double → déduplication silencieuse."""
        result = engine.apply_step(df_simple, {"select": {"columns": ["id", "id", "name"]}})
        assert list(result.output.columns) == ["id", "name"]

    def test_calculate_overwrites_existing_column(self, engine, df_simple):
        """calculate sur colonne existante → écrase sans erreur."""
        result = engine.apply_step(df_simple, {"calculate": {"column": "price", "expr": "price * 2"}})
        assert result.output["price"].tolist() == [20.0, 40.0, 60.0]

    def test_rename_then_select_chain(self, engine, df_simple):
        """Enchaînement rename → select : la colonne renommée est sélectionnable."""
        result = engine.apply_pipeline(df_simple, [
            {"rename": {"mapping": {"id": "pk"}}},
            {"select": {"columns": ["pk", "name"]}},
        ])
        assert list(result.output.columns) == ["pk", "name"]

    def test_cast_on_all_rows(self, engine):
        """Cast int → float sur toutes les lignes."""
        df = pd.DataFrame({"n": [1, 2, 3, 4, 5]})
        result = engine.apply_step(df, {"cast": {"mapping": {"n": "float"}}})
        assert str(result.output["n"].dtype) == "float64"


# ═══════════════════════════════════════════════════════════════
# 6. Destination parser : LoadMode + validation croisée
# ═══════════════════════════════════════════════════════════════

class TestDestinationParser:

    @pytest.fixture
    def parser(self):
        from internal.parser.destination import DestinationParser
        return DestinationParser()

    def _raw(self, mode, key=None, table="tbl"):
        cfg = {
            "destinations": {
                "dest": {
                    "type": "mysql",
                    "connection": {"host": "localhost"},
                    "load": {"table": table, "mode": mode},
                }
            }
        }
        if key is not None:
            cfg["destinations"]["dest"]["load"]["key"] = key
        return cfg

    def test_mode_append_parsed(self, parser):
        cfg = parser.parse(self._raw("append"))
        from internal.parser.destination import LoadMode
        assert cfg.destinations["dest"].load.mode == LoadMode.APPEND

    def test_mode_replace_parsed(self, parser):
        cfg = parser.parse(self._raw("replace"))
        from internal.parser.destination import LoadMode
        assert cfg.destinations["dest"].load.mode == LoadMode.REPLACE

    def test_mode_upsert_with_key_ok(self, parser):
        cfg = parser.parse(self._raw("upsert", key=["id"]))
        from internal.parser.destination import LoadMode
        assert cfg.destinations["dest"].load.mode == LoadMode.UPSERT
        assert cfg.destinations["dest"].load.key == ["id"]

    def test_mode_upsert_without_key_raises(self, parser):
        with pytest.raises(Exception, match="key"):
            parser.parse(self._raw("upsert", key=None))

    def test_composite_key_parsed(self, parser):
        cfg = parser.parse(self._raw("upsert", key=["region", "product_id"]))
        assert cfg.destinations["dest"].load.key == ["region", "product_id"]

    def test_key_deduplication(self, parser):
        cfg = parser.parse(self._raw("upsert", key=["id", "id"]))
        assert cfg.destinations["dest"].load.key == ["id"]

    def test_invalid_mode_raises(self, parser):
        with pytest.raises(Exception):
            parser.parse(self._raw("merge"))

    def test_empty_table_raises(self, parser):
        with pytest.raises(Exception):
            parser.parse(self._raw("append", table=""))


# ═══════════════════════════════════════════════════════════════
# 7. Transform parser : opérations inconnues, step malformé
# ═══════════════════════════════════════════════════════════════

class TestTransformParserEdgeCases:

    @pytest.fixture
    def parser(self):
        from internal.parser.transform import TransformParser
        return TransformParser()

    def test_unknown_op_raises(self, parser):
        with pytest.raises(Exception, match="inconnue|unknown"):
            parser.parse({"steps": [{"explode": {"column": "x"}}]})

    def test_step_with_two_keys_raises(self, parser):
        with pytest.raises(Exception):
            parser.parse({"steps": [{"select": {"columns": ["id"]}, "filter": {"expr": "id>1"}}]})

    def test_empty_steps_raises(self, parser):
        with pytest.raises(Exception):
            parser.parse({"steps": []})

    def test_wrapper_transformations_key_accepted(self, parser):
        """DSL avec clé 'transformations' wrappant 'steps'."""
        cfg = parser.parse({"transformations": {"steps": [{"select": {"columns": ["id"]}}]}})
        assert len(cfg.steps) == 1

    def test_select_empty_columns_raises(self, parser):
        with pytest.raises(Exception):
            parser.parse({"steps": [{"select": {"columns": []}}]})

    def test_filter_empty_expr_raises(self, parser):
        with pytest.raises(Exception):
            parser.parse({"steps": [{"filter": {"expr": ""}}]})

    def test_calculate_missing_column_raises(self, parser):
        with pytest.raises(Exception):
            parser.parse({"steps": [{"calculate": {"expr": "a * 2"}}]})

    def test_multiple_steps_parsed_in_order(self, parser):
        cfg = parser.parse({"steps": [
            {"select": {"columns": ["id", "name"]}},
            {"filter": {"expr": "id > 1"}},
            {"rename": {"mapping": {"id": "pk"}}},
        ]})
        assert [s.op for s in cfg.steps] == ["select", "filter", "rename"]
