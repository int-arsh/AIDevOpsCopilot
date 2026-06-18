"""Manual test script to verify kubectl and Prometheus tool functions."""

import asyncio
import pprint

from kubectl_tools import get_all_pods, get_crashing_pods, get_node_resources
from prometheus_tools import get_anomalies


def main() -> None:
    """Run manual tests on all tool functions."""
    print("\n" + "=" * 80)
    print("MANUAL TEST: Kubernetes and Prometheus Tools")
    print("=" * 80 + "\n")

    # Test 1: Get all pods
    print("1. GET_ALL_PODS (all namespaces)")
    print("-" * 80)
    result = get_all_pods(namespace="all")
    pprint.pprint(result)
    print()

    # Test 2: Get crashing pods
    print("2. GET_CRASHING_PODS")
    print("-" * 80)
    result = get_crashing_pods()
    pprint.pprint(result)
    print()

    # Test 3: Get node resources
    print("3. GET_NODE_RESOURCES")
    print("-" * 80)
    result = get_node_resources()
    pprint.pprint(result)
    print()

    # Test 4: Get anomalies (async)
    print("4. GET_ANOMALIES (CPU, Memory, Restart Anomalies)")
    print("-" * 80)
    result = asyncio.run(get_anomalies())
    pprint.pprint(result)
    print()

    print("=" * 80)
    print("Manual test completed")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
