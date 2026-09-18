import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Union

from bib_lookup.utils import _remove_comments

PROJECT_DIR = Path(__file__).resolve().parent
BUILD_DIR = PROJECT_DIR / "build"
BUILD_DIR.mkdir(parents=True, exist_ok=True)
MAIN_TEX_FILE = PROJECT_DIR / "main.tex"


def _get_main_tex_preamble():
    text = _remove_comments(MAIN_TEX_FILE.read_text(encoding="utf-8"))
    # remove the last line that starts with \input{...}
    lines = text.splitlines()

    # Find indices of lines that start with \input{ (allowing leading spaces)
    input_indices = [i for i, line in enumerate(lines) if re.match(r"^\s*\\input\{", line)]

    if input_indices:
        # Remove only the last occurrence
        del lines[input_indices[-1]]
    return "\n".join(lines)


MAIN_TEX_PREAMBLE = _get_main_tex_preamble()

# Status markers that may follow \input{...} lines in main.tex (as comments or inline text)
_STATUSES = ["已完成 ✅", "正在进行 ✏️", "待检查 ❓", "待更新 ⚠️", "未完成 ❌"]
_STATUS_COMPLETE = "已完成 ✅"
_PREVIEW_SUFFIX = "-Preview"


def _find_input_line_rest(tex_file: Path) -> Optional[str]:
    """Return the text following ``\\input{...}`` on the matching main.tex line, or None.

    Matches ``\\input{rel/path}`` or ``\\input{rel/path.tex}``.
    """
    try:
        rel_path = tex_file.relative_to(PROJECT_DIR)
    except ValueError:
        return None

    stem_path = rel_path.with_suffix("").as_posix()
    main_text = MAIN_TEX_FILE.read_text(encoding="utf-8")

    pattern = re.compile(r"\\input\{" + re.escape(stem_path) + r"(?:\.tex)?\}(.*)", re.UNICODE)

    for line in main_text.splitlines():
        m = pattern.search(line)
        if m:
            return m.group(1)
    return None  # \input line not in main.tex


def get_file_status_in_main_tex(tex_file: Path) -> Optional[str]:
    """Return the status marker on the \\input line for *tex_file* in main.tex.

    Returns the first matching status string from ``_STATUSES`` found on that line.
    Returns ``None`` when the \\input line is absent or carries no status marker.
    """
    rest = _find_input_line_rest(tex_file)
    if rest is None:
        return None
    for status in _STATUSES:
        if status in rest:
            return status
    return None  # line found but no status marker


def is_deprecated_in_main_tex(tex_file: Path) -> bool:
    """Return True when the \\input line for *tex_file* carries the 废弃 ⛔ marker.

    Trailing text after the marker is allowed, e.g. ``% 废弃 ⛔ (内容并入 §2.4)``.
    """
    rest = _find_input_line_rest(tex_file)
    if rest is None:
        return False
    return "废弃" in rest and "⛔" in rest


def get_output_pdf_path(tex_file: Path) -> Path:
    """Return the build/ output PDF path for *tex_file*.

    Sections marked 已完成 ✅ in main.tex (or absent from it) keep the mirrored
    path ``build/<课程>/<...>/<name>.pdf``. Any other section carrying a status
    marker is routed to a separate preview tree so that it never mixes with the
    completed output: ``build/<课程>-Preview/<...>/<name>-Preview.pdf``.
    """
    try:
        rel_path = tex_file.relative_to(PROJECT_DIR)
    except ValueError:
        rel_path = Path(tex_file.stem)

    out_pdf_path = BUILD_DIR / rel_path.with_suffix(".pdf")

    status = get_file_status_in_main_tex(tex_file)
    if status is not None and status != _STATUS_COMPLETE:
        parts = list(rel_path.with_suffix("").parts)
        parts[-1] += _PREVIEW_SUFFIX  # mark the file name
        if len(parts) > 1:
            parts[0] += _PREVIEW_SUFFIX  # course-level folder kept apart from completed files
        out_pdf_path = BUILD_DIR.joinpath(*parts).with_suffix(".pdf")

    return out_pdf_path


def execute_cmd(cmd: Union[str, List[str]], raise_error: bool = True, cwd: Optional[Path] = None) -> int:
    """
    Execute command using subprocess.Popen with real-time output printing.
    """
    is_windows = platform.system().lower() == "windows"
    shell_arg = True

    encoding = "gbk" if is_windows else "utf-8"

    cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
    print(f"\n[CMD] Executing: {cmd_str}")

    env = os.environ.copy()

    captured_logs = []

    try:
        with subprocess.Popen(
            cmd, shell=shell_arg, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(cwd) if cwd else None, env=env
        ) as p:
            if p.stdout:
                for line in iter(p.stdout.readline, b""):
                    try:
                        line_str = line.decode(encoding, errors="replace").rstrip()
                    except Exception:
                        line_str = line.decode("utf-8", errors="replace").rstrip()

                    if line_str:
                        print(line_str)
                        captured_logs.append(line_str)

            p.wait()
            exitcode = p.returncode

            if exitcode != 0:
                error_msg = f"\nCommand failed with exit code {exitcode}.\nCommand: {cmd_str}\n"
                error_msg += "\n--- Last 20 lines of output ---\n"
                error_msg += "\n".join(captured_logs[-20:])

                print("\n" + "!" * 10 + "  EXECUTION FAILED  " + "!" * 10)
                if raise_error:
                    raise subprocess.CalledProcessError(exitcode, cmd, output="\n".join(captured_logs))
                else:
                    return exitcode

    except KeyboardInterrupt:
        print("\n[WARN] Process interrupted by user.")
        return 130  # Standard SIGINT exit code

    return 0


def clean_up(target_file: Path):
    """Clean up auxiliary files generated by latexmk."""
    print(f"\n[INFO] Cleaning up auxiliary files for {target_file.name}...")
    cmd = f'latexmk -C -outdir="{str(PROJECT_DIR)}" "{str(target_file)}"'
    execute_cmd(cmd, raise_error=False)

    bbl_file = PROJECT_DIR / f"{target_file.stem}.bbl"
    if bbl_file.exists():
        try:
            bbl_file.unlink()
            print(f"Removed {bbl_file.name}")
        except OSError as e:
            print(f"Error removing {bbl_file.name}: {e}")

    for fls_file in PROJECT_DIR.glob("xelatex*.fls"):
        try:
            fls_file.unlink()
        except OSError:
            pass


def compile_section(tex_file: Path, args) -> int:
    """Compile a single section tex file by prepending MAIN_TEX_PREAMBLE.

    The resulting PDF is saved under build/ preserving the directory structure
    relative to PROJECT_DIR, e.g. build/数学分析/第7章-定积分/第5节-....pdf.
    Sections not marked 已完成 ✅ in main.tex are routed to the -Preview tree
    instead (see get_output_pdf_path).
    """
    try:
        rel_path = tex_file.relative_to(PROJECT_DIR)
    except ValueError:
        rel_path = Path(tex_file.stem)

    out_pdf_path = get_output_pdf_path(tex_file)

    # Sections not yet marked 已完成 ✅ are routed to the -Preview tree
    status = get_file_status_in_main_tex(tex_file)
    if status is not None and status != _STATUS_COMPLETE:
        print(f"[INFO] Status of {rel_path}: {status!r} → output goes to the -Preview tree")
    out_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # Combine preamble with \input pointing at the section file
    rel_input = tex_file.relative_to(PROJECT_DIR).as_posix()
    combined = MAIN_TEX_PREAMBLE + "\n" + f"\\input{{{rel_input}}}" + "\n"

    job_name = f"_target_{tex_file.stem}"
    temp_tex = PROJECT_DIR / f"{job_name}.tex"
    temp_tex.write_text(combined, encoding="utf-8")

    cmd = f'latexmk -xelatex --shell-escape -f -outdir="{str(PROJECT_DIR)}" ' f'-jobname="{job_name}" "{str(temp_tex)}"'

    print(f"\n[INFO] Compiling: {rel_path}")
    exitcode = 0
    try:
        exitcode = execute_cmd(cmd)
    except subprocess.CalledProcessError:
        exitcode = 1

    generated_pdf = PROJECT_DIR / f"{job_name}.pdf"
    if exitcode == 0 and generated_pdf.exists():
        shutil.copy(generated_pdf, out_pdf_path)
        print(f"[INFO] Output: {out_pdf_path}")
        # log is NOLONGER needed for this compilation mode
        # generated_log = generated_pdf.with_suffix(".log")
        # if generated_log.exists():
        #     shutil.copy(generated_log, out_pdf_path.with_suffix(".log"))
    else:
        print(f"[ERROR] Failed to compile: {tex_file.name}")

    if args.gc:
        clean_up(temp_tex)
    # Always remove the temporary tex file
    temp_tex.unlink(missing_ok=True)

    return exitcode


def compile_target(target_str: str, args):
    """Compile a target path: a single .tex file or all .tex files in a directory tree."""
    target = Path(target_str)
    if not target.is_absolute():
        target = PROJECT_DIR / target

    tex_file = target.with_suffix(".tex")

    if tex_file.exists():
        files_to_compile = [tex_file]
    elif target.is_dir():
        candidates = sorted(target.rglob("*.tex"))
        if not candidates:
            print(f"[WARN] No .tex files found under directory: {target}")
            sys.exit(1)

        # In directory mode, skip files whose \input line in main.tex carries the 废弃 ⛔ marker
        files_to_compile, skipped = [], []
        for f in candidates:
            (skipped if is_deprecated_in_main_tex(f) else files_to_compile).append(f)
        if skipped:
            print("[INFO] Skipping files marked 废弃 ⛔ in main.tex:")
            for f in skipped:
                try:
                    print(f"  [SKIP] {f.relative_to(PROJECT_DIR)}")
                except ValueError:
                    print(f"  [SKIP] {f}")
        if not files_to_compile:
            print(f"[WARN] All .tex files under {target} are marked 废弃 ⛔ in main.tex. Nothing to compile.")
            sys.exit(1)
    else:
        print(f"[WARN] Neither file '{tex_file}' nor directory '{target}' exists. Exiting.")
        sys.exit(1)

    failed = []
    for f in files_to_compile:
        ec = compile_section(f, args)
        if ec != 0:
            failed.append(f)

    if failed:
        print(f"\n[ERROR] {len(failed)} file(s) failed to compile:")
        for f in failed:
            print(f"  {f}")
        sys.exit(1)
    else:
        print(f"\n[INFO] All {len(files_to_compile)} file(s) compiled successfully.")


def main(args):
    if shutil.which("latexmk") is None:
        raise RuntimeError("latexmk is not installed or not in PATH.")

    if args.tex_entry_file:
        tex_entry_file = args.tex_entry_file
        is_handout = args.handout
    else:
        tex_entry_file = MAIN_TEX_FILE
        is_handout = True

    if not tex_entry_file.exists():
        raise FileNotFoundError(f"TeX file not found: {tex_entry_file}")

    print(f"Target: {tex_entry_file.name}")
    print(f"Mode: {'Handout' if is_handout else 'Standard'}")

    job_name = tex_entry_file.stem

    cmd = f'latexmk -xelatex --shell-escape -f -outdir="{str(PROJECT_DIR)}" ' f'-jobname="{job_name}" "{str(tex_entry_file)}"'

    try:
        exitcode = execute_cmd(cmd)
        if exitcode != 0:
            sys.exit(exitcode)
    except subprocess.CalledProcessError:
        if args.gc:
            clean_up(tex_entry_file)
        sys.exit(1)

    generated_pdf = PROJECT_DIR / f"{job_name}.pdf"

    if not generated_pdf.exists():
        print("[ERROR] PDF was not generated successfully.")
        sys.exit(1)

    suffix = time.strftime("%Y%m%d-%H%M%S")

    if tex_entry_file.stem == MAIN_TEX_FILE.stem and is_handout:
        backup_pdf_name = f"MathCourseSlides-{suffix}.pdf"
    else:
        backup_pdf_name = f"{tex_entry_file.stem}.pdf"

    backup_pdf_path = BUILD_DIR / backup_pdf_name

    print(f"\n[INFO] Copying result to: {backup_pdf_path}")
    shutil.copy(generated_pdf, backup_pdf_path)

    generated_log = generated_pdf.with_suffix(".log")
    if generated_log.exists():
        shutil.copy(generated_log, backup_pdf_path.with_suffix(".log"))

    if args.gc:
        clean_up(tex_entry_file)
    else:
        print("\n[INFO] Build files kept. Use --gc to clean up.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile LaTeX files using latexmk with automation.")

    parser.add_argument(
        "tex_entry_file",
        nargs="?",
        type=Path,
        default=None,
        help="The main tex file to compile. Defaults to main.tex inside project dir.",
    )

    parser.add_argument("--handout", action="store_true", help="Compile as handout (defaults to True if no file specified).")

    parser.add_argument("--gc", action="store_true", help="Garbage collect (clean) build files after compilation.")

    parser.add_argument(
        "--target",
        "-t",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Compile a specific section or directory. "
            "Examples: '数学分析/第7章-定积分/第6节-定积分的数值计算' or '数学分析/第7章-定积分'. "
            "If a matching .tex file exists it is compiled directly; otherwise all .tex files "
            "under the directory are compiled, skipping files whose \\input line in main.tex "
            "is marked 废弃 ⛔ (trailing text allowed). Output PDFs are saved under build/ "
            "preserving the original directory structure; sections not marked 已完成 ✅ go to "
            "build/<课程>-Preview/... with a -Preview suffix on the file name. "
            "When set, tex_entry_file is ignored."
        ),
    )

    args = parser.parse_args()

    if args.target:
        if args.tex_entry_file:
            print("[WARN] --target is set; tex_entry_file argument will be ignored.")
        if not args.gc:
            # set it to True and print a warning since compiling multiple files can generate many auxiliary files
            print(
                "[WARN] Compiling with --target can generate many auxiliary files. "
                "Enabling --gc to clean up after compilation."
            )
            args.gc = True

        try:
            compile_target(args.target, args)
        except KeyboardInterrupt:
            print("\n[INFO] Script interrupted.")
            sys.exit(130)
        except Exception as e:
            print(f"\n[ERROR] {e}")
            sys.exit(1)
    else:
        if args.tex_entry_file:
            args.tex_entry_file = args.tex_entry_file.expanduser().resolve()

        try:
            main(args)
        except KeyboardInterrupt:
            print("\n[INFO] Script interrupted.")
            sys.exit(130)
        except Exception as e:
            print(f"\n[ERROR] {e}")
            sys.exit(1)
