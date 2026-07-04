# Análise de refatoração prévia (Plano −1)

**Documento de engenharia — diagnóstico da estrutura de arquivos do `mill.tools` e proposta de refatoração anterior ao roadmap de ML/dados**
Data: 23 de junho de 2026 · Base medida: `src/` (31.575 linhas de código Python) · Critério do usuário: evitar arquivos muito grandes e que misturem funcionalidades distintas num mesmo `.py`

---

## Sumário

1. Objetivo e método
2. Panorama de tamanhos (medição real)
3. O critério correto: tamanho **e** coesão
4. Diagnóstico por arquivo
5. A causa-raiz na GUI — e o precedente que o próprio projeto já oferece
6. Veredito: é preciso refatorar antes do Plano 0?
7. O Plano −1, em detalhe
8. O que **não** refatorar agora (e por quê)
9. Como executar com segurança
10. Encaixe no roadmap

---

## 1. Objetivo e método

A pergunta é direta: antes de iniciar o roadmap de ML/dados (a partir do Plano 0), é necessária uma refatoração estrutural para evitar arquivos grandes e de responsabilidade misturada? Para responder, a base de código foi medida objetivamente — contagem de linhas por arquivo, contagem de funções e classes por arquivo, e inspeção da organização interna dos maiores. O diagnóstico abaixo se apoia nesses números, não em impressão.

A conclusão antecipada, para orientar a leitura: **o Plano 0 em si não exige refatoração**, pois ele cria arquivos novos no núcleo de dados, que está saudável. Porém, **uma refatoração curta e cirúrgica é recomendada** para dois arquivos que já ultrapassam qualquer limiar razoável hoje e que serão estendidos pelos planos seguintes. Refatorá-los antes evita que o roadmap empilhe funcionalidade sobre arquivos já saturados.

---

## 2. Panorama de tamanhos (medição real)

Os maiores arquivos de código (excluídos `__init__.py` e dados estáticos) são:

| Arquivo | Linhas | Estrutura interna | Em rota do roadmap? |
|---|---|---|---|
| `gui/modules/data/view.py` | **1.368** | **1 função** `build_data_module` com **47 funções aninhadas**, 3 abas | Sim — Planos 1 e 5 |
| `gui/components/audio_player.py` | 797 | 2 classes (motor de áudio + UI) + helpers | Tangencial — Plano 6 (áudio) |
| `core/recipes/registry.py` | **733** | **33 adaptadores** de 7 módulos num só arquivo | Sim — Planos 5 e 7 |
| `gui/modules/document/worker.py` | 726 | worker do módulo Documentos | Não |
| `gui/modules/video/form_view.py` | 722 | formulário do módulo Vídeo | Não |
| `gui/modules/ai/view.py` | 685 | 1 função `build_ai_module`, 21 aninhadas | Sim — Planos 2, 4 |
| `gui/modules/library/view.py` | 658 | 1 função `build_library_module`, 25 aninhadas | Sim — Planos 2, 4 |
| `gui/home.py` | 620 | tela inicial | Não |
| `gui/views/progress_view.py` | 598 | painel de progresso + resolvedores | Não |
| `gui/modules/image/worker.py` | 528 | worker do módulo Imagens | Tangencial — Plano 6 |
| `core/data/engine.py` | 351 | 16 funções coesas (fronteira DuckDB) | Sim — Plano 0 (adjacente) |
| `gui/modules/data/worker.py` | 296 | pares `run_*`/`start_*` curtos | Sim — Planos 1 e 5 |

Para contraste, o núcleo (`src/core/`) é, em geral, pequeno e coeso: `core/image/transform.py` (386 linhas) são nove funções puras; `core/data/engine.py` (351) são dezesseis funções todas dedicadas à fronteira DuckDB. **O peso concentra-se esmagadoramente na camada de interface gráfica (`src/gui/`)**, não na lógica.

---

## 3. O critério correto: tamanho **e** coesão

Tamanho, isolado, é um sinal imperfeito. Um arquivo de 386 linhas com nove funções que fazem variações da mesma coisa (transformar imagem) é saudável: tem **alta coesão** — tudo ali pertence junto. Já um arquivo de 400 linhas que mistura leitura de disco, regra de negócio e desenho de tela tem **baixa coesão** e é problemático mesmo sendo menor.

O critério do usuário — "evitar arquivos grandes **e** com funcionalidades distintas" — combina as duas dimensões, e é o correto. Aplicando-o, um arquivo entra na lista de refatoração quando é **grande** (digamos, acima de ~500 linhas para lógica de interface, ou ~400 para lógica de núcleo) **e** abriga responsabilidades que poderiam viver separadas. Os dois sintomas juntos é que pesam.

Por essa régua, a base de código tem poucos, mas claros, infratores — e eles se concentram exatamente onde o roadmap vai mexer.

---

## 4. Diagnóstico por arquivo

**`gui/modules/data/view.py` (1.368 linhas) — infrator crítico.** É uma única função `build_data_module` com 47 closures internas. Os comentários de seção do próprio arquivo já revelam que ele abriga **três abas distintas** (Consulta, Pré-visualização, Análise com IA), cada uma com seus manipuladores, rodapé e progresso, mais um bloco de estado compartilhado (cronômetros, seleção de fonte). São três funcionalidades grandes num só arquivo e numa só função. É o pior caso da base e, agravante, está na rota dos Planos 1 (gráficos adicionam uma quarta aba) e 5 (operações de ML tabular). Sem refatorar, esses planos o empurrariam para perto de 2.000 linhas.

**`core/recipes/registry.py` (733 linhas) — infrator claro.** Reúne 33 adaptadores de passo de **sete módulos diferentes** (áudio, vídeo, transcrição, documentos, imagens, dados, IA) num único arquivo. A coesão é baixa por definição: um adaptador de áudio nada tem a ver com um de documentos. Os Planos 5 e 7 adicionam adaptadores de dados e de ML aqui, agravando o problema. A divisão é natural e de baixo risco.

**`gui/modules/ai/view.py` (685) e `gui/modules/library/view.py` (658) — infratores moderados.** Mesmo padrão do `data/view.py` (uma função-builder gigante com 21 e 25 closures), em escala menor. São estendidos pelos Planos 2 (painéis analíticos) e 4 (recursos semânticos), que adicionarão abas. Hoje estão no limite; depois dos planos, estourariam.

**`gui/components/audio_player.py` (797) — coeso, porém grande.** Mistura duas responsabilidades separáveis: o **motor** (decodificação, forma de onda, reprodução — classe `_AudioEngine`) e a **interface** (classe `AudioPlayer`). É grande, mas internamente já organizado em duas classes, e está fora da rota principal do roadmap. Candidato a dividir, sem urgência.

**`gui/modules/document/worker.py` (726), `video/form_view.py` (722), `home.py` (620), `progress_view.py` (598) — grandes, fora de rota.** São volumosos, mas cada um trata de um assunto só (um worker, um formulário, a home, o painel de progresso). A coesão é aceitável e o roadmap não os toca. Não justificam refatoração agora.

**`core/data/engine.py` (351), `core/image/transform.py` (386), `gui/modules/data/worker.py` (296) — saudáveis.** Coesos, de tamanho moderado, cada um com responsabilidade única. O `engine.py`, em particular, é a fronteira DuckDB e o Plano 0 cria um arquivo **ao lado** dele (a camada pandas/Polars), sem inchá-lo. Nenhuma ação necessária.

---

## 5. A causa-raiz na GUI — e o precedente que o próprio projeto já oferece

O padrão por trás dos infratores da interface é claro: cada módulo de GUI é construído por uma única função `build_X_module` que cria todos os controles e prende dezenas de manipuladores como closures no mesmo escopo. Esse desenho é prático no começo — tudo compartilha estado sem cerimônia — mas cresce de forma não-linear: quanto mais abas e ações, maior a função, até virar um arquivo de mil linhas.

A boa notícia é que **o próprio projeto já demonstrou a solução**, em três lugares. Os módulos de Imagens e Documentos quebram seus formulários em `blocks/` — cada bloco é uma função `build_X_block(page) → (Coluna, Refs)` que devolve o controle e um conjunto nomeado de acessores. O hub de IA já extraiu a aba de índice para um arquivo próprio, `index_tab.py`. E cada módulo separa "o que emitir" de "como exibir" num `pipeline_log.py` dedicado. Ou seja, **a convenção de decomposição já existe e é testada na prática**; basta aplicá-la aos builders que ainda não a seguem.

Isso muda a natureza da refatoração proposta: não é inventar um padrão novo, é **estender um padrão já consagrado** aos arquivos que ficaram para trás.

---

## 6. Veredito: é preciso refatorar antes do Plano 0?

A resposta honesta tem duas partes.

**O Plano 0 não exige refatoração.** Ele cria a camada pandas/Polars como um arquivo novo (`core/data/frames.py`) ao lado da fronteira DuckDB, que está saudável. Iniciar o Plano 0 hoje é seguro e não acumula dívida.

**Mas uma refatoração curta é fortemente recomendada — como um "Plano −1" — por dois motivos.** Primeiro, `data/view.py` (1.368 linhas) e `recipes/registry.py` (733) **já ultrapassam qualquer limiar saudável hoje**, independentemente do roadmap; são dívida técnica que convém quitar. Segundo, e alinhado ao objetivo de minimizar retrabalho: esses dois arquivos estão na rota dos Planos 1, 5 e 7, que adicionariam ainda mais funcionalidade sobre uma base já saturada. Dividi-los **antes** transforma esses planos em "adicionar um arquivo de aba/adaptador novo" em vez de "inchar mais um arquivo gigante".

A recomendação, portanto, não é uma grande reorganização preventiva de toda a GUI — isso seria, ele próprio, retrabalho, pois alguns planos podem reestruturar essas telas de qualquer modo. A recomendação é **cirúrgica**: refatorar agora apenas os dois arquivos que já estouram o limiar e estão na rota, e adotar uma regra permanente que faça os demais serem divididos **no momento em que o plano correspondente os tocar** (divisão "ao tocar"), nunca antes.

---

## 7. O Plano −1, em detalhe

O Plano −1 tem três entregas.

**(a) Decompor `gui/modules/data/view.py`.** Aplicar o padrão de `blocks/`/`index_tab.py` às três abas. Estrutura-alvo:

- `gui/modules/data/view.py` — passa a ser um `build_data_module` enxuto que apenas monta o estado compartilhado e encaixa as três abas.
- `gui/modules/data/tabs/query_tab.py` — aba Consulta (cartão de revisão SQL, tabela paginada de resultado, rodapé de ações).
- `gui/modules/data/tabs/preview_tab.py` — aba Pré-visualização (prévia da fonte, seletor de aba XLSX, botão Indexar no RAG).
- `gui/modules/data/tabs/analysis_tab.py` — aba Análise com IA (parecer, cronômetro).
- `gui/modules/data/_state.py` — o estado transversal (cronômetros, `_scoped_update`, seleção de fonte compartilhada pelas abas Pré-visualização e Análise).

Cada aba vira uma função `build_X_tab(...) → (controle, refs/handlers)`, exatamente como os blocos de imagem. O `view.py` resultante deve cair para algumas centenas de linhas. Quando o Plano 1 (gráficos) e o Plano 5 (ML tabular) chegarem, eles simplesmente adicionam `tabs/plot_tab.py` e `tabs/ml_tab.py`, sem tocar nas demais.

**(b) Dividir `core/recipes/registry.py` por módulo.** Estrutura-alvo:

- `core/recipes/registry/__init__.py` — monta o `STEP_REGISTRY` importando os adaptadores de cada módulo.
- `core/recipes/registry/audio.py`, `video.py`, `transcription.py`, `document.py`, `image.py`, `data.py`, `ai.py` — os adaptadores de cada módulo.

Isso mantém o `STEP_REGISTRY` como fonte única (montado no `__init__`), mas faz cada grupo de adaptadores viver em seu arquivo. O Plano 5 passa a editar só `registry/data.py`; o Plano 7, só o que lhe couber. O arquivo de teste `test_registry.py` acompanha a divisão (um arquivo de teste por grupo, espelhando `src/`, conforme a convenção de testes do projeto).

**(c) Fixar a convenção permanente.** Registrar a regra — preferencialmente no `CLAUDE.md` — de que **nenhuma função-builder de GUI deve ultrapassar ~400–500 linhas**, e que abas e seções independentes devem ser extraídas para sub-builders `build_X(...) → (controle, refs)`, no padrão já usado em `blocks/`, `index_tab.py` e `tabs/`. Essa regra é o que garante que os Planos 2, 4 e 7 dividam `ai/view.py`, `library/view.py` e o builder das Receitas **ao tocá-los**, em vez de recriar o problema.

---

## 8. O que **não** refatorar agora (e por quê)

Tão importante quanto o que fazer é o que **deixar quieto**, para não gerar o retrabalho que o roadmap busca evitar.

`ai/view.py` e `library/view.py` **não** devem ser divididos no Plano −1, e sim no início dos Planos 2/4, que os estendem. Dividi-los agora e depois reestruturá-los para acomodar os painéis analíticos seria mexer duas vezes; dividir **no momento** em que a aba nova é adicionada é uma mexida só. `audio_player.py`, `document/worker.py`, `video/form_view.py`, `home.py` e `progress_view.py` estão fora da rota do roadmap; embora grandes, não há ganho em tocá-los agora — a divisão deles pode esperar uma futura faxina geral ou o plano que porventura os toque. E todo o `src/core/` saudável permanece intacto.

Em resumo: o Plano −1 toca **dois** arquivos (mais a convenção); todo o resto segue a regra "divide-se ao tocar".

---

## 9. Como executar com segurança

A refatoração é **preservadora de comportamento** — move código, não muda o que ele faz —, então a rede de proteção é o conjunto de testes já existente (913 testes unitários, verdes, mais o `ruff`). A regra do projeto vale integralmente: rodar `uv run pytest -m unit` verde antes de qualquer commit.

Há um cuidado específico com a GUI: como a camada Flet não é testável de forma automatizada (headless), os builders de interface não têm cobertura de teste. A mitigação é dupla. Primeiro, ao decompor um builder, **separar a lógica pura** (que pode ganhar testes) das amarrações Flet — por exemplo, a paginação da tabela e a montagem de SQL efetivo da aba Consulta são lógica pura extraível e testável. Segundo, fazer um **teste de fumaça manual** após cada divisão: abrir o módulo, percorrer as abas, rodar uma consulta. Para `recipes/registry.py`, o risco é menor, porque os adaptadores **já têm testes** (`test_registry.py`); basta espelhar a divisão nos testes.

Recomenda-se executar o Plano −1 em duas entregas independentes e pequenas — primeiro o `registry` (mais seguro, com testes), depois o `data/view` —, cada uma com a suíte verde, em vez de uma única refatoração grande.

---

## 10. Encaixe no roadmap

A sequência completa passa a ser: **Plano −1 (refatoração cirúrgica) → Plano 0 (fundação de dados) → … → Plano 7.**

O Plano −1 não bloqueia o Plano 0 — eles poderiam até ser paralelos, pois tocam arquivos diferentes (`registry`/`data/view` vs. o novo `frames.py`). Mas colocá-lo primeiro tem um valor de método: estabelece, logo de saída, a convenção de decomposição que todos os planos seguintes herdam. Com isso, a regra "divide-se ao tocar" passa a operar automaticamente — o Plano 1 cria `tabs/plot_tab.py`, o Plano 2 divide os builders dos hubs ao adicionar os painéis, o Plano 5 edita só `registry/data.py` — e o roadmap inteiro avança sem reinflar nenhum arquivo. É a mesma filosofia do roadmap aplicada à própria estrutura do código: pagar uma fundação pequena uma vez, para não pagar retrabalho muitas vezes.
