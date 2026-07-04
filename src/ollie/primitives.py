"""Operational primitive types (v1 enum)."""

EXTERNAL_INTERACTION = "external_interaction"
DELEGATION = "delegation"
STATE_MUTATION = "state_mutation"
VERIFICATION = "verification"
GENERATION = "generation"

BUILTIN_PRIMITIVES: frozenset[str] = frozenset(
    {
        EXTERNAL_INTERACTION,
        DELEGATION,
        STATE_MUTATION,
        VERIFICATION,
        GENERATION,
    }
)
