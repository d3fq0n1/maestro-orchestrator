"""
Tests for shard_manager — download, index, verify, and manage weight shards.

Uses synthetic safetensors files (no network calls needed).
"""

import json
import struct
from pathlib import Path

import pytest

from maestro.shard_manager import ShardManager, ShardManifest


def _create_safetensors_file(filepath: Path, tensors: dict):
    """Create a minimal safetensors file."""
    header_bytes = json.dumps(tensors).encode("utf-8")
    max_offset = 0
    for meta in tensors.values():
        offsets = meta.get("data_offsets", [0, 0])
        if len(offsets) == 2:
            max_offset = max(max_offset, offsets[1])

    with open(filepath, "wb") as f:
        f.write(struct.pack("<Q", len(header_bytes)))
        f.write(header_bytes)
        f.write(b"\x00" * max_offset)


def _make_llama_file(filepath: Path, layer_start: int, layer_end: int):
    """Create a safetensors file with Llama-style layer tensors."""
    tensors = {}
    offset = 0
    size = 512
    for i in range(layer_start, layer_end + 1):
        for part in ["self_attn.q_proj.weight", "mlp.gate_proj.weight"]:
            tensors[f"model.layers.{i}.{part}"] = {
                "dtype": "F16", "shape": [64, 64], "data_offsets": [offset, offset + size],
            }
            offset += size
    _create_safetensors_file(filepath, tensors)
    return filepath


class TestShardManagerIndex:
    def test_index_single_file(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model.safetensors", 0, 7)

        manager = ShardManager(shard_dir=tmp_path)
        manifest = manager.index_shards("test/model")

        assert manifest.model_id == "test/model"
        assert manifest.total_layers == 8
        assert len(manifest.files) == 1
        assert manifest.layer_coverage == [[0, 7]]
        assert manifest.precision == "fp16"

    def test_index_multiple_files(self, tmp_path):
        model_dir = tmp_path / "org__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model-00001.safetensors", 0, 15)
        _make_llama_file(model_dir / "model-00002.safetensors", 16, 31)

        manager = ShardManager(shard_dir=tmp_path)
        manifest = manager.index_shards("org/model")

        assert manifest.total_layers == 32
        assert len(manifest.files) == 2
        assert manifest.layer_coverage == [[0, 31]]
        assert manifest.complete is True

    def test_index_with_gaps(self, tmp_path):
        model_dir = tmp_path / "org__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "part1.safetensors", 0, 7)
        _make_llama_file(model_dir / "part2.safetensors", 16, 23)

        manager = ShardManager(shard_dir=tmp_path)
        manifest = manager.index_shards("org/model")

        assert manifest.complete is False
        assert len(manifest.layer_coverage) == 2  # Two separate ranges

    def test_manifest_persists(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        manager.index_shards("test/model")

        # Load from disk
        loaded = manager.load_manifest("test/model")
        assert loaded is not None
        assert loaded.model_id == "test/model"
        assert loaded.total_layers == 4

    def test_load_manifest_nonexistent(self, tmp_path):
        manager = ShardManager(shard_dir=tmp_path)
        assert manager.load_manifest("nonexistent/model") is None


class TestShardConfig:
    def test_generate_config(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model.safetensors", 0, 7)

        manager = ShardManager(shard_dir=tmp_path)
        manager.index_shards("test/model")
        config = manager.generate_shard_config("test/model")

        assert len(config) == 1
        assert config[0]["model_id"] == "test/model"
        assert config[0]["shard_format"] == "safetensors"
        assert "filepath" in config[0]
        assert "checksum" in config[0]

    def test_generate_config_with_layer_filter(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "part1.safetensors", 0, 15)
        _make_llama_file(model_dir / "part2.safetensors", 16, 31)

        manager = ShardManager(shard_dir=tmp_path)
        manager.index_shards("test/model")
        config = manager.generate_shard_config(
            "test/model", layer_start=0, layer_end=15
        )

        assert len(config) == 1
        assert config[0]["layer_range"][1] <= 15

    def test_generate_config_to_file(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        manager.index_shards("test/model")

        config_path = tmp_path / "node_shards.json"
        manager.generate_shard_config("test/model", output_path=config_path)

        assert config_path.exists()
        loaded = json.loads(config_path.read_text())
        assert len(loaded) == 1


class TestVerification:
    def test_verify_all_pass(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        manager.index_shards("test/model")
        results = manager.verify_all("test/model")

        assert len(results["passed"]) == 1
        assert len(results["failed"]) == 0
        assert len(results["missing"]) == 0

    def test_verify_missing_file(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        filepath = _make_llama_file(model_dir / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        manager.index_shards("test/model")

        # Delete the file after indexing
        filepath.unlink()
        results = manager.verify_all("test/model")

        assert len(results["missing"]) == 1

    def test_verify_corrupted_file(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        filepath = _make_llama_file(model_dir / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        manager.index_shards("test/model")

        # Corrupt the file
        with open(filepath, "r+b") as f:
            f.seek(100)
            f.write(b"\xff" * 50)

        results = manager.verify_all("test/model")
        assert len(results["failed"]) == 1

    def test_verify_no_manifest(self, tmp_path):
        manager = ShardManager(shard_dir=tmp_path)
        results = manager.verify_all("nonexistent")
        assert "manifest not found" in results["missing"]


class TestInventory:
    def test_list_models(self, tmp_path):
        for name in ["org__model1", "org__model2"]:
            d = tmp_path / name
            d.mkdir()
            _make_llama_file(d / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        models = manager.list_models()
        assert "org/model1" in models
        assert "org/model2" in models

    def test_list_models_empty(self, tmp_path):
        manager = ShardManager(shard_dir=tmp_path)
        assert manager.list_models() == []

    def test_disk_usage_single_model(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        usage = manager.disk_usage("test/model")
        assert usage["files"] == 1
        assert usage["total_bytes"] > 0

    def test_disk_usage_all(self, tmp_path):
        for name in ["m1", "m2"]:
            d = tmp_path / name
            d.mkdir()
            _make_llama_file(d / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        usage = manager.disk_usage()
        assert usage["total_files"] == 2

    def test_remove_model(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        assert manager.remove_model("test/model")
        assert not model_dir.exists()

    def test_remove_nonexistent(self, tmp_path):
        manager = ShardManager(shard_dir=tmp_path)
        assert not manager.remove_model("fake/model")


class TestGetShardFilepath:
    def test_existing_file(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()
        _make_llama_file(model_dir / "model.safetensors", 0, 3)

        manager = ShardManager(shard_dir=tmp_path)
        path = manager.get_shard_filepath("test/model", "model.safetensors")
        assert path is not None
        assert path.exists()

    def test_missing_file(self, tmp_path):
        model_dir = tmp_path / "test__model"
        model_dir.mkdir()

        manager = ShardManager(shard_dir=tmp_path)
        assert manager.get_shard_filepath("test/model", "nonexistent.safetensors") is None
