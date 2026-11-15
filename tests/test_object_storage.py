"""Stockage objet (storage.py) : sources et destinations CSV / JSON / Parquet sur
s3://, testées avec moto (serveur S3 en mémoire). Azure et GCS passent par le
même code (fsspec) ; Azurite est utilisé s'il répond (HYDRA_TEST_AZURITE)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

s3fs = pytest.importorskip("s3fs")
moto_server = pytest.importorskip("moto.server")

from hydra_etl.internal import storage  # noqa: E402
from hydra_etl.internal.runner.executor import JobExecutor  # noqa: E402


@pytest.fixture(scope="module")
def s3():
    for var in ("NO_PROXY", "no_proxy"):                 # le serveur local ne passe pas par un proxy
        os.environ[var] = ",".join(x for x in (os.environ.get(var), "127.0.0.1", "localhost") if x)
    srv = moto_server.ThreadedMotoServer(ip_address="127.0.0.1", port=0, verbose=False)
    srv.start()
    host, port = srv.get_host_and_port()
    opts = {"key": "test", "secret": "test", "endpoint_url": f"http://{host}:{port}",
            "client_kwargs": {"region_name": "us-east-1"}}
    fs = s3fs.S3FileSystem(**opts)
    fs.mkdir("lake", create_parents=True, region_name="us-east-1") if False else fs.call_s3("create_bucket", Bucket="lake")
    yield fs, opts
    srv.stop()


def _job(tmp_path: Path, src: dict, dst: dict, steps=None) -> Path:
    job = tmp_path / "job"
    job.mkdir(exist_ok=True)
    (job / "sources.yaml").write_text(json.dumps({"version": "1.0", "sources": {"src": src}}))
    (job / "destinations.yaml").write_text(json.dumps({"version": "1.0", "destinations": {"dst": dst}}))
    (job / "pipeline.yaml").write_text(json.dumps({"version": "1.0", "pipeline": {"from": "src", "to": "dst"}}))
    if steps:
        (job / "transformations.yaml").write_text(json.dumps({"version": "1.0", "steps": steps}))
    return job


def _run(job: Path):
    return JobExecutor(job_dir=job).run()


def test_uri_helpers():
    assert storage.is_remote("s3://b/k") and storage.is_remote("az://c/p") and storage.is_remote("gs://b/k")
    assert not storage.is_remote("C:\\data\\x.csv") and not storage.is_remote("data/x.csv")
    assert storage.join("s3://b/landing/", "2026/x.csv") == "s3://b/landing/2026/x.csv"
    assert storage.join("s3://b/landing", "s3://other/y.csv") == "s3://other/y.csv"
    with pytest.raises(ValueError, match="not supported yet"):
        storage.check_uri("sftp://host/x.csv", "source 'a'")
    with pytest.raises(ValueError, match="unknown location scheme"):
        storage.check_uri("foo://x/y", "source 'a'")


def test_csv_pattern_to_csv(s3, tmp_path):
    fs, opts = s3
    fs.pipe("lake/in/orders_1.csv", b"id,amount\n1,10.5\n2,3\n")
    fs.pipe("lake/in/orders_2.csv", b"id,amount\n3,7\n")
    fs.pipe("lake/in/other.txt", b"x")
    job = _job(tmp_path,
               {"type": "csv", "connection": {"base_path": "s3://lake/in/", "storage": opts},
                "extract": {"table": "orders_*.csv"}},
               {"type": "csv", "connection": {"storage": opts},
                "load": {"table": "s3://lake/out/orders.csv", "mode": "replace"}})
    r = _run(job)
    assert r.success, r.error
    assert r.rows_out == 3
    out = fs.cat("lake/out/orders.csv").decode()
    assert out.splitlines()[0] == "id,amount" and len(out.splitlines()) == 4
    assert not list(Path(job).glob("*.csv"))                 # rien n'est resté dans le job


def test_append_downloads_the_existing_file(s3, tmp_path):
    fs, opts = s3
    fs.pipe("lake/app/in.csv", b"id\n2\n")
    fs.pipe("lake/app/out.csv", b"id\n1\n")
    job = _job(tmp_path,
               {"type": "csv", "connection": {"storage": opts}, "extract": {"table": "s3://lake/app/in.csv"}},
               {"type": "csv", "connection": {"base_path": "s3://lake/app", "storage": opts},
                "load": {"table": "out.csv", "mode": "append"}})
    r = _run(job)
    assert r.success, r.error
    assert fs.cat("lake/app/out.csv").decode().split() == ["id", "1", "2"]


def test_failed_job_leaves_the_remote_file_unchanged(s3, tmp_path):
    fs, opts = s3
    fs.pipe("lake/f/in.csv", b"id\nabc\n")
    fs.pipe("lake/f/out.csv", b"id\nold\n")
    job = _job(tmp_path,
               {"type": "csv", "connection": {"storage": opts}, "extract": {"table": "s3://lake/f/in.csv"}},
               {"type": "csv", "connection": {"storage": opts},
                "load": {"table": "s3://lake/f/out.csv", "mode": "replace"}},
               steps=[{"cast": {"mapping": {"id": "int"}}}])
    r = _run(job)
    assert not r.success
    assert fs.cat("lake/f/out.csv").decode() == "id\nold\n"


def test_parquet_and_json_round_trip(s3, tmp_path):
    pytest.importorskip("pyarrow")
    fs, opts = s3
    fs.pipe("lake/j/in.json", json.dumps([{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]).encode())
    job = _job(tmp_path,
               {"type": "json", "connection": {"storage": opts}, "extract": {"table": "s3://lake/j/in.json"}},
               {"type": "parquet", "connection": {"storage": opts},
                "load": {"table": "s3://lake/j/out.parquet", "mode": "replace"}})
    r = _run(job)
    assert r.success, r.error
    import io
    import pyarrow.parquet as pq
    t = pq.read_table(io.BytesIO(fs.cat("lake/j/out.parquet")))
    assert t.num_rows == 2 and t.column_names == ["id", "name"]


def test_clear_errors(s3, tmp_path):
    fs, opts = s3
    job = _job(tmp_path,
               {"type": "csv", "connection": {"storage": opts}, "extract": {"table": "s3://lake/none/*.csv"}},
               {"type": "csv", "connection": {}, "load": {"table": "out.csv", "mode": "replace"}})
    r = _run(job)
    assert not r.success and "no file matches s3://lake/none/*.csv" in r.error
    job = _job(tmp_path,
               {"type": "csv", "connection": {"storage": opts}, "extract": {"table": "s3://lake/none/x.csv"}},
               {"type": "csv", "connection": {}, "load": {"table": "out.csv", "mode": "replace"}})
    r = _run(job)
    assert not r.success and "file not found" in r.error
    job = _job(tmp_path,
               {"type": "csv", "connection": {"storage": opts}, "extract": {"table": "local.csv"}},
               {"type": "csv", "connection": {}, "load": {"table": "out.csv", "mode": "replace"}})
    r = _run(job)
    assert not r.success and "connection.storage is set" in r.error


@pytest.mark.skipif(not os.environ.get("HYDRA_TEST_AZURITE"), reason="set HYDRA_TEST_AZURITE=host:port (Azurite blob)")
def test_azure_with_azurite(tmp_path):
    pytest.importorskip("adlfs")
    host, _, port = os.environ["HYDRA_TEST_AZURITE"].partition(":")
    conn = ("DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
            "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
            f"BlobEndpoint=http://{host}:{port}/devstoreaccount1;")
    opts = {"connection_string": conn}
    fs = storage.filesystem("az://x", opts)
    if not fs.exists("landing"):
        fs.mkdir("landing")
    fs.pipe("landing/in.csv", b"id,v\n1,a\n")
    job = _job(tmp_path,
               {"type": "csv", "connection": {"base_path": "az://landing", "storage": opts},
                "extract": {"table": "in.csv"}},
               {"type": "csv", "connection": {"base_path": "az://landing", "storage": opts},
                "load": {"table": "out/copy.csv", "mode": "replace"}})
    r = _run(job)
    assert r.success, r.error
    assert fs.cat("landing/out/copy.csv").decode().split() == ["id,v", "1,a"]


@pytest.mark.skipif(not os.environ.get("HYDRA_TEST_FAKE_GCS"), reason="set HYDRA_TEST_FAKE_GCS=http://host:port")
def test_gcs_with_fake_gcs_server(tmp_path):
    pytest.importorskip("gcsfs")
    opts = {"endpoint_url": os.environ["HYDRA_TEST_FAKE_GCS"], "token": "anon", "project": "test"}
    fs = storage.filesystem("gs://x", opts)
    if not fs.exists("landing"):
        fs.mkdir("landing")
    fs.pipe("landing/in.csv", b"id,v\n1,a\n")
    job = _job(tmp_path,
               {"type": "csv", "connection": {"storage": opts}, "extract": {"table": "gs://landing/in.csv"}},
               {"type": "csv", "connection": {"storage": opts},
                "load": {"table": "gs://landing/out/copy.csv", "mode": "replace"}})
    r = _run(job)
    assert r.success, r.error
    fs.invalidate_cache()
    assert fs.cat("landing/out/copy.csv").decode().split() == ["id,v", "1,a"]


def test_file_trigger_on_s3(s3):
    """Déclencheur fichier sur un motif s3:// : un fichier ajouté produit un événement."""
    from hydra_etl.triggers.engine import make_watcher
    from hydra_etl.triggers.models import ProjectTrigger
    fs, opts = s3
    fs.pipe("lake/drop/old.csv", b"x")
    t = ProjectTrigger(name="drop", type="file", path="s3://lake/drop/*.csv", storage=opts, debounce=0)
    w = make_watcher(Path("."), t)
    assert w.poll(0.0) == []
    fs.pipe("lake/drop/new.csv", b"y")
    events = w.poll(1.0) + w.poll(2.0)
    assert [(e.path, e.kind) for e in events] == [("s3://lake/drop/new.csv", "added")]


def test_trigger_path_rules():
    from hydra_etl.triggers.models import ProjectTrigger
    with pytest.raises(ValueError, match="not supported yet"):
        ProjectTrigger(name="t", type="file", path="sftp://host/in/*.csv")
    with pytest.raises(ValueError, match="storage only applies"):
        ProjectTrigger(name="t", type="file", path="in/*.csv", storage={"key": "k"})
    with pytest.raises(ValueError, match="must stay inside the project"):
        ProjectTrigger(name="t", type="file", path="../in/*.csv")
