# Módulo Imagem — o que muda em relação à fatia do Vídeo

Delta doc: foca **só no que o Imagem adiciona de novo**. O salto principal é conceitual — o core aqui
**não usa subprocesso**; é Python puro (Pillow). Isso muda o formato da fatia inteira.

> **Base:** [`../arquivos/sessao2-vertical-video.md`](../arquivos/sessao2-vertical-video.md) (o
> esqueleto), [`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) (`blocks/` — o Imagem é o
> exemplo canônico), [`../conceitos/TESTES.md`](../conceitos/TESTES.md) (Pillow testado de verdade).

## O que é igual

O esqueleto `core → worker → cli/view`, o `ImageArgs` como contrato, o worker reusado por CLI e GUI, o
contrato de eventos. O formulário é quebrado em `image/blocks/` (convert, resize, crop, rotate,
watermark, border, adjust, filter, favicon, contact_sheet, remove_bg, ocr) — o **exemplo canônico** de
`blocks/` que a [`../conceitos/decomposicao.md`](../conceitos/decomposicao.md) usa.

## Novidade 1 (a grande) — core puro Pillow, **sem `run_ffmpeg`**

No Vídeo/Áudio, o core monta uma lista de argumentos e chama o processo externo `ffmpeg`. No Imagem,
`core/image/transform/` são **funções puras Pillow** — abrem a imagem, transformam em memória, salvam.
Nada de subprocesso, nada de `progress_cb` de processo externo.

🔑 **A consequência conceitual:** some toda a maquinaria da espinha [`../arquivos/ffmpeg.md`](../arquivos/ffmpeg.md)
(processo, thread do stderr, deadlock, `-progress pipe:1`). Uma transformação de imagem é **rápida e
síncrona** — não precisa de barra de progresso por porcentagem. Isso simplifica o worker: ele chama a
função pura e emite `image_op_start`/`image_op_done`, sem os `progress_update` contínuos que o ffmpeg
alimentava. **Comparar isso com o Áudio é a lição:** mesma arquitetura, mas a natureza do core (externo
vs. em-processo) muda o que flui pelo contrato de eventos.

## Novidade 2 — `transform/` é um **pacote** com API flat

`core/image/transform` não é um arquivo — é uma pasta (`transform/` com `_shared.py`, `ops.py`,
`watermark.py`) reexportada por um `__init__.py`. É a decomposição de um módulo de core grande (analógo
aos `blocks/` da GUI). 🔑 A nota de teste ([`../conceitos/TESTES.md`](../conceitos/TESTES.md) §estrutura):
os testes **não** espelham os arquivos internos — testam a API pública via
`from src.core.image.transform import X` num único arquivo de teste. Espelhar 1:1 só vale quando cada
arquivo interno tem testes genuinamente independentes.

## Novidade 3 — imagem → {imagem **ou** texto}

A maioria das operações é imagem→imagem, mas duas produzem **texto**: `ocr` (Tesseract → `.txt`) e
`describe` (visão por LLM → descrição). Por isso a GUI tem o toggle **Edição | Descrição IA**, e o
`_ocr.txt` gerado é **indexável no RAG** (fecha o ciclo com a Sessão 5 —
[`../conceitos/RAG.md`](../conceitos/RAG.md)). O `describe` usa um modelo de visão local (moondream) ou
de nuvem opt-in, roteado pelo `llm_factory` da espinha
([`../arquivos/llm_factory.md`](../arquivos/llm_factory.md)).

## Novidade 4 — EXIF como pós-processo **aditivo**

O tratamento de metadados EXIF (`preserve|strip|strip_gps|inject`) roda **depois** da transformação,
como uma camada aditiva que **não toca** a assinatura das funções de transform. É a mesma filosofia do
"encode final" do Áudio: um passo extra opcional que não polui o núcleo. O visor Before/After usa um
fundo xadrez para mostrar transparência (alfa) — detalhe de GUI, não de core.

## Novidade 5 — gates de extra: `[ai-image]` e `[ocr]`

- `remove_bg` (fundo) depende do `rembg` (extra `[ai-image]`, ONNX).
- `ocr` depende do Tesseract (extra `[ocr]`, binário no PATH).

Mesmo padrão de gate/degradação graciosa do denoise no Áudio: recurso ausente desabilita o card com
dica. `describe.is_available()`/`ocr.is_available()` seguem o mesmo molde de `embedder.is_available()`.

## Novidade 6 — testes: Pillow **de verdade**, com pegadinhas

Diferente do ffmpeg (mockado nos unitários), o Pillow roda **real** nos testes (é dependência hard,
in-process — [`../conceitos/TESTES.md`](../conceitos/TESTES.md) §pymupdf/DuckDB). Isso traz gotchas de
valor esperado que o `TESTES.md` documenta: o `crop` modo `ratio` e o branch `target_h > ih`; o `_save`
que converte modo `L` (grayscale) para RGB ao salvar JPEG (teste precisa usar PNG); imagens de teste
para `autotrim` salvas como PNG (JPEG tem artefatos). São exemplos perfeitos de "o teste ensina o
comportamento real do core".

---

# Perguntas de fixação (comparativas)

1. O core do Imagem não tem `run_ffmpeg` nem `progress_cb` de processo. Por quê? O que isso simplifica
   no worker, comparado ao Áudio?
2. `transform/` é um pacote, não um arquivo. Por que os testes **não** espelham seus arquivos internos?
3. Duas operações do Imagem produzem **texto** em vez de imagem. Quais, e como o `_ocr.txt` reconecta
   com o RAG da Sessão 5?
4. Por que o tratamento de EXIF é um pós-processo "aditivo"? Que analogia isso tem com o "encode final"
   do Áudio?
5. Nos testes, por que o Pillow roda de verdade enquanto o ffmpeg é mockado? (ligue à distinção
   dependência hard/in-process vs. externa do [`../conceitos/TESTES.md`](../conceitos/TESTES.md))
