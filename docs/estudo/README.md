# Guia de Estudo do mill.tools

Acervo para entender o projeto a fundo, **arquivo por arquivo**, do zero ao avançado. Escrito para ser
lido no GitHub: tudo linkado, com glossários e referências cruzadas, sem depender de abrir o código no
editor.

Comece por **[`GUIA_ESTUDO.md`](GUIA_ESTUDO.md)** — o roteiro pedagógico (as 5 sessões, o porquê de
cada peça e as perguntas de fixação). Este README é o **índice de navegação**.

## Como usar

1. Siga as sessões na ordem (cada uma prepara a próxima). O guia diz o que ler e quando.
2. Abra o doc de detalhe, leia o código real junto, e responda as **perguntas de fixação** sem
   consultar.
3. Travou num termo? Cada doc tem glossário próprio; termos gerais estão em
   [`GLOSSARIO.md`](GLOSSARIO.md).

## As 5 sessões (ordem de estudo)

| # | Sessão | Docs |
|---|---|---|
| — | Fundamentos | [`GUIA_ESTUDO.md`](GUIA_ESTUDO.md) (as 6 regras invioláveis) |
| 1 | Espinha reutilizável | [`arquivos/ffmpeg.md`](arquivos/ffmpeg.md) · [`arquivos/utils.md`](arquivos/utils.md) · [`arquivos/llm_factory.md`](arquivos/llm_factory.md) |
| 2 | Fatia vertical (core→cli→gui→testes) | conceitos: [`TESTES`](conceitos/TESTES.md) · [`CLI`](conceitos/CLI.md) · [`FLET_GUI`](conceitos/FLET_GUI.md) → trace: [`arquivos/sessao2-vertical-video.md`](arquivos/sessao2-vertical-video.md) |
| 3 | Contrato de eventos | [`conceitos/EVENTOS.md`](conceitos/EVENTOS.md) |
| 4 | Demais módulos (variações) | [`conceitos/decomposicao.md`](conceitos/decomposicao.md) + [`modulos/`](modulos/) (áudio·imagem·documentos·dados·transcrição·biblioteca) |
| 5 | RAG / ML / NLP | conceitos: [`EMBEDDINGS`](conceitos/EMBEDDINGS.md) → [`RAG`](conceitos/RAG.md) · [`MACHINE_LEARNING`](conceitos/MACHINE_LEARNING.md) → hubs: [`modulos/`](modulos/) (ia·observatorio·receitas) |
| ★ | Síntese (por último) | [`conceitos/PRINCIPIOS.md`](conceitos/PRINCIPIOS.md) |

## Estrutura das pastas

```
docs/estudo/
├── README.md                 ← você está aqui (índice de navegação)
├── GUIA_ESTUDO.md            ← roteiro pedagógico + perguntas + tabela-mapa
├── GLOSSARIO.md              ← termos transversais
├── conceitos/                ← teoria transversal (lida de fora para dentro)
│   ├── TESTES · CLI · FLET_GUI · EVENTOS
│   ├── EMBEDDINGS · RAG · MACHINE_LEARNING
│   ├── decomposicao          ← padrões blocks/tabs/_state/registry
│   ├── PRINCIPIOS            ← capstone: os idiomas recorrentes
│   ├── PERSISTENCIA          ← onde as coisas ficam entre sessões
│   └── APENDICE_WINDOWS_HARDWARE
├── arquivos/                 ← detalhe fino: espinha + fatia vertical
│   ├── ffmpeg · utils · llm_factory
│   └── sessao2-vertical-video
└── modulos/                  ← variações por módulo (deltas)
    ├── audio · imagem · documentos · dados · transcricao · biblioteca   (Sessão 4)
    └── ia · observatorio · receitas                                     (Sessão 5)
```

## Mapa de dependências entre docs

- Os **conceitos** de cada sessão vêm **antes** dos traces que os usam.
- **Sessão 2** (`TESTES`/`CLI`/`FLET_GUI`) → habilita a fatia vertical e todos os `modulos/`.
- **Sessão 3** (`EVENTOS`) depende de `FLET_GUI` §3.
- **Sessão 5**: `EMBEDDINGS` é pré-requisito de `RAG` **e** `MACHINE_LEARNING`; os três habilitam os
  hubs `ia`/`observatorio`/`receitas`.
- **`decomposicao`** habilita a leitura dos `modulos/` (todos usam `blocks/`/`tabs/`).
- **`PRINCIPIOS`** é a síntese — só faz sentido depois de tudo.

## Referências do projeto

Este acervo é didático e complementa (não substitui) a documentação canônica do repositório:
`CLAUDE.md` (índice), as skills em `.claude/skills/` (`architecture`, `design-system`, `ml-rag`, `cli`,
`testing`) e `docs/HISTORY.md` (decisões).
