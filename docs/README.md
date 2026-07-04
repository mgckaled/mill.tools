# Documentação técnica — mill.tools

Esta pasta é a **documentação versionada** do projeto. Está organizada por finalidade: história,
roadmap, referência e planos por estado.

## Mapa da pasta

```text
docs/
├── README.md        # este arquivo — mapa + convenção de fonte única
├── HISTORY.md       # changelog de decisões e entregas (cronológico inverso)
├── ROADMAP.md       # roadmap vivo único (o que ainda falta)
├── reference/       # documentação de referência (não é plano nem história)
│   ├── MODELOS_IA.md
│   ├── PANDAS_POLARS_DADOS.md
│   └── RELATORIO_CENARIO_TORCH.md
└── plans/
    ├── active/      # planos ainda não implementados (backlog vivo)
    ├── implemented/ # planos concluídos da era atual (mill.tools multiferramenta)
    └── archive/     # era pré-mill.tools / material de gênese (só leitura histórica)
```

## Ciclo de vida de um plano

1. Um plano novo nasce em [`plans/active/`](plans/active/).
2. Ao concluir, **move** para [`plans/implemented/`](plans/implemented/) e ganha **uma linha** em
   [`HISTORY.md`](HISTORY.md) (com link).
3. [`plans/archive/`](plans/archive/) é **só leitura histórica** — material da era pré-mill.tools. Nunca é
   referenciado por `CLAUDE.md` ou pelas skills, e seus links internos podem estar defasados (apontam para
   arquivos que já não existem). Não conserte referências dentro do archive.

## Convenção "fonte única + ponteiro"

Cada assunto tem **um** documento dono. Todos os demais **apontam** para ele — nunca duplicam. Esta tabela é
replicada de forma resumida no topo do `CLAUDE.md`.

| Assunto | Fonte única | Todos os demais |
|---|---|---|
| Quirks do Flet 0.85 · controles verificados | skill `design-system` | apontam |
| Contrato de eventos (`PipelineEvent`, payloads) | skill `design-system` (`events.md`) | apontam |
| Regra de ouro do spinner | skill `design-system` | apontam |
| Camadas, limites de tamanho, decomposição | skill `architecture` | apontam |
| Flags de CLI | `--help` do próprio código | skill `cli` só padrões/gotchas |
| Estrutura e mocks de teste | skill `testing` (+ arquivos de referência) | apontam |
| RAG / ML / NLP / Observatório | skill `ml-rag` | apontam |
| Histórico e justificativas de decisão | `HISTORY.md` + planos | apontam |
| Roadmap pendente | `ROADMAP.md` | apontam |
| Cobertura de testes | saída do `pytest --cov` | ninguém copia tabela |

> Quando um fato precisar mudar, mude-o **no dono** e verifique que os ponteiros ainda fazem sentido.
> Duplicar um fato em dois lugares é dívida — o segundo lugar envelhece calado.
