import fileinput
from pathlib import Path
from typing import Callable
import subprocess
import re
import zstd
import logging

RETROSHEET_PATH = Path("/retrosheet")
OUTPUT_PATH = Path("/parsed")
OUTPUT_PATH.mkdir(exist_ok=True)

RETROSHEET_SUBDIRS = "gamelog", "schedule", "misc", "rosters", "event"
EVENT_FOLDERS = "asg", "post", "regular"

PARSE_FUNCS = {
    "daily": "cwdaily -q -y {year} {year}*",
    "comment": "cwcomment -q -y {year} {year}*",
    "game": "cwgame -q -y {year} -f 0-83 -x 0-94 {year}*",
    "sub": "cwsub -q -y {year} {year}*",
    "event": "cwevent -q -y {year} -f 0-96 -x 0-62 {year}*"
}


def compress(file: Path) -> None:
    """Replaces the original file with a compressed version"""
    logging.info("Compressing {}".format(file))
    compressed_file = file.with_suffix(file.suffix + ".zst")
    cctx = zstd.ZstdCompressor()
    with open(file, 'rb') as ifh, open(compressed_file, 'wb') as ofh:
        print(cctx.copy_stream(ifh, ofh))
    return file.unlink()


def parse_simple_files() -> None:
    def concat_files(input_path: Path, output_path: Path, glob: str = "*",
                     prepend_filename: bool = False,
                     strip_header: bool = False):
        files = (f for f in input_path.glob(glob) if f.is_file())
        with open(output_path, 'wt') as fout, fileinput.input(files) as fin:
            for line in fin:
                if fin.isfirstline() and strip_header:
                    continue
                if prepend_filename:
                    year = Path(fin.filename()).stem
                    modified_line = "{},{}".format(year, line)
                    fout.write(modified_line)
                else:
                    fout.write(line)
        return compress(output_path)

    retrosheet_base = Path(RETROSHEET_PATH)
    output_base = Path(OUTPUT_PATH)
    output_base.mkdir(exist_ok=True)
    subdirs = {subdir: retrosheet_base / subdir for subdir in RETROSHEET_SUBDIRS}

    print("Writing simple files...")
    concat_files(subdirs["gamelog"], output_base / "gamelog.csv.gz", glob="*.TXT")
    concat_files(subdirs["schedule"], output_base / "schedule.csv.gz", glob="*.TXT")
    concat_files(subdirs["misc"], output_base / "park.csv.gz", glob="parkcode.txt", strip_header=True)
    concat_files(subdirs["rosters"], output_base / "roster.csv.gz", glob="*.ROS", prepend_filename=True)


def parse_event_types():
    def parse_events(output_type: str, clean_func: Callable = None):
        event_base = RETROSHEET_PATH / "event"
        output_path = OUTPUT_PATH.joinpath(output_type).with_suffix(".csv")
        command_template = PARSE_FUNCS[output_type]
        f_out_inflated = open(output_path, 'w')
        for folder in EVENT_FOLDERS:
            data_path = event_base.joinpath(folder)
            years = {re.match("[0-9]{4}", f.stem)[0] for f in data_path.iterdir()
                     if re.match("[0-9]{4}", f.stem)}
            for year in sorted(years):
                command = command_template.format(year=year)
                print(data_path, command)
                subprocess.run(command, cwd=data_path, check=True, shell=True, text=True,
                               stdout=f_out_inflated)
        f_out_inflated.close()
        if clean_func:
            clean_func(output_path)
        compress(output_path)

    def drop_boxscore_files():
        for f in RETROSHEET_PATH.rglob("*.EB*"):
            f.unlink()

    def find_malformed_comments(output_path: Path):
        new_output_path = output_path.with_suffix(output_path.suffix + ".tmp")
        existing_comments = set()
        with open(output_path, 'r') as ifh, open(new_output_path, 'w') as ofh:
            for line in ifh:
                if line.count('"') % 2 != 0:
                    print("Bad comment line: {}".format(line))
                else:
                    existing_comments.add(line)
                    ofh.write(line)

        output_path.unlink()
        new_output_path.rename(output_path)

    parse_events("sub")
    parse_events("daily")
    drop_boxscore_files()
    parse_events("comment", clean_func=find_malformed_comments)
    parse_events("game")
    parse_events("event")


parse_simple_files()
parse_event_types()