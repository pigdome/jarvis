-- Synthetic seed for the jarvis db anonymize PostgreSQL fixture.
-- Every row below is invented for tests; there is no production data here.
-- Loaded into an empty `dspace_fixture` database by make_fixtures.sh, then
-- dumped with pg_dump plain format (COPY ... FROM stdin).

SET client_encoding = 'UTF8';

-- DSpace metadata registries (dumped before metadatavalue, as in DSpace).
CREATE TABLE metadataschemaregistry (
  metadata_schema_id integer NOT NULL,
  namespace varchar(256) NOT NULL,
  short_id varchar(32),
  CONSTRAINT metadataschemaregistry_pkey PRIMARY KEY (metadata_schema_id),
  CONSTRAINT metadataschemaregistry_namespace_key UNIQUE (namespace),
  CONSTRAINT metadataschemaregistry_short_id_key UNIQUE (short_id)
);

CREATE TABLE metadatafieldregistry (
  metadata_field_id integer NOT NULL,
  metadata_schema_id integer NOT NULL,
  element varchar(64),
  qualifier varchar(64),
  scope_note text,
  CONSTRAINT metadatafieldregistry_pkey PRIMARY KEY (metadata_field_id),
  CONSTRAINT metadatafieldregistry_schema_fkey FOREIGN KEY (metadata_schema_id)
    REFERENCES metadataschemaregistry (metadata_schema_id)
);

CREATE TABLE eperson (
  uuid uuid NOT NULL,
  email varchar(64),
  netid varchar(64),
  password varchar(128),
  salt varchar(32),
  session_salt varchar(32),
  CONSTRAINT eperson_pkey PRIMARY KEY (uuid),
  CONSTRAINT eperson_email_key UNIQUE (email),
  CONSTRAINT eperson_netid_key UNIQUE (netid)
);

CREATE TABLE metadatavalue (
  metadata_value_id integer NOT NULL,
  resource_id uuid NOT NULL,
  metadata_field_id integer NOT NULL,
  text_value text,
  text_lang varchar(24),
  place integer,
  CONSTRAINT metadatavalue_pkey PRIMARY KEY (metadata_value_id),
  CONSTRAINT metadatavalue_field_fkey FOREIGN KEY (metadata_field_id)
    REFERENCES metadatafieldregistry (metadata_field_id)
);

CREATE TABLE booking_patron (
  uuid uuid NOT NULL,
  patron_id varchar(128) NOT NULL,
  cardnumber varchar(64),
  name varchar(255),
  email varchar(254),
  phone varchar(32),
  organization text,
  CONSTRAINT booking_patron_pkey PRIMARY KEY (uuid),
  CONSTRAINT booking_patron_patron_id_key UNIQUE (patron_id)
);

CREATE TABLE booking_booking (
  uuid uuid NOT NULL,
  patron_id uuid NOT NULL,
  phone varchar(32),
  reason_description text,
  attendance_list jsonb,
  passcode varchar(64),
  passcode_pin varchar(64),
  CONSTRAINT booking_booking_pkey PRIMARY KEY (uuid),
  CONSTRAINT booking_booking_patron_fkey FOREIGN KEY (patron_id)
    REFERENCES booking_patron (uuid)
);

CREATE TABLE booking_actionlog (
  uuid uuid NOT NULL,
  ip_address inet,
  details jsonb,
  CONSTRAINT booking_actionlog_pkey PRIMARY KEY (uuid)
);

CREATE TABLE django_session (
  session_key varchar(40) NOT NULL,
  session_data text NOT NULL,
  expire_date timestamptz NOT NULL,
  CONSTRAINT django_session_pkey PRIMARY KEY (session_key)
);

INSERT INTO metadataschemaregistry (metadata_schema_id, namespace, short_id) VALUES
  (1, 'http://dublincore.org/documents/dcmi-terms/', 'dc'),
  (2, 'http://dspace.org/eperson', 'eperson'),
  (3, 'http://dspace.org/person', 'person');

INSERT INTO metadatafieldregistry
  (metadata_field_id, metadata_schema_id, element, qualifier, scope_note)
VALUES
  (1, 2, 'firstname', NULL, 'given name'),
  (2, 2, 'lastname', NULL, 'family name'),
  (3, 2, 'phone', NULL, 'phone number'),
  (4, 2, 'orcid', NULL, NULL),
  (5, 1, 'title', NULL, NULL),
  (6, 1, 'contributor', 'author', NULL),
  (7, 1, 'description', 'provenance', NULL),
  (8, 1, 'creator', NULL, NULL),
  (9, 3, 'email', NULL, NULL);

-- eperson: one UTF-8 row, one ASCII apostrophe row, NULL email, empty email.
INSERT INTO eperson (uuid, email, netid, password, salt, session_salt) VALUES
  ('11111111-1111-4111-8111-111111111111', 'somchai@example.ac.th', 'somchai',
   repeat('a1b2c3d4', 16), repeat('deadbeef', 4), NULL),
  ('22222222-2222-4222-8222-222222222222', 'patrick.obrien@example.ac.th',
   'pobrien', repeat('0123456789abcdef', 8), repeat('cafebabe', 4), NULL),
  ('33333333-3333-4333-8333-333333333333', NULL, 'nullmail',
   repeat('fedcba9876543210', 8), repeat('feedface', 4), NULL),
  ('44444444-4444-4444-8444-444444444444', '', 'emptymail',
   repeat('0011223344556677', 8), repeat('0badf00d', 4), '');

-- metadatavalue: person fields are rewritten, dc.title / contributor kept.
INSERT INTO metadatavalue
  (metadata_value_id, resource_id, metadata_field_id, text_value, text_lang,
   place)
VALUES
  (1, '11111111-1111-4111-8111-111111111111', 1,
   'สมชาย', 'th', 0),
  (2, '11111111-1111-4111-8111-111111111111', 2,
   'ใจดี', 'th', 0),
  (3, '11111111-1111-4111-8111-111111111111', 3,
   '0812345678', NULL, 0),
  (4, '11111111-1111-4111-8111-111111111111', 4,
   NULL, NULL, 0),
  (5, '11111111-1111-4111-8111-111111111111', 9,
   'somchai@example.ac.th', NULL, 0),
  (6, '22222222-2222-4222-8222-222222222222', 1,
   'Patrick', NULL, 0),
  (7, '22222222-2222-4222-8222-222222222222', 2,
   'O''Brien', NULL, 0),
  (8, '22222222-2222-4222-8222-222222222222', 7,
   E'Submitted by Patrick O''Brien (patrick.obrien@example.ac.th) on 2024-01-02\nbackslash C:\\temp\\file and tab\there',
   'en', 0),
  (9, '11111111-1111-4111-8111-111111111111', 5,
   E'การบริหารห้องสมุด\tและ\nบริการ C:\\docs\\title.docx', 'th', 0),
  (10, '11111111-1111-4111-8111-111111111111', 6,
   'สมชาย ใจดี; Patrick O''Brien', 'th', 1),
  (11, '33333333-3333-4333-8333-333333333333', 9,
   '', NULL, 0),
  (12, '44444444-4444-4444-8444-444444444444', 3,
   '', NULL, 0);

INSERT INTO booking_patron
  (uuid, patron_id, cardnumber, name, email, phone, organization)
VALUES
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'STAFF0001', '6401234567',
   'สมชาย ใจดี', 'somchai@example.ac.th', '0812345678', 'ห้องสมุดกลาง'),
  ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'STUDENT-2024-0002', '6407654321',
   'Patrick O''Brien', 'patrick.obrien@example.ac.th', '029999999',
   'Faculty of Arts'),
  ('cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'BACKSLASH01', NULL,
   'Back\slash Test', NULL, '', NULL);

INSERT INTO booking_booking
  (uuid, patron_id, phone, reason_description, attendance_list, passcode,
   passcode_pin)
VALUES
  ('dddddddd-dddd-4ddd-8ddd-dddddddddddd', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
   '0812345678', E'จองห้องประชุม\tชั้น 2\nต้องการโปรเจกเตอร์',
   '[{"id": "STAFF0001", "name": "สมชาย ใจดี"}]', '123456', '654321'),
  ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
   NULL, 'Study room C:\booked', '[]', NULL, NULL);

-- Truncated: action log rows hold IPs and names in JSON.
INSERT INTO booking_actionlog (uuid, ip_address, details) VALUES
  ('ffffffff-ffff-4fff-8fff-ffffffffffff', '192.0.2.55',
   '{"actor": "สมชาย ใจดี", "email": "somchai@example.ac.th"}'),
  ('99999999-9999-4999-8999-999999999999', NULL,
   '{"note": "O''Brien", "path": "C:\\temp"}');

-- Truncated: sessions hold ThaID numbers and names.
INSERT INTO django_session (session_key, session_data, expire_date) VALUES
  ('abc123def456', '{"pid": "1234567890123", "name": "สมชาย ใจดี"}',
   '2030-01-01 00:00:00+00'),
  ('zzz999', '{}', '2030-01-02 00:00:00+00');
