# Revisão espaçada — banco de quizzes cumulativos

O maior inimigo de um estudo longo, arquivo por arquivo, é o **esquecimento**: quando você chega na
Sessão 5, a Sessão 1 já apagou. Este arquivo combate isso com **quizzes cumulativos**: cada quiz
mistura a sessão recém-concluída com as anteriores, embaralhadas — porque relembrar *misturado* (o
nome técnico é *interleaving*) fixa muito mais do que reler.

## Como usar

1. **Terminou uma sessão?** Faça o quiz dela **no dia seguinte** (D+1), sem consultar nada.
2. Refaça o mesmo quiz em **D+7** e **D+30**. Errou uma pergunta? Releia só a seção correspondente,
   não o doc inteiro.
3. Responda **por escrito ou em voz alta** — reconhecer a resposta no gabarito não é o mesmo que
   produzi-la.
4. O **Quiz Final** é para depois do `PRINCIPIOS.md`, e vale repetir a cada 2-3 meses como
   manutenção.

> Formatos usados: pergunta direta · **[e se]** previsão de consequência · **[V/F]** julgue e
> justifique (a justificativa é o que vale) · **[bug]** diagnóstico por sintoma.

---

# Quiz 1 — após a Sessão 1 (a espinha)

1. Qual é a diferença entre o que o **stdout** e o **stderr** do ffmpeg carregam no `run_ffmpeg`, e
   por que os dois precisam ser lidos **ao mesmo tempo**?
2. **[V/F]** "O `run_ffmpeg` confia no returncode: se o ffmpeg devolveu 0, a conversão deu certo."
3. Para que serve o `*` sozinho no meio da assinatura de `run_ffmpeg`?
4. **[e se]** Você chama `sanitize_filename("AULA 03: intro | parte 1")`. Descreva (aproximadamente)
   o resultado e cite duas regras que agiram.
5. Por que `check_dependencies` roda no **início** do app, e o que `shutil.which` faz?
6. O que o `TqdmLoggingHandler` evita, concretamente, na tela do terminal?
7. No `llm_factory`, o que decide se um nome de modelo vai para Gemini, GLM ou Ollama?
8. **[e se]** Você chama `make_llm("gemini-2.5-flash")` numa máquina sem `.env`. O que acontece, e
   em que momento?
9. Por que `time.monotonic()` (e não `time.time()`) no `_TimingCallback`?
10. **[bug]** Um comando de CLI novo demora 4s só para *começar* — mesmo quando o usuário só pediu
    `--help`. Qual anti-padrão da espinha provavelmente foi cometido?

<details>
<summary><b>Gabarito — Quiz 1</b></summary>

1. stdout carrega o **progresso** (`out_time_us=...`, graças ao `-progress pipe:1`); stderr carrega
   **logs/erros**. Se só um for lido, o buffer do outro enche, o ffmpeg para de escrever e os dois
   lados travam esperando — deadlock. A thread `_drain` lê o stderr em paralelo.
2. **Falso.** Ele valida returncode **e** existência do arquivo de saída — o ffmpeg às vezes retorna
   0 sem gerar saída. Dois erros de tipos diferentes para o chamador distinguir.
3. Torna todos os parâmetros seguintes **keyword-only**: só podem ser passados por nome
   (`progress_cb=...`), evitando erros de posição e forçando clareza no chamador.
4. Algo como `AULA_03-_intro-parte_1` → na prática: `:` vira hífen (regra do ADS/NTFS), `|` vira
   hífen (separador visual), espaços viram `_`, repetições colapsam, pontas são limpas. (O
   importante: dois-pontos→hífen e espaços→underscore.)
5. Para **falhar cedo com mensagem útil** (o que instalar, onde), em vez de quebrar cripticamente no
   meio de um download. `shutil.which` procura o executável no PATH do sistema.
6. Que uma linha de log "rasgue" a barra de progresso do tqdm (barras duplicadas, linhas
   embaralhadas): ele escreve via `tqdm.write`, que apaga, escreve e redesenha a barra.
7. O **prefixo do nome**: `gemini*` → Google, `glm*` → Zhipu, qualquer outro → Ollama local
   (fallback).
8. `_make_gemini` chama `_load_env_once`, não encontra `GOOGLE_API_KEY` e levanta `RuntimeError`
   **imediatamente**, com instrução de criar o `.env` — antes de qualquer chamada de rede.
9. Porque `monotonic` só avança — imune a ajuste de relógio/fuso/sincronização. Para medir
   **duração**, `time.time()` pode literalmente voltar no tempo.
10. Import pesado no **topo do arquivo** em vez de preguiçoso (dentro da função que o usa). O padrão
    da espinha: LangChain e afins só carregam quando o recurso é de fato acionado.

</details>

---

# Quiz 2 — após a Sessão 2 (fatia vertical + testes/CLI/GUI)

*Mistura: ~6 da Sessão 2 + 4 da Sessão 1.*

1. Desenhe (de memória) o caminho de `uv run main.py video convert filme.mkv --codec h264` até o
   processo ffmpeg: cite as 4 camadas e o que cada uma faz.
2. Por que a CLI pode importar `run_video_pipeline` de `gui/modules/video/worker.py` sem violar a
   arquitetura?
3. **[V/F]** "No pytest, deve-se fazer o patch no módulo onde a função foi definida."
4. O que o padrão AAA significa, e por que o Act deve ter **uma** ação?
5. **[e se]** Um teste precisa modificar um arquivo da fixture `sample_wav` (escopo `session`). O que
   ele deve fazer antes, e que classe de bug isso evita?
6. Qual a diferença entre um argumento **posicional** e uma **opção** no argparse — e o que
   `set_defaults(func=...)` elimina no `main.py`?
7. *(S1)* Por que o `subprocess` do projeto roda sempre em modo binário?
8. *(S1)* O que é o padrão Factory, na frase mais curta que você conseguir?
9. **[bug]** Um teste unitário do módulo Áudio às vezes passa, às vezes falha — só quando roda a
   suíte inteira, nunca isolado. Cite as duas causas mais prováveis e o plugin que expõe isso.
10. *(S1)* Quem se beneficia das constantes de diretório centralizadas em `utils.py`? Dois exemplos.

<details>
<summary><b>Gabarito — Quiz 2</b></summary>

1. `main.py` despacha (`ns.func`) → `cli/video.py::run_video_cli` traduz `Namespace` → `VideoArgs` e
   cria o `CLIEventBus` → `gui/modules/video/worker.py::run_video_pipeline` (Flet-free) roda a fila e
   o `_process_item` emite eventos → `core/video/converter.py::convert_video` monta o cmd
   (`VCODEC_MAP`) → `core/ffmpeg.py::run_ffmpeg` executa o processo.
2. Porque o worker é **Flet-free**: só orquestra e emite eventos pelo bus injetado — nenhum controle
   de UI. O que é GUI-only mora na `view.py`.
3. **Falso.** Patch **onde é usado** (ex.: `src.core.audio.converter.run_ffmpeg`): o `from ... import`
   criou uma referência local no módulo consumidor, e é ela que o código sob teste enxerga.
4. Arrange (preparar o cenário), Act (executar **a** ação), Assert (verificar). Uma ação só: se o
   teste falha, você sabe exatamente qual comportamento quebrou.
5. Copiar primeiro para o seu `tmp_path` (`shutil.copy`). Evita contaminar a fixture compartilhada e
   criar *flaky tests* — testes que falham dependendo da ordem de execução.
6. Posicional: identificado pela **ordem**, sem `--`, geralmente obrigatório (o *o quê*). Opção:
   nomeada com `--`, ordem livre, geralmente com default (o *como*). `set_defaults(func=...)` elimina
   o `if/elif` central de despacho: `ns.func(ns)` chama a função certa.
7. Porque `text=True` herda o cp1252 do console Windows → `UnicodeDecodeError` com acentos. Bytes +
   `.decode("utf-8", errors="replace")` nunca quebram (regra nº 5).
8. Uma função que constrói e devolve o objeto certo para a situação, escondendo do chamador **qual
   classe** foi instanciada.
9. Estado vazando entre testes (fixture larga modificada, arquivo em caminho fixo, global) ou
   dependência de ordem. O `pytest-randomly` (ordem aleatória) expõe; `pytest-xdist` (paralelismo)
   expõe colisões de recurso.
10. A **Biblioteca** (o scanner sabe onde varrer) e o **RAG** (sabe onde indexar) — além de qualquer
    reestruturação de pastas virar uma edição única.

</details>

---

# Quiz 3 — após a Sessão 3 (contrato de eventos)

*Mistura: ~6 da Sessão 3 + 4 das Sessões 1–2.*

1. Cite os 4 campos do `PipelineEvent` e o papel de cada um.
2. Por que a thread daemon pode chamar `bus.emit(...)` mas **não** pode chamar
   `controle.update()`?
3. Quais eventos vêm do **runner genérico** e quais vêm do `_process_item` do módulo? (3 de cada)
4. **[e se]** Dois pipelines de módulos diferentes rodassem "ao mesmo tempo" e emitissem eventos.
   O que impede os painéis de misturarem as mensagens?
5. Como uma mensagem `logging.info(...)` do core puro chega ao painel da GUI, se o core não conhece
   o bus?
6. **[V/F]** "O `_LogScope` existe por elegância; sem ele, tudo funcionaria igual."
7. *(S2)* Qual é a assinatura comum que `EventBus` e `CLIEventBus` compartilham, e o que ela
   permite?
8. *(S1)* Na cadeia `run_ffmpeg → progress_cb → emit → barra`, quem conhece quem? Aponte a direção
   das dependências.
9. **[bug]** O spinner do moinho fica **parado** durante um pipeline, mas o log anda. Cite as duas
   causas clássicas da regra de ouro.
10. *(S2)* Por que o cancelamento (Esc) só age **entre** itens da fila?

<details>
<summary><b>Gabarito — Quiz 3</b></summary>

1. `type` (o que aconteceu), `stage` (contexto textual), `payload` (os dados, ex.:
   `{"current": 0.4}`), `module_id` (quem emitiu — a base do escopo).
2. `pubsub.send_all` é **thread-safe** (só publica dados num canal); `update()` de thread daemon não
   repinta no Flet 0.85 — a UI só pode ser tocada pela thread dela.
3. Runner: `progress_start`, `queue_progress`, `task_done` (e `task_error`). Módulo:
   `<mod>_op_start`, `<mod>_op_done`, `log`/`progress_update` do trabalho em si.
4. O escopo: cada painel foi criado com um `owner_id` e ignora eventos cujo `module_id` seja
   diferente. O `make_emitter` garante que todo evento sai carimbado.
5. Pela ponte `LogEventHandler`: durante o pipeline, o `_LogScope` o instala no root logger; cada
   record é convertido num evento `"log"` no bus (suprimindo os prefixos já cobertos por eventos
   estruturais).
6. **Falso.** Sem o context manager, o handler nunca seria removido: a cada execução um novo se
   acumularia e as mensagens apareceriam 2×, 3×, 4×... O `__exit__` remove **sempre**, mesmo com
   exceção.
7. `emit(type, stage, payload, module_id)`. Permite o mesmo worker servir GUI e CLI sem um único
   `if borda == "gui"` — cada bus traduz os eventos para seu contexto.
8. O de baixo nunca conhece o de cima: `run_ffmpeg` só conhece o callback recebido; o worker conhece
   o core (chama) e o bus (injetado); a view conhece o worker. As dependências apontam **para
   baixo**; a informação sobe por callbacks/eventos.
9. (1) `start()` chamado **antes** do `page.update()` que exibiu o container — a 1ª rotação foi para
   um controle oculto e a cadeia de `on_animation_end` morreu. (2) Um `page.update()` **global**
   durante o giro interrompeu a animação (por isso repintura escopada).
10. Porque o runner checa `cancel_event.is_set()` no topo de cada volta do laço da fila — um item em
    andamento (um ffmpeg rodando) termina; o corte é no próximo seam seguro.

</details>

---

# Quiz 4 — após a Sessão 4 (módulos como variações)

*Mistura: ~8 da Sessão 4 + 4 das anteriores.*

1. Complete a tabela de memória: qual biblioteca cada core embrulha e se é externa ou em-processo —
   Áudio, Vídeo, Imagem, Documentos, Dados.
2. Por que o worker do Imagem **não** emite `progress_update` contínuo, e o do Áudio emite vários por
   item?
3. O que é o OCR **híbrido** do Documentos, em uma frase?
4. No Dados, o que a IA do `nl2sql` recebe e o que ela **nunca** recebe?
5. **[e se]** O `ensure_select` deixasse passar um `COPY (SELECT ...) TO 'x.csv'`. Qual promessa do
   módulo seria quebrada, mesmo com a conexão read-only?
6. Cite os **três** modos de concorrência do projeto e um exemplo de uso certo de cada.
7. Por que a Biblioteca não tem worker, e o que isso prova sobre a definição de "módulo"?
8. Qual estágio do Áudio "conserta" a saída do denoise, e por quê?
9. *(S3)* Um bloco de formulário expõe `set_disabled`. Quem o chama, e em que momento?
10. *(S2)* Por que os testes de Dados/Documentos/Imagem usam DuckDB/pymupdf/Pillow **reais** e ainda
    são `unit`?
11. **[bug]** Após um refactor, o burn-in de legenda quebra com erro do filtro `subtitles` — só no
    Windows, só com caminho absoluto. Qual é o quirk, e qual é a solução do projeto?
12. *(S1)* A Transcrição usa `make_llm` para Formatter/Analyzer/Prompter. O que o usuário troca para
    a análise rodar na nuvem em vez de local?

<details>
<summary><b>Gabarito — Quiz 4</b></summary>

1. Áudio → ffmpeg (**externa**, subprocesso); Vídeo → ffmpeg + yt-dlp (**externa**); Imagem → Pillow
   (**em-processo**); Documentos → pymupdf (**em-processo**); Dados → DuckDB (**em-processo**,
   injetável).
2. Pillow é rápido e síncrono — sem processo externo não há fluxo de progresso; o worker emite só
   `op_start`/`op_done`. No Áudio, cada item passa por uma **cadeia** de estágios ffmpeg, cada um com
   seu progresso.
3. Por página: usa a camada de texto nativa se existir; rasteriza + Tesseract só nas páginas
   escaneadas.
4. Recebe **só o schema** (nomes/tipos de coluna) e devolve `(sql, explicação)`; **nunca** vê uma
   linha de dados.
5. "Só leitura" de verdade: um `COPY ... TO` **escreve no disco** mesmo em conexão read-only. O
   `ensure_select` (permissão + proibição) é a primeira linha de defesa.
6. **Thread daemon + eventos** (pipelines longos com processo externo: Vídeo/Áudio);
   **`page.run_task` + `asyncio.to_thread`** (trabalho Python pesado numa aba: DuckDB/LLM no Dados);
   **síncrono direto** (operações rápidas em-processo: uma transform do Imagem dentro do worker).
7. Porque ela é read-only: só navega/abre o que existe sob `output/`. Prova que módulo = entrada em
   `MODULES` com `control` e ganchos — não implica pipeline.
8. O **encode final**: o denoise sempre gera `.wav`; o encode aplica `fmt` + mono + sample-rate de
   uma vez, garantindo que o pedido do usuário seja honrado.
9. O builder principal do formulário, em **todos** os blocos de uma vez, quando o pipeline parte
   (congela o form) e quando termina (descongela).
10. São dependências **hard e in-process** (sempre presentes, sem rede/GPU/processo externo): rodar
    real é rápido, determinístico e exercita o comportamento verdadeiro.
11. O filtro `subtitles=` interpreta `:` como separador → o `:` do drive (`C:`) quebra o parser.
    Solução: rodar o ffmpeg com `cwd=` na pasta da legenda e referenciá-la por **basename** (o
    parâmetro `cwd` do `run_ffmpeg` existe para isso).
12. Só a **string do modelo** (ex.: `gemini-2.5-flash` no lugar do modelo Ollama): o roteamento por
    prefixo do `make_llm` faz o resto.

</details>

---

# Quiz 5 — após a Sessão 5 (RAG / ML / hubs)

*Mistura: ~8 da Sessão 5 + 4 das anteriores.*

1. Explique **similaridade de cosseno** para um leigo em até 3 frases (vale usar a analogia das
   bússolas ou das setas).
2. Por que, depois da normalização L2, "medir cosseno" vira só um produto escalar?
3. Qual é a fraqueza da busca **densa** e como o **BM25** a cobre? Dê um exemplo de pergunta em que o
   BM25 salva o resultado.
4. Por que o RRF funde os rankings por **posição** e não somando os scores?
5. O que o MMR evita no contexto final, e qual característica do **chunking** cria esse problema?
6. O que significa o aviso de cobertura (limiar 0.72), e por que o limiar é **calibrado** e não
   fixo universal?
7. O que é **mean-pooling**, e para que o ML clássico o usa?
8. HDBSCAN vs. k-means: qual descobre o número de grupos sozinho, e o que o outro exige?
9. **[e se]** Você troca o modelo de embedding e **não** reindexa (ou reindexa sem `force` após
   mudança de esquema). Cite dois estragos silenciosos.
10. *(S4)* Por que a reindexação mora no Observatório e não no hub IA?
11. *(S3)* O harness de Avaliação roda com `module_id="observatory"`. O que isso garante na GUI?
12. *(S1)* A condensação multiturno roda sempre com LLM local. Que princípio transversal do projeto
    isso materializa, e onde mais você o viu?

<details>
<summary><b>Gabarito — Quiz 5</b></summary>

1. Exemplo: "Cada texto vira uma seta apontando numa direção que representa o assunto. Para saber se
   dois textos falam da mesma coisa, comparamos só a **direção** das setas, não o tamanho. Setas
   paralelas = mesmo assunto; em ângulo reto = nada a ver."
2. Porque a fórmula do cosseno divide o produto escalar pelos comprimentos — e vetores normalizados
   têm comprimento 1, então a divisão desaparece: `cos = a·b`.
3. Densa é fraca em **termos exatos** (nomes próprios, siglas, códigos). O BM25 casa palavras-chave,
   com termos raros valendo mais (IDF). Ex.: "o que é RRF?" ou "WinError 32" — o pedaço com o termo
   literal é resgatado mesmo sem proximidade semântica forte.
4. Porque as escalas são incompatíveis (cosseno em `[-1,1]`, BM25 ilimitado) — somar deixaria o BM25
   dominar. Posições no pódio (`1/(k+rank)`) são comparáveis por construção (os dois jurados).
5. Quase-duplicatas: pedaços vizinhos compartilham 150 chars de overlap e são "irmãos". Sem MMR, os
   k lugares do contexto podem virar 3 fatias do mesmo parágrafo; o MMR penaliza redundância
   (`λ·relevância − (1−λ)·redundância`).
6. Se nem o **melhor** pedaço do acervo passa de 0.72 de cosseno com a pergunta, ela provavelmente
   está fora do corpus — a GUI avisa antes de o modelo inventar. O valor depende do **modelo de
   embedding** (cada espaço tem outra geometria), por isso foi calibrado com perguntas
   dentro/fora reais e é parâmetro.
7. A média dos vetores dos pedaços de um documento → um vetor-resumo por documento (normalizado
   depois). É a entrada de quase todo o ML clássico: clustering, mapa 2D, relacionados, classify.
8. HDBSCAN descobre sozinho (densidade; marca ruído com `-1`). k-means exige o `k` de antemão (ou a
   auto-seleção via silhouette, com corpus suficiente).
9. (1) Caches/modelos chaveados pelo espaço antigo continuariam "válidos" e prevendo lixo — vetores
   de espaços diferentes não são comparáveis. (2) A busca compararia a pergunta (embeddada no espaço
   novo) contra chunks do espaço antigo — resultados sem sentido, sem nenhum erro visível. (As
   assinaturas com `embed_space_id` e o `force` existem para isso.)
10. Porque é um **pipeline de escrita** (progresso/cancelamento/worker) e o hub IA é read-only sobre
    o índice — separação "quem lê vs. quem escreve"; o hub só navega para lá via bridge.
11. Que o progresso/cancelar da avaliação aparece **no painel do Observatório** e não vaza para
    outros módulos — o mesmo escopo por `owner_id` de sempre.
12. **Privacidade por desenho**: minimizar o que sai da máquina. Visto também no `nl2sql` (só
    schema), nos embeddings sempre locais, no cartão de dados, e no Observatório reportando só a
    presença das chaves.

</details>

---

# Quiz Final — síntese (após `PRINCIPIOS.md`)

*Cobre tudo. Repita a cada 2-3 meses.*

1. Enuncie as **6 regras invioláveis** de memória (a ordem não importa).
2. Para cada camada, diga em uma frase o que ela **pode** e o que ela **não pode**: `core/`,
   worker, `cli/`, `view`.
3. Dê **três** exemplos do idioma "a dependência é recebida, não criada", em três níveis de
   abstração diferentes.
4. **[bug]** Sintoma: um painel mostra mensagens de log duplicadas, e o número de cópias cresce a
   cada pipeline. Diagnóstico?
5. **[bug]** Sintoma: `UnicodeDecodeError` ao processar um arquivo com "ã" no nome — só no Windows.
   Diagnóstico e regra?
6. **[bug]** Sintoma: o teste passa, mas está **lento** e exige ffmpeg instalado, embora seja
   marcado `unit`. Diagnóstico?
7. **[bug]** Sintoma: depois de reindexar com um modelo novo, o mapa semântico e o classify ficaram
   "malucos", sem nenhum erro no log. Diagnóstico?
8. **[e se]** Uma nova ferramenta (módulo de rail) chamada "Legendas" será criada. Em 6 passos, o
   roteiro completo — do core ao teste.
9. Qual é a diferença entre um **hub** e uma **ferramenta**, e por que a Biblioteca/IA/Observatório/
   Receitas são hubs?
10. **[V/F]** "O core pode importar o `EventBus` desde que só o use quando rodar na GUI."
11. Por que `temperature=0.0`, `random_state=42` e `_fix_signs` são "o mesmo princípio em três
    lugares"? Que princípio?
12. A frase-síntese do estudo: complete de memória — "A lógica pura vive no..., desacoplada por...;
    as bordas...; e um vocabulário compartilhado...".

<details>
<summary><b>Gabarito — Quiz Final</b></summary>

1. (1) `core/` é puro; (2) injeção de dependência na fronteira de rede/modelo; (3) código em inglês
   (PT só em labels/exceções user-facing); (4) logging por handler dedicado, nunca `print`; (5)
   subprocess em modo binário; (6) degradação graciosa de extras ausentes.
2. `core/`: pode toda a lógica reutilizável; não pode Flet, `print`, nem conhecer bordas. Worker:
   pode orquestrar, chamar core e `emit`; não pode tocar controle de UI. `cli/`: pode traduzir
   `Namespace`→`Args` e criar o `CLIEventBus`; não pode conter lógica de negócio. `view`: pode
   montar controles e escutar eventos; não pode conter lógica que mereça teste (extraia).
3. `progress_cb` (um número), `bus`/`emit` (um vocabulário de eventos), `embed_fn`/`make_llm`/motor
   DuckDB (rede/modelo/banco).
4. Handler de log instalado sem o `_LogScope` (ou sem remoção garantida): handlers acumulam no root
   logger a cada execução.
5. Um `subprocess` com `text=True` (ou decode implícito) herdando cp1252 do console — violação da
   regra nº 5; corrigir para modo binário + `.decode("utf-8", errors="replace")`.
6. Patch feito **onde a função é definida** (`src.core.ffmpeg.run_ffmpeg`) em vez de onde é
   **usada** — o mock é ignorado e o ffmpeg real roda.
7. Algum cache/modelo não foi invalidado pelo espaço novo (assinatura sem `embed_space_id`, ou
   reindexação que não reembeddou de verdade — o caso do `force`): vetores de espaços diferentes
   sendo comparados.
8. (1) `core/legendas/` puro (`args.py` + funções, callbacks injetáveis); (2) worker Flet-free com
   `_process_item` emitindo o contrato de eventos; (3) `cli/legendas.py` (parser +
   `run_legendas_cli`, `CLIEventBus`, `install_log_handler=False`); (4) `view.py` + `form` (blocks se
   crescer) e entrada em `MODULES`; (5) dir canônico em `utils.py` (a Biblioteca ganha o kind de
   graça); (6) testes espelhados — integração no core, unit na tradução da CLI. `uv run poe check`
   verde.
9. Ferramenta transforma **entrada→saída** (fica na rail); hub **opera sobre as saídas de todos**
   (botão dourado no AppBar): Biblioteca navega, IA conversa sobre o corpus, Observatório observa a
   maquinaria, Receitas encadeia.
10. **Falso.** Core puro não conhece borda nenhuma, nunca — nem condicionalmente. A comunicação sobe
    por callbacks injetados; quem conhece o bus é o worker.
11. **Determinismo**: mesma entrada → mesmo resultado, para o usuário nunca ver saída/mapa/partição
    "pularem" sem motivo — no LLM, no k-means/t-SNE/UMAP e no PCA, respectivamente.
12. "...no `core/`, desacoplada por **injeção de dependência**; as bordas (CLI, GUI, Receitas) **só a
    traduzem**; e um vocabulário compartilhado (Args, eventos, `is_available`) **as liga sem que
    nenhuma conheça as outras**."

</details>
