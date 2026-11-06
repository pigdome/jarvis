--
-- PostgreSQL database dump
--

\restrict 8sCWMu53d7lAtxcxy5F1QG5YCDwZC5rc4beSfFmJuXkSWsiIlbRs166qE21nPyH

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: booking_actionlog; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.booking_actionlog (
    uuid uuid NOT NULL,
    ip_address inet,
    details jsonb
);


ALTER TABLE public.booking_actionlog OWNER TO postgres;

--
-- Name: booking_booking; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.booking_booking (
    uuid uuid NOT NULL,
    patron_id uuid NOT NULL,
    phone character varying(32),
    reason_description text,
    attendance_list jsonb,
    passcode character varying(64),
    passcode_pin character varying(64)
);


ALTER TABLE public.booking_booking OWNER TO postgres;

--
-- Name: booking_patron; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.booking_patron (
    uuid uuid NOT NULL,
    patron_id character varying(128) NOT NULL,
    cardnumber character varying(64),
    name character varying(255),
    email character varying(254),
    phone character varying(32),
    organization text
);


ALTER TABLE public.booking_patron OWNER TO postgres;

--
-- Name: django_session; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.django_session (
    session_key character varying(40) NOT NULL,
    session_data text NOT NULL,
    expire_date timestamp with time zone NOT NULL
);


ALTER TABLE public.django_session OWNER TO postgres;

--
-- Name: eperson; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.eperson (
    uuid uuid NOT NULL,
    email character varying(64),
    netid character varying(64),
    password character varying(128),
    salt character varying(32),
    session_salt character varying(32)
);


ALTER TABLE public.eperson OWNER TO postgres;

--
-- Name: metadatafieldregistry; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.metadatafieldregistry (
    metadata_field_id integer NOT NULL,
    metadata_schema_id integer NOT NULL,
    element character varying(64),
    qualifier character varying(64),
    scope_note text
);


ALTER TABLE public.metadatafieldregistry OWNER TO postgres;

--
-- Name: metadataschemaregistry; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.metadataschemaregistry (
    metadata_schema_id integer NOT NULL,
    namespace character varying(256) NOT NULL,
    short_id character varying(32)
);


ALTER TABLE public.metadataschemaregistry OWNER TO postgres;

--
-- Name: metadatavalue; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.metadatavalue (
    metadata_value_id integer NOT NULL,
    resource_id uuid NOT NULL,
    metadata_field_id integer NOT NULL,
    text_value text,
    text_lang character varying(24),
    place integer
);


ALTER TABLE public.metadatavalue OWNER TO postgres;

--
-- Data for Name: booking_actionlog; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.booking_actionlog (uuid, ip_address, details) FROM stdin;
ffffffff-ffff-4fff-8fff-ffffffffffff	192.0.2.55	{"actor": "สมชาย ใจดี", "email": "somchai@example.ac.th"}
99999999-9999-4999-8999-999999999999	\N	{"note": "O'Brien", "path": "C:\\\\temp"}
\.


--
-- Data for Name: booking_booking; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.booking_booking (uuid, patron_id, phone, reason_description, attendance_list, passcode, passcode_pin) FROM stdin;
dddddddd-dddd-4ddd-8ddd-dddddddddddd	aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa	0812345678	จองห้องประชุม\tชั้น 2\nต้องการโปรเจกเตอร์	[{"id": "STAFF0001", "name": "สมชาย ใจดี"}]	123456	654321
eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee	bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb	\N	Study room C:\\booked	[]	\N	\N
\.


--
-- Data for Name: booking_patron; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.booking_patron (uuid, patron_id, cardnumber, name, email, phone, organization) FROM stdin;
aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa	STAFF0001	6401234567	สมชาย ใจดี	somchai@example.ac.th	0812345678	ห้องสมุดกลาง
bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb	STUDENT-2024-0002	6407654321	Patrick O'Brien	patrick.obrien@example.ac.th	029999999	Faculty of Arts
cccccccc-cccc-4ccc-8ccc-cccccccccccc	BACKSLASH01	\N	Back\\slash Test	\N		\N
\.


--
-- Data for Name: django_session; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.django_session (session_key, session_data, expire_date) FROM stdin;
abc123def456	{"pid": "1234567890123", "name": "สมชาย ใจดี"}	2030-01-01 00:00:00+00
zzz999	{}	2030-01-02 00:00:00+00
\.


--
-- Data for Name: eperson; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.eperson (uuid, email, netid, password, salt, session_salt) FROM stdin;
11111111-1111-4111-8111-111111111111	somchai@example.ac.th	somchai	a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4a1b2c3d4	deadbeefdeadbeefdeadbeefdeadbeef	\N
22222222-2222-4222-8222-222222222222	patrick.obrien@example.ac.th	pobrien	0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef	cafebabecafebabecafebabecafebabe	\N
33333333-3333-4333-8333-333333333333	\N	nullmail	fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210	feedfacefeedfacefeedfacefeedface	\N
44444444-4444-4444-8444-444444444444		emptymail	00112233445566770011223344556677001122334455667700112233445566770011223344556677001122334455667700112233445566770011223344556677	0badf00d0badf00d0badf00d0badf00d	
\.


--
-- Data for Name: metadatafieldregistry; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.metadatafieldregistry (metadata_field_id, metadata_schema_id, element, qualifier, scope_note) FROM stdin;
1	2	firstname	\N	given name
2	2	lastname	\N	family name
3	2	phone	\N	phone number
4	2	orcid	\N	\N
5	1	title	\N	\N
6	1	contributor	author	\N
7	1	description	provenance	\N
8	1	creator	\N	\N
9	3	email	\N	\N
\.


--
-- Data for Name: metadataschemaregistry; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.metadataschemaregistry (metadata_schema_id, namespace, short_id) FROM stdin;
1	http://dublincore.org/documents/dcmi-terms/	dc
2	http://dspace.org/eperson	eperson
3	http://dspace.org/person	person
\.


--
-- Data for Name: metadatavalue; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.metadatavalue (metadata_value_id, resource_id, metadata_field_id, text_value, text_lang, place) FROM stdin;
1	11111111-1111-4111-8111-111111111111	1	สมชาย	th	0
2	11111111-1111-4111-8111-111111111111	2	ใจดี	th	0
3	11111111-1111-4111-8111-111111111111	3	0812345678	\N	0
4	11111111-1111-4111-8111-111111111111	4	\N	\N	0
5	11111111-1111-4111-8111-111111111111	9	somchai@example.ac.th	\N	0
6	22222222-2222-4222-8222-222222222222	1	Patrick	\N	0
7	22222222-2222-4222-8222-222222222222	2	O'Brien	\N	0
8	22222222-2222-4222-8222-222222222222	7	Submitted by Patrick O'Brien (patrick.obrien@example.ac.th) on 2024-01-02\nbackslash C:\\temp\\file and tab\there	en	0
9	11111111-1111-4111-8111-111111111111	5	การบริหารห้องสมุด\tและ\nบริการ C:\\docs\\title.docx	th	0
10	11111111-1111-4111-8111-111111111111	6	สมชาย ใจดี; Patrick O'Brien	th	1
11	33333333-3333-4333-8333-333333333333	9		\N	0
12	44444444-4444-4444-8444-444444444444	3		\N	0
\.


--
-- Name: booking_actionlog booking_actionlog_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.booking_actionlog
    ADD CONSTRAINT booking_actionlog_pkey PRIMARY KEY (uuid);


--
-- Name: booking_booking booking_booking_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.booking_booking
    ADD CONSTRAINT booking_booking_pkey PRIMARY KEY (uuid);


--
-- Name: booking_patron booking_patron_patron_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.booking_patron
    ADD CONSTRAINT booking_patron_patron_id_key UNIQUE (patron_id);


--
-- Name: booking_patron booking_patron_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.booking_patron
    ADD CONSTRAINT booking_patron_pkey PRIMARY KEY (uuid);


--
-- Name: django_session django_session_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.django_session
    ADD CONSTRAINT django_session_pkey PRIMARY KEY (session_key);


--
-- Name: eperson eperson_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.eperson
    ADD CONSTRAINT eperson_email_key UNIQUE (email);


--
-- Name: eperson eperson_netid_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.eperson
    ADD CONSTRAINT eperson_netid_key UNIQUE (netid);


--
-- Name: eperson eperson_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.eperson
    ADD CONSTRAINT eperson_pkey PRIMARY KEY (uuid);


--
-- Name: metadatafieldregistry metadatafieldregistry_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadatafieldregistry
    ADD CONSTRAINT metadatafieldregistry_pkey PRIMARY KEY (metadata_field_id);


--
-- Name: metadataschemaregistry metadataschemaregistry_namespace_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadataschemaregistry
    ADD CONSTRAINT metadataschemaregistry_namespace_key UNIQUE (namespace);


--
-- Name: metadataschemaregistry metadataschemaregistry_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadataschemaregistry
    ADD CONSTRAINT metadataschemaregistry_pkey PRIMARY KEY (metadata_schema_id);


--
-- Name: metadataschemaregistry metadataschemaregistry_short_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadataschemaregistry
    ADD CONSTRAINT metadataschemaregistry_short_id_key UNIQUE (short_id);


--
-- Name: metadatavalue metadatavalue_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadatavalue
    ADD CONSTRAINT metadatavalue_pkey PRIMARY KEY (metadata_value_id);


--
-- Name: booking_booking booking_booking_patron_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.booking_booking
    ADD CONSTRAINT booking_booking_patron_fkey FOREIGN KEY (patron_id) REFERENCES public.booking_patron(uuid);


--
-- Name: metadatafieldregistry metadatafieldregistry_schema_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadatafieldregistry
    ADD CONSTRAINT metadatafieldregistry_schema_fkey FOREIGN KEY (metadata_schema_id) REFERENCES public.metadataschemaregistry(metadata_schema_id);


--
-- Name: metadatavalue metadatavalue_field_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.metadatavalue
    ADD CONSTRAINT metadatavalue_field_fkey FOREIGN KEY (metadata_field_id) REFERENCES public.metadatafieldregistry(metadata_field_id);


--
-- PostgreSQL database dump complete
--

\unrestrict 8sCWMu53d7lAtxcxy5F1QG5YCDwZC5rc4beSfFmJuXkSWsiIlbRs166qE21nPyH

