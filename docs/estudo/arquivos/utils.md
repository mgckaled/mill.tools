# `src/utils.py` — constantes de caminho, logging e checagem de dependências

> **Papel no projeto:** as "utilidades" fundamentais que quase tudo importa: onde os arquivos de
> saída moram (constantes de diretório), como transformar um título em nome de arquivo seguro
> (`sanitize_filename`), como configurar o logging sem quebrar a barra de progresso
> (`setup_logging` + `TqdmLoggingHandler`) e como verificar que os programas externos existem
> (`check_dependencies`).
>
> Repare que este arquivo fica em `src/` (raiz), não em `src/core/`. Ele é infraestrutura
> transversal, usada por CLI, GUI e core.
>
> **Pré-requisitos conceituais:** logging, regex, `Path`, PATH do sistema, handler. Todos no
> Glossário ao final.

---

## Cabeçalho e efeito colateral de import

```python
import logging
import os
import re
import shutil
from pathlib import Path

from tqdm import tqdm

os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
```

- **`logging`** — módulo padrão de registro de mensagens (info, aviso, erro).
- **`os`** — acesso ao sistema operacional (variáveis de ambiente, aqui).
- **`re`** — *regular expressions* (regex): padrões para buscar/substituir texto.
- **`shutil`** — utilidades de arquivo de alto nível; aqui usamos `shutil.which` (procura um
  programa no PATH).
- **`from tqdm import tqdm`** — biblioteca da barra de progresso de terminal.

🔑 **`os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"`** roda **no momento em que o arquivo é
importado** (não dentro de função). É um *efeito colateral de import*: define uma variável de
ambiente que silencia um aviso chato da biblioteca `huggingface_hub` (usada pelo Whisper) sobre
links simbólicos no Windows. Colocá-lo no topo garante que já esteja definido antes de qualquer
outra parte carregar o huggingface. Efeitos colaterais de import são usados com parcimônia — este é
um caso legítimo (config global que precisa valer cedo).

---

## As constantes de diretório

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
AUDIO_SOURCE_DIR = OUTPUT_DIR / "audio" / "source"
AUDIO_PROCESSED_DIR = OUTPUT_DIR / "audio" / "processed"
# ... vídeo, imagem, documento, transcrições, dados
DATA_DIR = OUTPUT_DIR / "data"
```

- **`Path(__file__)`** — `__file__` é uma variável mágica do Python que contém o caminho do arquivo
  atual (`.../src/utils.py`).
- **`.resolve()`** — transforma em caminho absoluto e resolve links/`..`.
- **`.parent.parent`** — sobe dois níveis: de `src/utils.py` → `src/` → raiz do projeto. Assim
  `PROJECT_ROOT` aponta para a pasta do projeto **independentemente de onde o usuário rodou o
  comando**.
- **`OUTPUT_DIR = PROJECT_ROOT / "output"`** — 🔑 o operador `/` da `pathlib` **junta caminhos**. É
  sobrecarregado (redefinido) para `Path`: `pasta / "sub"` cria `pasta/sub` de forma
  multiplataforma (usa `\` no Windows, `/` no Linux, sem você se preocupar).

🔑 **Por que constantes centralizadas?** É a regra de *fonte única* aplicada a caminhos. Cada módulo
tem um diretório canônico de saída (ex.: `AUDIO_PROCESSED_DIR`). Definir todos aqui, um lugar só,
significa que a Biblioteca e o RAG sabem exatamente onde varrer, e mudar a estrutura de pastas é uma
edição única. Repare no par recorrente `source` (o que foi baixado) vs. `processed` (o que o app
gerou) — um padrão que se repete em áudio/vídeo/imagem/documento.

---

## As regex de `sanitize_filename`

Antes da função, oito padrões pré-compilados:

```python
_SANITIZE_SEPS = re.compile(r"\s*[｜|·–—]\s*")
_SANITIZE_COLON = re.compile(r"\s*[：:]\s*")
_SANITIZE_INVALID = re.compile(r'[<>"\\/?*\x00-\x1f]')
_SANITIZE_PUNCT = re.compile(r"[!！？]")
_SANITIZE_DASH_SPACE = re.compile(r"\s*-\s*")
_SANITIZE_SPACES = re.compile(r"\s+")
_SANITIZE_MULTI_US = re.compile(r"_+")
_SANITIZE_MULTI_HY = re.compile(r"-+")

_MAX_STEM_LENGTH = 120
```

🔑 **O que é regex?** *Regular expression* é uma mini-linguagem para descrever padrões de texto. Ex.:
`\s+` significa "um ou mais espaços"; `[abc]` significa "qualquer um de a, b ou c". `re.compile(...)`
pré-processa o padrão uma vez (mais eficiente do que recompilar a cada chamada).

Decifrando alguns:
- **`r"\s*[｜|·–—]\s*"`** — `\s*` = "zero ou mais espaços"; `[｜|·–—]` = qualquer um desses
  separadores visuais (barra vertical, ponto médio, travessões). O `r"..."` é uma *raw string*
  (string crua), onde `\` é literal — essencial em regex para não confundir com escapes do Python.
- **`r'[<>"\\/?*\x00-\x1f]'`** — os caracteres **inválidos** em nomes de arquivo no Windows: `< > "
  \ / ? *` e os "de controle" `\x00-\x1f` (bytes 0 a 31, invisíveis). Note as aspas simples externas
  porque a `"` aparece dentro.
- **`_MAX_STEM_LENGTH = 120`** — teto do tamanho do nome. O Windows tem um limite histórico de 260
  caracteres para o caminho **inteiro** (MAX_PATH); manter o "miolo" do nome (stem) em 120 deixa
  folga para o prefixo do diretório de saída e um sufixo (`_ocr`, `_subbed`).

### A função

```python
def sanitize_filename(name: str) -> str:
    name = _SANITIZE_SEPS.sub("-", name)
    name = _SANITIZE_COLON.sub("-", name)
    name = _SANITIZE_INVALID.sub("", name)
    name = _SANITIZE_PUNCT.sub("", name)
    name = _SANITIZE_DASH_SPACE.sub("-", name.strip())
    name = _SANITIZE_SPACES.sub("_", name)
    name = _SANITIZE_MULTI_US.sub("_", name)
    name = _SANITIZE_MULTI_HY.sub("-", name)
    return name.strip("-_.")[:_MAX_STEM_LENGTH].rstrip("-_.")
```

Recebe um título "sujo" (de um vídeo do YouTube, por exemplo) e devolve um *stem* limpo de arquivo.
O método `.sub(substituto, texto)` troca tudo que casa o padrão pelo substituto. Passo a passo:

1. separadores visuais → hífen;
2. dois-pontos (ASCII e fullwidth) → hífen;
3. caracteres inválidos no Windows → removidos (`""`);
4. pontuação de exclamação/interrogação → removida;
5. hífen cercado de espaços → hífen limpo (após `.strip()` tirar espaços das pontas);
6. espaços → underscore (`_`);
7. underscores repetidos (`__`) → um só;
8. hífens repetidos (`--`) → um só;
9. **finalização:** `.strip("-_.")` remove hífen/underscore/ponto das pontas; `[:_MAX_STEM_LENGTH]`
   corta em 120 chars; `.rstrip("-_.")` limpa de novo o fim (o corte pode ter deixado lixo lá).

🔑 **Dois detalhes que os testes cobram (skill `testing`):**
- **O ponto `.` NÃO está na lista de inválidos** → é preservado: `"Python 3.13 Tutorial"` vira
  `"Python_3.13_Tutorial"`, não `"Python_313_Tutorial"`. Faz sentido: versões e extensões usam ponto.
- **Por que trocar `:` por hífen em vez de só remover?** A docstring explica: no NTFS (sistema de
  arquivos do Windows), um `:` sozinho no nome cria um *Alternate Data Stream* (um fluxo de dados
  oculto e bizarro) em vez de falhar visivelmente. Trocar por hífen evita esse comportamento
  traiçoeiro.

---

## `TqdmLoggingHandler` — logging que convive com a barra de progresso

```python
class TqdmLoggingHandler(logging.Handler):
    """Logging handler that writes through tqdm to avoid progress bar conflicts."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            tqdm.write(self.format(record))
        except RuntimeError:
            self.handleError(record)
```

🔑 **O problema que resolve.** O `logging` normal escreve com `print` direto no terminal. Mas o
`tqdm` desenha uma barra de progresso que "vive" na última linha do terminal. Se um log comum
escrever no meio disso, ele **rasga** a barra (aparecem barras duplicadas, linhas embaralhadas). A
solução: um *handler* customizado que manda toda mensagem de log através de `tqdm.write(...)`, que
sabe apagar a barra, escrever a linha e redesenhar a barra por baixo. Convivência limpa.

Anatomia:
- **`class TqdmLoggingHandler(logging.Handler):`** — cria uma classe que *herda* de
  `logging.Handler`. Herança = "é um tipo de"; nosso handler é um Handler com um comportamento
  trocado.
- **`def emit(self, record):`** — `emit` é o método que o sistema de logging chama para cada
  mensagem. Sobrescrevê-lo é o ponto de customização.
- **`self.format(record)`** — transforma o registro de log num texto formatado (data, nível,
  mensagem).
- **`tqdm.write(...)`** — escreve sem quebrar a barra.
- **`except RuntimeError: self.handleError(record)`** — se algo der errado ao escrever, delega ao
  tratamento de erro padrão do handler em vez de estourar.

Este handler é a razão de a regra nº 4 do projeto ("logging por handler dedicado, nunca `print`")
ser viável: há um mecanismo central que faz logs e progresso conviverem.

---

## `setup_logging` — configurar o nível e silenciar bibliotecas barulhentas

```python
def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    handler = TqdmLoggingHandler()
    handler.setFormatter(
        logging.Formatter(fmt="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    logging.root.setLevel(level)
    logging.root.handlers = [handler]

    for noisy in ("httpx", "httpcore", "faster_whisper", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
```

- **`verbose: bool`** — se `True`, mostra tudo (nível `DEBUG`); se `False`, só o essencial (`INFO`).
- **`handler.setFormatter(logging.Formatter(...))`** — define o formato de cada linha:
  `%(asctime)s` = hora, `%(levelname)s` = nível (INFO/ERROR), `%(message)s` = a mensagem;
  `datefmt="%H:%M:%S"` = hora no formato `14:30:05`.
- **`logging.root.setLevel(level)`** — o *root logger* é o logger "pai" de todos; definir seu nível
  vale globalmente.
- **`logging.root.handlers = [handler]`** — substitui os handlers do root pelo nosso (tqdm-aware).
- 🔑 **O laço final** — bibliotecas como `httpx` (requisições HTTP), `faster_whisper` e
  `huggingface_hub` são *tagarelas*: despejam dezenas de mensagens internas por operação. Capá-las em
  `WARNING` (só avisos e erros passam) mantém a saída do app limpa e focada no que interessa ao
  usuário. Também é uma *mitigação de estabilidade* mencionada no CLAUDE.md (menos I/O de log ajuda a
  não sobrecarregar a máquina/GPU fraca).

---

## `check_dependencies` — garantir que os programas externos existem

```python
def check_dependencies() -> None:
    missing = [tool for tool in ("yt-dlp", "ffmpeg") if not shutil.which(tool)]
    if missing:
        for tool in missing:
            logging.error("'%s' not found. Install it...", tool)
        raise RuntimeError(f"Missing dependencies: {', '.join(missing)}. Install and add to PATH.")
    logging.debug("Dependencies OK: yt-dlp and ffmpeg found.")
```

- 🔑 **`shutil.which(tool)`** — procura um programa no **PATH** do sistema (a lista de pastas onde o
  SO busca executáveis). Devolve o caminho se achar, ou `None` se não. É o equivalente ao comando
  `which`/`where` do terminal.
- **`missing = [tool for tool in (...) if not shutil.which(tool)]`** — uma *list comprehension*
  (compreensão de lista): "para cada ferramenta na tupla `("yt-dlp", "ffmpeg")`, inclua na lista
  `missing` **se** ela **não** for encontrada". Resultado: lista das que faltam.
- **`if missing:`** — em Python, uma lista vazia é "falsa" e uma lista com itens é "verdadeira"; então
  isto significa "se faltar alguma".
- **`logging.error(...)` para cada faltante**, depois **`raise RuntimeError(...)`** com a lista
  agregada. `", ".join(missing)` junta os nomes com vírgula.
- **`logging.debug("Dependencies OK...")`** — se tudo existe, registra em nível DEBUG (invisível no
  modo normal).

🔑 **Falha rápida e clara.** Em vez de o app quebrar de forma críptica no meio de um download, esta
função é chamada no início e diz, alto e claro, exatamente o que instalar e onde. É a diferença entre
um erro que ensina e um que assusta.

---

## Lições transversais deste arquivo

1. **Fonte única de caminhos.** Todos os diretórios de saída num lugar só → Biblioteca/RAG sabem onde
   varrer, e reestruturar pastas é uma edição.
2. **Defensividade de plataforma.** `sanitize_filename` codifica anos de dores de Windows (caracteres
   inválidos, MAX_PATH, ADS do NTFS) numa função testável.
3. **Infra de logging que não atrapalha.** O handler tqdm-aware é o que torna a regra "nunca `print`"
   prática, e capar bibliotecas barulhentas mantém a saída utilizável.
4. **Falha cedo com mensagem útil.** `check_dependencies` transforma um erro futuro e obscuro num
   aviso imediato e acionável.

---

## Glossário deste arquivo

**Logging** — sistema padrão do Python para registrar mensagens com níveis (DEBUG < INFO < WARNING <
ERROR). Superior a `print` por permitir filtrar por nível e redirecionar a saída centralmente.

**Handler (de logging)** — o componente que decide *para onde* uma mensagem de log vai (terminal,
arquivo, etc.). `TqdmLoggingHandler` manda para o terminal via `tqdm.write`.

**Root logger** — o logger raiz, "pai" de todos os outros. Configurar seu nível e handlers vale
globalmente.

**Nível de log (DEBUG/INFO/WARNING/ERROR)** — a "gravidade" de uma mensagem. Definir o nível filtra:
em INFO, mensagens DEBUG não aparecem.

**Herança (`class X(Y)`)** — mecanismo em que uma classe "é um tipo de" outra e reaproveita/troca o
comportamento dela. `TqdmLoggingHandler(logging.Handler)` herda de Handler e sobrescreve `emit`.

**Sobrescrever (override)** — redefinir, na classe filha, um método que já existe na classe pai
(`emit`).

**Regex (expressão regular)** — mini-linguagem de padrões de texto. `\s` = espaço, `+` = "um ou
mais", `[...]` = "qualquer um destes". `re.compile` pré-processa; `.sub(rep, txt)` substitui.

**Raw string (`r"..."`)** — string em que `\` é literal (não inicia escape). Essencial para regex.

**`__file__`** — variável que guarda o caminho do arquivo Python atual. Base para achar a raiz do
projeto de forma portátil.

**`Path` e o operador `/`** — `pathlib.Path` representa caminhos como objetos; o `/` junta partes de
caminho de forma multiplataforma.

**PATH** — a lista de pastas onde o sistema operacional procura por executáveis. `shutil.which` busca
nela.

**List comprehension** — sintaxe concisa para criar uma lista com um laço embutido:
`[x for x in itens if condição]`.

**Efeito colateral de import** — código que roda no momento em que o módulo é importado (fora de
qualquer função), como a definição da variável de ambiente no topo.

**Stem** — o "miolo" do nome de um arquivo, sem o diretório nem a extensão. `sanitize_filename`
produz um stem.

**MAX_PATH / NTFS / ADS** — limites e peculiaridades do Windows: MAX_PATH ≈ 260 chars para o caminho
inteiro; NTFS é o sistema de arquivos; ADS (Alternate Data Stream) é um fluxo oculto que um `:` no
nome criaria acidentalmente.
