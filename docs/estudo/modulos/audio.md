# Módulo Áudio — o que muda em relação à fatia do Vídeo

Delta doc: **não** repete o padrão vertical (isso é a Sessão 2). Assume que você já entende
`core → worker → cli/view` e o contrato de eventos, e foca **só no que o Áudio adiciona de novo** — e
por quê. Referências cruzadas em vez de reexplicação.

> **Base:** [`../arquivos/sessao2-vertical-video.md`](../arquivos/sessao2-vertical-video.md) (o
> esqueleto), [`../conceitos/EVENTOS.md`](../conceitos/EVENTOS.md) (os eventos),
> [`../arquivos/ffmpeg.md`](../arquivos/ffmpeg.md) (o `run_ffmpeg`),
> [`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) (`blocks/`).

## O que é igual (aponta para a Sessão 2)

Tudo o esqueleto: `core/audio/` puro chamando `run_ffmpeg`; `VideoArgs`↔`AudioArgs` como contrato;
`cli/audio.py` traduz `Namespace`→`AudioArgs`; `gui/modules/audio/worker.py` reusado pela CLL **e** GUI
(Flet-free); `run_queue_pipeline` processando a fila; formulário quebrado em `audio/blocks/` (denoise,
normalize, silence, speed, output, presets). Se algo aqui te confundir, é sinal de reler a Sessão 2.

## Novidade 1 — o pipeline de **múltiplos estágios**

No Vídeo, um item sofre **uma** operação. No Áudio, um item passa por uma **cadeia** de pós-processos
em **ordem fixa**: `silêncio → denoise → velocidade → normalize → encode final`. O `_process_item` do
worker é uma sequência de blocos condicionais, cada um emitindo seus próprios eventos:

```python
# ── Post: Trim silence ──
if args.trim_silence:
    emit("audio_op_start", payload={"operation": "silence", ...})
    out_path = remove_silence(out_path, AUDIO_PROCESSED_DIR, ..., progress_cb=_silence_cb)
# ── Post: Denoise ──
if args.denoise:
    if not _denoise_available():
        emit("log", payload={"message": "[!] noisereduce not installed — skipping denoise."})
    else:
        out_path = _denoise_audio(out_path, AUDIO_PROCESSED_DIR, stationary=args.denoise_stationary)
# ── Post: Speed ── / ── Normalize ── / ── final encode ──
```

🔑 Repare: `out_path` é **reatribuído** a cada estágio — a saída de um alimenta o próximo (um mini
pipeline linear dentro de um item). Cada estágio emite `audio_op_start`/`progress_update`, então a
barra e o log refletem o passo atual. É o mesmo contrato de eventos da Sessão 3, mas emitido **várias
vezes por item** em vez de uma. O **encode final** existe para consertar o denoise (que sempre gera
`.wav`) e aplicar mono/sample-rate de uma vez.

## Novidade 2 — auto-detecção da entrada

O Áudio decide a operação pela **natureza** do item, não por uma flag:

```python
if item.kind == "url":            operation = "download"     # baixa
elif suffix in VIDEO_EXTENSIONS:  operation = "extract"      # extrai áudio do vídeo
elif suffix in AUDIO_EXTENSIONS:  operation = "convert"      # converte
```

🔑 URL → baixa; vídeo local → extrai a trilha; áudio local → converte. O mesmo formulário serve aos
três porque a decisão é do worker. (No Vídeo, a operação vem do subcomando; aqui, do tipo do arquivo.)

## Novidade 3 — gate de extra opcional (degradação graciosa)

O `denoise` depende do pacote `noisereduce` (extra opcional). O worker checa `_denoise_available()` e,
se faltar, **emite um log e pula** — não quebra:

```python
if args.denoise:
    if not _denoise_available():
        emit("log", payload={"message": "[!] noisereduce not installed — skipping denoise."})
    else:
        out_path = _denoise_audio(...)
```

🔑 É a **regra nº 6** (degradação graciosa) em ação, e o mesmo padrão `is_available()` que você verá no
RAG/ML ([`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md) §7): recurso ausente
desabilita a etapa com uma dica, nunca estoura. O bloco `denoise.py` (Sessão de decomposição) expõe o
toggle; o worker respeita o gate.

## Novidade 4 — áudio não toca pelo Flet (`ft.Audio` não existe)

O Áudio tem um **reprodutor embutido** (A/B Original|Processado + card de loudness). Como
[`../conceitos/FLET_GUI.md`](../conceitos/FLET_GUI.md) §6 avisa, **`ft.Audio` não existe** no Flet
0.85 — a reprodução usa `sounddevice` + ffmpeg (`audio_player.py`), fora do Flet. É a mesma lição de
"a GUI amarra, o trabalho real mora fora": o Flet só desenha os botões; o som sai pelo `sounddevice`.

## Novidade 5 — o quirk de Windows do downloader

O `FFmpegExtractAudio` do yt-dlp cria um `.temp.<ext>` **no diretório do arquivo de entrada**
(hardcoded), e o Defender às vezes trava o rename. A mitigação: rodar download+pós num
`tempfile.mkdtemp()` e mover com `shutil.move`. É o primo do quirk `FFmpegVideoConvertor` do Vídeo — a
mesma família de dores de plataforma (candidato ao futuro `APENDICE_WINDOWS_HARDWARE.md`).

---

# Perguntas de fixação (comparativas)

1. No Vídeo, um item sofre **uma** operação; no Áudio, uma **cadeia**. Como o worker encadeia os
   estágios? (dica: o que acontece com `out_path` a cada passo?)
2. Por que o Áudio auto-detecta a operação pelo tipo do item, enquanto o Vídeo a recebe do subcomando?
3. Se o `noisereduce` não estiver instalado, o que acontece quando você liga o denoise? Que regra do
   projeto isso ilustra?
4. Por que a reprodução de áudio **não** usa um controle do Flet? O que ela usa, e por quê?
5. Um mesmo item de áudio pode emitir `audio_op_start`/`progress_update` **várias vezes**. Por quê — e
   como o painel da GUI ainda mostra tudo coerente? (ligue ao [`../conceitos/EVENTOS.md`](../conceitos/EVENTOS.md))
