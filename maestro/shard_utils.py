"""
Shard Utilities — Low-level tools for working with safetensors weight files.

Provides:
  - Safetensors header parsing (tensor name → byte offset/size mapping)
  - Layer index extraction from tensor names (common transformer conventions)
  - Byte-range SHA-256 hashing for proof-of-storage challenges
  - Shard descriptor generation from actual files on disk
  - File integrity verification via full-file checksums

Designed to work WITHOUT torch or transformers — only needs the safetensors
metadata, not the actual tensor data (unless doing byte-range proofs).
"""

import hashlib
import json
import os
import struct
from pathlib import Path
from typing import Optional

from maestro.storage_proof import ShardDescriptor


def read_safetensors_header(filepath: str | Path) -> dict:
    """
    Parse the safetensors header without loading tensor data.

    Returns a dict mapping tensor names to their metadata:
      {
        "model.layers.0.self_attn.q_proj.weight": {
          "dtype": "F16",
          "shape": [4096, 4096],
          "data_offsets": [0, 33554432]
        },
        ...
        "__metadata__": {"format": "pt", ...}  # optional
      }
    """
    filepath = Path(filepath)
    with open(filepath, "rb") as f:
        # First 8 bytes: little-endian u64 header size
        header_size_bytes = f.read(8)
        if len(header_size_bytes) < 8:
            raise ValueError(f"File too small to be safetensors: {filepath}")
        header_size = struct.unpack("<Q", header_size_bytes)[0]

        if header_size > 100_000_000:  # sanity check: 100MB header max
            raise ValueError(f"Header size {header_size} seems unreasonable: {filepath}")

        header_bytes = f.read(header_size)
        if len(header_bytes) < header_size:
            raise ValueError(f"Truncated header in {filepath}")

    return json.loads(header_bytes)


def extract_layer_indices(header: dict) -> dict[int, list[str]]:
    """
    Group tensor names by their layer index.

    Handles common naming conventions:
      - model.layers.{N}.* (Llama, Mistral, etc.)
      - transformer.h.{N}.* (GPT-2, GPT-J)
      - encoder.layer.{N}.* / decoder.layer.{N}.* (BERT, T5)
      - blk.{N}.* (GGUF-converted models)

    Returns: {layer_index: [tensor_name, ...]}
    Non-layer tensors (embeddings, norms) go under index -1.
    """
    import re
    layer_patterns = [
        re.compile(r"\.layers\.(\d+)\."),
        re.compile(r"\.h\.(\d+)\."),
        re.compile(r"\.layer\.(\d+)\."),
        re.compile(r"blk\.(\d+)\."),
        re.compile(r"\.blocks\.(\d+)\."),
    ]

    layers: dict[int, list[str]] = {}
    for name in header:
        if name == "__metadata__":
            continue

        matched = False
        for pattern in layer_patterns:
            m = pattern.search(name)
            if m:
                idx = int(m.group(1))
                layers.setdefault(idx, []).append(name)
                matched = True
                break

        if not matched:
            # Non-layer tensors: embeddings, final norm, lm_head, etc.
            layers.setdefault(-1, []).append(name)

    return layers


def get_layer_range_from_file(filepath: str | Path) -> tuple[int, int]:
    """
    Determine the layer range covered by a safetensors file.

    Returns (min_layer, max_layer). If no layer tensors found, returns (-1, -1).
    """
    header = read_safetensors_header(filepath)
    layers = extract_layer_indices(header)
    numbered = [k for k in layers if k >= 0]
    if not numbered:
        return (-1, -1)
    return (min(numbered), max(numbered))


def get_tensor_byte_ranges(filepath: str | Path) -> dict[str, tuple[int, int]]:
    """
    Get the absolute byte offsets of each tensor in a safetensors file.

    The data region starts at offset 8 + header_size. Each tensor's
    data_offsets are relative to that data region start.

    Returns: {tensor_name: (absolute_start, absolute_end)}
    """
    filepath = Path(filepath)
    with open(filepath, "rb") as f:
        header_size = struct.unpack("<Q", f.read(8))[0]

    data_start = 8 + header_size
    header = read_safetensors_header(filepath)

    ranges = {}
    for name, meta in header.items():
        if name == "__metadata__":
            continue
        offsets = meta.get("data_offsets", [])
        if len(offsets) == 2:
            ranges[name] = (data_start + offsets[0], data_start + offsets[1])

    return ranges


def hash_byte_range(filepath: str | Path, offset: int, length: int) -> str:
    """
    Compute SHA-256 hash of a specific byte range within a file.

    This is the core primitive for proof-of-replication challenges.
    The orchestrator picks a random offset/length, and the node must
    return the correct hash — proving it actually holds the file.
    """
    filepath = Path(filepath)
    with open(filepath, "rb") as f:
        f.seek(offset)
        data = f.read(length)
    return hashlib.sha256(data).hexdigest()


def hash_file(filepath: str | Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 of an entire file (streaming, memory-efficient)."""
    filepath = Path(filepath)
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_shard_descriptor(
    filepath: str | Path,
    model_id: str,
    model_hash: str = "",
    shard_id: str = "",
    precision: str = "",
) -> ShardDescriptor:
    """
    Build a ShardDescriptor from an actual safetensors file on disk.

    Reads the header to determine layer range, tensor names, and size.
    Computes the file checksum for integrity verification.
    """
    filepath = Path(filepath)
    header = read_safetensors_header(filepath)
    layers = extract_layer_indices(header)
    numbered = [k for k in layers if k >= 0]

    layer_range = (min(numbered), max(numbered)) if numbered else (-1, -1)

    # Gather tensor names (excluding metadata)
    tensor_names = [n for n in header if n != "__metadata__"]

    # Detect precision from metadata or tensor dtype
    if not precision:
        for name, meta in header.items():
            if name == "__metadata__":
                continue
            dtype = meta.get("dtype", "")
            if dtype:
                precision = _safetensors_dtype_to_precision(dtype)
                break

    file_size = filepath.stat().st_size
    checksum = hash_file(filepath)

    if not shard_id:
        shard_id = f"{model_id.replace('/', '_')}__L{layer_range[0]}-{layer_range[1]}"

    return ShardDescriptor(
        shard_id=shard_id,
        model_id=model_id,
        model_hash=model_hash,
        layer_range=layer_range,
        shard_format="safetensors",
        precision=precision,
        size_bytes=file_size,
        tensor_names=tensor_names,
        checksum=checksum,
    )


def _safetensors_dtype_to_precision(dtype: str) -> str:
    """Map safetensors dtype strings to human-readable precision."""
    mapping = {
        "F32": "fp32",
        "F16": "fp16",
        "BF16": "bf16",
        "I8": "int8",
        "I16": "int16",
        "I32": "int32",
        "I64": "int64",
        "U8": "uint8",
        "F8_E4M3": "fp8",
        "F8_E5M2": "fp8",
    }
    return mapping.get(dtype, dtype.lower())


def scan_shard_directory(
    directory: str | Path,
    model_id: str,
    model_hash: str = "",
) -> list[ShardDescriptor]:
    """
    Scan a directory for safetensors files and build descriptors for all of them.

    Returns a list of ShardDescriptors sorted by layer range start.
    """
    directory = Path(directory)
    descriptors = []

    for filepath in sorted(directory.glob("*.safetensors")):
        try:
            desc = build_shard_descriptor(
                filepath, model_id=model_id, model_hash=model_hash
            )
            descriptors.append(desc)
        except (ValueError, OSError, json.JSONDecodeError) as e:
            print(f"[shard_utils] Skipping {filepath.name}: {e}")
            continue

    # Sort by layer range
    descriptors.sort(key=lambda d: d.layer_range[0] if d.layer_range[0] >= 0 else 999)
    return descriptors


def verify_shard_integrity(filepath: str | Path, expected_checksum: str) -> bool:
    """Verify a shard file's integrity against an expected checksum."""
    return hash_file(filepath) == expected_checksum
