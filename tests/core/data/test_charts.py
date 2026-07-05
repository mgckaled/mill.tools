"""Tests for the matplotlib boundary (``charts.py``): suggest + render to PNG.

matplotlib/pandas live behind the optional ``[data-plot]``/``[analysis]`` extras,
so the module skips gracefully when they are absent (``importorskip``). Agg
rendering is headless (no display), so these qualify as ``unit``.
"""

import io
import sys
import threading

import pytest
from PIL import Image

from src.core.data import charts

pd = pytest.importorskip("pandas")
pytest.importorskip("matplotlib")

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.mark.unit
def test_is_available_true_with_extra_installed():
    assert charts.is_available() is True


@pytest.mark.unit
def test_is_available_false_without_matplotlib(mocker):
    mocker.patch.dict(sys.modules, {"matplotlib": None})
    assert charts.is_available() is False


# --- suggest_spec ------------------------------------------------------------


@pytest.mark.unit
def test_suggest_categorical_plus_numeric_is_bar():
    spec = charts.suggest_spec([("produto", "VARCHAR"), ("total", "BIGINT")])
    assert spec.kind == "bar"
    assert spec.x == "produto"
    assert spec.y == "total"


@pytest.mark.unit
def test_suggest_temporal_plus_numeric_is_line():
    spec = charts.suggest_spec([("dia", "DATE"), ("vendas", "DOUBLE")])
    assert spec.kind == "line"
    assert spec.x == "dia"
    assert spec.y == "vendas"


@pytest.mark.unit
def test_suggest_two_numerics_is_scatter():
    spec = charts.suggest_spec([("altura", "DOUBLE"), ("peso", "DOUBLE")])
    assert spec.kind == "scatter"
    assert spec.x == "altura"
    assert spec.y == "peso"


@pytest.mark.unit
def test_suggest_single_numeric_is_hist():
    spec = charts.suggest_spec([("idade", "BIGINT")])
    assert spec.kind == "hist"
    assert spec.x == "idade"


@pytest.mark.unit
def test_suggest_no_numeric_falls_back_to_count_bar():
    spec = charts.suggest_spec([("cidade", "VARCHAR"), ("uf", "VARCHAR")])
    assert spec.kind == "bar"
    assert spec.x == "cidade"
    assert spec.y is None


@pytest.mark.unit
def test_schema_from_rows_infers_categories():
    import datetime

    cols = ["nome", "qtd", "preco", "dia"]
    rows = [("a", 3, 1.5, datetime.date(2026, 6, 26))]
    schema = charts.schema_from_rows(cols, rows)
    assert schema == [
        ("nome", "categorical"),
        ("qtd", "numeric"),
        ("preco", "numeric"),
        ("dia", "temporal"),
    ]


@pytest.mark.unit
def test_schema_from_rows_handles_bool_none_and_all_null():
    cols = ["flag", "valor", "vazio"]
    rows = [
        (None, None, None),  # first row all None → skip
        (True, 10, None),  # bool → categorical, int → numeric, still None
    ]
    schema = charts.schema_from_rows(cols, rows)
    assert schema == [
        ("flag", "categorical"),  # bool is not numeric
        ("valor", "numeric"),
        ("vazio", "categorical"),  # all-None column → default category
    ]
    # Feeding the canonical categories back through suggest_spec exercises the
    # _kind_of canonical-string path (the GUI's real pre-fill route).
    spec = charts.suggest_spec(schema)
    assert spec.kind == "bar"
    assert spec.x == "flag"
    assert spec.y == "valor"


# --- render_png --------------------------------------------------------------


def _df():
    return pd.DataFrame(
        {
            "produto": ["maçã", "banana", "uva"],
            "qtd": [3, 5, 2],
            "preco": [1.5, 0.8, 4.0],
        }
    )


def _assert_valid_png(data: bytes) -> None:
    assert data, "PNG bytes should not be empty"
    assert data[:8] == _PNG_MAGIC
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"
    assert img.size[0] > 0 and img.size[1] > 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "spec",
    [
        charts.ChartSpec(kind="bar", x="produto", y="qtd"),
        charts.ChartSpec(kind="bar", x="produto"),  # count bar (y=None)
        charts.ChartSpec(kind="line", x="produto", y="preco"),
        charts.ChartSpec(kind="hist", x="qtd"),
        charts.ChartSpec(kind="scatter", x="qtd", y="preco"),
    ],
)
def test_render_png_produces_valid_image_per_kind(spec):
    _assert_valid_png(charts.render_png(_df(), spec))


@pytest.mark.unit
def test_render_png_applies_custom_palette():
    palette = charts.ChartPalette(
        bg="#101014", fg="#FFFFFF", accent="#F4A63C", grid="#484850", muted="#A1A1AA"
    )
    out = charts.render_png(
        _df(),
        charts.ChartSpec(kind="bar", x="produto", y="qtd", title="Vendas"),
        palette=palette,
    )
    _assert_valid_png(out)


@pytest.mark.unit
def test_render_png_empty_dataframe_raises():
    with pytest.raises(ValueError, match="Sem dados"):
        charts.render_png(_df().iloc[0:0], charts.ChartSpec(kind="bar", x="produto"))


@pytest.mark.unit
def test_render_png_missing_column_raises():
    with pytest.raises(ValueError, match="inexistente"):
        charts.render_png(_df(), charts.ChartSpec(kind="bar", x="naoexiste"))


@pytest.mark.unit
def test_render_png_missing_x_raises():
    with pytest.raises(ValueError, match="eixo X"):
        charts.render_png(_df(), charts.ChartSpec(kind="bar", x=None))


@pytest.mark.unit
def test_render_png_bar_with_decimal_y():
    """A SUM(BIGINT) in DuckDB lands as a Decimal/object column — must still render.

    Regression: ax.bar with string x + Decimal heights tripped matplotlib's
    category converter ("'value' must be an instance of str or bytes, not float").
    """
    import decimal

    df = pd.DataFrame(
        {
            "categoria": ["a", "b", "c"],
            "total": [
                decimal.Decimal("10"),
                decimal.Decimal("25"),
                decimal.Decimal("7"),
            ],
        }
    )
    out = charts.render_png(df, charts.ChartSpec(kind="bar", x="categoria", y="total"))
    _assert_valid_png(out)


@pytest.mark.unit
def test_render_png_line_with_decimal_x():
    """A GROUP BY key that is itself a DuckDB aggregate/DECIMAL must still
    render as a line chart's x-axis (regression: _line used to pass the raw
    object/Decimal column straight to ax.plot, unlike _bar/_scatter)."""
    import decimal

    df = pd.DataFrame(
        {
            "total": [decimal.Decimal("1"), decimal.Decimal("2"), decimal.Decimal("3")],
            "preco": [1.5, 0.8, 4.0],
        }
    )
    out = charts.render_png(df, charts.ChartSpec(kind="line", x="total", y="preco"))
    _assert_valid_png(out)


@pytest.mark.unit
def test_render_png_line_with_temporal_x_is_untouched():
    """A datetime x-axis must not be coerced to float (that would wreck
    matplotlib's date axis) — only Decimal/object numeric columns are."""
    import datetime

    df = pd.DataFrame(
        {
            "dia": [datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)],
            "vendas": [10.0, 20.0],
        }
    )
    out = charts.render_png(df, charts.ChartSpec(kind="line", x="dia", y="vendas"))
    _assert_valid_png(out)


@pytest.mark.unit
def test_render_png_non_numeric_y_raises_friendly_error():
    df = pd.DataFrame({"categoria": ["a", "b"], "rotulo": ["x", "y"]})
    with pytest.raises(ValueError, match="não é numérica"):
        charts.render_png(df, charts.ChartSpec(kind="bar", x="categoria", y="rotulo"))


@pytest.mark.unit
def test_render_png_line_without_y_raises():
    with pytest.raises(ValueError, match="precisa de uma coluna Y"):
        charts.render_png(_df(), charts.ChartSpec(kind="line", x="produto"))


@pytest.mark.unit
def test_render_png_unknown_kind_raises():
    with pytest.raises(ValueError, match="inválido"):
        charts.render_png(_df(), charts.ChartSpec(kind="pizza", x="produto"))


# --- render_category_scatter (semantic map, Plano 4A) ------------------------


def _scatter_df():
    return pd.DataFrame(
        {
            "x": [0.0, 0.1, 2.0, 2.1, 5.0],
            "y": [0.0, 0.2, 2.0, 1.9, 5.0],
            "cluster": ["whisper", "whisper", "duna", "duna", "órfãos"],
        }
    )


@pytest.mark.unit
def test_render_category_scatter_produces_valid_png():
    out = charts.render_category_scatter(
        _scatter_df(),
        x="x",
        y="y",
        color="cluster",
        annotations=[(0.05, 0.1, "whisper"), (2.05, 1.95, "duna")],
        noise_value="órfãos",
        title="Mapa",
    )
    _assert_valid_png(out)


@pytest.mark.unit
def test_render_category_scatter_empty_raises():
    with pytest.raises(ValueError, match="Sem dados"):
        charts.render_category_scatter(
            pd.DataFrame({"x": [], "y": [], "cluster": []}),
            x="x",
            y="y",
            color="cluster",
        )


@pytest.mark.unit
def test_render_category_scatter_many_categories_skips_legend():
    # >12 categories → legend is skipped (would be unreadable) but PNG still valid.
    n = 15
    df = pd.DataFrame(
        {
            "x": list(range(n)),
            "y": list(range(n)),
            "cluster": [f"c{i}" for i in range(n)],
        }
    )
    _assert_valid_png(charts.render_category_scatter(df, x="x", y="y", color="cluster"))


@pytest.mark.unit
def test_render_category_scatter_missing_column_raises():
    with pytest.raises(ValueError, match="inexistente"):
        charts.render_category_scatter(_scatter_df(), x="x", y="y", color="ghost")


@pytest.mark.unit
def test_render_category_scatter_thread_safe():
    out1, out2 = [], []

    def _work(sink):
        sink.append(
            charts.render_category_scatter(
                _scatter_df(), x="x", y="y", color="cluster", noise_value="órfãos"
            )
        )

    threads = [
        threading.Thread(target=_work, args=(out1,)),
        threading.Thread(target=_work, args=(out2,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    _assert_valid_png(out1[0])
    _assert_valid_png(out2[0])


@pytest.mark.unit
def test_render_png_thread_safe_concurrent_renders():
    """Two concurrent renders both yield valid PNGs (proves Figure/Agg, not pyplot)."""
    results: list[bytes] = []
    errors: list[Exception] = []

    def _work(kind: str, x: str, y: str | None) -> None:
        try:
            results.append(
                charts.render_png(_df(), charts.ChartSpec(kind=kind, x=x, y=y))
            )
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [
        threading.Thread(target=_work, args=("bar", "produto", "qtd")),
        threading.Thread(target=_work, args=("scatter", "qtd", "preco")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 2
    for data in results:
        _assert_valid_png(data)
