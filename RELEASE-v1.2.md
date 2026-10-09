# AI Company OS v1.3 — Payment Ready

- Provider-agnostic payment request layer.
- Paid execution is gated behind an active subscription.
- Owner/internal account remains free for testing.
- Optional checkout URLs per plan via environment variables.
- Manager-only payment confirmation for controlled testing/manual settlement.
- No endpoint claims a real payment occurred without an explicit confirmation.

A real checkout processor must be selected based on the operator's country, business eligibility, and compliance requirements.
