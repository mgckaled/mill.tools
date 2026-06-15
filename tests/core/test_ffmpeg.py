"""Unit tests for src/core/ffmpeg.run_ffmpeg (subprocess mocked)."""

import pytest


def _mock_popen(mocker, returncode: int, stdout=None, stderr=None):
    proc = mocker.MagicMock()
    proc.stdout = iter(stdout or [])
    proc.stderr = iter(stderr or [])
    proc.returncode = returncode
    proc.wait.return_value = None
    return proc


@pytest.mark.unit
def test_run_ffmpeg_success_returns_out_path(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp3"
    out.write_bytes(b"audio")
    mock_proc = _mock_popen(mocker, returncode=0)
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    result = run_ffmpeg(["ffmpeg", "-y", "-i", "in.wav", str(out)], out)
    assert result == out


@pytest.mark.unit
def test_run_ffmpeg_nonzero_returncode_raises_runtime_error(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp3"
    mock_proc = _mock_popen(mocker, returncode=1, stderr=[b"codec not found\n"])
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    with pytest.raises(RuntimeError, match="ffmpeg returned 1"):
        run_ffmpeg(["ffmpeg"], out)


@pytest.mark.unit
def test_run_ffmpeg_runtime_error_no_stderr_shows_no_details(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp3"
    mock_proc = _mock_popen(mocker, returncode=2)
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    with pytest.raises(RuntimeError, match="no details"):
        run_ffmpeg(["ffmpeg"], out)


@pytest.mark.unit
def test_run_ffmpeg_missing_output_raises_file_not_found(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp3"  # intentionally not created
    mock_proc = _mock_popen(mocker, returncode=0)
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    with pytest.raises(FileNotFoundError, match="out.mp3"):
        run_ffmpeg(["ffmpeg"], out)


@pytest.mark.unit
def test_run_ffmpeg_progress_callback_called_with_ratio(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp3"
    out.write_bytes(b"audio")
    mock_proc = _mock_popen(
        mocker,
        returncode=0,
        stdout=[b"out_time_us=5000000\n", b"out_time_us=10000000\n"],
    )
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    ratios: list[float] = []
    run_ffmpeg(["ffmpeg"], out, total_secs=10.0, progress_cb=ratios.append)

    assert ratios == [0.5, 1.0]


@pytest.mark.unit
def test_run_ffmpeg_no_progress_when_total_secs_is_none(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp3"
    out.write_bytes(b"audio")
    mock_proc = _mock_popen(
        mocker,
        returncode=0,
        stdout=[b"out_time_us=5000000\n"],
    )
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    ratios: list[float] = []
    run_ffmpeg(["ffmpeg"], out, total_secs=None, progress_cb=ratios.append)

    assert ratios == []


@pytest.mark.unit
def test_run_ffmpeg_malformed_out_time_us_silenced(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp3"
    out.write_bytes(b"audio")
    mock_proc = _mock_popen(
        mocker,
        returncode=0,
        stdout=[b"out_time_us=INVALID\n"],
    )
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    ratios: list[float] = []
    # ValueError from int("INVALID") must be silenced — no exception propagates
    run_ffmpeg(["ffmpeg"], out, total_secs=10.0, progress_cb=ratios.append)
    assert ratios == []


@pytest.mark.unit
def test_run_ffmpeg_passes_cwd_to_popen(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp4"
    out.write_bytes(b"video")
    mock_proc = _mock_popen(mocker, returncode=0)
    popen = mocker.patch("subprocess.Popen", return_value=mock_proc)

    run_ffmpeg(["ffmpeg"], out, cwd=tmp_path)

    assert popen.call_args.kwargs["cwd"] == str(tmp_path)


@pytest.mark.unit
def test_run_ffmpeg_cwd_none_passes_none_to_popen(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp4"
    out.write_bytes(b"video")
    mock_proc = _mock_popen(mocker, returncode=0)
    popen = mocker.patch("subprocess.Popen", return_value=mock_proc)

    run_ffmpeg(["ffmpeg"], out)

    assert popen.call_args.kwargs["cwd"] is None


@pytest.mark.unit
def test_run_ffmpeg_stderr_tail_caps_buffer(tmp_path, mocker):
    from src.core.ffmpeg import run_ffmpeg

    out = tmp_path / "out.mp3"
    stderr_lines = [f"line{i}\n".encode() for i in range(5)]
    mock_proc = _mock_popen(mocker, returncode=1, stderr=stderr_lines)
    mocker.patch("subprocess.Popen", return_value=mock_proc)

    with pytest.raises(RuntimeError) as exc_info:
        run_ffmpeg(["ffmpeg"], out, stderr_tail=3)

    msg = str(exc_info.value)
    assert "line4" in msg
    assert "line0" not in msg
