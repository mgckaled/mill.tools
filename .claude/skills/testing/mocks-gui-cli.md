# Testing — workers de GUI e testes de CLI

Receitas para as duas superfícies que não têm rede/modelo, mas têm orquestração: os **workers da GUI**
(`src/gui/**/worker.py`, testáveis com um bus falso porque não dependem do Flet) e os **testes de CLI**
(`tests/cli/`, parser isolado + runner mockado). Abra este arquivo ao testar um worker ou um subcomando.

---

## Worker da GUI (`run_pipeline` / `_run_*`) — bus falso + dependências mockadas

Os workers (`src/gui/workers.py`, `src/gui/modules/<m>/worker.py`) **não dependem do Flet** — emitem por
`bus.emit(type, stage, payload, module_id=...)`. Teste com um bus falso que captura `(type, payload)` e
mocke as dependências pesadas:

```python
class _Bus:
    def __init__(self): self.events = []
    def emit(self, type, stage, payload, module_id=None):
        self.events.append((type, payload))
```

- **Transcrição** (`run_pipeline`): mocke `workers.check_dependencies` e a função LLM no namespace do worker
  (`workers.analyzer.analyze`); redirecione `workers.TRANSCRIPTIONS_TEXT_DIR` p/ `tmp_path` (o ramo texto
  **copia** o arquivo para lá, preservando o original). Asserte em `[t for t, _ in bus.events]` — ex.: `.txt`
  sem nenhuma análise → `task_error`; com `use_analyze` → `task_done` e `analyze` chamado num caminho ≠ do
  arquivo de origem.
- **Documentos** (`_run_analyze` etc.): chame o handler direto com um `emit` que acumula numa lista; o worker
  importa `analyze` **lazy** → mocke `src.analyzer.analyze`. Para fixar o ramo `.txt`, faça `get_pdf_info`
  levantar via `pytest.fail` e confirme que não foi chamado (`page_count == 0` no `document_op_start`). Ver
  `tests/gui/test_workers_text.py` e `tests/gui/modules/document/test_worker_analyze.py`.
- **IA** (`run_ai_index`/`run_ai_answer`): mesmo bus falso (assinatura `emit(type, stage, payload=None,
  module_id="")`). Passe `install_log_handler=False` p/ não tocar o root logger. Monkeypatch
  `src.core.rag.indexer.index_dir` p/ `tmp_path` (o `from ... import index_dir` é function-local → patchar o
  atributo do módulo resolve). Mocke `src.core.rag.embedder.is_available`/`embed_texts`/`embed_query` e
  `src.core.rag.chat.make_llm` (via `GenericFakeChatModel`). Asserte os `bus.types()`
  (`progress_start`/`index_done`/`answer_done`/`task_done` vs `task_error`). Cancelamento: `cancel_event.set()`
  antes → `progress_cb` levanta `_Cancelled` → `task_error` "cancelada". Ver
  `tests/gui/modules/ai/test_worker.py`.
- **Receitas** (`tests/gui/modules/recipes/test_worker.py`): bus falso `emit(type, stage, payload, module_id)`;
  mocke `src.core.recipes.runner.execute_recipe`/`execute_recipe_batch`; `install_log_handler=False`.
  Verifique forwarding sob `module_id="recipes"`, linhas de log de passo, `clean_intermediates` (escreva
  arquivos reais em `tmp_path`; só os não-finais somem) e retorno `False` sem saída/em exceção.

> Os detalhes de mock do **core** de cada worker (RAG, Receitas, LLM) ficam em
> [`mocks-llm-rag-ml.md`](mocks-llm-rag-ml.md).

---

## Padrão de teste de CLI (`tests/cli/`)

Nunca chamar `sys.argv` diretamente — criar `_parse(*argv)` local com parser isolado:

```python
def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_audio_parser(sub)
    return parser.parse_args(["audio", *argv])

@pytest.mark.unit
def test_defaults():
    ns = _parse("https://youtu.be/abc")
    assert ns.fmt == "mp3"
    assert callable(ns.func)
```

Para testar o **runner** (a função `run_*_cli` que traduz `Namespace` → `XxxArgs` e dispara a pipeline),
mocke a função de pipeline no **caminho onde ela é importada** (não onde é definida — embora aqui seja o
mesmo arquivo) e a verificação de dependências:

```python
def test_run_audio_cli_dispatches_to_pipeline(mocker):
    mocker.patch("src.utils.check_dependencies")  # ou "src.utils.setup_logging" no doc
    mock_pipeline = mocker.patch(
        "src.gui.modules.audio.worker.run_audio_pipeline",
        return_value=True,
    )
    ns = _parse("https://youtu.be/abc", "--normalize", "--lufs", "-16")
    ns.func(ns)
    assert mock_pipeline.called
    args = mock_pipeline.call_args.args[0]   # AudioArgs construído pelo runner
    assert args.normalize is True
    assert args.normalize_target_lufs == -16.0
```

Caminhos das pipelines a mockar:

| CLI         | Função a mockar                                     |
|-------------|-----------------------------------------------------|
| `audio`     | `src.gui.modules.audio.worker.run_audio_pipeline`   |
| `video`     | `src.gui.modules.video.worker.run_video_pipeline`   |
| `image`     | `src.gui.modules.image.worker.run_image_pipeline`   |
| `document`  | `src.gui.modules.document.worker.run_document_pipeline` |

Quando o runner retorna `False`, ele chama `sys.exit(1)`. Para cobrir esse caminho, use
`pytest.raises(SystemExit)` (apenas `audio`/`video`/`image` têm essa branch — `document` não).

**Gotcha kebab → snake**: operações como `extract-audio` (CLI) viram `extract_audio` em
`VideoArgs.operation`. `pdf-to-images` vira `pdf_to_images`. `contact-sheet` vira `contact_sheet`. Sempre
asserte o nome em `snake_case` no `Args` construído.

`_pipeline_runner.item_label` é testável diretamente — sempre verificar que `kind="local"` retorna
`Path(value).name` e `kind="url"` retorna o `netloc` (ver `tests/cli/test_transcription.py`).

> Os subcomandos read-only (`library`/`ai`/`data`/`observatory`) não têm bus — testam o core direto com
> `capsys`. Ver a skill `cli` para os gotchas por subcomando (UTF-8 no stdout, `log_activity` a mockar).
