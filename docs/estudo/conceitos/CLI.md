# Interfaces de linha de comando e `argparse` — guia completo do mill.tools

Documento de referência para entender CLIs de verdade: o que são, as convenções que valem para
qualquer linguagem, e os detalhes de Python (`argparse`) e do seu projeto. Foco especial em
**desmistificar o `argparse`**, que confunde no começo porque tem um vocabulário próprio
(parser, argumento posicional, opção, `Namespace`, subparser...). Todo exemplo é código real de
`main.py` e `src/cli/`. Glossário no fim.

> Como ler: a Parte 1 (fundamentos de CLI) vale para qualquer projeto/linguagem. Da Parte 2 em
> diante é `argparse` e a arquitetura da sua CLI. As caixas 🔑 marcam o que mais confunde.

---

# PARTE 1 — Fundamentos (valem para qualquer linguagem)

## 1.1 O que é uma CLI e por que ela existe

**CLI** (*Command-Line Interface*, interface de linha de comando) é a forma de usar um programa
**digitando um comando** no terminal, em vez de clicar numa tela. Você digita algo como:

```
uv run main.py video convert filme.mp4 --codec h264
```

e o programa faz o trabalho e devolve texto. É o oposto da **GUI** (*Graphical User Interface*), a
interface com janelas e botões (o seu `gui.py` com Flet).

Por que manter uma CLI se o projeto já tem GUI? Porque a CLI tem superpoderes que a GUI não tem:

- **Automação e scripts.** Um comando pode ser colocado num arquivo `.bat`/`.sh`, agendado, ou
  encadeado com outros. Você não "agenda um clique".
- **Composição.** A saída de um programa pode virar a entrada de outro (*pipes* do shell).
- **Velocidade para quem sabe.** Sem esperar telas carregarem.
- **Servidores e CI.** Máquinas sem tela (um servidor de testes) só têm CLI.

🔑 No seu projeto, CLI e GUI **compartilham o mesmo `core/` puro**. A CLI é uma das "bordas" (a outra
é a GUI) que traduzem a intenção do usuário em chamadas ao core. É a regra nº 1 do projeto pagando
dividendos: escrever a lógica uma vez, expor por dois caminhos.

## 1.2 A anatomia de um comando

Decore este vocabulário — o `argparse` inteiro gira em torno dele. Veja um comando real, dissecado:

```
uv run main.py   video    convert   filme.mp4    --codec h264   --verbose
└──── shell ────┘ └──────┘ └───────┘ └─────────┘  └──────────┘   └───────┘
                subcomando  sub-sub   argumento     opção com      opção
                            comando   posicional     valor       booleana
```

- **Programa:** `main.py` — o executável que recebe tudo.
- **Subcomando:** `video` — escolhe *qual área* do programa você quer (áudio, vídeo, imagem...).
- **Sub-subcomando:** `convert` — dentro de vídeo, *qual operação* (converter, cortar, comprimir...).
- **Argumento posicional:** `filme.mp4` — um valor **obrigatório** cuja identidade vem da **posição**
  (não tem `--nome`). O programa sabe que o primeiro valor solto é o arquivo.
- **Opção (ou flag):** `--codec` — um parâmetro **nomeado**, identificado pelo `--`. Pode ter um
  valor (`--codec h264`) ou ser apenas um interruptor (`--verbose`, ligado/desligado).
- **Valor da opção:** `h264` — o que acompanha `--codec`.

🔑 **Posicional vs. opção — a distinção que mais confunde.** Posicional = identificado pela **ordem**,
geralmente obrigatório, sem `--` (é o *o quê*: o arquivo). Opção = identificada pelo **nome** (`--`),
geralmente com um padrão, ordem livre (é o *como*: o codec, a qualidade). "Argumento" é o termo
guarda-chuva para os dois.

## 1.3 Convenções universais de CLI

Existem padrões que quase todo programa de terminal respeita (herança do mundo Unix/POSIX/GNU). Vale
conhecê-los porque o `argparse` os implementa para você:

- **Opções curtas e longas:** `-v` (curta, uma letra) e `--verbose` (longa, legível). Seu projeto usa
  quase só as longas (`--quality`, `--codec`), que são mais claras.
- **Posicionais primeiro, opções depois** — por convenção, mas o `argparse` aceita em qualquer ordem.
- **`--help`** deve existir e explicar o uso, saindo sem fazer nada. 🔑 O `argparse` **gera o `--help`
  automaticamente** a partir dos seus `help=` — de graça.
- **Código de saída (exit code):** `0` = sucesso, qualquer outro número = falha. Scripts checam isso
  para decidir o que fazer em seguida. Seu projeto respeita à risca: `sys.exit(1)` quando um pipeline
  falha (veremos onde).
- **stdout vs. stderr:** a saída "de resultado" vai para o **stdout**; erros e diagnósticos vão para o
  **stderr**. Separá-los permite ao usuário redirecionar cada um. Seu `CLIEventBus` manda logs de erro
  via `logging` (stderr) e o resultado via `tqdm.write` (stdout).

---

# PARTE 2 — `argparse`, o coração da CLI

`argparse` é o módulo padrão do Python para **analisar** (fazer o *parsing* de) os argumentos que o
usuário digitou. Sem ele, você receberia uma lista crua de strings (`sys.argv`) e teria que decifrar
tudo na mão. O `argparse` faz isso, valida, gera `--help` e mensagens de erro.

## 2.1 O fluxo mental do `argparse` (3 passos)

Todo uso de `argparse` segue o mesmo roteiro:

1. **Criar um parser:** `parser = argparse.ArgumentParser(...)` — o objeto que vai "entender" a linha
   de comando.
2. **Declarar o que você espera:** `parser.add_argument(...)` — uma chamada por argumento (posicional
   ou opção). Você descreve o nome, o tipo, o padrão, a ajuda.
3. **Analisar:** `ns = parser.parse_args()` — o parser lê `sys.argv`, valida, e devolve um objeto
   `Namespace` com os valores prontos. Se algo estiver errado, ele imprime o erro e o `--help` e
   encerra.

🔑 **O `Namespace` é o produto final.** É só um objeto simples cujos atributos são os valores lidos:
se você declarou `--quality`, depois do parse existe `ns.quality`. Pense nele como um formulário
preenchido. O resto do programa só lê esse formulário — nunca mexe em `sys.argv` de novo.

## 2.2 Declarando argumentos: posicional vs. opção

A **mesma** função, `add_argument`, cria os dois tipos — a diferença é o **nome**:

```python
# POSICIONAL: nome SEM traço → identificado pela posição, obrigatório
dl.add_argument("url", help="YouTube/yt-dlp URL")

# OPÇÃO: nome COM "--" → identificada pelo nome, opcional (tem default)
dl.add_argument("--quality", default="1080", metavar="HEIGHT",
                help="Max resolution height (default 1080)")
```

Depois do parse, ambos viram atributos do `Namespace`: `ns.url` e `ns.quality`.

## 2.3 Os parâmetros de `add_argument` (o dicionário que você precisa)

Estes são os parâmetros que aparecem no seu `cli/transcription.py` e `cli/video.py`. Entender estes
seis resolve 95% do `argparse`:

| Parâmetro | O que faz | Exemplo real do projeto |
|---|---|---|
| **`default`** | Valor usado quando a opção é omitida. | `--quality` default `"1080"` |
| **`type`** | Converte a string digitada para outro tipo. | `--crf` com `type=int` → `23` vira `int`, não `"23"` |
| **`choices`** | Restringe os valores aceitos; fora da lista → erro. | `--preset` com `choices=["ultrafast", ..., "veryslow"]` |
| **`action="store_true"`** | Faz a opção ser um **interruptor** booleano (presente=`True`, ausente=`False`), sem valor. | `--verbose`, `--reenc`, `--srt` |
| **`dest`** | O nome do atributo no `Namespace` (quando difere do nome da opção). | `--start` com `dest="trim_start"` → lê-se `ns.trim_start` |
| **`help`** | Texto exibido no `--help`. | todos |
| **`required=True`** | Torna uma **opção** obrigatória (posicionais já são). | `--start` (`required=True`) no `trim` |
| **`metavar`** | O nome do valor exibido no `--help` (cosmético). | `--start` com `metavar="TIME"` → mostra `--start TIME` |

Veja tudo junto num exemplo real (`cli/video.py`, operação `trim`):

```python
tr.add_argument("file", help="Local video file")                    # posicional obrigatório
tr.add_argument("--start", required=True, dest="trim_start",        # opção obrigatória,
                metavar="TIME", help="Start time e.g. '0:30'")       #   lida como ns.trim_start
tr.add_argument("--end", default="", dest="trim_end",               # opção com default vazio
                metavar="TIME", help="End time (omit to cut to end)")
tr.add_argument("--reenc", action="store_true", dest="trim_reenc",  # interruptor booleano
                help="Re-encode instead of stream-copy")
```

🔑 **Por que `dest`?** A opção na linha de comando é `--start` (curta e amigável), mas no código você
quer um nome sem ambiguidade (`trim_start`, para não colidir com o `--start` de outra operação num
`Namespace` compartilhado). `dest` faz essa ponte: usuário digita `--start`, seu código lê
`ns.trim_start`.

🔑 **`action="store_true"` é o que faz uma flag "sem valor".** `--verbose` não recebe um valor; sua
mera presença liga algo. `store_true` significa "se aparecer, guarde `True`; senão, `False`". É por
isso que você escreve `if args.verbose:` e não `if args.verbose == "sim":`.

## 2.4 O parser legado do projeto (transcrição)

No seu `main.py`, o comando de transcrição (o "legado", o primeiro do projeto) usa um parser único:

```python
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe a YouTube video or local audio file using faster-whisper.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_transcribe_args(parser)
    return parser.parse_args(argv)
```

Dois detalhes didáticos:

- 🔑 **`argv: list[str] | None = None`** e `parser.parse_args(argv)`. Por padrão, `parse_args()` lê de
  `sys.argv` (o que o usuário digitou de verdade). Mas aceitar uma lista opcional permite os **testes**
  passarem argumentos falsos sem mexer no estado do processo — exatamente o que o `tests/cli/` faz
  (lembra do `_parse(*argv)` no doc de testes?). Um detalhe pequeno que torna o parser testável.
- **`formatter_class=ArgumentDefaultsHelpFormatter`** — faz o `--help` mostrar automaticamente o valor
  padrão de cada opção. Cortesia com o usuário, de graça.

E `add_transcribe_args` (em `cli/transcription.py`) é onde todas as flags de transcrição são
declaradas. 🔑 Ela é **fonte única**: o parser legado **e** o parser de referência do NL→CLI a
reusam, então uma flag nova aparece nos dois automaticamente. Repare também no **import preguiçoso**
lá dentro:

```python
if include_profile_choices:
    from src.analysis import list_profiles   # lazy: evita carregar LangChain nos outros comandos
    profile_choices = list_profiles()
else:
    profile_choices = None
parser.add_argument("--profile", default="default", choices=profile_choices, ...)
```

Carregar a lista de perfis puxa o LangChain (pesado). Fazer esse import **dentro** da função, só
quando de fato preciso, mantém rápidos os outros subcomandos. É a mesma regra de import preguiçoso do
`llm_factory`.

---

# PARTE 3 — Subcomandos e subparsers (a estrutura da sua CLI)

Quando um programa faz **várias coisas diferentes** (áudio, vídeo, imagem...), cada uma com seus
próprios argumentos, você não empilha tudo num parser só — você usa **subcomandos**, via
**subparsers**. É como o `git`: `git commit`, `git push`, cada um com suas flags.

## 3.1 `add_subparsers` — o roteador de subcomandos

```python
parser = argparse.ArgumentParser(prog="main.py", description="mill.tools — ...")
subparsers = parser.add_subparsers(dest="command", required=True)
add_audio_parser(subparsers)
add_video_parser(subparsers)
# ... image, document, library, ai, recipe, data, observatory
```

- **`add_subparsers(...)`** cria o "encaixe" onde os subcomandos serão registrados.
- **`dest="command"`** — guarda o nome do subcomando escolhido em `ns.command` (útil para saber o que
  o usuário pediu).
- 🔑 **`required=True`** — obriga o usuário a escolher **algum** subcomando. Sem isso, `argparse`
  permitiria rodar `main.py` sozinho, sem dizer o quê fazer, e você teria um `Namespace` vazio.

Cada `add_*_parser(subparsers)` registra um subcomando. Veja `add_video_parser` (`cli/video.py`):

```python
def add_video_parser(subparsers) -> None:
    video_p = subparsers.add_parser("video", help="Download, convert, trim, ...")
    video_sub = video_p.add_subparsers(dest="video_op", required=True)   # sub-SUB-comandos!
    ...
```

## 3.2 Sub-subcomandos (dois níveis)

🔑 Repare que `video_p` (o parser do `video`) cria **seus próprios** subparsers (`video_sub`). Isso é
um **segundo nível**: `video` → `convert`/`trim`/`compress`... Cada operação vira um sub-subparser com
argumentos próprios:

```python
cv = video_sub.add_parser("convert", help="Convert video codec or container")
cv.add_argument("file", help="Local video file")
cv.add_argument("--codec", default="copy", help="...")

tr = video_sub.add_parser("trim", help="Trim video to a time range")
tr.add_argument("file", help="Local video file")
tr.add_argument("--start", required=True, dest="trim_start", ...)
```

Assim, `video convert` e `video trim` têm conjuntos de flags totalmente diferentes, e o `--help` de
cada um mostra só o que faz sentido para ele. É a organização que mantém uma CLI grande navegável.

## 3.3 O padrão `set_defaults(func=...)` — despacho sem `if/elif`

Aqui está a sacada mais elegante do `argparse`, e a que o seu projeto adota. Em vez de, depois do
parse, escrever um `if ns.command == "video": ... elif ns.command == "audio": ...` gigante, cada
parser **anexa a própria função de execução** ao `Namespace`:

```python
video_p.set_defaults(func=run_video_cli)      # no fim de add_video_parser
```

`set_defaults(func=...)` guarda uma referência à função `run_video_cli` no atributo `ns.func`. Então
o despacho vira **uma linha**, no `main.py`:

```python
ns = parser.parse_args(sys.argv[1:])
ns.func(ns)          # chama a função certa, seja qual for o subcomando
```

🔑 **Por que isso é superior ao `if/elif`.** Adicionar um subcomando novo não exige tocar num bloco
central de decisão — o parser dele já traz sua função embutida. É o mesmo princípio de "cada peça
sabe se executar" que mantém o código desacoplado. (Esta é uma recomendação clássica de design de
CLI, não uma invenção do projeto.)

## 3.4 O despacho de dois estágios do `main.py`

Seu `main.py` tem um detalhe a mais: ele separa o comando **legado** de transcrição dos demais. O
roteamento acontece pelo **primeiro argumento**:

```python
_NON_TRANSCRIBE_CMDS = frozenset({"audio", "audio-viz", "video", "image", "document",
                                  "library", "ai", "recipe", "data", "observatory"})

def main() -> None:
    # 1) Se o 1º arg é um subcomando conhecido → despacha para os módulos de cli/
    if len(sys.argv) > 1 and sys.argv[1] in _NON_TRANSCRIBE_CMDS:
        _dispatch_other(sys.argv[1])
        return
    # 2) "transcribe" explícito é aceito e removido, para forward-compat
    if len(sys.argv) > 1 and sys.argv[1] == "transcribe":
        sys.argv.pop(1)
    # 3) senão, tudo é tratado como transcrição (o modo legado: main.py <URL>)
    args = parse_args()
    ...
```

🔑 **Por que dois estágios em vez de um subparser único para tudo?** História: o projeto **nasceu**
como só um transcritor (`main.py <URL>`). Para não quebrar esse uso quando novos módulos chegaram, o
`main.py` checa se o primeiro argumento é um subcomando novo; se não for, assume que é o velho fluxo
de transcrição (onde o primeiro argumento é a própria URL/arquivo). `frozenset` é um conjunto
**imutável** — perfeito para uma lista fixa de nomes consultada com `in` (busca rápida). O
`sys.argv.pop(1)` remove a palavra `transcribe` para o parser legado continuar vendo a URL na posição
que espera.

---

# PARTE 4 — A arquitetura da CLI do projeto

Além do `argparse`, sua `cli/` tem padrões próprios que vale entender.

## 4.1 A taxonomia: dois tipos de subcomando

A skill `cli` divide todos os subcomandos em dois grupos, e a diferença define como você escreve cada
um:

| Tipo | Subcomandos | Como funciona |
|---|---|---|
| **Pipeline + `CLIEventBus`** | `audio`, `video`, `image`, `document`, `recipe` | Têm progresso longo. Constroem um `XxxArgs`, criam um `CLIEventBus`, e chamam `run_X_pipeline(args, bus, cancel, install_log_handler=False)`. Retorno `False` → `sys.exit(1)`. |
| **Read-only, core direto** | `library`, `ai`, `data`, `observatory`, `audio-viz` | Operações rápidas e síncronas, sem barra de progresso. Chamam o core **direto**, sem bus. Reconfiguram o `stdout` para UTF-8. |

🔑 **Decida a qual grupo o subcomando pertence ANTES de escrevê-lo** — isso define se há bus, cancel e
`install_log_handler`, ou se é core-direto. É a primeira pergunta ao criar um subcomando novo.

## 4.2 `run_X_cli` — a tradução `Namespace` → `Args`

O trabalho de um runner de CLI é **traduzir** o `Namespace` (formato do `argparse`) para o objeto
`Args` que o pipeline do core espera. Veja `run_video_cli` (`cli/video.py`):

```python
def run_video_cli(ns: argparse.Namespace) -> None:
    check_dependencies()
    op = ns.video_op

    if op == "download":
        item = InputItem(kind="url", value=ns.url)
    else:
        item = InputItem(kind="local", value=str(Path(ns.file).resolve()))

    args = VideoArgs(
        items=[item],
        operation=op if op != "extract-audio" else "extract_audio",
        resolution=getattr(ns, "quality", "1080"),
        container=getattr(ns, "container", "mp4"),
        crf=getattr(ns, "crf", 23),
        ...
    )
    bus = CLIEventBus()
    cancel = threading.Event()
    success = run_video_pipeline(args, bus, cancel, install_log_handler=False)
    if not success:
        sys.exit(1)
```

Três coisas para reparar:

- 🔑 **`getattr(ns, "quality", "1080")`** — pega `ns.quality` **se existir**, senão devolve o padrão
  `"1080"`. Por que a proteção? Porque o `Namespace` de `video convert` **não tem** `quality` (essa
  flag só existe em `download`). Como todas as operações montam **o mesmo** `VideoArgs`, o runner usa
  `getattr` com padrão para os campos que só algumas operações preenchem. É a cola que permite um
  runner único servir 8 operações.
- 🔑 **`operation=op if op != "extract-audio" else "extract_audio"`** — o famoso **kebab→snake**. Na
  linha de comando a operação é `extract-audio` (com hífen, convenção de CLI); no código Python o
  nome precisa ser `extract_audio` (com underscore, para ser um identificador válido). O runner faz
  essa conversão. (Os subcomandos `video`/`image`/`document` fazem isso genericamente com
  `op.replace("-", "_")`.)
- **`if not success: sys.exit(1)`** — o pipeline devolve `True`/`False`; a CLI traduz um `False` em
  código de saída `1` (falha), respeitando a convenção de exit code que scripts checam.

## 4.3 `resolve_input` — URL ou arquivo local?

Uma função pequena e reusada por todos os runners (`cli/transcription.py`):

```python
def resolve_input(value: str) -> tuple[str, str]:
    path = Path(value)
    if path.is_file():
        return ("local", str(path.resolve()))
    return ("url", value)
```

🔑 A heurística é simples e robusta: **se existe como arquivo no disco, é local; senão, trata como
URL**. O resultado alimenta o `InputItem(kind, value)` que você já conhece do doc da espinha —
fechando a ponte entre a borda (CLI) e o tipo puro do core.

---

# PARTE 5 — `CLIEventBus`: progresso no terminal

Os pipelines do core não sabem se estão rodando na GUI ou na CLI — eles só **emitem eventos** (o
contrato de eventos, tema da Sessão 3). Na GUI, um `EventBus` transforma esses eventos em atualização
de tela. Na CLI, o **`CLIEventBus`** (`cli/bus.py`) transforma os **mesmos** eventos em barra `tqdm` e
linhas de log. É o padrão **Adapter** (adaptador): mesma interface, saída diferente.

```python
class CLIEventBus:
    def emit(self, type, stage="", payload=None, module_id=""):
        p = payload or {}
        handler = self._HANDLERS.get(type)     # despacha por tipo de evento
        if handler:
            handler(self, p)
```

🔑 **O `emit` tem a mesma assinatura do `EventBus` da GUI** — é o que permite o **mesmo**
`run_video_pipeline` funcionar com qualquer um dos dois. O core chama `bus.emit(...)` sem saber qual
bus é. Injeção de dependência de novo: o pipeline recebe o bus pronto.

Como cada evento vira saída de terminal:

- **`progress_start`** cria uma barra `tqdm` (`total=100`); **`progress_update`** move a barra;
  **`task_done`** a fecha e imprime os caminhos de saída com `[✓]`.
- **`log`** escreve uma linha; se `mutable=True`, sobrescreve a linha anterior (`\r`) — útil para um
  contador que atualiza no lugar.
- **`task_error`** fecha a barra e loga o erro via `logging.error` (que vai para o **stderr**).

🔑 **A limpeza de ANSI** (`_strip`): o yt-dlp e outras ferramentas emitem sequências de cor ANSI
(`\x1b[0m...`) no meio do texto de progresso. Se você as imprimisse cruas, o terminal mostraria lixo.
A regex `_ANSI_ESC` as remove antes de exibir. É o mesmo cuidado de encoding que você viu em
`ffmpeg.py`, agora do lado da saída.

E o parâmetro **`install_log_handler=False`** que os runners sempre passam: ele impede o worker de
instalar **seu próprio** handler de log no logger raiz, porque a CLI já recebe os logs via o
`CLIEventBus`. Sem isso, cada mensagem apareceria **duas vezes**. Sempre passe `False` nos runners de
pipeline.

---

# PARTE 6 — Gotchas da CLI do projeto (o que o `--help` não conta)

- **kebab→snake** (`video`/`image`/`document`): a operação vem com hífen no `Namespace`
  (`ns.image_op == "contact-sheet"`); o runner converte com `op.replace("-", "_")`. Nos testes,
  asserte sempre o nome em `snake_case` no `Args`.
- **UTF-8 no stdout** (todos os read-only + `recipe`): os runners reconfiguram `sys.stdout` para
  UTF-8/replace antes de imprimir — nomes de arquivo com caracteres fora do cp1252 (ex.: `｜`)
  quebrariam o console do Windows sem isso. (Mesma raiz do modo binário do `ffmpeg.py`.)
- **`data query` é multi-input:** `files` (`nargs="+"`, um ou mais) seguido do positional `question`.
  `--sql` trata `question` como SQL literal e pula o NL→SQL.
- **`ai` é a exceção sem sub-subparser:** tem um único positional `query` despachado por valor literal
  (`index`/`stats`/`map`... são fluxos de ML; qualquer outro valor é a pergunta ao RAG).
- **`ai --cmd` tem prioridade:** com essa flag, `ai --cmd stats` **não** roda o fluxo `stats` — gera um
  comando CLI para a palavra "stats" (NL→CLI). A flag vence os fluxos de palavra-chave.
- **`--strict-markers` não é da CLI, é do pytest** — mas o espírito é o mesmo: falhar cedo em erro de
  digitação. Na CLI, o `argparse` já faz isso: uma opção desconhecida → erro + `--help` + exit.

---

# PARTE 7 — Como adicionar um subcomando novo (checklist)

1. **Decida a taxonomia** (Parte 4.1): pipeline+bus ou read-only core-direto?
2. **Crie `src/cli/novo.py`** com:
   - `add_novo_parser(subparsers)` — registra o parser (posicionais, opções, `choices`, `type`,
     `dest`), e no fim `novo_p.set_defaults(func=run_novo_cli)`.
   - `run_novo_cli(ns)` — traduz o `Namespace` para os `Args`; pipeline+bus → constrói `Args`,
     `CLIEventBus`, `run_novo_pipeline(..., install_log_handler=False)`, `sys.exit(1)` se falhar;
     read-only → chama o core direto + reconfigura stdout UTF-8.
3. **Registre em `main.py`:** adicione `"novo"` a `_NON_TRANSCRIBE_CMDS` e importe/registre em
   `_dispatch_other`.
4. **Testes** em `tests/cli/test_novo_cli.py` (`@pytest.mark.unit`): use o padrão `_parse(*argv)` para
   testar o parsing e `mocker.patch(...run_novo_pipeline...)` para testar o despacho (veja `TESTES.md`,
   Parte 4).
5. **Import preguiçoso** de qualquer coisa pesada (LangChain, core de um módulo) dentro do runner, não
   no topo — preserva a partida rápida dos outros comandos.

---

# Glossário

**CLI (Command-Line Interface)** — usar um programa digitando comandos no terminal, em vez de clicar.
Oposto de GUI.

**GUI (Graphical User Interface)** — interface gráfica com janelas e botões (o `gui.py` com Flet).

**Shell / terminal** — o programa onde você digita comandos (PowerShell, bash). Ele lê o que você
digita, encontra o programa e passa os argumentos.

**`sys.argv`** — a lista crua de strings que o programa recebeu (o nome do programa + cada argumento
digitado). `argparse` a analisa para você.

**Argumento** — termo guarda-chuva para qualquer valor passado a um comando (posicional ou opção).

**Argumento posicional** — identificado pela **posição**, geralmente obrigatório, sem `--` (ex.: o
arquivo). O primeiro valor solto é o primeiro posicional declarado.

**Opção / flag** — argumento **nomeado**, identificado por `--nome` (ou `-x`), geralmente opcional.
Pode ter valor (`--codec h264`) ou ser um interruptor booleano (`--verbose`).

**Interruptor booleano (`action="store_true"`)** — opção sem valor: presente = `True`, ausente =
`False`.

**argparse** — o módulo padrão do Python que analisa a linha de comando, valida, gera `--help` e
mensagens de erro.

**Parser (`ArgumentParser`)** — o objeto que "entende" a linha de comando. Você o configura com
`add_argument` e o executa com `parse_args`.

**`add_argument(...)`** — declara um argumento esperado (posicional ou opção) e como tratá-lo.

**`parse_args(argv=None)`** — lê os argumentos (de `sys.argv` ou de uma lista passada nos testes),
valida e devolve um `Namespace`.

**Namespace** — o objeto simples que `parse_args` devolve, com um atributo por argumento (ex.:
`ns.quality`). O "formulário preenchido".

**`default`** — valor de uma opção quando ela é omitida.

**`type`** — função de conversão da string digitada (ex.: `type=int` transforma `"23"` em `23`).

**`choices`** — lista fechada de valores aceitos; fora dela → erro.

**`dest`** — o nome do atributo no `Namespace`, quando difere do nome da opção (ex.: `--start` →
`ns.trim_start`).

**`metavar`** — nome do valor exibido no `--help` (cosmético).

**`required=True`** — torna uma **opção** obrigatória (posicionais já são por natureza).

**Subcomando / subparser (`add_subparsers`, `add_parser`)** — dividir um programa em modos, cada um
com seus próprios argumentos (como `git commit` vs `git push`). Subparsers podem ter subparsers
próprios (sub-subcomandos, como `video convert`).

**`dest="command"` (no subparsers)** — guarda o nome do subcomando escolhido.

**`set_defaults(func=...)`** — anexa uma função ao `Namespace` (`ns.func`), permitindo o despacho em
uma linha (`ns.func(ns)`) sem `if/elif`.

**`frozenset`** — um conjunto **imutável**; usado para a lista fixa de subcomandos, com busca rápida
por `in`.

**`getattr(obj, "nome", padrão)`** — lê um atributo se existir, senão devolve o padrão. Usado no
runner para campos que só algumas operações preenchem.

**kebab-case / snake_case** — `extract-audio` (hífen, convenção de CLI) vs `extract_audio` (underscore,
identificador Python). O runner converte um no outro.

**Exit code (código de saída)** — número devolvido ao terminar: `0` = sucesso, outro = falha.
`sys.exit(1)` sinaliza erro.

**stdout / stderr** — canais de saída: resultado normal vai no stdout; erros/diagnósticos no stderr.

**`CLIEventBus`** — o adaptador que traduz os eventos do pipeline em barra `tqdm` + logs no terminal;
espelha a interface do `EventBus` da GUI.

**Adapter (adaptador)** — padrão de projeto: dar a duas coisas a mesma interface para que um cliente
(o pipeline) funcione com qualquer uma (bus da GUI ou da CLI) sem saber qual é.

**tqdm** — biblioteca da barra de progresso de terminal.

**ANSI escape** — sequências invisíveis de cor/estilo no texto de terminal (`\x1b[0m`). Precisam ser
removidas antes de exibir texto capturado de outra ferramenta.

**`install_log_handler=False`** — parâmetro que impede o worker de instalar seu próprio handler de
log, evitando mensagens duplicadas na CLI (que já loga via o `CLIEventBus`).

**Import preguiçoso (lazy import)** — importar uma lib pesada dentro da função que a usa, para não
atrasar a partida dos outros comandos.

---

## Fontes

Refinado com as convenções e a documentação atuais de:

- [argparse — Parser for command-line options, arguments and subcommands (Python docs)](https://docs.python.org/3/library/argparse.html)
- [Build Command-Line Interfaces With Python's argparse — Real Python](https://realpython.com/command-line-interfaces-python-argparse/)
- [Python argparse: Subparsers Explained — Common Pitfalls and Alternatives](https://runebook.dev/en/docs/python/library/argparse/argparse.ArgumentParser.add_subparsers)
- [Simplifying argparse usage with subcommands — mike.depalatis.net](https://mike.depalatis.net/blog/simplifying-argparse.html)
- [Argument Syntax (The GNU C Library)](https://www.gnu.org/software/libc/manual/html_node/Argument-Syntax.html)
- [Utility Conventions — The Open Group (POSIX)](https://pubs.opengroup.org/onlinepubs/9699919799/basedefs/V1_chap12.html)
- [Stdin, Stdout, and Stderr: Linux I/O Streams Explained — Boot.dev](https://www.boot.dev/blog/devops/stdin-stdout-stderr)
