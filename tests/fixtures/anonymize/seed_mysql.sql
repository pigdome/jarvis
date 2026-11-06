-- Synthetic seed for the jarvis db anonymize MySQL fixture.
-- Every row below is invented for tests; there is no production data here.
-- Loaded into an empty `koha_fixture` database by make_fixtures.sh, then
-- dumped with mariadb-dump defaults (extended INSERTs, no column names).

SET NAMES utf8mb4;
SET SESSION sql_mode = '';  -- allow the Koha zero date 0000-00-00

CREATE TABLE borrowers (
  borrowernumber INT NOT NULL AUTO_INCREMENT,
  cardnumber VARCHAR(32) NOT NULL,
  userid VARCHAR(75) NOT NULL,
  surname VARCHAR(100) NOT NULL DEFAULT '',
  firstname VARCHAR(100) NOT NULL DEFAULT '',
  email VARCHAR(100) DEFAULT NULL,
  phone VARCHAR(50) DEFAULT NULL,
  dateofbirth DATE DEFAULT NULL,
  password VARCHAR(60) DEFAULT NULL,
  borrowernotes TEXT,
  sort1 VARCHAR(80) DEFAULT NULL,
  PRIMARY KEY (borrowernumber),
  UNIQUE KEY cardnumber (cardnumber),
  UNIQUE KEY userid (userid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE borrower_attributes (
  id INT NOT NULL AUTO_INCREMENT,
  borrowernumber INT NOT NULL,
  code VARCHAR(64) NOT NULL,
  attribute TEXT,
  PRIMARY KEY (id),
  KEY borrowernumber (borrowernumber),
  CONSTRAINT borrower_attributes_ibfk_1 FOREIGN KEY (borrowernumber)
    REFERENCES borrowers (borrowernumber)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE sessions (
  id VARCHAR(32) NOT NULL,
  a_session LONGBLOB,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE issues (
  issue_id INT NOT NULL AUTO_INCREMENT,
  borrowernumber INT NOT NULL,
  note TEXT,
  PRIMARY KEY (issue_id),
  KEY borrowernumber (borrowernumber),
  CONSTRAINT issues_ibfk_1 FOREIGN KEY (borrowernumber)
    REFERENCES borrowers (borrowernumber)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE biblio (
  biblionumber INT NOT NULL AUTO_INCREMENT,
  title TEXT,
  author TEXT,
  PRIMARY KEY (biblionumber)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Hand-written edge cases: Thai, quote, backslash, newline/tab, NULL, ''
INSERT INTO borrowers
  (cardnumber, userid, surname, firstname, email, phone, dateofbirth,
   password, borrowernotes, sort1)
VALUES
  ('9000000001', 'somchai', 'ใจดี', 'สมชาย', 'somchai@example.ac.th',
   '0812345678', '1980-03-04',
   '$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO',
   'ผู้ใช้ทดสอบภาษาไทย ถนนสุขุมวิท', 'S900001'),
  ('9000000002', 'obrien', 'O''Brien', 'Patrick',
   'patrick.obrien@example.ac.th', '029999999', '1975-12-31',
   '$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO',
   'His nickname is "Paddy"; say \'hi\' to him.', 'S900002'),
  ('9000000003', 'backslash', 'Back\\slash', 'Escape\\Test',
   'escape@example.ac.th', '0811111111', '1990-07-08',
   '$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO',
   'C:\\Users\\patron\\notes.txt and a lone \\ backslash', 'S900003'),
  ('9000000004', 'multiline', 'Newline', 'Tabbed',
   'multiline@example.ac.th', '0822222222', '2001-02-03',
   '$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO',
   'line one\nline two\tend of tab', 'S900004'),
  ('9000000005', 'nullmail', 'Nullson', 'Nulla', NULL, NULL, NULL, NULL, NULL, NULL),
  ('9000000006', 'emptymail', 'Empty', 'Epsilon', '', '', '0000-00-00', '', '', ''),
  ('9000000007', 'farang', 'Smith', 'Anna', 'anna.smith@example.ac.th',
   '029999998', '1955-06-15',
   '$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO',
   'plain ascii note', 'S900007');

-- Enough filler rows for mariadb-dump to split the extended INSERT.
DELIMITER //
CREATE PROCEDURE seed_borrowers(IN total INT)
BEGIN
  DECLARE i INT DEFAULT 1;
  WHILE i <= total DO
    INSERT INTO borrowers
      (cardnumber, userid, surname, firstname, email, phone, dateofbirth,
       password, borrowernotes, sort1)
    VALUES
      (LPAD(i, 10, '0'),
       CONCAT('user', LPAD(i, 6, '0')),
       CONCAT('นามสกุล', i),
       CONCAT('ชื่อ', i),
       CONCAT('patron', i, '@example.ac.th'),
       CONCAT('08', LPAD(i, 8, '0')),
       '1990-01-01',
       '$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO',
       REPEAT('หมายเหตุการยืมหนังสือ ', 14),
       CONCAT('S', LPAD(i, 6, '0')));
    SET i = i + 1;
  END WHILE;
END//
DELIMITER ;

START TRANSACTION;
CALL seed_borrowers(3000);
COMMIT;
DROP PROCEDURE seed_borrowers;

-- FACULTY is not PII, CITIZENID is; both are present for `unless` tests.
INSERT INTO borrower_attributes (borrowernumber, code, attribute) VALUES
  (1, 'FACULTY', 'Engineering'),
  (2, 'CITIZENID', '1234567890123'),
  (1, 'CITIZENID', '9876543210987'),
  (3, 'FACULTY', NULL),
  (4, 'PASSPORT', 'AA1234567');

-- Truncated table: rows carry opaque binary session payloads.
INSERT INTO sessions (id, a_session) VALUES
  ('sess-001', 0x00FF27),
  ('sess-002', 'plain text session data'),
  ('sess-003', 0x504150495F53455353494F4E);

-- No rules: must pass through byte-for-byte.
INSERT INTO issues (borrowernumber, note) VALUES
  (1, 'patron asked for somchai@example.ac.th at the desk'),
  (2, 'Thai note: ผู้ใช้สอบถามเรื่องการต่ออายุ'),
  (3, 'path C:\\temp\\issue.txt');

INSERT INTO biblio (title, author) VALUES
  ('การบริหารห้องสมุดสมัยใหม่', 'สมชาย ใจดี'),
  ('O''Brien and the Library', 'Patrick O''Brien'),
  ('Backslashes \\ in MARC', 'Escape Tester');
