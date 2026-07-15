# Padrões de decomposição — como o projeto quebra arquivos grandes

Documento de conceito sobre **como** o mill.tools divide arquivos que crescem demais, sem virar
bagunça. Estes padrões (`blocks/`, `tabs/`, `_state.py`, `registry/`, `pipeline_log.py`) se repetem em
Imagem, Documentos, Áudio, Dados e Receitas — então valem uma explicação única, referenciada pelos
delta docs de módulo. Todo exemplo é código real. Glossário no fim.

> **Pré-requisito:** [`FLET_GUI.md`](FLET_GUI.md) §4.2 (o truque de closure `[valor]` e as fábricas
> que devolvem "controle + acessores"). Aqui generalizamos esse padrão para a escala de um módulo.

---

# PARTE 1 — O problema: tamanho e coesão

A skill `architecture` define uma régua dupla (tamanho **e** coesão). Um builder de GUI passa de ~400
linhas, ou um arquivo reúne "mundos" diferentes (várias abas, adaptadores de vários módulos), e vira
candidato a divisão. 🔑 A régua não é só tamanho: um arquivo de 300 linhas com **uma** responsabilidade
está ok; um de 250 que mistura três abas distintas, não. Os dois sintomas juntos é que reprovam.

A regra operacional é **"divide-se ao tocar"**: não refatore a base inteira preventivamente; divida um
arquivo grande **no momento** em que um plano for estendê-lo.

---

# PARTE 2 — O princípio comum a todos os padrões

Todos os padrões abaixo compartilham **uma** ideia. Cada sub-builder:

> **devolve o controle E seus acessores/handlers**; o builder principal só monta o estado
> compartilhado e **encaixa** as partes.

Você já viu isso em miniatura no `segmented_selector` ([`FLET_GUI.md`](FLET_GUI.md) §4.2), que devolve
`(grid, get_value, set_disabled)`. Na escala de um módulo, isso vira um arquivo por bloco, cada um
expondo suas funções de leitura/escrita via uma **`NamedTuple` de acessores**.

---

# PARTE 3 — `blocks/` — quebrar um formulário grande

O padrão mais comum. Um formulário com muitas seções vira uma pasta `blocks/`, um arquivo por seção.
Cada bloco é `build_X_block(page) → (controle, XRefs)`, onde `XRefs` é uma `NamedTuple` de funções
`get_*`/`set_*`.

Exemplo real, `gui/modules/image/blocks/crop.py`:

```python
class CropRefs(NamedTuple):
    get_mode: Callable[[], str]
    get_left: Callable[[], int]
    get_width: Callable[[], int]
    get_ratio: Callable[[], str]
    ...

def build_crop_block(page: ft.Page) -> tuple[ft.Column, CropRefs]:
    """Build the crop operation block. Returns the Column and a CropRefs for value collection."""
    left_tf = ft.TextField(hint_text="Esquerda px", value="0", ...)
    ...
    return coluna, CropRefs(get_mode=..., get_left=lambda: _parse_int(left_tf, 0), ...)
```

🔑 Anatomia:
- **`CropRefs(NamedTuple)`** — o "contrato" do bloco: quais valores ele sabe entregar. Uma `NamedTuple`
  (tupla com campos nomeados) é imutável e auto-documentada — o builder principal lê `refs.get_left()`
  sem saber **como** o bloco guarda o valor.
- **`build_crop_block(page) → (ft.Column, CropRefs)`** — devolve **o widget** (para encaixar no
  layout) **e os acessores** (para coletar os valores na hora de montar os `Args`). Essa separação é a
  chave: o layout e a coleta de dados ficam desacoplados.
- Os `get_*` são **closures** sobre os campos do formulário (`lambda: _parse_int(left_tf, 0)`) — leem o
  valor atual do `TextField` quando chamados.

Blocos podem ter **setters** também, quando a UI precisa mudar programaticamente. Veja
`audio/blocks/denoise.py`:

```python
class DenoiseRefs(NamedTuple):
    get_denoise: Callable[[], bool]
    get_stationary: Callable[[], bool]
    set_stationary: Callable[[bool], None]      # ← setter (ex.: aplicar um preset)
    set_denoise: Callable[[bool], None]
    set_disabled: Callable[[bool], None]         # ← desabilitar durante o pipeline

def build_denoise_block(page, cfg) -> tuple[ft.Control, DenoiseRefs]:
    ...
    def _set_disabled(running: bool) -> None:
        denoise_switch.disabled = running
        _set_mode_disabled(running)
    return control, DenoiseRefs(get_denoise=lambda: bool(denoise_switch.value), ..., set_disabled=_set_disabled)
```

🔑 O `set_disabled` aparece em quase todo bloco: é como o formulário inteiro se "congela" durante o
pipeline (o worker roda; o form desabilita). O builder principal chama `refs.set_disabled(True)` em
cada bloco de uma vez. Note também o padrão de **revelar** o seletor de modo só quando o denoise está
ligado (`mode_block.visible = ...` + `mode_block.update()` escopado — a regra de repintura do
[`FLET_GUI.md`](FLET_GUI.md) §3.1).

---

# PARTE 4 — `tabs/` — quebrar um painel multi-aba

Quando o painel não é um formulário linear, mas várias **abas** (como o módulo Dados:
Consulta·Pré-visualização·Análise·Gráfico), cada aba vira `build_X_tab(...) → (controle, refs/handlers)`
numa pasta `tabs/`. Mesma ideia dos blocos, mas a unidade é uma aba inteira. É a resposta ao antigo
`data/view.py` que tinha 47 closures e 3 abas num arquivo só.

Lembre ([`FLET_GUI.md`](FLET_GUI.md) §quirks): `ft.Tabs` **não existe** no Flet 0.85 — as abas são
`TextButton` + `visible=` num `ft.Stack`. Então "aba" aqui é uma convenção do projeto, não um controle
do Flet.

---

# PARTE 5 — `_state.py` — estado compartilhado entre abas/blocos

Quando várias abas/blocos precisam **dividir** estado (um cronômetro, a seleção de fonte, um helper de
repintura escopada), esse estado sai para um `_state.py` próprio, em vez de virar variáveis soltas no
builder gigante. Existe no módulo Dados (`gui/modules/data/_state.py`). É o "quarto" onde mora o que é
transversal às partes — para nenhuma aba precisar conhecer os detalhes internos da outra.

---

# PARTE 6 — `registry/<módulo>.py` — coleções de adaptadores

Um caso diferente: quando um arquivo reúne **handlers/adaptadores de vários módulos** (o antigo
`recipes/registry.py` com 33 adaptadores de 7 módulos), ele vira uma pasta `registry/`, um arquivo por
módulo (`registry/audio.py`, `registry/video.py`...), e um `__init__` que monta o registro completo. É
a decomposição por **origem** (de qual módulo vem cada peça), não por seção de UI. Você vê isso nas
Receitas (Sessão 5).

---

# PARTE 7 — `pipeline_log.py` — separar "o que emitir" de "como exibir"

Um padrão presente em **todo** módulo: as funções de formatação de mensagem de log
(`fmt_convert_detail`, `fmt_denoise_start`...) moram num `pipeline_log.py` separado do worker. O worker
decide **o que** logar (`emit("log", {"message": pipeline_log.fmt_convert_detail(...)})`); o
`pipeline_log` decide **como** o texto fica. Assim o worker fica enxuto e as mensagens ficam num lugar
só, fáceis de ajustar. (Você viu isso no worker do Vídeo, Sessão 2 §3.2.)

---

# PARTE 8 — Resumo: qual padrão para qual sintoma

| Sintoma | Padrão | Onde ver |
|---|---|---|
| Formulário grande, muitas seções | **`blocks/`** — `build_X_block → (Column, XRefs)` | `image/blocks/`, `audio/blocks/`, `document/blocks/` |
| Painel com várias abas | **`tabs/`** — `build_X_tab → (controle, refs)` | `data/tabs/` |
| Aba pesada e autônoma | **`index_tab.py`** — a aba num arquivo próprio | `ai/index_tab.py` |
| Estado dividido entre abas/blocos | **`_state.py`** | `data/_state.py` |
| Adaptadores de vários módulos | **`registry/<módulo>.py`** + `__init__` | `recipes/registry/` |
| Mensagens de log/evento | **`pipeline_log.py`** (`fmt_*`) | todos os módulos |

🔑 O fio comum, de novo: **cada parte devolve seu controle + seus acessores; o builder principal só
encaixa.** Quando você abrir qualquer módulo da Sessão 4 e vir uma pasta `blocks/` ou `tabs/`, já sabe
o formato: procure a `NamedTuple` de refs de cada arquivo, e o builder que as junta.

---

# Glossário

**Régua de tamanho/coesão** — o critério da skill `architecture`: um arquivo reprova quando é grande
**e** de baixa coesão (mistura responsabilidades). "Divide-se ao tocar", não preventivamente.

**Builder** — uma função que **monta** uma parte da UI (`build_X_module`, `build_X_block`,
`build_X_tab`). Devolve o controle e, geralmente, acessores.

**`blocks/`** — pasta onde cada seção de um formulário grande vira um arquivo `build_X_block(page) →
(controle, XRefs)`.

**`XRefs` (NamedTuple de acessores)** — o "contrato" de um bloco: uma tupla nomeada de funções
`get_*`/`set_*` que o builder principal usa para ler/escrever os valores do bloco sem conhecer seus
detalhes internos.

**`NamedTuple`** — uma tupla com campos nomeados (`refs.get_left`), imutável e auto-documentada.

**Getter / setter** — funções que **leem** (`get_*`) ou **escrevem** (`set_*`) um valor. Aqui são
closures sobre os campos do formulário.

**`set_disabled`** — o setter comum a quase todo bloco, que desabilita os controles durante o pipeline.

**`tabs/`** — pasta onde cada aba de um painel multi-aba vira `build_X_tab(...) → (controle, refs)`.

**`_state.py`** — arquivo com o estado transversal compartilhado entre abas/blocos (cronômetros,
seleção, helpers de repintura).

**`registry/<módulo>.py`** — decomposição por origem: um arquivo por módulo reunindo seus adaptadores,
montados por um `__init__`.

**`pipeline_log.py`** — o arquivo que separa a formatação das mensagens (`fmt_*`) da lógica do worker.

**Closure** — função interna que "lembra" variáveis do escopo externo; a base dos `get_*`/`set_*`
(ver [`FLET_GUI.md`](FLET_GUI.md) §4.2).

---

# Perguntas de fixação

1. Por que `build_crop_block` devolve **dois** valores — o `ft.Column` e o `CropRefs`? O que cada um
   serve?
2. O que é uma `NamedTuple` de refs, e por que ela desacopla o builder principal do bloco?
3. Quase todo bloco expõe um `set_disabled`. Para que ele serve, e quem o chama?
4. Qual a diferença entre decompor em `blocks/` e em `registry/`? (dica: por seção de UI vs. por
   origem)
5. Ligue ao `segmented_selector` do [`FLET_GUI.md`](FLET_GUI.md): em que sentido `blocks/` é "o mesmo
   padrão, uma escala acima"?
