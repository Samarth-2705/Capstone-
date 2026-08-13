"""
deploy.py
=========
Deploys DataProvenancePro.sol to Ganache or Sepolia.
Run this ONCE from the web_app/ folder before starting server.py.

Usage
-----
    # Ganache (default)
    cd web_app/
    python deploy.py

    # Sepolia
    python deploy.py --network sepolia \
        --rpc https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY \
        --owner-key 0xYOUR_PRIVATE_KEY

Output
------
    web_app/abi.json               loaded by blockchain_utils.py
    web_app/contract_address.txt   loaded by blockchain_utils.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from web3 import Web3
from solcx import compile_source, install_solc

HERE          = Path(__file__).resolve().parent
SOL_FILE      = HERE / "DataProvenancePro.sol"
ABI_FILE      = HERE / "abi.json"
ADDR_FILE     = HERE / "contract_address.txt"
SOLC_VERSION  = "0.8.7"


def load_source() -> str:
    if not SOL_FILE.exists():
        print(f"[ERROR] {SOL_FILE} not found.")
        sys.exit(1)
    return SOL_FILE.read_text()


def compile_contract(source: str):
    print(f"[1/5] Installing solc {SOLC_VERSION} …")
    install_solc(SOLC_VERSION)
    print("[2/5] Compiling DataProvenancePro.sol …")
    compiled = compile_source(source, solc_version=SOLC_VERSION)
    _, interface = compiled.popitem()
    return interface["abi"], interface["bin"]


def deploy_ganache(w3: Web3, abi: list, bytecode: str):
    owner    = w3.eth.accounts[0]
    Contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    print(f"[4/5] Deploying from {owner} …")
    tx_hash  = Contract.constructor().transact({"from": owner})
    receipt  = w3.eth.wait_for_transaction_receipt(tx_hash)
    address  = receipt.contractAddress
    print(f"      Contract deployed at: {address}")
    print(f"      Gas used: {receipt.gasUsed:,}")

    # Grant accounts[1] ML role, accounts[2] Researcher role automatically
    contract = w3.eth.contract(address=address, abi=abi)
    if len(w3.eth.accounts) > 1:
        tx = contract.functions.grantMLSystem(w3.eth.accounts[1]).transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx)
        print(f"      isMLSystem  → {w3.eth.accounts[1]}")
    if len(w3.eth.accounts) > 2:
        tx = contract.functions.grantResearcher(w3.eth.accounts[2]).transact({"from": owner})
        w3.eth.wait_for_transaction_receipt(tx)
        print(f"      isResearcher → {w3.eth.accounts[2]}")

    return address


def deploy_sepolia(w3: Web3, abi: list, bytecode: str, deployer: str, pk: str):
    Contract  = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce     = w3.eth.get_transaction_count(deployer)
    tx        = Contract.constructor().build_transaction({
        "from": deployer, "nonce": nonce,
        "gasPrice": w3.eth.gas_price, "gas": 3_000_000,
    })
    signed    = w3.eth.account.sign_transaction(tx, pk)
    tx_hash   = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"[4/5] Tx sent: {tx_hash.hex()}")
    receipt   = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    address   = receipt.contractAddress
    print(f"      Contract deployed at: {address}")
    print(f"      Etherscan: https://sepolia.etherscan.io/address/{address}")
    return address


def save(abi: list, address: str):
    ABI_FILE.write_text(json.dumps(abi, indent=2))
    ADDR_FILE.write_text(address)
    print(f"\n      Saved: {ABI_FILE}")
    print(f"      Saved: {ADDR_FILE}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--network",   default="ganache",
                        choices=["ganache", "sepolia"])
    parser.add_argument("--rpc",       default="http://127.0.0.1:7545")
    parser.add_argument("--owner-key", default=None)
    args = parser.parse_args()

    print("\n╔══════════════════════════════════════╗")
    print("║  DataProvenancePro — Deploy Script  ║")
    print("╚══════════════════════════════════════╝\n")

    source       = load_source()
    abi, bytecode = compile_contract(source)

    print(f"[3/5] Connecting to {args.rpc} …")
    w3 = Web3(Web3.HTTPProvider(args.rpc))
    if not w3.is_connected():
        print(f"[ERROR] Cannot connect to {args.rpc}")
        sys.exit(1)
    print(f"      Connected — chain ID: {w3.eth.chain_id}")

    if args.network == "ganache":
        address = deploy_ganache(w3, abi, bytecode)
    else:
        if not args.owner_key:
            print("[ERROR] --owner-key required for Sepolia.")
            sys.exit(1)
        deployer = w3.eth.account.from_key(args.owner_key).address
        print(f"      Deployer: {deployer}")
        address  = deploy_sepolia(w3, abi, bytecode, deployer, args.owner_key)

    save(abi, address)
    print(f"\n[5/5] Done.  Contract: {address}\n")


if __name__ == "__main__":
    main()
