# Histórico de decisões e entregas — mill.tools

Changelog em ordem cronológica inversa. **Uma entrada curta por marco**, com link para o plano
correspondente em [`plans/implemented/`](plans/implemented/) ou [`plans/archive/`](plans/archive/). O
detalhe completo vive no plano linkado; aqui fica só o "o quê + por quê" de cada entrega. Pendências
ficam em [`ROADMAP.md`](ROADMAP.md) e [`plans/active/`](plans/active/).

> Fonte única de história. CLAUDE.md e as skills apenas **apontam** para cá — não narram planos concluídos.

---

## Entregas (marcos)

### Correções dos arquivos soltos de `src/` + entry points (jul/2026)
Revisão exploratória arquivo-a-arquivo dos 9 `.py` soltos em `src/` (`__init__`, `__main__`, `analyzer`,
`formatter`, `llm_factory`, `llm_utils`, `prompter`, `transcriber`, `utils`) + `gui.py`/`main.py` na raiz —
os arquivos mais antigos do projeto (pré-mill.tools), ~2.120 linhas. **Fase 1 — bugs reais**:
`sanitize_filename` não removia `:` ASCII (só o wide colon fullwidth) — título tipo "Python: aula 1" virava
`Python:_aula_1.txt`, que no NTFS cria um Alternate Data Stream em vez de falhar visivelmente; `:` passou a
receber o mesmo tratamento do wide colon, e o stem ganhou cap de ~120 chars contra MAX_PATH.
`analyzer`/`formatter`/`prompter` faziam `response.content.strip()` cru — Gemini/GLM podem devolver
`.content` como lista de blocos (motivo de `llm_utils.extract_llm_text` existir), quebrando com
`AttributeError` em produção com modelo cloud; os 3 módulos passaram a rotear tudo por `extract_llm_text`.
`transcriber.transcribe`: `input()` de overwrite tratava `EOFError` (execução sem stdin) como crash — agora
trata como "não sobrescrever"; `sys.exit(0)` dentro do `except KeyboardInterrupt` saía de dentro de uma
função de biblioteca — a decisão de sair virou responsabilidade do `main.py`, e o cleanup do `.txt` parcial
generalizou pra qualquer exceção do loop, não só Ctrl-C. Barra de progresso: mídia local tinha
`meta["duration"]=0` → `tqdm(total=0)` sem porcentagem, agora cai pra `info.duration`;
`progress_bar.update(int(elapsed_seg))` truncava a cada segmento e acumulava déficit em vídeos com muitos
segmentos curtos — atualiza agora pela diferença inteira da posição cumulativa em float. **Fase 2**: o
separador `"-"*64` era parseado 3× com semânticas divergentes (analyzer com janela de 4096 chars contra
falso-positivo, formatter/prompter sem janela — o mesmo arquivo podia ter o corpo amputado no format/prompt
e não no analyze); `src/transcript_io.py` novo é o dono único (`split_header_body`/`parse_header_meta`),
migrado nos 3 call sites + testes; comentários em `core/rag/indexer.py`/`core/text/reader.py` (que citavam a
função removida do analyzer) atualizados pra apontar ao novo dono, sem migrar as implementações deles
(fora do escopo deste plano). **Fase 3**: `_ensure_portuguese` deixava um JSON malformado na tradução
derrubar a análise inteira depois de todos os chunks pagos — agora usa `_invoke_and_parse` (retry 1×) e cai
pro original em inglês com warning se persistir. `formatter._format_chunk` novo retry 1× em resposta vazia e
valida preservação de contagem de palavras (~2% tolerância) **por chunk**, não no corpo inteiro — os chunks
têm overlap, então uma checagem no corpo já reagrupado veria contagem sempre inflada pelo texto duplicado nas
bordas e falharia até em transcrições normais com múltiplos chunks (achado só durante a implementação, não
previsto no plano original). `prompter.build_prompt_ready` com corpo vazio retornava `input_path` como se
fosse o output gerado — contrato enganoso; agora retorna `None`, e o adaptador de receitas
(`core/recipes/registry/transcription.py::_prompt`) levanta `ValueError` nesse caso (o worker da GUI já
esperava `Path | None`). `_parse_json_response` ganhou fallback fatiando do primeiro `{` ao último `}` quando
o modelo prefixa/sufixa prosa fora de qualquer fence. **Fase 4**: `check_dependencies()` rodava incondicional
(exigia yt-dlp+ffmpeg até pra entrada `.txt`, onde nenhum é usado) — agora só roda quando o input resolvido é
uma URL; entrada de texto sem `--format/--analyze/--prompt` e `--srt/--vtt/--subtitles` combinados com texto
ganharam avisos novos (espelham guardas que a GUI já tinha ou eram silenciosamente ignorados). **Fase 5**:
`_emit(payload: dict = {})` (default mutável, 5 ocorrências) → `dict | None = None`; import de `SubtitleCue`
saiu de dentro do loop de segmentos; `_resolve_device(threads)` — parâmetro nunca usado — assinatura limpa;
docstring do `analyzer` com exemplos mortos (`uv run yt-analyzer`, script inexistente) atualizada;
`gui.py::page.window.center()` depois de `maximized=True` (inócuo) removido. Plano:
[`plans/implemented/PLANO_CORRECOES_SRC_RAIZ.md`](plans/implemented/PLANO_CORRECOES_SRC_RAIZ.md).

### Correções do `src/analysis/` (jul/2026)
Revisão exploratória arquivo-a-arquivo do pacote (9 arquivos, ~1.296 linhas — `types`/`prompts`/`report` +
catálogo `profiles/` por grupo), pacote recente e bem desenhado (catálogo declarativo, puro, sem duplicação
de prompt); os achados se concentraram num único tema. **Fase 1 — o bug principal**: `report._render_section`
confiava que o LLM respeitava os tipos do schema à risca — qualquer desvio de shape virava lixo silencioso:
string onde se esperava lista virava bullet por-caractere (`list(value)` fatiando a string), lista onde se
esperava parágrafo imprimia o repr Python, dict pra keyvalue perdia as definições (`_is_empty` não tratava
dict) e item não-string dentro de lista imprimia o repr do dict. Normalizadores por kind
(`_normalize_items`/`_normalize_paragraph`) absorvem o desvio antes de renderizar; complementos: citação
multilinha prefixa cada linha do blockquote, item já bulletado não duplica o `-`, placeholder `"..."` ecoado
do skeleton do prompt e itens em branco são descartados. Golden test novo trava o relatório do perfil
default byte-a-byte contra a saída legada (capturada com `datetime.now()` congelado) — a única salvaguarda
mecânica de que o caminho feliz não mudou. **Fase 2 — integridade do catálogo**: `Field.kind` era string
livre (um typo caía silenciosamente no branch de lista); `Field.__post_init__` agora levanta `ValueError`
para kind desconhecido e para `always=True` sem `empty_text` — corrigiu o único ofensor real do catálogo
inteiro (`key_points` do perfil `default`). `AnalysisProfile.__post_init__` valida key não vazia e sem
duplicatas entre os fields do perfil; a bijeção PROFILES×GROUPS e o smoke test do catálogo inteiro já
existiam em `tests/analysis/test_profiles.py`, não duplicados. **Fase 3**: prompts de análise e merge
ganharam regra explícita contra copiar os placeholders `"..."` do skeleton, e o merge passou a listar
dinamicamente os fields `always=True` do perfil como obrigatórios ("nunca deixe vazios"). **Fase 4**:
`format_report` ganhou `generated_at: datetime | None = None` (default `now()`) para relatório
determinístico sem mudar call sites. Plano:
[`plans/implemented/PLANO_CORRECOES_SRC_ANALYSIS.md`](plans/implemented/PLANO_CORRECOES_SRC_ANALYSIS.md).

### Correções do `core/document/` (jul/2026)
Revisão exploratória arquivo-a-arquivo do pacote (7 arquivos, ~805 linhas), mesmo formato do quarteto ML e
dos três pacotes revisados antes (image/library/audio), implementada fase a fase direto no `main`. **Fase 0**:
`DocumentArgs.analyze_model` e o segmented_selector da GUI usavam `qwen7b-custom` como default, divergindo da
decisão já tomada nos demais módulos (`gemma3-4b-custom`); alinhado à mesma referência do módulo Dados.
**Fase 1 — o bug principal, investigado via context7 antes do fix**: `compress_pdf` aceitava `image_quality`
mas nunca o usava — o loop reinjetava via `update_stream` os bytes originais de `extract_image`, um no-op
disfarçado (a redução real vinha só do `garbage=4, deflate=True` do `save`). Trocado por
`Document.rewrite_images(quality=image_quality)`, API nativa do pymupdf para essa finalidade. Validado
empiricamente antes de trocar: quality realmente escala o tamanho de saída, `rewrite_images` nunca produz
arquivo maior que o baseline garbage+deflate (testado até quality 99 sobre imagem já comprimida), e a
transparência (soft mask) sobrevive à conversão pra JPEG — não precisou desativar `lossless`. Fixture nova
`sample_pdf_with_textured_image` (JPEG de ruído) substituiu `session_jpg` nos testes de qualidade, que
comprimia a quase nada em qualquer quality e não discriminava as duas execuções. **Fase 2 — robustez**:
`_shared.open_pdf` novo centraliza o check de `doc.needs_pass` — nenhuma operação do pacote tratava PDF
protegido por senha antes disso; adotado nos 12 pontos que abrem um PDF fonte (processor/converter/info/ocr).
`converter.images_to_pdf` ganhou `ImageOps.exif_transpose` (mesma família de bug já corrigida em
`core/image`) e trocou o save multi-page do Pillow (todas as imagens decodificadas em RAM antes de salvar)
por inserção página-a-página via pymupdf, memória limitada a uma imagem por vez. Trade-off aceito: cada
página agora é reencodada como PNG sem perdas (antes, o Pillow às vezes emitia JPEG passthrough para fontes
já-JPEG) — um lote grande de fotos gera um PDF maior; não há teste de tamanho, é decisão de produto (memória > tamanho de saída), revisitável se o tamanho do PDF incomodar na prática. `info.get_pdf_info.has_text`
passou a amostrar só as primeiras 20 páginas (scan completo era lento demais para um metadado de preview num
PDF escaneado de centenas de páginas) e reusa `render_first_page_png` em vez de reimplementar o raster
inline. Um teste (`test_render_first_page_png_zero_pages_returns_none`) mockava pymupdf com `MagicMock` sem
fixar `needs_pass` — o novo check virava verdadeiro por acidente (MagicMock não configurado é truthy) e a
asserção passava pelo motivo errado, sem mais exercitar o guard de `page_count==0` que o teste dizia cobrir;
corrigido fixando `needs_pass=False` no mock, com teste dedicado novo para o caminho `needs_pass=True` usando
um PDF criptografado real. **Fase 3 — miudezas**: `_resolve_tesseract_cmd` (privada) promovida a
`resolve_tesseract_cmd` pública — já tinha dois consumidores externos importando o nome privado direto
(`core/image/ocr.py`, `core/observatory/status.py`); sem alias de compatibilidade, os dois call sites e os
mocks de teste foram atualizados junto. `LANGS` ganhou dono único em `document/ocr.py`. `stamp_pdf` em página
com `/Rotate` ≠ 0 saía de lado — `insert_text`/`draw_rect` escrevem no espaço de conteúdo não-rotacionado da
página enquanto a posição vinha do rect visual (rotacionado); fix: mapear ponto e caixa por
`page.derotation_matrix` (com `Rect.normalize()` depois — os cantos trocam de ordem) e contra-rotacionar o
texto com `rotate=page.rotation`, validado numericamente nas quatro rotações (0/90/180/270) via render +
inspeção de pixels antes de codificar. `watermark_pdf` tem o mesmo bug, mas soma um `TextWriter` com clip
próprio e o `morph` diagonal de 45° já existente — uma tentativa de aplicar a mesma correção não convergiu
(watermark sai clipado ou fora da página em pelo menos uma rotação); registrado como limitação conhecida no
`ROADMAP.md` §11 em vez de arriscar um fix quebrado. `__init__.py` ganhou docstring citando os cinco
submódulos. Cobertura do pacote fechou em 95% (era 93% no baseline; `processor.py` 91%→92%, `info.py`
94%→96%, `_shared.py` novo 100%). `processor.py` (~351 linhas, acima do alvo de 300) registrado no
`ROADMAP.md` §11 para dividir ao tocar. Plano:
[`plans/implemented/PLANO_CORRECOES_CORE_DOCUMENT.md`](plans/implemented/PLANO_CORRECOES_CORE_DOCUMENT.md).

### NL→CLI no hub de IA — modo "Comandos CLI" + `ai --cmd` (jul/2026)
Traduz um pedido em português no comando `uv run main.py ...` exato — revisa e copia, nada roda sozinho.
**Fase 0**: divide `gui/modules/ai/view.py` (677 linhas) em `index_controls.py`/`answer_view.py`. **Fase 0b**:
conclui a migração do reindex pro Observatório (ver decisão acima). **Fase 1**: `cli/reference.py` —
`build_reference()`/`validate_command()` por introspecção real dos parsers argparse (zero texto hardcoded,
zero drift). **Fase 2**: `core/text/nl2cli.py` — `to_command()` análogo a `nl2sql.py`, com retry 1x e recusa
para pergunta fora de escopo (ver decisões acima). **Fase 3**: toggle Corpus\|Comandos CLI no hub de IA,
card de comando com Copiar (Clipboard assíncrono). **Fase 4**: `ai --cmd "..."` na CLI, mesma amarração do
worker da GUI. Planos:
[`plans/implemented/PLANO_NL2CLI_HUB_IA.md`](plans/implemented/PLANO_NL2CLI_HUB_IA.md).

> **Pendência não-bloqueante**: o plano previa um teste manual de acurácia (~15 perguntas reais em PT contra
> `qwen7b-custom`/`gemma3-4b-custom`) para calibrar o few-shot do `nl2cli.py` antes de arquivar — arquivado
> sem esse passo (ambiente sem Ollama local disponível na sessão de implementação). Se o few-shot atual
> errar comandos com frequência no uso real, ajustar os exemplos em `core/text/nl2cli.py` é o primeiro lugar
> a olhar.

### Correções do `core/image/` (jul/2026)
Revisão exploratória arquivo-a-arquivo do pacote (13 arquivos, ~1.320 linhas), mesmo formato dos planos
anteriores, implementada fase a fase direto no `main`. **Bugs de comportamento** (Fase 1):
`background.replace_background` não aplicava `ImageOps.exif_transpose` antes do rembg — as outras 11
transforms do pacote já faziam isso; uma foto de celular em retrato saía com o recorte rotacionado 90° e o
EXIF descartado; `bg_mode="image"` com `bg_image` ausente caía em silêncio para cor sólida, agora loga
warning; `describe.describe_image` retornava `response.content` cru (mesmo fix do quarteto ML/core-data
não propagado até aqui) — usa `llm_utils.extract_llm_text`. `background.py` não tinha nenhum teste; ganhou
os dois primeiros. **Estrutural** (Fase 2): `transform.py` (496 linhas, acima do teto de ~400 da régua de
arquitetura) dividido em pacote `transform/` (`_shared.py`/`watermark.py`/`ops.py`, `__init__.py` reexporta
a API flat — nenhum call site externo mudou); a lógica de "path único sem colisão", duplicada 4× (
`downloader`/`converter`/`transform`/`describe`), consolidada num único `_paths.unique_path` (que também
sanitiza o stem, fechando a lacuna que só `describe.save_description` tinha); o flatten de alpha p/ JPEG,
duplicado entre `converter.convert_image` e `transform._save`/`_ensure_rgb`, virou um único
`converter._ensure_rgb` compartilhado. **Decisão tomada com o usuário**: a pesquisa no Pillow via context7
(exigida para EXIF/ICO/AVIF) revelou que `LOSSY_FMTS` não incluía `"avif"` — o slider de qualidade da GUI
não tinha nenhum efeito ao exportar AVIF (sempre saía na qualidade 75 default do Pillow); AVIF ganhou seu
próprio range de quality (0-100, sem o teto de 95 do jpg/webp, que existe só p/ conter o crescimento de
arquivo desses dois formatos além do ganho visível). **Robustez** (Fase 3): `downloader.download_image`
ganhou cap de 100MB (Content-Length checado antes de ler o corpo + leitura limitada contra servidor que
mente/omite o header); `smart_crop.focal_crop_box` clampa `new_w`/`new_h` às dimensões da imagem após o
`round()` (não reproduzido numa busca exaustiva, mas protegido mesmo assim — teste de invariante cobrindo
uma grade ampla de dimensões/ratios/focos); texto de ajuda do `--quality` na CLI alinhado ao clamp real.
Cobertura do pacote `transform/` fechou em 94% (era 91% no arquivo único). Plano:
[`plans/active/PLANO_CORRECOES_CORE_IMAGE.md`](plans/implemented/PLANO_CORRECOES_CORE_IMAGE.md).

### Correções do `core/library/` (jul/2026)
Revisão exploratória arquivo-a-arquivo do pacote (7 arquivos, ~636 linhas) — o mais novo e mais limpo dos
avaliados nesta rodada (mesmo formato do quarteto ML, core/data e core/audio), implementada fase a fase
direto no `main`. **Bug real** (Fase 1): `tags.tags_for_item` cacheava o `[]` que `tags_for_text` devolve
quando o extra `[nlp]` está ausente, carimbado com o mtime atual — ao instalar `[nlp]` depois, o cache
continuava servindo `[]` para sempre (mtime não mudou) e as auto-tags nunca apareciam para arquivos já
escaneados; fix: só persiste quando `keywords.is_available()` é `True` (um `[]` legítimo de texto vazio
continua sendo cacheado). **Lacunas de produto** (Fase 2): `TRANSCRIPTIONS_SUBTITLES_DIR` (`.srt`/`.vtt`
gravados pelo transcriber) não entrava nos roots do scanner — violava a premissa do hub ("tudo sob
`output/` aparece"); `thumbnails.thumbnail_for` despachava só por `item.kind`, então o waveform/espectrograma
PNG do módulo Áudio (kind `audio`) caía no ícone genérico apesar de ser imagem de verdade — dispatch agora
checa o suffix de imagem primeiro, qualquer kind. **Robustez** (Fase 3): `thumbnails._video_frame` ganhou
timeout no ffmpeg (vídeo corrompido não pendura mais a thread de thumbnails); `image_dedup.near_duplicate_images`
tolera uma imagem corrompida por item (skip + warning) em vez de derrubar o lote inteiro; `tags.save_tags`
migrado para `io_atomic.atomic_write_text`. **Duplicação aceita library×ml**: o union-find de
`image_dedup.py` duplica (não importa) `core/ml/dedup.py::near_duplicates` — decisão de independência já
documentada no próprio `types.py`, mas nunca registrada aqui (o quarteto ML só tinha registrado a
duplicação text×ml); registrada agora, mesmo racional. Cache `(path, mtime)→JSON` duplicado entre
`core/data/assess.py` e `core/library/tags.py` registrado como pendência de baixo risco no `ROADMAP.md`
§10 (extração de helper genérico tocaria `core/data` de novo, fora do escopo deste plano). Plano:
[`plans/active/PLANO_CORRECOES_CORE_LIBRARY.md`](plans/implemented/PLANO_CORRECOES_CORE_LIBRARY.md).

### Correções do `core/audio/` (jul/2026)
Revisão exploratória arquivo-a-arquivo do pacote (10 arquivos, ~745 linhas), mesmo formato do quarteto ML e
do `core/data`, implementada fase a fase direto no `main`. Fase 1 foi de **verificação guiada via context7**
antes de decidir o fix — os dois suspeitos eram de comportamento do ffmpeg/yt-dlp, não bugs óbvios de código:
**loudnorm** (`normalizer.normalize_lufs`) caía em silêncio no modo dinâmico quando o passe 1 de medição
falhava (returncode nunca checado) — a doc do ffmpeg confirma que o modo dinâmico upsampleia a saída p/ 192
kHz; agora loga warning claro e força `-ar` da fonte no passe 2 p/ conter o efeito colateral; **EmbedThumbnail**
com `fmt="best"` arriscava abortar o download inteiro — sem reencode, o container final é escolhido pelo
yt-dlp (frequentemente webm), que o `EmbedThumbnailPP` do próprio yt-dlp rejeita (não está na lista de
extensões suportadas) — thumbnail agora é pulada para `fmt="best"`. **Robustez**: timeouts nos subprocessos
ffmpeg sem timeout (decode do denoiser, passe 1 do normalizer); `sf.read` com `dtype="float32"` no denoiser
(corta o pico de RAM pela metade); nome do tmp WAV via `mkstemp` (evita colisão entre execuções concorrentes);
`_parse_loudnorm_json` valida as 5 chaves lidas pelo passe 2 (JSON incompleto virava `KeyError` cru);
`socket_timeout` no downloader; cleanup do `.tmp_encode_` órfão no converter se o encode falhar. **Perf**: o
passe 2 do normalizer (que duplicava à mão o Popen+thread+parse de progresso que `core/ffmpeg.run_ffmpeg` já
oferece) foi consolidado nesse helper; `extract_audio` ganhou fast path `-acodec copy` quando o codec de
origem já casa com o fmt alvo (ex.: AAC de um MP4 → m4a), com fallback automático pro reencode se o copy
falhar. **Convenção**: docstrings/comentários PT→EN nos arquivos tocados; `__init__.py` do pacote atualizado
p/ as 8 capacidades reais (download, convert/extract, silence, denoise, speed, normalize, visualize).
Pendência de baixo risco registrada no `ROADMAP.md` §9 (processamento em chunks do `denoiser` p/ áudio muito
longo). Plano: [`plans/active/PLANO_CORRECOES_CORE_AUDIO.md`](plans/implemented/PLANO_CORRECOES_CORE_AUDIO.md).

### Correções do `core/data/` (jul/2026)
Revisão exploratória arquivo-a-arquivo do pacote (14 arquivos, ~1.450 linhas), mesmo formato do quarteto ML,
implementada fase a fase direto no `main`: **3 bugs reais** (`validate.ensure_select` rejeitava a própria
receita pt-BR recomendada pelo docstring de `engine.reader_expr` — `"replace"` como palavra-chave proibida
colidia com a função pura `replace()`; um `;` dentro de literal de string era confundido com um segundo
statement porque o strip de literais rodava depois do check; `nl2sql._extract_payload` usava o índice errado
no fallback de SQL cru em bloco cercado, nunca funcionando no caso pra que foi escrito); **robustez** (`store`/
`assess` migrados para o `io_atomic` do quarteto ML; `resp.content` como lista de blocos — Gemini/tool-call —
agora tolerado por `nl2sql`/`assess` via `extract_llm_text`, promovido de `core/rag/chat._extract_text` p/
`src/llm_utils.py`; `ml.detect_outliers` dropa coluna numérica 100% NaN antes do `fillna(mean)`); **perf/seams**
(`profile.profile_text` aceita um `DataFile` já escaneado — `datacard.card_for_path` parou de escanear o
arquivo 2×; `engine.describe_file` ganhou `connect_fn` injetável, único ponto do engine sem o seam); **miudezas**
(`view_name_for` prefixa stems que colidem com keyword SQL — `select.csv` → view `t_select`; `charts._line`
coage o eixo X via `_numeric` só quando a coluna é de fato numérica, sem quebrar o eixo temporal). Decisão de
convenção de idioma em entrada própria (abaixo). Pendências de baixo risco registradas no `ROADMAP.md` §8
(sheet de XLSX não propagado em consultas; `charts.py`/`engine.py` acima do alvo de tamanho — dividir ao
tocar). Plano: [`plans/implemented/PLANO_CORRECOES_CORE_DATA.md`](plans/implemented/PLANO_CORRECOES_CORE_DATA.md).

### Decisão — mensagens de exceção user-facing do core podem ser em PT (jul/2026)
Fase 0 da revisão exploratória do `core/data/` (14 arquivos, ~1.450 linhas): o pacote é todo PT em mensagens
de exceção (`DataEngineError`, `ConvertError`, `ValueError` dos charts), enquanto `core/ml` é EN — inconsistência
não resolvida entre pacotes. Decisão: exceções *user-facing* (as que chegam cruas à GUI/CLI, sem
transformação) podem ficar em PT — são texto de interface, não código; docstrings/logs/comentários continuam
em EN sem exceção. Formalizado em CLAUDE.md §Convenções e na skill `architecture` §1.3.
[`plans/implemented/PLANO_CORRECOES_CORE_DATA.md`](plans/implemented/PLANO_CORRECOES_CORE_DATA.md).

### Correções do quarteto ML — rag · ml · text · observatory (jul/2026)
Revisão exploratória arquivo-a-arquivo dos 4 pacotes (37 arquivos, ~4.370 linhas) virou um plano de 6 fases,
implementado sessão a sessão direto no `main`: **infra compartilhada** (escrita atômica em
`core/io_atomic.py`; log JSON genérico em `observatory/_jsonlog.py`, incl. mitigação do hot path de
`record_timing`); **`core/rag/`** (bug real do `index_health` que nunca marcava documento stale; tokenização
BM25 sem pontuação; timeout curto (`10s`) do gate do embedder; persistência em grupo atômica; `store.load`
tolera `meta.json` ausente; `cancel_is_set` no `batch.run_batch`; `_index_one` extraída do duplicado
`index_files`/`build_index`; pula fusão RRF quando o BM25 não tem match); **`core/ml/`** (`classify.py`
dividido em pacote `classify/`; cegueira ao embed model corrigida nas assinaturas de cache de
protótipos/SVM via `embed_space_id`; canonicalização de path simétrica em `record_label`/`ChunkMeta`; gate do
`mapviz` antes do `import pandas`; guarda quadrática em `related()`; miudezas de robustez do `cache`/`store`);
**`core/text/`** (marcadores de idioma ambíguos removidos de `_PT_MARKERS`; amostragem estratificada no
resumo de textos longos — o item de maior impacto de produto do plano; `"transformer"` morto removido de
`_NER_PIPES`; `entities()` não re-checa `is_available` com pipeline em cache; edge case do separador de
header de 64 traços limitado a uma janela de prefixo); **`core/observatory/`** (docstring do `__init__.py`
para os 5 módulos reais; `disk_usage` blindado contra ciclo de symlink; ausência de lock inter-processo nos
logs documentada e aceita). Decisões pontuais de produto/arquitetura ficam em entradas próprias (abaixo).
Plano: [`plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md`](plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md).

### Decisão — `MLConfigSnapshot` reporta os dois `_MMR_LAMBDA` (jul/2026)
Fase 4 do plano do quarteto ML (item T3/O5): `core/observatory/status.py::config_snapshot()` só lia
`recommend._MMR_LAMBDA`, deixando `summarize._MMR_LAMBDA` (`core/text`) invisível no board do Observatório —
mesmo nome, mesmo valor hoje (0.6), mas constantes independentes por design (ver decisão abaixo). Decisão:
reportar as duas (`mmr_lambda` + `mmr_lambda_summary`) em vez de esconder uma; não move nenhuma constante
entre camadas, só lê ambas para exibição. CLI (`observatory status`) e a aba Status do hub Observatório
mostram as duas linhas. [`plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md`](plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md).

### Decisão — duplicação aceita entre `core/text` × `core/ml` (jul/2026)
Revisão arquivo-a-arquivo do quarteto ML (rag·ml·text·observatory) encontrou três pequenas duplicações na
fronteira entre `core/text` e `core/ml`: separador de cabeçalho `"-" * 64` (`core/rag/indexer.py`,
`core/text/reader.py`, `src/analyzer.py`), a função `_mmr` (`core/ml/recommend.py`,
`core/text/summarize.py`) e o gate `is_available()` de scikit-learn (`core/ml/deps.py`,
`core/text/summarize.py`). Decisão: manter — `core/text` é independente de `core/ml` por design (Plano 4B)
e o acoplamento de extrair uma camada comum para ~3 linhas repetidas não compensa. Não "consertar" uma
cópia isolada sem revisitar esta nota. [`plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md`](plans/implemented/PLANO_CORRECOES_QUARTETO_ML.md).

### Reorganização da documentação técnica (jul/2026)
Consolidação dos três locais de plano (`docs/` raiz, `docs/plan/`, `.claude/plans/`) numa árvore única
`docs/plans/{active,implemented,archive}`; roadmap vivo único em `ROADMAP.md`; referência em `reference/`;
CLAUDE.md reduzido a índice + contratos, com skills como fonte única por assunto (esta é a convenção "fonte
única + ponteiro" de [`README.md`](README.md)). Nova skill `ml-rag`; `testing`/`design-system` divididas em
arquivos de referência. Plano: [`plans/implemented/PLANO_REORGANIZACAO_DOCS_SKILLS.md`](plans/implemented/PLANO_REORGANIZACAO_DOCS_SKILLS.md).

### Observatório — fast-follow 2: perf fix + Índice/RAG aninhado ✅
A aba Status travava a UI por 7-12s (cold-import de extras + `ollama.Client().list()` síncronos na UI
thread) → movidos para thread daemon com placeholder + `Client(timeout=5)`. Índice e Painel saíram do hub
de IA (que virou só Conversa) e viraram a aba aninhada **Índice/RAG** no Observatório (Índice · Painel ·
**Uso de disco**, esta nova — `core/observatory/disk_usage.py`). "Reindexar" bridgeia pro hub de IA
(`trigger_reindex`) em vez de rodar pipeline. CLI `observatory disk-usage`.
[`plans/implemented/PLANO_ML_NOVAS_FEATURES.md`](plans/implemented/PLANO_ML_NOVAS_FEATURES.md).

### Observatório — fast-follow 1: GUI write-through + Status ampliado ✅
Fechou o gap em que só a CLI gravava `log_activity`: a GUI da Transcrição passou a gravar auto-sugestão e
confirmação de perfil. Nova aba **Logs** (`core/observatory/logs.py`) captura `task_error` de qualquer
módulo via hook central em `EventBus.emit()` — sem tocar nenhum `worker.py`. Status ganhou inventário
Ollama, gates expandidos, binários externos, provedores de nuvem e glossário de entidades; Status virou a
aba padrão. [`plans/implemented/PLANO_ML_NOVAS_FEATURES.md`](plans/implemented/PLANO_ML_NOVAS_FEATURES.md).

### Novas features de ML — Tier A ✅
Busca **híbrida** no RAG (BM25+RRF, `rank-bm25` base); outliers tabulares (`IsolationForest`); dedup de
imagens (**dHash** hand-rolled, zero dep); `classify.py` parametrizado por domínio; **novo hub Observatório**
(`core/observatory/` + `gui/modules/observatory/` + CLI `observatory`) centralizando atividade/status de ML
cross-módulo; stepper contextual (infra pronta, wiring adiado).
[`plans/implemented/PLANO_ML_NOVAS_FEATURES.md`](plans/implemented/PLANO_ML_NOVAS_FEATURES.md).

### Refinamento ML/texto/RAG (Tiers 1–3) ✅
Correção de recall + cache na busca do RAG (Tier 1); MMR em `recommend`/`summarize`, c-TF-IDF com
`ngram_range`, YAKE afinado, TextRank com viés de posição, glossário opcional do `EntityRuler` (Tier 2);
TSNE como 3º método de projeção, auto-k via `silhouette_score` (Tier 3). Zero dependência nova.
[`plans/implemented/PLANO_REFINAMENTO_ML_TEXTO_RAG.md`](plans/implemented/PLANO_REFINAMENTO_ML_TEXTO_RAG.md).

### Plano 4B — classificação supervisionada + inteligência textual ✅
Camada que precisa de **rótulo** ou **NLP textual**. `core/ml/classify.py`: perfil zero-shot por protótipo
que escala para supervisionado (`LinearSVC`+`CalibratedClassifierCV`) conforme o usuário confirma o perfil
(`record_label` no worker). Novo pacote `core/text/` (YAKE · TextRank self-contained · spaCy NER CNN ·
reader/lang), independente de `core/ml`. Extra `[nlp]`. GUI: auto-sugestão de perfil, aba Insights,
auto-tags na Biblioteca. [`plans/implemented/PLANO_4B_SUPERVISIONADO_TEXTUAL.md`](plans/implemented/PLANO_4B_SUPERVISIONADO_TEXTUAL.md).

### Plano 4A — inteligência semântica não-supervisionada ✅
Só geometria de embeddings (sem rótulos/treino), reusa `features.document_matrix` (Plano 3) e `charts`
(Plano 1). `cluster` (HDBSCAN/k-means), `labeling` (c-TF-IDF), `project` (PCA default / UMAP `[ml-viz]`),
`recommend` (numpy-puro), `mapviz` → PNG. GUI: modo **Mapa** na Biblioteca + aviso de fora-de-escopo na IA.
CLI `ai topics`/`map`/`related`. [`plans/implemented/PLANO_4A_SEMANTICO.md`](plans/implemented/PLANO_4A_SEMANTICO.md).

### Plano 3 — fundação de ML ✅
Pacote puro `core/ml/` espelhando `core/rag/`, **reusando o `VectorStore` persistido** (sem recalcular
embedding). `features.py` (numpy-puro) mean-pool dos chunks; `dedup.py` (prova de vida). Gate `[ml]`
(scikit-learn ≥1.4) só nos algoritmos futuros; acessor/dedup são fundação grátis. `store.py` versiona
modelos por `sklearn.__version__`+signature. CLI `ai dups`.
[`plans/implemented/PLANO_3_FUNDACAO_ML.md`](plans/implemented/PLANO_3_FUNDACAO_ML.md).

### Plano 2 — painéis analíticos dos hubs ✅
Superfície de painel em cada hub sobre dados já coletados, **sem ML** e sem dep nova. Núcleos puros
`core/library/analytics.py` · `core/rag/analytics.py` · `core/recipes/history.py`. Biblioteca ganha modo
Painel, IA ganha aba Painel (depois migrada ao Observatório), Receitas ganha Histórico. Helper
`gui/modules/_charts.py`. CLI `library stats`/`recipe stats`.
[`plans/implemented/PLANO_2_PAINEIS_HUBS.md`](plans/implemented/PLANO_2_PAINEIS_HUBS.md).

### PR9.1 / Plano 1 — gráficos no módulo Dados ✅
`core/data/charts.py` (única fronteira matplotlib, render off-thread `Figure`/`Agg` sem `pyplot` → PNG),
aba **Gráfico** na GUI + CLI `data plot`, extra `[data-plot]`. Reusa o caminho Arrow do Plano 0.
[`plans/implemented/PLANO_1_GRAFICOS.md`](plans/implemented/PLANO_1_GRAFICOS.md).

### Plano 0 — fundação de dados ✅
Camada Polars sobre o DuckDB: `core/data/frames.py` (única fronteira de DataFrame) + `engine.run_query_arrow`
(Arrow zero-copy), extra `[analysis]`. Puramente aditiva; destrava os Planos 1/2/5.
[`plans/implemented/PLANO_0_FUNDACAO_DADOS.md`](plans/implemented/PLANO_0_FUNDACAO_DADOS.md).

### PR9.3 — prévia visual, avaliação de qualidade e indexação de dados ✅
Aba **Pré-visualização** (tabela paginada + tipos por coluna, seletor de aba XLSX), **Análise com IA**
(`assess.py` + cache), e **indexação dos 5 formatos no RAG** via cartão de dados (`datacard.py`, `card_fn`
no indexer). CLI `data assess`. [`plans/archive/PLANO_PR9.3_PREVIA_AVALIACAO_INDEXACAO.md`](plans/archive/PLANO_PR9.3_PREVIA_AVALIACAO_INDEXACAO.md).

### PR9 — módulo Dados (query-first sobre DuckDB) ✅
6ª ferramenta. Motor DuckDB (in-process, torch-free); IA traduz PT→SQL recebendo **só o schema**. CLI
`data`; integração Receitas/Biblioteca. [`plans/archive/PLANO_PR9_DADOS.md`](plans/archive/PLANO_PR9_DADOS.md).

### Áudio Tier 2 — visualização e feedback ✅
Aba **Visualizar** (áudio→imagem via `showwavespic`/`showspectrumpic`, off-thread), toggle
`Converter|Visualizar`, **A/B antes/depois** no player, **card de loudness** medido vs. alvo. CLI
`audio-viz`. Cursor do player migrado para `page.run_task`. Backlog avançado em
[`plans/active/PLANO_AUDIO_TIER3_RESUMO.md`](plans/active/PLANO_AUDIO_TIER3_RESUMO.md).
[`plans/implemented/PLANO_AUDIO_TIER2.md`](plans/implemented/PLANO_AUDIO_TIER2.md).

### Áudio Tier 1 — pós-processamento estendido ✅
Cadeia 100% ffmpeg: remoção de silêncio, velocidade sem pitch (`atempo`), downmix mono + sample-rate no
encode final, toggle de modo de ruído, **presets de uma tecla**. Formulário fatiado em `blocks/`.
[`plans/implemented/PLANO_AUDIO_TIER1.md`](plans/implemented/PLANO_AUDIO_TIER1.md).

### PR7.2 — inspetor de índice + indexação por escolha + ETA ✅
`ai stats`, indexação por escolha (nunca automática), ETA da Transcrição e estimativa de tempo da resposta.
[`plans/archive/ROADMAP_PR7.2_IA_INDICE.md`](plans/archive/ROADMAP_PR7.2_IA_INDICE.md).

### PR8 — módulo Receitas / Automação ✅
Cadeias lineares nomeadas atravessando módulos (core `src/core/recipes/`, GUI Rodar|Construir, CLI
`recipe`). [`plans/archive/ROADMAP_PR8_RECEITAS.md`](plans/archive/ROADMAP_PR8_RECEITAS.md).

### PR7 — módulo IA / RAG local ✅
RAG local sobre o corpus (core `src/core/rag/`, GUI hub, CLI `ai`). Embeddings 100% locais.
[`plans/archive/ROADMAP_PR7_IA.md`](plans/archive/ROADMAP_PR7_IA.md).

### PR6 — módulo Biblioteca ✅
Índice navegável de `output/` (grade+lista, bridges, visor in-app) + entrada flexível de análise.
[`plans/archive/ROADMAP_PR6_BIBLIOTECA.md`](plans/archive/ROADMAP_PR6_BIBLIOTECA.md).

### Tier 0 — legendas + OCR ✅
Legendas SRT/VTT, legenda no vídeo (mux/burn-in), OCR híbrido.
[`plans/archive/ROADMAP_TIER0_LACUNAS.md`](plans/archive/ROADMAP_TIER0_LACUNAS.md) ·
[`plans/archive/STATUS_TIER0.md`](plans/archive/STATUS_TIER0.md).

### PR5 / PR5.1 — módulo Documentos ✅
13 ops GUI / 12 CLI + OCR híbrido via pytesseract.
[`plans/archive/MILL_PR5_DOCUMENTS_PLAN.md`](plans/archive/MILL_PR5_DOCUMENTS_PLAN.md).

### Plano −1 — refatoração prévia ✅
Aplicou a régua de tamanho/coesão da skill `architecture` a `data/view.py` (→ `tabs/`) e
`recipes/registry.py` (→ `registry/<módulo>.py`) e fixou a regra da seção 3 no CLAUDE.md — fundação
estrutural que os planos de dados/ML herdaram. [`plans/archive/REFATORACAO_PREVIA.md`](plans/archive/REFATORACAO_PREVIA.md).

### Anteriores (era pré-mill.tools e migração)
Vídeo (PR4), Áudio (PR3), Imagens (PR-IMG), migração para multiferramenta, design system, home screen,
splash — todos em [`plans/archive/`](plans/archive/) (só leitura histórica).

---

## Decisões arquiteturais (justificativas citáveis)

Estas justificativas se repetiam em vários lugares; cada uma é fonte única aqui, referenciável por link.

### Decisão: sem PyTorch no app base
Pós-processamento de áudio é CPU-only/torch-free (noisereduce/soundfile). IA com torch (Demucs,
DeepFilterNet) ficaria isolada num extra `[ai-audio]` — o app base permanece torch-free. Ver cenário
completo em [`reference/RELATORIO_CENARIO_TORCH.md`](reference/RELATORIO_CENARIO_TORCH.md).

### Decisão: encoding de vídeo 100% CPU — sem NVENC
Definitivo. A MX150 (2GB) disputa a GPU com o Whisper/DirectX; NVENC não compensa o risco de instabilidade.

### Decisão: `rank-bm25` (não `bm25s`) para a busca híbrida
`rank-bm25` é dependência **base** — puro Python/numpy, sem scipy. `bm25s` seria mais rápido, mas puxa
scipy para um ganho que só importa acima de ~1M documentos — fora do perfil do app.

### Decisão: dHash hand-rolled (não `imagehash`) para dedup de imagens
`core/image/dhash.py` usa só Pillow+numpy. O pacote `imagehash` puxaria scipy/PyWavelets (pelo `phash`) —
correção em relação ao plano original do Tier A, que cogitava `imagehash`.

### Decisão: GLM via `langchain-openai` (não `ChatZhipuAI`)
`ChatOpenAI` com `base_url` da Zhipu (API OpenAI-compatible) evita o `ChatZhipuAI` do `langchain_community`
(que puxa `pyjwt`, legado).

### Decisão: Observatório virou hub próprio (não aba do hub de IA)
O CLAUDE.md define hub como algo que "opera sobre as saídas de todos os módulos". A superfície de ML cobre
RAG/Biblioteca/Transcrição/Dados/Receitas — aninhá-la na IA seria descasamento semântico. Ver
[`plans/implemented/PLANO_ML_NOVAS_FEATURES.md`](plans/implemented/PLANO_ML_NOVAS_FEATURES.md) (item 3.5).

### Decisão: `classify.py` parametrizado por domínio
As mesmas funções servem perfil de transcrição / domínio de dados / tipo de documento, chaveadas por prefixo
de arquivo. O domínio default preserva os nomes pré-existentes → zero invalidação de cache.

### Decisão: embeddings sempre locais; nuvem só opt-in na resposta
`core/rag/embedder.py` é a única rede na indexação (Ollama, CPU, torch-free). Gemini/GLM entram só na
geração da resposta e sempre opt-in. Racional de modelos em [`reference/MODELOS_IA.md`](reference/MODELOS_IA.md).

### Decisão: Observatório é read-only exceto a indexação — o dono do índice exibe o botão (jul/2026)
Reversão parcial da decisão anterior. A migração Índice/Painel do hub de IA para o Observatório (PR7.2.3)
tinha ficado incompleta: as abas foram, mas o pipeline de indexação (botão "Reindexar", progresso, cancelar)
continuou no hub de IA, que só bridgeava (`nav[0]("ai", {"trigger_reindex": True})`) de volta pra lá — um
pulo de tela sem necessidade real. Fase 0b do
[`plans/active/PLANO_NL2CLI_HUB_IA.md`](plans/active/PLANO_NL2CLI_HUB_IA.md) move o worker
(`observatory/index_worker.py`, `module_id="observatory"`) e a UI de progresso/cancelar para
`observatory/index_tab.py`/`rag_tab.py`, no mesmo padrão worker+view de um módulo-ferramenta. O hub de IA
mantém só a linha de status do índice (read-only) + um botão "Indexar no Observatório" que navega pra lá.
Regra geral: o Observatório continua read-only **exceto** onde ele é o dono de um recurso (o índice RAG) —
nesse caso ele roda o próprio pipeline, em vez de bridgear para quem originalmente o hospedava.

### Decisão: NL→CLI é prompt direto com few-shot, não RAG (jul/2026)
O modo "Comandos CLI" (hub de IA + `ai --cmd`,
[`plans/implemented/PLANO_NL2CLI_HUB_IA.md`](plans/implemented/PLANO_NL2CLI_HUB_IA.md)) traduz um pedido em
português no comando `uv run main.py ...` exato. A referência de CLI inteira (~54 operações, introspectadas
por `cli/reference.build_reference()`) cabe em ~8,5k caracteres — dentro do `DEFAULT_OLLAMA_NUM_CTX = 8192`
junto com o few-shot, sem precisar mexer em config. RAG (retrieval sobre os fragmentos da referência) foi
descartado deliberadamente: trocaria "o modelo vê a CLI inteira" por "vê top-k flags", o que pioraria a
acurácia justamente no caso em que os poucos tokens do corpus tornam isso desnecessário. Só reabrir a
decisão se o corpus de CLI crescer o bastante para não caber mais no contexto de um modelo local.

### Decisão: exceção de camada `gui/ → cli/reference.py` (jul/2026)
`gui/` nunca importa `cli/` (regra da skill `architecture`) — a única exceção é
`gui/modules/ai/worker.py::run_ai_command`, que precisa dos parsers argparse **reais**
(`cli/reference.build_reference()`/`validate_command()`) para gerar e validar o comando do modo "Comandos
CLI". Não dava para duplicar essa introspecção em `core/` sem recriar `cli/reference.py` inteiro; como esse
módulo já é puro (sem Flet), a GUI reusá-lo é mais barato que inventar uma segunda fonte de verdade. É o
espelho inverso da exceção já existente (a CLI reusa `gui/modules/<m>/worker.py` puro) — juntas, as duas são
as únicas travessias de camada registradas no projeto. O import mora só em `run_ai_command`, comentado
inline; `cli/ai.py::_nl2cli` (`ai --cmd`) usa o mesmo `cli/reference.py` diretamente, já na camada correta.
