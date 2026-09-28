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
    IF current_setting('nmos.delete_conversation', true) IS NOT NULL
       AND current_setting('nmos.delete_conversation', true) <> ''
       AND EXISTS (SELECT 1 FROM source_object so WHERE so.id = OLD.source_object_id
                     AND so.conversation_id = current_setting('nmos.delete_conversation', true)::uuid) THEN
        RETURN OLD;
    END IF;
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
    window_hash text,
    turn integer,
    turn_hash text
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
    polarity text DEFAULT 'positive'::text NOT NULL,
    modality text DEFAULT 'actual'::text NOT NULL,
    source text,
    asserted_by text,
    salience text,
    participants jsonb,
    outcome text,
    because text,
    CONSTRAINT assertion_knowledge_check CHECK ((knowledge = ANY (ARRAY['public'::text, 'limited'::text, 'unknown'::text]))),
    CONSTRAINT assertion_modality_check CHECK ((modality = ANY (ARRAY['actual'::text, 'hypothetical'::text, 'dreamed'::text, 'unknown'::text]))),
    CONSTRAINT assertion_participants_check CHECK (((participants IS NULL) OR (jsonb_typeof(participants) = 'array'::text))),
    CONSTRAINT assertion_polarity_check CHECK ((polarity = ANY (ARRAY['positive'::text, 'negative'::text]))),
    CONSTRAINT assertion_salience_check CHECK ((salience = ANY (ARRAY['major'::text, 'minor'::text]))),
    CONSTRAINT assertion_source_check CHECK ((source = ANY (ARRAY['narration'::text, 'character_claim'::text]))),
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
    host_chat_name text,
    host_persona_name text,
    memory_strict boolean DEFAULT false NOT NULL,
    memory_narrator text,
    CONSTRAINT conversation_memory_narrator_check CHECK (((memory_narrator IS NULL) OR ((length(memory_narrator) >= 1) AND (length(memory_narrator) <= 60))))
);


--
-- Name: entity_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_link (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    entity_type text NOT NULL,
    name text NOT NULL,
    same_as text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    removed_at timestamp with time zone,
    CONSTRAINT entity_link_entity_type_check CHECK ((entity_type = ANY (ARRAY['character'::text, 'place'::text, 'item'::text, 'group'::text, 'concept'::text])))
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
    coverage jsonb,
    members uuid[],
    discarded_at timestamp with time zone,
    hints jsonb
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
-- Name: observation_base; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.observation_base (
    observation_id uuid NOT NULL,
    conversation_id uuid NOT NULL
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
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    policy text,
    budget_tokens integer,
    upto_position integer,
    previous_ai text,
    in_context jsonb,
    extractor_key text,
    embed_projection text,
    rules_version text,
    recall_options jsonb,
    lines jsonb
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
    projection text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
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
-- Name: worldline_append; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.worldline_append (
    seq bigint NOT NULL,
    commit_id uuid NOT NULL,
    ops jsonb NOT NULL,
    changes jsonb NOT NULL,
    host_observation_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: worldline_append_seq_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.worldline_append_seq_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: worldline_append_seq_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.worldline_append_seq_seq OWNED BY public.worldline_append.seq;


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
-- Name: worldline_append seq; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worldline_append ALTER COLUMN seq SET DEFAULT nextval('public.worldline_append_seq_seq'::regclass);


--
-- Data for Name: active_membership; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 0, '01a0e617-d7f8-7931-96c8-f6d039fa7a76', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 1, '01a0e617-d7fa-737b-9d1d-101b5bc3b812', NULL, 0, 'd7e8109ca7c4c5d6d0febe39cfaa8e8f');
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 2, '01a0e617-d7fb-7e12-8f2f-4356e1e78933', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 3, '01a0e617-de8a-7f35-8b3c-b593bc7a736c', NULL, 1, 'ec211dc7fbfef87fb0afac344644bd37');
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 4, '01a0e617-d830-76d9-b7f8-1463d1a0ddc9', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 5, '01a0e617-d832-72a2-b38e-d135af01d1ba', NULL, 2, '9150bf42741c20bb9320bb070c930073');
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 6, '01a0e617-d832-7691-9519-929c0119ef21', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 7, '01a0e617-d833-7821-840d-8ba8236ec730', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 8, '01a0e617-dedc-7798-a41e-f784c8039024', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 9, '01a0e617-d859-747c-8ec6-ce0b6a99cc1c', NULL, 3, 'b5d5895bd4788c59e2027a51fb826cfd');
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 10, '01a0e617-d85a-71bc-96de-cca3e70e7292', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 11, '01a0e617-d85a-73cf-9083-7aafb74667ce', NULL, 4, '309b8dfba937c32a80b9cf98b9a10fdf');
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 12, '01a0e617-d87f-7fa1-a6dc-fc5a8a493651', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 13, '01a0e617-de8b-7520-86ac-65006e933665', NULL, 5, 'bff5020e1bb7c3ec9c14e86eab177caa');
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 14, '01a0e617-de8c-7612-a0f3-2c9b75e1398b', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 15, '01a0e617-dedd-785a-b9df-54af5cf6328c', NULL, 6, 'f4b2a7dad6f32a3f7c3f3b45ba9fd5cf');
INSERT INTO public.active_membership VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 16, '01a0e617-dede-7c4f-9613-1d6b65a17b8c', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 0, '01a0e617-e4f6-7c9b-b81c-9a45371f5f4e', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 1, '01a0e617-e4f7-7fe1-b3bc-ca31191c71da', NULL, 0, 'fee271d1a6a19f4c6df82b541fe21b03');
INSERT INTO public.active_membership VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 2, '01a0e617-e4f8-7f2e-a258-2cbb6f21edf1', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 3, '01a0e617-e4f8-7f5c-8e08-b66288247f31', NULL, 1, '10ec1ef17528a1564aae39fa0cff437c');
INSERT INTO public.active_membership VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 4, '01a0e617-e4f9-7633-b7b2-f42c98885e36', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 5, '01a0e617-e4f9-7aee-b729-09bc20aee8d8', NULL, 2, '9ebe168004367417e6f519140c789f07');
INSERT INTO public.active_membership VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 6, '01a0e617-e4fa-762e-bd2b-f17c3889a9f9', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 7, '01a0e617-e4fa-70d7-a92d-2ec982b32da9', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0e617-dd85-7d24-9938-4a782a2d01c8', '01a0e617-d85a-73cf-9083-7aafb74667ce', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0e617-dd9d-7ef5-bb3b-6b824c436e6d', '01a0e617-d859-747c-8ec6-ce0b6a99cc1c', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0e617-ddc8-7017-8834-6f346c054954', '01a0e617-d832-72a2-b38e-d135af01d1ba', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0e617-dde0-74f9-b953-8adb27961eb3', '01a0e617-d7fc-76a6-8998-3f67d1548f45', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0e617-dde0-74f9-b953-8adb27961eb3', '01a0e617-d7fc-76a6-8998-3f67d1548f45', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0e617-de36-7c44-af5f-23e64a4e630a', '01a0e617-d7fa-737b-9d1d-101b5bc3b812', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0e617-de36-7c44-af5f-23e64a4e630a', '01a0e617-d7fa-737b-9d1d-101b5bc3b812', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0e617-e29e-7edf-a336-8ea9cdc30433', '01a0e617-dedd-785a-b9df-54af5cf6328c', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0e617-e2ce-7301-8999-e75942801fc3', '01a0e617-d85a-73cf-9083-7aafb74667ce', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0e617-e2e5-7519-8af3-0304b5cd139b', '01a0e617-d859-747c-8ec6-ce0b6a99cc1c', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0e617-e307-715f-9d92-fb545b0a3ca4', '01a0e617-d832-72a2-b38e-d135af01d1ba', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0e617-e31c-75d5-bdf7-7127d376f250', '01a0e617-de8a-7f35-8b3c-b593bc7a736c', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0e617-e31c-75d5-bdf7-7127d376f250', '01a0e617-de8a-7f35-8b3c-b593bc7a736c', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0e617-e7a1-7a07-83fa-f379301abb92', '01a0e617-e4f9-7aee-b729-09bc20aee8d8', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0e617-e7b6-73d5-a11f-d556a9b86139', '01a0e617-e4f8-7f5c-8e08-b66288247f31', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0e617-e7b6-73d5-a11f-d556a9b86139', '01a0e617-e4f8-7f5c-8e08-b66288247f31', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0e617-e7cd-77c5-b771-2a2062d33126', '01a0e617-e4f7-7fe1-b3bc-ca31191c71da', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0e617-e7cd-77c5-b771-2a2062d33126', '01a0e617-e4f7-7fe1-b3bc-ca31191c71da', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'pocketrisu', NULL, 'f3e85ce8-bcd1-4ec6-9737-45385b97f241', '2026-09-28 03:38:37.417141+00', NULL, NULL, NULL, '01a0e617-dee0-7ce0-81fa-b37c0c251ecc', '7cde6e0cd4a11e35940fa7953d2a963cd38efbeddc7948e700f543453957ccf2', 'Mina', 'Upgrade fixture', 'Yuuma', false, NULL);
INSERT INTO public.conversation VALUES ('01a0e617-e4e9-7af6-8a07-5e5952d0ab40', 'pocketrisu', NULL, 'b775bf3d-cc6e-46d2-a2b9-b04c2a79306b', '2026-09-28 03:38:40.745447+00', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'f3e85ce8-bcd1-4ec6-9737-45385b97f241', '136cdef8-48ea-4fde-b077-59416f6065f6', '01a0e617-e4fc-7972-8289-1c78f9fadb42', 'daafb0e14e3a5d51b5563d2319aa333a95812a55644c1e53dec2a2f6063f3e25', 'Mina', 'Upgrade fixture', 'Yuuma', false, NULL);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0e617-dd85-7d24-9938-4a782a2d01c8', '01a0e617-d85a-73cf-9083-7aafb74667ce', 'bc7f4ef56c9e73877349b02066ab6445', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:38.853418+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e617-d85a-71bc-96de-cca3e70e7292,01a0e617-d85a-73cf-9083-7aafb74667ce}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-dd9d-7ef5-bb3b-6b824c436e6d', '01a0e617-d859-747c-8ec6-ce0b6a99cc1c', 'da148d431cda4eefa41d358b8385e88a', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:38.877205+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e617-d858-74c1-8263-7854ef20bf6c,01a0e617-d859-747c-8ec6-ce0b6a99cc1c}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-ddb4-7a35-a032-5f48c4190f8a', '01a0e617-d833-7821-840d-8ba8236ec730', '4ea2ed0282d118b88c7abbf2deef0246', 'extract-v13', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 03:38:38.900421+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e617-d832-7691-9519-929c0119ef21,01a0e617-d833-7821-840d-8ba8236ec730}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-ddc8-7017-8834-6f346c054954', '01a0e617-d832-72a2-b38e-d135af01d1ba', '714d5f6fec7f67179fe412985050140f', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:38.920613+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e617-d830-76d9-b7f8-1463d1a0ddc9,01a0e617-d832-72a2-b38e-d135af01d1ba}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-dde0-74f9-b953-8adb27961eb3', '01a0e617-d7fc-76a6-8998-3f67d1548f45', '61c7fcaad386ddcd19f06cc6a4a1455a', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:38.9448+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e617-d7fb-7e12-8f2f-4356e1e78933,01a0e617-d7fc-76a6-8998-3f67d1548f45}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-de36-7c44-af5f-23e64a4e630a', '01a0e617-d7fa-737b-9d1d-101b5bc3b812', 'd7e8109ca7c4c5d6d0febe39cfaa8e8f', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:39.030826+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e617-d7f8-7931-96c8-f6d039fa7a76,01a0e617-d7fa-737b-9d1d-101b5bc3b812}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e29e-7edf-a336-8ea9cdc30433', '01a0e617-dedd-785a-b9df-54af5cf6328c', 'f4b2a7dad6f32a3f7c3f3b45ba9fd5cf', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:40.15815+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e617-de8c-7612-a0f3-2c9b75e1398b,01a0e617-dedd-785a-b9df-54af5cf6328c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e2b8-7df7-8aab-a2597050ae69', '01a0e617-de8b-7520-86ac-65006e933665', 'bff5020e1bb7c3ec9c14e86eab177caa', 'extract-v13', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 03:38:40.184321+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e617-d87f-7fa1-a6dc-fc5a8a493651,01a0e617-de8b-7520-86ac-65006e933665}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e2ce-7301-8999-e75942801fc3', '01a0e617-d85a-73cf-9083-7aafb74667ce', '309b8dfba937c32a80b9cf98b9a10fdf', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:40.206194+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e617-d85a-71bc-96de-cca3e70e7292,01a0e617-d85a-73cf-9083-7aafb74667ce}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e2e5-7519-8af3-0304b5cd139b', '01a0e617-d859-747c-8ec6-ce0b6a99cc1c', 'b5d5895bd4788c59e2027a51fb826cfd', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:40.229508+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0e617-d832-7691-9519-929c0119ef21,01a0e617-d833-7821-840d-8ba8236ec730,01a0e617-d859-747c-8ec6-ce0b6a99cc1c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e307-715f-9d92-fb545b0a3ca4', '01a0e617-d832-72a2-b38e-d135af01d1ba', '9150bf42741c20bb9320bb070c930073', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:40.263698+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e617-d830-76d9-b7f8-1463d1a0ddc9,01a0e617-d832-72a2-b38e-d135af01d1ba}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e31c-75d5-bdf7-7127d376f250', '01a0e617-de8a-7f35-8b3c-b593bc7a736c', 'ec211dc7fbfef87fb0afac344644bd37', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:40.284785+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e617-d7fb-7e12-8f2f-4356e1e78933,01a0e617-de8a-7f35-8b3c-b593bc7a736c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e7a1-7a07-83fa-f379301abb92', '01a0e617-e4f9-7aee-b729-09bc20aee8d8', '9ebe168004367417e6f519140c789f07', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:41.441349+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e617-e4f9-7633-b7b2-f42c98885e36,01a0e617-e4f9-7aee-b729-09bc20aee8d8}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e7b6-73d5-a11f-d556a9b86139', '01a0e617-e4f8-7f5c-8e08-b66288247f31', '10ec1ef17528a1564aae39fa0cff437c', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:41.462093+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e617-e4f8-7f2e-a258-2cbb6f21edf1,01a0e617-e4f8-7f5c-8e08-b66288247f31}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e617-e7cd-77c5-b771-2a2062d33126', '01a0e617-e4f7-7fe1-b3bc-ca31191c71da', 'fee271d1a6a19f4c6df82b541fe21b03', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 03:38:41.48575+00', 'extract-a702fad919c0aad808c219478f650d39', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e617-e4f6-7c9b-b81c-9a45371f5f4e,01a0e617-e4f7-7fe1-b3bc-ca31191c71da}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0e617-d7fd-7914-b89d-3973a2b6f9b2', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'manifest', 'bf88a6090c6597ab9568aecdd83b1cfe543fce64dc71ded8bfe80a95a7d14b72', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9:bf88a6090c6597ab9568aecdd83b1cfe543fce64dc71ded8bfe80a95a7d14b72:manifest', '2026-09-28 03:38:37.430972+00', '{"chat_id": "f3e85ce8-bcd1-4ec6-9737-45385b97f241", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["6a637319-8482-409a-a2a8-9ba0a1b93aac", "a68f62c44af4746c3051f9211d6a87aaa7ea5427fa21a2c8d8c54bb35618b115", "user", null, null, null, 0, null, null], ["b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", "3e7dd641a4bfbd46c89f6bc4306a3ca6425bfbd19b14cc1ca89753db27f2a1ef", "char", null, null, null, 0, "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", null], ["8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f", "eecd6f3adf1260879967cab3e35dc31595eb0623c67020534d3b1a0911b2c056", "user", null, null, null, 0, null, null], ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "ba7b959ca39ce3eae774510197c160b4ee0bc6be9e73a8f1c9d3c83930d03b2a", "char", null, null, null, 0, "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", null]]}');
INSERT INTO public.host_observation VALUES ('01a0e617-d836-7eff-b99d-8cd0701f88f7', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'manifest', '5c11b70936bee05f4b822e2b98bdf11580f2d26350294e2b5f7667e6c848ad2a', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9:5c11b70936bee05f4b822e2b98bdf11580f2d26350294e2b5f7667e6c848ad2a:manifest', '2026-09-28 03:38:37.488025+00', '{"chat_id": "f3e85ce8-bcd1-4ec6-9737-45385b97f241", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0", "d655d683d86f4a8e6c59c981e4fa98efbf233333cb58ed3689f53c807feacfdc", "user", null, null, null, 0, null, null], ["136cdef8-48ea-4fde-b077-59416f6065f6", "e499bb6e9014d9dbf935683e8af962d6fadc9bd5bb46e3676d9e70009a28ce17", "char", null, null, null, 0, "136cdef8-48ea-4fde-b077-59416f6065f6", null], ["4277d78d-5578-473b-acc2-e9744def571a", "6783f7c95be26129b4525525410670a3373bf40f6fde1ae284b8ee621d6cd20d", "user", null, null, null, 0, null, null], ["7da60303-41ff-42a4-b727-0d7afb0e9ecf", "878139bb69535d2347f01ed9ae155587ef3e4c0e18e6989bcbaa6b63807c10be", "char", null, null, null, 0, "7da60303-41ff-42a4-b727-0d7afb0e9ecf", null]], "base_manifest_hash": "bf88a6090c6597ab9568aecdd83b1cfe543fce64dc71ded8bfe80a95a7d14b72"}');
INSERT INTO public.host_observation VALUES ('01a0e617-d85d-7e9c-a622-404ed7d8f8d4', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'manifest', '1acd8766c40e1ec5e5ae2cf03b3c193c4bb8450a78ac9e5fe6e49ac87b0d307b', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9:1acd8766c40e1ec5e5ae2cf03b3c193c4bb8450a78ac9e5fe6e49ac87b0d307b:manifest', '2026-09-28 03:38:37.527734+00', '{"chat_id": "f3e85ce8-bcd1-4ec6-9737-45385b97f241", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "9a9eb4e7d26e2195a10b4cabf00fc497d92cc7e8633052a53653e42b6eac5b56", "user", null, null, null, 0, null, null], ["a69d9892-8ee5-4ca2-9480-7c8518147ddb", "ad45fdc0312a5f9d5556768a78747cdbce877983a340fd11f77a215d9f46f777", "char", null, null, null, 0, "a69d9892-8ee5-4ca2-9480-7c8518147ddb", null], ["24a7954b-6a8e-4f28-93c5-e375c83ede17", "fb4b544439795cb10a585a9a309395a99df153a797ee9ed37fa3b7556970779a", "user", null, null, null, 0, null, null], ["d23c5849-d346-4907-9411-d8274b1dca0a", "81c4c052aec9e3d9cf768c73b0f62fc6c3c7a821a857fe409e862153722c3209", "char", null, null, null, 0, "d23c5849-d346-4907-9411-d8274b1dca0a", null]], "base_manifest_hash": "5c11b70936bee05f4b822e2b98bdf11580f2d26350294e2b5f7667e6c848ad2a"}');
INSERT INTO public.host_observation VALUES ('01a0e617-d882-7490-8dd0-1b0b4633835a', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'manifest', '1dac55b60a1e0d13f1c092193404433581f0b4d3f7086b40e2896694fa9cebc2', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9:1dac55b60a1e0d13f1c092193404433581f0b4d3f7086b40e2896694fa9cebc2:manifest', '2026-09-28 03:38:37.566689+00', '{"chat_id": "f3e85ce8-bcd1-4ec6-9737-45385b97f241", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["4280930a-6e83-4262-8c73-83aa471506a4", "4c035a7527fe3c88c2b9172f0ada34dacd35afc1b84fb298c214e3c77454c9f3", "user", null, null, null, 0, null, null]], "base_manifest_hash": "1acd8766c40e1ec5e5ae2cf03b3c193c4bb8450a78ac9e5fe6e49ac87b0d307b"}');
INSERT INTO public.host_observation VALUES ('01a0e617-de8d-71f7-b977-92a34ed37a28', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'manifest', 'b78190ff4adbfbea859cf476538dd156a3b97077d7e5573332f82fcdf6055c21', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9:b78190ff4adbfbea859cf476538dd156a3b97077d7e5573332f82fcdf6055c21:manifest', '2026-09-28 03:38:39.113317+00', '{"chat_id": "f3e85ce8-bcd1-4ec6-9737-45385b97f241", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["6a637319-8482-409a-a2a8-9ba0a1b93aac", "a68f62c44af4746c3051f9211d6a87aaa7ea5427fa21a2c8d8c54bb35618b115", "user", null, null, null, 0, null, null], ["b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", "3e7dd641a4bfbd46c89f6bc4306a3ca6425bfbd19b14cc1ca89753db27f2a1ef", "char", null, null, null, 0, "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", null], ["8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f", "eecd6f3adf1260879967cab3e35dc31595eb0623c67020534d3b1a0911b2c056", "user", null, null, null, 0, null, null], ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "144c8bbdf5c652a6dc8051008d948c923df5a9cecddbe0bddb14f94c4ebf358c", "char", null, null, null, 0, "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", null], ["4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0", "d655d683d86f4a8e6c59c981e4fa98efbf233333cb58ed3689f53c807feacfdc", "user", null, null, null, 0, null, null], ["136cdef8-48ea-4fde-b077-59416f6065f6", "e499bb6e9014d9dbf935683e8af962d6fadc9bd5bb46e3676d9e70009a28ce17", "char", null, null, null, 0, "136cdef8-48ea-4fde-b077-59416f6065f6", null], ["4277d78d-5578-473b-acc2-e9744def571a", "6783f7c95be26129b4525525410670a3373bf40f6fde1ae284b8ee621d6cd20d", "user", null, null, null, 0, null, null], ["7da60303-41ff-42a4-b727-0d7afb0e9ecf", "878139bb69535d2347f01ed9ae155587ef3e4c0e18e6989bcbaa6b63807c10be", "char", null, null, null, 0, "7da60303-41ff-42a4-b727-0d7afb0e9ecf", null], ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "9a9eb4e7d26e2195a10b4cabf00fc497d92cc7e8633052a53653e42b6eac5b56", "user", null, null, null, 0, null, null], ["a69d9892-8ee5-4ca2-9480-7c8518147ddb", "ad45fdc0312a5f9d5556768a78747cdbce877983a340fd11f77a215d9f46f777", "char", null, null, null, 0, "a69d9892-8ee5-4ca2-9480-7c8518147ddb", null], ["24a7954b-6a8e-4f28-93c5-e375c83ede17", "fb4b544439795cb10a585a9a309395a99df153a797ee9ed37fa3b7556970779a", "user", null, null, null, 0, null, null], ["d23c5849-d346-4907-9411-d8274b1dca0a", "81c4c052aec9e3d9cf768c73b0f62fc6c3c7a821a857fe409e862153722c3209", "char", null, null, null, 0, "d23c5849-d346-4907-9411-d8274b1dca0a", null], ["4280930a-6e83-4262-8c73-83aa471506a4", "4c035a7527fe3c88c2b9172f0ada34dacd35afc1b84fb298c214e3c77454c9f3", "user", null, null, null, 0, null, null], ["e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "279feddf855191735005a88f4f98e5114e219d26d6bf4afffcc3129612d2a393", "char", null, null, null, 0, "e9931a97-3071-41d5-b0d2-6a4d6420b6b1", null], ["b852bba6-9524-4de2-8088-c70b6e7243eb", "f76b478c7eba0a2cab3f0287ddfc87e3bc6a8ac09ee8284fcfd42b3bfaacace7", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e617-deb6-75f3-912b-a20576416eba', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'manifest', '8668461820d5236d9a22894ba69b993217961690924d397f3231d1741ec0012c', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9:8668461820d5236d9a22894ba69b993217961690924d397f3231d1741ec0012c:manifest', '2026-09-28 03:38:39.154644+00', '{"chat_id": "f3e85ce8-bcd1-4ec6-9737-45385b97f241", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "251a05ef78dbdb97a3c9a9ed753d78c5234d2b72b1f883d6db21f3e75a605f2b", "char", null, null, 1, 2, "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", null]], "base_manifest_hash": "b78190ff4adbfbea859cf476538dd156a3b97077d7e5573332f82fcdf6055c21"}');
INSERT INTO public.host_observation VALUES ('01a0e617-dedf-771b-bb7a-3920883683db', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'manifest', '7cde6e0cd4a11e35940fa7953d2a963cd38efbeddc7948e700f543453957ccf2', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9:7cde6e0cd4a11e35940fa7953d2a963cd38efbeddc7948e700f543453957ccf2:manifest', '2026-09-28 03:38:39.195834+00', '{"chat_id": "f3e85ce8-bcd1-4ec6-9737-45385b97f241", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["6a637319-8482-409a-a2a8-9ba0a1b93aac", "a68f62c44af4746c3051f9211d6a87aaa7ea5427fa21a2c8d8c54bb35618b115", "user", null, null, null, 0, null, null], ["b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", "3e7dd641a4bfbd46c89f6bc4306a3ca6425bfbd19b14cc1ca89753db27f2a1ef", "char", null, null, null, 0, "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", null], ["8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f", "eecd6f3adf1260879967cab3e35dc31595eb0623c67020534d3b1a0911b2c056", "user", null, null, null, 0, null, null], ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "144c8bbdf5c652a6dc8051008d948c923df5a9cecddbe0bddb14f94c4ebf358c", "char", null, null, null, 0, "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", null], ["4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0", "d655d683d86f4a8e6c59c981e4fa98efbf233333cb58ed3689f53c807feacfdc", "user", null, null, null, 0, null, null], ["136cdef8-48ea-4fde-b077-59416f6065f6", "e499bb6e9014d9dbf935683e8af962d6fadc9bd5bb46e3676d9e70009a28ce17", "char", null, null, null, 0, "136cdef8-48ea-4fde-b077-59416f6065f6", null], ["4277d78d-5578-473b-acc2-e9744def571a", "6783f7c95be26129b4525525410670a3373bf40f6fde1ae284b8ee621d6cd20d", "user", null, null, null, 0, null, null], ["7da60303-41ff-42a4-b727-0d7afb0e9ecf", "878139bb69535d2347f01ed9ae155587ef3e4c0e18e6989bcbaa6b63807c10be", "char", null, null, null, 0, "7da60303-41ff-42a4-b727-0d7afb0e9ecf", null], ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "1d07b1e2204f7b21d2794ba0e6d68e893c3c18e2d52c0abc6942ebcdbc0070b3", "user", true, null, null, 0, null, null], ["a69d9892-8ee5-4ca2-9480-7c8518147ddb", "ad45fdc0312a5f9d5556768a78747cdbce877983a340fd11f77a215d9f46f777", "char", null, null, null, 0, "a69d9892-8ee5-4ca2-9480-7c8518147ddb", null], ["24a7954b-6a8e-4f28-93c5-e375c83ede17", "fb4b544439795cb10a585a9a309395a99df153a797ee9ed37fa3b7556970779a", "user", null, null, null, 0, null, null], ["d23c5849-d346-4907-9411-d8274b1dca0a", "81c4c052aec9e3d9cf768c73b0f62fc6c3c7a821a857fe409e862153722c3209", "char", null, null, null, 0, "d23c5849-d346-4907-9411-d8274b1dca0a", null], ["4280930a-6e83-4262-8c73-83aa471506a4", "4c035a7527fe3c88c2b9172f0ada34dacd35afc1b84fb298c214e3c77454c9f3", "user", null, null, null, 0, null, null], ["e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "279feddf855191735005a88f4f98e5114e219d26d6bf4afffcc3129612d2a393", "char", null, null, null, 0, "e9931a97-3071-41d5-b0d2-6a4d6420b6b1", null], ["b852bba6-9524-4de2-8088-c70b6e7243eb", "f76b478c7eba0a2cab3f0287ddfc87e3bc6a8ac09ee8284fcfd42b3bfaacace7", "user", null, null, null, 0, null, null], ["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "998dbc7d609db829153e8cedc4d2e6fcbfdb826d9b7835e71ec1c8d166e56a7d", "char", null, null, 0, 2, "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", null], ["bbd16d3b-3710-47f2-bf07-999c3c026ccd", "730ee5d2b76df128da8ed81765162ac42f7e26d8de6149fbcbcb4e1363320571", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e617-e4fb-7409-bfff-993dfcc8d20e', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', 'manifest', 'daafb0e14e3a5d51b5563d2319aa333a95812a55644c1e53dec2a2f6063f3e25', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40:daafb0e14e3a5d51b5563d2319aa333a95812a55644c1e53dec2a2f6063f3e25:manifest', '2026-09-28 03:38:40.75805+00', '{"chat_id": "b775bf3d-cc6e-46d2-a2b9-b04c2a79306b", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["9bad5655-e7ee-44a0-998a-ac8bab8a2854", "aa7a3e4283d01a011478f698d61f9ccec58f1b39ceac37580e814778dfbb3e32", "user", null, null, null, 0, null, null], ["c1d7206f-4506-437f-a188-416018f11c79", "de2249d95ec723114155c93b321faf63fcd821dbefb01fe2b61eed7d96b91750", "char", null, null, null, 0, "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", null], ["b3c1c683-3085-4c6e-b29e-96d8342ea7dd", "38ad21fe14e9e4a47f3c3d04a27d45694fa46d67103d29fa2b342dcf208b18f8", "user", null, null, null, 0, null, null], ["d2b7a957-6364-4df2-8697-0b20f87655cd", "c2d7008c5719bbf7f3619f0501deb6c36ccb32ba65bcfa0a5af41f729bc1694e", "char", null, null, null, 0, "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", null], ["85768dd5-1af8-44bb-8c84-0cbf61a30fac", "4a5f3b4799d3fd67248860760fb1556c7d9fc047152895b64b40cb26e0423a09", "user", null, null, null, 0, null, null], ["0cf8df41-b935-4abe-83f7-420f8f1ecce6", "928a9d374d665d916c156a4d49d7d118262e853668ce3c924cdffbf1567b9ead", "char", null, null, null, 0, "136cdef8-48ea-4fde-b077-59416f6065f6", null], ["75e725c5-95f6-439d-ac4d-09d43191cb30", "ddb7776d67383e72ce254957f0faf1cd10b654fdffcf107504c6a817cf0f1062", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::f3e85ce8-bcd1-4ec6-9737-45385b97f241::Harbor route::136cdef8-48ea-4fde-b077-59416f6065f6::}}"]], ["661f618f-ebc1-43e1-9c6d-ae21f437d1c8", "5e0640dbcbd873aca05d3a37900822483c05b9e2a861228ad7652160d0ae7de0", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0e617-d87f-7fa1-a6dc-fc5a8a493651:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d87f-7fa1-a6dc-fc5a8a493651"}', 50, 'done', 1, '2026-09-28 03:38:37.566689+00', NULL, NULL, '2026-09-28 03:38:37.566689+00', '2026-09-28 03:38:38.640022+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0e617-d85a-73cf-9083-7aafb74667ce:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d85a-73cf-9083-7aafb74667ce"}', 50, 'done', 1, '2026-09-28 03:38:37.566689+00', NULL, NULL, '2026-09-28 03:38:37.566689+00', '2026-09-28 03:38:38.660698+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0e617-d85a-71bc-96de-cca3e70e7292:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d85a-71bc-96de-cca3e70e7292"}', 50, 'done', 1, '2026-09-28 03:38:37.527734+00', NULL, NULL, '2026-09-28 03:38:37.527734+00', '2026-09-28 03:38:38.680809+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0e617-d859-747c-8ec6-ce0b6a99cc1c:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c"}', 50, 'done', 1, '2026-09-28 03:38:37.527734+00', NULL, NULL, '2026-09-28 03:38:37.527734+00', '2026-09-28 03:38:38.70287+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0e617-d858-74c1-8263-7854ef20bf6c:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d858-74c1-8263-7854ef20bf6c"}', 50, 'done', 1, '2026-09-28 03:38:37.527734+00', NULL, NULL, '2026-09-28 03:38:37.527734+00', '2026-09-28 03:38:38.726166+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0e617-d833-7821-840d-8ba8236ec730:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d833-7821-840d-8ba8236ec730"}', 50, 'done', 1, '2026-09-28 03:38:37.527734+00', NULL, NULL, '2026-09-28 03:38:37.527734+00', '2026-09-28 03:38:38.746128+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0e617-d832-7691-9519-929c0119ef21:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d832-7691-9519-929c0119ef21"}', 50, 'done', 1, '2026-09-28 03:38:37.488025+00', NULL, NULL, '2026-09-28 03:38:37.488025+00', '2026-09-28 03:38:38.764951+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0e617-d832-72a2-b38e-d135af01d1ba:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d832-72a2-b38e-d135af01d1ba"}', 50, 'done', 1, '2026-09-28 03:38:37.488025+00', NULL, NULL, '2026-09-28 03:38:37.488025+00', '2026-09-28 03:38:38.784539+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0e617-d830-76d9-b7f8-1463d1a0ddc9:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d830-76d9-b7f8-1463d1a0ddc9"}', 50, 'done', 1, '2026-09-28 03:38:37.488025+00', NULL, NULL, '2026-09-28 03:38:37.488025+00', '2026-09-28 03:38:38.804865+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0e617-d7fc-76a6-8998-3f67d1548f45:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d7fc-76a6-8998-3f67d1548f45"}', 50, 'done', 1, '2026-09-28 03:38:37.488025+00', NULL, NULL, '2026-09-28 03:38:37.488025+00', '2026-09-28 03:38:38.82644+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0e617-d85a-73cf-9083-7aafb74667ce:bc7f4ef56c9e73877349b02066ab6445:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d85a-73cf-9083-7aafb74667ce", "window_hash": "bc7f4ef56c9e73877349b02066ab6445"}', 100, 'done', 1, '2026-09-28 03:38:37.566689+00', NULL, NULL, '2026-09-28 03:38:37.566689+00', '2026-09-28 03:38:38.856146+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0e617-d859-747c-8ec6-ce0b6a99cc1c:da148d431cda4eefa41d358b8385e88a:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c", "window_hash": "da148d431cda4eefa41d358b8385e88a"}', 100, 'done', 1, '2026-09-28 03:38:37.527734+00', NULL, NULL, '2026-09-28 03:38:37.527734+00', '2026-09-28 03:38:38.879378+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0e617-d833-7821-840d-8ba8236ec730:4ea2ed0282d118b88c7abbf2deef0246:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d833-7821-840d-8ba8236ec730", "window_hash": "4ea2ed0282d118b88c7abbf2deef0246"}', 100, 'done', 1, '2026-09-28 03:38:37.527734+00', NULL, NULL, '2026-09-28 03:38:37.527734+00', '2026-09-28 03:38:38.90197+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0e617-d832-72a2-b38e-d135af01d1ba:714d5f6fec7f67179fe412985050140f:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d832-72a2-b38e-d135af01d1ba", "window_hash": "714d5f6fec7f67179fe412985050140f"}', 100, 'done', 1, '2026-09-28 03:38:37.488025+00', NULL, NULL, '2026-09-28 03:38:37.488025+00', '2026-09-28 03:38:38.922521+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0e617-d7fc-76a6-8998-3f67d1548f45:61c7fcaad386ddcd19f06cc6a4a1455a:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d7fc-76a6-8998-3f67d1548f45", "window_hash": "61c7fcaad386ddcd19f06cc6a4a1455a"}', 100, 'done', 1, '2026-09-28 03:38:37.488025+00', NULL, NULL, '2026-09-28 03:38:37.488025+00', '2026-09-28 03:38:38.947034+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0e617-d7fb-7e12-8f2f-4356e1e78933:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d7fb-7e12-8f2f-4356e1e78933"}', 150, 'done', 1, '2026-09-28 03:38:37.430972+00', NULL, NULL, '2026-09-28 03:38:37.430972+00', '2026-09-28 03:38:38.968219+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0e617-d7fa-737b-9d1d-101b5bc3b812:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d7fa-737b-9d1d-101b5bc3b812"}', 150, 'done', 1, '2026-09-28 03:38:37.430972+00', NULL, NULL, '2026-09-28 03:38:37.430972+00', '2026-09-28 03:38:38.988122+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0e617-d7f8-7931-96c8-f6d039fa7a76:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-d7f8-7931-96c8-f6d039fa7a76"}', 150, 'done', 1, '2026-09-28 03:38:37.430972+00', NULL, NULL, '2026-09-28 03:38:37.430972+00', '2026-09-28 03:38:39.009948+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0e617-d7fa-737b-9d1d-101b5bc3b812:d7e8109ca7c4c5d6d0febe39cfaa8e8f:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d7fa-737b-9d1d-101b5bc3b812", "window_hash": "d7e8109ca7c4c5d6d0febe39cfaa8e8f"}', 200, 'done', 1, '2026-09-28 03:38:37.430972+00', NULL, NULL, '2026-09-28 03:38:37.430972+00', '2026-09-28 03:38:39.033255+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0e617-d832-72a2-b38e-d135af01d1ba:9150bf42741c20bb9320bb070c930073:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d832-72a2-b38e-d135af01d1ba", "window_hash": "9150bf42741c20bb9320bb070c930073"}', 100, 'done', 1, '2026-09-28 03:38:39.113317+00', NULL, NULL, '2026-09-28 03:38:39.113317+00', '2026-09-28 03:38:40.265707+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0e617-de8a-7f35-8b3c-b593bc7a736c:ec211dc7fbfef87fb0afac344644bd37:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-de8a-7f35-8b3c-b593bc7a736c", "window_hash": "ec211dc7fbfef87fb0afac344644bd37"}', 100, 'done', 1, '2026-09-28 03:38:39.113317+00', NULL, NULL, '2026-09-28 03:38:39.113317+00', '2026-09-28 03:38:40.286748+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0e617-e4f9-7633-b7b2-f42c98885e36:embed-3611f434158007b791964d34e76302a5', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-e4f9-7633-b7b2-f42c98885e36"}', 150, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.344185+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0e617-dede-7c4f-9613-1d6b65a17b8c:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-dede-7c4f-9613-1d6b65a17b8c"}', 50, 'done', 1, '2026-09-28 03:38:39.195834+00', NULL, NULL, '2026-09-28 03:38:39.195834+00', '2026-09-28 03:38:40.059909+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0e617-dedd-785a-b9df-54af5cf6328c:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-dedd-785a-b9df-54af5cf6328c"}', 50, 'done', 1, '2026-09-28 03:38:39.195834+00', NULL, NULL, '2026-09-28 03:38:39.195834+00', '2026-09-28 03:38:40.08156+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0e617-de8c-7612-a0f3-2c9b75e1398b:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-de8c-7612-a0f3-2c9b75e1398b"}', 50, 'done', 1, '2026-09-28 03:38:39.113317+00', NULL, NULL, '2026-09-28 03:38:39.113317+00', '2026-09-28 03:38:40.100399+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0e617-de8b-7520-86ac-65006e933665:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-de8b-7520-86ac-65006e933665"}', 50, 'done', 1, '2026-09-28 03:38:39.113317+00', NULL, NULL, '2026-09-28 03:38:39.113317+00', '2026-09-28 03:38:40.119342+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0e617-de8a-7f35-8b3c-b593bc7a736c:embed-3611f434158007b791964d34e76302a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-de8a-7f35-8b3c-b593bc7a736c"}', 50, 'done', 1, '2026-09-28 03:38:39.113317+00', NULL, NULL, '2026-09-28 03:38:39.113317+00', '2026-09-28 03:38:40.137895+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0e617-dedd-785a-b9df-54af5cf6328c:f4b2a7dad6f32a3f7c3f3b45ba9fd5cf:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-dedd-785a-b9df-54af5cf6328c", "window_hash": "f4b2a7dad6f32a3f7c3f3b45ba9fd5cf"}', 100, 'done', 1, '2026-09-28 03:38:39.195834+00', NULL, NULL, '2026-09-28 03:38:39.195834+00', '2026-09-28 03:38:40.159963+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0e617-de8b-7520-86ac-65006e933665:bff5020e1bb7c3ec9c14e86eab177caa:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-de8b-7520-86ac-65006e933665", "window_hash": "bff5020e1bb7c3ec9c14e86eab177caa"}', 100, 'done', 1, '2026-09-28 03:38:39.195834+00', NULL, NULL, '2026-09-28 03:38:39.195834+00', '2026-09-28 03:38:40.185934+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0e617-d85a-73cf-9083-7aafb74667ce:309b8dfba937c32a80b9cf98b9a10fdf:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d85a-73cf-9083-7aafb74667ce", "window_hash": "309b8dfba937c32a80b9cf98b9a10fdf"}', 100, 'done', 1, '2026-09-28 03:38:39.195834+00', NULL, NULL, '2026-09-28 03:38:39.195834+00', '2026-09-28 03:38:40.208019+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0e617-d859-747c-8ec6-ce0b6a99cc1c:b5d5895bd4788c59e2027a51fb826cfd:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c", "window_hash": "b5d5895bd4788c59e2027a51fb826cfd"}', 100, 'done', 1, '2026-09-28 03:38:39.195834+00', NULL, NULL, '2026-09-28 03:38:39.195834+00', '2026-09-28 03:38:40.231351+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0e617-de8b-7520-86ac-65006e933665:a0f20a7d0b7041b207b5861deb61a065:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-de8b-7520-86ac-65006e933665", "window_hash": "a0f20a7d0b7041b207b5861deb61a065"}', 100, 'obsolete', 1, '2026-09-28 03:38:39.113317+00', NULL, NULL, '2026-09-28 03:38:39.113317+00', '2026-09-28 03:38:40.235341+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0e617-d859-747c-8ec6-ce0b6a99cc1c:31653c43b43f8725adbbe390b2c649b4:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c", "window_hash": "31653c43b43f8725adbbe390b2c649b4"}', 100, 'obsolete', 1, '2026-09-28 03:38:39.113317+00', NULL, NULL, '2026-09-28 03:38:39.113317+00', '2026-09-28 03:38:40.238967+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0e617-d833-7821-840d-8ba8236ec730:4925df8295fb9ee9cfe93a4e08f6bbd7:extract-a702fad919c0aad808c219478f650d39', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-d833-7821-840d-8ba8236ec730", "window_hash": "4925df8295fb9ee9cfe93a4e08f6bbd7"}', 100, 'obsolete', 1, '2026-09-28 03:38:39.113317+00', NULL, NULL, '2026-09-28 03:38:39.113317+00', '2026-09-28 03:38:40.242483+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0e617-e4f9-7aee-b729-09bc20aee8d8:embed-3611f434158007b791964d34e76302a5', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-e4f9-7aee-b729-09bc20aee8d8"}', 150, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.324903+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0e617-e4f8-7f5c-8e08-b66288247f31:embed-3611f434158007b791964d34e76302a5', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-e4f8-7f5c-8e08-b66288247f31"}', 150, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.365605+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0e617-e4f8-7f2e-a258-2cbb6f21edf1:embed-3611f434158007b791964d34e76302a5', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-e4f8-7f2e-a258-2cbb6f21edf1"}', 150, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.383719+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0e617-e4f7-7fe1-b3bc-ca31191c71da:embed-3611f434158007b791964d34e76302a5', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-e4f7-7fe1-b3bc-ca31191c71da"}', 150, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.402615+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0e617-e4f6-7c9b-b81c-9a45371f5f4e:embed-3611f434158007b791964d34e76302a5', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-e4f6-7c9b-b81c-9a45371f5f4e"}', 150, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.421426+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0e617-e4f9-7aee-b729-09bc20aee8d8:9ebe168004367417e6f519140c789f07:extract-a702fad919c0aad808c219478f650d39', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-e4f9-7aee-b729-09bc20aee8d8", "window_hash": "9ebe168004367417e6f519140c789f07"}', 200, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.443121+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0e617-e4f8-7f5c-8e08-b66288247f31:10ec1ef17528a1564aae39fa0cff437c:extract-a702fad919c0aad808c219478f650d39', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-e4f8-7f5c-8e08-b66288247f31", "window_hash": "10ec1ef17528a1564aae39fa0cff437c"}', 200, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.466731+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0e617-e4f7-7fe1-b3bc-ca31191c71da:fee271d1a6a19f4c6df82b541fe21b03:extract-a702fad919c0aad808c219478f650d39', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "extract-a702fad919c0aad808c219478f650d39", "revision_id": "01a0e617-e4f7-7fe1-b3bc-ca31191c71da", "window_hash": "fee271d1a6a19f4c6df82b541fe21b03"}', 200, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.487704+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0e617-e4fa-70d7-a92d-2ec982b32da9:embed-3611f434158007b791964d34e76302a5', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{"generation": "embed-3611f434158007b791964d34e76302a5", "revision_id": "01a0e617-e4fa-70d7-a92d-2ec982b32da9"}', 150, 'done', 1, '2026-09-28 03:38:40.75805+00', NULL, NULL, '2026-09-28 03:38:40.75805+00', '2026-09-28 03:38:41.306465+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0e617-d7fd-7914-b89d-3973a2b6f9b2', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-a702fad919c0aad808c219478f650d39', 'extract', 'stub', 'http://127.0.0.1:33251/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "a0de52e41b72df2c", "compiler": "extract-v13", "endpoint": "http://127.0.0.1:33251/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "a6511d2d7b4e2fca", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-28 03:38:37.282407+00', '2026-09-28 03:38:37.283583+00');
INSERT INTO public.projection_generation VALUES ('embed-3611f434158007b791964d34e76302a5', 'embed', 'stub-embed', 'http://127.0.0.1:33251/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:33251/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-28 03:38:37.282407+00', '2026-09-28 03:38:37.287287+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0e617-d825-7124-82f4-36088e76e4b7', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '01a0e617-d7fe-7fb0-bb71-6079ee0e37de', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e617-d7fb-7e12-8f2f-4356e1e78933", "host_logical_id": "8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e617-d7fb-7e12-8f2f-4356e1e78933", "host_logical_id": "8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f"}]', 0, '{"fit": 0.0, "embed": 23.11, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 1.99, "fits_at": null, "lexical": 3.44, "threads": 0, "extractor": "extract-a702fad919c0", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 32.55, "embedding_projection": "embed-3611f434158007", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 03:38:37.445363+00', 'packet-v6', 600, 3, '', '["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "6a637319-8482-409a-a2a8-9ba0a1b93aac", "8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f", "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7"]', 'extract-a702fad919c0aad808c219478f650d39', 'embed-3611f434158007b791964d34e76302a5', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e617-d84f-706c-afd2-d913adbd0557', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '01a0e617-d7fe-7fb0-bb71-6079ee0e37de', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e617-d832-7691-9519-929c0119ef21", "host_logical_id": "4277d78d-5578-473b-acc2-e9744def571a"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e617-d832-7691-9519-929c0119ef21", "host_logical_id": "4277d78d-5578-473b-acc2-e9744def571a"}]', 0, '{"fit": 0.0, "embed": 13.78, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 0.78, "fits_at": null, "lexical": 2.15, "threads": 0, "extractor": "extract-a702fad919c0", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.03, "embedding_projection": "embed-3611f434158007", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 03:38:37.500419+00', 'packet-v6', 600, 7, '', '["136cdef8-48ea-4fde-b077-59416f6065f6", "4277d78d-5578-473b-acc2-e9744def571a", "4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0", "7da60303-41ff-42a4-b727-0d7afb0e9ecf"]', 'extract-a702fad919c0aad808c219478f650d39', 'embed-3611f434158007b791964d34e76302a5', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e617-d876-7127-ab37-d251d048cf8a', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '01a0e617-d7fe-7fb0-bb71-6079ee0e37de', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e617-d85a-71bc-96de-cca3e70e7292", "host_logical_id": "24a7954b-6a8e-4f28-93c5-e375c83ede17"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e617-d85a-71bc-96de-cca3e70e7292", "host_logical_id": "24a7954b-6a8e-4f28-93c5-e375c83ede17"}]', 0, '{"fit": 0.0, "embed": 13.61, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 0.74, "fits_at": null, "lexical": 2.53, "threads": 0, "extractor": "extract-a702fad919c0", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.04, "embedding_projection": "embed-3611f434158007", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 03:38:37.539565+00', 'packet-v6', 600, 11, '', '["24a7954b-6a8e-4f28-93c5-e375c83ede17", "4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "a69d9892-8ee5-4ca2-9480-7c8518147ddb", "d23c5849-d346-4907-9411-d8274b1dca0a"]', 'extract-a702fad919c0aad808c219478f650d39', 'embed-3611f434158007b791964d34e76302a5', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e617-d899-763d-af03-7f12f696c68d', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '01a0e617-d7fe-7fb0-bb71-6079ee0e37de', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e617-d87f-7fa1-a6dc-fc5a8a493651", "host_logical_id": "4280930a-6e83-4262-8c73-83aa471506a4"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0e617-d7fc-76a6-8998-3f67d1548f45", "host_logical_id": "6a2beaa3-e607-44ae-bc76-fe0574ef24ba"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0e617-d7fa-737b-9d1d-101b5bc3b812", "host_logical_id": "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0e617-d7fa-737b-9d1d-101b5bc3b812"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e617-d7fc-76a6-8998-3f67d1548f45"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e617-d87f-7fa1-a6dc-fc5a8a493651", "host_logical_id": "4280930a-6e83-4262-8c73-83aa471506a4"}]', 174, '{"fit": 0.0, "embed": 13.1, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 0.74, "fits_at": null, "lexical": 2.35, "threads": 0, "extractor": "extract-a702fad919c0", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 18.54, "embedding_projection": "embed-3611f434158007", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 03:38:37.574962+00', 'packet-v6', 600, 12, '', '["24a7954b-6a8e-4f28-93c5-e375c83ede17", "4280930a-6e83-4262-8c73-83aa471506a4", "a69d9892-8ee5-4ca2-9480-7c8518147ddb", "d23c5849-d346-4907-9411-d8274b1dca0a"]', 'extract-a702fad919c0aad808c219478f650d39', 'embed-3611f434158007b791964d34e76302a5', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e617-d7fc-76a6-8998-3f67d1548f45"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 3, "placed": true}, {"ref": {"revision": "01a0e617-d7fa-737b-9d1d-101b5bc3b812"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e617-dea8-70ab-bf7d-c607a238810b', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '01a0e617-de8f-7113-9662-6c70260dbf6d', 'And the compass?', '[{"rrf": 0.03151, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c", "host_logical_id": "a69d9892-8ee5-4ca2-9480-7c8518147ddb"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e617-de8c-7612-a0f3-2c9b75e1398b", "host_logical_id": "b852bba6-9524-4de2-8088-c70b6e7243eb"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0e617-d7fa-737b-9d1d-101b5bc3b812", "host_logical_id": "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0e617-d7f8-7931-96c8-f6d039fa7a76", "host_logical_id": "6a637319-8482-409a-a2a8-9ba0a1b93aac"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0e617-d833-7821-840d-8ba8236ec730", "host_logical_id": "7da60303-41ff-42a4-b727-0d7afb0e9ecf"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0e617-d7f8-7931-96c8-f6d039fa7a76"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0e617-d7fa-737b-9d1d-101b5bc3b812"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0e617-d833-7821-840d-8ba8236ec730"}, {"turn": 9, "score": 0.03151, "revision_id": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e617-de8c-7612-a0f3-2c9b75e1398b", "host_logical_id": "b852bba6-9524-4de2-8088-c70b6e7243eb"}]', 223, '{"fit": 0.0, "embed": 13.78, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 4}, "vector": 0.93, "fits_at": null, "lexical": 2.33, "threads": 0, "extractor": "extract-a702fad919c0", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.88, "embedding_projection": "embed-3611f434158007", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 03:38:39.124674+00', 'packet-v6', 600, 14, '', '["4280930a-6e83-4262-8c73-83aa471506a4", "b852bba6-9524-4de2-8088-c70b6e7243eb", "d23c5849-d346-4907-9411-d8274b1dca0a", "e9931a97-3071-41d5-b0d2-6a4d6420b6b1"]', 'extract-a702fad919c0aad808c219478f650d39', 'embed-3611f434158007b791964d34e76302a5', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e617-d7fa-737b-9d1d-101b5bc3b812"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}, {"ref": {"revision": "01a0e617-d7f8-7931-96c8-f6d039fa7a76"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a0e617-d833-7821-840d-8ba8236ec730"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 7, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e617-ded0-7fe8-9f37-983c9b543cf7', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '01a0e617-de8f-7113-9662-6c70260dbf6d', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c", "host_logical_id": "a69d9892-8ee5-4ca2-9480-7c8518147ddb"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e617-de8c-7612-a0f3-2c9b75e1398b", "host_logical_id": "b852bba6-9524-4de2-8088-c70b6e7243eb"}, {"rrf": 0.01639, "sim": 0.5799, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0e617-d832-72a2-b38e-d135af01d1ba", "host_logical_id": "136cdef8-48ea-4fde-b077-59416f6065f6"}, {"rrf": 0.01613, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0e617-d85a-73cf-9083-7aafb74667ce", "host_logical_id": "d23c5849-d346-4907-9411-d8274b1dca0a"}]', '[{"turn": 5, "score": 0.01639, "revision_id": "01a0e617-d832-72a2-b38e-d135af01d1ba"}, {"turn": 9, "score": 0.03002, "revision_id": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c"}, {"turn": 11, "score": 0.01613, "revision_id": "01a0e617-d85a-73cf-9083-7aafb74667ce"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e617-de8c-7612-a0f3-2c9b75e1398b", "host_logical_id": "b852bba6-9524-4de2-8088-c70b6e7243eb"}]', 200, '{"fit": 0.0, "embed": 13.87, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 3}, "vector": 1.01, "fits_at": null, "lexical": 3.33, "threads": 0, "extractor": "extract-a702fad919c0", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 21.57, "embedding_projection": "embed-3611f434158007", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 03:38:39.163408+00', 'packet-v6', 600, 15, '', '["4280930a-6e83-4262-8c73-83aa471506a4", "b852bba6-9524-4de2-8088-c70b6e7243eb", "e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6"]', 'extract-a702fad919c0aad808c219478f650d39', 'embed-3611f434158007b791964d34e76302a5', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e617-d859-747c-8ec6-ce0b6a99cc1c"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e617-d832-72a2-b38e-d135af01d1ba"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Yuuma to return before the bell rings.", "turn": 5, "placed": true}, {"ref": {"revision": "01a0e617-d85a-73cf-9083-7aafb74667ce"}, "tok": 24, "why": "placed", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 11, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e617-defd-7a87-aefa-8aa3ee2e12f9', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0e617-d832-7691-9519-929c0119ef21", "host_logical_id": "4277d78d-5578-473b-acc2-e9744def571a"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e617-dede-7c4f-9613-1d6b65a17b8c", "host_logical_id": "bbd16d3b-3710-47f2-bf07-999c3c026ccd"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0e617-d832-7691-9519-929c0119ef21"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e617-dede-7c4f-9613-1d6b65a17b8c", "host_logical_id": "bbd16d3b-3710-47f2-bf07-999c3c026ccd"}]', 138, '{"fit": 0.0, "embed": 18.03, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1}, "vector": 1.01, "fits_at": null, "lexical": 2.02, "threads": 0, "extractor": "extract-a702fad919c0", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 23.29, "embedding_projection": "embed-3611f434158007", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 03:38:39.206439+00', 'packet-v6', 600, 16, '', '["b852bba6-9524-4de2-8088-c70b6e7243eb", "bbd16d3b-3710-47f2-bf07-999c3c026ccd", "e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6"]', 'extract-a702fad919c0aad808c219478f650d39', 'embed-3611f434158007b791964d34e76302a5', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e617-d832-7691-9519-929c0119ef21"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 6, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e617-e51a-7c59-92fa-a0221fd2dbe3', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '01a0e617-e4fc-7972-8289-1c78f9fadb42', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0e617-e4f8-7f2e-a258-2cbb6f21edf1", "host_logical_id": "b3c1c683-3085-4c6e-b29e-96d8342ea7dd"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0e617-e4f8-7f5c-8e08-b66288247f31", "host_logical_id": "d2b7a957-6364-4df2-8697-0b20f87655cd"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0e617-e4f8-7f2e-a258-2cbb6f21edf1"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e617-e4f8-7f5c-8e08-b66288247f31"}]', '[]', 164, '{"fit": 0.0, "embed": 18.99, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 0.94, "fits_at": null, "lexical": 3.08, "threads": 0, "extractor": "extract-a702fad919c0", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 25.48, "embedding_projection": "embed-3611f434158007", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 03:38:40.769549+00', 'packet-v6', 600, 7, '', '["0cf8df41-b935-4abe-83f7-420f8f1ecce6", "661f618f-ebc1-43e1-9c6d-ae21f437d1c8", "75e725c5-95f6-439d-ac4d-09d43191cb30", "85768dd5-1af8-44bb-8c84-0cbf61a30fac"]', 'extract-a702fad919c0aad808c219478f650d39', 'embed-3611f434158007b791964d34e76302a5', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e617-e4f8-7f2e-a258-2cbb6f21edf1"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 2, "placed": true}, {"ref": {"revision": "01a0e617-e4f8-7f5c-8e08-b66288247f31"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 3, "placed": true}]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0e617-d87f-7fa1-a6dc-fc5a8a493651', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.63723+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d85a-73cf-9083-7aafb74667ce', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.659236+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d85a-71bc-96de-cca3e70e7292', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.679404+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d859-747c-8ec6-ce0b6a99cc1c', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.700536+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d858-74c1-8263-7854ef20bf6c', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.72467+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d833-7821-840d-8ba8236ec730', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.74469+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d832-7691-9519-929c0119ef21', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.763605+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d832-72a2-b38e-d135af01d1ba', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.783044+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d830-76d9-b7f8-1463d1a0ddc9', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.803364+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d7fc-76a6-8998-3f67d1548f45', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.824918+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d7fb-7e12-8f2f-4356e1e78933', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.966687+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d7fa-737b-9d1d-101b5bc3b812', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:38.986606+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-d7f8-7931-96c8-f6d039fa7a76', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:39.008274+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-dede-7c4f-9613-1d6b65a17b8c', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:40.058339+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-dedd-785a-b9df-54af5cf6328c', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:40.07749+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-de8c-7612-a0f3-2c9b75e1398b', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:40.098894+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-de8b-7520-86ac-65006e933665', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:40.117881+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-de8a-7f35-8b3c-b593bc7a736c', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:40.136349+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-e4fa-70d7-a92d-2ec982b32da9', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:41.305005+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-e4f9-7aee-b729-09bc20aee8d8', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:41.323556+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-e4f9-7633-b7b2-f42c98885e36', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:41.342756+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-e4f8-7f5c-8e08-b66288247f31', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:41.364122+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-e4f8-7f2e-a258-2cbb6f21edf1', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:41.382285+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-e4f7-7fe1-b3bc-ca31191c71da', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:41.401211+00');
INSERT INTO public.revision_embedding VALUES ('01a0e617-e4f6-7c9b-b81c-9a45371f5f4e', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-3611f434158007b791964d34e76302a5', '2026-09-28 03:38:41.420063+00');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0e617-d7f8-7931-96c8-f6d039fa7a76', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-28 03:38:37.430972+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d7fa-737b-9d1d-101b5bc3b812', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 03:38:37.430972+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d7fb-7e12-8f2f-4356e1e78933', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-28 03:38:37.430972+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d7fc-76a6-8998-3f67d1548f45', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-28 03:38:37.430972+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d830-76d9-b7f8-1463d1a0ddc9', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-28 03:38:37.488025+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d832-72a2-b38e-d135af01d1ba', 'clean-v3', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-28 03:38:37.488025+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d832-7691-9519-929c0119ef21', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-09-28 03:38:37.488025+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d833-7821-840d-8ba8236ec730', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-28 03:38:37.488025+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d858-74c1-8263-7854ef20bf6c', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-28 03:38:37.527734+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d859-747c-8ec6-ce0b6a99cc1c', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-28 03:38:37.527734+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d85a-71bc-96de-cca3e70e7292', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-09-28 03:38:37.527734+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d85a-73cf-9083-7aafb74667ce', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-09-28 03:38:37.527734+00');
INSERT INTO public.revision_text VALUES ('01a0e617-d87f-7fa1-a6dc-fc5a8a493651', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-09-28 03:38:37.566689+00');
INSERT INTO public.revision_text VALUES ('01a0e617-de8a-7f35-8b3c-b593bc7a736c', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 03:38:39.113317+00');
INSERT INTO public.revision_text VALUES ('01a0e617-de8b-7520-86ac-65006e933665', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-09-28 03:38:39.113317+00');
INSERT INTO public.revision_text VALUES ('01a0e617-de8c-7612-a0f3-2c9b75e1398b', 'clean-v3', 'And the compass?', 16, 16, '2026-09-28 03:38:39.113317+00');
INSERT INTO public.revision_text VALUES ('01a0e617-deb3-727b-853f-8631e83b054a', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-28 03:38:39.154644+00');
INSERT INTO public.revision_text VALUES ('01a0e617-dedc-7798-a41e-f784c8039024', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-28 03:38:39.195834+00');
INSERT INTO public.revision_text VALUES ('01a0e617-dedd-785a-b9df-54af5cf6328c', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-09-28 03:38:39.195834+00');
INSERT INTO public.revision_text VALUES ('01a0e617-dede-7c4f-9613-1d6b65a17b8c', 'clean-v3', 'Let''s go.', 9, 9, '2026-09-28 03:38:39.195834+00');
INSERT INTO public.revision_text VALUES ('01a0e617-e4f6-7c9b-b81c-9a45371f5f4e', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-28 03:38:40.75805+00');
INSERT INTO public.revision_text VALUES ('01a0e617-e4f7-7fe1-b3bc-ca31191c71da', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 03:38:40.75805+00');
INSERT INTO public.revision_text VALUES ('01a0e617-e4f8-7f2e-a258-2cbb6f21edf1', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-28 03:38:40.75805+00');
INSERT INTO public.revision_text VALUES ('01a0e617-e4f8-7f5c-8e08-b66288247f31', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 03:38:40.75805+00');
INSERT INTO public.revision_text VALUES ('01a0e617-e4f9-7633-b7b2-f42c98885e36', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-28 03:38:40.75805+00');
INSERT INTO public.revision_text VALUES ('01a0e617-e4f9-7aee-b729-09bc20aee8d8', 'clean-v3', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-28 03:38:40.75805+00');
INSERT INTO public.revision_text VALUES ('01a0e617-e4fa-762e-bd2b-f17c3889a9f9', 'clean-v3', '{{specialcomment::branchedfrom::f3e85ce8-bcd1-4ec6-9737-45385b97f241::Harbor route::136cdef8-48ea-4fde-b077-59416f6065f6::}}', 124, 124, '2026-09-28 03:38:40.75805+00');
INSERT INTO public.revision_text VALUES ('01a0e617-e4fa-70d7-a92d-2ec982b32da9', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-09-28 03:38:40.75805+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-28 03:38:36.481872+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-28 03:38:36.566891+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-28 03:38:36.582371+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-28 03:38:36.625686+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-28 03:38:36.646492+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-28 03:38:36.655294+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-28 03:38:36.657252+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-28 03:38:36.667446+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-28 03:38:36.685516+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-28 03:38:36.687623+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-28 03:38:36.689253+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-28 03:38:36.698459+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-28 03:38:36.725039+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-28 03:38:36.741349+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-28 03:38:36.744407+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-28 03:38:36.756957+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-28 03:38:36.758744+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-28 03:38:36.760791+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-09-28 03:38:36.762799+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-09-28 03:38:36.776283+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-09-28 03:38:36.778562+00');
INSERT INTO public.schema_migrations VALUES ('0022_thread_outcome_and_cause.sql', '9a8507f1b42457d2c44d568a2bd60d868f923613f8c83acb2be7f9104041cc88', '2026-09-28 03:38:36.780589+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0e617-d7f7-7463-bdfa-b849858d09a5', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '6a637319-8482-409a-a2a8-9ba0a1b93aac', 'message', '2026-09-28 03:38:37.430972+00');
INSERT INTO public.source_object VALUES ('01a0e617-d7f9-75d7-91ac-553703f67c33', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'b0c30074-bf15-4fc6-bc88-6b17dc3f17b7', 'message', '2026-09-28 03:38:37.430972+00');
INSERT INTO public.source_object VALUES ('01a0e617-d7fa-7f70-a4ec-178ccc34f7e2', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f', 'message', '2026-09-28 03:38:37.430972+00');
INSERT INTO public.source_object VALUES ('01a0e617-d7fb-7195-b81c-4c06eb22ff26', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '6a2beaa3-e607-44ae-bc76-fe0574ef24ba', 'message', '2026-09-28 03:38:37.430972+00');
INSERT INTO public.source_object VALUES ('01a0e617-d830-7ac9-a7a6-2ddcbea5cba4', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0', 'message', '2026-09-28 03:38:37.488025+00');
INSERT INTO public.source_object VALUES ('01a0e617-d831-73f5-8c86-ce2d0a1348da', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '136cdef8-48ea-4fde-b077-59416f6065f6', 'message', '2026-09-28 03:38:37.488025+00');
INSERT INTO public.source_object VALUES ('01a0e617-d832-7ac9-be41-171a10ef66c3', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '4277d78d-5578-473b-acc2-e9744def571a', 'message', '2026-09-28 03:38:37.488025+00');
INSERT INTO public.source_object VALUES ('01a0e617-d833-7f42-98c8-d71d80fc6048', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '7da60303-41ff-42a4-b727-0d7afb0e9ecf', 'message', '2026-09-28 03:38:37.488025+00');
INSERT INTO public.source_object VALUES ('01a0e617-d858-7aad-bf71-2968593d03f9', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '4a3eaae5-f8a7-42b9-bcad-b63995d8650b', 'message', '2026-09-28 03:38:37.527734+00');
INSERT INTO public.source_object VALUES ('01a0e617-d859-7136-93d6-fe46ccbf7aed', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'a69d9892-8ee5-4ca2-9480-7c8518147ddb', 'message', '2026-09-28 03:38:37.527734+00');
INSERT INTO public.source_object VALUES ('01a0e617-d859-720a-b223-1ded739f54bb', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '24a7954b-6a8e-4f28-93c5-e375c83ede17', 'message', '2026-09-28 03:38:37.527734+00');
INSERT INTO public.source_object VALUES ('01a0e617-d85a-79d7-b34f-a4def850c1f2', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'd23c5849-d346-4907-9411-d8274b1dca0a', 'message', '2026-09-28 03:38:37.527734+00');
INSERT INTO public.source_object VALUES ('01a0e617-d87f-78e6-9c81-1a64aece0cf8', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '4280930a-6e83-4262-8c73-83aa471506a4', 'message', '2026-09-28 03:38:37.566689+00');
INSERT INTO public.source_object VALUES ('01a0e617-de8a-746e-b8f1-353d90969a21', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'e9931a97-3071-41d5-b0d2-6a4d6420b6b1', 'message', '2026-09-28 03:38:39.113317+00');
INSERT INTO public.source_object VALUES ('01a0e617-de8b-7173-8990-3af2ecdf45fd', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'b852bba6-9524-4de2-8088-c70b6e7243eb', 'message', '2026-09-28 03:38:39.113317+00');
INSERT INTO public.source_object VALUES ('01a0e617-deb3-733d-a484-cc8ba4ae169e', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'f51867ea-6a23-4aae-b3f2-f398bd2b3dc6', 'message', '2026-09-28 03:38:39.154644+00');
INSERT INTO public.source_object VALUES ('01a0e617-dedd-7759-84db-f3b42985ac28', '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', 'bbd16d3b-3710-47f2-bf07-999c3c026ccd', 'message', '2026-09-28 03:38:39.195834+00');
INSERT INTO public.source_object VALUES ('01a0e617-e4f6-7954-9c32-fef7c80b9119', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '9bad5655-e7ee-44a0-998a-ac8bab8a2854', 'message', '2026-09-28 03:38:40.75805+00');
INSERT INTO public.source_object VALUES ('01a0e617-e4f7-7b44-b44c-2a2adeadc56f', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', 'c1d7206f-4506-437f-a188-416018f11c79', 'message', '2026-09-28 03:38:40.75805+00');
INSERT INTO public.source_object VALUES ('01a0e617-e4f7-7c0d-8b13-167d81e09d9d', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', 'b3c1c683-3085-4c6e-b29e-96d8342ea7dd', 'message', '2026-09-28 03:38:40.75805+00');
INSERT INTO public.source_object VALUES ('01a0e617-e4f8-75b4-af7f-7959354ec6a1', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', 'd2b7a957-6364-4df2-8697-0b20f87655cd', 'message', '2026-09-28 03:38:40.75805+00');
INSERT INTO public.source_object VALUES ('01a0e617-e4f8-7b03-8507-63f651759faf', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '85768dd5-1af8-44bb-8c84-0cbf61a30fac', 'message', '2026-09-28 03:38:40.75805+00');
INSERT INTO public.source_object VALUES ('01a0e617-e4f9-7014-aab0-43e967acc583', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '0cf8df41-b935-4abe-83f7-420f8f1ecce6', 'message', '2026-09-28 03:38:40.75805+00');
INSERT INTO public.source_object VALUES ('01a0e617-e4f9-7c29-8337-fed44ae5019d', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '75e725c5-95f6-439d-ac4d-09d43191cb30', 'message', '2026-09-28 03:38:40.75805+00');
INSERT INTO public.source_object VALUES ('01a0e617-e4fa-7d3e-97b4-926b76a67419', '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '661f618f-ebc1-43e1-9c6d-ae21f437d1c8', 'message', '2026-09-28 03:38:40.75805+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0e617-d7f8-7931-96c8-f6d039fa7a76', '01a0e617-d7f7-7463-bdfa-b849858d09a5', 'a68f62c44af4746c3051f9211d6a87aaa7ea5427fa21a2c8d8c54bb35618b115', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "6a637319-8482-409a-a2a8-9ba0a1b93aac", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:37.430972+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d7fb-7e12-8f2f-4356e1e78933', '01a0e617-d7fa-7f70-a4ec-178ccc34f7e2', 'eecd6f3adf1260879967cab3e35dc31595eb0623c67020534d3b1a0911b2c056', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:37.430972+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d7fa-737b-9d1d-101b5bc3b812', '01a0e617-d7f9-75d7-91ac-553703f67c33', '3e7dd641a4bfbd46c89f6bc4306a3ca6425bfbd19b14cc1ca89753db27f2a1ef', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", "specialComments": []}', '2026-09-28 03:38:37.430972+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d830-76d9-b7f8-1463d1a0ddc9', '01a0e617-d830-7ac9-a7a6-2ddcbea5cba4', 'd655d683d86f4a8e6c59c981e4fa98efbf233333cb58ed3689f53c807feacfdc', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:37.488025+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d832-7691-9519-929c0119ef21', '01a0e617-d832-7ac9-be41-171a10ef66c3', '6783f7c95be26129b4525525410670a3373bf40f6fde1ae284b8ee621d6cd20d', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "4277d78d-5578-473b-acc2-e9744def571a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:37.488025+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d832-72a2-b38e-d135af01d1ba', '01a0e617-d831-73f5-8c86-ce2d0a1348da', 'e499bb6e9014d9dbf935683e8af962d6fadc9bd5bb46e3676d9e70009a28ce17', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "136cdef8-48ea-4fde-b077-59416f6065f6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "136cdef8-48ea-4fde-b077-59416f6065f6", "specialComments": []}', '2026-09-28 03:38:37.488025+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d858-74c1-8263-7854ef20bf6c', '01a0e617-d858-7aad-bf71-2968593d03f9', '9a9eb4e7d26e2195a10b4cabf00fc497d92cc7e8633052a53653e42b6eac5b56', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:37.527734+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d85a-71bc-96de-cca3e70e7292', '01a0e617-d859-720a-b223-1ded739f54bb', 'fb4b544439795cb10a585a9a309395a99df153a797ee9ed37fa3b7556970779a', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "24a7954b-6a8e-4f28-93c5-e375c83ede17", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:37.527734+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d833-7821-840d-8ba8236ec730', '01a0e617-d833-7f42-98c8-d71d80fc6048', '878139bb69535d2347f01ed9ae155587ef3e4c0e18e6989bcbaa6b63807c10be', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "7da60303-41ff-42a4-b727-0d7afb0e9ecf", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "7da60303-41ff-42a4-b727-0d7afb0e9ecf", "specialComments": []}', '2026-09-28 03:38:37.488025+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d859-747c-8ec6-ce0b6a99cc1c', '01a0e617-d859-7136-93d6-fe46ccbf7aed', 'ad45fdc0312a5f9d5556768a78747cdbce877983a340fd11f77a215d9f46f777', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "a69d9892-8ee5-4ca2-9480-7c8518147ddb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a69d9892-8ee5-4ca2-9480-7c8518147ddb", "specialComments": []}', '2026-09-28 03:38:37.527734+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d87f-7fa1-a6dc-fc5a8a493651', '01a0e617-d87f-78e6-9c81-1a64aece0cf8', '4c035a7527fe3c88c2b9172f0ada34dacd35afc1b84fb298c214e3c77454c9f3', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "4280930a-6e83-4262-8c73-83aa471506a4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:37.566689+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d85a-73cf-9083-7aafb74667ce', '01a0e617-d85a-79d7-b34f-a4def850c1f2', '81c4c052aec9e3d9cf768c73b0f62fc6c3c7a821a857fe409e862153722c3209', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "d23c5849-d346-4907-9411-d8274b1dca0a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "d23c5849-d346-4907-9411-d8274b1dca0a", "specialComments": []}', '2026-09-28 03:38:37.527734+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-de8c-7612-a0f3-2c9b75e1398b', '01a0e617-de8b-7173-8990-3af2ecdf45fd', 'f76b478c7eba0a2cab3f0287ddfc87e3bc6a8ac09ee8284fcfd42b3bfaacace7', 'And the compass?', '{"name": null, "role": "user", "chatId": "b852bba6-9524-4de2-8088-c70b6e7243eb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:39.113317+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-de8a-7f35-8b3c-b593bc7a736c', '01a0e617-d7fb-7195-b81c-4c06eb22ff26', '144c8bbdf5c652a6dc8051008d948c923df5a9cecddbe0bddb14f94c4ebf358c', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "specialComments": []}', '2026-09-28 03:38:39.113317+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-d7fc-76a6-8998-3f67d1548f45', '01a0e617-d7fb-7195-b81c-4c06eb22ff26', 'ba7b959ca39ce3eae774510197c160b4ee0bc6be9e73a8f1c9d3c83930d03b2a', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "specialComments": []}', '2026-09-28 03:38:37.430972+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-de8b-7520-86ac-65006e933665', '01a0e617-de8a-746e-b8f1-353d90969a21', '279feddf855191735005a88f4f98e5114e219d26d6bf4afffcc3129612d2a393', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "specialComments": []}', '2026-09-28 03:38:39.113317+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-dedc-7798-a41e-f784c8039024', '01a0e617-d858-7aad-bf71-2968593d03f9', '1d07b1e2204f7b21d2794ba0e6d68e893c3c18e2d52c0abc6942ebcdbc0070b3', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:39.195834+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-dede-7c4f-9613-1d6b65a17b8c', '01a0e617-dedd-7759-84db-f3b42985ac28', '730ee5d2b76df128da8ed81765162ac42f7e26d8de6149fbcbcb4e1363320571', 'Let''s go.', '{"name": null, "role": "user", "chatId": "bbd16d3b-3710-47f2-bf07-999c3c026ccd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:39.195834+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-deb3-727b-853f-8631e83b054a', '01a0e617-deb3-733d-a484-cc8ba4ae169e', '251a05ef78dbdb97a3c9a9ed753d78c5234d2b72b1f883d6db21f3e75a605f2b', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "specialComments": []}', '2026-09-28 03:38:39.154644+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-dedd-785a-b9df-54af5cf6328c', '01a0e617-deb3-733d-a484-cc8ba4ae169e', '998dbc7d609db829153e8cedc4d2e6fcbfdb826d9b7835e71ec1c8d166e56a7d', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "specialComments": []}', '2026-09-28 03:38:39.195834+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-e4f6-7c9b-b81c-9a45371f5f4e', '01a0e617-e4f6-7954-9c32-fef7c80b9119', 'aa7a3e4283d01a011478f698d61f9ccec58f1b39ceac37580e814778dfbb3e32', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "9bad5655-e7ee-44a0-998a-ac8bab8a2854", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:40.75805+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-e4f8-7f2e-a258-2cbb6f21edf1', '01a0e617-e4f7-7c0d-8b13-167d81e09d9d', '38ad21fe14e9e4a47f3c3d04a27d45694fa46d67103d29fa2b342dcf208b18f8', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "b3c1c683-3085-4c6e-b29e-96d8342ea7dd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:40.75805+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-e4f9-7633-b7b2-f42c98885e36', '01a0e617-e4f8-7b03-8507-63f651759faf', '4a5f3b4799d3fd67248860760fb1556c7d9fc047152895b64b40cb26e0423a09', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "85768dd5-1af8-44bb-8c84-0cbf61a30fac", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:40.75805+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-e4fa-762e-bd2b-f17c3889a9f9', '01a0e617-e4f9-7c29-8337-fed44ae5019d', 'ddb7776d67383e72ce254957f0faf1cd10b654fdffcf107504c6a817cf0f1062', '{{specialcomment::branchedfrom::f3e85ce8-bcd1-4ec6-9737-45385b97f241::Harbor route::136cdef8-48ea-4fde-b077-59416f6065f6::}}', '{"name": null, "role": "char", "chatId": "75e725c5-95f6-439d-ac4d-09d43191cb30", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::f3e85ce8-bcd1-4ec6-9737-45385b97f241::Harbor route::136cdef8-48ea-4fde-b077-59416f6065f6::}}"]}', '2026-09-28 03:38:40.75805+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-e4fa-70d7-a92d-2ec982b32da9', '01a0e617-e4fa-7d3e-97b4-926b76a67419', '5e0640dbcbd873aca05d3a37900822483c05b9e2a861228ad7652160d0ae7de0', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "661f618f-ebc1-43e1-9c6d-ae21f437d1c8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 03:38:40.75805+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-e4f9-7aee-b729-09bc20aee8d8', '01a0e617-e4f9-7014-aab0-43e967acc583', '928a9d374d665d916c156a4d49d7d118262e853668ce3c924cdffbf1567b9ead', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "0cf8df41-b935-4abe-83f7-420f8f1ecce6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "136cdef8-48ea-4fde-b077-59416f6065f6", "specialComments": []}', '2026-09-28 03:38:40.75805+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-e4f7-7fe1-b3bc-ca31191c71da', '01a0e617-e4f7-7b44-b44c-2a2adeadc56f', 'de2249d95ec723114155c93b321faf63fcd821dbefb01fe2b61eed7d96b91750', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "c1d7206f-4506-437f-a188-416018f11c79", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", "specialComments": []}', '2026-09-28 03:38:40.75805+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e617-e4f8-7f5c-8e08-b66288247f31', '01a0e617-e4f8-75b4-af7f-7959354ec6a1', 'c2d7008c5719bbf7f3619f0501deb6c36ccb32ba65bcfa0a5af41f729bc1694e', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "d2b7a957-6364-4df2-8697-0b20f87655cd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "specialComments": []}', '2026-09-28 03:38:40.75805+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0e617-d7fe-7fb0-bb71-6079ee0e37de', '[{"op": "insert", "after": ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "ba7b959ca39ce3eae774510197c160b4ee0bc6be9e73a8f1c9d3c83930d03b2a"], "member": ["4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0", "d655d683d86f4a8e6c59c981e4fa98efbf233333cb58ed3689f53c807feacfdc"]}, {"op": "insert", "after": ["4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0", "d655d683d86f4a8e6c59c981e4fa98efbf233333cb58ed3689f53c807feacfdc"], "member": ["136cdef8-48ea-4fde-b077-59416f6065f6", "e499bb6e9014d9dbf935683e8af962d6fadc9bd5bb46e3676d9e70009a28ce17"]}, {"op": "insert", "after": ["136cdef8-48ea-4fde-b077-59416f6065f6", "e499bb6e9014d9dbf935683e8af962d6fadc9bd5bb46e3676d9e70009a28ce17"], "member": ["4277d78d-5578-473b-acc2-e9744def571a", "6783f7c95be26129b4525525410670a3373bf40f6fde1ae284b8ee621d6cd20d"]}, {"op": "insert", "after": ["4277d78d-5578-473b-acc2-e9744def571a", "6783f7c95be26129b4525525410670a3373bf40f6fde1ae284b8ee621d6cd20d"], "member": ["7da60303-41ff-42a4-b727-0d7afb0e9ecf", "878139bb69535d2347f01ed9ae155587ef3e4c0e18e6989bcbaa6b63807c10be"]}]', '[{"new": ["4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0", "d655d683d86f4a8e6c59c981e4fa98efbf233333cb58ed3689f53c807feacfdc"], "old": null, "kind": "append", "position": 4, "host_logical_id": "4dfdcaac-3ee1-4e96-b7b9-3bb491c2d9b0"}, {"new": ["136cdef8-48ea-4fde-b077-59416f6065f6", "e499bb6e9014d9dbf935683e8af962d6fadc9bd5bb46e3676d9e70009a28ce17"], "old": null, "kind": "append", "position": 5, "host_logical_id": "136cdef8-48ea-4fde-b077-59416f6065f6"}, {"new": ["4277d78d-5578-473b-acc2-e9744def571a", "6783f7c95be26129b4525525410670a3373bf40f6fde1ae284b8ee621d6cd20d"], "old": null, "kind": "append", "position": 6, "host_logical_id": "4277d78d-5578-473b-acc2-e9744def571a"}, {"new": ["7da60303-41ff-42a4-b727-0d7afb0e9ecf", "878139bb69535d2347f01ed9ae155587ef3e4c0e18e6989bcbaa6b63807c10be"], "old": null, "kind": "append", "position": 7, "host_logical_id": "7da60303-41ff-42a4-b727-0d7afb0e9ecf"}]', '01a0e617-d836-7eff-b99d-8cd0701f88f7', '2026-09-28 03:38:37.488025+00');
INSERT INTO public.worldline_append VALUES (2, '01a0e617-d7fe-7fb0-bb71-6079ee0e37de', '[{"op": "insert", "after": ["7da60303-41ff-42a4-b727-0d7afb0e9ecf", "878139bb69535d2347f01ed9ae155587ef3e4c0e18e6989bcbaa6b63807c10be"], "member": ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "9a9eb4e7d26e2195a10b4cabf00fc497d92cc7e8633052a53653e42b6eac5b56"]}, {"op": "insert", "after": ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "9a9eb4e7d26e2195a10b4cabf00fc497d92cc7e8633052a53653e42b6eac5b56"], "member": ["a69d9892-8ee5-4ca2-9480-7c8518147ddb", "ad45fdc0312a5f9d5556768a78747cdbce877983a340fd11f77a215d9f46f777"]}, {"op": "insert", "after": ["a69d9892-8ee5-4ca2-9480-7c8518147ddb", "ad45fdc0312a5f9d5556768a78747cdbce877983a340fd11f77a215d9f46f777"], "member": ["24a7954b-6a8e-4f28-93c5-e375c83ede17", "fb4b544439795cb10a585a9a309395a99df153a797ee9ed37fa3b7556970779a"]}, {"op": "insert", "after": ["24a7954b-6a8e-4f28-93c5-e375c83ede17", "fb4b544439795cb10a585a9a309395a99df153a797ee9ed37fa3b7556970779a"], "member": ["d23c5849-d346-4907-9411-d8274b1dca0a", "81c4c052aec9e3d9cf768c73b0f62fc6c3c7a821a857fe409e862153722c3209"]}]', '[{"new": ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "9a9eb4e7d26e2195a10b4cabf00fc497d92cc7e8633052a53653e42b6eac5b56"], "old": null, "kind": "append", "position": 8, "host_logical_id": "4a3eaae5-f8a7-42b9-bcad-b63995d8650b"}, {"new": ["a69d9892-8ee5-4ca2-9480-7c8518147ddb", "ad45fdc0312a5f9d5556768a78747cdbce877983a340fd11f77a215d9f46f777"], "old": null, "kind": "append", "position": 9, "host_logical_id": "a69d9892-8ee5-4ca2-9480-7c8518147ddb"}, {"new": ["24a7954b-6a8e-4f28-93c5-e375c83ede17", "fb4b544439795cb10a585a9a309395a99df153a797ee9ed37fa3b7556970779a"], "old": null, "kind": "append", "position": 10, "host_logical_id": "24a7954b-6a8e-4f28-93c5-e375c83ede17"}, {"new": ["d23c5849-d346-4907-9411-d8274b1dca0a", "81c4c052aec9e3d9cf768c73b0f62fc6c3c7a821a857fe409e862153722c3209"], "old": null, "kind": "append", "position": 11, "host_logical_id": "d23c5849-d346-4907-9411-d8274b1dca0a"}]', '01a0e617-d85d-7e9c-a622-404ed7d8f8d4', '2026-09-28 03:38:37.527734+00');
INSERT INTO public.worldline_append VALUES (3, '01a0e617-d7fe-7fb0-bb71-6079ee0e37de', '[{"op": "insert", "after": ["d23c5849-d346-4907-9411-d8274b1dca0a", "81c4c052aec9e3d9cf768c73b0f62fc6c3c7a821a857fe409e862153722c3209"], "member": ["4280930a-6e83-4262-8c73-83aa471506a4", "4c035a7527fe3c88c2b9172f0ada34dacd35afc1b84fb298c214e3c77454c9f3"]}]', '[{"new": ["4280930a-6e83-4262-8c73-83aa471506a4", "4c035a7527fe3c88c2b9172f0ada34dacd35afc1b84fb298c214e3c77454c9f3"], "old": null, "kind": "append", "position": 12, "host_logical_id": "4280930a-6e83-4262-8c73-83aa471506a4"}]', '01a0e617-d882-7490-8dd0-1b0b4633835a', '2026-09-28 03:38:37.566689+00');
INSERT INTO public.worldline_append VALUES (4, '01a0e617-de8f-7113-9662-6c70260dbf6d', '[{"op": "insert", "after": ["b852bba6-9524-4de2-8088-c70b6e7243eb", "f76b478c7eba0a2cab3f0287ddfc87e3bc6a8ac09ee8284fcfd42b3bfaacace7"], "member": ["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "251a05ef78dbdb97a3c9a9ed753d78c5234d2b72b1f883d6db21f3e75a605f2b"]}]', '[{"new": ["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "251a05ef78dbdb97a3c9a9ed753d78c5234d2b72b1f883d6db21f3e75a605f2b"], "old": null, "kind": "append", "position": 15, "host_logical_id": "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6"}]', '01a0e617-deb6-75f3-912b-a20576416eba', '2026-09-28 03:38:39.154644+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e617-d7fe-7fb0-bb71-6079ee0e37de', 1, '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{}', 'import', 'bf88a6090c6597ab9568aecdd83b1cfe543fce64dc71ded8bfe80a95a7d14b72', '{"ops": [{"op": "set", "members": [["6a637319-8482-409a-a2a8-9ba0a1b93aac", "a68f62c44af4746c3051f9211d6a87aaa7ea5427fa21a2c8d8c54bb35618b115"], ["b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", "3e7dd641a4bfbd46c89f6bc4306a3ca6425bfbd19b14cc1ca89753db27f2a1ef"], ["8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f", "eecd6f3adf1260879967cab3e35dc31595eb0623c67020534d3b1a0911b2c056"], ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "ba7b959ca39ce3eae774510197c160b4ee0bc6be9e73a8f1c9d3c83930d03b2a"]]}], "changes": [{"new": ["6a637319-8482-409a-a2a8-9ba0a1b93aac", "a68f62c44af4746c3051f9211d6a87aaa7ea5427fa21a2c8d8c54bb35618b115"], "old": null, "kind": "append", "position": 0, "host_logical_id": "6a637319-8482-409a-a2a8-9ba0a1b93aac"}, {"new": ["b0c30074-bf15-4fc6-bc88-6b17dc3f17b7", "3e7dd641a4bfbd46c89f6bc4306a3ca6425bfbd19b14cc1ca89753db27f2a1ef"], "old": null, "kind": "append", "position": 1, "host_logical_id": "b0c30074-bf15-4fc6-bc88-6b17dc3f17b7"}, {"new": ["8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f", "eecd6f3adf1260879967cab3e35dc31595eb0623c67020534d3b1a0911b2c056"], "old": null, "kind": "append", "position": 2, "host_logical_id": "8e11041e-9bdd-4ec1-b4e1-e1e1cf95469f"}, {"new": ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "ba7b959ca39ce3eae774510197c160b4ee0bc6be9e73a8f1c9d3c83930d03b2a"], "old": null, "kind": "append", "position": 3, "host_logical_id": "6a2beaa3-e607-44ae-bc76-fe0574ef24ba"}]}', '2026-09-28 03:38:37.430972+00', '01a0e617-d7fd-7914-b89d-3973a2b6f9b2');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e617-de8f-7113-9662-6c70260dbf6d', 2, '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{01a0e617-d7fe-7fb0-bb71-6079ee0e37de}', 'edit', 'b78190ff4adbfbea859cf476538dd156a3b97077d7e5573332f82fcdf6055c21', '{"ops": [{"op": "replace", "to": ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "144c8bbdf5c652a6dc8051008d948c923df5a9cecddbe0bddb14f94c4ebf358c"], "from": ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "ba7b959ca39ce3eae774510197c160b4ee0bc6be9e73a8f1c9d3c83930d03b2a"]}, {"op": "insert", "after": ["4280930a-6e83-4262-8c73-83aa471506a4", "4c035a7527fe3c88c2b9172f0ada34dacd35afc1b84fb298c214e3c77454c9f3"], "member": ["e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "279feddf855191735005a88f4f98e5114e219d26d6bf4afffcc3129612d2a393"]}, {"op": "insert", "after": ["e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "279feddf855191735005a88f4f98e5114e219d26d6bf4afffcc3129612d2a393"], "member": ["b852bba6-9524-4de2-8088-c70b6e7243eb", "f76b478c7eba0a2cab3f0287ddfc87e3bc6a8ac09ee8284fcfd42b3bfaacace7"]}], "changes": [{"new": ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "144c8bbdf5c652a6dc8051008d948c923df5a9cecddbe0bddb14f94c4ebf358c"], "old": ["6a2beaa3-e607-44ae-bc76-fe0574ef24ba", "ba7b959ca39ce3eae774510197c160b4ee0bc6be9e73a8f1c9d3c83930d03b2a"], "kind": "edit", "position": 3, "host_logical_id": "6a2beaa3-e607-44ae-bc76-fe0574ef24ba"}, {"new": ["e9931a97-3071-41d5-b0d2-6a4d6420b6b1", "279feddf855191735005a88f4f98e5114e219d26d6bf4afffcc3129612d2a393"], "old": null, "kind": "append", "position": 13, "host_logical_id": "e9931a97-3071-41d5-b0d2-6a4d6420b6b1"}, {"new": ["b852bba6-9524-4de2-8088-c70b6e7243eb", "f76b478c7eba0a2cab3f0287ddfc87e3bc6a8ac09ee8284fcfd42b3bfaacace7"], "old": null, "kind": "append", "position": 14, "host_logical_id": "b852bba6-9524-4de2-8088-c70b6e7243eb"}]}', '2026-09-28 03:38:39.113317+00', '01a0e617-de8d-71f7-b977-92a34ed37a28');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e617-dee0-7ce0-81fa-b37c0c251ecc', 3, '01a0e617-d7e9-7a20-ad9c-4fd34e9b8ae9', '{01a0e617-de8f-7113-9662-6c70260dbf6d}', 'reconciliation', '7cde6e0cd4a11e35940fa7953d2a963cd38efbeddc7948e700f543453957ccf2', '{"ops": [{"op": "replace", "to": ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "1d07b1e2204f7b21d2794ba0e6d68e893c3c18e2d52c0abc6942ebcdbc0070b3"], "from": ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "9a9eb4e7d26e2195a10b4cabf00fc497d92cc7e8633052a53653e42b6eac5b56"]}, {"op": "replace", "to": ["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "998dbc7d609db829153e8cedc4d2e6fcbfdb826d9b7835e71ec1c8d166e56a7d"], "from": ["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "251a05ef78dbdb97a3c9a9ed753d78c5234d2b72b1f883d6db21f3e75a605f2b"]}, {"op": "insert", "after": ["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "998dbc7d609db829153e8cedc4d2e6fcbfdb826d9b7835e71ec1c8d166e56a7d"], "member": ["bbd16d3b-3710-47f2-bf07-999c3c026ccd", "730ee5d2b76df128da8ed81765162ac42f7e26d8de6149fbcbcb4e1363320571"]}], "changes": [{"new": ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "1d07b1e2204f7b21d2794ba0e6d68e893c3c18e2d52c0abc6942ebcdbc0070b3"], "old": ["4a3eaae5-f8a7-42b9-bcad-b63995d8650b", "9a9eb4e7d26e2195a10b4cabf00fc497d92cc7e8633052a53653e42b6eac5b56"], "kind": "disable", "position": 8, "host_logical_id": "4a3eaae5-f8a7-42b9-bcad-b63995d8650b"}, {"new": ["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "998dbc7d609db829153e8cedc4d2e6fcbfdb826d9b7835e71ec1c8d166e56a7d"], "old": ["f51867ea-6a23-4aae-b3f2-f398bd2b3dc6", "251a05ef78dbdb97a3c9a9ed753d78c5234d2b72b1f883d6db21f3e75a605f2b"], "kind": "swipe", "position": 15, "host_logical_id": "f51867ea-6a23-4aae-b3f2-f398bd2b3dc6"}, {"new": ["bbd16d3b-3710-47f2-bf07-999c3c026ccd", "730ee5d2b76df128da8ed81765162ac42f7e26d8de6149fbcbcb4e1363320571"], "old": null, "kind": "append", "position": 16, "host_logical_id": "bbd16d3b-3710-47f2-bf07-999c3c026ccd"}]}', '2026-09-28 03:38:39.195834+00', '01a0e617-dedf-771b-bb7a-3920883683db');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e617-e4fc-7972-8289-1c78f9fadb42', 4, '01a0e617-e4e9-7af6-8a07-5e5952d0ab40', '{}', 'branch', 'daafb0e14e3a5d51b5563d2319aa333a95812a55644c1e53dec2a2f6063f3e25', '{"ops": [{"op": "set", "members": [["9bad5655-e7ee-44a0-998a-ac8bab8a2854", "aa7a3e4283d01a011478f698d61f9ccec58f1b39ceac37580e814778dfbb3e32"], ["c1d7206f-4506-437f-a188-416018f11c79", "de2249d95ec723114155c93b321faf63fcd821dbefb01fe2b61eed7d96b91750"], ["b3c1c683-3085-4c6e-b29e-96d8342ea7dd", "38ad21fe14e9e4a47f3c3d04a27d45694fa46d67103d29fa2b342dcf208b18f8"], ["d2b7a957-6364-4df2-8697-0b20f87655cd", "c2d7008c5719bbf7f3619f0501deb6c36ccb32ba65bcfa0a5af41f729bc1694e"], ["85768dd5-1af8-44bb-8c84-0cbf61a30fac", "4a5f3b4799d3fd67248860760fb1556c7d9fc047152895b64b40cb26e0423a09"], ["0cf8df41-b935-4abe-83f7-420f8f1ecce6", "928a9d374d665d916c156a4d49d7d118262e853668ce3c924cdffbf1567b9ead"], ["75e725c5-95f6-439d-ac4d-09d43191cb30", "ddb7776d67383e72ce254957f0faf1cd10b654fdffcf107504c6a817cf0f1062"], ["661f618f-ebc1-43e1-9c6d-ae21f437d1c8", "5e0640dbcbd873aca05d3a37900822483c05b9e2a861228ad7652160d0ae7de0"]]}], "changes": [{"new": ["9bad5655-e7ee-44a0-998a-ac8bab8a2854", "aa7a3e4283d01a011478f698d61f9ccec58f1b39ceac37580e814778dfbb3e32"], "old": null, "kind": "append", "position": 0, "host_logical_id": "9bad5655-e7ee-44a0-998a-ac8bab8a2854"}, {"new": ["c1d7206f-4506-437f-a188-416018f11c79", "de2249d95ec723114155c93b321faf63fcd821dbefb01fe2b61eed7d96b91750"], "old": null, "kind": "append", "position": 1, "host_logical_id": "c1d7206f-4506-437f-a188-416018f11c79"}, {"new": ["b3c1c683-3085-4c6e-b29e-96d8342ea7dd", "38ad21fe14e9e4a47f3c3d04a27d45694fa46d67103d29fa2b342dcf208b18f8"], "old": null, "kind": "append", "position": 2, "host_logical_id": "b3c1c683-3085-4c6e-b29e-96d8342ea7dd"}, {"new": ["d2b7a957-6364-4df2-8697-0b20f87655cd", "c2d7008c5719bbf7f3619f0501deb6c36ccb32ba65bcfa0a5af41f729bc1694e"], "old": null, "kind": "append", "position": 3, "host_logical_id": "d2b7a957-6364-4df2-8697-0b20f87655cd"}, {"new": ["85768dd5-1af8-44bb-8c84-0cbf61a30fac", "4a5f3b4799d3fd67248860760fb1556c7d9fc047152895b64b40cb26e0423a09"], "old": null, "kind": "append", "position": 4, "host_logical_id": "85768dd5-1af8-44bb-8c84-0cbf61a30fac"}, {"new": ["0cf8df41-b935-4abe-83f7-420f8f1ecce6", "928a9d374d665d916c156a4d49d7d118262e853668ce3c924cdffbf1567b9ead"], "old": null, "kind": "append", "position": 5, "host_logical_id": "0cf8df41-b935-4abe-83f7-420f8f1ecce6"}, {"new": ["75e725c5-95f6-439d-ac4d-09d43191cb30", "ddb7776d67383e72ce254957f0faf1cd10b654fdffcf107504c6a817cf0f1062"], "old": null, "kind": "append", "position": 6, "host_logical_id": "75e725c5-95f6-439d-ac4d-09d43191cb30"}, {"new": ["661f618f-ebc1-43e1-9c6d-ae21f437d1c8", "5e0640dbcbd873aca05d3a37900822483c05b9e2a861228ad7652160d0ae7de0"], "old": null, "kind": "append", "position": 7, "host_logical_id": "661f618f-ebc1-43e1-9c6d-ae21f437d1c8"}]}', '2026-09-28 03:38:40.75805+00', '01a0e617-e4fb-7409-bfff-993dfcc8d20e');


--
-- Name: assertion_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.assertion_id_seq', 18, true);


--
-- Name: job_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.job_id_seq', 43, true);


--
-- Name: state_observation_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.state_observation_id_seq', 1, false);


--
-- Name: worldline_append_seq_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.worldline_append_seq_seq', 4, true);


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
-- Name: entity_link entity_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_link
    ADD CONSTRAINT entity_link_pkey PRIMARY KEY (id);


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
-- Name: observation_base observation_base_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observation_base
    ADD CONSTRAINT observation_base_pkey PRIMARY KEY (observation_id);


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
-- Name: worldline_append worldline_append_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worldline_append
    ADD CONSTRAINT worldline_append_pkey PRIMARY KEY (seq);


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
-- Name: active_membership_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX active_membership_revision ON public.active_membership USING btree (source_revision_id);


--
-- Name: active_membership_turn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX active_membership_turn ON public.active_membership USING btree (commit_id, turn);


--
-- Name: assertion_extraction; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX assertion_extraction ON public.assertion USING btree (extraction_id);


--
-- Name: assertion_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX assertion_revision ON public.assertion USING btree (source_revision_id);


--
-- Name: entity_link_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX entity_link_conversation ON public.entity_link USING btree (conversation_id) WHERE (removed_at IS NULL);


--
-- Name: extraction_generation_window; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX extraction_generation_window ON public.extraction USING btree (source_revision_id, window_hash, extractor_key) WHERE (discarded_at IS NULL);


--
-- Name: extraction_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX extraction_revision ON public.extraction USING btree (source_revision_id);


--
-- Name: host_observation_full; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX host_observation_full ON public.host_observation USING btree (conversation_id, id) WHERE ((kind = 'manifest'::text) AND (raw_manifest ? 'entries'::text));


--
-- Name: job_ready; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX job_ready ON public.job USING btree (priority, id) WHERE (status = 'queued'::text);


--
-- Name: observation_base_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX observation_base_conversation ON public.observation_base USING btree (conversation_id, observation_id);


--
-- Name: retrieval_trace_commit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX retrieval_trace_commit ON public.retrieval_trace USING btree (commit_id);


--
-- Name: revision_text_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX revision_text_trgm ON public.revision_text USING gin (clean_content public.gin_trgm_ops);


--
-- Name: source_revision_lineage_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX source_revision_lineage_parent ON public.source_revision USING btree (lineage_parent_revision_id);


--
-- Name: state_observation_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX state_observation_conversation ON public.state_observation USING btree (conversation_id, rules_version, key);


--
-- Name: state_observation_revision; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX state_observation_revision ON public.state_observation USING btree (source_revision_id);


--
-- Name: worldline_append_commit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX worldline_append_commit ON public.worldline_append USING btree (commit_id, seq);


--
-- Name: worldline_append_observation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX worldline_append_observation ON public.worldline_append USING btree (host_observation_id);


--
-- Name: worldline_commit_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX worldline_commit_conversation ON public.worldline_commit USING btree (conversation_id, seq);


--
-- Name: worldline_commit_observation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX worldline_commit_observation ON public.worldline_commit USING btree (host_observation_id);


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
-- Name: entity_link entity_link_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_link
    ADD CONSTRAINT entity_link_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


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
-- Name: observation_base observation_base_observation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.observation_base
    ADD CONSTRAINT observation_base_observation_id_fkey FOREIGN KEY (observation_id) REFERENCES public.host_observation(id) ON DELETE CASCADE;


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
-- Name: worldline_append worldline_append_commit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worldline_append
    ADD CONSTRAINT worldline_append_commit_id_fkey FOREIGN KEY (commit_id) REFERENCES public.worldline_commit(id);


--
-- Name: worldline_append worldline_append_host_observation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worldline_append
    ADD CONSTRAINT worldline_append_host_observation_id_fkey FOREIGN KEY (host_observation_id) REFERENCES public.host_observation(id);


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


