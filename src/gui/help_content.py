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
        "Reinsere quebras de parágrafo na transcrição via LLM, "
        "sem alterar o texto."
    ),
    "transcription.analyze": (
        "Gera uma análise estruturada (resumo, pontos-chave, citações…) "
        "a partir da transcrição."
    ),
    "transcription.prompt": (
        "Cria uma versão condensada (~40%) da transcrição, "
        "pronta para colar como contexto em prompts."
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
        "Auto-trim: remove bordas da cor indicada."
    ),
    "image.rotate": (
        "Ângulo em múltiplos de 90°. EXIF auto corrige a orientação registrada pela câmera. "
        "Espelhar H/V é independente do ângulo."
    ),
    "image.watermark": (
        "Texto: fonte embutida, sem dependência do sistema. "
        "Imagem: sobreposição redimensionada a 25% da largura. "
        "Opacidade 0 = invisível, 100 = sólida."
    ),
    "image.border": (
        "Adiciona borda sólida em torno da imagem. "
        "'Preencher alpha' substitui transparência pela cor da borda antes — "
        "necessário para salvar em JPEG."
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
        "Gera um .ico com múltiplas resoluções embutidas. "
        "Marque os tamanhos desejados."
    ),
    "image.contact_sheet": (
        "Monta uma grade com todas as imagens da fila. "
        "O resultado é uma única imagem de saída."
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
    "transcription.beam_size": (
        "O decodificador do Whisper usa busca em feixe (beam search) para gerar "
        "a transcrição.\n\n"
        "• beam_size=1 (greedy): mais rápido, usa menos memória.\n"
        "• beam_size=3–5: explora mais candidatos, pode melhorar a precisão em "
        "trechos ambíguos, porém aumenta o tempo de processamento proporcionalmente.\n"
        "• Para a maioria dos casos (fala clara, português ou inglês), "
        "beam_size=1 já produz resultados excelentes."
    ),
}


def help_for(key: str) -> str | None:
    """Texto curto (tooltip) ou None se não houver entrada."""
    return HELP_SHORT.get(key)


def help_long_for(key: str) -> str | None:
    """Texto longo (modal) ou None."""
    return HELP_LONG.get(key)
