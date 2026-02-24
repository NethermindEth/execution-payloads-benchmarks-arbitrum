import base64
import json
import re
import sys
from pathlib import Path

import typer
from typing_extensions import Annotated

from expb.logging import setup_logging

app = typer.Typer()

FILE_PATTERN = re.compile(r"^rpc\.(\d+)\.txt$")


def discover_files(
    input_dir: Path,
    start_block: int,
    end_block: int | None,
) -> list[tuple[int, Path]]:
    """Scan input directory for rpc.<N>.txt files, filter by range, sort numerically."""
    files: list[tuple[int, Path]] = []
    for entry in input_dir.iterdir():
        match = FILE_PATTERN.match(entry.name)
        if match and entry.is_file():
            idx = int(match.group(1))
            if idx >= start_block and (end_block is None or idx <= end_block):
                files.append((idx, entry))
    files.sort(key=lambda x: x[0])
    return files


def calculate_msg_data_size(parsed: dict) -> int:
    """Calculate combined base64-decoded l2Msg size from digestMessage params."""
    total = 0
    params = parsed.get("params", [])
    for i in (1, 2):
        if i < len(params) and isinstance(params[i], dict):
            msg = params[i].get("message", {})
            l2msg = msg.get("l2Msg", "")
            if l2msg:
                try:
                    total += len(base64.b64decode(l2msg))
                except Exception:
                    pass
    return total


def process_file(
    file_path: Path,
    method_suffixes: list[str],
    output_file,
    logger,
) -> int:
    """Process a single rpc.<N>.txt file. Returns count of lines written."""
    lines_written = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                logger.warning(
                    "Malformed JSON line, skipping",
                    file=str(file_path),
                    line=line_num,
                )
                continue

            method = parsed.get("method", "")
            if not any(method.endswith(suffix) for suffix in method_suffixes):
                continue

            # Calculate msgDataSize for digestMessage calls
            if method.endswith("digestMessage"):
                msg_data_size = calculate_msg_data_size(parsed)
                parsed["msgDataSize"] = msg_data_size

            output_file.write(json.dumps(parsed, separators=(",", ":")) + "\n")
            lines_written += 1
    return lines_written


@app.command()
def convert_arbitrum_payloads(
    input_dir: Annotated[Path, typer.Option(help="Directory containing rpc.<N>.txt files")],
    output_dir: Annotated[Path, typer.Option(help="Directory for output payloads.jsonl")],
    start_block: Annotated[int, typer.Option(help="First file index to process (inclusive)")] = 0,
    end_block: Annotated[
        int | None, typer.Option(help="Last file index to process (inclusive)")
    ] = None,
    methods: Annotated[
        str, typer.Option(help="Comma-separated list of method suffixes to include")
    ] = "digestMessage",
    log_level: Annotated[str, typer.Option(help="Log level")] = "INFO",
) -> None:
    """Convert recorded Arbitrum Nitro RPC files into benchmark JSONL format."""
    logger = setup_logging(log_level)

    # Validate input directory
    if not input_dir.exists() or not input_dir.is_dir():
        logger.error("Input directory does not exist", input_dir=str(input_dir))
        raise SystemExit(1)

    # Discover files
    files = discover_files(input_dir, start_block, end_block)
    if not files:
        logger.error(
            "No matching rpc.<N>.txt files found in range",
            input_dir=str(input_dir),
            start_block=start_block,
            end_block=end_block,
        )
        raise SystemExit(1)

    # Check for missing files in range
    actual_indices = {idx for idx, _ in files}
    max_idx = end_block if end_block is not None else max(actual_indices)
    for i in range(start_block, max_idx + 1):
        if i not in actual_indices:
            logger.warning("Missing file in range", missing_file=f"rpc.{i}.txt")

    # Prepare output
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file_path = output_dir / "payloads.jsonl"
    if output_file_path.exists():
        logger.error(
            "Output file already exists, refusing to overwrite",
            output_file=str(output_file_path),
        )
        raise SystemExit(2)

    method_suffixes = [m.strip() for m in methods.split(",")]

    logger.info(
        "Starting conversion",
        input_dir=str(input_dir),
        output_file=str(output_file_path),
        file_count=len(files),
        start_block=start_block,
        end_block=end_block,
        methods=method_suffixes,
    )

    total_lines = 0
    with open(output_file_path, "w", encoding="utf-8") as out_f:
        for file_idx, (idx, file_path) in enumerate(files):
            lines_written = process_file(file_path, method_suffixes, out_f, logger)
            total_lines += lines_written
            if (file_idx + 1) % 100 == 0 or file_idx == len(files) - 1:
                logger.info(
                    "Progress",
                    files_processed=file_idx + 1,
                    total_files=len(files),
                    lines_written=total_lines,
                )

    logger.info(
        "Conversion complete",
        total_files=len(files),
        total_lines=total_lines,
        output_file=str(output_file_path),
    )
