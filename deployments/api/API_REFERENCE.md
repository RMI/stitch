# Stitch API Reference

## Auth

### `GET /api/v1/auth/me`

<!-- description -->

**Response:** `200`

- `user`: User | null
- `claims`: TokenClaimsView

---

## Other

### `GET /api/v1/health`

<!-- description -->

**Response:** `200`

---

### `GET /api/v1/health/details`

<!-- description -->

**Response:** `200`

---

## Oil Gas Fields

### `GET /api/v1/oil-gas-fields/`

<!-- description -->

**Response:** `200`

- `items`: array[OGFieldListItemView]
- `total_count`: integer
- `page`: integer
- `page_size`: integer
- `total_pages`: integer

---

### `POST /api/v1/oil-gas-fields/`

<!-- description -->

**Request Body:** `OGFieldResource`

- `id`: integer | null
- `source_data`: array[GemSource-Input | WoodMacSource-Input | RMISource-Input | LLMSource-Input]
- `repointed_to`: integer | null
- `constituents`: array[integer]
- `provenance`: object[string, array[object] | null]
- `view`: OilGasFieldBase | null

**Response:** `200`

- `id`: integer | null
- `source_data`: array[GemSourceView | WoodMacSourceView | RMISourceView | LLMSourceView]
- `repointed_to`: integer | null
- `constituents`: array[integer]
- `provenance`: object[string, array[object] | null]
- `view`: OilGasFieldBase | null

---

### `GET /api/v1/oil-gas-fields/filter-options`

<!-- description -->

**Response:** `200`

- `field`: string
- `values`: array[string]

---

### `GET /api/v1/oil-gas-fields/merge-candidates`

<!-- description -->

**Response:** `200`

- array[MergeCandidateView]

---

### `POST /api/v1/oil-gas-fields/merge-candidates`

<!-- description -->

**Request Body:** `MergeCandidateCreateRequest`

- `resource_ids`: array[integer]

**Response:** `200`

- `id`: integer
- `resource_ids`: array[integer]
- `status`: MergeCandidateStatus
- `review_notes`: string | null
- `merged_resource_id`: integer | null
- `created`: string
- `updated`: string
- `created_by_id`: integer
- `last_updated_by_id`: integer
- `reviewed_at`: string | null
- `reviewed_by_id`: integer | null

---

### `GET /api/v1/oil-gas-fields/merge-candidates/{id}`

<!-- description -->

**Response:** `200`

- `id`: integer
- `resource_ids`: array[integer]
- `status`: MergeCandidateStatus
- `review_notes`: string | null
- `merged_resource_id`: integer | null
- `created`: string
- `updated`: string
- `created_by_id`: integer
- `last_updated_by_id`: integer
- `reviewed_at`: string | null
- `reviewed_by_id`: integer | null

---

### `GET /api/v1/oil-gas-fields/merge-candidates/{id}/preview`

<!-- description -->

**Response:** `200`

- `resource_ids`: array[integer]
- `data`: OilGasFieldBase
- `provenance`: object[string, string | null]

---

### `POST /api/v1/oil-gas-fields/merge-candidates/{id}/approve`

<!-- description -->

**Request Body:** MergeCandidateReviewRequest | null


**Response:** `200`

- `id`: integer
- `resource_ids`: array[integer]
- `status`: MergeCandidateStatus
- `review_notes`: string | null
- `merged_resource_id`: integer | null
- `created`: string
- `updated`: string
- `created_by_id`: integer
- `last_updated_by_id`: integer
- `reviewed_at`: string | null
- `reviewed_by_id`: integer | null

---

### `POST /api/v1/oil-gas-fields/merge-candidates/{id}/deny`

<!-- description -->

**Request Body:** MergeCandidateReviewRequest | null


**Response:** `200`

- `id`: integer
- `resource_ids`: array[integer]
- `status`: MergeCandidateStatus
- `review_notes`: string | null
- `merged_resource_id`: integer | null
- `created`: string
- `updated`: string
- `created_by_id`: integer
- `last_updated_by_id`: integer
- `reviewed_at`: string | null
- `reviewed_by_id`: integer | null

---

### `GET /api/v1/oil-gas-fields/{id}`

<!-- description -->

**Response:** `200`

- `name`: string | null
- `country`: string | null
- `latitude`: number | null
- `longitude`: number | null
- `name_local`: string | null
- `state_province`: string | null
- `region`: string | null
- `basin`: string | null
- `owners`: array[OilGasOwner] | null
- `operators`: array[OilGasOperator] | null
- `location_type`: string | null
- `production_conventionality`: string | null
- `primary_hydrocarbon_group`: string | null
- `reservoir_formation`: string | null
- `discovery_year`: integer | null
- `production_start_year`: integer | null
- `fid_year`: integer | null
- `field_status`: string | null
- `id`: integer

---

### `GET /api/v1/oil-gas-fields/{id}/detail`

<!-- description -->

**Response:** `200`

- `id`: integer
- `data`: OilGasFieldBase
- `provenance`: object[string, string | null]
- `source_data`: array[GemSourceView | WoodMacSourceView | RMISourceView | LLMSourceView]

---

### `GET /api/v1/oil-gas-fields/{id}/fields/{field}/sources`

<!-- description -->

**Response:** `200`

- array[OGFieldSourceValueView]

---

### `POST /api/v1/oil-gas-fields/{id}/sources`

<!-- description -->

**Request Body:** GemSource-Input | WoodMacSource-Input | RMISource-Input | LLMSource-Input


**Response:** `200`

- GemSourceView | WoodMacSourceView | RMISourceView | LLMSourceView

---

## Oil Gas Field Sources

### `POST /api/v1/oil-gas-field-sources/`

<!-- description -->

**Request Body:** GemSource-Input | WoodMacSource-Input | RMISource-Input | LLMSource-Input


**Response:** `200`

- GemSourceView | WoodMacSourceView | RMISourceView | LLMSourceView

---

### `GET /api/v1/oil-gas-field-sources/`

<!-- description -->

**Response:** `200`

- `items`: array[GemSourceView | WoodMacSourceView | RMISourceView | LLMSourceView]
- `total_count`: integer
- `page`: integer
- `page_size`: integer
- `total_pages`: integer

---

### `GET /api/v1/oil-gas-field-sources/{id}`

<!-- description -->

**Response:** `200`

- GemSourceView | WoodMacSourceView | RMISourceView | LLMSourceView

---

### `GET /api/v1/oil-gas-field-sources/{id}/detail`

<!-- description -->

**Response:** `200`

- GemSource-Output | WoodMacSource-Output | RMISource-Output | LLMSource-Output

---
