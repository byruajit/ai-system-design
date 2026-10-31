"""
Ep 6 demo — Northwind "card servicing" MCP server.

Design points shown in code:
  * READ tools and WRITE tools are separate, and named so the risk is obvious
  * every tool is scoped to the session's customer (no account_id the user didn't authenticate for)
  * write tools never execute directly: they create a PENDING action that a human approves
  * every call is written to an audit log

Run (stdio):    python servicing_mcp_server.py
Inspect:        npx @modelcontextprotocol/inspector python servicing_mcp_server.py

Works with the MCP Python SDK v2 (MCPServer) and v1 (FastMCP).
"""
from __future__ import annotations

import json
import time
import uuid

try:                                    # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:                     # MCP Python SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

server = _Server("northwind-card-servicing")

# ---- fake systems of record (synthetic) ------------------------------------
SESSION = {"customer_id": "C-88213", "agent_id": "cc-agent-17", "channel": "contact-centre"}
CARDS = {"C-88213": [{"card_id": "4111-XXXX-XXXX-2231", "status": "active", "type": "debit"}],
         "C-10007": [{"card_id": "4111-XXXX-XXXX-9054", "status": "active", "type": "debit"}]}
TXNS = {"C-88213": [{"id": "T1", "date": "2026-11-28", "merchant": "QuickMart Online", "amount_inr": 18450},
                    {"id": "T2", "date": "2026-11-29", "merchant": "Metro Fuel", "amount_inr": 3200}]}
PENDING: dict[str, dict] = {}
AUDIT: list[dict] = []


def _audit(tool: str, args: dict, outcome: str) -> None:
    AUDIT.append({"ts": time.time(), "session": SESSION, "tool": tool, "args": args, "outcome": outcome})


def _own(card_id: str) -> bool:
    return any(c["card_id"] == card_id for c in CARDS.get(SESSION["customer_id"], []))


# ---- READ tools --------------------------------------------------------------
@server.tool()
def get_my_cards() -> str:
    """READ. List cards of the customer verified in this session."""
    _audit("get_my_cards", {}, "ok")
    return json.dumps(CARDS.get(SESSION["customer_id"], []))


@server.tool()
def get_recent_transactions(days: int = 7) -> str:
    """READ. Recent card transactions for the verified customer (max 30 days)."""
    days = min(max(days, 1), 30)
    _audit("get_recent_transactions", {"days": days}, "ok")
    return json.dumps(TXNS.get(SESSION["customer_id"], []))


# ---- WRITE tools (approval-gated) ----------------------------------------------
@server.tool()
def request_card_block(card_id: str, reason: str) -> str:
    """WRITE (needs human approval). Request a block on one of the verified customer's cards."""
    if not _own(card_id):
        _audit("request_card_block", {"card_id": card_id}, "DENIED_not_owner")
        return json.dumps({"error": "card does not belong to the verified customer"})
    action_id = f"A-{uuid.uuid4().hex[:6]}"
    PENDING[action_id] = {"type": "block_card", "card_id": card_id, "reason": reason, "status": "PENDING_APPROVAL"}
    _audit("request_card_block", {"card_id": card_id, "reason": reason}, f"PENDING {action_id}")
    return json.dumps({"action_id": action_id, "status": "PENDING_APPROVAL",
                       "message": "A human agent must approve this action."})


@server.tool()
def request_dispute(transaction_id: str, reason: str) -> str:
    """WRITE (needs human approval). Raise a debit card dispute (POL-OPS-301: within 90 days)."""
    if transaction_id not in {t["id"] for t in TXNS.get(SESSION["customer_id"], [])}:
        _audit("request_dispute", {"transaction_id": transaction_id}, "DENIED_unknown_txn")
        return json.dumps({"error": "transaction not found for the verified customer"})
    action_id = f"A-{uuid.uuid4().hex[:6]}"
    PENDING[action_id] = {"type": "dispute", "transaction_id": transaction_id, "reason": reason, "status": "PENDING_APPROVAL"}
    _audit("request_dispute", {"transaction_id": transaction_id}, f"PENDING {action_id}")
    return json.dumps({"action_id": action_id, "status": "PENDING_APPROVAL"})


# Deliberately NOT exposed as a tool: issue_refund. Money movement stays in the
# core-banking workflow with maker-checker, not in the agent's hands.

if __name__ == "__main__":
    server.run()
