# Roadmap encadeado — extensões de ML e análise de dados (sem PyTorch)

**Documento de planejamento — sequência de implementação que engloba todas as sugestões dos artefatos `ML_SEM_PYTORCH.md` e `PANDAS_POLARS_DADOS.md`**
Data: 23 de junho de 2026 · Público-alvo: leitor sem formação em programação, com interesse técnico · Princípio orientador: **fundações primeiro, mínimo de retrabalho e refatoração**

---

## Sumário

1. Objetivo
2. O princípio que minimiza retrabalho: construir as fundações antes das funcionalidades
3. Decisões transversais tomadas uma única vez
4. Mapa de dependências (o que cada onda reutiliza)
5. A sequência encadeada, plano a plano
   - Plano 0 — Fundação de dados (pandas/Polars sobre o DuckDB)
   - Plano 1 — Gráficos (realiza o PR9.1 já previsto)
   - Plano 2 — Painéis analíticos dos três hubs
   - Plano 3 — Fundação de ML (núcleo `core/ml` + acesso aos embeddings)
   - Plano 4 — Inteligência semântica e textual
   - Plano 5 — ML tabular no módulo Dados
   - Plano 6 — ML de mídia (Áudio, Vídeo, Imagens)
   - Plano 7 — ML operacional nas Receitas
6. Visão consolidada e justificativa da ordem
7. Riscos e observações sobre a máquina

---

## 1. Objetivo

Este documento responde a uma pergunta de engenharia: **em que ordem implementar todas as ideias dos dois artefatos anteriores**, de modo que cada etapa se apoie na anterior e que se evite ao máximo refazer trabalho já feito. Ele não reabre o mérito de cada funcionalidade — isso está nos artefatos — mas define a **sequência** e a **arquitetura de encaixe**.

O critério de sucesso é explícito: nenhum plano posterior deve obrigar a reescrever um plano anterior. Quando uma decisão precisa ser tomada, ela é tomada **na fundação**, uma única vez, e herdada por todos os planos seguintes.

---

## 2. O princípio que minimiza retrabalho: construir as fundações antes das funcionalidades

O maior gerador de retrabalho em projetos de software é descobrir, no quinto recurso, que ele precisa de uma peça compartilhada que os quatro anteriores também precisariam — e então voltar para reescrever os quatro. A defesa contra isso é identificar essas **peças compartilhadas** desde o início e construí-las primeiro, ainda que elas, sozinhas, não entreguem nada visível ao usuário.

No caso destas extensões, as ideias dos dois artefatos se apoiam, no fundo, em **três fundações comuns**:

A primeira é uma **camada de análise de dados** — a forma padronizada de transformar o resultado de uma consulta DuckDB em uma tabela de trabalho (pandas ou Polars) e de volta. Praticamente toda análise, todo gráfico e todo painel depende dela.

A segunda é um **núcleo de aprendizado de máquina** — um pacote puro, isolado, com a biblioteca scikit-learn atrás de um extra opcional e um portão de disponibilidade, seguindo o mesmo molde que o projeto já usou para o RAG e para o módulo Dados.

A terceira é um **acesso aos embeddings que já existem** — o módulo de IA já calcula e guarda as "coordenadas de significado" de cada texto; expô-las para reuso, sem recalcular, é o que torna baratas quase todas as funcionalidades semânticas.

A estratégia, portanto, é: **primeiro as três fundações, depois as ondas de funcionalidades agrupadas pela fundação que utilizam.** Funcionalidades que compartilham uma fundação são implementadas na mesma onda, para que essa fundação seja tocada uma única vez.

---

## 3. Decisões transversais tomadas uma única vez

Estas escolhas atravessam todos os planos. Fixá-las agora, na fundação, é o que evita divergência e retrabalho depois.

**Fronteira pandas/Polars.** Adota-se a regra do artefato 2: o DuckDB reduz os dados; o Polars faz as transformações intermediárias quando houver volume; o pandas é o formato de entrega na fronteira com aprendizado de máquina e gráficos. A conversão entre eles é trivial e ocorre sempre no mesmo ponto. Essa política é decidida no Plano 0 e nunca mais rediscutida.

**Estrutura de extras opcionais.** Seguindo o padrão de `[ai-image]` e `[ocr]`, as novas dependências entram como extras: `[ml]` para o núcleo clássico (scikit-learn e afins), e extras de mídia separados (por exemplo `[ml-audio]`, `[ml-image]`) para as bibliotecas mais pesadas de extração de características. O aplicativo base permanece mínimo; cada recurso ausente desabilita seu botão com uma dica, como já ocorre hoje.

**Pureza do núcleo e injeção de dependências.** Toda lógica nova de análise e de ML vive em `src/core/` sem nenhuma dependência de interface gráfica, recebendo o modelo ou a função de inferência por injeção — exatamente como o RAG recebe a função de embedding e o módulo Dados recebe o motor. Isso preserva a testabilidade sem rede nem placa de vídeo.

**Persistência e cache.** Modelos treinados, agrupamentos e resultados de análise são gravados em `~/.mill-tools/`, chaveados por `(caminho, data de modificação)`, reaproveitando exatamente a convenção de cache já usada pela avaliação de qualidade do módulo Dados. Decidir o formato uma vez evita caches incompatíveis entre planos.

**Dupla superfície CLI e GUI.** Cada funcionalidade nova nasce com as duas interfaces, seguindo os contratos já existentes: na CLI, reutilizando o padrão de subcomando (e o `CLIEventBus` quando houver progresso); na GUI, emitindo eventos com o `module_id` correto e respeitando as regras do design system, incluindo a "regra de ouro" do spinner. Padronizar isso desde o Plano 0 impede que planos posteriores inventem convenções próprias.

**Importação preguiçosa.** Nenhuma biblioteca pesada é carregada na abertura do programa; ela só é importada quando o recurso é acionado, como já acontece com a remoção de fundo. Isso mantém a partida rápida independentemente de quantos recursos forem adicionados.

---

## 4. Mapa de dependências (o que cada onda reutiliza)

A tabela abaixo é a espinha dorsal do encadeamento. A coluna "Reutiliza" mostra por que a ordem é a que é: nenhum plano aparece antes daquilo de que depende.

| Plano | Entrega | Reutiliza | Nova dependência |
|---|---|---|---|
| **0 — Fundação de dados** | Camada pandas/Polars sobre o DuckDB | Módulo Dados (DuckDB) | pandas, Polars |
| **1 — Gráficos (PR9.1)** | Visualizações no módulo Dados | Plano 0 | matplotlib |
| **2 — Painéis dos hubs** | Análises sobre catálogo, índice e histórico | Plano 0; Plano 1 (opcional) | — |
| **3 — Fundação de ML** | Núcleo `core/ml` + acesso a embeddings | RAG existente | scikit-learn |
| **4 — Inteligência semântica/textual** | Classificação, agrupamento, recomendação, escopo, palavras-chave, resumo | Plano 3 (e Plano 0 p/ exibição) | YAKE, sumy, spaCy (pequeno) |
| **5 — ML tabular (Dados)** | Anomalias, agrupamento de linhas, previsão, importância de variáveis | Plano 0 + Plano 3 | XGBoost/LightGBM |
| **6 — ML de mídia** | Cenas de vídeo, paleta/duplicatas de imagem, fala/música em áudio | Plano 3 | librosa, PySceneDetect, OpenCV, imagehash |
| **7 — ML operacional (Receitas)** | Previsão de tempo, próxima etapa, falhas, agregação de lote | Plano 0 + Plano 2 + Plano 3 | — |

A leitura essencial: os Planos 0 e 3 são fundações puras; tudo o que vem depois apenas se conecta a elas. As funcionalidades semânticas (4) são agrupadas porque todas usam o acesso a embeddings; as tabulares (5) e as operacionais (7) usam as duas fundações; as de mídia (6) são as mais independentes e, por isso, ficam por último, sem pressionar nada que veio antes.

---

## 5. A sequência encadeada, plano a plano

### Plano 0 — Fundação de dados (pandas/Polars sobre o DuckDB)

**Objetivo.** Estabelecer a "camada de acabamento" descrita no artigo de pandas/Polars: uma forma única e eficiente de levar o resultado de uma consulta DuckDB para uma tabela de trabalho em memória e de volta, com a política pandas/Polars fixada.

**O que entrega.** Já melhora o próprio módulo Dados — transformações finais, renomeações e cálculos derivados sobre o resultado tornam-se mais expressivos — e, sobretudo, destrava todos os planos seguintes que tocam tabelas.

**Encaixe arquitetural.** Um novo arquivo puro em `src/core/data/` (por exemplo, `frames.py`) com as funções de ponte (resultado → DataFrame, DataFrame → consulta), a aplicação das boas práticas de tipos de dados e a escolha pandas/Polars. Nenhuma alteração na fronteira DuckDB existente; apenas uma camada acima dela. Testes unitários como os do módulo Dados (DuckDB in-process qualifica como `unit`).

**Por que primeiro.** É a fundação de menor risco e maior alcance: não depende de nada novo, melhora o que já existe e é pré-requisito de quatro planos posteriores.

### Plano 1 — Gráficos (realiza o PR9.1 já previsto)

**Objetivo.** Adicionar visualizações ao módulo Dados, o item `plot` que já consta no roadmap do projeto.

**O que entrega.** Gráficos a partir do resultado de uma consulta — distribuições, séries, comparações — diretamente sobre a camada do Plano 0.

**Encaixe arquitetural.** Núcleo puro para gerar a figura; nova aba ou ação no painel do módulo Dados; extra opcional contendo o matplotlib. Reaproveita a tabela paginada e o padrão de abas já existentes.

**Por que aqui.** Assenta diretamente sobre o Plano 0 (o gráfico consome o DataFrame que o Plano 0 produz) e é uma entrega visível e motivadora antes de partir para o aprendizado de máquina. Como já estava planejado, este plano apenas o posiciona no lugar certo da cadeia.

### Plano 2 — Painéis analíticos dos três hubs

**Objetivo.** Transformar em análise os dados tabulares que os hubs **já coletam**: o catálogo da Biblioteca, os metadados do índice da IA (incluindo os tempos de resposta já registrados) e o histórico de execução das Receitas.

**O que entrega.** Na Biblioteca, um painel com contagens por tipo, distribuição de tamanhos e evolução temporal do acervo. Na IA, estatísticas de saúde do índice e comparação de tempos por modelo. Nas Receitas, taxas de sucesso, tempos por etapa e cadeias mais usadas.

**Encaixe arquitetural.** Cada hub ganha uma superfície analítica (uma aba, no padrão de abas manuais já usado no módulo Dados e no hub de IA), alimentada pela camada do Plano 0 e, opcionalmente, pelos gráficos do Plano 1. **Nenhum aprendizado de máquina é necessário aqui** — é só pandas sobre dados existentes.

**Por que antes do ML.** Duas razões. Primeiro, é barato e usa apenas as fundações já prontas. Segundo, e mais importante para evitar retrabalho: estabelece **a superfície analítica em cada hub** que os planos de ML posteriores (4 e 7) vão estender. Construir essa superfície uma vez e ampliá-la depois custa muito menos do que adicioná-la de forma dispersa.

### Plano 3 — Fundação de ML (núcleo `core/ml` + acesso aos embeddings)

**Objetivo.** Criar o esqueleto do aprendizado de máquina clássico, espelhando a forma como o RAG e o módulo Dados foram construídos, e expor os embeddings já existentes para reuso.

**O que entrega.** Um pacote puro `src/core/ml/` com as convenções de modelo injetável, persistência e gate; o extra `[ml]` com o scikit-learn; e um **acessor de embeddings** que entrega a matriz numérica e os metadados já calculados pelo RAG, sem recálculo. Como prova de funcionamento, uma primeira funcionalidade mínima — a detecção de documentos duplicados por similaridade — pode ser entregue aqui, já que depende apenas do acessor.

**Encaixe arquitetural.** `src/core/ml/` puro, com o portão `is_available()` que bloqueia os fluxos quando o extra não está instalado, à imagem do `embedder.is_available()` do RAG. O acessor lê o `VectorStore` e os metadados existentes.

**Por que aqui.** É a segunda fundação, pré-requisito de tudo que é ML. Vem depois dos painéis (Plano 2) porque estes não precisam de ML; assim, a dependência do scikit-learn só entra no projeto quando é de fato necessária.

### Plano 4 — Inteligência semântica e textual

**Objetivo.** Entregar, em uma única onda, todas as funcionalidades que se apoiam nos embeddings e em técnicas textuais leves — porque todas compartilham o acessor do Plano 3 e devem tocá-lo uma única vez.

**O que entrega.** Na Biblioteca: agrupamento temático automático do acervo, recomendação de itens relacionados e etiquetagem automática. Na Transcrição e nos Documentos: classificação do tipo de conteúdo, extração de palavras-chave, resumo extractivo e, nos documentos, reconhecimento de entidades. Na IA: detecção de pergunta fora de escopo, agrupamento do índice por tópico e roteamento de modelo. (O reordenamento de resultados por um modelo ONNX, por ser mais pesado, fica como item final desta onda ou início da seguinte, conforme o apetite.)

**Encaixe arquitetural.** Funções puras em `src/core/ml/` (agrupamento, classificação) e em um módulo de texto (palavras-chave, resumo, entidades, com os extras correspondentes). As entregas de hub entram nas superfícies criadas no Plano 2; as de ferramenta, nos painéis de resultado existentes da Transcrição e dos Documentos.

**Por que agrupado.** Reunir todas as funcionalidades de embedding numa só onda é o ponto central da estratégia anti-retrabalho: o acessor de embeddings, os utilitários de agrupamento e o padrão de exibição de resultados semânticos são definidos uma vez e reusados por todas elas.

### Plano 5 — ML tabular no módulo Dados

**Objetivo.** Trazer o aprendizado de máquina sobre tabelas — o terreno mais favorável ao ML clássico — para o módulo Dados.

**O que entrega.** Detecção de anomalias, agrupamento de linhas, previsão por regressão e importância de variáveis, como novas operações do módulo, com saída textual que fecha o ciclo com o hub de IA e com as Receitas.

**Encaixe arquitetural.** Reutiliza a camada do Plano 0 (para levar o resultado da consulta ao formato que os modelos esperam) e o núcleo do Plano 3 (mais o extra com XGBoost/LightGBM). Integra-se às Receitas como passos `data.*` e à Biblioteca pelo tipo de dados, exatamente como o módulo Dados já se integra. Relaciona-se com o **PR9.2 (encadeamento em estágios)** já previsto: quando o resultado de uma análise puder virar nova fonte, as saídas tabulares de ML encadeiam-se naturalmente — vale alinhar este plano com aquele item do roadmap.

**Por que aqui.** Depende das duas fundações (0 e 3), já prontas, e do padrão de operações do módulo Dados; nada que venha depois o altera.

### Plano 6 — ML de mídia (Áudio, Vídeo, Imagens)

**Objetivo.** Adicionar a compreensão de conteúdo de mídia, que exige extratores de características próprios de cada formato.

**O que entrega.** Em Áudio: detecção de fala e distinção fala/música. Em Vídeo: detecção de cenas, capítulos automáticos e miniaturas inteligentes. Em Imagens: paleta de cores dominante, detecção de duplicatas e classificação.

**Encaixe arquitetural.** Núcleo puro por módulo, com os extratores (librosa, PySceneDetect/OpenCV, imagehash) atrás de extras de mídia próprios, e os classificadores reaproveitando o núcleo do Plano 3. Cada recurso entra como nova operação no seu módulo, seguindo os contratos de eventos já documentados.

**Por que por último entre as ondas de ML.** É a mais independente e a que traz as dependências mais pesadas. Justamente por não ser pré-requisito de nenhuma outra, fica ao final: implementá-la não pressiona nem altera nada do que veio antes, e pode até ser dividida por módulo (áudio, depois vídeo, depois imagens) sem qualquer acoplamento.

### Plano 7 — ML operacional nas Receitas

**Objetivo.** Fechar o ciclo transformando o histórico de execução das Receitas em automação inteligente.

**O que entrega.** Previsão de tempo de execução, sugestão da próxima etapa ao montar uma cadeia, detecção de configurações que tendem a falhar e agregação dos resultados de lote em tabela analítica.

**Encaixe arquitetural.** Apoia-se no histórico já estruturado pelo Plano 2, na camada de dados do Plano 0 e no núcleo de ML do Plano 3. As previsões entram no construtor e no painel de Receitas; a agregação de lote reusa a exportação do módulo Dados.

**Por que por último.** É o plano que mais depende dos anteriores — precisa do histórico tabular (Plano 2), das fundações (0 e 3) e se beneficia dos padrões de ML já estabelecidos nos Planos 4 a 6. Colocá-lo ao final garante que ele apenas **consome** o que já existe, sem exigir nenhuma fundação nova.

---

## 6. Visão consolidada e justificativa da ordem

A cadeia completa é: **fundação de dados → gráficos → painéis dos hubs → fundação de ML → onda semântica → ML tabular → ML de mídia → ML operacional.**

A lógica que a sustenta pode ser resumida em três movimentos. O primeiro movimento (Planos 0 a 2) é inteiramente sobre **dados e análise sem aprendizado de máquina**: constrói a camada tabular, os gráficos e os painéis, introduzindo apenas pandas, Polars e matplotlib. Ele entrega valor visível cedo e, de quebra, ergue as superfícies analíticas que serão estendidas depois. O segundo movimento (Planos 3 e 4) introduz o **aprendizado de máquina pela porta mais barata**: a fundação de ML e, sobre ela, tudo que reaproveita os embeddings já calculados — a maior concentração de retorno por esforço, porque quase não há dependência nova. O terceiro movimento (Planos 5 a 7) cobre o **ML que exige extração de características ou dados próprios**: tabular, de mídia e operacional, do mais central e reaproveitável ao mais independente.

Em nenhum ponto um plano posterior obriga a reabrir um anterior, porque cada decisão compartilhada foi tomada na fundação: a política pandas/Polars no Plano 0, as convenções de ML e o acesso a embeddings no Plano 3, as superfícies analíticas dos hubs no Plano 2. Esse é, precisamente, o desenho que minimiza retrabalho e refatoração.

---

## 7. Riscos e observações sobre a máquina

Três pontos merecem atenção ao executar a cadeia.

O primeiro é a **disciplina dos extras**: à medida que as dependências crescem, é essencial mantê-las atrás dos extras opcionais e dos portões de disponibilidade, sob pena de inflar a instalação base e contrariar a filosofia de leveza do projeto. O segundo é a **fronteira de conversão pandas/Polars**, que deve permanecer no único ponto definido no Plano 0; espalhá-la é a forma mais comum de introduzir o retrabalho que este roadmap busca evitar. O terceiro é a **adequação à máquina**: todos os planos rodam na CPU e respeitam a restrição sem PyTorch; os volumes envolvidos nos hubs são pequenos e instantâneos, e o cuidado de desempenho concentra-se no módulo Dados, onde a regra de ouro (o DuckDB encolhe antes da bancada explorar) e o eventual uso do Polars dão a margem necessária com os 16 GB de memória disponíveis.

Por fim, vale alinhar dois itens já presentes no roadmap do projeto: o **PR9.1 (gráficos)** é realizado pelo Plano 1, e o **PR9.2 (encadeamento em estágios)** conversa diretamente com o Plano 5, em que as saídas tabulares de ML ganham mais valor se puderem virar novas fontes. Tratá-los em conjunto evita esforço duplicado.

---

## 8. Pendências pontuais — revisão exploratória do `core/data/` (jul/2026)

Itens de baixo risco, deliberadamente não corrigidos na revisão arquivo-a-arquivo do `core/data/`
([`plans/active/PLANO_CORRECOES_CORE_DATA.md`](plans/active/PLANO_CORRECOES_CORE_DATA.md)) — registrados aqui
em vez de expandir o escopo da correção:

- **XLSX multi-planilha em consultas**: `engine.register_views` não repassa `sheet` — uma consulta (via NL→SQL
  ou SQL manual) sobre um arquivo XLSX de várias abas sempre lê a planilha padrão; só o `preview` (modal de
  pré-visualização) aceita selecionar a aba. Propagar `sheet` exigiria um campo novo em `DataFile` e
  atravessar `scanner`/GUI/CLI — vale a pena quando um plano futuro precisar de fato de consultas
  multi-planilha, não como correção isolada.
- **Tamanho de arquivo**: `core/data/charts.py` está no teto da régua de tamanho (~430 linhas — corte natural
  seria heurísticas puras × renderers matplotlib) e `core/data/engine.py` ficou acima do alvo (~410 linhas,
  após a Fase 1-4 deste plano). Nenhum dos dois tem baixa coesão hoje (arquitetura §3) — dividir **ao tocar**
  na próxima feature que os estender, não preventivamente.

---

## 9. Pendências pontuais — revisão exploratória do `core/audio/` (jul/2026)

Item de baixo risco, deliberadamente não corrigido na revisão arquivo-a-arquivo do `core/audio/`
([`plans/active/PLANO_CORRECOES_CORE_AUDIO.md`](plans/active/PLANO_CORRECOES_CORE_AUDIO.md)):

- **`denoiser.denoise` processa o arquivo inteiro em memória**: mesmo com `dtype="float32"` (Fase 2 do plano
  corta o pico pela metade frente ao `float64` default), um áudio de várias horas ainda carrega tudo de uma
  vez via `sf.read`. Processamento em chunks (janela deslizante com overlap, reduce_noise por bloco) resolveria
  o caso extremo, mas é reestruturação real do pipeline — vale a pena só se surgir um caso de uso concreto de
  áudio muito longo, não como correção isolada.

---

## 10. Pendências pontuais — revisão exploratória do `core/library/` (jul/2026)

Item de baixo risco, deliberadamente não corrigido na revisão arquivo-a-arquivo do `core/library/`
([`plans/active/PLANO_CORRECOES_CORE_LIBRARY.md`](plans/active/PLANO_CORRECOES_CORE_LIBRARY.md)):

- **Cache `(path, mtime) → JSON` duplicado entre `core/data/assess.py` e `core/library/tags.py`**: os dois
  módulos implementam a mesma tríade `_load_cache`/`load_cached_*`/`save_*` (carrega JSON tolerando arquivo
  ausente/malformado, valida frescor pelo mtime, grava via `io_atomic`), diferindo só no tipo do valor
  cacheado (`text: str` vs `tags: list[str]`). Extrair um helper genérico exigiria um módulo novo em
  `core/` compartilhado pelos dois pacotes e tocar `core/data` de novo fora do escopo deste plano — mantido
  como duplicação aceita (mesmo racional de `core/text` × `core/ml` já registrado no HISTORY). Vale a pena
  se um terceiro consumidor do mesmo padrão aparecer.

---

## 11. Pendências pontuais — revisão exploratória do `core/document/` (jul/2026)

Itens de baixo risco, deliberadamente não corrigidos na revisão arquivo-a-arquivo do `core/document/`
([`plans/active/PLANO_CORRECOES_CORE_DOCUMENT.md`](plans/active/PLANO_CORRECOES_CORE_DOCUMENT.md)):

- **`watermark_pdf` em páginas com `rotation` ≠ 0 sai de lado**: mesma causa-raiz do `stamp_pdf` (corrigido
  nesta revisão) — `TextWriter`/`insert_text`/`draw_rect` escrevem no espaço de conteúdo não-rotacionado da
  página, enquanto a posição é calculada a partir do rect visual (rotacionado). Para o `stamp_pdf`, mapear o
  ponto/retângulo por `page.derotation_matrix` (com `Rect.normalize()` depois, já que os cantos podem trocar
  de ordem) e contra-rotacionar o texto com `rotate=page.rotation` resolveu de forma limpa, validado
  numericamente nas quatro rotações (0/90/180/270). O `watermark_pdf` soma a essa mecânica seu próprio
  `TextWriter(rect, opacity=...)` com clip próprio e o `morph=(pivot, rot_matrix)` do efeito diagonal de 45°;
  a tentativa de aplicar a mesma correção (`TextWriter(page.mediabox, ...)` + pontos/pivot mapeados por
  `derotation_matrix` + ângulo composto `45 + page.rotation`) não convergiu num teste (watermark sai clipado
  ou fora da página em pelo menos uma das quatro rotações) — não é um fix trivial de uma linha como o do
  stamp; exige entender a interação entre o clip-rect do `TextWriter` e o `morph`. Vale revisitar se um
  usuário reportar o problema na prática (a maioria dos PDFs não tem `/Rotate` ≠ 0).
- **Tamanho de arquivo**: `processor.py` está em ~351 linhas — acima do alvo de 300 para módulos de `core/`,
  abaixo do teto de 400 (arquitetura §3). Nenhum sinal de baixa coesão hoje (é uma função por operação de
  PDF, sem abas/seções misturadas) — dividir **ao tocar** na próxima operação nova, não preventivamente.

---

## 12. Pendência pontual — adotar `core/text/clean.py` na indexação do RAG (jul/2026)

Item deliberadamente fora do escopo do
[`plans/implemented/PLANO_INSIGHTS_QUALIDADE.md`](plans/implemented/PLANO_INSIGHTS_QUALIDADE.md), que criou
`clean.py` só para `summarize`/`keywords`/o painel Insights:

- **`rag/indexer.py` ainda embedda os marcadores de página crus** (`--- Página N ---`): o texto que vira
  chunk no índice RAG não passa por `clean.clean_document_text`, então esses marcadores continuam sendo
  embeddados e citados como se fossem conteúdo. Adotar `clean.py` aqui exige **reindexação** (o texto
  embeddado muda) e pertence ao `PLANO_RAG_ESPACO_EMBEDDING` já cogitado (junto dos prefixos de tarefa do
  `nomic-embed` e do header de contexto do chunk — ver `docs/reference/AVALIACAO_ML_RAG_FABLE5.md` §2.1/2.4)
  — uma reindexação versionada única, não uma correção isolada.
