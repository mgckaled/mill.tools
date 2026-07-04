# Plano de expansão local de áudio para a GUI

## 1. Contexto

Este documento descreve uma expansão pós-refatoração para um projeto pessoal,
executado localmente, com GUI em Flet e pipeline de transcrição/análise de áudio.

A refatoração atual deve continuar com seu escopo original:

1. PR 1: cadência fiel ao CLI no painel de logs da GUI.
2. PR 2: layout split com formulário à esquerda e pipeline/resultados à direita.

A expansão de áudio proposta neste documento deve começar somente depois da
conclusão e validação desses dois PRs. A razão é simples: o PR 1 estabiliza
eventos, logs, progresso e compatibilidade com o CLI; o PR 2 estabiliza a
estrutura visual necessária para exibir modos de execução, pipeline e artefatos.

O objetivo da próxima fase não é clonar o cobalt.tools. O objetivo é aproveitar
a ideia de produto: colar uma URL, escolher uma saída e obter um arquivo local.
Internamente, a solução deve ser simples, local e controlável.

## 2. Decisão principal

Como o programa será usado apenas localmente e por uma única pessoa, não há
necessidade inicial de:

- API pública.
- Autenticação.
- Multiusuário.
- Banco de dados.
- Rate limit.
- Filas distribuídas.
- Deploy remoto.
- Proxy público.
- Storage remoto.
- Integração obrigatória com cobalt.tools.

A solução recomendada é usar diretamente ferramentas locais:

- `yt-dlp` para obtenção de mídia.
- `ffmpeg` para conversão, corte, normalização e extração.
- `ffprobe` para leitura de duração, streams, bitrate e metadados.

O programa deve evoluir de "transcritor de vídeos" para um "media pipeline
local", começando por áudio.

## 3. Referência conceitual: cobalt.tools

O cobalt.tools é uma boa referência de UX: uma ferramenta simples para salvar
mídia pública, com fluxo direto de entrada e saída. A documentação pública do
projeto descreve o cobalt como um downloader de mídia sem anúncios, trackers ou
paywalls, baseado em colar um link e obter um arquivo.

Para este projeto, o cobalt deve ser usado apenas como inspiração de produto,
não como dependência técnica direta.

A API hospedada do cobalt, como `api.cobalt.tools`, não deve ser usada como
dependência do projeto. A documentação do cobalt informa que instâncias
hospedadas usam proteção contra bots e não são destinadas ao uso por outros
projetos sem permissão explícita. Quem quiser usar a API deve hospedar a própria
instância ou pedir acesso ao dono da instância.

Também é necessário observar a licença AGPL-3.0 do cobalt. Não copiar código do
cobalt para este projeto sem revisar as obrigações da licença. Para uso pessoal
e local, a decisão mais simples é copiar apenas ideias de UX e implementar a
lógica própria com `yt-dlp` e `ffmpeg`.

## 4. Objetivo da expansão

Adicionar um modo local de manipulação de áudio à GUI, mantendo a transcrição
como uma operação entre várias possíveis.

O projeto deve deixar de presumir que toda execução termina em Whisper. Em vez
disso, deve existir uma camada intermediária de artefatos de mídia.

Modelo conceitual:

```txt
fonte de mídia -> artefato de áudio -> operação -> artefato final
```

Exemplos de composição:

```txt
URL -> baixar áudio -> salvar
URL -> baixar áudio -> converter -> salvar
URL -> baixar áudio -> cortar -> transcrever
arquivo local -> converter -> transcrever
arquivo local -> normalizar -> salvar
arquivo local -> cortar -> normalizar -> transcrever
```

A transcrição deve consumir um `AudioArtifact`. Ela não deve saber se o áudio
veio de uma URL, de um arquivo local, de uma conversão ou de um corte.

## 5. Escopo inicial recomendado

O primeiro incremento deve ser pequeno e validável.

### 5.1 Funcionalidades do primeiro ciclo

Implementar inicialmente:

- Baixar apenas áudio de uma URL.
- Converter áudio para `mp3`, `wav`, `m4a`, `opus` ou `ogg`.
- Escolher bitrate para formatos com perdas.
- Cortar áudio por timestamp inicial e final.
- Normalizar volume com opção simples.
- Preservar ou remover metadados.
- Exibir artefatos gerados na aba de resultados.
- Permitir que o áudio processado seja usado como entrada para transcrição.

### 5.2 Fora do escopo inicial

Não implementar no primeiro ciclo:

- Clone completo do cobalt.tools.
- API HTTP própria.
- Suporte avançado a múltiplas plataformas.
- Playlists complexas.
- Histórico persistido em banco de dados.
- Fila de jobs.
- Worker pool.
- Download de vídeo.
- Upload para nuvem.
- Compartilhamento externo.
- Multiusuário.
- Plugin system.

Esses recursos podem ser avaliados depois, se o uso local justificar.

## 6. Arquitetura proposta

Criar uma nova camada em `src/media/`.

```txt
src/media/
  __init__.py
  sources.py
  metadata.py
  downloader.py
  ffmpeg.py
  audio.py
  artifacts.py
  options.py
```

Responsabilidades sugeridas:

```txt
sources.py
  Define origem da mídia:
  - URL remota
  - arquivo local
  - pasta local, no futuro

metadata.py
  Lê e normaliza metadados:
  - título
  - duração
  - origem
  - extensão
  - bitrate
  - sample rate
  - streams

downloader.py
  Encapsula uso de yt-dlp:
  - metadata
  - download de áudio
  - nome de arquivo seguro
  - cache

ffmpeg.py
  Wrapper baixo nível para ffmpeg/ffprobe:
  - execução de comandos
  - captura de stdout/stderr
  - tratamento de erro
  - validação de binários disponíveis

audio.py
  Operações de áudio:
  - converter
  - cortar
  - normalizar
  - remover metadados
  - preservar metadados

artifacts.py
  Organização de saídas:
  - diretório da execução
  - nomes consistentes
  - metadata.json
  - paths finais

options.py
  Dataclasses de opções:
  - AudioDownloadOptions
  - AudioConvertOptions
  - AudioTrimOptions
  - AudioNormalizeOptions
  - MediaPipelineOptions
```

## 7. Tipos sugeridos

### 7.1 AudioArtifact

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioArtifact:
    path: Path
    format: str
    duration: float | None = None
    bitrate: str | None = None
    sample_rate: int | None = None
    title: str | None = None
    source_url: str | None = None
```

### 7.2 MediaMetadata

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaMetadata:
    title: str | None
    duration: float | None
    source_url: str | None
    extractor: str | None = None
    channel: str | None = None
    webpage_url: str | None = None
```

### 7.3 Opções de áudio

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioDownloadOptions:
    output_format: str = "mp3"
    bitrate: str | None = "192k"
    preserve_metadata: bool = True


@dataclass(frozen=True)
class AudioConvertOptions:
    output_format: str = "mp3"
    bitrate: str | None = "192k"
    preserve_metadata: bool = True


@dataclass(frozen=True)
class AudioTrimOptions:
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class AudioNormalizeOptions:
    enabled: bool = False
    mode: str = "loudnorm"
```

## 8. Funções principais sugeridas

```python
from pathlib import Path


def fetch_media_metadata(url: str) -> MediaMetadata:
    ...


def download_audio(
    url: str,
    output_dir: Path,
    options: AudioDownloadOptions,
) -> AudioArtifact:
    ...


def probe_audio(path: Path) -> AudioArtifact:
    ...


def convert_audio(
    input_path: Path,
    output_dir: Path,
    options: AudioConvertOptions,
) -> AudioArtifact:
    ...


def trim_audio(
    input_path: Path,
    output_dir: Path,
    options: AudioTrimOptions,
) -> AudioArtifact:
    ...


def normalize_audio(
    input_path: Path,
    output_dir: Path,
    options: AudioNormalizeOptions,
) -> AudioArtifact:
    ...
```

Essas funções não devem depender da GUI. A GUI deve apenas chamar o pipeline e
receber eventos via `EventBus`.

## 9. Organização de arquivos de saída

A saída deve ser organizada por execução. Isso facilita depuração, reuso e
exibição na aba de resultados.

Estrutura recomendada:

```txt
output/
  2026-05-29_nome-do-video/
    metadata.json
    audio.original.m4a
    audio.mp3
    audio.trimmed.mp3
    audio.normalized.mp3
    transcript.md
    analysis.md
    prompt.md
```

Alternativa mais próxima do estado atual:

```txt
data/
  audios/
    raw/
    converted/
    trimmed/
    normalized/
  transcripts/
  analysis/
  prompts/
```

Recomendação: preferir a estrutura por execução em `output/`, porque ela agrupa
todos os artefatos gerados no mesmo fluxo.

## 10. Novos modos de execução na GUI

Adicionar um seletor no formulário esquerdo após o PR 2.

```txt
Modo de execução
[ Transcrever ]
```

Opções iniciais:

```txt
Transcrever
Baixar áudio
Converter áudio local
Baixar + converter
Baixar + transcrever
Cortar áudio
```

Campos condicionais por modo:

```txt
Transcrever:
  - URL ou arquivo local
  - modelo Whisper
  - idioma
  - beam size
  - opções atuais de format/analyze/prompt

Baixar áudio:
  - URL
  - formato
  - bitrate
  - preservar metadados

Converter áudio local:
  - arquivo local
  - formato
  - bitrate
  - preservar metadados

Baixar + converter:
  - URL
  - formato
  - bitrate
  - preservar metadados

Baixar + transcrever:
  - URL
  - formato intermediário
  - opções Whisper

Cortar áudio:
  - arquivo local ou URL
  - início
  - fim
  - formato de saída
```

## 11. Eventos novos para o EventBus

A expansão deve seguir a mesma filosofia do plano atual: eventos explícitos para
etapas estruturais e logs capturados para detalhes granulares.

Eventos sugeridos:

```txt
media_metadata_start
media_metadata_done
audio_download_start
audio_download_done
audio_cache_hit
audio_probe_start
audio_probe_done
audio_convert_start
audio_convert_done
audio_trim_start
audio_trim_done
audio_normalize_start
audio_normalize_done
artifact_ready
media_pipeline_done
media_pipeline_error
```

Mensagens sugeridas para a GUI:

```txt
[i] Fetching media metadata...
[i] Title: {title}
[i] Duration: {duration}
[»] Audio already exists, skipping download: {audio_path}
[i] Downloading audio...
[✓] Audio downloaded: {audio_path}
[*] Converting audio to {format} ({bitrate})...
[✓] Audio converted: {output_path}
[*] Trimming audio from {start} to {end}...
[✓] Audio trimmed: {output_path}
[*] Normalizing audio...
[✓] Audio normalized: {output_path}
[✓] Artifact ready: {output_path}
[✓] Media pipeline complete.
[!] Error: {message}
```

## 12. Integração com o pipeline atual

A transcrição deve passar a receber um `AudioArtifact` ou um `Path` derivado do
artefato.

Fluxo atual presumido:

```txt
URL -> download_audio -> transcribe -> format/analyze/prompt
```

Fluxo futuro:

```txt
MediaSource -> AudioArtifact -> optional audio operations -> transcribe
```

O worker da GUI pode orquestrar os passos, mas não deve conter lógica de
`ffmpeg` ou `yt-dlp` diretamente. A lógica deve ficar em `src/media/`.

## 13. Estratégia de PRs

### 13.1 PR 3: núcleo local de áudio

Objetivo: criar a base sem alterar significativamente a GUI.

Checklist:

- [ ] Criar `src/media/`.
- [ ] Criar dataclasses de opções.
- [ ] Criar `AudioArtifact`.
- [ ] Criar wrapper para `ffmpeg` e `ffprobe`.
- [ ] Criar função `probe_audio()`.
- [ ] Criar função `convert_audio()`.
- [ ] Criar função `trim_audio()`.
- [ ] Criar função `normalize_audio()`.
- [ ] Criar testes unitários para funções puras e montagem de comandos.
- [ ] Validar erro claro quando `ffmpeg` não estiver disponível.

Critério de aceitação:

- [ ] Converter um arquivo local para `mp3`.
- [ ] Converter um arquivo local para `wav`.
- [ ] Cortar um arquivo por timestamps.
- [ ] Normalizar um arquivo.
- [ ] Gerar artefatos em diretório previsível.
- [ ] Nenhuma regressão no CLI atual.

### 13.2 PR 4: modo "Baixar áudio"

Objetivo: primeiro modo novo visível na GUI.

Checklist:

- [ ] Adicionar seletor de modo no formulário.
- [ ] Adicionar modo "Baixar áudio".
- [ ] Usar campo de URL existente.
- [ ] Adicionar formato e bitrate.
- [ ] Emitir eventos de metadata, download e artifact.
- [ ] Mostrar card final na aba de resultados.
- [ ] Manter logs no painel direito.

Critério de aceitação:

- [ ] Colar URL.
- [ ] Escolher formato.
- [ ] Baixar áudio sem transcrever.
- [ ] Ver arquivo final na aba de resultados.
- [ ] Abrir pasta do artefato.

### 13.3 PR 5: conversão e corte

Objetivo: permitir manipulação local de arquivos e de áudio baixado.

Checklist:

- [ ] Adicionar input de arquivo local.
- [ ] Adicionar modo "Converter áudio local".
- [ ] Adicionar campos de corte: início e fim.
- [ ] Validar timestamps.
- [ ] Exibir erros de validação na GUI.
- [ ] Exibir artefatos gerados.

Critério de aceitação:

- [ ] Converter arquivo local.
- [ ] Cortar arquivo local.
- [ ] Baixar e converter áudio de URL.
- [ ] Baixar e cortar áudio de URL.

### 13.4 PR 6: composição com transcrição

Objetivo: permitir que áudio processado seja transcrito.

Checklist:

- [ ] Permitir pipeline "Baixar + transcrever".
- [ ] Permitir pipeline "Baixar + converter + transcrever".
- [ ] Permitir pipeline "Arquivo local + converter + transcrever".
- [ ] Garantir que Whisper receba apenas o arquivo final processado.
- [ ] Atualizar card de resumo com todos os artefatos.

Critério de aceitação:

- [ ] Baixar áudio, converter para formato intermediário e transcrever.
- [ ] Cortar trecho de um áudio e transcrever apenas esse trecho.
- [ ] Manter format/analyze/prompt funcionando quando selecionados.

### 13.5 PR 7: histórico local e presets

Objetivo: melhorar uso pessoal recorrente.

Checklist:

- [ ] Criar presets locais.
- [ ] Criar histórico simples baseado em diretórios de saída.
- [ ] Salvar `metadata.json` por execução.
- [ ] Mostrar execuções recentes na GUI, se útil.

Presets sugeridos:

```txt
Whisper rápido:
  formato: wav
  normalizar: não
  cortar: opcional

Podcast:
  formato: mp3
  bitrate: 192k
  normalizar: sim

Arquivo leve:
  formato: opus
  bitrate: 96k
  normalizar: não

Alta qualidade:
  formato: m4a
  bitrate: 256k
  preservar metadados: sim
```

## 14. Validações necessárias

### 14.1 Validação de dependências

Ao iniciar a aplicação ou ao executar um modo de áudio, validar:

```txt
ffmpeg disponível
ffprobe disponível
yt-dlp disponível ou biblioteca Python instalada
```

A mensagem de erro deve ser objetiva:

```txt
[!] Error: ffmpeg not found. Install ffmpeg and ensure it is available in PATH.
```

### 14.2 Validação de timestamps

Aceitar formatos:

```txt
SS
MM:SS
HH:MM:SS
```

Regras:

- Início deve ser menor que fim.
- Fim não pode ser maior que a duração, quando a duração for conhecida.
- Campos vazios devem ser permitidos em alguns modos.

### 14.3 Validação de formato

Formatos iniciais permitidos:

```txt
mp3
wav
m4a
opus
ogg
```

Bitrate deve ser ignorado ou desabilitado para `wav`.

## 15. Comandos de referência

Exemplos conceituais. O Claude Code deve adaptar para wrapper Python seguro com
`subprocess.run()` e argumentos em lista, sem shell quando possível.

### 15.1 Converter para MP3

```bash
ffmpeg -y -i input.m4a -vn -codec:a libmp3lame -b:a 192k output.mp3
```

### 15.2 Converter para WAV

```bash
ffmpeg -y -i input.m4a -vn -acodec pcm_s16le -ar 16000 -ac 1 output.wav
```

### 15.3 Cortar áudio

```bash
ffmpeg -y -ss 00:01:00 -to 00:03:00 -i input.mp3 -c copy output.trimmed.mp3
```

Observação: `-c copy` é rápido, mas pode cortar em pontos menos precisos em
alguns formatos. Para corte preciso, reencodar.

### 15.4 Normalizar com loudnorm

```bash
ffmpeg -y -i input.mp3 -af loudnorm output.normalized.mp3
```

### 15.5 Extrair áudio com yt-dlp

```bash
yt-dlp -x --audio-format mp3 --audio-quality 192K -o "output/%(title)s.%(ext)s" "<URL>"
```

## 16. Cuidados de implementação

### 16.1 Não usar shell=True

Montar comandos como lista:

```python
subprocess.run(
    ["ffmpeg", "-y", "-i", str(input_path), str(output_path)],
    check=True,
    capture_output=True,
    text=True,
)
```

### 16.2 Sanitizar nomes de arquivo

Toda origem remota deve gerar nomes seguros para o filesystem. Evitar confiar em título de vídeo sem normalização.

### 16.3 Não quebrar o CLI

A compatibilidade do CLI continua sendo requisito. Se a expansão exigir novas
opções, elas devem ser aditivas.

### 16.4 Não acoplar GUI e media core

`src/media/` não deve importar Flet. A GUI pode importar `src/media/`, mas nunca
o contrário.

### 16.5 Não duplicar logs

Seguir a mesma regra do plano atual: evento estrutural para etapas principais;
logging para detalhe granular; `LogEventHandler` deve evitar duplicação quando
necessário.

## 17. Testes recomendados

### 17.1 Testes unitários

Testar:

- Parsing de timestamp.
- Geração de paths.
- Sanitização de nomes.
- Montagem de comandos `ffmpeg`.
- Montagem de opções de download.
- Conversão de `MediaMetadata` para `metadata.json`.

### 17.2 Testes manuais

Casos mínimos:

```txt
1. Baixar áudio de URL curta.
2. Baixar áudio quando o arquivo já existe.
3. Converter arquivo local para MP3.
4. Converter arquivo local para WAV.
5. Cortar de 00:00:10 até 00:00:30.
6. Normalizar áudio.
7. Baixar e transcrever.
8. Baixar, cortar e transcrever.
9. Cancelar pipeline durante download/conversão.
10. Rodar novamente com outra URL.
```

## 18. Critérios de aceitação finais

A expansão local de áudio estará aceitável quando:

- [ ] O usuário conseguir baixar áudio sem transcrever.
- [ ] O usuário conseguir converter áudio local.
- [ ] O usuário conseguir cortar áudio por timestamp.
- [ ] O usuário conseguir normalizar áudio.
- [ ] O usuário conseguir usar áudio processado como entrada de transcrição.
- [ ] Todos os artefatos aparecerem na aba de resultados.
- [ ] O painel de logs mostrar cada etapa com prefixos consistentes.
- [ ] Erros de dependência e validação aparecerem de forma clara.
- [ ] O CLI atual continuar funcionando.
- [ ] A GUI continuar estável em reruns.
- [ ] Nenhuma lógica de mídia depender diretamente de Flet.

## 19. Prompt sugerido para Claude Code

```txt
Leia primeiro docs/GUI_REFACTOR_PLAN.md e confirme o estado atual da refatoração.

Depois leia este documento e faça apenas planejamento inicial da expansão local
de áudio. Não implemente nada antes de validar o plano.

Premissas:
- O projeto é pessoal e roda localmente.
- Não criar API pública.
- Não integrar com a API pública do cobalt.tools.
- Usar o cobalt apenas como referência de UX.
- Preferir yt-dlp + ffmpeg/ffprobe.
- Não quebrar o CLI.
- Não acoplar src/media à GUI Flet.
- Implementar somente depois de PR 1 e PR 2 estarem estáveis.

Tarefas:
1. Inspecione a estrutura atual do projeto.
2. Identifique onde hoje ficam download, cache, transcrição, workers e eventos.
3. Proponha a estrutura exata de src/media/ considerando o código existente.
4. Liste arquivos que seriam criados e alterados.
5. Proponha PRs pequenos e sequenciais.
6. Aponte riscos de regressão no CLI e na GUI.
7. Consulte documentação atual de Flet via context7 se precisar mexer na GUI.
8. Consulte documentação atual de yt-dlp e ffmpeg se precisar validar comandos.
9. Não implemente até o plano ser aprovado.
```

## 20. Referências

- cobalt GitHub: <https://github.com/imputnet/cobalt>
- cobalt API docs: <https://github.com/imputnet/cobalt/blob/main/docs/api.md>
- cobalt API license notes: <https://github.com/imputnet/cobalt/blob/main/api/README.md>
- yt-dlp GitHub: <https://github.com/yt-dlp/yt-dlp>
- FFmpeg filters documentation: <https://ffmpeg.org/ffmpeg-filters.html>
- FFmpeg audio volume notes: <https://trac.ffmpeg.org/wiki/AudioVolume>
