# Testes de software e `pytest` — guia completo do mill.tools

Documento de referência para entender testes automatizados de verdade: por que existem, os conceitos
do básico ao avançado, o `pytest` e seus plugins auxiliares, e — o mais importante — **como tudo
isso aparece no seu próprio projeto**. Todo exemplo aqui é código real de `tests/`. Termos técnicos
têm um glossário no fim.

> Como ler: os fundamentos (Parte 1) valem para qualquer linguagem. A partir da Parte 2 é `pytest`
> concreto. Você pode ler linear ou pular para a seção que precisar. As caixas 🔑 marcam os pontos
> não óbvios que separam "sei rodar um teste" de "entendo testar".

---

# PARTE 1 — Fundamentos (valem para qualquer linguagem)

## 1.1 O que é um teste automatizado e por que ele existe

Um **teste automatizado** é um pedaço de código cuja única função é **executar outro pedaço de
código e verificar se ele se comportou como o esperado**. Se o comportamento bate, o teste "passa"
(verde); se não bate, "falha" (vermelho).

Por que investir nisso em vez de só testar na mão abrindo o app? Três razões práticas do dia a dia:

1. **Regressão.** Você mexe no código do módulo Áudio e, sem querer, quebra algo no módulo Imagem.
   Testar tudo na mão a cada mudança é inviável. Uma suíte de testes roda em segundos e grita
   exatamente o que quebrou. (No seu projeto, a regra é literal: `uv run pytest -m unit` verde
   **antes de commitar**.)
2. **Documentação viva.** Um bom teste é um exemplo executável de como uma função deve ser usada e o
   que ela promete. Quando você volta ao código meses depois, os testes contam a intenção.
3. **Design.** Código difícil de testar quase sempre é código mal desenhado (acoplado demais, faz
   coisas demais). A dor de testar é um *sinal de projeto* — foi o que empurrou o seu `core/` a ser
   puro e a usar injeção de dependência.

🔑 **Teste não prova ausência de bugs — reduz o custo de encontrá-los cedo.** Um bug pego pelo teste
na sua máquina custa segundos; o mesmo bug pego pelo usuário custa horas e confiança. Testar é
mover a descoberta do erro para o momento mais barato possível.

## 1.2 A anatomia de um teste: o padrão AAA (Arrange, Act, Assert)

Praticamente todo teste bem escrito tem três fases, nesta ordem — o padrão **Arrange-Act-Assert**
(Preparar, Agir, Verificar):

- **Arrange (Preparar):** monta o cenário — cria os dados de entrada, os arquivos, os objetos falsos.
- **Act (Agir):** executa **a** ação sob teste — normalmente **uma** chamada de função. É o gatilho.
- **Assert (Verificar):** confere se o resultado (ou o efeito colateral) foi o esperado.

Veja num teste real do seu projeto (`tests/core/audio/test_converter_unit.py`), com as fases
anotadas:

```python
def test_convert_audio_mono_adds_ac_flag(tmp_path, mocker):
    """channels=1 deve injetar '-ac 1' no comando ffmpeg."""
    from src.core.audio.converter import convert_audio

    # ARRANGE — cria um arquivo de entrada e prepara a captura do comando
    src = tmp_path / "in.wav"
    src.write_bytes(b"")
    captured = _capture_cmd(mocker)

    # ACT — a única ação: converter pedindo mono (channels=1)
    convert_audio(src, tmp_path / "out", fmt="mp3", channels=1)

    # ASSERT — o comando ffmpeg montado contém '-ac 1'?
    cmd = captured["cmd"]
    assert "-ac" in cmd
    assert cmd[cmd.index("-ac") + 1] == "1"
```

🔑 **Por que "uma" ação no Act importa.** Se um teste faz várias ações e falha, você não sabe qual
delas quebrou. Um teste = um comportamento = uma pergunta clara ("pedir mono injeta `-ac 1`?"). O
nome do teste deve responder a essa pergunta — repare que os nomes no projeto descrevem
**comportamento** (`test_convert_audio_mono_adds_ac_flag`), não implementação.

## 1.3 Os níveis de teste: a pirâmide

Nem todo teste é igual. Há uma hierarquia clássica, a **pirâmide de testes**:

```
        /\        Poucos, lentos, caros
       /E2E\      end-to-end: o sistema inteiro, como o usuário usa
      /------\
     /  Integ \   integração: várias peças reais juntas (ex.: chama o ffmpeg de verdade)
    /----------\
   /    Unit    \ muitos, rápidos, baratos: uma peça isolada, sem dependências externas
  /--------------\
```

- **Unitário (unit):** testa **uma** unidade (uma função) **isolada** do mundo — sem rede, sem
  disco pesado, sem GPU, sem ffmpeg. Rápido (milissegundos) e determinístico. É a base da pirâmide:
  a maioria dos testes.
- **Integração (integration):** testa peças reais **juntas**. No seu projeto, um teste de integração
  chama o ffmpeg **de verdade** para converter um áudio real e confere o arquivo de saída. Mais
  lento e depende de o ffmpeg existir na máquina.
- **End-to-end (E2E):** exercita o fluxo completo como o usuário faria. Caros e frágeis; o projeto
  praticamente não os faz (ex.: não faz E2E de download do YouTube — só teria valor real em rede
  ao vivo, custo alto, retorno baixo).

🔑 **Por que a base é larga.** Testes unitários são o melhor retorno por real investido: pegam a
maioria dos bugs, rodam rápido e não dependem do ambiente. Integração cobre o que a unidade não
alcança (o ffmpeg realmente aceita aquele comando?). O seu projeto marca cada teste com `unit` ou
`integration` justamente para poder rodar só a base rápida no dia a dia e a pirâmide inteira quando
necessário (veremos os *markers* na Parte 3).

O seu projeto materializa os dois níveis no mesmo módulo. Compare:

```python
# tests/core/audio/test_converter_unit.py  → UNIT: ffmpeg é MOCKADO (falso), roda em ms
mocker.patch("src.core.audio.converter.run_ffmpeg", side_effect=_fake)

# tests/core/audio/test_normalizer_integration.py → INTEGRAÇÃO: ffmpeg REAL
pytestmark = pytest.mark.integration
def test_...(sample_wav, out_dir):
    out = convert_audio(sample_wav, out_dir, fmt="mp3", bitrate="128")
    assert out.exists() and out.stat().st_size > 1000
```

---

# PARTE 2 — `pytest`, o essencial

`pytest` é o *framework* de testes que o projeto usa (versão 9). Ele descobre, roda e reporta seus
testes, e traz uma sintaxe muito mais leve que o `unittest` da biblioteca padrão.

## 2.1 Descoberta: como o pytest acha seus testes

Você não registra testes em lugar nenhum — o pytest os **descobre** por convenção de nome:

- arquivos `test_*.py` (ou `*_test.py`);
- funções `test_*` dentro deles;
- classes `Test*` (opcional; o projeto usa funções soltas, não classes).

No seu projeto isso é configurado no `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths  = ["tests"]      # onde procurar
pythonpath = ["."]          # permite `from src.modulo import ...`
```

🔑 A árvore de `tests/` **espelha** a de `src/`: `src/core/audio/normalizer.py` →
`tests/core/audio/test_normalizer_unit.py`. Essa convenção (regra da skill `testing`) faz você achar
o teste de qualquer arquivo instantaneamente, sem procurar.

## 2.2 O `assert` mágico

Em muitos frameworks você escreve `self.assertEqual(a, b)`. No pytest, você usa o `assert` puro do
Python:

```python
assert resultado == esperado
assert "-ac" in cmd
assert out.exists()
```

🔑 O pytest **reescreve** o `assert` nos bastidores (*assertion rewriting*) para, quando ele falha,
mostrar os valores reais dos dois lados — não só "falhou". Com o plugin `pytest-clarity` (que você
tem), esse diff fica ainda mais legível, colorido, mostrando exatamente o que diferiu. É por isso
que no pytest você quase nunca precisa de mensagens de erro manuais.

## 2.3 Como rodar (os atalhos do projeto)

O projeto usa o `poethepoet` como atalho (`uv run poe <tarefa>`), definido no `pyproject.toml`:

```bash
uv run poe test        # pytest -m unit   → só unitários (rápido, sem ffmpeg)
uv run poe test-all    # pytest           → tudo (unit + integração)
uv run poe cov         # pytest -m unit --cov → unitários + relatório de cobertura
uv run poe check       # lint + test      → o "portão" antes de commitar
```

Comandos `pytest` úteis diretos:

```bash
uv run pytest tests/core/audio/            # só uma pasta
uv run pytest -k "mono"                    # só testes cujo nome casa "mono"
uv run pytest -x                           # para no primeiro que falhar
uv run pytest -v                           # verboso (lista cada teste)
uv run pytest --randomly-seed=1234         # fixa a semente de ordem aleatória
```

---

# PARTE 3 — Fixtures, parametrização e markers

## 3.1 Fixtures: preparar o cenário de forma reutilizável

Uma **fixture** é uma função decorada com `@pytest.fixture` que **prepara algo** de que os testes
precisam (um arquivo, um objeto, uma conexão) e o **entrega** para eles. Em vez de repetir a mesma
preparação em 20 testes, você a escreve uma vez como fixture e a "pede" por nome.

Como se pede? **Declarando o nome da fixture como parâmetro do teste.** O pytest vê o parâmetro,
roda a fixture correspondente e injeta o resultado. Isso é *injeção de dependência* aplicada a
testes — o mesmo princípio do seu `core/`.

Exemplo real (`tests/conftest.py`):

```python
@pytest.fixture
def jpg_image(tmp_path: Path) -> Path:
    """JPEG RGB 200×150."""
    return _make_rgb_jpg(tmp_path)
```

E um teste que a usa — repare que basta nomear `jpg_image` no parâmetro:

```python
def test_algo(jpg_image):          # pytest roda a fixture e injeta o Path aqui
    assert jpg_image.exists()
```

🔑 **`tmp_path` é uma fixture embutida do pytest** — repare que a própria fixture `jpg_image` a
recebe como parâmetro. Ela dá a cada teste um **diretório temporário limpo e único**, apagado
depois. É a base do isolamento: cada teste tem seu próprio espaço em disco e nunca pisa no do outro.
Nunca escreva arquivos de teste em caminhos fixos — use `tmp_path`.

### setup e teardown com `yield`

Uma fixture pode ter uma fase de **limpeza** (teardown). Em vez de `return`, ela usa `yield`: o que
vem antes do `yield` é o setup; o que vem depois roda **quando o teste termina**, garantidamente.

```python
@pytest.fixture
def recurso():
    conexao = abrir()      # setup (arrange)
    yield conexao          # entrega ao teste
    conexao.fechar()       # teardown — sempre roda, mesmo se o teste falhar
```

(Suas fixtures atuais usam `return` porque `tmp_path` já cuida da limpeza sozinho — não há o que
desfazer.)

### Escopo de fixture (`scope`): o balanço custo × isolamento

Por padrão, uma fixture roda **de novo para cada teste** (`scope="function"`) — máximo isolamento.
Mas gerar certos recursos é caro. Seu projeto usa `scope="session"` para os áudios de amostra, que
são gerados **uma vez** via ffmpeg e reusados por toda a suíte:

```python
@pytest.fixture(scope="session")
def sample_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """WAV mono 44100 Hz 3 s — sine wave 440 Hz."""
    out = tmp_path_factory.mktemp("fixtures") / "sample.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=3", ...], check=True, capture_output=True)
    return out
```

🔑 **O trade-off do escopo é uma faca de dois gumes.** `session` é rápido (gera uma vez), mas se um
teste **modificar** o recurso compartilhado, contamina os outros — uma fonte clássica de *flaky
tests* (testes instáveis). Regra de ouro (e do seu projeto): fixtures de escopo largo são
**somente-leitura**; um teste que precisa modificar a entrada primeiro **copia** para o seu
`tmp_path` (`shutil.copy`). E note: `sample_wav` usa `tmp_path_factory` (a versão de sessão do
`tmp_path`), não `tmp_path` (que é por função).

### `conftest.py`: fixtures compartilhadas sem importar

O arquivo especial **`conftest.py`** guarda fixtures visíveis para todos os testes da pasta (e
subpastas), **sem precisar importá-las**. O pytest as descobre automaticamente. Seu `tests/conftest.py`
tem as fixtures globais (`jpg_image`, `out_dir`, `sample_wav`, ...); há também `conftest.py` locais,
como `tests/core/data/conftest.py`, com fixtures específicas daquele domínio (CSVs de exemplo).

## 3.2 Parametrização: um teste, muitos casos

Quando o mesmo teste deve rodar com **entradas diferentes**, você não copia-e-cola — você
**parametriza** com `@pytest.mark.parametrize`. O pytest gera uma variante independente por caso
(cada uma passa ou falha sozinha):

```python
import pytest

@pytest.mark.parametrize("entrada, esperado", [
    ("Python 3.13", "Python_3.13"),
    ("a  b  c",     "a_b_c"),
    ("faixa | 01",  "faixa-01"),
])
def test_sanitize(entrada, esperado):
    from src.utils import sanitize_filename
    assert sanitize_filename(entrada) == esperado
```

🔑 **Por que isso é melhor que um `for` dentro do teste?** Com `parametrize`, cada caso vira um teste
com nome próprio no relatório; se um falha, você vê **qual** entrada quebrou e os outros continuam
rodando. Um `for` pararia no primeiro erro e esconderia os demais.

## 3.3 Markers: rotular e selecionar testes

Um **marker** é um rótulo que você cola num teste com `@pytest.mark.<nome>`. O projeto usa dois,
declarados no `pyproject.toml` (com `--strict-markers`, que **rejeita** marker não declarado — pega
erro de digitação):

```toml
markers = [
    "unit: testes unitários — sem dependências externas",
    "integration: requer ffmpeg, arquivos reais ou rede",
]
```

Formas de aplicar (as duas aparecem no seu código):

```python
# Por teste:
@pytest.mark.unit
def test_video_download_defaults(): ...

# Para o módulo inteiro (uma linha no topo do arquivo):
pytestmark = pytest.mark.unit
```

E aí você seleciona por marker ao rodar:

```bash
uv run pytest -m unit               # só os unitários
uv run pytest -m "not integration"  # tudo menos integração
```

### O hook que pula integração sozinho

🔑 Um detalhe elegante do seu `conftest.py`: se o `ffmpeg` **não** estiver instalado, os testes de
integração são **pulados automaticamente** (não falham). Isso é feito por um *hook* — uma função com
nome mágico que o pytest chama em momentos-chave:

```python
def pytest_collection_modifyitems(config, items):
    import shutil
    if shutil.which("ffmpeg") is None:
        skip_no_ffmpeg = pytest.mark.skip(reason="ffmpeg não encontrado no PATH")
        for item in items:
            if item.get_closest_marker("integration"):
                item.add_marker(skip_no_ffmpeg)
```

`pytest_collection_modifyitems` roda **depois** que o pytest coletou todos os testes e **antes** de
executá-los; aqui ele varre a lista e adiciona o marcador `skip` a cada teste de integração quando
falta ffmpeg. Resultado: a suíte roda limpa numa máquina sem ffmpeg (como um servidor de CI), sem
ninguém precisar lembrar de filtrar na mão.

---

# PARTE 4 — Mocking: isolar a unidade do mundo

Esta é a parte que mais confunde no começo, e a mais poderosa. Vale ir devagar.

## 4.1 O problema que o mock resolve

Um teste **unitário** precisa ser rápido, determinístico e não depender do mundo externo. Mas a
função que você quer testar frequentemente **chama** algo externo: o ffmpeg, uma API na nuvem, o
relógio, o disco. Se o teste chamasse o ffmpeg de verdade, seria lento, exigiria ffmpeg instalado e
poderia falhar por motivos alheios à lógica que você quer verificar.

A solução é o **mock** (dublê): você substitui a dependência externa por um **objeto falso** que
você controla. Assim o teste isola **só a sua lógica**.

🔑 **A virada de chave.** No teste `test_convert_audio_mono_adds_ac_flag`, você **não** quer saber se
o ffmpeg converte áudio — isso é problema do ffmpeg. Você quer saber se a **sua** função monta o
**comando certo** (`-ac 1`) para pedir mono. Então você troca o `run_ffmpeg` real por um falso que
só **guarda o comando** que recebeu, e depois você inspeciona esse comando. Você testa a decisão da
sua função, não o trabalho da ferramenta externa.

```python
def _capture_cmd(mocker):
    captured: dict = {}
    def _fake(cmd, out_path, **kwargs):
        captured["cmd"] = cmd          # o dublê só anota o que recebeu
        captured["out_path"] = out_path
        return out_path
    mocker.patch("src.core.audio.converter.run_ffmpeg", side_effect=_fake)
    return captured
```

## 4.2 `mocker` (pytest-mock): a ferramenta principal

O plugin **`pytest-mock`** dá a fixture **`mocker`**, que embrulha o `unittest.mock` da biblioteca
padrão de forma mais limpa: sem `with` nem decoradores, e **desfeito automaticamente** ao fim do
teste (o patch some sozinho, sem contaminar os próximos). Você pede `mocker` como parâmetro do
teste.

Os três usos que aparecem no seu projeto:

```python
# 1. Substituir por um mock "vazio" (só registra que foi chamado)
run = mocker.patch("src.core.audio.converter.run_ffmpeg")
...
run.assert_not_called()          # afirma que NÃO foi chamado

# 2. Substituir por um valor de retorno fixo
mocker.patch("src.core.audio.converter.get_audio_codec_ffprobe", return_value="aac")

# 3. Substituir por um comportamento (uma função sua) via side_effect
mocker.patch("src.core.audio.converter.run_ffmpeg", side_effect=_fake)
```

- **`return_value=X`** — quando chamado, o mock devolve `X`. Bom para simular "o ffprobe disse que o
  codec é aac".
- **`side_effect=funcao`** — quando chamado, o mock **executa `funcao`** com os mesmos argumentos.
  Use quando o dublê precisa fazer algo (capturar o comando, ou simular falha). 🔑 Se `side_effect`
  for uma **exceção**, o mock a **levanta** — é assim que se simula erro:

```python
def _fake_fail(cmd, out_path, **kwargs):
    out_path.write_bytes(b"partial")      # simula um encode parcial
    raise RuntimeError("ffmpeg boom")     # e então falha
mocker.patch("src.core.audio.converter.run_ffmpeg", side_effect=_fake_fail)
```

### Verificar interações: `assert_called...`

Um mock **lembra** como foi chamado. Você pode afirmar sobre isso:

```python
move = mocker.patch("src.core.audio.converter.shutil.move")
...
move.assert_called_once()                 # foi chamado exatamente 1 vez?
mock_pipeline.call_args.args[0]           # o 1º argumento posicional da chamada
```

Exemplo real do teste de CLI de vídeo, verificando que o parser traduziu a operação corretamente:

```python
mock_pipeline = mocker.patch("src.gui.modules.video.worker.run_video_pipeline", return_value=True)
ns.func(ns)                               # dispara o runner da CLI
args = mock_pipeline.call_args.args[0]    # captura o VideoArgs que ele montou
assert args.operation == "extract_audio"  # 'extract-audio' (kebab) virou snake?
assert args.audio_fmt == "wav"
```

🔑 Isto é um **teste de interação**: em vez de checar um valor de retorno, ele verifica **como** a sua
função chamou a peça seguinte. Perfeito para a camada CLI, cujo trabalho é justamente *traduzir*
argumentos e *despachar* para o pipeline — sem realmente rodar o pipeline (que está mockado).

## 4.3 A armadilha nº 1 do mock: "faça o patch onde é USADO, não onde é DEFINIDO"

Este é *o* erro clássico, e entendê-lo te poupa horas. Repare no alvo do patch nos exemplos:

```python
mocker.patch("src.core.audio.converter.run_ffmpeg", ...)   # ✅ certo
```

`run_ffmpeg` é **definido** em `src.core.ffmpeg`. Mas o `converter.py` faz, no topo,
`from src.core.ffmpeg import run_ffmpeg` — o que cria uma **cópia da referência** dentro do namespace
do `converter`. Quando o `convert_audio` chama `run_ffmpeg`, ele usa
`src.core.audio.converter.run_ffmpeg`, não `src.core.ffmpeg.run_ffmpeg`.

🔑 Por isso você faz o patch em **`src.core.audio.converter.run_ffmpeg`** (onde é *usado*), não em
`src.core.ffmpeg.run_ffmpeg` (onde é *definido*). Se você patchasse a origem, o `converter` continuaria
apontando para a função real e o seu mock seria ignorado — o teste chamaria o ffmpeg de verdade sem
você entender por quê. **Regra:** o alvo do patch é sempre o caminho pelo qual o **código sob teste**
enxerga o objeto.

## 4.4 `monkeypatch` e `capsys`: outras fronteiras

Além do `mocker`, o pytest traz fixtures embutidas para casos específicos:

- **`monkeypatch`** — troca atributos, variáveis de ambiente e afins, desfazendo ao fim do teste. É
  o ideal para ambiente e configuração. Padrão do seu projeto para simular chaves de API e isolar a
  config global:

```python
def test_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")                       # variável de ambiente falsa
    monkeypatch.setattr("src.llm_factory.load_dotenv", lambda *a, **k: None)  # neutraliza o .env real
```

🔑 `mocker` vs. `monkeypatch`: fazem coisas parecidas. Na prática, o projeto usa `mocker` para
**substituir funções/objetos** (com `return_value`/`side_effect`/asserts de chamada) e `monkeypatch`
para **ambiente e atributos simples**. `mocker` costuma exigir menos código quando você quer
configurar retorno numa linha.

- **`capsys`** — captura o que o código imprimiu em `stdout`/`stderr`, para você verificar a saída
  de terminal. É a fixture usada nos testes dos subcomandos read-only da CLI (que imprimem resultado
  direto):

```python
def test_algum_cli(capsys):
    rodar_comando()
    out = capsys.readouterr().out         # o texto impresso
    assert "esperado" in out
```

## 4.5 Testando que um erro acontece: `pytest.raises`

Às vezes o comportamento correto **é** levantar uma exceção. Você afirma isso com o gerenciador de
contexto `pytest.raises`:

```python
def test_convert_audio_inplace_transform_cleans_tmp_on_failure(tmp_path, mocker):
    ...
    with pytest.raises(RuntimeError):        # o bloco DEVE levantar RuntimeError
        convert_audio(src, tmp_path, fmt="mp3", channels=1)

    assert list(tmp_path.glob(".tmp_encode_*")) == []   # e o temp órfão foi limpo
```

🔑 Se o bloco **não** levantar a exceção esperada, o próprio `pytest.raises` faz o teste falhar. Aqui
o teste verifica duas coisas de uma vez: que a falha do ffmpeg **propaga** como `RuntimeError` e que,
mesmo falhando, o arquivo temporário parcial foi **removido** (não deixou lixo). É um teste de
robustez.

Outro caso comum no projeto — argparse chama `SystemExit` quando falta um argumento obrigatório:

```python
def test_video_subtitle_requires_subs():
    with pytest.raises(SystemExit):          # sem --subs, o parser aborta
        _parse("subtitle", "video.mp4")
```

## 4.6 Dependências opcionais: `importorskip`

O projeto tem extras opcionais (`[ml]`, `[ocr]`, pymupdf...). Um teste que precisa de uma lib que
pode não estar instalada usa **`pytest.importorskip`**: se a lib existe, importa; se não, **pula** o
teste (não falha).

```python
@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory):
    pymupdf = pytest.importorskip("pymupdf")   # sem pymupdf, pula quem depender desta fixture
    ...
```

🔑 É o irmão do hook de ffmpeg: mantém a suíte verde em ambientes que não têm todos os extras,
respeitando a regra nº 6 do projeto (degradação graciosa). Note também uma decisão de projeto:
pymupdf e DuckDB **não são mockados** nos testes unitários — são dependências *hard* (sempre
presentes) e in-process (sem rede/GPU), então os testes os usam **de verdade** e ainda contam como
`unit`.

---

# PARTE 5 — Os plugins auxiliares (e por que cada um existe)

Seu `pyproject.toml` lista cinco plugins de pytest. Cada um resolve um problema real:

| Plugin | O que faz | Por que o projeto usa |
|---|---|---|
| **pytest-cov** | Mede **cobertura** de código (que linhas os testes exercitaram). | Enxergar buracos de teste. Config com `branch = true` (cobre também os dois lados de cada `if`) e `omit = src/gui/*` (Flet não é testável headless). |
| **pytest-mock** | A fixture `mocker`. | Toda a estratégia de mock do projeto (visto na Parte 4). |
| **pytest-randomly** | Roda os testes em **ordem aleatória** a cada execução. | 🔑 Expõe *dependência oculta entre testes*: se o teste B só passa porque A rodou antes e deixou um estado, a ordem aleatória revela isso. Reproduza uma ordem com `--randomly-seed=NNN`; desligue com `-p no:randomly`. |
| **pytest-xdist** | Roda testes **em paralelo** (`-n auto`, um por núcleo). | Acelera a suíte e, de brinde, expõe colisões por recurso compartilhado (dois testes brigando pelo mesmo arquivo/singleton). |
| **pytest-timeout** | **Mata** um teste que passar de um limite de tempo (60s no projeto). | 🔑 Protege contra travas: um ffmpeg/yt-dlp pendurado, um laço infinito. Sem isso, um teste travado paralisaria a suíte inteira. |
| **pytest-clarity** | Deixa os **diffs de asserção** mais legíveis. | Quando um `assert a == b` falha, mostra exatamente o que diferiu, colorido. |

🔑 **A dupla randomly + xdist é uma rede de segurança contra *flaky tests* (testes instáveis).** A
maior causa de instabilidade é **estado vazando entre testes** (uma fixture de escopo largo
modificada, um arquivo em caminho fixo, uma variável global). Ordem aleatória + paralelismo forçam
esses vazamentos a aparecerem cedo, na sua máquina, em vez de piscarem aleatoriamente no CI. A defesa
é o isolamento que você já viu: `tmp_path` por teste, fixtures de sessão somente-leitura, `monkeypatch`
que desfaz sozinho.

---

# PARTE 6 — Cobertura de código

**Cobertura** (coverage) mede quanto do seu código foi **executado** durante os testes. Rode:

```bash
uv run pytest -m unit --cov=src --cov-report=term-missing
```

O `term-missing` lista, por arquivo, **quais linhas não foram cobertas** — o mapa do que falta
testar. A config do projeto:

```toml
[tool.coverage.run]
source = ["src"]
omit   = ["src/gui/*"]   # GUI Flet não roda headless
branch = true            # cobertura de RAMO, não só de linha
```

🔑 **Cobertura de linha vs. de ramo.** Cobertura de *linha* só pergunta "esta linha rodou?".
Cobertura de *ramo* (`branch = true`) é mais exigente: num `if x:`, pergunta se **os dois** caminhos
(x verdadeiro **e** x falso) foram testados. É por isso que os testes do `convert_audio` cobrem tanto
o caso "com `-ac`" quanto o "sem `-ac`" — cada `if` tem dois lados a exercitar.

🔑 **Cuidado com a métrica.** Cobertura alta **não** garante testes bons — dá para "cobrir" uma linha
sem verificar nada de útil. É uma bússola (onde há buraco), não um troféu. O projeto mira **≥90% por
módulo** (agregado ~88% com ramo), mas aceita lacunas justificadas (ex.: `downloader.py` do yt-dlp,
que só teria valor real em E2E). Linhas impossíveis de cobrir sem desinstalar dependências levam um
comentário `# pragma: no cover`.

---

# PARTE 7 — Boas práticas, anti-padrões e a regra de ouro do projeto

**Faça:**
- Um teste = um comportamento; nome descreve o comportamento, não a implementação.
- Estruture em AAA (Arrange, Act, Assert).
- Isole a unidade: mocke as fronteiras (ffmpeg, rede, relógio), use `tmp_path` para disco.
- Importe o alvo **dentro** da função de teste (`from src.modulo import fn`) — isola falhas de import
  e evita efeitos colaterais na coleta.
- Patch **onde é usado**, não onde é definido.

**Evite:**
- Testes que dependem da ordem (o `pytest-randomly` vai te delatar).
- Fixtures de escopo largo que são modificadas (contaminam outros testes).
- Asserções frouxas (`assert resultado` só checa "não é vazio/None" — prefira o valor exato).
- Testar a biblioteca de terceiros em vez da sua lógica (não é sua função garantir que o ffmpeg
  converte; é garantir que você o chama certo).

🔑 **A regra dura do seu projeto — testes NÃO podem travar a máquina (OOM).** A skill `testing`
documenta um risco real e específico da sua bancada (16 GB de RAM): um teste que faz o processo
crescer sem limite estoura a RAM e **trava o Windows / fecha o VSCode sem aviso** — e o
`pytest-timeout` **não protege**, porque o travamento por falta de memória acontece *antes* dos 60s.
A causa nº 1 já observada foi um helper que **anda a árvore de controles Flet recursivamente** e, ao
encontrar um `MagicMock` enterrado, recursa para sempre (um `MagicMock` fabrica um filho novo a cada
acesso de atributo). A defesa: **helper de travessia PARA em mocks** (`isinstance(control,
NonCallableMock)` → `return`). Vigie também `while <mock>` (mock é sempre "verdadeiro" → laço
infinito) e iteradores infinitos (`itertools.count`) como `side_effect`. Esta é a regra mais séria
da suíte — vale reler a seção correspondente da skill `testing` antes de escrever testes de GUI.

---

# PARTE 8 — Como adicionar um teste no projeto (checklist)

1. **Espelhe o caminho:** `src/core/x/y.py` → `tests/core/x/test_y.py` (ou `test_y_unit.py` /
   `test_y_integration.py`). Cada subpasta de `tests/` tem um `__init__.py` vazio.
2. **Escolha o nível/marker:** lógica pura sem ffmpeg → `@pytest.mark.unit`; precisa de ffmpeg/arquivo
   real → `@pytest.mark.integration` (será pulado sem ffmpeg).
3. **Escreva em AAA**, com nome que descreve o comportamento.
4. **Isole as fronteiras:** mocke (`mocker.patch` no caminho **usado**), use `tmp_path`, reuse as
   fixtures de `conftest.py`.
5. **Rode o portão:** `uv run poe check` (ruff + `pytest -m unit`) verde antes de commitar.

Receitas de mock por fronteira (ffmpeg/Whisper, LLM/RAG/ML, GUI/CLI) estão nos três arquivos de
referência da skill `testing` (`mocks-media.md`, `mocks-llm-rag-ml.md`, `mocks-gui-cli.md`) — abra o
que casar com o que você está testando.

---

# Glossário

**Teste automatizado** — código que executa outro código e verifica se ele se comportou como
esperado; passa (verde) ou falha (vermelho).

**Suíte de testes** — o conjunto de todos os testes do projeto.

**Regressão** — quando uma mudança quebra algo que antes funcionava. Testes de regressão pegam isso.

**AAA (Arrange, Act, Assert)** — as três fases de um teste: preparar o cenário, executar a ação,
verificar o resultado.

**Unit (teste unitário)** — testa uma unidade isolada, sem dependências externas (rede/disco pesado/
GPU/ffmpeg). Rápido e determinístico.

**Integração (integration)** — testa peças reais juntas (ex.: chama o ffmpeg de verdade). Mais lento;
depende do ambiente.

**E2E (end-to-end)** — exercita o fluxo completo como o usuário. Caro e frágil.

**Pirâmide de testes** — a proporção ideal: muitos unitários (base), menos de integração, pouquíssimos
E2E (topo).

**Determinístico** — mesma entrada, mesmo resultado, sempre. Testes devem ser determinísticos.

**Flaky test (teste instável)** — passa às vezes e falha às vezes sem mudança no código, quase sempre
por estado vazando entre testes ou dependência de ordem.

**pytest** — o framework de testes do projeto: descobre, roda e reporta testes com sintaxe leve.

**Assertion / `assert`** — a verificação central de um teste. O pytest reescreve o `assert` para
mostrar os valores reais quando falha.

**Assertion rewriting** — a mágica do pytest que enriquece a mensagem de falha do `assert` com os
valores dos dois lados.

**Descoberta (discovery)** — como o pytest encontra testes por convenção de nome (`test_*.py`,
`test_*`).

**Fixture** — função `@pytest.fixture` que prepara e entrega um recurso a testes que a declaram como
parâmetro. Injeção de dependência aplicada a testes.

**`tmp_path` / `tmp_path_factory`** — fixtures embutidas que dão um diretório temporário limpo (por
função / por sessão). Base do isolamento em disco.

**Setup / Teardown** — preparação antes e limpeza depois de um teste. Numa fixture, separados pelo
`yield`.

**Escopo (`scope`)** — quantas vezes uma fixture roda: `function` (padrão, por teste), `session` (uma
vez para toda a suíte), entre outros. Trade-off custo × isolamento.

**`conftest.py`** — arquivo especial que fornece fixtures/hooks a todos os testes da pasta e
subpastas, sem import.

**Parametrização (`@pytest.mark.parametrize`)** — rodar o mesmo teste com várias entradas; cada caso
vira um teste independente.

**Marker (`@pytest.mark.<nome>`)** — rótulo em um teste (ex.: `unit`, `integration`) para seleção.
`--strict-markers` rejeita markers não declarados.

**Hook (`pytest_*`)** — função de nome mágico que o pytest chama em momentos-chave (ex.:
`pytest_collection_modifyitems`, para pular integração sem ffmpeg).

**Mock / dublê** — objeto falso que substitui uma dependência externa para isolar a unidade sob teste.

**`mocker` (pytest-mock)** — fixture que cria mocks/patches de forma limpa, desfeitos ao fim do teste.

**Patch** — substituir temporariamente um objeto por um mock. Deve mirar **onde o objeto é usado**,
não onde é definido.

**`return_value`** — o valor que um mock devolve ao ser chamado.

**`side_effect`** — comportamento que um mock executa ao ser chamado (uma função, ou uma exceção a
levantar).

**`assert_called_once` / `assert_not_called` / `call_args`** — verificações sobre **como** um mock
foi chamado (quantas vezes, com quais argumentos).

**`monkeypatch`** — fixture embutida para trocar atributos e variáveis de ambiente, desfeita ao fim
do teste. Ideal para ambiente/config.

**`capsys`** — fixture que captura `stdout`/`stderr` para verificar a saída de terminal.

**`pytest.raises`** — gerenciador de contexto que afirma que um bloco levanta uma exceção esperada.

**`pytest.importorskip`** — importa uma lib opcional ou pula o teste se ela faltar.

**Cobertura (coverage)** — quanto do código foi executado pelos testes. **De linha**: a linha rodou?
**De ramo (branch)**: os dois lados de cada `if` foram testados?

**`# pragma: no cover`** — comentário que exclui uma linha impossível/irrelevante de cobrir da
métrica.

**pytest-randomly** — plugin que embaralha a ordem dos testes para expor dependências ocultas.

**pytest-xdist** — plugin que roda testes em paralelo (`-n auto`), acelerando e expondo colisões.

**pytest-timeout** — plugin que mata testes que passam de um limite de tempo (60s no projeto).

**pytest-cov** — plugin de cobertura.

**pytest-clarity** — plugin que melhora a legibilidade dos diffs de asserção.

**OOM (Out Of Memory)** — quando o processo estoura a RAM. No projeto, um teste com OOM trava o
Windows; a defesa é o helper de travessia parar em mocks.

**`MagicMock` / `NonCallableMock`** — tipos de mock. `MagicMock` fabrica um atributo-filho novo a cada
acesso — perigoso em travessia recursiva (fonte do OOM).

---

## Fontes

Refinado com as boas práticas atuais de:

- [pytest Tutorial: Effective Python Testing — Real Python](https://realpython.com/pytest-python-testing/)
- [How to use fixtures — pytest documentation](https://docs.pytest.org/en/stable/how-to/fixtures.html)
- [How to monkeypatch/mock modules and environments — pytest documentation](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)
- [Python Mock Pitfall: Patch Where It Is Used, Not Where It Is Defined](https://recca0120.github.io/en/2026/03/19/python-mock-imported-function/)
- [pytest-mock: Cleaner Mocking With the mocker Fixture](https://recca0120.github.io/en/2026/04/03/pytest-mock/)
- [Flaky tests — pytest documentation](https://docs.pytest.org/en/stable/explanation/flaky.html)
- [pytest-xdist — documentation](https://pytest-xdist.readthedocs.io/en/stable/)
- [pytest-cov — PyPI](https://pypi.org/project/pytest-cov/)
