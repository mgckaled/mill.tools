# E se o mill.tools NÃO fosse "torch-free"?

**Relatório de cenário — uma exploração técnica, contada para quem nunca programou**
Data: 23 de junho de 2026 · Máquina-alvo: Dell Inspiron 7580 (i5-8265U · 16 GB RAM · NVIDIA MX150 2 GB · CUDA 12.6 · Windows 10)

---

## 1. Em uma frase

Adotar o PyTorch abriria a porta para recursos de IA muito mais sofisticados (saber **quem** falou em cada trecho, separar voz de música, ampliar imagens borradas), mas cobraria um preço alto em peso de instalação, complexidade e — no seu caso específico — esbarraria com força na sua placa de vídeo de apenas **2 GB**. A decisão atual de ficar sem torch não é teimosia: ela é, em boa parte, **sob medida para a sua máquina**.

---

## 2. Antes de tudo: o que é o "torch"?

Vamos do zero, porque o resto do relatório depende de você entender bem isto.

### 2.1 O que é uma "biblioteca" / "framework"

Quando alguém escreve um programa, ela não constrói tudo do zero. Ela usa **bibliotecas**: caixas de peças prontas que outras pessoas já fabricaram e testaram. É a diferença entre construir uma casa serrando suas próprias árvores e construir uma casa comprando tijolos, portas e janelas prontos numa loja de materiais.

O **PyTorch** (no código, ele se chama só `torch`) é uma dessas caixas de peças — só que uma caixa **gigante e especializada em inteligência artificial**. Pense nele como uma **oficina industrial pré-montada para fabricar e operar "cérebros artificiais"** (as chamadas redes neurais). Quase toda a IA moderna que você ouve falar — desde reconhecimento de voz até geradores de imagem — foi construída usando o PyTorch ou um primo dele.

O termo **"torch-free"** que aparece o tempo todo no seu projeto significa, literalmente, **"sem essa oficina instalada"**. Seu programa hoje faz IA, mas usando ferramentas mais leves e alternativas, sem trazer a oficina pesada para dentro de casa.

### 2.2 Tensores — a "planilha com superpoderes"

A peça central do PyTorch se chama **tensor**. Não se assuste com o nome.

Imagine uma **planilha do Excel**: linhas e colunas cheias de números. Um tensor é exatamente isso, só que pode ter mais "dimensões" (imagine várias planilhas empilhadas, e depois várias pilhas lado a lado). Uma foto, por exemplo, é só uma tabela de números: cada pixel tem um valor de vermelho, verde e azul. Um som é uma fileira de números (a altura da onda a cada instante). Para o computador, **tudo vira tabela de números** — e o tensor é o formato dessa tabela.

O superpoder do PyTorch é fazer **contas com tabelas inteiras de uma vez**, e fazer isso muito rápido. Em vez de somar número por número (como você faria na mão), ele soma a planilha inteira em um único gesto. É a diferença entre um caixa de banco atendendo um cliente por vez e um caixa eletrônico que processa mil transações simultâneas.

### 2.3 Autograd — o "professor que corrige a prova e ainda ensina"

A parte mais "mágica" do PyTorch chama-se **autograd** (gradiente automático). Esta é a peça que permite **treinar** uma IA, ou seja, fazê-la aprender.

Analogia: imagine ensinar uma criança a acertar uma cesta de basquete. Ela arremessa, erra para a direita, e você diz "errou 30 cm para a direita". Ela ajusta e tenta de novo. O autograd é um **assistente que, depois de cada erro da IA, calcula automaticamente em que direção e o quanto cada "músculo" do cérebro artificial precisa se ajustar** para errar menos na próxima. Sem ele, ensinar uma rede neural seria como treinar a criança vendado e sem ninguém dizer se acertou ou errou.

Detalhe importante para o seu caso: **você quase nunca quer treinar** uma IA do zero — isso exige supercomputadores e meses. O que você faz é **usar** cérebros já treinados por empresas grandes. Mas mesmo só para *usar* um modelo treinado em PyTorch, você costuma precisar da oficina PyTorch instalada para "ligar" esse cérebro. É como precisar de uma tomada específica para plugar um aparelho importado.

### 2.4 CPU, GPU e CUDA — "o escritório de gênios vs. o galpão de mil estagiários"

Aqui está o conceito que decide quase tudo no seu projeto.

- **CPU** (o processador principal, o seu i5-8265U) é como um **escritório com 4 a 8 funcionários extremamente inteligentes**. Cada um resolve qualquer problema complicado, um depois do outro. Ótimo para tarefas variadas e sequenciais.

- **GPU** (a placa de vídeo, sua NVIDIA MX150) é como um **galpão com milhares de estagiários**. Cada um sozinho é fraco e só sabe fazer continhas simples, mas são **milhares fazendo ao mesmo tempo**. Para o tipo de conta da IA — "multiplique estas mil tabelas de números todas de uma vez" — o galpão de estagiários é absurdamente mais rápido que o escritório de gênios.

- **CUDA** é a **língua que só as placas NVIDIA falam** para receber ordens desse tipo. É o idioma em que você diz ao galpão de estagiários o que fazer. O PyTorch sabe falar CUDA fluentemente — por isso a IA "voa" numa placa NVIDIA.

A grande sacada: o PyTorch foi feito justamente para **mandar o trabalho pesado para o galpão de estagiários (GPU) automaticamente**. É aí que mora tanto o atrativo quanto a armadilha no seu caso — porque o seu galpão é pequeno (volto a isso na seção 9).

### 2.5 Por que quase todo o mundo da IA usa torch

Porque virou o **idioma comum** da área. A esmagadora maioria dos modelos novos é publicada já "embrulhada" em PyTorch. Adotar torch é como aprender inglês para viajar: você passa a entender quase todo mundo sem precisar de tradutor. Ficar torch-free é como viajar só com tradutores de bolso — funciona, mas alguns lugares ficam inacessíveis ou dão mais trabalho.

---

## 3. O que significa, hoje, o seu projeto ser "torch-free"

O seu `mill.tools` **já faz inteligência artificial** — e bastante. A graça é que ele faz isso com **substitutos mais leves** no lugar da oficina PyTorch. Vale entender o que você já tem, porque é a régua contra a qual mediremos o "e se":

- **Transcrição (Whisper):** em vez do Whisper original (que roda sobre PyTorch), você usa o **faster-whisper** com o motor **ctranslate2**. É o mesmo cérebro do Whisper, mas "recompactado" para rodar sem a oficina pesada e usando muito menos memória de vídeo. É como ter a receita de um prato famoso adaptada para uma cozinha pequena, em vez de exigir a cozinha industrial original.

- **Remoção de fundo de imagem (rembg):** roda sobre o **onnxruntime**, outro "motor de IA" mais enxuto que o torch. Mesma ideia: usa o cérebro pré-treinado sem a oficina inteira.

- **Redução de ruído de áudio:** o **noisereduce** faz limpeza por método estatístico clássico (sem rede neural), 100% na CPU.

- **IA de texto / RAG (perguntar sobre seus documentos):** você delega para o **Ollama** (modelos locais) e para o **Gemini** (nuvem). O peso de rodar a IA fica *fora* do seu programa — o Ollama é um aplicativo separado.

- **Dados:** o **DuckDB** faz as contas pesadas, também sem torch.

Em resumo: hoje seu programa é um **carro econômico bem afinado**. Adotar o torch seria trocar por um **caminhão potente** — capaz de carregar coisas que o carro não carrega, mas que gasta mais combustível, ocupa a garagem inteira e não cabe em algumas ruas (a sua placa de 2 GB é uma "rua estreita").

---

## 4. O que mudaria se você adotasse o torch

Concretamente, "adotar o torch" significaria adicionar o `torch` (e geralmente os irmãos `torchvision` para imagem e `torchaudio` para som) à lista de peças do projeto. A partir daí, você poderia instalar e rodar **diretamente** centenas de modelos de IA que hoje estão fora do seu alcance — sem precisar de adaptações como o ctranslate2.

Mas atenção a um ponto que muita gente erra: **instalar o torch não deixa nada mais rápido por mágica.** Ele só **abre a porta** para novos recursos e para usar a GPU diretamente. Os ganhos e as perdas vêm do *que você faz* depois que a porta está aberta. É o que detalham as próximas seções.

---

## 5. Vantagens de adotar o torch

**Acesso imediato ao ecossistema inteiro.** A maior vantagem não é velocidade — é **possibilidade**. Recursos que hoje exigiriam você "traduzir" um modelo (trabalho difícil e às vezes inviável) passariam a ser um `pip install` e algumas linhas. Saber **quem falou** numa reunião, separar a voz da música de um vídeo, ampliar uma foto pequena: tudo isso vive no mundo torch.

**Fim das adaptações frágeis.** Hoje, para fugir do torch, você depende de portes como o ctranslate2 e o onnxruntime. Eles são ótimos, mas nem todo modelo tem uma versão "traduzida" — e quando tem, costuma ficar **atrás da versão original** em recursos. Com torch, você usa sempre a versão de referência, a primeira a receber melhorias.

**Aproveitar a GPU para mais coisas.** Hoje só a transcrição usa a sua placa de vídeo. Com torch, imagem, áudio e outras tarefas também poderiam usá-la — *quando* couberem nos 2 GB (esse "quando" é o problema, vide seção 9).

**Padronização.** Tudo passaria a falar a mesma língua. Menos motores diferentes (ctranslate2, onnxruntime, etc.) convivendo no mesmo programa significa, em tese, menos peças para manter funcionando juntas.

---

## 6. Desvantagens de adotar o torch

**Peso brutal de instalação.** A versão do PyTorch com suporte a GPU NVIDIA ocupa, **só ela**, cerca de **2,3 GB**, e a instalação completa (com as bibliotecas-irmãs e as peças de CUDA embutidas) chega a **5–6 GB de disco**. Para efeito de comparação, hoje o seu programa inteiro é uma fração disso. É como decidir guardar um trator na garagem de casa: ele cabe, mas toma o espaço de quase tudo.

**Fim da "leveza" como princípio.** O seu `CLAUDE.md` repete que a leveza é uma **decisão consciente** (até evita Node/Deno por isso). O torch vai na direção contrária. Você perderia uma das características de identidade do projeto.

**Complexidade do "inferno de versões".** Esta é real e é citada nas próprias discussões oficiais do PyTorch: a combinação certa de **versão do torch + versão do CUDA + versão do driver da NVIDIA + arquitetura da placa** é notoriamente chata de acertar. Errar uma peça resulta em "a GPU não foi detectada" ou travamentos. É um tipo de dor de cabeça que o seu projeto hoje **não tem**.

**Mais coisas para dar errado.** Cada peça nova é uma peça que pode quebrar numa atualização. Hoje seu conjunto é enxuto e previsível.

**Risco específico já documentado na sua máquina.** O seu próprio `CLAUDE.md` registra que o Flet (a interface) e o Whisper já **brigam pela MX150** e isso pode causar a temida tela azul `WIN32K_POWER_WATCHDOG_TIMEOUT`. Colocar **mais** tarefas torch disputando a mesma placa de 2 GB tende a **piorar** esse conflito, não melhorar.

---

## 7. Ganhos de eficiência (onde você ganharia)

Vou ser honesto e específico, porque "IA é mais rápido com GPU" é verdade pela metade no seu caso.

**Onde há ganho real:** tarefas que hoje rodam na CPU e que *cabem* na sua placa de 2 GB poderiam acelerar bastante na GPU. Limpeza de ruído por rede neural, descrição de imagem, alguns tipos de OCR — se couberem nos 2 GB, sairiam de "lento na CPU" para "rápido na GPU".

**O ganho mais importante não é de velocidade, é de qualidade e capacidade.** Um denoise por IA (DeepFilterNet) limpa muito melhor que o método estatístico atual. Uma transcrição com diarização te diz **quem** falou. Isso não é "fazer mais rápido o que já faz" — é **fazer coisas que hoje não tem como fazer**. Esse é o verdadeiro prêmio do torch.

---

## 8. Perdas de eficiência (os custos escondidos)

**Partida mais lenta e mais memória RAM.** Carregar a oficina torch demora alguns segundos e consome RAM extra toda vez. Para um programa de desktop que você abre e fecha, isso incomoda.

**Paradoxo da transcrição: o torch pode ser PIOR para o seu caso.** Este ponto é contraintuitivo e importante. O seu faster-whisper atual usa um truque chamado **int8** (números "arredondados" que ocupam pouca memória) — por isso um modelo Whisper "médio" cabe nos seus 2 GB. A versão do Whisper baseada em torch, na sua placa, rodaria em **fp32** (números "cheios", de alta precisão), porque a sua MX150 é da geração **Pascal**, que **não acelera bem o fp16** (o formato intermediário que economizaria memória). Resultado: **a mesma transcrição ocuparia mais memória de vídeo e poderia nem caber.** Ou seja, no quesito transcrição, o seu stack torch-free de hoje é provavelmente **melhor** para esta máquina específica do que o caminho torch seria.

**Disco e backups maiores, atualizações mais demoradas.** Cada `pip install` ou atualização passa a mexer com gigabytes.

---

## 9. O uso da CPU (e da GPU): o nó da sua máquina

Esta é a seção que mais importa para você, porque a sua máquina tem um **gargalo muito claro**.

### A sua máquina, traduzida

- **CPU i5-8265U (4 núcleos):** um "escritório de 4 gênios" modesto. Dá conta de muita coisa, mas tarefas de IA pesada na CPU são lentas — minutos onde a GPU levaria segundos.
- **RAM 16 GB:** confortável. Não é aqui o problema.
- **GPU MX150 com 2 GB:** aqui está o **gargalo**. 2 GB de memória de vídeo é **muito pouco** para os padrões da IA moderna. É um "galpão de estagiários", mas um galpão **minúsculo**: cabem poucos estagiários trabalhando, e modelos grandes simplesmente **não entram pela porta**.

### Por que 2 GB muda tudo

Pense na memória da placa (VRAM) como o **tamanho da bancada de trabalho**. Não importa quão rápidos sejam os estagiários: se a peça que eles precisam montar não cabe na bancada, o trabalho **não acontece** — o programa dá erro de "memória insuficiente" e para.

Um exemplo concreto e verificado: o **Demucs** (separador de voz/instrumentos, uma das features mais legais que o torch traria) pede **no mínimo ~3 GB** de VRAM e usa **~7 GB** no modo padrão. Na sua placa de 2 GB, ele só roda com **truques de economia** (processar o áudio em pedacinhos, desligar o cache de memória) — e mesmo assim **mais devagar** e com **qualidade um pouco pior**. Funciona "no susto", não com folga.

### A consequência prática

Na sua máquina, boa parte do que o torch promete cairia em uma de três caixas:

1. **Não cabe na GPU** → teria que rodar na CPU (lento) ou nem rodar.
2. **Cabe com truques** → roda, mas devagar e brigando por memória.
3. **Cabe bem** → modelos pequenos; aqui o torch realmente brilharia.

E há o agravante da disputa: como o seu `CLAUDE.md` já documenta, a **interface gráfica e a transcrição já competem pela MX150**, com risco de tela azul. Empilhar mais tarefas torch na mesma placa de 2 GB é pedir para esse conflito acontecer mais vezes.

> **Tradução honesta:** o torch foi feito pensando em galpões grandes (placas de 8, 12, 24 GB). A sua máquina é uma exceção difícil — e é exatamente o tipo de máquina para a qual a escolha "torch-free" faz mais sentido.

---

## 10. Quais novas features o programa poderia ter

Aqui está o lado animador. Se o torch entrasse, estes recursos passariam a ser possíveis. Organizei por módulo, com uma nota realista de viabilidade na **sua** placa de 2 GB.

| Módulo | Nova feature | O que faz (em linguagem simples) | Cabe nos 2 GB? |
|---|---|---|---|
| Transcrição | **Diarização ("quem falou")** | Marca cada trecho com "Pessoa 1", "Pessoa 2"… numa reunião ou entrevista | Parcialmente — o modelo de diarização é leve; alterna com o Whisper na GPU |
| Transcrição | **Legenda palavra-por-palavra** (WhisperX) | Timestamps exatos de **cada palavra**, não só da frase — legendas que acendem palavra a palavra | Parcialmente — a etapa de alinhamento é mais pesada |
| Áudio | **Separação de faixas** (Demucs) | Separa voz, bateria, baixo e "resto" de uma música ou pista | No limite — só com truques, devagar |
| Áudio | **Denoise neural** (DeepFilterNet) | Limpeza de ruído por IA, muito superior ao método atual; remove chiado/ventilador mantendo a voz natural | Sim — é notavelmente leve, roda até em CPU em tempo real |
| Imagens | **Ampliação inteligente** (Real-ESRGAN) | Aumenta o tamanho de fotos pequenas **inventando detalhes plausíveis**, sem borrar | No limite — depende do tamanho da imagem |
| Imagens | **Restauração de rostos** (GFPGAN) | Recupera rostos borrados/antigos em fotos de baixa qualidade | No limite |
| Imagens | **Remoção de fundo melhor** | Modelos mais novos que o atual, bordas mais limpas (cabelo, pelos) | Sim — modelos de segmentação são leves |
| Documentos | **OCR por deep learning** (EasyOCR/TrOCR) | Lê texto de imagens/PDFs escaneados com mais precisão que o Tesseract atual, inclusive manuscritos | Parcialmente |
| IA / RAG | **Embeddings e reranking locais** (sentence-transformers) | Busca semântica mais precisa nos seus documentos, e um "segundo juiz" que reordena os melhores trechos antes de responder | Sim, em modelos pequenos — **mas você já resolve isso via Ollama sem torch** |
| Vídeo | **Upscale / interpolação** | Aumentar resolução de vídeo ou criar quadros intermediários (câmera lenta suave) | Não — pesado demais para 2 GB |

**Os destaques realistas para a sua máquina** seriam três: **diarização** ("quem falou"), **legendas palavra-por-palavra** e o **denoise neural (DeepFilterNet)** — porque são os que de fato cabem e entregam algo que você não tem hoje. O resto ou não cabe, ou você já resolve por outro caminho.

---

## 11. Como tudo isso seria adaptado ao seu programa

Boa notícia: a sua arquitetura **já está preparada** para receber o torch de um jeito disciplinado, sem destruir a leveza onde ela importa. O seu `CLAUDE.md` inclusive já antecipa isso com o extra planejado `[ai-audio]`. O padrão seria este:

**1. Torch entra como "extra" opcional, nunca obrigatório.** Em vez de todo mundo baixar 6 GB, só quem quiser as features pesadas instalaria com algo como `[ai-audio]`, `[ai-image]`. O programa base continua leve. É como uma loja de móveis que monta sob encomenda: a entrega básica é rápida, e o "sofá-cama com massagem" só vem se você pedir (e pagar o frete maior).

**2. Carregamento preguiçoso ("lazy import").** A oficina torch só é "ligada" no instante em que você clica no recurso que precisa dela — nunca na abertura do programa. Assim, abrir o `mill.tools` continua rápido. Você **já faz exatamente isso** com o rembg, então o padrão é conhecido.

**3. "Portão" de disponibilidade (gate).** Cada card de feature pesada checaria, no momento de aparecer, se o torch e a placa estão prontos. Se não estiverem, o botão fica **desabilitado com uma dica** ("instale o extra `[ai-audio]`") — exatamente como o seu OCR/Tesseract e o rembg já se comportam hoje. Nada quebra; o recurso só fica indisponível com explicação clara.

**4. O núcleo puro (`src/core/`) continua sem Flet e sem torch onde der.** As funções torch ficariam **isoladas em arquivos próprios** (ex.: `core/audio/separation.py`), do mesmo jeito que o `background.py` isola o rembg hoje. O resto do programa nem fica sabendo que o torch existe.

**5. "Fixar" a versão certa do CUDA — passo obrigatório na sua placa.** Aqui um detalhe técnico crítico, com uma nuance importante. A sua MX150 é da arquitetura **Pascal**. A placa **não foi banida**: ela continua recebendo drivers, e programas que embarcam código "PTX" ainda *rodam* nela via compilação na hora (PTX-JIT) — inclusive sob um driver que reporta "CUDA 13" no `nvidia-smi`. O que mudou é outra coisa: o **CUDA Toolkit 13.0 removeu o suporte *nativo* ao Pascal** — ou seja, o compilador e as bibliotecas (cuFFT, cuSPARSE, etc.) deixaram de gerar código sob medida para a sua placa (o Toolkit 13 cobre de Turing em diante). Na prática, para o PyTorch isso significa **travar nos pacotes de CUDA 12.x** (especificamente o `cu126` ainda traz o Pascal; os pacotes de `cu128`/`cu129`/CUDA 13 já largaram). O Pascal está marcado como "completo, sem novas melhorias": **funciona, mas é fim de linha**. Uma placa nova mudaria isso; enquanto for a MX150, fique nessa faixa de versões.

**6. Manter o "CPU-pinning" como já se faz com o Ollama.** Para features torch que **não** caibam na GPU, você as forçaria a rodar na CPU de propósito (mais lento, porém estável e sem brigar pela placa) — exatamente a filosofia que você já aplica nos modelos do Ollama (`num_gpu 0`). Isso preserva a estabilidade contra a tela azul.

Em resumo: a adaptação seria **cirúrgica e opcional**, encaixando-se nos padrões que o seu projeto já usa. O torch entraria "pela porta dos fundos", só quando chamado.

---

## 12. Os custos concretos, na SUA máquina

Juntando tudo, em números:

- **Disco:** +2,3 GB só do torch; **5–6 GB** com os complementos. Os modelos de IA (Demucs, Real-ESRGAN, etc.) somam mais alguns GB cada.
- **Memória de vídeo (VRAM):** o teto de **2 GB** é o muro. Várias features só rodam com truques e lentidão; outras não rodam.
- **Estabilidade:** risco aumentado da tela azul `WIN32K_POWER_WATCHDOG_TIMEOUT`, que você já enfrenta, por causa da disputa pela MX150.
- **Térmico:** o seu Inspiron já gerencia calor agressivamente (~63–65 °C). Tarefas torch prolongadas na GPU geram mais calor e podem provocar mais "throttling" (a máquina se desacelera para não fritar).
- **Manutenção:** entra o "inferno de versões" torch+CUDA+driver, que hoje você não tem.

---

## 13. Existe um meio-termo? (Sim — e você já está nele)

A pergunta não precisa ser "torch ou nada". Existe um caminho do meio, e é justamente o que o seu projeto já pratica: o **ONNX Runtime** (que o seu rembg usa) e os **modelos recompactados** (como o ctranslate2 do faster-whisper).

A ideia: pega-se um modelo treinado em torch, **converte-se para um formato enxuto** (ONNX) e roda-se esse formato com um motor leve, **sem instalar a oficina torch inteira**. É como receber um móvel **já montado e desmontável** em vez de receber a marcenaria completa para fabricá-lo em casa. Você fica com o resultado, sem o peso da fábrica.

Boa parte das features da seção 10 — denoise neural, OCR melhor, embeddings, remoção de fundo aprimorada — **tem versão ONNX** e poderia chegar ao seu programa **sem quebrar o torch-free**. As que *só* existem em torch (Demucs, alguns alinhamentos) é que exigiriam a oficina completa.

> Em outras palavras: você pode capturar talvez **70–80% do prêmio** mantendo a leveza, e reservar o torch só para o punhado de recursos que não têm alternativa — e, mesmo esses, só se couberem nos 2 GB.

---

## 14. Veredito

Para a sua máquina e a sua filosofia de projeto, em junho de 2026:

**Adotar o torch como base seria um mau negócio.** O custo (peso, complexidade, fim de linha do Pascal, briga pela placa de 2 GB) é alto, e a maior promessa — velocidade via GPU — é justamente o que a sua placa **não** entrega com folga. No caso emblemático da transcrição, o torch seria até **pior** que o seu stack atual.

**Mas vale tratar o torch como um "extra opcional" para features específicas.** Diarização ("quem falou"), legendas palavra-por-palavra e denoise neural são prêmios reais que cabem na sua máquina e que você não consegue de outro jeito. Encaixados como extra opcional, com lazy import e gate — exatamente o padrão que você já domina — eles agregariam muito **sem** comprometer o programa base.

**O movimento mais inteligente primeiro:** esgotar o caminho **ONNX Runtime** (que já é torch-free e que você já usa). Veja quantas das features novas você consegue por ali antes de trazer a oficina pesada para dentro de casa. O torch fica reservado para o que realmente não tem substituto leve — e idealmente para o dia em que houver uma placa com mais de 2 GB na jogada.

---

## 15. Glossário rápido

- **PyTorch / torch:** a "oficina" de software mais usada para construir e operar IA. Pesada e poderosa.
- **torch-free:** projeto que faz IA **sem** instalar essa oficina, usando alternativas mais leves.
- **Tensor:** uma tabela de números (como uma planilha multidimensional); a peça básica que a IA manipula.
- **Autograd:** o mecanismo do torch que permite uma IA **aprender** com os próprios erros.
- **CPU:** processador principal; poucos "trabalhadores" muito inteligentes (o seu i5).
- **GPU:** placa de vídeo; milhares de "trabalhadores" simples e simultâneos (a sua MX150).
- **VRAM:** a memória **dentro** da placa de vídeo; a "bancada de trabalho". A sua tem só 2 GB — o gargalo.
- **CUDA:** o idioma das placas NVIDIA para receber ordens de cálculo pesado.
- **Pascal:** a geração da sua placa MX150. Continua recebendo drivers e ainda *roda* programas via PTX-JIT, mas o **CUDA Toolkit 13.0 removeu o suporte nativo** (compilador e bibliotecas) ao Pascal. Para o PyTorch, na prática isso significa ficar nos pacotes de **CUDA 12.x** (o `cu126`); os de CUDA 12.8+/13 já largaram o Pascal.
- **fp16 / fp32 / int8:** formatos de número, do "cheio e preciso" (fp32, gasta memória) ao "arredondado e econômico" (int8, cabe na sua placa). O seu faster-whisper usa int8 — por isso é tão eficiente na MX150.
- **Diarização:** descobrir **quem** falou em cada trecho de um áudio.
- **ONNX Runtime:** motor leve que roda modelos de IA já "recompactados", sem a oficina torch inteira — o seu meio-termo.

---

## Fontes

- [Delete support for Maxwell, Pascal, and Volta architectures for CUDA 12.8/12.9 — pytorch/pytorch #157517](https://github.com/pytorch/pytorch/issues/157517)
- [GPU compute capability support for each PyTorch version — PyTorch Forums](https://discuss.pytorch.org/t/gpu-compute-capability-support-for-each-pytorch-version/62434)
- [CUDA & PyTorch Compatibility by Compute Capability — LLM Laboratory](https://llmlaba.com/articles/cuda-pytorch-compatibility.html)
- [WhisperX: Automatic Speech Recognition with Word-level Timestamps (& Diarization) — m-bain/whisperX](https://github.com/m-bain/whisperX)
- [Pytorch install is that large? 5 Gbs? — PyTorch Forums](https://discuss.pytorch.org/t/pytorch-install-is-that-large-5-gbs/213629)
- [Why torch wheel is so huge (582MB)? — pytorch/pytorch #17621](https://github.com/pytorch/pytorch/issues/17621)
- [Environment Setup — facebookresearch/demucs (DeepWiki)](https://deepwiki.com/facebookresearch/demucs/2.1-environment-setup)
- [demucs — PyPI](https://pypi.org/project/demucs/)
