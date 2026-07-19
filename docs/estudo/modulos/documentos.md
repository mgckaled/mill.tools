# Módulo Documentos — o que muda em relação à fatia do Vídeo

Delta doc. O Documentos é o "primo" do Imagem: também tem core puro de biblioteca (sem ffmpeg), mas
com **pymupdf** em vez de Pillow, e uma ideia própria — o **OCR híbrido**.

> **Base:** [`../arquivos/sessao2-vertical-video.md`](../arquivos/sessao2-vertical-video.md),
> [`imagem.md`](imagem.md) (o paralelo core-puro-de-biblioteca),
> [`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) (`blocks/`),
> [`../conceitos/TESTES.md`](../conceitos/TESTES.md) (pymupdf testado de verdade).

## O que é igual

Esqueleto `core → worker → cli/view`, `DocumentArgs`, worker reusado, contrato de eventos, formulário
em `document/blocks/` (13 operações). Como no Imagem, o core é **em-processo** (sem subprocesso), então
o worker é simples: chama a função pura e emite `op_start`/`op_done`, sem `progress_update` contínuo.

## Novidade 1 — core pymupdf (sem ffmpeg, e nem Pillow)

`core/document/` usa **pymupdf** (biblioteca de PDF): `processor.py` (7 funções — merge, split,
compress, rotate, watermark, stamp, encrypt), `converter.py` (`pdf_to_images`/`images_to_pdf`/
`extract_text`), `info.py`, `qr.py`. É a terceira "família" de core que você vê: ffmpeg (áudio/vídeo,
externo), Pillow (imagem, em-processo), pymupdf (documento, em-processo). 🔑 A arquitetura é a mesma; só
muda a ferramenta que o core embrulha. Reconhecer isso é o objetivo da Sessão 4.

## Novidade 2 — OCR **híbrido** (a ideia própria do módulo)

Um PDF pode ter texto **nativo** (selecionável) ou ser um **scan** (imagem de página). O OCR do
Documentos é híbrido: para cada página, usa a **camada de texto nativa** se existir; só **rasteriza**
(vira imagem a 300 DPI) e roda **Tesseract** nas páginas escaneadas.

🔑 Por que isso importa? Rodar OCR em tudo seria lento e degradaria texto que já era perfeito. Usar só
a camada nativa perderia as páginas escaneadas. O híbrido pega o melhor dos dois — e fecha um fluxo
completo: **PDF escaneado → OCR → texto → `analyze`** (a análise de IA da Transcrição, reusada). O
texto extraído é indexável no RAG ([`../conceitos/RAG.md`](../conceitos/RAG.md)), como o `_ocr.txt` do
Imagem.

## Novidade 3 — reúso cross-módulo: `render_first_page_png`

`info.py` tem `get_pdf_info` + `render_first_page_png` — e este último é **reusado pela Biblioteca**
para gerar a miniatura de um PDF ([`biblioteca.md`](biblioteca.md)). É um exemplo de fonte única
atravessando módulos: a lógica de "desenhar a 1ª página" mora num lugar só, e o hub de Biblioteca a
consome sem reimplementar.

## Novidade 4 — `analyze` é só-GUI (13 ops GUI / 12 CLI)

Uma assimetria pequena mas instrutiva: a operação `analyze` existe na GUI mas **não** na CLI (13 vs.
12). Nem toda operação precisa das duas bordas — o `analyze` depende do pipeline de IA e faz mais
sentido na tela. Contraste com o Vídeo, onde CLI e GUI cobrem as mesmas operações.

## Novidade 5 — testes: pymupdf **de verdade**

Como o Imagem com Pillow, os testes de `tests/core/document/` **não mockam** pymupdf — usam as fixtures
`sample_pdf`/`sample_pdf_with_images` (PDFs reais gerados por pymupdf, com `importorskip`). Mesma
justificativa: dependência hard, in-process, sem rede/GPU → qualifica como `unit` e exerce o
comportamento real ([`../conceitos/TESTES.md`](../conceitos/TESTES.md) §pymupdf/DuckDB).

---

# Perguntas de fixação (comparativas)

1. Documentos, Imagem e Vídeo têm cores baseados em bibliotecas diferentes. Liste qual biblioteca cada
   um embrulha e qual é externa (subprocesso) vs. em-processo.
2. O que é OCR "híbrido"? Por que não rodar Tesseract em todas as páginas?
3. `render_first_page_png` é definido em `core/document/info.py` mas usado pela Biblioteca. Que
   princípio isso ilustra?
4. Por que `analyze` existe na GUI mas não na CLI? O que isso diz sobre "nem toda operação precisa das
   duas bordas"?
5. Por que os testes de Documentos rodam pymupdf de verdade, como o Imagem roda Pillow, mas o Vídeo
   mocka o ffmpeg?

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. Áudio/Vídeo → **ffmpeg** (externo, subprocesso); Imagem → **Pillow** (em-processo); Documentos →
   **pymupdf** (em-processo). Mesma arquitetura, só muda a ferramenta embrulhada.
2. Por página: usa a camada de texto **nativa** se existir; só rasteriza (300 DPI) + Tesseract nas
   páginas **escaneadas**. OCR em tudo seria lento e degradaria texto que já era perfeito; só nativo
   perderia os scans.
3. Fonte única atravessando módulos: a lógica de "desenhar a 1ª página" mora num lugar só, e a
   Biblioteca a consome para thumbnails sem reimplementar.
4. Porque depende do pipeline de IA e faz mais sentido na tela. Lição: as bordas não precisam ser
   espelhos perfeitos — cada operação vive onde tem valor.
5. pymupdf é dependência hard e **in-process** (roda real, qualifica como `unit`); o ffmpeg é
   **processo externo** (mockado nos unitários).

</details>

## Desafios

- **D1 (projete)** Nova operação: **carimbar assinatura** (uma imagem PNG posicionada em página/
  coordenada escolhidas). Em que arquivo do core ela entra, e o que mais precisa ser tocado até
  chegar à GUI e à CLI?
- **D2 (e se...?)** E se o OCR híbrido não existisse e o módulo rasterizasse + rodasse Tesseract em
  **todas** as páginas? Para um PDF de 300 páginas com 290 nativas, estime as duas perdas.
- **D3 (ache o bug)** Um PR da Biblioteca adiciona `import pymupdf` no `thumbnails.py` e reimplementa
  ali o render da 1ª página "para não depender do módulo Documentos". Por que o revisor recusa?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — No `processor.py` (a 8ª função pymupdf — é irmã de `watermark`/`stamp`): função pura
  recebendo PDF, imagem, página e coordenadas. Depois: campos no `DocumentArgs`, bloco em
  `document/blocks/`, `case` no worker, sub-subparser na CLI, e teste `unit` com pymupdf real +
  fixture `sample_pdf`.
- **D2** — (1) **Tempo**: rasterizar a 300 DPI + Tesseract em 290 páginas que já tinham texto — de
  segundos para muitos minutos. (2) **Qualidade**: a camada nativa é perfeita; o OCR sobre a
  rasterização reintroduz erros de reconhecimento em texto que já estava certo. O híbrido paga o
  custo só nas ~10 páginas escaneadas.
- **D3** — Viola a fonte única: a lógica de "desenhar a 1ª página" já mora em
  `core/document/info.py::render_first_page_png`, e é **desenhada** para ser reusada (o core de
  Documentos é puro — depender dele não é acoplamento de borda). Duplicar = dois lugares para
  consertar o mesmo bug de render.

</details>
