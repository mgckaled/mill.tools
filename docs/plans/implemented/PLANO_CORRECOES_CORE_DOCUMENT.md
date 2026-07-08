# Plano — Correções do `core/document/`

> **Origem**: avaliação exploratória arquivo-a-arquivo (sessão Cowork, jul/2026). 7 arquivos / ~805 linhas.
> Formato padrão. O item principal exige investigação da API do pymupdf (context7) antes do fix.

## Checklist ativo de salvaguardas

| Salvaguarda | Resultado em `core/document/` |
|---|---|
| Escritas não-atômicas / `io_atomic` | **N/A-OK** — saídas são PDFs/imagens via pymupdf |
| Timeouts | **N/A-OK** — pymupdf é in-process (sem subprocess/rede) |
| Duplicação intra-pacote | **PARCIAL** — `get_pdf_info` re-implementa inline o raster que `render_first_page_png` já faz; `LANGS` duplicada com `image/ocr.py` |
| Docstring de pacote | **PARCIAL** — não cita `ocr`/`extract`/`pdf_to_images` |
| Strings PT no core | **OK** — pacote é EN (só os headers `--- Página N ---`, que são conteúdo user-facing) |

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline + verificação de default |
| 1 | O bug do `compress_pdf` (investigar antes de fixar) |
| 2 | Robustez |
| 3 | Miudezas |
| 4 | Verificação + docs |

---

## Fase 0 — Baseline + verificação

1. Suíte verde.
2. **[Família R2] `DocumentArgs.analyze_model = "qwen7b-custom"`**: o quarteto padronizou
   `gemma3-4b-custom` como default de resposta/análise local. Verificar o default real do
   `analyzer.analyze` e da GUI — se divergirem, alinhar (mesma decisão de produto já tomada).

## Fase 1 — `compress_pdf`: o parâmetro `image_quality` é aceito e **nunca usado**

O corpo do loop faz `doc.update_stream(xref, doc.extract_image(xref)["image"])` — reinsere os **bytes
originais** da imagem extraída, sem qualquer recompressão; `image_quality` (o slider 50–95 da GUI e a flag
`--image-quality` da CLI) não participa de nada. A redução de tamanho real vem só do
`save(garbage=4, deflate...)`. Agravante: reinjetar o payload de `extract_image` num stream cujo dict
(`/Filter`/`/ColorSpace`) não é atualizado é de eficácia duvidosa — o `try/except pass` engole qualquer
falha, então o loop pode ser um no-op integral.

1. Investigar com context7 a forma correta no pymupdf de recomprimir imagens embutidas com qualidade JPEG
   (caminhos candidatos: `Pixmap(doc, xref)` → `tobytes("jpg", jpg_quality=...)` → `page.replace_image`/
   `Document.update_stream` com dict coerente; ou o recurso nativo de recompressão do `save` em versões
   recentes).
2. Implementar a recompressão real honrando `image_quality`, com salvaguarda: pular imagens cuja
   recompressão *aumente* o tamanho (JPEG re-JPEG pode crescer) e imagens com máscaras/alpha.
3. Se a investigação concluir que o custo não vale (decisão legítima), **remover o parâmetro e o slider**
   e documentar que compress = garbage+deflate — o que não pode ficar é o controle placebo.
4. Teste de integração: PDF com imagem grande → saída menor com qualidade 50 vs 95 (ou teste do caminho
   escolhido no item 3).

## Fase 2 — Robustez

1. **`converter.images_to_pdf`**: (a) **sem `exif_transpose`** — fotos de celular viram páginas deitadas
   (mesmo bug-família do `background.py` do plano image); (b) abre **todas** as imagens na RAM antes de
   salvar (200 fotos = pico de GB) — usar `exif_transpose` + considerar redimensionamento opcional ou
   inserção incremental via pymupdf; no mínimo, documentar o limite.
2. **PDFs criptografados**: nenhuma operação checa `doc.needs_pass` — o usuário recebe erro cru do pymupdf.
   Um check no início das operações com mensagem clara ("PDF protegido por senha") cobre o pacote inteiro
   (helper pequeno).
3. **`info.get_pdf_info`**: varre **todas** as páginas atrás de texto (`has_text`) — num PDF escaneado de
   500 páginas isso é lento para um metadado de preview; cap nas primeiras ~20 páginas (documentando a
   heurística). Reusar `render_first_page_png` no lugar do raster inline (dedup do checklist).

## Fase 3 — Miudezas

1. `image/ocr.py` importa `_resolve_tesseract_cmd` (privado) de `document/ocr` — promover a API pública
   (`resolve_tesseract_cmd`) e manter alias; mover `LANGS` para um único dono (document exporta, image
   importa).
2. `stamp_pdf`/`watermark_pdf` em páginas com `rotation` ≠ 0 saem de lado (coordenadas no espaço
   não-rotacionado) — corrigir se trivial (`page.derotation_matrix`), senão registrar como limitação
   conhecida no ROADMAP.
3. `__init__.py`: docstring completo (incluir ocr/extract/pdf_to_images/images_to_pdf).
4. Registrar no ROADMAP: `processor.py` com 346 linhas (acima do alvo 300, abaixo do teto) — **dividir ao
   tocar** na próxima extensão.

## Fase 4 — Verificação + docs

1. Suíte completa verde (o pacote usa pymupdf REAL nos testes unit — regra de projeto; manter);
   `ruff`; cobertura sem regressão (processor 91% hoje — a Fase 1 deve **subir** isso, o loop do compress
   ganhará testes de verdade).
2. Re-auditar o checklist; CLAUDE.md §Documentos (afirma "compress" — conferir descrição pós Fase 1);
   HISTORY + mover para `implemented/`.

## Não-achados dignos de nota
- A extração híbrida do `ocr.py` (texto nativo por página; raster+Tesseract só nas escaneadas) está
  exemplar — não tocar.
- Saídas do pacote **sobrescrevem** por design (sufixos `_rotated90`, `_stamp`…) enquanto o pacote image
  uniquifica — convenções distintas entre pacotes; se incomodar, é decisão de produto para o ROADMAP,
  não correção.
- `_parse_page_ranges` está correto e bem testado (incluindo "8-" aberto) — não mexer.
