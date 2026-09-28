#!/usr/bin/env python3
"""
Organize photos from an external drive by capture date and time-based "events".

Requires: exiftool (brew install exiftool)

Does NOT upload to iCloud — it prepares a clean folder tree for import into Photos.app.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

IMAGE_EXT = {
    ".jpg",
    ".jpeg",
    ".heic",
    ".heif",
    ".png",
    ".tif",
    ".tiff",
    ".dng",
    ".cr2",
    ".cr3",
    ".nef",
    ".arw",
    ".orf",
    ".rw2",
    ".gif",
    ".webp",
    ".mov",
    ".mp4",
    ".m4v",
}


@dataclass(frozen=True)
class PhotoMeta:
    path: Path
    taken: datetime
    camera: str
    lat: float | None
    lon: float | None
    used_file_date: bool


def require_exiftool() -> str:
    exe = shutil.which("exiftool")
    if not exe:
        print(
            "exiftool not found. Install: brew install exiftool",
            file=sys.stderr,
        )
        sys.exit(1)
    return exe


def iter_media(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXT:
            yield p


def parse_exif_datetime(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in (
        "%Y:%m:%d %H:%M:%S%z",
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(raw.replace("+00:00", "+0000"), fmt)
        except ValueError:
            continue
    return None


def read_metadata(exiftool: str, paths: list[Path]) -> list[PhotoMeta]:
    """Batch-read DateTimeOriginal / CreateDate via exiftool JSON."""
    if not paths:
        return []

    cmd = [
        exiftool,
        "-json",
        "-DateTimeOriginal",
        "-CreateDate",
        "-ModifyDate",
        "-Model",
        "-GPSLatitude",
        "-GPSLongitude",
        *map(str, paths),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 1):  # exiftool uses 1 when some files fail
        print(proc.stderr, file=sys.stderr)
        sys.exit(proc.returncode)

    out: list[PhotoMeta] = []
    for item in json.loads(proc.stdout or "[]"):
        src = Path(item.get("SourceFile", ""))
        dt_raw = (
            item.get("DateTimeOriginal")
            or item.get("CreateDate")
            or item.get("ModifyDate")
        )
        used_file_date = False
        taken = parse_exif_datetime(str(dt_raw)) if dt_raw else None
        if taken is None:
            taken = datetime.fromtimestamp(src.stat().st_mtime)
            used_file_date = True

        camera = str(item.get("Model") or "Unknown")
        lat = item.get("GPSLatitude")
        lon = item.get("GPSLongitude")
        out.append(
            PhotoMeta(
                path=src,
                taken=taken,
                camera=camera,
                lat=float(lat) if lat is not None else None,
                lon=float(lon) if lon is not None else None,
                used_file_date=used_file_date,
            )
        )
    return out


def safe_name(s: str, max_len: int = 80) -> str:
    s = re.sub(r'[\\/:*?"<>|]', "_", s.strip())
    s = re.sub(r"\s+", " ", s)
    return (s[:max_len] or "unnamed").strip(" .")


def cluster_events(
    items: list[PhotoMeta],
    gap_hours: float,
) -> list[list[PhotoMeta]]:
    """Split sorted photos into events when gap between shots exceeds threshold."""
    if not items:
        return []
    sorted_items = sorted(items, key=lambda x: x.taken)
    clusters: list[list[PhotoMeta]] = [[sorted_items[0]]]
    gap = timedelta(hours=gap_hours)
    for photo in sorted_items[1:]:
        if photo.taken - clusters[-1][-1].taken > gap:
            clusters.append([photo])
        else:
            clusters[-1].append(photo)
    return clusters


def event_folder_name(cluster: list[PhotoMeta], index: int) -> str:
    start = min(p.taken for p in cluster)
    end = max(p.taken for p in cluster)
    day = start.strftime("%Y-%m-%d")
    if start.date() == end.date():
        suffix = f"event_{index:03d}"
    else:
        suffix = f"event_{index:03d}_{end.strftime('%m-%d')}"
    return safe_name(f"{day}_{suffix}")


def unique_dest(dest_dir: Path, filename: str) -> Path:
    dest = dest_dir / filename
    if not dest.exists():
        return dest
    stem = Path(filename).stem
    ext = Path(filename).suffix
    n = 2
    while True:
        candidate = dest_dir / f"{stem}_{n}{ext}"
        if not candidate.exists():
            return candidate
        n += 1


def copy_or_link(src: Path, dest: Path, mode: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if mode == "copy":
        shutil.copy2(src, dest)
    elif mode == "hardlink":
        try:
            dest.hardlink_to(src)
        except OSError:
            shutil.copy2(src, dest)
    else:
        raise ValueError(mode)


def organize_by_date_only(meta: list[PhotoMeta], out: Path, mode: str) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for p in meta:
        rel = Path(p.taken.strftime("%Y")) / p.taken.strftime("%m") / p.taken.strftime("%d")
        dest_dir = out / rel
        dest = unique_dest(dest_dir, p.path.name)
        copy_or_link(p.path, dest, mode)
        counts[str(rel)] += 1
    return dict(counts)


def organize_by_events(
    meta: list[PhotoMeta],
    out: Path,
    mode: str,
    gap_hours: float,
) -> list[dict]:
    report: list[dict] = []
    by_day: dict[str, list[PhotoMeta]] = defaultdict(list)
    for p in meta:
        by_day[p.taken.strftime("%Y-%m-%d")].append(p)

    event_index = 1
    for day in sorted(by_day.keys()):
        clusters = cluster_events(by_day[day], gap_hours)
        for cluster in clusters:
            folder = event_folder_name(cluster, event_index)
            event_index += 1
            dest_dir = out / folder
            for p in cluster:
                dest = unique_dest(dest_dir, p.path.name)
                copy_or_link(p.path, dest, mode)
            report.append(
                {
                    "folder": folder,
                    "count": len(cluster),
                    "start": min(p.taken for p in cluster).isoformat(),
                    "end": max(p.taken for p in cluster).isoformat(),
                    "cameras": sorted({p.camera for p in cluster}),
                }
            )
    return report


def write_report_csv(report: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["folder", "count", "start", "end", "cameras", "event_title"],
        )
        w.writeheader()
        for row in report:
            w.writerow({**row, "cameras": "; ".join(row["cameras"]), "event_title": ""})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sort photos by EXIF date and optional time-based events.",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Root folder on the USB drive (e.g. /Volumes/MyDisk/DCIM)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.home() / "Pictures" / "SortedImport",
        help="Destination folder (default: ~/Pictures/SortedImport)",
    )
    parser.add_argument(
        "--mode",
        choices=("copy", "hardlink"),
        default="copy",
        help="copy (safe) or hardlink (saves space on same disk)",
    )
    parser.add_argument(
        "--layout",
        choices=("date", "events"),
        default="events",
        help="date = YYYY/MM/DD; events = clusters with time gaps",
    )
    parser.add_argument(
        "--gap-hours",
        type=float,
        default=4.0,
        help="New event if gap between photos exceeds this (events layout)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only scan and print summary, do not copy",
    )
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    if not source.is_dir():
        print(f"Source not found: {source}", file=sys.stderr)
        sys.exit(1)

    exiftool = require_exiftool()
    paths = list(iter_media(source))
    print(f"Found {len(paths)} media files under {source}")

    if not paths:
        sys.exit(0)

    # exiftool can choke on huge arg lists; batch in chunks
    meta: list[PhotoMeta] = []
    chunk = 400
    for i in range(0, len(paths), chunk):
        meta.extend(read_metadata(exiftool, paths[i : i + chunk]))

    no_exif = sum(1 for p in meta if p.used_file_date)
    print(f"Metadata loaded. Files using file date fallback: {no_exif}")

    if args.dry_run:
        if args.layout == "date":
            buckets: dict[str, int] = defaultdict(int)
            for p in meta:
                key = p.taken.strftime("%Y-%m-%d")
                buckets[key] += 1
            for day in sorted(buckets):
                print(f"  {day}: {buckets[day]} files")
        else:
            by_day: dict[str, list[PhotoMeta]] = defaultdict(list)
            for p in meta:
                by_day[p.taken.strftime("%Y-%m-%d")].append(p)
            total_events = 0
            for day in sorted(by_day.keys()):
                n = len(cluster_events(by_day[day], args.gap_hours))
                total_events += n
                print(f"  {day}: {len(by_day[day])} files -> {n} event folder(s)")
            print(f"Total event folders: {total_events}")
        return

    args.output.mkdir(parents=True, exist_ok=True)

    if args.layout == "date":
        counts = organize_by_date_only(meta, args.output, args.mode)
        print(f"Done. {sum(counts.values())} files -> {args.output}")
    else:
        report = organize_by_events(meta, args.output, args.mode, args.gap_hours)
        report_path = args.output / "_events_report.csv"
        write_report_csv(report, report_path)
        print(f"Done. {len(meta)} files in {len(report)} event folders -> {args.output}")
        print(f"Rename events: edit column event_title in {report_path} (optional)")


if __name__ == "__main__":
    main()
