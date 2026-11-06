# `jarvis db anonymize` — Design

Date: 2026-11-02 · Branch: `feat/anonymize` · Status: draft for review

## 1. Intent / ทำไมต้องมี

Dev และ tester ต้องใช้ฐานข้อมูลจาก production (Koha, DSpace, room-reservation,
linebrarian) เพื่อทดสอบ แต่ข้อมูลมีข้อมูลส่วนบุคคลตาม PDPA (ชื่อ นามสกุล อีเมล
เบอร์โทร เลขบัตร ฯลฯ) เครื่องมือนี้แทนค่าข้อมูลส่วนบุคคลด้วยค่าสุ่ม **ระหว่างทาง**
ก่อนข้อมูลถึงเครื่อง dev โดยไม่แตะความสัมพันธ์ของข้อมูล ระบบจึงยังทำงานได้

```bash
pv dump.sql.gz | gunzip | jarvis db anonymize -p koha   | jarvis db mysql koha_spu
pv dump.sql.gz | gunzip | jarvis db anonymize -p dspace | jarvis db psql dspace8_nalt
jarvis db anonymize -p koha   -t mysql -d koha_spu       # แก้ใน DB ที่ restore แล้ว
jarvis db anonymize -p dspace -t psql  -d dspace8_spu
```

ข้อสังเกตทางกฎหมาย (จาก research PDPA): ผลลัพธ์เป็น pseudonymization ไม่ใช่
anonymization เต็มรูปแบบ (ประวัติการยืม/วันที่ยังอยู่) dump ที่ได้ยังต้องดูแลตาม
มาตรา 37 — ห้ามเขียนในเอกสาร/ข้อความ CLI ว่า "พ้น PDPA แล้ว"

## 2. Goals

1. Stream mode: อ่าน SQL dump จาก stdin เขียน dump ที่ anonymize แล้วออก stdout
   restore ได้ทันทีด้วย `jarvis db mysql` / `jarvis db psql`
2. Direct mode: `-t mysql|psql -d DB` รัน UPDATE/TRUNCATE ใน DB ที่ restore แล้ว
3. Profiles สำเร็จรูป 4 ตัว: `koha` (mysql), `dspace` (psql, DSpace 7–10),
   `room_reservation` (psql), `linebrarian` (psql) — มีแล้วใน
   `src/jarvis/anonymize/profiles/` (ดู README ในโฟลเดอร์นั้นสำหรับรูปแบบไฟล์
   และ strategy ทั้งหมด)
4. ผู้ใช้เพิ่ม profile เองได้ด้วย `--profile-file PATH`
5. รายงานสรุปทาง stderr ทุกครั้ง

## 3. Non-goals

- ค่าปลอมไม่ต้องตรงกันข้ามตาราง/ข้าม DB/ข้ามรอบ (สุ่มใหม่ทุกครั้ง, ไม่ต้องห่วง login)
- ไม่ต้องย้อนกลับได้ ไม่เก็บ mapping
- ไม่รองรับ pg_dump custom/directory format, `pg_dump --inserts`,
  `mysqldump --complete-insert` ในรอบนี้
- ไม่ scrub ข้อความอิสระในคอลัมน์ที่ไม่ได้อยู่ใน profile (ไม่ทำ regex/NER)
- ไม่จัดการไฟล์ media, Solr, assetstore
- Profile อื่น (nida-resource-reservation, autocat, …) ไม่อยู่ในรอบนี้

## 4. Anti-goals (ถ้าเกิดถือว่าล้มเหลว แม้จะ "ทำงานได้")

- PK / FK / sequence (`setval`, `AUTO_INCREMENT`) / โครงสร้างตารางเปลี่ยน
- Output restore ไม่ผ่าน (escape ผิด, JSON เสีย, ชน UNIQUE)
- ค่าจริงหลุดในคอลัมน์ที่ profile ระบุไว้
- Parse ส่วนของตารางที่ต้องแก้ไม่ได้ แล้วส่งค่าเดิมผ่านไปเงียบๆ → ต้อง exit ≠ 0
  (fail-closed เฉพาะตารางที่มีกฎ/อยู่ใน truncate; ตารางอื่นส่งผ่าน byte-for-byte)
- ข้อความใดๆ อ้างว่าข้อมูล "ปลอดภัย/พ้น PDPA"

## 5. Decisions (ตัดสินใจกับผู้ใช้แล้ว)

| เรื่อง | ตัดสินใจ |
|---|---|
| ชื่อคำสั่ง | `jarvis db anonymize` (ใน `src/jarvis/commands/db.py` group เดิม) |
| เลือก profile | ต้องใส่ `-p` ทุกครั้ง, ไม่ auto-detect |
| Direct mode | UPDATE/TRUNCATE ใน DB ที่ restore แล้ว; ถามให้พิมพ์ชื่อ DB ยืนยัน, `--yes` ข้าม |
| ขอบเขต profile | 4 ตัว + `--profile-file` |
| คอลัมน์ไม่รู้จักที่ชื่อดูเป็น PII | เตือนทาง stderr แล้วทำต่อ, สรุปในรายงาน |
| อีเมลปลอม | `<random>@<random>.invalid` |
| รหัสผ่าน | สุ่ม (ไม่มีใคร login ด้วยรหัสเดิมได้, ไม่มี dev password) |
| ค่าสุ่ม | สุ่มใหม่ทุกครั้ง ไม่ต้อง consistent; จำนวนคำ/ความยาวไม่ต้องเท่าเดิม (ยกเว้น strategy ที่ระบุ) |
| ขนาด dump | < 5 GB หลัง gunzip |
| รูปแบบ dump | mysqldump default (extended INSERT ไม่มีชื่อคอลัมน์) และ pg_dump plain (`COPY … FROM stdin`) |
| Koha `sort1/sort2`, `borrower_attributes` | สุ่มทั้งหมด; profile มี `keep_codes` สำหรับ attribute code ที่ไม่ใช่ PII |
| จบงาน | commit บน `feat/anonymize` รอ review — ไม่ merge, ไม่ bump version, ไม่ build |

## 6. CLI

```
jarvis db anonymize -p PROFILE [--profile-file PATH] [-q]
jarvis db anonymize -p PROFILE -t {mysql|psql} -d DATABASE [--yes] [--dry-run]
jarvis db anonymize --list
```

- `-p` ชื่อ profile ที่ติดมากับ jarvis; `--profile-file` ใช้ไฟล์ TOML ภายนอกแทน
  (ต้องระบุอย่างใดอย่างหนึ่ง)
- `-t` ต้องตรงกับ `profile.engine` ไม่ตรง → error
- ไม่มี `-t/-d` = stream mode; stdin เป็น TTY → error พร้อมตัวอย่างการใช้
- `--list` แสดง profile ที่มีพร้อม engine/description
- `--dry-run` (direct mode) พิมพ์ SQL ที่จะรันแทนการรัน
- `-q` ปิดรายงาน (เหลือแค่ error)
- stdout ใช้สำหรับ SQL เท่านั้น; ทุกข้อความอื่นไป stderr

Exit codes: 0 สำเร็จ · 1 ใช้งานผิด/profile ผิด · 2 parse ไม่ได้/ข้อมูลผิดรูป ·
3 direct mode ล้มเหลวกลางทาง

## 7. Profiles

รูปแบบไฟล์ และ strategy อยู่ใน `src/jarvis/anonymize/profiles/README.md`
(ถือเป็นส่วนหนึ่งของ spec นี้) สรุป:

- `[profile]`: `name`, `engine`, `description`, `truncate = [...]`, `email_tld`
- `[tables.<t>]`: `<column> = "<strategy>"` หรือ `{ strategy, unique }`
- `[tables.<t>.when]`: แก้เฉพาะแถวที่คอลัมน์ตรงค่า (เช่น `record_table = "borrowers"`)
- `[tables.<t>.unless]`: ข้ามแถวที่คอลัมน์ตรงค่า — ใช้กับ
  `borrower_attributes` แบบ `code = []` (= keep_codes, ค่าเริ่มต้นว่าง)
- `[tables.metadatavalue.by_metadata_field]` (DSpace) — map
  `schema.element[.qualifier]` → strategy โดยอ่าน id จาก
  `metadataschemaregistry` + `metadatafieldregistry` ในสตรีมเดียวกัน

Strategies: `name text email phone digits id date ip json password null empty`
(นิยามในตาราง README). กติการ่วม: ค่า NULL และ `''` คงเดิม; `unique = true` →
เก็บ set ในหน่วยความจำและสุ่มใหม่เมื่อชน; ต้องเคารพความยาวคอลัมน์
(`varchar(n)`) — ถ้า strategy สร้างค่ายาวกว่า n ให้ตัด

Validation ตอนโหลด profile: strategy ไม่รู้จัก, engine ผิด, key แปลก → exit 1
ก่อนอ่าน stdin

Profile ที่ติดมาต้องถูก bundle เข้า PyInstaller binary (`jarvis.spec` datas)
และอ่านผ่าน `importlib.resources`

## 8. Stream mode

อ่านเป็นบรรทัดแบบ bytes (`sys.stdin.buffer`), เขียน `sys.stdout.buffer`
บรรทัดที่ไม่เกี่ยวกับตารางที่มีกฎหรือ truncate → ส่งผ่าน **byte-for-byte**

### MySQL (mysqldump default)

- จำ column order จาก `CREATE TABLE \`t\` (` … `)` ที่มาก่อน INSERT ของตารางนั้น
- `INSERT INTO \`t\` VALUES (…),(…);` — tokenizer ต้องรองรับ: string `'…'`
  พร้อม escape `\\ \' \" \0 \n \r \Z \t` และ `''`, `NULL`, ตัวเลข, `_binary '…'`,
  `0x…` hex, วงเล็บ/คอมมาภายใน string. แก้เฉพาะ cell ของคอลัมน์ในกฎ แล้ว
  re-escape แบบเดียวกับ mysqldump
- INSERT ของตารางที่ไม่มี CREATE TABLE ให้เห็น แต่มีกฎ → exit 2
- truncate: ตัดบรรทัด INSERT ของตารางนั้นทิ้ง (CREATE/LOCK/ALTER คงไว้)
- string ใน dump อาจไม่ใช่ UTF-8 (blob) → ประมวลผลเป็น bytes หรือ
  decode ด้วย `surrogateescape`; cell ที่ไม่แก้ต้องออกมาเหมือนเดิมทุก byte

### PostgreSQL (pg_dump plain)

- `COPY schema.t (c1, c2, …) FROM stdin;` → column order จาก header
- แถวข้อมูล: tab-separated, `\N` = NULL, escape `\\ \t \n \r \b \f \v` และ
  `\ooo`/`\xhh`; จบด้วยบรรทัด `\.`
- truncate: ตัดแถวข้อมูลทิ้ง คง header และ `\.`
- `json`/`jsonb`: strategy `json` → `{}` หรือ `[]` ตามตัวแรกของค่าเดิม
- `inet` → strategy `ip` (TEST-NET-1) หรือ `null`
- DSpace `by_metadata_field`: เก็บ map จาก `metadataschemaregistry`
  (`metadata_schema_id → short_id`) และ `metadatafieldregistry`
  (`metadata_field_id → schema.element.qualifier`) ระหว่างสตรีม
  (pg_dump เรียง data ตามชื่อตาราง → สองตารางนี้มาก่อน `metadatavalue`)
  ถ้าเจอ `metadatavalue` ก่อนได้ map → exit 2

### ตารางที่ไม่รู้จัก / คอลัมน์ที่หายไป

- คอลัมน์ใน profile แต่ไม่มีใน dump (ต่างเวอร์ชัน) → เตือนครั้งเดียวต่อคอลัมน์
- คอลัมน์ที่ไม่อยู่ใน profile และชื่อ match regex PII
  (`mail|phone|mobile|tel|fax|surname|lastname|firstname|first_name|last_name|
  address|birth|dob|passport|citizen|national|id_card|line_id`, ไม่สนตัวพิมพ์)
  และตารางนั้นไม่ได้ถูก truncate → เตือน, ทำต่อ

### รายงาน (stderr, ตอนจบ)

profile, เวลา, MB/s; ต่อตาราง: แถวที่เห็น / cell ที่แก้ / แถวที่ truncate;
คำเตือนคอลัมน์หาย; คำเตือนคอลัมน์ที่ดูเป็น PII; บรรทัดท้าย:
"Output is pseudonymized test data — still handle under PDPA s.37."

### Performance

< 5 GB; เป้า ≥ 20 MB/s บนเครื่องนี้ (Python ล้วน, ไม่มี dependency ใหม่)
บรรทัดที่ไม่เกี่ยวต้องไม่ถูก parse

## 9. Direct mode

- ตรวจว่า DB มีอยู่, ถามให้พิมพ์ชื่อ DB (ไม่ตรง → ยกเลิก), `--yes` ข้าม
- รันผ่าน client เดิม: `sudo mysql --defaults-file=/etc/mysql/debian.cnf DB` /
  `sudo -u postgres psql DB` (ป้อน SQL ทาง stdin, `ON_ERROR_STOP=1` สำหรับ psql)
- สร้าง SQL ต่อกฎ: `TRUNCATE` (psql: ไม่ใช้ `CASCADE`; mysql: ปิด
  `FOREIGN_KEY_CHECKS` ชั่วคราว) และ `UPDATE t SET col = <expr> WHERE col IS NOT
  NULL AND col <> ''` (+ เงื่อนไข when/unless)
- ค่าสุ่มสร้างฝั่ง SQL (`RAND()/MD5` ใน MySQL, `random()/md5` ใน PG) —
  ตารางไม่มี PK ก็ทำได้ (`deletedborrowers`)
- คอลัมน์ `unique`: ต้องไม่ชน — ผู้สร้างเลือกวิธีเอง (เช่น ผสม row number
  หรือ 2-pass) ขอแค่ไม่ fail และไม่เหลือค่าเดิม
- `by_metadata_field`: UPDATE … FROM join registry tables
- ตาราง/คอลัมน์ที่ไม่มีใน DB → ข้ามพร้อมเตือน (อ่านจาก information_schema)
- ทำทั้งหมดใน transaction เดียวเมื่อ engine รองรับ (psql); MySQL TRUNCATE
  commit เองอยู่แล้ว — ระบุในข้อความเตือนก่อนยืนยัน
- `--dry-run` พิมพ์ SQL, ไม่รัน

## 10. Testing

- ไม่มี dump จริงใน repo/tests (มี PII)
- Unit: tokenizer MySQL/COPY (escape ทุกแบบ, multi-line ใน string, binary),
  strategies (รูปแบบ, NULL/empty คงเดิม, unique), profile loader/validation,
  by_metadata_field, when/unless
- Round-trip: dump สังเคราะห์ → anonymize → ตรวจว่าทุกบรรทัดที่ไม่เกี่ยวเหมือนเดิม
  และ cell เป้าหมายเปลี่ยน
- Integration (marker `docker`, ข้ามได้ถ้าไม่มี docker): `mariadb:11` และ
  `postgres:16` — สร้าง schema ย่อของแต่ละ profile + ข้อมูลปลอม → mysqldump /
  pg_dump → anonymize → restore ลง DB ใหม่สำเร็จ → ตรวจ FK/จำนวนแถว/ค่าเปลี่ยน;
  direct mode รันบน DB เดียวกันแล้วตรวจแบบเดียวกัน
- ทดสอบตามแบบ tests เดิม (`tests/test_skill_audit.py`: `sys.path` ชี้ `src`)

## 11. Build process (agent team)

- งานทำใน worktree `.worktrees/anonymize` branch `feat/anonymize`
- Worker = `qwen` ผ่าน Musubi, model `deepseek-flash`, `--approval-mode yolo`,
  `cwd` = worktree; หนึ่ง task ต่อหนึ่ง qwen run
- Claude (coordinator) แตก plan เป็น task, ส่งให้ qwen, review diff + รัน test
  ทุก task ก่อนรับ; ไม่ผ่าน → ส่งกลับพร้อม feedback
- จบ: commit บน `feat/anonymize`, ไม่ merge

## 12. Calls made after builder review (Claude's call — ตรวจได้)

1. **ล้มกลางสตรีม:** ไม่ spool ลงไฟล์ (dump ใหญ่, ช้า) เมื่อ exit 2 ให้เขียน
   "poison" ท้าย stdout ก่อนออก: บรรทัด comment อธิบาย + statement ที่ผิด
   syntax แน่นอน (`JARVIS_ANONYMIZE_FAILED;`) เพื่อให้ client ฝั่ง restore
   error ด้วย และพิมพ์คำแนะนำ `set -o pipefail` ทาง stderr. ค่าจริงไม่หลุดอยู่แล้ว
   เพราะ fail-closed ไม่เขียนแถวที่ parse ไม่ได้
2. **TRUNCATE กับ AUTO_INCREMENT:** anti-goal ข้อ sequence ใช้กับตารางที่ "เก็บไว้"
   เท่านั้น ตารางที่ truncate (log/session) จะ reset counter ได้ — ใช้ TRUNCATE
3. **ตรวจรูปแบบ dump:** ถ้าอ่านจบแล้วไม่พบ statement ของ engine เลย
   (mysql: `CREATE TABLE`+`INSERT INTO`, psql: `COPY … FROM stdin`) → exit 2.
   ตารางที่มีกฎแต่เจอรูปแบบไม่รองรับ (`INSERT INTO` ใน psql, INSERT มีรายชื่อคอลัมน์
   ใน mysql) → exit 2 ทันที
4. **รูปทรงค่าใน direct mode:** ไม่ต้องเหมือน stream mode เป๊ะ ขอแค่ type/ความยาว
   ถูก และไม่เหลือค่าเดิม: `name`/`text` = ตัวอักษรสุ่ม (จาก md5 แปลงเป็นตัวอักษร),
   `email` = `<hex>@<hex>.invalid`, `phone`/`digits` = ตัวเลขสุ่ม,
   `password`/`id` = hex สุ่มความยาวเท่าเดิม
5. **`date` กับค่าที่ไม่ใช่วันที่สะอาด:** `0000-00-00` คงเดิม (ไม่ใช่ PII); ค่าที่
   parse เป็นวันที่ไม่ได้ (เช่น `"c. 1980"`) → แทนด้วยวันที่สุ่ม `YYYY-MM-DD`
   ไม่ปล่อยค่าเดิม
6. **Profile แก้ได้:** builder แก้ TOML ได้เมื่อ integration test พิสูจน์ว่ากฎผิด
   (เช่น `null` บนคอลัมน์ NOT NULL) โดยต้องบอกเหตุผลใน commit message;
   ไม่ต้องทำ validation profile กับ schema ในรอบนี้

## 13. Left to the builder

- โครงโมดูลภายใน `src/jarvis/anonymize/` (parser, strategies, profile, direct)
- ความยาว/ตัวอักษรของ `name`/`text` ตามตาราง README
- วิธีรับประกัน unique ใน direct mode
- รูปแบบตาราง report (ใช้ `rich` ที่มีอยู่ได้)
