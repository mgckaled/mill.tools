# Persistência — onde as coisas ficam entre sessões

Documento de referência: **onde** o projeto guarda dados no disco e **quem** grava o quê. Fecha o "o
que sobrevive entre execuções". Dois lugares: `output/` (as saídas que você produz) e
`~/.mill-tools/` (índices, modelos, logs, config).

---

# PARTE 1 — `output/` — as saídas dos módulos

Cada módulo grava no seu **dir canônico**, definido nas constantes de `utils.py`
([`../arquivos/utils.md`](../arquivos/utils.md)). O padrão `source` (baixado) vs. `processed` (gerado)
se repete:

```
output/
├── audio/{source,processed}/         · video/{source,processed}/
├── image/{source,processed}/         · document/{source,processed}/
├── transcriptions/{text,analysis,digest,subtitles}/
└── data/
```

🔑 Por que centralizar? A **Biblioteca** varre exatamente esses diretórios ([`../modulos/biblioteca.md`](../modulos/biblioteca.md))
e o **RAG** indexa o texto que mora aqui. Fonte única de caminhos = todo mundo sabe onde ler/escrever.

---

# PARTE 2 — `~/.mill-tools/` — o estado de ML/config

O diretório na sua home guarda o que é caro recomputar. Quem grava cada arquivo (da skill `ml-rag`):

| Caminho | Dono | Conteúdo |
|---|---|---|
| `rag/` (`.npz`/`.json` + `index_info.json`) | `rag/store.persist` | índice do RAG: matriz de vetores + metadados + modelo/dim/esquema |
| `ml/` | `ml/store` | modelos sklearn versionados (classify supervisionado) |
| `ml_activity.json` | `observatory/activity` | log de sucesso cross-módulo (cap 200) |
| `ml_logs.json` | `observatory/logs` | log de falhas (`task_error`, cap 100) |
| `model_timings.json` | `observatory/model_timing` | latência por `(domínio, modelo)` (cap 500/par) |
| `data_assessments.json` | `data/assess` | avaliação de qualidade da IA, por `(path, mtime)` |
| `library_tags.json` | `library/tags` | auto-tags YAKE por item, por `(path, mtime)` |
| `entity_glossary.json` | (manual) | padrões opcionais do EntityRuler (NER) |
| `prompts.json` | `rag/templates` | biblioteca de prompts do usuário |
| `rag_eval.json` | `rag/eval` | golden set + histórico de avaliações (`{golden, runs}`, cap 20) |
| `retrieval_feedback.json` | `rag/feedback` | log de 👍/👎 da Conversa (cap 200) |
| `config.json` | `gui/settings` | preferências + janela de tempos da Conversa + `last_embed_model` |

🔑 Três padrões recorrentes:
- **Cache por `(path, mtime)`** — reusa o resultado se o arquivo não mudou (avaliações, tags). O mesmo
  motivo do `force` no indexer: uma mudança de esquema não move o mtime, então precisa de override.
- **Logs append-only com cap** — os logs do Observatório crescem até um teto e descartam os antigos.
- **Versionamento por assinatura** — modelos de ML e o índice guardam `embed_space_id`/`sklearn
  version` para se invalidarem sozinhos quando o espaço muda ([`MACHINE_LEARNING.md`](MACHINE_LEARNING.md) §5.3).

---

# PARTE 3 — `.env` na raiz (segredos)

As chaves de API (`GOOGLE_API_KEY`/`ZHIPU_API_KEY`) ficam num `.env` na raiz do projeto, lido pelo
`llm_factory._load_env_once` ([`../arquivos/llm_factory.md`](../arquivos/llm_factory.md)) e editado pelo
diálogo de Configurações. 🔑 **Fora do código e fora do controle de versão** — o Observatório reporta só
a **presença** da chave, nunca o valor.

---

# Perguntas de fixação

1. Por que centralizar os dirs de `output/` num arquivo de constantes? Quem se beneficia?
2. O cache de avaliações é chaveado por `(path, mtime)`. Que problema o `force` do indexer resolve
   nesse esquema?
3. Por que os modelos de ML e o índice do RAG guardam o `embed_space_id`? O que aconteceria sem isso?
4. Onde ficam as chaves de API, e o que o Observatório mostra sobre elas?
