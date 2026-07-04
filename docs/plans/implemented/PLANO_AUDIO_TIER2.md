# Plano de Implementação — Módulo Áudio · Tier 2

> **Status:** aprovado · **Origem:** consolidação das sugestões em `.claude/suggestions/m-audio/`
> **Escopo:** visualização e feedback (aba nova áudio→imagem, A/B antes/depois, métricas)
> **Pré-requisito:** Tier 1 mergeado · skills `architecture`, `design-system`, `cli`, `testing`
> **⚠️ Atenção máxima:** representação de áudio por waveform tem histórico de bugs/lentidão —
> ver §2.3. Toda decisão visual deste tier foi tomada para **não** tocar o caminho crítico.

## 1. Objetivo

Tornar o efeito do processamento tangível: ver o áudio (espectrograma/waveform estático),
ouvir original vs. processado (A/B) e ler as métricas de loudness medidas. Tudo ffmpeg
nativo + reuso do motor de player existente. Zero dependência nova.

### Itens do tier

| # | Feature | Natureza | Superfície |
|---|---|---|---|
| 7 | Espectrograma / waveform PNG (`showspectrumpic`/`showwavespic`) | áudio→imagem | **Aba nova** |
| 6 | A/B antes/depois no player | UX | painel direito (reuso) |
| 8 | Card de métricas do loudnorm | UX | painel de resultado |

## 2. Decisões de arquitetura

### 2.1 Nova aba "Visualizar" (toggle no topo do módulo)

A geração de espectrograma/waveform é **áudio→imagem** — uma natureza distinta do fluxo
principal (áudio→áudio), exatamente como `describe` (imagem→texto) é distinto das 11
operações imagem→imagem no módulo Imagens. Por isso ganha **aba própria**, seguindo o
padrão consagrado:

- Toggle no topo: `Converter | Visualizar` (dois `ft.TextButton` + `hairline` + `ft.Stack`
  com `visible=`), idêntico ao `Edição | Descrição IA` de `image/view.py:401-409`.
- **Aba "Converter"** = o módulo atual inteiro (form Tier 1 + player + progress), envolvido
  num `edicao_body` (`ft.Row`).
- **Aba "Visualizar"** = novo `gui/modules/audio/visualize_tab.py`, espelhando
  `image/describe_tab.py`: fonte à esquerda (380px) | imagem gerada à direita.

```
view.py
 ├─ ft.Row([tab_converter, tab_visualizar])
 ├─ hairline()
 └─ ft.Stack([converter_body, visualize_tab.control])   # alterna por visible=
```

> Regra "não trocar `Container.content` em runtime" (quirk Flet 0.85): o toggle alterna
> **visibilidade** num `Stack`, nunca reatribui `content`. Bloquear troca enquanto
> `pipeline_running[0]` (como `image/view.py::_show_tab`).

### 2.2 A aba Visualizar produz um artefato indexável (não é só preview)

`showspectrumpic`/`showwavespic` geram um **PNG de um frame só**, escrito em
`output/audio/processed/<stem>_spectrogram.png` (ou `_waveform.png`). Sendo arquivo em
`output/`, é varrido pela Biblioteca automaticamente e abre o bridge para o módulo Imagens.
Não usa `pipe:1` (evita o quirk de `image2pipe`); escreve em arquivo via `run_ffmpeg`.

### 2.3 ⚠️ Waveform: o que NÃO fazer e por quê

Histórico de bugs/lentidão no `audio_player.py` (2 threads de decode, generation counter,
re-encode de PNG por tick). **Regras invioláveis deste tier:**

1. **A imagem da aba Visualizar é estática e gerada UMA vez** pelo ffmpeg, off-thread
   (`page.run_task` + `asyncio.to_thread`), exibida num `ft.Image`. **Não** anima, **não**
   tem cursor, **não** re-renderiza por tick. É um caminho totalmente separado do waveform
   ao vivo do player — não há risco de regressão de performance.
2. **O A/B NÃO cria um segundo waveform ao vivo.** Duplicar o waveform animado dobraria o
   custo de PNG/tick (a fonte da lentidão). Em vez disso: **um único** `AudioPlayer`/
   `_AudioEngine`, com um `segmented_selector` "Original | Processado" que apenas chama
   `player.load(path)` na fonte escolhida. O `_load_generation` já existente descarta a
   carga anterior com segurança (`audio_player.py:767`). Zero código novo de render.
3. **`audio_player.py` não ganha lógica de negócio** — só uma extensão mínima para o A/B
   (ver Fase 2.3). O motor de waveform fica intocado.

### 2.4 Sem matplotlib

deepseek/qwen propuseram `matplotlib`+`soundfile` para espectrograma. Rejeitado: o ffmpeg
faz nativo (`showspectrumpic`/`showwavespic`), sem dependência e sem render off-`pyplot`.
Mantém o app base leve.

## 3. Fases

### Fase 2.1 — Núcleo de visualização + CLI (sem GUI)

**Core** (`core/audio/visualize.py`, novo, ≤ ~140 linhas):
```python
def render_waveform_png(
    src: Path, out_dir: Path, *,
    width: int = 1200, height: int = 240, color: str = "#F4A63C",
) -> Path:
    """Render a static waveform PNG via ffmpeg showwavespic."""

def render_spectrogram_png(
    src: Path, out_dir: Path, *,
    width: int = 1200, height: int = 480, mode: str = "combined",
) -> Path:
    """Render a static spectrogram PNG via ffmpeg showspectrumpic."""
```
- Comandos (escrevem em arquivo, reusam `run_ffmpeg`):
  ```
  ffmpeg -y -i <src> -filter_complex "showwavespic=s=1200x240:colors=#F4A63C" \
         -frames:v 1 <out>_waveform.png
  ffmpeg -y -i <src> -filter_complex "showspectrumpic=s=1200x480:mode=combined" \
         -frames:v 1 <out>_spectrogram.png
  ```
- `is_available()` não é necessário (ffmpeg já é dependência verificada em runtime).
- Saída em `AUDIO_PROCESSED_DIR`.

**CLI** (`cli/audio.py`): subcomando novo **separado** do `audio` (audio→imagem, não passa
pelo pipeline de fila). Seguindo o padrão de subcomandos:
```
uv run main.py audio-viz <arquivo> [--spectrogram] [--width 1200] [--height 480]
```
> Alternativa: flag no subcomando `audio` existente. Decisão: **subcomando próprio
> `audio-viz`** porque a saída é imagem, não áudio — não cabe no `AudioArgs`/fila. Reusa o
> core direto (sem `CLIEventBus`), stdout em UTF-8.

**Testes** (`tests/core/audio/test_visualize.py`):
- unit: monta o `-filter_complex` esperado (mock `run_ffmpeg`).
- integration: `sample_wav` → PNG não-vazio (header `\x89PNG`).

**Commit:**
```
feat(audio): espectrograma e waveform PNG via ffmpeg

Novo core/audio/visualize.py gera imagens estáticas (showspectrumpic /
showwavespic) escritas em output/audio/processed/, indexáveis pela
Biblioteca. Subcomando CLI audio-viz. Zero dependência nova (sem
matplotlib — filtro nativo do ffmpeg).
```

### Fase 2.2 — Aba "Visualizar" na GUI (toggle + superfície áudio→imagem)

- `gui/modules/audio/visualize_tab.py` (novo), espelhando `image/describe_tab.py`:
  - **Esquerda (380px):** `build_input_source` (áudio/vídeo local) + `segmented_selector`
    "Waveform | Espectrograma" + botão "Gerar".
  - **Direita:** `ft.Image` (placeholder `_BLANK_PNG` 1×1 — Flet 0.85 exige `src` no
    construtor) num container com fundo `surface_variant`; abaixo, ações "Abrir arquivo",
    "Salvar em..." e bridge "Abrir no módulo Imagens" (`nav[0]("image", {"file": png})`).
  - `spinner()` com a **regra de ouro**: `page.update()` ANTES de `start()` (o spinner pode
    estar em container `visible=False` no primeiro uso).
  - Render off-thread: `page.run_task` → `asyncio.to_thread(render_*_png, ...)` → setar
    `img.src = <path>` e `page.update()`. **Nunca** bloquear a UI thread.
  - Devolve um dataclass `VisualizeTab(control, set_running, fill_from_path)`.
- `gui/modules/audio/view.py`:
  - envolver o layout atual num `converter_body` (`ft.Row`).
  - adicionar `tab_converter`/`tab_visualizar` + `_show_tab` (cópia do padrão de
    `image/view.py`, com guarda `pipeline_running[0]`).
  - `on_mount`: se `payload["file"]`, encaminhar para a aba ativa (Converter por padrão).

**Testes:** GUI não testável headless → teste manual.

**Commit:**
```
feat(audio): aba Visualizar (áudio→imagem) com toggle Converter|Visualizar

Adiciona o toggle de abas no topo do módulo (padrão Edição|Descrição IA
do módulo Imagens) e a aba Visualizar, que gera waveform/espectrograma
off-thread e exibe num ft.Image estático, com bridge para o módulo
Imagens. O waveform ao vivo do player permanece intocado.
```

### Fase 2.3 — A/B antes/depois + card de métricas do loudnorm (GUI)

**A/B (sem novo waveform ao vivo — §2.3):**
- O worker (Tier 1) já conhece o caminho de entrada e o de saída. Emitir no `audio_op_done`
  um campo extra `source_path` (o arquivo base, pré-pós-processamento) quando houver
  pós-processamento aplicado.
- `audio_player.py` — extensão mínima: expor no dataclass `AudioPlayer` um
  `set_compare(original: str | None, processed: str | None)` que guarda os dois caminhos e
  mostra um `segmented_selector` "Original | Processado" **somente quando ambos existem**.
  Trocar de opção chama o `_load` interno na fonte escolhida (reusa generation counter).
  Preservar a posição de playback é *nice-to-have*; o seguro é recarregar do início.
- `view.py::_on_done` — em vez de só `player.load(out)`, chamar
  `player.set_compare(source_path, out)`.

**Card de métricas do loudnorm:**
- `normalize_lufs` já retorna `stats` (`input_i`/`input_tp`/`input_lra`) — hoje só vai pro
  log (`worker.py:239`). Propagar `stats` no payload do `audio_op_done` (operation="normalize").
- `view.py::_render_audio_results` / `_make_output_card` — quando houver `stats`, anexar um
  card compacto: `"−19,2 → −14,0 LUFS · TP −1,2 dBTP · LRA 8,4 LU"`. Helper de formatação em
  `pipeline_log.py` (`fmt_loudness_card(stats, target)`), puro/testável.

**Testes:**
- unit (`tests/gui/modules/audio/test_pipeline_log.py`): `fmt_loudness_card` formata
  corretamente (números PT-BR com vírgula, campos ausentes → "?").
- A/B e card: teste manual.

**Commit:**
```
feat(audio): comparação A/B e card de métricas de loudness

O reprodutor ganha um seletor Original|Processado (sem segundo waveform
ao vivo — reusa o motor e o generation counter existentes) e o painel de
resultado mostra um card com o loudness medido vs. alvo (IL/TP/LRA), que
o normalizer já calculava e só ia para o log.
```

### Fase 2.4 (opcional) — Waveform como thumbnail da Biblioteca

Sugerido por kimi. Hoje `core/library/thumbnails.py` despacha áudio→ícone. Poderia gerar um
mini-waveform via `render_waveform_png` (cache por `(path, mtime)`). **Fora do caminho
crítico**, mas adiciona custo de geração na varredura da Biblioteca. **Recomendação:**
deixar como item separado, decidir depois (não bloquear o Tier 2). Se implementado, reusar
`core/audio/visualize.py` com `width/height` pequenos e cache no padrão da Biblioteca.

## 4. Checklist final do tier

- [ ] Aba alterna por `visible=` num `ft.Stack` (nunca reatribui `content`); troca bloqueada
      durante o pipeline.
- [ ] Imagem da aba Visualizar é **estática, gerada 1×, off-thread** — sem cursor/tick.
- [ ] A/B **não** cria segundo waveform ao vivo; reusa `_AudioEngine` + generation counter.
- [ ] `ft.Image` com `src` no construtor (placeholder `_BLANK_PNG`); spinner com `page.update()`
      antes de `start()`.
- [ ] `core/audio/visualize.py` puro, reusa `run_ffmpeg` (subprocess binário).
- [ ] CLI `audio-viz` cobre a feature; stdout UTF-8.
- [ ] `uv run pytest -m unit` verde; `ruff` limpo.
- [ ] Docstrings/logs em inglês; labels em português.
- [ ] App rodado manualmente: gerar espectrograma, alternar A/B, conferir card — sem
      travamento/flicker no waveform do player.

## 5. Nota sobre commits

Cada fase = um commit detalhado e independente (mensagens acima). **Sem trailer
`Co-Authored-By`**. Rodar `uv run pytest -m unit` antes de cada commit. A Fase 2.4 é
opcional e, se feita, vira commit próprio.
