# Módulo Transcrição — o que muda em relação à fatia do Vídeo

Delta doc. A Transcrição é o módulo **original** do projeto (o app nasceu como um transcritor) e o que
mais **amarra os fios**: usa a espinha do `llm_factory`, aponta para o mundo de ML (perfis, insights) e
tem um formulário que muda de forma conforme a entrada.

> **Base:** [`../arquivos/sessao2-vertical-video.md`](../arquivos/sessao2-vertical-video.md),
> [`../arquivos/llm_factory.md`](../arquivos/llm_factory.md) (a cadeia de IA),
> [`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md) (perfis/classify),
> [`../conceitos/RAG.md`](../conceitos/RAG.md) (a saída indexável).

## O que é igual

Esqueleto `core → worker → cli/view`, contrato de eventos. Mas há três novidades que o tornam o módulo
mais rico.

## Novidade 1 — o formulário **adaptativo**

A entrada é um `InputSource` único que aceita **URL**, **áudio/vídeo local** e **texto** (`.txt`/`.md`).
O formulário (`views/form_view.py`) **muda de forma**: para texto, esconde a seção de transcrição e
mantém só as etapas de IA; para mídia/URL, mostra tudo. 🔑 É a GUI reagindo ao tipo de entrada — no
Vídeo, o formulário é fixo por operação; aqui, a própria estrutura do form se adapta.

## Novidade 2 — o worker de três ramos (`gui/workers.py::run_pipeline`)

O worker ramifica pela natureza da entrada:

- **texto** → **copia** para `output/transcriptions/text/` (nunca edita o original — o `formatter`
  reescreve in-place), **pula o Whisper**, roda só a IA. 🔑 Tem uma **guarda**: exige ≥1 análise
  (copiar um texto sem pedir nada de IA seria inútil).
- **áudio/vídeo local** → transcreve com **faster-whisper** (que decodifica vídeo via PyAV — **sem**
  extração de áudio separada).
- **URL** → metadata + download + transcrição.

Compare com o Vídeo (um item, uma operação): aqui a entrada define um **fluxo** diferente. E o Whisper
roda na **GPU** (o único uso pesado de GPU do app — daí o aviso de BSOD MX150 no CLAUDE.md).

## Novidade 3 — a cadeia de IA (o reencontro com o `llm_factory`)

Depois de ter o texto, entram três etapas opcionais de LLM, todas via o `make_llm` da espinha
([`../arquivos/llm_factory.md`](../arquivos/llm_factory.md)):

- **Formatter** — adiciona parágrafos ao texto cru.
- **Analyzer** — análise estruturada por **perfil** (aula/entrevista/palestra...).
- **Prompter** — versão condensada "prompt-ready".

🔑 Aqui os conceitos convergem: o roteamento por prefixo (Ollama/Gemini/GLM), o `num_ctx`, o bypass de
contexto longo — tudo do `llm_factory` — servem a estas três etapas. E a **auto-sugestão de perfil** +
a aba **Insights** puxam o ML clássico ([`../conceitos/MACHINE_LEARNING.md`](../conceitos/MACHINE_LEARNING.md)):
o `classify` zero-shot sugere o perfil; keywords/summary/entities alimentam os Insights. A saída
(transcrição + análise) é indexável no RAG. **Este módulo é onde a espinha, o ML e o RAG se tocam.**

## Novidade 4 — métricas de qualidade `[?]`

O `transcriber.py` sinaliza segmentos duvidosos com `[?]` (`avg_logprob < -1.0` ou
`no_speech_prob > 0.6`) — a confiança do Whisper virando um marcador visível. É um detalhe de
transparência: o usuário vê onde a transcrição pode ter errado.

---

# Perguntas de fixação (comparativas)

1. O formulário do Vídeo é fixo; o da Transcrição é adaptativo. O que muda no form quando a entrada é
   texto (`.txt`) em vez de um vídeo? Por quê?
2. O worker de Transcrição tem três ramos. Qual deles **pula o Whisper**, e qual **guarda** ele tem?
3. As três etapas de IA (Formatter/Analyzer/Prompter) usam o `make_llm` da espinha. Como o roteamento
   por prefixo permite escolher entre Ollama local e Gemini de nuvem para a análise?
4. Como o ML clássico aparece neste módulo? (dica: auto-sugestão de perfil + aba Insights)
5. O que o marcador `[?]` num segmento significa, e de onde vem essa informação?
