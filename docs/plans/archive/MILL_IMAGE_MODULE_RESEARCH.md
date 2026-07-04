# mill.tools — Módulo Imagens (levantamento para novo PR)

> Documento de **pesquisa/spike**, não de implementação. Reúne libs, operações e o
> encaixe na arquitetura definida na Fase A (Module, InputSource, eventos genéricos,
> fila, bridge). O detalhamento do PR fica para depois, após as decisões em aberto.

## Escopo proposto

Módulo "Imagens" na mesma sidebar dos demais. Três famílias de operação:

1. **Conversão** — trocar formato/codec, otimizar tamanho.
2. **Manipulação** — redimensionar, cortar, girar, ajustar, marca d'água, etc.
3. **Melhorias** — remoção de fundo e (opcional/avançado) upscaling por IA.

O caso de uso central é **lote**: aplicar uma operação a N imagens de uma vez — encaixa
direto na fila sequencial já especificada no PR2.

---

## Stack recomendada

### Núcleo (obrigatório, 100% CPU)

| Lib | Papel | Observação |
|---|---|---|
| **Pillow (PIL fork)** | toda manipulação e a maioria das conversões | versão atual 12.x; lib Python pura, sem binário externo |
| **pillow-heif** (opcional) | ler/escrever HEIC/HEIF | necessário para fotos de iPhone; plugin separado |

Pillow 12 já lê/escreve **AVIF nativamente** (incl. sequências), além de JPEG, PNG, WebP
(animado), GIF (animado), TIFF, BMP, ICO, PPM, PCX, EPS, PSD (leitura) e PDF. HEIC continua
exigindo o plugin `pillow-heif`. O `pillow-avif-plugin` ficou redundante com o suporte nativo.

### Melhorias por IA (opcional, ver restrição de hardware)

| Lib | Papel | Custo |
|---|---|---|
| **rembg** | remoção de fundo | modelos 40–300 MB (u2net ~170 MB, silueta ~43 MB); ~1–2 GB total com onnxruntime; **roda em CPU** (lento, mas estável) |
| **Real-ESRGAN** | upscaling por IA | recomenda **≥4 GB VRAM**; 2 GB é apertado mesmo com tiling — ver abaixo |

---

## Restrição de hardware (MX150, 2 GB VRAM) — decisão crítica

A MX150 já é disputada entre Whisper (CUDA) e o Flet (DirectX), com histórico de BSOD por
uso concorrente de GPU documentado no `CLAUDE.md`. Implicações para o módulo Imagens:

- **Pillow é CPU-only e seguro** — toda manipulação/conversão entra sem risco.
- **rembg em CPU é viável** — lento por imagem, mas estável; não toca a GPU. Recomendado como
  a única feature de IA da primeira versão.
- **Upscaling por IA (Real-ESRGAN/GFPGAN) é arriscado neste hardware** — 2 GB de VRAM estoura
  fácil em 4×, e rodar CUDA junto com transcrição reabre o problema de GPU concorrente.

**Recomendação:** v1 do módulo = **só CPU** (Pillow + rembg-CPU). Upscaling por IA fica para
uma fase posterior e opcional, com tiling agressivo ou backend **ncnn-vulkan/CPU**, e **nunca
simultâneo** com um pipeline de transcrição ativo (a regra de bloqueio do PR2 já ajuda nisso).

---

## Operações candidatas

### Conversão
- Trocar formato: JPEG ⇄ PNG ⇄ WebP ⇄ AVIF ⇄ TIFF ⇄ BMP ⇄ GIF (e HEIC com plugin)
- Otimizar/comprimir: qualidade JPEG, `optimize` PNG, WebP lossless/lossy
- Controle de metadados EXIF: preservar ou remover
- Conversão de modo de cor: RGB / RGBA / grayscale / CMYK
- imagens → PDF e PDF → imagens (cruza com futuro módulo PDF)

### Manipulação
- Redimensionar (com/sem manter proporção), `thumbnail`, escala por %
- Cortar (manual, por proporção, auto-trim de bordas)
- Girar / espelhar / transpor; **auto-rotação por orientação EXIF**
- Marca d'água (texto ou imagem, com opacidade/posição)
- Borda / padding / redimensionar canvas / fundo sólido para transparência
- Ajustes (`ImageEnhance`): brilho, contraste, saturação, nitidez
- Filtros (`ImageFilter`): blur, sharpen, etc.; `ImageOps`: autocontrast, equalize, grayscale
- Gerar favicon/ICO multi-resolução
- Colagem em grade / contact sheet a partir de várias imagens

### Melhorias
- Remoção de fundo (rembg, CPU) → saída PNG com alpha
- *(fase posterior, opcional)* Upscaling por IA

---

## Encaixe na arquitetura mill.tools

### Core (funções puras, sem Flet)
```
src/core/image/
├── __init__.py
├── converter.py   ← formato, qualidade, modo de cor
├── transform.py   ← resize, crop, rotate, watermark, ajustes
├── enhance.py     ← rembg (e futuro upscaling)
└── info.py        ← dimensões, formato, EXIF, tamanho
```

### GUI (módulo na sidebar)
```
src/gui/modules/image/
├── __init__.py
├── form_view.py   ← operação + parâmetros + InputSource
├── worker.py      ← emite os eventos genéricos do PR2
└── view.py        ← build_image_module() → Module
```

### Contratos do PR2 reaproveitados
- **Module**: `id="image"`, label "Imagens", ícone `ft.Icons.IMAGE_OUTLINED` / `IMAGE`.
- **InputSource**: imagens são tipicamente **locais** (`kind="local"`); download por URL é
  possível mas secundário. `accepted_extensions`: `.jpg .jpeg .png .webp .avif .tiff .bmp .gif`
  (+ `.heic .heif` se o plugin estiver instalado).
- **Fila sequencial**: o lote é o caso natural aqui — converter/redimensionar uma pasta
  inteira. `queue_progress(current_item, total_items, item_name)` cobre o progresso.
- **Eventos genéricos**: a maioria das operações Pillow é quase instantânea, então o progresso
  relevante é o **da fila** (item N/M). Exceções com barra interna: rembg e upscaling.
- **Output**: nova pasta `output/image/processed/` + nova constante `IMAGE_PROCESSED_DIR` em
  `utils.py`. **Atenção:** a estrutura `output/` definida no PR1 não previu `image/` — é preciso
  ou retroajustar o PR1 ou criar a pasta neste PR.
- **Bridge**: nenhum cruzamento crítico com outros módulos por ora. Candidato futuro:
  Imagens → PDF (montar PDF a partir de imagens), quando o módulo PDF existir.

### Dependências externas
Diferente de Áudio/Vídeo (que dependem de `ffmpeg`/`yt-dlp`), o módulo Imagens é quase
todo **lib Python** — não exige binário externo. `check_dependencies()` só precisaria validar:
- `pillow-heif` instalado **se** o usuário escolher operação HEIC;
- `onnxruntime`/modelo baixado **se** usar remoção de fundo.

---

## Decisões em aberto (definir antes de fechar o PR)

1. **Escopo de IA na v1**: só Pillow + rembg-CPU, ou já incluir upscaling? (recomendo adiar o upscaling)
2. **HEIC**: incluir `pillow-heif`? (relevante se você lida com fotos de iPhone)
3. **Entrada por URL**: baixar imagem de URL faz sentido, ou só arquivo/pasta local?
4. **Lote recursivo**: aceitar uma pasta inteira (e subpastas) como entrada?
5. **`output/image/` no PR1**: retroajustar a estrutura agora ou criar só quando o módulo nascer?

---

## Fontes
- [Pillow — Image file formats (12.x)](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html)
- [pillow-heif (PyPI / GitHub)](https://github.com/bigcat88/pillow_heif)
- [pillow-avif-plugin (PyPI)](https://pypi.org/project/pillow-avif-plugin/)
- [rembg (GitHub)](https://github.com/danielgatis/rembg)
- [Real-ESRGAN upscaling — requisitos de VRAM/tiling](https://docs.clore.ai/guides/image-processing/real-esrgan-upscaling)
