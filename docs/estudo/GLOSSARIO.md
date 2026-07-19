# Glossário — mill.tools

Termos técnicos **transversais** que aparecem no estudo, explicados do zero e com analogia. Este
arquivo cobre a base comum (Python, sistema operacional, concorrência, padrões do projeto) — termos
específicos de um assunto (GUI/Flet, CLI/argparse, testes, RAG/embeddings, ML) moram no **glossário
do próprio doc**, no fim de cada um. Organizado por categoria; dentro de cada uma, em ordem de
"quando você encontra".

---

## Python — a linguagem

**Objeto** — um "pacote" de dados que tem *atributos* (valores) e às vezes *métodos* (funções).
Em vez de andar com uma string solta, você embrulha os dados num objeto com nomes. Ex.: um
`InputItem` é um objeto com os atributos `kind` e `value`.

**Classe** — a *fôrma* de um objeto: define quais atributos ele terá. `InputItem` é a classe;
`InputItem("url", "https://...")` é *um* objeto feito com essa fôrma. Classe = planta; objeto =
casa construída a partir da planta.

**`dataclass`** — um atalho do Python (um *decorator*, veja abaixo) para criar uma classe que só
guarda dados, sem escrever código repetitivo. Você declara os campos e o Python gera o construtor
automaticamente. Alternativa "crua" seria escrever um `__init__` à mão.

**Decorator** — uma linha com `@` **em cima** de uma função ou classe que a "envolve" para
adicionar comportamento sem mexer no corpo dela. `@dataclass` em cima de `class InputItem`
transforma a classe numa dataclass. Pense num adesivo que muda o que o item faz.

**Type hint (anotação de tipo)** — a parte `: str` em `kind: str`. É uma *dica* de que aquele
campo deve ser uma string. O Python não obriga em runtime (é documentação + ajuda do editor), mas
deixa o código claro e permite ferramentas pegarem erros antes de rodar.

**`from __future__ import annotations`** — uma linha no topo do arquivo que faz o Python tratar
todas as anotações de tipo como *texto*, sem avaliá-las quando o arquivo carrega. Vantagem: pode
usar sintaxe moderna (`X | None`) e anotar tipos "pesados" sem pagar o custo de importá-los. Aparece
em quase todo arquivo do `core/`.

**Callback (função de retorno)** — uma função que você *passa como argumento* para outra função,
para que esta a chame no momento certo. Você entrega o "o que fazer quando..." e a outra função
decide "quando". Ex.: `run_ffmpeg(..., progress_cb=minha_funcao)` — o ffmpeg chama `minha_funcao`
a cada avanço. Veja a seção "Padrões" para o porquê disso ser tão importante aqui.

---

## Sistema operacional — processos e canais

**Processo** — um programa em execução, com sua própria memória, isolado dos outros. Quando o app
roda o `ffmpeg`, ele lança o ffmpeg como um processo *separado* e conversa com ele por canais.

**`subprocess`** — o módulo do Python para lançar e controlar outro processo (como o ffmpeg) de
dentro do seu programa. `subprocess.Popen(cmd)` inicia o processo e te dá canais para ler a saída
dele.

**stdin / stdout / stderr** — todo processo tem três canais padrão:
- **stdin** — entrada (o que ele *lê*).
- **stdout** — saída "normal" (o resultado). No ffmpeg, é por onde vem o progresso.
- **stderr** — saída de *erro/diagnóstico* (logs, avisos). Separada da stdout de propósito, para
  você poder distinguir resultado de mensagem.

**Pipe (cano)** — o "cano" que liga a saída de um processo ao seu programa. `stdout=subprocess.PIPE`
diz "quero ler a stdout do ffmpeg por um cano". O cano tem **tamanho limitado** (veja buffer).

**Buffer** — uma área de memória temporária de tamanho fixo onde os dados esperam para serem lidos.
O pipe é um buffer: o ffmpeg escreve de um lado, seu programa lê do outro. 🔑 **Se ninguém lê e o
buffer enche, quem escreve PARA e fica esperando espaço livre.** É a chave para entender o deadlock.

**Deadlock (impasse)** — dois lados travados esperando um ao outro para sempre. No `ffmpeg.py`:
o ffmpeg quer escrever no stderr, mas o buffer do stderr encheu e ninguém o esvazia → o ffmpeg
congela. Enquanto isso, seu programa espera mais progresso pela stdout, que nunca vem porque o
ffmpeg está congelado. Os dois esperam eternamente. **Solução:** ler os dois canais ao mesmo tempo
(uma thread para o stderr — veja abaixo).

**returncode (código de saída)** — o número que um processo devolve ao terminar. **0 = sucesso**;
qualquer outro = algum erro. Por isso `run_ffmpeg` checa `if proc.returncode != 0`.

**Encoding (codificação) / UTF-8 / cp1252** — como *bytes* viram *texto*. UTF-8 é o padrão universal
moderno (cobre acentos, emojis). cp1252 é um encoding antigo do Windows, limitado. 🔑 O console do
Windows usa cp1252 por padrão; ler bytes como UTF-8 à mão (`.decode("utf-8", errors="replace")`)
evita que um acento num nome de arquivo derrube o programa. `errors="replace"` troca um byte
inválido por `�` em vez de lançar erro.

---

## Concorrência — fazer coisas ao mesmo tempo

**Thread (linha de execução)** — uma "mão" extra do seu programa que executa código em paralelo ao
fluxo principal, dentro do *mesmo* processo. Usada quando você precisa fazer duas coisas ao mesmo
tempo — ex.: ler a stdout **e** o stderr simultaneamente para evitar o deadlock.

**Daemon thread** — uma thread "de fundo" que o Python encerra automaticamente quando o programa
principal acaba, sem esperar por ela. `threading.Thread(target=_drain, daemon=True)` — a thread que
esvazia o stderr não deve segurar o programa aberto se tudo já terminou.

---

## Padrões de projeto — as regras do mill.tools

**Core puro** — a camada `src/core/` só contém lógica reutilizável, **sem** nada de interface
(sem Flet, sem `print`). Assim CLI e GUI reusam o mesmo core. Regra nº 1 do projeto.

**Injeção de dependência** — em vez de a função *criar/conhecer* a coisa pesada de que precisa
(rede, GUI, modelo de IA), ela **recebe** essa coisa como parâmetro. Quem chama decide qual passar.
O `progress_cb` do `run_ffmpeg` é um exemplo: o core não conhece a barra de progresso; ele recebe um
callback e chama. Nos testes, você passa um callback falso e verifica os valores — sem precisar de
ffmpeg de verdade rodando uma GUI.

**Fonte única (single source of truth)** — cada assunto tem *um* dono no código. Todo mundo que
fala com o ffmpeg passa por `run_ffmpeg`; então há um lugar só para consertar um bug de subprocess,
em vez de dez cópias espalhadas.
