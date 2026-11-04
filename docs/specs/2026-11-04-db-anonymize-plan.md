# `jarvis db anonymize` Implementation Plan

> **For agentic workers:** งานนี้ทำโดย qwen workers (Musubi, `deepseek-flash`,
> `--approval-mode yolo`) ทีละ task ใน worktree `.worktrees/anonymize`
> โดย Claude เป็น coordinator: ส่ง task, review diff, รัน test, commit.
> **Worker ห้าม `git commit`, ห้าม `sudo`, ห้ามแตะไฟล์นอก worktree.**
> Steps ใช้ checkbox (`- [ ]`).

**Goal:** เพิ่มคำสั่ง `jarvis db anonymize` ที่แทนข้อมูลส่วนบุคคลใน SQL dump
(stream) หรือใน DB ที่ restore แล้ว (direct) ตาม profile TOML

**Architecture:** แพ็กเกจ `src/jarvis/anonymize/` แยกเป็น profile loader,
ตัวสร้างค่าปลอม (`Faker`), rewriter ทีละบรรทัดของ mysqldump และ pg_dump COPY,
ตัวขับ stream (format check + poison on failure), และ direct mode ที่สร้าง SQL
แล้วป้อนเข้า client. คำสั่ง CLI อยู่ใน `src/jarvis/commands/db.py`

**Tech Stack:** Python 3.12 stdlib (`tomllib`, `importlib.resources`, `random`),
typer, rich (มีอยู่แล้ว) — **ห้ามเพิ่ม dependency**. Test: pytest 8, docker
(`mariadb:11`, `postgres:16`) สำหรับ integration

**Spec:** `docs/specs/2026-11-02-db-anonymize-design.md` +
`src/jarvis/anonymize/profiles/README.md` (อ่านทั้งสองไฟล์ก่อนเริ่มทุก task)

## Global Constraints

- รัน test ด้วย system python: `python3 -m pytest …` (venv ไม่มี pytest)
- Test ใหม่ทำตามแบบ `tests/test_skill_audit.py`: `sys.path.insert(0, <repo>/src)`
- stdout = SQL เท่านั้น; ข้อความอื่นทั้งหมดไป stderr
- บรรทัดที่ไม่เกี่ยวกับตารางที่มีกฎ/truncate ต้องออกมา byte-for-byte
- ค่า NULL และ `''` คงเดิมเสมอ (ไม่ส่งเข้า `Faker`)
- ห้ามเปลี่ยน PK/FK/sequence/โครงสร้างของตารางที่ไม่ถูก truncate
- Exit codes: 0 สำเร็จ · 1 ใช้งานผิด/profile ผิด · 2 dump ผิดรูป/parse ไม่ได้ · 3 direct mode ล้มกลางทาง
- อีเมลปลอม `<random>@<random>.invalid` (ค่า `email_tld` default = `"invalid"`)
- บรรทัดท้ายรายงาน (copy ตรงตัว): `Output is pseudonymized test data — still handle under PDPA s.37.`
- ห้ามมีข้อความใดอ้างว่าข้อมูล "ปลอดภัย" หรือ "พ้น PDPA"
- Test fixtures เป็นข้อมูลสังเคราะห์เท่านั้น ห้ามใช้ dump จริง

## Review Focus

1. **Restore ล้มเพราะ escape ผิด** (Thai UTF-8, `'`, `\`, newline/tab ใน string,
   blob) → ต้อง restore ได้; ทดสอบจาก fixture ที่สร้างด้วย mysqldump/pg_dump จริง (Task 3, 8)
2. **ล้มกลางสตรีมแต่ pipeline exit 0** (psql ไม่ตั้ง `ON_ERROR_STOP`, ล้มระหว่าง COPY,
   `\restrict` ของ pg_dump รุ่นใหม่) → pipeline restore ต้อง exit ≠ 0 (Task 6, 8)
3. **UNIQUE ชนใน direct mode** ค่าสุ่มใหม่ชนค่าเดิมของแถวที่ยังไม่ถูกแก้ → two-pass (Task 7, 8)
4. **Unique ค่าสั้นหมด space** (`digits` ยาว 4 หลัก 20,000 แถว) → ต้องขยายความยาว
   ภายใต้ `varchar(n)` ไม่ใช่วนไม่จบ (Task 2)
5. **binary ใช้ profile ไม่ได้** (PyInstaller ไม่ได้ bundle TOML) → โหลดผ่าน
   `importlib.resources` + `jarvis.spec` datas (Task 1)

---

## File Structure

| ไฟล์ | หน้าที่ |
|---|---|
| `src/jarvis/anonymize/__init__.py` | แพ็กเกจ (ว่าง) |
| `src/jarvis/anonymize/errors.py` | `ProfileError`, `DumpFormatError` |
| `src/jarvis/anonymize/profile.py` | dataclasses + load/validate/list profiles |
| `src/jarvis/anonymize/strategies.py` | `Faker` สร้างค่าปลอมทุก strategy + unique |
| `src/jarvis/anonymize/report.py` | `Report`, `TableStats`, render ไป stderr |
| `src/jarvis/anonymize/detect.py` | regex ชื่อคอลัมน์ที่ดูเป็น PII |
| `src/jarvis/anonymize/mysql_stream.py` | `MysqlRewriter` (CREATE TABLE + extended INSERT) |
| `src/jarvis/anonymize/pg_stream.py` | `PgRewriter` (COPY blocks, by_metadata_field) |
| `src/jarvis/anonymize/stream.py` | `run_stream()` + format check + poison |
| `src/jarvis/anonymize/direct.py` | สร้าง SQL + รันผ่าน client ที่สลับได้ |
| `src/jarvis/commands/db.py` | เพิ่มคำสั่ง `anonymize` |
| `jarvis.spec`, `pyproject.toml` | bundle profiles |
| `tests/anonymize/…` | unit + docker integration tests |
| `tests/fixtures/anonymize/` | dump สังเคราะห์จาก mysqldump/pg_dump จริง |

---

### Task 1: Profile loader + packaging

**Files:**
- Create: `src/jarvis/anonymize/__init__.py`, `src/jarvis/anonymize/errors.py`, `src/jarvis/anonymize/profile.py`
- Modify: `jarvis.spec` (datas เพิ่ม `('src/jarvis/anonymize/profiles', 'jarvis/anonymize/profiles')`), `pyproject.toml` (`[tool.setuptools.package-data] "jarvis.anonymize" = ["profiles/*.toml", "profiles/*.md"]`)
- Test: `tests/anonymize/test_profile.py`

**Interfaces:**
- Produces:
  ```python
  # errors.py
  class ProfileError(ValueError): ...
  class DumpFormatError(Exception): ...
  # profile.py
  STRATEGIES: frozenset[str]  # name text email phone digits id date ip json password null empty
  @dataclass(frozen=True) class Rule: strategy: str; unique: bool = False
  @dataclass(frozen=True) class TableRules:
      columns: dict[str, Rule]; when: dict[str, frozenset[str]]
      unless: dict[str, frozenset[str]]; by_metadata_field: dict[str, Rule]
  @dataclass(frozen=True) class Profile:
      name: str; engine: str; description: str; truncate: frozenset[str]
      email_tld: str; tables: dict[str, TableRules]
  def load_profile(name: str | None = None, path: Path | None = None) -> Profile
  def list_profiles() -> list[Profile]
  ```
- `load_profile` อ่านไฟล์ที่ติดมาผ่าน `importlib.resources.files("jarvis.anonymize") / "profiles" / f"{name}.toml"`; ต้องได้ `name` หรือ `path` อย่างใดอย่างหนึ่ง
- ค่า `when` เป็น string เดียวหรือ list → เก็บเป็น frozenset; `unless` เหมือนกัน

- [ ] **Step 1: เขียน test ที่ fail**

  - `test_all_bundled_profiles_load` — `list_profiles()` คืน 4 ตัว ชื่อ `{"koha","dspace","room_reservation","linebrarian"}`; engine ของ koha = `"mysql"` ที่เหลือ `"psql"`
  - `test_rule_short_and_long_form` — koha `borrowers.surname == Rule("name")`, `borrowers.cardnumber == Rule("digits", unique=True)`
  - `test_when_unless_and_metadata` — koha `additional_field_values.when == {"record_table": frozenset({"borrowers"})}`; koha `borrower_attributes.unless == {"code": frozenset()}`; dspace `metadatavalue.by_metadata_field["eperson.firstname"] == Rule("name")`
  - `test_truncate_and_tld` — `"sessions" in koha.truncate`; `koha.email_tld == "invalid"`
  - `test_unknown_strategy_rejected` — ไฟล์ tmp มี `x = "bogus"` → `ProfileError` ที่ข้อความมี `"bogus"`
  - `test_bad_engine_rejected` — `engine = "oracle"` → `ProfileError`
  - `test_unknown_profile_name` — `load_profile("nope")` → `ProfileError`
  - `test_neither_or_both_args` — `load_profile()` และ `load_profile("koha", path=…)` → `ProfileError`

- [ ] **Step 2: รัน `python3 -m pytest tests/anonymize/test_profile.py -v` → FAIL (import error)**
- [ ] **Step 3: Implement ตาม Interfaces และแก้ `jarvis.spec`, `pyproject.toml`**
- [ ] **Step 4: รันซ้ำ → PASS ทั้งหมด; `python3 -m pytest tests -q` → test เดิม 48 ตัวยังผ่าน**
- [ ] **Step 5: Commit** `feat(anonymize): profile loader and packaging`

---

### Task 2: Faker (strategies)

**Files:**
- Create: `src/jarvis/anonymize/strategies.py`
- Test: `tests/anonymize/test_strategies.py`

**Interfaces:**
- Consumes: `Rule` (Task 1)
- Produces:
  ```python
  class Faker:
      def __init__(self, rng: random.Random | None = None, email_tld: str = "invalid") -> None
      def fake(self, rule: Rule, original: str, *, key: str, max_len: int | None = None) -> str | None
  ```
  คืน `None` = SQL NULL. `key` = `"table.column"` ใช้แยก set ของ unique.
  ผู้เรียกรับประกันว่า `original` ไม่ใช่ NULL และไม่ใช่ `''`

รูปแบบผลลัพธ์ (ตาราง README เป็นหลัก) เพิ่มเติมที่ต้อง pin:
- `name`: 1–3 คำ แต่ละคำ 3–10 ตัว `[A-Z][a-z]+`
- `text`: คำตัวเล็ก 2–8 ตัว คั่นช่องว่าง ยาวรวม ≈ `min(len(original), 200)` (อย่างน้อย 1 คำ)
- `email`: `[a-z]{6,12}@[a-z]{4,10}.<tld>`
- `phone`: `"0"` + 9 หลัก
- `digits`: ตัวเลขยาวเท่า `len(original)`; `id`: `[a-z0-9]` ยาวเท่า `len(original)`
- `date`: ถ้า original ตรง `^\d{4}-\d{2}-\d{2}` (มีเวลาต่อท้ายได้) → สุ่มปี 1950–2005 คงส่วนเวลาเดิม; `0000-00-00…` → คืนค่าเดิม; parse ไม่ได้ → `YYYY-MM-DD` สุ่ม
- `ip`: `192.0.2.<1-254>`
- `json`: `"[]"` ถ้า original.lstrip() ขึ้นต้น `[` มิฉะนั้น `"{}"`
- `password`: คงทุกอย่างจนถึง `$` ตัวสุดท้าย (รวม `$`); ส่วนที่เหลือสุ่มจาก alphabet เดิม: ถ้าเป็น hex ล้วน → hex ตัวเล็ก; ถ้าเป็นชุด bcrypt (`./A-Za-z0-9`) → ชุดนั้น; มิฉะนั้น `[A-Za-z0-9+/]`; ความยาวเท่าเดิม
- `null` → `None`; `empty` → `""`
- `max_len`: ตัดผลลัพธ์ไม่ให้ยาวเกิน (ไม่ตัด `email` ให้เสีย `@` — ถ้าเกินให้ย่อ local/domain part)
- `unique`: เก็บ set ต่อ `key`; ชนให้สุ่มใหม่ ≤ 20 ครั้ง แล้วเพิ่มความยาว 1 ตัว (ไม่เกิน `max_len`); ถ้าเต็ม `max_len` แล้วยังชน → `DumpFormatError`

- [ ] **Step 1: เขียน test ที่ fail** (ใช้ `random.Random(1)`)
  - `test_name_shape` — 100 ครั้ง ตรง `^[A-Z][a-z]{2,9}( [A-Z][a-z]{2,9}){0,2}$`
  - `test_email_shape` — ตรง `^[a-z]{6,12}@[a-z]{4,10}\.invalid$`; Faker(email_tld="net") → ลงท้าย `.net`
  - `test_phone_digits_id` — phone `^0\d{9}$`; digits ของ `"6401234"` ยาว 7 ตัวเลข ≠ เดิม; id ของ `"apirak.c"` ตรง `^[a-z0-9]{8}$`
  - `test_date_variants` — `"1990-05-01"` → `^\d{4}-\d{2}-\d{2}$` ปี 1950–2005; `"1990-05-01 10:11:12"` ลงท้าย `" 10:11:12"`; `"0000-00-00"` คงเดิม; `"c. 1980"` → `^\d{4}-\d{2}-\d{2}$`
  - `test_json_ip_null_empty` — `'[{"id":1}]'`→`"[]"`; `'{"a":1}'`→`"{}"`; ip ขึ้นต้น `"192.0.2."`; null→`None`; empty→`""`
  - `test_password_bcrypt` — `"$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO"` → ขึ้นต้น `"$2a$08$"` ยาว 60 ส่วนท้ายตรง `^[./A-Za-z0-9]{53}$` และ ≠ เดิม
  - `test_password_django` — `"pbkdf2_sha256$870000$abc$XYZ="` → ขึ้นต้น `"pbkdf2_sha256$870000$abc$"` ยาวเท่าเดิม
  - `test_password_hex` — hex 128 ตัว (DSpace) → hex ตัวเล็ก 128 ตัว ≠ เดิม
  - `test_max_len` — `text` ของสตริงยาว 500 กับ `max_len=30` → `len <= 30`; `email` กับ `max_len=20` → ยังตรง `@.+\.invalid$` และ `len <= 20`
  - `test_unique_grows` — `Rule("digits", unique=True)`, original `"12"`, `max_len=10`, 500 ครั้ง key เดียวกัน → ไม่ซ้ำเลย, ทุกค่ายาว ≤ 10
  - `test_unique_exhausted` — original `"1"`, `max_len=1`, 11 ครั้ง → ครั้งที่ 11 ยก `DumpFormatError`
- [ ] **Step 2: รัน `python3 -m pytest tests/anonymize/test_strategies.py -v` → FAIL**
- [ ] **Step 3: Implement `Faker`**
- [ ] **Step 4: รันซ้ำ → PASS**
- [ ] **Step 5: Commit** `feat(anonymize): fake value strategies`

---

### Task 3: Fixtures จาก dump จริง (docker)

**Files:**
- Create: `tests/fixtures/anonymize/make_fixtures.sh`, `tests/fixtures/anonymize/seed_mysql.sql`, `tests/fixtures/anonymize/seed_pg.sql`
- Create (ผลจากสคริปต์, commit ด้วย): `tests/fixtures/anonymize/mysql_dump.sql`, `tests/fixtures/anonymize/pg_dump.sql`
- Create: `tests/anonymize/conftest.py` (fixture `docker_available`, marker `docker`)

**Interfaces:**
- Produces: path constants `MYSQL_DUMP`, `PG_DUMP` (ใน `conftest.py`); fixture `mariadb_container` / `pg_container` (scope=session) ที่คืน `list[str]` คำสั่ง client เช่น `["docker","exec","-i",name,"mariadb","-uroot","-ptest"]` และ `["docker","exec","-i",name,"psql","-U","postgres","-v","ON_ERROR_STOP=1"]` + ฟังก์ชัน `create_db(client, name)`. ข้าม test (`pytest.skip`) ถ้า `docker info` ไม่ผ่าน

Seed (สังเคราะห์ทั้งหมด) ต้องมีอย่างน้อย:
- **MySQL** ตาราง `borrowers` (borrowernumber PK auto_increment, cardnumber UNIQUE varchar(32), userid UNIQUE varchar(75), surname, firstname, email, phone, dateofbirth DATE, password varchar(60), borrowernotes TEXT, sort1 varchar(80)), `borrower_attributes` (id, borrowernumber FK, code, attribute — มีแถว code `FACULTY` และ `CITIZENID` เลข 13 หลัก), `sessions` (id, a_session LONGBLOB), `issues` (issue_id, borrowernumber FK, note TEXT — ไม่มีกฎ), `biblio` (ไม่มีกฎ). แถวต้องมี: ชื่อไทย `'สมชาย ใจดี'`, `O'Brien`, `back\slash`, newline ในหมายเหตุ, NULL และ `''`, blob `0x00FF27` ใน sessions, วันเกิด `0000-00-00` (ปิด strict mode ตอน seed), และ ≥ 3000 แถว borrowers เพื่อให้ extended INSERT ยาวมากและแตกหลาย statement
- **PG** ตาราง `eperson` (uuid PK, email UNIQUE varchar(64), netid UNIQUE, password varchar(128) hex, salt varchar(32) hex, session_salt), `metadataschemaregistry`, `metadatafieldregistry`, `metadatavalue` (eperson.firstname/lastname + dc.title ที่ต้องไม่ถูกแก้ + dc.contributor.author ที่ต้องไม่ถูกแก้), `booking_patron` (uuid PK, patron_id UNIQUE, name, email, phone), `booking_booking` (uuid, patron_id uuid FK, attendance_list jsonb, reason_description text), `booking_actionlog` (ip_address inet, details jsonb) และ `django_session`. แถวต้องมี: Thai, tab และ newline ใน text, backslash, NULL vs `''`
- สคริปต์: start `mariadb:11` / `postgres:16` ชั่วคราว → seed → `mariadb-dump --databases`-ไม่ใช้ (dump DB เดียวแบบ default ของ `jarvis db mysqldump`: ไม่มี `--complete-insert`) และ `pg_dump` plain → เขียนไฟล์ → ลบ container

- [ ] **Step 1: เขียน seed + `make_fixtures.sh`**
- [ ] **Step 2: รัน `bash tests/fixtures/anonymize/make_fixtures.sh` → ได้ไฟล์ dump สองไฟล์**
- [ ] **Step 3: ตรวจ** `grep -c "^INSERT INTO \`borrowers\`" mysql_dump.sql` ≥ 2; `grep -n "^COPY public.eperson" pg_dump.sql` มี 1; จดใน commit message ว่าบรรทัดแรกๆ ของ pg_dump มี `\restrict` หรือไม่
- [ ] **Step 4: `conftest.py` + test `test_fixtures_exist` (ไม่ต้องใช้ docker) → PASS**
- [ ] **Step 5: Commit** `test(anonymize): synthetic dump fixtures from real mysqldump/pg_dump`

---

### Task 4: MySQL rewriter + report + PII detection

**Files:**
- Create: `src/jarvis/anonymize/report.py`, `src/jarvis/anonymize/detect.py`, `src/jarvis/anonymize/mysql_stream.py`
- Test: `tests/anonymize/test_mysql_stream.py`, `tests/anonymize/test_detect.py`

**Interfaces:**
- Consumes: `Profile`, `Rule`, `TableRules` (Task 1); `Faker` (Task 2); `DumpFormatError`; `MYSQL_DUMP` (Task 3)
- Produces:
  ```python
  # detect.py
  PII_PATTERN: re.Pattern  # ตาม spec §8 (ignorecase)
  def looks_like_pii(column: str) -> bool
  # report.py
  @dataclass class TableStats: rows: int = 0; cells: int = 0; truncated_rows: int = 0
  @dataclass class Report:
      profile: str; tables: dict[str, TableStats]; missing_columns: set[tuple[str, str]]
      suspicious_columns: set[tuple[str, str]]; bytes_in: int = 0; seconds: float = 0.0
      def stats(self, table: str) -> TableStats
      def render(self, console: rich.console.Console) -> None  # จบด้วยบรรทัด PDPA ตาม Global Constraints
  # mysql_stream.py
  class MysqlRewriter:
      def __init__(self, profile: Profile, faker: Faker, report: Report) -> None
      def feed(self, line: bytes) -> bytes | None   # None = ทิ้งบรรทัด
      def finish(self) -> None                       # DumpFormatError ถ้าไม่เคยเห็น CREATE TABLE + INSERT INTO
  ```

พฤติกรรม:
- จำคอลัมน์ (ลำดับ + `max_len` จาก `varchar(n)`/`char(n)`) จาก `CREATE TABLE \`t\` (` จนถึง `) ENGINE`
- เมื่อจบ CREATE TABLE: คอลัมน์ในกฎที่ไม่มี → `report.missing_columns`; คอลัมน์ที่ `looks_like_pii` แต่ไม่มีในกฎและตารางไม่ถูก truncate → `report.suspicious_columns`
- `INSERT INTO \`t\` VALUES …;` ของตารางที่ไม่มีกฎและไม่ truncate → คืน `line` เดิม (ไม่ parse)
- ตาราง truncate → นับแถวลง `truncated_rows` แล้วคืน `None`
- `INSERT INTO \`t\` (\`a\`,…) VALUES` ของตารางที่มีกฎ → `DumpFormatError`
- INSERT ของตารางที่มีกฎแต่ไม่เคยเห็น CREATE TABLE → `DumpFormatError`
- Tokenizer ทำงานบน bytes: string `'…'` (escape `\\ \' \" \0 \n \r \Z \t` และ `''`), `NULL`, ตัวเลข, `_binary '…'`, `0x…`. cell ที่ไม่แก้ → bytes เดิมทุกตัว. cell ที่แก้ → decode UTF-8 (ถ้า decode ไม่ได้ ให้ปฏิบัติเป็นค่าที่ต้องแทน และใช้ `"x"` เป็น original), เรียก `faker.fake`, แล้ว re-escape แบบ mysqldump (`\\`, `\'`, `\n`, `\r`, `\0`, `\Z`); `None` → `NULL`
- `when`/`unless`: เทียบค่า (decoded) ของคอลัมน์ในแถวเดียวกัน
- นับ `rows`, `cells` ต่อตาราง

- [ ] **Step 1: test ที่ fail**
  - `test_detect` — `looks_like_pii` จริงกับ `email`, `B_phone`, `dateofbirth`, `line_id`, `Surname`; เท็จกับ `borrowernumber`, `biblionumber`, `title`
  - `test_passthrough_unrelated_bytes` — feed `MYSQL_DUMP` ทั้งไฟล์ผ่าน koha profile; ทุกบรรทัดที่ไม่ใช่ `INSERT INTO \`borrowers\``/`\`borrower_attributes\``/`\`sessions\`` เท่ากับ input ทุก byte
  - `test_borrowers_rewritten` — ใน output ไม่พบ `สมชาย`, `O\'Brien`, อีเมลต้นฉบับใดๆ ของ seed; จำนวน tuple ของ borrowers เท่าเดิม; borrowernumber ทุกแถวเท่าเดิมและเรียงเหมือนเดิม
  - `test_null_and_empty_kept` — แถว seed ที่ email เป็น NULL/`''` ยังเป็น `NULL`/`''`
  - `test_sessions_truncated` — ไม่มี `INSERT INTO \`sessions\``; `report.stats("sessions").truncated_rows` = จำนวนแถวใน seed
  - `test_unique_cardnumber` — cardnumber ใน output ไม่ซ้ำกันเลย
  - `test_complete_insert_rejected` — บรรทัด `` INSERT INTO `borrowers` (`borrowernumber`) VALUES (1); `` หลัง CREATE TABLE → `DumpFormatError`
  - `test_insert_without_create_rejected` — INSERT ของ borrowers โดยไม่มี CREATE → `DumpFormatError`
  - `test_finish_no_statements` — feed บรรทัด `COPY public.x (a) FROM stdin;` แล้ว `finish()` → `DumpFormatError`
  - `test_missing_and_suspicious_columns` — CREATE TABLE borrowers ที่ไม่มี `sort2` และมี `nickname_email` → `("borrowers","sort2") in missing_columns`, `("borrowers","nickname_email") in suspicious_columns`
  - `test_unless_keep_code` — profile tmp ที่ `unless code = ["FACULTY"]`: แถว `FACULTY` คงเดิม, แถว `CITIZENID` เปลี่ยน
- [ ] **Step 2: `python3 -m pytest tests/anonymize/test_mysql_stream.py tests/anonymize/test_detect.py -v` → FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: รันซ้ำ → PASS**
- [ ] **Step 5: Commit** `feat(anonymize): mysqldump rewriter, report, PII detection`

---

### Task 5: PostgreSQL COPY rewriter

**Files:**
- Create: `src/jarvis/anonymize/pg_stream.py`
- Test: `tests/anonymize/test_pg_stream.py`

**Interfaces:**
- Consumes: Task 1, 2, 4 (`Report`, `looks_like_pii`), `PG_DUMP`
- Produces:
  ```python
  class PgRewriter:
      in_copy: bool                 # อยู่ระหว่าง COPY block
      restrict_key: str | None      # จากบรรทัด `\restrict <key>` ถ้ามี
      def __init__(self, profile: Profile, faker: Faker, report: Report) -> None
      def feed(self, line: bytes) -> bytes | None
      def finish(self) -> None      # DumpFormatError ถ้าไม่เคยเห็น COPY
  ```

พฤติกรรม:
- `max_len` จาก `CREATE TABLE schema.t (` … `);` (`character varying(n)`); ชื่อตารางใช้ส่วนหลังจุด (`public.eperson` → `eperson`)
- `COPY schema.t (c1, c2) FROM stdin;` → คอลัมน์จาก header (ชื่ออาจมี `"` ครอบ); missing/suspicious เหมือน Task 4
- แถว: แยกด้วย `\t`, `\N` = NULL, unescape `\\ \t \n \r \b \f \v \ooo \xhh` ก่อนส่ง Faker, escape กลับเฉพาะ cell ที่แก้; cell ที่ไม่แก้ bytes เดิม; จบที่บรรทัด `\.`
- truncate: ทิ้งแถวข้อมูล คง header และ `\.`
- `INSERT INTO` ของตารางที่มีกฎ → `DumpFormatError` (ไม่รองรับ `--inserts`)
- `by_metadata_field`: จาก COPY `metadataschemaregistry` เก็บ `metadata_schema_id → short_id`; จาก `metadatafieldregistry` เก็บ `metadata_field_id → "short_id.element[.qualifier]"`; ในแถว `metadatavalue` ใช้ `metadata_field_id` หา rule แล้วแก้ `text_value`. เจอ COPY `metadatavalue` ก่อนมี map ทั้งสอง → `DumpFormatError`
- `restrict_key`: จับจากบรรทัด `\restrict KEY` (ส่งผ่านตามเดิม)

- [ ] **Step 1: test ที่ fail** (ใช้ dspace + room_reservation profile กับ `PG_DUMP`)
  - `test_passthrough_unrelated_bytes` — บรรทัดนอก COPY ของตารางที่มีกฎ/truncate เท่าเดิมทุก byte
  - `test_eperson_rewritten` — ไม่พบอีเมลต้นฉบับ; uuid คอลัมน์แรกของทุกแถวเท่าเดิม; email ใหม่ลงท้าย `.invalid` และไม่ซ้ำ
  - `test_metadata_field_targeting` — ค่า `eperson.firstname/lastname` เปลี่ยน; ค่า `dc.title` และ `dc.contributor.author` ไม่เปลี่ยน
  - `test_metadata_before_registry_rejected` — COPY metadatavalue ก่อน registry → `DumpFormatError`
  - `test_escapes_roundtrip` — แถวที่มี tab/newline/backslash ในคอลัมน์ที่ไม่มีกฎ: bytes เดิม; ในคอลัมน์ที่มีกฎ: ค่าใหม่ไม่มี tab/newline ดิบ
  - `test_jsonb_and_session_truncate` (room_reservation) — `attendance_list` กลายเป็น `[]`; COPY `django_session` เหลือแค่ header + `\.`
  - `test_inserts_rejected` — `INSERT INTO public.eperson VALUES (...)` → `DumpFormatError`
  - `test_restrict_key_captured` — feed `\restrict abc123` → `restrict_key == "abc123"`
- [ ] **Step 2: `python3 -m pytest tests/anonymize/test_pg_stream.py -v` → FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: รันซ้ำ → PASS**
- [ ] **Step 5: Commit** `feat(anonymize): pg_dump COPY rewriter`

---

### Task 6: Stream driver + CLI (stream mode)

**Files:**
- Create: `src/jarvis/anonymize/stream.py`
- Modify: `src/jarvis/commands/db.py` (เพิ่ม `anonymize`)
- Test: `tests/anonymize/test_stream_cli.py`

**Interfaces:**
- Consumes: Tasks 1–5
- Produces:
  ```python
  # stream.py
  POISON_SQL: bytes = b"JARVIS_ANONYMIZE_FAILED;\n"
  def run_stream(profile: Profile, inp: BinaryIO, out: BinaryIO, faker: Faker | None = None) -> Report
  ```
  ล้มด้วย `DumpFormatError` → เขียน poison ลง `out` แล้ว raise ต่อ. Poison:
  - MySQL: `b"-- jarvis db anonymize FAILED: <msg>\n" + POISON_SQL`
  - PG: ถ้า `in_copy` → `b"\\.\n"` ก่อน; ถ้า `restrict_key` → `b"\\unrestrict <key>\n"`; แล้ว `b"\\set ON_ERROR_STOP on\n"` + comment + `POISON_SQL`
- CLI (typer, ใน `db.app`):
  ```
  anonymize(-p/--profile, --profile-file, -t/--type, -d/--database, --yes, --dry-run, --list, -q/--quiet)
  ```
  stream mode: `-t/-d` ไม่ใส่ทั้งคู่; stdin เป็น TTY → exit 1 พร้อมตัวอย่าง pipeline ทาง stderr; `-t` ไม่ตรง `profile.engine` → exit 1; ใส่ `-t` หรือ `-d` อย่างเดียว → exit 1; `--list` พิมพ์ `name  engine  description` ทาง stderr exit 0. Report render ไป `Console(stderr=True)` เว้น `-q`. `DumpFormatError` → พิมพ์ข้อความ + `Hint: run the pipeline with 'set -o pipefail'` → exit 2. `ProfileError` → exit 1
  (direct mode เรียก `run_direct` จาก Task 7 — ใน task นี้ให้ `-t/-d` ครบแล้ว exit 1 ด้วยข้อความ `direct mode not implemented yet`)

- [ ] **Step 1: test ที่ fail** (เรียก CLI ด้วย `typer.testing.CliRunner` หรือ `subprocess` `python3 -m jarvis.main` + `PYTHONPATH=src`)
  - `test_stream_koha_fixture` — stdin = `MYSQL_DUMP`, `db anonymize -p koha` → exit 0; stdout ไม่มี `สมชาย`; stderr มีบรรทัด PDPA ตรงตัว
  - `test_stream_wrong_engine_input` — stdin = `PG_DUMP`, `-p koha` → exit 2; stdout ลงท้าย `POISON_SQL`
  - `test_poison_pg_inside_copy` — stdin = header COPY metadatavalue (ก่อน registry) + 1 แถว, `-p dspace` → exit 2; stdout มี `\.` ตามด้วย `\set ON_ERROR_STOP on` ก่อน `POISON_SQL`
  - `test_type_mismatch` — `-p koha -t psql -d x` → exit 1
  - `test_list` — `--list` → exit 0, stderr มีทั้ง 4 ชื่อ
  - `test_profile_file` — `--profile-file <tmp toml>` ใช้ได้; ใส่ทั้ง `-p` และ `--profile-file` → exit 1
  - `test_quiet` — `-q` แล้ว stderr ไม่มีบรรทัด PDPA
- [ ] **Step 2: `python3 -m pytest tests/anonymize/test_stream_cli.py -v` → FAIL**
- [ ] **Step 3: Implement**
- [ ] **Step 4: รันซ้ำ → PASS; `python3 -m pytest tests -q` ผ่านหมด**
- [ ] **Step 5: Commit** `feat(anonymize): jarvis db anonymize stream mode`

---

### Task 7: Direct mode

**Files:**
- Create: `src/jarvis/anonymize/direct.py`
- Modify: `src/jarvis/commands/db.py` (ต่อ `-t/-d` เข้ากับ `run_direct`)
- Test: `tests/anonymize/test_direct_sql.py`

**Interfaces:**
- Consumes: Tasks 1, 4 (`Report`, `looks_like_pii`), 6 (CLI)
- Produces:
  ```python
  @dataclass(frozen=True) class Column: name: str; data_type: str; max_len: int | None; nullable: bool
  @dataclass(frozen=True) class TableInfo: columns: dict[str, Column]; pk: tuple[str, ...]
  def default_client(engine: str, db: str) -> list[str]
      # mysql: ["sudo","mysql","--defaults-file=/etc/mysql/debian.cnf",db]
      # psql:  ["sudo","-u","postgres","psql","-v","ON_ERROR_STOP=1","-X","-q",db]
  def fetch_schema(client: list[str], engine: str, db: str) -> dict[str, TableInfo]
      # อ่าน information_schema ผ่าน client (ส่ง SQL ทาง stdin, อ่าน TSV จาก stdout: mysql -B -N, psql -A -t -F '\t')
  def build_sql(profile: Profile, engine: str, schema: dict[str, TableInfo], report: Report) -> list[str]
  def run_direct(profile: Profile, engine: str, db: str, *, client: list[str] | None = None,
                 dry_run: bool = False, assume_yes: bool = False,
                 confirm: Callable[[str], str] = input, out: TextIO = sys.stdout) -> Report
  ```
  env `JARVIS_ANON_CLIENT` (ถ้าตั้ง) = คำสั่ง client แบบ shlex-split ใช้แทน default (สำหรับ docker test)

SQL ที่ต้องสร้าง (pin):
- ตาราง/คอลัมน์ที่ไม่มีใน `schema` → ข้าม + `report.missing_columns`; คอลัมน์ PII-ish ที่ไม่มีกฎ → `report.suspicious_columns`
- truncate: psql `TRUNCATE t;` (ไม่ใช้ CASCADE; FK error ให้ล้มตามจริง); mysql ครอบทั้งไฟล์ด้วย `SET FOREIGN_KEY_CHECKS=0;` … `SET FOREIGN_KEY_CHECKS=1;`
- UPDATE ต่อคอลัมน์: `WHERE col IS NOT NULL AND col <> ''` + เงื่อนไข `when` (`AND c IN (…)`) / `unless` (`AND c NOT IN (…)`, ข้ามถ้า list ว่าง); ค่า literal escape ถูกต้องต่อ engine
- expression ต่อ strategy (ไม่ต้องหน้าตาเหมือน stream; spec §12.4): `name`/`text` = ตัวอักษรจาก md5 แปลงตัวเลขเป็นตัวอักษร (`translate`/`REPLACE` ซ้อน) ขึ้นต้นตัวใหญ่สำหรับ name; `email` = `<md5 8>@<md5 6>.<tld>`; `phone` = `'0'` + 9 หลักสุ่ม; `digits` = ตัวเลขสุ่มยาว `length(col)`; `id`/`password` = hex สุ่มยาว `length(col)` (password: คง prefix ถึง `$` สุดท้าย — psql `substring(col from '^(.*\$)')`, mysql `SUBSTRING_INDEX`); `date` = วันที่สุ่ม 1950–2005 (คอลัมน์ชนิด date/timestamp) หรือ string `YYYY-MM-DD`; `ip` = `'192.0.2.' || (1 + floor(random()*254))` (cast `::inet` ถ้า type inet); `json` = `'[]'` ถ้าค่าขึ้นต้น `[` ไม่งั้น `'{}'` (cast ตาม type); `null`/`empty`
- ทุก expression ตัดด้วย `max_len` ถ้ามี
- `unique` = **two-pass**: (1) `UPDATE t SET col = CONCAT('~', <pk text>)` (psql `'~' || pk::text`) สำหรับแถวที่ตรงเงื่อนไข; (2) `UPDATE t SET col = <random ยาว k> || <pk text เติม 0 ให้ยาวเท่า pk ที่ยาวที่สุด>` ตัดตาม `max_len` — ถ้า `k < 4` หลังเผื่อ pk → ยก `ProfileError` ตอน build; ตารางที่มี rule unique แต่ไม่มี PK → `ProfileError`
- `by_metadata_field` (psql): `UPDATE metadatavalue mv SET text_value = <expr> FROM metadatafieldregistry f JOIN metadataschemaregistry s ON s.metadata_schema_id = f.metadata_schema_id WHERE mv.metadata_field_id = f.metadata_field_id AND s.short_id = '<schema>' AND f.element = '<element>' AND f.qualifier IS [NOT DISTINCT FROM] <qualifier|NULL> AND mv.text_value IS NOT NULL AND mv.text_value <> ''`
- psql: ครอบด้วย `BEGIN;` … `COMMIT;`. mysql: ไม่มี transaction (TRUNCATE auto-commit) — ข้อความยืนยันต้องบอกว่า `MySQL changes are not transactional`
- `run_direct`: fetch_schema → ไม่มี table ใน profile เลย → `ProfileError`; build; `dry_run` → พิมพ์ SQL ลง `out` จบ; ไม่ `assume_yes` → แสดงสรุป (จำนวนตาราง truncate/update, ชื่อ DB) แล้ว `confirm("Type the database name to continue: ")` ต้องตรง `db` ไม่งั้นยกเลิก exit 1; รัน SQL ทาง stdin ของ client; client exit ≠ 0 → CLI exit 3

- [ ] **Step 1: test ที่ fail** (ใช้ `schema` ที่สร้างเองใน test, ไม่ต้องมี DB)
  - `test_mysql_truncate_and_fk_wrap` — koha: SQL แรก `SET FOREIGN_KEY_CHECKS=0;`, สุดท้าย `SET FOREIGN_KEY_CHECKS=1;`, มี `TRUNCATE \`sessions\`;`
  - `test_psql_transaction` — room_reservation: แรก `BEGIN;` สุดท้าย `COMMIT;`, ไม่มี `CASCADE`
  - `test_skip_missing_table_and_column` — schema ไม่มี `deletedborrowers` และ borrowers ไม่มี `sort2` → ไม่มี SQL อ้างถึงทั้งสอง; `("borrowers","sort2") in report.missing_columns`
  - `test_unique_two_pass` — UPDATE ของ `borrowers.cardnumber` มีสองคำสั่ง ลำดับ: คำสั่งแรกมี `'~'` คำสั่งที่สองไม่มี
  - `test_unique_without_pk_rejected` — schema ที่ `borrowers.pk == ()` → `ProfileError`
  - `test_when_unless_clauses` — `additional_field_values` มี `record_table IN ('borrowers')`; `borrower_attributes` ที่ `unless code=["FACULTY"]` มี `code NOT IN ('FACULTY')`; ถ้า list ว่างไม่มี `NOT IN`
  - `test_metadata_field_update` — dspace: มี `s.short_id = 'eperson'` และ `f.element = 'firstname'`
  - `test_literal_escaping` — `unless code=["O'X"]` → mysql `'O\'X'` หรือ `'O''X'` (เลือกหนึ่งแบบให้ถูกต่อ engine), psql `'O''X'`
  - `test_run_direct_confirm_mismatch` — `confirm=lambda _: "wrong"` → ไม่เรียก client (ใช้ client = `["false"]` แล้วตรวจว่าไม่ถูกเรียก), CLI exit 1
  - `test_dry_run_prints_sql` — `dry_run=True` → `out` มี `UPDATE`, ไม่เรียก client
- [ ] **Step 2: `python3 -m pytest tests/anonymize/test_direct_sql.py -v` → FAIL**
- [ ] **Step 3: Implement + ต่อ CLI**
- [ ] **Step 4: รันซ้ำ → PASS; ทั้ง `tests` ผ่าน**
- [ ] **Step 5: Commit** `feat(anonymize): direct mode (UPDATE in place)`

---

### Task 8: Docker integration tests

**Files:**
- Create: `tests/anonymize/test_integration_docker.py` (ทุก test ติด `@pytest.mark.docker`, skip ถ้าไม่มี docker)
- Modify: `pyproject.toml` หรือ `tests/anonymize/conftest.py` — register marker `docker`

**Interfaces:**
- Consumes: ทุก task; container fixtures จาก Task 3

- [ ] **Step 1: เขียน test**
  - `test_mysql_stream_restore` — `MYSQL_DUMP` → `run_stream(koha)` → ป้อนเข้า DB ใหม่ใน mariadb → client exit 0; `SELECT COUNT(*) FROM borrowers` = จำนวน seed; `COUNT(DISTINCT cardnumber)` = จำนวนแถวที่ cardnumber ไม่ว่าง; ไม่มีแถวที่ `surname = 'สมชาย'`-ต้นฉบับ; `SELECT COUNT(*) FROM issues i JOIN borrowers b USING(borrowernumber)` = จำนวน issues ใน seed; `sessions` ว่าง
  - `test_pg_stream_restore` — `PG_DUMP` → `run_stream(dspace)` และ `run_stream(room_reservation)` (ตาม fixture) → restore ด้วย `ON_ERROR_STOP=1` → exit 0; อีเมล eperson ลงท้าย `.invalid`; `dc.title` เท่าเดิม; FK `booking_booking.patron_id` join ครบ
  - `test_mysql_poison_fails_pipeline` — ตัด `MYSQL_DUMP` ครึ่งทางแล้วต่อด้วย `` INSERT INTO `borrowers` (`x`) VALUES (1); `` → `run_stream` ยก error; ป้อน output ที่ได้เข้า mariadb client → exit ≠ 0
  - `test_pg_poison_fails_pipeline` — ทำให้ล้มระหว่าง COPY (metadatavalue ก่อน registry) → ป้อนเข้า `psql` **ไม่ตั้ง** `ON_ERROR_STOP` (แบบ `jarvis db psql`) → exit ≠ 0
  - `test_mysql_direct_mode` — restore `MYSQL_DUMP` ดิบลง DB ใหม่ → `run_direct(koha, client=<docker client>, assume_yes=True)` → ไม่ error; borrowers นับแถวเท่าเดิม, cardnumber ไม่ซ้ำ, ไม่มีชื่อต้นฉบับ, sessions ว่าง
  - `test_pg_direct_mode` — เหมือนกันกับ `PG_DUMP` + dspace profile
- [ ] **Step 2: `python3 -m pytest tests/anonymize/test_integration_docker.py -v -m docker` → แก้จนผ่าน** (bug ที่เจอให้แก้ใน module เจ้าของ พร้อม unit test ที่ pin bug นั้น; แก้ profile TOML ได้ตาม spec §12.6 พร้อมเหตุผล)
- [ ] **Step 3: `python3 -m pytest tests -q` ผ่านทั้งหมด**
- [ ] **Step 4: Commit** `test(anonymize): docker restore round-trip and poison pipeline`

---

### Task 9: Performance + docs

**Files:**
- Create: `tests/anonymize/bench_stream.py` (สคริปต์, ไม่ใช่ test)
- Modify: `README.md` (ตาราง `db` เพิ่มแถว `jarvis db anonymize` + ตัวอย่าง pipeline ทั้งสองแบบ + บรรทัดเตือน PDPA s.37)

- [ ] **Step 1: bench** — สร้าง dump ~200 MB โดยทวีคูณ INSERT ของ `MYSQL_DUMP` (เปลี่ยน borrowernumber/cardnumber/userid ไม่ให้ซ้ำ) ใน scratch dir; `python3 tests/anonymize/bench_stream.py` พิมพ์ MB/s ทั้งแบบ koha (มีกฎ) และ passthrough
- [ ] **Step 2: ต้องได้ ≥ 20 MB/s** สำหรับ passthrough และรายงานตัวเลขของ koha; ถ้าไม่ถึง ให้ optimize (เช่น เช็ค prefix bytes ก่อน regex) แล้ววัดใหม่
- [ ] **Step 3: แก้ README**
- [ ] **Step 4: `python3 -m pytest tests -q` ผ่าน**
- [ ] **Step 5: Commit** `docs(anonymize): README usage and benchmark script`
