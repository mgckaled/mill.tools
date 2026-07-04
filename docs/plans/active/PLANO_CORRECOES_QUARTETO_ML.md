# Plano — Correções do quarteto ML (rag · ml · text · observatory)

> **Origem**: avaliações exploratórias arquivo-a-arquivo dos 4 pacotes (sessão Cowork, jul/2026).
> 37 arquivos / ~4.370 linhas lidos. Este plano consolida os achados em fases com dependência lógica —
> infraestrutura compartilhada primeiro, para os fixes pontuais nascerem sobre ela.
>
> **Estilo**: intencionalmente não-detalhista. Cada item diz *o quê* e *onde*; o *como* é decisão da
> sessão de implementação (consultar o MCP context7 para dúvidas de API de sklearn/spaCy/ollama/rank_bm25).
> Regras do projeto valem integralmente: skills `architecture`/`testing`/`ml-rag`, `pytest -m unit` verde
> + `ruff` limpo por fase, commits direto no main, sem Co-Authored-By.

## Sequência de fases

| Fase | Tema | Por que nesta ordem |
|---|---|---|
| 0 | Decisões prévias + baseline | Itens que mudam o escopo das fases seguintes |
| 1 | Infra compartilhada (escrita atômica + log JSON genérico) | Vários fixes das fases 2–5 usam esses helpers — criá-los depois seria retrabalho |
| 2 | `core/rag/` | Bug + robustez; o sidecar `index_info.json` daqui alimenta a Fase 3 |
| 3 | `core/ml/` | Divisão do `classify.py` ANTES do fix de assinatura (divide-se ao tocar) |
| 4 | `core/text/` | Independente; inclui a decisão da constante MMR que a Fase 5 consome |
| 5 | `core/observatory/` | Sobra pouco — a Fase 1 já migrou os logs; ajustes finais |
| 6 | Verificação + docs | Suíte completa, skills/HISTORY atualizados, plano → implemented |

---

## Fase 0 — Decisões prévias + baseline

1. **[R2] Resolver a discrepância do modelo default de resposta do RAG**: `chat.DEFAULT_MODEL = "qwen7b-custom"`
   vs. skill `ml-rag` afirmando que `gemma3-4b-custom` é o default. Verificar o que a GUI usa
   (`gui/settings`/worker) e decidir: corrigir o código, a skill, ou documentar que CLI e GUI têm defaults
   distintos. É decisão de produto — perguntar ao Marcel se ambíguo.
2. **Registrar em `docs/HISTORY.md`** a decisão de duplicação aceita na fronteira `core/text` × `core/ml`
   (header-sep de 64 traços ×3, `_mmr` ×2, gate sklearn ×2) **[T3]** — com a lista explícita, para ninguém
   "consertar" uma cópia isolada depois. A Fase 4 pode reduzir a lista; registrar o estado final.
3. Baseline: `uv run pytest -m unit` verde antes de tocar qualquer coisa.

---

## Fase 1 — Infraestrutura compartilhada

### 1.1 Helper de escrita atômica **[M7 / R4 / O7]**
Criar um helper único em `core/` (ex.: `core/io_atomic.py` ou função em módulo existente apropriado):
temp + `os.replace`, com suporte a escrever um **grupo** de arquivos como unidade (o par npz+json é o caso
típico). Consumidores a migrar (nas fases seguintes, ao tocar cada um): `rag/store.persist` (3 arquivos),
`ml/store.save_model` (2), `ml/cache.save_map` (3), `ml/classify._save_prototypes` (2) e
`record_label`/logs do observatory. Atenção Windows: `os.replace` sobre arquivo aberto/Defender — testar.

### 1.2 Log JSON append-only genérico **[O1 / O2]**
Extrair o esqueleto triplicado de `observatory/{activity,logs,model_timing}.py` (~90% idênticos) para um
helper interno do pacote (ex.: `observatory/_jsonlog.py`): load tolerante por entrada + append + cap +
`recent()`, parametrizado por dataclass e estratégia de trim (flat vs. per-bucket do `model_timing`).
Usar o helper 1.1 na escrita. **Incluir a mitigação do hot path [O2]**: `record_timing` é chamado por batch
de embedding e hoje faz load+rewrite completo do JSON a cada chamada — decidir entre buffer em memória com
flush no fim da operação ou JSONL append-only com compactação; o context7 não ajuda aqui, é decisão de
desenho local. Os três módulos viram fachadas finas (API pública preservada — testes existentes devem
continuar passando com ajustes mínimos de monkeypatch).

**Aceite da fase**: helpers testados isoladamente; `activity`/`logs`/`model_timing` migrados; suíte verde.

---

## Fase 2 — `core/rag/`

1. **[R1 — BUG] `analytics.index_health` nunca marca documento stale**: compara o mtime *gravado no embed*
   (`ChunkMeta.mtime`) com o mtime do `vectors.npz` — por construção sempre anterior. Fix: comparar o mtime
   **atual no disco** (`Path(source).stat().st_mtime`) com o gravado (ou com `updated_at`). Ajustar os testes
   que hoje passam com mtimes sintéticos que não refletem o fluxo real.
2. **[R3] Tokenização do BM25**: `.lower().split()` → tokenização sem pontuação (ex.:
   `re.findall(r"\w+", ...)`) em `bm25.py`, nos **dois** pontos (índice e query). Revisar os testes de
   ranking. Cache `_bm25` é lazy — sem migração de dados.
3. **[R5] Timeout do ping de disponibilidade**: `embedder.is_available()` herda `EMBED_TIMEOUT=300` —
   dar ao ping um timeout curto próprio (~5-10 s), no espírito do `ollama_inventory` (`timeout=5`).
   Resolve também **[O4]** (status board pendurável) sem tocar o observatory.
4. **[R4] Persistência**: `store.persist` → escrita atômica em grupo (helper 1.1); `store.load` tolerar
   `vectors.npz` presente + `meta.json` ausente (hoje `FileNotFoundError` cru) → store vazio + warning.
5. **[R6] Cancelamento no batch**: `run_batch` ganha `cancel_is_set: Callable[[], bool] | None`, checado
   entre itens (padrão do runner de Receitas). ~~Propagar no worker da GUI e no `cli/ai.py --batch`~~ —
   **correção pós-implementação**: não existe worker de GUI que chame `run_batch` hoje (o hub IA só tem a
   Conversa single-answer; batch é CLI-only) e `cli/ai.py --batch` é um script síncrono sem nenhum mecanismo
   de cancelamento para plugar (sem `CLIEventBus`, sem signal handler) — Ctrl+C já cobre esse caso. Escopo
   real implementado: só o seam no core, testado isoladamente, pronto para quando um chamador cancelável de
   verdade existir (GUI futura, ou um passo de Receita).
6. **[R7] Extrair `_index_one`** no `indexer.py` (corpo duplicado verbatim entre `index_files` e
   `build_index`); avaliar proteger contra falha do `embed_fn` pós-`drop_source` (hoje só o `card_fn` é
   protegido).
7. **[R8 — miudezas, oportunistas ao tocar cada arquivo]**: `stats._read_dim` ler `dim` do sidecar
   `index_info.json` com fallback pro npz; `retrieve` checar store vazio antes de `embed_query_fn`;
   `store.add` validar largura dos vetores contra `self.dim` quando o store está vazio (quirk #10176);
   `chat.answer` tolerar `resp.content` como lista de blocos; considerar pular a fusão RRF quando
   `lexical.max() <= 0` (BM25 sem match injeta viés de ordem-de-índice).

---

## Fase 3 — `core/ml/`

1. **[M1] Dividir `classify.py`** (471 linhas > teto ~400 da architecture §3). Corte natural:
   protótipos/seeds · rótulos+treino · inferência (padrão de decomposição da skill; manter API pública via
   `classify/__init__.py` reexportando — zero mudança nos call sites). **Fazer ANTES do item 2** para o fix
   de assinatura nascer nos arquivos novos.
2. **[M2 — o mais sério] Cegueira ao modelo de embedding**: incluir o `embed_model` (e/ou `dim`) do
   `index_info.json` do RAG nas assinaturas do cache de protótipos **e** do modelo supervisionado. Trocar o
   embed model + reindexar hoje deixa protótipos/SVM do espaço antigo válidos e prevendo lixo em silêncio.
   Definir comportamento para índices antigos sem sidecar (`embed_model="?"`).
3. **[M6] Canonicalização de path simétrica**: `record_label` grava `Path(...).resolve()`, mas
   `ChunkMeta.source_path` é `str(item.path)` cru — o join do `_training_xy` pode casar zero rótulos no
   Windows. Canonicalizar dos dois lados ou de nenhum (investigar qual forma o scanner produz antes de decidir).
4. **[M3] `mapviz.render_semantic_map_png`**: mover `import pandas` para depois do gate
   `charts.is_available()` — hoje `[analysis]` ausente vira `ImportError` cru em vez de `RuntimeError` +
   `SETUP_HINT` (viola degradação graciosa).
5. **[M4] Guarda quadrática em `related()`**: `dedup` tem `max_docs=5000`, `related` monta a matriz
   pairwise `(M-1)²` sem guarda. Adicionar guard ou limitar o MMR a um pool top-N por relevância.
6. **[M5] Docstring de `labeling.py`**: o exemplo "aprendizado de máquina" é impossível — o
   `CountVectorizer` remove stopwords ("de") **antes** de formar n-gramas. Corrigir o exemplo ou repensar a
   lista (context7: docs do CountVectorizer confirmam a ordem stopwords→ngram).
7. **[M8 — miudezas]**: `cache.load_map` capturar `KeyError`/`zipfile.BadZipFile` (paridade com
   `_load_prototypes`); mensagem do `_kmeans` sem o nome de flag `--k` (vazamento CLI→core);
   justificar ou mover `ORPHAN_LABEL`/"grupo {id}" PT no core (precedente: docstring do `templates.py`);
   suavizar o claim de `features.py` ("only module that knows the layout").
8. Migrar `ml/store`, `ml/cache` e `_save_prototypes` para o helper atômico (1.1), já que todos serão tocados.

---

## Fase 4 — `core/text/`

1. **[T1] Marcadores de idioma**: remover "do" e "as" de `_PT_MARKERS` (top-100 do inglês; viés sistemático
   pró-PT que degrada YAKE e spaCy silenciosamente). Substituir por marcadores realmente exclusivos
   (ex.: "é", "já", "então", "também"). Revisar testes de `detect_lang`.
2. **[T2] Resumo de transcrições longas**: `_MAX_SENTENCES=400` trunca pela cabeça e o prior posicional
   agrava — a segunda metade de uma aula de 2h fica inalcançável. Trocar truncamento por amostragem
   estratificada (a cada k-ésima sentença) ou resumo hierárquico. É o item de maior impacto de produto do
   plano; medir com uma transcrição real longa antes/depois.
3. **[T4] Remover `"transformer"` de `_NER_PIPES`** (ou comentar por quê fica) — contradiz a proibição de
   modelos `_trf` do próprio docstring.
4. **[T5 — miudezas]**: `entities()` não re-checar `is_available` quando o pipeline já está no
   `_NLP_CACHE` (varredura de metadata por chamada); avaliar log/aviso no fallback silencioso PT de
   `_model_for`; edge do corpo com 64 traços em `reader.py` (herdado do indexer — se corrigir, corrigir nos
   dois + `analyzer`).
5. **[T3/O5] Constante MMR**: decidir o destino do `_MMR_LAMBDA` duplicado (recommend × summarize) sabendo
   que `status.config_snapshot` reporta só o do recommend. Opções: reportar os dois no snapshot, ou aceitar
   e documentar no HISTORY (Fase 0.2). Não mover a constante entre camadas sem necessidade — a independência
   text×ml é decisão registrada.

---

## Fase 5 — `core/observatory/`

Grande parte já resolvida pela Fase 1 (logs) e Fase 2.3 (timeout do gate). Restam:

1. **[O3] Atualizar o docstring do `__init__.py`** — descreve 2 módulos; o pacote tem 5 (`logs`,
   `model_timing`, `disk_usage` ausentes).
2. **[O6] `disk_usage`**: corrigir o docstring de `DiskUsageEntry` ("one level deep" — o scan é recursivo
   total); blindar loop de symlink (`RecursionError` não é `OSError`) — `is_dir(follow_symlinks=False)` ou
   guarda de profundidade.
3. **[O7 — miudezas]**: type hint em `domain_statuses(directory)`; avaliar (e provavelmente aceitar,
   documentando) a ausência de lock nos logs GUI×CLI concorrentes.
4. **[O5]** conforme decisão da Fase 4.5, ajustar `config_snapshot` se for o caso.

---

## Fase 6 — Verificação + documentação

1. `uv run pytest -m unit` e `-m integration` (com ffmpeg) verdes; `ruff` limpo.
2. **Atualizar a skill `ml-rag`** nos fatos que este plano muda: default de resposta (F0.1), invalidação
   agora incluindo embed_model (F3.2), tokenização BM25 (F2.2), cancelamento do batch (F2.5), estrutura do
   `classify/` (F3.1). Atualizar `testing`/referências de mock se os patch targets mudarem com a divisão.
3. **`docs/HISTORY.md`**: uma entrada para o conjunto ("Correções do quarteto ML") + as entradas de decisão
   das Fases 0.2 e 4.5.
4. Conferir que a cobertura dos módulos tocados não regrediu (`--cov=src.core.rag --cov=src.core.ml ...`).
5. Mover este plano para `docs/plans/implemented/`.

---

## Fora do escopo (registrar no ROADMAP se desejado)

- Upgrade do vector store para `sqlite-vec` (seam documentado em `rag/store.py`).
- `skops.io` como formato seguro de modelo (documentado em `ml/store.py`).
- Locking real inter-processo nos logs do observatory.
- Resumo hierárquico completo multi-nível (se a Fase 4.2 optar pela amostragem simples).
