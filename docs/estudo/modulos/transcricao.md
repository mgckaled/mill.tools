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

<details>
<summary><b>Gabarito</b> — abra só depois de tentar responder</summary>

1. Esconde a seção de transcrição (modelo Whisper etc.) e mantém só as etapas de IA — um `.txt` já é
   texto, não há o que transcrever.
2. O ramo **texto** pula o Whisper (só copia para `output/` e roda a IA). A guarda: exige **≥1
   análise** — copiar um texto sem pedir nada de IA seria inútil.
3. `make_llm` roteia pelo **prefixo do nome**: `gemini-*` → nuvem Google, `glm-*` → Zhipu, resto →
   Ollama local. Escolher o provedor da análise = escolher a string do modelo no formulário.
4. O `classify` zero-shot (nearest-prototype sobre o embedding do texto) **sugere o perfil** de
   análise; keywords (YAKE), summary (TextRank) e entities (NER) alimentam a aba **Insights**.
5. Um segmento em que o próprio Whisper teve baixa confiança: `avg_logprob < -1.0` ou
   `no_speech_prob > 0.6`. A incerteza do modelo virando um marcador visível para o usuário revisar.

</details>

## Desafios

- **D1 (e se...?)** E se o ramo texto do worker **não copiasse** o arquivo para
  `output/transcriptions/text/` e rodasse a IA direto sobre o original? Que dado do usuário fica em
  risco, e por quê?
- **D2 (projete)** Você quer um perfil de análise novo: **"sermão/homilia"**. O que precisa criar —
  e o que acontece **automaticamente** com a auto-sugestão de perfil, sem você treinar nada?
- **D3 (e se...?)** Durante uma transcrição longa, o usuário fica usando a GUI intensamente (trocando
  visual, abrindo painéis). No hardware deste projeto, qual é o risco real, por que ele existe, e
  quais mitigações o projeto já embute?

<details>
<summary><b>Gabarito dos desafios</b></summary>

- **D1** — O `formatter` **reescreve in-place**. Sem a cópia, ele reescreveria o arquivo **original**
  do usuário — as notas `.md` de alguém seriam alteradas permanentemente por um passo de IA. A cópia
  para o dir canônico é a proteção: o pipeline só toca o que é dele.
- **D2** — Criar o perfil em `src/analysis/profiles/` (prompts/estrutura do relatório) com uma
  **frase-semente** descrevendo a categoria. A auto-sugestão ganha o perfil de graça: o `classify`
  zero-shot embedda a frase-semente (vira protótipo) e passa a considerá-la no nearest-prototype —
  nenhum treino, nenhum rótulo (só o ramo supervisionado exigiria exemplos acumulados).
- **D3** — Risco: BSOD `WIN32K_POWER_WATCHDOG_TIMEOUT`. O Whisper (CUDA) e o Flet (DirectX) disputam
  a mesma MX150 de 2GB — uso simultâneo intenso pode estourar o watchdog. Mitigações embutidas: logs
  em INFO com libs ruidosas capadas (menos I/O), fila de áudio sequencial, e a recomendação de forçar
  o `python.exe` na iGPU Intel se persistir. É também por isso que só a Transcrição usa GPU pesada —
  todo encode de vídeo é CPU-only.

</details>
