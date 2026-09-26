--
-- PostgreSQL database dump
--


-- Dumped from database version 16.15 (Debian 16.15-1.pgdg12+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg12+2)

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

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: source_revision_guard(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.source_revision_guard() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.content IS DISTINCT FROM OLD.content
       OR NEW.revision_hash IS DISTINCT FROM OLD.revision_hash
       OR NEW.source_object_id IS DISTINCT FROM OLD.source_object_id
       OR NEW.metadata IS DISTINCT FROM OLD.metadata
       OR NEW.recorded_at IS DISTINCT FROM OLD.recorded_at
       OR (OLD.lineage_parent_revision_id IS NOT NULL
           AND NEW.lineage_parent_revision_id IS DISTINCT FROM OLD.lineage_parent_revision_id) THEN
        RAISE EXCEPTION 'source_revision % is immutable except lifecycle', OLD.id;
    END IF;
    RETURN NEW;
END $$;


--
-- Name: source_revision_no_delete(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.source_revision_no_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'source_revision rows are never deleted';
END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: active_membership; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.active_membership (
    commit_id uuid NOT NULL,
    "position" integer NOT NULL,
    source_revision_id uuid NOT NULL,
    window_hash text
);


--
-- Name: app_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.app_config (
    key text NOT NULL,
    value jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: assertion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assertion (
    id bigint NOT NULL,
    extraction_id uuid NOT NULL,
    source_revision_id uuid NOT NULL,
    subject text NOT NULL,
    subject_type text,
    predicate text NOT NULL,
    object text,
    object_type text,
    value text,
    epistemic text DEFAULT 'stated'::text NOT NULL,
    confidence real,
    evidence text,
    status text NOT NULL,
    reason text,
    known_by text[],
    hidden_from text[],
    knowledge text DEFAULT 'unknown'::text NOT NULL,
    CONSTRAINT assertion_knowledge_check CHECK ((knowledge = ANY (ARRAY['public'::text, 'limited'::text, 'unknown'::text]))),
    CONSTRAINT assertion_status_check CHECK ((status = ANY (ARRAY['valid'::text, 'pending'::text])))
);


--
-- Name: assertion_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.assertion ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.assertion_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: conversation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversation (
    id uuid NOT NULL,
    host text NOT NULL,
    host_character_ref text,
    host_chat_ref text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    branched_from_conversation_id uuid,
    branched_from_host_chat_ref text,
    branched_from_message_ref text,
    head_commit_id uuid,
    head_manifest_hash text,
    host_character_name text,
    host_chat_name text
);


--
-- Name: extraction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extraction (
    id uuid NOT NULL,
    source_revision_id uuid NOT NULL,
    window_hash text NOT NULL,
    compiler_version text NOT NULL,
    model text NOT NULL,
    raw jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    extractor_key text,
    coverage jsonb
);


--
-- Name: host_observation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.host_observation (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    kind text NOT NULL,
    manifest_hash text,
    idempotency_key text NOT NULL,
    observed_at timestamp with time zone DEFAULT now() NOT NULL,
    raw_manifest jsonb NOT NULL,
    CONSTRAINT host_observation_kind_check CHECK ((kind = ANY (ARRAY['manifest'::text, 'output'::text])))
);


--
-- Name: job; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job (
    id bigint NOT NULL,
    kind text NOT NULL,
    dedupe_key text NOT NULL,
    conversation_id uuid NOT NULL,
    payload jsonb NOT NULL,
    priority integer DEFAULT 100 NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    run_after timestamp with time zone DEFAULT now() NOT NULL,
    locked_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'done'::text, 'obsolete'::text, 'dead'::text])))
);


--
-- Name: job_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.job ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.job_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: projection_generation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projection_generation (
    key text NOT NULL,
    kind text NOT NULL,
    model text NOT NULL,
    endpoint text NOT NULL,
    spec jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    activated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT projection_generation_kind_check CHECK ((kind = ANY (ARRAY['extract'::text, 'embed'::text])))
);


--
-- Name: retrieval_trace; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.retrieval_trace (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    commit_id uuid,
    query text NOT NULL,
    candidates jsonb NOT NULL,
    selected jsonb NOT NULL,
    excluded_in_context jsonb NOT NULL,
    token_estimate integer NOT NULL,
    latency_ms jsonb NOT NULL,
    freshness text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: revision_embedding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.revision_embedding (
    source_revision_id uuid NOT NULL,
    model text NOT NULL,
    chunk integer NOT NULL,
    dim integer NOT NULL,
    text_start integer NOT NULL,
    text_end integer NOT NULL,
    embedding public.vector NOT NULL,
    projection text NOT NULL
);


--
-- Name: revision_text; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.revision_text (
    source_revision_id uuid NOT NULL,
    normalizer text NOT NULL,
    clean_content text NOT NULL,
    original_chars integer NOT NULL,
    clean_chars integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: source_object; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_object (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    host_logical_id text NOT NULL,
    source_kind text DEFAULT 'message'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: source_revision; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_revision (
    id uuid NOT NULL,
    source_object_id uuid NOT NULL,
    revision_hash text NOT NULL,
    content text NOT NULL,
    metadata jsonb NOT NULL,
    recorded_at timestamp with time zone DEFAULT now() NOT NULL,
    lifecycle text NOT NULL,
    lineage_parent_revision_id uuid,
    CONSTRAINT source_revision_lifecycle_check CHECK ((lifecycle = ANY (ARRAY['provisional'::text, 'accepted'::text, 'retracted'::text, 'superseded'::text])))
);


--
-- Name: state_observation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.state_observation (
    id bigint NOT NULL,
    conversation_id uuid NOT NULL,
    source_revision_id uuid NOT NULL,
    rules_version text NOT NULL,
    rule_id text NOT NULL,
    key text NOT NULL,
    value text NOT NULL
);


--
-- Name: state_observation_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.state_observation ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.state_observation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: worldline_commit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.worldline_commit (
    id uuid NOT NULL,
    seq bigint NOT NULL,
    conversation_id uuid NOT NULL,
    parent_commit_ids uuid[] NOT NULL,
    reason text NOT NULL,
    manifest_hash text NOT NULL,
    delta jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    host_observation_id uuid,
    CONSTRAINT worldline_commit_reason_check CHECK ((reason = ANY (ARRAY['import'::text, 'branch'::text, 'edit'::text, 'delete'::text, 'swipe'::text, 'reroll'::text, 'disable'::text, 'reconciliation'::text, 'manual'::text])))
);


--
-- Name: worldline_commit_seq_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.worldline_commit ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.worldline_commit_seq_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Data for Name: active_membership; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 0, '01a0dd31-194e-7a25-8d80-a0e0ec67c1eb', 'fd9308e5b25e359067f46879f30c1b4c');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 1, '01a0dd31-1950-79d5-aa28-3623540b0241', '64a09e656e2ce1afc2b488563a315d0e');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 2, '01a0dd31-1951-7a30-a3ae-7acb35a5edf4', '88e6f1fee79475f90234ef95621f83b4');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 3, '01a0dd31-21df-782d-9fae-c74fc7c400e1', '05d187dc7ec8af379b6d81697217f043');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 4, '01a0dd31-1988-7ef4-876a-639eb241fc2c', 'db4b00da04156135e5fe7de4a130cbfe');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 5, '01a0dd31-1989-7aaf-aa6c-fa50e3832f1e', 'daae76df598d2e6929f4c9ca3b06e04a');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 6, '01a0dd31-198a-7a9a-9924-15402b69b10f', '15c9a947cd4246f643fe4cc4f4753c7b');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 7, '01a0dd31-198b-7fe4-a3a5-3472f45d68d0', 'dd5477fdb7295daad400391b7de8559c');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 8, '01a0dd31-2229-7cbb-b6cb-418422de5f72', '7526300ac660843048bffcd1dc870ecd');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 9, '01a0dd31-19b2-702b-bd92-d67874bd4bc1', '243cf96191944378def783dd7b6f0a5b');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 10, '01a0dd31-19b2-716e-a754-55d85a999b2e', '9f043b54c86073af0dd5eaab43fd16e1');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 11, '01a0dd31-19b3-7570-9078-158e0e0fabac', '6c79b101701b9cc4462ad1d0be6d26ea');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 12, '01a0dd31-19d6-7514-8fc4-7c78a619b10f', '0a5a41f6790182ec7915fa4c5fee3d42');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 13, '01a0dd31-21e0-709a-8445-e4614cea757b', 'f9acc9e09f968aabe49ce2c32b2765e0');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 14, '01a0dd31-21e1-772b-bb9f-3af6ee06765a', 'eca9aa1b83f8ccfcae18b84aec6ae1c1');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 15, '01a0dd31-222a-789b-983e-ce9dcd6697e3', 'bdcd55bc351d1e60947285dfc17dac87');
INSERT INTO public.active_membership VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 16, '01a0dd31-222b-7594-b34c-31ef9c391a5a', '833c944206edcae4d9fb92d65791f289');
INSERT INTO public.active_membership VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 0, '01a0dd31-2642-72ad-9b58-57810882f7bc', '4ab34d4ede0034e77b216de517cc7861');
INSERT INTO public.active_membership VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 1, '01a0dd31-2642-75fc-975f-7015e8a113f2', '6769ba52e071e3be81dd12b9a8c2ad21');
INSERT INTO public.active_membership VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 2, '01a0dd31-2643-718b-9435-6d45c32dc2c6', '512fde5fa326a5256a88d456a8e780c5');
INSERT INTO public.active_membership VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 3, '01a0dd31-2644-760d-8aee-0d21dd40fc4b', 'da5a24f9bff33b9a17429b60e0e7c9fe');
INSERT INTO public.active_membership VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 4, '01a0dd31-2645-778f-a64f-42eb008725c4', 'd2ba2821fed107a07290201041b8d0d0');
INSERT INTO public.active_membership VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 5, '01a0dd31-2645-7c66-b9c7-e31a67ace436', 'b7d318144ddffc51675a381beb06a375');
INSERT INTO public.active_membership VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 6, '01a0dd31-2646-7d22-a3eb-74d21639dbcf', 'bd00b5a96164fd2f2abd99c7063a9a92');
INSERT INTO public.active_membership VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 7, '01a0dd31-2647-7765-b52d-8aeaa9ebf903', 'ecf5529674b38ce1e21a4d17ef4d1e1f');


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0dd31-1ed6-750c-bfc4-02d1d2075cc1', '01a0dd31-19b3-7570-9078-158e0e0fabac', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0dd31-1f02-75d4-933f-20499d936310', '01a0dd31-19b2-702b-bd92-d67874bd4bc1', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0dd31-1f5a-713b-83fe-8a8b8154cb39', '01a0dd31-1989-7aaf-aa6c-fa50e3832f1e', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0dd31-1f84-7e84-83bb-e92d3d88e118', '01a0dd31-1952-7d57-88b4-1fca4d26b219', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0dd31-1f84-7e84-83bb-e92d3d88e118', '01a0dd31-1952-7d57-88b4-1fca4d26b219', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0dd31-1fef-7180-8472-cb276f066a4e', '01a0dd31-1950-79d5-aa28-3623540b0241', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0dd31-1fef-7180-8472-cb276f066a4e', '01a0dd31-1950-79d5-aa28-3623540b0241', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0dd31-2473-7115-8f5c-234918df2bb8', '01a0dd31-222a-789b-983e-ce9dcd6697e3', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0dd31-24ce-7241-adcf-ef1620f9e170', '01a0dd31-19b3-7570-9078-158e0e0fabac', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0dd31-24fe-7e63-984c-0c972cdc6134', '01a0dd31-19b2-702b-bd92-d67874bd4bc1', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0dd31-2558-7185-8efa-4e4f6b355685', '01a0dd31-1989-7aaf-aa6c-fa50e3832f1e', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0dd31-257e-771e-bae7-517299fc3a56', '01a0dd31-21df-782d-9fae-c74fc7c400e1', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0dd31-257e-771e-bae7-517299fc3a56', '01a0dd31-21df-782d-9fae-c74fc7c400e1', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0dd31-2a09-7ce4-821e-39737908f6f2', '01a0dd31-2647-7765-b52d-8aeaa9ebf903', 'Rin', 'character', 'located_in', 'market', 'place', NULL, 'stated', 0.9, 'Rin moved to the market.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0dd31-2a1e-746f-9176-8fdcff0f02ea', '01a0dd31-2645-7c66-b9c7-e31a67ace436', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0dd31-2a4d-7186-a52b-7b79f2bd6758', '01a0dd31-2644-760d-8aee-0d21dd40fc4b', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0dd31-2a4d-7186-a52b-7b79f2bd6758', '01a0dd31-2644-760d-8aee-0d21dd40fc4b', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0dd31-2a77-7b62-88e9-57aeab78a5c8', '01a0dd31-2642-75fc-975f-7015e8a113f2', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (19, '01a0dd31-2a77-7b62-88e9-57aeab78a5c8', '01a0dd31-2642-75fc-975f-7015e8a113f2', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown');


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'pocketrisu', NULL, '18c9ce87-9094-4184-83df-a86c6e79abef', '2026-09-26 10:09:37.60658+00', NULL, NULL, NULL, '01a0dd31-222e-7876-83e6-7be9af226fd4', '5ad69c50532f4770ed76d034f6a015613d96674b466dac02f1f18888b2816526', 'Mina', 'Upgrade fixture');
INSERT INTO public.conversation VALUES ('01a0dd31-263c-7037-9012-3b6c2938263e', 'pocketrisu', NULL, 'e5afdd12-2f40-4ccb-8dfd-1fa3f581f2be', '2026-09-26 10:09:40.924753+00', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '18c9ce87-9094-4184-83df-a86c6e79abef', '2ffcd574-0a53-455a-80df-f0785832a2cb', '01a0dd31-2649-7f30-9041-93bb14628730', '0512b3df4a90bcf9dacba28a4670b3b751cabe3cb0eb7fe9bf31cba7ec98b9f9', 'Mina', 'Upgrade fixture');


--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0dd31-1ebc-7294-946b-a62650646843', '01a0dd31-19d6-7514-8fc4-7c78a619b10f', 'bd91a990e5d90a308c129f61e43e94d7', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:39.004675+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 18, "target_chars": 18, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1ed6-750c-bfc4-02d1d2075cc1', '01a0dd31-19b3-7570-9078-158e0e0fabac', '5dac09684db4b239cadf03155140319d', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:39.030668+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 29, "target_chars": 29, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1eed-725a-b2c1-3a228b06b6da', '01a0dd31-19b2-716e-a754-55d85a999b2e', 'd639c3f51a77703a4ab170ebfcb554fc', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:39.053512+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 25, "target_chars": 25, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1f02-75d4-933f-20499d936310', '01a0dd31-19b2-702b-bd92-d67874bd4bc1', '7e19a33ca6fa09e14fd34f82a0ab14fc', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:39.074871+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 53, "target_chars": 53, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1f18-75e5-a327-54d196e46aff', '01a0dd31-19b0-7c96-971a-c5c7334fa379', '74c09ef1f8cabf07e0df36b3228e91d0', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:39.096378+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 25, "target_chars": 25, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1f2d-738b-8954-565420ad5bc9', '01a0dd31-198b-7fe4-a3a5-3472f45d68d0', '0bba9c568d7bbcbc052ca7e448b9165b', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:39.117862+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 35, "target_chars": 35, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1f46-7a79-a998-ddf00f8ae9c5', '01a0dd31-198a-7a9a-9924-15402b69b10f', '2ff74ba54ca0eb5542358ee3181ba3c9', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:39.142214+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 23, "target_chars": 23, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1f5a-713b-83fe-8a8b8154cb39', '01a0dd31-1989-7aaf-aa6c-fa50e3832f1e', '8dd0a1448bad22800d1a2d6e2e3dc3ee', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:39.16259+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 52, "target_chars": 52, "context_messages": 5, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1f6e-7d03-9886-91058f223048', '01a0dd31-1988-7ef4-876a-639eb241fc2c', 'd90843eac439b48469d6dd7a90ae5fd4', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:39.182316+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 34, "target_chars": 34, "context_messages": 4, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1f84-7e84-83bb-e92d3d88e118', '01a0dd31-1952-7d57-88b4-1fca4d26b219', '72e687a56949dfc4fe036a55ce8d7021', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:39.204088+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 45, "target_chars": 45, "context_messages": 3, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1fd8-79ef-9720-9dc6f5f97a35', '01a0dd31-1951-7a30-a3ae-7acb35a5edf4', '88e6f1fee79475f90234ef95621f83b4', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:39.288799+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 16, "target_chars": 16, "context_messages": 2, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-1fef-7180-8472-cb276f066a4e', '01a0dd31-1950-79d5-aa28-3623540b0241', '64a09e656e2ce1afc2b488563a315d0e', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:39.311401+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 50, "target_chars": 50, "context_messages": 1, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2004-7262-946f-20c29daeeede', '01a0dd31-194e-7a25-8d80-a0e0ec67c1eb', 'fd9308e5b25e359067f46879f30c1b4c', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:39.332111+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 30, "target_chars": 30, "context_messages": 0, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-245e-74c0-8311-4c5631e0f5e7', '01a0dd31-222b-7594-b34c-31ef9c391a5a', '833c944206edcae4d9fb92d65791f289', 'extract-v3', 'stub', '{"reply": ""}', '2026-09-26 10:09:40.446305+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 9, "target_chars": 9, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2473-7115-8f5c-234918df2bb8', '01a0dd31-222a-789b-983e-ce9dcd6697e3', 'bdcd55bc351d1e60947285dfc17dac87', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:40.467734+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 27, "target_chars": 27, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2488-71a1-99d9-2cfac3bab909', '01a0dd31-21e1-772b-bb9f-3af6ee06765a', 'eca9aa1b83f8ccfcae18b84aec6ae1c1', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:40.488305+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 16, "target_chars": 16, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-249d-7fef-915c-ed6e153e334f', '01a0dd31-21e0-709a-8445-e4614cea757b', 'f9acc9e09f968aabe49ce2c32b2765e0', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:40.509351+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 31, "target_chars": 31, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-24b2-753c-a8bd-244349fd3a08', '01a0dd31-19d6-7514-8fc4-7c78a619b10f', '0a5a41f6790182ec7915fa4c5fee3d42', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:40.529964+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 18, "target_chars": 18, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-24ce-7241-adcf-ef1620f9e170', '01a0dd31-19b3-7570-9078-158e0e0fabac', '6c79b101701b9cc4462ad1d0be6d26ea', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:40.558757+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 29, "target_chars": 29, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-24e9-74cb-b3e0-110798e1551a', '01a0dd31-19b2-716e-a754-55d85a999b2e', '9f043b54c86073af0dd5eaab43fd16e1', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:40.585611+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 25, "target_chars": 25, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-24fe-7e63-984c-0c972cdc6134', '01a0dd31-19b2-702b-bd92-d67874bd4bc1', '243cf96191944378def783dd7b6f0a5b', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:40.606915+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 53, "target_chars": 53, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2523-7702-a898-6ba862bd00c5', '01a0dd31-198b-7fe4-a3a5-3472f45d68d0', 'dd5477fdb7295daad400391b7de8559c', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:40.643819+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 35, "target_chars": 35, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-253f-707f-a049-885d59fbf3d5', '01a0dd31-198a-7a9a-9924-15402b69b10f', '15c9a947cd4246f643fe4cc4f4753c7b', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:40.671518+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 23, "target_chars": 23, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2558-7185-8efa-4e4f6b355685', '01a0dd31-1989-7aaf-aa6c-fa50e3832f1e', 'daae76df598d2e6929f4c9ca3b06e04a', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:40.696531+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 52, "target_chars": 52, "context_messages": 5, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-256c-7895-b722-c8ead62ba270', '01a0dd31-1988-7ef4-876a-639eb241fc2c', 'db4b00da04156135e5fe7de4a130cbfe', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:40.716057+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 34, "target_chars": 34, "context_messages": 4, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-257e-771e-bae7-517299fc3a56', '01a0dd31-21df-782d-9fae-c74fc7c400e1', '05d187dc7ec8af379b6d81697217f043', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:40.734724+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 48, "target_chars": 48, "context_messages": 3, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2a09-7ce4-821e-39737908f6f2', '01a0dd31-2647-7765-b52d-8aeaa9ebf903', 'ecf5529674b38ce1e21a4d17ef4d1e1f', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"market\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin moved to the market.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:41.897487+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 24, "target_chars": 24, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2a1e-746f-9176-8fdcff0f02ea', '01a0dd31-2645-7c66-b9c7-e31a67ace436', 'b7d318144ddffc51675a381beb06a375', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:41.91888+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 52, "target_chars": 52, "context_messages": 5, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2a37-7c93-9056-623957310255', '01a0dd31-2645-778f-a64f-42eb008725c4', 'd2ba2821fed107a07290201041b8d0d0', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:41.943204+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 34, "target_chars": 34, "context_messages": 4, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2a4d-7186-a52b-7b79f2bd6758', '01a0dd31-2644-760d-8aee-0d21dd40fc4b', 'da5a24f9bff33b9a17429b60e0e7c9fe', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:41.965804+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 48, "target_chars": 48, "context_messages": 3, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2a62-7ed9-85cf-a13e123edf2c', '01a0dd31-2643-718b-9435-6d45c32dc2c6', '512fde5fa326a5256a88d456a8e780c5', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:41.986435+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 16, "target_chars": 16, "context_messages": 2, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2a77-7b62-88e9-57aeab78a5c8', '01a0dd31-2642-75fc-975f-7015e8a113f2', '6769ba52e071e3be81dd12b9a8c2ad21', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:42.007007+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 50, "target_chars": 50, "context_messages": 1, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0dd31-2a8c-7088-ab44-6609740f3e57', '01a0dd31-2642-72ad-9b58-57810882f7bc', '4ab34d4ede0034e77b216de517cc7861', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:42.028403+00', 'extract-4c6f66df7fe54c209d0ff0829eff3f40', '{"target_used": 30, "target_chars": 30, "context_messages": 0, "context_truncated": 0}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0dd31-1953-7470-9e24-24b609454e3c', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'manifest', 'e8e8c75e23a907af076c59d9cab061069efcf853bbf6a707c3793171e2f7f93a', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f:e8e8c75e23a907af076c59d9cab061069efcf853bbf6a707c3793171e2f7f93a:manifest', '2026-09-26 10:09:37.611979+00', '{"chat_id": "18c9ce87-9094-4184-83df-a86c6e79abef", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["7dbc00d0-695e-4da3-813d-15e1f19523b1", "e5a88b24ce5776f2b9f17be02a4ecb62f85115ef1769303421c40c881224aa44", "user", null, null, null, 0, null, null], ["a8bececd-2f3c-40a5-a6ec-9a1a01c34072", "31c7f7064f4af5dc8943d6c76e119b5fc551cadb493a6b5f2d6a5f064785b00c", "char", null, null, null, 0, "a8bececd-2f3c-40a5-a6ec-9a1a01c34072", null], ["bc60835a-0e85-43be-b1b5-ccd2b436f328", "862faddfb174c8afd2f66f4377982296cc9e90139286707fa796f29c8d063dcf", "user", null, null, null, 0, null, null], ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "ec542df1cd9f10b00f3765bf1d3a3a7459e21f1c4bc916d510b508937d800629", "char", null, null, null, 0, "ebdae24c-af65-4eb4-b214-d55a3e71f111", null]]}');
INSERT INTO public.host_observation VALUES ('01a0dd31-198d-7a83-82aa-965d9fa5234d', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'manifest', '1f40dd357eafb14351029620c3b8ca9d801d969ae5a3cd846f3aaec4ecb72f8c', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f:1f40dd357eafb14351029620c3b8ca9d801d969ae5a3cd846f3aaec4ecb72f8c:manifest', '2026-09-26 10:09:37.671818+00', '{"chat_id": "18c9ce87-9094-4184-83df-a86c6e79abef", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["f9fdd22b-6d16-4bb3-8ec4-70025915ffe9", "e165ac3190405e90720980e9a4ba0b3e7b0c4b6a9d69cbb5bfe10a98de191fdc", "user", null, null, null, 0, null, null], ["2ffcd574-0a53-455a-80df-f0785832a2cb", "905a214ac7fd10923133e36f2e5ce197ff40a0c41e005cf119a66e311835b207", "char", null, null, null, 0, "2ffcd574-0a53-455a-80df-f0785832a2cb", null], ["3dabdb1c-6e15-4525-b5d5-7db8bcaa213d", "e5f86f5bf36e44691d6bef6c60e957c4b9fddc5e5163178cea49859e9a355bde", "user", null, null, null, 0, null, null], ["d4aa945f-34da-44c6-9a8d-68b0c1b0306c", "f90162bce00327285ebca5e3b9a0c6761a2a1fb6294ab3de197925afc2e43c39", "char", null, null, null, 0, "d4aa945f-34da-44c6-9a8d-68b0c1b0306c", null]], "base_manifest_hash": "e8e8c75e23a907af076c59d9cab061069efcf853bbf6a707c3793171e2f7f93a"}');
INSERT INTO public.host_observation VALUES ('01a0dd31-19b6-7c31-9ac3-c44cf974cc3b', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'manifest', 'f220caadfac78c897380b875d0586c23a0d4297ee6000939225f4526cc4b3b40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f:f220caadfac78c897380b875d0586c23a0d4297ee6000939225f4526cc4b3b40:manifest', '2026-09-26 10:09:37.712067+00', '{"chat_id": "18c9ce87-9094-4184-83df-a86c6e79abef", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["b6b99cec-6168-45aa-8831-3dbff520600f", "0b939e024e945396a99ec14663e745af2391fa8fbccdc2d7c269311876df7ec5", "user", null, null, null, 0, null, null], ["4ba4776e-6a6f-49a9-8d78-41c03da2b419", "ef2a8f784463059170f8443515ae75c6712873dafac76fb1b2eeb14d10eeeca7", "char", null, null, null, 0, "4ba4776e-6a6f-49a9-8d78-41c03da2b419", null], ["ab733482-3d65-4600-802b-b28a5f994cf7", "2278266624107092398ca637f8eef1752cfcfd36a59d32c4fa97f3f47ce5199a", "user", null, null, null, 0, null, null], ["6597d4bd-e56f-4742-8be4-812b093bbb2b", "6e66944d895a7f903e143e770a2af818d2fc5d85b683aeac2700bd1d59c43778", "char", null, null, null, 0, "6597d4bd-e56f-4742-8be4-812b093bbb2b", null]], "base_manifest_hash": "1f40dd357eafb14351029620c3b8ca9d801d969ae5a3cd846f3aaec4ecb72f8c"}');
INSERT INTO public.host_observation VALUES ('01a0dd31-19d9-75e0-9224-a05bb560d68f', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'manifest', '3d41cb379c9117e77e9e8d81a1d791088f6dac9d3b7c637c9764478a75e0cd1c', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f:3d41cb379c9117e77e9e8d81a1d791088f6dac9d3b7c637c9764478a75e0cd1c:manifest', '2026-09-26 10:09:37.749948+00', '{"chat_id": "18c9ce87-9094-4184-83df-a86c6e79abef", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["0c4b7035-cd47-450a-b7c8-ba01a17aee9f", "b985197685df6ddbdfb1e53f2fa65288d4e86e643fd50c084b208058f355d5fc", "user", null, null, null, 0, null, null]], "base_manifest_hash": "f220caadfac78c897380b875d0586c23a0d4297ee6000939225f4526cc4b3b40"}');
INSERT INTO public.host_observation VALUES ('01a0dd31-21e3-743f-afe4-05220ed72151', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'manifest', '6c353580780eeaf53c17a8a4cc8982b504f3d7f2f4404c189944b37451637766', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f:6c353580780eeaf53c17a8a4cc8982b504f3d7f2f4404c189944b37451637766:manifest', '2026-09-26 10:09:39.807084+00', '{"chat_id": "18c9ce87-9094-4184-83df-a86c6e79abef", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["7dbc00d0-695e-4da3-813d-15e1f19523b1", "e5a88b24ce5776f2b9f17be02a4ecb62f85115ef1769303421c40c881224aa44", "user", null, null, null, 0, null, null], ["a8bececd-2f3c-40a5-a6ec-9a1a01c34072", "31c7f7064f4af5dc8943d6c76e119b5fc551cadb493a6b5f2d6a5f064785b00c", "char", null, null, null, 0, "a8bececd-2f3c-40a5-a6ec-9a1a01c34072", null], ["bc60835a-0e85-43be-b1b5-ccd2b436f328", "862faddfb174c8afd2f66f4377982296cc9e90139286707fa796f29c8d063dcf", "user", null, null, null, 0, null, null], ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "fe2827dae24469d8049c5dc212f0fe44866d5c6799272d5941eab24adb535b90", "char", null, null, null, 0, "ebdae24c-af65-4eb4-b214-d55a3e71f111", null], ["f9fdd22b-6d16-4bb3-8ec4-70025915ffe9", "e165ac3190405e90720980e9a4ba0b3e7b0c4b6a9d69cbb5bfe10a98de191fdc", "user", null, null, null, 0, null, null], ["2ffcd574-0a53-455a-80df-f0785832a2cb", "905a214ac7fd10923133e36f2e5ce197ff40a0c41e005cf119a66e311835b207", "char", null, null, null, 0, "2ffcd574-0a53-455a-80df-f0785832a2cb", null], ["3dabdb1c-6e15-4525-b5d5-7db8bcaa213d", "e5f86f5bf36e44691d6bef6c60e957c4b9fddc5e5163178cea49859e9a355bde", "user", null, null, null, 0, null, null], ["d4aa945f-34da-44c6-9a8d-68b0c1b0306c", "f90162bce00327285ebca5e3b9a0c6761a2a1fb6294ab3de197925afc2e43c39", "char", null, null, null, 0, "d4aa945f-34da-44c6-9a8d-68b0c1b0306c", null], ["b6b99cec-6168-45aa-8831-3dbff520600f", "0b939e024e945396a99ec14663e745af2391fa8fbccdc2d7c269311876df7ec5", "user", null, null, null, 0, null, null], ["4ba4776e-6a6f-49a9-8d78-41c03da2b419", "ef2a8f784463059170f8443515ae75c6712873dafac76fb1b2eeb14d10eeeca7", "char", null, null, null, 0, "4ba4776e-6a6f-49a9-8d78-41c03da2b419", null], ["ab733482-3d65-4600-802b-b28a5f994cf7", "2278266624107092398ca637f8eef1752cfcfd36a59d32c4fa97f3f47ce5199a", "user", null, null, null, 0, null, null], ["6597d4bd-e56f-4742-8be4-812b093bbb2b", "6e66944d895a7f903e143e770a2af818d2fc5d85b683aeac2700bd1d59c43778", "char", null, null, null, 0, "6597d4bd-e56f-4742-8be4-812b093bbb2b", null], ["0c4b7035-cd47-450a-b7c8-ba01a17aee9f", "b985197685df6ddbdfb1e53f2fa65288d4e86e643fd50c084b208058f355d5fc", "user", null, null, null, 0, null, null], ["afe375c9-9537-40bb-9c86-42bffefa2ea4", "0321f79d66f361ce849920c2da243bbd76b3dd294171e057f19f8f37c4d06402", "char", null, null, null, 0, "afe375c9-9537-40bb-9c86-42bffefa2ea4", null], ["b1cb917a-f96a-45cd-831e-1907b8cd5950", "5b6bd801aa533051b7b01231887c37c283256f035963933654faa65d4b786d72", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0dd31-2208-7e13-964e-91b21e62514d', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'manifest', '6fe7797c3da4a9ef61da34f17b3ba4ba53732463dcbfe89cd46740c4b1e0c2f7', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f:6fe7797c3da4a9ef61da34f17b3ba4ba53732463dcbfe89cd46740c4b1e0c2f7:manifest', '2026-09-26 10:09:39.843923+00', '{"chat_id": "18c9ce87-9094-4184-83df-a86c6e79abef", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["28707914-3e38-474c-a3f0-38ec06029637", "5c990b83e326ef234162eb19d3fe01b0f5c05c3572624ddd0f98308070f8c03d", "char", null, null, 1, 2, "28707914-3e38-474c-a3f0-38ec06029637", null]], "base_manifest_hash": "6c353580780eeaf53c17a8a4cc8982b504f3d7f2f4404c189944b37451637766"}');
INSERT INTO public.host_observation VALUES ('01a0dd31-222d-7ddd-925e-c1e1351f5068', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'manifest', '5ad69c50532f4770ed76d034f6a015613d96674b466dac02f1f18888b2816526', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f:5ad69c50532f4770ed76d034f6a015613d96674b466dac02f1f18888b2816526:manifest', '2026-09-26 10:09:39.881011+00', '{"chat_id": "18c9ce87-9094-4184-83df-a86c6e79abef", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["7dbc00d0-695e-4da3-813d-15e1f19523b1", "e5a88b24ce5776f2b9f17be02a4ecb62f85115ef1769303421c40c881224aa44", "user", null, null, null, 0, null, null], ["a8bececd-2f3c-40a5-a6ec-9a1a01c34072", "31c7f7064f4af5dc8943d6c76e119b5fc551cadb493a6b5f2d6a5f064785b00c", "char", null, null, null, 0, "a8bececd-2f3c-40a5-a6ec-9a1a01c34072", null], ["bc60835a-0e85-43be-b1b5-ccd2b436f328", "862faddfb174c8afd2f66f4377982296cc9e90139286707fa796f29c8d063dcf", "user", null, null, null, 0, null, null], ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "fe2827dae24469d8049c5dc212f0fe44866d5c6799272d5941eab24adb535b90", "char", null, null, null, 0, "ebdae24c-af65-4eb4-b214-d55a3e71f111", null], ["f9fdd22b-6d16-4bb3-8ec4-70025915ffe9", "e165ac3190405e90720980e9a4ba0b3e7b0c4b6a9d69cbb5bfe10a98de191fdc", "user", null, null, null, 0, null, null], ["2ffcd574-0a53-455a-80df-f0785832a2cb", "905a214ac7fd10923133e36f2e5ce197ff40a0c41e005cf119a66e311835b207", "char", null, null, null, 0, "2ffcd574-0a53-455a-80df-f0785832a2cb", null], ["3dabdb1c-6e15-4525-b5d5-7db8bcaa213d", "e5f86f5bf36e44691d6bef6c60e957c4b9fddc5e5163178cea49859e9a355bde", "user", null, null, null, 0, null, null], ["d4aa945f-34da-44c6-9a8d-68b0c1b0306c", "f90162bce00327285ebca5e3b9a0c6761a2a1fb6294ab3de197925afc2e43c39", "char", null, null, null, 0, "d4aa945f-34da-44c6-9a8d-68b0c1b0306c", null], ["b6b99cec-6168-45aa-8831-3dbff520600f", "4d35914192c5e5ccf872a052a8f32e82b3617593798f39ffa862432e5247b0fd", "user", true, null, null, 0, null, null], ["4ba4776e-6a6f-49a9-8d78-41c03da2b419", "ef2a8f784463059170f8443515ae75c6712873dafac76fb1b2eeb14d10eeeca7", "char", null, null, null, 0, "4ba4776e-6a6f-49a9-8d78-41c03da2b419", null], ["ab733482-3d65-4600-802b-b28a5f994cf7", "2278266624107092398ca637f8eef1752cfcfd36a59d32c4fa97f3f47ce5199a", "user", null, null, null, 0, null, null], ["6597d4bd-e56f-4742-8be4-812b093bbb2b", "6e66944d895a7f903e143e770a2af818d2fc5d85b683aeac2700bd1d59c43778", "char", null, null, null, 0, "6597d4bd-e56f-4742-8be4-812b093bbb2b", null], ["0c4b7035-cd47-450a-b7c8-ba01a17aee9f", "b985197685df6ddbdfb1e53f2fa65288d4e86e643fd50c084b208058f355d5fc", "user", null, null, null, 0, null, null], ["afe375c9-9537-40bb-9c86-42bffefa2ea4", "0321f79d66f361ce849920c2da243bbd76b3dd294171e057f19f8f37c4d06402", "char", null, null, null, 0, "afe375c9-9537-40bb-9c86-42bffefa2ea4", null], ["b1cb917a-f96a-45cd-831e-1907b8cd5950", "5b6bd801aa533051b7b01231887c37c283256f035963933654faa65d4b786d72", "user", null, null, null, 0, null, null], ["28707914-3e38-474c-a3f0-38ec06029637", "f8da90ae0bde1c21cd45b2d3de88e1ee3ef34eb934a2b0c61f91ca72f49e2fbd", "char", null, null, 0, 2, "28707914-3e38-474c-a3f0-38ec06029637", null], ["a510c9c7-5271-4530-a5c2-946712ad3245", "879f4a546cd900aabd903af161f6c909ecca4cfaacdc38b3590a18c739144e85", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0dd31-2648-7ec8-8ca6-9647c9846c2e', '01a0dd31-263c-7037-9012-3b6c2938263e', 'manifest', '0512b3df4a90bcf9dacba28a4670b3b751cabe3cb0eb7fe9bf31cba7ec98b9f9', '01a0dd31-263c-7037-9012-3b6c2938263e:0512b3df4a90bcf9dacba28a4670b3b751cabe3cb0eb7fe9bf31cba7ec98b9f9:manifest', '2026-09-26 10:09:40.929202+00', '{"chat_id": "e5afdd12-2f40-4ccb-8dfd-1fa3f581f2be", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["3a706102-a50b-40b2-a369-0277eae9b505", "f06bf022c7e81917ee77b9255ac171f129e67fe74d6a88733405ee129fc0bd2e", "user", null, null, null, 0, null, null], ["bf85d576-f1a2-4291-be64-4b622d301906", "21a316346beb075de0e9e02131cfdd84b7b2be49b8d602b703ed3327057401ba", "char", null, null, null, 0, "a8bececd-2f3c-40a5-a6ec-9a1a01c34072", null], ["4c9b0695-212c-4218-9cb5-8236dd7f48db", "59e2e21aeb5afeac4fe52f0a2e78baec5f37e55c63001fcde617339c251c30a4", "user", null, null, null, 0, null, null], ["cf2e8c87-1535-45bd-a4c8-76050bef85c4", "091f9fea320075b22a6f698586486a8460974b4cd30c98ab6e9b494f438f2e4b", "char", null, null, null, 0, "ebdae24c-af65-4eb4-b214-d55a3e71f111", null], ["dcc24320-ca73-4a4b-b809-2c5d3718cde7", "fd47da1fc1cf93e3a140da3d6d7e08fe10f5f7435db342700615167fe2f9fd2e", "user", null, null, null, 0, null, null], ["7dd97721-3273-4913-bfd7-a4fc7661fd71", "a155ba30b3aa235c3d76a7c58171f63931009f78a849f03a67c55dc282c2b320", "char", null, null, null, 0, "2ffcd574-0a53-455a-80df-f0785832a2cb", null], ["3f9cc783-7ae3-471c-9640-b65eecd371b3", "03756bff8bb11e48b1474bb5cd9ec9ee853212bc9790b5712fc5a8b52d29632c", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::18c9ce87-9094-4184-83df-a86c6e79abef::Harbor route::2ffcd574-0a53-455a-80df-f0785832a2cb::}}"]], ["1635d4a7-6b9e-4445-ad15-eb71c660d761", "56bdb23c853dde13efb3e31f630b4602c7f1433ba76c07123a0afc00663cb5c5", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'embed', 'embed:01a0dd31-19b2-716e-a754-55d85a999b2e:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-19b2-716e-a754-55d85a999b2e"}', 50, 'done', 1, '2026-09-26 10:09:37.712067+00', NULL, NULL, '2026-09-26 10:09:37.712067+00', '2026-09-26 10:09:38.834622+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'embed', 'embed:01a0dd31-19b2-702b-bd92-d67874bd4bc1:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-19b2-702b-bd92-d67874bd4bc1"}', 50, 'done', 1, '2026-09-26 10:09:37.712067+00', NULL, NULL, '2026-09-26 10:09:37.712067+00', '2026-09-26 10:09:38.856385+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0dd31-19b0-7c96-971a-c5c7334fa379:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-19b0-7c96-971a-c5c7334fa379"}', 50, 'done', 1, '2026-09-26 10:09:37.712067+00', NULL, NULL, '2026-09-26 10:09:37.712067+00', '2026-09-26 10:09:38.878657+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0dd31-198a-7a9a-9924-15402b69b10f:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-198a-7a9a-9924-15402b69b10f"}', 50, 'done', 1, '2026-09-26 10:09:37.671818+00', NULL, NULL, '2026-09-26 10:09:37.671818+00', '2026-09-26 10:09:38.919845+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'embed', 'embed:01a0dd31-1989-7aaf-aa6c-fa50e3832f1e:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-1989-7aaf-aa6c-fa50e3832f1e"}', 50, 'done', 1, '2026-09-26 10:09:37.671818+00', NULL, NULL, '2026-09-26 10:09:37.671818+00', '2026-09-26 10:09:38.938822+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0dd31-1988-7ef4-876a-639eb241fc2c:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-1988-7ef4-876a-639eb241fc2c"}', 50, 'done', 1, '2026-09-26 10:09:37.671818+00', NULL, NULL, '2026-09-26 10:09:37.671818+00', '2026-09-26 10:09:38.958615+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0dd31-1952-7d57-88b4-1fca4d26b219:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-1952-7d57-88b4-1fca4d26b219"}', 50, 'done', 1, '2026-09-26 10:09:37.671818+00', NULL, NULL, '2026-09-26 10:09:37.671818+00', '2026-09-26 10:09:38.978921+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0dd31-19b2-716e-a754-55d85a999b2e:d639c3f51a77703a4ab170ebfcb554fc:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b2-716e-a754-55d85a999b2e", "window_hash": "d639c3f51a77703a4ab170ebfcb554fc"}', 100, 'done', 1, '2026-09-26 10:09:37.712067+00', NULL, NULL, '2026-09-26 10:09:37.712067+00', '2026-09-26 10:09:39.055077+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'extract', 'extract:01a0dd31-19b2-702b-bd92-d67874bd4bc1:7e19a33ca6fa09e14fd34f82a0ab14fc:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b2-702b-bd92-d67874bd4bc1", "window_hash": "7e19a33ca6fa09e14fd34f82a0ab14fc"}', 100, 'done', 1, '2026-09-26 10:09:37.712067+00', NULL, NULL, '2026-09-26 10:09:37.712067+00', '2026-09-26 10:09:39.076753+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0dd31-19b0-7c96-971a-c5c7334fa379:74c09ef1f8cabf07e0df36b3228e91d0:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b0-7c96-971a-c5c7334fa379", "window_hash": "74c09ef1f8cabf07e0df36b3228e91d0"}', 100, 'done', 1, '2026-09-26 10:09:37.712067+00', NULL, NULL, '2026-09-26 10:09:37.712067+00', '2026-09-26 10:09:39.098042+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'extract', 'extract:01a0dd31-198b-7fe4-a3a5-3472f45d68d0:0bba9c568d7bbcbc052ca7e448b9165b:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-198b-7fe4-a3a5-3472f45d68d0", "window_hash": "0bba9c568d7bbcbc052ca7e448b9165b"}', 100, 'done', 1, '2026-09-26 10:09:37.712067+00', NULL, NULL, '2026-09-26 10:09:37.712067+00', '2026-09-26 10:09:39.119504+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'extract', 'extract:01a0dd31-198a-7a9a-9924-15402b69b10f:2ff74ba54ca0eb5542358ee3181ba3c9:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-198a-7a9a-9924-15402b69b10f", "window_hash": "2ff74ba54ca0eb5542358ee3181ba3c9"}', 100, 'done', 1, '2026-09-26 10:09:37.671818+00', NULL, NULL, '2026-09-26 10:09:37.671818+00', '2026-09-26 10:09:39.143724+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0dd31-1989-7aaf-aa6c-fa50e3832f1e:8dd0a1448bad22800d1a2d6e2e3dc3ee:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-1989-7aaf-aa6c-fa50e3832f1e", "window_hash": "8dd0a1448bad22800d1a2d6e2e3dc3ee"}', 100, 'done', 1, '2026-09-26 10:09:37.671818+00', NULL, NULL, '2026-09-26 10:09:37.671818+00', '2026-09-26 10:09:39.16434+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'extract', 'extract:01a0dd31-1988-7ef4-876a-639eb241fc2c:d90843eac439b48469d6dd7a90ae5fd4:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-1988-7ef4-876a-639eb241fc2c", "window_hash": "d90843eac439b48469d6dd7a90ae5fd4"}', 100, 'done', 1, '2026-09-26 10:09:37.671818+00', NULL, NULL, '2026-09-26 10:09:37.671818+00', '2026-09-26 10:09:39.183836+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'extract', 'extract:01a0dd31-1952-7d57-88b4-1fca4d26b219:72e687a56949dfc4fe036a55ce8d7021:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-1952-7d57-88b4-1fca4d26b219", "window_hash": "72e687a56949dfc4fe036a55ce8d7021"}', 100, 'done', 1, '2026-09-26 10:09:37.671818+00', NULL, NULL, '2026-09-26 10:09:37.671818+00', '2026-09-26 10:09:39.205946+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'embed', 'embed:01a0dd31-1951-7a30-a3ae-7acb35a5edf4:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-1951-7a30-a3ae-7acb35a5edf4"}', 150, 'done', 1, '2026-09-26 10:09:37.611979+00', NULL, NULL, '2026-09-26 10:09:37.611979+00', '2026-09-26 10:09:39.226093+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0dd31-1950-79d5-aa28-3623540b0241:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-1950-79d5-aa28-3623540b0241"}', 150, 'done', 1, '2026-09-26 10:09:37.611979+00', NULL, NULL, '2026-09-26 10:09:37.611979+00', '2026-09-26 10:09:39.246419+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0dd31-194e-7a25-8d80-a0e0ec67c1eb:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-194e-7a25-8d80-a0e0ec67c1eb"}', 150, 'done', 1, '2026-09-26 10:09:37.611979+00', NULL, NULL, '2026-09-26 10:09:37.611979+00', '2026-09-26 10:09:39.265027+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0dd31-1951-7a30-a3ae-7acb35a5edf4:88e6f1fee79475f90234ef95621f83b4:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-1951-7a30-a3ae-7acb35a5edf4", "window_hash": "88e6f1fee79475f90234ef95621f83b4"}', 200, 'done', 1, '2026-09-26 10:09:37.611979+00', NULL, NULL, '2026-09-26 10:09:37.611979+00', '2026-09-26 10:09:39.290474+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'extract', 'extract:01a0dd31-1950-79d5-aa28-3623540b0241:64a09e656e2ce1afc2b488563a315d0e:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-1950-79d5-aa28-3623540b0241", "window_hash": "64a09e656e2ce1afc2b488563a315d0e"}', 200, 'done', 1, '2026-09-26 10:09:37.611979+00', NULL, NULL, '2026-09-26 10:09:37.611979+00', '2026-09-26 10:09:39.313226+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0dd31-194e-7a25-8d80-a0e0ec67c1eb:fd9308e5b25e359067f46879f30c1b4c:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-194e-7a25-8d80-a0e0ec67c1eb", "window_hash": "fd9308e5b25e359067f46879f30c1b4c"}', 200, 'done', 1, '2026-09-26 10:09:37.611979+00', NULL, NULL, '2026-09-26 10:09:37.611979+00', '2026-09-26 10:09:39.333604+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0dd31-19d6-7514-8fc4-7c78a619b10f:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-19d6-7514-8fc4-7c78a619b10f"}', 50, 'done', 1, '2026-09-26 10:09:37.749948+00', NULL, NULL, '2026-09-26 10:09:37.749948+00', '2026-09-26 10:09:38.795717+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'embed', 'embed:01a0dd31-19b3-7570-9078-158e0e0fabac:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-19b3-7570-9078-158e0e0fabac"}', 50, 'done', 1, '2026-09-26 10:09:37.749948+00', NULL, NULL, '2026-09-26 10:09:37.749948+00', '2026-09-26 10:09:38.816004+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0dd31-198b-7fe4-a3a5-3472f45d68d0:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-198b-7fe4-a3a5-3472f45d68d0"}', 50, 'done', 1, '2026-09-26 10:09:37.712067+00', NULL, NULL, '2026-09-26 10:09:37.712067+00', '2026-09-26 10:09:38.899404+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'extract', 'extract:01a0dd31-19d6-7514-8fc4-7c78a619b10f:bd91a990e5d90a308c129f61e43e94d7:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19d6-7514-8fc4-7c78a619b10f", "window_hash": "bd91a990e5d90a308c129f61e43e94d7"}', 100, 'done', 1, '2026-09-26 10:09:37.749948+00', NULL, NULL, '2026-09-26 10:09:37.749948+00', '2026-09-26 10:09:39.006931+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0dd31-19b3-7570-9078-158e0e0fabac:5dac09684db4b239cadf03155140319d:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b3-7570-9078-158e0e0fabac", "window_hash": "5dac09684db4b239cadf03155140319d"}', 100, 'done', 1, '2026-09-26 10:09:37.749948+00', NULL, NULL, '2026-09-26 10:09:37.749948+00', '2026-09-26 10:09:39.033448+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (60, 'embed', 'embed:01a0dd31-222b-7594-b34c-31ef9c391a5a:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-222b-7594-b34c-31ef9c391a5a"}', 50, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.362876+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (53, 'extract', 'extract:01a0dd31-21e0-709a-8445-e4614cea757b:f9acc9e09f968aabe49ce2c32b2765e0:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-21e0-709a-8445-e4614cea757b", "window_hash": "f9acc9e09f968aabe49ce2c32b2765e0"}', 100, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.51108+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'extract', 'extract:01a0dd31-21df-782d-9fae-c74fc7c400e1:05d187dc7ec8af379b6d81697217f043:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-21df-782d-9fae-c74fc7c400e1", "window_hash": "05d187dc7ec8af379b6d81697217f043"}', 100, 'done', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.736435+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (62, 'embed', 'embed:01a0dd31-2642-72ad-9b58-57810882f7bc:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-2642-72ad-9b58-57810882f7bc"}', 150, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.879527+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (63, 'extract', 'extract:01a0dd31-2642-75fc-975f-7015e8a113f2:6769ba52e071e3be81dd12b9a8c2ad21:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-2642-75fc-975f-7015e8a113f2", "window_hash": "6769ba52e071e3be81dd12b9a8c2ad21"}', 200, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:42.010266+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (61, 'extract', 'extract:01a0dd31-2642-72ad-9b58-57810882f7bc:4ab34d4ede0034e77b216de517cc7861:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-2642-72ad-9b58-57810882f7bc", "window_hash": "4ab34d4ede0034e77b216de517cc7861"}', 200, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:42.029895+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (58, 'embed', 'embed:01a0dd31-222a-789b-983e-ce9dcd6697e3:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-222a-789b-983e-ce9dcd6697e3"}', 50, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.381131+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (44, 'embed', 'embed:01a0dd31-21e1-772b-bb9f-3af6ee06765a:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-21e1-772b-bb9f-3af6ee06765a"}', 50, 'done', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.399489+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0dd31-21e0-709a-8445-e4614cea757b:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-21e0-709a-8445-e4614cea757b"}', 50, 'done', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.422629+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'embed', 'embed:01a0dd31-21df-782d-9fae-c74fc7c400e1:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-21df-782d-9fae-c74fc7c400e1"}', 50, 'done', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.441068+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (59, 'extract', 'extract:01a0dd31-222b-7594-b34c-31ef9c391a5a:833c944206edcae4d9fb92d65791f289:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-222b-7594-b34c-31ef9c391a5a", "window_hash": "833c944206edcae4d9fb92d65791f289"}', 100, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.447956+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (57, 'extract', 'extract:01a0dd31-222a-789b-983e-ce9dcd6697e3:bdcd55bc351d1e60947285dfc17dac87:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-222a-789b-983e-ce9dcd6697e3", "window_hash": "bdcd55bc351d1e60947285dfc17dac87"}', 100, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.469382+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (55, 'extract', 'extract:01a0dd31-21e1-772b-bb9f-3af6ee06765a:eca9aa1b83f8ccfcae18b84aec6ae1c1:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-21e1-772b-bb9f-3af6ee06765a", "window_hash": "eca9aa1b83f8ccfcae18b84aec6ae1c1"}', 100, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.48975+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (51, 'extract', 'extract:01a0dd31-19d6-7514-8fc4-7c78a619b10f:0a5a41f6790182ec7915fa4c5fee3d42:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19d6-7514-8fc4-7c78a619b10f", "window_hash": "0a5a41f6790182ec7915fa4c5fee3d42"}', 100, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.531535+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (49, 'extract', 'extract:01a0dd31-19b3-7570-9078-158e0e0fabac:6c79b101701b9cc4462ad1d0be6d26ea:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b3-7570-9078-158e0e0fabac", "window_hash": "6c79b101701b9cc4462ad1d0be6d26ea"}', 100, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.563616+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (47, 'extract', 'extract:01a0dd31-19b2-716e-a754-55d85a999b2e:9f043b54c86073af0dd5eaab43fd16e1:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b2-716e-a754-55d85a999b2e", "window_hash": "9f043b54c86073af0dd5eaab43fd16e1"}', 100, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.587109+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (45, 'extract', 'extract:01a0dd31-19b2-702b-bd92-d67874bd4bc1:243cf96191944378def783dd7b6f0a5b:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b2-702b-bd92-d67874bd4bc1", "window_hash": "243cf96191944378def783dd7b6f0a5b"}', 100, 'done', 1, '2026-09-26 10:09:39.881011+00', NULL, NULL, '2026-09-26 10:09:39.881011+00', '2026-09-26 10:09:40.608739+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'extract', 'extract:01a0dd31-21e1-772b-bb9f-3af6ee06765a:e09316a9f4fb07f770258617f7eb9adb:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-21e1-772b-bb9f-3af6ee06765a", "window_hash": "e09316a9f4fb07f770258617f7eb9adb"}', 100, 'obsolete', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.611896+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'extract', 'extract:01a0dd31-21e0-709a-8445-e4614cea757b:12cd6541c04b5b71d97391b0ec4e6726:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-21e0-709a-8445-e4614cea757b", "window_hash": "12cd6541c04b5b71d97391b0ec4e6726"}', 100, 'obsolete', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.615336+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'extract', 'extract:01a0dd31-19b2-702b-bd92-d67874bd4bc1:35636de7f2cec00d375e6db342d6ec3a:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b2-702b-bd92-d67874bd4bc1", "window_hash": "35636de7f2cec00d375e6db342d6ec3a"}', 100, 'obsolete', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.618521+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'extract', 'extract:01a0dd31-19b0-7c96-971a-c5c7334fa379:7bea80d2c4e62bdc8005db165744ab5b:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-19b0-7c96-971a-c5c7334fa379", "window_hash": "7bea80d2c4e62bdc8005db165744ab5b"}', 100, 'obsolete', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.621908+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0dd31-198b-7fe4-a3a5-3472f45d68d0:dd5477fdb7295daad400391b7de8559c:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-198b-7fe4-a3a5-3472f45d68d0", "window_hash": "dd5477fdb7295daad400391b7de8559c"}', 100, 'done', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.648173+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'extract', 'extract:01a0dd31-198a-7a9a-9924-15402b69b10f:15c9a947cd4246f643fe4cc4f4753c7b:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-198a-7a9a-9924-15402b69b10f", "window_hash": "15c9a947cd4246f643fe4cc4f4753c7b"}', 100, 'done', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.673067+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0dd31-1989-7aaf-aa6c-fa50e3832f1e:daae76df598d2e6929f4c9ca3b06e04a:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-1989-7aaf-aa6c-fa50e3832f1e", "window_hash": "daae76df598d2e6929f4c9ca3b06e04a"}', 100, 'done', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.6983+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0dd31-1988-7ef4-876a-639eb241fc2c:db4b00da04156135e5fe7de4a130cbfe:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-1988-7ef4-876a-639eb241fc2c", "window_hash": "db4b00da04156135e5fe7de4a130cbfe"}', 100, 'done', 1, '2026-09-26 10:09:39.807084+00', NULL, NULL, '2026-09-26 10:09:39.807084+00', '2026-09-26 10:09:40.717493+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (74, 'embed', 'embed:01a0dd31-2647-7765-b52d-8aeaa9ebf903:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-2647-7765-b52d-8aeaa9ebf903"}', 150, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.75931+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (72, 'embed', 'embed:01a0dd31-2645-7c66-b9c7-e31a67ace436:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-2645-7c66-b9c7-e31a67ace436"}', 150, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.779053+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (70, 'embed', 'embed:01a0dd31-2645-778f-a64f-42eb008725c4:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-2645-778f-a64f-42eb008725c4"}', 150, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.798158+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (68, 'embed', 'embed:01a0dd31-2644-760d-8aee-0d21dd40fc4b:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-2644-760d-8aee-0d21dd40fc4b"}', 150, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.820328+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (66, 'embed', 'embed:01a0dd31-2643-718b-9435-6d45c32dc2c6:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-2643-718b-9435-6d45c32dc2c6"}', 150, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.839883+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (64, 'embed', 'embed:01a0dd31-2642-75fc-975f-7015e8a113f2:embed-83450cab2bdc589276178e93b671e9b2', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "embed-83450cab2bdc589276178e93b671e9b2", "revision_id": "01a0dd31-2642-75fc-975f-7015e8a113f2"}', 150, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.859114+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (73, 'extract', 'extract:01a0dd31-2647-7765-b52d-8aeaa9ebf903:ecf5529674b38ce1e21a4d17ef4d1e1f:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-2647-7765-b52d-8aeaa9ebf903", "window_hash": "ecf5529674b38ce1e21a4d17ef4d1e1f"}', 200, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.89935+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (71, 'extract', 'extract:01a0dd31-2645-7c66-b9c7-e31a67ace436:b7d318144ddffc51675a381beb06a375:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-2645-7c66-b9c7-e31a67ace436", "window_hash": "b7d318144ddffc51675a381beb06a375"}', 200, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.920581+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (69, 'extract', 'extract:01a0dd31-2645-778f-a64f-42eb008725c4:d2ba2821fed107a07290201041b8d0d0:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-2645-778f-a64f-42eb008725c4", "window_hash": "d2ba2821fed107a07290201041b8d0d0"}', 200, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.944619+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (67, 'extract', 'extract:01a0dd31-2644-760d-8aee-0d21dd40fc4b:da5a24f9bff33b9a17429b60e0e7c9fe:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-2644-760d-8aee-0d21dd40fc4b", "window_hash": "da5a24f9bff33b9a17429b60e0e7c9fe"}', 200, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.967611+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (65, 'extract', 'extract:01a0dd31-2643-718b-9435-6d45c32dc2c6:512fde5fa326a5256a88d456a8e780c5:extract-4c6f66df7fe54c209d0ff0829eff3f40', '01a0dd31-263c-7037-9012-3b6c2938263e', '{"generation": "extract-4c6f66df7fe54c209d0ff0829eff3f40", "revision_id": "01a0dd31-2643-718b-9435-6d45c32dc2c6", "window_hash": "512fde5fa326a5256a88d456a8e780c5"}', 200, 'done', 1, '2026-09-26 10:09:40.929202+00', NULL, NULL, '2026-09-26 10:09:40.929202+00', '2026-09-26 10:09:41.987836+00');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-4c6f66df7fe54c209d0ff0829eff3f40', 'extract', 'stub', 'http://127.0.0.1:44227/v1', '{"kind": "extract", "model": "stub", "prompt": "beea838dfb7120ac", "window": 6, "compiler": "extract-v3", "endpoint": "http://127.0.0.1:44227/v1", "json_mode": true, "normalizer": "clean-v1", "predicates": "253e9535891a7be7", "temperature": 0, "target_chars": 6000, "context_chars": 2000}', '2026-09-26 10:09:37.419052+00', '2026-09-26 10:09:37.422847+00');
INSERT INTO public.projection_generation VALUES ('embed-83450cab2bdc589276178e93b671e9b2', 'embed', 'stub-embed', 'http://127.0.0.1:44227/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:44227/v1", "max_chunks": 8, "normalizer": "clean-v1", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-26 10:09:37.419052+00', '2026-09-26 10:09:37.425746+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0dd31-197a-72df-8b12-699fe8a0408f', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '01a0dd31-1955-77c6-99d8-5b884c5f9f8b', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0dd31-1951-7a30-a3ae-7acb35a5edf4", "host_logical_id": "bc60835a-0e85-43be-b1b5-ccd2b436f328"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0dd31-1951-7a30-a3ae-7acb35a5edf4", "host_logical_id": "bc60835a-0e85-43be-b1b5-ccd2b436f328"}]', 0, '{"embed": 24.42, "facts": 0, "vector": 1.61, "lexical": 2.87, "extractor": "extract-4c6f66df7fe5", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 29.92, "embedding_projection": "embed-83450cab2bdc58"}', 'fresh', '2026-09-26 10:09:37.628654+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-19a7-7177-a1f9-6c9e8680769b', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '01a0dd31-1955-77c6-99d8-5b884c5f9f8b', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0dd31-198a-7a9a-9924-15402b69b10f", "host_logical_id": "3dabdb1c-6e15-4525-b5d5-7db8bcaa213d"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0dd31-198a-7a9a-9924-15402b69b10f", "host_logical_id": "3dabdb1c-6e15-4525-b5d5-7db8bcaa213d"}]', 0, '{"embed": 14.27, "facts": 0, "vector": 1.85, "lexical": 2.75, "extractor": "extract-4c6f66df7fe5", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 19.88, "embedding_projection": "embed-83450cab2bdc58"}', 'fresh', '2026-09-26 10:09:37.683309+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-19cd-7264-a8c8-d31c92a3f33c', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '01a0dd31-1955-77c6-99d8-5b884c5f9f8b', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0dd31-19b2-716e-a754-55d85a999b2e", "host_logical_id": "ab733482-3d65-4600-802b-b28a5f994cf7"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0dd31-19b2-716e-a754-55d85a999b2e", "host_logical_id": "ab733482-3d65-4600-802b-b28a5f994cf7"}]', 0, '{"embed": 13.74, "facts": 0, "vector": 1.08, "lexical": 2.29, "extractor": "extract-4c6f66df7fe5", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 17.88, "embedding_projection": "embed-83450cab2bdc58"}', 'fresh', '2026-09-26 10:09:37.723614+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-19f2-7543-a135-34efe10ed054', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '01a0dd31-1955-77c6-99d8-5b884c5f9f8b', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0dd31-19d6-7514-8fc4-7c78a619b10f", "host_logical_id": "0c4b7035-cd47-450a-b7c8-ba01a17aee9f"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0dd31-1952-7d57-88b4-1fca4d26b219", "host_logical_id": "ebdae24c-af65-4eb4-b214-d55a3e71f111"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0dd31-1950-79d5-aa28-3623540b0241", "host_logical_id": "a8bececd-2f3c-40a5-a6ec-9a1a01c34072"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0dd31-1950-79d5-aa28-3623540b0241"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0dd31-1952-7d57-88b4-1fca4d26b219"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0dd31-19d6-7514-8fc4-7c78a619b10f", "host_logical_id": "0c4b7035-cd47-450a-b7c8-ba01a17aee9f"}]', 174, '{"embed": 15.49, "facts": 0, "vector": 1.12, "lexical": 2.37, "extractor": "extract-4c6f66df7fe5", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 19.84, "embedding_projection": "embed-83450cab2bdc58"}', 'fresh', '2026-09-26 10:09:37.758459+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-21fa-7df6-b4cb-f80f3d65bc7e', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '01a0dd31-21e4-75ec-a011-f7f6b21d2376', 'And the compass?', '[{"rrf": 0.03151, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0dd31-19b2-702b-bd92-d67874bd4bc1", "host_logical_id": "4ba4776e-6a6f-49a9-8d78-41c03da2b419"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0dd31-21e1-772b-bb9f-3af6ee06765a", "host_logical_id": "b1cb917a-f96a-45cd-831e-1907b8cd5950"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0dd31-1950-79d5-aa28-3623540b0241", "host_logical_id": "a8bececd-2f3c-40a5-a6ec-9a1a01c34072"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0dd31-194e-7a25-8d80-a0e0ec67c1eb", "host_logical_id": "7dbc00d0-695e-4da3-813d-15e1f19523b1"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0dd31-198b-7fe4-a3a5-3472f45d68d0", "host_logical_id": "d4aa945f-34da-44c6-9a8d-68b0c1b0306c"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0dd31-194e-7a25-8d80-a0e0ec67c1eb"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0dd31-1950-79d5-aa28-3623540b0241"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0dd31-198b-7fe4-a3a5-3472f45d68d0"}, {"turn": 9, "score": 0.03151, "revision_id": "01a0dd31-19b2-702b-bd92-d67874bd4bc1"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0dd31-21e1-772b-bb9f-3af6ee06765a", "host_logical_id": "b1cb917a-f96a-45cd-831e-1907b8cd5950"}]', 223, '{"embed": 12.9, "facts": 0, "vector": 0.85, "lexical": 2.08, "extractor": "extract-4c6f66df7fe5", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 16.65, "embedding_projection": "embed-83450cab2bdc58"}', 'fresh', '2026-09-26 10:09:39.817768+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-221f-70db-88b8-0e0ab8a011aa', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '01a0dd31-21e4-75ec-a011-f7f6b21d2376', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0dd31-19b2-702b-bd92-d67874bd4bc1", "host_logical_id": "4ba4776e-6a6f-49a9-8d78-41c03da2b419"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0dd31-21e1-772b-bb9f-3af6ee06765a", "host_logical_id": "b1cb917a-f96a-45cd-831e-1907b8cd5950"}, {"rrf": 0.01639, "sim": 0.5799, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0dd31-1989-7aaf-aa6c-fa50e3832f1e", "host_logical_id": "2ffcd574-0a53-455a-80df-f0785832a2cb"}, {"rrf": 0.01613, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0dd31-19b3-7570-9078-158e0e0fabac", "host_logical_id": "6597d4bd-e56f-4742-8be4-812b093bbb2b"}]', '[{"turn": 5, "score": 0.01639, "revision_id": "01a0dd31-1989-7aaf-aa6c-fa50e3832f1e"}, {"turn": 9, "score": 0.03002, "revision_id": "01a0dd31-19b2-702b-bd92-d67874bd4bc1"}, {"turn": 11, "score": 0.01613, "revision_id": "01a0dd31-19b3-7570-9078-158e0e0fabac"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0dd31-21e1-772b-bb9f-3af6ee06765a", "host_logical_id": "b1cb917a-f96a-45cd-831e-1907b8cd5950"}]', 200, '{"embed": 14.3, "facts": 0, "vector": 1.16, "lexical": 3.04, "extractor": "extract-4c6f66df7fe5", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 19.41, "embedding_projection": "embed-83450cab2bdc58"}', 'fresh', '2026-09-26 10:09:39.852304+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-2246-7200-a138-0700589a7e3c', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '01a0dd31-222e-7876-83e6-7be9af226fd4', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0dd31-198a-7a9a-9924-15402b69b10f", "host_logical_id": "3dabdb1c-6e15-4525-b5d5-7db8bcaa213d"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0dd31-222b-7594-b34c-31ef9c391a5a", "host_logical_id": "a510c9c7-5271-4530-a5c2-946712ad3245"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0dd31-198a-7a9a-9924-15402b69b10f"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0dd31-222b-7594-b34c-31ef9c391a5a", "host_logical_id": "a510c9c7-5271-4530-a5c2-946712ad3245"}]', 138, '{"embed": 13.26, "facts": 0, "vector": 0.94, "lexical": 2.36, "extractor": "extract-4c6f66df7fe5", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 17.3, "embedding_projection": "embed-83450cab2bdc58"}', 'fresh', '2026-09-26 10:09:39.893398+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-2660-789a-b13a-6195a2f73a5b', '01a0dd31-263c-7037-9012-3b6c2938263e', '01a0dd31-2649-7f30-9041-93bb14628730', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0dd31-2643-718b-9435-6d45c32dc2c6", "host_logical_id": "4c9b0695-212c-4218-9cb5-8236dd7f48db"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0dd31-2644-760d-8aee-0d21dd40fc4b", "host_logical_id": "cf2e8c87-1535-45bd-a4c8-76050bef85c4"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0dd31-2643-718b-9435-6d45c32dc2c6"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0dd31-2644-760d-8aee-0d21dd40fc4b"}]', '[]', 164, '{"embed": 14.18, "facts": 0, "vector": 0.88, "lexical": 2.19, "extractor": "extract-4c6f66df7fe5", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 18.01, "embedding_projection": "embed-83450cab2bdc58"}', 'fresh', '2026-09-26 10:09:40.943033+00');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0dd31-19d6-7514-8fc4-7c78a619b10f', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-19b3-7570-9078-158e0e0fabac', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-19b2-716e-a754-55d85a999b2e', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-19b2-702b-bd92-d67874bd4bc1', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-19b0-7c96-971a-c5c7334fa379', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-198b-7fe4-a3a5-3472f45d68d0', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-198a-7a9a-9924-15402b69b10f', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-1989-7aaf-aa6c-fa50e3832f1e', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-1988-7ef4-876a-639eb241fc2c', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-1952-7d57-88b4-1fca4d26b219', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-1951-7a30-a3ae-7acb35a5edf4', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-1950-79d5-aa28-3623540b0241', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-194e-7a25-8d80-a0e0ec67c1eb', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-222b-7594-b34c-31ef9c391a5a', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-222a-789b-983e-ce9dcd6697e3', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-21e1-772b-bb9f-3af6ee06765a', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-21e0-709a-8445-e4614cea757b', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-21df-782d-9fae-c74fc7c400e1', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-2647-7765-b52d-8aeaa9ebf903', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-2645-7c66-b9c7-e31a67ace436', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-2645-778f-a64f-42eb008725c4', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-2644-760d-8aee-0d21dd40fc4b', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-2643-718b-9435-6d45c32dc2c6', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-2642-75fc-975f-7015e8a113f2', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-83450cab2bdc589276178e93b671e9b2');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-2642-72ad-9b58-57810882f7bc', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-83450cab2bdc589276178e93b671e9b2');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0dd31-194e-7a25-8d80-a0e0ec67c1eb', 'clean-v1', 'We should rest somewhere safe.', 30, 30, '2026-09-26 10:09:37.611979+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-1950-79d5-aa28-3623540b0241', 'clean-v1', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-26 10:09:37.611979+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-1951-7a30-a3ae-7acb35a5edf4', 'clean-v1', 'Is Rin with you?', 16, 16, '2026-09-26 10:09:37.611979+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-1952-7d57-88b4-1fca4d26b219', 'clean-v1', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-26 10:09:37.611979+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-1988-7ef4-876a-639eb241fc2c', 'clean-v1', 'What did Mina say before she left?', 34, 34, '2026-09-26 10:09:37.671818+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-1989-7aaf-aa6c-fa50e3832f1e', 'clean-v1', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-26 10:09:37.671818+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-198a-7a9a-9924-15402b69b10f', 'clean-v1', 'Let''s check the market.', 23, 23, '2026-09-26 10:09:37.671818+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-198b-7fe4-a3a5-3472f45d68d0', 'clean-v1', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-26 10:09:37.671818+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-19b0-7c96-971a-c5c7334fa379', 'clean-v1', 'Any news from the harbor?', 25, 25, '2026-09-26 10:09:37.712067+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-19b2-702b-bd92-d67874bd4bc1', 'clean-v1', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-26 10:09:37.712067+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-19b2-716e-a754-55d85a999b2e', 'clean-v1', 'Where do we meet tonight?', 25, 25, '2026-09-26 10:09:37.712067+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-19b3-7570-9078-158e0e0fabac', 'clean-v1', 'Mina moved to the bell tower.', 29, 29, '2026-09-26 10:09:37.712067+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-19d6-7514-8fc4-7c78a619b10f', 'clean-v1', 'Where is Mina now?', 18, 18, '2026-09-26 10:09:37.749948+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-21df-782d-9fae-c74fc7c400e1', 'clean-v1', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-26 10:09:39.807084+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-21e0-709a-8445-e4614cea757b', 'clean-v1', 'Mina keeps the brass key close.', 31, 31, '2026-09-26 10:09:39.807084+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-21e1-772b-bb9f-3af6ee06765a', 'clean-v1', 'And the compass?', 16, 16, '2026-09-26 10:09:39.807084+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2205-795b-b200-cd91da3f23ca', 'clean-v1', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-26 10:09:39.843923+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2229-7cbb-b6cb-418422de5f72', 'clean-v1', 'Any news from the harbor?', 25, 25, '2026-09-26 10:09:39.881011+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-222a-789b-983e-ce9dcd6697e3', 'clean-v1', 'Rin has the silver compass.', 27, 27, '2026-09-26 10:09:39.881011+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-222b-7594-b34c-31ef9c391a5a', 'clean-v1', 'Let''s go.', 9, 9, '2026-09-26 10:09:39.881011+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2642-72ad-9b58-57810882f7bc', 'clean-v1', 'We should rest somewhere safe.', 30, 30, '2026-09-26 10:09:40.929202+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2642-75fc-975f-7015e8a113f2', 'clean-v1', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-26 10:09:40.929202+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2643-718b-9435-6d45c32dc2c6', 'clean-v1', 'Is Rin with you?', 16, 16, '2026-09-26 10:09:40.929202+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2644-760d-8aee-0d21dd40fc4b', 'clean-v1', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-26 10:09:40.929202+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2645-778f-a64f-42eb008725c4', 'clean-v1', 'What did Mina say before she left?', 34, 34, '2026-09-26 10:09:40.929202+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2645-7c66-b9c7-e31a67ace436', 'clean-v1', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-26 10:09:40.929202+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2646-7d22-a3eb-74d21639dbcf', 'clean-v1', '{{specialcomment::branchedfrom::18c9ce87-9094-4184-83df-a86c6e79abef::Harbor route::2ffcd574-0a53-455a-80df-f0785832a2cb::}}', 124, 124, '2026-09-26 10:09:40.929202+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-2647-7765-b52d-8aeaa9ebf903', 'clean-v1', 'Rin moved to the market.', 24, 24, '2026-09-26 10:09:40.929202+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-26 10:09:36.765955+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-26 10:09:36.846843+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-26 10:09:36.863345+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-26 10:09:36.906805+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-26 10:09:36.927681+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-26 10:09:36.937196+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-26 10:09:36.939169+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-26 10:09:36.948793+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-26 10:09:36.966618+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-26 10:09:36.968599+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0dd31-194d-7b29-b6eb-d9670f941510', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '7dbc00d0-695e-4da3-813d-15e1f19523b1', 'message', '2026-09-26 10:09:37.611979+00');
INSERT INTO public.source_object VALUES ('01a0dd31-1950-76fd-978a-6d3dc46e04ae', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'a8bececd-2f3c-40a5-a6ec-9a1a01c34072', 'message', '2026-09-26 10:09:37.611979+00');
INSERT INTO public.source_object VALUES ('01a0dd31-1951-740e-8317-7edfa77b1eea', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'bc60835a-0e85-43be-b1b5-ccd2b436f328', 'message', '2026-09-26 10:09:37.611979+00');
INSERT INTO public.source_object VALUES ('01a0dd31-1951-7aab-b1f5-c57018c2140c', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'ebdae24c-af65-4eb4-b214-d55a3e71f111', 'message', '2026-09-26 10:09:37.611979+00');
INSERT INTO public.source_object VALUES ('01a0dd31-1988-707a-b7c4-840fb63ecf8a', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'f9fdd22b-6d16-4bb3-8ec4-70025915ffe9', 'message', '2026-09-26 10:09:37.671818+00');
INSERT INTO public.source_object VALUES ('01a0dd31-1989-73af-adc5-fa523b7e0105', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '2ffcd574-0a53-455a-80df-f0785832a2cb', 'message', '2026-09-26 10:09:37.671818+00');
INSERT INTO public.source_object VALUES ('01a0dd31-198a-72a0-b022-e7a6abb73560', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '3dabdb1c-6e15-4525-b5d5-7db8bcaa213d', 'message', '2026-09-26 10:09:37.671818+00');
INSERT INTO public.source_object VALUES ('01a0dd31-198b-7be5-8a06-14a5da3574df', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'd4aa945f-34da-44c6-9a8d-68b0c1b0306c', 'message', '2026-09-26 10:09:37.671818+00');
INSERT INTO public.source_object VALUES ('01a0dd31-19b0-7db1-8efc-67a1c67f5398', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'b6b99cec-6168-45aa-8831-3dbff520600f', 'message', '2026-09-26 10:09:37.712067+00');
INSERT INTO public.source_object VALUES ('01a0dd31-19b1-72c1-81d3-187b3d30751c', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '4ba4776e-6a6f-49a9-8d78-41c03da2b419', 'message', '2026-09-26 10:09:37.712067+00');
INSERT INTO public.source_object VALUES ('01a0dd31-19b2-76ac-8501-2fcc01f1080d', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'ab733482-3d65-4600-802b-b28a5f994cf7', 'message', '2026-09-26 10:09:37.712067+00');
INSERT INTO public.source_object VALUES ('01a0dd31-19b3-7ef6-8390-cc8df252d5ec', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '6597d4bd-e56f-4742-8be4-812b093bbb2b', 'message', '2026-09-26 10:09:37.712067+00');
INSERT INTO public.source_object VALUES ('01a0dd31-19d6-7d96-b4dc-7beb0122b36b', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '0c4b7035-cd47-450a-b7c8-ba01a17aee9f', 'message', '2026-09-26 10:09:37.749948+00');
INSERT INTO public.source_object VALUES ('01a0dd31-21e0-7e43-bfdf-5a8ee70f3f71', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'afe375c9-9537-40bb-9c86-42bffefa2ea4', 'message', '2026-09-26 10:09:39.807084+00');
INSERT INTO public.source_object VALUES ('01a0dd31-21e1-75fa-bb8b-4640bec273c4', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'b1cb917a-f96a-45cd-831e-1907b8cd5950', 'message', '2026-09-26 10:09:39.807084+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2204-7c8c-a0c1-1f8b06de5103', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '28707914-3e38-474c-a3f0-38ec06029637', 'message', '2026-09-26 10:09:39.843923+00');
INSERT INTO public.source_object VALUES ('01a0dd31-222b-7808-8e5a-0b76104cc51f', '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', 'a510c9c7-5271-4530-a5c2-946712ad3245', 'message', '2026-09-26 10:09:39.881011+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2641-70b9-a0b5-6415aa98a4eb', '01a0dd31-263c-7037-9012-3b6c2938263e', '3a706102-a50b-40b2-a369-0277eae9b505', 'message', '2026-09-26 10:09:40.929202+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2642-7c4f-9863-f072beab35f4', '01a0dd31-263c-7037-9012-3b6c2938263e', 'bf85d576-f1a2-4291-be64-4b622d301906', 'message', '2026-09-26 10:09:40.929202+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2643-798a-8b37-f3b882fe3079', '01a0dd31-263c-7037-9012-3b6c2938263e', '4c9b0695-212c-4218-9cb5-8236dd7f48db', 'message', '2026-09-26 10:09:40.929202+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2644-7dac-b772-fbc9f2a86957', '01a0dd31-263c-7037-9012-3b6c2938263e', 'cf2e8c87-1535-45bd-a4c8-76050bef85c4', 'message', '2026-09-26 10:09:40.929202+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2644-798d-898b-d5f7444667f0', '01a0dd31-263c-7037-9012-3b6c2938263e', 'dcc24320-ca73-4a4b-b809-2c5d3718cde7', 'message', '2026-09-26 10:09:40.929202+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2645-7bbe-9f1d-6f99534f9a1d', '01a0dd31-263c-7037-9012-3b6c2938263e', '7dd97721-3273-4913-bfd7-a4fc7661fd71', 'message', '2026-09-26 10:09:40.929202+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2646-7fac-a5ed-1b2bdd81d88a', '01a0dd31-263c-7037-9012-3b6c2938263e', '3f9cc783-7ae3-471c-9640-b65eecd371b3', 'message', '2026-09-26 10:09:40.929202+00');
INSERT INTO public.source_object VALUES ('01a0dd31-2646-7df3-945d-a35c3f6f5776', '01a0dd31-263c-7037-9012-3b6c2938263e', '1635d4a7-6b9e-4445-ad15-eb71c660d761', 'message', '2026-09-26 10:09:40.929202+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0dd31-194e-7a25-8d80-a0e0ec67c1eb', '01a0dd31-194d-7b29-b6eb-d9670f941510', 'e5a88b24ce5776f2b9f17be02a4ecb62f85115ef1769303421c40c881224aa44', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "7dbc00d0-695e-4da3-813d-15e1f19523b1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:37.611979+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-1951-7a30-a3ae-7acb35a5edf4', '01a0dd31-1951-740e-8317-7edfa77b1eea', '862faddfb174c8afd2f66f4377982296cc9e90139286707fa796f29c8d063dcf', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "bc60835a-0e85-43be-b1b5-ccd2b436f328", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:37.611979+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-1950-79d5-aa28-3623540b0241', '01a0dd31-1950-76fd-978a-6d3dc46e04ae', '31c7f7064f4af5dc8943d6c76e119b5fc551cadb493a6b5f2d6a5f064785b00c', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "a8bececd-2f3c-40a5-a6ec-9a1a01c34072", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a8bececd-2f3c-40a5-a6ec-9a1a01c34072", "specialComments": []}', '2026-09-26 10:09:37.611979+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-1988-7ef4-876a-639eb241fc2c', '01a0dd31-1988-707a-b7c4-840fb63ecf8a', 'e165ac3190405e90720980e9a4ba0b3e7b0c4b6a9d69cbb5bfe10a98de191fdc', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "f9fdd22b-6d16-4bb3-8ec4-70025915ffe9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:37.671818+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-198a-7a9a-9924-15402b69b10f', '01a0dd31-198a-72a0-b022-e7a6abb73560', 'e5f86f5bf36e44691d6bef6c60e957c4b9fddc5e5163178cea49859e9a355bde', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "3dabdb1c-6e15-4525-b5d5-7db8bcaa213d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:37.671818+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-1989-7aaf-aa6c-fa50e3832f1e', '01a0dd31-1989-73af-adc5-fa523b7e0105', '905a214ac7fd10923133e36f2e5ce197ff40a0c41e005cf119a66e311835b207', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "2ffcd574-0a53-455a-80df-f0785832a2cb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "2ffcd574-0a53-455a-80df-f0785832a2cb", "specialComments": []}', '2026-09-26 10:09:37.671818+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-19b2-716e-a754-55d85a999b2e', '01a0dd31-19b2-76ac-8501-2fcc01f1080d', '2278266624107092398ca637f8eef1752cfcfd36a59d32c4fa97f3f47ce5199a', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "ab733482-3d65-4600-802b-b28a5f994cf7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:37.712067+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-19b2-702b-bd92-d67874bd4bc1', '01a0dd31-19b1-72c1-81d3-187b3d30751c', 'ef2a8f784463059170f8443515ae75c6712873dafac76fb1b2eeb14d10eeeca7', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "4ba4776e-6a6f-49a9-8d78-41c03da2b419", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "4ba4776e-6a6f-49a9-8d78-41c03da2b419", "specialComments": []}', '2026-09-26 10:09:37.712067+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-198b-7fe4-a3a5-3472f45d68d0', '01a0dd31-198b-7be5-8a06-14a5da3574df', 'f90162bce00327285ebca5e3b9a0c6761a2a1fb6294ab3de197925afc2e43c39', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "d4aa945f-34da-44c6-9a8d-68b0c1b0306c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "d4aa945f-34da-44c6-9a8d-68b0c1b0306c", "specialComments": []}', '2026-09-26 10:09:37.671818+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-19d6-7514-8fc4-7c78a619b10f', '01a0dd31-19d6-7d96-b4dc-7beb0122b36b', 'b985197685df6ddbdfb1e53f2fa65288d4e86e643fd50c084b208058f355d5fc', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "0c4b7035-cd47-450a-b7c8-ba01a17aee9f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:37.749948+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-19b3-7570-9078-158e0e0fabac', '01a0dd31-19b3-7ef6-8390-cc8df252d5ec', '6e66944d895a7f903e143e770a2af818d2fc5d85b683aeac2700bd1d59c43778', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "6597d4bd-e56f-4742-8be4-812b093bbb2b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6597d4bd-e56f-4742-8be4-812b093bbb2b", "specialComments": []}', '2026-09-26 10:09:37.712067+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-21e1-772b-bb9f-3af6ee06765a', '01a0dd31-21e1-75fa-bb8b-4640bec273c4', '5b6bd801aa533051b7b01231887c37c283256f035963933654faa65d4b786d72', 'And the compass?', '{"name": null, "role": "user", "chatId": "b1cb917a-f96a-45cd-831e-1907b8cd5950", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:39.807084+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-21e0-709a-8445-e4614cea757b', '01a0dd31-21e0-7e43-bfdf-5a8ee70f3f71', '0321f79d66f361ce849920c2da243bbd76b3dd294171e057f19f8f37c4d06402', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "afe375c9-9537-40bb-9c86-42bffefa2ea4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "afe375c9-9537-40bb-9c86-42bffefa2ea4", "specialComments": []}', '2026-09-26 10:09:39.807084+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-1952-7d57-88b4-1fca4d26b219', '01a0dd31-1951-7aab-b1f5-c57018c2140c', 'ec542df1cd9f10b00f3765bf1d3a3a7459e21f1c4bc916d510b508937d800629', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "ebdae24c-af65-4eb4-b214-d55a3e71f111", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "ebdae24c-af65-4eb4-b214-d55a3e71f111", "specialComments": []}', '2026-09-26 10:09:37.611979+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2205-795b-b200-cd91da3f23ca', '01a0dd31-2204-7c8c-a0c1-1f8b06de5103', '5c990b83e326ef234162eb19d3fe01b0f5c05c3572624ddd0f98308070f8c03d', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "28707914-3e38-474c-a3f0-38ec06029637", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "28707914-3e38-474c-a3f0-38ec06029637", "specialComments": []}', '2026-09-26 10:09:39.843923+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-19b0-7c96-971a-c5c7334fa379', '01a0dd31-19b0-7db1-8efc-67a1c67f5398', '0b939e024e945396a99ec14663e745af2391fa8fbccdc2d7c269311876df7ec5', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "b6b99cec-6168-45aa-8831-3dbff520600f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:37.712067+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2642-72ad-9b58-57810882f7bc', '01a0dd31-2641-70b9-a0b5-6415aa98a4eb', 'f06bf022c7e81917ee77b9255ac171f129e67fe74d6a88733405ee129fc0bd2e', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "3a706102-a50b-40b2-a369-0277eae9b505", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:40.929202+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-21df-782d-9fae-c74fc7c400e1', '01a0dd31-1951-7aab-b1f5-c57018c2140c', 'fe2827dae24469d8049c5dc212f0fe44866d5c6799272d5941eab24adb535b90', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "ebdae24c-af65-4eb4-b214-d55a3e71f111", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "ebdae24c-af65-4eb4-b214-d55a3e71f111", "specialComments": []}', '2026-09-26 10:09:39.807084+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2229-7cbb-b6cb-418422de5f72', '01a0dd31-19b0-7db1-8efc-67a1c67f5398', '4d35914192c5e5ccf872a052a8f32e82b3617593798f39ffa862432e5247b0fd', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "b6b99cec-6168-45aa-8831-3dbff520600f", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:39.881011+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-222b-7594-b34c-31ef9c391a5a', '01a0dd31-222b-7808-8e5a-0b76104cc51f', '879f4a546cd900aabd903af161f6c909ecca4cfaacdc38b3590a18c739144e85', 'Let''s go.', '{"name": null, "role": "user", "chatId": "a510c9c7-5271-4530-a5c2-946712ad3245", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:39.881011+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-222a-789b-983e-ce9dcd6697e3', '01a0dd31-2204-7c8c-a0c1-1f8b06de5103', 'f8da90ae0bde1c21cd45b2d3de88e1ee3ef34eb934a2b0c61f91ca72f49e2fbd', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "28707914-3e38-474c-a3f0-38ec06029637", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "28707914-3e38-474c-a3f0-38ec06029637", "specialComments": []}', '2026-09-26 10:09:39.881011+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2643-718b-9435-6d45c32dc2c6', '01a0dd31-2643-798a-8b37-f3b882fe3079', '59e2e21aeb5afeac4fe52f0a2e78baec5f37e55c63001fcde617339c251c30a4', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "4c9b0695-212c-4218-9cb5-8236dd7f48db", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:40.929202+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2645-778f-a64f-42eb008725c4', '01a0dd31-2644-798d-898b-d5f7444667f0', 'fd47da1fc1cf93e3a140da3d6d7e08fe10f5f7435db342700615167fe2f9fd2e', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "dcc24320-ca73-4a4b-b809-2c5d3718cde7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:40.929202+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2646-7d22-a3eb-74d21639dbcf', '01a0dd31-2646-7fac-a5ed-1b2bdd81d88a', '03756bff8bb11e48b1474bb5cd9ec9ee853212bc9790b5712fc5a8b52d29632c', '{{specialcomment::branchedfrom::18c9ce87-9094-4184-83df-a86c6e79abef::Harbor route::2ffcd574-0a53-455a-80df-f0785832a2cb::}}', '{"name": null, "role": "char", "chatId": "3f9cc783-7ae3-471c-9640-b65eecd371b3", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::18c9ce87-9094-4184-83df-a86c6e79abef::Harbor route::2ffcd574-0a53-455a-80df-f0785832a2cb::}}"]}', '2026-09-26 10:09:40.929202+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2647-7765-b52d-8aeaa9ebf903', '01a0dd31-2646-7df3-945d-a35c3f6f5776', '56bdb23c853dde13efb3e31f630b4602c7f1433ba76c07123a0afc00663cb5c5', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "1635d4a7-6b9e-4445-ad15-eb71c660d761", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:40.929202+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2645-7c66-b9c7-e31a67ace436', '01a0dd31-2645-7bbe-9f1d-6f99534f9a1d', 'a155ba30b3aa235c3d76a7c58171f63931009f78a849f03a67c55dc282c2b320', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "7dd97721-3273-4913-bfd7-a4fc7661fd71", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "2ffcd574-0a53-455a-80df-f0785832a2cb", "specialComments": []}', '2026-09-26 10:09:40.929202+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2642-75fc-975f-7015e8a113f2', '01a0dd31-2642-7c4f-9863-f072beab35f4', '21a316346beb075de0e9e02131cfdd84b7b2be49b8d602b703ed3327057401ba', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "bf85d576-f1a2-4291-be64-4b622d301906", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a8bececd-2f3c-40a5-a6ec-9a1a01c34072", "specialComments": []}', '2026-09-26 10:09:40.929202+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-2644-760d-8aee-0d21dd40fc4b', '01a0dd31-2644-7dac-b772-fbc9f2a86957', '091f9fea320075b22a6f698586486a8460974b4cd30c98ab6e9b494f438f2e4b', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "cf2e8c87-1535-45bd-a4c8-76050bef85c4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "ebdae24c-af65-4eb4-b214-d55a3e71f111", "specialComments": []}', '2026-09-26 10:09:40.929202+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0dd31-222e-7876-83e6-7be9af226fd4', 3, '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{01a0dd31-21e4-75ec-a011-f7f6b21d2376}', 'reconciliation', '5ad69c50532f4770ed76d034f6a015613d96674b466dac02f1f18888b2816526', '{"ops": [{"op": "replace", "to": ["b6b99cec-6168-45aa-8831-3dbff520600f", "4d35914192c5e5ccf872a052a8f32e82b3617593798f39ffa862432e5247b0fd"], "from": ["b6b99cec-6168-45aa-8831-3dbff520600f", "0b939e024e945396a99ec14663e745af2391fa8fbccdc2d7c269311876df7ec5"]}, {"op": "replace", "to": ["28707914-3e38-474c-a3f0-38ec06029637", "f8da90ae0bde1c21cd45b2d3de88e1ee3ef34eb934a2b0c61f91ca72f49e2fbd"], "from": ["28707914-3e38-474c-a3f0-38ec06029637", "5c990b83e326ef234162eb19d3fe01b0f5c05c3572624ddd0f98308070f8c03d"]}, {"op": "insert", "after": ["28707914-3e38-474c-a3f0-38ec06029637", "f8da90ae0bde1c21cd45b2d3de88e1ee3ef34eb934a2b0c61f91ca72f49e2fbd"], "member": ["a510c9c7-5271-4530-a5c2-946712ad3245", "879f4a546cd900aabd903af161f6c909ecca4cfaacdc38b3590a18c739144e85"]}], "changes": [{"new": ["b6b99cec-6168-45aa-8831-3dbff520600f", "4d35914192c5e5ccf872a052a8f32e82b3617593798f39ffa862432e5247b0fd"], "old": ["b6b99cec-6168-45aa-8831-3dbff520600f", "0b939e024e945396a99ec14663e745af2391fa8fbccdc2d7c269311876df7ec5"], "kind": "disable", "position": 8, "host_logical_id": "b6b99cec-6168-45aa-8831-3dbff520600f"}, {"new": ["28707914-3e38-474c-a3f0-38ec06029637", "f8da90ae0bde1c21cd45b2d3de88e1ee3ef34eb934a2b0c61f91ca72f49e2fbd"], "old": ["28707914-3e38-474c-a3f0-38ec06029637", "5c990b83e326ef234162eb19d3fe01b0f5c05c3572624ddd0f98308070f8c03d"], "kind": "swipe", "position": 15, "host_logical_id": "28707914-3e38-474c-a3f0-38ec06029637"}, {"new": ["a510c9c7-5271-4530-a5c2-946712ad3245", "879f4a546cd900aabd903af161f6c909ecca4cfaacdc38b3590a18c739144e85"], "old": null, "kind": "append", "position": 16, "host_logical_id": "a510c9c7-5271-4530-a5c2-946712ad3245"}]}', '2026-09-26 10:09:39.881011+00', '01a0dd31-222d-7ddd-925e-c1e1351f5068');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0dd31-1955-77c6-99d8-5b884c5f9f8b', 1, '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{}', 'import', 'e8e8c75e23a907af076c59d9cab061069efcf853bbf6a707c3793171e2f7f93a', '{"ops": [{"op": "set", "members": [["7dbc00d0-695e-4da3-813d-15e1f19523b1", "e5a88b24ce5776f2b9f17be02a4ecb62f85115ef1769303421c40c881224aa44"], ["a8bececd-2f3c-40a5-a6ec-9a1a01c34072", "31c7f7064f4af5dc8943d6c76e119b5fc551cadb493a6b5f2d6a5f064785b00c"], ["bc60835a-0e85-43be-b1b5-ccd2b436f328", "862faddfb174c8afd2f66f4377982296cc9e90139286707fa796f29c8d063dcf"], ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "ec542df1cd9f10b00f3765bf1d3a3a7459e21f1c4bc916d510b508937d800629"]]}, {"op": "insert", "after": ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "ec542df1cd9f10b00f3765bf1d3a3a7459e21f1c4bc916d510b508937d800629"], "member": ["f9fdd22b-6d16-4bb3-8ec4-70025915ffe9", "e165ac3190405e90720980e9a4ba0b3e7b0c4b6a9d69cbb5bfe10a98de191fdc"]}, {"op": "insert", "after": ["f9fdd22b-6d16-4bb3-8ec4-70025915ffe9", "e165ac3190405e90720980e9a4ba0b3e7b0c4b6a9d69cbb5bfe10a98de191fdc"], "member": ["2ffcd574-0a53-455a-80df-f0785832a2cb", "905a214ac7fd10923133e36f2e5ce197ff40a0c41e005cf119a66e311835b207"]}, {"op": "insert", "after": ["2ffcd574-0a53-455a-80df-f0785832a2cb", "905a214ac7fd10923133e36f2e5ce197ff40a0c41e005cf119a66e311835b207"], "member": ["3dabdb1c-6e15-4525-b5d5-7db8bcaa213d", "e5f86f5bf36e44691d6bef6c60e957c4b9fddc5e5163178cea49859e9a355bde"]}, {"op": "insert", "after": ["3dabdb1c-6e15-4525-b5d5-7db8bcaa213d", "e5f86f5bf36e44691d6bef6c60e957c4b9fddc5e5163178cea49859e9a355bde"], "member": ["d4aa945f-34da-44c6-9a8d-68b0c1b0306c", "f90162bce00327285ebca5e3b9a0c6761a2a1fb6294ab3de197925afc2e43c39"]}, {"op": "insert", "after": ["d4aa945f-34da-44c6-9a8d-68b0c1b0306c", "f90162bce00327285ebca5e3b9a0c6761a2a1fb6294ab3de197925afc2e43c39"], "member": ["b6b99cec-6168-45aa-8831-3dbff520600f", "0b939e024e945396a99ec14663e745af2391fa8fbccdc2d7c269311876df7ec5"]}, {"op": "insert", "after": ["b6b99cec-6168-45aa-8831-3dbff520600f", "0b939e024e945396a99ec14663e745af2391fa8fbccdc2d7c269311876df7ec5"], "member": ["4ba4776e-6a6f-49a9-8d78-41c03da2b419", "ef2a8f784463059170f8443515ae75c6712873dafac76fb1b2eeb14d10eeeca7"]}, {"op": "insert", "after": ["4ba4776e-6a6f-49a9-8d78-41c03da2b419", "ef2a8f784463059170f8443515ae75c6712873dafac76fb1b2eeb14d10eeeca7"], "member": ["ab733482-3d65-4600-802b-b28a5f994cf7", "2278266624107092398ca637f8eef1752cfcfd36a59d32c4fa97f3f47ce5199a"]}, {"op": "insert", "after": ["ab733482-3d65-4600-802b-b28a5f994cf7", "2278266624107092398ca637f8eef1752cfcfd36a59d32c4fa97f3f47ce5199a"], "member": ["6597d4bd-e56f-4742-8be4-812b093bbb2b", "6e66944d895a7f903e143e770a2af818d2fc5d85b683aeac2700bd1d59c43778"]}, {"op": "insert", "after": ["6597d4bd-e56f-4742-8be4-812b093bbb2b", "6e66944d895a7f903e143e770a2af818d2fc5d85b683aeac2700bd1d59c43778"], "member": ["0c4b7035-cd47-450a-b7c8-ba01a17aee9f", "b985197685df6ddbdfb1e53f2fa65288d4e86e643fd50c084b208058f355d5fc"]}], "changes": [{"new": ["7dbc00d0-695e-4da3-813d-15e1f19523b1", "e5a88b24ce5776f2b9f17be02a4ecb62f85115ef1769303421c40c881224aa44"], "old": null, "kind": "append", "position": 0, "host_logical_id": "7dbc00d0-695e-4da3-813d-15e1f19523b1"}, {"new": ["a8bececd-2f3c-40a5-a6ec-9a1a01c34072", "31c7f7064f4af5dc8943d6c76e119b5fc551cadb493a6b5f2d6a5f064785b00c"], "old": null, "kind": "append", "position": 1, "host_logical_id": "a8bececd-2f3c-40a5-a6ec-9a1a01c34072"}, {"new": ["bc60835a-0e85-43be-b1b5-ccd2b436f328", "862faddfb174c8afd2f66f4377982296cc9e90139286707fa796f29c8d063dcf"], "old": null, "kind": "append", "position": 2, "host_logical_id": "bc60835a-0e85-43be-b1b5-ccd2b436f328"}, {"new": ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "ec542df1cd9f10b00f3765bf1d3a3a7459e21f1c4bc916d510b508937d800629"], "old": null, "kind": "append", "position": 3, "host_logical_id": "ebdae24c-af65-4eb4-b214-d55a3e71f111"}, {"new": ["f9fdd22b-6d16-4bb3-8ec4-70025915ffe9", "e165ac3190405e90720980e9a4ba0b3e7b0c4b6a9d69cbb5bfe10a98de191fdc"], "old": null, "kind": "append", "position": 4, "host_logical_id": "f9fdd22b-6d16-4bb3-8ec4-70025915ffe9"}, {"new": ["2ffcd574-0a53-455a-80df-f0785832a2cb", "905a214ac7fd10923133e36f2e5ce197ff40a0c41e005cf119a66e311835b207"], "old": null, "kind": "append", "position": 5, "host_logical_id": "2ffcd574-0a53-455a-80df-f0785832a2cb"}, {"new": ["3dabdb1c-6e15-4525-b5d5-7db8bcaa213d", "e5f86f5bf36e44691d6bef6c60e957c4b9fddc5e5163178cea49859e9a355bde"], "old": null, "kind": "append", "position": 6, "host_logical_id": "3dabdb1c-6e15-4525-b5d5-7db8bcaa213d"}, {"new": ["d4aa945f-34da-44c6-9a8d-68b0c1b0306c", "f90162bce00327285ebca5e3b9a0c6761a2a1fb6294ab3de197925afc2e43c39"], "old": null, "kind": "append", "position": 7, "host_logical_id": "d4aa945f-34da-44c6-9a8d-68b0c1b0306c"}, {"new": ["b6b99cec-6168-45aa-8831-3dbff520600f", "0b939e024e945396a99ec14663e745af2391fa8fbccdc2d7c269311876df7ec5"], "old": null, "kind": "append", "position": 8, "host_logical_id": "b6b99cec-6168-45aa-8831-3dbff520600f"}, {"new": ["4ba4776e-6a6f-49a9-8d78-41c03da2b419", "ef2a8f784463059170f8443515ae75c6712873dafac76fb1b2eeb14d10eeeca7"], "old": null, "kind": "append", "position": 9, "host_logical_id": "4ba4776e-6a6f-49a9-8d78-41c03da2b419"}, {"new": ["ab733482-3d65-4600-802b-b28a5f994cf7", "2278266624107092398ca637f8eef1752cfcfd36a59d32c4fa97f3f47ce5199a"], "old": null, "kind": "append", "position": 10, "host_logical_id": "ab733482-3d65-4600-802b-b28a5f994cf7"}, {"new": ["6597d4bd-e56f-4742-8be4-812b093bbb2b", "6e66944d895a7f903e143e770a2af818d2fc5d85b683aeac2700bd1d59c43778"], "old": null, "kind": "append", "position": 11, "host_logical_id": "6597d4bd-e56f-4742-8be4-812b093bbb2b"}, {"new": ["0c4b7035-cd47-450a-b7c8-ba01a17aee9f", "b985197685df6ddbdfb1e53f2fa65288d4e86e643fd50c084b208058f355d5fc"], "old": null, "kind": "append", "position": 12, "host_logical_id": "0c4b7035-cd47-450a-b7c8-ba01a17aee9f"}]}', '2026-09-26 10:09:37.611979+00', '01a0dd31-1953-7470-9e24-24b609454e3c');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0dd31-21e4-75ec-a011-f7f6b21d2376', 2, '01a0dd31-1946-78fe-be6f-b0b04fe2a29f', '{01a0dd31-1955-77c6-99d8-5b884c5f9f8b}', 'edit', '6c353580780eeaf53c17a8a4cc8982b504f3d7f2f4404c189944b37451637766', '{"ops": [{"op": "replace", "to": ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "fe2827dae24469d8049c5dc212f0fe44866d5c6799272d5941eab24adb535b90"], "from": ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "ec542df1cd9f10b00f3765bf1d3a3a7459e21f1c4bc916d510b508937d800629"]}, {"op": "insert", "after": ["0c4b7035-cd47-450a-b7c8-ba01a17aee9f", "b985197685df6ddbdfb1e53f2fa65288d4e86e643fd50c084b208058f355d5fc"], "member": ["afe375c9-9537-40bb-9c86-42bffefa2ea4", "0321f79d66f361ce849920c2da243bbd76b3dd294171e057f19f8f37c4d06402"]}, {"op": "insert", "after": ["afe375c9-9537-40bb-9c86-42bffefa2ea4", "0321f79d66f361ce849920c2da243bbd76b3dd294171e057f19f8f37c4d06402"], "member": ["b1cb917a-f96a-45cd-831e-1907b8cd5950", "5b6bd801aa533051b7b01231887c37c283256f035963933654faa65d4b786d72"]}, {"op": "insert", "after": ["b1cb917a-f96a-45cd-831e-1907b8cd5950", "5b6bd801aa533051b7b01231887c37c283256f035963933654faa65d4b786d72"], "member": ["28707914-3e38-474c-a3f0-38ec06029637", "5c990b83e326ef234162eb19d3fe01b0f5c05c3572624ddd0f98308070f8c03d"]}], "changes": [{"new": ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "fe2827dae24469d8049c5dc212f0fe44866d5c6799272d5941eab24adb535b90"], "old": ["ebdae24c-af65-4eb4-b214-d55a3e71f111", "ec542df1cd9f10b00f3765bf1d3a3a7459e21f1c4bc916d510b508937d800629"], "kind": "edit", "position": 3, "host_logical_id": "ebdae24c-af65-4eb4-b214-d55a3e71f111"}, {"new": ["afe375c9-9537-40bb-9c86-42bffefa2ea4", "0321f79d66f361ce849920c2da243bbd76b3dd294171e057f19f8f37c4d06402"], "old": null, "kind": "append", "position": 13, "host_logical_id": "afe375c9-9537-40bb-9c86-42bffefa2ea4"}, {"new": ["b1cb917a-f96a-45cd-831e-1907b8cd5950", "5b6bd801aa533051b7b01231887c37c283256f035963933654faa65d4b786d72"], "old": null, "kind": "append", "position": 14, "host_logical_id": "b1cb917a-f96a-45cd-831e-1907b8cd5950"}, {"new": ["28707914-3e38-474c-a3f0-38ec06029637", "5c990b83e326ef234162eb19d3fe01b0f5c05c3572624ddd0f98308070f8c03d"], "old": null, "kind": "append", "position": 15, "host_logical_id": "28707914-3e38-474c-a3f0-38ec06029637"}]}', '2026-09-26 10:09:39.807084+00', '01a0dd31-21e3-743f-afe4-05220ed72151');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0dd31-2649-7f30-9041-93bb14628730', 4, '01a0dd31-263c-7037-9012-3b6c2938263e', '{}', 'branch', '0512b3df4a90bcf9dacba28a4670b3b751cabe3cb0eb7fe9bf31cba7ec98b9f9', '{"ops": [{"op": "set", "members": [["3a706102-a50b-40b2-a369-0277eae9b505", "f06bf022c7e81917ee77b9255ac171f129e67fe74d6a88733405ee129fc0bd2e"], ["bf85d576-f1a2-4291-be64-4b622d301906", "21a316346beb075de0e9e02131cfdd84b7b2be49b8d602b703ed3327057401ba"], ["4c9b0695-212c-4218-9cb5-8236dd7f48db", "59e2e21aeb5afeac4fe52f0a2e78baec5f37e55c63001fcde617339c251c30a4"], ["cf2e8c87-1535-45bd-a4c8-76050bef85c4", "091f9fea320075b22a6f698586486a8460974b4cd30c98ab6e9b494f438f2e4b"], ["dcc24320-ca73-4a4b-b809-2c5d3718cde7", "fd47da1fc1cf93e3a140da3d6d7e08fe10f5f7435db342700615167fe2f9fd2e"], ["7dd97721-3273-4913-bfd7-a4fc7661fd71", "a155ba30b3aa235c3d76a7c58171f63931009f78a849f03a67c55dc282c2b320"], ["3f9cc783-7ae3-471c-9640-b65eecd371b3", "03756bff8bb11e48b1474bb5cd9ec9ee853212bc9790b5712fc5a8b52d29632c"], ["1635d4a7-6b9e-4445-ad15-eb71c660d761", "56bdb23c853dde13efb3e31f630b4602c7f1433ba76c07123a0afc00663cb5c5"]]}], "changes": [{"new": ["3a706102-a50b-40b2-a369-0277eae9b505", "f06bf022c7e81917ee77b9255ac171f129e67fe74d6a88733405ee129fc0bd2e"], "old": null, "kind": "append", "position": 0, "host_logical_id": "3a706102-a50b-40b2-a369-0277eae9b505"}, {"new": ["bf85d576-f1a2-4291-be64-4b622d301906", "21a316346beb075de0e9e02131cfdd84b7b2be49b8d602b703ed3327057401ba"], "old": null, "kind": "append", "position": 1, "host_logical_id": "bf85d576-f1a2-4291-be64-4b622d301906"}, {"new": ["4c9b0695-212c-4218-9cb5-8236dd7f48db", "59e2e21aeb5afeac4fe52f0a2e78baec5f37e55c63001fcde617339c251c30a4"], "old": null, "kind": "append", "position": 2, "host_logical_id": "4c9b0695-212c-4218-9cb5-8236dd7f48db"}, {"new": ["cf2e8c87-1535-45bd-a4c8-76050bef85c4", "091f9fea320075b22a6f698586486a8460974b4cd30c98ab6e9b494f438f2e4b"], "old": null, "kind": "append", "position": 3, "host_logical_id": "cf2e8c87-1535-45bd-a4c8-76050bef85c4"}, {"new": ["dcc24320-ca73-4a4b-b809-2c5d3718cde7", "fd47da1fc1cf93e3a140da3d6d7e08fe10f5f7435db342700615167fe2f9fd2e"], "old": null, "kind": "append", "position": 4, "host_logical_id": "dcc24320-ca73-4a4b-b809-2c5d3718cde7"}, {"new": ["7dd97721-3273-4913-bfd7-a4fc7661fd71", "a155ba30b3aa235c3d76a7c58171f63931009f78a849f03a67c55dc282c2b320"], "old": null, "kind": "append", "position": 5, "host_logical_id": "7dd97721-3273-4913-bfd7-a4fc7661fd71"}, {"new": ["3f9cc783-7ae3-471c-9640-b65eecd371b3", "03756bff8bb11e48b1474bb5cd9ec9ee853212bc9790b5712fc5a8b52d29632c"], "old": null, "kind": "append", "position": 6, "host_logical_id": "3f9cc783-7ae3-471c-9640-b65eecd371b3"}, {"new": ["1635d4a7-6b9e-4445-ad15-eb71c660d761", "56bdb23c853dde13efb3e31f630b4602c7f1433ba76c07123a0afc00663cb5c5"], "old": null, "kind": "append", "position": 7, "host_logical_id": "1635d4a7-6b9e-4445-ad15-eb71c660d761"}]}', '2026-09-26 10:09:40.929202+00', '01a0dd31-2648-7ec8-8ca6-9647c9846c2e');


--
-- Name: assertion_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.assertion_id_seq', 19, true);


--
-- Name: job_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.job_id_seq', 74, true);


--
-- Name: state_observation_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.state_observation_id_seq', 1, false);


--
-- Name: worldline_commit_seq_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.worldline_commit_seq_seq', 4, true);


--
-- Name: active_membership active_membership_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.active_membership
    ADD CONSTRAINT active_membership_pkey PRIMARY KEY (commit_id, "position");


--
-- Name: app_config app_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.app_config
    ADD CONSTRAINT app_config_pkey PRIMARY KEY (key);


--
-- Name: assertion assertion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assertion
    ADD CONSTRAINT assertion_pkey PRIMARY KEY (id);


--
-- Name: conversation conversation_host_host_chat_ref_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation
    ADD CONSTRAINT conversation_host_host_chat_ref_key UNIQUE (host, host_chat_ref);


--
-- Name: conversation conversation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation
    ADD CONSTRAINT conversation_pkey PRIMARY KEY (id);


--
-- Name: extraction extraction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction
    ADD CONSTRAINT extraction_pkey PRIMARY KEY (id);


--
-- Name: host_observation host_observation_idempotency_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.host_observation
    ADD CONSTRAINT host_observation_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: host_observation host_observation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.host_observation
    ADD CONSTRAINT host_observation_pkey PRIMARY KEY (id);


--
-- Name: job job_dedupe_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job
    ADD CONSTRAINT job_dedupe_key_key UNIQUE (dedupe_key);


--
-- Name: job job_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job
    ADD CONSTRAINT job_pkey PRIMARY KEY (id);


--
-- Name: projection_generation projection_generation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projection_generation
    ADD CONSTRAINT projection_generation_pkey PRIMARY KEY (key);


--
-- Name: retrieval_trace retrieval_trace_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.retrieval_trace
    ADD CONSTRAINT retrieval_trace_pkey PRIMARY KEY (id);


--
-- Name: revision_embedding revision_embedding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revision_embedding
    ADD CONSTRAINT revision_embedding_pkey PRIMARY KEY (source_revision_id, projection, chunk);


--
-- Name: revision_text revision_text_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revision_text
    ADD CONSTRAINT revision_text_pkey PRIMARY KEY (source_revision_id, normalizer);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: source_object source_object_conversation_id_host_logical_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_object
    ADD CONSTRAINT source_object_conversation_id_host_logical_id_key UNIQUE (conversation_id, host_logical_id);


--
-- Name: source_object source_object_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_object
    ADD CONSTRAINT source_object_pkey PRIMARY KEY (id);


--
-- Name: source_revision source_revision_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_revision
    ADD CONSTRAINT source_revision_pkey PRIMARY KEY (id);


--
-- Name: source_revision source_revision_source_object_id_revision_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_revision
    ADD CONSTRAINT source_revision_source_object_id_revision_hash_key UNIQUE (source_object_id, revision_hash);


--
-- Name: state_observation state_observation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_observation
    ADD CONSTRAINT state_observation_pkey PRIMARY KEY (id);


--
-- Name: state_observation state_observation_source_revision_id_rules_version_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_observation
    ADD CONSTRAINT state_observation_source_revision_id_rules_version_key_key UNIQUE (source_revision_id, rules_version, key);


--
-- Name: worldline_commit worldline_commit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worldline_commit
    ADD CONSTRAINT worldline_commit_pkey PRIMARY KEY (id);


--
-- Name: worldline_commit worldline_commit_seq_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worldline_commit
    ADD CONSTRAINT worldline_commit_seq_key UNIQUE (seq);


--
-- Name: assertion_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX assertion_revision ON public.assertion USING btree (source_revision_id);


--
-- Name: extraction_generation_window; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX extraction_generation_window ON public.extraction USING btree (source_revision_id, window_hash, extractor_key);


--
-- Name: job_ready; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX job_ready ON public.job USING btree (priority, id) WHERE (status = 'queued'::text);


--
-- Name: revision_text_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX revision_text_trgm ON public.revision_text USING gin (clean_content public.gin_trgm_ops);


--
-- Name: state_observation_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX state_observation_conversation ON public.state_observation USING btree (conversation_id, rules_version, key);


--
-- Name: worldline_commit_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX worldline_commit_conversation ON public.worldline_commit USING btree (conversation_id, seq);


--
-- Name: source_revision source_revision_append_only; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER source_revision_append_only BEFORE DELETE ON public.source_revision FOR EACH ROW EXECUTE FUNCTION public.source_revision_no_delete();


--
-- Name: source_revision source_revision_immutable; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER source_revision_immutable BEFORE UPDATE ON public.source_revision FOR EACH ROW EXECUTE FUNCTION public.source_revision_guard();


--
-- Name: active_membership active_membership_commit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.active_membership
    ADD CONSTRAINT active_membership_commit_id_fkey FOREIGN KEY (commit_id) REFERENCES public.worldline_commit(id);


--
-- Name: active_membership active_membership_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.active_membership
    ADD CONSTRAINT active_membership_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revision(id);


--
-- Name: assertion assertion_extraction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assertion
    ADD CONSTRAINT assertion_extraction_id_fkey FOREIGN KEY (extraction_id) REFERENCES public.extraction(id);


--
-- Name: assertion assertion_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assertion
    ADD CONSTRAINT assertion_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revision(id);


--
-- Name: conversation conversation_branched_from_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation
    ADD CONSTRAINT conversation_branched_from_conversation_id_fkey FOREIGN KEY (branched_from_conversation_id) REFERENCES public.conversation(id);


--
-- Name: conversation conversation_head_commit_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversation
    ADD CONSTRAINT conversation_head_commit_fk FOREIGN KEY (head_commit_id) REFERENCES public.worldline_commit(id);


--
-- Name: extraction extraction_extractor_key_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction
    ADD CONSTRAINT extraction_extractor_key_fkey FOREIGN KEY (extractor_key) REFERENCES public.projection_generation(key);


--
-- Name: extraction extraction_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction
    ADD CONSTRAINT extraction_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revision(id);


--
-- Name: host_observation host_observation_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.host_observation
    ADD CONSTRAINT host_observation_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


--
-- Name: job job_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job
    ADD CONSTRAINT job_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


--
-- Name: retrieval_trace retrieval_trace_commit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.retrieval_trace
    ADD CONSTRAINT retrieval_trace_commit_id_fkey FOREIGN KEY (commit_id) REFERENCES public.worldline_commit(id);


--
-- Name: retrieval_trace retrieval_trace_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.retrieval_trace
    ADD CONSTRAINT retrieval_trace_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


--
-- Name: revision_embedding revision_embedding_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revision_embedding
    ADD CONSTRAINT revision_embedding_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revision(id);


--
-- Name: revision_text revision_text_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revision_text
    ADD CONSTRAINT revision_text_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revision(id);


--
-- Name: source_object source_object_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_object
    ADD CONSTRAINT source_object_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


--
-- Name: source_revision source_revision_lineage_parent_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_revision
    ADD CONSTRAINT source_revision_lineage_parent_revision_id_fkey FOREIGN KEY (lineage_parent_revision_id) REFERENCES public.source_revision(id);


--
-- Name: source_revision source_revision_source_object_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_revision
    ADD CONSTRAINT source_revision_source_object_id_fkey FOREIGN KEY (source_object_id) REFERENCES public.source_object(id);


--
-- Name: state_observation state_observation_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_observation
    ADD CONSTRAINT state_observation_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


--
-- Name: state_observation state_observation_source_revision_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.state_observation
    ADD CONSTRAINT state_observation_source_revision_id_fkey FOREIGN KEY (source_revision_id) REFERENCES public.source_revision(id);


--
-- Name: worldline_commit worldline_commit_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worldline_commit
    ADD CONSTRAINT worldline_commit_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


--
-- Name: worldline_commit worldline_commit_host_observation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worldline_commit
    ADD CONSTRAINT worldline_commit_host_observation_id_fkey FOREIGN KEY (host_observation_id) REFERENCES public.host_observation(id);


--
-- PostgreSQL database dump complete
--


