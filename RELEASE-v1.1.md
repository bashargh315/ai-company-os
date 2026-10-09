# AI Company OS v1.1 — Paid Client MVP

This release changes the commercial rule: **customers pay; internal owner access is free for development/testing.**

## Plans
- Starter: $49/month
- Growth: $149/month
- Pro: $399/month

## Billing architecture
The backend now has subscriptions and entitlement checks. The owner account can activate plans for internal testing. Real customer checkout is intentionally provider-agnostic until a payment provider that legally supports the operator is selected.

Paddle currently lists Syria as unsupported for suppliers, and Stripe's global availability list does not include Syria; therefore do not assume either provider can be used from Syria. Verify eligibility before onboarding a payment processor.
