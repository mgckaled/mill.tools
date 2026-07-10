# Design System — Contrato de eventos (`PipelineEvent`)

Fonte única do contrato de eventos da GUI: payloads por módulo, barra de progresso, thread-safety e abas
aninhadas. Abra este arquivo ao emitir/consumir eventos num `worker.py`/`view.py`/`pipeline_log.py`. Tokens,
factories e quirks do Flet ficam no [`SKILL.md`](SKILL.md).

> **Nota de manutenção (anti-drift)**: os campos exatos de cada payload derivam do `worker.py`/`pipeline_log.py`
> de cada módulo. Ao mudar um payload, **atualize aqui no mesmo PR** — este é o contrato de referência.

---

## `PipelineEvent`

`PipelineEvent(type, stage, payload, module_id)` é publicado via `page.pubsub.send_all()` (thread-safe;
worker thread → callbacks na UI thread). `module_id` ∈ {`"transcription"`, `"audio"`, `"image"`, `"video"`,
`"document"`, `"data"`, `"ai"`, `"recipes"`, `"observatory"`, `""` (legado)}. O `ProgressPanel` ignora eventos
cujo `module_id` ≠ `owner_id`; os hubs **IA**, **Receitas** e **Observatório** (só a sub-aba Índice) e a
ferramenta **Dados** são auto-contidos (assinam os próprios eventos, não usam `ProgressPanel`).

**`EventBus.emit()` grava falhas no Observatório**: além do `send_all()`, todo evento `task_error` (de
qualquer módulo) é gravado em `core/observatory/logs.py` (aba Logs), exceto cancelamentos do usuário
(mensagens com "cancel", filtradas por `_is_cancellation()`). É um hook central em `gui/events.py`, não algo
que cada `worker.py` precisa chamar — mudar o formato de `payload["message"]` de um `task_error` existente
afeta o que aparece nessa aba.

`pipeline_log.py` (por módulo) separa "o que emitir" de "como exibir": `worker.py` importa `fmt_*` p/
`emit("log", ...)`; `view.py`/`progress_view.py` importa `resolve_messages()`/`resolve_stage_label()`.

---

## Abas aninhadas

Precedente: `observatory/rag_tab.py`. Como "aba" no Flet 0.85 deste projeto é só `Row(TextButton) +
Stack(visible=)` (não um widget dedicado — ver quirk `ft.Tabs` no `SKILL.md`), aninhar é repetir o mesmo
padrão um nível dentro — sem suporte especial do framework, nem necessário. A aba externa (Índice/RAG do
Observatório) é ela própria um `(control, apply)` que internamente tem seu próprio `Row`/`Stack`/`_show_subtab`;
o `apply()` externo só delega pro sub-apply da sub-aba ativa no momento (mesmo espírito lazy-refresh-on-select
das abas de topo). Persistência de estado usa uma chave própria por nível (`last_observatory_tab` fora,
`last_observatory_rag_subtab` dentro).

---

## Tabelas de payload

### Genéricos (todos os módulos)

| Evento | Payload | Efeito na UI |
|---|---|---|
| `progress_start` | — | barra indeterminada + inicia spinner |
| `progress_update` | `current`, `total` (0–1) | barra determinada |
| `queue_progress` | `current_item`, `total_items`, `item_name` | label "Item 2/5 — arquivo.mp3" |
| `task_done` | `output_path(s)` | barra 1.0, para spinner, habilita Resultados |
| `task_error` | `message` | log de erro, para spinner |
| `log` | `message`, `level`, `mutable: bool` | passthrough colorido; `mutable=True` atualiza a última linha em vez de criar nova (progresso contínuo, ex.: download yt-dlp) |

### Áudio (stage="audio")

`audio_op_start` (`operation`, `item_name`, `item_idx`, `total`), `audio_op_done` (`output_path`, `elapsed`,
`item_idx`, `total`, `src_size_bytes`, `out_size_bytes`, **`source_path`** quando há pós-processamento → A/B,
**`loudness_stats`/`loudness_target`** quando há normalize → card de loudness). `operation` ∈ {`download`,
`convert`, `extract`, `silence`, `denoise`, `speed`, `normalize`, `encode`}. A cadeia de pós-processamento
roda em ordem fixa (silêncio → denoise → velocidade → normalize → **encode** final, que aplica `args.fmt` +
mono/sample-rate).

O `segmented_selector` aceita `with_setter=True` → retorna um 4º elemento `set_value(opt)` para seleção
programática (presets do módulo Áudio); retrocompatível (3-tupla por padrão). A **aba Visualizar**
(áudio→imagem) é auto-contida (não usa `ProgressPanel`): gera o PNG off-thread (`page.run_task` +
`asyncio.to_thread`) e tem mini-log com cronômetro/previsão (reusa `ai/timing.py`). O **loop do cursor do
`audio_player`** roda na UI event loop via `page.run_task` (não thread daemon — senão `page.update()` não
repinta até o próximo update da UI thread, atrasando o cursor).

### Vídeo (stage="video")

`video_op_start` (`operation`, `item_name`, `item_idx`, `total`), `video_op_done` (`output_path`, `elapsed`,
`item_idx`, `total`, `src_size_bytes`, `out_size_bytes`), `video_op_error` (`item_name`, `message`).
`operation` ∈ {`download`, `convert`, `trim`, `compress`, `resize`, `extract_audio`, `thumbnail`}.

### Imagens (stage="image")

`image_op_start` (`operation`, `item_name`, `item_idx`, `total_items`, `thumb: bytes|None`), `image_op_done`
(`output_path`, `elapsed`, `src_size_bytes`, `out_size_bytes`, `thumb`, `item_idx`, `total_items`),
`image_op_error` (`item_name`, `message`).

### Documentos (stage="document")

`document_op_start` (`operation`, `item_name`, `item_idx`, `total`, `page_count`), `document_op_done`
(`output_path`, `elapsed`, `operation`, `item_idx`, `total`, `extra_stats`), `document_op_error`
(`item_name`, `message`). `operation` ∈ {`merge`, `split`, `compress`, `rotate`, `watermark`, `stamp`,
`encrypt`, `extract`, `ocr`, `pdf_to_images`, `images_to_pdf`, `analyze`, `qr`}.

### Transcrição (stage específico)

`metadata_start/done`, `audio_cached`, `download_start/done`, `whisper_loading/loaded`, `transcribe_started`,
`language_detected` (`audio_duration`), `vad_filtered` (`duration`, `duration_after_vad`, `removed` — silêncio
pulado pelo VAD; `[i] VAD removed Xs of silence (Y%)`), `transcribe_segment` (`end`, `is_low_confidence`),
`transcribe_summary`, `format_*`, `analyze_*`, `translation_*`, `prompt_*`.

### IA — Conversa (module_id="ai")

Auto-contido (não usa `ProgressPanel`). `progress_start` → **[`condense_start`, só quando há histórico —
Fase 2, `PLANO_CONVERSA_MULTITURNO.md`]** → `answer_start` (`query`, `search_query`, `model_name`) →
`answer_done` (`query`/`search_query`/`text`/`sources`/`model_name`/`elapsed` + **`low_confidence`/
`best_score`**, Plano 4A — `best_score` agora é o `pool_max_score` que `retriever.retrieve()` devolve, não
mais derivado de `hits` no worker; `True` mostra um banner "o acervo não cobre bem esta pergunta" acima da
resposta) → `task_done`/`task_error`. Sem `progress_update` (um único `invoke()` bloqueante não tem fração de
progresso) — a view mostra um ticker de tempo decorrido + "típico do modelo" (`ai/timing.py`) em vez de uma
barra determinada.

- **`query` vs. `search_query`** (Fase 2): `query` é sempre a pergunta original do usuário — é o que vira o
  card do turno e entra no histórico de condensação (nunca uma reescrita, pra referências não se acumularem
  entre turnos). `search_query` é o que de fato foi usado no retrieve/answer — igual a `query` na maioria das
  perguntas (histórico vazio ou pergunta já autossuficiente); quando a condensação reescreve a pergunta, a
  view mostra uma legenda discreta "buscou por: …" no card **só** quando os dois diferem.
  `pipeline_log.fmt_query_condensed(search_query)` loga a reformulação (estágio `condense_start` no ticker →
  "Condensando pergunta…").

### Observatório — Índice/RAG (module_id="observatory")

A sub-aba Índice roda o pipeline de reindexação (Fase 0b, `PLANO_NL2CLI_HUB_IA.md`, jul/2026 — movido do hub
de IA): `progress_start` → `index_start` (`total`) → `progress_update` (`current`/`total`, mutable) →
`index_done` (`n_docs`/`n_chunks`/`added`) → `task_done`/`task_error`. Emitido por
`gui/modules/observatory/index_worker.py::run_ai_index`, consumido por `rag_tab.py` (que também refaz a
leitura de `index_stats`/`analytics` em `task_done`) — a mesma forma worker+view de um módulo-ferramenta,
não o padrão auto-contido single-file do hub de IA/Receitas. `core/observatory/` (o pacote puro) continua sem
saber nada disso — o pipeline vive só na camada `gui/`.

### Dados (module_id="data")

Eventos próprios: `data_scanned` (chips de fonte), `data_sql_ready` (`sql`/`explanation`), `data_result`
(`columns`/`rows`/`n_rows`/`elapsed`/`truncated`), `data_saved` (`output_path`); **PR9.3** acrescenta
`data_index_start`/`data_index_progress` (`current`/`total`)/`data_indexed` (`added`/`total`/`chunks`) p/ a
indexação RAG na aba Pré-visualização e `data_assess_start`/`data_assessed` (`name`/`text`) p/ a Análise com
IA. **Plano 1 (PR9.1)** acrescenta `data_plot_start`/`data_plot_done` (`png: bytes`) p/ a aba Gráfico — o
render matplotlib roda off-thread (`run_data_plot`: `run_query_arrow → frames.to_pandas → charts.render_png`)
e a UI só troca o `src` de um `ft.Image`; falha via `task_error` roteado por `ctx.action[0] == "plot"`.

O painel tem **4 abas manuais** (Consulta | Pré-visualização | Análise com IA | Gráfico — padrão
`Conversa|Índice` do hub de IA, `visible=` num `Stack`, persistidas em `last_data_tab`), cada uma com
**rodapé fixo** (ações) e **progress/log no topo**. A tabela paginada reutilizável é
`modules/data/table_view.py` (cabeçalho mostra o tipo por coluna).

> **Quirk do spinner aplicado**: eventos de progresso emitidos *enquanto o moinho gira* (`data_index_*`,
> `data_assess_start`, `data_plot_start`, `log`) fazem **update escopado** (`control.update()`) + `return` —
> nunca o `page.update()` global do fim do handler, que interromperia a animação. Regra completa do spinner →
> [`SKILL.md`](SKILL.md) (factory `spinner()`).

### Receitas (module_id="recipes")

`recipe_start` (`name`, `total_steps`), `step_start` (`op`, `label`, `idx`, `total`), `step_done` (`op`,
`idx`, `total`, `outputs`), `step_error` (`op`, `idx`, `message`); reusa `progress_*`/`task_done`/`task_error`
e, no lote, `queue_progress`. Os adaptadores de passo encaminham os eventos das funções de core (ex.:
`transcribe_segment`) sob o mesmo `module_id`.

---

## Barra de progresso (transcrição/genérico)

- **Idle**: oculta, label "Inicie o pipeline pelo formulário →". **Indeterminada**: 1º evento de início
  (`value=None`).
- **Determinada**: transcrição `transcribe_segment.end / audio_duration`; áudio
  `progress_update(current/total)`; chunks LLM `i / total`.
- **`extra_header` no `build_progress_view`**: `ft.Control | None` opcional entre a barra e o log (Áudio
  injeta o `AudioPlayer`).

---

## Thread safety

- `bus.emit()` roda na worker thread; `page.pubsub.send_all()` é thread-safe; callbacks de `subscribe` rodam
  na UI thread.
- `pipeline_running[0]` resetado em `finally` (sucesso/erro/cancelamento) — senão a navegação trava.
- Não chamar `page.update()` em cascata no mesmo evento (quirk `object_patch` IndexError → `SKILL.md`).
