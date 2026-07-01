"""Tests for the ``data`` CLI subcommand (parser + dispatch)."""

import argparse

import pytest

from src.cli.data import add_data_parser


@pytest.fixture
def csv_sales(tmp_path):
    """A small real CSV so the scanner/dispatch run without mocking the engine."""
    p = tmp_path / "vendas.csv"
    p.write_text("produto,qtd\nmaca,3\nbanana,5\n", encoding="utf-8")
    return p


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_data_parser(sub)
    return parser.parse_args(["data", *argv])


@pytest.mark.unit
def test_query_parses_files_and_question():
    ns = _parse("query", "a.csv", "b.csv", "quantas linhas?")
    assert ns.data_op == "query"
    assert ns.files == ["a.csv", "b.csv"]
    assert ns.question == "quantas linhas?"
    assert ns.sql is False
    assert ns.limit == 50
    assert callable(ns.func)


@pytest.mark.unit
def test_query_sql_and_out_flags():
    ns = _parse(
        "query", "a.csv", "SELECT 1", "--sql", "--out", "parquet", "--name", "r"
    )
    assert ns.sql is True
    assert ns.out == "parquet"
    assert ns.name == "r"


@pytest.mark.unit
def test_query_invalid_out_format_rejected():
    with pytest.raises(SystemExit):
        _parse("query", "a.csv", "q", "--out", "xml")


@pytest.mark.unit
def test_convert_defaults_to_csv():
    ns = _parse("convert", "a.json")
    assert ns.data_op == "convert"
    assert ns.file == "a.json"
    assert ns.out == "csv"


@pytest.mark.unit
def test_profile_parser():
    ns = _parse("profile", "a.csv")
    assert ns.data_op == "profile"
    assert ns.file == "a.csv"


@pytest.mark.unit
def test_run_data_cli_query_sql_dispatch(mocker, csv_sales, capsys):
    from src.core.data.types import QueryResult

    mock_run = mocker.patch(
        "src.cli.data.run_query",
        return_value=QueryResult(["n"], [(3,)], 0.01, 1),
    )
    mock_to_sql = mocker.patch("src.cli.data.nl2sql.to_sql")  # must NOT be called

    ns = _parse("query", str(csv_sales), "SELECT count(*) AS n FROM vendas", "--sql")
    ns.func(ns)

    assert mock_run.called
    mock_to_sql.assert_not_called()  # --sql skips the IA
    out = capsys.readouterr().out
    assert "1 linha(s)" in out


@pytest.mark.unit
def test_run_data_cli_query_uses_nl2sql(mocker, csv_sales, capsys):
    from src.core.data.types import QueryResult

    mocker.patch(
        "src.cli.data.nl2sql.to_sql",
        return_value=("SELECT 1", "Conta as linhas."),
    )
    mocker.patch(
        "src.cli.data.run_query",
        return_value=QueryResult(["x"], [(1,)], 0.0, 1),
    )
    ns = _parse("query", str(csv_sales), "quantas linhas?")
    ns.func(ns)

    out = capsys.readouterr().out
    assert "Entendi assim: Conta as linhas." in out


@pytest.mark.unit
def test_run_data_cli_query_saves_output(mocker, csv_sales, tmp_path):
    from src.core.data.types import QueryResult

    mocker.patch(
        "src.cli.data.run_query",
        return_value=QueryResult(["n"], [(3,)], 0.0, 1),
    )
    mock_save = mocker.patch(
        "src.cli.data.convert.save_query", return_value=tmp_path / "r.csv"
    )
    ns = _parse(
        "query", str(csv_sales), "SELECT 1", "--sql", "--out", "csv", "--name", "r"
    )
    ns.func(ns)

    assert mock_save.called
    assert mock_save.call_args.args[3] == "csv"  # fmt
    assert mock_save.call_args.args[4] == "r"  # stem


@pytest.mark.unit
def test_run_data_cli_missing_file_exits(mocker):
    ns = _parse("query", "does_not_exist.csv", "q", "--sql")
    with pytest.raises(SystemExit):
        ns.func(ns)


@pytest.mark.unit
def test_run_data_cli_convert_dispatch(mocker, csv_sales, tmp_path):
    mock_conv = mocker.patch(
        "src.cli.data.convert.convert_file", return_value=tmp_path / "o.json"
    )
    ns = _parse("convert", str(csv_sales), "--out", "json")
    ns.func(ns)
    assert mock_conv.called
    assert mock_conv.call_args.args[2] == "json"


@pytest.mark.unit
def test_run_data_cli_profile_dispatch(mocker, csv_sales, tmp_path):
    report = tmp_path / "vendas_profile.txt"
    report.write_text("# Perfil\n- Linhas: 3\n", encoding="utf-8")
    mock_prof = mocker.patch("src.cli.data.profile.profile_file", return_value=report)
    ns = _parse("profile", str(csv_sales))
    ns.func(ns)
    assert mock_prof.called


@pytest.mark.unit
def test_assess_parser_defaults():
    ns = _parse("assess", "a.csv")
    assert ns.data_op == "assess"
    assert ns.file == "a.csv"
    assert ns.no_cache is False
    assert callable(ns.func)


@pytest.mark.unit
def test_run_data_cli_assess_uses_cache(mocker, csv_sales, capsys):
    # A cached assessment short-circuits the LLM call entirely.
    mocker.patch(
        "src.core.data.assess.load_cached_assessment",
        return_value="## ok\n- consistente",
    )
    mock_assess = mocker.patch("src.core.data.assess.assess")
    ns = _parse("assess", str(csv_sales))
    ns.func(ns)

    mock_assess.assert_not_called()
    out = capsys.readouterr().out
    assert "do cache" in out
    assert "consistente" in out


@pytest.mark.unit
def test_run_data_cli_assess_generates_and_caches(mocker, csv_sales, capsys):
    mocker.patch("src.core.data.assess.load_cached_assessment", return_value=None)
    mock_assess = mocker.patch(
        "src.core.data.assess.assess", return_value="- coluna qtd ok"
    )
    mock_save = mocker.patch("src.core.data.assess.save_assessment")
    ns = _parse("assess", str(csv_sales), "--no-cache")
    ns.func(ns)

    assert mock_assess.called
    assert mock_save.called  # result is cached for reuse by indexing
    out = capsys.readouterr().out
    assert "coluna qtd ok" in out


@pytest.mark.unit
def test_run_data_cli_assess_missing_file_exits():
    ns = _parse("assess", "ghost.csv")
    with pytest.raises(SystemExit):
        ns.func(ns)


# --- plot --------------------------------------------------------------------


@pytest.mark.unit
def test_plot_parser_flags():
    ns = _parse(
        "plot",
        "a.csv",
        "vendas por produto",
        "--kind",
        "bar",
        "--x",
        "produto",
        "--y",
        "total",
        "--out",
        "g.png",
    )
    assert ns.data_op == "plot"
    assert ns.files == ["a.csv"]
    assert ns.question == "vendas por produto"
    assert ns.kind == "bar"
    assert ns.x == "produto"
    assert ns.y == "total"
    assert ns.out == "g.png"
    assert callable(ns.func)


@pytest.mark.unit
def test_plot_invalid_kind_rejected():
    with pytest.raises(SystemExit):
        _parse("plot", "a.csv", "q", "--kind", "pizza")


@pytest.mark.unit
def test_run_data_cli_plot_dispatch(mocker, csv_sales, tmp_path):
    # Stub the Plano-0 Arrow→pandas chain and the renderer so no real
    # polars/matplotlib work is needed for the dispatch test.
    mocker.patch("src.core.data.frames.is_available", return_value=True)
    mocker.patch("src.cli.data.charts.is_available", return_value=True)
    fake_df = mocker.MagicMock()
    fake_df.height = 2
    fake_df.schema = {"produto": "String", "qtd": "Int64"}
    mocker.patch("src.core.data.engine.run_query_arrow", return_value="ARROW")
    mocker.patch("src.core.data.frames.from_arrow", return_value=fake_df)
    mocker.patch("src.core.data.frames.to_pandas", return_value="PANDAS")
    mock_render = mocker.patch(
        "src.cli.data.charts.render_png", return_value=b"\x89PNG\r\n"
    )
    mock_to_sql = mocker.patch("src.cli.data.nl2sql.to_sql")  # must NOT be called
    mocker.patch("src.cli.data.DATA_DIR", tmp_path)

    ns = _parse(
        "plot", str(csv_sales), "SELECT produto, qtd FROM vendas", "--sql", "--out", "g"
    )
    ns.func(ns)

    mock_to_sql.assert_not_called()
    assert mock_render.called
    # Suggested spec for (String, Int64) is a bar(produto, qtd).
    spec = mock_render.call_args.args[1]
    assert spec.kind == "bar" and spec.x == "produto" and spec.y == "qtd"
    assert (tmp_path / "g.png").read_bytes() == b"\x89PNG\r\n"  # .png appended


@pytest.mark.unit
def test_run_data_cli_plot_gate_unavailable_exits(mocker, csv_sales):
    mocker.patch("src.core.data.frames.is_available", return_value=False)
    ns = _parse("plot", str(csv_sales), "q", "--sql")
    with pytest.raises(SystemExit):
        ns.func(ns)


@pytest.mark.unit
def test_run_data_cli_plot_missing_file_exits(mocker):
    mocker.patch("src.core.data.frames.is_available", return_value=True)
    mocker.patch("src.cli.data.charts.is_available", return_value=True)
    ns = _parse("plot", "ghost.csv", "q", "--sql")
    with pytest.raises(SystemExit):
        ns.func(ns)


@pytest.mark.unit
def test_outliers_parser_defaults():
    ns = _parse("outliers", "a.csv")
    assert ns.data_op == "outliers"
    assert ns.file == "a.csv"
    assert ns.contamination == 0.05
    assert ns.limit == 20
    assert callable(ns.func)


@pytest.mark.unit
def test_run_data_cli_outliers_dispatch(mocker, csv_sales, capsys):
    import pandas as pd

    mocker.patch("src.core.data.frames.is_available", return_value=True)
    mocker.patch("src.core.ml.deps.is_available", return_value=True)
    fake_df = mocker.MagicMock()
    fake_df.height = 2
    mocker.patch("src.core.data.engine.run_query_arrow", return_value="ARROW")
    mocker.patch("src.core.data.frames.from_arrow", return_value=fake_df)
    mocker.patch(
        "src.core.data.frames.to_pandas", return_value=pd.DataFrame({"qtd": [3, 5]})
    )

    ns = _parse("outliers", str(csv_sales))
    ns.func(ns)

    out = capsys.readouterr().out
    assert "linha(s) sinalizada(s)" in out


@pytest.mark.unit
def test_run_data_cli_outliers_gate_unavailable_exits(mocker, csv_sales):
    mocker.patch("src.core.data.frames.is_available", return_value=True)
    mocker.patch("src.core.ml.deps.is_available", return_value=False)
    ns = _parse("outliers", str(csv_sales))
    with pytest.raises(SystemExit):
        ns.func(ns)


@pytest.mark.unit
def test_run_data_cli_outliers_missing_file_exits(mocker):
    mocker.patch("src.core.data.frames.is_available", return_value=True)
    mocker.patch("src.core.ml.deps.is_available", return_value=True)
    ns = _parse("outliers", "ghost.csv")
    with pytest.raises(SystemExit):
        ns.func(ns)
