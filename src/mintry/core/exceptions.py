"""
Mintry Fabric exception hierarchy.

MintryMandateExceeded inherits from PermissionError to maintain backwards
compatibility with existing code that catches PermissionError, while providing
structured budget attributes for programmatic handling.
"""


class MintryMandateExceeded(PermissionError):
    """Raised when an agent's request is blocked by transport-layer budget constraints.

    Attributes:
        task: The mandate ID or task name that was exceeded.
        cap: The budget ceiling (max_usd) for the mandate.
        spent: The current attributed spend at the time of rejection.
    """

    def __init__(self, task: str, cap: float, spent: float):
        self.task = task
        self.cap = cap
        self.spent = spent
        super().__init__(
            f"\U0001f6d1 [Mintry Shield] Mandate '{task}' exceeded. "
            f"Hard Cap: ${cap:.4f} | Current Attributed Spend: ${spent:.4f}"
        )
