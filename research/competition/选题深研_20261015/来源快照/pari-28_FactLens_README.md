# FactLens

## Multi-Document Fact Knowledge Layer

FactLens is a document-grounded verification system that extracts structured facts from multiple PDF documents, preserves their source evidence, normalizes comparable values, identifies semantically related facts, and determines how those facts relate to each other.

The system is designed to work with **arbitrary PDF documents**, rather than relying on a specific company, metric, filename, value, reporting period, or starter dataset.

### Core Pipeline

```text
PDFs
  ↓
Document / Text Extraction
  ↓
AI-Assisted Fact Extraction
  ↓
Source-Grounded Structured Facts
  ↓
Deterministic Normalization
  ↓
Cross-Document Semantic Matching
  ↓
Contextual Comparison
  ↓
Relationship Classification
  ↓
Human-Readable Explanation
  ↓
Evidence / Audit Trail
```

## Problem

The same underlying fact can appear in different documents using different wording, units, periods, scopes, currencies, or reporting conventions.

A simple comparison of metric names or numerical values can therefore produce incorrect conclusions.

FactLens separates **semantic understanding** from **deterministic verification**.

- AI/LLM processing is used for semantic understanding and fact extraction.
- Deterministic application logic handles numerical normalization, calculations, contextual comparison, and relationship classification wherever possible.
- Source evidence is preserved so that every result can be inspected and verified.

## Key Design Principle

> Use AI to understand what a document says, but use deterministic application logic wherever possible to verify what the extracted facts actually imply.

The system also preserves uncertainty instead of forcing unrelated or insufficiently supported facts into a relationship.

---

# Demo Video

**FactLens Demo — Superjoin Engineering Intern Assignment**

[▶️ Watch the 3-minute demo video](https://drive.google.com/file/d/1YczbMEYOXEVcU1W7XSUn1UN1QGYusr5Z/view?usp=sharing)

The demo covers:

- PDF upload and document processing
- Generic fact extraction
- Source evidence and page references
- Fact Knowledge Base
- Cross-document semantic matching
- Deterministic normalization
- Corroborated relationships
- Contradicted relationships
- Reconciled-by-context relationships
- Uncertain / insufficient-evidence handling
- AI extraction failure and fallback behavior

---

# Architecture

FactLens uses a hybrid architecture where semantic interpretation and deterministic verification are separated.

```text
                         PDF Upload
                             |
                             v
                 +-----------------------+
                 | PDF / Page Extraction  |
                 +-----------+-----------+
                             |
                             v
                 +-----------------------+
                 | Text + Evidence       |
                 | with Page References  |
                 +-----------+-----------+
                             |
                             v
                 +-----------------------+
                 | AI-Assisted Fact      |
                 | Extraction            |
                 +-----------+-----------+
                             |
                  AI unavailable?
                       /          \
                     Yes           No
                     |              |
                     v              v
              +-----------+   +------------+
              |Deterministic| | Semantic   |
              |Fallback     | | Extraction |
              +------+------+\ +-----+------+
                     |             |
                     +------+------+
                            |
                            v
                 +-----------------------+
                 | Structured Fact       |
                 | Knowledge Layer       |
                 +-----------+-----------+
                             |
                             v
                 +-----------------------+
                 | Deterministic        |
                 | Normalization        |
                 +-----------+-----------+
                             |
                             v
                 +-----------------------+
                 | Semantic Fact        |
                 | Matching             |
                 +-----------+-----------+
                             |
                             v
                 +-----------------------+
                 | Contextual           |
                 | Comparison           |
                 +-----------+-----------+
                             |
                             v
                 +-----------------------+
                 | Relationship         |
                 | Classification       |
                 +-----------+-----------+
                             |
                             v
                 +-----------------------+
                 | Evidence +           |
                 | Explanation          |
                 +-----------------------+
```

## Structured Fact Model

Every extracted fact is represented using a generic and extensible structure.

A fact can contain:

| Field | Description |
|---|---|
| Document ID / name | Identifies the source document |
| Page number | Source page when available |
| Evidence quote | Verbatim supporting text |
| Entity / subject | Entity or subject being discussed |
| Concept / metric | Underlying fact or concept |
| Value | Numerical value when applicable |
| Unit | Unit of measurement when applicable |
| Currency | Currency when applicable |
| Normalized value | Deterministic normalized representation |
| Period | Date, year, quarter, or range |
| Period type | Annual, quarterly, point-in-time, etc. |
| Scope | Entity, segment, geography, population, etc. |
| Reporting / measurement basis | Reported, adjusted, accounting basis, etc. |
| Confidence | Extraction confidence |
| Qualifiers / context | Additional information affecting interpretation |

Not every field is required for every fact.

If the source document does not provide enough information, the corresponding field remains unknown rather than being invented.

The schema is deliberately **not tied to any particular company, metric, currency, reporting year, or document format**.

---

# What I Implemented

I implemented FactLens as a hybrid document-verification pipeline rather than a simple LLM wrapper.

### 1. Generic document ingestion

The application accepts multiple PDFs directly through the UI and processes each document independently.

Each document is assigned an internal document identity and its extracted pages remain associated with the source document.

The implementation does not depend on:

- specific filenames
- company names
- predefined metrics
- predefined numerical values
- fixed reporting periods
- a fixed number of pages
- the starter PDF structure

This allows the same pipeline to process new documents without changing the application logic.

### 2. Source-grounded fact representation

I introduced a structured fact representation that keeps the extracted claim connected to its source evidence.

A fact can retain:

```text
Document
Page
Evidence
Entity / Subject
Concept / Metric
Value
Unit
Currency
Normalized Value
Period
Period Type
Scope
Reporting / Measurement Basis
Confidence
Qualifiers
```

Missing information is preserved as unknown rather than being fabricated.

### 3. Hybrid extraction strategy

The primary path uses AI-assisted extraction for semantic understanding.

I also implemented a deterministic fallback path for cases where the external AI service is unavailable.

This means an API failure does not automatically terminate the entire document-processing workflow.

The UI explicitly indicates when fallback extraction is being used.

### 4. Deterministic normalization

I implemented normalization outside the LLM wherever the operation can be reliably performed through code.

This includes:

- numerical parsing
- scale conversion
- unit normalization
- currency representation
- percentage handling
- period normalization
- variance calculations

The system retains the original value as well as the normalized representation so that transformations can be audited.

### 5. Cross-document semantic matching

Fact matching is separated from relationship classification.

Potentially related facts are identified based on their underlying meaning rather than requiring identical metric names.

For example, two documents may describe the same concept using different wording.

The system then evaluates their context before deciding how the facts relate.

### 6. Context-aware relationship classification

I implemented deterministic comparison logic that evaluates contextual dimensions before declaring a contradiction.

The comparison considers available information such as:

- metric/concept
- period
- period type
- scope
- geography
- unit
- currency
- reporting basis
- operational basis
- actual vs forecast/target
- other explicit qualifiers

This prevents a simple numerical difference from automatically becoming a contradiction.

### 7. Evidence-first UI

The UI exposes the reasoning behind a relationship instead of displaying only a label.

For each relationship, the user can inspect:

- source documents
- page references
- original values
- normalized values
- evidence quotes
- contextual differences
- comparison details
- final classification
- explanation

This makes the result auditable rather than a black-box prediction.

### 8. Defensive handling of incomplete data

Real-world documents do not always contain every piece of metadata.

The implementation therefore uses defensive handling for optional fields and avoids assuming that every document contains the same structure.

This is particularly important for arbitrary PDFs where:

- periods may be missing,
- units may be implicit,
- scope may not be stated,
- facts may be qualitative,
- or extraction may be incomplete.

---

# Source Grounding

Source evidence is retained as part of the fact rather than being treated as an optional UI detail.

The intended relationship is:

```text
Document
   ↓
Page
   ↓
Evidence Quote
   ↓
Structured Fact
   ↓
Comparison
   ↓
Verification Result
```

This allows a reviewer to trace a result back to the original document.

For numerical facts, FactLens preserves both the original representation and the normalized representation.

For example:

```text
Source:
12.5 million

Normalized:
12,500,000
```

The normalization is performed by application logic rather than relying on the LLM to perform arithmetic.

---

# Cross-Document Relationship Classification

FactLens does not classify two facts as related simply because their names or numbers look similar.

The comparison stage first evaluates whether the facts describe the same underlying concept and whether their available context is sufficiently comparable.

The system supports four primary outcomes.

## 1. CORROBORATED

Facts are classified as **CORROBORATED** when they describe the same underlying fact and their available context and normalized values are compatible.

```text
Same underlying concept
        +
Comparable context
        +
Compatible values / claims
        ↓
CORROBORATED
```

Examples of compatible evidence may include the same measurement reported in different documents with equivalent units or equivalent wording.

---

## 2. CONTRADICTED

Facts are classified as **CONTRADICTED** only when:

1. They refer to the same underlying fact.
2. Their relevant context is sufficiently comparable.
3. Their values or claims are materially incompatible.
4. No valid contextual explanation is available.

```text
Same underlying concept
        +
Comparable context
        +
Materially incompatible claims
        +
No valid reconciliation
        ↓
CONTRADICTED
```

A numerical difference by itself is **not sufficient** to declare a contradiction.

---

## 3. RECONCILED BY CONTEXT

Two facts can appear inconsistent while actually referring to different contextual dimensions of the same concept.

FactLens checks available contextual information before declaring a contradiction.

Relevant dimensions can include:

- Time period
- Specific date
- Quarterly vs annual reporting
- Point-in-time vs period total
- Entity or scope
- Geography
- Unit
- Currency
- Gross vs net measurement
- Reporting/accounting basis
- Reported vs adjusted values
- Forecast/target vs historical actual
- Other meaningful qualifiers explicitly present in the documents

```text
Related underlying concept
        +
Explicit contextual difference
        +
Difference explains the apparent conflict
        ↓
RECONCILED BY CONTEXT
```

The explanation shown in the UI identifies the contextual dimension responsible for the reconciliation whenever sufficient evidence is available.

---

## 4. UNCERTAIN / INSUFFICIENT EVIDENCE

FactLens uses **UNCERTAIN / INSUFFICIENT EVIDENCE** when it cannot establish a reliable relationship.

This can happen when:

- the concepts are only superficially similar,
- the reporting period is unknown,
- scope is missing,
- evidence is incomplete,
- the values cannot be compared safely,
- or the documents do not provide enough information.

```text
Insufficient evidence
        ↓
Do not force a relationship
        ↓
UNCERTAIN
```

The system intentionally prefers uncertainty over an unsupported conclusion.

---

# Context Before Contradiction

A central design principle is:

> **A different number does not automatically mean the documents contradict each other.**

For example, two documents may report the same concept for different periods:

```text
Document A
Concept X
Period A
Value A

Document B
Concept X
Period B
Value B
```

Even if:

```text
Value A ≠ Value B
```

the difference may be legitimate because:

```text
Period A ≠ Period B
```

The comparison engine therefore evaluates contextual dimensions before producing a contradiction.

---

# Preventing False Relationships

The system does not intentionally force every extracted fact into a cross-document relationship.

Candidate matching and relationship classification are separate stages:

```text
Extracted Facts
      ↓
Potential Semantic Matches
      ↓
Context Comparison
      ↓
Verification
      ↓
Relationship Classification
```

This separation helps prevent a superficially similar fact from being incorrectly classified as a contradiction or corroboration.

When the available evidence is insufficient, the correct output is uncertainty.

# AI-Assisted Extraction

FactLens uses AI for the parts of document understanding that require semantic interpretation.

The AI extraction layer is responsible for interpreting natural language and identifying structured facts such as:

- Entity or subject
- Concept or metric
- Numerical value
- Unit
- Currency
- Date or reporting period
- Period type
- Scope
- Reporting or measurement basis
- Qualifiers
- Supporting evidence

The AI is **not treated as the final authority for numerical verification**.

Instead, extracted facts are passed to deterministic application logic for normalization and comparison.

---

# Deterministic Normalization

Numerical operations that can be performed reliably through code are kept deterministic.

For example:

```text
Input:
25 million

        ↓

Scale detection:
million = 1,000,000

        ↓

Normalized value:
25 × 1,000,000

        ↓

25,000,000
```

This approach avoids relying on an LLM for arithmetic.

The normalization layer is designed to work across different numerical representations rather than depending on a predefined starter dataset.

The same principle applies to supported units, scales, percentages, currencies, and temporal representations.

---

# Hybrid AI + Deterministic Architecture

FactLens deliberately combines two approaches.

### AI is used for:

- Natural-language understanding
- Semantic fact extraction
- Concept identification
- Entity identification
- Context interpretation
- Understanding differently worded claims

### Deterministic code is used for:

- Numerical parsing
- Unit/scale normalization
- Arithmetic
- Variance calculation
- Context comparison
- Relationship classification
- Defensive validation

This separation provides a balance between the flexibility of AI and the predictability of application logic.

---

# Failure Handling

FactLens treats external AI output and service availability as uncertain inputs rather than assuming they will always succeed.

The extraction pipeline validates model output before facts enter the verification layer. If AI-assisted extraction is temporarily unavailable, the application can use its deterministic extraction path where applicable and clearly communicates the extraction mode to the user.

This keeps the verification workflow resilient while avoiding presenting fallback results as AI-generated.

The fallback is a resilience mechanism, not a replacement for semantic extraction.

```text
PDF
 ↓
AI-Assisted Extraction
 ↓
Validation
 ↓
Structured Facts
 ↓
Normalization + Context Comparison
 ↓
Relationship Classification

If AI extraction is unavailable:
        ↓
Deterministic Extraction
        ↓
Structured Facts
        ↓
Same verification pipeline
```

The UI explicitly communicates when AI extraction is unavailable instead of presenting the fallback output as if it were generated by the AI model.

For example:

```text
AI extraction unavailable
Deterministic fallback used
```

This makes the failure mode visible to the user and allows the rest of the verification pipeline to continue where possible.

---


# Handling Model Output

AI-generated structured output is treated as untrusted input.

Before facts enter the verification pipeline, the application validates and normalizes the available fields.

Missing or malformed fields should not cause the entire analysis to fail.

For example:

```text
Extracted fact
    |
    +-- value        → available
    +-- unit         → available
    +-- period       → unknown
    +-- scope        → unknown
    +-- evidence     → available
```

The system can continue processing the fact while preserving unknown fields.

This is important because real-world documents do not consistently provide the same metadata for every statement.

---

---

# Trade-offs

## 1. AI extraction vs deterministic extraction

AI provides stronger semantic understanding of arbitrary language and document structure, but introduces external dependencies such as:

- API availability
- API quotas
- Rate limits
- Latency
- Model variability

The deterministic fallback improves resilience but has lower semantic coverage than an LLM.

---

## 2. Conservative matching vs recall

A permissive matcher could identify more potential relationships, but it would also increase false positives.

FactLens therefore uses a conservative approach:

> If there is insufficient evidence to establish that two facts represent the same underlying claim, the system should preserve uncertainty rather than invent a relationship.

This prioritizes verification quality over simply maximizing the number of relationships produced.

---

## 3. Deterministic verification vs fully LLM-based reasoning

Using application code for normalization and comparison makes the results more reproducible and easier to audit.

The trade-off is that highly specialized domain reasoning may require more sophisticated semantic models in a future version.

---

## 4. Text extraction vs visual document understanding

Text extraction works well for digitally generated PDFs, but PDFs can contain:

- Scanned pages
- Complex tables
- Charts
- Images containing text
- Multi-column layouts
- Visually encoded information

These cases can reduce extraction accuracy.

---

# Limitations

FactLens is an engineering prototype and is not intended to claim production-scale document intelligence.

Current limitations include:

### PDF processing

- Scanned/image-only PDFs may require OCR.
- Complex tables may not always be reconstructed perfectly.
- Charts and visual elements may require dedicated vision-based processing.
- Evidence quality depends on successful PDF text and page extraction.

### AI extraction

- External model availability can affect semantic extraction.
- API quotas and rate limits can temporarily prevent AI extraction.
- Model output can occasionally be incomplete or ambiguous.
- Different models may produce different interpretations of difficult statements.

### Semantic matching

- Highly domain-specific terminology can be difficult to match.
- Entity resolution can become challenging when documents use abbreviations or aliases.
- Similar concepts with subtle semantic differences may remain uncertain.

### Numerical normalization

- Some specialized units may require additional normalization rules.
- Cross-currency comparison should remain conservative without a reliable conversion basis.
- Ratios, rates, percentages, and derived metrics may require richer dimensional reasoning.

### Contextual reconciliation

Reconciliation depends on context actually being present in the source documents.

If a document does not state the relevant period, scope, basis, or qualifier, FactLens should not invent it.

---

# Next Steps

If this prototype were extended beyond the assignment, the highest-value improvements would be:

## 1. Better PDF understanding

- Add OCR for scanned PDFs.
- Add layout-aware parsing.
- Improve table extraction.
- Add chart and figure understanding.
- Improve handling of multi-column documents.

## 2. Stronger semantic matching

- Add embedding-based candidate retrieval.
- Combine lexical and semantic similarity.
- Improve entity resolution.
- Improve temporal reasoning.
- Add concept normalization.

## 3. Stronger verification

- Improve dimensional analysis.
- Support more percentage and rate comparisons.
- Add reliable currency conversion using authoritative exchange-rate sources.
- Improve handling of forecasts, targets, and historical actuals.
- Calibrate confidence scores against labeled evaluation data.

## 4. Evaluation benchmark

A larger evaluation dataset should be created containing manually verified:

- Extracted facts
- Evidence spans
- Fact matches
- Corroborations
- Contradictions
- Contextual reconciliations
- Uncertain relationships

The system could then be evaluated separately on:

```text
Extraction Quality
        +
Evidence Grounding
        +
Semantic Matching
        +
Relationship Classification
```

This would make it possible to measure improvements objectively instead of relying only on demonstrations.

---

# Assignment Requirements Coverage

| Assignment Requirement | FactLens Implementation |
|---|---|
| Accept new PDFs | PDF upload through the UI |
| Extract grounded facts | AI-assisted extraction + deterministic fallback |
| Preserve evidence | Document, page, and evidence quote are retained |
| Numerical facts | Structured values and deterministic normalization |
| Semantic facts | AI-assisted semantic extraction |
| Cross-document matching | Semantic candidate matching |
| Unit/value normalization | Deterministic normalization layer |
| Corroboration | Compatible underlying facts |
| Contradiction | Material conflict under comparable context |
| Contextual reconciliation | Context dimensions checked before contradiction |
| Uncertainty | Insufficient evidence is preserved |
| AI failure handling | Deterministic fallback path |
| Auditability | Evidence and comparison details exposed in UI |
| Generalization | No dependency on a specific starter document |

---

# Engineering Scope

FactLens is intentionally presented as an engineering prototype rather than a production-scale system.

The goal of this assignment implementation is to demonstrate the core architecture and reasoning approach:

```text
Generic Documents
       ↓
Grounded Facts
       ↓
Semantic Understanding
       ↓
Deterministic Verification
       ↓
Context-Aware Relationships
       ↓
Auditable Results
```

The implementation prioritizes correctness of the approach, explainability, and graceful failure handling within the scope of the assignment.

---

---

# Local Setup

## Requirements

- Node.js 18+
- npm

## Install dependencies

```bash
npm install
```

## Configure environment variables

Create a local `.env` file:

```env
GEMINI_API_KEY=your_api_key_here
```

Do not commit the real API key.

The repository contains `.env.example` as a configuration reference.

## Start the development server

```bash
npm run dev
```

The application will run at:

```text
http://localhost:3000
```

## Build

```bash
npm run build
```

---

# Usage

1. Open the FactLens application.
2. Upload two or more PDF documents.
3. Start analysis.
4. Wait for document extraction and fact processing.
5. Review the extracted Fact Knowledge Base.
6. Open cross-document relationships.
7. Inspect source evidence, page references, normalized values, and contextual dimensions.
8. Review the final relationship classification and explanation.
9. If the external AI service is unavailable, inspect the explicitly displayed deterministic fallback behavior.

---

# Project Structure

```text
factlens/
│
├── src/
│   ├── components/
│   │   ├── AuditExportModal.tsx
│   │   ├── DocumentViewerModal.tsx
│   │   ├── FactExplorer.tsx
│   │   ├── RelationshipCard.tsx
│   │   └── ...
│   │
│   ├── lib/
│   │   ├── deterministic-normalizer.ts
│   │   ├── deterministic-matcher.ts
│   │   └── ...
│   │
│   ├── types.ts
│   └── App.tsx
│
├── server/
│   ├── gemini.ts
│   ├── fallback-extractor.ts
│   └── ...
│
├── scripts/
├── server.ts
├── package.json
├── package-lock.json
├── .env.example
├── .gitignore
├── tsconfig.json
└── vite.config.ts
```

---

# Security

API credentials are intentionally excluded from the repository.

Use environment variables for local development:

```env
GEMINI_API_KEY=your_api_key_here
```

The actual `.env` file must never be committed to GitHub.

The repository's `.gitignore` excludes local environment files.

---

# Demo

The demonstration video shows the complete FactLens workflow:

```text
PDF Upload
    ↓
Document Processing
    ↓
Fact Extraction
    ↓
Fact Knowledge Base
    ↓
Evidence Inspection
    ↓
Cross-Document Matching
    ↓
Normalization
    ↓
Contextual Comparison
    ↓
Relationship Classification
    ↓
Audit / Explanation
```

The demo covers the four required relationship outcomes:

- **Corroborated**
- **Contradicted**
- **Reconciled by Context**
- **Uncertain / Insufficient Evidence**

The demo also shows the application's behavior when AI extraction is unavailable.

---

# Conclusion

FactLens demonstrates a hybrid approach to cross-document verification:

> **AI for semantic understanding. Deterministic code for verification. Evidence for trust. Uncertainty when evidence is insufficient.**

The architecture is designed to generalize to new documents rather than relying on hard-coded starter-dataset facts.

---

## Superjoin Engineering Intern Assignment — VIT 2026

**FactLens — Multi-Document Fact Knowledge Layer**