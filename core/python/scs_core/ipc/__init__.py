"""JSON-RPC command dispatching layer for SCS Core."""

from scs_core.ipc.dispatcher import SCSDispatcher

# Alias for specification consistency
JsonRpcDispatcher = SCSDispatcher

__all__ = ["SCSDispatcher", "JsonRpcDispatcher"]
