"""
Try PVR compression on sample PDFs before trusting a setting.

    python scripts/pvr_compress_test.py <folder-with-pdfs> [--dpi 200] [--quality 85]
    # inside Docker:
    docker compose exec fastapi-web python scripts/pvr_compress_test.py /app/spool/samples

For every PDF it runs the `lossless` and `balanced` modes (the same code the background
worker uses) and prints a size table. In <folder>/_compress_test/ it writes:
  * <name>.lossless.pdf / <name>.balanced.pdf   (only when the safety rules accept them)
  * <name>.p1.original.png / .p1.lossless.png / .p1.balanced.png   page-1 previews (needs Ghostscript)
Open the PNGs side by side and check that handwriting, signatures, meter readings and
seal numbers are still clearly readable.
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings  # noqa: E402
from services import pdf_compress  # noqa: E402


def render_page1(pdf: str, png: str, dpi: int = 150) -> bool:
    gs = pdf_compress.ghostscript_bin()
    if not gs:
        return False
    r = subprocess.run([gs, "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=png16m", f"-r{dpi}",
                        "-dFirstPage=1", "-dLastPage=1", f"-sOutputFile={png}", pdf],
                       capture_output=True, timeout=120)
    return r.returncode == 0 and os.path.exists(png)


def mb(n: int) -> str:
    return f"{n / 1048576:6.2f} MB"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--dpi", type=int, default=settings.PVR_COMPRESS_DPI)
    ap.add_argument("--quality", type=int, default=settings.PVR_JPEG_QUALITY)
    args = ap.parse_args()
    settings.PVR_COMPRESS_DPI, settings.PVR_JPEG_QUALITY = args.dpi, args.quality

    pdfs = sorted(f for f in os.listdir(args.folder) if f.lower().endswith(".pdf"))
    if not pdfs:
        print("No .pdf files in", args.folder)
        return 1
    out_dir = os.path.join(args.folder, "_compress_test")
    os.makedirs(out_dir, exist_ok=True)
    has_gs = bool(pdf_compress.ghostscript_bin())
    print(f"Ghostscript: {'yes' if has_gs else 'NOT FOUND (balanced = lossless only, no previews)'}"
          f" | DPI {args.dpi} | JPEG quality {args.quality}\n")
    print(f"{'file':40} {'pages':>5} {'original':>10} {'lossless':>18} {'balanced':>18}")

    tot = {"orig": 0, "lossless": 0, "balanced": 0}
    for name in pdfs:
        src = os.path.join(args.folder, name)
        stem = os.path.splitext(name)[0]
        row = {}
        render_page1(src, os.path.join(out_dir, f"{stem}.p1.original.png"))
        for mode in ("lossless", "balanced"):
            res = pdf_compress.compress(src, mode=mode)
            row[mode] = res
            if res.used:
                dst = os.path.join(out_dir, f"{stem}.{mode}.pdf")
                shutil.move(res.path, dst)
                render_page1(dst, os.path.join(out_dir, f"{stem}.p1.{mode}.png"))
        orig = row["lossless"].original_size
        tot["orig"] += orig

        def cell(mode):
            r = row[mode]
            tot[mode] += r.final_size
            pct = 100 * r.final_size / orig if orig else 100
            return f"{mb(r.final_size)} {pct:4.0f}%{'' if r.used else '*'}"

        print(f"{name[:40]:40} {str(row['lossless'].page_count or '?'):>5} {mb(orig):>10} "
              f"{cell('lossless'):>18} {cell('balanced'):>18}")
        for mode in ("lossless", "balanced"):
            if not row[mode].used:
                print(f"{'':48}* {mode}: {row[mode].note}")

    print(f"\n{'TOTAL':40} {'':>5} {mb(tot['orig']):>10} {mb(tot['lossless']):>13} {'':4} {mb(tot['balanced']):>13}")
    print(f"\n* = original kept by the safety rules. Previews and accepted PDFs: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
