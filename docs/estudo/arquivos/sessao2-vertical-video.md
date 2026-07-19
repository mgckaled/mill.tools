# Sessão 2 — A fatia vertical: `video convert` de ponta a ponta

Este é o **coração** do estudo: seguir **uma** operação — converter um vídeo — atravessando as quatro
camadas (`core → cli → worker → view → testes`) para internalizar o **padrão que se repete em todos os
módulos**. Escolhemos `convert` de propósito: é a operação mais simples que **reencontra a espinha**
(ela chama o `run_ffmpeg` que já dissecamos). As 7 outras operações do Vídeo e o download via yt-dlp
ficam de fora aqui — entram na Sessão 4.

> **Pré-requisitos:** os três guias de conceito da Sessão 2 — [`FLET_GUI.md`](../conceitos/FLET_GUI.md),
> [`CLI.md`](../conceitos/CLI.md), [`TESTES.md`](../conceitos/TESTES.md) — e a espinha
> ([`ffmpeg.md`](ffmpeg.md), [`utils.md`](utils.md)). Aqui **não** reexplicamos esses conceitos;
> referenciamos.
>
> **Método:** seguimos um comando concreto —
> `uv run main.py video convert filme.mkv --codec h264 --container mp4` — e vemos cada string virar
> objeto, chamar função, gerar comando ffmpeg e emitir evento. Fazemos o trace **CLI-primeiro** (menos
> peças) e depois vemos **o que muda na GUI**.

---

## Mapa da fatia (o esqueleto que se repete)

```
                          ┌─────────────────────────────────────────────┐
CLI:  main.py ─dispatch─► cli/video.py::run_video_cli                    │
                          │  traduz Namespace → VideoArgs                │
                          └───────────────┬─────────────────────────────┘
                                          │  (mesmo worker!)
GUI:  view.py::_on_start ─────────────────┤
      (thread daemon)                     ▼
                          gui/modules/video/worker.py::run_video_pipeline
                          │  run_queue_pipeline → _process_item          │
                          │  chama o core + emit(eventos)                │
                          └───────────────┬─────────────────────────────┘
                                          ▼
                          core/video/converter.py::convert_video   (PURO)
                          │  monta o cmd ffmpeg + progress_cb            │
                          └───────────────┬─────────────────────────────┘
                                          ▼
                          core/ffmpeg.py::run_ffmpeg   (a espinha!)
```

🔑 A lição holística já está no desenho: **CLI e GUI convergem no mesmo worker**, que chama o mesmo
core puro. Um core, duas bordas. Guarde isso — é o que a fatia inteira prova.

---

# PARTE 1 — O núcleo puro: `core/video/converter.py`

Começamos de baixo (direção da dependência). A função que faz o trabalho real:

```python
VCODEC_MAP = {
    "copy": ["-c:v", "copy"],
    "h264": ["-c:v", "libx264", "-preset", "medium"],
    "h265": ["-c:v", "libx265", "-preset", "medium"],
    "vp9":  ["-c:v", "libvpx-vp9"],
}
CONTAINER_EXT = {"mp4": "mp4", "mkv": "mkv", "webm": "webm", "avi": "avi"}

def convert_video(src, out_dir, container="mp4", vcodec="copy", progress_cb=None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = CONTAINER_EXT.get(container, "mp4")
    out_path = out_dir / f"{sanitize_filename(src.stem)}_converted.{ext}"
    codec_flags = VCODEC_MAP.get(vcodec, ["-c:v", "copy"])
    cmd = (
        ["ffmpeg", "-y", "-i", str(src)]
        + codec_flags
        + ["-c:a", "copy", "-progress", "pipe:1", "-nostats", str(out_path)]
    )
    total_secs = get_video_info(src).duration if progress_cb else None
    return run_ffmpeg(cmd, out_path, total_secs=total_secs, progress_cb=progress_cb)
```

Ponto por ponto, com o `--codec h264 --container mp4` do nosso comando:

- **`out_path = .../{stem}_converted.mp4`** — o nome de saída, com `sanitize_filename` (do doc da
  espinha [`utils.md`](utils.md)) limpando o stem. `CONTAINER_EXT.get("mp4", "mp4")` resolve a
  extensão. Saída no dir canônico `VIDEO_PROCESSED_DIR` (quem passa é o worker).
- **`codec_flags = VCODEC_MAP.get("h264", ...)`** → `["-c:v", "libx264", "-preset", "medium"]`. Um
  **dicionário como tabela de tradução** "nome amigável → flags do ffmpeg". Se o vcodec fosse `copy`,
  seria `["-c:v", "copy"]` (sem reencodar — rápido). 🔑 Note o comentário `# no NVENC (CPU-only by
  design)`: a decisão de projeto "encode 100% CPU" (do CLAUDE.md) vive aqui, materializada na ausência
  de um `h264_nvenc` no mapa.
- **`cmd = [...]`** — a **lista de argumentos** do ffmpeg montada à mão (a `list[str]` que o
  `run_ffmpeg` espera — [`ffmpeg.md`](ffmpeg.md) §assinatura). `-i str(src)` é a entrada; `-c:a copy`
  copia o áudio sem reencodar; **`-progress pipe:1 -nostats`** é a flag que faz o ffmpeg emitir
  progresso legível no stdout (é o que o `run_ffmpeg` lê no seu Bloco 3!).
- **`total_secs = get_video_info(src).duration if progress_cb else None`** — só descobre a duração
  (via ffprobe) **se** alguém quer progresso. É a economia: sem callback, não paga o ffprobe. A
  duração é o denominador que transforma "segundos processados" em porcentagem.
- **`return run_ffmpeg(cmd, out_path, total_secs=..., progress_cb=...)`** — 🔑 **o reencontro com a
  espinha.** Todo o trabalho de processo, thread do stderr, deadlock e validação está lá dentro,
  estudado no [`ffmpeg.md`](ffmpeg.md). Aqui você vê `run_ffmpeg` sendo **chamado de verdade**, e o
  `progress_cb` sendo **repassado** — o callback que o core empurra sem saber quem o recebe.

🔑 Repare: `convert_video` **não sabe** se roda pela CLI ou pela GUI. É `core/` puro (regra nº 1): sem
Flet, sem `print`, dependência de progresso **injetada** (`progress_cb`). Testável sem GUI nenhuma.

## O contrato de dados: `core/video/args.py`

Antes de subir, a peça que as bordas preenchem — o `VideoArgs`:

```python
@dataclass
class VideoArgs:
    items: list[InputItem] = field(default_factory=list)
    operation: str = "download"
    # Convert
    vcodec: str = "copy"
    out_container: str = "mp4"
    # Trim / Compress / Resize / ... (campos de todas as operações)
```

🔑 Um **dataclass** (como o `InputItem` da espinha) que carrega **todos** os parâmetros de **todas** as
8 operações do Vídeo. Cada borda preenche os campos que a operação escolhida usa e deixa o resto no
default. É o "formulário" único que viaja da borda até o worker. `items` é a lista de `InputItem`
(URL/local) do doc de fundação [`io_types` no guia](../GUIA_ESTUDO.md).

---

# PARTE 2 — A borda CLI: `cli/video.py::run_video_cli`

Já vimos o parser (`add_video_parser`) no [`CLI.md`](../conceitos/CLI.md) §3. Foco agora no **runner**, que
traduz o `Namespace` do argparse no `VideoArgs`:

```python
def run_video_cli(ns: argparse.Namespace) -> None:
    from src.gui.modules.video.worker import run_video_pipeline    # ← importa o worker da GUI!
    check_dependencies()
    op = ns.video_op
    item = InputItem(kind="local", value=str(Path(ns.file).resolve()))   # convert → arquivo local
    args = VideoArgs(
        items=[item],
        operation=op if op != "extract-audio" else "extract_audio",
        vcodec=getattr(ns, "codec", "copy"),
        out_container=getattr(ns, "container", "mp4"),
        ...
    )
    bus = CLIEventBus()
    cancel = threading.Event()
    success = run_video_pipeline(args, bus, cancel, install_log_handler=False)
    if not success:
        sys.exit(1)
```

O trace do nosso comando `video convert filme.mkv --codec h264 --container mp4`:

1. `ns.video_op == "convert"`, `ns.file == "filme.mkv"`, `ns.codec == "h264"`, `ns.container == "mp4"`
   (o parser já preencheu — [`CLI.md`](../conceitos/CLI.md) §2.3).
2. `InputItem(kind="local", value=<caminho absoluto de filme.mkv>)` — `resolve_input` nem é preciso
   aqui porque `convert` é sempre arquivo local; a CLI resolve direto.
3. `VideoArgs(..., vcodec="h264", out_container="mp4")` — os `getattr(ns, "codec", "copy")` pegam o
   valor **se existir** (por que `getattr`? porque o mesmo runner monta o `VideoArgs` para 8 operações
   e nem todas têm `--codec` — [`CLI.md`](../conceitos/CLI.md) §4.2).
4. **`CLIEventBus`** (não o `EventBus` da GUI) — a borda CLI usa o adaptador que imprime no terminal
   ([`CLI.md`](../conceitos/CLI.md) §5). `install_log_handler=False` evita log duplicado.
5. `run_video_pipeline(args, bus, cancel, ...)` — chama o **mesmo worker** que a GUI usa.

🔑 **O ponto que quebra a intuição:** a linha `from src.gui.modules.video.worker import
run_video_pipeline` — a **CLI importa código de `gui/`**. Isso parece violar a arquitetura ("cli não
fala com gui"). A explicação (registrada no [`CLI.md`](../conceitos/CLI.md) e na skill `architecture`): o
**worker é Flet-free** — ele só orquestra e chama `bus.emit(...)`, sem nenhum controle Flet. Por isso
pode ser reusado pela CLI. É a razão de o worker existir separado da view: a lógica de orquestração
mora no worker (reutilizável), e só a amarração visual mora na view (GUI-only). **Pergunta de fixação
adiante fixa isto.**

---

# PARTE 3 — O worker compartilhado: `gui/modules/video/worker.py`

O worker é o mesmo para CLI e GUI. Ele tem duas partes: um invólucro fino e o `_process_item`.

## 3.1 O invólucro delega para o runner genérico

```python
def run_video_pipeline(args, bus, cancel_event, *, install_log_handler=True) -> bool:
    return run_queue_pipeline(
        items=args.items,
        bus=bus,
        module_id=_MODULE_ID,          # "video"
        default_stage="video",
        cancel_event=cancel_event,
        process_item=_make_process_item(args),
        install_log_handler=install_log_handler,
    )
```

🔑 A **fila** (processar N itens em sequência), o cancelamento, a emissão de `progress_start`/
`task_done`/`task_error` — nada disso é reescrito por módulo. Vive no `_pipeline_runner.py`
(`run_queue_pipeline`), compartilhado por Áudio/Vídeo/Imagem. O worker só fornece o **`process_item`**:
o que fazer com **um** item. Esse é o contrato de eventos — assunto da Sessão 3 ([`EVENTOS.md`](../conceitos/EVENTOS.md)).

## 3.2 O `_process_item` (o miolo, para o ramo `convert`)

```python
def _process_item(emit, item, idx, total, cancel_event) -> str:
    effective_op = "download" if item.kind == "url" else args.operation   # local → "convert"
    emit("video_op_start", payload={"operation": effective_op, "item_name": ..., ...})
    t0 = time()

    def _progress_cb(ratio: float) -> None:
        emit("progress_update", payload={"current": ratio})               # ← a ponte!

    else:  # item local
        src = Path(item.value)
        info = get_video_info(src)
        emit("log", payload={"message": pipeline_log.fmt_video_info(info)})
        match effective_op:
            case "convert":
                emit("log", payload={"message": pipeline_log.fmt_convert_detail(args.vcodec, args.out_container)})
                out_path = convert_video(src, VIDEO_PROCESSED_DIR,
                                         container=args.out_container, vcodec=args.vcodec,
                                         progress_cb=_progress_cb)          # ← chama o core!
            case "trim": ...
    emit("video_op_done", payload={"output_path": str(out_path), "elapsed": ..., ...})
    return str(out_path)
```

O trace continua:

- **`effective_op`** — para um arquivo local, é `args.operation` (`"convert"`). Para uma URL, seria
  forçado a `"download"` (por isso o Vídeo auto-detecta pela `kind` do item).
- **`emit("video_op_start", ...)`** — o worker **avisa** que começou uma operação. `emit` é o helper
  ligado ao bus (CLI ou GUI); quem consome decide o que exibir. Detalhe em [`EVENTOS.md`](../conceitos/EVENTOS.md).
- 🔑 **`_progress_cb`** — **aqui se fecha o círculo da espinha.** Lá no [`ffmpeg.md`](ffmpeg.md) o
  `run_ffmpeg` chamava `progress_cb(ratio)` "sem saber quem era". Aqui você vê quem é: uma função que
  faz `emit("progress_update", {"current": ratio})`. A cadeia completa é:
  `run_ffmpeg` lê `out_time_us` do stdout → chama `_progress_cb(0.4)` → `emit(...)` → o bus leva à
  barra (GUI) ou ao `tqdm` (CLI). **Quatro camadas ligadas por injeção de dependência.**
- **`case "convert":`** — o `match` (switch do Python) despacha pela operação. Só o ramo `convert`
  interessa aqui: emite uma linha de log com os detalhes e chama `convert_video(...)` — a função pura
  da Parte 1 — passando `args.vcodec="h264"`, `args.out_container="mp4"` e o `_progress_cb`.
- **`emit("video_op_done", {...})`** — avisa que terminou, com o caminho de saída, o tempo decorrido e
  os tamanhos (para a GUI mostrar o card de resultado).
- **`return str(out_path)`** — devolve o caminho; o `run_queue_pipeline` o coleta em `output_paths`.

🔑 Note também o `except` que enriquece erros de **WinError 32** (arquivo travado pelo antivírus) com
uma dica acionável — o mesmo cuidado de plataforma que você viu nos quirks de Windows do Vídeo
(CLAUDE.md). O worker não deixa um erro cru chegar cru; ele o traduz para algo que o usuário entende.

---

# PARTE 4 — A borda GUI: `gui/modules/video/view.py`

Só **agora** o Flet entra. Compare com a CLI: onde a CLI monta `CLIEventBus` e chama
`run_video_pipeline` **síncrono**, a GUI dispara o worker numa **thread** e escuta os eventos numa
tela. O `build_video_module` monta tudo.

## 4.1 O disparo (o botão → thread daemon)

```python
def _on_start(args: VideoArgs) -> None:
    if pipeline_running[0]:
        return
    pipeline_running[0] = True          # trava navegação (app.py checa isto)
    cancel_event.clear()
    progress_panel.reset()
    form_panel.set_running(True)        # botão vira "Executando...", desabilita
    start_video_pipeline(args, bus, cancel_event)   # dispara a THREAD daemon
```

- **`pipeline_running[0] = True`** — o truque da **lista de 1 elemento** ([`FLET_GUI.md`](../conceitos/FLET_GUI.md)
  §4.2), compartilhado com o `app.py` para bloquear a troca de módulo durante o pipeline.
- **`start_video_pipeline(...)`** — lança o worker numa **thread daemon** (via `start_pipeline` do
  runner). 🔑 Por que thread? Porque converter demora, e rodar na thread da UI **congelaria** a tela
  ([`FLET_GUI.md`](../conceitos/FLET_GUI.md) §3.2). A thread emite eventos; a UI (na thread dela) os recebe.

## 4.2 O painel que escuta (`ProgressPanel`)

```python
progress_panel = build_progress_view(page, on_cancel=_on_cancel, on_done=_on_done,
                                     owner_id="video", on_show_results=_render_video_results)
```

🔑 **`owner_id="video"`** — o painel só reage a eventos cujo `module_id == "video"`, ignorando os de
outros módulos ([`FLET_GUI.md`](../conceitos/FLET_GUI.md) §4.5, e a fundo em [`EVENTOS.md`](../conceitos/EVENTOS.md)). É o
escopo de eventos. Quando o worker emite `progress_update`, esse painel move a barra; quando emite
`task_done`, chama `_on_done` → `_render_video_results` mostra os cards de saída.

## 4.3 A ponte de saída (bridges)

```python
def _transcribe(_e, _path=str(p)) -> None:
    nav[0]("transcription", {"file": _path})       # manda o arquivo para a Transcrição
```

O card de resultado, se for áudio, oferece "Transcrever"/"Processar no Áudio" — que chamam
`navigate_to` com um payload ([`FLET_GUI.md`](../conceitos/FLET_GUI.md) §4.4). É a **bridge** entre módulos:
Vídeo→Transcrição. E `_on_mount` faz o inverso (recebe um `{"file": ...}` de outro módulo).

---

# PARTE 5 — Os testes: `tests/core/video/` e `tests/cli/`

Dois níveis, exatamente como o [`TESTES.md`](../conceitos/TESTES.md) ensinou.

## 5.1 Teste de integração do core (ffmpeg de verdade)

```python
pytestmark = pytest.mark.integration     # ffmpeg REAL — pulado sem ffmpeg no PATH

def test_convert_video_copy_keeps_container(sample_mp4, out_dir):
    from src.core.video.converter import convert_video
    out = convert_video(sample_mp4, out_dir, container="mp4", vcodec="copy")
    assert out.exists()
    assert out.suffix.lower() == ".mp4"
    assert out.stat().st_size > 1000
```

🔑 É **integração** ([`TESTES.md`](../conceitos/TESTES.md) §1.3): usa a fixture `sample_mp4` (um MP4 real gerado
por ffmpeg no `conftest.py`) e roda o ffmpeg **de verdade** para provar que `convert_video` produz um
arquivo válido. Sem ffmpeg no PATH, o hook `pytest_collection_modifyitems` o pula automaticamente.

## 5.2 Teste unitário da CLI (worker mockado)

```python
@pytest.mark.unit
def test_run_video_cli_extract_audio_normalises_op_name(mocker, tmp_path):
    mocker.patch("src.utils.check_dependencies")
    mock_pipeline = mocker.patch("src.gui.modules.video.worker.run_video_pipeline", return_value=True)
    ns = _parse("extract-audio", str(f), "--fmt", "wav")
    ns.func(ns)
    args = mock_pipeline.call_args.args[0]
    assert args.operation == "extract_audio"     # kebab→snake
    assert args.audio_fmt == "wav"
```

🔑 É **unitário** ([`TESTES.md`](../conceitos/TESTES.md) §4): **mocka** o `run_video_pipeline` (não quer rodar o
pipeline; quer só provar que a CLI **traduziu** o `Namespace` no `VideoArgs` certo). Repare no alvo do
patch — `src.gui.modules.video.worker.run_video_pipeline` — é onde o runner da CLI **importa** a
função ([`TESTES.md`](../conceitos/TESTES.md) §4.3, "patch onde é usado"). E verifica a **interação**
(`call_args`), não um valor de retorno — perfeito para a camada de tradução.

---

## Síntese da fatia

O que esta operação te ensinou, e que se repete em **todo** módulo:

1. **Direção da dependência:** `core` puro embaixo → `worker` orquestra → `cli`/`view` são bordas.
2. **`Args` como contrato:** um dataclass carrega os parâmetros da borda até o core.
3. **Um worker, duas bordas:** CLI (síncrona, `CLIEventBus`) e GUI (thread, `EventBus`) chamam o
   **mesmo** `run_video_pipeline` porque ele é Flet-free.
4. **A cadeia do `progress_cb`:** `run_ffmpeg` → `_progress_cb` → `emit` → barra/tqdm. Injeção de
   dependência ligando quatro camadas.
5. **Dois níveis de teste:** integração no core (ffmpeg real), unitário na borda (worker mockado).

---

## Perguntas de fixação

Responda sem consultar; confira depois nos arquivos citados.

1. Siga o `--codec h264` desde o terminal: em qual arquivo e linha ele vira um argumento **do ffmpeg**?
   (dica: `VCODEC_MAP`)
2. Por que `convert_video` recebe `progress_cb` como parâmetro em vez de emitir eventos ela mesma?
   O que isso permite?
3. A CLI importa `run_video_pipeline` de `gui/modules/video/worker.py`. Por que isso **não** viola a
   arquitetura? O que torna o worker reutilizável pela CLI?
4. Onde exatamente o `progress_cb` do core vira uma atualização de barra na GUI? Descreva a cadeia
   completa (`run_ffmpeg` → ... → barra).
5. Por que o teste do core de `convert` é `integration` e o teste da CLI é `unit`? O que cada um
   mocka (ou não)?
6. Na GUI, por que o pipeline roda numa thread daemon em vez de na thread da UI? E como, então, a
   barra de progresso se move (já que a thread não pode tocar a UI direto)?
7. O que `owner_id="video"` no `ProgressPanel` garante? Que problema ele evita quando há vários
   módulos montados no mesmo `Stack`?

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. `cli/video.py` o coloca em `VideoArgs(vcodec="h264")`; em `core/video/converter.py`, o
   `VCODEC_MAP.get("h264")` o traduz para `["-c:v", "libx264", "-preset", "medium"]` — a linha que
   entra no `cmd` do ffmpeg.
2. Porque o core é puro e não conhece bordas. Recebendo o callback, a **mesma** função serve GUI
   (barra), CLI (tqdm) e testes (callback falso que anota valores).
3. Porque o worker é **Flet-free**: só orquestra e chama `bus.emit(...)`, sem nenhum controle de UI.
   O que é GUI-only mora na `view.py`; o worker é reutilizável por qualquer borda.
4. `run_ffmpeg` lê `out_time_us=` do stdout → chama `progress_cb(ratio)` → que é o `_progress_cb` do
   worker → `emit("progress_update", {"current": ratio})` → `pubsub` → o `ProgressPanel` (thread da
   UI) move a barra.
5. O teste do core quer provar que o ffmpeg **real** produz um arquivo válido (integração, pulado sem
   ffmpeg). O da CLI só quer provar a **tradução** `Namespace` → `VideoArgs` — o pipeline inteiro é
   mockado, então é unitário e roda em ms.
6. Na thread da UI, a conversão **congelaria** a tela. A thread daemon não pode tocar a UI (quirk da
   0.85), então ela só **emite eventos**; a UI os recebe via `pubsub` na thread dela e repinta.
7. Garante que o painel só reage a eventos com `module_id == "video"`. Sem isso, o log e a barra de
   qualquer outro módulo (todos montados no mesmo `Stack`) poluiriam a tela do Vídeo.

</details>

## Desafios

- **D1 (e se...?)** E se `convert_video` (o core) chamasse `emit("progress_update", ...)` diretamente,
  em vez de receber `progress_cb`? O código até funcionaria na GUI — mas o que quebraria no projeto
  como um todo?
- **D2 (projete)** Você vai adicionar a operação `watermark` ao módulo Vídeo (marca d'água de imagem
  sobre o vídeo, via filtro do ffmpeg). Liste **arquivo por arquivo** o que precisa ser tocado, da
  camada mais baixa à mais alta — e que tipo de teste cada camada ganha.
- **D3 (ache o bug)** Num teste unitário do converter, um colega escreveu
  `mocker.patch("src.core.ffmpeg.run_ffmpeg")`. O teste dele fica **lento** e falha em máquinas sem
  ffmpeg. Por quê?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — O core deixaria de ser puro: passaria a conhecer o bus/contrato de eventos (uma
  dependência de borda). A CLI e os testes teriam que arrastar essa infraestrutura; testar
  `convert_video` isolado exigiria um bus falso; e qualquer mudança no contrato de eventos tocaria o
  core. O `progress_cb` (um `Callable[[float], None]`) mantém a fronteira: o core empurra números,
  quem traduz para eventos é o worker.
- **D2** — (1) `core/video/converter.py` (ou arquivo novo): função pura `add_watermark(...)` montando
  o cmd ffmpeg → teste de **integração** (ffmpeg real). (2) `core/video/args.py`: campos novos no
  `VideoArgs`. (3) `cli/video.py`: sub-subparser `watermark` + tradução no `run_video_cli` → teste
  **unitário** (pipeline mockado, asserta o `VideoArgs`). (4) `gui/modules/video/worker.py`: um
  `case "watermark":` no `_process_item`. (5) `form_view.py`/blocks: os campos na GUI. Nenhuma
  mudança no runner genérico nem no contrato de eventos — eles já servem.
- **D3** — Patch **onde é definido**, não onde é usado. O `converter.py` importou `run_ffmpeg` no
  topo (`from src.core.ffmpeg import run_ffmpeg`), criando uma referência própria; o patch na origem
  não a alcança. O teste chama o ffmpeg **de verdade** sem o colega perceber. O alvo certo é
  `src.core.video.converter.run_ffmpeg`.

</details>

*Próximo: [`EVENTOS.md`](../conceitos/EVENTOS.md) (Sessão 3) abre a "caixa preta" do `emit` — o contrato de
eventos que liga o worker à tela.*
