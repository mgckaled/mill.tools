# Hub IA — a superfície do RAG (Sessão 5)

Delta doc. O hub IA é a **superfície** dos motores que você já estudou nos conceitos: ele **usa** o RAG
([`../conceitos/RAG.md`](../conceitos/RAG.md)) e o `llm_factory`
([`../arquivos/llm_factory.md`](../arquivos/llm_factory.md)) — não os reimplementa. Aqui vemos como a
tela se conecta a eles.

> **Base (conceitos):** [`../conceitos/EMBEDDINGS.md`](../conceitos/EMBEDDINGS.md),
> [`../conceitos/RAG.md`](../conceitos/RAG.md), [`../conceitos/CLI.md`](../conceitos/CLI.md) (nl2cli),
> [`../conceitos/EVENTOS.md`](../conceitos/EVENTOS.md), [`../arquivos/llm_factory.md`](../arquivos/llm_factory.md).

## O que é um "hub"

Diferente das 6 ferramentas (na rail), os hubs são **botões dourados no AppBar** que operam sobre as
**saídas de todos** os módulos. O IA é um hub: ele conversa sobre tudo que você produziu sob `output/`.
Estruturalmente é auto-contido (não tem a fila de itens do Vídeo/Áudio).

## Toggle Corpus | Comandos CLI — dois modos, dois motores

O hub tem duas caras, e cada uma usa um motor diferente:

### Modo Corpus (a Conversa) — RAG

Você pergunta em português; o hub **recupera** os trechos relevantes do seu corpus e o LLM **responde
citando as fontes**. É o pipeline inteiro do [`../conceitos/RAG.md`](../conceitos/RAG.md): embeda a
pergunta → busca híbrida (denso+BM25) → RRF → MMR → piso → `chat.answer` com `[n]`. A GUI mostra o card
de fontes distinguindo **citadas** (em destaque) de **consultadas, não citadas** (discretas) — o parse
dos `[n]` vem de `chat.cited_source_numbers` (RAG §6.2).

🔑 Detalhe de arquitetura: a **reindexação NÃO roda aqui**. O modo Corpus mostra só a **linha de status
do índice** (read-only) + um botão "Indexar no Observatório" (`nav[0]("observatory", {"tab":
"index"})`). Por quê? Porque reindexar é um pipeline com progresso/cancelamento, e ele mora no
Observatório ([`observatorio.md`](observatorio.md)) — o hub IA fica só com a leitura. É a separação
"quem lê vs. quem escreve" levada a sério.

### Modo Comandos CLI — NL→CLI (sem RAG)

Aqui você descreve uma tarefa em português e o hub gera o **comando `uv run main.py ...` exato** — mas
**nunca executa**, só copia. Usa `core/text/nl2cli.to_command` + a referência introspectada de
`cli/reference.py` ([`../conceitos/CLI.md`](../conceitos/CLI.md) §NL→CLI).

🔑 Duas lições finas aqui: (1) este modo **não faz retrieval nenhum** — então o gate é só o Ollama de
chat (`ollama_inventory().reachable`), **nunca** o embedder. (2) É a **exceção de camada registrada**:
`gui/modules/ai/worker.py::run_ai_command` importa `cli/reference.py` — a GUI importando de `cli/`,
normalmente proibido. A justificativa (da skill `architecture`): a introspecção real dos parsers
argparse só existe em `cli/reference.py`, e duplicá-la em `core/` seria reinventá-la. A exceção está
comentada inline e é a única do tipo.

## Conversa multiturno — `condense.py`

Numa conversa com follow-up ("e sobre esse vídeo?"), a pergunta corrente é reescrita como **standalone**
antes do retrieval (`condense.condense_query`), resolvendo referências pelo stem citado no turno
anterior. 🔑 Sempre via **LLM local** (mesmo que a resposta use nuvem): o histórico nunca sai da
máquina nesse passo. Falha → fallback silencioso para a pergunta crua (a Conversa nunca deixa de
responder).

## Como o worker se liga aos eventos

O `run_ai_answer` (worker do hub) emite `answer_start`/`answer_done` pelo mesmo contrato de eventos da
Sessão 3 ([`../conceitos/EVENTOS.md`](../conceitos/EVENTOS.md)), com `module_id="ai"`. O `answer_done`
carimba o `embed_space_id` no payload — para o feedback (👍/👎) gravar em qual espaço a resposta foi
dada (senão uma reindexação tornaria o histórico incomparável).

---

# Perguntas de fixação

1. Os dois modos do hub (Corpus e Comandos CLI) usam motores diferentes. Qual usa o embedder e qual
   **não** usa? Por que o modo Comandos CLI não precisa do embedder?
2. Por que a reindexação não roda no hub IA, mas no Observatório? O que o hub IA mantém sobre o índice?
3. O `run_ai_command` importa `cli/reference.py` — uma exceção de camada. Qual é a justificativa?
4. Numa pergunta de follow-up, o que o `condense.py` faz **antes** do retrieval? Por que ele usa sempre
   o LLM local?
5. Ligue ao [`../conceitos/RAG.md`](../conceitos/RAG.md): quando você faz uma pergunta na Conversa, quais
   etapas (chunking já feito) rodam entre o seu texto e a resposta citada?
