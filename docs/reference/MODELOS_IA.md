# Modelos de IA — matriz por papel (CPU-only)

> Guia de modelos open-source para o mill.tools, calibrado para o hardware-alvo e
> para os próximos PRs (Tier 0, PR6 Biblioteca, PR7 IA/RAG, PR8 Receitas).
> Complementa `llm_factory.py` e a seção **Ollama** do `CLAUDE.md`.
>
> **Princípio central:** não procurar "o modelo", e sim **definir papéis** e
> escolher o mais leve que cumpre cada papel. Em RAG, a qualidade do *retrieval*
> (embeddings + chunking) pesa mais que o tamanho do LLM; em dados tabulares,
> **Python calcula, o LLM narra**.

---

## 1. Hardware-alvo e restrições

- **CPU:** Intel i5-8265U — **4 núcleos físicos** / 8 lógicos.
- **RAM:** 16 GB (comporta até 7–8B Q4 ao lado de browser/VSCode).
- **GPU:** NVIDIA MX150, 2 GB VRAM — **reservada para o Whisper (CUDA)**.
- **OS:** Windows 10.

**Decisão:** os LLMs/VLMs do mill.tools rodam **CPU-only** (`num_gpu 0`). Isso:

1. libera a MX150 inteira para a transcrição (Whisper na GPU + LLM na CPU rodam
   sem disputa — elimina o BSOD `WIN32K_POWER_WATCHDOG_TIMEOUT` documentado no CLAUDE.md);
2. mantém a máquina utilizável com browser + VSCode abertos.

### Os dois knobs do Ollama (Modelfile)

| Parâmetro | Valor | Porquê |
|---|---|---|
| `num_gpu` | **0** | CPU-only; GPU fica para o Whisper. |
| `num_thread` | **4** | = núcleos **físicos**. Validado: o llama.cpp/Ollama atinge o pico em torno do nº de núcleos físicos; passar disso (hyperthreads) dá ganho desprezível/negativo e satura a CPU. Capar em 4 dá throughput quase máximo **e** deixa 4 threads lógicos livres para browser/VSCode. **Não é sacrifício — é o valor ótimo.** |

> Em CPU-only o gargalo é **throughput de tokens**, não VRAM. Por isso o ponto
> ótimo de tamanho desce para a faixa **1B–4B** para uso interativo, deixando 7B+
> para lotes em segundo plano.

---

## 2. Velocidade esperada na CPU (4 threads, Q4_K_M)

| Faixa | ~tokens/s* | Uso prático |
|---|---|---|
| 1B | ~10–18 | Interativo, snappy |
| 3–4B | ~3–6 | Tolerável; respostas curtas / segundo plano |
| 7–8B | ~1,5–3 | Lento; batch enquanto se faz outra coisa |

\* *Ordem de grandeza para uma U-series de 2018 a 4 threads. **Meça na sua máquina**
com um arquivo real antes de fixar configurações. VLMs (visão) somam um custo de
prefill ao processar a imagem — vários segundos por imagem além da geração.*

---

## 3. Matriz por papel

### 3.1 Texto

| Papel | Modelo | Params | Observação |
|---|---|---|---|
| **Interativo (novo)** | **Gemma 3 1B** | 1B | Rápido na CPU; ótimo para RAG ao vivo (retrieval carrega a qualidade). Preenche a lacuna "rápido" que qwen/phi não cobrem. Alternativas: Llama 3.2 3B, Qwen3 1.7B. |
| **Formatação (atual)** | `phi4mini-custom` | 3,8B | Já em uso (`--format`). |
| **Profundidade c/ visão** | **Gemma 3 4B** | 4B | Multilíngue (PT-BR), contexto 128K (bom p/ empilhar trechos no RAG), e **multimodal** (ver §3.2). Mais lento — usar sob demanda/segundo plano. |
| **Qualidade máxima / batch (atual)** | `qwen7b-custom` (Qwen 2.5 7B) | 7B | Já em uso (`--analyze`). Lento na CPU; reservar para lotes. Upgrade futuro: Qwen3 8B. |

### 3.2 Visão (VLM)

| Papel | Modelo | Params | Brilha em | Limite |
|---|---|---|---|---|
| **Interativo leve (atual)** | `moondream-custom` | ~1,9B | descrição, contagem, detecção, OCR leve | nuance limitada |
| **Ainda mais leve** | SmolVLM | 0,5–2,2B | tempo real, edge/browser | menor teto |
| **Baixa memória** | MiniCPM-V | ~3B | comprime visão p/ 64 tokens | menos difundido |
| **Texto-em-imagem / qualidade** | **Qwen2.5-VL 3B** (ou Qwen3-VL) | 3B | **ler texto/documento em imagem (OCR forte)**, VQA | mais pesado que moondream |
| **Multilíngue + consolidação** | **Gemma 3 4B** (/Gemma 4 E4B) | 4B | descrição multilíngue, 128K ctx, texto+visão num só modelo | mais lento; conta denso por aproximação |

> **"Absorver o moondream":** como o Gemma 3 4B é multimodal, ele pode cobrir
> **texto e visão** num modelo só, aposentando o `moondream-custom`. Vantagem:
> um modelo a menos + descrições melhores. Custo: mais lento na CPU que o moondream.
> Recomendação para uso com browser/VSCode abertos: **manter moondream/SmolVLM no
> papel interativo** e usar Qwen-VL/Gemma 4B **só quando a qualidade da descrição
> importar mais que a velocidade**.

### 3.3 Embeddings (PR7 — RAG)

| Papel | Modelo | Dim | Observação |
|---|---|---|---|
| **Embeddings do corpus** | **`nomic-embed-text`** | 768 | Torch-free, mesmo pacote `langchain-ollama`. Embedding é 1 forward pass por chunk (barato na CPU mesmo a 4 threads); indexação grande é custo único/incremental em background. Alternativas: `mxbai-embed-large`, `bge-m3`. |

### 3.4 OCR de documentos (Tier 0) — não é VLM

| Papel | Ferramenta | Observação |
|---|---|---|
| **Transcrição verbatim de PDF/scan** | **Tesseract** (`pytesseract`, extra `[ocr]`) | A ferramenta certa para extrair texto literal e layout-aware. VLM descreve/entende imagem; **OCR dedicado transcreve documento**. Ver `docs/plans/archive/ROADMAP_TIER0_LACUNAS.md` §D. |

---

## 4. Descrever ≠ transcrever (resumo)

- **Descrever / "ver"** (caption, VQA, detecção): forte em qualquer VLM (Gemma 3 4B,
  moondream, Qwen-VL). O modelo escreve o que vê e responde perguntas sobre a imagem.
- **Transcrever (OCR verbatim)**: VLM pequeno aproxima e pode alucinar/pular texto
  denso. Para documento, usar **Tesseract**. VLM lê texto **no contexto** ("o que
  diz a placa?"), não substitui OCR de documento.
- **Limites do Gemma 3 4B visão:** encoder SigLIP comprime a imagem em 256 tokens
  (Pan-and-Scan ajuda imagens grandes, mas texto minúsculo/detalhe fino degrada);
  contagem de objetos densos é aproximada; alucina com prompt vago; teto de um 4B.

---

## 5. Modelfiles sugeridos (padrão dos custom existentes)

Todos **CPU-only** com **4 threads**. Salvar em `ollama/`.

```dockerfile
# ollama/Modelfile.gemma3-1b  — texto interativo (RAG ao vivo, narração rápida)
FROM gemma3:1b
PARAMETER num_gpu 0
PARAMETER num_thread 4
PARAMETER temperature 0.3
SYSTEM "Você é um assistente analítico. Responda em português brasileiro, objetivo."
```

```dockerfile
# ollama/Modelfile.gemma3  — texto profundo + visão (sob demanda / segundo plano)
FROM gemma3:4b
PARAMETER num_gpu 0
PARAMETER num_thread 4
PARAMETER temperature 0.3
SYSTEM "Você é um analista. Responda em português brasileiro, objetivo. Para imagens, descreva o que vê com precisão e sem inventar detalhes."
```

```dockerfile
# ollama/Modelfile.qwen-vl  — visão de qualidade / ler texto em imagem (opcional)
FROM qwen2.5-vl:3b
PARAMETER num_gpu 0
PARAMETER num_thread 4
PARAMETER temperature 0.2
```

Embeddings (sem Modelfile custom — usado direto via `OllamaEmbeddings`):

```bash
ollama pull nomic-embed-text
```

> Ajuste de `num_thread`: começar em 4 (núcleos físicos). Só reduzir se a máquina
> ficar travada com browser/VSCode sob carga; aumentar acima de 4 **não** vale a pena.

---

## 6. Uso por PR

| PR | Modelos |
|---|---|
| **Tier 0 — Legendas** | nenhum LLM (Whisper já dá os timestamps). |
| **Tier 0 — OCR** | **Tesseract** (não-LLM). O `.txt` resultante alimenta análise. |
| **PR6 — Biblioteca** | nenhum LLM (só metadados/thumbnails). |
| **PR7 — IA/RAG** | **Embeddings:** `nomic-embed-text`. **Resposta:** **Gemma 3 1B** (interativo) ou **Gemma 3 4B**/`qwen7b-custom` (profundidade/batch). Gemini opt-in só no passo de resposta, com aviso de privacidade. |
| **PR8 — Receitas** | Passos de análise reusam os de texto acima (Python calcula agregações, LLM narra). Passos de visão usam `moondream-custom`/Qwen-VL/Gemma 4B. |

---

## 7. Resumo executivo — o que adicionar

O projeto hoje tem `qwen7b-custom` (Qwen 2.5 7B), `phi4mini-custom` (Phi-4 Mini),
`moondream-custom` (visão). Para os próximos PRs em CPU-only, adicionar:

1. **`nomic-embed-text`** — obrigatório para o RAG do PR7 (embeddings locais).
2. **Gemma 3 1B** (`gemma3-1b-custom`) — o modelo de texto **rápido** que falta,
   ideal para RAG interativo na CPU.
3. **Gemma 3 4B** (`gemma3-custom`) — opcional: texto de mais profundidade +
   multilíngue + a possibilidade de consolidar a visão (aposentar o moondream),
   trocando velocidade por qualidade.
4. **Qwen2.5-VL 3B** — opcional: quando precisar **ler texto em imagem** com
   qualidade acima do moondream.

Tudo `num_gpu 0`, `num_thread 4`, torch-free. Os números de velocidade são
estimativas — **medir localmente** antes de fixar.

> Nota de atualidade (jun/2026): o **Gemma 4** (abril/2026) é a geração corrente,
> com variantes eficientes E2B/E4B feitas para hardware modesto — vale avaliar como
> substituto direto do Gemma 3 nos papéis acima; o raciocínio por papel se mantém.

---

## Fontes

- [Best Ollama Models, jun/2026 — Morph](https://www.morphllm.com/best-ollama-models)
- [Best Open Source LLM 2026 + Ollama Guide — whatllm.org](https://whatllm.org/best-open-source-llm)
- [Ollama CPU Benchmark: tokens/s por quantização e threads — Markaicode](https://markaicode.com/benchmarks/tool-cpu-benchmark/)
- [llama.cpp threads — P-cores vs todos os cores (GitHub #572)](https://github.com/ggml-org/llama.cpp/discussions/572)
- [Gemma 3 QAT — consumer GPUs (Google Developers Blog)](https://developers.googleblog.com/en/gemma-3-quantized-aware-trained-state-of-the-art-ai-to-consumer-gpus/)
- [Gemma 3 VRAM/RAM Requirements (Will It Run AI)](https://willitrunai.com/blog/gemma-3-local-inference-guide)
- [Vision understanding — Gemma (Google AI)](https://ai.google.dev/gemma/docs/capabilities/vision)
- [Gemma 3 — Multimodal & Vision Analysis (Roboflow)](https://blog.roboflow.com/gemma-3/)
- [Local Vision-Language Models for Offline AI (Roboflow)](https://blog.roboflow.com/local-vision-language-models/)
- [Moondream 2 — Vision Analysis (Roboflow)](https://blog.roboflow.com/moondream-2/)
- [SmolVLM (Hugging Face)](https://huggingface.co/blog/smolvlm)
- [Qwen2.5-VL-3B-Instruct (Hugging Face)](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct)
- [OllamaEmbeddings — LangChain](https://python.langchain.com/docs/integrations/text_embedding/ollama/)
- [nomic-embed-text — Ollama](https://ollama.com/library/nomic-embed-text)
