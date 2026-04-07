# SyncServer Enhancements Plan

## Overview
This document outlines the plan to enhance the SyncServer warehouse management system with five key features:
1. Hashtag/tagging system for inventory items
2. Decimal quantity support for operations
3. Operation date flexibility
4. Repository of issued items/operations
5. Document generation system

## Current System Analysis
SyncServer is a Python/FastAPI warehouse inventory system with:
- Operations management (RECEIVE, EXPENSE, WRITE_OFF, MOVE, ADJUSTMENT, ISSUE, ISSUE_RETURN)
- Catalog hierarchy with categories and units
- Site-based access control
- Balance tracking derived from operations
- Device synchronization events

## Feature Designs

### 1. Hashtag/Tagging System
**Purpose:** Enable categorization and search of inventory items by brands, equipment types, and custom tags.

**Design:**
- `tags` table: `id`, `name`, `tag_type` (brand/equipment_type/custom), `created_at`
- `item_tags` junction table: `item_id`, `tag_id`, `created_at`
- Tag management API with CRUD operations
- Item search by multiple tags
- Tag suggestions based on existing usage

**API Endpoints:**
```
POST   /tags              # Create tag
GET    /tags              # List tags
GET    /tags/{id}         # Get tag
PUT    /tags/{id}         # Update tag
DELETE /tags/{id}         # Delete tag
POST   /items/{item_id}/tags      # Add tag to item
DELETE /items/{item_id}/tags/{tag_id}  # Remove tag
GET    /items/search?tags=tag1,tag2  # Search by tags
```

### 2. Decimal Quantity Support
**Purpose:** Support fractional quantities for operations (e.g., 1.5 kg, 0.75 liters).

**Current State:**
- Database: `operation_lines.qty` is `Numeric(18,3)` (already supports decimals)
- Schema: `OperationLineCreate.qty` is `int` (needs update)

**Changes Required:**
1. Update `app/schemas/operation.py`:
   - Change `qty: int` to `qty: Decimal` in `OperationLineCreate`
   - Update validation to handle decimal values
   - Maintain backward compatibility with alias

2. Update business logic:
   - Ensure decimal arithmetic in balance calculations
   - Update quantity validation rules

### 3. Operation Date Flexibility
**Purpose:** Allow operations to be backdated or scheduled for specific dates.

**Current State:**
- Model has `effective_at: datetime | None` field
- Currently optional with no validation

**Enhancements:**
1. **Validation Rules:**
   - `effective_at` cannot be in future (configurable)
   - Default to `created_at` if not provided
   - Allow historical dates for corrections

2. **Business Logic:**
   - Operations sequenced by `effective_at` for balance calculations
   - Historical operation support with proper auditing

3. **API Changes:**
   - Enhanced filtering: `?effective_after=...&effective_before=...`
   - Required `effective_at` for certain operation types

### 4. Repository of Issued Items/Operations
**Purpose:** Track issued items with return dates, status, and reporting.

**Design:**
- `issued_items` table: links to `operation_lines`, tracks recipient, dates, status
- Automatic creation when ISSUE operations are submitted
- Return tracking and overdue notifications
- Comprehensive reporting

**API Endpoints:**
```
GET    /issued                    # List issued items
GET    /issued/{id}               # Get issued item details
POST   /issued/{id}/return        # Mark as returned
GET    /issued/reports/overdue    # Overdue items report
GET    /issued/reports/summary    # Issuance summary
```

### 5. Document Generation System
**Purpose:** Generate printable documents for operations, reports, and invoices.

**Design:**
- **Templates:** Jinja2 HTML templates stored in database/filesystem
- **Generation:** HTML → PDF using WeasyPrint or similar
- **Storage:** `documents` table with JSON content and file references
- **Types:** Waybills, issue slips, inventory reports, balance sheets

**API Endpoints:**
```
POST   /documents/generate        # Generate document
GET    /documents/{id}            # Get generated document
GET    /documents/templates       # List templates
POST   /documents/templates       # Upload template
GET    /operations/{id}/documents # Get operation documents
```

## Database Migration Plan

### Migration 001: Tagging System
```sql
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    tag_type VARCHAR(50) NOT NULL DEFAULT 'general',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE item_tags (
    item_id UUID NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (item_id, tag_id)
);
```

### Migration 002: Document System
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_type VARCHAR(50) NOT NULL,
    template_name VARCHAR(100),
    title VARCHAR(255) NOT NULL,
    content JSONB,
    file_path VARCHAR(500),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generated_by_user_id UUID REFERENCES users(id),
    site_id UUID REFERENCES sites(id)
);

CREATE TABLE document_operations (
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    operation_id UUID NOT NULL REFERENCES operations(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, operation_id)
);
```

### Migration 003: Issued Items Tracking
```sql
CREATE TABLE issued_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation_line_id BIGINT NOT NULL REFERENCES operation_lines(id),
    issued_to_user_id UUID REFERENCES users(id),
    issued_to_name VARCHAR(255),
    expected_return_date TIMESTAMPTZ,
    actual_return_date TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL DEFAULT 'issued',
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Implementation Roadmap

### Phase 1: Foundation (2 weeks)
1. Database migrations and model updates
2. Decimal quantity support implementation
3. Basic testing infrastructure

### Phase 2: Core Features (2 weeks)
4. Tagging system implementation
5. Operation date enhancements
6. API integration for new features

### Phase 3: Business Features (2 weeks)
7. Issued items repository
8. Document generation system
9. Reporting and search functionality

### Phase 4: Integration & Testing (2 weeks)
10. Comprehensive testing
11. Performance optimization
12. Documentation and deployment

## Technical Considerations

### Backward Compatibility
- Decimal quantity: Maintain alias support for `int` during transition
- API versioning: Consider `/v2/` endpoints for breaking changes
- Data migration: Plan for existing integer quantities

### Performance
- Indexing strategy for tag searches
- Document generation queue for large operations
- Caching for frequently accessed documents

### Security
- Tag management permissions
- Document access controls by site
- Issued items visibility based on user roles

## Success Metrics
1. All operation types support decimal quantities
2. Tagging system used for 80% of inventory items
3. Document generation < 5 seconds per operation
4. Issued items tracking reduces lost equipment by 30%

## Next Steps
1. Review and approve this plan
2. Begin Phase 1 implementation
3. Regular progress reviews every 2 weeks
4. User acceptance testing after each phase

---
*Plan created: 2026-03-31*
*System: SyncServer Warehouse Management*
*Version: 1.0*
