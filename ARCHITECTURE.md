# Architecture

## Experience layer
1. Client App
2. Owner/Manager App (PWA)

## Application layer
- Authentication
- Conversation/Discovery Engine
- Company Brain
- AI Orchestrator
- Agent registry + permissions
- Workflow engine
- Creative generation
- Analytics
- Billing/payments
- Notifications
- Audit/security

## Agent registry
CEO, Research, Sales, Marketing, Content, Creative Image, Creative Video,
Support, Operations, Analytics, Finance, QA/Security.

Agents are coordinated by the orchestrator. The client should not need to
understand which agent performed a task.

## Security rule
High-risk external actions require explicit approval. Secrets belong only in
backend secret storage, never in browser code.
