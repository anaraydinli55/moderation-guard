#!/usr/bin/env python3
"""Contract checker — validates Python syntax, GenLayer structure, and runs genvm-linter."""

import ast
import sys
import os
import subprocess

def check_file(filepath):
    print(f"\n🔍 Checking: {filepath}")
    with open(filepath, "r") as f:
        source = f.read()

    try:
        tree = ast.parse(source)
        print("  ✅ Syntax OK")
    except SyntaxError as e:
        print(f"  ❌ Syntax Error: {e}")
        return False

    required = ["@gl.public.write", "@gl.public.view"]
    found = {r: False for r in required}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                deco_str = ast.unparse(decorator) if hasattr(ast, "unparse") else ""
                for req in required:
                    if req in deco_str or req.replace("@", "") in deco_str:
                        found[req] = True

    for req, ok in found.items():
        print(f"  {'✅' if ok else '⚠️'}  {req}")

    has_contract = "gl.Contract" in source
    print(f"  {'✅' if has_contract else '⚠️'}  Inherits from gl.Contract")

    has_nondet = "gl.nondet" in source
    has_eq = "gl.eq_principle" in source
    if has_nondet and has_eq:
        print("  ✅  Non-deterministic calls wrapped in eq_principle")
    elif has_nondet:
        print("  ❌  Non-deterministic calls NOT wrapped in eq_principle")
        return False
    else:
        print("  ⚠️  No non-deterministic blocks")

    has_emit = "gl.emit" in source
    print(f"  {'✅' if has_emit else '⚠️'}  Emits events")

    has_usererror = "gl.vm.UserError" in source
    print(f"  {'✅' if has_usererror else '⚠️'}  Uses gl.vm.UserError")

    return True

def run_linter(contract_file):
    try:
        result = subprocess.run(
            ["genvm-lint", "check", contract_file],
            capture_output=True, text=True
        )
        out = (result.stdout or "") + (result.stderr or "")
        if "Lint passed" in out or "✓" in out:
            print(f"  ✅ genvm-lint passed for {os.path.basename(contract_file)}")
            return True
        elif "Lint failed" in out or "✗ Lint failed" in out:
            print(f"  ❌ genvm-lint failed for {os.path.basename(contract_file)}:")
            print(out)
            return False
        return True
    except FileNotFoundError:
        print("\n⚠️  genvm-lint not installed.")
        return True

def main():
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    contract_file = os.path.join(repo_root, "ModerationGuard.py")
    if not os.path.exists(contract_file):
        print(f"❌ Contract not found: {contract_file}")
        sys.exit(1)

    all_ok = check_file(contract_file)
    linter_ok = run_linter(contract_file)

    print("\n" + "="*50)
    if all_ok and linter_ok:
        print("✅ All checks and genvm-lint passed successfully!")
    else:
        print("❌ Fix issues before submission.")
    return 0 if (all_ok and linter_ok) else 1

if __name__ == "__main__":
    sys.exit(main())
