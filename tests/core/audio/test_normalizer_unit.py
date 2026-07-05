"""Testes unitários — normalize_lufs com subprocess mockado (sem ffmpeg)."""

import pytest

# Stderr de referência com JSON loudnorm válido (bytes, como retornado pelo subprocess)
_LOUDNORM_STDERR = b"""\
[Parsed_loudnorm_0 @ 0x...] Input Integrated: -23.0 LUFS
{
    "input_i" : "-23.0",
    "input_tp" : "-2.0",
    "input_lra" : "7.0",
    "input_thresh" : "-33.0",
    "output_i" : "-14.0",
    "output_tp" : "-1.0",
    "output_lra" : "6.5",
    "output_thresh" : "-24.0",
    "normalization_type" : "dynamic",
    "target_offset" : "9.0"
}
"""


def _mock_popen(
    mocker, returncode: int, stdout: list[bytes] = None, stderr: list[bytes] = None
):
    """Cria mock de Popen com stdout/stderr controláveis e returncode fixo."""
    proc = mocker.MagicMock()
    proc.stdout = iter(stdout or [])
    proc.stderr = iter(stderr or [])
    proc.returncode = returncode
    proc.wait.return_value = None
    return proc


@pytest.mark.unit
def test_normalize_lufs_stats_none_uses_fallback_af(tmp_path, mocker, caplog):
    """Quando pass 1 não retorna JSON (stats=None), o filtro fallback é usado e Popen é chamado."""
    from src.core.audio.normalizer import normalize_lufs

    fake_src = tmp_path / "input.wav"
    fake_src.write_bytes(b"")

    # Pass 1: stderr sem JSON → stats=None → linha 62 (fallback af) é coberta
    mocker.patch(
        "subprocess.run", return_value=mocker.Mock(returncode=0, stderr=b"", stdout=b"")
    )
    mock_proc = _mock_popen(mocker, returncode=1)
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    # RuntimeError vindo do returncode=1 prova que Popen foi chamado com o fallback af
    with caplog.at_level("WARNING"):
        with pytest.raises(RuntimeError):
            normalize_lufs(fake_src, tmp_path / "out", target_lufs=-14.0)

    assert "falling back to dynamic loudnorm" in caplog.text


@pytest.mark.unit
def test_normalize_lufs_pass1_nonzero_returncode_logs_reason(tmp_path, mocker, caplog):
    """Warning do fallback cita o código de saída quando o passe 1 falha (não só JSON ausente)."""
    from src.core.audio.normalizer import normalize_lufs

    fake_src = tmp_path / "input.wav"
    fake_src.write_bytes(b"")

    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(returncode=5, stderr=b"boom", stdout=b""),
    )
    mock_proc = _mock_popen(mocker, returncode=1)
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    with caplog.at_level("WARNING"):
        with pytest.raises(RuntimeError):
            normalize_lufs(fake_src, tmp_path / "out", target_lufs=-14.0)

    assert "exited with code 5" in caplog.text


@pytest.mark.unit
def test_normalize_lufs_dynamic_fallback_forces_source_sample_rate(tmp_path, mocker):
    """No ramo dinâmico, -ar da fonte é injetado no comando do passe 2 (mitiga upsample p/ 192kHz)."""
    from src.core.audio.normalizer import normalize_lufs

    fake_src = tmp_path / "input.wav"
    fake_src.write_bytes(b"")

    mocker.patch(
        "subprocess.run",
        side_effect=[
            mocker.Mock(returncode=0, stderr=b"", stdout=b""),  # pass 1 sem JSON
            mocker.Mock(
                returncode=0, stdout=b"44100\n", stderr=b""
            ),  # ffprobe sample rate
        ],
    )
    captured_cmd: list[str] = []

    def _fake_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        return _mock_popen(mocker, returncode=0)

    mocker.patch("subprocess.Popen", side_effect=_fake_popen)
    (tmp_path / "out").mkdir()
    out_path = (tmp_path / "out") / "input_normalized.wav"
    out_path.write_bytes(b"")

    normalize_lufs(fake_src, tmp_path / "out", target_lufs=-14.0)

    assert "-ar" in captured_cmd
    assert captured_cmd[captured_cmd.index("-ar") + 1] == "44100"


@pytest.mark.unit
def test_normalize_lufs_second_pass_nonzero_raises_runtime_error(tmp_path, mocker):
    """RuntimeError é lançado quando o segundo passe retorna código não-zero."""
    from src.core.audio.normalizer import normalize_lufs

    fake_src = tmp_path / "input.wav"
    fake_src.write_bytes(b"")

    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(returncode=0, stderr=_LOUDNORM_STDERR, stdout=b""),
    )
    mock_proc = _mock_popen(
        mocker, returncode=1, stderr=[b"encoder error: codec not found\n"]
    )
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    with pytest.raises(RuntimeError, match="ffmpeg returned 1"):
        normalize_lufs(fake_src, tmp_path / "out", target_lufs=-14.0)


@pytest.mark.unit
def test_normalize_lufs_output_missing_after_success_raises_file_not_found(
    tmp_path, mocker
):
    """FileNotFoundError é lançado se o arquivo de saída não existir após returncode=0."""
    from src.core.audio.normalizer import normalize_lufs

    fake_src = tmp_path / "input.wav"
    fake_src.write_bytes(b"")

    mocker.patch(
        "subprocess.run",
        return_value=mocker.Mock(returncode=0, stderr=_LOUDNORM_STDERR, stdout=b""),
    )
    # returncode=0 mas ffmpeg mockado não cria o arquivo no disco
    mock_proc = _mock_popen(mocker, returncode=0)
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    with pytest.raises(FileNotFoundError):
        normalize_lufs(fake_src, tmp_path / "out", target_lufs=-14.0)


@pytest.mark.unit
def test_normalize_lufs_malformed_out_time_us_is_silenced(tmp_path, mocker):
    """ValueError ao parsear out_time_us com valor não-numérico é silenciado (except captura)."""
    from src.core.audio.normalizer import normalize_lufs

    fake_src = tmp_path / "input.wav"
    fake_src.write_bytes(b"")

    # Dois calls a subprocess.run: (1) pass 1 loudnorm, (2) get_duration_ffprobe (com progress_cb)
    mocker.patch(
        "subprocess.run",
        side_effect=[
            mocker.Mock(returncode=0, stderr=_LOUDNORM_STDERR, stdout=b""),  # pass 1
            mocker.Mock(returncode=0, stdout=b"3.0\n", stderr=b""),  # ffprobe
        ],
    )
    # Stdout com valor malformado → int("INVALIDO") → ValueError → silenciado
    mock_proc = _mock_popen(mocker, returncode=1, stdout=[b"out_time_us=INVALIDO\n"])
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    # RuntimeError (do returncode=1), não ValueError — a exceção de parsing foi silenciada
    with pytest.raises(RuntimeError):
        normalize_lufs(
            fake_src,
            tmp_path / "out",
            target_lufs=-14.0,
            progress_cb=lambda r: None,
        )
