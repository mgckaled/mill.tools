"""Conteúdo de ajuda por controle — texto curto (tooltip) e longo (modal opcional).

Chave: "<módulo>.<campo>". Editar aqui é o único lugar para ajustar a cópia.
"""

from __future__ import annotations

#: Texto curto exibido no tooltip (hover). 1–2 frases.
HELP_SHORT: dict[str, str] = {
    # --- Transcrição ---
    "transcription.whisper_model": (
        "Modelo do Whisper. Maiores = mais precisos e mais lentos. "
        "'small' equilibra bem; use 'medium'/'large' em áudio difícil."
    ),
    "transcription.language": (
        "Idioma do áudio. 'auto' detecta sozinho; fixar o idioma evita erros "
        "de detecção em áudios curtos ou ruidosos."
    ),
    "transcription.beam_size": (
        "Largura da busca do decodificador. 1 = mais rápido; "
        "3–5 = um pouco mais preciso e mais lento."
    ),
    "transcription.format": (
        "Reinsere quebras de parágrafo na transcrição via LLM, sem alterar o texto."
    ),
    "transcription.analyze": (
        "Gera uma análise estruturada (resumo, pontos-chave, citações…) "
        "a partir da transcrição."
    ),
    "transcription.analysis_profile": (
        "Perfil de análise: troca o esquema de campos e o prompt conforme o tipo "
        "de conteúdo (aula, entrevista, tutorial, reunião…). Não altera o "
        "formulário, só o que é extraído. 'Geral' mantém o esquema padrão. "
        "Ao escolher um texto já indexado, a IA pré-seleciona o perfil mais "
        "provável (chip 'Sugerido: ...') — você pode aceitar ou trocar."
    ),
    "transcription.prompt": (
        "Cria uma versão condensada (~40%) da transcrição, "
        "pronta para colar como contexto em prompts."
    ),
    "transcription.subtitles": (
        "Gera arquivos .srt e .vtt com timestamps a partir dos mesmos "
        "segmentos do Whisper — sem custo extra de GPU."
    ),
    "transcription.model_stage": (
        "Modelo desta etapa. Nomes começando com 'gemini' usam a nuvem "
        "(requer GOOGLE_API_KEY); os demais rodam local no Ollama."
    ),
    # --- Áudio ---
    "audio.input": (
        "Cole URLs (YouTube, SoundCloud…) ou selecione arquivos locais. "
        "URLs são baixadas; arquivos locais são convertidos/extraídos."
    ),
    "audio.format": (
        "'best' mantém o codec original sem reconverter (sem perda extra); "
        "os demais convertem via ffmpeg."
    ),
    "audio.bitrate": (
        "Taxa de bits para formatos com perda. Não melhora a fonte — "
        "acima de ~192 kbps pode só inflar o arquivo. Ignorado em 'best' e 'wav'."
    ),
    "audio.embed_meta": (
        "Embute título, autor e capa no arquivo de saída. "
        "Em ogg/opus a capa pode ser omitida automaticamente."
    ),
    "audio.denoise": (
        "Atenua ruído de fundo constante (ventilador, hum, chiado de fita) via spectral gating. "
        "Requer noisereduce e soundfile instalados."
    ),
    "audio.normalize": (
        "Ajusta o volume para um nível consistente em LUFS via ffmpeg loudnorm. "
        "Não distorce nem clipa (True Peak ≤ −1 dBFS)."
    ),
    "audio.normalize_lufs": (
        "Alvo de loudness integrado. −14 LUFS: streaming (Spotify/YouTube). "
        "−23 LUFS: broadcast. −16 a −18 LUFS: podcasts."
    ),
    "audio.channels": (
        "Mono reduz o arquivo pela metade e acelera a transcrição. "
        "16 kHz é a taxa nativa do Whisper — ideal para 'Pronto p/ transcrição'."
    ),
    "audio.trim_silence": (
        "Remove silêncio do início, fim e meio do áudio via ffmpeg silenceremove. "
        "Útil para limpar aulas e podcasts antes de transcrever."
    ),
    "audio.speed": (
        "Acelera/desacelera sem alterar o tom (atempo). 1,25–1,5× corta o tempo "
        "de transcrição proporcionalmente."
    ),
    # --- Vídeo ---
    "video.input": (
        "Cole a URL do vídeo ou selecione um arquivo local. "
        "Suporta YouTube, Vimeo, Twitter, Instagram, TikTok, Twitch e centenas de outros via yt-dlp."
    ),
    "video.operation": (
        "O que fazer com o vídeo. 'Converter' sem reencoding usa -c copy (rápido, sem perda extra)."
    ),
    "video.resolution": (
        "Resolução máxima do download. Resoluções maiores = arquivo maior e download mais lento."
    ),
    "video.embed_meta": (
        "Embute título, uploader e outros metadados no arquivo de saída via FFmpegMetadata."
    ),
    "video.codec": (
        "'copy' preserva codec original sem reencoding (rápido, sem perda). "
        "H.264 é o mais compatível para reprodução em qualquer dispositivo."
    ),
    "video.trim": (
        "Recorta um trecho. 'Corte rápido' usa -c copy (impreciso ao keyframe mais próximo). "
        "'Frame-preciso' reencoda com H.264 — mais lento, mas exato."
    ),
    "video.crf": (
        "Fator de qualidade do H.264. 18 = alta qualidade. 23 = padrão ffmpeg. 28 = arquivo menor."
    ),
    "video.preset": (
        "Velocidade de encoding H.264. 'medium' é o equilíbrio padrão. "
        "'slow' gera arquivo menor, mas demora mais."
    ),
    "video.resize": (
        "Redimensiona preservando aspect ratio. "
        "Deixe largura ou altura em branco para calcular automaticamente."
    ),
    "video.subtitle": (
        "Insere uma legenda .srt/.vtt no vídeo. 'Embutir' adiciona uma faixa "
        "toggleável sem reencodar (rápido). 'Queimar' grava a legenda na imagem "
        "(permanente, reencoda — ideal para Shorts/Reels)."
    ),
    # --- Imagens ---
    "image.input": (
        "Cole URLs diretas de imagens ou selecione arquivos locais. "
        "URLs são baixadas; arquivos locais são convertidos. "
        "Link de página HTML de banco de imagens não funciona — use o link direto do arquivo."
    ),
    "image.format": (
        "Formato de saída. PNG/TIFF/BMP são sem perda; "
        "JPG/WebP usam compressão com perda (controlada pela qualidade); "
        "AVIF é moderno e compacto."
    ),
    "image.quality": (
        "Qualidade de compressão (50–100) para formatos com perda (JPG/WebP). "
        "Maior = melhor imagem e arquivo maior. Ignorada em formatos sem perda."
    ),
    "image.resize": (
        "Caber: redimensiona proporcionalmente dentro do limite. "
        "Exato: força as dimensões (pode distorcer). "
        "Escala %: reduz ou amplia na porcentagem indicada."
    ),
    "image.crop": (
        "Manual: define região em px (0 = até a borda). "
        "Proporção: recorta o maior retângulo da proporção escolhida, centralizado. "
        "Auto-trim: remove bordas da cor indicada. "
        "Smart: recorta para uma proporção alvo mantendo um ponto focal "
        "(sliders X/Y) sempre enquadrado."
    ),
    "image.rotate": (
        "Ângulo em múltiplos de 90°. EXIF auto corrige a orientação registrada pela câmera. "
        "Espelhar H/V é independente do ângulo."
    ),
    "image.watermark": (
        "Texto: fonte embutida, sem dependência do sistema. "
        "Imagem: sobreposição redimensionada a 25% da largura. "
        "QR Code: gera e aplica um QR a partir do texto/URL informado. "
        "Posição: grade 3×3 ou 'tile' (repete em mosaico). "
        "Opacidade 0 = invisível, 100 = sólida; rotação em graus."
    ),
    "image.border": (
        "Adiciona borda sólida em torno da imagem. "
        "'Preencher alpha' substitui transparência pela cor da borda antes — "
        "necessário para salvar em JPEG."
    ),
    "image.exif": (
        "Controla os metadados EXIF da saída. Preservar copia os dados originais; "
        "Remover GPS tira só a localização; Remover tudo zera os metadados (privacidade); "
        "Injetar grava Artista/Copyright/Descrição."
    ),
    "image.ocr": (
        "Extrai texto da imagem via Tesseract e salva um .txt indexável no RAG. "
        "Escolha o idioma (ou combine por+eng). Requer o extra [ocr] e o binário do Tesseract."
    ),
    "image.adjust": (
        "Sliders de 0.1 a 2.0; 1.0 = sem alteração. "
        "Brilho e Contraste são os mais impactantes. "
        "Saturação 0.1 ≈ preto e branco."
    ),
    "image.filter": (
        "Blur/Sharpen: convolução. Autocontraste: estica o histograma. "
        "Equalizar: redistribui histograma. Grayscale: tons de cinza."
    ),
    "image.favicon": (
        "Gera um .ico com múltiplas resoluções embutidas. Marque os tamanhos desejados."
    ),
    "image.contact_sheet": (
        "Monta uma grade com todas as imagens da fila. "
        "O resultado é uma única imagem de saída."
    ),
    "image.rembg_model": (
        "u2net: geral (padrão, ~170MB). u2netp: rápido e leve (~4MB). "
        "silueta: compacto (~43MB). isnet: recortes precisos. "
        "humano: otimizado para pessoas. Todos rodam na CPU; "
        "1ª execução baixa o modelo."
    ),
    "image.describe_model": (
        "Modelo com suporte a visão. moondream-custom: leve e rápido. "
        "gemma3-4b-custom: melhor qualidade e PT-BR nativo, porém mais lento (CPU). "
        "llava:7b / minicpm-v: alternativas locais. glm-4.6v-flash / gemini-2.5-flash: "
        "nuvem (tier grátis) — a imagem sai da máquina."
    ),
    "image.describe_prompt": (
        "Instrução enviada ao modelo. Preenchida pelo preset escolhido acima "
        "(Estilo de descrição) — editável antes de rodar."
    ),
    # --- Documentos ---
    "document.input": (
        "Selecione um ou mais PDFs — ou uma URL direta para download. "
        "Unir e Imagens→PDF aceitam múltiplos arquivos."
    ),
    "document.operation": "Escolha a operação a realizar sobre o(s) documento(s).",
    "document.pages": (
        'Intervalo de páginas: "1-3,5,8-" = págs. 1, 2, 3, 5, 8 até o fim. '
        "Numeração começa em 1."
    ),
    "document.image_quality": (
        "Qualidade das imagens recomprimidas. "
        "75 = boa relação tamanho/qualidade. Menor = arquivo menor, mais artefatos."
    ),
    "document.watermark": "Marca d'água sutil em diagonal sobre todas as páginas.",
    "document.stamp": "Carimbo em destaque centralizado na página: PAGO, RASCUNHO, etc.",
    "document.password": (
        "Criptografia AES-256. Guarde a senha — não é possível recuperá-la."
    ),
    "document.dpi": ("Resolução da rasterização. 150 = boa qualidade; 300 = imprimir."),
    "document.qr_size": "Tamanho do QR code gerado em pixels.",
    "document.analyze_model": "Modelo para análise do conteúdo extraído. Local ou Gemini.",
    "document.ocr": (
        "Reconhece texto em PDFs escaneados via Tesseract. Páginas que já têm "
        "camada de texto são lidas direto; só as imagens são processadas por OCR. "
        "300 DPI é o piso recomendado para boa precisão."
    ),
    # --- Biblioteca ---
    "library": (
        "Reúne tudo que você já gerou — áudio, vídeo, imagens, transcrições, "
        "documentos e dados — num só lugar. Filtre por tipo, busque por nome "
        "ou tag, reabra arquivos ou reenvie uma saída para outro módulo num "
        "clique. Tem também um Painel de estatísticas e um Mapa semântico."
    ),
    # --- IA ---
    "ai.scope": (
        "Onde buscar a resposta: todo o acervo, apenas um tipo (transcrições, "
        "documentos, descrições de imagem) ou um único documento."
    ),
    "ai.model": (
        "Modelo que redige a resposta. Nomes começando com 'gemini' usam a "
        "nuvem (requer GOOGLE_API_KEY) e recebem os trechos recuperados; "
        "os demais rodam local no Ollama."
    ),
    "ai.question": (
        "Pergunte em linguagem natural sobre o que você já processou. "
        "A resposta usa apenas o seu acervo e cita as fontes [n]."
    ),
    "ai.index": (
        "Índice semântico local do seu acervo. Reindexar embute só os arquivos "
        "novos ou alterados (incremental, por mtime)."
    ),
    "ai": (
        "Converse com o seu próprio acervo — RAG 100% local. Indexa transcrições, "
        "textos de PDF, descrições de imagem e cartões de dados, e responde "
        "citando as fontes."
    ),
    # --- Dados ---
    "data": (
        "Consulte planilhas e arquivos de dados (CSV, TSV, JSON, Parquet, XLSX) "
        "com o motor DuckDB. Descreva o que quer em português — a IA traduz para "
        "SQL vendo só os nomes de coluna; o conteúdo das tabelas fica 100% local. "
        "Abas: Consulta · Pré-visualização · Análise com IA · Gráfico."
    ),
    # --- Receitas ---
    "recipes": (
        "Encadeie módulos numa sequência automática: a saída de cada passo vira "
        "a entrada do próximo. Rode um preset pronto ou monte a sua receita."
    ),
    "recipes.batch": (
        "Roda a receita uma vez por arquivo da fila, de forma independente. "
        "Desligado, uma única execução consome todos os arquivos juntos — útil "
        "para mesclar PDFs ou montar um PDF a partir de várias imagens."
    ),
    "recipes.clean": (
        "Ao terminar, apaga os arquivos gerados pelos passos intermediários "
        "(ex.: o áudio baixado antes de transcrever). Mantém as saídas finais "
        "e os seus arquivos de entrada."
    ),
    # --- Observatório ---
    "observatory.gates": (
        "Disponibilidade dos extras opcionais de ML/NLP e do embedder do RAG. "
        "Um X não quebra o app — só desativa aquele recurso, com a dica de "
        "instalação ao lado."
    ),
    "observatory.ollama": (
        "Quais dos modelos *-custom do app (ollama/Modelfile*) estão puxados "
        "no seu Ollama local agora."
    ),
    "observatory.binaries": (
        "Onde o app encontrou (ou não) os binários externos que ele invoca "
        "via subprocess — yt-dlp, ffmpeg, ffprobe e Tesseract."
    ),
    "observatory.cloud": (
        "Se GOOGLE_API_KEY/ZHIPU_API_KEY estão presentes no .env — nunca "
        "mostra a chave em si, só se está configurada."
    ),
    "observatory.classify": (
        "Quantos rótulos de treino existem por domínio e se o classificador já "
        "usa um modelo supervisionado ou ainda está em zero-shot."
    ),
    "observatory.config": (
        "Parâmetros internos de ML em vigor agora, lidos direto do código-fonte "
        "— nunca uma cópia hardcoded que poderia divergir."
    ),
}

#: Texto longo (opcional) — quando presente, a ⓘ vira clicável e abre um modal.
HELP_LONG: dict[str, str] = {
    "transcription.whisper_model": (
        "Modelos disponíveis, do mais rápido ao mais preciso:\n\n"
        "• tiny — ultrarápido, ~1 GB VRAM. Boa para testes e áudios simples.\n"
        "• base — rápido, levemente mais preciso que tiny.\n"
        "• small — equilíbrio ideal para uso geral. Recomendado como padrão.\n"
        "• medium — mais preciso em sotaques e vocabulário técnico; ~2–3× mais lento.\n"
        "• large-v3-turbo — qualidade próxima ao large-v3 com velocidade melhorada.\n"
        "• large-v3 — máxima precisão disponível; mais lento e exige mais VRAM.\n\n"
        "Hardware desta máquina: MX150 (2 GB VRAM, Pascal). Para VRAM limitada, "
        "prefira small ou medium com compute_type int8_float32. "
        "large-v3 pode causar OOM neste hardware."
    ),
    "audio.bitrate": (
        "O bitrate define quantos kbps o codec usa em formatos com perda "
        "(mp3, m4a, ogg, opus).\n\n"
        "Pontos importantes:\n"
        "• Não recupera qualidade que não existe na fonte — converter um áudio "
        "de 128 kbps para 320 kbps não melhora nada, só aumenta o arquivo.\n"
        "• 128–192 kbps costuma ser transparente para fala; música pede mais.\n"
        "• É ignorado quando o formato é 'best' (sem reencode) ou 'wav' (sem perda)."
    ),
    "image.rembg_model": (
        "Modelos disponíveis:\n\n"
        "• u2net — geral, padrão (~170 MB). Boa cobertura para a maioria das imagens.\n"
        "• u2netp — versão comprimida do u2net (~4 MB). Mais rápido, menor precisão.\n"
        "• silueta — compacto (~43 MB), focado em silhuetas nítidas.\n"
        "• isnet — recortes de alta precisão com detalhes finos de borda.\n"
        "• humano — especializado em segmentação de pessoas.\n\n"
        "Todos rodam 100% na CPU via ONNX Runtime. O modelo é baixado para "
        "~/.u2net/ automaticamente na primeira execução de cada variante."
    ),
    "image.describe_model": (
        "Modelos com suporte a visão:\n\n"
        "• moondream-custom — leve (~800 MB RAM), rápido. Bom para uma descrição ágil.\n"
        "  Setup: ollama pull moondream && ollama create moondream-custom -f ollama/Modelfile.vision\n"
        "• gemma3-4b-custom — melhor qualidade e PT-BR nativo, lê texto na imagem muito melhor;\n"
        "  multimodal de fábrica (~3,3 GB), porém mais lento na CPU.\n"
        "  Setup: ollama pull gemma3:4b && ollama create gemma3-4b-custom -f ollama/Modelfile.gemma3-4b\n"
        "• llava:7b — mais capaz e detalhado, requer ~4 GB RAM.\n"
        "• minicpm-v — alternativa leve com bom desempenho em PT-BR.\n"
        "• glm-4.6v-flash — nuvem (Zhipu/Z.ai, tier grátis), sem instalar nada; "
        "a imagem sai da máquina. Requer ZHIPU_API_KEY no .env.\n"
        "• gemini-2.5-flash — nuvem (Google, tier grátis), sem instalar nada; "
        "a imagem sai da máquina. Requer GOOGLE_API_KEY no .env.\n\n"
        "A descrição é salva como .txt em output/image/processed/ (indexável no RAG, "
        "reaproveitável via Biblioteca). Modelos locais devem estar instalados no Ollama antes de usar."
    ),
    "audio.denoise": (
        "Redução de Ruído — Spectral Gating\n\n"
        "Analisa o espectro do áudio e atenua as frequências que se comportam como ruído "
        "estacionário. Bom para ventiladores, ar-condicionado, hum de fio e chiado de fita.\n\n"
        "Tipo de ruído: 'Constante' assume um perfil de ruído fixo ao longo do "
        "áudio (mais rápido); 'Variável' reestima o perfil continuamente, útil "
        "quando o ruído de fundo muda de intensidade.\n\n"
        "A saída é sempre WAV para não perder qualidade no passo intermediário. "
        "Roda 100% na CPU (noisereduce + soundfile), sem dependência extra para instalar."
    ),
    "audio.normalize": (
        "Normalização de Volume — EBU R128\n\n"
        "Usa o filtro loudnorm do ffmpeg em dois passos: primeiro mede o loudness integrado "
        "(LUFS), depois aplica ganho linear para atingir o alvo preservando o True Peak "
        "(máx. −1 dBFS).\n\n"
        "• −14 LUFS: Spotify, Apple Music, YouTube.\n"
        "• −23 LUFS: broadcast (TV/rádio).\n"
        "• −16 a −18 LUFS: podcasts.\n\n"
        "O resultado mantém o mesmo contêiner e codec do arquivo de entrada."
    ),
    "video.codec": (
        "Codec de Vídeo\n\n"
        "'copy' é o modo mais rápido: o ffmpeg apenas remonta o container sem reprocessar o vídeo. "
        "H.264 (libx264) é o codec mais compatível para reprodução em qualquer dispositivo. "
        "H.265 (libx265) gera arquivos ~50% menores que H.264 com a mesma qualidade, "
        "mas o encoding é ~3× mais lento. "
        "VP9 é ideal para WebM/web, com boa compressão e formato aberto."
    ),
    "video.crf": (
        "CRF — Constant Rate Factor\n\n"
        "Controla a qualidade do encoding H.264. Valores menores = melhor qualidade = arquivo maior.\n"
        "• 18: praticamente imperceptível vs original.\n"
        "• 23: padrão do ffmpeg, boa qualidade.\n"
        "• 28: compressão visível, arquivo pequeno.\n\n"
        "Para arquivamento use 18–20; para compartilhamento use 23–26."
    ),
    "transcription.beam_size": (
        "O decodificador do Whisper usa busca em feixe (beam search) para gerar "
        "a transcrição.\n\n"
        "• beam_size=1 (greedy): mais rápido, usa menos memória.\n"
        "• beam_size=3–5: explora mais candidatos, pode melhorar a precisão em "
        "trechos ambíguos, porém aumenta o tempo de processamento proporcionalmente.\n"
        "• Para a maioria dos casos (fala clara, português ou inglês), "
        "beam_size=1 já produz resultados excelentes."
    ),
    "video.input": (
        "Sites suportados pelo yt-dlp (seleção):\n\n"
        "Principais:\n"
        "• YouTube e YouTube Shorts (youtube.com, youtu.be)\n"
        "• Vimeo\n"
        "• Twitter / X\n"
        "• Instagram — posts, Reels, Stories\n"
        "• Facebook\n"
        "• TikTok\n"
        "• Dailymotion\n"
        "• Twitch — clipes e VODs\n\n"
        "Outros:\n"
        "• LinkedIn, Reddit, Pinterest (vídeos)\n"
        "• Rumble, Odysee / LBRY\n"
        "• Bilibili, Niconico\n"
        "• Streamable, Imgur (vídeo)\n"
        "• Globoplay, Band, R7 (portais BR)\n\n"
        "Lista completa: yt-dlp --list-extractors (1000+ sites)"
    ),
    "document.pages": (
        "Formato de intervalo de páginas\n\n"
        "1-3     → páginas 1, 2, 3\n"
        "1,3,5   → páginas 1, 3, 5\n"
        "8-      → página 8 até o fim\n"
        "1-3,5,8- → combinação\n\n"
        "Numeração começa em 1."
    ),
    "document.password": (
        "Criptografia de PDF\n\n"
        "O documento é protegido com AES-256 (padrão PDF 1.7).\n\n"
        "Não há como recuperar a senha esquecida — "
        "guarde-a em um gerenciador de senhas."
    ),
    "document.dpi": (
        "Resolução de rasterização\n\n"
        "72 dpi  → tela, arquivos menores\n"
        "96 dpi  → padrão web\n"
        "150 dpi → boa qualidade, equilíbrio\n"
        "300 dpi → impressão profissional\n\n"
        "A cada dobro de DPI, o tamanho do arquivo quadruplica."
    ),
    "library": (
        "Biblioteca — o índice de tudo que o mill.tools já produziu.\n\n"
        "O que ela mostra:\n"
        "• Todos os arquivos sob output/ — áudio, vídeo, imagens, transcrições, "
        "documentos e dados — em cards com miniatura (imagem, 1ª página do PDF "
        "ou frame do vídeo); áudio e texto usam um ícone do tipo.\n\n"
        "Quatro modos de visualização:\n"
        "• Grade e Lista — navegação padrão, com miniaturas.\n"
        "• Painel — resumo do acervo: contagem e tamanho por tipo, maiores "
        "arquivos, crescimento por período.\n"
        "• Mapa — mapa semântico do acervo (clusters de assuntos por "
        "similaridade de embedding, com tópicos rotulados); clique num "
        'documento para ver os "Relacionados".\n\n'
        "O que você pode fazer:\n"
        "• Filtrar por tipo e por período (24h, 7 ou 30 dias).\n"
        "• Buscar por nome ou por auto-tag (palavras-chave extraídas do "
        "texto de cada item) e ordenar por data, nome ou tamanho.\n"
        "• Abrir o arquivo ou a pasta dele no sistema.\n"
        "• Reenviar uma saída para outro módulo num clique — ex.: mandar um "
        "áudio baixado para a Transcrição ou reprocessar uma imagem.\n\n"
        "A lista é recarregada ao abrir a Biblioteca e quando um pipeline "
        "termina. Há paridade na linha de comando: "
        "uv run main.py library list / library stats."
    ),
    "ai": (
        "IA / Conteúdo — converse com o seu próprio acervo (RAG local).\n\n"
        "Como funciona:\n"
        "• Indexa o texto que você já produziu — transcrições, análises, "
        "digests, texto extraído/OCR de PDF, descrições de imagem e cartões "
        "de dados (schema + perfil de planilhas/CSV) — em vetores de "
        "embedding (Ollama, nomic-embed-custom, 100% local, CPU).\n"
        "• Recupera os trechos mais relevantes para a sua pergunta (busca "
        "semântica por similaridade).\n"
        "• Responde com um LLM local (Ollama) ou na nuvem (Gemini, opcional), "
        "usando apenas o contexto recuperado e citando as fontes [n]. Quando a "
        "pergunta foge do que está indexado, um aviso discreto aparece acima "
        "da resposta — ela ainda é gerada, você decide se confia.\n\n"
        "Escopo: pergunte ao acervo inteiro, a um tipo (transcrições, "
        "documentos, descrições de imagem, dados) ou a um único documento.\n\n"
        "Abas do painel: Conversa · Índice (inspetor de documentos/chunks "
        "indexados) · Painel (saúde do índice e tempo médio de resposta por "
        "modelo).\n\n"
        "Privacidade: os embeddings são sempre locais. Se você escolher um "
        "modelo Gemini, apenas os trechos recuperados são enviados à nuvem no "
        "passo de resposta.\n\n"
        "Pré-requisito: ollama pull nomic-embed-text && "
        "ollama create nomic-embed-custom -f ollama/Modelfile.nomic. "
        'Paridade na linha de comando: uv run main.py ai "sua pergunta".'
    ),
    "recipes": (
        "Receitas — automação entre módulos.\n\n"
        "O que é:\n"
        "• Uma receita é uma cadeia ordenada de passos onde a saída de um "
        "alimenta a entrada do próximo, atravessando os módulos — por exemplo: "
        "URL → baixar áudio → transcrever → analisar.\n"
        "• Cada passo só aceita o tipo de conteúdo que o passo anterior produz; "
        "a validação impede cadeias sem sentido antes de gastar processamento.\n\n"
        "Rodar:\n"
        "• Escolha uma receita (embutida ou salva), informe a entrada (URL ou "
        "arquivo) e clique em Rodar. O painel mostra o progresso passo a passo "
        "e os arquivos finais — todos visíveis na Biblioteca.\n\n"
        "Construir:\n"
        "• No modo Construir você monta a sua própria cadeia: o seletor só "
        "oferece operações compatíveis com a saída do passo anterior. Reordene "
        'com ↑/↓, remova passos e salve com um nome — fica em "Salvas" e na CLI.\n\n'
        "Lote e limpeza:\n"
        '• "Aplicar a cada arquivo" roda a receita uma vez por arquivo da fila, '
        "em vez de uma execução consumindo todos.\n"
        '• "Limpar intermediários" apaga, ao fim, os arquivos gerados pelos '
        "passos intermediários — mantém só as saídas finais e as suas entradas.\n\n"
        "Histórico:\n"
        "• A aba Histórico mostra taxa de sucesso, duração média e o passo que "
        "mais falha em cada receita, com gráfico — útil para identificar "
        "receitas frágeis antes de automatizá-las mais.\n\n"
        "Paridade na linha de comando: uv run main.py recipe list / "
        'recipe run "<nome>" <URL_OU_ARQUIVO> / recipe stats.'
    ),
    "data": (
        "O módulo Dados é query-first: toda a composição (juntar, filtrar, "
        "agrupar, somar, ordenar) vive numa única consulta sobre o motor DuckDB "
        "(embutido, local, sem servidor). Formatos: CSV, TSV, JSON, Parquet e "
        "XLSX.\n\n"
        "Como funciona a divisão de papéis:\n"
        "• Você descreve em português o que quer; a IA traduz para SQL vendo "
        "APENAS o esquema (nomes e tipos de coluna) — nunca as linhas.\n"
        "• O DuckDB abre os arquivos e executa a consulta na sua máquina.\n"
        "• Com Gemini, só os nomes de coluna saem da máquina; com modelos locais "
        "(Ollama), nada sai. O conteúdo das tabelas fica 100% local.\n\n"
        "Privacidade reforçada: somente leitura. Um guard rejeita qualquer SQL "
        "que não seja SELECT (sem COPY/INSERT/UPDATE/DELETE/ATTACH/PRAGMA) e "
        "múltiplos comandos.\n\n"
        "As quatro abas do painel:\n"
        "• Consulta — escreva em português (ou SQL na mão), pré-visualize o que "
        "a IA entendeu (cartão “Entendi assim”, com SQL editável), execute e veja "
        "o resultado paginado. Em seguida personalize o retorno (renomear "
        "colunas, escolher formato) e Salvar / Conversar sobre / Salvar como "
        "Receita / Indexar no RAG.\n"
        "• Pré-visualização — primeiras linhas de um arquivo-fonte, com o tipo "
        "inferido de cada coluna no cabeçalho (uma lente de qualidade). XLSX com "
        "várias abas ganha um seletor de aba. O rodapé indexa suas saídas no RAG.\n"
        "• Análise com IA — um parecer de qualidade: a IA recebe só esquema + "
        "resumo estatístico (SUMMARIZE) + amostra de ~10 linhas e aponta tipos "
        "suspeitos, nomes ruins, duplicatas, valores fora de faixa e problemas de "
        "estrutura. O parecer fica em cache e é reaproveitado pela indexação.\n"
        "• Gráfico — sugere automaticamente o tipo de gráfico (barra/linha/"
        "histograma/dispersão) a partir do resultado da consulta; gere e salve "
        "o PNG em output/data/.\n\n"
        "Dica XLSX: números em formato pt-BR (1.234,56) são lidos como texto para "
        "o arquivo sempre carregar; converta no SQL quando precisar de número.\n\n"
        "Paridade na linha de comando: uv run main.py data query <arquivos> "
        '"<pergunta>" [--sql] [--out csv|xlsx|json|parquet] · data convert · '
        "data profile · data assess <arquivo>."
    ),
    "observatory.gates": (
        "Cada linha é um recurso opcional que pode estar ausente sem quebrar o "
        "app — só desliga aquela funcionalidade específica, com a dica de "
        "instalação ao lado.\n\n"
        "• [ml] (scikit-learn) — clustering (HDBSCAN/k-means), classificação "
        "supervisionada, dedup semântico de texto. Sem ele, Mapa semântico, "
        "'ai topics'/'ai dups' e a promoção do classificador a supervisionado "
        "ficam indisponíveis.\n"
        "• [ml-viz] (UMAP) — método alternativo de projeção 2D do mapa "
        "semântico. Sem ele, o mapa usa só PCA (padrão, sem dependência extra).\n"
        "• [nlp] (YAKE) — extração de palavras-chave estatística, usada em "
        "'ai keywords' e nos rótulos de cluster.\n"
        "• [nlp] (spaCy) — reconhecimento de entidades nomeadas ('ai entities'). "
        "Exige também o modelo pt_core_news_sm baixado à parte.\n"
        "• Embedder (Ollama) — o motor de embeddings do RAG (nomic-embed-custom). "
        "Sem ele, indexação e busca semântica não funcionam em lugar nenhum do app.\n"
        "• [ocr] (Tesseract) — OCR híbrido de PDFs/imagens escaneadas. Exige "
        "também o binário do Tesseract instalado (packs por/eng).\n"
        "• [ai-image] (rembg) — remoção/troca de fundo no módulo Imagens.\n"
        "• [analysis] (Polars/PyArrow) — camada de DataFrame sobre o DuckDB "
        "(fundação para gráficos e ML tabular no módulo Dados).\n"
        "• [data-plot] (matplotlib) — renderização dos gráficos da aba Gráfico "
        "do módulo Dados e do gráfico de tempo de resposta aqui no Observatório.\n\n"
        "A última linha (Glossário de entidades) não é um gate binário — mostra "
        "quantos padrões o EntityRuler opcional de ~/.mill-tools/entity_glossary."
        "json tem carregado, quando o arquivo existe."
    ),
    "observatory.ollama": (
        "O app usa 6 modelos Ollama customizados (Modelfiles em ollama/, "
        "CPU-pinned): phi4mini-custom (formatação), gemma3-4b-custom "
        "(análise/prompt/RAG/PT→SQL, padrão), gemma3-1b-custom (fallback "
        "rápido), qwen7b-custom (máxima qualidade, lento na CPU), "
        "nomic-embed-custom (embeddings do RAG) e moondream-custom "
        "(descrição de imagens).\n\n"
        "Um X aqui não significa erro — só que aquele modelo ainda não foi "
        "puxado/criado localmente (ver 'Instalação → Modelos locais' no "
        "README). Se o Ollama não estiver rodando, a lista some e aparece um "
        "aviso único no lugar."
    ),
    "observatory.binaries": (
        "yt-dlp e ffmpeg são exigidos por Áudio/Vídeo/Transcrição (checados no "
        "início da GUI/CLI). ffprobe acompanha o ffmpeg e é usado para ler "
        "duração/metadados de áudio. Tesseract é opcional (extra [ocr]) — "
        "resolvido no PATH ou, no Windows, em "
        "'C:\\Program Files\\Tesseract-OCR\\tesseract.exe' como fallback.\n\n"
        "Um X aqui explica na hora por que um download trava ou um OCR "
        "recusa rodar, sem precisar abrir um terminal e testar cada binário "
        "manualmente."
    ),
    "observatory.cloud": (
        "Gemini e GLM são opt-in — o app funciona 100% local sem nenhum dos "
        "dois. Configurar a chave em Configurações (engrenagem no AppBar → "
        "Credenciais) libera os modelos gemini-*/glm-* nos seletores de "
        "modelo da Transcrição, IA, Dados e descrição de imagens.\n\n"
        "Esta linha só confirma presença/ausência da chave no .env — nunca "
        "lê nem exibe o valor. Uma chave 'configurada' mas inválida/expirada "
        "só aparece como erro na hora de usar o modelo, não aqui."
    ),
    "observatory.classify": (
        "O classificador de perfil/domínio (core/ml/classify.py) começa em "
        "zero-shot: compara o embedding do documento com protótipos por rótulo "
        "e escolhe o mais próximo por cosseno, sem exigir treino.\n\n"
        "Conforme você confirma ou corrige a sugestão (ex.: aceitar/trocar o "
        "perfil sugerido na Transcrição), esse rótulo é gravado como exemplo de "
        "treino. Ao acumular exemplos suficientes por classe, o domínio migra "
        "automaticamente para um modelo supervisionado (LinearSVC + calibração), "
        "mais preciso que o zero-shot — sem exigir nenhuma ação manual.\n\n"
        "Os três domínios são independentes entre si:\n"
        "• Perfil de transcrição — aula, entrevista, tutorial, reunião…\n"
        "• Domínio de dados — tipo de planilha/CSV analisado no módulo Dados.\n"
        "• Tipo de documento — categoria de PDF/documento processado."
    ),
    "observatory.config": (
        "Números que várias operações de ML usam por baixo dos panos, lidos "
        "direto das constantes reais do código (nunca uma cópia que poderia "
        "ficar desatualizada) — aqui só para transparência, sem UI para editá-los.\n\n"
        "• Limiar de dedup de texto (padrão 0.95) — cosseno mínimo para dois "
        "documentos entrarem no mesmo grupo de quase-duplicatas ('ai dups').\n"
        "• Distância máx. dedup de imagem (padrão 8) — distância de Hamming "
        "máxima entre dHashes para duas imagens contarem como quase-idênticas "
        "na Biblioteca.\n"
        "• Piso de corpus p/ auto-k (padrão 20) — tamanho mínimo do acervo para "
        "o k-means escolher o número de clusters sozinho via silhouette score; "
        "abaixo disso, o k precisa ser informado manualmente.\n"
        "• λ do MMR (padrão 0.6) — equilíbrio entre relevância e diversidade em "
        "'Relacionados' e no resumo extrativo. Mais perto de 1 prioriza "
        "relevância pura; mais perto de 0 prioriza variedade."
    ),
}


def help_for(key: str) -> str | None:
    """Texto curto (tooltip) ou None se não houver entrada."""
    return HELP_SHORT.get(key)


def help_long_for(key: str) -> str | None:
    """Texto longo (modal) ou None."""
    return HELP_LONG.get(key)
