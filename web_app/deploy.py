"""
deploy.py
=========
Deploys DataProvenancePro.sol to Ganache or Sepolia.

Run this ONCE from the web_app/ folder before starting server.py.

Usage
-----
    # Ganache
    cd web_app
    python deploy.py

    # Sepolia
    python deploy.py --network sepolia \
        --rpc https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY \
        --owner-key 0xYOUR_PRIVATE_KEY

Output
------
    web_app/abi.json
    web_app/contract_address.txt
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from web3 import Web3
from solcx import compile_source


# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve().parent

SOL_FILE = HERE / "DataProvenancePro.sol"
ABI_FILE = HERE / "abi.json"
ADDR_FILE = HERE / "contract_address.txt"


# ─────────────────────────────────────────────────────────────────────────────
# SOLIDITY CONFIG
# ─────────────────────────────────────────────────────────────────────────────

# Your contract says:
#
#     pragma solidity ^0.8.7;
#
# Therefore Solidity 0.8.36 is valid.
SOLC_VERSION = "0.8.36"

# Optimize the contract to reduce bytecode size and deployment gas.
OPTIMIZER_ENABLED = True
OPTIMIZER_RUNS = 200

# Explicitly target an EVM version supported by modern Ganache.
EVM_VERSION = "paris"

# Deployment gas limit.
# We will first try to estimate the actual requirement.
# This is only a safety ceiling.
DEPLOY_GAS_LIMIT = 8_000_000


# ─────────────────────────────────────────────────────────────────────────────
# FIND SOLC
# ─────────────────────────────────────────────────────────────────────────────

def find_solc() -> str:
    """
    Find the system-installed Solidity compiler.

    On Apple Silicon with Homebrew this is normally:

        /opt/homebrew/bin/solc
    """

    solc_path = shutil.which("solc")

    if not solc_path:
        print("[ERROR] Solidity compiler 'solc' was not found.")
        print()
        print("Install it with:")
        print("    brew install solidity")
        print()
        print("Then verify:")
        print("    solc --version")
        sys.exit(1)

    return solc_path


# ─────────────────────────────────────────────────────────────────────────────
# VERIFY SOLC
# ─────────────────────────────────────────────────────────────────────────────

def verify_solc(solc_path: str) -> None:
    """
    Verify that solc is executable and report its version.
    """

    try:
        result = subprocess.run(
            [solc_path, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )

    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[ERROR] Could not execute solc: {exc}")
        sys.exit(1)

    print("[1/5] Using system Solidity compiler …")
    print(f"      Path: {solc_path}")

    version_line = next(
        (
            line.strip()
            for line in result.stdout.splitlines()
            if "Version:" in line
        ),
        "Unknown version",
    )

    print(f"      {version_line}")
    print(f"      EVM target: {EVM_VERSION}")
    print(
        f"      Optimizer: "
        f"{'enabled' if OPTIMIZER_ENABLED else 'disabled'} "
        f"(runs={OPTIMIZER_RUNS})"
    )

    if "0.8." not in version_line:
        print()
        print("[ERROR] This project requires Solidity 0.8.x.")
        print(f"       Detected: {version_line}")
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# LOAD CONTRACT
# ─────────────────────────────────────────────────────────────────────────────

def load_source() -> str:
    """
    Load DataProvenancePro.sol.
    """

    if not SOL_FILE.exists():
        print(f"[ERROR] {SOL_FILE} not found.")
        sys.exit(1)

    return SOL_FILE.read_text()


# ─────────────────────────────────────────────────────────────────────────────
# COMPILE
# ─────────────────────────────────────────────────────────────────────────────

def compile_contract(source: str):
    """
    Compile DataProvenancePro.sol using the locally installed
    Homebrew Solidity compiler.

    No internet connection is required.
    """

    solc_path = find_solc()
    verify_solc(solc_path)

    print("[2/5] Compiling DataProvenancePro.sol …")

    try:
        compiled = compile_source(
            source,
            solc_binary=solc_path,

            # IMPORTANT:
            # Optimization reduces deployment bytecode and gas.
            optimize=OPTIMIZER_ENABLED,
            optimize_runs=OPTIMIZER_RUNS,

            # Explicit EVM target.
            evm_version=EVM_VERSION,
        )

    except Exception as exc:
        print()
        print("[ERROR] Solidity compilation failed.")
        print()
        print(str(exc))
        sys.exit(1)

    if not compiled:
        print("[ERROR] Solidity compiler returned no contract.")
        sys.exit(1)

    # Find the actual contract explicitly.
    contract_key = None

    for key in compiled:
        if key.endswith(":DataProvenancePro"):
            contract_key = key
            break

    if contract_key is None:
        print("[ERROR] DataProvenancePro contract was not found.")
        print(f"       Compiled contracts: {list(compiled.keys())}")
        sys.exit(1)

    interface = compiled[contract_key]

    abi = interface["abi"]
    bytecode = interface["bin"]

    if not bytecode:
        print("[ERROR] Compiler produced empty bytecode.")
        sys.exit(1)

    print(f"      Contract: DataProvenancePro")
    print(f"      Bytecode: {len(bytecode) // 2:,} bytes")

    return abi, bytecode


# ─────────────────────────────────────────────────────────────────────────────
# DEPLOY TO GANACHE
# ─────────────────────────────────────────────────────────────────────────────

def deploy_ganache(
    w3: Web3,
    abi: list,
    bytecode: str,
):
    """
    Deploy DataProvenancePro to local Ganache.
    """

    accounts = w3.eth.accounts

    if not accounts:
        print("[ERROR] Ganache returned no accounts.")
        sys.exit(1)

    owner = accounts[0]

    print(f"[4/5] Deploying from {owner} …")

    Contract = w3.eth.contract(
        abi=abi,
        bytecode=bytecode,
    )

    # ─────────────────────────────────────────────────────────────────────
    # Build deployment transaction
    # ─────────────────────────────────────────────────────────────────────

    try:
        deployment_tx = Contract.constructor().build_transaction(
            {
                "from": owner,
                "gas": DEPLOY_GAS_LIMIT,
                "gasPrice": w3.eth.gas_price,
            }
        )

    except Exception as exc:
        print()
        print("[ERROR] Could not build deployment transaction.")
        print(exc)
        sys.exit(1)

    # ─────────────────────────────────────────────────────────────────────
    # Estimate deployment gas
    # ─────────────────────────────────────────────────────────────────────

    try:
        estimated_gas = w3.eth.estimate_gas(
            deployment_tx
        )

        print(f"      Estimated deployment gas: {estimated_gas:,}")
        print(f"      Gas limit: {DEPLOY_GAS_LIMIT:,}")

    except Exception as exc:
        print()
        print("[WARNING] Ganache could not estimate deployment gas.")
        print(f"          {exc}")
        print()
        print(
            "          Continuing with the configured "
            f"gas limit of {DEPLOY_GAS_LIMIT:,}."
        )

    # ─────────────────────────────────────────────────────────────────────
    # Send deployment transaction
    # ─────────────────────────────────────────────────────────────────────

    try:
        tx_hash = w3.eth.send_transaction(
            deployment_tx
        )

        print(f"      Deployment transaction: {tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=120,
        )

    except Exception as exc:
        print()
        print("[ERROR] Contract deployment transaction failed.")
        print()
        print(exc)
        sys.exit(1)

    # ─────────────────────────────────────────────────────────────────────
    # Check receipt
    # ─────────────────────────────────────────────────────────────────────

    if receipt.status != 1:
        print()
        print("[ERROR] Contract deployment transaction reverted.")
        print(f"       Transaction: {tx_hash.hex()}")
        print(f"       Gas used: {receipt.gasUsed:,}")
        print(f"       Gas limit: {DEPLOY_GAS_LIMIT:,}")
        print()
        print("Possible causes:")
        print("  1. Ganache block gas limit is too low.")
        print("  2. Contract deployment bytecode is too expensive.")
        print("  3. Ganache EVM configuration is incompatible.")
        print()
        print(
            "Try restarting Ganache with a larger block gas limit:"
        )
        print()
        print(
            "    ganache --port 7545 --chain.chainId 1337 "
            "--miner.blockGasLimit 12000000"
        )
        print()
        sys.exit(1)

    address = receipt.contractAddress

    if not address:
        print()
        print("[ERROR] Deployment succeeded but no contract address "
              "was returned.")
        sys.exit(1)

    print(f"      Contract deployed at: {address}")
    print(f"      Gas used: {receipt.gasUsed:,}")

    # ─────────────────────────────────────────────────────────────────────
    # Grant ML role to accounts[1]
    # ─────────────────────────────────────────────────────────────────────

    contract = w3.eth.contract(
        address=address,
        abi=abi,
    )

    if len(accounts) > 1:

        print()
        print("      Granting ML System role …")

        try:
            tx = contract.functions.grantMLSystem(
                accounts[1]
            ).transact(
                {
                    "from": owner,
                    "gas": 500_000,
                }
            )

            receipt_role = w3.eth.wait_for_transaction_receipt(
                tx,
                timeout=120,
            )

            if receipt_role.status != 1:
                raise RuntimeError(
                    "grantMLSystem transaction reverted"
                )

            print(
                f"      isMLSystem  → {accounts[1]}"
            )

        except Exception as exc:
            print(
                f"      [WARNING] Could not grant ML role: {exc}"
            )

    # ─────────────────────────────────────────────────────────────────────
    # Grant Researcher role to accounts[2]
    # ─────────────────────────────────────────────────────────────────────

    if len(accounts) > 2:

        print()
        print("      Granting Researcher role …")

        try:
            tx = contract.functions.grantResearcher(
                accounts[2]
            ).transact(
                {
                    "from": owner,
                    "gas": 500_000,
                }
            )

            receipt_role = w3.eth.wait_for_transaction_receipt(
                tx,
                timeout=120,
            )

            if receipt_role.status != 1:
                raise RuntimeError(
                    "grantResearcher transaction reverted"
                )

            print(
                f"      isResearcher → {accounts[2]}"
            )

        except Exception as exc:
            print(
                f"      [WARNING] Could not grant Researcher role: {exc}"
            )

    return address


# ─────────────────────────────────────────────────────────────────────────────
# DEPLOY TO SEPOLIA
# ─────────────────────────────────────────────────────────────────────────────

def deploy_sepolia(
    w3: Web3,
    abi: list,
    bytecode: str,
    deployer: str,
    pk: str,
):
    """
    Deploy DataProvenancePro to Ethereum Sepolia.
    """

    Contract = w3.eth.contract(
        abi=abi,
        bytecode=bytecode,
    )

    nonce = w3.eth.get_transaction_count(
        deployer,
        "pending",
    )

    # Try to estimate deployment gas first.
    try:
        estimated_gas = Contract.constructor().estimate_gas(
            {
                "from": deployer,
            }
        )

        print(
            f"      Estimated deployment gas: "
            f"{estimated_gas:,}"
        )

        gas_limit = int(estimated_gas * 1.20)

    except Exception as exc:
        print(
            f"      [WARNING] Gas estimation failed: {exc}"
        )

        gas_limit = DEPLOY_GAS_LIMIT

    tx = Contract.constructor().build_transaction(
        {
            "from": deployer,
            "nonce": nonce,
            "gasPrice": w3.eth.gas_price,
            "gas": gas_limit,
        }
    )

    signed = w3.eth.account.sign_transaction(
        tx,
        pk,
    )

    tx_hash = w3.eth.send_raw_transaction(
        signed.raw_transaction
    )

    print(f"[4/5] Tx sent: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(
        tx_hash,
        timeout=180,
    )

    if receipt.status != 1:
        print()
        print("[ERROR] Sepolia deployment transaction reverted.")
        print(f"       Transaction: {tx_hash.hex()}")
        print(f"       Gas used: {receipt.gasUsed:,}")
        sys.exit(1)

    address = receipt.contractAddress

    print(f"      Contract deployed at: {address}")
    print(
        f"      Etherscan: "
        f"https://sepolia.etherscan.io/address/{address}"
    )

    return address


# ─────────────────────────────────────────────────────────────────────────────
# SAVE ABI + ADDRESS
# ─────────────────────────────────────────────────────────────────────────────

def save(
    abi: list,
    address: str,
):
    """
    Save ABI and deployed contract address.
    """

    ABI_FILE.write_text(
        json.dumps(
            abi,
            indent=2,
        )
    )

    ADDR_FILE.write_text(
        address
    )

    print()
    print(f"      Saved: {ABI_FILE}")
    print(f"      Saved: {ADDR_FILE}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--network",
        default="ganache",
        choices=[
            "ganache",
            "sepolia",
        ],
    )

    parser.add_argument(
        "--rpc",
        default="http://127.0.0.1:7545",
    )

    parser.add_argument(
        "--owner-key",
        default=None,
    )

    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════╗")
    print("║  DataProvenancePro — Deploy Script  ║")
    print("╚══════════════════════════════════════╝")
    print()

    # ─────────────────────────────────────────────────────────────────────
    # Load contract
    # ─────────────────────────────────────────────────────────────────────

    source = load_source()

    # ─────────────────────────────────────────────────────────────────────
    # Compile
    # ─────────────────────────────────────────────────────────────────────

    abi, bytecode = compile_contract(
        source
    )

    # ─────────────────────────────────────────────────────────────────────
    # Connect to blockchain
    # ─────────────────────────────────────────────────────────────────────

    print(
        f"[3/5] Connecting to {args.rpc} …"
    )

    w3 = Web3(
        Web3.HTTPProvider(
            args.rpc,
            request_kwargs={
                "timeout": 30,
            },
        )
    )

    if not w3.is_connected():

        print(
            f"[ERROR] Cannot connect to {args.rpc}"
        )

        print()
        print("For Ganache, start it with:")
        print()
        print(
            "ganache --port 7545 "
            "--chain.chainId 1337 "
            "--miner.blockGasLimit 12000000"
        )

        sys.exit(1)

    print(
        f"      Connected — chain ID: "
        f"{w3.eth.chain_id}"
    )

    # ─────────────────────────────────────────────────────────────────────
    # Deploy
    # ─────────────────────────────────────────────────────────────────────

    if args.network == "ganache":

        address = deploy_ganache(
            w3,
            abi,
            bytecode,
        )

    else:

        if not args.owner_key:
            print(
                "[ERROR] --owner-key required for Sepolia."
            )
            sys.exit(1)

        deployer = w3.eth.account.from_key(
            args.owner_key
        ).address

        print(
            f"      Deployer: {deployer}"
        )

        address = deploy_sepolia(
            w3,
            abi,
            bytecode,
            deployer,
            args.owner_key,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Save
    # ─────────────────────────────────────────────────────────────────────

    save(
        abi,
        address,
    )

    print()
    print(
        f"[5/5] Done. Contract: {address}"
    )
    print()


if __name__ == "__main__":
    main()
