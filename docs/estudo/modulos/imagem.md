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

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. Porque o core é Pillow **em-processo**: rápido e síncrono, sem processo externo emitindo progresso.
   O worker vira "chama a função pura + `image_op_start`/`image_op_done`", sem os `progress_update`
   contínuos que o ffmpeg alimentava no Áudio.
2. Porque os arquivos internos (`_shared`, `ops`, `watermark`) são detalhe privado; o contrato é a
   API pública reexportada pelo `__init__`. Espelhar 1:1 só vale quando cada arquivo tem testes
   genuinamente independentes.
3. `ocr` (Tesseract → `.txt`) e `describe` (visão por LLM → descrição). O `_ocr.txt` cai em `output/`
   e o RAG o indexa — texto extraído de imagem vira corpus pesquisável.
4. Roda **depois** da transformação, sem tocar a assinatura das funções de transform — um passo extra
   opcional que não polui o núcleo, como o encode final do Áudio.
5. Pillow é dependência **hard e in-process** (sempre presente, sem rede/GPU) → roda real e ainda
   conta como `unit`. O ffmpeg é **processo externo** → mockado nos unitários, real só na integração.

</details>

## Desafios

- **D1 (projete)** O roadmap prevê **upscale** de imagem (aumentar resolução com IA). Decida: core
  puro Pillow ou extra opcional com gate? Onde mora, e o que muda na GUI se o extra faltar?
- **D2 (e se...?)** Alguém propõe adicionar "vídeo → GIF animado" como operação do módulo Imagem
  ("GIF é imagem, ora"). Por que a proposta está na família errada — e onde a operação deveria morar?
- **D3 (ache o bug)** Um PR adiciona gravação de EXIF **dentro** de cada função de
  `transform/ops.py` (novo parâmetro `exif_mode` em todas). Funciona — mas o revisor recusa. Com que
  argumento?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — Upscale com IA puxa um modelo (ONNX, como o rembg) → **extra opcional** (`[ai-image]` ou
  um novo), nunca no app base. A função mora em `core/image/` (ex.: `upscale.py`, como `background.py`),
  com `is_available()`. Na GUI, o gate desabilita o card com dica de instalação — regra nº 6, o mesmo
  molde do `remove_bg`.
- **D2** — Decodificar vídeo exige **ffmpeg** (processo externo) — a família do core de Imagem é
  Pillow em-processo, sem `run_ffmpeg`, sem progresso contínuo. A operação pertence ao **Vídeo**
  (que já embrulha o ffmpeg e tem a maquinaria de progresso); a saída `.gif` pode até aparecer na
  Biblioteca como imagem, mas o *processamento* é da família do ffmpeg.
- **D3** — Viola o desenho "EXIF como **pós-processo aditivo**": tocar a assinatura de **todas** as
  transforms para um aspecto transversal espalha a responsabilidade e quebra a pureza das funções
  (cada uma passaria a saber de metadados). O lugar do EXIF é a camada aditiva (`exif.py`) que roda
  **depois** de qualquer transform — um lugar só, nenhuma assinatura tocada.

</details>
