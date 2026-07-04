# Plano de Implementação — Módulo Áudio · Tier 1

> **Status:** aprovado · **Origem:** consolidação das sugestões em `.claude/suggestions/m-audio/`
> **Escopo:** correções de bugs reais + quick wins 100% ffmpeg (zero dependência nova, torch-free)
> **Pré-requisito de leitura:** skill `architecture` (camadas/limites), `cli`, `design-system`, `testing`

## 1. Objetivo

Fechar os gaps confirmados no código atual e adicionar operações de pós-processamento
de alto valor para o fluxo de transcrição/voz, sem introduzir dependências. Todas as
features deste tier são filtros nativos do ffmpeg ou reuso de código já existente.

### Itens do tier

| # | Feature | Natureza | Onde nasce |
|---|---|---|---|
| 1 | Denoise respeitar `fmt`/`quality` (encode final) | **Bug** | core + worker |
| 2 | Expor toggle `stationary` (ruído constante/variável) | Gap | core (pronto) + GUI |
| 3 | Canais (mono) + sample-rate, com preset "Transcrição" | Feature | core + GUI |
| 4 | Remoção de silêncio (`silenceremove`) | Feature | core novo |
| 5 | Mudança de velocidade sem pitch (`atempo`) | Feature | core novo |

## 2. Decisões de arquitetura

### 2.1 Ordem da cadeia de pós-processamento (define o desenho do worker)

A cadeia hoje é `convert/extract → denoise(→wav) → normalize`. O bug do item 1 é que o
denoise grava `.wav` fixo (`denoiser.py:61`) e nada reencoda para `args.fmt` depois.
A correção e os itens 3-5 reorganizam a cadeia para uma ordem única e tecnicamente correta:

```
1. base       : download / convert / extract  → arquivo de trabalho
2. silence     : silenceremove (ffmpeg -af)     [se ativo]
3. denoise     : noisereduce (round-trip wav)   [se ativo]
4. speed       : atempo (ffmpeg -af)            [se ativo]
5. normalize   : loudnorm 2-pass                [se ativo]  ← por último (controla picos)
6. FINAL ENCODE: convert_audio(fmt, quality, channels, sample_rate)
                 só roda se o suffix ≠ fmt OU se mono/sample-rate foram pedidos
```

> O **passo 6 é a peça-chave**: ele conserta o bug do denoise (garante a saída em
> `args.fmt`) **e** implementa mono + sample-rate de uma vez, num único encode. Não há
> passe único afftdn+loudnorm aqui — isso é Tier 3 (item 10). Tier 1 mantém passos
> discretos por clareza e testabilidade.

### 2.2 Sem nova aba na GUI neste tier

Tier 1 estende o formulário existente (entrada → formato → pós-processamento → iniciar).
São **switches/sliders encadeáveis** (denoise E silêncio E velocidade E normalize podem
coexistir), portanto **não** usam grade de operações mutuamente exclusivas (diferente do
módulo Imagens). O toggle de abas só entra no **Tier 2** (superfície de visualização
áudio→imagem).

Como o `form_view.py` já está em ~347 linhas e ganharia 4 controles novos, aplica-se a
regra **"divide-se ao tocar"**: o formulário é refatorado para `blocks/` (padrão do módulo
Imagens — cada `build_X_block(page) → (ft.Column, XRefs)`), **antes** de receber os novos
controles. Ver Fase 1.4.

### 2.3 Waveform: intocado neste tier

Tier 1 **não** altera o `audio_player.py` nem o caminho de render do waveform ao vivo
(2 threads, generation counter, `gapless_playback`, update escopado). Nenhuma feature aqui
toca a área de risco de performance. O player continua só carregando o resultado final.

## 3. Fases

### Fase 1.1 — Correção do encode final + canais/sample-rate + stationary (core/cli)

**Core:**
- `core/audio/converter.py::convert_audio` — adicionar parâmetros `channels: int | None = None`
  e `sample_rate: int | None = None`. Quando setados, anexar `-ac {channels}` / `-ar {sample_rate}`
  ao comando ffmpeg (antes de `-progress`). Docstring em inglês.
- `core/audio/args.py::AudioArgs` — novos campos:
  ```python
  denoise_stationary: bool = True
  channels: int | None = None          # 1 = mono, None = preservar
  sample_rate: int | None = None       # 16000, 22050, 44100, None = preservar
  ```
- `gui/modules/audio/worker.py`:
  - passar `stationary=args.denoise_stationary` para `_denoise_audio(...)` e para
    `pipeline_log.fmt_denoise_detail(...)` (hoje ambos hardcoded em `True`).
  - adicionar o **passo 6 (encode final)** após o normalize: se
    `out_path.suffix.lstrip('.') != target_fmt` **ou** `args.channels`/`args.sample_rate`
    setados, chamar `convert_audio(out_path, AUDIO_PROCESSED_DIR, fmt=target_fmt,
    bitrate=…, channels=…, sample_rate=…)`. Emitir `audio_op_start` (operation="encode")
    + log. `target_fmt = args.fmt if args.fmt != "best" else "mp3"`.
- `gui/modules/audio/pipeline_log.py` — adicionar `"encode"` em `OP_VERBS`/`OP_LABELS`
  ("Reencodando" / "Reencodando saída...") e um `fmt_encode_detail(channels, sample_rate)`.

**CLI** (`cli/audio.py`):
- `--denoise-adaptive` (store_true) → `denoise_stationary = not ns.denoise_adaptive`.
- `--mono` (store_true) → `channels = 1`.
- `--sample-rate` (type=int, choices `[16000, 22050, 44100, 48000]`) → `sample_rate`.

**Testes** (`tests/core/audio/test_converter.py`):
- unit: `convert_audio` com `channels=1`/`sample_rate=16000` monta o comando esperado
  (mockar `run_ffmpeg`, asserir `-ac 1`/`-ar 16000` no argv).
- integration (skip se sem ffmpeg): converter `sample_wav` → mp3 mono 16k e ffprobe
  confirma 1 canal / 16000 Hz.

**Commit:**
```
feat(audio): encode final respeita formato, canais e sample-rate

Corrige o denoise que sempre gravava .wav ignorando o formato pedido:
a cadeia agora termina num encode único para args.fmt, que também
aplica downmix mono (-ac) e sample-rate alvo (-ar) quando solicitados.
Expõe o modo de ruído (stationary) do denoise, antes fixo em True.

- converter.convert_audio: parâmetros channels/sample_rate
- AudioArgs: denoise_stationary, channels, sample_rate
- worker: passo de encode final + stationary repassado ao denoiser
- pipeline_log: vocabulário do passo "encode"
- cli: --denoise-adaptive, --mono, --sample-rate
```

### Fase 1.2 — Remoção de silêncio (core/cli)

**Core** (`core/audio/silence.py`, novo, ≤ ~120 linhas):
```python
def remove_silence(
    src: Path,
    out_dir: Path,
    fmt: str,
    *,
    threshold_db: float = -40.0,
    min_silence_s: float = 0.5,
    keep_silence_s: float = 0.1,
    bitrate: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Remove leading/trailing and internal silence via ffmpeg silenceremove."""
```
- Filtergraph (validado por web search — `stop_periods` negativo remove silêncio do
  meio): constrói dinamicamente
  ```
  silenceremove=start_periods=1:start_silence=0:start_threshold={th}dB:
                stop_periods=-1:stop_duration={min_silence_s}:
                stop_threshold={th}dB:stop_silence={keep_silence_s}
  ```
- Reusa `run_ffmpeg` (binário, progress). Saída `<stem>_nosilence.{fmt}`.

**args/worker/pipeline_log/cli:**
- `AudioArgs`: `trim_silence: bool = False`, `silence_threshold_db: float = -40.0`,
  `silence_min_s: float = 0.5`.
- worker: passo 2 da cadeia (antes do denoise). `audio_op_start(operation="silence")`.
- pipeline_log: verbo/label "Removendo silêncio" + `fmt_silence_detail`.
- CLI: `--trim-silence`, `--silence-threshold`, `--silence-min`.

**Testes** (`tests/core/audio/test_silence.py`):
- unit: monta o filtergraph esperado (mock `run_ffmpeg`, asserir substring do `-af`).
- integration: gerar wav com silêncio (fixture sintetizada ou `sample_wav`) → saída mais
  curta que a entrada.

**Commit:**
```
feat(audio): remoção de silêncio via ffmpeg silenceremove

Novo passo de pós-processamento que corta silêncio do início, fim e
meio do áudio (stop_periods negativo). Útil para limpar aulas/podcasts
antes da transcrição. Zero dependência nova — filtro nativo do ffmpeg.

- core/audio/silence.py: remove_silence (filtergraph dinâmico)
- AudioArgs/worker/pipeline_log: passo "silence" na cadeia
- cli: --trim-silence, --silence-threshold, --silence-min
```

### Fase 1.3 — Mudança de velocidade sem pitch (core/cli)

**Core** (`core/audio/speed.py`, novo, ≤ ~90 linhas):
```python
def change_speed(
    src: Path, out_dir: Path, fmt: str, *,
    factor: float, bitrate: str | None = None,
    progress_cb: Callable[[float], None] | None = None,
) -> Path:
    """Change playback speed without altering pitch via ffmpeg atempo."""
```
- `atempo` aceita só 0.5–2.0 → para fatores fora da faixa, **encadear** filtros
  (ex. 3.0 → `atempo=2.0,atempo=1.5`). Função pura `_atempo_chain(factor) -> str`
  (unit-testável isolada). Validação: 0.5 ≤ factor ≤ 4.0.
- Saída `<stem>_{factor}x.{fmt}`.

**args/worker/pipeline_log/cli:**
- `AudioArgs`: `speed_factor: float = 1.0` (1.0 = desativado).
- worker: passo 4 (após denoise, antes do normalize). Só roda se `speed_factor != 1.0`.
- pipeline_log: "Ajustando velocidade" + `fmt_speed_detail(factor)`.
- CLI: `--speed` (type=float, default 1.0).

**Testes** (`tests/core/audio/test_speed.py`):
- unit: `_atempo_chain(1.25)=="atempo=1.25"`, `_atempo_chain(3.0)=="atempo=2.0,atempo=1.5"`,
  `_atempo_chain(0.5)=="atempo=0.5"`; fatores inválidos levantam `ValueError`.
- integration: duração da saída ≈ duração/factor.

**Commit:**
```
feat(audio): mudança de velocidade sem alterar pitch (atempo)

Acelera/desacelera o áudio (0.5x–4.0x) encadeando filtros atempo para
respeitar a faixa 0.5–2.0 de cada estágio. Corta o tempo de Whisper
proporcionalmente em estudo. Zero dependência nova.

- core/audio/speed.py: change_speed + _atempo_chain (puro/testado)
- AudioArgs/worker/pipeline_log: passo "speed" na cadeia
- cli: --speed
```

### Fase 1.4 — Refatoração do formulário em `blocks/` (GUI, sem mudança de comportamento)

Pré-requisito para os controles novos não estourarem o teto. **Refatoração pura** — a GUI
deve ficar idêntica ao usuário.

- Criar `gui/modules/audio/blocks/__init__.py`.
- Extrair do `form_view.py` atual, cada um devolvendo `(ft.Column|ft.Control, XRefs)`:
  - `blocks/output.py::build_output_block` — formato (grade) + bitrate (grade) + `embed_row`.
  - `blocks/denoise.py::build_denoise_block` — switch denoise.
  - `blocks/normalize.py::build_normalize_block` — switch normalize + slider LUFS.
- `form_view.py` passa a compor os blocos (espelha `image/form_view.py`). Alvo ≤ ~250 linhas.

**Testes:** nenhum novo (refatoração de GUI, não testável headless). Rodar o app manualmente.

**Commit:**
```
refactor(audio): formulário fatiado em blocks/ (sem mudança de UX)

Extrai as seções de saída, denoise e normalize do form_view para
gui/modules/audio/blocks/, no padrão do módulo Imagens, preparando o
formulário para os novos controles do Tier 1 sem estourar o teto de
tamanho da skill architecture.
```

### Fase 1.5 — Controles novos + presets (GUI)

- `blocks/denoise.py` — adicionar toggle "Ruído constante | variável" (`segmented_selector`
  2 opções, default "constante" = stationary). Refs expõem `get_stationary()`.
- `blocks/output.py` — adicionar sub-seção "Canais e taxa": `segmented_selector`
  ["Preservar","Mono"] e ["Preservar","16k","22k","44k"]. Refs `get_channels()`/`get_sample_rate()`.
- `blocks/silence.py` (novo) — switch + `labeled_slider` threshold (−60..−20 dB) +
  `labeled_slider` duração mínima (0.2..3.0 s), revelados quando o switch liga
  (padrão do `lufs_block`: container `visible=` + `animate_opacity`).
- `blocks/speed.py` (novo) — switch + `labeled_slider` (0.5..3.0×, fmt `"{v:.2f}×"`).
- `blocks/presets.py` (novo) — linha de **chips de preset** no topo do formulário:
  - **"Pronto p/ transcrição"** → mono + 16 kHz + denoise + remoção de silêncio.
  - **"Podcast"** → −16 LUFS + denoise + remoção de silêncio.
  - **"Arquivo musical"** → preserva canais/taxa, sem normalizar.
  Cada chip chama setters dos refs dos blocos (estado, não pipeline). Implementar como
  `build_presets_block(apply: Callable[[str], None])`; o `form_view` fornece o `apply`
  que escreve nos blocos.
- `form_view.py::_on_start_click` — montar `AudioArgs` com os novos campos.
- `form_view.py::_set_running` — desabilitar os novos controles durante o run.
- Persistência (`settings`): `last_audio_stationary`, `last_audio_channels`,
  `last_audio_sample_rate`, `last_audio_trim_silence`, `last_audio_silence_threshold`,
  `last_audio_silence_min`, `last_audio_speed`.

**Testes:** GUI não testável headless → teste manual (rodar `uv run gui.py`, exercitar
cada preset e cada controle, conferir os args no log do pipeline).

**Commit:**
```
feat(audio): controles de silêncio, velocidade, canais/taxa e presets

Adiciona ao formulário os novos blocos (remoção de silêncio, velocidade,
canais/sample-rate, modo de ruído) e uma linha de presets de uma tecla
("Pronto p/ transcrição", "Podcast", "Arquivo musical") que pré-ajustam
os switches. Persiste todas as escolhas em config.json.
```

## 4. Checklist final do tier

- [ ] `core/audio/` continua puro (sem Flet/print); `silence.py`/`speed.py` reusam `run_ffmpeg`.
- [ ] `subprocess` em modo binário (herdado de `run_ffmpeg`).
- [ ] Nenhum arquivo passou do teto (`form_view` ≤ ~250 após blocks/; cada core ≤ ~120).
- [ ] CLI **e** GUI cobertas; eventos com `module_id="audio"`.
- [ ] `uv run pytest -m unit` verde; `ruff` limpo.
- [ ] Docstrings/logs/comentários em inglês; labels em português.
- [ ] Saídas em `output/audio/processed/`.
- [ ] App rodado manualmente (sem screenshot — usuário valida localmente).

## 5. Nota sobre commits

Cada fase é um commit detalhado e independente (mensagens acima). **Sem trailer
`Co-Authored-By`** — convenção do projeto. Rodar `uv run pytest -m unit` antes de cada commit.
