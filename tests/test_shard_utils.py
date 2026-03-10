"""
Tests for shard_utils — safetensors parsing, layer mapping, byte-range hashing.

Uses synthetic safetensors files (no real model weights needed).
"""

import hashlib
import json
import struct
from pathlib import Path

import pytest

from maestro.shard_utils import (
    read_safetensors_header,
    extract_layer_indices,
    get_layer_range_from_file,
    get_tensor_byte_ranges,
    hash_byte_range,
    hash_file,
    build_shard_descriptor,
    scan_shard_directory,
    verify_shard_integrity,
    _safetensors_dtype_to_precision,
)


def _create_safetensors_file(filepath: Path, tensors: dict, metadata: dict = None):
    """
    Create a minimal safetensors file for testing.

    tensors: {name: {"dtype": "F16", "shape": [dim1, dim2], "data_offsets": [start, end]}}
    The actual tensor data is filled with zeros.
    """
    header = dict(tensors)
    if metadata:
        header["__metadata__"] = metadata

    # Calculate total data size from offsets
    max_offset = 0
    for name, meta in tensors.items():
        offsets = meta.get("data_offsets", [0, 0])
        if len(offsets) == 2:
            max_offset = max(max_offset, offsets[1])

    header_bytes = json.dumps(header).encode("utf-8")
    header_size = len(header_bytes)

    with open(filepath, "wb") as f:
        f.write(struct.pack("<Q", header_size))
        f.write(header_bytes)
        # Write zero-filled tensor data
        f.write(b"\x00" * max_offset)


def _make_llama_safetensors(filepath: Path, layer_start: int, layer_end: int):
    """Create a safetensors file mimicking Llama layer naming."""
    tensors = {}
    offset = 0
    tensor_size = 1024  # small for testing

    for layer_idx in range(layer_start, layer_end + 1):
        for suffix in [
            "self_attn.q_proj.weight",
            "self_attn.k_proj.weight",
            "self_attn.v_proj.weight",
            "mlp.gate_proj.weight",
        ]:
            name = f"model.layers.{layer_idx}.{suffix}"
            tensors[name] = {
                "dtype": "F16",
                "shape": [128, 128],
                "data_offsets": [offset, offset + tensor_size],
            }
            offset += tensor_size

    _create_safetensors_file(filepath, tensors)
    return filepath


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReadHeader:
    def test_read_valid_header(self, tmp_path):
        filepath = tmp_path / "test.safetensors"
        _create_safetensors_file(filepath, {
            "weight": {"dtype": "F16", "shape": [10, 10], "data_offsets": [0, 200]},
        })
        header = read_safetensors_header(filepath)
        assert "weight" in header
        assert header["weight"]["dtype"] == "F16"

    def test_read_header_with_metadata(self, tmp_path):
        filepath = tmp_path / "test.safetensors"
        _create_safetensors_file(
            filepath,
            {"w": {"dtype": "F32", "shape": [5], "data_offsets": [0, 20]}},
            metadata={"format": "pt"},
        )
        header = read_safetensors_header(filepath)
        assert "__metadata__" in header
        assert header["__metadata__"]["format"] == "pt"

    def test_read_truncated_file(self, tmp_path):
        filepath = tmp_path / "bad.safetensors"
        filepath.write_bytes(b"\x00\x00")
        with pytest.raises(ValueError, match="too small"):
            read_safetensors_header(filepath)

    def test_read_oversized_header(self, tmp_path):
        filepath = tmp_path / "huge.safetensors"
        # Header size claims to be 200MB
        with open(filepath, "wb") as f:
            f.write(struct.pack("<Q", 200_000_000))
            f.write(b"\x00" * 100)
        with pytest.raises(ValueError, match="unreasonable"):
            read_safetensors_header(filepath)


class TestExtractLayerIndices:
    def test_llama_naming(self):
        header = {
            "model.layers.0.self_attn.q_proj.weight": {},
            "model.layers.0.mlp.gate_proj.weight": {},
            "model.layers.1.self_attn.q_proj.weight": {},
            "model.embed_tokens.weight": {},
            "model.norm.weight": {},
        }
        layers = extract_layer_indices(header)
        assert 0 in layers
        assert 1 in layers
        assert -1 in layers  # non-layer tensors
        assert len(layers[0]) == 2
        assert len(layers[1]) == 1

    def test_gpt2_naming(self):
        header = {
            "transformer.h.0.attn.weight": {},
            "transformer.h.5.mlp.weight": {},
            "transformer.wte.weight": {},
        }
        layers = extract_layer_indices(header)
        assert 0 in layers
        assert 5 in layers
        assert -1 in layers

    def test_bert_naming(self):
        header = {
            "encoder.layer.0.attention.weight": {},
            "encoder.layer.11.output.weight": {},
        }
        layers = extract_layer_indices(header)
        assert 0 in layers
        assert 11 in layers

    def test_gguf_naming(self):
        header = {
            "blk.0.attn_q.weight": {},
            "blk.31.ffn_down.weight": {},
        }
        layers = extract_layer_indices(header)
        assert 0 in layers
        assert 31 in layers

    def test_metadata_excluded(self):
        header = {
            "__metadata__": {"format": "pt"},
            "model.layers.0.weight": {},
        }
        layers = extract_layer_indices(header)
        assert "__metadata__" not in str(layers)


class TestGetLayerRange:
    def test_layer_range_from_file(self, tmp_path):
        filepath = _make_llama_safetensors(tmp_path / "layers_0_7.safetensors", 0, 7)
        start, end = get_layer_range_from_file(filepath)
        assert start == 0
        assert end == 7

    def test_layer_range_middle(self, tmp_path):
        filepath = _make_llama_safetensors(tmp_path / "layers_16_31.safetensors", 16, 31)
        start, end = get_layer_range_from_file(filepath)
        assert start == 16
        assert end == 31

    def test_no_layer_tensors(self, tmp_path):
        filepath = tmp_path / "embeddings.safetensors"
        _create_safetensors_file(filepath, {
            "model.embed_tokens.weight": {"dtype": "F16", "shape": [32000, 4096], "data_offsets": [0, 100]},
        })
        start, end = get_layer_range_from_file(filepath)
        assert start == -1
        assert end == -1


class TestTensorByteRanges:
    def test_byte_ranges(self, tmp_path):
        filepath = tmp_path / "test.safetensors"
        _create_safetensors_file(filepath, {
            "w1": {"dtype": "F16", "shape": [10], "data_offsets": [0, 20]},
            "w2": {"dtype": "F16", "shape": [10], "data_offsets": [20, 40]},
        })
        ranges = get_tensor_byte_ranges(filepath)
        assert "w1" in ranges
        assert "w2" in ranges
        # w2 starts after w1
        assert ranges["w2"][0] > ranges["w1"][0]


class TestByteRangeHash:
    def test_hash_deterministic(self, tmp_path):
        filepath = tmp_path / "data.bin"
        filepath.write_bytes(b"hello world" * 100)
        h1 = hash_byte_range(filepath, 0, 11)
        h2 = hash_byte_range(filepath, 0, 11)
        assert h1 == h2

    def test_different_ranges_different_hashes(self, tmp_path):
        filepath = tmp_path / "data.bin"
        filepath.write_bytes(b"abcdefghijklmnop" * 100)
        h1 = hash_byte_range(filepath, 0, 8)
        h2 = hash_byte_range(filepath, 8, 8)
        assert h1 != h2

    def test_hash_matches_manual(self, tmp_path):
        filepath = tmp_path / "data.bin"
        data = b"test data for hashing"
        filepath.write_bytes(data)
        expected = hashlib.sha256(data[:10]).hexdigest()
        assert hash_byte_range(filepath, 0, 10) == expected


class TestHashFile:
    def test_full_file_hash(self, tmp_path):
        filepath = tmp_path / "data.bin"
        data = b"full file content"
        filepath.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert hash_file(filepath) == expected


class TestBuildShardDescriptor:
    def test_descriptor_from_file(self, tmp_path):
        filepath = _make_llama_safetensors(tmp_path / "model.safetensors", 0, 7)
        desc = build_shard_descriptor(filepath, model_id="test/model")
        assert desc.model_id == "test/model"
        assert desc.layer_range == (0, 7)
        assert desc.shard_format == "safetensors"
        assert desc.precision == "fp16"
        assert desc.size_bytes > 0
        assert desc.checksum != ""
        assert len(desc.tensor_names) > 0

    def test_auto_generated_shard_id(self, tmp_path):
        filepath = _make_llama_safetensors(tmp_path / "model.safetensors", 0, 3)
        desc = build_shard_descriptor(filepath, model_id="org/model")
        assert "org_model" in desc.shard_id
        assert "L0-3" in desc.shard_id

    def test_custom_shard_id(self, tmp_path):
        filepath = _make_llama_safetensors(tmp_path / "model.safetensors", 0, 3)
        desc = build_shard_descriptor(filepath, model_id="m", shard_id="custom-id")
        assert desc.shard_id == "custom-id"


class TestScanDirectory:
    def test_scan_finds_all_files(self, tmp_path):
        _make_llama_safetensors(tmp_path / "part1.safetensors", 0, 7)
        _make_llama_safetensors(tmp_path / "part2.safetensors", 8, 15)
        descriptors = scan_shard_directory(tmp_path, model_id="test/model")
        assert len(descriptors) == 2
        # Sorted by layer range
        assert descriptors[0].layer_range[0] <= descriptors[1].layer_range[0]

    def test_scan_skips_non_safetensors(self, tmp_path):
        _make_llama_safetensors(tmp_path / "model.safetensors", 0, 3)
        (tmp_path / "readme.txt").write_text("not a shard")
        descriptors = scan_shard_directory(tmp_path, model_id="test/model")
        assert len(descriptors) == 1

    def test_scan_empty_directory(self, tmp_path):
        descriptors = scan_shard_directory(tmp_path, model_id="test/model")
        assert descriptors == []


class TestVerifyIntegrity:
    def test_valid_file(self, tmp_path):
        filepath = _make_llama_safetensors(tmp_path / "model.safetensors", 0, 3)
        checksum = hash_file(filepath)
        assert verify_shard_integrity(filepath, checksum)

    def test_corrupted_file(self, tmp_path):
        filepath = _make_llama_safetensors(tmp_path / "model.safetensors", 0, 3)
        checksum = hash_file(filepath)
        # Corrupt the file
        with open(filepath, "r+b") as f:
            f.seek(100)
            f.write(b"\xff\xff\xff\xff")
        assert not verify_shard_integrity(filepath, checksum)


class TestDtypeMapping:
    def test_common_dtypes(self):
        assert _safetensors_dtype_to_precision("F16") == "fp16"
        assert _safetensors_dtype_to_precision("BF16") == "bf16"
        assert _safetensors_dtype_to_precision("F32") == "fp32"
        assert _safetensors_dtype_to_precision("I8") == "int8"

    def test_unknown_dtype(self):
        assert _safetensors_dtype_to_precision("WEIRD") == "weird"
