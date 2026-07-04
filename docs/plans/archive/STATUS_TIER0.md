# Tier 0 — Status de implementação

> Relatório do que foi entregue e do que ficou pendente do
> [ROADMAP_TIER0_LACUNAS.md](./ROADMAP_TIER0_LACUNAS.md). As partes
> pendentes serão implementadas em uma nova sessão; este documento
> serve como ponto de retomada.

**Branch:** `main` · **Range de commits:** `661a449..f59cfa0` · **Push:** ✅ origin

---

## Visão geral

| Fase | Entrega | Status | Sessão |
|---|---|---|---|
| **T0.1** | `core/subtitles.py` (puro) + testes | ✅ Concluído | Atual |
| **T0.2** | Legendas no `transcriber.transcribe()` + GUI + CLI **e** cobertura de `transcriber.py` | ✅ Concluído | Atual |
| **T0.3** | OCR (PR5.1): `core/document/ocr.py` + card + worker + CLI + testes | ✅ Concluído | Seguinte |
| **T0.4** | Operação de legenda no Vídeo (mux/queima) + testes | ✅ Concluído | Seguinte |

> **Atualização (sessão seguinte):** Partes C (T0.4) e D (T0.3) entregues —
> Tier 0 **completo**. Ordem executada: C primeiro (legenda no vídeo,
> commit `6cc1c7a`), depois D (OCR, desbloqueado pela instalação do
> Tesseract em `C:\Program Files\Tesseract-OCR`). Suíte: **493 testes**
> passando (unit + integration). Detalhes nas seções abaixo (antes
> "O que ficou faltando", agora entregues).

Decisão da sessão (auto-mode off, resposta direta do usuário):

- **Escopo escolhido:** A+B (Partes A e B do roadmap).
- **OCR (D):** "Pular Parte D nesta sessão" — Tesseract não está
  instalado no PATH.
- **Vídeo × legenda (C):** Não chegou a ser priorizado nesta sessão;
  candidato natural a vir junto com C0.4 numa sessão posterior, com
  Biblioteca (PR6) facilitando a seleção de `.srt` + vídeo.

---

## O que foi entregue

### Parte A — Legendas `.srt` / `.vtt` na Transcrição

#### A.1 — `src/core/subtitles.py` + testes (commit `661a449`)

Módulo puro, sem deps externas (Pillow, ffmpeg, faster-whisper, Flet).
Reutilizável por CLI e GUI; todo o resto do Tier 0 que envolve
legendas depende dele.

API pública:

```python
@dataclass(frozen=True, slots=True)
class SubtitleCue:
    index: int      # 1-based
    start: float    # seconds
    end: float      # seconds
    text: str

def to_srt(cues: list[SubtitleCue]) -> str
def to_vtt(cues: list[SubtitleCue]) -> str
def write_subtitles(
    cues: list[SubtitleCue],
    out_stem: Path,
    formats: tuple[str, ...] = ("srt",),
) -> list[Path]
```

Detalhes:

- `_format_ts(seconds, sep=','|'.')` arredonda via `round()` (não
  trunca), clampa negativos a 0, pad de zeros consistente.
- `to_srt`: blocos índice/timestamp/texto separados por linha em
  branco; texto é `strip()`ado.
- `to_vtt`: header `"WEBVTT"`, separador `.`, **sem** linha de índice.
- `write_subtitles`: formatos desconhecidos são silenciosamente
  ignorados (callers controlam o que é válido); ordem de saída
  preservada conforme `formats=`.

Testes: `tests/core/test_subtitles.py` — **29 testes**, cobertura
**100%** (statement + branch). Inclui parametrização canônica do
`_format_ts` em 10 pontos críticos (zero, sub-ms, ms boundary, hora
completa, arredondamento up) e garantia de que `SubtitleCue` é
frozen.

#### A.2 — Integração em `transcriber.transcribe()` (commit `9d2519e`)

Mudança **retrocompatível**: novo parâmetro opcional
`subtitle_formats: tuple[str, ...] = ()` em `transcribe()`.

```python
def transcribe(
    audio_path: Path,
    output_path: Path,
    meta: dict,
    url: str,
    model_size: str,
    language: str | None,
    threads: int,
    beam_size: int,
    on_event: Callable[[str, str, dict], None] | None = None,
    force_overwrite: bool = False,
    subtitle_formats: tuple[str, ...] = (),   # NOVO
) -> float | None:
```

Quando não vazio, os segmentos do faster-whisper são coletados como
`SubtitleCue` no **mesmo loop** que já escreve o `.txt` — zero custo
adicional de GPU/CPU além da serialização final.

Após o loop, se houver `cues`, `write_subtitles()` grava em
`TRANSCRIPTIONS_SUBTITLES_DIR` (constante nova em `src/utils.py`:
`OUTPUT_DIR / "transcriptions" / "subtitles"`) e emite o evento
`"subtitles_done"` com a lista de paths gerados.

Imports de `src.core.subtitles` e `TRANSCRIPTIONS_SUBTITLES_DIR`
ficam dentro do `if subtitle_formats:` (lazy import — padrão do
`core/image/background.py`).

#### A.4 — Wire-up GUI (commit `5e2ab01`)

Cinco arquivos modificados, todos no módulo Transcrição:

- `src/gui/settings.py`: nova chave `last_export_subtitles` (default
  `False`) em `_DEFAULTS`.
- `src/gui/workers.py`:
  - `PipelineArgs.export_subtitles: bool = False`.
  - `PipelineResult.subtitle_paths: list[Path] | None`.
  - `on_event` captura paths quando `"subtitles_done"` chega.
  - Chama `transcriber.transcribe(subtitle_formats=("srt","vtt"))`
    quando `export_subtitles=True`.
  - `task_done` payload inclui `subtitle_paths`.
- `src/gui/views/form_view.py`: `switch` "Exportar legendas
  (.srt + .vtt)" sob o bloco Prompt-ready. Persiste em settings via
  `_on_start_click`.
- `src/gui/views/result_view.py`:
  - Novo parâmetro `subtitle_paths: list[Path] | None`.
  - Quando presente, **4ª aba "Legendas"** com prévia do `.srt`
    (preferido por legibilidade; fallback para 1º arquivo se sem
    `.srt`).
  - Botão extra "Abrir pasta de legendas" no `action_row`
    (`SUBTITLES` icon).
- `src/gui/views/progress_view.py`: passa `result.subtitle_paths`
  para `build_result_view`.

Bônus DS (commit `298f969`): a seção "Legendas" foi alinhada às
outras (`section()` + `help_key="transcription.subtitles"` + ⓘ).

#### A.5 — Wire-up CLI (commits `6c3557c` + `9a615e1`)

`main.py`:

- 3 flags novas no parser:
  - `--srt`: exporta `.srt`.
  - `--vtt`: exporta `.vtt`.
  - `--subtitles`: atalho para `--srt --vtt` (tem prioridade).
- Helper `_subtitle_formats_from_args(args) -> tuple[str, ...]`:
  resolve a tupla a partir das flags, preserva ordem `srt → vtt`,
  retorna `()` quando nenhuma flag foi passada.
- `main()` repassa para `transcribe(subtitle_formats=...)`.
- `parse_args(argv: list[str] | None = None)`: nova assinatura
  aceita `argv` opcional. Em produção `parse_args()` continua lendo
  `sys.argv` como antes; em testes, `parse_args(["--srt"])` mantém o
  parser isolado de estado global — **alinha à skill `cli`**
  ("nunca chamar `sys.argv` diretamente").

Testes: `tests/cli/test_transcribe_main.py` — **9 testes**:

- 6 do `_subtitle_formats_from_args`: vazio, srt-only, vtt-only,
  ambos, `--subtitles` expande, `--subtitles` prevalece sobre
  individual.
- 3 do `parse_args`: defaults, flags True, sanidade junto com
  `--format`/`--analyze`.

Docstring de uso de `main.py` atualizada com exemplos `--srt` e
`--subtitles`.

### Parte B — Cobertura de `transcriber.py` (commit `f7136c3`)

`transcriber.py` saltou de **31% → 97%** (statement + branch).
**25 testes** adicionados em `tests/test_transcriber.py`,
totalizando 36 no arquivo.

Padrão de mock estabelecido (Context7-validado contra
`faster-whisper` v1):

```python
class _Seg:
    def __init__(self, start, end, text, avg_logprob=-0.2, no_speech_prob=0.1):
        ...

class _Info:
    def __init__(self, language="pt", language_probability=0.99, duration=6.0):
        ...

def _patch_whisper(mocker, segments, info=None):
    fake = mocker.MagicMock()
    fake.transcribe.return_value = (iter(segments), info or _Info())
    mocker.patch("src.transcriber.WhisperModel", return_value=fake)
    mocker.patch("src.transcriber._resolve_device", return_value=("cpu", "int8"))
    return fake
```

Casos cobertos:

- Header (via `format_metadata`) + corpo do `.txt`.
- Marcação `[?]` por `avg_logprob < -1.0` **e** por
  `no_speech_prob > 0.6` (2 ramos distintos do `or`).
- Eventos `whisper_loading`/`loaded`/`transcribe_started`/
  `language_detected`/`transcribe_segment` (N×)/`transcribe_done`
  com `flagged_count` e `output_path`.
- Subtitles: `("srt","vtt")` gera ambos arquivos em
  `TRANSCRIPTIONS_SUBTITLES_DIR` (redirecionado via
  `monkeypatch.setattr`); `subtitles_done` emitido; default `()` não
  cria pasta; zero segmentos não escreve.
- `force_overwrite=False` + arquivo existente + `input='n'` →
  `None`, conteúdo original preservado.
- `force_overwrite=False` + `input='y'` → sobrescreve.
- `KeyboardInterrupt` no meio do iterador de segments → remove
  arquivo incompleto + `sys.exit(0)` (via generator que `yield`a e
  depois levanta).
- `print_summary`: smoke test de output em stdout.

Restantes (1 stmt + 2 partial branches): apenas logs secundários
(log de overwrite) e condição de import lazy — sem valor real em
cobrir.

### Documentação alinhada (commit `f59cfa0`)

`.claude/skills/testing/SKILL.md`:

1. Árvore de `tests/` inclui `test_subtitles.py` e
   `test_transcribe_main.py`.
2. Tabela de cobertura refeita: total 84% → **87%**,
   `core/subtitles.py` em 100%, `transcriber.py` em 97%.
3. Removida a entrada de lacuna do transcriber ("~2h, ~75%") — está
   feito.
4. Nova subseção **"Mock de `WhisperModel` (faster-whisper)"** em
   *Padrões de mock*, com os stand-ins `_Seg`/`_Info`, helper
   `_patch_whisper`, e gotchas (patchar `src.transcriber.WhisperModel`,
   não `faster_whisper.WhisperModel`; `iter()` em vez de `list`;
   padrão do `KeyboardInterrupt` via generator; isolation de
   `TRANSCRIPTIONS_SUBTITLES_DIR` via monkeypatch).

---

## Métricas

| Métrica | Antes (sessão anterior) | Depois (esta sessão) | Δ |
|---|---|---|---|
| Testes | 414 | **466** | +52 |
| Cobertura agregada (com branch) | 84% | **87%** | +3 pp |
| `transcriber.py` | 31% | **97%** | +66 pp |
| `core/subtitles.py` | — | **100%** | novo |
| Módulos em 100% | 16 | **17** | +1 |
| Suíte unit (`-m unit`) | ~4.5s | **~5s** | inalterada |
| Suíte completa | 17.7s | **25.6s** | +legendas em test_transcriber |

Commits da sessão (`661a449..f59cfa0`, 8 ao todo):

```
f59cfa0 docs(skill-testing): alinha à realidade pós Tier 0 A+B
9a615e1 refactor(cli): parse_args aceita argv opcional (alinha à skill cli)
298f969 feat(gui): alinha seção "Legendas" ao design system (section + ⓘ)
6c3557c feat(cli): flags --srt/--vtt/--subtitles para exportar legendas
5e2ab01 feat(gui): adiciona switch "Exportar legendas (.srt + .vtt)" no módulo Transcrição
f7136c3 test(transcriber): cobre transcribe() via WhisperModel mock (31% → 97%)
9d2519e feat(transcriber): exporta legendas SRT/VTT no mesmo loop dos segmentos
661a449 feat(core): adiciona src/core/subtitles.py — SRT/VTT puro
```

---

## Partes C e D (entregues na sessão seguinte)

### Parte C — Legenda no vídeo (Vídeo × Transcrição)

Une os dois módulos: pegar o `.srt` da Transcrição e **embutir
(mux)** ou **queimar (hardcode)** no vídeo. Detalhamento completo em
[ROADMAP_TIER0_LACUNAS.md §C](./ROADMAP_TIER0_LACUNAS.md#parte-c--legenda-no-vídeo-vídeo--transcrição).

**✅ Entregue (commit `6cc1c7a`):** 8ª operação `subtitle` do módulo
Vídeo, em dois modos — `soft` (mux `-c copy -c:s mov_text`, sem
reencode) e `hard` (burn-in `-vf subtitles=…` + libx264). `run_ffmpeg`
ganhou `cwd=`; o burn-in roda com cwd na pasta da legenda + basename
para evitar o drive-letter colon do Windows. Card + bloco (FilePicker
`.srt`/`.vtt` + segmented Embutir|Queimar) + CLI `video subtitle FILE
--subs PATH [--mode soft|hard]`. Testes: 3 integration (`add_subtitles`
soft/hard/progress) + 2 unit (`run_ffmpeg cwd`) + 4 unit CLI + 1 unit
pipeline_log. A ponte do lado da Transcrição ("Embutir no vídeo") foi
deixada para depois do PR6 (Biblioteca), como o roadmap sugere.

**Plano original (realizado):**

1. **Core**: `src/core/video/converter.py::add_subtitles(src,
   subtitle_path, out_dir, mode="soft"|"hard", progress_cb=)`.
   - `mode="soft"` (default): `-c copy -c:s mov_text` para `.mp4` /
     `-c:s srt` para `.mkv`. Sem reencoding, rápido.
   - `mode="hard"`: `-vf subtitles=<arquivo>` (CPU, libx264).
2. **`src/core/ffmpeg.py`**: `run_ffmpeg` precisa aceitar `cwd=` e
   repassar a `subprocess.Popen` — mitigação do bug Windows do filtro
   `subtitles` (drive-letter colon `C:` quebra o parser de filtro
   se passado pelo path absoluto). Solução: rodar com `cwd =
   subtitle_path.parent` + basename.
3. **GUI**: 8ª operação do módulo Vídeo. `VideoArgs.subtitle_path:
   Path | None`, `subtitle_mode: str = "soft"`. Card `subtitle` no
   grid; bloco condicional com FilePicker para `.srt`/`.vtt` +
   `segmented_selector("Embutir | Queimar")`. Op `subtitle` em
   `OP_VERBS`/`OP_LABELS` do `pipeline_log.py`. Worker chama
   `add_subtitles`.
4. **Bridge**: botão "Embutir no vídeo" no painel de resultados da
   Transcrição quando há `.srt` (caminho principal: usuário escolhe
   vídeo + legenda no módulo Vídeo).
5. **Testes** (`tests/core/video/test_converter.py` — já é
   `integration`): gerar `.srt` mínimo em `tmp_path`, rodar
   `add_subtitles(sample_mp4, srt, mode="soft")` e `mode="hard"`,
   asserts de `out.exists()` e `size > 1000`. O modo `hard` valida o
   caminho `cwd`+basename.

**Arquivos a tocar (resumo):**

```
src/core/video/converter.py              (add_subtitles)
src/core/video/args.py                   (subtitle_path, subtitle_mode)
src/core/ffmpeg.py                       (run_ffmpeg aceita cwd=)
src/gui/modules/video/{form_view,worker,pipeline_log}.py
src/cli/video.py                         (sub-subcomando)
tests/core/video/test_converter.py       (add_subtitles)
CLAUDE.md                                (op + quirks Windows)
```

### Parte D — OCR (PR5.1)

PDF escaneado → texto → LLM. Já especificado no `CLAUDE.md`
(`pytesseract>=0.3` no extra `[ocr]`, card `_UNAVAILABLE`).
Detalhamento em
[ROADMAP_TIER0_LACUNAS.md §D](./ROADMAP_TIER0_LACUNAS.md#parte-d--ocr-pr51--pdf-escaneado--texto--llm).

**✅ Entregue:** `src/core/document/ocr.py` com `ocr_pdf()` híbrido
(texto nativo por página; OCR via pytesseract só nas páginas sem camada
de texto) e `is_available()` que resolve o binário no PATH **ou** em
`C:\Program Files\Tesseract-OCR` (o instalador do usuário não adicionou
ao PATH — o fallback resolve transparentemente e configura
`pytesseract.tesseract_cmd`). 13ª operação GUI/12ª CLI: card `ocr`
(habilita/desabilita conforme disponibilidade), bloco com idioma
(por/eng/por+eng/spa) + DPI (150/300), `document ocr FILE --lang --dpi`.
Saída renderiza no Mode 3 (texto), igual ao `extract`; fecha o loop PDF
escaneado → OCR → `analyze`. Testes: 10 unit (mock pytesseract) + 1
integration real (Tesseract validado E2E nesta máquina). pytesseract e
Tesseract (langpacks por/eng) já presentes no ambiente.

**Plano original (realizado):**

1. **Core novo**: `src/core/document/ocr.py` com
   `is_available()` (gateia `shutil.which("tesseract")` +
   `import pytesseract`) e `ocr_pdf(path, output_dir, lang="por",
   dpi=300, progress_cb=)`. Híbrido: usa texto nativo da página
   quando presente, OCR só nos caminhos onde a camada de texto está
   vazia.
2. **`DocumentArgs`**: `ocr_lang: str = "por"`, `ocr_dpi: int = 300`.
3. **GUI**: habilitar o card `ocr` (padrão `_UNAVAILABLE` do
   módulo Imagens — `blocks/ai.py`). Dropdown de idioma
   (`por`/`eng`/`por+eng`/`spa`) + seg/slider de DPI (150/300).
   `worker.py` emite `document_op_done` com `extra_stats={"word_count":
   n}`. `pipeline_log.py` ganha verbo "Reconhecendo texto" / label
   "OCR".
4. **CLI**: `document ocr <pdf> --lang por --dpi 300` (sub-subparser).
5. **Testes**:
   - `is_available()`: mockar `shutil.which` → `None` + import
     mockado via `mocker.patch.dict("sys.modules", {...})`.
   - `ocr_pdf` caminho **texto nativo**: usar fixture `sample_pdf`
     (já tem texto) → não invoca Tesseract → `word_count > 0`. Unit.
   - `ocr_pdf` caminho **OCR**: gerar PDF só-imagem via
     `images_to_pdf` de um PNG; mockar
     `pytesseract.image_to_string` → cobre o ramo sem exigir
     Tesseract no CI. Unit.
   - E2E real com Tesseract → marcar `integration` (skip
     automático se binário ausente).
6. **Doc**: README seção "Dependências externas" recebe Tesseract +
   language packs (`por.traineddata`, `eng.traineddata`).
7. **Ciclo fechado**: `analyze` (documento) já roda sobre `.txt` —
   PDF escaneado → OCR → texto → LLM.

**Arquivos a tocar (resumo):**

```
src/core/document/ocr.py                 (NOVO)
src/core/document/args.py                (ocr_lang, ocr_dpi)
src/gui/modules/document/blocks/ocr_block.py    (NOVO)
src/gui/modules/document/{form_view,worker,pipeline_log}.py
src/cli/document.py                      (sub-subcomando ocr)
tests/core/document/test_ocr.py          (NOVO)
README.md / CLAUDE.md                    (Tesseract no PATH)
```

**Pré-requisito do ambiente:** instalar Tesseract (`choco install
tesseract` ou download direto) e os language packs antes de E2E. O
CI funciona sem (testes `integration` pulam; testes `unit` usam
mocks).

---

## Definição de pronto do Tier 0 completo

Critérios do roadmap original atrelados a C e D — **agora cumpridos**:

- ✅ Vídeo embute/queima legenda (mux e burn) sem `WinError 32` no
  Windows (cwd+basename no burn-in). (Parte C)
- ✅ Card OCR habilita-se quando Tesseract presente; desabilita com
  aviso quando ausente; `document ocr` na CLI funciona. (Parte D)
- ✅ `analyze` roda sobre o `.txt` do OCR (loop PDF escaneado → LLM
  fechado — saída `_ocr.txt` consumível pelo `analyze`). (Parte D)
- ✅ `core/document/ocr.py` coberto por testes unit (mock pytesseract:
  fluxo híbrido texto-nativo/OCR, ramos de `is_available`) + 1
  integration real. (Parte D)

Critérios já cumpridos por A+B:

- ✅ `uv run pytest -m unit` verde — 428 testes.
- ✅ `core/subtitles.py` ≥ 95% — está em **100%**.
- ✅ `transcriber.py` ≥ 70% — está em **97%**.
- ✅ Ruff limpo; docstrings/logs em inglês; labels PT-BR.
- ✅ Transcrição exporta `.srt`/`.vtt` (GUI switch + CLI flags);
  arquivos aparecem no painel de resultados (4ª aba + botão de
  pasta).
- ✅ Sem dependência nova obrigatória; projeto permanece torch-free.
- ✅ Skills `testing`, `cli`, `design-system` atualizadas com os
  novos padrões e números.

---

## Próxima sessão — sugestão de ordem

1. **C primeiro** (sem dependência de binário externo).
   - `run_ffmpeg(cwd=)` é a mudança mais delicada — quebra Windows
     se errar.
   - Testar `mode="soft"` antes de `mode="hard"` (soft é `-c copy`,
     rápido e validável visualmente em qualquer player).
2. **D depois** (depende de Tesseract instalado para E2E real).
   - Começar pelos testes unit com mocks — valida a lógica do
     híbrido texto-nativo + OCR sem precisar do binário.
   - Quando Tesseract chegar ao PATH, adicionar 1-2 testes
     `integration` do caminho OCR de verdade.
   - Documentar o setup em `README.md` na seção de dependências
     externas.

Ambas independentes — se fizer sentido, podem entrar em PRs
paralelos.
