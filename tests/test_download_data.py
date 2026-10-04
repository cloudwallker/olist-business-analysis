"""Downloader safety tests; synthetic archives never enter real analysis data."""

import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import zipfile

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "download_data.py"
CSV_NAMES = (
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "product_category_name_translation.csv",
)
TRANSLATION = b"\xef\xbb\xbfproduct_category_name,product_category_name_english\nexemplo,example\n"


def load_downloader():
    # A missing implementation is a normal RED assertion, not a collection error.
    assert SCRIPT.is_file(), "The data download CLI has not been implemented yet."
    spec = importlib.util.spec_from_file_location("olist_download_data", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_archive(tmp_path, *, missing=None, extra=None, symlink=False):
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as package:
        for name in CSV_NAMES:
            if name != missing:
                package.writestr(name, TRANSLATION if name == CSV_NAMES[-1] else b"id,value\nfixture,1\n")
        if extra:
            if symlink:
                entry = zipfile.ZipInfo(extra)
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                package.writestr(entry, "../outside.csv")
            else:
                package.writestr(extra, b"unexpected\n")
    return archive


def set_fixture_hash(monkeypatch, module, archive):
    # Synthetic fixtures cannot have the official archive's cryptographic hash.
    # Only test process memory is patched; the CLI has no override option.
    monkeypatch.setattr(module, "EXPECTED_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())


def old_raw(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "olist_orders_dataset.csv").write_bytes(b"previous valid input\n")
    (raw / "kaggle-dataset-metadata.json").write_bytes(b'{"local":"metadata"}\n')
    return raw


def test_offline_install_preserves_original_bytes_and_utf8_bom(tmp_path, monkeypatch):
    module = load_downloader()
    archive = make_archive(tmp_path)
    set_fixture_hash(monkeypatch, module, archive)
    raw = old_raw(tmp_path)
    result = module.acquire_data(raw, archive=archive)
    assert result["status"] == "passed"
    assert (raw / "product_category_name_translation.csv").read_bytes() == TRANSLATION
    assert (raw / "olist_orders_dataset.csv").read_bytes() == b"id,value\nfixture,1\n"
    assert (raw / "brazilian-ecommerce.zip").read_bytes() == archive.read_bytes()
    assert (raw / "kaggle-dataset-metadata.json").read_bytes() == b'{"local":"metadata"}\n'
    assert all((raw / name).is_file() for name in CSV_NAMES)
    assert not list(tmp_path.glob(".olist-download-*"))


def test_official_hash_is_enforced_and_old_raw_is_unchanged(tmp_path):
    module = load_downloader()
    archive = make_archive(tmp_path)
    raw = old_raw(tmp_path)
    before = {p.name: p.read_bytes() for p in raw.iterdir()}
    with pytest.raises(module.DataAcquisitionError, match="SHA-256"):
        module.acquire_data(raw, archive=archive)
    assert {p.name: p.read_bytes() for p in raw.iterdir()} == before
    assert not list(tmp_path.glob(".olist-download-*"))


def test_missing_required_csv_does_not_publish_partial_inputs(tmp_path, monkeypatch):
    module = load_downloader()
    archive = make_archive(tmp_path, missing="olist_order_reviews_dataset.csv")
    set_fixture_hash(monkeypatch, module, archive)
    raw = old_raw(tmp_path)
    with pytest.raises(module.DataAcquisitionError, match="olist_order_reviews_dataset.csv"):
        module.acquire_data(raw, archive=archive)
    assert (raw / "olist_orders_dataset.csv").read_bytes() == b"previous valid input\n"
    assert not (raw / "olist_order_items_dataset.csv").exists()


@pytest.mark.parametrize("unsafe_name", [
    "../escape.csv", "nested/../../escape.csv", "/absolute.csv",
    "..\\escape.csv", "C:/escape.csv", "C:\\escape.csv",
    "\\\\server\\share\\escape.csv", "file.csv:stream",
])
def test_unsafe_zip_paths_are_rejected_before_any_publication(tmp_path, monkeypatch, unsafe_name):
    module = load_downloader()
    archive = make_archive(tmp_path, extra=unsafe_name)
    set_fixture_hash(monkeypatch, module, archive)
    raw = old_raw(tmp_path)
    with pytest.raises(module.DataAcquisitionError, match="ZIP"):
        module.acquire_data(raw, archive=archive)
    assert (raw / "olist_orders_dataset.csv").read_bytes() == b"previous valid input\n"
    assert not (tmp_path / "escape.csv").exists()


def test_zip_symlink_is_rejected_even_when_not_selected(tmp_path, monkeypatch):
    module = load_downloader()
    archive = make_archive(tmp_path, extra="link.csv", symlink=True)
    set_fixture_hash(monkeypatch, module, archive)
    with pytest.raises(module.DataAcquisitionError, match="ZIP"):
        module.acquire_data(tmp_path / "raw", archive=archive)
    assert not (tmp_path / "raw").exists()


def test_duplicate_zip_member_is_rejected(tmp_path, monkeypatch):
    module = load_downloader()
    archive = make_archive(tmp_path)
    with pytest.warns(UserWarning), zipfile.ZipFile(archive, "a") as package:
        package.writestr("olist_orders_dataset.csv", b"different\n")
    set_fixture_hash(monkeypatch, module, archive)
    with pytest.raises(module.DataAcquisitionError, match="ZIP"):
        module.acquire_data(tmp_path / "raw", archive=archive)
    assert not (tmp_path / "raw").exists()


def test_install_failure_restores_previous_raw(tmp_path, monkeypatch):
    module = load_downloader()
    archive = make_archive(tmp_path)
    set_fixture_hash(monkeypatch, module, archive)
    raw = old_raw(tmp_path)
    replace = module.os.replace

    def fail_install(source, destination):
        if Path(source).name == "candidate_raw" and Path(destination) == raw:
            raise OSError("simulated publish failure")
        return replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_install)
    with pytest.raises(module.DataAcquisitionError):
        module.acquire_data(raw, archive=archive)
    assert (raw / "olist_orders_dataset.csv").read_bytes() == b"previous valid input\n"
    assert (raw / "kaggle-dataset-metadata.json").is_file()
    assert not list(tmp_path.glob(".olist-download-*"))


def test_official_download_stream_is_verified_before_install(tmp_path, monkeypatch):
    module = load_downloader()
    archive = make_archive(tmp_path)
    set_fixture_hash(monkeypatch, module, archive)

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
            assert not request.has_header("Authorization")
            assert not request.has_header("Cookie")
            return io.BytesIO(archive.read_bytes())

    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *handlers: Opener())
    raw = tmp_path / "raw"
    result = module.acquire_data(raw)
    assert result["status"] == "passed"
    assert (raw / "brazilian-ecommerce.zip").read_bytes() == archive.read_bytes()


def test_failed_download_preserves_raw_and_sanitizes_error(tmp_path, monkeypatch, capsys):
    module = load_downloader()
    raw = old_raw(tmp_path)

    class BrokenResponse(io.BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("private-query-value-must-not-be-printed")
            return super().read(4)

    class Opener:
        def open(self, request, timeout):
            return BrokenResponse(b"partial archive")

    monkeypatch.setattr(module.urllib.request, "build_opener", lambda *handlers: Opener())
    assert module.main(["--output", str(raw)]) == 1
    assert "private-query-value" not in capsys.readouterr().err
    assert (raw / "olist_orders_dataset.csv").read_bytes() == b"previous valid input\n"
    assert not list(tmp_path.glob(".olist-download-*"))


def test_cli_supports_offline_archive(tmp_path, monkeypatch, capsys):
    module = load_downloader()
    archive = make_archive(tmp_path)
    set_fixture_hash(monkeypatch, module, archive)
    assert module.main(["--archive", str(archive), "--output", str(tmp_path / "raw")]) == 0
    assert "7" in capsys.readouterr().out


@pytest.mark.parametrize("url", ["http://storage.googleapis.com/data.zip", "https://example.com/data.zip"])
def test_download_rejects_untrusted_or_insecure_redirects(url):
    module = load_downloader()
    handler = module.OfficialRedirectHandler()
    request = module.urllib.request.Request(module.DOWNLOAD_URL)
    with pytest.raises(module.DataAcquisitionError):
        handler.redirect_request(request, None, 302, "redirect", {}, url)
