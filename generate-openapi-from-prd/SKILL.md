---
name: generate-openapi-from-prd
description: Use when a PRD, product requirement, user story, acceptance criteria, or feature description must become an OpenAPI contract for frontend, backend, mock, or test agents before parallel API development.
---

# Generate OpenAPI from PRD

## Goal

Turn a PRD directly into one implementation-ready OpenAPI 3.0.3 contract and a short handoff for frontend, backend, and test agents. Favor forward progress without hiding invented product decisions.

## Inputs and outputs

- Accept pasted PRD text or a PRD file. Read it completely.
- Do not require source code. If a repository is available, follow its naming and contract location conventions without reverse-engineering behavior that contradicts the PRD.
- Follow a user-specified output path. Otherwise use:
  - `api-contract/openapi.yaml`
  - `api-contract/agent-handoff.md`
- Do not require OpenAPI Generator.

## Inference policy

Generate immediately. When the user explicitly asks for direct generation, do not block on clarification: choose the narrowest safe behavior and record it. Otherwise ask one focused question only when an unknown changes authorization, money, irreversible deletion, regulatory behavior, or another high-impact semantic and no narrow representation exists.

Treat an omitted capability as unsupported, not as permission to design it. A constraint does not imply additional features: for example, "refund must not exceed the order amount" does not by itself authorize partial refunds, repeated refunds, asynchronous processing, or an idempotency header. Prefer one operation and the fewest states that satisfy the PRD.

For remaining omissions, choose the smallest conventional default and record it in the top-level `x-ai-assumptions` array. Use at most five short, single-decision assumptions. Never silently invent:

- endpoints or UI features not needed by the PRD;
- state transitions, permissions, partial operations, or retry behavior;
- queues, databases, object storage, events, Outbox, or other implementation architecture;
- UUIDs, JWT, asynchronous processing, idempotency protocols, or pagination semantics unless required by the PRD or an established repository convention.

Keep IDs as `string` unless their format is known. Describe side effects such as notifications without defining webhooks or event APIs unless requested.

## Build the contract

1. Extract actors, resources, actions, ownership, constraints, state changes, errors, and acceptance criteria.
2. Map only required external behavior to REST paths and methods.
3. Write OpenAPI `3.0.3` YAML with:
   - `info`, relative `servers`, `tags`, `paths`, and reusable `components`;
   - unique stable `operationId` values;
   - explicit parameters and request bodies with required/optional semantics;
   - complete response schemas and explicit success/error status codes;
   - reusable error schema containing at least `code` and `message`;
   - types, formats, enums, bounds, nullable behavior, and realistic examples;
   - authentication only when implied by the PRD, with the chosen mechanism recorded if unspecified.
4. Put every non-PRD product decision in `x-ai-assumptions`. Keep the list short and concrete.
5. Do not leave `TODO`, `TBD`, placeholder schemas, or prose-only responses.

Example extension:

```yaml
x-ai-assumptions:
  - "Authenticated endpoints use Bearer tokens because the PRD specifies logged-in users but not the session mechanism."
  - "Resource identifiers are opaque strings; their storage format is intentionally unspecified."
```

## Create the agent handoff

Write `agent-handoff.md` with the contract path, PRD source, assumptions, and these sections:

- **Shared rule:** all agents use this exact contract; nobody changes fields, paths, or status codes unilaterally.
- **Frontend agent:** implement against the schemas and examples, use a contract-derived mock when helpful, and write implementation-level frontend tests.
- **Backend agent:** implement every operation and response, enforce constraints and ownership, and write domain/unit/integration tests.
- **Test agent:** independently generate contract, boundary, permission, frontend, backend, and integration tests from the PRD plus OpenAPI; report contradictions instead of changing the contract.
- **Definition of done:** relevant unit tests pass, both sides conform to OpenAPI, and at least one real frontend-backend smoke path passes before merge.

Keep the handoff under one page. Do not repeat the full OpenAPI document.

## Validate

Run the bundled validator, resolving the script relative to this skill directory:

```text
python scripts/validate_openapi.py <path-to-openapi.yaml>
```

Fix every reported problem. If the repository already has a stronger OpenAPI linter, run it too. Then verify:

- every PRD acceptance criterion maps to an operation, constraint, response, or handoff test instruction;
- every path parameter is declared and required;
- every operation has a unique `operationId` and an explicit 2xx response;
- every local `$ref` resolves;
- examples match their schemas;
- handoff names and paths match the contract.

## Completion

Return links to `openapi.yaml` and `agent-handoff.md`, plus only the recorded assumptions and any single blocking question. Do not paste the entire contract unless requested.

## Common mistakes

| Mistake | Correction |
|---|---|
| Expanding a vague PRD into a full platform | Specify only behavior required for this feature. |
| Hiding guesses in descriptions | Move them to `x-ai-assumptions`. |
| Generating implementation architecture | Keep the artifact at HTTP contract level. |
| Treating unit tests as integration proof | Require contract checks and one real smoke path. |
| Making three agents interpret different copies | Hand off one versioned file from one shared path. |
