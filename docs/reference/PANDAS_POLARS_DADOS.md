# pandas e Polars no mill.tools

**Documento técnico — exploração e análise de dados de forma leve e eficiente, com foco no módulo Dados e extensão aos 3 hubs**
Data: 23 de junho de 2026 · Público-alvo: leitor sem formação em programação, com interesse técnico · Restrição de projeto: torch-free, CPU-first, máquina modesta (16 GB de RAM)

---

## Sumário

1. Objetivo
2. Três ferramentas, três papéis: DuckDB, pandas e Polars
3. O princípio que governa tudo: deixar o motor encolher antes de explorar
4. Foco no módulo Dados
   - 4.1 Onde pandas e Polars entram (e onde não devem entrar)
   - 4.2 A ponte DuckDB ↔ pandas, sem cópia
   - 4.3 Práticas de eficiência em pandas
   - 4.4 Polars: quando e por quê
   - 4.5 Quadro comparativo completo: pandas vs Polars
   - 4.6 Recomendação para o módulo Dados
5. Estendendo os 3 hubs com pandas/Polars
   - 5.1 Biblioteca
   - 5.2 IA (RAG)
   - 5.3 Receitas
6. Considerações sobre a máquina
7. Glossário técnico

---

## 1. Objetivo

Este documento explica como as bibliotecas de análise de dados **pandas** e **Polars** podem ser empregadas no `mill.tools` de maneira **leve e eficiente**, sem violar a filosofia torch-free nem sobrecarregar uma máquina modesta. O foco principal é o módulo **Dados**, que já adota o DuckDB como motor; em seguida, examina-se se as mesmas ferramentas conseguem **estender funcionalidades dos três hubs** (Biblioteca, IA e Receitas).

A tese central é simples e será repetida porque é a chave de tudo: **pandas e Polars não competem com o DuckDB que você já tem — eles ocupam um papel diferente e complementar.** Usá-los bem significa saber exatamente qual papel é esse.

---

## 2. Três ferramentas, três papéis: DuckDB, pandas e Polars

É indispensável entender por que existem três ferramentas que, à primeira vista, "fazem a mesma coisa" com tabelas. Elas não fazem.

O **DuckDB** é um **motor de banco de dados analítico**. Sua especialidade é ler arquivos grandes **direto do disco**, sem carregá-los inteiros na memória, e executar consultas — filtrar, juntar, agrupar, somar — de forma extremamente otimizada. É o equivalente a um **galpão logístico**: você pede "todas as vendas de março acima de mil reais agrupadas por região" e ele devolve apenas o resultado, sem nunca despejar o estoque inteiro no seu colo. No seu projeto, ele já é a única fronteira de dados, por escolha consciente.

O **pandas** é uma **bancada de trabalho em memória**. Ele carrega os dados na RAM e oferece um ferramental riquíssimo para manipular, transformar, explorar e — crucialmente — **conectar os dados a outras bibliotecas** (gráficos, aprendizado de máquina, estatística). É o equivalente à **bancada do artesão**: tudo fica à mão para um trabalho detalhado, mas a bancada tem tamanho limitado (a RAM) e não comporta uma carga inteira de galpão.

O **Polars** é uma **bancada de trabalho moderna**, projetada anos depois do pandas e escrita na linguagem Rust. Faz o mesmo papel do pandas, porém é tipicamente mais rápido, usa menos memória, aproveita todos os núcleos do processador e tem um modo "preguiçoso" (*lazy*) que planeja toda a sequência de operações antes de executá-la, evitando trabalho desperdiçado. É como uma bancada com instrumentos elétricos e um assistente que organiza a ordem das tarefas antes de começar.

A consequência prática dessa divisão de papéis: **o galpão (DuckDB) faz o trabalho pesado de reduzir os dados; a bancada (pandas ou Polars) faz o acabamento fino do resultado já reduzido.** Inverter essa ordem — jogar a carga do galpão inteira na bancada — é a causa número um de lentidão e estouro de memória.

---

## 3. O princípio que governa tudo: deixar o motor encolher antes de explorar

Antes de descer aos detalhes, vale fixar o princípio que organiza todas as recomendações deste documento.

Um arquivo de dados pode ter gigabytes. O pandas é **in-memory**: ao abrir um arquivo, ele puxa **tudo** para a RAM de uma vez, e ainda costuma usar tipos de dados perdulários, podendo ocupar **várias vezes** o tamanho do arquivo original. Numa máquina com 16 GB de RAM, abrir diretamente um CSV de 2 GB no pandas é um convite ao travamento.

O DuckDB não tem esse problema: ele lê o arquivo "de fora", aplica os filtros e as agregações e devolve **apenas o resultado** — que, quase sempre, é pequeno. A regra de ouro, portanto, é:

> **Use o DuckDB para encolher os dados ao mínimo necessário; só então entregue esse resultado reduzido ao pandas ou ao Polars para a exploração detalhada, os gráficos ou o aprendizado de máquina.**

Esse princípio preserva tanto a leveza quanto a eficiência, e respeita a arquitetura que o projeto já escolheu. Tudo o que segue é uma elaboração dele.

---

## 4. Foco no módulo Dados

### 4.1 Onde pandas e Polars entram (e onde não devem entrar)

O módulo Dados foi construído em torno do DuckDB, e isso deve permanecer. O DuckDB continua sendo o responsável por **abrir os arquivos, executar as consultas em português ou SQL, perfilar e converter** — tudo o que envolve ler dados grandes do disco.

O pandas e o Polars entram em **três pontos específicos**, todos depois que o DuckDB já reduziu os dados.

O primeiro ponto é o **acabamento da exploração**: transformações finais que são mais naturais ou expressivas na bancada do que em SQL — reformatar colunas, calcular indicadores derivados, pivotar uma pequena tabela de resultado, formatar para exibição. O segundo ponto é a **cola com o aprendizado de máquina**: as bibliotecas de ML descritas no documento complementar (scikit-learn, XGBoost) esperam receber os dados justamente no formato do pandas ou do numpy; portanto, o pandas é a ponte obrigatória entre uma consulta de dados e um modelo. O terceiro ponto são os **gráficos**: a evolução planejada do módulo (gráficos via matplotlib) consome DataFrames naturalmente — o pandas é o alimentador padrão de qualquer visualização.

Onde pandas e Polars **não** devem entrar: na leitura inicial de arquivos grandes, na execução das consultas principais e em qualquer operação que o DuckDB já faça bem sobre o arquivo bruto. Substituir o motor pela bancada seria um retrocesso de eficiência.

### 4.2 A ponte DuckDB ↔ pandas, sem cópia

A integração entre o DuckDB e o pandas é um dos pontos mais elegantes desse ecossistema, e é o que torna a "regra de ouro" barata na prática.

O DuckDB devolve o resultado de uma consulta **diretamente como um DataFrame do pandas**, com uma única instrução ao final da consulta. Essa transferência ocorre através de um formato de memória compartilhado chamado **Apache Arrow**, o que significa que ela é feita **praticamente sem cópia de dados** — rápida e econômica, sem duplicar nada na memória. O caminho inverso também existe: o DuckDB consegue **consultar um DataFrame que já está na memória como se fosse uma tabela**, permitindo alternar entre SQL e bancada conforme a conveniência de cada etapa.

A implicação é importante: não há penalidade de desempenho em usar o DuckDB para o trabalho pesado e o pandas para o acabamento. A passagem entre os dois é fluida e barata. Você obtém o melhor dos dois mundos — a eficiência do motor e a expressividade da bancada — sem custo de integração.

### 4.3 Práticas de eficiência em pandas

Quando o trabalho exigir o pandas, as seguintes práticas mantêm o uso leve. Estão ordenadas por impacto.

A prática de maior efeito é o **controle dos tipos de dados**. Por padrão, o pandas armazena números com a maior precisão possível e textos da forma mais cara possível. Converter números para tipos menores quando a precisão extra é desnecessária (de 64 para 32 bits) reduz o consumo pela metade; e converter colunas de texto repetido — categorias, status, nomes de cidade — para o tipo "categórico" pode cortar o consumo em **dez vezes ou mais**, porque o pandas passa a guardar cada valor distinto uma única vez. Em conjuntos reais, essa única medida costuma ser a diferença entre caber e não caber na memória.

A segunda prática é **ler apenas o necessário**: selecionar de antemão somente as colunas relevantes e, em arquivos grandes, processar em blocos sucessivos em vez de tudo de uma vez. A terceira é **vetorizar as operações** — operar sobre a coluna inteira de uma só vez, em vez de percorrer linha por linha. Percorrer um DataFrame linha a linha é o erro de eficiência mais comum e mais grave; a versão vetorizada da mesma tarefa pode ser centenas de vezes mais rápida. A quarta é **preferir formatos de arquivo eficientes**: o formato Parquet — que o módulo já oferece como saída — é colunar, tipado e comprimido, sendo lido muito mais rápido e ocupando muito menos espaço que o CSV. A quinta é **medir antes de otimizar**: o pandas informa o consumo real de memória por coluna, permitindo identificar com precisão onde está o peso.

### 4.4 Polars: quando e por quê

O Polars merece consideração séria justamente porque **se alinha com a filosofia de leveza do projeto**.

Suas vantagens sobre o pandas são concretas: usa todos os núcleos do processador automaticamente (o pandas é majoritariamente de núcleo único), consome menos memória, e seu modo "preguiçoso" planeja a sequência completa de operações antes de executá-la — descartando trabalho desnecessário e lendo apenas as colunas e linhas que o resultado final exige. Possui ainda um modo de processamento "em fluxo" (*streaming*) capaz de lidar com volumes maiores que a memória disponível. Em uma máquina modesta, essas características são especialmente bem-vindas.

As contrapartidas, que devem ser declaradas com honestidade: o Polars tem uma forma de uso diferente da do pandas, exigindo aprendizado; seu ecossistema de bibliotecas vizinhas, embora cresça depressa, ainda é menor; e, como o aprendizado de máquina em Python espera dados no formato do pandas/numpy, na fronteira com um modelo seria necessário converter de Polars para pandas de qualquer maneira — uma operação simples, mas que relativiza o ganho quando o destino final é o ML.

Em termos práticos: o Polars é uma alternativa moderna e eficiente para a **bancada de trabalho**, atraente sobretudo quando os resultados intermediários ainda são volumosos ou quando o desempenho de transformação importa. Não substitui o DuckDB como motor, e na borda do ML cede lugar ao pandas.

### 4.5 Quadro comparativo completo: pandas vs Polars

A tabela a seguir resume **todas as diferenças relevantes** entre as duas bancadas. A última coluna indica, em cada critério, qual delas leva vantagem — com a ressalva de que "vantagem" depende do objetivo: alguns critérios pesam no desempenho, outros na facilidade de integração.

| Critério | pandas | Polars | Vantagem |
|---|---|---|---|
| **Origem / implementação** | Python sobre C/NumPy; criado em 2008 | Escrito em Rust; criado em 2020 | — (contexto) |
| **Velocidade bruta** | Boa, mas de núcleo único | Muito alta, tipicamente várias vezes mais rápido | **Polars** |
| **Paralelismo** | Majoritariamente um único núcleo do processador | Usa todos os núcleos automaticamente | **Polars** |
| **Uso de memória** | Alto; tipos perdulários e cópias intermediárias | Enxuto; baseado em Apache Arrow, com menos cópias | **Polars** |
| **Modelo de execução** | Imediato (*eager*): cada passo roda na hora | Imediato **e** preguiçoso (*lazy*) com otimizador de consulta | **Polars** |
| **Dados maiores que a RAM** | Não — carrega tudo na memória | Sim — modo de processamento em fluxo (*streaming*) | **Polars** |
| **Valores ausentes (vazios)** | Confuso: mistura `NaN` e nulos, às vezes muda o tipo da coluna | Conceito de nulo nativo e consistente | **Polars** |
| **Índice (rótulo de linha)** | Possui índice — poderoso, mas fonte frequente de erros | Não possui índice — modelo mais simples e previsível | Depende do gosto |
| **Sintaxe / desenho da API** | Flexível, porém às vezes ambígua (várias formas de fazer o mesmo) | Explícita e baseada em expressões; mais consistente | **Polars** (qualidade) |
| **Curva de aprendizado e material** | Vastíssimo: anos de tutoriais, cursos e respostas prontas | Menor, embora cresça depressa | **pandas** |
| **Ecossistema e integração** | Universal: gráficos, estatística e ML esperam receber pandas | Crescente, mas exige conversão na fronteira com outras libs | **pandas** |
| **Integração com aprendizado de máquina** | Direta (scikit-learn, XGBoost, numpy consomem pandas) | Requer converter para pandas/numpy na borda do modelo | **pandas** |
| **Interoperabilidade (Arrow, DuckDB, Parquet)** | Excelente, via Apache Arrow | Excelente e ainda mais natural (Arrow é a base) | Leve **Polars** |
| **Estabilidade da API** | Madura e estável há anos | Evolui rápido; pode haver mudanças entre versões | **pandas** |
| **Maturidade e adoção** | Padrão de fato, onipresente na indústria | Adoção crescente, ainda minoritária | **pandas** |
| **Adequação a máquina modesta (CPU, RAM limitada)** | Adequado, desde que os dados já estejam reduzidos | Superior: menos memória, multinúcleo e *streaming* | **Polars** |

A leitura honesta do quadro: **o Polars vence nos eixos de engenharia — velocidade, memória, paralelismo, escala e desenho da linguagem.** O **pandas vence nos eixos de ecossistema — maturidade, volume de material de apoio, estabilidade e, sobretudo, integração direta com o aprendizado de máquina.** Não há um vencedor absoluto; há um vencedor por finalidade. Para *transformar e explorar dados com eficiência*, o Polars é claramente mais vantajoso. Para *entregar dados a um modelo de ML ou a uma biblioteca de gráficos consagrada*, o pandas ainda é o caminho de menor atrito — e, na prática, a conversão de Polars para pandas nessa fronteira é trivial.

### 4.6 Recomendação para o módulo Dados

A hierarquia recomendada é clara e estável: **o DuckDB permanece como motor de peso**, lendo arquivos e executando consultas; **o pandas (ou o Polars) atua na última milha**, recebendo o resultado já reduzido para acabamento, gráficos e preparação de dados; e **as bibliotecas de ML** consomem o resultado do pandas quando houver modelagem. Não se promove a bancada a motor; não se rebaixa o motor a bancada. Cada um no seu papel, com a passagem entre eles barata graças ao formato Arrow.

---

## 5. Estendendo os 3 hubs com pandas/Polars

A pergunta — se pandas/Polars podem ampliar funcionalidades dos hubs — tem resposta afirmativa, e por um motivo estrutural: os três hubs **produzem ou acumulam informação tabular** (catálogos, índices, históricos) que hoje é tratada de forma pontual. Organizar essa informação como tabelas em memória abre espaço para análises e painéis que hoje não existem. Em todos os casos vale a mesma regra de ouro: tabelas pequenas, derivadas de dados que o sistema já tem.

### 5.1 Biblioteca

A Biblioteca já varre tudo sob `output/` e conhece, de cada item, seu tipo, categoria, tamanho e data de modificação. Hoje essa varredura serve apenas para listar e filtrar. Convertida em uma tabela do pandas, ela habilita um **painel analítico do acervo**.

Concretamente: contagens e proporções por tipo e por categoria (quantos áudios, vídeos, documentos, conjuntos de dados); distribuição de tamanhos, identificando os maiores ocupantes de disco; e **evolução temporal** a partir das datas de modificação — quanto foi produzido por semana ou por mês, revelando ritmo de uso e períodos de maior atividade. Disso decorrem recursos úteis: identificar candidatos a limpeza (arquivos grandes e antigos), medir o crescimento do acervo e resumir o estado geral em poucos números. É uma camada de inteligência sobre metadados que a Biblioteca já coleta, sem nenhuma leitura nova de conteúdo pesado.

### 5.2 IA (RAG)

O hub de IA mantém um índice cujos metadados — quais documentos foram indexados, quantos fragmentos cada um gerou, qual o tamanho em disco, quando foi atualizado — já são apresentados pelo inspetor de índice atual. Tratados como uma tabela, esses metadados permitem **análises de saúde do índice** mais ricas.

Por exemplo: identificar quais documentos dominam o índice em número de fragmentos (e podem enviesar as buscas); apontar documentos potencialmente desatualizados; e quantificar a distribuição dos fragmentos. Há ainda dois ativos tabulares pouco explorados. O primeiro é o **histórico de tempos de resposta por modelo**, que o projeto já registra: organizado em uma tabela, rende estatísticas comparativas — tempo típico, variação, tendência — por modelo, sustentando a estimativa de tempo já exibida na interface com mais rigor. O segundo é a própria **matriz de embeddings**, que já é uma estrutura numérica (numpy): sobre ela é possível calcular, de forma leve, indicadores de redundância do acervo (quão semelhantes são os documentos entre si) e detectar fragmentos quase idênticos. Em todos esses casos, pandas e numpy bastam; não há leitura pesada envolvida.

### 5.3 Receitas

As Receitas encadeiam operações e registram o que ocorre em cada execução. Esse histórico de execução é, por natureza, tabular, e hoje é subutilizado. Estruturado em pandas, torna-se base para **inteligência operacional**.

As aplicações: **taxas de sucesso e falha** por receita e por etapa, revelando quais cadeias são confiáveis e quais costumam quebrar; **análise de tempos**, identificando os passos mais lentos e o custo típico de cada receita; e o **levantamento das cadeias mais usadas**, que sugere quais merecem virar predefinições. No modo lote, em que uma receita roda sobre vários arquivos, os resultados podem ser **agregados em uma única tabela analítica** — quantos itens foram processados, quantos tiveram êxito, quais demoraram mais — exportável nos formatos que o módulo Dados já oferece. Esse histórico tabular é, ainda, a matéria-prima das aplicações de ML descritas no documento complementar (previsão de tempo, detecção de configurações problemáticas), fechando o ciclo entre os dois documentos.

---

## 6. Considerações sobre a máquina

A máquina-alvo dispõe de 16 GB de RAM, o que é confortável para a estratégia recomendada, porém não ilimitado. As implicações são diretas.

Para os hubs, os volumes envolvidos — metadados de catálogo, registros de índice, históricos de execução — são pequenos: milhares de linhas, não milhões. O pandas os manipula instantaneamente, e a questão de eficiência sequer se coloca. O cuidado real está no módulo Dados, onde os arquivos do usuário podem ser grandes: é ali que a regra de ouro (DuckDB primeiro, bancada depois) e as práticas de tipos de dados fazem a diferença entre fluidez e travamento. O Polars, com seu menor consumo de memória e seu modo em fluxo, é um aliado natural justamente nessa máquina, para os casos em que os resultados intermediários ainda forem volumosos. Em nenhuma hipótese as recomendações deste documento exigem GPU, e todas respeitam a restrição torch-free.

---

## 7. Glossário técnico

- **DuckDB:** motor de banco de dados analítico que lê arquivos grandes direto do disco e executa consultas sem carregá-los inteiros na memória; já é o motor do módulo Dados.
- **pandas:** biblioteca que carrega dados na memória e oferece ferramental amplo para manipulá-los, explorá-los e conectá-los a gráficos e ML; a "bancada de trabalho".
- **Polars:** alternativa moderna ao pandas, escrita em Rust; mais rápida, mais econômica em memória, multinúcleo e com execução "preguiçosa".
- **DataFrame:** a estrutura central de pandas e Polars — uma tabela em memória com linhas e colunas tipadas.
- **In-memory:** que opera carregando os dados na memória RAM (caso do pandas), em oposição a ler do disco sob demanda (caso do DuckDB).
- **Apache Arrow:** formato de dados em memória compartilhado que permite transferir tabelas entre DuckDB, pandas e Polars praticamente sem cópia.
- **Parquet:** formato de arquivo colunar, tipado e comprimido; lê mais rápido e ocupa menos espaço que o CSV.
- **Tipo categórico:** forma de armazenar colunas de texto repetido guardando cada valor distinto uma só vez, reduzindo drasticamente o consumo de memória.
- **Vetorização:** operar sobre uma coluna inteira de uma vez, em vez de percorrer linha a linha; muito mais rápido.
- **Execução preguiçosa (lazy):** planejar toda a sequência de operações antes de executá-la, para descartar trabalho desnecessário (recurso do Polars).
- **Processamento em fluxo (streaming):** processar dados em pedaços sucessivos, permitindo lidar com volumes maiores que a memória disponível.
- **Última milha:** a etapa final de acabamento sobre um resultado já reduzido — o lugar próprio de pandas e Polars neste projeto.
