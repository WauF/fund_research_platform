"""Routine tests must not reach the internet (pytest-socket config in pyproject.toml).

If this fails, someone removed the --allow-hosts guard and tests could silently call a live
LLM or market-data API. Live calls belong in evaluations/.
"""

import socket

import pytest
from pytest_socket import SocketConnectBlockedError


@pytest.mark.filterwarnings("ignore:A test tried to use socket:UserWarning")
def test_internet_is_blocked() -> None:
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(("1.1.1.1", 443), timeout=1)


def test_localhost_is_allowed() -> None:
    with socket.create_server(("127.0.0.1", 0)) as server:
        port = server.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
