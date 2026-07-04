# Plano de implementação — GUI Flet: cadência fiel ao CLI + layout split

> **Objetivo**: refatorar a GUI Flet para (1) replicar exatamente a cadência de logs e a sequência do CLI no painel direito e (2) adotar layout split (form fixo à esquerda, pipeline expansível à direita).
>
> Divisão em dois PRs sequenciais. PR 1 é invisível ao layout (mudanças de instrumentação e cadência); PR 2 é a refatoração visual. Implementar nessa ordem — se PR 2 quebrar, PR 1 continua válido isoladamente.

---

## 1. Estado atual (resumo)

- Navegação por views: `form → progress → result`, cada uma ocupando a janela inteira.
- `workers.py` emite eventos discretos via `EventBus` (page.pubsub).
- `progress_view._resolve_message` traduz eventos em strings genéricas tipo "Carregando modelo Whisper..." — perde a riqueza dos logs do CLI (`[*] Loading model 'small' on CUDA (int8_float32)...`).
- `LogEventHandler` existe em `events.py` mas **não está registrado em `logging.root`** — todos os `logging.info/debug` do código atual ficam invisíveis na GUI.
- Barra de progresso indeterminada durante transcrição, apesar de `info.duration` estar disponível.
- `print_summary` do CLI não tem equivalente na GUI.

---

## 2. Princípios de design

1. **CLI permanece intocado**. `main.py` continua funcionando exatamente como hoje. Zero regressão.
2. **GUI é um espelho do terminal**. A coluna direita deve reproduzir, linha por linha, a mesma sequência de logs que o usuário veria rodando `uv run main.py ... --verbose` (incluindo prefixos `[i] [*] [~] [✓] [!] [»] [d]`).
3. **Eventos explícitos para etapas estruturais**, logging captura para detalhe granular. Não duplicar: se um evento `transcribe_started` é emitido pelo worker, o `LogEventHandler` deve filtrar o `logging.info("[~] Transcribing...")` do `transcriber.py` para não aparecer duas vezes.
4. **Thread safety**: worker roda em thread daemon; toda atualização de UI passa por `page.pubsub.send_all()` (já é o caso).

---

# PR 1 — Cadência fiel ao CLI (invisível ao layout)

## 1.1 Eventos novos a adicionar

### Em `src/gui/workers.py`

Atualmente o worker pula a etapa de metadata e emite `download_start` direto. Inserir antes:

```python
emit("metadata_start", "download", {"url": args.url})
video_id = extract_video_id(args.url)
meta = fetch_metadata(args.url)
emit("metadata_done", "download", {
    "title": meta.get("title", ""),
    "channel": meta.get("channel", ""),
    "duration": meta.get("duration", 0),
})
```

Detectar cache hit de áudio e emitir evento diferente:

```python
audio_path = AUDIOS_DIR / f"{audio_slug}.mp3"
if audio_path.exists():
    emit("audio_cached", "download", {"audio_path": str(audio_path)})
else:
    emit("download_start", "download", {"url": args.url})
    AUDIOS_DIR.mkdir(parents=True, exist_ok=True)
    download_audio(args.url, audio_path)
    emit("download_done", "download", {"audio_path": str(audio_path)})
```

Emitir `summary` ao final, antes de `pipeline_done`:

```python
emit("transcribe_summary", "pipeline", {
    "title": meta.get("title", "n/a"),
    "duration": meta.get("duration", 0),
    "output_path": str(output_path),
    "elapsed": elapsed_total,
    "flagged_count": flagged_count,  # vir do retorno de transcribe()
})
```

### Em `src/transcriber.py`

Após `model.transcribe`, emitir o `language_detected` que hoje não existe:

```python
segments, info = model.transcribe(...)
_emit("language_detected", {
    "language": info.language,
    "confidence": info.language_probability,
    "audio_duration": info.duration,
})
```

O evento `transcribe_done` já existe — confirmar que payload inclui `flagged_count` (já inclui). Vai ser usado pelo `progress_view` para renderizar o aviso amarelo `[!] N segment(s) flagged as low-confidence [?] — review recommended`.

> ⚠️ `transcribe()` precisa retornar `(elapsed, flagged_count)` em vez de só `elapsed`. Atualizar a assinatura e a chamada no `workers.py`. **NÃO atualizar em `main.py`** se isso quebrar — alternativa: emitir `flagged_count` apenas via `on_event` e manter retorno atual.

### Em `src/formatter.py`, `src/analyzer.py`, `src/prompter.py`

Já emitem `_chunk_start/done` com tempo decorrido. Confirmar que payload de `_chunk_done` inclui `elapsed` (em alguns casos `progress_view` lê `p.get("elapsed", "?")`).

## 1.2 Instalação do `LogEventHandler`

Em `workers.py`, ao iniciar o pipeline:

```python
def run_pipeline(args, bus, cancel_event):
    handler = LogEventHandler(bus)
    handler.setLevel(logging.DEBUG)  # captura tudo
    handler.setFormatter(logging.Formatter("%(message)s"))

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    original_level = root_logger.level
    root_logger.setLevel(logging.DEBUG)

    try:
        # ... pipeline atual ...
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(original_level)
```

Filtrar duplicação: o `LogEventHandler.emit` deve ignorar mensagens que correspondem a eventos estruturais. Manter um set de prefixos suprimidos:

```python
class LogEventHandler(logging.Handler):
    # Mensagens que já são emitidas como eventos estruturais
    _SUPPRESSED_PREFIXES = (
        "[~] Transcribing",   # já vira transcribe_started
        "[i] Detected language",  # já vira language_detected
        "[*] Loading model",  # já vira whisper_loading
        "[i] Fetching video metadata",  # já vira metadata_start
        "[»] Audio already exists",  # já vira audio_cached
        "[i] Downloading audio",  # já vira download_start
    )

    def emit(self, record):
        try:
            msg = self.format(record)
            if any(msg.startswith(p) for p in self._SUPPRESSED_PREFIXES):
                return
            self._bus.emit("log", "system", {
                "message": msg,
                "level": record.levelname,
            })
        except Exception:
            self.handleError(record)
```

## 1.3 Mapeamento exato de mensagens

Em `progress_view._resolve_message`, atualizar para reproduzir os prefixos do CLI:

| Evento | Mensagem GUI |
|---|---|
| `metadata_start` | `[i] Fetching video metadata...` |
| `metadata_done` | `[i] Title: {title}` + `[i] Duration: {format_duration(duration)}` (duas linhas) |
| `audio_cached` | `[»] Audio already exists, skipping download: {audio_path}` |
| `download_start` | `[i] Downloading audio...` |
| `download_done` | `[✓] Audio downloaded: {audio_path}` |
| `whisper_loading` | `[*] Loading model '{model_size}' on {device.upper()} ({compute_type})...` (precisa adicionar `model_size`, `device`, `compute_type` ao payload do `_emit("whisper_loading")` em `transcriber.py`) |
| `whisper_loaded` | `[d] Model loaded in {elapsed:.1f}s` |
| `transcribe_started` | `[~] Transcribing... (this may take a while for long videos)` |
| `language_detected` | `[i] Detected language: {language} ({confidence*100:.0f}% confidence)` |
| `transcribe_segment` | `{text.strip()}` ou `{text.strip()} [?]` se `is_low_confidence` |
| `transcribe_done` | `[✓] Transcription saved` + se `flagged_count > 0`: `[!] {flagged_count} segment(s) flagged as low-confidence [?]` |
| `format_started` | `[*] Formatting: {input_name}` + `[*] Format model: {model_name}` |
| `format_chunk_start` | `[~] Formatting chunk {i}/{total}...` |
| `format_chunk_done` | `[d] Chunk {i} done in {elapsed:.1f}s` |
| `format_done` | `[✓] Formatted in place ({elapsed:.0f}s)` |
| `analyze_started` | `[*] Analyzing: {input_name}` + `[*] Model: {model_name}` |
| `analyze_chunk_start` | `[~] Analyzing chunk {i}/{total}...` |
| `analyze_chunk_done` | `[d] Chunk {i} done in {elapsed:.1f}s` |
| `analyze_merge_start` | `[~] Merging {n} partial analyses...` |
| `language_detected` (analyzer) | `[~] Detecting analysis language...` + `[i] Detected language: {lang}` |
| `translation_start` | `[~] Translating analysis to PT-BR...` |
| `translation_done` | `[✓] Translation complete.` |
| `analyze_done` | `[✓] Analysis saved to: {output_path} ({elapsed:.0f}s)` |
| `prompt_started` | `[*] Building prompt-ready: {input_name}` + `[*] Prompt model: {model_name}` |
| `prompt_chunk_start` | `[~] Condensing chunk {i}/{total}...` |
| `prompt_chunk_done` | `[d] Chunk {i} done in {elapsed:.1f}s` |
| `prompt_done` | `[✓] Prompt-ready saved to: {output_path} ({elapsed:.0f}s)` |
| `transcribe_summary` | Renderizar como **card** (ver seção 1.5) |
| `pipeline_done` | `[✓] Pipeline complete.` |
| `pipeline_error` | `[!] Error: {message}` em vermelho |

Cores por prefixo:

- `[*]` → ciano (etapa principal)
- `[~]` → amarelo (em execução)
- `[i]` → azul claro (informação)
- `[✓]` → verde (sucesso)
- `[!]` → vermelho (aviso/erro)
- `[»]` → cinza (skip/cache)
- `[d]` → cinza claro (debug)
- segmentos de transcrição → branco

Implementar parsing simples:

```python
def _color_for_prefix(msg: str) -> str:
    if msg.startswith("[*]"): return ft.Colors.CYAN_300
    if msg.startswith("[~]"): return ft.Colors.YELLOW_300
    if msg.startswith("[i]"): return ft.Colors.BLUE_300
    if msg.startswith("[✓]"): return ft.Colors.GREEN_300
    if msg.startswith("[!]"): return ft.Colors.RED_300
    if msg.startswith("[»]"): return ft.Colors.GREY_400
    if msg.startswith("[d]"): return ft.Colors.GREY_500
    return ft.Colors.WHITE
```

## 1.4 Barra de progresso determinada na transcrição

`transcribe_segment` já carrega `start` e `end` do segmento. Adicionar `audio_duration` ao payload de `language_detected` (já proposto acima). Em `progress_view._resolve_progress`:

```python
# Estado mantido no closure de build_progress_view
audio_duration: list[float] = [0.0]

# ao receber language_detected
if event.type == "language_detected":
    audio_duration[0] = event.payload.get("audio_duration", 0)

# ao receber transcribe_segment
if event.type == "transcribe_segment" and audio_duration[0] > 0:
    end = event.payload.get("end", 0)
    return min(end / audio_duration[0], 1.0)
```

## 1.5 Card de resumo (substitui `print_summary`)

Quando receber `transcribe_summary`, em vez de uma linha de log, criar um `ft.Container` estilizado e inserir no log_list:

```python
def _make_summary_card(payload: dict) -> ft.Control:
    return ft.Container(
        margin=ft.Margin(top=8, bottom=8, left=0, right=0),
        padding=12,
        border=ft.border.all(1, ft.Colors.GREEN_700),
        border_radius=6,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.GREEN_400),
        content=ft.Column(
            spacing=4,
            controls=[
                ft.Text("=" * 50, size=10, color=ft.Colors.GREEN_300),
                ft.Text(f"title    : {payload['title']}", size=12, font_family="monospace"),
                ft.Text(f"duration : {format_duration(payload['duration'])}", size=12, font_family="monospace"),
                ft.Text(f"output   : {payload['output_path']}", size=12, font_family="monospace"),
                ft.Text(f"elapsed  : {format_elapsed(payload['elapsed'])}", size=12, font_family="monospace"),
                ft.Text("=" * 50, size=10, color=ft.Colors.GREEN_300),
            ],
        ),
    )
```

Importar `format_duration` de `src.utils` e `format_elapsed` de `src.transcriber`.

## 1.6 Stage label dinâmico

Atualizar `_resolve_stage_label` para incluir as novas etapas:

```python
case "metadata_start": return "Buscando metadados..."
case "audio_cached":   return "Áudio em cache."
case "download_start": return "Baixando áudio..."
```

## 1.7 Checklist do PR 1

- [ ] `workers.py`: emitir `metadata_start`, `metadata_done`, `audio_cached` (com cache hit detection), `transcribe_summary`
- [ ] `workers.py`: instalar/desinstalar `LogEventHandler` em `logging.root` no try/finally
- [ ] `transcriber.py`: payload de `whisper_loading` deve incluir `model_size`, `device`, `compute_type`
- [ ] `transcriber.py`: emitir `language_detected` com `language`, `confidence`, `audio_duration`
- [ ] `transcriber.py`: retornar `(elapsed, flagged_count)` ou expor via `on_event("transcribe_done", {...})`
- [ ] `events.py`: `LogEventHandler.emit` filtra prefixos suprimidos
- [ ] `progress_view.py`: `_resolve_message` reescrito com mapeamento da seção 1.3
- [ ] `progress_view.py`: cores por prefixo de log via `_color_for_prefix`
- [ ] `progress_view.py`: barra determinada usando `audio_duration` + `segment.end`
- [ ] `progress_view.py`: renderizar `transcribe_summary` como card estilizado
- [ ] Smoke test: rodar `uv run main.py <URL> --verbose` e comparar saída terminal com `uv run gui.py` rodando o mesmo URL — devem ser equivalentes linha por linha (modulo timestamps)
- [ ] Smoke test CLI: garantir que `uv run main.py <URL> --format --analyze --prompt` continua funcionando idêntico (regressão zero)

---

# PR 2 — Layout split

## 2.1 Mockup-alvo

```
┌─ AppBar: yt-transcriber ─────────────────────[🌙]┐
├──────────────────┬───────────────────────────────┤
│  FORM            │  PIPELINE                     │
│  width=380       │  expand=True                  │
│  scroll AUTO     │                               │
│                  │  ▸ Pipeline | Resultados      │
│  Vídeo           │                               │
│  [URL_________]  │  Etapa: Transcrevendo...      │
│                  │  [████████░░░░░░░░] 64%       │
│  Transcrição     │                               │
│  Whisper [▼]     │  [i] Fetching metadata...     │
│  Language [▼]    │  [i] Title: ...               │
│  Beam ●──○ 1     │  [»] Audio cached             │
│                  │  [*] Loading model 'small'... │
│  ☑ Format        │  [~] Transcribing...          │
│    [phi4mini..]  │  [i] Detected language: pt    │
│                  │  hoje vamos falar sobre...    │
│  ☑ Analyze       │  ...                          │
│    [gemini-...]  │                               │
│                  │  ┌─ Resumo ────────────────┐  │
│  ☑ Prompt        │  │ title    : ...          │  │
│    [gemini-...]  │  │ duration : 27m 55s      │  │
│                  │  │ elapsed  : 4m 12s       │  │
│  Credenciais     │  └─────────────────────────┘  │
│  [API_KEY_____]  │                               │
│                  │  [Cancelar]                   │
│  [Iniciar]       │                               │
└──────────────────┴───────────────────────────────┘
```

## 2.2 Mudanças em `gui.py`

Aumentar largura mínima para acomodar split:

```python
page.window.width = 1200
page.window.height = 800
page.window.min_width = 1000
page.window.min_height = 600
```

## 2.3 Refatorar `src/gui/app.py`

Eliminar `_show_form` / `_show_progress` / `_show_result` e a navegação. Sempre renderizar o layout split:

```python
def build_app(page: ft.Page) -> None:
    cfg = settings.load()
    page.theme_mode = ...

    cancel_event = threading.Event()
    bus = EventBus(page)  # criar uma vez, reutilizar entre runs

    # State observável para o botão Iniciar / barra
    pipeline_state = {"running": False, "last_result": None}

    def _on_start(args: PipelineArgs) -> None:
        if pipeline_state["running"]:
            return
        pipeline_state["running"] = True
        cancel_event.clear()
        # opcional: limpar log anterior se cfg.get("clear_log_on_start", True)
        progress_panel.reset()
        form_panel.set_running(True)
        start_pipeline(args, bus, cancel_event)

    def _on_cancel() -> None:
        cancel_event.set()

    def _on_pipeline_done(payload: dict) -> None:
        pipeline_state["running"] = False
        pipeline_state["last_result"] = PipelineResult(
            raw_path=payload.get("raw_path"),
            analysis_path=payload.get("analysis_path"),
            prompt_path=payload.get("prompt_path"),
        )
        form_panel.set_running(False)
        progress_panel.show_results(pipeline_state["last_result"])

    form_panel = build_form_view(page, on_start=_on_start)
    progress_panel = build_progress_view(page, on_cancel=_on_cancel, on_done=_on_pipeline_done)

    layout = ft.Row(
        controls=[
            ft.Container(content=form_panel, width=380, padding=12),
            ft.VerticalDivider(width=1, color=ft.Colors.OUTLINE_VARIANT),
            ft.Container(content=progress_panel, expand=True, padding=12),
        ],
        expand=True,
        spacing=0,
    )

    page.appbar = _build_appbar(page)
    page.controls.clear()
    page.add(layout)
    page.update()
```

## 2.4 Adaptar `form_view.py`

- Remover `expand=True` da `Column` raiz; manter `scroll=ft.ScrollMode.AUTO`.
- Botão Iniciar precisa expor método `set_running(bool)`:

```python
def set_running(running: bool) -> None:
    start_btn.disabled = running
    start_btn.text = "Executando..." if running else "Iniciar"
    start_btn.icon = ft.Icons.HOURGLASS_EMPTY if running else ft.Icons.PLAY_ARROW_ROUNDED
    page.update()
```

- Retornar tanto o controle quanto o método `set_running`. Alternativa: retornar uma dataclass `FormPanel(control, set_running)`.

## 2.5 Adaptar `progress_view.py`

Refatorar `build_progress_view` para retornar um objeto com métodos:

```python
@dataclass
class ProgressPanel:
    control: ft.Control
    reset: Callable[[], None]
    show_results: Callable[[PipelineResult], None]
```

Estrutura interna em **tabs**:

```python
tabs = ft.Tabs(
    selected_index=0,
    tabs=[
        ft.Tab(text="Pipeline", content=pipeline_content),
        ft.Tab(text="Resultados", content=results_content, disabled=True),
    ],
)
```

- `pipeline_content`: header (stage_label + progress_bar) + log_list + cancel_button (estrutura atual).
- `results_content`: vazio inicialmente, populado por `show_results()` com o que hoje é o `result_view.py` (3 sub-abas Transcrição / Análise / Prompt-ready).
- `show_results(result)`: habilita o tab "Resultados", popula com conteúdo dos arquivos, troca selected_index para 1.
- `reset()`: limpa `log_list.controls`, reseta `stage_label`, `progress_bar.value = None`, desabilita tab "Resultados", volta para tab 0.

## 2.6 Eliminar/reutilizar `result_view.py`

Opção A — mais limpa: extrair de `result_view.py` apenas a função `build_results_tabs(raw_path, analysis_path, prompt_path, page)` que retorna o `ft.Tabs` com Transcrição/Análise/Prompt-ready, sem o botão "Nova transcrição" nem o action_row de topo (cópia/abrir pasta vai para o footer do progress panel ou fica embutido nas próprias tabs).

Opção B — preservar `result_view.py` quase intacto: mantém o `build_result_view` retornando o controle pronto, e o `progress_panel.show_results` simplesmente coloca esse controle dentro do tab "Resultados". Mais simples, menos refatoração.

Preferir Opção B para minimizar mudança.

## 2.7 Atalhos de teclado

- `Ctrl+Enter`: dispara `_on_start` se botão habilitado (já existe, mas remover dependência de `_view_state` — sempre ativo enquanto form for visível, que agora é sempre)
- `Esc`: cancela pipeline se `pipeline_state["running"]`

## 2.8 Persistência de estado entre runs

- Logs anteriores: oferecer toggle no form ou simplesmente limpar sempre ao iniciar (mais simples no MVP). Documentar no `settings.json`: `"clear_log_on_start": true`.
- Tab "Resultados" da run anterior: substituir pelo novo resultado.

## 2.9 Checklist do PR 2

- [ ] `gui.py`: ajustar window size
- [ ] `app.py`: remover navegação, montar `ft.Row` com form (largura 380) + divider + progress (expand)
- [ ] `app.py`: criar `EventBus` uma vez, gerenciar `pipeline_state["running"]`
- [ ] `form_view.py`: expor `set_running()`, remover `expand=True` da column raiz
- [ ] `progress_view.py`: encapsular em `ProgressPanel` com métodos `reset()` e `show_results()`
- [ ] `progress_view.py`: adicionar `ft.Tabs` com Pipeline | Resultados (Resultados disabled inicialmente)
- [ ] `result_view.py`: manter `build_result_view` mas remover botão "Nova transcrição" (não faz sentido no split — usuário simplesmente clica Iniciar de novo no form)
- [ ] Smoke test visual: redimensionar janela, verificar que form mantém 380px e pipeline expande; min_width respeitado
- [ ] Smoke test funcional: rodar pipeline completo, verificar que tab "Resultados" aparece habilitada ao fim, conteúdo carregado
- [ ] Rerun: clicar Iniciar com nova URL após primeira run — log limpa, tab Resultados reseta, tudo flui normalmente

---

## 3. Notas para o Claude Code (revisão via context7)

Quando o CC for revisar/implementar, sugerir consultar a documentação atualizada do Flet via context7 para:

1. **`flet >= 0.24` API**: confirmar que `page.pubsub.send_all()`, `page.pubsub.subscribe()`, `page.update()` continuam estáveis. Atenção a possíveis breaking changes em `ft.Tabs`, `ft.Container.padding`, `ft.Border`.
2. **`ft.Markdown`**: verificar se já suporta `extension_set=ft.MarkdownExtensionSet.GITHUB_WEB` para syntax highlight de code blocks na aba de Análise.
3. **`page.pubsub.unsubscribe()`** sem argumentos: na implementação atual de `progress_view.py` é chamado ao fim do pipeline — confirmar comportamento em Flet recente; alternativa é manter assinatura persistente entre runs (mais eficiente no split layout).
4. **`ft.Slider`** com `divisions`: confirmar API de `on_change` e `label` template.
5. **`ft.run(main)` vs `ft.app(target=main)`**: `gui.py` usa `ft.run(main)` — verificar qual é o atual idiomático.
6. **Thread safety**: documentar que callbacks de `pubsub.subscribe` rodam na UI thread; `bus.emit()` é chamado da worker thread; OK porque `send_all` é thread-safe.

Comando sugerido para o CC:

```
Revise o plano em docs/GUI_REFACTOR_PLAN.md. Antes de implementar:
1. Consulte a doc atual do Flet via context7 para confirmar APIs mencionadas
   (pubsub, Tabs, Markdown extensions, Slider, ft.run vs ft.app)
2. Liste qualquer divergência encontrada e proponha ajuste
3. Implemente PR 1 primeiro (cadência fiel ao CLI), em commits granulares
4. Antes de PR 2, valide PR 1 com: uv run main.py <URL> --verbose
   comparado a uv run gui.py rodando o mesmo URL — log deve ser equivalente
5. Implemente PR 2 (layout split) só após PR 1 mergeado/validado
6. Não tocar em main.py — CLI deve permanecer 100% retrocompatível
```

---

## 4. Critérios de aceitação finais

**PR 1** (cadência):

- [ ] Rodar `uv run gui.py` e observar o painel de logs durante uma transcrição completa
- [ ] Cada linha visível na GUI tem equivalente exato no `uv run main.py <URL> --verbose` (mesmos prefixos, mesma ordem)
- [ ] Cores aplicadas corretamente por prefixo
- [ ] Barra de progresso da transcrição atualiza percentualmente (não fica indeterminada)
- [ ] Card de resumo aparece após `transcribe_done`
- [ ] Aviso `[!] N segments flagged` aparece quando aplicável
- [ ] Erros do pipeline (ex: chave Gemini inválida) aparecem em vermelho com `[!] Error: ...`
- [ ] CLI continua idêntico ao comportamento anterior

**PR 2** (layout):

- [ ] Janela abre com form à esquerda (380px) e painel direito expansível
- [ ] Não há navegação entre views — tudo visível simultaneamente
- [ ] Botão Iniciar fica `disabled` + label "Executando..." durante run
- [ ] Tab "Resultados" desabilitada até `pipeline_done`
- [ ] Após conclusão, tab "Resultados" habilita e seleciona automaticamente
- [ ] Clicar Iniciar de novo limpa logs, reseta barra, desabilita Resultados, reroda
- [ ] `Esc` cancela run em andamento
- [ ] `Ctrl+Enter` dispara Iniciar quando formulário válido
