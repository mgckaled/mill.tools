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

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. O **Corpus** usa o embedder (precisa embeddar a pergunta para o retrieval). O **Comandos CLI** não
   faz retrieval nenhum — só traduz português → comando via LLM de chat + a referência introspectada;
   por isso o gate é só o Ollama de chat, nunca o embedder.
2. Porque reindexar é um **pipeline** (progresso, cancelamento, escrita) — e pipelines moram no
   Observatório. O hub IA mantém só a linha de status do índice (read-only) + o botão que navega
   para lá.
3. A introspecção real dos parsers argparse só existe em `cli/reference.py`; duplicá-la em `core/`
   seria reinventá-la. Exceção única, registrada e comentada inline.
4. Reescreve a pergunta como **standalone** (resolve "esse vídeo" → o stem citado no turno anterior)
   antes do retrieval. Sempre com LLM **local** para o histórico da conversa nunca sair da máquina.
5. Condensação (se multiturno) → embedding da pergunta → busca híbrida (denso + BM25) → fusão RRF →
   piso de relevância → MMR → contexto numerado `[n]` → LLM responde citando → parse defensivo das
   citações → card de fontes (citadas vs. consultadas).

</details>

## Desafios

- **D1 (e se...?)** E se a **condensação multiturno** usasse o mesmo modelo da resposta — inclusive
  quando o usuário escolheu Gemini? O que exatamente passaria a sair da máquina que hoje não sai?
- **D2 (ache o bug)** Um PR da view da Conversa adiciona uma regex própria para extrair os `[n]` da
  resposta e montar o card de fontes ("a minha cobre um caso a mais"). Por que recusar, mesmo se a
  regex for boa?
- **D3 (projete)** Um usuário pede: "coloca um botão Reindexar aqui na Conversa mesmo, é mais
  prático". Você tem que responder como arquiteto: por que a resposta é não, e qual é a alternativa
  que atende o desejo sem violar o desenho?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — O **histórico inteiro da conversa** (todos os turnos anteriores, que são o contexto da
  condensação) sairia para a nuvem — não só a pergunta corrente. Hoje o desenho garante: condensação
  **sempre local**; para a nuvem vai, no máximo, a pergunta standalone + os trechos recuperados. É
  uma diferença enorme de superfície de exposição.
- **D2** — Fonte única: `chat.cited_source_numbers` é o **único** parser de `[n]`, consumido por GUI,
  CLI e Receitas. Duas regexes = dois comportamentos divergindo em silêncio (um card mostraria
  "citada" onde o outro não). Se a regex nova cobre um caso real a mais, o lugar dela é **dentro** da
  função única, com teste — aí todos os consumidores ganham juntos.
- **D3** — Reindexar é um **pipeline de escrita** (progresso, cancelamento, worker próprio), e o hub
  IA é deliberadamente **read-only** sobre o índice — a separação "quem lê vs. quem escreve". Um
  botão que roda pipeline na Conversa reintroduziria toda a maquinaria (e a confusão de estado) que o
  desenho tirou de lá. A alternativa que já existe: o botão "Indexar no Observatório" navega via
  bridge (`nav[0]("observatory", {"tab": "index"})`) direto para a sub-aba certa — um clique a mais,
  arquitetura intacta.

</details>
