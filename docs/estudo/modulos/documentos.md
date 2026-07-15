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
