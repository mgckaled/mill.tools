# mill.tools — Roadmap (índice)

> Índice da série de planos das próximas fases. Cada documento abaixo é autocontido
> e pronto para consumo pelo Claude Code como contexto de implementação.

## O arco

Os módulos de mídia (Áudio, Vídeo, Imagens, Transcrição, Documentos) **processam
mídia**; o módulo Dados (**PR9**) processa dados estruturados. As fases do arco
fecham o ciclo **processar → recuperar → raciocinar → automatizar**:

1. tapar lacunas óbvias dos módulos atuais (**Tier 0**);
2. tornar todas as saídas navegáveis num acervo (**PR6 — Biblioteca**);
3. conversar e analisar sobre esse acervo com RAG local (**PR7 — IA**);
4. encadear os módulos em pipelines reutilizáveis (**PR8 — Receitas**);
5. consultar dados estruturados em linguagem natural (**PR9 — Dados**, ✅ entregue).

Dois documentos transversais sustentam tudo: a matriz de **modelos** e a viabilidade
de **GUI**.

## Documentos

| Documento | O que é | Tipo |
|---|---|---|
| [ROADMAP_TIER0_LACUNAS.md](ROADMAP_TIER0_LACUNAS.md) | Legendas `.srt`/`.vtt`, queima no vídeo, OCR (PR5.1) e cobertura de `transcriber.py` | Fase |
| [ROADMAP_PR6_BIBLIOTECA.md](ROADMAP_PR6_BIBLIOTECA.md) | Módulo Biblioteca — índice navegável de `output/`, a fundação dos próximos PRs | Fase |
| [ROADMAP_PR7_IA.md](ROADMAP_PR7_IA.md) | Módulo IA — RAG local sobre o corpus (embeddings Ollama + busca + resposta com fontes) | Fase |
| [ROADMAP_PR8_RECEITAS.md](ROADMAP_PR8_RECEITAS.md) | Automação — cadeias de passos cross-módulo via registro + runner sequencial | Fase |
| [PLANO_PR9_DADOS.md](PLANO_PR9_DADOS.md) | Módulo Dados — query-first sobre DuckDB, PT→SQL pela IA (✅ entregue) | Fase |
| [PLANO_PR9.3_PREVIA_AVALIACAO_INDEXACAO.md](PLANO_PR9.3_PREVIA_AVALIACAO_INDEXACAO.md) | Dados PR9.3 — prévia visual da fonte, avaliação de qualidade pela IA e indexação dos 5 formatos no RAG via cartão de dados (✅ entregue) | Fase |
| [MODELOS_IA.md](MODELOS_IA.md) | Matriz de modelos por papel (texto/visão/embeddings/OCR), CPU-only, Modelfiles | Transversal |
| [GUI_FLET_PR678.md](GUI_FLET_PR678.md) | Viabilidade Flet 0.85 (possível/difícil/impossível) + novas factories do design system | Transversal |

## Ordem de execução e dependências

```
Tier 0   ── independente (legendas, OCR, cobertura) — maior retorno imediato
PR6      ── fundação (Biblioteca); o core (scan_library) destrava PR7 e PR8
PR7      ── depende do core do PR6 (corpus enumerado) — pode ir em paralelo se PR6.0 sair antes
PR8      ── último; beneficia-se de tudo, mas o núcleo não depende de PR6/PR7
```

(Esquema textual de dependência, não um diagrama.)

Sugestão de sequência: **Tier 0 (A+B legendas/cobertura)** → **PR6.0** (core da
Biblioteca) → **PR7.0–7.1** (RAG via CLI) → GUIs (PR6.1+, PR7.2+) → **PR8**. Modelos
e GUI são consultados ao longo de todas as fases.

## Princípios transversais

- **Torch-free** — nenhuma fase introduz PyTorch.
- **Modelos CPU-only** — `num_gpu 0`, `num_thread 4` (GPU reservada ao Whisper). Ver [MODELOS_IA.md](MODELOS_IA.md).
- **Core puro** — `src/core/**` sem Flet, reutilizável por CLI e GUI.
- **Código em inglês / labels em PT-BR**.
- **Flet 0.85** — respeitar os quirks e o polimorfismo de layout. Ver [GUI_FLET_PR678.md](GUI_FLET_PR678.md).
- **Sem dependência pesada nova** salvo onde explicitado (numpy explícito no PR7; openpyxl/python-pptx num eventual PR9 Dados & Apresentação).

## Skills do projeto a invocar (Claude Code)

- **`testing`** — ao criar/editar testes (`tests/**`).
- **`cli`** — ao adicionar subcomandos (`src/cli/**`, `main.py`).
- **`design-system`** — ao construir GUI (`src/gui/**`), incluindo as 3 factories novas.

## Além do roadmap (devaneios registrados)

- **PR9.3 — Prévia, avaliação e indexação** (✅ entregue): prévia visual da fonte
  (modal), avaliação de qualidade pela IA e indexação dos 5 formatos no RAG via
  cartão de dados. Ver `PLANO_PR9.3_PREVIA_AVALIACAO_INDEXACAO.md`.
- **PR9.1 — Gráficos** (`plot` via `matplotlib`, extra `[data-plot]`) e **PR9.2 —
  Encadeamento em estágios** (o resultado de uma consulta vira nova fonte): os
  sub-PRs deixados de fora do PR9 (entregue). A geração de slides (python-pptx,
  "Python calcula, LLM narra") segue como devaneio separado.
- **Coleções/projetos nomeados** no PR7 — extensão que aproxima a experiência de
  "projeto Claude" (várias bases isoladas em vez de um corpus único com escopo).
