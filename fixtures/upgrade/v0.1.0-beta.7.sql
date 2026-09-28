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

INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 0, '01a0e7b4-d182-7a20-b999-89010ce75cc7', 'e181fbdddab83d6a5c8d8910245256a9');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 1, '01a0e7b4-d184-7f9d-be20-9168f66a5654', '0037b5198a1db6c9f84b15ff237848ce');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 2, '01a0e7b4-d185-7b97-9674-b1aeb0f30629', '88bc65647f516a89f492d5a2cb91843e');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 3, '01a0e7b4-da07-78a0-8e99-b39656abd837', '3f4b45f1486c4bb84210c87804ec3f18');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 4, '01a0e7b4-d1b5-7f9b-9001-8cb68abe5349', 'bd34dd60ac3585a0d27a27889c5e5236');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 5, '01a0e7b4-d1b7-767c-a348-e0accd39fa0d', '7b874ac060b4700c7cba96ef9e57b4da');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 6, '01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b', '537f0b8ce54132fd8b37b4e653cb0cc8');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 7, '01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa', '8752bc13be1d14fde52d0629bceb183d');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 8, '01a0e7b4-da4f-7ddc-add2-fe287da4eea7', 'be06bca1f43d535dc32b36cf2eb3a74b');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 9, '01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8', '7951a75e76cd133ed5f42573402d82e0');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 10, '01a0e7b4-d1e2-7143-892d-fbdf05300d51', 'fab333f701230fa88c14bcabff9fe4eb');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 11, '01a0e7b4-d1e3-78d3-b08e-908a50db8850', '99727ba10708095d2c1b13bb579ca081');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 12, '01a0e7b4-d206-78ff-9bbd-5d97d1875760', 'ad7cc55b39cbfa832af446090212d18b');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 13, '01a0e7b4-da08-7412-9cec-0251b9229307', 'a9b1cad7d120fe6acb83d23e7f9842a4');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 14, '01a0e7b4-da08-7fff-8856-3791bbdd0757', '533f9942604be9d70ae8287a062dd13c');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 15, '01a0e7b4-da4f-7b8b-881e-b9aa119a0a08', 'be2b8de3716d8907720b62fdec3d2495');
INSERT INTO public.active_membership VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 16, '01a0e7b4-da50-7d14-a61b-a62e60f366b3', 'd8e02f599675c2c8d31837d12e4aa5d2');
INSERT INTO public.active_membership VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 0, '01a0e7b4-de72-7784-bc44-eb00c4a48a72', 'f31ec11098e3a0f792b503029b492f1c');
INSERT INTO public.active_membership VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 1, '01a0e7b4-de72-73c6-a167-e3bd8271d888', 'a2e54636bdce93c1390a8de61393d6e9');
INSERT INTO public.active_membership VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 2, '01a0e7b4-de73-7aef-8427-28cc5d0da0b3', '79de3656e948f6cfb3c547129937b848');
INSERT INTO public.active_membership VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 3, '01a0e7b4-de74-795f-8b91-1a2ef726a51d', '42e66c4b657421fc289850146b70c634');
INSERT INTO public.active_membership VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 4, '01a0e7b4-de75-70a9-89c0-39a145311d39', 'dbe7cd523e7c2c126b45d62bbc9e20c0');
INSERT INTO public.active_membership VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 5, '01a0e7b4-de75-7c4a-9692-5bd348227a5e', '854c64b17a9913d53a9607c395e2afcc');
INSERT INTO public.active_membership VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 6, '01a0e7b4-de76-72f3-82b2-58055eabb07a', '1572716b74bd55380995bc43528edabe');
INSERT INTO public.active_membership VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 7, '01a0e7b4-de77-7801-bd7d-cc65b4055e6f', '8d13ca14fe88afd764997983d196e851');


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0e7b4-d6fa-78c1-88a6-7ce85ed92127', '01a0e7b4-d1e3-78d3-b08e-908a50db8850', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0e7b4-d726-7d1e-80b7-ebd26c809c3f', '01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0e7b4-d77b-7590-8d26-62a35a193532', '01a0e7b4-d1b7-767c-a348-e0accd39fa0d', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0e7b4-d7a2-7699-93a3-9078287d53e4', '01a0e7b4-d186-798a-8b0f-be104495deb7', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0e7b4-d7a2-7699-93a3-9078287d53e4', '01a0e7b4-d186-798a-8b0f-be104495deb7', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0e7b4-d807-7969-aead-a767523e48b9', '01a0e7b4-d184-7f9d-be20-9168f66a5654', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0e7b4-d807-7969-aead-a767523e48b9', '01a0e7b4-d184-7f9d-be20-9168f66a5654', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0e7b4-dc8b-7433-a1d3-e136b6365055', '01a0e7b4-da4f-7b8b-881e-b9aa119a0a08', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0e7b4-dce4-7105-b25f-2374face5ae1', '01a0e7b4-d1e3-78d3-b08e-908a50db8850', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0e7b4-dd0d-7999-8f49-d7d41d456f8c', '01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0e7b4-dd5b-77c9-adad-ecb612c3c402', '01a0e7b4-d1b7-767c-a348-e0accd39fa0d', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0e7b4-dd88-70d5-8add-4f449819802f', '01a0e7b4-da07-78a0-8e99-b39656abd837', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0e7b4-dd88-70d5-8add-4f449819802f', '01a0e7b4-da07-78a0-8e99-b39656abd837', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0e7b4-e20d-739a-80f1-91a556f1c8f0', '01a0e7b4-de77-7801-bd7d-cc65b4055e6f', 'Rin', 'character', 'located_in', 'market', 'place', NULL, 'stated', 0.9, 'Rin moved to the market.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0e7b4-e220-7e15-b9bc-b41992fa3e6f', '01a0e7b4-de75-7c4a-9692-5bd348227a5e', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0e7b4-e24b-70ff-99d2-6d04a98f3a07', '01a0e7b4-de74-795f-8b91-1a2ef726a51d', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0e7b4-e24b-70ff-99d2-6d04a98f3a07', '01a0e7b4-de74-795f-8b91-1a2ef726a51d', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0e7b4-e272-7495-9919-607ca9059c8c', '01a0e7b4-de72-73c6-a167-e3bd8271d888', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown');
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (19, '01a0e7b4-e272-7495-9919-607ca9059c8c', '01a0e7b4-de72-73c6-a167-e3bd8271d888', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown');


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0e7b4-d174-739f-86c1-49cc6910abe9', 'pocketrisu', NULL, '52abe29c-6ec4-4338-85ec-fb767911e4bd', '2026-09-28 11:09:42.132281+00', NULL, NULL, NULL, '01a0e7b4-da52-7e20-a978-f7fef6fb6090', '1f065114e5b8330959267800828e7988689d28b1db5066d42eb8035501a78051', 'Mina', 'Upgrade fixture');
INSERT INTO public.conversation VALUES ('01a0e7b4-de63-7415-a4c3-26661d9565f5', 'pocketrisu', NULL, 'd70ed6e2-92b5-457c-b608-288ea35a6e95', '2026-09-28 11:09:45.443208+00', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '52abe29c-6ec4-4338-85ec-fb767911e4bd', '2047e848-7099-4d81-a50a-9d790dd2def2', '01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 'fc6425c8854f83f5f5ac67738c103afebc59e9b3dfe199bff41ded493d4748fd', 'Mina', 'Upgrade fixture');


--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0e7b4-d6e4-78f2-ad5f-d84e7b16ddd0', '01a0e7b4-d206-78ff-9bbd-5d97d1875760', 'a40b926a62243deb10d15040f00c6411', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:43.524272+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 18, "target_chars": 18, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d6fa-78c1-88a6-7ce85ed92127', '01a0e7b4-d1e3-78d3-b08e-908a50db8850', '929c45850591810a5bb2fb8150f65304', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:43.546193+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 29, "target_chars": 29, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d711-765b-a363-84061ccbce5b', '01a0e7b4-d1e2-7143-892d-fbdf05300d51', '0c47e3aa59a2bb907865e9cfc64c5f59', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:43.56947+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 25, "target_chars": 25, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d726-7d1e-80b7-ebd26c809c3f', '01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8', '8b353bb352bfaf19fe75ae18b3cbdbf3', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:43.590944+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 53, "target_chars": 53, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d73b-70ed-a11f-07b14fa610e7', '01a0e7b4-d1e1-7844-af67-852273a8ff72', 'f0283f6ee9c67a49f8d90a3910ca70ec', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:43.611054+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 25, "target_chars": 25, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d750-7695-bf3f-948ca93819f0', '01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa', '6421157ebbbc590217f9f15fb66e0d5e', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:43.632699+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 35, "target_chars": 35, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d768-7bcc-b37e-a6868f0d1d7a', '01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b', 'd3280a055be13980d114986965d05880', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:43.656076+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 23, "target_chars": 23, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d77b-7590-8d26-62a35a193532', '01a0e7b4-d1b7-767c-a348-e0accd39fa0d', '51419cb815b171fcfa0bc7a45dfc1d01', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:43.675146+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 53, "target_chars": 53, "context_messages": 5, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d78f-7eca-96c0-b1f70c5d6d5c', '01a0e7b4-d1b5-7f9b-9001-8cb68abe5349', '217e8c1beb0e668367ca440be66a8aa7', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:43.694964+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 34, "target_chars": 34, "context_messages": 4, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d7a2-7699-93a3-9078287d53e4', '01a0e7b4-d186-798a-8b0f-be104495deb7', '797bcea6b9cd922012580e801e201de1', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:43.714102+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 45, "target_chars": 45, "context_messages": 3, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d7f4-7aa5-b87f-9c574dbfbce8', '01a0e7b4-d185-7b97-9674-b1aeb0f30629', '88bc65647f516a89f492d5a2cb91843e', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:43.796585+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 16, "target_chars": 16, "context_messages": 2, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d807-7969-aead-a767523e48b9', '01a0e7b4-d184-7f9d-be20-9168f66a5654', '0037b5198a1db6c9f84b15ff237848ce', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:43.815811+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 50, "target_chars": 50, "context_messages": 1, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-d81b-7d51-9cf0-663118800d83', '01a0e7b4-d182-7a20-b999-89010ce75cc7', 'e181fbdddab83d6a5c8d8910245256a9', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:43.835495+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 30, "target_chars": 30, "context_messages": 0, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dc76-7682-aae7-810b5d52f0c2', '01a0e7b4-da50-7d14-a61b-a62e60f366b3', 'd8e02f599675c2c8d31837d12e4aa5d2', 'extract-v3', 'stub', '{"reply": ""}', '2026-09-28 11:09:44.950719+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 9, "target_chars": 9, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dc8b-7433-a1d3-e136b6365055', '01a0e7b4-da4f-7b8b-881e-b9aa119a0a08', 'be2b8de3716d8907720b62fdec3d2495', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:44.971844+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 27, "target_chars": 27, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dca1-7fe6-b479-97131d6cb5cc', '01a0e7b4-da08-7fff-8856-3791bbdd0757', '533f9942604be9d70ae8287a062dd13c', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:44.993567+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 16, "target_chars": 16, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dcb8-7ba4-922c-132197dc8fc7', '01a0e7b4-da08-7412-9cec-0251b9229307', 'a9b1cad7d120fe6acb83d23e7f9842a4', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:45.016425+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 31, "target_chars": 31, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dccc-76bf-a679-8e6db4596038', '01a0e7b4-d206-78ff-9bbd-5d97d1875760', 'ad7cc55b39cbfa832af446090212d18b', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:45.036394+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 18, "target_chars": 18, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dce4-7105-b25f-2374face5ae1', '01a0e7b4-d1e3-78d3-b08e-908a50db8850', '99727ba10708095d2c1b13bb579ca081', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:45.060064+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 29, "target_chars": 29, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dcf9-7533-bf05-8d2ec322337c', '01a0e7b4-d1e2-7143-892d-fbdf05300d51', 'fab333f701230fa88c14bcabff9fe4eb', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:45.080945+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 25, "target_chars": 25, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dd0d-7999-8f49-d7d41d456f8c', '01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8', '7951a75e76cd133ed5f42573402d82e0', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:45.101321+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 53, "target_chars": 53, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dd2f-7a3a-9889-1d0439a508ac', '01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa', '8752bc13be1d14fde52d0629bceb183d', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:45.135747+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 35, "target_chars": 35, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dd43-7a61-afe8-41911cf3aabf', '01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b', '537f0b8ce54132fd8b37b4e653cb0cc8', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:45.155009+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 23, "target_chars": 23, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dd5b-77c9-adad-ecb612c3c402', '01a0e7b4-d1b7-767c-a348-e0accd39fa0d', '7b874ac060b4700c7cba96ef9e57b4da', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:45.179655+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 53, "target_chars": 53, "context_messages": 5, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dd71-771d-9584-91e02cbb517d', '01a0e7b4-d1b5-7f9b-9001-8cb68abe5349', 'bd34dd60ac3585a0d27a27889c5e5236', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:45.200973+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 34, "target_chars": 34, "context_messages": 4, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-dd88-70d5-8add-4f449819802f', '01a0e7b4-da07-78a0-8e99-b39656abd837', '3f4b45f1486c4bb84210c87804ec3f18', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:45.224043+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 48, "target_chars": 48, "context_messages": 3, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-e20d-739a-80f1-91a556f1c8f0', '01a0e7b4-de77-7801-bd7d-cc65b4055e6f', '8d13ca14fe88afd764997983d196e851', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"market\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin moved to the market.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:46.381453+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 24, "target_chars": 24, "context_messages": 6, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-e220-7e15-b9bc-b41992fa3e6f', '01a0e7b4-de75-7c4a-9692-5bd348227a5e', '854c64b17a9913d53a9607c395e2afcc', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:46.400637+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 53, "target_chars": 53, "context_messages": 5, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-e234-77a5-bede-b64fcdd7ea2a', '01a0e7b4-de75-70a9-89c0-39a145311d39', 'dbe7cd523e7c2c126b45d62bbc9e20c0', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:46.420471+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 34, "target_chars": 34, "context_messages": 4, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-e24b-70ff-99d2-6d04a98f3a07', '01a0e7b4-de74-795f-8b91-1a2ef726a51d', '42e66c4b657421fc289850146b70c634', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:46.443066+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 48, "target_chars": 48, "context_messages": 3, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-e25f-7cd8-a7e3-60cf5d223543', '01a0e7b4-de73-7aef-8427-28cc5d0da0b3', '79de3656e948f6cfb3c547129937b848', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:46.463342+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 16, "target_chars": 16, "context_messages": 2, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-e272-7495-9919-607ca9059c8c', '01a0e7b4-de72-73c6-a167-e3bd8271d888', 'a2e54636bdce93c1390a8de61393d6e9', 'extract-v3', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:46.482865+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 50, "target_chars": 50, "context_messages": 1, "context_truncated": 0}');
INSERT INTO public.extraction VALUES ('01a0e7b4-e286-79a1-a2f3-7a63605d6695', '01a0e7b4-de72-7784-bc44-eb00c4a48a72', 'f31ec11098e3a0f792b503029b492f1c', 'extract-v3', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:46.50259+00', 'extract-259aff6e1aca31fb03c8a44fe16acf27', '{"target_used": 30, "target_chars": 30, "context_messages": 0, "context_truncated": 0}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0e7b4-d187-750c-b9a7-f8819314ea1e', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'manifest', 'b5ecb4df53cf3f396a3d214dff423749c8a18b2c815f59d913772386d3fd91da', '01a0e7b4-d174-739f-86c1-49cc6910abe9:b5ecb4df53cf3f396a3d214dff423749c8a18b2c815f59d913772386d3fd91da:manifest', '2026-09-28 11:09:42.144425+00', '{"chat_id": "52abe29c-6ec4-4338-85ec-fb767911e4bd", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["c2c100c6-a2a0-411b-91eb-a9d5b654ff06", "17e4ba427e5685cfa9d67220bee94eba0d7d5328136a515abd71ec3595e354fc", "user", null, null, null, 0, null, null], ["b8c7dc42-7a01-4a44-aec4-02f250dad410", "fb04935fe0caccaed815cf4cb0e98f68d9a8095f539ad3de9c81559f60f57958", "char", null, null, null, 0, "b8c7dc42-7a01-4a44-aec4-02f250dad410", null], ["3d78bc65-a11b-4c78-ab58-4b66fa45edea", "71fe3b62b131f41594a1abe0587663c2a25556cd6e7692c5b4dcfd6fd3a316a5", "user", null, null, null, 0, null, null], ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "fed91523ee6aa10eeb8cdabb7b0c005062ebdb50f605b72cfb882ebe41aba0d8", "char", null, null, null, 0, "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-d1ba-7ca3-b290-e09fb160c37c', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'manifest', 'd1113a34119346f36e1058df3c61465fe4d9eb33a8e81819db82ff76683fce42', '01a0e7b4-d174-739f-86c1-49cc6910abe9:d1113a34119346f36e1058df3c61465fe4d9eb33a8e81819db82ff76683fce42:manifest', '2026-09-28 11:09:42.197099+00', '{"chat_id": "52abe29c-6ec4-4338-85ec-fb767911e4bd", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893", "53dedee3233d1a8ecd4790c7d9102cbdde4848fbc053154c2692e82e773dbf37", "user", null, null, null, 0, null, null], ["2047e848-7099-4d81-a50a-9d790dd2def2", "79c3127817fe16ab0993ba16bcf3b27b75f064c250dc914fbc55a48455c28765", "char", null, null, null, 0, "2047e848-7099-4d81-a50a-9d790dd2def2", null], ["f95c8265-e9d8-4dbb-b359-2da87e358cea", "4548e3c47f01e977311c3bd11cd49416e36f0454b1a69a1e2012ba757d8baf9e", "user", null, null, null, 0, null, null], ["d382d783-d96e-4d51-bc0c-210eb2f74ea8", "72063d31aa1cd86c091920ef80c3c3bbaebf52a4cae85f21b1944c3f615fc8b0", "char", null, null, null, 0, "d382d783-d96e-4d51-bc0c-210eb2f74ea8", null]], "base_manifest_hash": "b5ecb4df53cf3f396a3d214dff423749c8a18b2c815f59d913772386d3fd91da"}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-d1e5-7be4-8d15-1a7b0d3215ad', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'manifest', '1fb3e7aff3e90140c665cc2bd123005145bf2464ef69aaad70fcf61d64ee873e', '01a0e7b4-d174-739f-86c1-49cc6910abe9:1fb3e7aff3e90140c665cc2bd123005145bf2464ef69aaad70fcf61d64ee873e:manifest', '2026-09-28 11:09:42.23998+00', '{"chat_id": "52abe29c-6ec4-4338-85ec-fb767911e4bd", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "b8f53dc792434d3a2f4af64a860ddd3a85eb9c11a44407f42f79587cbc744b13", "user", null, null, null, 0, null, null], ["c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", "54b55bc9335213b8d129e821c5cf1a1eeb12673aa47c8d5f5aa28836d77be9f3", "char", null, null, null, 0, "c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", null], ["d7757c68-9a1b-4081-9f65-7d49940bf4cd", "97c8a29f11a4420b4a7c5dddf2a42a4a0e31ccef4860dbd5e61e44d18c5b0dc7", "user", null, null, null, 0, null, null], ["56b05611-ddb1-4a7f-8841-51af71f8e09c", "44134fd1a7ed1cbfca1a432226061afbcdd69013fa2f89a390819422ee241c8b", "char", null, null, null, 0, "56b05611-ddb1-4a7f-8841-51af71f8e09c", null]], "base_manifest_hash": "d1113a34119346f36e1058df3c61465fe4d9eb33a8e81819db82ff76683fce42"}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-d208-7a6e-9d49-a34ff9c725b8', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'manifest', '88953c3dd2a65c444f7f4a07f10af2f7841af324bd4c6fd28ac60f57c8ebaf12', '01a0e7b4-d174-739f-86c1-49cc6910abe9:88953c3dd2a65c444f7f4a07f10af2f7841af324bd4c6fd28ac60f57c8ebaf12:manifest', '2026-09-28 11:09:42.277224+00', '{"chat_id": "52abe29c-6ec4-4338-85ec-fb767911e4bd", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["5d1b5d31-37c4-463e-bb57-3347fba30237", "b2751dbc4c114dfd243159e23cc2251cbbd5957edfaf1593f4df22496606961a", "user", null, null, null, 0, null, null]], "base_manifest_hash": "1fb3e7aff3e90140c665cc2bd123005145bf2464ef69aaad70fcf61d64ee873e"}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-da0a-7365-ab8f-90d4ff0b1532', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'manifest', '2b4765b878882a5cba7dfc3b97eabe08596b240248abee8cb2f0b59e93459a8c', '01a0e7b4-d174-739f-86c1-49cc6910abe9:2b4765b878882a5cba7dfc3b97eabe08596b240248abee8cb2f0b59e93459a8c:manifest', '2026-09-28 11:09:44.326192+00', '{"chat_id": "52abe29c-6ec4-4338-85ec-fb767911e4bd", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["c2c100c6-a2a0-411b-91eb-a9d5b654ff06", "17e4ba427e5685cfa9d67220bee94eba0d7d5328136a515abd71ec3595e354fc", "user", null, null, null, 0, null, null], ["b8c7dc42-7a01-4a44-aec4-02f250dad410", "fb04935fe0caccaed815cf4cb0e98f68d9a8095f539ad3de9c81559f60f57958", "char", null, null, null, 0, "b8c7dc42-7a01-4a44-aec4-02f250dad410", null], ["3d78bc65-a11b-4c78-ab58-4b66fa45edea", "71fe3b62b131f41594a1abe0587663c2a25556cd6e7692c5b4dcfd6fd3a316a5", "user", null, null, null, 0, null, null], ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "78c443c18a2119cf938ff1e9e8182f7fb6ca4ec46b35da3271bbc067f9e178b5", "char", null, null, null, 0, "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", null], ["0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893", "53dedee3233d1a8ecd4790c7d9102cbdde4848fbc053154c2692e82e773dbf37", "user", null, null, null, 0, null, null], ["2047e848-7099-4d81-a50a-9d790dd2def2", "79c3127817fe16ab0993ba16bcf3b27b75f064c250dc914fbc55a48455c28765", "char", null, null, null, 0, "2047e848-7099-4d81-a50a-9d790dd2def2", null], ["f95c8265-e9d8-4dbb-b359-2da87e358cea", "4548e3c47f01e977311c3bd11cd49416e36f0454b1a69a1e2012ba757d8baf9e", "user", null, null, null, 0, null, null], ["d382d783-d96e-4d51-bc0c-210eb2f74ea8", "72063d31aa1cd86c091920ef80c3c3bbaebf52a4cae85f21b1944c3f615fc8b0", "char", null, null, null, 0, "d382d783-d96e-4d51-bc0c-210eb2f74ea8", null], ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "b8f53dc792434d3a2f4af64a860ddd3a85eb9c11a44407f42f79587cbc744b13", "user", null, null, null, 0, null, null], ["c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", "54b55bc9335213b8d129e821c5cf1a1eeb12673aa47c8d5f5aa28836d77be9f3", "char", null, null, null, 0, "c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", null], ["d7757c68-9a1b-4081-9f65-7d49940bf4cd", "97c8a29f11a4420b4a7c5dddf2a42a4a0e31ccef4860dbd5e61e44d18c5b0dc7", "user", null, null, null, 0, null, null], ["56b05611-ddb1-4a7f-8841-51af71f8e09c", "44134fd1a7ed1cbfca1a432226061afbcdd69013fa2f89a390819422ee241c8b", "char", null, null, null, 0, "56b05611-ddb1-4a7f-8841-51af71f8e09c", null], ["5d1b5d31-37c4-463e-bb57-3347fba30237", "b2751dbc4c114dfd243159e23cc2251cbbd5957edfaf1593f4df22496606961a", "user", null, null, null, 0, null, null], ["02cc2796-0c46-4b9e-9788-420646a4c724", "f157131b7b826caedc9f9dfb95aa634b5cce8ac3b5ca23069a041cd4b4ac8fe7", "char", null, null, null, 0, "02cc2796-0c46-4b9e-9788-420646a4c724", null], ["5e8f5229-c65f-4f14-bad1-03784cda34e4", "f346bdba7caf72a0c255bf0f765edbc3cf725419d2aa3d13f85f338ce6101dd4", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-da2f-71bd-a523-fd392b0f7e80', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'manifest', '322340d40cb275fa993520ff879ce2fa5a86cfe0fe002d551605601ab6104dce', '01a0e7b4-d174-739f-86c1-49cc6910abe9:322340d40cb275fa993520ff879ce2fa5a86cfe0fe002d551605601ab6104dce:manifest', '2026-09-28 11:09:44.364026+00', '{"chat_id": "52abe29c-6ec4-4338-85ec-fb767911e4bd", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["cd924214-7bd4-4e2d-acda-39b13a165021", "836932692fcb5a89b812e5e7ae93cc7f60426b59ae0fe0f28870d75683480d48", "char", null, null, 1, 2, "cd924214-7bd4-4e2d-acda-39b13a165021", null]], "base_manifest_hash": "2b4765b878882a5cba7dfc3b97eabe08596b240248abee8cb2f0b59e93459a8c"}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-da52-7321-b17c-cdb543194b81', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'manifest', '1f065114e5b8330959267800828e7988689d28b1db5066d42eb8035501a78051', '01a0e7b4-d174-739f-86c1-49cc6910abe9:1f065114e5b8330959267800828e7988689d28b1db5066d42eb8035501a78051:manifest', '2026-09-28 11:09:44.398308+00', '{"chat_id": "52abe29c-6ec4-4338-85ec-fb767911e4bd", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["c2c100c6-a2a0-411b-91eb-a9d5b654ff06", "17e4ba427e5685cfa9d67220bee94eba0d7d5328136a515abd71ec3595e354fc", "user", null, null, null, 0, null, null], ["b8c7dc42-7a01-4a44-aec4-02f250dad410", "fb04935fe0caccaed815cf4cb0e98f68d9a8095f539ad3de9c81559f60f57958", "char", null, null, null, 0, "b8c7dc42-7a01-4a44-aec4-02f250dad410", null], ["3d78bc65-a11b-4c78-ab58-4b66fa45edea", "71fe3b62b131f41594a1abe0587663c2a25556cd6e7692c5b4dcfd6fd3a316a5", "user", null, null, null, 0, null, null], ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "78c443c18a2119cf938ff1e9e8182f7fb6ca4ec46b35da3271bbc067f9e178b5", "char", null, null, null, 0, "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", null], ["0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893", "53dedee3233d1a8ecd4790c7d9102cbdde4848fbc053154c2692e82e773dbf37", "user", null, null, null, 0, null, null], ["2047e848-7099-4d81-a50a-9d790dd2def2", "79c3127817fe16ab0993ba16bcf3b27b75f064c250dc914fbc55a48455c28765", "char", null, null, null, 0, "2047e848-7099-4d81-a50a-9d790dd2def2", null], ["f95c8265-e9d8-4dbb-b359-2da87e358cea", "4548e3c47f01e977311c3bd11cd49416e36f0454b1a69a1e2012ba757d8baf9e", "user", null, null, null, 0, null, null], ["d382d783-d96e-4d51-bc0c-210eb2f74ea8", "72063d31aa1cd86c091920ef80c3c3bbaebf52a4cae85f21b1944c3f615fc8b0", "char", null, null, null, 0, "d382d783-d96e-4d51-bc0c-210eb2f74ea8", null], ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "a96e8e54a325c0ffc402545ea9d4f8bce1efbfd873f5de1fd6ce9c7c6bd93256", "user", true, null, null, 0, null, null], ["c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", "54b55bc9335213b8d129e821c5cf1a1eeb12673aa47c8d5f5aa28836d77be9f3", "char", null, null, null, 0, "c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", null], ["d7757c68-9a1b-4081-9f65-7d49940bf4cd", "97c8a29f11a4420b4a7c5dddf2a42a4a0e31ccef4860dbd5e61e44d18c5b0dc7", "user", null, null, null, 0, null, null], ["56b05611-ddb1-4a7f-8841-51af71f8e09c", "44134fd1a7ed1cbfca1a432226061afbcdd69013fa2f89a390819422ee241c8b", "char", null, null, null, 0, "56b05611-ddb1-4a7f-8841-51af71f8e09c", null], ["5d1b5d31-37c4-463e-bb57-3347fba30237", "b2751dbc4c114dfd243159e23cc2251cbbd5957edfaf1593f4df22496606961a", "user", null, null, null, 0, null, null], ["02cc2796-0c46-4b9e-9788-420646a4c724", "f157131b7b826caedc9f9dfb95aa634b5cce8ac3b5ca23069a041cd4b4ac8fe7", "char", null, null, null, 0, "02cc2796-0c46-4b9e-9788-420646a4c724", null], ["5e8f5229-c65f-4f14-bad1-03784cda34e4", "f346bdba7caf72a0c255bf0f765edbc3cf725419d2aa3d13f85f338ce6101dd4", "user", null, null, null, 0, null, null], ["cd924214-7bd4-4e2d-acda-39b13a165021", "db434213e21d672387210c8ac013afdc5bae70c44cbb379d7dbefb3adb23f2bc", "char", null, null, 0, 2, "cd924214-7bd4-4e2d-acda-39b13a165021", null], ["73411225-e8d2-4d65-b058-490007d055d6", "e74667c971e4101884c36374fe1715f63bc657deda511ee0b3a075cb7ab2f595", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-de78-794e-b7fb-fb19e51ee0ef', '01a0e7b4-de63-7415-a4c3-26661d9565f5', 'manifest', 'fc6425c8854f83f5f5ac67738c103afebc59e9b3dfe199bff41ded493d4748fd', '01a0e7b4-de63-7415-a4c3-26661d9565f5:fc6425c8854f83f5f5ac67738c103afebc59e9b3dfe199bff41ded493d4748fd:manifest', '2026-09-28 11:09:45.456499+00', '{"chat_id": "d70ed6e2-92b5-457c-b608-288ea35a6e95", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["216d6c4b-58bd-4a49-a40e-74bc99428d1d", "c02f6d21ba026ce5ce775cac9bac1c9d96ac94878029a9fd7450ab9c18b62701", "user", null, null, null, 0, null, null], ["c45e6101-e4db-4a7d-84ed-870937c43445", "af76476da5f520d4f1d281cbb754b585a9ed075224241cc1bb50447a0d51e56d", "char", null, null, null, 0, "b8c7dc42-7a01-4a44-aec4-02f250dad410", null], ["2c9979da-86a7-4bdd-b0db-4183ad1045f5", "c555403f910b6debaf6dcfaab2a499e81c29999710e97dd665c46df99033bcbc", "user", null, null, null, 0, null, null], ["90690f57-62e5-47c2-abf4-70b23c8f6098", "5a09ef939d3183250d8a3abe5f5901088ab866a53a7aed122c5fa63d6dcfb006", "char", null, null, null, 0, "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", null], ["ee20569f-fd73-4a0f-ba5e-c871ee3b5199", "762b36c2d46a9bdd8721b0590fa2bc39ce67974857154a7aefc0f599dd1db85c", "user", null, null, null, 0, null, null], ["58d4e552-4910-4439-8ee4-03f984387fbf", "445095ff1e0a24412377fd437d27ed745d5f5a833a593df92ca3ea4d5ddb1567", "char", null, null, null, 0, "2047e848-7099-4d81-a50a-9d790dd2def2", null], ["bff5aa15-9d87-4d92-bb82-e493db0053d4", "18c5a41da549a40ea47e7dcac1d3a2987f506a02df07db889b6ed6572eef0873", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::52abe29c-6ec4-4338-85ec-fb767911e4bd::Harbor route::2047e848-7099-4d81-a50a-9d790dd2def2::}}"]], ["0486736e-d82a-41f0-9913-052693fc3cc8", "de092557697cb28b83d9b14d58758762e68c7634768121ee053b62bd5038697e", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'embed', 'embed:01a0e7b4-d1e2-7143-892d-fbdf05300d51:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d1e2-7143-892d-fbdf05300d51"}', 50, 'done', 1, '2026-09-28 11:09:42.23998+00', NULL, NULL, '2026-09-28 11:09:42.23998+00', '2026-09-28 11:09:43.359013+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'embed', 'embed:01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8"}', 50, 'done', 1, '2026-09-28 11:09:42.23998+00', NULL, NULL, '2026-09-28 11:09:42.23998+00', '2026-09-28 11:09:43.37822+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0e7b4-d1e1-7844-af67-852273a8ff72:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d1e1-7844-af67-852273a8ff72"}', 50, 'done', 1, '2026-09-28 11:09:42.23998+00', NULL, NULL, '2026-09-28 11:09:42.23998+00', '2026-09-28 11:09:43.400662+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b"}', 50, 'done', 1, '2026-09-28 11:09:42.197099+00', NULL, NULL, '2026-09-28 11:09:42.197099+00', '2026-09-28 11:09:43.439099+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'embed', 'embed:01a0e7b4-d1b7-767c-a348-e0accd39fa0d:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d1b7-767c-a348-e0accd39fa0d"}', 50, 'done', 1, '2026-09-28 11:09:42.197099+00', NULL, NULL, '2026-09-28 11:09:42.197099+00', '2026-09-28 11:09:43.459536+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0e7b4-d1b5-7f9b-9001-8cb68abe5349:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d1b5-7f9b-9001-8cb68abe5349"}', 50, 'done', 1, '2026-09-28 11:09:42.197099+00', NULL, NULL, '2026-09-28 11:09:42.197099+00', '2026-09-28 11:09:43.478242+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0e7b4-d186-798a-8b0f-be104495deb7:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d186-798a-8b0f-be104495deb7"}', 50, 'done', 1, '2026-09-28 11:09:42.197099+00', NULL, NULL, '2026-09-28 11:09:42.197099+00', '2026-09-28 11:09:43.499259+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0e7b4-d1e2-7143-892d-fbdf05300d51:0c47e3aa59a2bb907865e9cfc64c5f59:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e2-7143-892d-fbdf05300d51", "window_hash": "0c47e3aa59a2bb907865e9cfc64c5f59"}', 100, 'done', 1, '2026-09-28 11:09:42.23998+00', NULL, NULL, '2026-09-28 11:09:42.23998+00', '2026-09-28 11:09:43.571057+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'extract', 'extract:01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8:8b353bb352bfaf19fe75ae18b3cbdbf3:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8", "window_hash": "8b353bb352bfaf19fe75ae18b3cbdbf3"}', 100, 'done', 1, '2026-09-28 11:09:42.23998+00', NULL, NULL, '2026-09-28 11:09:42.23998+00', '2026-09-28 11:09:43.59272+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0e7b4-d1e1-7844-af67-852273a8ff72:f0283f6ee9c67a49f8d90a3910ca70ec:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e1-7844-af67-852273a8ff72", "window_hash": "f0283f6ee9c67a49f8d90a3910ca70ec"}', 100, 'done', 1, '2026-09-28 11:09:42.23998+00', NULL, NULL, '2026-09-28 11:09:42.23998+00', '2026-09-28 11:09:43.612592+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'extract', 'extract:01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa:6421157ebbbc590217f9f15fb66e0d5e:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa", "window_hash": "6421157ebbbc590217f9f15fb66e0d5e"}', 100, 'done', 1, '2026-09-28 11:09:42.23998+00', NULL, NULL, '2026-09-28 11:09:42.23998+00', '2026-09-28 11:09:43.634294+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'extract', 'extract:01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b:d3280a055be13980d114986965d05880:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b", "window_hash": "d3280a055be13980d114986965d05880"}', 100, 'done', 1, '2026-09-28 11:09:42.197099+00', NULL, NULL, '2026-09-28 11:09:42.197099+00', '2026-09-28 11:09:43.657552+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0e7b4-d1b7-767c-a348-e0accd39fa0d:51419cb815b171fcfa0bc7a45dfc1d01:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1b7-767c-a348-e0accd39fa0d", "window_hash": "51419cb815b171fcfa0bc7a45dfc1d01"}', 100, 'done', 1, '2026-09-28 11:09:42.197099+00', NULL, NULL, '2026-09-28 11:09:42.197099+00', '2026-09-28 11:09:43.676886+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'extract', 'extract:01a0e7b4-d1b5-7f9b-9001-8cb68abe5349:217e8c1beb0e668367ca440be66a8aa7:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1b5-7f9b-9001-8cb68abe5349", "window_hash": "217e8c1beb0e668367ca440be66a8aa7"}', 100, 'done', 1, '2026-09-28 11:09:42.197099+00', NULL, NULL, '2026-09-28 11:09:42.197099+00', '2026-09-28 11:09:43.696416+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'extract', 'extract:01a0e7b4-d186-798a-8b0f-be104495deb7:797bcea6b9cd922012580e801e201de1:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d186-798a-8b0f-be104495deb7", "window_hash": "797bcea6b9cd922012580e801e201de1"}', 100, 'done', 1, '2026-09-28 11:09:42.197099+00', NULL, NULL, '2026-09-28 11:09:42.197099+00', '2026-09-28 11:09:43.715974+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'embed', 'embed:01a0e7b4-d185-7b97-9674-b1aeb0f30629:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d185-7b97-9674-b1aeb0f30629"}', 150, 'done', 1, '2026-09-28 11:09:42.144425+00', NULL, NULL, '2026-09-28 11:09:42.144425+00', '2026-09-28 11:09:43.735285+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0e7b4-d184-7f9d-be20-9168f66a5654:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d184-7f9d-be20-9168f66a5654"}', 150, 'done', 1, '2026-09-28 11:09:42.144425+00', NULL, NULL, '2026-09-28 11:09:42.144425+00', '2026-09-28 11:09:43.755118+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0e7b4-d182-7a20-b999-89010ce75cc7:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d182-7a20-b999-89010ce75cc7"}', 150, 'done', 1, '2026-09-28 11:09:42.144425+00', NULL, NULL, '2026-09-28 11:09:42.144425+00', '2026-09-28 11:09:43.774134+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0e7b4-d185-7b97-9674-b1aeb0f30629:88bc65647f516a89f492d5a2cb91843e:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d185-7b97-9674-b1aeb0f30629", "window_hash": "88bc65647f516a89f492d5a2cb91843e"}', 200, 'done', 1, '2026-09-28 11:09:42.144425+00', NULL, NULL, '2026-09-28 11:09:42.144425+00', '2026-09-28 11:09:43.798193+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'extract', 'extract:01a0e7b4-d184-7f9d-be20-9168f66a5654:0037b5198a1db6c9f84b15ff237848ce:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d184-7f9d-be20-9168f66a5654", "window_hash": "0037b5198a1db6c9f84b15ff237848ce"}', 200, 'done', 1, '2026-09-28 11:09:42.144425+00', NULL, NULL, '2026-09-28 11:09:42.144425+00', '2026-09-28 11:09:43.817745+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0e7b4-d182-7a20-b999-89010ce75cc7:e181fbdddab83d6a5c8d8910245256a9:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d182-7a20-b999-89010ce75cc7", "window_hash": "e181fbdddab83d6a5c8d8910245256a9"}', 200, 'done', 1, '2026-09-28 11:09:42.144425+00', NULL, NULL, '2026-09-28 11:09:42.144425+00', '2026-09-28 11:09:43.836917+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0e7b4-d206-78ff-9bbd-5d97d1875760:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d206-78ff-9bbd-5d97d1875760"}', 50, 'done', 1, '2026-09-28 11:09:42.277224+00', NULL, NULL, '2026-09-28 11:09:42.277224+00', '2026-09-28 11:09:43.318158+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'embed', 'embed:01a0e7b4-d1e3-78d3-b08e-908a50db8850:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d1e3-78d3-b08e-908a50db8850"}', 50, 'done', 1, '2026-09-28 11:09:42.277224+00', NULL, NULL, '2026-09-28 11:09:42.277224+00', '2026-09-28 11:09:43.33804+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa"}', 50, 'done', 1, '2026-09-28 11:09:42.23998+00', NULL, NULL, '2026-09-28 11:09:42.23998+00', '2026-09-28 11:09:43.42006+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'extract', 'extract:01a0e7b4-d206-78ff-9bbd-5d97d1875760:a40b926a62243deb10d15040f00c6411:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d206-78ff-9bbd-5d97d1875760", "window_hash": "a40b926a62243deb10d15040f00c6411"}', 100, 'done', 1, '2026-09-28 11:09:42.277224+00', NULL, NULL, '2026-09-28 11:09:42.277224+00', '2026-09-28 11:09:43.526148+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0e7b4-d1e3-78d3-b08e-908a50db8850:929c45850591810a5bb2fb8150f65304:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e3-78d3-b08e-908a50db8850", "window_hash": "929c45850591810a5bb2fb8150f65304"}', 100, 'done', 1, '2026-09-28 11:09:42.277224+00', NULL, NULL, '2026-09-28 11:09:42.277224+00', '2026-09-28 11:09:43.548493+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (60, 'embed', 'embed:01a0e7b4-da50-7d14-a61b-a62e60f366b3:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-da50-7d14-a61b-a62e60f366b3"}', 50, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:44.865268+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (53, 'extract', 'extract:01a0e7b4-da08-7412-9cec-0251b9229307:a9b1cad7d120fe6acb83d23e7f9842a4:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-da08-7412-9cec-0251b9229307", "window_hash": "a9b1cad7d120fe6acb83d23e7f9842a4"}', 100, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:45.018135+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'extract', 'extract:01a0e7b4-da07-78a0-8e99-b39656abd837:3f4b45f1486c4bb84210c87804ec3f18:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-da07-78a0-8e99-b39656abd837", "window_hash": "3f4b45f1486c4bb84210c87804ec3f18"}', 100, 'done', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.22597+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (62, 'embed', 'embed:01a0e7b4-de72-7784-bc44-eb00c4a48a72:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-de72-7784-bc44-eb00c4a48a72"}', 150, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.363145+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (63, 'extract', 'extract:01a0e7b4-de72-73c6-a167-e3bd8271d888:a2e54636bdce93c1390a8de61393d6e9:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-de72-73c6-a167-e3bd8271d888", "window_hash": "a2e54636bdce93c1390a8de61393d6e9"}', 200, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.484665+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (61, 'extract', 'extract:01a0e7b4-de72-7784-bc44-eb00c4a48a72:f31ec11098e3a0f792b503029b492f1c:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-de72-7784-bc44-eb00c4a48a72", "window_hash": "f31ec11098e3a0f792b503029b492f1c"}', 200, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.504136+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (58, 'embed', 'embed:01a0e7b4-da4f-7b8b-881e-b9aa119a0a08:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-da4f-7b8b-881e-b9aa119a0a08"}', 50, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:44.884612+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (44, 'embed', 'embed:01a0e7b4-da08-7fff-8856-3791bbdd0757:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-da08-7fff-8856-3791bbdd0757"}', 50, 'done', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:44.903908+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0e7b4-da08-7412-9cec-0251b9229307:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-da08-7412-9cec-0251b9229307"}', 50, 'done', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:44.927224+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'embed', 'embed:01a0e7b4-da07-78a0-8e99-b39656abd837:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-da07-78a0-8e99-b39656abd837"}', 50, 'done', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:44.945989+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (59, 'extract', 'extract:01a0e7b4-da50-7d14-a61b-a62e60f366b3:d8e02f599675c2c8d31837d12e4aa5d2:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-da50-7d14-a61b-a62e60f366b3", "window_hash": "d8e02f599675c2c8d31837d12e4aa5d2"}', 100, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:44.952293+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (57, 'extract', 'extract:01a0e7b4-da4f-7b8b-881e-b9aa119a0a08:be2b8de3716d8907720b62fdec3d2495:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-da4f-7b8b-881e-b9aa119a0a08", "window_hash": "be2b8de3716d8907720b62fdec3d2495"}', 100, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:44.973429+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (55, 'extract', 'extract:01a0e7b4-da08-7fff-8856-3791bbdd0757:533f9942604be9d70ae8287a062dd13c:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-da08-7fff-8856-3791bbdd0757", "window_hash": "533f9942604be9d70ae8287a062dd13c"}', 100, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:44.995063+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (51, 'extract', 'extract:01a0e7b4-d206-78ff-9bbd-5d97d1875760:ad7cc55b39cbfa832af446090212d18b:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d206-78ff-9bbd-5d97d1875760", "window_hash": "ad7cc55b39cbfa832af446090212d18b"}', 100, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:45.037968+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (49, 'extract', 'extract:01a0e7b4-d1e3-78d3-b08e-908a50db8850:99727ba10708095d2c1b13bb579ca081:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e3-78d3-b08e-908a50db8850", "window_hash": "99727ba10708095d2c1b13bb579ca081"}', 100, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:45.061927+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (47, 'extract', 'extract:01a0e7b4-d1e2-7143-892d-fbdf05300d51:fab333f701230fa88c14bcabff9fe4eb:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e2-7143-892d-fbdf05300d51", "window_hash": "fab333f701230fa88c14bcabff9fe4eb"}', 100, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:45.082476+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (45, 'extract', 'extract:01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8:7951a75e76cd133ed5f42573402d82e0:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8", "window_hash": "7951a75e76cd133ed5f42573402d82e0"}', 100, 'done', 1, '2026-09-28 11:09:44.398308+00', NULL, NULL, '2026-09-28 11:09:44.398308+00', '2026-09-28 11:09:45.103101+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'extract', 'extract:01a0e7b4-da08-7fff-8856-3791bbdd0757:688cc4e208c07d63e31fa423aa6ee5d5:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-da08-7fff-8856-3791bbdd0757", "window_hash": "688cc4e208c07d63e31fa423aa6ee5d5"}', 100, 'obsolete', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.106442+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'extract', 'extract:01a0e7b4-da08-7412-9cec-0251b9229307:e98df38c9db30e89d63a8533fb8a72db:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-da08-7412-9cec-0251b9229307", "window_hash": "e98df38c9db30e89d63a8533fb8a72db"}', 100, 'obsolete', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.109841+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'extract', 'extract:01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8:4a8d95bca8c24327bbe1a7e65fedf50e:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8", "window_hash": "4a8d95bca8c24327bbe1a7e65fedf50e"}', 100, 'obsolete', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.113495+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'extract', 'extract:01a0e7b4-d1e1-7844-af67-852273a8ff72:e5fb163ada5d3e292fa99fefd586ec3a:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1e1-7844-af67-852273a8ff72", "window_hash": "e5fb163ada5d3e292fa99fefd586ec3a"}', 100, 'obsolete', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.11703+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa:8752bc13be1d14fde52d0629bceb183d:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa", "window_hash": "8752bc13be1d14fde52d0629bceb183d"}', 100, 'done', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.137418+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'extract', 'extract:01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b:537f0b8ce54132fd8b37b4e653cb0cc8:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b", "window_hash": "537f0b8ce54132fd8b37b4e653cb0cc8"}', 100, 'done', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.156478+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0e7b4-d1b7-767c-a348-e0accd39fa0d:7b874ac060b4700c7cba96ef9e57b4da:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1b7-767c-a348-e0accd39fa0d", "window_hash": "7b874ac060b4700c7cba96ef9e57b4da"}', 100, 'done', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.181412+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0e7b4-d1b5-7f9b-9001-8cb68abe5349:bd34dd60ac3585a0d27a27889c5e5236:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-d1b5-7f9b-9001-8cb68abe5349", "window_hash": "bd34dd60ac3585a0d27a27889c5e5236"}', 100, 'done', 1, '2026-09-28 11:09:44.326192+00', NULL, NULL, '2026-09-28 11:09:44.326192+00', '2026-09-28 11:09:45.202587+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (74, 'embed', 'embed:01a0e7b4-de77-7801-bd7d-cc65b4055e6f:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-de77-7801-bd7d-cc65b4055e6f"}', 150, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.245687+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (72, 'embed', 'embed:01a0e7b4-de75-7c4a-9692-5bd348227a5e:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-de75-7c4a-9692-5bd348227a5e"}', 150, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.264139+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (70, 'embed', 'embed:01a0e7b4-de75-70a9-89c0-39a145311d39:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-de75-70a9-89c0-39a145311d39"}', 150, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.282733+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (68, 'embed', 'embed:01a0e7b4-de74-795f-8b91-1a2ef726a51d:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-de74-795f-8b91-1a2ef726a51d"}', 150, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.308032+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (66, 'embed', 'embed:01a0e7b4-de73-7aef-8427-28cc5d0da0b3:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-de73-7aef-8427-28cc5d0da0b3"}', 150, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.32723+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (64, 'embed', 'embed:01a0e7b4-de72-73c6-a167-e3bd8271d888:embed-bd6973701dba84f5445973dc5b973fd3', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "embed-bd6973701dba84f5445973dc5b973fd3", "revision_id": "01a0e7b4-de72-73c6-a167-e3bd8271d888"}', 150, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.345262+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (73, 'extract', 'extract:01a0e7b4-de77-7801-bd7d-cc65b4055e6f:8d13ca14fe88afd764997983d196e851:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-de77-7801-bd7d-cc65b4055e6f", "window_hash": "8d13ca14fe88afd764997983d196e851"}', 200, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.383273+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (71, 'extract', 'extract:01a0e7b4-de75-7c4a-9692-5bd348227a5e:854c64b17a9913d53a9607c395e2afcc:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-de75-7c4a-9692-5bd348227a5e", "window_hash": "854c64b17a9913d53a9607c395e2afcc"}', 200, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.402463+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (69, 'extract', 'extract:01a0e7b4-de75-70a9-89c0-39a145311d39:dbe7cd523e7c2c126b45d62bbc9e20c0:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-de75-70a9-89c0-39a145311d39", "window_hash": "dbe7cd523e7c2c126b45d62bbc9e20c0"}', 200, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.42195+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (67, 'extract', 'extract:01a0e7b4-de74-795f-8b91-1a2ef726a51d:42e66c4b657421fc289850146b70c634:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-de74-795f-8b91-1a2ef726a51d", "window_hash": "42e66c4b657421fc289850146b70c634"}', 200, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.444919+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (65, 'extract', 'extract:01a0e7b4-de73-7aef-8427-28cc5d0da0b3:79de3656e948f6cfb3c547129937b848:extract-259aff6e1aca31fb03c8a44fe16acf27', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{"generation": "extract-259aff6e1aca31fb03c8a44fe16acf27", "revision_id": "01a0e7b4-de73-7aef-8427-28cc5d0da0b3", "window_hash": "79de3656e948f6cfb3c547129937b848"}', 200, 'done', 1, '2026-09-28 11:09:45.456499+00', NULL, NULL, '2026-09-28 11:09:45.456499+00', '2026-09-28 11:09:46.464841+00');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-259aff6e1aca31fb03c8a44fe16acf27', 'extract', 'stub', 'http://127.0.0.1:42457/v1', '{"kind": "extract", "model": "stub", "prompt": "beea838dfb7120ac", "window": 6, "compiler": "extract-v3", "endpoint": "http://127.0.0.1:42457/v1", "json_mode": true, "normalizer": "clean-v1", "predicates": "253e9535891a7be7", "temperature": 0, "target_chars": 6000, "context_chars": 2000}', '2026-09-28 11:09:41.90367+00', '2026-09-28 11:09:41.908267+00');
INSERT INTO public.projection_generation VALUES ('embed-bd6973701dba84f5445973dc5b973fd3', 'embed', 'stub-embed', 'http://127.0.0.1:42457/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:42457/v1", "max_chunks": 8, "normalizer": "clean-v1", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-28 11:09:41.90367+00', '2026-09-28 11:09:41.911625+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-d1ac-7631-bdc1-aa55f2aeec1d', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '01a0e7b4-d188-7c20-9585-f19c7f5edd6c', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b4-d185-7b97-9674-b1aeb0f30629", "host_logical_id": "3d78bc65-a11b-4c78-ab58-4b66fa45edea"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b4-d185-7b97-9674-b1aeb0f30629", "host_logical_id": "3d78bc65-a11b-4c78-ab58-4b66fa45edea"}]', 0, '{"embed": 23.75, "facts": 0, "vector": 1.63, "lexical": 2.91, "extractor": "extract-259aff6e1aca", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 29.4, "embedding_projection": "embed-bd6973701dba84"}', 'fresh', '2026-09-28 11:09:42.158884+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-d1d5-7e29-859e-7ab818b7bf92', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '01a0e7b4-d188-7c20-9585-f19c7f5edd6c', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b", "host_logical_id": "f95c8265-e9d8-4dbb-b359-2da87e358cea"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b", "host_logical_id": "f95c8265-e9d8-4dbb-b359-2da87e358cea"}]', 0, '{"embed": 15.48, "facts": 0, "vector": 1.78, "lexical": 2.7, "extractor": "extract-259aff6e1aca", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 21.12, "embedding_projection": "embed-bd6973701dba84"}', 'fresh', '2026-09-28 11:09:42.208627+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-d1fc-7621-b476-8beffd269f59', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '01a0e7b4-d188-7c20-9585-f19c7f5edd6c', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b4-d1e2-7143-892d-fbdf05300d51", "host_logical_id": "d7757c68-9a1b-4081-9f65-7d49940bf4cd"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b4-d1e2-7143-892d-fbdf05300d51", "host_logical_id": "d7757c68-9a1b-4081-9f65-7d49940bf4cd"}]', 0, '{"embed": 13.72, "facts": 0, "vector": 1.14, "lexical": 2.02, "extractor": "extract-259aff6e1aca", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 17.62, "embedding_projection": "embed-bd6973701dba84"}', 'fresh', '2026-09-28 11:09:42.250748+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-d21f-7893-9464-b8bca3aa804d', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '01a0e7b4-d188-7c20-9585-f19c7f5edd6c', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b4-d206-78ff-9bbd-5d97d1875760", "host_logical_id": "5d1b5d31-37c4-463e-bb57-3347fba30237"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0e7b4-d186-798a-8b0f-be104495deb7", "host_logical_id": "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0e7b4-d184-7f9d-be20-9168f66a5654", "host_logical_id": "b8c7dc42-7a01-4a44-aec4-02f250dad410"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0e7b4-d184-7f9d-be20-9168f66a5654"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b4-d186-798a-8b0f-be104495deb7"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b4-d206-78ff-9bbd-5d97d1875760", "host_logical_id": "5d1b5d31-37c4-463e-bb57-3347fba30237"}]', 174, '{"embed": 14.09, "facts": 0, "vector": 1.2, "lexical": 2.32, "extractor": "extract-259aff6e1aca", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 18.37, "embedding_projection": "embed-bd6973701dba84"}', 'fresh', '2026-09-28 11:09:42.285669+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-da23-764f-bc7f-7e0471586545', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '01a0e7b4-da0b-7d7a-9e9e-cb415d9c7650', 'And the compass?', '[{"rrf": 0.03128, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8", "host_logical_id": "c7c57cf9-9ef7-47b4-8ecf-3a455ee18732"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b4-da08-7fff-8856-3791bbdd0757", "host_logical_id": "5e8f5229-c65f-4f14-bad1-03784cda34e4"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0e7b4-d184-7f9d-be20-9168f66a5654", "host_logical_id": "b8c7dc42-7a01-4a44-aec4-02f250dad410"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0e7b4-d182-7a20-b999-89010ce75cc7", "host_logical_id": "c2c100c6-a2a0-411b-91eb-a9d5b654ff06"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa", "host_logical_id": "d382d783-d96e-4d51-bc0c-210eb2f74ea8"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0e7b4-d1b7-767c-a348-e0accd39fa0d", "host_logical_id": "2047e848-7099-4d81-a50a-9d790dd2def2"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0e7b4-d182-7a20-b999-89010ce75cc7"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0e7b4-d184-7f9d-be20-9168f66a5654"}, {"turn": 5, "score": 0.01562, "revision_id": "01a0e7b4-d1b7-767c-a348-e0accd39fa0d"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa"}, {"turn": 9, "score": 0.03128, "revision_id": "01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b4-da08-7fff-8856-3791bbdd0757", "host_logical_id": "5e8f5229-c65f-4f14-bad1-03784cda34e4"}]', 252, '{"embed": 14.0, "facts": 0, "vector": 1.04, "lexical": 3.13, "extractor": "extract-259aff6e1aca", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 19.14, "embedding_projection": "embed-bd6973701dba84"}', 'fresh', '2026-09-28 11:09:44.33663+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-da46-790e-a4a0-0ff746b81820', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '01a0e7b4-da0b-7d7a-9e9e-cb415d9c7650', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8", "host_logical_id": "c7c57cf9-9ef7-47b4-8ecf-3a455ee18732"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b4-da08-7fff-8856-3791bbdd0757", "host_logical_id": "5e8f5229-c65f-4f14-bad1-03784cda34e4"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0e7b4-d1e3-78d3-b08e-908a50db8850", "host_logical_id": "56b05611-ddb1-4a7f-8841-51af71f8e09c"}]', '[{"turn": 9, "score": 0.03002, "revision_id": "01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8"}, {"turn": 11, "score": 0.01639, "revision_id": "01a0e7b4-d1e3-78d3-b08e-908a50db8850"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b4-da08-7fff-8856-3791bbdd0757", "host_logical_id": "5e8f5229-c65f-4f14-bad1-03784cda34e4"}]', 171, '{"embed": 13.88, "facts": 0, "vector": 1.14, "lexical": 2.03, "extractor": "extract-259aff6e1aca", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 17.93, "embedding_projection": "embed-bd6973701dba84"}', 'fresh', '2026-09-28 11:09:44.372414+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-da69-7088-8a3c-c02d37a9608e', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '01a0e7b4-da52-7e20-a978-f7fef6fb6090', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b", "host_logical_id": "f95c8265-e9d8-4dbb-b359-2da87e358cea"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b4-da50-7d14-a61b-a62e60f366b3", "host_logical_id": "73411225-e8d2-4d65-b058-490007d055d6"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b4-da50-7d14-a61b-a62e60f366b3", "host_logical_id": "73411225-e8d2-4d65-b058-490007d055d6"}]', 138, '{"embed": 14.03, "facts": 0, "vector": 1.07, "lexical": 2.24, "extractor": "extract-259aff6e1aca", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 18.11, "embedding_projection": "embed-bd6973701dba84"}', 'fresh', '2026-09-28 11:09:44.407719+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-de90-757d-9a43-6c7bb4c69789', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0e7b4-de73-7aef-8427-28cc5d0da0b3", "host_logical_id": "2c9979da-86a7-4bdd-b0db-4183ad1045f5"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0e7b4-de74-795f-8b91-1a2ef726a51d", "host_logical_id": "90690f57-62e5-47c2-abf4-70b23c8f6098"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0e7b4-de73-7aef-8427-28cc5d0da0b3"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b4-de74-795f-8b91-1a2ef726a51d"}]', '[]', 164, '{"embed": 13.86, "facts": 0, "vector": 0.69, "lexical": 2.12, "extractor": "extract-259aff6e1aca", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 17.36, "embedding_projection": "embed-bd6973701dba84"}', 'fresh', '2026-09-28 11:09:45.471128+00');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d206-78ff-9bbd-5d97d1875760', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d1e3-78d3-b08e-908a50db8850', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d1e2-7143-892d-fbdf05300d51', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d1e1-7844-af67-852273a8ff72', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d1b7-767c-a348-e0accd39fa0d', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d1b5-7f9b-9001-8cb68abe5349', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d186-798a-8b0f-be104495deb7', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d185-7b97-9674-b1aeb0f30629', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d184-7f9d-be20-9168f66a5654', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-d182-7a20-b999-89010ce75cc7', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-da50-7d14-a61b-a62e60f366b3', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-da4f-7b8b-881e-b9aa119a0a08', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-da08-7fff-8856-3791bbdd0757', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-da08-7412-9cec-0251b9229307', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-da07-78a0-8e99-b39656abd837', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-de77-7801-bd7d-cc65b4055e6f', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-de75-7c4a-9692-5bd348227a5e', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-de75-70a9-89c0-39a145311d39', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-de74-795f-8b91-1a2ef726a51d', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-de73-7aef-8427-28cc5d0da0b3', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-de72-73c6-a167-e3bd8271d888', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-bd6973701dba84f5445973dc5b973fd3');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-de72-7784-bc44-eb00c4a48a72', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-bd6973701dba84f5445973dc5b973fd3');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0e7b4-d182-7a20-b999-89010ce75cc7', 'clean-v1', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:09:42.144425+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d184-7f9d-be20-9168f66a5654', 'clean-v1', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:09:42.144425+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d185-7b97-9674-b1aeb0f30629', 'clean-v1', 'Is Rin with you?', 16, 16, '2026-09-28 11:09:42.144425+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d186-798a-8b0f-be104495deb7', 'clean-v1', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-28 11:09:42.144425+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d1b5-7f9b-9001-8cb68abe5349', 'clean-v1', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:09:42.197099+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d1b7-767c-a348-e0accd39fa0d', 'clean-v1', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:09:42.197099+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b', 'clean-v1', 'Let''s check the market.', 23, 23, '2026-09-28 11:09:42.197099+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa', 'clean-v1', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-28 11:09:42.197099+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d1e1-7844-af67-852273a8ff72', 'clean-v1', 'Any news from the harbor?', 25, 25, '2026-09-28 11:09:42.23998+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8', 'clean-v1', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-28 11:09:42.23998+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d1e2-7143-892d-fbdf05300d51', 'clean-v1', 'Where do we meet tonight?', 25, 25, '2026-09-28 11:09:42.23998+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d1e3-78d3-b08e-908a50db8850', 'clean-v1', 'Mina moved to the bell tower.', 29, 29, '2026-09-28 11:09:42.23998+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-d206-78ff-9bbd-5d97d1875760', 'clean-v1', 'Where is Mina now?', 18, 18, '2026-09-28 11:09:42.277224+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-da07-78a0-8e99-b39656abd837', 'clean-v1', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:09:44.326192+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-da08-7412-9cec-0251b9229307', 'clean-v1', 'Mina keeps the brass key close.', 31, 31, '2026-09-28 11:09:44.326192+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-da08-7fff-8856-3791bbdd0757', 'clean-v1', 'And the compass?', 16, 16, '2026-09-28 11:09:44.326192+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-da2d-7c93-bd6b-43b1b0c3d889', 'clean-v1', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-28 11:09:44.364026+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-da4f-7ddc-add2-fe287da4eea7', 'clean-v1', 'Any news from the harbor?', 25, 25, '2026-09-28 11:09:44.398308+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-da4f-7b8b-881e-b9aa119a0a08', 'clean-v1', 'Rin has the silver compass.', 27, 27, '2026-09-28 11:09:44.398308+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-da50-7d14-a61b-a62e60f366b3', 'clean-v1', 'Let''s go.', 9, 9, '2026-09-28 11:09:44.398308+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-de72-7784-bc44-eb00c4a48a72', 'clean-v1', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:09:45.456499+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-de72-73c6-a167-e3bd8271d888', 'clean-v1', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:09:45.456499+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-de73-7aef-8427-28cc5d0da0b3', 'clean-v1', 'Is Rin with you?', 16, 16, '2026-09-28 11:09:45.456499+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-de74-795f-8b91-1a2ef726a51d', 'clean-v1', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:09:45.456499+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-de75-70a9-89c0-39a145311d39', 'clean-v1', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:09:45.456499+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-de75-7c4a-9692-5bd348227a5e', 'clean-v1', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:09:45.456499+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-de76-72f3-82b2-58055eabb07a', 'clean-v1', '{{specialcomment::branchedfrom::52abe29c-6ec4-4338-85ec-fb767911e4bd::Harbor route::2047e848-7099-4d81-a50a-9d790dd2def2::}}', 124, 124, '2026-09-28 11:09:45.456499+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-de77-7801-bd7d-cc65b4055e6f', 'clean-v1', 'Rin moved to the market.', 24, 24, '2026-09-28 11:09:45.456499+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-28 11:09:41.263063+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-28 11:09:41.34297+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-28 11:09:41.359208+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-28 11:09:41.401238+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-28 11:09:41.423123+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-28 11:09:41.432543+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-28 11:09:41.43467+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-28 11:09:41.446886+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-28 11:09:41.464112+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-28 11:09:41.466322+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0e7b4-d181-78b6-8969-b0167792f518', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'c2c100c6-a2a0-411b-91eb-a9d5b654ff06', 'message', '2026-09-28 11:09:42.144425+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d184-7863-9f3a-d0ea8d3006f2', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'b8c7dc42-7a01-4a44-aec4-02f250dad410', 'message', '2026-09-28 11:09:42.144425+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d185-73ff-80f8-315a0a71426a', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '3d78bc65-a11b-4c78-ab58-4b66fa45edea', 'message', '2026-09-28 11:09:42.144425+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d185-7431-9a25-454e061e598b', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d', 'message', '2026-09-28 11:09:42.144425+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d1b5-7ecf-9c6e-fcfc0f360197', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893', 'message', '2026-09-28 11:09:42.197099+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d1b6-7a97-9b00-c65d5cecae5d', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '2047e848-7099-4d81-a50a-9d790dd2def2', 'message', '2026-09-28 11:09:42.197099+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d1b7-75d1-887e-793bd0cd226b', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'f95c8265-e9d8-4dbb-b359-2da87e358cea', 'message', '2026-09-28 11:09:42.197099+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d1b8-7040-96cf-3312a6d59dd7', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'd382d783-d96e-4d51-bc0c-210eb2f74ea8', 'message', '2026-09-28 11:09:42.197099+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d1e0-74cf-994a-06345318119d', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c', 'message', '2026-09-28 11:09:42.23998+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d1e1-72a7-97ba-73c6ad6d27d0', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'c7c57cf9-9ef7-47b4-8ecf-3a455ee18732', 'message', '2026-09-28 11:09:42.23998+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d1e2-74d3-9e65-d4da3f983b12', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'd7757c68-9a1b-4081-9f65-7d49940bf4cd', 'message', '2026-09-28 11:09:42.23998+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d1e3-7cea-ae46-fd2307af4637', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '56b05611-ddb1-4a7f-8841-51af71f8e09c', 'message', '2026-09-28 11:09:42.23998+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-d205-77ce-9b3d-3ee97fc33697', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '5d1b5d31-37c4-463e-bb57-3347fba30237', 'message', '2026-09-28 11:09:42.277224+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-da07-7cf2-b59e-c71d469d1295', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '02cc2796-0c46-4b9e-9788-420646a4c724', 'message', '2026-09-28 11:09:44.326192+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-da08-7e8f-a364-448bf3988363', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '5e8f5229-c65f-4f14-bad1-03784cda34e4', 'message', '2026-09-28 11:09:44.326192+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-da2c-7032-a6f3-f82358b88349', '01a0e7b4-d174-739f-86c1-49cc6910abe9', 'cd924214-7bd4-4e2d-acda-39b13a165021', 'message', '2026-09-28 11:09:44.364026+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-da4f-7813-a14a-35c7a72ea409', '01a0e7b4-d174-739f-86c1-49cc6910abe9', '73411225-e8d2-4d65-b058-490007d055d6', 'message', '2026-09-28 11:09:44.398308+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-de71-719c-a3bb-5e3d366b1a8e', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '216d6c4b-58bd-4a49-a40e-74bc99428d1d', 'message', '2026-09-28 11:09:45.456499+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-de72-77a7-9372-c5deb5da105f', '01a0e7b4-de63-7415-a4c3-26661d9565f5', 'c45e6101-e4db-4a7d-84ed-870937c43445', 'message', '2026-09-28 11:09:45.456499+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-de73-7c38-b1af-74000885ef35', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '2c9979da-86a7-4bdd-b0db-4183ad1045f5', 'message', '2026-09-28 11:09:45.456499+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-de74-7ce1-9d52-4448a57fbd1f', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '90690f57-62e5-47c2-abf4-70b23c8f6098', 'message', '2026-09-28 11:09:45.456499+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-de74-76f8-bb20-674337e32a57', '01a0e7b4-de63-7415-a4c3-26661d9565f5', 'ee20569f-fd73-4a0f-ba5e-c871ee3b5199', 'message', '2026-09-28 11:09:45.456499+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-de75-72d0-864b-c7f22bd4ddc9', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '58d4e552-4910-4439-8ee4-03f984387fbf', 'message', '2026-09-28 11:09:45.456499+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-de76-70b0-afc9-7711e26a8dec', '01a0e7b4-de63-7415-a4c3-26661d9565f5', 'bff5aa15-9d87-4d92-bb82-e493db0053d4', 'message', '2026-09-28 11:09:45.456499+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-de76-7f9c-94aa-9ecad2d16ec4', '01a0e7b4-de63-7415-a4c3-26661d9565f5', '0486736e-d82a-41f0-9913-052693fc3cc8', 'message', '2026-09-28 11:09:45.456499+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0e7b4-d182-7a20-b999-89010ce75cc7', '01a0e7b4-d181-78b6-8969-b0167792f518', '17e4ba427e5685cfa9d67220bee94eba0d7d5328136a515abd71ec3595e354fc', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "c2c100c6-a2a0-411b-91eb-a9d5b654ff06", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:42.144425+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d185-7b97-9674-b1aeb0f30629', '01a0e7b4-d185-73ff-80f8-315a0a71426a', '71fe3b62b131f41594a1abe0587663c2a25556cd6e7692c5b4dcfd6fd3a316a5', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "3d78bc65-a11b-4c78-ab58-4b66fa45edea", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:42.144425+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d184-7f9d-be20-9168f66a5654', '01a0e7b4-d184-7863-9f3a-d0ea8d3006f2', 'fb04935fe0caccaed815cf4cb0e98f68d9a8095f539ad3de9c81559f60f57958', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "b8c7dc42-7a01-4a44-aec4-02f250dad410", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b8c7dc42-7a01-4a44-aec4-02f250dad410", "specialComments": []}', '2026-09-28 11:09:42.144425+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d1b5-7f9b-9001-8cb68abe5349', '01a0e7b4-d1b5-7ecf-9c6e-fcfc0f360197', '53dedee3233d1a8ecd4790c7d9102cbdde4848fbc053154c2692e82e773dbf37', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:42.197099+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d1b7-7ec8-aac2-4b9bc32f863b', '01a0e7b4-d1b7-75d1-887e-793bd0cd226b', '4548e3c47f01e977311c3bd11cd49416e36f0454b1a69a1e2012ba757d8baf9e', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "f95c8265-e9d8-4dbb-b359-2da87e358cea", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:42.197099+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d1b7-767c-a348-e0accd39fa0d', '01a0e7b4-d1b6-7a97-9b00-c65d5cecae5d', '79c3127817fe16ab0993ba16bcf3b27b75f064c250dc914fbc55a48455c28765', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "2047e848-7099-4d81-a50a-9d790dd2def2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "2047e848-7099-4d81-a50a-9d790dd2def2", "specialComments": []}', '2026-09-28 11:09:42.197099+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d1e2-7143-892d-fbdf05300d51', '01a0e7b4-d1e2-74d3-9e65-d4da3f983b12', '97c8a29f11a4420b4a7c5dddf2a42a4a0e31ccef4860dbd5e61e44d18c5b0dc7', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "d7757c68-9a1b-4081-9f65-7d49940bf4cd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:42.23998+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d1e2-7d0b-9193-f27f758a8ea8', '01a0e7b4-d1e1-72a7-97ba-73c6ad6d27d0', '54b55bc9335213b8d129e821c5cf1a1eeb12673aa47c8d5f5aa28836d77be9f3', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", "specialComments": []}', '2026-09-28 11:09:42.23998+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d1b8-74cb-955f-2a9e3e1b76fa', '01a0e7b4-d1b8-7040-96cf-3312a6d59dd7', '72063d31aa1cd86c091920ef80c3c3bbaebf52a4cae85f21b1944c3f615fc8b0', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "d382d783-d96e-4d51-bc0c-210eb2f74ea8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "d382d783-d96e-4d51-bc0c-210eb2f74ea8", "specialComments": []}', '2026-09-28 11:09:42.197099+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d206-78ff-9bbd-5d97d1875760', '01a0e7b4-d205-77ce-9b3d-3ee97fc33697', 'b2751dbc4c114dfd243159e23cc2251cbbd5957edfaf1593f4df22496606961a', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "5d1b5d31-37c4-463e-bb57-3347fba30237", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:42.277224+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d1e3-78d3-b08e-908a50db8850', '01a0e7b4-d1e3-7cea-ae46-fd2307af4637', '44134fd1a7ed1cbfca1a432226061afbcdd69013fa2f89a390819422ee241c8b', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "56b05611-ddb1-4a7f-8841-51af71f8e09c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "56b05611-ddb1-4a7f-8841-51af71f8e09c", "specialComments": []}', '2026-09-28 11:09:42.23998+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-da08-7fff-8856-3791bbdd0757', '01a0e7b4-da08-7e8f-a364-448bf3988363', 'f346bdba7caf72a0c255bf0f765edbc3cf725419d2aa3d13f85f338ce6101dd4', 'And the compass?', '{"name": null, "role": "user", "chatId": "5e8f5229-c65f-4f14-bad1-03784cda34e4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:44.326192+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-da08-7412-9cec-0251b9229307', '01a0e7b4-da07-7cf2-b59e-c71d469d1295', 'f157131b7b826caedc9f9dfb95aa634b5cce8ac3b5ca23069a041cd4b4ac8fe7', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "02cc2796-0c46-4b9e-9788-420646a4c724", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "02cc2796-0c46-4b9e-9788-420646a4c724", "specialComments": []}', '2026-09-28 11:09:44.326192+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-da07-78a0-8e99-b39656abd837', '01a0e7b4-d185-7431-9a25-454e061e598b', '78c443c18a2119cf938ff1e9e8182f7fb6ca4ec46b35da3271bbc067f9e178b5', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "specialComments": []}', '2026-09-28 11:09:44.326192+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-da2d-7c93-bd6b-43b1b0c3d889', '01a0e7b4-da2c-7032-a6f3-f82358b88349', '836932692fcb5a89b812e5e7ae93cc7f60426b59ae0fe0f28870d75683480d48', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "cd924214-7bd4-4e2d-acda-39b13a165021", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "cd924214-7bd4-4e2d-acda-39b13a165021", "specialComments": []}', '2026-09-28 11:09:44.364026+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d1e1-7844-af67-852273a8ff72', '01a0e7b4-d1e0-74cf-994a-06345318119d', 'b8f53dc792434d3a2f4af64a860ddd3a85eb9c11a44407f42f79587cbc744b13', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:42.23998+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-de72-7784-bc44-eb00c4a48a72', '01a0e7b4-de71-719c-a3bb-5e3d366b1a8e', 'c02f6d21ba026ce5ce775cac9bac1c9d96ac94878029a9fd7450ab9c18b62701', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "216d6c4b-58bd-4a49-a40e-74bc99428d1d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:45.456499+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-d186-798a-8b0f-be104495deb7', '01a0e7b4-d185-7431-9a25-454e061e598b', 'fed91523ee6aa10eeb8cdabb7b0c005062ebdb50f605b72cfb882ebe41aba0d8', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "specialComments": []}', '2026-09-28 11:09:42.144425+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-da4f-7ddc-add2-fe287da4eea7', '01a0e7b4-d1e0-74cf-994a-06345318119d', 'a96e8e54a325c0ffc402545ea9d4f8bce1efbfd873f5de1fd6ce9c7c6bd93256', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:44.398308+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-da50-7d14-a61b-a62e60f366b3', '01a0e7b4-da4f-7813-a14a-35c7a72ea409', 'e74667c971e4101884c36374fe1715f63bc657deda511ee0b3a075cb7ab2f595', 'Let''s go.', '{"name": null, "role": "user", "chatId": "73411225-e8d2-4d65-b058-490007d055d6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:44.398308+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-da4f-7b8b-881e-b9aa119a0a08', '01a0e7b4-da2c-7032-a6f3-f82358b88349', 'db434213e21d672387210c8ac013afdc5bae70c44cbb379d7dbefb3adb23f2bc', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "cd924214-7bd4-4e2d-acda-39b13a165021", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "cd924214-7bd4-4e2d-acda-39b13a165021", "specialComments": []}', '2026-09-28 11:09:44.398308+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-de73-7aef-8427-28cc5d0da0b3', '01a0e7b4-de73-7c38-b1af-74000885ef35', 'c555403f910b6debaf6dcfaab2a499e81c29999710e97dd665c46df99033bcbc', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "2c9979da-86a7-4bdd-b0db-4183ad1045f5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:45.456499+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-de75-70a9-89c0-39a145311d39', '01a0e7b4-de74-76f8-bb20-674337e32a57', '762b36c2d46a9bdd8721b0590fa2bc39ce67974857154a7aefc0f599dd1db85c', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "ee20569f-fd73-4a0f-ba5e-c871ee3b5199", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:45.456499+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-de76-72f3-82b2-58055eabb07a', '01a0e7b4-de76-70b0-afc9-7711e26a8dec', '18c5a41da549a40ea47e7dcac1d3a2987f506a02df07db889b6ed6572eef0873', '{{specialcomment::branchedfrom::52abe29c-6ec4-4338-85ec-fb767911e4bd::Harbor route::2047e848-7099-4d81-a50a-9d790dd2def2::}}', '{"name": null, "role": "char", "chatId": "bff5aa15-9d87-4d92-bb82-e493db0053d4", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::52abe29c-6ec4-4338-85ec-fb767911e4bd::Harbor route::2047e848-7099-4d81-a50a-9d790dd2def2::}}"]}', '2026-09-28 11:09:45.456499+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-de77-7801-bd7d-cc65b4055e6f', '01a0e7b4-de76-7f9c-94aa-9ecad2d16ec4', 'de092557697cb28b83d9b14d58758762e68c7634768121ee053b62bd5038697e', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "0486736e-d82a-41f0-9913-052693fc3cc8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:45.456499+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-de75-7c4a-9692-5bd348227a5e', '01a0e7b4-de75-72d0-864b-c7f22bd4ddc9', '445095ff1e0a24412377fd437d27ed745d5f5a833a593df92ca3ea4d5ddb1567', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "58d4e552-4910-4439-8ee4-03f984387fbf", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "2047e848-7099-4d81-a50a-9d790dd2def2", "specialComments": []}', '2026-09-28 11:09:45.456499+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-de74-795f-8b91-1a2ef726a51d', '01a0e7b4-de74-7ce1-9d52-4448a57fbd1f', '5a09ef939d3183250d8a3abe5f5901088ab866a53a7aed122c5fa63d6dcfb006', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "90690f57-62e5-47c2-abf4-70b23c8f6098", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "specialComments": []}', '2026-09-28 11:09:45.456499+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-de72-73c6-a167-e3bd8271d888', '01a0e7b4-de72-77a7-9372-c5deb5da105f', 'af76476da5f520d4f1d281cbb754b585a9ed075224241cc1bb50447a0d51e56d', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "c45e6101-e4db-4a7d-84ed-870937c43445", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b8c7dc42-7a01-4a44-aec4-02f250dad410", "specialComments": []}', '2026-09-28 11:09:45.456499+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b4-da52-7e20-a978-f7fef6fb6090', 3, '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{01a0e7b4-da0b-7d7a-9e9e-cb415d9c7650}', 'reconciliation', '1f065114e5b8330959267800828e7988689d28b1db5066d42eb8035501a78051', '{"ops": [{"op": "replace", "to": ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "a96e8e54a325c0ffc402545ea9d4f8bce1efbfd873f5de1fd6ce9c7c6bd93256"], "from": ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "b8f53dc792434d3a2f4af64a860ddd3a85eb9c11a44407f42f79587cbc744b13"]}, {"op": "replace", "to": ["cd924214-7bd4-4e2d-acda-39b13a165021", "db434213e21d672387210c8ac013afdc5bae70c44cbb379d7dbefb3adb23f2bc"], "from": ["cd924214-7bd4-4e2d-acda-39b13a165021", "836932692fcb5a89b812e5e7ae93cc7f60426b59ae0fe0f28870d75683480d48"]}, {"op": "insert", "after": ["cd924214-7bd4-4e2d-acda-39b13a165021", "db434213e21d672387210c8ac013afdc5bae70c44cbb379d7dbefb3adb23f2bc"], "member": ["73411225-e8d2-4d65-b058-490007d055d6", "e74667c971e4101884c36374fe1715f63bc657deda511ee0b3a075cb7ab2f595"]}], "changes": [{"new": ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "a96e8e54a325c0ffc402545ea9d4f8bce1efbfd873f5de1fd6ce9c7c6bd93256"], "old": ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "b8f53dc792434d3a2f4af64a860ddd3a85eb9c11a44407f42f79587cbc744b13"], "kind": "disable", "position": 8, "host_logical_id": "fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c"}, {"new": ["cd924214-7bd4-4e2d-acda-39b13a165021", "db434213e21d672387210c8ac013afdc5bae70c44cbb379d7dbefb3adb23f2bc"], "old": ["cd924214-7bd4-4e2d-acda-39b13a165021", "836932692fcb5a89b812e5e7ae93cc7f60426b59ae0fe0f28870d75683480d48"], "kind": "swipe", "position": 15, "host_logical_id": "cd924214-7bd4-4e2d-acda-39b13a165021"}, {"new": ["73411225-e8d2-4d65-b058-490007d055d6", "e74667c971e4101884c36374fe1715f63bc657deda511ee0b3a075cb7ab2f595"], "old": null, "kind": "append", "position": 16, "host_logical_id": "73411225-e8d2-4d65-b058-490007d055d6"}]}', '2026-09-28 11:09:44.398308+00', '01a0e7b4-da52-7321-b17c-cdb543194b81');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b4-d188-7c20-9585-f19c7f5edd6c', 1, '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{}', 'import', 'b5ecb4df53cf3f396a3d214dff423749c8a18b2c815f59d913772386d3fd91da', '{"ops": [{"op": "set", "members": [["c2c100c6-a2a0-411b-91eb-a9d5b654ff06", "17e4ba427e5685cfa9d67220bee94eba0d7d5328136a515abd71ec3595e354fc"], ["b8c7dc42-7a01-4a44-aec4-02f250dad410", "fb04935fe0caccaed815cf4cb0e98f68d9a8095f539ad3de9c81559f60f57958"], ["3d78bc65-a11b-4c78-ab58-4b66fa45edea", "71fe3b62b131f41594a1abe0587663c2a25556cd6e7692c5b4dcfd6fd3a316a5"], ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "fed91523ee6aa10eeb8cdabb7b0c005062ebdb50f605b72cfb882ebe41aba0d8"]]}, {"op": "insert", "after": ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "fed91523ee6aa10eeb8cdabb7b0c005062ebdb50f605b72cfb882ebe41aba0d8"], "member": ["0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893", "53dedee3233d1a8ecd4790c7d9102cbdde4848fbc053154c2692e82e773dbf37"]}, {"op": "insert", "after": ["0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893", "53dedee3233d1a8ecd4790c7d9102cbdde4848fbc053154c2692e82e773dbf37"], "member": ["2047e848-7099-4d81-a50a-9d790dd2def2", "79c3127817fe16ab0993ba16bcf3b27b75f064c250dc914fbc55a48455c28765"]}, {"op": "insert", "after": ["2047e848-7099-4d81-a50a-9d790dd2def2", "79c3127817fe16ab0993ba16bcf3b27b75f064c250dc914fbc55a48455c28765"], "member": ["f95c8265-e9d8-4dbb-b359-2da87e358cea", "4548e3c47f01e977311c3bd11cd49416e36f0454b1a69a1e2012ba757d8baf9e"]}, {"op": "insert", "after": ["f95c8265-e9d8-4dbb-b359-2da87e358cea", "4548e3c47f01e977311c3bd11cd49416e36f0454b1a69a1e2012ba757d8baf9e"], "member": ["d382d783-d96e-4d51-bc0c-210eb2f74ea8", "72063d31aa1cd86c091920ef80c3c3bbaebf52a4cae85f21b1944c3f615fc8b0"]}, {"op": "insert", "after": ["d382d783-d96e-4d51-bc0c-210eb2f74ea8", "72063d31aa1cd86c091920ef80c3c3bbaebf52a4cae85f21b1944c3f615fc8b0"], "member": ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "b8f53dc792434d3a2f4af64a860ddd3a85eb9c11a44407f42f79587cbc744b13"]}, {"op": "insert", "after": ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "b8f53dc792434d3a2f4af64a860ddd3a85eb9c11a44407f42f79587cbc744b13"], "member": ["c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", "54b55bc9335213b8d129e821c5cf1a1eeb12673aa47c8d5f5aa28836d77be9f3"]}, {"op": "insert", "after": ["c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", "54b55bc9335213b8d129e821c5cf1a1eeb12673aa47c8d5f5aa28836d77be9f3"], "member": ["d7757c68-9a1b-4081-9f65-7d49940bf4cd", "97c8a29f11a4420b4a7c5dddf2a42a4a0e31ccef4860dbd5e61e44d18c5b0dc7"]}, {"op": "insert", "after": ["d7757c68-9a1b-4081-9f65-7d49940bf4cd", "97c8a29f11a4420b4a7c5dddf2a42a4a0e31ccef4860dbd5e61e44d18c5b0dc7"], "member": ["56b05611-ddb1-4a7f-8841-51af71f8e09c", "44134fd1a7ed1cbfca1a432226061afbcdd69013fa2f89a390819422ee241c8b"]}, {"op": "insert", "after": ["56b05611-ddb1-4a7f-8841-51af71f8e09c", "44134fd1a7ed1cbfca1a432226061afbcdd69013fa2f89a390819422ee241c8b"], "member": ["5d1b5d31-37c4-463e-bb57-3347fba30237", "b2751dbc4c114dfd243159e23cc2251cbbd5957edfaf1593f4df22496606961a"]}], "changes": [{"new": ["c2c100c6-a2a0-411b-91eb-a9d5b654ff06", "17e4ba427e5685cfa9d67220bee94eba0d7d5328136a515abd71ec3595e354fc"], "old": null, "kind": "append", "position": 0, "host_logical_id": "c2c100c6-a2a0-411b-91eb-a9d5b654ff06"}, {"new": ["b8c7dc42-7a01-4a44-aec4-02f250dad410", "fb04935fe0caccaed815cf4cb0e98f68d9a8095f539ad3de9c81559f60f57958"], "old": null, "kind": "append", "position": 1, "host_logical_id": "b8c7dc42-7a01-4a44-aec4-02f250dad410"}, {"new": ["3d78bc65-a11b-4c78-ab58-4b66fa45edea", "71fe3b62b131f41594a1abe0587663c2a25556cd6e7692c5b4dcfd6fd3a316a5"], "old": null, "kind": "append", "position": 2, "host_logical_id": "3d78bc65-a11b-4c78-ab58-4b66fa45edea"}, {"new": ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "fed91523ee6aa10eeb8cdabb7b0c005062ebdb50f605b72cfb882ebe41aba0d8"], "old": null, "kind": "append", "position": 3, "host_logical_id": "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d"}, {"new": ["0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893", "53dedee3233d1a8ecd4790c7d9102cbdde4848fbc053154c2692e82e773dbf37"], "old": null, "kind": "append", "position": 4, "host_logical_id": "0f2aa0f9-ce9d-420a-8aeb-d5fe5c8aa893"}, {"new": ["2047e848-7099-4d81-a50a-9d790dd2def2", "79c3127817fe16ab0993ba16bcf3b27b75f064c250dc914fbc55a48455c28765"], "old": null, "kind": "append", "position": 5, "host_logical_id": "2047e848-7099-4d81-a50a-9d790dd2def2"}, {"new": ["f95c8265-e9d8-4dbb-b359-2da87e358cea", "4548e3c47f01e977311c3bd11cd49416e36f0454b1a69a1e2012ba757d8baf9e"], "old": null, "kind": "append", "position": 6, "host_logical_id": "f95c8265-e9d8-4dbb-b359-2da87e358cea"}, {"new": ["d382d783-d96e-4d51-bc0c-210eb2f74ea8", "72063d31aa1cd86c091920ef80c3c3bbaebf52a4cae85f21b1944c3f615fc8b0"], "old": null, "kind": "append", "position": 7, "host_logical_id": "d382d783-d96e-4d51-bc0c-210eb2f74ea8"}, {"new": ["fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c", "b8f53dc792434d3a2f4af64a860ddd3a85eb9c11a44407f42f79587cbc744b13"], "old": null, "kind": "append", "position": 8, "host_logical_id": "fcc64fb3-9b0a-4d4f-b251-282ee9ca0e3c"}, {"new": ["c7c57cf9-9ef7-47b4-8ecf-3a455ee18732", "54b55bc9335213b8d129e821c5cf1a1eeb12673aa47c8d5f5aa28836d77be9f3"], "old": null, "kind": "append", "position": 9, "host_logical_id": "c7c57cf9-9ef7-47b4-8ecf-3a455ee18732"}, {"new": ["d7757c68-9a1b-4081-9f65-7d49940bf4cd", "97c8a29f11a4420b4a7c5dddf2a42a4a0e31ccef4860dbd5e61e44d18c5b0dc7"], "old": null, "kind": "append", "position": 10, "host_logical_id": "d7757c68-9a1b-4081-9f65-7d49940bf4cd"}, {"new": ["56b05611-ddb1-4a7f-8841-51af71f8e09c", "44134fd1a7ed1cbfca1a432226061afbcdd69013fa2f89a390819422ee241c8b"], "old": null, "kind": "append", "position": 11, "host_logical_id": "56b05611-ddb1-4a7f-8841-51af71f8e09c"}, {"new": ["5d1b5d31-37c4-463e-bb57-3347fba30237", "b2751dbc4c114dfd243159e23cc2251cbbd5957edfaf1593f4df22496606961a"], "old": null, "kind": "append", "position": 12, "host_logical_id": "5d1b5d31-37c4-463e-bb57-3347fba30237"}]}', '2026-09-28 11:09:42.144425+00', '01a0e7b4-d187-750c-b9a7-f8819314ea1e');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b4-da0b-7d7a-9e9e-cb415d9c7650', 2, '01a0e7b4-d174-739f-86c1-49cc6910abe9', '{01a0e7b4-d188-7c20-9585-f19c7f5edd6c}', 'edit', '2b4765b878882a5cba7dfc3b97eabe08596b240248abee8cb2f0b59e93459a8c', '{"ops": [{"op": "replace", "to": ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "78c443c18a2119cf938ff1e9e8182f7fb6ca4ec46b35da3271bbc067f9e178b5"], "from": ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "fed91523ee6aa10eeb8cdabb7b0c005062ebdb50f605b72cfb882ebe41aba0d8"]}, {"op": "insert", "after": ["5d1b5d31-37c4-463e-bb57-3347fba30237", "b2751dbc4c114dfd243159e23cc2251cbbd5957edfaf1593f4df22496606961a"], "member": ["02cc2796-0c46-4b9e-9788-420646a4c724", "f157131b7b826caedc9f9dfb95aa634b5cce8ac3b5ca23069a041cd4b4ac8fe7"]}, {"op": "insert", "after": ["02cc2796-0c46-4b9e-9788-420646a4c724", "f157131b7b826caedc9f9dfb95aa634b5cce8ac3b5ca23069a041cd4b4ac8fe7"], "member": ["5e8f5229-c65f-4f14-bad1-03784cda34e4", "f346bdba7caf72a0c255bf0f765edbc3cf725419d2aa3d13f85f338ce6101dd4"]}, {"op": "insert", "after": ["5e8f5229-c65f-4f14-bad1-03784cda34e4", "f346bdba7caf72a0c255bf0f765edbc3cf725419d2aa3d13f85f338ce6101dd4"], "member": ["cd924214-7bd4-4e2d-acda-39b13a165021", "836932692fcb5a89b812e5e7ae93cc7f60426b59ae0fe0f28870d75683480d48"]}], "changes": [{"new": ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "78c443c18a2119cf938ff1e9e8182f7fb6ca4ec46b35da3271bbc067f9e178b5"], "old": ["b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d", "fed91523ee6aa10eeb8cdabb7b0c005062ebdb50f605b72cfb882ebe41aba0d8"], "kind": "edit", "position": 3, "host_logical_id": "b0fd89a3-fb5e-4c5a-ba1d-0e7880c5830d"}, {"new": ["02cc2796-0c46-4b9e-9788-420646a4c724", "f157131b7b826caedc9f9dfb95aa634b5cce8ac3b5ca23069a041cd4b4ac8fe7"], "old": null, "kind": "append", "position": 13, "host_logical_id": "02cc2796-0c46-4b9e-9788-420646a4c724"}, {"new": ["5e8f5229-c65f-4f14-bad1-03784cda34e4", "f346bdba7caf72a0c255bf0f765edbc3cf725419d2aa3d13f85f338ce6101dd4"], "old": null, "kind": "append", "position": 14, "host_logical_id": "5e8f5229-c65f-4f14-bad1-03784cda34e4"}, {"new": ["cd924214-7bd4-4e2d-acda-39b13a165021", "836932692fcb5a89b812e5e7ae93cc7f60426b59ae0fe0f28870d75683480d48"], "old": null, "kind": "append", "position": 15, "host_logical_id": "cd924214-7bd4-4e2d-acda-39b13a165021"}]}', '2026-09-28 11:09:44.326192+00', '01a0e7b4-da0a-7365-ab8f-90d4ff0b1532');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b4-de79-71ba-a3df-bc0f2fe48d94', 4, '01a0e7b4-de63-7415-a4c3-26661d9565f5', '{}', 'branch', 'fc6425c8854f83f5f5ac67738c103afebc59e9b3dfe199bff41ded493d4748fd', '{"ops": [{"op": "set", "members": [["216d6c4b-58bd-4a49-a40e-74bc99428d1d", "c02f6d21ba026ce5ce775cac9bac1c9d96ac94878029a9fd7450ab9c18b62701"], ["c45e6101-e4db-4a7d-84ed-870937c43445", "af76476da5f520d4f1d281cbb754b585a9ed075224241cc1bb50447a0d51e56d"], ["2c9979da-86a7-4bdd-b0db-4183ad1045f5", "c555403f910b6debaf6dcfaab2a499e81c29999710e97dd665c46df99033bcbc"], ["90690f57-62e5-47c2-abf4-70b23c8f6098", "5a09ef939d3183250d8a3abe5f5901088ab866a53a7aed122c5fa63d6dcfb006"], ["ee20569f-fd73-4a0f-ba5e-c871ee3b5199", "762b36c2d46a9bdd8721b0590fa2bc39ce67974857154a7aefc0f599dd1db85c"], ["58d4e552-4910-4439-8ee4-03f984387fbf", "445095ff1e0a24412377fd437d27ed745d5f5a833a593df92ca3ea4d5ddb1567"], ["bff5aa15-9d87-4d92-bb82-e493db0053d4", "18c5a41da549a40ea47e7dcac1d3a2987f506a02df07db889b6ed6572eef0873"], ["0486736e-d82a-41f0-9913-052693fc3cc8", "de092557697cb28b83d9b14d58758762e68c7634768121ee053b62bd5038697e"]]}], "changes": [{"new": ["216d6c4b-58bd-4a49-a40e-74bc99428d1d", "c02f6d21ba026ce5ce775cac9bac1c9d96ac94878029a9fd7450ab9c18b62701"], "old": null, "kind": "append", "position": 0, "host_logical_id": "216d6c4b-58bd-4a49-a40e-74bc99428d1d"}, {"new": ["c45e6101-e4db-4a7d-84ed-870937c43445", "af76476da5f520d4f1d281cbb754b585a9ed075224241cc1bb50447a0d51e56d"], "old": null, "kind": "append", "position": 1, "host_logical_id": "c45e6101-e4db-4a7d-84ed-870937c43445"}, {"new": ["2c9979da-86a7-4bdd-b0db-4183ad1045f5", "c555403f910b6debaf6dcfaab2a499e81c29999710e97dd665c46df99033bcbc"], "old": null, "kind": "append", "position": 2, "host_logical_id": "2c9979da-86a7-4bdd-b0db-4183ad1045f5"}, {"new": ["90690f57-62e5-47c2-abf4-70b23c8f6098", "5a09ef939d3183250d8a3abe5f5901088ab866a53a7aed122c5fa63d6dcfb006"], "old": null, "kind": "append", "position": 3, "host_logical_id": "90690f57-62e5-47c2-abf4-70b23c8f6098"}, {"new": ["ee20569f-fd73-4a0f-ba5e-c871ee3b5199", "762b36c2d46a9bdd8721b0590fa2bc39ce67974857154a7aefc0f599dd1db85c"], "old": null, "kind": "append", "position": 4, "host_logical_id": "ee20569f-fd73-4a0f-ba5e-c871ee3b5199"}, {"new": ["58d4e552-4910-4439-8ee4-03f984387fbf", "445095ff1e0a24412377fd437d27ed745d5f5a833a593df92ca3ea4d5ddb1567"], "old": null, "kind": "append", "position": 5, "host_logical_id": "58d4e552-4910-4439-8ee4-03f984387fbf"}, {"new": ["bff5aa15-9d87-4d92-bb82-e493db0053d4", "18c5a41da549a40ea47e7dcac1d3a2987f506a02df07db889b6ed6572eef0873"], "old": null, "kind": "append", "position": 6, "host_logical_id": "bff5aa15-9d87-4d92-bb82-e493db0053d4"}, {"new": ["0486736e-d82a-41f0-9913-052693fc3cc8", "de092557697cb28b83d9b14d58758762e68c7634768121ee053b62bd5038697e"], "old": null, "kind": "append", "position": 7, "host_logical_id": "0486736e-d82a-41f0-9913-052693fc3cc8"}]}', '2026-09-28 11:09:45.456499+00', '01a0e7b4-de78-794e-b7fb-fb19e51ee0ef');


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


