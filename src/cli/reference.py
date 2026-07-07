"""Compact CLI reference for the NL→CLI feature (Fase 1, PLANO_NL2CLI_HUB_IA.md).

Pure (no Flet, no network). Builds a discardable ``ArgumentParser`` by reusing
the real ``add_*_parser(subparsers)`` registration functions from every CLI
module, then introspects it — never hand-written/duplicated flag text, so a
new flag shows up here automatically (zero drift).

``build_reference()`` is the text fed to the LLM prompt in
``core/text/nl2cli.py`` (Fase 2). ``validate_command()`` is the canonical
validator: it runs the generated command through the same parser's real
``parse_args()``, closing the loop without executing anything.
"""

from __future__ import annotations

import argparse
import functools
import shlex

_PREFIX = "uv run main.py "


def _build_parser() -> argparse.ArgumentParser:
    """Register every subcommand parser on a throwaway top-level parser."""
    from src.cli.ai import add_ai_parser
    from src.cli.audio import add_audio_parser, add_audio_viz_parser
    from src.cli.data import add_data_parser
    from src.cli.document import add_document_parser
    from src.cli.image import add_image_parser
    from src.cli.library import add_library_parser
    from src.cli.observatory import add_observatory_parser
    from src.cli.recipes import add_recipe_parser
    from src.cli.transcription import add_transcribe_args
    from src.cli.video import add_video_parser

    parser = argparse.ArgumentParser(prog="main.py", add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=True)

    transcribe_p = subparsers.add_parser(
        "transcribe", help="Transcribe a URL/local file (Whisper) + optional AI steps"
    )
    add_transcribe_args(transcribe_p, include_profile_choices=False)

    add_audio_parser(subparsers)
    add_audio_viz_parser(subparsers)
    add_video_parser(subparsers)
    add_image_parser(subparsers)
    add_document_parser(subparsers)
    add_library_parser(subparsers)
    add_ai_parser(subparsers)
    add_recipe_parser(subparsers)
    add_data_parser(subparsers)
    add_observatory_parser(subparsers)
    return parser


def _find_subparsers_action(
    parser: argparse.ArgumentParser,
) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def _choice_help_map(sub_action: argparse._SubParsersAction) -> dict[str, str]:
    """Map each subcommand/operation name to its ``help=`` text.

    ``add_parser(name, help=...)`` stores ``help`` on a pseudo-action in
    ``_choices_actions`` — it is never copied onto the sub-parser itself.
    """
    return {pseudo.dest: (pseudo.help or "") for pseudo in sub_action._choices_actions}


def _fmt_action(action: argparse.Action) -> str | None:
    """Format one argparse action as a compact reference token, or None to skip it."""
    if isinstance(action, (argparse._HelpAction, argparse._SubParsersAction)):
        return None

    if not action.option_strings:
        # Positional.
        name = action.metavar or action.dest
        token = f"<{name}>"
        if action.nargs == "+":
            token = f"{token}..."
            return token
        if action.nargs == "?":
            return f"[{token}]"
        return token

    flag = max(action.option_strings, key=len)
    takes_value = action.nargs != 0 and not isinstance(
        action, (argparse._StoreTrueAction, argparse._StoreFalseAction)
    )
    if not takes_value:
        token = flag
    else:
        if action.choices:
            value = "{" + "|".join(str(c) for c in action.choices) + "}"
        else:
            value = f"<{(action.metavar or action.dest).upper()}>"
        token = f"{flag} {value}"
        if action.default not in (None, argparse.SUPPRESS, False, ""):
            token = f"{token}={action.default}"

    return token if action.required else f"[{token}]"


def _fmt_operation(name: str, parser: argparse.ArgumentParser, description: str) -> str:
    tokens = [t for a in parser._actions if (t := _fmt_action(a)) is not None]
    line = f"{name} {' '.join(tokens)}".rstrip()
    return f"{line} — {description}" if description else line


@functools.lru_cache(maxsize=1)
def build_reference() -> str:
    """Return the compact CLI reference (one line per operation), cached per process."""
    parser = _build_parser()
    top_action = _find_subparsers_action(parser)
    assert top_action is not None
    top_help = _choice_help_map(top_action)

    lines: list[str] = []
    for name, sub in top_action.choices.items():
        nested = _find_subparsers_action(sub)
        if nested is not None:
            nested_help = _choice_help_map(nested)
            for op_name, op_parser in nested.choices.items():
                lines.append(
                    _fmt_operation(
                        f"{name} {op_name}", op_parser, nested_help.get(op_name, "")
                    )
                )
        else:
            lines.append(_fmt_operation(name, sub, top_help.get(name, "")))
    return "\n".join(lines)


def validate_command(command: str) -> str | None:
    """Validate a generated ``uv run main.py ...`` command.

    Returns ``None`` when valid, or the argparse error message otherwise.
    Never executes anything — parses only.
    """
    text = command.strip()
    if not text.startswith(_PREFIX):
        return f"O comando deve começar com {_PREFIX!r}."
    text = text[len(_PREFIX) :].strip()
    if not text:
        return "Comando vazio após o prefixo."

    try:
        tokens = shlex.split(text, posix=False)
    except ValueError as exc:  # unbalanced quotes, etc.
        return f"Não foi possível interpretar o comando: {exc}"

    # shlex(posix=False) keeps surrounding quotes on quoted tokens — strip them
    # so argparse sees the same value a POSIX shell/PowerShell would pass.
    tokens = [
        t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t
        for t in tokens
    ]

    parser = _build_parser()
    errors: list[str] = []

    def _capture_error(_self: argparse.ArgumentParser, message: str) -> None:
        errors.append(message)
        raise SystemExit(2)

    # A sub-subcommand (e.g. "video trim") raises via its own nested
    # ArgumentParser instance, not the top-level one — patch the class method
    # (not just this parser's) so every parser in the tree is captured.
    original_error = argparse.ArgumentParser.error
    argparse.ArgumentParser.error = _capture_error  # type: ignore[method-assign]
    try:
        parser.parse_args(tokens)
    except SystemExit:
        return errors[-1] if errors else "Comando inválido."
    finally:
        argparse.ArgumentParser.error = original_error
    return None
