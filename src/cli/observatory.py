"""CLI subcommand `observatory` — cross-module ML activity + status (read-only).

Like `library`/`ai stats`, this reuses the pure core directly: no
`CLIEventBus`, no `run_*_pipeline` (nothing here has progress to render).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_DOMAIN_LABELS = {
    "transcription_profile": "Perfil de transcrição",
    "data_domain": "Domínio de dados",
    "document_type": "Tipo de documento",
}


def add_observatory_parser(subparsers) -> None:
    """Register the `observatory` subcommand and its `status`/`activity` ops."""
    p = subparsers.add_parser(
        "observatory",
        help="Observatório de ML — atividade e status cross-módulo (leitura)",
    )
    sub = p.add_subparsers(dest="observatory_op", required=True)

    status_p = sub.add_parser(
        "status",
        help="Status dos motores de ML (gates, classificador, config, timings)",
    )
    status_p.add_argument("--verbose", action="store_true", help="Logging DEBUG")

    activity_p = sub.add_parser(
        "activity", help="Atividade recente de ML entre todos os módulos"
    )
    activity_p.add_argument(
        "--limit",
        type=int,
        default=15,
        help="Quantidade de eventos exibidos (default: 15)",
    )
    activity_p.add_argument("--verbose", action="store_true", help="Logging DEBUG")

    p.set_defaults(func=run_observatory_cli)


def _fmt_time(ts: float) -> str:
    return time.strftime("%d/%m %H:%M", time.localtime(ts))


def _answer_times() -> dict[str, list[float]]:
    """Read the per-model answer-time map from ~/.mill-tools/config.json.

    Read directly (not via gui.settings) so the CLI layer never imports the
    GUI — same convention as `cli/ai.py::_answer_times`.
    """
    import json

    config = Path.home() / ".mill-tools" / "config.json"
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    times = data.get("ai_answer_times", {})
    return times if isinstance(times, dict) else {}


def _run_status(ns: argparse.Namespace) -> None:
    """Run the `observatory status` operation."""
    from src.core.observatory import status

    print("Gates e extras:")
    for gate in status.gate_statuses():
        mark = "[✓]" if gate.available else "[✗]"
        extra = "" if gate.available else f" — {gate.hint}"
        print(f"  {mark} {gate.name}{extra}")

    print("\nClassificador (por domínio):")
    for d in status.domain_statuses():
        method = "supervisionado" if d.supervised else "zero-shot"
        label = _DOMAIN_LABELS.get(d.domain, d.domain)
        print(f"  {label}: {d.n_labels} rótulo(s) · {method}")

    snap = status.config_snapshot()
    print("\nConfiguração em vigor:")
    print(f"  Limiar de dedup de texto: {snap.text_dedup_threshold:.2f}")
    print(f"  Distância máx. dedup de imagem: {snap.image_dedup_max_distance}")
    print(f"  Piso de corpus p/ auto-k: {snap.auto_k_min_corpus}")
    print(f"  λ do MMR: {snap.mmr_lambda:.2f}")

    from src.core.rag.analytics import model_timings

    timings = model_timings(_answer_times())
    print("\nTempo de resposta por modelo:")
    if not timings:
        print("  Nenhuma resposta registrada ainda.")
    else:
        for t in timings:
            print(f"  {t.model}: {t.count}x · média {t.mean:.1f}s · p90 {t.p90:.1f}s")


def _run_activity(ns: argparse.Namespace) -> None:
    """Run the `observatory activity` operation."""
    from src.core.observatory.activity import load_activity, recent

    entries = recent(load_activity(), limit=ns.limit)
    if not entries:
        print("Nenhuma atividade de ML registrada ainda.")
        return
    for e in entries:
        print(f"{_fmt_time(e.timestamp)}  {e.module:<12}  {e.detail}")


def run_observatory_cli(ns: argparse.Namespace) -> None:
    """Dispatch the `observatory` subcommand: `status` or `activity`."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    if ns.observatory_op == "status":
        _run_status(ns)
    else:
        _run_activity(ns)
