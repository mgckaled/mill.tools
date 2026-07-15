# `src/llm_factory.py` — a fábrica de modelos de linguagem

> **Papel no projeto:** o **ponto único** por onde toda chamada a um modelo de linguagem (LLM) passa.
> Uma função, `make_llm(...)`, recebe o nome de um modelo e decide qual provedor instanciar — Ollama
> local, Google Gemini ou Zhipu GLM — devolvendo sempre um objeto LangChain uniforme. Todos os
> consumidores (formatter, analyzer, prompter, chat do RAG, `data.assess`, `data.nl2sql`, descrição
> de imagem) usam a mesma porta.
>
> É a materialização de dois princípios: **fonte única** (um só lugar decide o provedor e instrumenta
> tempo) e **injeção de dependência** (quem chama não sabe nem se importa com qual provedor rodou).
>
> **Pré-requisitos conceituais:** LLM, LangChain, provedor/API, variável de ambiente, import
> preguiçoso, callback, `TYPE_CHECKING`. Todos no Glossário ao final.

---

## O conceito central: "factory" (fábrica)

🔑 *Factory* é um **padrão de projeto**: uma função cujo trabalho é **construir e devolver o objeto
certo** conforme a situação, escondendo do chamador os detalhes de qual classe concreta foi criada.
Aqui, o chamador diz apenas `make_llm("gemini-2.5-flash")` ou `make_llm("qwen7b-custom")` e recebe de
volta "um modelo de chat que responde `.invoke(...)`". Se é Gemini na nuvem ou Ollama na sua máquina,
ele nem precisa saber. Trocar de provedor é trocar uma string.

**Por que isso é valioso:** o projeto nasceu 100% local (Ollama). Adicionar Gemini e GLM sem essa
fábrica exigiria espalhar `if provedor == ...` por dezenas de arquivos. Com ela, a decisão vive num
lugar só, e o resto do código continua igual.

---

## A docstring de módulo (leia-a: ela é o mapa)

```python
"""
llm_factory.py: Provider-agnostic LLM factory.

Single entry point `make_llm()` decides which LangChain chat model to instantiate
based on the model name passed via CLI flags (--fm / --am / --pm). ...
`make_llm()` is also the single funnel every text/vision LLM call ... goes through ...
so it is the one place a `domain`-tagged timing callback ... can observe every call ...
"""
```

Dois pontos-chave já anunciados aqui: (1) o **roteamento é por prefixo do nome** (`gemini*` → Google,
`glm*` → Zhipu, resto → Ollama); (2) por ser o funil único, é o lugar perfeito para **cronometrar**
toda chamada sem tocar em cada consumidor. Guarde essas duas ideias — o arquivo inteiro as executa.

---

## Imports e o truque do `TYPE_CHECKING`

```python
import logging, os, time
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from dotenv import load_dotenv
from langchain_core.callbacks import BaseCallbackHandler

if TYPE_CHECKING:  # avoid hard import at module load — keeps Ollama-only runs fast
    from langchain_core.language_models.chat_models import BaseChatModel
```

- **`load_dotenv`** — da biblioteca `python-dotenv`; carrega variáveis de um arquivo `.env` (onde
  ficam as chaves de API) para dentro do ambiente do processo.
- **`BaseCallbackHandler`** — a classe base do LangChain para "ganchos" que observam o ciclo de vida
  de uma chamada (início, fim, erro). Vamos herdar dela no `_TimingCallback`.
- 🔑 **`if TYPE_CHECKING:`** — `TYPE_CHECKING` é uma constante que vale `False` em tempo de execução,
  mas `True` para as ferramentas de checagem de tipo. Ou seja: o import de `BaseChatModel` **nunca
  roda de verdade** — ele existe só para as anotações de tipo (`-> "BaseChatModel"`) fazerem sentido
  para o editor/checador. Combinado com `from __future__ import annotations` (que torna as anotações
  texto), isso permite anotar tipos "pesados" **sem pagar o custo de importá-los**. O comentário diz
  o porquê: manter rápida a partida de quem só usa Ollama. As aspas em `"BaseChatModel"` (uma *forward
  reference*) reforçam: é um tipo referido por nome, não avaliado.

---

## Constantes de roteamento e defaults

```python
GEMINI_PREFIXES = ("gemini",)
GEMINI_DEFAULT_MAX_RETRIES = 3
GEMINI_DEFAULT_TIMEOUT = 120

GLM_PREFIXES = ("glm",)
GLM_BASE_URL = "https://api.z.ai/api/paas/v4/"
GLM_DEFAULT_MAX_RETRIES = 3
GLM_DEFAULT_TIMEOUT = 120

DEFAULT_OLLAMA_NUM_CTX = 8192
```

- **`GEMINI_PREFIXES = ("gemini",)`** — uma *tupla* com um item (a vírgula é obrigatória para ser
  tupla e não só um parêntese). O roteamento testa se o nome do modelo **começa** com esse prefixo.
- **`MAX_RETRIES` / `TIMEOUT`** — quantas vezes reenviar se a API falhar, e quanto esperar (segundos)
  antes de desistir. As nuvens recebem 3 tentativas e 120s.
- **`GLM_BASE_URL`** — a GLM é acessada por uma API **compatível com OpenAI**; por isso usamos o
  cliente `ChatOpenAI` apontado para o servidor da Zhipu (detalhe adiante).
- 🔑 **`DEFAULT_OLLAMA_NUM_CTX = 8192`** — a *janela de contexto* (quantos tokens o modelo enxerga de
  uma vez). O padrão do Ollama é 2048, **pequeno demais**: o JSON verboso que o analyzer/prompter
  emitem estoura esse limite e é **cortado no meio**, virando JSON inválido. Subir para 8192 evita o
  truncamento. O comentário no código explica ainda que manter o valor **uniforme** impede o Ollama
  de recarregar o modelo toda vez que uma chamada grande e uma pequena se alternam. **Regra de ouro:
  edite esta constante, não o slider do app Ollama** (a constante vence, por precedência).

---

## Os helpers de roteamento (privados e públicos)

```python
def _is_gemini(model_name: str) -> bool:
    return model_name.lower().startswith(GEMINI_PREFIXES)

def is_gemini_model(model_name: str) -> bool:
    return _is_gemini(model_name)
```

(e os análogos `_is_glm` / `is_glm_model`, mais `is_cloud_model`.)

- **`.lower().startswith(GEMINI_PREFIXES)`** — normaliza para minúsculas e testa se começa com algum
  prefixo da tupla (`.startswith` aceita uma tupla e retorna `True` se **qualquer** um casar).
- 🔑 **Por que existe um `_is_gemini` "privado" E um `is_gemini_model` "público" que só o chama?**
  A convenção do projeto: o `_` no início marca "uso interno deste arquivo". A versão sem `_` é a
  **API pública**, para outros módulos (`analyzer.py`, `prompter.py`) perguntarem "esse modelo é
  Gemini?" sem depender de um detalhe interno. Ter as duas separa "como eu decido aqui dentro" de "o
  que eu prometo lá fora" — se um dia a lógica interna mudar, a API pública continua estável.

```python
def is_cloud_model(model_name: str) -> bool:
    return _is_gemini(model_name) or _is_glm(model_name)
```

- 🔑 **`is_cloud_model`** é a distinção que mais importa em vários pontos: "roda local (Ollama)" vs.
  "sai para uma API externa". É usada para (a) pular o fatiamento de contexto em modelos de nuvem, que
  têm janelas gigantes, e (b) mostrar um aviso de privacidade na GUI quando o texto vai sair da
  máquina.

```python
def long_context_char_budget(model_name: str) -> int | None:
    return LONG_CONTEXT_LOCAL_BUDGETS.get(model_name)
```

- **`LONG_CONTEXT_LOCAL_BUDGETS`** é um dicionário `{"gemma3-4b-custom": 12_000}`. `.get(chave)`
  devolve o valor se a chave existe ou `None` se não. 🔑 A ideia: modelos **locais** com janela grande
  podem processar entradas curtas/médias numa passada só (sem fatiar), mas há um **teto em
  caracteres** porque uma passada gigante numa CPU fraca fica lenta demais; acima do teto, volta a
  fatiar. Nuvens não entram aqui (bypass incondicional via `is_cloud_model`).

---

## `_load_env_once` — carregar as chaves de API

```python
def _load_env_once() -> None:
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    load_dotenv(env_path)
```

- Acha o arquivo `.env` na raiz do projeto (mesma técnica `__file__ → parent.parent` de `utils.py`)
  e o carrega. O `.env` contém linhas como `GOOGLE_API_KEY=...`.
- 🔑 **"once" (uma vez)** — `load_dotenv` é *idempotente*: chamá-lo de novo não faz mal (não
  recarrega/sobrescreve). Por isso pode ser chamado no início de cada `_make_*` sem custo. As chaves
  **não** são hardcoded no código — ficam no `.env`, que não vai para o controle de versão. Segurança
  básica de segredos.

---

## `_TimingCallback` — cronometrar cada chamada sem tocar em ninguém

```python
class _TimingCallback(BaseCallbackHandler):
    def __init__(self, model_name: str, domain: str) -> None:
        self._model_name = model_name
        self._domain = domain
        self._starts: dict[UUID, float] = {}

    def on_llm_start(self, serialized, prompts, *, run_id: UUID, **kwargs) -> None:
        self._starts[run_id] = time.monotonic()

    def on_llm_end(self, response, *, run_id: UUID, **kwargs) -> None:
        t0 = self._starts.pop(run_id, None)
        if t0 is not None:
            from src.core.observatory.model_timing import record_timing
            record_timing(self._model_name, self._domain, time.monotonic() - t0)

    def on_llm_error(self, error, *, run_id: UUID, **kwargs) -> None:
        self._starts.pop(run_id, None)  # descarta — não registra chamadas que falharam
```

🔑 **A grande sacada deste arquivo.** LangChain permite anexar *callbacks* a um modelo; ele chama
`on_llm_start` quando uma requisição começa e `on_llm_end` quando termina — **automaticamente**, sem
você instrumentar cada `.invoke()`. Como `make_llm` é o funil único, anexar este callback ali
significa cronometrar **toda** chamada de LLM do projeto de um lugar só.

Anatomia:
- **`class _TimingCallback(BaseCallbackHandler)`** — herda do handler base do LangChain e sobrescreve
  os ganchos que interessam.
- **`__init__`** — o *construtor*; guarda o nome do modelo, o "domínio" (bucket de medição: `"llm"`,
  `"vlm"` para visão, `"embed"`) e um dicionário `_starts` vazio.
- **`self._starts: dict[UUID, float]`** — mapeia `run_id` (um identificador único de cada chamada,
  do tipo `UUID`) → o instante de início. 🔑 **Por que por `run_id` e não uma variável só?** Um
  mesmo objeto-modelo pode ser reusado em várias chamadas em sequência (o analyzer fatia um texto
  grande e chama o modelo N vezes). Chavear por `run_id` cronometra **cada** chamada
  independentemente, sem uma sobrescrever o início da outra.
- **`time.monotonic()`** — um relógio que **só avança** e é imune a ajustes do relógio do sistema
  (fuso, sincronização). É o certo para medir *duração* (diferente de `time.time()`, que pode
  "voltar no tempo").
- **`on_llm_end`** — recupera o início com `.pop(run_id, None)` (pega e remove; `None` se não achar),
  e se havia um início, chama `record_timing(modelo, domínio, duração)`.
- 🔑 **`from ... import record_timing` DENTRO do método** — um *import preguiçoso* (lazy). Só carrega
  o módulo de observabilidade quando uma chamada realmente termina, evitando um import circular
  (llm_factory ↔ observatory) e mantendo a partida leve.
- **`on_llm_error`** — se a chamada falhou, descarta o início e **não registra** (medir uma falha
  poluiria a estatística de latência).

```python
def timing_callbacks(model_name: str, domain: str) -> list[BaseCallbackHandler]:
    return [_TimingCallback(model_name, domain)]
```

- Uma função pública que embrulha a criação do callback numa lista (o formato que o LangChain
  espera). É pública para que um chamador que monte um modelo **sem** passar por `make_llm` (o ramo
  Ollama local de `describe.py`) possa anexar a **mesma** instrumentação.

---

## Os três construtores `_make_*` — um por provedor

Os três seguem a mesma forma. Vejamos o Gemini como representante:

```python
def _make_gemini(model_name, temperature, callbacks=None) -> "BaseChatModel":
    _load_env_once()
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY não encontrada. Crie um arquivo .env ...")

    from langchain_google_genai import ChatGoogleGenerativeAI  # lazy import

    logging.debug("[d] Provider: Google Gemini | model=%s | temperature=%.2f", model_name, temperature)
    return ChatGoogleGenerativeAI(
        model=model_name, temperature=temperature, google_api_key=api_key,
        max_retries=GEMINI_DEFAULT_MAX_RETRIES, timeout=GEMINI_DEFAULT_TIMEOUT, callbacks=callbacks,
    )
```

- **`_load_env_once()` + `os.getenv("GOOGLE_API_KEY")`** — carrega o `.env` e lê a chave. `os.getenv`
  devolve `None` se a variável não existe.
- 🔑 **`if not api_key: raise RuntimeError(...)`** — se falta a chave, falha **imediatamente** com uma
  mensagem que ensina exatamente o que fazer (criar `.env`, onde gerar a chave). Note que a mensagem
  está **em português**: é a exceção da regra de idioma — mensagens de erro *user-facing* do core
  podem ser em PT, pois chegam cruas à tela do usuário (regra nº 3).
- 🔑 **`from langchain_google_genai import ChatGoogleGenerativeAI` dentro da função** — outro *import
  preguiçoso*. A biblioteca do Google só é carregada se o usuário **de fato** optar por Gemini. Quem
  usa só Ollama nunca paga o custo de importar as libs de nuvem. Este é o padrão do projeto: import
  pesado sempre lazy (regra de partida rápida).
- **`logging.debug("[d] Provider: ...")`** — registra qual provedor foi escolhido (só em modo
  verboso).
- **`return ChatGoogleGenerativeAI(...)`** — instancia o modelo LangChain com os defaults do projeto
  e os `callbacks` (o cronômetro). Devolve um objeto que responde à interface comum de chat.

**Diferenças dos outros dois:**
- **`_make_glm`** usa `ZHIPU_API_KEY` e instancia `ChatOpenAI` apontado para `base_url=GLM_BASE_URL`.
  🔑 Por quê `ChatOpenAI` e não um cliente GLM próprio? A API da Zhipu é *compatível com a da OpenAI*,
  então reusar o cliente `ChatOpenAI` (maduro e bem mantido) evita depender do cliente legado da
  Zhipu. Um truque de compatibilidade elegante.
- **`_make_ollama`** não precisa de chave (é local). Recebe `num_ctx` e passa
  `client_kwargs={"timeout": 300.0}` — um timeout de leitura de 300s repassado ao cliente HTTP
  subjacente, para que `.invoke()` não fique **pendurado para sempre** se o Ollama travar. Também é
  um import preguiçoso (`from langchain_ollama import ChatOllama`), mantendo o Ollama opcional para
  ambientes que só usam nuvem.

---

## `make_llm` — a porta única

```python
def make_llm(model_name, temperature=0.0, num_ctx=DEFAULT_OLLAMA_NUM_CTX, *, domain="llm") -> "BaseChatModel":
    callbacks = timing_callbacks(model_name, domain)
    if _is_gemini(model_name):
        return _make_gemini(model_name, temperature, callbacks)
    if _is_glm(model_name):
        return _make_glm(model_name, temperature, callbacks)
    return _make_ollama(model_name, temperature, num_ctx, callbacks)
```

O clímax, e é curtíssimo — sinal de bom design. Toda a complexidade foi empurrada para os helpers; a
função que todos chamam é trivial de ler.

- **`temperature=0.0`** — a "criatividade" do modelo. 🔑 `0.0` = **determinístico** (mesma entrada
  tende à mesma saída), ideal para tarefas estruturadas (JSON, extração). Valores maiores (até ~1.0)
  = mais variação/criatividade. O default 0.0 reflete que a maioria dos usos aqui quer previsibilidade.
- **`*, domain="llm"`** — de novo o `*`: `domain` só por nome. É o *bucket* de cronometragem; a
  descrição de imagem passa `domain="vlm"` explicitamente.
- **`callbacks = timing_callbacks(...)`** — monta o cronômetro **antes** de rotear, e o repassa a
  qualquer que seja o provedor. Assim, **toda** chamada é medida, não importa o caminho.
- **O roteamento** — três `if` por prefixo, com o Ollama como *fallback* (o "senão" final). Preserva a
  compatibilidade histórica: qualquer nome que não seja de nuvem cai no local, como era no início do
  projeto.

---

## Lições transversais deste arquivo

1. **Padrão Factory.** Uma função constrói o objeto certo e esconde o "qual classe" do chamador.
   Trocar de provedor = trocar uma string.
2. **Funil único = instrumentação única.** Por tudo passar por `make_llm`, dá para cronometrar cada
   chamada (e, no futuro, aplicar qualquer política transversal) sem tocar nos consumidores.
3. **Import preguiçoso em todo lugar.** Libs de nuvem e de Ollama só carregam quando usadas → partida
   rápida e dependências opcionais de verdade.
4. **Segredos fora do código.** Chaves vêm do `.env`; ausência falha cedo com instrução clara.
5. **Determinismo por padrão.** `temperature=0.0` porque as tarefas do projeto querem saídas estáveis.

---

## Glossário deste arquivo

**LLM (Large Language Model)** — modelo de linguagem que recebe texto e gera texto (responder,
resumir, formatar). Aqui, acessado via LangChain.

**LangChain** — biblioteca que dá uma interface **uniforme** para muitos provedores de LLM. Um objeto
LangChain de chat responde a `.invoke(...)` seja ele Gemini, GLM ou Ollama.

**Provedor / API** — quem hospeda o modelo. Local (Ollama, na sua máquina) ou nuvem (Google Gemini,
Zhipu GLM, acessados por rede via API).

**Factory (fábrica)** — padrão de projeto: função que constrói e devolve o objeto adequado à
situação, escondendo a classe concreta do chamador.

**Roteamento por prefixo** — decidir o provedor pelo começo do nome do modelo (`gemini*`, `glm*`,
resto → Ollama).

**Variável de ambiente / `.env` / `python-dotenv`** — valores de configuração (como chaves de API)
guardados fora do código. O arquivo `.env` na raiz é carregado por `load_dotenv` para o ambiente do
processo.

**Import preguiçoso (lazy import)** — importar uma biblioteca **dentro** da função que a usa, em vez
de no topo do arquivo, para só pagar o custo quando o recurso é acionado. Mantém a partida rápida e as
dependências opcionais.

**`TYPE_CHECKING`** — constante que é `False` em runtime e `True` para checadores de tipo. Imports sob
`if TYPE_CHECKING:` servem só às anotações, sem rodar de verdade.

**Forward reference (`"BaseChatModel"`)** — um tipo referido por nome em string, avaliado só pela
ferramenta de tipos, não em runtime.

**Callback (LangChain) / `BaseCallbackHandler`** — objeto com ganchos (`on_llm_start`/`end`/`error`)
que o LangChain chama automaticamente no ciclo de vida de uma chamada. Base para o cronômetro.

**`run_id` / `UUID`** — identificador único de cada chamada de LLM. `UUID` é um tipo de ID de 128
bits praticamente irrepetível. Chavear tempos por `run_id` isola chamadas concorrentes/sequenciais.

**`time.monotonic()`** — relógio que só avança, imune a ajustes do relógio do sistema; correto para
medir durações.

**Construtor (`__init__`)** — o método chamado ao criar um objeto de uma classe; inicializa seus
atributos.

**`os.getenv` / `.pop(k, default)` / `.get(k)`** — leituras seguras: `getenv` lê variável de ambiente
(ou `None`); `.pop`/`.get` de dicionário retornam um padrão em vez de estourar se a chave falta.

**Temperature (temperatura)** — parâmetro de amostragem do LLM: `0.0` = determinístico/estável;
maior = mais criativo/variável.

**num_ctx (janela de contexto)** — quantos tokens o modelo enxerga por vez. O default do Ollama
(2048) é pequeno; o projeto usa 8192 para o JSON verboso não ser truncado.

**Timeout / max_retries** — tempo máximo de espera por resposta e número de re-tentativas em caso de
falha da API.

**Fallback** — o caminho "senão", o padrão quando nenhuma condição específica casa. Aqui, Ollama
local é o fallback do roteamento.
