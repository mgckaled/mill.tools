---
name: cli
description: Guia da CLI modular do mill.tools (subcomandos audio/video/image/document +
  transcribe, CLIEventBus, padrões de argparse). Invocar ao criar/editar subcomandos em
  src/cli/, adicionar flags, mexer no dispatcher de main.py ou escrever testes em tests/cli/.
---

# mill.tools — Guia da CLI Modular

## Visão geral

`main.py` despacha para subcomandos por prefixo do primeiro argumento:

```python
_NON_TRANSCRIBE_CMDS = frozenset({"audio", "video", "image", "document", "library", "ai", "recipe", "data"})

def main():
    if len(sys.argv) > 1 and sys.argv[1] in _NON_TRANSCRIBE_CMDS:
        _dispatch_other(sys.argv[1])   # → src/cli/{audio,video,image,document,library,ai,recipes,data}.py
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
├── video.py          — add_video_parser() + run_video_cli()    (sub-subparsers)
├── image.py          — add_image_parser() + run_image_cli()    (sub-subparsers)
├── document.py       — add_document_parser() + run_document_cli()  (sub-subparsers)
├── library.py        — add_library_parser() + run_library_cli()  (read-only, sem CLIEventBus)
├── ai.py             — add_ai_parser() + run_ai_cli()  (RAG local; index / pergunta / --batch)
├── recipes.py        — add_recipe_parser() + run_recipe_cli()  (recipe list / run; usa CLIEventBus)
└── data.py           — add_data_parser() + run_data_cli()  (query/convert/profile; reusa core direto)
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
- `audio_op_start/done`, `video_op_start/done`, `image_op_start/done`, `document_op_start/done` → mensagens formatadas
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

> **`transcribe` (legado) ramifica pelo sufixo do arquivo local** (`main.py`):
> `.txt`/`.md` → pula download+Whisper, copia para `transcriptions/text/` e roda
> só `--format`/`--analyze`/`--prompt`; áudio/vídeo local → transcreve (vídeo é
> decodificado via PyAV); URL → metadata + download. O ramo local checa
> `kind == "local"` (não `"file"`).

> **`--profile` (perfil de análise)**: `transcribe ... --analyze --profile <id>` escolhe
> o esquema/prompt da análise (`src/analysis`). `choices=list_profiles()` (import lazy
> dentro de `parse_args` para não carregar LangChain nos demais subcomandos); repassado a
> `analyze(profile=...)`. Default `default` (esquema legado de 10 campos). Ids Tier 1:
> `default`/`lecture`/`interview`/`tutorial`/`scientific`/`administrative`/`notes`. O
> standalone `uv run -m src ... --profile <id>` também aceita. Nos testes, asserir
> `ns.profile` no parser (escolha inválida → `SystemExit`).

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
| `--mono` | off | Downmix p/ 1 canal (`-ac 1`) no encode final |
| `--sample-rate` | None | Reamostra (`-ar`): 16000/22050/44100/48000 (16k = Whisper) |
| `--trim-silence` | off | Remove silêncio início/fim/meio (`silenceremove`) |
| `--silence-threshold` | `-40.0` | Limiar dBFS (só com `--trim-silence`) |
| `--silence-min` | `0.5` | Silêncio mínimo em s (só com `--trim-silence`) |
| `--speed` | `1.0` | Velocidade sem pitch (`atempo`), faixa 0.5–4.0 |
| `--denoise` | off | Spectral gating pós-conversão |
| `--denoise-adaptive` | off | Ruído adaptativo (não-estacionário) |
| `--normalize` | off | Loudnorm EBU R128 pós-conversão |
| `--lufs` | `-14.0` | Alvo LUFS (só com `--normalize`) |
| `--verbose` | off | Logging DEBUG |

Auto-detecção de operação: URL → download; vídeo local → extração; áudio → conversão. Cadeia de pós-processamento (ordem fixa): silêncio → denoise → velocidade → normalize → encode final (`--mono`/`--sample-rate` + formato).

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
| `subtitle` | arquivo | `--subs PATH` (obrigatório, `.srt`/`.vtt`), `--mode soft\|hard` |

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
| `crop` | `--mode manual/ratio/autotrim/focal`, `--ratio 16:9`, `--trim-color`, `--focal-x`, `--focal-y` (modo `focal` = smart crop) |
| `rotate` | `--angle 0/90/180/270`, `--flip-h`, `--flip-v`, `--exif` |
| `watermark` | `--mode text/image/qr`, `--text "texto/payload"`, `--image logo.png`, `--color`, `--size`, `--position` (9-grid \| `tile`), `--opacity`, `--rotation` |
| `border` | `--padding 20`, `--color #000000`, `--fill-alpha` |
| `adjust` | `--brightness`, `--contrast`, `--saturation`, `--sharpness` |
| `filter` | `--type blur/sharpen/autocontrast/equalize/grayscale` |
| `favicon` | `--sizes 16,32,48,64,128,256` |
| `contact-sheet` | `files…`, `--cols 4`, `--thumb 200`, `--gap 10`, `--bg-color` |
| `remove-bg` | `--model u2net/…`, `--bg-mode transparent/color/blur/image`, `--bg-color`, `--bg-blur`, `--bg-image` |
| `describe` | `--model moondream-custom/gemma3-4b-custom/llava:7b/minicpm-v`, `--prompt` |
| `exif` | `--show` \| `--strip` \| `--strip-gps` \| `--artist`/`--copyright`/`--description` (inject), `--out` (read/write direto, sem pipeline) |
| `ocr` | `--lang por/eng/por+eng/spa` (Tesseract → `<stem>_ocr.txt`, indexável no RAG) |

Todos (exceto `favicon`, `describe`, `contact-sheet`, `exif`, `ocr`) aceitam `--out-fmt` e `--out-quality`. `exif` é direto sobre o core (não passa pelo pipeline/`check_dependencies`).

---

## Subcomando `document`

```bash
uv run main.py document <operação> <entrada> [opções]
```

Usa sub-subparsers. `ns.document_op` contém a operação. Mapeamento kebab → snake: `op.replace("-", "_")` (ex.: `"pdf-to-images"` → `"pdf_to_images"`).

| Operação | Entrada | Flags principais |
|---|---|---|
| `merge` | múltiplos PDFs | `files…` |
| `split` | PDF | `--pages "1-3,5,8-"` |
| `compress` | PDF | `--image-quality 75` (50–95) |
| `rotate` | PDF | `--angle 90/180/270`, `--pages "all"` |
| `watermark` | PDF | `--text "texto"`, `--opacity 0.3`, `--position center/top/bottom` |
| `stamp` | PDF | `--text "PAGO"` |
| `encrypt` | PDF | `--password "senha"` |
| `extract` | PDF | — |
| `ocr` | PDF | `--lang por/eng/por+eng/spa` (dest `ocr_lang`), `--dpi 150/300` (dest `ocr_dpi`) |
| `pdf-to-images` | PDF | `--fmt jpg/png`, `--dpi 72/96/150/300` |
| `images-to-pdf` | imagens | `files…`, `--name "stem"` |
| `qr` | texto/URL | `data` (posicional), `--size 300`, `--fmt png/jpg` |

Sem operação `analyze` na CLI (apenas GUI).

---

## Subcomando `library`

```bash
uv run main.py library list [opções]
```

**Read-only** — lista tudo sob `output/` numa tabela. Reaproveita o core
(`scan_library`/`filter_items`/`sort_items`); **não** usa pipeline nem
`CLIEventBus`. Usa sub-subparser (`ns.library_op`), por ora só `list`.

| Flag | Default | Descrição |
|---|---|---|
| `--kind` | (todos) | `audio`/`video`/`image`/`transcription`/`document` |
| `--since` | — | Duração: `7d`, `24h`, `30m` (número puro = dias). `_parse_since` levanta `ValueError` em formato inválido |
| `--sort` | `modified` | `modified`/`name`/`size` |
| `--verbose` | off | Logging DEBUG |

`run_library_cli` reconfigura `sys.stdout` para UTF-8/replace antes de imprimir
(nomes de arquivo com caracteres fora do cp1252, ex.: `｜`, quebram o console
do Windows).

> Atenção: `library` foge do padrão dos demais — não há `CLIEventBus`,
> `install_log_handler` nem `run_*_pipeline` a mockar. Nos testes, mocke
> `src.cli.library.scan_library` e capture stdout via `capsys`.

---

## Subcomando `ai`

```bash
uv run main.py ai index                                  # (re)indexa o corpus
uv run main.py ai stats                                  # resumo do índice (read-only)
uv run main.py ai dups [--threshold 0.95] [--scope kind] # duplicatas (ML, read-only)
uv run main.py ai topics                                 # clusters + rótulos c-TF-IDF ([ml])
uv run main.py ai map [--method pca|umap] [--out p.png]  # PNG do mapa semântico ([ml])
uv run main.py ai related <path> [--k 5]                 # vizinhos por cosseno (numpy)
uv run main.py ai classify <path>                        # perfil sugerido + confiança/margem (4B)
uv run main.py ai keywords <path> [--top 10]             # keyphrases YAKE ([nlp], 4B)
uv run main.py ai summary <path> [--sentences 5]         # resumo extractivo TextRank ([ml], 4B)
uv run main.py ai entities <path>                        # entidades spaCy NER ([nlp]+modelo, 4B)
uv run main.py ai "pergunta?"                            # responde, citando fontes
uv run main.py ai "resuma" --scope output/.../x.txt      # um documento
uv run main.py ai "liste as ações" --batch --kind transcription
uv run main.py ai "..." --model gemini-2.5-flash --k 8
```

**Um único positional** `query` (não usa sub-subparser): se for o literal
`index` → (re)indexa e retorna; se for `stats` → imprime o resumo do índice
(`_stats()`, **read-only**, reaproveita `src.core.rag.stats.index_stats`, **não**
toca o embedder/Ollama) e retorna; se for `dups` → imprime grupos de documentos
quase-idênticos (`_dups()`, **read-only/sem embedder** — fundação de ML do Plano 3:
`features.document_matrix` faz mean-pool do `VectorStore` e `dedup.near_duplicates`
agrupa por cosseno; `--scope` aqui é só kind, `--threshold` ajusta o limiar) e
retorna; se for `topics`/`map`/`related` → camada semântica do Plano 4A
(`_topics`/`_map`/`_related`, read-only/sem embedder): `topics` clusteriza e lista
os grupos com rótulos c-TF-IDF, `map` salva o PNG do mapa em `--out`
(default `DATA_DIR/semantic_map.png`, `--method pca|umap`), `related <path>` lista
vizinhos por cosseno (resolve o path por absoluto→basename). topics/map exigem `[ml]`
(+ extras de gráfico no map); `related` é numpy-puro. Todos retornam; senão é a
pergunta. Reaproveita o core
(`scan_library`/`build_index`/`retrieve`/`answer`); **não** usa `CLIEventBus`
nem `run_*_pipeline` (como `library`). Embeddings **sempre locais** (Ollama);
Gemini só no passo de resposta. `run_ai_cli` reconfigura `sys.stdout` p/ UTF-8.

`ai stats` imprime cabeçalho (docs · chunks · dim · modelo de embedding ·
tamanho em disco · atualizado em · local) + tabela por documento
(nome · tipo · #chunks · data). Índice vazio → dica para rodar `ai index`
(sem `sys.exit`, pois é só leitura).

| Flag | Default | Descrição |
|---|---|---|
| `query` (posicional) | — | Pergunta, ou `index`/`stats`/`dups`/`topics`/`map`/`related` (fluxos de ML) |
| `target` (posicional opcional) | — | Com `related`, o caminho do documento (absoluto ou basename) |
| `--threshold` | `0.95` | Com `dups`, cosseno mínimo p/ agrupar documentos |
| `--method` | `pca` | Com `map`, projeção 2D (`pca` / `umap` exige `[ml-viz]`) |
| `--out` | — | Com `map`, caminho do PNG (default `output/data/semantic_map.png`) |
| `--scope` | (acervo) | Caminho de arquivo (1 doc) **ou** kind (`transcription`/`document`/`image`). `_resolve_scope` resolve path existente → absoluto; senão trata como kind |
| `--model` | `qwen7b-custom` | Modelo da resposta — Ollama tag ou `gemini-2.5-flash` |
| `--embed-model` | `nomic-embed-custom` | Modelo de embedding (sempre local, CPU `num_gpu 0`; ver `ollama/Modelfile.nomic`) |
| `--k` | `6` | Trechos recuperados |
| `--reindex` | off | Reindexa antes de responder |
| `--batch` | off | Aplica a pergunta como instrução a **cada** documento indexado |
| `--kind` | — | Com `--batch`, restringe a um kind |

> Nos testes (`tests/cli/test_ai_cli.py`): mocke `src.core.rag.embedder.is_available`
> e os runners `src.cli.ai._build`/`_ask`/`_batch`/`_stats` para validar o dispatch;
> para `_build`/`_ask`/`_batch` em si, monkeypatch `src.core.rag.indexer.index_dir`
> p/ `tmp_path`, mocke `embedder.embed_texts`/`embed_query` e
> `src.core.rag.chat.make_llm` (via `GenericFakeChatModel`). `query == "index"`
> e os erros (índice vazio / embedder indisponível) chamam `sys.exit(1)` →
> `pytest.raises(SystemExit)`. Para `_stats`, basta `_persisted_store(tmp_path)` +
> monkeypatch de `indexer.index_dir` + `capsys` (não toca embedder; índice vazio
> **não** chama `sys.exit`).

---

## Subcomando `recipe`

```bash
uv run main.py recipe list                                    # presets + receitas salvas
uv run main.py recipe run "Limpar áudio do YouTube" <URL>     # roda por nome
uv run main.py recipe run "YouTube → transcrição completa" <URL> --model medium
```

Usa **sub-subparsers** (`ns.recipe_op` ∈ {`list`, `run`}); `set_defaults(func=run_recipe_cli)`
no parser `recipe` (os sub-subparsers não redefinem `func`). Diferente de
`library`/`ai`: Receitas **tem** um runner real (`execute_recipe`), então segue o
padrão dos runners normais — `run_recipe_cli` resolve a receita (presets +
`store.load_recipes`), monta `initial_inputs`+`initial_kind` via `resolve_input`
+ `kind_for` (de `src/core/recipes/inputs.py`), cria um `CLIEventBus` e chama
`execute_recipe` (mesmo core da GUI). Um `_make_emit` traduz `recipe_start`/
`step_*` em linhas de log e repassa os genéricos (`progress_*`/`task_done`). UTF-8
no stdout (nomes com `｜`). `--model` sobrescreve só o Whisper dos passos
`transcription.transcribe`.

| Flag | Default | Descrição |
|---|---|---|
| `recipe_op` (`list`/`run`) | — | sub-subcomando |
| `name` (posicional de `run`) | — | nome da receita (ver `recipe list`) |
| `input` (posicional de `run`) | — | URL ou caminho de arquivo |
| `--model` | — | sobrescreve o Whisper dos passos de transcrição |

> Nos testes (`tests/cli/test_recipe_cli.py`): `_parse(*argv)` com parser isolado;
> mocke `src.core.recipes.runner.execute_recipe` (importado function-local em
> `run_recipe_cli`) p/ validar o dispatch (`initial_inputs`/`initial_kind`/`emit`/
> `cancel_is_set`); `src.core.recipes.store.load_recipes` p/ os ramos de
> `_find_recipe`/`list`; receita inexistente, saída vazia e arquivo de extensão
> não suportada chamam `sys.exit(1)` → `pytest.raises(SystemExit)`. `_make_emit`
> é testável direto com um bus falso.

---

## Subcomando `data`

```bash
uv run main.py data query <arquivos...> "<pergunta>" [--sql] [--out csv|xlsx|json|parquet] [--name] [--limit]
uv run main.py data convert <arquivo> [--out parquet]
uv run main.py data profile <arquivo>
uv run main.py data assess <arquivo> [--model gemma3-4b-custom] [--no-cache]
```

Usa **sub-subparsers** (`ns.data_op` ∈ {`query`, `convert`, `profile`, `assess`}); `set_defaults(func=run_data_cli)`
no parser `data`. Como `library`/`ai`, **reusa o core puro direto** (`src/core/data/`) — operações
síncronas, sem progresso → **sem `CLIEventBus`/`run_*_pipeline`**. `run_data_cli` reconfigura
`sys.stdout` p/ UTF-8 (valores com caracteres fora do cp1252). `query` é **multi-input** (`files`
`nargs="+"` seguido do positional `question` — argparse reserva o último p/ a pergunta); `--sql`
pula o NL→SQL; em PT mostra a explicação da IA + o SQL (espelha o cartão de revisão da GUI) antes
da tabela; `--out` salva em `output/data/`.

| Flag | Default | Descrição |
|---|---|---|
| `files` (posicional, `query`) | — | Um ou mais arquivos de dados (CSV/TSV/JSON/Parquet/XLSX) |
| `question` (posicional, `query`) | — | Pergunta em PT, ou a consulta SQL com `--sql` |
| `--sql` | off | Trata `question` como SQL literal (pula a IA) |
| `--model` | `gemma3-4b-custom` | Modelo da tradução PT→SQL |
| `--out` | — (`csv` no convert) | Formato de saída: `csv`/`tsv`/`json`/`parquet`/`xlsx` |
| `--name` | `consulta` | Nome do arquivo de saída (sem extensão) |
| `--limit` | `50` | Linhas exibidas na prévia |
| `--no-cache` (`assess`) | off | Ignora a avaliação cacheada e força uma nova |

`assess <arquivo>` (PR9.3) roda o parecer de qualidade da IA (esquema + `SUMMARIZE` +
amostra, nunca as linhas), imprime o Markdown e **cacheia** o resultado em
`~/.mill-tools/data_assessments.json` (reaproveitado pela indexação); por padrão reusa
a avaliação cacheada se houver. `--model` = modelo do parecer.

> Nos testes (`tests/cli/test_data_cli.py`): `_parse(*argv)` isolado; mocke `src.cli.data.run_query`/
> `src.cli.data.nl2sql.to_sql`/`src.cli.data.convert.*`/`src.cli.data.profile.profile_file` p/ o
> dispatch; `--sql` deve **não** chamar `to_sql`; arquivo inexistente/ não suportado → `sys.exit(1)`.
> Para `assess`, mocke `src.core.data.assess.load_cached_assessment`/`assess`/`save_assessment`
> (cache hit não chama `assess`; `--no-cache` força e salva).

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

Arquivos de teste: `tests/cli/test_audio_cli.py` (5), `test_video_cli.py` (14, inclui `subtitle`), `test_image_cli.py` (15), `test_document_cli.py` (inclui `ocr`), `test_library_cli.py` (parser + `_parse_since` + runner com `scan_library` mockado e `capsys`).
