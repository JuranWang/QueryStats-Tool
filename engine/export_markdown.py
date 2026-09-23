"""Convert an existing Word report to portable Markdown and media in a ZIP."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import zipfile

from engine.i18n import t


class ExportToolMissingError(RuntimeError):
    """The external converter is not installed or executable."""


def _is_executable(path: str) -> bool:
    return Path(path).is_file() and os.access(path, os.X_OK)


def _find_pandoc() -> str:
    executable = shutil.which("pandoc")
    if executable:
        return executable
    for candidate in ("/opt/homebrew/bin/pandoc", "/usr/local/bin/pandoc"):
        if _is_executable(candidate):
            return candidate
    raise ExportToolMissingError(t(
        "未检测到 Pandoc（pandoc），请下载安装：https://pandoc.org/installing.html"
    ))


def convert_docx_to_markdown(docx_path: str, output_dir: str, timeout: int = 60) -> str:
    """Return the absolute ZIP path, with relative image links inside Markdown."""
    executable = _find_pandoc()
    source = Path(docx_path).resolve(strict=True)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    markdown = destination / f"{source.stem}.md"
    media = destination / f"{source.stem}_media"
    archive = destination / f"{source.stem}.zip"

    # Regenerating the same report must not include images from a previous run.
    markdown.unlink(missing_ok=True)
    if media.exists():
        shutil.rmtree(media)
    media.mkdir()
    command = [
        executable, str(source), "-o", markdown.name, f"--extract-media={media.name}",
    ]
    try:
        result = subprocess.run(
            command, cwd=destination, capture_output=True, text=True, timeout=timeout, check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(t(
            "{tool} 转换超时（{timeout} 秒）：{error}",
            tool="Pandoc", timeout=timeout, error=exc.stderr or "",
        )) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(t(
            "{tool} 转换失败（退出码 {code}）：{error}",
            tool="Pandoc", code=exc.returncode, error=exc.stderr or "",
        )) from exc
    if not markdown.is_file() or markdown.stat().st_size == 0:
        raise RuntimeError(t(
            "{tool} 未生成非空文件：{error}",
            tool="Pandoc", error=result.stderr or result.stdout or "",
        ))
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(markdown, markdown.name)
        bundle.write(media, media.name)
        for path in sorted(media.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(destination))
    return str(archive)
