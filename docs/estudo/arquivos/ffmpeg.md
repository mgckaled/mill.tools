# `src/core/ffmpeg.py` — a única porta para o ffmpeg

> **Papel no projeto:** a *fonte única* de comunicação com o programa externo `ffmpeg`. Os módulos
> Áudio e Vídeo nunca chamam o ffmpeg direto — todos passam por `run_ffmpeg(...)`. Um lugar só para
> montar o processo, ler progresso, tratar erro e contornar quirks de Windows.
>
> **Pré-requisitos conceituais:** processo, stdout/stderr, buffer, deadlock, thread, callback. Todos
> explicados no Glossário ao final deste doc.

---

## Visão de 30 segundos

```python
def run_ffmpeg(cmd, out_path, *, total_secs=None, progress_cb=None,
               stderr_tail=100, cwd=None) -> Path:
    # 1. lança o ffmpeg como processo, lendo stdout e stderr por "canos"
    # 2. drena o stderr numa thread paralela (evita deadlock)
    # 3. lê o progresso do stdout e chama progress_cb(0.0–1.0)
    # 4. espera terminar; valida returncode E existência do arquivo
    # 5. devolve out_path (ou levanta erro explicativo)
```

É uma função só. Não há classe aqui — é lógica pura de orquestração de um processo externo.

---

## O cabeçalho do arquivo

```python
"""Shared ffmpeg runner used by audio and video pipelines."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Callable
```

- **`"""Shared ffmpeg runner..."""`** — a *docstring* de módulo. A palavra "Shared" (compartilhado)
  já anuncia a intenção de fonte única.
- **`from __future__ import annotations`** — faz o Python tratar as anotações de tipo (`: Path`,
  `-> Path`) como texto, sem avaliá-las ao carregar. Barato e permite sintaxe moderna. Padrão em
  todo o `core/`.
- **`import subprocess`** — o módulo padrão do Python para lançar e controlar outro processo.
- **`import threading`** — para criar a thread que drena o stderr (item 2).
- **`from pathlib import Path`** — `Path` é a forma moderna de representar caminhos de arquivo como
  objetos (em vez de strings), com métodos como `.exists()`.
- **`from typing import Callable`** — o tipo que descreve "uma função que pode ser chamada",
  usado para anotar o parâmetro `progress_cb`.

---

## A assinatura, parâmetro por parâmetro

```python
def run_ffmpeg(
    cmd: list[str],
    out_path: Path,
    *,
    total_secs: float | None = None,
    progress_cb: Callable[[float], None] | None = None,
    stderr_tail: int = 100,
    cwd: Path | None = None,
) -> Path:
```

| Parâmetro | Tipo | O que é |
|---|---|---|
| `cmd` | `list[str]` | A linha de comando do ffmpeg já montada pelo chamador, como lista de strings — ex.: `["ffmpeg", "-i", "entrada.mp4", ...]`. |
| `out_path` | `Path` | Onde o arquivo de saída **deve** aparecer. Usado no fim para validar sucesso. |
| `total_secs` | `float \| None` | Duração total da mídia em segundos. Necessária para transformar tempo processado em *porcentagem*. `None` = não calcula progresso. |
| `progress_cb` | `Callable[[float], None] \| None` | O **callback de progresso**. Uma função que recebe um `float` (0.0 a 1.0) e não devolve nada (`None`). `None` = ninguém quer saber do progresso. |
| `stderr_tail` | `int` | Quantas linhas finais do stderr guardar (padrão 100). |
| `cwd` | `Path \| None` | Diretório de trabalho do processo. Existe por um quirk de Windows (detalhado abaixo). |

🔑 **O `*` sozinho na lista de parâmetros.** Tudo que vem *depois* do `*` só pode ser passado
**por nome** (`progress_cb=minha_funcao`), nunca por posição. Isso força o chamador a ser explícito
e evita erros do tipo "passei o quarto argumento sem saber qual era". É uma convenção de clareza
comum no projeto.

🔑 **A tipagem `Callable[[float], None]`.** Lê-se: "uma função que recebe um argumento `float` e
retorna `None`". Essa anotação é a *forma escrita* do contrato de callback: o core promete chamar a
sua função passando um número entre 0 e 1. É a regra de injeção de dependência expressa em tipos.

🔑 **`X | None` e o valor `= None`.** O `| None` (lê-se "ou None") diz que o parâmetro é *opcional*
— pode ser um valor real ou o "nada" (`None`). O `= None` define esse "nada" como padrão. Juntos,
significam: "se você não passar, eu simplesmente não faço essa parte". É como o mesmo `run_ffmpeg`
serve tanto a quem quer barra de progresso quanto a quem não quer.

**Retorno `-> Path`:** em caso de sucesso, devolve o próprio `out_path`. Devolver o caminho (em vez
de `True`) permite encadear: `resultado = run_ffmpeg(...)` já te dá o arquivo pronto para o próximo
passo.

---

## O corpo, bloco por bloco

### Bloco 1 — lançar o processo em modo binário

```python
proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=str(cwd) if cwd else None,
)
```

- **`subprocess.Popen(...)`** inicia o ffmpeg como processo separado e devolve um objeto `proc` que
  te dá controle sobre ele (ler saídas, esperar terminar, ver o código de saída).
- **`stdout=subprocess.PIPE`** e **`stderr=subprocess.PIPE`** — pedem um "cano" (pipe) para *ler*
  cada canal do ffmpeg de dentro do Python.
- **`cwd=str(cwd) if cwd else None`** — se um diretório de trabalho foi passado, converte para
  string; senão, `None` (deixa o padrão). Essa expressão é um *if inline* (operador ternário):
  `A if condição else B`.

🔑 **A ausência de `text=True` é a decisão mais importante deste bloco.** Sem `text=True`, o Python
lê a saída como **bytes** crus, não como texto decodificado automaticamente. Por que isso importa?
No Windows, a decodificação automática usa o encoding `cp1252` do console; um nome de arquivo com
acento (comum em títulos de vídeo) vira um byte que o cp1252 não entende → `UnicodeDecodeError`, e o
programa quebra. Lendo bytes e decodificando à mão com `errors="replace"` (nos blocos seguintes),
nada quebra. **É a regra nº 5 do projeto** ("subprocess sempre em modo binário").

### Bloco 2 — a thread que drena o stderr

```python
stderr_lines: list[str] = []

def _drain() -> None:
    for raw in proc.stderr:
        stderr_lines.append(raw.decode("utf-8", errors="replace").rstrip())
        if len(stderr_lines) > stderr_tail:
            del stderr_lines[:-stderr_tail]

stderr_thread = threading.Thread(target=_drain, daemon=True)
stderr_thread.start()
```

- **`stderr_lines: list[str] = []`** — uma lista vazia que vai acumular as linhas de log do stderr.
- **`def _drain()`** — uma função *aninhada* (definida dentro de `run_ffmpeg`). Ela enxerga a
  variável `stderr_lines` da função externa — isso se chama *closure* (fechamento).
- **`for raw in proc.stderr:`** — itera sobre as linhas que o ffmpeg escreve no stderr, uma a uma,
  em **bytes** (`raw`).
- **`raw.decode("utf-8", errors="replace").rstrip()`** — decodifica os bytes para texto usando
  UTF-8; se algum byte for inválido, `errors="replace"` o troca por `�` em vez de lançar erro.
  `.rstrip()` remove espaços/quebras à direita.
- **`if len(stderr_lines) > stderr_tail: del stderr_lines[:-stderr_tail]`** — se a lista passou de
  100 linhas, apaga tudo **menos** as últimas 100. A fatia `[:-stderr_tail]` significa "do começo
  até 100 antes do fim"; `del` remove esse pedaço. Resultado: a lista nunca cresce sem limite, e
  guarda sempre o *fim* do log (que é onde estão as mensagens de erro úteis).
- **`threading.Thread(target=_drain, daemon=True)`** — cria uma thread que vai rodar `_drain` em
  paralelo. `daemon=True` = "thread de fundo, pode ser morta quando o programa acabar".
- **`.start()`** — dispara a thread.

🔑 **Por que uma thread inteira só para isso?** Este é o coração do arquivo. O ffmpeg escreve em
**dois** canais ao mesmo tempo — progresso no stdout, logs no stderr. Cada cano é um *buffer* de
tamanho fixo. Se o código lesse só o stdout e ignorasse o stderr, numa conversão longa o buffer do
stderr encheria; **quando um buffer enche, o ffmpeg é obrigado a parar e esperar espaço** — e,
parado, deixa de mandar progresso pelo stdout; o Python, por sua vez, espera progresso que nunca
chega. Os dois congelam esperando um ao outro: um **deadlock**, e a conversão pendura para sempre.
A thread resolve isso lendo o stderr *em paralelo*, mantendo aquele buffer sempre vazio. (Analogia:
pia com duas torneiras e um ralo só transborda; a thread é o segundo ralo.)

### Bloco 3 — ler o progresso do stdout

```python
for raw in proc.stdout:
    line = raw.decode("utf-8", errors="replace").strip()
    if line.startswith("out_time_us=") and progress_cb and total_secs:
        try:
            ratio = min(int(line.split("=", 1)[1]) / 1_000_000 / total_secs, 1.0)
            progress_cb(ratio)
        except (ValueError, IndexError):
            pass
```

Para isso funcionar, o `cmd` do chamador inclui a flag `-progress pipe:1`, que faz o ffmpeg emitir
o andamento em linhas legíveis pelo stdout, como `out_time_us=5000000` (5 segundos, em
microssegundos).

- **`for raw in proc.stdout:`** — lê o stdout linha a linha, em bytes.
- **`line = raw.decode(...).strip()`** — vira texto limpo.
- **`if line.startswith("out_time_us=") and progress_cb and total_secs:`** — só age se a linha for
  de progresso **e** houver um callback para chamar **e** a duração total for conhecida. Se qualquer
  um faltar, ignora. (Repare: `progress_cb` e `total_secs` sendo `None` fazem a condição ser falsa —
  é assim que a função "desliga" o progresso quando ninguém pediu.)
- **`int(line.split("=", 1)[1])`** — `split("=", 1)` corta a linha no primeiro `=`, dando
  `["out_time_us", "5000000"]`; `[1]` pega o segundo pedaço; `int(...)` converte para número.
- **`/ 1_000_000 / total_secs`** — microssegundos → segundos (÷1.000.000), depois segundos ÷ duração
  total = razão de progresso (ex.: 0.25). O `_` em `1_000_000` é só separador visual de milhar.
- **`min(..., 1.0)`** — trava o teto em 1.0 (100%), pois arredondamentos podem passar um pouquinho.
- **`progress_cb(ratio)`** — **chama o callback** com o número. Aqui o core "avisa a GUI" sem
  conhecê-la.
- **`except (ValueError, IndexError): pass`** — se uma linha vier malformada (conversão falha, índice
  não existe), engole o erro silenciosamente. Uma linha ruim não deve derrubar a conversão inteira.

🔑 **O `progress_cb(ratio)` é a regra de injeção de dependência em ação.** O `run_ffmpeg` não sabe se
esse callback move uma barrinha (GUI), atualiza um `tqdm` (CLI) ou anota valores numa lista (teste).
Ele só empurra o número; quem passou o callback decide o significado. É por isso que **o mesmo**
`run_ffmpeg` serve GUI, CLI e testes sem depender de nenhum.

### Bloco 4 — esperar e validar

```python
proc.wait()
stderr_thread.join(timeout=2)

if proc.returncode != 0:
    tail = "\n".join(stderr_lines[-10:]) if stderr_lines else "(no details)"
    raise RuntimeError(f"ffmpeg returned {proc.returncode}: {tail}")

if not out_path.exists():
    raise FileNotFoundError(f"ffmpeg finished but output not found: {out_path}")

return out_path
```

- **`proc.wait()`** — bloqueia até o ffmpeg terminar de verdade.
- **`stderr_thread.join(timeout=2)`** — espera a thread do stderr encerrar (no máximo 2 segundos, para
  não travar caso ela emperre).
- **`if proc.returncode != 0:`** — o *returncode* (código de saída) de um processo é `0` para sucesso
  e qualquer outro número para erro. Se não for 0, algo deu errado.
  - **`"\n".join(stderr_lines[-10:])`** — pega as **últimas 10** linhas do log (`[-10:]`) e as junta
    com quebras de linha. Mensagem de erro útil e enxuta, não um despejo gigante.
  - **`raise RuntimeError(...)`** — levanta o erro com essa mensagem.
- 🔑 **`if not out_path.exists():`** — a segunda checagem, sutil e importante. Às vezes o ffmpeg
  retorna 0 ("sucesso") mas **não gera** o arquivo (parâmetros estranhos, filtro que não produziu
  saída). Confirmar que o arquivo existe fecha esse buraco. Levanta `FileNotFoundError` — um tipo de
  erro *diferente* do de returncode, para o chamador distinguir os dois casos.
- **`return out_path`** — sucesso: devolve o caminho pronto.

---

## O quirk do `cwd` (uma decisão de plataforma disfarçada de parâmetro)

🔑 O parâmetro `cwd` parece inofensivo, mas carrega uma história. No módulo Vídeo, a operação de
"queimar" legenda no vídeo (*burn-in*) usa o filtro `subtitles=arquivo.srt` do ffmpeg. Esse filtro
interpreta o caractere `:` como separador de seus próprios argumentos — e o `:` do caminho do
Windows (`C:\videos\...`) quebra o parser do filtro. A solução foi: rodar o ffmpeg **dentro** da
pasta da legenda (passando `cwd=pasta`) e referenciar o arquivo só pelo nome (basename), sem a letra
de drive. Assim não há `:` no argumento do filtro. Um parâmetro genérico que existe por causa de um
detalhe muito específico do Windows.

---

## Lições transversais deste arquivo

1. **Fonte única.** Todo acesso ao ffmpeg passa por aqui → um lugar só para consertar bugs de
   subprocess, encoding e progresso.
2. **Core puro + callback.** A função não conhece GUI nem CLI; recebe `progress_cb` e o chama. Este
   é *o* padrão que se repete em todo módulo do projeto.
3. **Robustez em duas frentes.** Valida returncode **e** existência do arquivo — sucesso aparente não
   é sucesso real.
4. **Defensividade seletiva.** Engole erros de parse de uma linha (`pass`), mas levanta erro alto e
   claro quando o processo inteiro falha.

---

## Glossário deste arquivo

**Processo** — um programa em execução, com memória própria e isolado. O ffmpeg roda como processo
separado do seu app.

**`subprocess` / `Popen`** — módulo e classe do Python para lançar e controlar outro processo. `Popen`
devolve um objeto para ler saídas, esperar e checar o código de saída.

**stdout / stderr** — os dois canais de saída de um processo. stdout = saída normal (aqui, o
progresso); stderr = erros e logs. Separados de propósito.

**Pipe (cano) / buffer** — o `PIPE` é o canal por onde você lê a saída do processo; ele é um *buffer*
(memória de tamanho fixo). Se enche e ninguém lê, quem escreve trava esperando espaço.

**Deadlock (impasse)** — dois lados travados esperando um ao outro para sempre. Aqui: ffmpeg esperando
esvaziar o stderr, Python esperando progresso no stdout. Resolvido lendo os dois canais em paralelo.

**Thread** — uma "mão" extra de execução paralela dentro do mesmo processo. A thread `_drain` lê o
stderr enquanto o fluxo principal lê o stdout.

**Daemon thread** — thread de fundo que o programa encerra automaticamente ao sair, sem esperá-la.

**Callback** — uma função passada como argumento para outra chamar no momento certo. `progress_cb` é
o callback de progresso: `run_ffmpeg` o chama a cada avanço.

**Closure (fechamento)** — uma função aninhada que "enxerga" variáveis da função que a contém.
`_drain` acessa `stderr_lines` por closure.

**returncode (código de saída)** — número que um processo devolve ao terminar: `0` = sucesso, outro =
erro.

**Encoding / UTF-8 / cp1252 / `errors="replace"`** — regras de conversão bytes↔texto. UTF-8 é o padrão
universal; cp1252 é o antigo do console Windows. `errors="replace"` troca um byte inválido por `�` em
vez de quebrar.

**`Path` (pathlib)** — objeto que representa um caminho de arquivo, com métodos como `.exists()`.

**`Callable[[float], None]`** — anotação de tipo: "função que recebe um `float` e retorna `None`".

**Operador ternário (`A if cond else B`)** — um `if` numa expressão só. `str(cwd) if cwd else None`.

**Type hint / `X | None`** — dica de tipo; `| None` marca o valor como opcional (pode ser `None`).
