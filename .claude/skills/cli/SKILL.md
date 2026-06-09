---
name: cli
description: Guia da CLI modular do mill.tools (subcomandos audio/video/image + transcribe,
  CLIEventBus, padrões de argparse). Invocar ao criar/editar subcomandos em src/cli/,
  adicionar flags, mexer no dispatcher de main.py ou escrever testes em tests/cli/.
---

# mill.tools — Guia da CLI Modular

## Visão geral

`main.py` despacha para subcomandos por prefixo do primeiro argumento:

```python
_NON_TRANSCRIBE_CMDS = frozenset({"audio", "video", "image"})

def main():
    if len(sys.argv) > 1 and sys.argv[1] in _NON_TRANSCRIBE_CMDS:
        _dispatch_other(sys.argv[1])   # → src/cli/{audio,video,image}.py
        return
    # legado: transcrição (parse_args direto)
```

`transcribe` como subcomando explícito também é aceito (`sys.argv.pop(1)` antes do parser legado).

---

## Estrutura de arquivos

```
src/cli/
├── bus.py            — CLIEventBus: TqdmLoggingHandler + barra tqdm (sem Flet)
├── transcription.py  — resolve_input(), build_output_stem()
├── audio.py          — add_audio_parser() + run_audio_cli()
├── video.py          — add_video_parser() + run_video_cli()  (sub-subparsers)
└── image.py          — add_image_parser() + run_image_cli()  (sub-subparsers)
```

---

## CLIEventBus (`src/cli/bus.py`)

Substitui o `EventBus` da GUI sem Flet. Exibe progresso via `tqdm` e linhas de texto.

```python
from src.cli.bus import CLIEventBus
bus = CLIEventBus()
```

**Eventos tratados:**
- `log` → `tqdm.write(msg)` com cor ANSI por prefixo
- `progress_update` → atualiza barra tqdm (0–100%)
- `queue_progress` → label "Item N/M — nome"
- `audio_op_start/done`, `video_op_start/done`, `image_op_start/done` → mensagens formatadas
- `task_done` → fecha barra
- `task_error` → mensagem de erro

**Padrão de uso em todos os CLI runners:**
```python
bus = CLIEventBus()
cancel = threading.Event()
success = run_X_pipeline(args, bus, cancel, install_log_handler=False)
if not success:
    sys.exit(1)
```

`install_log_handler=False` evita que o `LogEventHandler` do worker instale um handler
no root logger — a CLI já recebe os logs via `tqdm.write` pelo CLIEventBus.

---

## `resolve_input` (`src/cli/transcription.py`)

Classifica entrada como URL ou arquivo local:

```python
kind, value = resolve_input("https://youtu.be/abc")  # → ("url", "https://…")
kind, value = resolve_input("/path/to/file.mp3")      # → ("local", "/path/…")
```

Usado por todos os CLI runners para popular `InputItem(kind, value)`.

---

## Subcomando `audio`

```bash
uv run main.py audio <URL_OR_FILE> [opções]
```

| Flag | Default | Descrição |
|---|---|---|
| `--fmt` | `mp3` | Formato: mp3/m4a/wav/ogg/opus |
| `--quality` | `best` | Bitrate kbps ou `best` |
| `--no-meta` | off | Não embutir capa/metadados |
| `--denoise` | off | Spectral gating pós-conversão |
| `--normalize` | off | Loudnorm EBU R128 pós-conversão |
| `--lufs` | `-14.0` | Alvo LUFS (só com `--normalize`) |
| `--verbose` | off | Logging DEBUG |

Auto-detecção de operação: URL → download; vídeo local → extração; áudio → conversão.

---

## Subcomando `video`

```bash
uv run main.py video <operação> <entrada> [opções]
```

Usa sub-subparsers. `ns.video_op` contém a operação. Mapeamento especial: `"extract-audio"` → `"extract_audio"` no `VideoArgs`.

| Operação | Entrada | Flags principais |
|---|---|---|
| `download` | URL | `--quality 1080`, `--container mp4`, `--no-meta` |
| `convert` | arquivo | `--codec copy/h264/h265/vp9`, `--container mp4` |
| `trim` | arquivo | `--start HH:MM:SS`, `--end HH:MM:SS`, `--reenc` |
| `compress` | arquivo | `--crf 23`, `--preset medium` |
| `resize` | arquivo | `--width px`, `--height px` |
| `extract-audio` | arquivo | `--fmt mp3` |
| `thumbnail` | arquivo | `--time 00:00:01`, `--fmt jpg` |

---

## Subcomando `image`

```bash
uv run main.py image <operação> <entrada> [opções]
```

Usa sub-subparsers. `ns.image_op` contém a operação (com hífen, ex: `"contact-sheet"`). `run_image_cli` converte com `op.replace("-", "_")` para o `ImageArgs`.

`contact-sheet` é o único que aceita múltiplos arquivos (`nargs="+"` em `ns.files`).

| Operação | Flags principais |
|---|---|
| `convert` | `--fmt jpg`, `--quality 90` |
| `resize` | `--mode contain/exact/scale_pct`, `--width`, `--height`, `--scale` |
| `crop` | `--mode manual/ratio/autotrim`, `--ratio 16:9`, `--trim-color` |
| `rotate` | `--angle 0/90/180/270`, `--flip-h`, `--flip-v`, `--exif` |
| `watermark` | `--text "texto"`, `--color`, `--size`, `--position`, `--opacity` |
| `border` | `--padding 20`, `--color #000000`, `--fill-alpha` |
| `adjust` | `--brightness`, `--contrast`, `--saturation`, `--sharpness` |
| `filter` | `--type blur/sharpen/autocontrast/equalize/grayscale` |
| `favicon` | `--sizes 16,32,48,64,128,256` |
| `contact-sheet` | `files…`, `--cols 4`, `--thumb 200`, `--gap 10`, `--bg-color` |
| `remove-bg` | `--model u2net/u2netp/silueta/isnet-general-use/u2net_human_seg` |
| `describe` | `--model moondream-custom/llava:7b/minicpm-v`, `--prompt` |

Todos (exceto `favicon`, `describe`, `contact-sheet`) aceitam `--out-fmt` e `--out-quality`.

---

## Como adicionar um novo subcomando

1. Criar `src/cli/novo.py` com:
   - `add_novo_parser(subparsers)` — registra o parser
   - `run_novo_cli(ns)` — constrói Args, cria CLIEventBus, chama `run_novo_pipeline(..., install_log_handler=False)`
2. Em `main.py`:
   - Adicionar `"novo"` a `_NON_TRANSCRIBE_CMDS`
   - Importar e registrar em `_dispatch_other`
3. Adicionar testes em `tests/cli/test_novo_cli.py` com `@pytest.mark.unit`

---

## Padrões de argparse

### Sub-subparser (video/image)

```python
video_p = subparsers.add_parser("video", ...)
video_sub = video_p.add_subparsers(dest="video_op", required=True)

dl = video_sub.add_parser("download", ...)
dl.add_argument("url", ...)
dl.add_argument("--quality", default="1080")
video_p.set_defaults(func=run_video_cli)
```

`ns.func(ns)` é chamado em `_dispatch_other` após `parse_args`.

### Mapeamento de operação com hífen

```python
op = ns.image_op.replace("-", "_")  # "contact-sheet" → "contact_sheet"
# ou para vídeo:
op = ns.video_op if ns.video_op != "extract-audio" else "extract_audio"
```

---

## Testes CLI

Padrão: criar `_parse(*argv)` localmente com parser isolado, nunca chamar `sys.argv` diretamente.

```python
def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_audio_parser(sub)
    return parser.parse_args(["audio", *argv])

@pytest.mark.unit
def test_audio_defaults():
    ns = _parse("https://youtu.be/abc")
    assert ns.fmt == "mp3"
    assert callable(ns.func)
```

Arquivos de teste: `tests/cli/test_audio_cli.py` (5), `test_video_cli.py` (10), `test_image_cli.py` (15).
