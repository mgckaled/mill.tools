# Módulo Áudio · Tier 3 — Resumo (decisão pendente)

> Não é um plano de implementação. É um catálogo curto das ideias avançadas para você
> escolher o que (e se) implementar depois. Cada item vira um plano próprio quando aprovado.

## Itens candidatos

| # | Ideia | Custo | Dependência | Valor | Observação |
|---|---|---|---|---|---|
| 10 | **Passe único ffmpeg** (`afftdn` + `loudnorm` num só `-af`) | Médio | Nenhuma | Eficiência | Motor *alternativo* ao noisereduce: 1 decode em vez de 3-4. Usar `afftdn` (FFT, zero-config), **não** `arnndn` (exige arquivo de modelo `.rnnn`). Não substitui o noisereduce — é uma opção "rápida". |
| 11 | **Split por silêncio** (fatiar em trechos numerados) | Médio | Nenhuma | Alto p/ podcasts | `silencedetect` → cortar em N arquivos. Encadeia muito bem com Transcrição e Receitas. Reusa o filtro do Tier 1. |
| 12 | **Seleção de região no waveform → clip + perfil de ruído** | Alto | Nenhuma | Médio-alto | Arrastar-e-selecionar no waveform (estende o `GestureDetector` atual). A região vira `y_noise` do noisereduce (validado: parâmetro existe) → denoise muito melhor que o gating cego. **⚠️ Mexe no caminho crítico do waveform** — exige cuidado redobrado com performance. |
| 13 | **Sugestão automática de cadeia** (probe → pré-seleciona switches) | Médio | Nenhuma | Médio | Probe rápido (loudness integrada, piso de ruído, mono/estéreo, fala vs. música) → pré-marca os switches com chip "Sugerido", no espírito do auto-perfil do Plano 4B. |
| 14 | **Audio fingerprint / dedup** (`fpcalc`/Chromaprint) | Médio | Binário externo | Médio-baixo | Detecta duplicatas de áudio (mesmo conteúdo, formatos diferentes). Padrão do Tesseract: gate `is_available()` no PATH, card desabilita se ausente. Modo "Duplicatas" na Biblioteca. |

## Rejeitadas na consolidação (não reabrir sem motivo novo)

- **BPM/Key detection** (`librosa`/`aubio`) — puxa `numba`/binário C para feature de baixo
  valor num app de voz/transcrição.
- **Time-stretch/pitch via `librosa`** — redundante com `atempo` (já no Tier 1).
- **Vocal isolation por phase-cancellation** — barato, mas qualidade ruim; nicho karaokê.
- **Playlist no player** — UX marginal para o fluxo.
- **ID3 tag editor** (`mutagen`) — nova dep, valor moderado; só sob demanda real.
- **Stem separation (Demucs)** — já no roadmap como extra `[ai-audio]` (torch); fora do
  escopo torch-free atual, mantém-se onde está.
- **Batch pipeline visual** — **Receitas já faz** encadeamento linear cross-módulo;
  construir um segundo orquestrador no módulo Áudio duplicaria a camada. Em vez disso,
  expor as ops novas (silêncio/velocidade/split) como **passos de Receita**.

## Recomendação de ordem (se for implementar)

1. **#11 Split por silêncio** — maior valor, zero dep, reusa o Tier 1, fecha com Receitas.
2. **#13 Sugestão automática** — bom alinhamento com o padrão de UX do projeto (Plano 4B).
3. **#10 Passe único** — ganho de eficiência tangível em CPU.
4. **#14 Fingerprint** / **#12 Região no waveform** — nichos; o #12 só com cautela de
   performance no waveform.
