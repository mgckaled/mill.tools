# Plano — NL→CLI no hub de IA (modo "Comandos CLI")

> **Status: implementado (jul/2026)** — Fases 0/0b/1/2/3/4 concluídas e commitadas; detalhe em
> `docs/HISTORY.md`. **Pendência não-bloqueante**: o teste manual de acurácia da Fase 5 (~15 perguntas reais
> contra `qwen7b-custom`/`gemma3-4b-custom`) não rodou nesta sessão (sem Ollama local disponível) — ver a
> nota em `docs/HISTORY.md`. Se o few-shot errar comandos com frequência no uso real, `core/text/nl2cli.py`
> é o primeiro lugar a ajustar.

> **Origem**: sessão Cowork (jul/2026). Objetivo: perguntar em português ("corta o silêncio desse mp3 e
> acelera 1.5x") e receber o comando `uv run main.py ...` exato, via modelo Ollama local, integrado ao hub
> de IA como modo exclusivo ao lado da Conversa RAG.
>
> **Decisão de abordagem (já tomada, não reabrir)**: **prompt direto com few-shot em PT**, não RAG. O corpus
> de CLI (~214 flags em ~15 subcomandos) cabe inteiro no contexto: referência compacta ≈ 4–5k tokens +
> few-shot ≈ 800 → total ~5–6k, dentro do `DEFAULT_OLLAMA_NUM_CTX = 8192` atual (sem mexer em config).
> RAG em corpus desse tamanho trocaria "modelo vê tudo" por "modelo vê top-k" — pioraria a acurácia.
> Modelos-alvo: `qwen7b-custom` (default, mais preciso em formato) e `gemma3-4b-custom` (fallback rápido).

## Decisões de arquitetura

| Decisão | Racional |
|---|---|
| Referência de comandos por **introspecção dos parsers argparse** (nunca texto hardcoded) | Fonte única — flag nova entra no prompt automaticamente; zero drift |
| Extrator/validador em **`src/cli/reference.py`** (Flet-free, torch-free) | Os parsers moram em `cli/`; introspectá-los de `core/` inverteria a camada |
| **Exceção de camada registrada**: `gui/` importa `src/cli/reference.py` | Espelha a exceção existente no sentido inverso (`cli/` reusa `worker.py` puro da GUI). Registrar em `docs/HISTORY.md` e na skill `architecture` ao concluir |
| Geração NL→comando em **`src/core/text/nl2cli.py`** (puro) | Análogo ao `core/data/nl2sql.py`: recebe `reference: str` + `make_llm_fn` injetados, devolve `(command, explanation)`. Unit-testável sem Ollama |
| Validação = **`parse_args` real** em try/except + 1 retry com a mensagem de erro | Fecha o ciclo sem executar nada; o argparse é o validador canônico |
| Modo CLI **não passa pelo retriever** | Sem embeddings/chunks/`[n]` → o card "fontes consultadas" nunca nasce (payload sem `sources`); funciona com índice RAG vazio ou `nomic-embed` fora do ar. Gate = só `make_llm` |
| Toggle **`segmented_selector` "Corpus \| Comandos CLI"** | Padrão consagrado de modos exclusivos (Receitas "Rodar \| Construir", Imagens "Edição \| Descrição IA"). Nunca `ft.Tabs` (não existe no 0.85) |
| **Reindex muda de dono: IA → Observatório** (⚠️ reversão parcial de decisão registrada) | A migração Índice/Painel → Observatório ficou incompleta: as abas foram, mas o pipeline de indexação (botão, `_on_reindex`, progresso, eventos) ficou no `ai/view.py`, e a bridge `trigger_reindex` pula de tela só para disparar. O hub passa a ser "read-only **exceto** o pipeline de indexação" (o dono do índice exibe o botão). Registrar a reversão em `docs/HISTORY.md` + skills `ml-rag`/`design-system` — hoje elas documentam o read-only estrito e a bridge |

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline + divisão do `ai/view.py` (677 linhas — acima do teto de ~500) |
| 0b | Migrar o pipeline de reindex IA → Observatório (conclui a migração; remove a bridge `trigger_reindex`) |
| 1 | `src/cli/reference.py` — extrator + validador |
| 2 | `src/core/text/nl2cli.py` — geração pura + few-shot |
| 3 | GUI — modo "Comandos CLI" no hub de IA |
| 4 | CLI — flag `--cmd` no subcomando `ai` |
| 5 | Verificação + docs |

---

## Fase 0 — Baseline + "divide-se ao tocar"

1. Suíte verde (`uv run pytest -m unit`) antes de qualquer mudança.
2. **Dividir `src/gui/modules/ai/view.py`** (677 linhas) pelo padrão da seção 4 da skill `architecture`
   **antes** de adicionar o modo. A divisão separa os dois "mundos" que hoje coabitam o arquivo:
   - **Conversa** (o grosso: `_make_turn`/`_append_turn`/`_source_item`/`_scope_warning`, ticker de tempo
     típico, handlers de resposta) → extrair para `ai/answer_view.py` (ou `ai/tabs/`), no padrão
     `build_X(...) → (controle, refs/handlers)`.
   - **Indexação** (`_on_reindex`, `_refresh_status`, `reindex_btn`, linha de progresso "Indexando N/M…",
     ramos de evento de índice em `_on_event`) → extrair para `ai/index_controls.py` **já pensado como
     mala de viagem**: a Fase 0b move esse arquivo quase intacto para o Observatório.
3. Nenhuma mudança de comportamento nesta fase — só decomposição + testes continuam verdes.

## Fase 0b — Reindex muda de dono: IA → Observatório

Conclui a migração que levou as abas Índice/Painel para o Observatório mas deixou a execução para trás
(hoje `observatory/rag_tab.py` faz `nav[0]("ai", {"trigger_reindex": True})` — pulo de tela).

1. **Worker**: mover `run_ai_index`/`start_ai_index` de `ai/worker.py` para
   `observatory/index_worker.py` (import gui→gui interno, permitido). Emitir eventos com
   `module_id="observatory"` — o escopo de eventos por `owner_id` passa a casar com o novo dono.
2. **`observatory/index_tab.py`**: ganha o botão "Reindexar" real + linha de progresso + cancel
   (transplante do `ai/index_controls.py` da Fase 0). Atenção: o Observatório deixa de ser 100%
   read-only — respeitar `pipeline_running[0]` (bloqueio de navegação durante pipeline) como os módulos
   ferramenta fazem. Refresh das abas Índice/Painel ao concluir (`task_done`).
3. **Hub de IA**: remove `reindex_btn`, `_on_reindex` e o ramo `trigger_reindex` do `_on_mount`.
   Mantém a **linha de status do índice** (read-only, via `_refresh_status`) + `action_button`
   "Indexar no Observatório" → `nav[0]("observatory", {"tab": "index"})` (bridge no sentido novo,
   payload de aba a confirmar com o `_on_mount` do Observatório).
4. **Módulo Dados**: o botão "Indexar no RAG" da aba Pré-visualização usa `index_files` (aditivo) —
   verificar se importa algo de `ai/worker.py`; se sim, apontar para o novo home.
5. **Docs da reversão**: `docs/HISTORY.md` (decisão: "read-only exceto indexação — o dono do índice
   exibe o botão"), skill `ml-rag` (remover a bridge `trigger_reindex`, atualizar a seção Superfícies),
   skill `design-system`/`events.md` (payloads de índice com `module_id="observatory"`) e o `CLAUDE.md`
   (bloco Bridges e a linha do hub Observatório citam a bridge antiga).
6. Testes de worker/eventos ajustados (`module_id` novo); suíte verde.

## Fase 1 — `src/cli/reference.py` (extrator + validador)

Módulo novo, **puro** (sem Flet, sem rede), na camada `cli/`:

1. **`build_reference() -> str`** — monta a referência compacta por introspecção:
   - Registra todos os parsers num `ArgumentParser` descartável reusando os `add_*_parser(subparsers)`
     existentes (+ o parser legado de `transcribe` e o `audio-viz`).
   - Percorre `subparsers` / `_SubParsersAction` / `_actions` e emite **uma linha por operação**:
     `video trim <input> --start <t> --end <t> — corta trecho do vídeo` (nome, positionals com metavar,
     flags com metavar/choices/default relevante, e o `help=` como descrição).
   - Formato compacto, sem usage-lines/alinhamento do argparse (é o que corta ~50% dos tokens).
   - Cachear em módulo (`functools.lru_cache`) — a introspecção roda 1× por processo.
2. **`validate_command(command: str) -> str | None`** — devolve `None` se válido ou a mensagem de erro:
   - Aceita e remove o prefixo `uv run main.py ` (exigi-lo faz parte da validação).
   - Tokeniza com `shlex.split(..., posix=False)` (paths Windows com `\` e aspas).
   - `parse_args` no parser introspectado dentro de try/except `SystemExit` — capturar a mensagem via
     `parser.error` override ou redirecionamento de stderr (argparse imprime antes de sair).
   - **Cuidado**: `--profile` usa `choices=list_profiles()` com import lazy de LangChain dentro do
     `parse_args` do legado — no parser descartável, substituir por um stub sem choices (a validação de
     perfil não vale o import pesado).
3. Testes `tests/cli/test_reference.py` (`@pytest.mark.unit`): referência contém operações conhecidas
   (`video trim`, `image contact-sheet`, `data query`); comando válido → `None`; flag inexistente /
   subcomando errado / sem prefixo → mensagem; kebab-case preservado na referência.

## Fase 2 — `src/core/text/nl2cli.py` (geração pura)

Análogo direto ao `core/data/nl2sql.py`:

1. **`to_command(question, reference, make_llm_fn, *, model, validate_fn) -> tuple[str, str]`** —
   devolve `(command, explanation)`; levanta `NL2CLIError` (mensagem PT, user-facing) se o modelo não
   produzir comando válido após 1 retry.
   - `reference` e `validate_fn` **injetados** (o core não importa `cli/` — a amarração é do chamador).
   - Prompt: instruções estritas (responder **só** JSON `{"command": ..., "explanation": ...}` ou o
     formato delimitado que o `nl2sql` já usa — seguir o mesmo padrão de `_extract_payload`), a referência
     completa, e o few-shot.
   - **Retry**: se `validate_fn(command)` devolver erro, re-prompta 1× anexando a mensagem do argparse
     ("o comando gerado falhou com: ..."). Segunda falha → `NL2CLIError`.
2. **Few-shot (8–10 pares PT→comando)** cobrindo os pontos onde modelos pequenos erram:
   - kebab-case: `extract-audio`, `contact-sheet`, `images-to-pdf`, `dedup-images`;
   - a ambiguidade áudio-de-vídeo: "extrair o áudio do vídeo X" → `video extract-audio`, vs. "converter
     esse áudio p/ mp3" → `audio`;
   - `data query` multi-input (`files... "pergunta"`) e `--sql`;
   - `ai` com positional despachado por valor literal (pergunta livre vs. `index`/`stats`);
   - `transcribe` com `--format --analyze --profile`;
   - 1 exemplo de pergunta **fora de escopo** ("qual a previsão do tempo?") → resposta de recusa
     padronizada, para o modo não alucinar comandos.
3. Temperatura baixa (seguir o padrão por papel do `make_llm`); default `qwen7b-custom`.
4. Testes `tests/core/text/test_nl2cli.py` com LLM **mockado** (padrão `testing/mocks-llm-rag-ml.md`):
   payload válido de primeira; inválido→retry→válido; inválido 2× → `NL2CLIError`; recusa fora de escopo.

## Fase 3 — GUI: modo "Comandos CLI" no hub de IA

1. **Toggle** `segmented_selector(["Corpus", "Comandos CLI"], ...)` acima do campo de pergunta
   (`form_view.py`). Em modo CLI: desabilitar escopo/reindex e demais controles só-RAG (via os `set_disabled`
   existentes); placeholder do campo muda ("descreva o que quer fazer...").
2. **Worker** (`ai/worker.py`): novo `run_ai_command(...)`/`start_ai_command(...)` ao lado de
   `run_ai_answer` — chama `to_command` com `reference`/`validate_fn` de `src/cli/reference.py` (a exceção
   de camada mora **só aqui**, comentada). Emite payload com `mode="cli"`, `command`, `explanation` e **sem
   `sources`** — a view de resposta renderiza condicionalmente (o card de fontes e o aviso de baixa
   confiança nunca nascem neste modo).
3. **Card de comando**: container `Type.mono` + fundo `surface_variant` com o comando, explicação em
   `helper_text` abaixo, e botão **"Copiar"** — handler `async def` com `await ft.Clipboard().set(cmd)`
   (quirk 0.85: `page.set_clipboard` não existe) + `page.show_dialog(SnackBar(...))` de confirmação.
4. **Threading**: mesmo padrão da Conversa — o LLM roda fora da UI thread; spinner segue a regra de ouro
   (`page.update()` antes de `start()`); updates escopados.
5. **Gate**: modo CLI exige só `make_llm` disponível (Ollama de chat) — **não** checa o embedder. Se o
   Ollama estiver fora, degradação graciosa com hint (padrão `SETUP_HINT`).
6. **Observatório de graça**: `make_llm` já anexa `_TimingCallback` → timing aparece sem tocar nada.
   Avaliar `log_activity` no sucesso (padrão dos workers) — entrada `nl2cli` na Atividade.

## Fase 4 — CLI: flag `--cmd` no subcomando `ai`

1. `add_ai_parser`: flag booleana `--cmd` — com ela, o positional `query` vira pergunta NL→CLI
   (bypass total do RAG/retriever, como na GUI).
2. `run_ai_cli`: ramo `--cmd` chama `to_command` (mesma amarração do worker), imprime comando +
   explicação (stdout já é UTF-8/replace no `ai`). Erro → mensagem + `sys.exit(1)`.
3. Exemplo: `uv run main.py ai --cmd "corta o silêncio do podcast.mp3 e acelera 1.25x"`.
4. Testes em `tests/cli/test_ai_cli.py` (LLM mockado, `capsys`).

## Fase 5 — Verificação + docs

1. `uv run pytest -m unit` verde + `ruff` limpo.
2. **Teste manual de acurácia** (não automatizado): ~15 perguntas reais em PT contra `qwen7b-custom` e
   `gemma3-4b-custom`; ajustar few-shot conforme os erros. Registrar resultado no plano ao arquivar.
3. Docs: bloco Comandos do `CLAUDE.md` (+1 linha no `ai`); skill `cli` (gotcha do `--cmd` + o stub do
   `--profile` na Fase 1); skill `ml-rag` (modo CLI do hub — gate sem embedder); skill `architecture`
   (registrar a exceção de camada `gui/ → cli/reference.py`); `docs/HISTORY.md` (decisão prompt-direto
   vs. RAG + exceção de camada).
4. Mover este plano para `docs/plans/implemented/`.

---

## Fora de escopo (não fazer agora)

- RAG sobre a referência de CLI (decisão registrada acima — só reabrir se o corpus multiplicar).
- Executar o comando gerado direto da GUI (botão "Rodar") — candidato a plano futuro; hoje só copiar.
- Histórico de perguntas/comandos persistido.
- Referência incluir gotchas/quirks das skills (cookies, presets) — v1 é só argparse.
