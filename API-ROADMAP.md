# API roadmap

## Authentication
POST /api/auth/session
POST /api/auth/logout

## Company
GET /api/company
PATCH /api/company

## Conversation
POST /api/conversations
POST /api/conversations/:id/messages
GET /api/conversations/:id

## AI execution
POST /api/goals
GET /api/workflows/:id
POST /api/workflows/:id/approve
GET /api/agent-runs

## Owner
GET /api/admin/overview
GET /api/admin/customers
GET /api/admin/revenue
GET /api/admin/approvals
GET /api/admin/audit

## Billing
GET /api/billing/subscription
POST /api/billing/checkout
POST /api/billing/webhook
GET /api/billing/payout-status

These are contracts/roadmap only in this UI package; production endpoints must
be implemented with authentication, authorization, validation, rate limits,
audit logging and webhook signature verification.
