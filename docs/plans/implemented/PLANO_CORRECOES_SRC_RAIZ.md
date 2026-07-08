# Plano — Correções dos arquivos soltos de `src/` + entry points

> **Origem**: avaliação exploratória arquivo-a-arquivo (sessão Cowork, jul/2026). Escopo: os 9 `.py`
> soltos em `src/` (`__init__`, `__main__`, `analyzer`, `formatter`, `llm_factory`, `llm_utils`,
> `prompter`, `transcriber`, `utils`) + `gui.py` e `main.py` na raiz. ~2.120 linhas.
> São os arquivos mais antigos do projeto (pré-mill.tools) — os achados centrais são: um bug de
> sanitização de filename no Windows, o pipeline LLM legado ignorando o próprio `extract_llm_text`,
> e triplicação inconsistente do parsing de header de transcrição.

## Checklist ativo de salvaguardas

| Salvaguarda | Resultado nesta rodada |
|---|---|
| Escritas não-atômicas | **FALHOU** — `formatter` reescreve in-place sem backup/validação; `transcriber` deixa `.txt` parcial órfão em exceção ≠ KeyboardInterrupt |
| Timeouts | **OK** — Ollama 300s via `client_kwargs`, Gemini/GLM 120s + retries |
| Duplicação intra-escopo | **FALHOU** — parsing do header `"-"*64` implementado 3× (analyzer, formatter, prompter) com semânticas divergentes |
| `.content` pode ser lista (Gemini) | **FALHOU** — `extract_llm_text` existe em `llm_utils` e é usado pelos cores, mas analyzer/formatter/prompter fazem `.content.strip()` cru |
| Strings PT em código | **FALHOU pontual** — log PT em `formatter.py` ("LLM retornou resposta vazia"); exceções user-facing PT estão OK pela convenção |
| Defaults mutáveis (`payload: dict = {}`) | **FALHOU** — padrão `_emit` repetido em transcriber/analyzer/formatter/prompter |

## Fases

| Fase | Tema |
|---|---|
| 0 | Baseline |
| 1 | Bugs reais |
| 2 | Unificação do parsing de header |
| 3 | Robustez do pipeline LLM |
| 4 | CLI / UX (`main.py`) |
| 5 | Higiene + docs |
| 6 | Verificação |

---

## Fase 0 — Baseline
`uv run pytest -m unit` verde antes de tocar qualquer coisa.

## Fase 1 — Bugs reais

1. **[BUG] `sanitize_filename` não remove `:` ASCII** (`utils.py`). `_SANITIZE_WIDE_COLON` só cobre o
   fullwidth `：`; `_SANITIZE_INVALID` (`[<>"\\/?*\x00-\x1f]`) não inclui `:`. Título como
   `"Python: aula 1"` vira `Python:_aula_1.txt` — em NTFS isso cria um **Alternate Data Stream**
   (arquivo `Python` com stream `_aula_1.txt`) ou falha, silenciosamente. Fix: incluir `:` no mesmo
   tratamento do wide colon (`[：:]` → hífen, preserva legibilidade). Aproveitar e adicionar **cap de
   comprimento** do stem (~120 chars) contra MAX_PATH. Testes com títulos contendo `:` e títulos longos.

2. **[BUG] Pipeline LLM legado quebra com `.content` em lista** (analyzer/formatter/prompter).
   Gemini/GLM podem devolver `resp.content` como lista de blocos — exatamente o motivo de
   `llm_utils.extract_llm_text` existir (nl2sql/assess/describe/rag já usam). Mas:
   `analyzer._invoke_and_parse` e `_ensure_portuguese` fazem `response.content`/`.strip()` direto;
   `formatter` linha ~151 e `prompter` linhas ~194/211 idem → `AttributeError` em produção com cloud.
   Fix mecânico: rotear todo `.content` desses 3 módulos por `extract_llm_text`.

3. **[BUG] `transcriber.transcribe` não é seguro fora de terminal interativo**:
   - `input()` no prompt de overwrite levanta `EOFError` sem stdin (execução agendada/pipe). Tratar
     `EOFError` como "não sobrescrever".
   - `sys.exit(0)` no `except KeyboardInterrupt` dentro de função de biblioteca — mover a decisão de
     sair para `main.py` (re-raise após o cleanup do arquivo parcial).
   - Arquivo parcial órfão: o cleanup só existe para KeyboardInterrupt; qualquer outra exceção no meio
     do loop deixa o `.txt` incompleto (que a Biblioteca/RAG depois indexam). Generalizar: `except
     BaseException` → unlink + re-raise, ou escrever em `.tmp` e renomear no fim.

4. **[BUG] Barra de progresso com `total=0` para mídia local** (`main.py` + `transcriber.py`).
   `main.py` monta `meta={"duration": 0}` para arquivo local → `tqdm(total=0)` fica sem porcentagem.
   `info.duration` (retornado pelo Whisper antes do loop) está disponível — usar como fallback do
   total. Bônus: `progress_bar.update(int(elapsed_seg))` trunca a cada segmento e acumula déficit —
   acumular em float e atualizar pela diferença inteira.

## Fase 2 — Unificação do parsing de header

O separador `"-"*64` é parseado **3×** com semânticas divergentes: `analyzer` limita a busca a uma
janela de 4096 chars (guarda anti-falso-positivo contra 64 hífens no corpo); `formatter` e `prompter`
usam `split(SEPARATOR, 1)` sem janela — o mesmo arquivo pode ter o corpo silenciosamente amputado no
format/prompt e não no analyze. Extrair helper único (ex.: `split_header_body(raw) -> tuple[dict, str]`
em `llm_utils` ou módulo novo `src/transcript_io.py`) com a janela do analyzer, e migrar os 3 call
sites + testes. `SEPARATOR` passa a ter dono único.

## Fase 3 — Robustez do pipeline LLM

1. **`analyzer._ensure_portuguese`**: se o JSON traduzido não parsear, a `ValueError` derruba a análise
   inteira **depois** de todos os chunks pagos. Fallback: warning + devolver a análise original (inglês
   é melhor que nada); usar `_invoke_and_parse` (retry) na tradução.
2. **`formatter`**: valida vazio só no corpo total — um chunk individual vazio é silenciosamente colado.
   Validar por chunk (retry 1× ou manter o chunk original). Considerar validação barata de preservação
   (nº de palavras output ≈ input, tolerância ~2%) antes de reescrever in-place; se falhar, manter o
   original e avisar.
3. **`prompter`**: quando o corpo é vazio, retorna `input_path` como se fosse o output gerado — contrato
   enganoso p/ chamadores (GUI/receitas). Retornar `None` (alinhar com `formatter`) e ajustar call
   sites. Validar `final_body` vazio antes de gravar.
4. **`_parse_json_response`**: fallback extra — localizar primeiro `{` / último `}` quando o modelo
   prefixa prosa fora do fence (reduz retries desperdiçados em modelo local).

## Fase 4 — CLI / UX (`main.py`)

1. **`check_dependencies()` incondicional**: exige yt-dlp+ffmpeg mesmo para entrada `.txt` (nenhum é
   usado) e exige yt-dlp para mídia local. Condicionar por tipo de entrada resolvido.
2. **Entrada texto sem nenhuma etapa de IA**: `main.py transcribe notas.txt` (sem `--format/--analyze/
   --prompt`) só copia o arquivo e termina sem avisar. A GUI tem guarda (exige ≥1 análise); espelhar no
   CLI com warning claro.
3. `--srt/--vtt/--subtitles` são aceitos e ignorados para entrada texto — avisar quando combinados.

## Fase 5 — Higiene + docs

1. `_emit(type: str, payload: dict = {})` — default mutável + sombra do builtin `type`, repetido 4×.
   Padronizar `payload: dict | None = None` (ruff B006).
2. `transcriber`: import de `SubtitleCue` dentro do loop de segmentos → mover para fora do loop.
3. `transcriber._resolve_device(threads)` — parâmetro nunca usado; limpar assinatura e call site.
4. `formatter.py` log PT ("LLM retornou resposta vazia") → EN, conforme convenção.
5. Docstring do `analyzer` com exemplos mortos: `uv run yt-analyzer` (script não existe no pyproject)
   e caminho antigo `transcriptions/raw/` → atualizar para `uv run -m src output/transcriptions/text/…`.
6. `gui.py`: `page.window.maximized = True` seguido de `await page.window.center()` — o center é inócuo
   maximizado; remover ou condicionar (cosmético).

## Fase 6 — Verificação

- `uv run pytest -m unit` verde; ruff limpo nos arquivos tocados.
- Smoke manual: (a) transcrição de URL com título contendo `:`; (b) `--analyze --am gemini-2.5-flash`
  (valida o item 1.2); (c) arquivo local de áudio (barra de progresso com total real); (d) entrada
  `.txt` sem flags (warning novo).
- Registrar rodada no `docs/HISTORY.md` e mover este plano para `docs/plans/` concluídos, conforme
  convenção.
