"""Storage adapter tests for local persistence and S3-compatible object operations."""
import hashlib
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.services import object_storage


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.upload_args = None

    def upload_file(self, filename, bucket, key, ExtraArgs):
        payload = Path(filename).read_bytes()
        self.objects[(bucket, key)] = (payload, ExtraArgs["Metadata"])
        self.upload_args = ExtraArgs

    def head_object(self, Bucket, Key):
        payload, metadata = self.objects[(Bucket, Key)]
        return {"ContentLength": len(payload), "Metadata": metadata}

    def download_file(self, bucket, key, destination):
        payload, _ = self.objects[(bucket, key)]
        Path(destination).write_bytes(payload)

    def delete_object(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


@pytest.fixture
def settings(tmp_path):
    config = get_settings()
    previous = {
        "document_storage_backend": config.document_storage_backend,
        "document_storage_path": config.document_storage_path,
        "object_storage_bucket": config.object_storage_bucket,
    }
    config.document_storage_path = str(tmp_path / "private")
    config.document_storage_backend = "local"
    config.object_storage_bucket = None
    yield config
    for key, value in previous.items():
        setattr(config, key, value)


def test_local_storage_round_trip_and_path_traversal_rejection(settings, tmp_path):
    source = tmp_path / "upload.txt"
    source.write_bytes(b"course material")
    key = "ab/generated.txt"

    object_storage.persist_file(source, key)
    with object_storage.open_storage_file(key) as stored:
        assert stored.read_bytes() == b"course material"
    object_storage.delete_file(key)
    assert not (Path(settings.document_storage_path) / key).exists()

    with pytest.raises(ValueError):
        object_storage.delete_file("../outside.txt")


def test_s3_round_trip_verifies_checksum_and_uses_private_server_encryption(
    settings, monkeypatch, tmp_path
):
    fake = FakeS3()
    settings.document_storage_backend = "s3"
    settings.object_storage_bucket = "examgen-private"
    monkeypatch.setattr(object_storage, "_s3_client", lambda: fake)

    source = tmp_path / "upload.txt"
    payload = b"private academic source"
    source.write_bytes(payload)
    key = "ab/stable-object.txt"

    object_storage.persist_file(source, key)
    assert fake.upload_args["ServerSideEncryption"] == "AES256"
    assert "ACL" not in fake.upload_args
    assert fake.objects[("examgen-private", key)][1]["sha256"] == hashlib.sha256(payload).hexdigest()

    with object_storage.open_storage_file(key) as downloaded:
        assert downloaded.read_bytes() == payload
        temporary_path = downloaded
    assert not temporary_path.exists()

    object_storage.delete_file(key)
    assert ("examgen-private", key) not in fake.objects


def test_s3_upload_rejects_post_upload_integrity_mismatch(settings, monkeypatch, tmp_path):
    class CorruptS3(FakeS3):
        def head_object(self, Bucket, Key):
            return {"ContentLength": 999, "Metadata": {"sha256": "wrong"}}

    settings.document_storage_backend = "s3"
    settings.object_storage_bucket = "examgen-private"
    fake = CorruptS3()
    monkeypatch.setattr(object_storage, "_s3_client", lambda: fake)
    source = tmp_path / "upload.txt"
    source.write_bytes(b"source")

    with pytest.raises(RuntimeError, match="verification failed"):
        object_storage.persist_file(source, "ab/object.txt")
    assert ("examgen-private", "ab/object.txt") not in fake.objects
