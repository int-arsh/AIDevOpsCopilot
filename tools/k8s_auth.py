"""Helpers for deciding how kubectl should authenticate."""

from pathlib import Path
import os


SERVICEACCOUNT_TOKEN_PATH = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")


def is_in_cluster() -> bool:
    """Return True when the process is running inside a Kubernetes pod."""

    return SERVICEACCOUNT_TOKEN_PATH.exists()


def get_kubectl_env() -> dict[str, str]:
    """Return the environment kubectl should inherit for the current runtime."""

    env = os.environ.copy()
    if is_in_cluster():
        env.pop("KUBECONFIG", None)
    return env