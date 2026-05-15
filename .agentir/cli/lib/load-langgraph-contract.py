#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from pathlib import Path

from langgraph_contract_emit import (
    ContractEmitProviderRuntimeError,
    contract_to_dict,
    prepare_contract_emit_environment,
)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: load-langgraph-contract.py <repo-root> <module-path> <symbol>"
        )

    repo_root = Path(sys.argv[1]).resolve()
    module_path = Path(sys.argv[2]).resolve()
    symbol = sys.argv[3].strip()

    if not symbol:
        raise RuntimeError("LangGraph contract loading requires an explicit symbol.")

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    prepare_contract_emit_environment()
    spec = importlib.util.spec_from_file_location("agentir_compile_target", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import module from '{module_path}'.")

    module = importlib.util.module_from_spec(spec)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            spec.loader.exec_module(module)
            if not hasattr(module, symbol):
                raise RuntimeError(
                    f"Module '{module_path.relative_to(repo_root)}' does not define '{symbol}'."
                )
            payload = contract_to_dict(getattr(module, symbol))
    except ContractEmitProviderRuntimeError as error:
        raise RuntimeError(
            f"Contract emission for '{module_path.relative_to(repo_root)}' cannot execute provider calls at import time: {error}"
        ) from error

    print(json.dumps(payload))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
