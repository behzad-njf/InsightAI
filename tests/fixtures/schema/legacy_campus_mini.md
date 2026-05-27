# CampusMetrics — Database Schema (test fixture)

Minimal legacy markdown layout for parser regression tests.

## 2. Domain overview

| `accounts` | 1 | User accounts |
| `school` | 2 | School domain tables |

### 2.1 Central hub tables

| `accounts_user` | 2 | ~100 | Central user identity |
| `school_classroom` | 1 | ~50 | Classroom hub |

### 2.3 Common join patterns

**Child in classroom**
```sql
SELECT c.id, COUNT(cc.id)
FROM school_classroom c
INNER JOIN school_classroomchild cc ON cc.classroom_id = c.id
GROUP BY c.id
```

### 2.4 Table reference

<a id="table-accounts_user"></a>
### `accounts_user`

- **Schema:** `dbo`
- **Domain:** `accounts`
- **Primary key:** `id`

**Columns:**

| # | Column | Type | Nullable |
|---|--------|------|----------|
| 1 | `id` 🔑 | int | NO |
| 2 | `email` | varchar | NO |

<a id="table-school_classroom"></a>
### `school_classroom`

- **Schema:** `dbo`
- **Domain:** `school`
- **Primary key:** `id`

**Columns:**

| # | Column | Type | Nullable |
|---|--------|------|----------|
| 1 | `id` 🔑 | int | NO |
| 2 | `name` | varchar | NO |

**References (outgoing foreign keys):**

- `school_id` → `school_school.id`

<a id="table-school_classroomchild"></a>
### `school_classroomchild`

- **Schema:** `dbo`
- **Domain:** `school`
- **Primary key:** `id`

**Columns:**

| # | Column | Type | Nullable |
|---|--------|------|----------|
| 1 | `id` 🔑 | int | NO |
| 2 | `child_id` | int | NO |
| 3 | `classroom_id` | int | NO |

**References (outgoing foreign keys):**

- `child_id` → `accounts_user.id`
- `classroom_id` → `school_classroom.id`
