# Anonymize profiles

One TOML file per application. A profile tells `jarvis` which columns hold
personal data (PDPA) and how to replace them while streaming a SQL dump.
Keys, foreign keys and every column not listed are passed through untouched.

## Format

```toml
[profile]
name   = "koha"
engine = "mysql"            # mysql | psql
description = "..."
truncate = ["sessions", ...] # tables whose rows are dropped (schema kept)
email_tld = "invalid"        # optional; fake emails: <random>@<random>.<tld>
keep = ["branches.*", "items.datelastseen"]  # optional; columns that look like PII but are kept on purpose (silences the warning)

[tables.<table>]
<column> = "<strategy>"                          # short form
<column> = { strategy = "digits", unique = true } # long form

[tables.<table>.when]        # only rewrite rows where this matches
<column> = "<value>"         # or ["v1", "v2"]

[tables.<table>.unless]      # skip rows where this matches
<column> = ["v1", "v2"]      # e.g. borrower_attributes code = ["FACULTY"]
```

## Strategies

| strategy   | output                                              | example                        |
|------------|-----------------------------------------------------|--------------------------------|
| `name`     | 1–3 random capitalised words                        | `Apirak Ch` → `Uasdf Uiioopo`  |
| `text`     | random lowercase words, about the original length   | `note…` → `qwe rtyu iop`       |
| `email`    | `<random>@<random>.<email_tld>`                     | `uasdfasdf@asdf.invalid`       |
| `phone`    | `0` + 9 random digits                               | `0812345678`                   |
| `digits`   | random digits, same length as the original          | `6401234` → `9283710`          |
| `id`       | random lowercase letters+digits, same length        | `apirak.c` → `k2j9xq0a`        |
| `date`     | random date in the same format                      | `1990-05-01` → `1977-11-23`    |
| `ip`       | random address in 192.0.2.0/24 (TEST-NET-1)         | `192.0.2.17`                   |
| `json`     | empty JSON of the same kind (`{}` or `[]`)          |                                |
| `password` | random characters, same length and charset style as the original hash (nobody can log in) | `$2a$08$…` → `$2a$08$<random>` |
| `null`     | SQL NULL (column must be nullable)                  |                                |
| `empty`    | empty string (for NOT NULL text columns)            |                                |

Rules for every strategy:

- NULL and empty-string values stay as they are (nothing is invented).
- Values are random on every run; the same person gets different fakes in
  different tables (no cross-table consistency, by design).
- `unique = true` keeps an in-memory set and re-rolls on collision, for
  columns with a UNIQUE constraint.
- A listed column missing from the dump (older/newer app version) prints a
  warning and is skipped.

Special lookup, only `dspace.toml` uses it:

```toml
[tables.metadatavalue.by_metadata_field]   # resolves field ids from the
"eperson.firstname" = "name"               # metadataschemaregistry +
                                            # metadatafieldregistry rows
```
