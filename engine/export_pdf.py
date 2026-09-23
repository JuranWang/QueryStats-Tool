"""Convert an existing Word report to PDF with LibreOffice."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from engine.i18n import t


class ExportToolMissingError(RuntimeError):
    """The external converter is not installed or executable."""


def _is_executable(path: str) -> bool:
    return Path(path).is_file() and os.access(path, os.X_OK)


def _find_soffice() -> str:
    executable = shutil.which("soffice")
    if executable:
        return executable
    for candidate in (
        "/opt/homebrew/bin/soffice",
        "/usr/local/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if _is_executable(candidate):
            return candidate
    raise ExportToolMissingError(t(
        "未检测到 LibreOffice（soffice），请下载安装：https://www.libreoffice.org/download/download-libreoffice/"
    ))


def convert_docx_to_pdf(docx_path: str, output_dir: str, timeout: int = 60) -> str:
    """Return the absolute PDF path; never accept a stale conversion result."""
    executable = _find_soffice()
    source = Path(docx_path).resolve(strict=True)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f"{source.stem}.pdf"

    # Separate profiles avoid interference with an open desktop LibreOffice.
    # Stage the PDF so a successful exit without output cannot reuse an old file.
    with tempfile.TemporaryDirectory(prefix=".pdf-", dir=destination) as work_dir:
        work = Path(work_dir)
        command = [
            executable,
            f"-env:UserInstallation={(work / 'profile').as_uri()}",
            "--headless", "--convert-to", "pdf", "--outdir", str(work), str(source),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(t(
                "{tool} 转换超时（{timeout} 秒）：{error}",
                tool="LibreOffice", timeout=timeout, error=exc.stderr or "",
            )) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(t(
                "{tool} 转换失败（退出码 {code}）：{error}",
                tool="LibreOffice", code=exc.returncode, error=exc.stderr or "",
            )) from exc
        converted = work / target.name
        if not converted.is_file() or converted.stat().st_size == 0:
            raise RuntimeError(t(
                "{tool} 未生成非空文件：{error}",
                tool="LibreOffice", error=result.stderr or result.stdout or "",
            ))
        converted.replace(target)
    return str(target)
