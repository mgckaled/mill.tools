# Machine Learning sem PyTorch no mill.tools

**Documento técnico — aplicação de aprendizado de máquina leve às 6 ferramentas e aos 3 hubs do projeto**
Data: 23 de junho de 2026 · Público-alvo: leitor sem formação em programação, com interesse técnico · Restrição de projeto: torch-free, CPU-first, máquina modesta

---

## Sumário

1. Objetivo e premissas
2. O que é "aprendizado de máquina" (de forma precisa, sem jargão vazio)
3. A pilha de ML leve, torch-free, recomendada
4. Aplicação às 6 ferramentas
   - 4.1 Áudio
   - 4.2 Vídeo
   - 4.3 Imagens
   - 4.4 Transcrição
   - 4.5 Documentos
   - 4.6 Dados
5. Aplicação aos 3 hubs
   - 5.1 Biblioteca
   - 5.2 IA (RAG)
   - 5.3 Receitas
6. Como isso se encaixaria na arquitetura existente
7. Priorização por esforço × retorno
8. Glossário técnico

---

## 1. Objetivo e premissas

Este documento descreve, de forma aprofundada, **o que o `mill.tools` poderia passar a fazer com técnicas de aprendizado de máquina — sem nunca instalar o PyTorch**. A premissa não é abrir mão de inteligência artificial; é reconhecer que uma parcela enorme do ML aplicado e útil **não depende de redes neurais profundas** e, portanto, dispensa a "oficina pesada" descrita no relatório anterior.

Três premissas guiam todas as recomendações abaixo:

A primeira é a **leveza**: toda biblioteca citada roda na CPU, ocupa pouco espaço e não traz o PyTorch como dependência. A segunda é o **reaproveitamento**: o projeto já produz dois ativos valiosos — os *embeddings* locais gerados pelo Ollama (no módulo de IA) e o motor de dados DuckDB — e a maior parte das ideias se apoia neles, evitando trabalho redundante. A terceira é a **disciplina arquitetural**: nada do que segue exige reescrever o programa; tudo encaixa nos padrões que o projeto já adota (núcleo puro, importação preguiçosa, recursos opcionais isolados em *extras*).

---

## 2. O que é "aprendizado de máquina", de forma precisa

Convém estabelecer o conceito com rigor, porque o termo é usado de forma frouxa.

**Aprendizado de máquina (machine learning, ou ML)** é a técnica de fazer um programa **descobrir padrões a partir de exemplos**, em vez de seguir regras escritas à mão. A distinção é essencial. Na programação tradicional, um humano escreve a regra: "se o arquivo termina em `.pdf`, trate como documento". No aprendizado de máquina, mostra-se ao programa milhares de exemplos rotulados ("este texto é uma palestra", "este é uma entrevista") e ele **infere sozinho a regra** que separa as categorias. Depois, aplica essa regra a casos novos que nunca viu.

É útil separar três famílias de tarefas, porque elas reaparecem o documento inteiro:

A primeira é a **classificação**: atribuir um rótulo a algo ("este áudio é fala ou música?"). A segunda é o **agrupamento (clustering)**: organizar itens parecidos em grupos **sem rótulos prévios** ("separe estes 200 arquivos em temas, descobrindo os temas sozinho"). A terceira é a **regressão**: prever um número ("quanto tempo esta transcrição vai levar?").

Há ainda um conceito-ponte indispensável: o **vetor de características (embedding)**. Computadores não comparam textos ou sons diretamente; eles os convertem em **listas de números que representam o significado ou as propriedades do item**. Dois textos sobre o mesmo assunto produzem listas de números próximas; dois assuntos distintos produzem listas distantes. Uma vez que tudo vira "coordenadas num mapa", as três tarefas acima se reduzem a **geometria sobre esses pontos** — e geometria é justamente o que as bibliotecas leves fazem muito bem e muito rápido, sem rede neural alguma rodando dentro do programa.

O ponto central, então, é este: **o trabalho pesado de transformar conteúdo em números o seu projeto já terceiriza** (o Ollama gera os embeddings de texto; bibliotecas clássicas extraem características de áudio e imagem). O que sobra para o seu app é a parte leve — a matemática sobre esses números — e é nela que o ML clássico brilha.

---

## 3. A pilha de ML leve, torch-free, recomendada

As seguintes bibliotecas compõem um conjunto coerente, todas sem PyTorch e todas executáveis na sua CPU:

| Biblioteca | Papel | Por que é leve |
|---|---|---|
| **scikit-learn** | Classificação, agrupamento, regressão, detecção de anomalia | O "canivete suíço" do ML clássico; pequeno, maduro, CPU |
| **XGBoost / LightGBM** | Modelos de árvore (*gradient boosting*) para dados em tabela | Estado da arte em dados tabulares; treina em segundos na CPU |
| **ONNX Runtime** | Executar redes neurais **já treinadas**, exportadas para o formato ONNX | Motor de inferência enxuto; **o projeto já o utiliza** (rembg) |
| **UMAP + HDBSCAN** | Reduzir dimensionalidade e agrupar embeddings | Baseados em numpy/numba, sem rede neural treinável |
| **librosa** | Extrair características de áudio (timbre, ritmo, energia) | numpy/scipy puro, padrão da indústria de áudio |
| **OpenCV / scikit-image / imagehash** | Visão computacional clássica (bordas, cor, "impressão digital" de imagem) | Algoritmos determinísticos, sem treino pesado |
| **spaCy (modelos pequenos) / NLTK / gensim** | Processamento de linguagem (entidades, tópicos) | Os modelos *small/medium* do spaCy são torch-free |
| **YAKE / sumy** | Palavras-chave e resumo extractivo, puramente estatísticos | Python puro, resultado instantâneo, sem modelo neural |

A leitura correta desta tabela: **o scikit-learn e o gradient boosting cobrem o ML "estrutural"** (classificar, agrupar, prever); **o ONNX Runtime é a ponte** para colher resultados de aprendizado profundo sem a oficina torch; e **librosa/OpenCV/spaCy extraem as características** que alimentam os dois primeiros. Juntas, elas formam um laboratório de ML completo que não pesa quase nada.

---

## 4. Aplicação às 6 ferramentas

Cada seção descreve o que a ferramenta faz hoje, o que o ML acrescentaria, a biblioteca indicada e uma avaliação honesta de viabilidade na sua máquina.

### 4.1 Áudio

A ferramenta hoje baixa, converte e pós-processa áudio (redução de ruído estatística e normalização de volume). O aprendizado de máquina entra na **compreensão do conteúdo sonoro**, não apenas na sua manipulação.

A aplicação mais direta é a **classificação automática de trechos**: distinguir fala, música e silêncio ao longo de um arquivo. Tecnicamente, a biblioteca **librosa** extrai as chamadas características espectrais (uma descrição numérica do "timbre" do som a cada instante) e um classificador do scikit-learn rotula cada segmento. Disso derivam recursos concretos: **detecção de fala (VAD)** para cortar silêncios automaticamente antes de transcrever — economizando tempo de processamento do Whisper; **identificação de música de fundo** para acionar a separação ou a normalização adequada; e **detecção de eventos** (aplausos, palmas, trechos muito altos).

Uma segunda aplicação é o **agrupamento de arquivos por semelhança acústica** — reunir gravações com perfil sonoro parecido —, útil quando a biblioteca acumula muitos áudios. A terceira é a **avaliação objetiva de qualidade**: estimar a relação sinal-ruído e detectar distorção por saturação (*clipping*) usando processamento de sinais clássico, oferecendo um parecer "este áudio está limpo / está ruidoso" antes do pós-processamento.

*Viabilidade:* alta. Extração de características de áudio e classificadores clássicos são leves e rodam confortavelmente na CPU.

### 4.2 Vídeo

A ferramenta executa oito operações de download e edição. O ML agrega valor sobretudo na **análise do conteúdo visual ao longo do tempo**, que hoje é inexistente.

O recurso mais valioso é a **detecção de cenas**: identificar automaticamente os pontos em que a imagem muda de forma significativa. A biblioteca **PySceneDetect** (construída sobre o OpenCV, sem torch) faz isso de modo determinístico. Disso decorre a **seleção inteligente de miniaturas** — em vez de capturar um quadro fixo, o programa escolhe quadros representativos de cada cena — e a **geração automática de capítulos**, marcando os tempos de transição. Uma extensão natural é a **sumarização visual**: agrupar os quadros-chave por semelhança (agrupamento sobre características de cor e composição) e apresentar uma "folha de contato" que resume o vídeo inteiro em poucas imagens.

*Viabilidade:* média-alta. A detecção de cenas processa quadros amostrados, não o vídeo todo em alta resolução, mantendo o custo de CPU controlado. Reconhecimento de objetos seria possível via ONNX Runtime, com custo maior, e fica como passo opcional.

### 4.3 Imagens

A ferramenta oferece doze operações, incluindo remoção de fundo (já via ONNX) e descrição por IA. O ML clássico amplia bastante o leque sem peso adicional.

Um caso quase didático é a **extração da paleta de cores dominante**: o algoritmo de agrupamento *K-means* do scikit-learn, aplicado aos pixels, devolve as cores predominantes da imagem — útil para gerar paletas, fundos coordenados ou metadados. A **detecção de imagens duplicadas ou quase idênticas** usa "impressões digitais perceptuais" (biblioteca **imagehash**): duas fotos visualmente parecidas geram códigos próximos, o que permite limpar a biblioteca de repetições e variações. A **classificação automática de imagens** — distinguir fotografia, captura de tela, documento escaneado, diagrama — pode ser feita com características clássicas e um classificador leve, ou com um modelo ONNX pré-treinado, e serviria para organizar e rotular automaticamente. Por fim, o **agrupamento temático** reúne imagens semelhantes em coleções automáticas, alimentando folhas de contato organizadas por assunto.

*Viabilidade:* alta para paleta, duplicatas e agrupamento; média para classificação por modelo ONNX (depende do tamanho da imagem).

### 4.4 Transcrição

Esta é a ferramenta mais "rica em texto" e, portanto, a que mais se beneficia do ML clássico de linguagem — **complementando**, não substituindo, o pipeline de IA já existente.

A **classificação automática do tipo de conteúdo** (palestra, entrevista, tutorial, reunião) permitiria **selecionar sozinho o perfil de análise** apropriado, eliminando uma decisão manual. Tecnicamente, basta um classificador do scikit-learn treinado sobre os embeddings da transcrição. A **segmentação por tópico** (técnica clássica de "TextTiling") divide um texto longo em blocos temáticos, gerando capítulos automáticos. A **extração de palavras-chave** (biblioteca YAKE, puramente estatística) produz etiquetas instantâneas para busca e organização. O **resumo extractivo** (biblioteca sumy, método TextRank) seleciona as frases mais centrais sem chamar nenhum modelo de linguagem — uma prévia gratuita e instantânea que complementa o resumo mais sofisticado do Analyzer.

Há ainda o refinamento da **marcação de qualidade**: hoje o transcritor sinaliza segmentos duvidosos com `[?]` por uma regra fixa sobre duas métricas; um classificador leve treinado nessas mesmas métricas poderia sinalizar com mais precisão.

Uma observação honesta sobre **diarização** ("quem falou"): as boas soluções dependem de PyTorch. Existe uma abordagem clássica — extrair características de voz e agrupá-las — que é torch-free, porém de qualidade nitidamente inferior. Vale como experimento, não como recurso confiável.

*Viabilidade:* alta. Tudo aqui opera sobre texto ou sobre embeddings já existentes; o custo é desprezível.

### 4.5 Documentos

A ferramenta manipula PDFs e já realiza OCR e análise textual. O ML acrescenta **compreensão e organização documental**.

A **classificação de documentos** — fatura, contrato, currículo, artigo — pode ser feita com a representação clássica "TF-IDF" (que mede a importância das palavras) somada a um classificador do scikit-learn, ou com embeddings. Isso habilita roteamento automático e arquivamento por categoria. A **extração de entidades nomeadas** (nomes, datas, valores, organizações), via modelo pequeno do spaCy, transformaria PDFs em dados estruturados pesquisáveis. O **agrupamento de documentos por tema** organiza acervos grandes sem rótulos prévios. E a **detecção de idioma** roteia o documento para o pacote de OCR e análise corretos.

*Viabilidade:* alta. TF-IDF e spaCy pequeno são leves; o gargalo, quando houver, é o OCR já existente, não o ML.

### 4.6 Dados

Esta ferramenta é a **fronteira natural do ML clássico**, porque o aprendizado de máquina tabular (sobre linhas e colunas) é exatamente onde o scikit-learn e o gradient boosting são imbatíveis — e onde o PyTorch tipicamente **não** ajuda.

As aplicações são diretas e de alto valor. A **detecção de anomalias** (algoritmos *Isolation Forest* ou *Local Outlier Factor*) aponta linhas que destoam do padrão — transações suspeitas, leituras de sensor improváveis, erros de digitação em massa. O **agrupamento de linhas** (*K-means*) segmenta registros parecidos, revelando grupos naturais (perfis de cliente, categorias de produto). A **regressão** projeta tendências e faz previsões simples. E a **importância de variáveis** do XGBoost/LightGBM responde à pergunta "quais colunas mais explicam este resultado?" — algo que a sumarização estatística do DuckDB não entrega.

Há também ganhos de **inteligência sobre o próprio dado**: detecção automática do tipo de cada coluna, identificação de possíveis dados sensíveis (padrões de CPF, e-mail, telefone) e sugestão de relações entre tabelas.

*Viabilidade:* alta. É o terreno mais favorável de todos; modelos de árvore treinam em segundos sobre milhares de linhas na CPU.

---

## 5. Aplicação aos 3 hubs

Os hubs operam **sobre as saídas de todas as ferramentas** e, por isso, são os lugares onde o ML rende efeitos de conjunto — recomendação, organização global e automação.

### 5.1 Biblioteca

A Biblioteca cataloga tudo sob `output/`, hoje de forma puramente descritiva (lista, filtra, ordena). O ML a transformaria de **catálogo passivo em organizador ativo**.

O recurso de maior impacto é o **agrupamento automático de todo o acervo por tema**: aplicando redução de dimensionalidade e agrupamento (UMAP + HDBSCAN) sobre os embeddings de todos os textos, a Biblioteca proporia "coleções" descobertas sozinha — "estes 12 arquivos são sobre finanças; estes 7, sobre saúde" — sem que ninguém defina os temas. Em segundo lugar, a **recomendação por similaridade** ("itens relacionados a este") usa exatamente o mesmo cálculo de distância entre embeddings que o RAG já emprega. Em terceiro, a **detecção global de duplicatas e quase-duplicatas** — textos que dizem quase a mesma coisa, imagens repetidas — ajuda a manter `output/` enxuto. Por fim, o **etiquetamento automático** anexa palavras-chave a cada item, melhorando a busca.

*Viabilidade:* alta, porque reaproveita embeddings já calculados; o agrupamento de algumas centenas de itens é instantâneo na CPU.

### 5.2 IA (RAG)

O hub de IA já recupera trechos e responde citando fontes. O ML clássico melhoraria a **qualidade e o controle** dessa recuperação.

A adição mais valiosa é o **reordenamento (reranking)**: depois de recuperar os trechos candidatos por similaridade, um segundo critério — um modelo compacto via ONNX Runtime, ou uma re-pontuação clássica — reordena-os para colocar os mais relevantes no topo antes de a resposta ser gerada, aumentando a precisão das citações. Um segundo recurso é a **detecção de pergunta fora de escopo**: se o trecho mais próximo ainda estiver "longe demais" da pergunta (distância acima de um limiar), o sistema avisa que o corpus provavelmente não contém a resposta, em vez de inventar — um ganho direto de confiabilidade. Um terceiro é o **roteamento de modelo**: um classificador leve examina a pergunta e escolhe automaticamente entre um modelo local rápido e um mais capaz, equilibrando velocidade e qualidade. E o **agrupamento do índice por tópico** ofereceria uma navegação temática do acervo indexado, complementando o inspetor de índice atual.

*Viabilidade:* alta para detecção de escopo, roteamento e agrupamento (matemática sobre vetores que já existem); média para o reranking por ONNX, que adiciona um modelo, ainda que pequeno.

### 5.3 Receitas

As Receitas encadeiam operações entre módulos e já registram dados de execução (incluindo tempos de resposta da IA). O ML transformaria esse histórico em **automação inteligente**.

A aplicação mais útil é a **previsão de tempo de execução**: uma regressão treinada sobre o histórico de durações estima quanto uma receita levará antes de rodar — informação valiosa numa máquina modesta. Em seguida, a **sugestão da próxima etapa** ao montar uma receita: analisando quais operações costumam suceder quais (mineração de sequências sobre o histórico), o construtor passa a recomendar o passo seguinte mais provável. Uma terceira aplicação é a **detecção de configurações problemáticas**: um classificador sobre os registros de execução aprende quais combinações de parâmetros tendem a falhar e alerta preventivamente. E, no modo lote, a **agregação dos resultados em uma tabela analítica** — quantas execuções tiveram sucesso, quais foram mais lentas — usando as próprias ferramentas tabulares descritas no documento complementar.

*Viabilidade:* alta. São análises sobre dados de operação já coletados; o custo é insignificante.

---

## 6. Como isso se encaixaria na arquitetura existente

Nenhuma das propostas exige romper com os princípios do projeto. O encaixe seguiria quatro padrões já consagrados no código.

Primeiro, o **núcleo permaneceria puro e testável**: as funções de ML viveriam em módulos próprios dentro de `src/core/`, recebendo o modelo ou a função de inferência por injeção — exatamente como o RAG já recebe a função de *embedding* e o cartão de dados. Isso mantém a testabilidade sem rede nem GPU. Segundo, a **importação seria preguiçosa**: as bibliotecas de ML só seriam carregadas no instante em que o recurso fosse acionado, preservando a abertura rápida do programa, tal como o rembg já faz. Terceiro, os recursos mais pesados ficariam atrás de um **extra opcional** (por exemplo, `[ml]`), de modo que a instalação base continue mínima e quem não usa não paga o custo. Quarto, cada recurso teria um **portão de disponibilidade**: se a dependência não estiver instalada, o botão correspondente aparece desabilitado com uma dica clara, como já ocorre com o OCR e a remoção de fundo.

Em síntese, o ML clássico entraria "pela mesma porta" que os recursos opcionais já existentes — de forma cirúrgica, isolada e reversível.

---

## 7. Priorização por esforço × retorno

Para orientar uma eventual implementação, segue uma ordenação pragmática, do mais vantajoso ao mais custoso.

No grupo de **maior retorno e menor esforço** estão os recursos que reaproveitam os embeddings já calculados: agrupamento temático da Biblioteca, recomendação por similaridade, detecção de duplicatas, classificação de tipo de transcrição/documento e detecção de pergunta fora de escopo no RAG. Praticamente não há dependência nova — é matemática sobre vetores existentes.

No grupo **intermediário** ficam os recursos que exigem extrair características novas mas com bibliotecas leves: classificação e VAD de áudio (librosa), detecção de cenas de vídeo (PySceneDetect), paleta de cores e duplicatas de imagem, ML tabular no módulo Dados (scikit-learn, XGBoost), previsão de tempo nas Receitas.

No grupo de **maior esforço ou retorno incerto** ficam o reranking por ONNX, a classificação de imagem por modelo pré-treinado e a diarização clássica de qualidade limitada — todos viáveis, porém com melhor relação custo-benefício apenas após os anteriores.

---

## 8. Glossário técnico

- **Aprendizado de máquina (ML):** fazer o programa inferir regras a partir de exemplos, em vez de seguir regras escritas à mão.
- **Classificação:** atribuir um rótulo a um item (fala/música; fatura/contrato).
- **Agrupamento (clustering):** organizar itens semelhantes em grupos sem rótulos prévios.
- **Regressão:** prever um valor numérico (duração, tendência).
- **Embedding (vetor de características):** representação de um item como uma lista de números que captura seu significado ou suas propriedades; permite medir semelhança como distância.
- **Detecção de anomalias:** identificar itens que destoam do padrão da maioria.
- **TF-IDF:** método clássico que mede a importância de cada palavra num texto, usado para classificar documentos sem rede neural.
- **scikit-learn:** biblioteca padrão de ML clássico em Python, leve e baseada em CPU.
- **Gradient boosting (XGBoost/LightGBM):** modelos de árvore de decisão combinados; referência em dados tabulares.
- **ONNX Runtime:** motor que executa redes neurais já treinadas, exportadas para um formato enxuto, sem a biblioteca de treino (torch); já usado no projeto.
- **librosa:** biblioteca de extração de características de áudio, sem torch.
- **PySceneDetect / OpenCV / imagehash:** ferramentas de visão computacional clássica (cenas, bordas, "impressão digital" de imagem).
- **spaCy / YAKE / sumy:** processamento de linguagem leve (entidades, palavras-chave, resumo) sem torch.
- **UMAP / HDBSCAN:** técnicas para reduzir dimensões e agrupar embeddings.
- **VAD (Voice Activity Detection):** detecção de presença de fala num áudio.
- **Reranking (reordenamento):** reordenar resultados de busca por um segundo critério de relevância antes de usá-los.
