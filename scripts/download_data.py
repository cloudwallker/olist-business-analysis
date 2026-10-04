#!/usr/bin/env python3
"""Acquire the pinned Olist snapshot using only the Python standard library.

Source data and adapted data: CC BY-NC-SA 4.0, credited to Olist.
The independently written downloader follows the repository's code license.
"""

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import stat
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile


DOWNLOAD_URL = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
EXPECTED_SHA256 = "967e41e04fc306fe604e2a693f488995a8b41e5047418f8a5c8e4abd6deca784"
ARCHIVE_NAME = "brazilian-ecommerce.zip"
REQUIRED_CSVS = (
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "product_category_name_translation.csv",
)
CHUNK_SIZE = 1024 * 1024


class DataAcquisitionError(Exception):
    """An actionable acquisition failure that is safe to print."""


class OfficialRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Allow only HTTPS redirects to the hosts used by the official download."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if (parsed.scheme != "https"
                or parsed.hostname not in {"www.kaggle.com", "storage.googleapis.com"}
                or parsed.username or parsed.password
                or parsed.port not in {None, 443}):
            raise DataAcquisitionError("官方下载出现不可信或非 HTTPS 重定向，已停止。")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(destination):
    request = urllib.request.Request(
        DOWNLOAD_URL, headers={"User-Agent": "Olist-Independent-Analytics/1.0"})
    opener = urllib.request.build_opener(OfficialRedirectHandler())
    try:
        # No authorization headers, cookie jar, Kaggle credentials or URL logging.
        with opener.open(request, timeout=120) as response, destination.open("xb") as stream:
            shutil.copyfileobj(response, stream, length=CHUNK_SIZE)
            stream.flush()
            os.fsync(stream.fileno())
    except DataAcquisitionError:
        raise
    except urllib.error.HTTPError as error:
        raise DataAcquisitionError(
            "Kaggle 官方下载返回 HTTP %s；可使用 --archive 离线复用固定快照。" % error.code) from None
    except (OSError, ValueError):
        # Underlying errors can contain signed redirect URLs or proxy credentials.
        raise DataAcquisitionError(
            "Kaggle 官方下载未完成；检查网络，或使用 --archive 离线复用固定快照。") from None


def _validate_package(package):
    seen = set()
    for member in package.infolist():
        name = member.filename
        posix = PurePosixPath(name)
        windows = PureWindowsPath(name)
        parts = name.replace("\\", "/").split("/")
        if (posix.is_absolute() or windows.is_absolute() or windows.drive
                or "\\" in name or ":" in name or "\x00" in name
                or any(part in {".", ".."} for part in parts)
                or any(part == "" for part in parts[:-1])
                or stat.S_ISLNK(member.external_attr >> 16)):
            raise DataAcquisitionError("ZIP 包含不安全路径或符号链接，已拒绝解压。")
        if name in seen:
            raise DataAcquisitionError("ZIP 包含重复成员，已拒绝解压。")
        seen.add(name)
    missing = sorted(set(REQUIRED_CSVS) - seen)
    if missing:
        raise DataAcquisitionError("ZIP 缺少所需 CSV：" + ", ".join(missing))
    if package.testzip() is not None:
        raise DataAcquisitionError("ZIP CRC 校验失败，原始数据未更新。")


def acquire_data(output_dir, *, archive=None):
    """Validate a full candidate before replacing raw; rollback failed installs.

    There is deliberately no hash override: every CLI input must match the
    reviewed official snapshot. Offline archives are copied before any rename.
    """
    output = Path(output_dir).absolute()
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise DataAcquisitionError("输出目录必须是普通目录，不能是文件或符号链接。")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".olist-download-", dir=str(output.parent))).resolve()
    # Confirm cleanup and all recursive moves remain in the explicitly chosen parent.
    if work.parent != output.parent or not work.name.startswith(".olist-download-"):
        raise DataAcquisitionError("无法确认临时目录边界，已停止。")
    candidate = work / "candidate_raw"
    previous = work / "previous_raw"
    installed = False
    try:
        partial = work / "archive.part"
        if archive is None:
            _download(partial)
        else:
            source = Path(archive)
            if not source.is_file():
                raise DataAcquisitionError("--archive 指定的本地 ZIP 不存在。")
            shutil.copyfile(source, partial)
        actual_hash = _sha256(partial)
        if actual_hash != EXPECTED_SHA256:
            raise DataAcquisitionError(
                "SHA-256 与固定官方快照不一致，原始数据未更新；不能自动接受新版或镜像。")
        verified_archive = work / ARCHIVE_NAME
        os.replace(partial, verified_archive)
        with zipfile.ZipFile(verified_archive) as package:
            _validate_package(package)
            if output.exists():
                # Keep existing metadata and other local files; selected inputs are
                # replaced in staging rather than opening an old symlink in-place.
                shutil.copytree(output, candidate, symlinks=True,
                                ignore=shutil.ignore_patterns(ARCHIVE_NAME, *REQUIRED_CSVS))
            else:
                candidate.mkdir()
            for name in REQUIRED_CSVS:
                destination = candidate / name
                if destination.parent.resolve() != candidate.resolve():
                    raise DataAcquisitionError("ZIP 解压目标超出候选目录，已停止。")
                with package.open(name) as source, destination.open("xb") as stream:
                    shutil.copyfileobj(source, stream, length=CHUNK_SIZE)
        shutil.copyfile(verified_archive, candidate / ARCHIVE_NAME)
        if output.exists():
            os.replace(output, previous)
        try:
            os.replace(candidate, output)
        except OSError:
            if previous.exists():
                try:
                    os.replace(previous, output)
                except OSError:
                    raise DataAcquisitionError(
                        "安装及回滚均失败；旧数据保留在临时目录 previous_raw，请恢复后再运行。") from None
            raise DataAcquisitionError("安装失败，已有原始数据已恢复。") from None
        installed = True
        return {"status": "passed", "archive_sha256": actual_hash, "files": list(REQUIRED_CSVS)}
    except DataAcquisitionError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        raise DataAcquisitionError("数据获取或 ZIP 校验失败，原始数据未更新。") from None
    finally:
        # Do not delete the sole surviving previous snapshot if rollback failed.
        if installed or not previous.exists():
            shutil.rmtree(work)


def main(argv=None):
    parser = argparse.ArgumentParser(description="获取并校验固定 Olist 官方公开数据快照。")
    parser.add_argument("--archive", type=Path, help="离线复用本地原版 ZIP，仍校验固定 SHA-256")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parents[1] / "data" / "raw",
                        help="原始数据输出目录，默认项目 data/raw")
    args = parser.parse_args(argv)
    try:
        result = acquire_data(args.output, archive=args.archive)
    except DataAcquisitionError as error:
        print("数据获取失败：%s" % error, file=sys.stderr)
        return 1
    print("已校验并安装 %s 个原版 CSV；SHA-256：%s" % (len(result["files"]), result["archive_sha256"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
