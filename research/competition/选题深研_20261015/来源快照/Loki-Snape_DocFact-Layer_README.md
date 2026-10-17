# Fact Knowledge Layer

A document fact extraction and cross-document reconciliation system built on the PERN stack (PostgreSQL, Express, React, Node.js). The system parses unstructured corporate financial reports and macroeconomic policy PDFs, extracts atomic, structured facts grounded with verbatim quotes and page numbers, and performs automated cross-document reconciliation to identify corroborations, contradictions, and contextual reconciliations.

---

## Setup and Run Instructions

### Prerequisites
- Node.js (v18 or higher)
- PostgreSQL database (local instance or managed cloud provider such as Neon)
- LLM API key (Groq API key configured; OpenRouter / Cerebras also supported)

### 1. Repository Setup & Dependencies

```bash
# Clone the repository
git clone https://github.com/Loki-Snape/DocFact-Layer.git
cd DocFact-Layer/fact-layer

# Install backend dependencies
cd backend
npm install

# Install frontend dependencies
cd ../frontend
npm install
```

### 2. Environment Configuration

Create a `.env` file in `fact-layer/backend/` using `backend/.env.example` as a template:

```env
PORT=5000
DATABASE_URL=postgresql://<user>:<password>@<host>/<dbname>?sslmode=require
GROQ_API_KEY=your_groq_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here
CEREBRAS_API_KEY=your_cerebras_api_key_here
```

### 3. Database Initialization

Run database migrations to initialize tables (`documents`, `facts`, `relationships`):

```bash
cd fact-layer/backend
node -e "const { runMigrations, pool } = require('./src/db'); runMigrations().then(() => { console.log('Migrations complete'); pool.end(); });"
```

### 4. Running the Application

Start the backend API server (runs on port 5000):
```bash
cd fact-layer/backend
npm start
# or: node src/index.js
```

In a separate terminal, start the frontend development server:
```bash
cd fact-layer/frontend
npm run dev
```

Open `http://localhost:5173` in your browser to view the Fact Layer user interface.

---

## Video Demo

https://drive.google.com/file/d/1lfLyzfrMQga3w2I9bkUVQ3DxyJRWRkez/view?usp=sharing

---

## Approach

The system operates as an end-to-end, multi-stage pipeline designed for evidentiary document grounding and factual consistency checking:

1. **Document Ingestion & Page-by-Page Parsing**:
   - PDFs are ingested and parsed into discrete pages using `pdf-parse`.
   - Content is windowed into coherent semantic chunks (1 to 2 pages per chunk) while preserving strict page boundaries and page number metadata.

2. **Grounded Fact Extraction**:
   - Chunks are dispatched to an LLM extractor with strict schema validation (`subject`, `predicate`, `value`, `unit`, `time_period`, `scope`, `fact_type`, `evidence`).
   - Every extracted fact requires exact, verbatim source quotes and target page numbers to ensure strict evidentiary grounding and prevent hallucinations.
   - Extracted facts are immediately validated against JSON schemas and persisted into PostgreSQL per chunk, ensuring no loss of progress during long processing runs.

3. **Database Architecture**:
   - Facts and documents are indexed in PostgreSQL with foreign keys linking back to source documents, storing structured attributes alongside raw evidentiary citations.

4. **Cross-Document Fact Reconciliation**:
   - The reconciliation engine pairs facts across distinct documents using heuristic domain and subject pre-filters (preventing invalid cross-domain pairings such as corporate logistics revenue vs. national GDP).
   - Pairs are evaluated with structured classification prompts into:
     - `corroborates`: Both facts assert equivalent statements with mutually supporting evidence.
     - `contradicts`: Direct empirical disagreement on numbers, metrics, or factual statements.
     - `contextual_reconciliation`: Discrepancies explained by differing time periods, accounting scopes, forecasting horizons, or reporting standards.
     - `unclear`: Insufficient overlap or non-comparable dimensions.

5. **LLM Infrastructure & Resilience**:
   - An adaptive multi-provider fallback engine was implemented with automated backoff for per-minute rate limits, token usage tracking, and multi-model failover (e.g. `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `allam-2-7b`).

---

## Empirical Results and Reconciliation Findings

Across the complete 6-document dataset ingested into the database (209 total facts):

### Strong Contextual Reconciliation Example (India GDP Growth Forecasts)
- **Fact A (`01-india-economic-survey-2024-25-excerpt.pdf`, Page 4):**
  - Subject: `India's real GDP`
  - Predicate: `estimated growth rate`
  - Value: `6.4%` (Time Period: `FY25`)
  - Evidence: *"India’s real GDP is estimated to grow by 6.4 per cent in FY25."*
- **Fact B (`03-imf-india-2025-article-iv-excerpt.pdf`, Page 68):**
  - Subject: `India's GDP growth rate`
  - Predicate: `2022-2026`
  - Value: `7.5%` (Time Period: `2022-2026 / FY22-26`)
  - Evidence: *"India's GDP growth rate is expected to be 7.5% in FY22-26."*
- **Reconciliation Reasoning:**
  - Both documents discuss India's GDP growth trajectory, but they represent different forecasting horizons. The Economic Survey reports a single-year point estimate specifically for FY25 (6.4%), whereas the IMF Article IV report cites a multi-year medium-term average trajectory across FY22-26 (7.5%). The numerical divergence is fully resolved by accounting for the differing time scopes rather than a factual disagreement.

---

## Documented Extraction & Reasoning Failure Case (RBI Content Limitation)

Across the ingested corpus, no confident cross-document `corroborates` or `contradicts` relationships emerged from the datasets as provided. A thorough analysis revealed the root cause:

1. **Dataset Period Disconnect (Delhivery Group):**
   - The Delhivery Prospectus excerpt covers historical periods (FY19 to FY21), whereas the Annual Report and Earnings Presentation excerpts focus almost exclusively on FY24, preventing direct single-period metric overlap.

2. **Source Document Content Gap (RBI Annual Report Excerpt):**
   - Direct database and document inspection showed that the provided excerpt for `02-rbi-annual-report-2024-25-excerpt.pdf` contained primarily Table of Contents front matter, section headings, and balance sheet structure annexures rather than the core macroeconomic indicator tables (such as headline CPI inflation, real GDP growth projections, or fiscal deficit ratios) required to cross-compare against the Economic Survey and IMF documents.
   - **Extraction Fidelity:** The extractor operated correctly and faithfully, capturing 8 structured facts from the pages (e.g., Box titles on R&D productivity growth, accounting period definitions) with zero hallucinations.
   - **The Actual Failure:** The failure was an architectural assumption that all three macroeconomic excerpts would contain directly comparable numeric macro indicators. In reality, the RBI excerpt lacked the necessary data tables.

3. **What We Would Do Differently:**
   - **Automated Content Coverage Verification:** Implement a pre-extraction document profiling step that verifies whether a source PDF contains target metric categories (e.g. searching for tabular CPI/GDP keywords) before queueing reconciliation passes.
   - **Targeted Page Ingestion:** With access to a paid LLM tier and a complete RBI Annual Report, ingest the specific chapters dedicated to "Economic Review and Monetary Policy" where GDP and inflation projections reside, enabling full corroboration and contradiction verification against Economic Survey and IMF figures.

---

## Limitations and Next Steps

1. **Absence of Same-Period Numeric Contradictions in Source Datasets**:
   - After searching all 209 extracted facts, no genuine same-period numeric contradiction was found across the corpus, since the documents largely cover non-overlapping fiscal periods or forecast horizons rather than reporting conflicting values for the same point in time. With a longer time window, we would prioritize sourcing documents with deliberately overlapping reporting periods to surface a genuine contradiction case, or manually construct one from the existing 209 facts using human judgment as an interim solution.

2. **Candidate Pair Generation**:
   - The current reconciler candidate selection relies on subject and keyword heuristics. For larger scale corpora, transitioning to vector embeddings (e.g. cosine similarity over fact embeddings) will allow more scalable and semantically targeted candidate pair pre-filtering.

3. **Frontier Model Reasoning**:
   - Moving from open-weight models on free rate limits to frontier models (e.g. GPT-4o, Claude 3.5 Sonnet) will provide higher reasoning fidelity on subtle domain distinctions and eliminate token rate-limiting bottlenecks.

---

## Additional Notes

- **AI Tools Used**:
  - Anthropic Claude was used for high-level architectural design and debugging strategies.
  - The Antigravity coding agent was used for codebase implementation, test scripting, database queries, and pipeline execution.
