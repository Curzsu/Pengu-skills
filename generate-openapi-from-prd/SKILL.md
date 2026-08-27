---
name: generate-openapi-from-prd
description: Use when a PRD, product requirement, user story, acceptance criteria, or feature description must become an OpenAPI contract for frontend, backend, mock, or test agents before parallel API development.
---

# Generate OpenAPI from PRD

## Goal

Turn a PRD directly into one implementation-ready OpenAPI 3.0.3 contract and a short handoff for frontend, backend, and test agents. Favor forward progress without hiding invented product decisions.

## Mandatory confirmation gate

The confirmation protocol uses ASCII-only JSON string literals so that Windows
loaders cannot reinterpret literal UTF-8 Chinese bytes as GBK or ANSI. Decode
these JSON values to Unicode before comparing or responding; never print the
backslash-u escape sequences themselves. The reply arrays are examples of
clear intent, not substring patterns.

CONFIRMATION_QUESTION_JSON = "\u8bf7\u786e\u8ba4 PRD \u6587\u4ef6\u548c\u539f\u4ed3\u5e93\uff08\u53ef\u9009\uff09\u5df2\u7ecf\u63d0\u4f9b\u3002\u56de\u590d\u201c\u786e\u5b9a\u201d\u7ee7\u7eed\uff0c\u56de\u590d\u201c\u53d6\u6d88\u201d\u9000\u51fa\u3002"
AFFIRMATIVE_REPLIES_JSON = ["\u786e\u5b9a","\u786e\u8ba4","\u662f","\u662f\u7684","\u53ef\u4ee5","\u597d","\u597d\u7684","\u884c","\u7ee7\u7eed","ok","ok\u4e86","okay","yes"]
CANCELLATION_REPLIES_JSON = ["\u53d6\u6d88","\u505c\u6b62","\u9000\u51fa","\u4e0d\u7528\u4e86","\u4e0d\u9700\u8981","\u5148\u4e0d\u505a","cancel","stop","no"]
CANCELLATION_RESPONSE_JSON = "\u5df2\u53d6\u6d88\u3002\u672c\u6b21\u672a\u8bfb\u53d6 PRD \u6216\u4ed3\u5e93\uff0c\u4e5f\u672a\u751f\u6210\u4efb\u4f55\u6587\u4ef6\u3002"
AMBIGUOUS_REPROMPT_JSON = "\u6211\u8fd8\u6ca1\u6709\u5f00\u59cb\u5de5\u4f5c\u3002\u8bf7\u56de\u590d\u201c\u786e\u5b9a\u201d\u7ee7\u7eed\uff0c\u6216\u56de\u590d\u201c\u53d6\u6d88\u201d\u9000\u51fa\u3002"
AMBIGUOUS_EXIT_JSON = "\u672a\u6536\u5230\u660e\u786e\u9009\u62e9\uff0c\u672c\u6b21\u5df2\u7ed3\u675f\u4e14\u672a\u5f00\u59cb\u4efb\u4f55\u5de5\u4f5c\u3002\u51c6\u5907\u597d\u540e\u8bf7\u91cd\u65b0\u8c03\u7528\u3002"

Treat the gate as a state machine. Infer an unresolved confirmation request
from the visible conversation, not from exact serialization of an assistant
message. A request is pending when the most recent gate question or reprompt
has no later confirmation, cancellation, or terminal exit. Recognize the
decoded question or reprompt even when the assistant or host adds formatting,
labels, or status text around it. Do not require whole-message equality.

On a new invocation with no pending request, regardless of what the user says
or whether paths and attachments appear to be present, respond with exactly the
decoded value of `CONFIRMATION_QUESTION_JSON`. Return no other text. Before this
response and before the user's confirmation:

- do not inspect, open, read, or search any PRD, attachment, path, or repository;
- do not call tools, create a plan, analyze requirements, generate artifacts, or start implementation;
- do not treat an affirmative reply contained in the invocation message as confirmation.

When a request is pending, normalize the whole current reply with Unicode NFKC,
trim surrounding whitespace and quote marks, remove only final sentence
punctuation, and lowercase ASCII letters. Classify the normalized whole reply:

- **Affirmative:** its complete meaning is a short, unconditional authorization
  to continue. Values in `AFFIRMATIVE_REPLIES_JSON` and close standalone
  synonyms qualify.
- **Cancellation:** its complete meaning is to cancel, stop, exit, or not
  proceed. Values in `CANCELLATION_REPLIES_JSON` and close standalone synonyms
  qualify. Cancellation wins if a reply contains conflicting intent.
- **Ambiguous:** everything else. Never confirm from a substring. A reply with
  conditions, extra instructions, contradiction, or negation is not affirmative.

Apply these transitions:

| Starting condition | Reply class | Action |
|---|---|---|
| No pending request | Any | Ask `CONFIRMATION_QUESTION_JSON`; stay pending. |
| Pending after the initial question | Affirmative | Pass the gate and continue the workflow in the same turn. |
| Pending after the reprompt | Affirmative | Pass the gate and continue the workflow in the same turn. |
| Pending | Cancellation | Respond with exactly `CANCELLATION_RESPONSE_JSON`; do no work; close the request. |
| Pending after the initial question | Ambiguous | Respond with exactly `AMBIGUOUS_REPROMPT_JSON`; do no work; stay pending. |
| Pending after the reprompt | Ambiguous | Respond with exactly `AMBIGUOUS_EXIT_JSON`; do no work; close the request. |

This caps consecutive ambiguous replies at two without relying on a hidden
counter: the decoded reprompt marks the second and final chance. After a request
is confirmed or closed, do not reuse it as confirmation for a later invocation.

After the gate passes, verify that a PRD is accessible. If it is missing, ask the user to provide it; the repository remains optional. Once the missing PRD is provided, continue without repeating the confirmation gate.

## Inputs and outputs

- Accept pasted PRD text or a PRD file. Read it completely.
- Do not require source code. If a repository is available, follow its naming and contract location conventions without reverse-engineering behavior that contradicts the PRD, and inspect its verified implementation constraints as described below.
- Follow a user-specified output path. Otherwise use:
  - `api-contract/openapi.yaml`
  - `api-contract/agent-handoff.md`
- Do not require OpenAPI Generator.

## Optional business knowledge

After the confirmation gate passes, use the bundled business knowledge CLI only when the PRD concerns Xinxintong and business vocabulary, roles, flows, or current capabilities need background context. Resolve the script relative to this skill directory.

Use this retrieval shape:

1. Run `python scripts/query_business_knowledge.py status --source xinxintong --document product-overview` when source freshness or availability matters.
2. Run `python scripts/query_business_knowledge.py search --source xinxintong --document product-overview --query "<specific business terms>"` first.
3. Run `python scripts/query_business_knowledge.py sections --source xinxintong --document product-overview` only when search terms are unclear.
4. Run `python scripts/query_business_knowledge.py get --source xinxintong --document product-overview --heading "<exact returned heading>"` for each relevant section. Do not load the full document by default.

Treat retrieved content as background, not as requirements. The user's explicit decisions and the current PRD define target behavior. Use background to clarify meaning and current context, but never add endpoints, fields, states, or permissions that the PRD does not require. If background conflicts with the PRD, keep the PRD behavior and record the conflict for the handoff unless the inference policy requires a focused question.

For every retrieved section, retain its commit, path, line range, freshness, and citation URL. Do not copy Git credentials, cache paths, or unrelated sections into generated artifacts.

## Inspect repository constraints

When one or more repositories are available, inspect each repository before writing the agent handoff. Derive constraints from evidence instead of assuming the newest or locally installed tooling. Check, when present:

- production and deployment configuration, including container images, deployment manifests, process definitions, and environment configuration;
- runtime and toolchain versions declared by version files, build configuration, or project metadata;
- dependency manifests and lockfiles, including supported runtime ranges and package-manager choice;
- CI configuration, repository-native build and test commands, and startup or health-check commands.

Prefer evidence in this order: production or deployment configuration, CI configuration, project metadata and version files, then developer documentation. Record the source path for every verified constraint. If authoritative sources disagree, report the conflict and preserve both pieces of evidence; do not silently choose one.

Do not hard-code any language, framework, runtime, package manager, or version in this skill or in a generated handoff unless it is verified from the supplied repository. Do not guess missing repository constraints. If no repository is supplied or no reliable runtime evidence exists, state that runtime constraints are unknown and require the implementation agent to verify them before coding.

Keep repository implementation constraints out of `openapi.yaml`; OpenAPI remains language- and framework-agnostic. Carry verified constraints, evidence, conflicts, and required verification steps only in `agent-handoff.md`.

## Inference policy

After the mandatory confirmation gate passes, generate immediately. When the user explicitly asks for direct generation, do not block on clarification: choose the narrowest safe behavior and record it. Otherwise ask one focused question only when an unknown changes authorization, money, irreversible deletion, regulatory behavior, or another high-impact semantic and no narrow representation exists.

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
- **Business context consulted:** when the business knowledge CLI was used, list each consulted heading with commit, path, line range, freshness, citation URL, and any conflict with the PRD. Otherwise state that no business context was consulted.
- **Repository constraints:** for each supplied repository, list verified language/runtime/toolchain, framework and dependency constraints, package manager, repository-native commands, and the evidence path for each value. If none are verified, state that runtime constraints are unknown.
- **Conflicts or unknowns:** list conflicting or missing repository evidence and the decision the responsible implementation agent must resolve before coding; do not turn unknowns into assumptions.
- **Frontend agent:** implement against the schemas and examples, use a contract-derived mock when helpful, obey the verified repository constraints, and write implementation-level frontend tests. Do not use syntax, APIs, or dependencies unsupported by the verified target runtime or toolchain.
- **Backend agent:** implement every operation and response, enforce constraints and ownership, obey the verified repository constraints, and write domain/unit/integration tests. Do not use language syntax, standard-library APIs, or dependency versions unsupported by the verified target runtime or toolchain.
- **Test agent:** independently generate contract, boundary, permission, frontend, backend, and integration tests from the PRD plus OpenAPI; report contradictions instead of changing the contract. When a deployment environment is identifiable, test with the exact deployment runtime or container and include an application import or equivalent startup preflight plus service startup and health check when applicable.
- **Definition of done:** relevant unit tests pass, both sides conform to OpenAPI, each implementation passes its repository-native checks under the verified target environment, and at least one real frontend-backend smoke path passes before merge. Dependency changes must update the repository's manifest and lockfile when applicable.

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
- handoff names and paths match the contract;
- every supplied repository has either evidence-backed constraints or an explicit unknown marker;
- every verified constraint cites a repository path and every conflict is reported;
- target-environment verification includes repository-native checks and startup validation when the repository exposes them.
- business background, when consulted, is cited in the handoff and has not expanded the PRD's API surface.

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
| Hard-coding a runtime after one compatibility incident | Derive technology and version constraints from each supplied repository. |
| Testing only in the agent's local environment | Verify with the repository's deployment runtime or container when available. |
