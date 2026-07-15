# Apêndice — quirks de Windows, GPU e anti-bot

Referência das dores de plataforma que aparecem espalhadas pelo código. Não são conceitos de
arquitetura — são armadilhas do mundo real (Windows, GPU fraca, YouTube) que o projeto contorna. Reúno
aqui para consulta.

---

# PARTE 1 — Quirks de Windows

## Encoding (cp1252 vs. UTF-8)

O console do Windows usa `cp1252` por padrão; um nome de arquivo com acento estoura
`UnicodeDecodeError`. Mitigações no código:
- **`subprocess` em modo binário** (sem `text=True`) + decode manual com `errors="replace"` — regra
  nº 5 ([`../arquivos/ffmpeg.md`](../arquivos/ffmpeg.md)).
- **`sys.stdout` reconfigurado para UTF-8** nos subcomandos read-only da CLI ([`CLI.md`](CLI.md) §6).

## Nomes de arquivo (`sanitize_filename`)

Caracteres inválidos no Windows (`< > " \ / ? *`), o limite MAX_PATH (~260 chars) e o ADS do NTFS (um
`:` no nome cria um fluxo oculto) — tudo tratado em `sanitize_filename`
([`../arquivos/utils.md`](../arquivos/utils.md)).

## O `.temp.<ext>` do yt-dlp

Dois quirks da mesma família — o yt-dlp cria um arquivo `.temp.<ext>` que o Defender às vezes trava no
rename (`[WinError 32]`):
- **Vídeo** — nunca usar `FFmpegVideoConvertor` (cria `.temp` no dir de saída, Defender bloqueia). Usar
  `merge_output_format` + `nopart=True`, `paths={"temp": tempfile.gettempdir()}`.
- **Áudio** — o `FFmpegExtractAudio` cria `.temp` **no dir do arquivo de entrada** (hardcoded). Rodar
  download+pós num `tempfile.mkdtemp()` e mover com `shutil.move` ([`../modulos/audio.md`](../modulos/audio.md)).

O worker de Vídeo **enriquece** o erro de `WinError 32` com uma dica ("aguarde e tente de novo, ou
exclua `output/` do Defender"). Fix durável: excluir `output/` do Windows Defender.

## Burn-in de legenda (o `:` do drive)

O filtro `subtitles=` do ffmpeg usa `:` como separador; o `:` de `C:\...` quebra o parser. Solução:
rodar o ffmpeg com `cwd` na pasta da legenda e referenciá-la por **basename** (o parâmetro `cwd` do
`run_ffmpeg` existe por isso — [`../arquivos/ffmpeg.md`](../arquivos/ffmpeg.md)).

## Pacote corrompido após `uv sync` (lock de `.pyd`)

Um `uv sync` interrompido por lock do Windows sobre um `.pyd` (binário em uso pela GUI aberta ou pelo
Defender) deixa um pacote meio-instalado → `ImportError: cannot import name 'X' ... (unknown
location)`. **Fix:** `uv run poe repair <pkg>`. **Prevenção:** feche a GUI antes de `uv sync`.

---

# PARTE 2 — GPU e estabilidade (MX150 / Pascal)

O Flet (DirectX) e o Whisper (CUDA) disputam a MX150 (2GB VRAM) — uso simultâneo pode causar BSOD
`WIN32K_POWER_WATCHDOG_TIMEOUT`. Mitigações no projeto:
- `LogEventHandler` em INFO; libs ruidosas capadas em WARNING; fila de áudio sequencial.
- Compute `int8_float32` (a MX150 é Pascal, sem suporte a algumas precisões).
- Se persistir: forçar `python.exe` em "Economia de energia" (iGPU Intel) nas configs de gráficos do
  Windows.

🔑 É por isso que só a **Transcrição** usa GPU pesada (Whisper); o resto do encode é **100% CPU, sem
NVENC** (decisão definitiva — [`../modulos/transcricao.md`](../modulos/transcricao.md)).

---

# PARTE 3 — Anti-bot do YouTube (cookies / PO Token)

O YouTube tem um gate anti-bot. O projeto pode passar cookies de um navegador logado
(`core/ytdlp_cookies.py`, puro, nunca levanta):
- **Zen Browser** — o yt-dlp não conhece "zen"; mapeia para `("firefox", <perfil Zen>, ...)`.
- **Config** — env `MILL_YT_COOKIES_*` → `config.json`. Default `"none"` (opt-in).

🔑 **Limitação (jun/2026):** cookies passam o gate anti-bot, mas cookies de **conta logada** fazem o
YouTube exigir **PO Token**; sem ele o yt-dlp recebe só storyboards → `Requested format is not
available`. Por isso o default é `none` (cookies de conta costumam **atrapalhar**). Fix durável
(`bgutil-ytdlp-pot-provider`) não implementado (exige Node/Deno). Mitigação: baixar sem cookies +
retry.
