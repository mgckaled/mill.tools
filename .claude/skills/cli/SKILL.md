---
name: cli
description: Guia da CLI modular do mill.tools — subcomandos audio/audio-viz/video/image/document/library/ai/recipe/data/observatory + transcribe, CLIEventBus, taxonomia (pipeline+bus vs. read-only), padrões de argparse e gotchas por subcomando. Invocar ao criar/editar subcomandos em src/cli/, adicionar flags, mexer no dispatcher de main.py ou escrever testes em tests/cli/. A referência completa de flags é o `--help` do código; detalhes de RAG/ML → skill ml-rag; receitas de teste de CLI → skill testing.
---

# mill.tools — Guia da CLI Modular

> **Referência de flags = `--help` do próprio código** (+ o bloco Comandos do `CLAUDE.md`). Esta skill cobre
> só o que **não** se descobre pelo `--help`: padrões, taxonomia e gotchas. Receitas de teste →
> [`testing/mocks-gui-cli.md`](../testing/mocks-gui-cli.md). Detalhes de `ai`/`observatory` → skill `ml-rag`.

## Visão geral

`main.py` despacha para subcomandos por prefixo do primeiro argumento:

```python
_NON_TRANSCRIBE_CMDS = frozenset({"audio", "video", "image", "document",
                                  "library", "ai", "recipe", "data", "observatory"})

def main():
    if len(sys.argv) > 1 and sys.argv[1] in _NON_TRANSCRIBE_CMDS:
        _dispatch_other(sys.argv[1])   # → src/cli/<cmd>.py
        return
    # legado: transcrição (parse_args direto)
```

`transcribe` como subcomando explícito também é aceito (`sys.argv.pop(1)` antes do parser legado).
`audio-viz` é um parser à parte em `cli/audio.py` (não passa pela fila do `audio`).

## Estrutura de arquivos

```text
src/cli/
├── bus.py            — CLIEventBus: TqdmLoggingHandler + barra tqdm (sem Flet)
├── transcription.py  — resolve_input(), build_output_stem(), add_transcribe_args()
├── reference.py       — build_reference()/validate_command() — introspecção p/ NL->CLI (ver skill ml-rag)
├── audio.py          — add_audio_parser/run_audio_cli + add_audio_viz_parser/run_audio_viz_cli
├── video.py          — add_video_parser/run_video_cli        (sub-subparsers)
├── image.py          — add_image_parser/run_image_cli        (sub-subparsers)
├── document.py       — add_document_parser/run_document_cli  (sub-subparsers)
├── library.py        — add_library_parser/run_library_cli    (read-only)
├── ai.py             — add_ai_parser/run_ai_cli              (RAG local; ver skill ml-rag)
├── recipes.py        — add_recipe_parser/run_recipe_cli      (sub-subparsers; usa CLIEventBus)
├── data.py           — add_data_parser/run_data_cli          (sub-subparsers; reusa core direto)
└── observatory.py    — add_observatory_parser/run_observatory_cli  (read-only; ver skill ml-rag)
```

---

## Taxonomia: dois tipos de subcomando

| Tipo | Subcomandos | Como funciona |
|---|---|---|
| **Pipeline + `CLIEventBus`** | `audio` · `video` · `image` · `document` · `recipe` | Constroem `XxxArgs`, criam um `CLIEventBus`, chamam `run_X_pipeline(args, bus, cancel, install_log_handler=False)`. Retorno `False` → `sys.exit(1)` (`audio`/`video`/`image` têm essa branch; `document` não). |
| **Read-only, core direto** | `library` · `ai` · `data` · `observatory` · `audio-viz` | Reusam o core puro **direto** (operações síncronas, sem progresso) → **sem `CLIEventBus`/`run_*_pipeline`**. Reconfiguram `sys.stdout` p/ UTF-8/replace antes de imprimir. |

Ao criar um subcomando, decida a que grupo pertence **antes** de escrever — isso define se há bus, cancel e
`install_log_handler`, ou se é core-direto com `capsys` nos testes.

---

## CLIEventBus (`src/cli/bus.py`)

Substitui o `EventBus` da GUI sem Flet. Exibe progresso via `tqdm` e linhas de texto. Trata `log` (→
`tqdm.write` com cor ANSI por prefixo), `progress_update` (barra 0–100%), `queue_progress` (label "Item N/M"),
os `*_op_start/done` de cada módulo (mensagens formatadas), `task_done` (fecha barra) e `task_error`.

```python
bus = CLIEventBus()
cancel = threading.Event()
success = run_X_pipeline(args, bus, cancel, install_log_handler=False)
if not success:
    sys.exit(1)
```

`install_log_handler=False` evita que o `LogEventHandler` do worker instale um handler no root logger — a CLI
já recebe os logs via `tqdm.write` pelo CLIEventBus. **Sempre** passe isso nos runners de pipeline.

---

## `resolve_input` + ramos de entrada

`resolve_input` (`src/cli/transcription.py`) classifica a entrada como URL ou arquivo local:

```python
resolve_input("https://youtu.be/abc")  # → ("url", "https://…")
resolve_input("/path/to/file.mp3")      # → ("local", "/path/…")
```

Usado por todos os runners para popular `InputItem(kind, value)`. Dois ramos merecem atenção:

- **`transcribe` (legado) ramifica pelo sufixo do arquivo local** (`main.py`): `.txt`/`.md` → pula
  download+Whisper, copia para `transcriptions/text/` e roda só `--format`/`--analyze`/`--prompt`; áudio/vídeo
  local → transcreve (vídeo decodificado via PyAV); URL → metadata + download. O ramo local checa
  `kind == "local"` (não `"file"`).
- **`--profile` (perfil de análise)**: `choices=list_profiles()` com **import lazy dentro de
  `add_transcribe_args`** (`src/cli/transcription.py` — extraído de `main.py::parse_args` na Fase 1 do
  `PLANO_NL2CLI_HUB_IA.md`, reusado pelo parser legado **e** pelo parser descartável de
  `cli/reference.py::build_reference()`). Não carregar LangChain nos demais subcomandos nem na referência do
  NL→CLI: `add_transcribe_args(parser, include_profile_choices=False)` troca `choices=list_profiles()` por
  `choices=None` — a referência só precisa que o flag exista, não da validação real de perfil. Repassado a
  `analyze(profile=...)`. Default `default` (esquema legado). Escolha inválida → `SystemExit`.

---

## Gotchas por subcomando (o que o `--help` não conta)

- **kebab → snake** (`video`/`image`/`document`): a operação vem com hífen no `Namespace`
  (`ns.image_op == "contact-sheet"`) e o runner converte com `op.replace("-", "_")` p/ o `Args`. Caso especial
  do vídeo: `"extract-audio"` → `"extract_audio"`. Nos testes, asserte sempre o nome em `snake_case` no `Args`.
- **UTF-8 no stdout** (todos os read-only + `recipe`): `run_*_cli` reconfigura `sys.stdout` p/ UTF-8/replace —
  nomes de arquivo com caracteres fora do cp1252 (ex.: `｜`) quebram o console do Windows sem isso.
- **`data query` é multi-input**: `files` (`nargs="+"`) seguido do positional `question` — argparse reserva o
  último token p/ a pergunta. `--sql` trata `question` como SQL literal e **pula** o NL→SQL da IA.
- **`ai --scope` é path-ou-kind**: `_resolve_scope` resolve um caminho existente → absoluto (1 doc); senão
  trata a string como kind (`transcription`/`document`/`image`). Ver skill `ml-rag` para o resto de `ai`.
- **`ai related <path>`** resolve o path por absoluto→basename; `ai map --method` aceita `pca|tsne|umap`
  (TSNE já vem no `[ml]`, sem exigir `[ml-viz]`).
- **`log_activity` a mockar**: subcomandos que gravam no log do Observatório no caminho de sucesso —
  `library dedup-images`, `ai dups`, `ai classify`, `data outliers` — chamam
  `core.observatory.activity.log_activity`. **Mocke** nos testes, senão a suíte escreve no
  `~/.mill-tools/ml_activity.json` real.
- **`recipe` tem runner real**: diferente dos outros read-only, Receitas usa `execute_recipe` (mesmo core da
  GUI) + `CLIEventBus`; `_make_emit` traduz `recipe_start`/`step_*` em linhas de log. `--model` sobrescreve só
  o Whisper dos passos `transcription.transcribe`.
- **`ai --cmd` é NL→CLI, não a Conversa** (`PLANO_NL2CLI_HUB_IA.md`, Fase 4): com a flag, `query` vira um
  pedido em português traduzido para o comando `uv run main.py ...` equivalente (`_nl2cli`, mesma amarração
  do worker da GUI — `core/text/nl2cli.to_command` + `cli/reference.build_reference`/`validate_command`).
  **Prioridade sobre os fluxos de palavra-chave**: `ai --cmd stats` não roda `_stats()`, gera um comando pra
  a palavra "stats". Gate só de `ollama_inventory().reachable` (não o embedder) — pulado p/ modelo de nuvem
  via `llm_factory.is_cloud_model`. Detalhe de arquitetura → skill `ml-rag`.

> Receitas de teste (patch targets por subcomando, `_parse(*argv)`, `sys.exit` branches) →
> [`testing/mocks-gui-cli.md`](../testing/mocks-gui-cli.md).

---

## Como adicionar um novo subcomando

1. Criar `src/cli/novo.py` com:
   - `add_novo_parser(subparsers)` — registra o parser.
   - `run_novo_cli(ns)` — decide o tipo (taxonomia acima): pipeline+bus → constrói Args, `CLIEventBus`,
     `run_novo_pipeline(..., install_log_handler=False)`; read-only → chama o core direto + UTF-8 stdout.
2. Em `main.py`: adicionar `"novo"` a `_NON_TRANSCRIBE_CMDS` + importar/registrar em `_dispatch_other`.
3. Testes em `tests/cli/test_novo_cli.py` com `@pytest.mark.unit` (padrão em `testing/mocks-gui-cli.md`).

---

## Padrões de argparse

### Sub-subparser (video/image/document/recipe/data/observatory)

```python
video_p = subparsers.add_parser("video", ...)
video_sub = video_p.add_subparsers(dest="video_op", required=True)

dl = video_sub.add_parser("download", ...)
dl.add_argument("url", ...)
dl.add_argument("--quality", default="1080")
video_p.set_defaults(func=run_video_cli)   # os sub-subparsers não redefinem func
```

`ns.func(ns)` é chamado em `_dispatch_other` após `parse_args`.

### Mapeamento de operação com hífen

```python
op = ns.image_op.replace("-", "_")  # "contact-sheet" → "contact_sheet"
op = ns.video_op if ns.video_op != "extract-audio" else "extract_audio"
```

### `ai` é a exceção: um único positional

`ai` **não** usa sub-subparser — tem um positional `query` que é despachado por valor literal (`index`/
`stats`/`dups`/`topics`/`map`/`related` são fluxos de ML; qualquer outro valor é a pergunta). Ver skill
`ml-rag`.
