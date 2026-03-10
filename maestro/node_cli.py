"""
Node CLI — Command-line interface for storage node operators.

Usage:
    python -m maestro.node_cli setup   --model meta-llama/Llama-3.3-70B-Instruct --layers 0-15
    python -m maestro.node_cli start   --port 8001 --orchestrator http://localhost:8080
    python -m maestro.node_cli status
    python -m maestro.node_cli verify  --model meta-llama/Llama-3.3-70B-Instruct
    python -m maestro.node_cli shards

This is the primary tool for people who want to run a storage node and
contribute weight shards to the Maestro network.
"""

import argparse
import json
import os
import sys
import uuid
from pathlib import Path


def cmd_setup(args):
    """Download model shards and generate node config."""
    from maestro.shard_manager import ShardManager

    manager = ShardManager(shard_dir=args.shard_dir)

    print(f"\n  Maestro Storage Node Setup")
    print(f"  {'=' * 40}")
    print(f"  Model:  {args.model}")

    layer_start = 0
    layer_end = -1
    if args.layers:
        parts = args.layers.split("-")
        layer_start = int(parts[0])
        layer_end = int(parts[1]) if len(parts) > 1 else layer_start
        print(f"  Layers: {layer_start}-{layer_end}")
    else:
        print(f"  Layers: all")

    token = args.token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        print(f"  Auth:   token provided")
    else:
        print(f"  Auth:   none (public models only)")

    print()

    # Download
    print("  Downloading shards...")
    try:
        downloaded = manager.download_model_shards(
            model_id=args.model,
            layer_start=layer_start,
            layer_end=layer_end,
            token=token,
        )
        print(f"\n  Downloaded {len(downloaded)} file(s)")
    except ImportError as e:
        print(f"\n  Error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n  Error: {e}")
        sys.exit(1)

    # Generate node config
    node_id = args.node_id or f"node-{uuid.uuid4().hex[:8]}"
    config_path = Path(args.config or "data/node_shards.json")

    shard_config = manager.generate_shard_config(
        model_id=args.model,
        layer_start=layer_start if args.layers else None,
        layer_end=layer_end if args.layers else None,
        output_path=config_path,
    )

    print(f"  Generated config: {config_path} ({len(shard_config)} shard(s))")

    # Show summary
    manifest = manager.load_manifest(args.model)
    if manifest:
        print(f"\n  Summary:")
        print(f"    Total layers: {manifest.total_layers}")
        print(f"    Coverage:     {manifest.layer_coverage}")
        print(f"    Precision:    {manifest.precision}")
        print(f"    Size:         {manifest.total_size_bytes / (1024**3):.2f} GB")
        print(f"    Complete:     {'yes' if manifest.complete else 'no'}")

    print(f"\n  Node ID: {node_id}")
    print(f"\n  To start the node:")
    print(f"    MAESTRO_NODE_ID={node_id} \\")
    print(f"    MAESTRO_SHARD_CONFIG={config_path} \\")
    print(f"    uvicorn maestro.node_server:app --host 0.0.0.0 --port 8001")
    print()


def cmd_start(args):
    """Start the storage node server."""
    import uvicorn

    node_id = args.node_id or os.environ.get("MAESTRO_NODE_ID", f"node-{uuid.uuid4().hex[:8]}")
    config_path = args.config or os.environ.get("MAESTRO_SHARD_CONFIG", "data/node_shards.json")

    # Set environment variables for the node server
    os.environ["MAESTRO_NODE_ID"] = node_id
    os.environ["MAESTRO_SHARD_CONFIG"] = config_path
    os.environ["MAESTRO_NODE_PORT"] = str(args.port)
    os.environ["MAESTRO_NODE_HOST"] = args.host

    if args.orchestrator:
        os.environ["MAESTRO_ORCHESTRATOR_URL"] = args.orchestrator

    if args.advertised_host:
        os.environ["MAESTRO_ADVERTISED_HOST"] = args.advertised_host

    print(f"\n  Starting Maestro Storage Node")
    print(f"  {'=' * 40}")
    print(f"  Node ID:      {node_id}")
    print(f"  Config:       {config_path}")
    print(f"  Listen:       {args.host}:{args.port}")
    if args.orchestrator:
        print(f"  Orchestrator: {args.orchestrator}")
    if args.advertised_host:
        print(f"  Advertised:   {args.advertised_host}:{args.port}")
    print()

    uvicorn.run(
        "maestro.node_server:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )


def cmd_status(args):
    """Show status of local shards."""
    from maestro.shard_manager import ShardManager

    manager = ShardManager(shard_dir=args.shard_dir)
    models = manager.list_models()

    if not models:
        print("\n  No models found. Run 'setup' to download shards.\n")
        return

    print(f"\n  Local Shard Inventory")
    print(f"  {'=' * 50}")

    for model_id in models:
        manifest = manager.load_manifest(model_id)
        usage = manager.disk_usage(model_id)

        print(f"\n  {model_id}")
        if manifest:
            print(f"    Layers:    {manifest.total_layers} total")
            print(f"    Coverage:  {manifest.layer_coverage}")
            print(f"    Precision: {manifest.precision}")
            print(f"    Complete:  {'yes' if manifest.complete else 'no'}")
        print(f"    Files:     {usage['files']}")
        print(f"    Size:      {usage['total_gb']} GB")

    # Total
    total = manager.disk_usage()
    print(f"\n  {'─' * 50}")
    print(f"  Total: {total['total_files']} file(s), {total['total_gb']} GB\n")


def cmd_verify(args):
    """Verify integrity of local shards."""
    from maestro.shard_manager import ShardManager

    manager = ShardManager(shard_dir=args.shard_dir)
    models = [args.model] if args.model else manager.list_models()

    if not models:
        print("\n  No models found.\n")
        return

    print(f"\n  Verifying shard integrity...")

    all_ok = True
    for model_id in models:
        print(f"\n  {model_id}:")
        results = manager.verify_all(model_id)

        for f in results["passed"]:
            print(f"    [ok]      {f}")
        for f in results["failed"]:
            print(f"    [FAILED]  {f}")
            all_ok = False
        for f in results["missing"]:
            print(f"    [MISSING] {f}")
            all_ok = False

    print()
    if all_ok:
        print("  All shards verified.\n")
    else:
        print("  Some shards have issues. Re-run setup to re-download.\n")
        sys.exit(1)


def cmd_shards(args):
    """List shard details (what a node would serve)."""
    config_path = Path(args.config or "data/node_shards.json")

    if not config_path.exists():
        print(f"\n  No shard config found at {config_path}")
        print(f"  Run 'setup' first.\n")
        return

    with open(config_path) as f:
        config = json.load(f)

    print(f"\n  Node Shard Config: {config_path}")
    print(f"  {'=' * 50}")

    for shard in config:
        layer_range = shard.get("layer_range", [-1, -1])
        filepath = shard.get("filepath", "")
        on_disk = os.path.exists(filepath) if filepath else False

        print(f"\n  Shard: {shard.get('shard_id', 'unknown')}")
        print(f"    Model:     {shard.get('model_id', '')}")
        print(f"    Layers:    {layer_range[0]}-{layer_range[1]}")
        print(f"    Precision: {shard.get('precision', 'unknown')}")
        print(f"    Format:    {shard.get('shard_format', 'unknown')}")
        print(f"    Size:      {shard.get('size_bytes', 0) / (1024**3):.2f} GB")
        print(f"    On disk:   {'yes' if on_disk else 'NO'}")

    print(f"\n  Total: {len(config)} shard(s)\n")


def main():
    parser = argparse.ArgumentParser(
        prog="maestro-node",
        description="Maestro Storage Node — manage weight shards and run a node",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # --- setup ---
    p_setup = subparsers.add_parser("setup", help="Download model shards and generate config")
    p_setup.add_argument("--model", "-m", required=True, help="HuggingFace model ID")
    p_setup.add_argument("--layers", "-l", help="Layer range (e.g., 0-15)")
    p_setup.add_argument("--token", help="HuggingFace auth token")
    p_setup.add_argument("--node-id", help="Node ID (auto-generated if not set)")
    p_setup.add_argument("--config", help="Output config path (default: data/node_shards.json)")
    p_setup.add_argument("--shard-dir", help="Shard storage directory")

    # --- start ---
    p_start = subparsers.add_parser("start", help="Start the storage node server")
    p_start.add_argument("--port", "-p", type=int, default=8001, help="Listen port")
    p_start.add_argument("--host", default="0.0.0.0", help="Listen host")
    p_start.add_argument("--node-id", help="Node ID")
    p_start.add_argument("--config", help="Shard config path")
    p_start.add_argument("--orchestrator", "-o", help="Orchestrator URL for auto-registration")
    p_start.add_argument("--advertised-host", help="Host the orchestrator uses to reach this node")

    # --- status ---
    p_status = subparsers.add_parser("status", help="Show local shard inventory")
    p_status.add_argument("--shard-dir", help="Shard storage directory")

    # --- verify ---
    p_verify = subparsers.add_parser("verify", help="Verify shard integrity")
    p_verify.add_argument("--model", "-m", help="Model to verify (all if not set)")
    p_verify.add_argument("--shard-dir", help="Shard storage directory")

    # --- shards ---
    p_shards = subparsers.add_parser("shards", help="Show node shard config")
    p_shards.add_argument("--config", help="Config path (default: data/node_shards.json)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "setup": cmd_setup,
        "start": cmd_start,
        "status": cmd_status,
        "verify": cmd_verify,
        "shards": cmd_shards,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
