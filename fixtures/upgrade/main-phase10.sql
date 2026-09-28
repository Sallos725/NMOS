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

INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 0, '01a0e50d-4756-78a9-8026-38c45c4ab013', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 1, '01a0e50d-4758-7c15-a79e-a1ca327d4b0d', NULL, 0, 'e8d7b66104f16eacaf609785fbe20062');
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 2, '01a0e50d-4759-7cc1-997b-115ad4c2cb98', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 3, '01a0e50d-4deb-7f64-98bc-c773a6101ef4', NULL, 1, 'c31f3684b947a2c86be94689aa27262f');
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 4, '01a0e50d-478e-73d1-b69f-ac286a2d7dde', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 5, '01a0e50d-478f-78a7-b3cf-8df717607ebc', NULL, 2, '1f5ec5fc4b1f62b153b8a0b417108802');
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 6, '01a0e50d-4790-79d9-ad06-8ea8d9240cdd', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 7, '01a0e50d-4790-7686-b8a9-7bfc858792a0', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 8, '01a0e50d-4e3b-7e59-b3cc-766a0e2c4605', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 9, '01a0e50d-47b6-7555-96ec-f071c998443f', NULL, 3, '08a34524aef0e1bd57936175a8004b26');
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 10, '01a0e50d-47b7-715a-a482-d44e57848c9b', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 11, '01a0e50d-47b8-7ca2-9d1d-384eea54c8e6', NULL, 4, 'c7162f8d7705073e9497fb5d31d278e1');
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 12, '01a0e50d-47de-727f-977f-1f0503a07055', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 13, '01a0e50d-4dec-77e0-9a52-b08e903b58c0', NULL, 5, '22d7947626ceafd7c62b759ba3d76c8d');
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 14, '01a0e50d-4dec-7921-8ae5-6a4cbffede94', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 15, '01a0e50d-4e3b-7a49-b01e-0b824500e4d2', NULL, 6, 'b587e338e6550a9f38a230c1ec45bb96');
INSERT INTO public.active_membership VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 16, '01a0e50d-4e3c-771a-9952-5ae7feb5fbb0', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 0, '01a0e50d-544b-7c1b-b384-f5197fc2862d', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 1, '01a0e50d-544c-7014-a344-b4a7f86bd831', NULL, 0, '9e4b26d9781684de9abecfef1a44cb2a');
INSERT INTO public.active_membership VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 2, '01a0e50d-544c-7b0c-a548-d307424ae19e', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 3, '01a0e50d-544d-79ce-988c-c88011b887d6', NULL, 1, '570d67d3883025674ae56ff878f1300f');
INSERT INTO public.active_membership VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 4, '01a0e50d-544d-777a-837a-d6f81157d4ff', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 5, '01a0e50d-544e-79de-895a-8775562ae846', NULL, 2, 'a9574d56ee4aa73843e580b2c5690452');
INSERT INTO public.active_membership VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 6, '01a0e50d-544f-793a-b4e9-14e987935b6a', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 7, '01a0e50d-544f-762e-a70a-42267e86fb61', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0e50d-4ce1-7db1-8a17-d7b3b633626f', '01a0e50d-47b8-7ca2-9d1d-384eea54c8e6', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0e50d-4cf7-76ff-be75-ee9542b0ea79', '01a0e50d-47b6-7555-96ec-f071c998443f', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0e50d-4d26-7aeb-9e0c-d75cbc55d8ea', '01a0e50d-478f-78a7-b3cf-8df717607ebc', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0e50d-4d3c-7a41-af22-10a33b08c740', '01a0e50d-475a-7dc2-9f79-79e77d7f3536', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0e50d-4d3c-7a41-af22-10a33b08c740', '01a0e50d-475a-7dc2-9f79-79e77d7f3536', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0e50d-4d90-794e-993c-5b332dd83277', '01a0e50d-4758-7c15-a79e-a1ca327d4b0d', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0e50d-4d90-794e-993c-5b332dd83277', '01a0e50d-4758-7c15-a79e-a1ca327d4b0d', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0e50d-51fb-7718-9f6d-892d6e50e839', '01a0e50d-4e3b-7a49-b01e-0b824500e4d2', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0e50d-5227-7761-b487-d0d4459c6706', '01a0e50d-47b8-7ca2-9d1d-384eea54c8e6', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0e50d-523c-7e7a-9c6f-9ea9fb0da603', '01a0e50d-47b6-7555-96ec-f071c998443f', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0e50d-5260-73a4-acac-e7ccbd17439e', '01a0e50d-478f-78a7-b3cf-8df717607ebc', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0e50d-5275-713d-b4d9-5d16fad6db6a', '01a0e50d-4deb-7f64-98bc-c773a6101ef4', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0e50d-5275-713d-b4d9-5d16fad6db6a', '01a0e50d-4deb-7f64-98bc-c773a6101ef4', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0e50d-5705-7af1-8d8e-2868f28ed801', '01a0e50d-544e-79de-895a-8775562ae846', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0e50d-5719-7669-8971-52dd2a11e729', '01a0e50d-544d-79ce-988c-c88011b887d6', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0e50d-5719-7669-8971-52dd2a11e729', '01a0e50d-544d-79ce-988c-c88011b887d6', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0e50d-572e-76f5-b905-97ce1afda592', '01a0e50d-544c-7014-a344-b4a7f86bd831', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0e50d-572e-76f5-b905-97ce1afda592', '01a0e50d-544c-7014-a344-b4a7f86bd831', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0e50d-474e-7801-af89-7da0a33c9bdf', 'pocketrisu', NULL, '9135e722-f916-40e5-83f8-a6ea007df4a1', '2026-09-27 22:47:27.822708+00', NULL, NULL, NULL, '01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', '3098e368a19edee9c922d6a9e3fafe43854bac3dfff763d427069a507f078482', 'Mina', 'Upgrade fixture', 'Yuuma', false, NULL);
INSERT INTO public.conversation VALUES ('01a0e50d-5446-7365-af2f-6dc779076142', 'pocketrisu', NULL, 'c0019028-8eec-4db7-8011-04d08b62624d', '2026-09-27 22:47:31.142175+00', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '9135e722-f916-40e5-83f8-a6ea007df4a1', '860407f5-66be-4293-aaa3-e31c07b5e6e7', '01a0e50d-5451-7c73-a2b1-44a31d3afadb', '9f5220f03a3ad6a9907717655c27ec6c4d17490abab488e0359c25c1f17c04b7', 'Mina', 'Upgrade fixture', 'Yuuma', false, NULL);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0e50d-4ce1-7db1-8a17-d7b3b633626f', '01a0e50d-47b8-7ca2-9d1d-384eea54c8e6', '2519dcfd680e2d551f200a1711d4ad12', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:29.249486+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e50d-47b7-715a-a482-d44e57848c9b,01a0e50d-47b8-7ca2-9d1d-384eea54c8e6}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-4cf7-76ff-be75-ee9542b0ea79', '01a0e50d-47b6-7555-96ec-f071c998443f', '9f28a117bebbba413bf76ff11bbafc4e', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:29.271777+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e50d-47b5-7014-b256-efa5a177cf63,01a0e50d-47b6-7555-96ec-f071c998443f}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-4d0d-701f-a135-ef4431fdd985', '01a0e50d-4790-7686-b8a9-7bfc858792a0', '21cd0031106eb7415e6a471d538e6c38', 'extract-v12', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-27 22:47:29.293887+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e50d-4790-79d9-ad06-8ea8d9240cdd,01a0e50d-4790-7686-b8a9-7bfc858792a0}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-4d26-7aeb-9e0c-d75cbc55d8ea', '01a0e50d-478f-78a7-b3cf-8df717607ebc', 'd14d2efa772a2240a8a8f5cce8c582bc', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:29.31862+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e50d-478e-73d1-b69f-ac286a2d7dde,01a0e50d-478f-78a7-b3cf-8df717607ebc}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-4d3c-7a41-af22-10a33b08c740', '01a0e50d-475a-7dc2-9f79-79e77d7f3536', '9e70c7c692b07cb38ea1c588c9e95664', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:29.34082+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e50d-4759-7cc1-997b-115ad4c2cb98,01a0e50d-475a-7dc2-9f79-79e77d7f3536}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-4d90-794e-993c-5b332dd83277', '01a0e50d-4758-7c15-a79e-a1ca327d4b0d', 'e8d7b66104f16eacaf609785fbe20062', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:29.424763+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e50d-4756-78a9-8026-38c45c4ab013,01a0e50d-4758-7c15-a79e-a1ca327d4b0d}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-51fb-7718-9f6d-892d6e50e839', '01a0e50d-4e3b-7a49-b01e-0b824500e4d2', 'b587e338e6550a9f38a230c1ec45bb96', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:30.554982+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e50d-4dec-7921-8ae5-6a4cbffede94,01a0e50d-4e3b-7a49-b01e-0b824500e4d2}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-5211-70d3-9930-4e4ecbeca654', '01a0e50d-4dec-77e0-9a52-b08e903b58c0', '22d7947626ceafd7c62b759ba3d76c8d', 'extract-v12', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-27 22:47:30.577711+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e50d-47de-727f-977f-1f0503a07055,01a0e50d-4dec-77e0-9a52-b08e903b58c0}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-5227-7761-b487-d0d4459c6706', '01a0e50d-47b8-7ca2-9d1d-384eea54c8e6', 'c7162f8d7705073e9497fb5d31d278e1', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:30.599173+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e50d-47b7-715a-a482-d44e57848c9b,01a0e50d-47b8-7ca2-9d1d-384eea54c8e6}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-523c-7e7a-9c6f-9ea9fb0da603', '01a0e50d-47b6-7555-96ec-f071c998443f', '08a34524aef0e1bd57936175a8004b26', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:30.620853+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0e50d-4790-79d9-ad06-8ea8d9240cdd,01a0e50d-4790-7686-b8a9-7bfc858792a0,01a0e50d-47b6-7555-96ec-f071c998443f}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-5260-73a4-acac-e7ccbd17439e', '01a0e50d-478f-78a7-b3cf-8df717607ebc', '1f5ec5fc4b1f62b153b8a0b417108802', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:30.656193+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e50d-478e-73d1-b69f-ac286a2d7dde,01a0e50d-478f-78a7-b3cf-8df717607ebc}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-5275-713d-b4d9-5d16fad6db6a', '01a0e50d-4deb-7f64-98bc-c773a6101ef4', 'c31f3684b947a2c86be94689aa27262f', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:30.677513+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e50d-4759-7cc1-997b-115ad4c2cb98,01a0e50d-4deb-7f64-98bc-c773a6101ef4}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-5705-7af1-8d8e-2868f28ed801', '01a0e50d-544e-79de-895a-8775562ae846', 'a9574d56ee4aa73843e580b2c5690452', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:31.845167+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e50d-544d-777a-837a-d6f81157d4ff,01a0e50d-544e-79de-895a-8775562ae846}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-5719-7669-8971-52dd2a11e729', '01a0e50d-544d-79ce-988c-c88011b887d6', '570d67d3883025674ae56ff878f1300f', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:31.865901+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e50d-544c-7b0c-a548-d307424ae19e,01a0e50d-544d-79ce-988c-c88011b887d6}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e50d-572e-76f5-b905-97ce1afda592', '01a0e50d-544c-7014-a344-b4a7f86bd831', '9e4b26d9781684de9abecfef1a44cb2a', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-27 22:47:31.886761+00', 'extract-de532d894a86bf0cd75dd4831f040c9b', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e50d-544b-7c1b-b384-f5197fc2862d,01a0e50d-544c-7014-a344-b4a7f86bd831}', NULL, '{"secrets": [], "entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0e50d-475c-731a-8713-d57149d485a3', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'manifest', '2e71b29f8bf1f3164969140d396f63892d67f9f1581e629755c813149f99bf5c', '01a0e50d-474e-7801-af89-7da0a33c9bdf:2e71b29f8bf1f3164969140d396f63892d67f9f1581e629755c813149f99bf5c:manifest', '2026-09-27 22:47:27.829337+00', '{"chat_id": "9135e722-f916-40e5-83f8-a6ea007df4a1", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["a060144d-8d75-4374-95ae-308df5760366", "96ddf919be36476491778386d3f09ab5d62ac59ca7c1b38612f82dbe52e5c5b3", "user", null, null, null, 0, null, null], ["e1c2f23e-2bb6-42fe-9093-50c04f78fa85", "f09b274b86309f927942511a56ee2ec50db1ec863dc36f82dcc26917cf03b999", "char", null, null, null, 0, "e1c2f23e-2bb6-42fe-9093-50c04f78fa85", null], ["146cfad5-a2e7-43f0-81b4-9ef2f8e134d5", "766cd4f9855fca81b403949fbaf46cb70cfae9d7091200059c76950dde1f22e9", "user", null, null, null, 0, null, null], ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "315367c14657cd6b70ec76dd5bc80f0a0486ce0084b01a854852b697786084ba", "char", null, null, null, 0, "76ed04e3-4e7e-4df2-ba97-2a1825899d39", null]]}');
INSERT INTO public.host_observation VALUES ('01a0e50d-4793-756f-b055-1702969ff4da', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'manifest', 'b66a055c59e64933ca999fd439fde37cd536ffc458e3f65275a9ff2005230528', '01a0e50d-474e-7801-af89-7da0a33c9bdf:b66a055c59e64933ca999fd439fde37cd536ffc458e3f65275a9ff2005230528:manifest', '2026-09-27 22:47:27.885159+00', '{"chat_id": "9135e722-f916-40e5-83f8-a6ea007df4a1", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["2b9c6209-3972-4f5c-b050-04bfdf938cc5", "2f69ee9eb657bd0cdf89ac86858bfc4151acd8b3258f7b97f617d64d93c6f04d", "user", null, null, null, 0, null, null], ["860407f5-66be-4293-aaa3-e31c07b5e6e7", "622602feb18e9ad6ccd3722a363fe76aa8b00351a6e8d479130592d4e44e4bae", "char", null, null, null, 0, "860407f5-66be-4293-aaa3-e31c07b5e6e7", null], ["78851a2a-232e-404e-977a-cc20c0848d15", "64be4db5059633c4e1a697a08b050237fd0c95e5b227ad8f8103ff5c0f154666", "user", null, null, null, 0, null, null], ["00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "c7529e7693ac8212b08b2163b62859f9e08a151c40fd0d53cb5cba4a1a332d9b", "char", null, null, null, 0, "00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", null]], "base_manifest_hash": "2e71b29f8bf1f3164969140d396f63892d67f9f1581e629755c813149f99bf5c"}');
INSERT INTO public.host_observation VALUES ('01a0e50d-47ba-7051-9c63-9361ce6e2349', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'manifest', '8548c530d090cc5ce5f6b58c7d3465c7c61c7dee1691c1a915f03d9dbda10679', '01a0e50d-474e-7801-af89-7da0a33c9bdf:8548c530d090cc5ce5f6b58c7d3465c7c61c7dee1691c1a915f03d9dbda10679:manifest', '2026-09-27 22:47:27.925133+00', '{"chat_id": "9135e722-f916-40e5-83f8-a6ea007df4a1", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "f538f16d9a5fab2b5739cc9a564938509f9808efdb3e93f111ab5c1170980f4b", "user", null, null, null, 0, null, null], ["69393859-90ab-4e84-a98e-25d03648cdf9", "729739b4fc6ebbbdc15a08d856f91eeb42fb42c54d3aa588dcc0d381c88793a9", "char", null, null, null, 0, "69393859-90ab-4e84-a98e-25d03648cdf9", null], ["af37fd99-2f07-4511-9c1d-d69359f38f5a", "9a5b4d71394a1ef5066a51609aa5ca53c7d287a2250a7edba96cc05af6ae3859", "user", null, null, null, 0, null, null], ["736129b9-7145-400f-80d0-e6b5cd5b2b89", "eb1658873ddd1daf70b210de2f1e830ea3fdd0721696de5e25359fdf7aa8fac9", "char", null, null, null, 0, "736129b9-7145-400f-80d0-e6b5cd5b2b89", null]], "base_manifest_hash": "b66a055c59e64933ca999fd439fde37cd536ffc458e3f65275a9ff2005230528"}');
INSERT INTO public.host_observation VALUES ('01a0e50d-47e1-73f6-8642-bbea8f83f0e2', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'manifest', '6f8c3141c2f217ae50c3b740281cd328b6385af09b5ad5db347b9e0317fa9f5d', '01a0e50d-474e-7801-af89-7da0a33c9bdf:6f8c3141c2f217ae50c3b740281cd328b6385af09b5ad5db347b9e0317fa9f5d:manifest', '2026-09-27 22:47:27.96505+00', '{"chat_id": "9135e722-f916-40e5-83f8-a6ea007df4a1", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["1f954246-d0d1-4729-8392-347861a1a036", "c19544c36e9a787fc6ad1969b93643a321eafabbfdee78b259d240f446906ee6", "user", null, null, null, 0, null, null]], "base_manifest_hash": "8548c530d090cc5ce5f6b58c7d3465c7c61c7dee1691c1a915f03d9dbda10679"}');
INSERT INTO public.host_observation VALUES ('01a0e50d-4dee-7d65-91cf-8868ee70f046', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'manifest', 'd56bbfb87911d341b3bbc84ec79ab8945503b17884c0ac86456c779170c516c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf:d56bbfb87911d341b3bbc84ec79ab8945503b17884c0ac86456c779170c516c8:manifest', '2026-09-27 22:47:29.514544+00', '{"chat_id": "9135e722-f916-40e5-83f8-a6ea007df4a1", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["a060144d-8d75-4374-95ae-308df5760366", "96ddf919be36476491778386d3f09ab5d62ac59ca7c1b38612f82dbe52e5c5b3", "user", null, null, null, 0, null, null], ["e1c2f23e-2bb6-42fe-9093-50c04f78fa85", "f09b274b86309f927942511a56ee2ec50db1ec863dc36f82dcc26917cf03b999", "char", null, null, null, 0, "e1c2f23e-2bb6-42fe-9093-50c04f78fa85", null], ["146cfad5-a2e7-43f0-81b4-9ef2f8e134d5", "766cd4f9855fca81b403949fbaf46cb70cfae9d7091200059c76950dde1f22e9", "user", null, null, null, 0, null, null], ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "b6ea8fb28e8857625f4e54103dbc4524dc21710f5d499253dd6af5ec362e3c93", "char", null, null, null, 0, "76ed04e3-4e7e-4df2-ba97-2a1825899d39", null], ["2b9c6209-3972-4f5c-b050-04bfdf938cc5", "2f69ee9eb657bd0cdf89ac86858bfc4151acd8b3258f7b97f617d64d93c6f04d", "user", null, null, null, 0, null, null], ["860407f5-66be-4293-aaa3-e31c07b5e6e7", "622602feb18e9ad6ccd3722a363fe76aa8b00351a6e8d479130592d4e44e4bae", "char", null, null, null, 0, "860407f5-66be-4293-aaa3-e31c07b5e6e7", null], ["78851a2a-232e-404e-977a-cc20c0848d15", "64be4db5059633c4e1a697a08b050237fd0c95e5b227ad8f8103ff5c0f154666", "user", null, null, null, 0, null, null], ["00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "c7529e7693ac8212b08b2163b62859f9e08a151c40fd0d53cb5cba4a1a332d9b", "char", null, null, null, 0, "00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", null], ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "f538f16d9a5fab2b5739cc9a564938509f9808efdb3e93f111ab5c1170980f4b", "user", null, null, null, 0, null, null], ["69393859-90ab-4e84-a98e-25d03648cdf9", "729739b4fc6ebbbdc15a08d856f91eeb42fb42c54d3aa588dcc0d381c88793a9", "char", null, null, null, 0, "69393859-90ab-4e84-a98e-25d03648cdf9", null], ["af37fd99-2f07-4511-9c1d-d69359f38f5a", "9a5b4d71394a1ef5066a51609aa5ca53c7d287a2250a7edba96cc05af6ae3859", "user", null, null, null, 0, null, null], ["736129b9-7145-400f-80d0-e6b5cd5b2b89", "eb1658873ddd1daf70b210de2f1e830ea3fdd0721696de5e25359fdf7aa8fac9", "char", null, null, null, 0, "736129b9-7145-400f-80d0-e6b5cd5b2b89", null], ["1f954246-d0d1-4729-8392-347861a1a036", "c19544c36e9a787fc6ad1969b93643a321eafabbfdee78b259d240f446906ee6", "user", null, null, null, 0, null, null], ["d5abcb2b-91fe-457b-894e-e364e66288ab", "1d414c5fb1561e09277bf77610e37221c8921a871872df60efec79ff163141ad", "char", null, null, null, 0, "d5abcb2b-91fe-457b-894e-e364e66288ab", null], ["7b425248-121d-489b-8207-0979cc4c1508", "4eed7de0f0305536c463024e1cb42ad4fb081cffbce9bbdf2ed61970e7d265db", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e50d-4e17-7698-aa19-bc2f11e52c87', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'manifest', '61ee3eea4f8987a9cc05837fddc85799390f0be6f015826649a2267de4274042', '01a0e50d-474e-7801-af89-7da0a33c9bdf:61ee3eea4f8987a9cc05837fddc85799390f0be6f015826649a2267de4274042:manifest', '2026-09-27 22:47:29.555249+00', '{"chat_id": "9135e722-f916-40e5-83f8-a6ea007df4a1", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["412076cb-caff-48ba-9221-38fbca3bf2af", "f5cc0ccce67eb7e912536c26d246154b3435365583608c321aa9324c557a26ea", "char", null, null, 1, 2, "412076cb-caff-48ba-9221-38fbca3bf2af", null]], "base_manifest_hash": "d56bbfb87911d341b3bbc84ec79ab8945503b17884c0ac86456c779170c516c8"}');
INSERT INTO public.host_observation VALUES ('01a0e50d-4e3e-7e21-84dc-f1ecf5cdac93', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'manifest', '3098e368a19edee9c922d6a9e3fafe43854bac3dfff763d427069a507f078482', '01a0e50d-474e-7801-af89-7da0a33c9bdf:3098e368a19edee9c922d6a9e3fafe43854bac3dfff763d427069a507f078482:manifest', '2026-09-27 22:47:29.594079+00', '{"chat_id": "9135e722-f916-40e5-83f8-a6ea007df4a1", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["a060144d-8d75-4374-95ae-308df5760366", "96ddf919be36476491778386d3f09ab5d62ac59ca7c1b38612f82dbe52e5c5b3", "user", null, null, null, 0, null, null], ["e1c2f23e-2bb6-42fe-9093-50c04f78fa85", "f09b274b86309f927942511a56ee2ec50db1ec863dc36f82dcc26917cf03b999", "char", null, null, null, 0, "e1c2f23e-2bb6-42fe-9093-50c04f78fa85", null], ["146cfad5-a2e7-43f0-81b4-9ef2f8e134d5", "766cd4f9855fca81b403949fbaf46cb70cfae9d7091200059c76950dde1f22e9", "user", null, null, null, 0, null, null], ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "b6ea8fb28e8857625f4e54103dbc4524dc21710f5d499253dd6af5ec362e3c93", "char", null, null, null, 0, "76ed04e3-4e7e-4df2-ba97-2a1825899d39", null], ["2b9c6209-3972-4f5c-b050-04bfdf938cc5", "2f69ee9eb657bd0cdf89ac86858bfc4151acd8b3258f7b97f617d64d93c6f04d", "user", null, null, null, 0, null, null], ["860407f5-66be-4293-aaa3-e31c07b5e6e7", "622602feb18e9ad6ccd3722a363fe76aa8b00351a6e8d479130592d4e44e4bae", "char", null, null, null, 0, "860407f5-66be-4293-aaa3-e31c07b5e6e7", null], ["78851a2a-232e-404e-977a-cc20c0848d15", "64be4db5059633c4e1a697a08b050237fd0c95e5b227ad8f8103ff5c0f154666", "user", null, null, null, 0, null, null], ["00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "c7529e7693ac8212b08b2163b62859f9e08a151c40fd0d53cb5cba4a1a332d9b", "char", null, null, null, 0, "00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", null], ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "fc6606ed3f4695640d0732042e5ff4d65676e65693b73efd1015c62bc2612ab2", "user", true, null, null, 0, null, null], ["69393859-90ab-4e84-a98e-25d03648cdf9", "729739b4fc6ebbbdc15a08d856f91eeb42fb42c54d3aa588dcc0d381c88793a9", "char", null, null, null, 0, "69393859-90ab-4e84-a98e-25d03648cdf9", null], ["af37fd99-2f07-4511-9c1d-d69359f38f5a", "9a5b4d71394a1ef5066a51609aa5ca53c7d287a2250a7edba96cc05af6ae3859", "user", null, null, null, 0, null, null], ["736129b9-7145-400f-80d0-e6b5cd5b2b89", "eb1658873ddd1daf70b210de2f1e830ea3fdd0721696de5e25359fdf7aa8fac9", "char", null, null, null, 0, "736129b9-7145-400f-80d0-e6b5cd5b2b89", null], ["1f954246-d0d1-4729-8392-347861a1a036", "c19544c36e9a787fc6ad1969b93643a321eafabbfdee78b259d240f446906ee6", "user", null, null, null, 0, null, null], ["d5abcb2b-91fe-457b-894e-e364e66288ab", "1d414c5fb1561e09277bf77610e37221c8921a871872df60efec79ff163141ad", "char", null, null, null, 0, "d5abcb2b-91fe-457b-894e-e364e66288ab", null], ["7b425248-121d-489b-8207-0979cc4c1508", "4eed7de0f0305536c463024e1cb42ad4fb081cffbce9bbdf2ed61970e7d265db", "user", null, null, null, 0, null, null], ["412076cb-caff-48ba-9221-38fbca3bf2af", "22d3b215a6a43fff66e078a2bb32cb1560f5960d74c0e00e491a64a80a25f108", "char", null, null, 0, 2, "412076cb-caff-48ba-9221-38fbca3bf2af", null], ["340cf8b5-f9a3-46f3-92ee-49e72570a9b0", "9026e2e4bb8fb3318af9255a69c9848e4a7e4ea4a145e439f0ec15cf0291d865", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e50d-5450-758f-8849-4db0d92301ac', '01a0e50d-5446-7365-af2f-6dc779076142', 'manifest', '9f5220f03a3ad6a9907717655c27ec6c4d17490abab488e0359c25c1f17c04b7', '01a0e50d-5446-7365-af2f-6dc779076142:9f5220f03a3ad6a9907717655c27ec6c4d17490abab488e0359c25c1f17c04b7:manifest', '2026-09-27 22:47:31.146971+00', '{"chat_id": "c0019028-8eec-4db7-8011-04d08b62624d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["afeb64d1-3b1d-40a5-a418-6a9c516beb3a", "eaf24a65d767200cba3296c1e541b92033ba503c21426885d22b7330a7f306bc", "user", null, null, null, 0, null, null], ["83909bd8-7e3b-4223-9ffd-ca3b4eecfdff", "79f50ee67c002d1c1292c160de3b1608841d9c2d0d7129ece1f5dc59363c9798", "char", null, null, null, 0, "e1c2f23e-2bb6-42fe-9093-50c04f78fa85", null], ["b6703e73-33d8-4fd3-a45b-e0bcbd82b1e0", "d2f5100dd028659b67a1292bb97bae5c45df66dcedcff740d12bfc7d478d7881", "user", null, null, null, 0, null, null], ["7dad2adb-0e12-4157-b53a-79f1a8d8dd11", "2d7d104f32c7c491c6d0d5ba4e23a7dd3869827c84ff4df58d49ff4fa28330ec", "char", null, null, null, 0, "76ed04e3-4e7e-4df2-ba97-2a1825899d39", null], ["e95a1ba6-228c-468e-b0a5-dfab0d4a5ed2", "0f41ea07051721fc99370a4298177a6e1d3c4ff7e93aff303f939f074083ff0a", "user", null, null, null, 0, null, null], ["1d7bfe39-ac73-4327-a87a-218ddfdfbc86", "8431eb49298514973c19d9576dd6f0784d29b251185951c8f81315d7829494f7", "char", null, null, null, 0, "860407f5-66be-4293-aaa3-e31c07b5e6e7", null], ["bfaf0ed8-191b-4bdc-ba49-22948c2f25ea", "326420ccbc56127e035909e7750038e7bde83499bc508504c4c6810a0c4c749c", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::9135e722-f916-40e5-83f8-a6ea007df4a1::Harbor route::860407f5-66be-4293-aaa3-e31c07b5e6e7::}}"]], ["b10d2faa-12f5-4e4c-9a32-90707682f720", "6c056ed63d766d0ad0d4b3d7fcc26201c52d1417231f4303d3a1c8479561e355", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0e50d-47de-727f-977f-1f0503a07055:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-47de-727f-977f-1f0503a07055"}', 50, 'done', 1, '2026-09-27 22:47:27.96505+00', NULL, NULL, '2026-09-27 22:47:27.96505+00', '2026-09-27 22:47:29.041027+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0e50d-47b8-7ca2-9d1d-384eea54c8e6:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-47b8-7ca2-9d1d-384eea54c8e6"}', 50, 'done', 1, '2026-09-27 22:47:27.96505+00', NULL, NULL, '2026-09-27 22:47:27.96505+00', '2026-09-27 22:47:29.062183+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0e50d-47b7-715a-a482-d44e57848c9b:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-47b7-715a-a482-d44e57848c9b"}', 50, 'done', 1, '2026-09-27 22:47:27.925133+00', NULL, NULL, '2026-09-27 22:47:27.925133+00', '2026-09-27 22:47:29.082893+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0e50d-47b6-7555-96ec-f071c998443f:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-47b6-7555-96ec-f071c998443f"}', 50, 'done', 1, '2026-09-27 22:47:27.925133+00', NULL, NULL, '2026-09-27 22:47:27.925133+00', '2026-09-27 22:47:29.105597+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0e50d-47b5-7014-b256-efa5a177cf63:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-47b5-7014-b256-efa5a177cf63"}', 50, 'done', 1, '2026-09-27 22:47:27.925133+00', NULL, NULL, '2026-09-27 22:47:27.925133+00', '2026-09-27 22:47:29.125088+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0e50d-4790-7686-b8a9-7bfc858792a0:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4790-7686-b8a9-7bfc858792a0"}', 50, 'done', 1, '2026-09-27 22:47:27.925133+00', NULL, NULL, '2026-09-27 22:47:27.925133+00', '2026-09-27 22:47:29.144423+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0e50d-4790-79d9-ad06-8ea8d9240cdd:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4790-79d9-ad06-8ea8d9240cdd"}', 50, 'done', 1, '2026-09-27 22:47:27.885159+00', NULL, NULL, '2026-09-27 22:47:27.885159+00', '2026-09-27 22:47:29.163993+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0e50d-478f-78a7-b3cf-8df717607ebc:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-478f-78a7-b3cf-8df717607ebc"}', 50, 'done', 1, '2026-09-27 22:47:27.885159+00', NULL, NULL, '2026-09-27 22:47:27.885159+00', '2026-09-27 22:47:29.182952+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0e50d-478e-73d1-b69f-ac286a2d7dde:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-478e-73d1-b69f-ac286a2d7dde"}', 50, 'done', 1, '2026-09-27 22:47:27.885159+00', NULL, NULL, '2026-09-27 22:47:27.885159+00', '2026-09-27 22:47:29.203578+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0e50d-475a-7dc2-9f79-79e77d7f3536:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-475a-7dc2-9f79-79e77d7f3536"}', 50, 'done', 1, '2026-09-27 22:47:27.885159+00', NULL, NULL, '2026-09-27 22:47:27.885159+00', '2026-09-27 22:47:29.227196+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0e50d-47b8-7ca2-9d1d-384eea54c8e6:2519dcfd680e2d551f200a1711d4ad12:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-47b8-7ca2-9d1d-384eea54c8e6", "window_hash": "2519dcfd680e2d551f200a1711d4ad12"}', 100, 'done', 1, '2026-09-27 22:47:27.96505+00', NULL, NULL, '2026-09-27 22:47:27.96505+00', '2026-09-27 22:47:29.252209+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0e50d-47b6-7555-96ec-f071c998443f:9f28a117bebbba413bf76ff11bbafc4e:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-47b6-7555-96ec-f071c998443f", "window_hash": "9f28a117bebbba413bf76ff11bbafc4e"}', 100, 'done', 1, '2026-09-27 22:47:27.925133+00', NULL, NULL, '2026-09-27 22:47:27.925133+00', '2026-09-27 22:47:29.273701+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0e50d-4790-7686-b8a9-7bfc858792a0:21cd0031106eb7415e6a471d538e6c38:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-4790-7686-b8a9-7bfc858792a0", "window_hash": "21cd0031106eb7415e6a471d538e6c38"}', 100, 'done', 1, '2026-09-27 22:47:27.925133+00', NULL, NULL, '2026-09-27 22:47:27.925133+00', '2026-09-27 22:47:29.295571+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0e50d-478f-78a7-b3cf-8df717607ebc:d14d2efa772a2240a8a8f5cce8c582bc:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-478f-78a7-b3cf-8df717607ebc", "window_hash": "d14d2efa772a2240a8a8f5cce8c582bc"}', 100, 'done', 1, '2026-09-27 22:47:27.885159+00', NULL, NULL, '2026-09-27 22:47:27.885159+00', '2026-09-27 22:47:29.320658+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0e50d-475a-7dc2-9f79-79e77d7f3536:9e70c7c692b07cb38ea1c588c9e95664:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-475a-7dc2-9f79-79e77d7f3536", "window_hash": "9e70c7c692b07cb38ea1c588c9e95664"}', 100, 'done', 1, '2026-09-27 22:47:27.885159+00', NULL, NULL, '2026-09-27 22:47:27.885159+00', '2026-09-27 22:47:29.342819+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0e50d-4759-7cc1-997b-115ad4c2cb98:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4759-7cc1-997b-115ad4c2cb98"}', 150, 'done', 1, '2026-09-27 22:47:27.829337+00', NULL, NULL, '2026-09-27 22:47:27.829337+00', '2026-09-27 22:47:29.361821+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0e50d-4758-7c15-a79e-a1ca327d4b0d:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4758-7c15-a79e-a1ca327d4b0d"}', 150, 'done', 1, '2026-09-27 22:47:27.829337+00', NULL, NULL, '2026-09-27 22:47:27.829337+00', '2026-09-27 22:47:29.381686+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0e50d-4756-78a9-8026-38c45c4ab013:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4756-78a9-8026-38c45c4ab013"}', 150, 'done', 1, '2026-09-27 22:47:27.829337+00', NULL, NULL, '2026-09-27 22:47:27.829337+00', '2026-09-27 22:47:29.400726+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0e50d-4758-7c15-a79e-a1ca327d4b0d:e8d7b66104f16eacaf609785fbe20062:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-4758-7c15-a79e-a1ca327d4b0d", "window_hash": "e8d7b66104f16eacaf609785fbe20062"}', 200, 'done', 1, '2026-09-27 22:47:27.829337+00', NULL, NULL, '2026-09-27 22:47:27.829337+00', '2026-09-27 22:47:29.42743+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0e50d-478f-78a7-b3cf-8df717607ebc:1f5ec5fc4b1f62b153b8a0b417108802:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-478f-78a7-b3cf-8df717607ebc", "window_hash": "1f5ec5fc4b1f62b153b8a0b417108802"}', 100, 'done', 1, '2026-09-27 22:47:29.514544+00', NULL, NULL, '2026-09-27 22:47:29.514544+00', '2026-09-27 22:47:30.658075+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0e50d-4deb-7f64-98bc-c773a6101ef4:c31f3684b947a2c86be94689aa27262f:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-4deb-7f64-98bc-c773a6101ef4", "window_hash": "c31f3684b947a2c86be94689aa27262f"}', 100, 'done', 1, '2026-09-27 22:47:29.514544+00', NULL, NULL, '2026-09-27 22:47:29.514544+00', '2026-09-27 22:47:30.679539+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0e50d-544d-777a-837a-d6f81157d4ff:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-544d-777a-837a-d6f81157d4ff"}', 150, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.74899+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0e50d-4e3c-771a-9952-5ae7feb5fbb0:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4e3c-771a-9952-5ae7feb5fbb0"}', 50, 'done', 1, '2026-09-27 22:47:29.594079+00', NULL, NULL, '2026-09-27 22:47:29.594079+00', '2026-09-27 22:47:30.45631+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0e50d-4e3b-7a49-b01e-0b824500e4d2:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4e3b-7a49-b01e-0b824500e4d2"}', 50, 'done', 1, '2026-09-27 22:47:29.594079+00', NULL, NULL, '2026-09-27 22:47:29.594079+00', '2026-09-27 22:47:30.474539+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0e50d-4dec-7921-8ae5-6a4cbffede94:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4dec-7921-8ae5-6a4cbffede94"}', 50, 'done', 1, '2026-09-27 22:47:29.514544+00', NULL, NULL, '2026-09-27 22:47:29.514544+00', '2026-09-27 22:47:30.493787+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0e50d-4dec-77e0-9a52-b08e903b58c0:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4dec-77e0-9a52-b08e903b58c0"}', 50, 'done', 1, '2026-09-27 22:47:29.514544+00', NULL, NULL, '2026-09-27 22:47:29.514544+00', '2026-09-27 22:47:30.511958+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0e50d-4deb-7f64-98bc-c773a6101ef4:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-4deb-7f64-98bc-c773a6101ef4"}', 50, 'done', 1, '2026-09-27 22:47:29.514544+00', NULL, NULL, '2026-09-27 22:47:29.514544+00', '2026-09-27 22:47:30.530739+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0e50d-4e3b-7a49-b01e-0b824500e4d2:b587e338e6550a9f38a230c1ec45bb96:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-4e3b-7a49-b01e-0b824500e4d2", "window_hash": "b587e338e6550a9f38a230c1ec45bb96"}', 100, 'done', 1, '2026-09-27 22:47:29.594079+00', NULL, NULL, '2026-09-27 22:47:29.594079+00', '2026-09-27 22:47:30.55688+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0e50d-4dec-77e0-9a52-b08e903b58c0:22d7947626ceafd7c62b759ba3d76c8d:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-4dec-77e0-9a52-b08e903b58c0", "window_hash": "22d7947626ceafd7c62b759ba3d76c8d"}', 100, 'done', 1, '2026-09-27 22:47:29.594079+00', NULL, NULL, '2026-09-27 22:47:29.594079+00', '2026-09-27 22:47:30.579326+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0e50d-47b8-7ca2-9d1d-384eea54c8e6:c7162f8d7705073e9497fb5d31d278e1:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-47b8-7ca2-9d1d-384eea54c8e6", "window_hash": "c7162f8d7705073e9497fb5d31d278e1"}', 100, 'done', 1, '2026-09-27 22:47:29.594079+00', NULL, NULL, '2026-09-27 22:47:29.594079+00', '2026-09-27 22:47:30.60123+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0e50d-47b6-7555-96ec-f071c998443f:08a34524aef0e1bd57936175a8004b26:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-47b6-7555-96ec-f071c998443f", "window_hash": "08a34524aef0e1bd57936175a8004b26"}', 100, 'done', 1, '2026-09-27 22:47:29.594079+00', NULL, NULL, '2026-09-27 22:47:29.594079+00', '2026-09-27 22:47:30.622642+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0e50d-4dec-77e0-9a52-b08e903b58c0:e5099efca8df5e05e25ef84e1bee0a6b:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-4dec-77e0-9a52-b08e903b58c0", "window_hash": "e5099efca8df5e05e25ef84e1bee0a6b"}', 100, 'obsolete', 1, '2026-09-27 22:47:29.514544+00', NULL, NULL, '2026-09-27 22:47:29.514544+00', '2026-09-27 22:47:30.626647+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0e50d-47b6-7555-96ec-f071c998443f:851f80b9f8a6baff941be28ace8f87eb:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-47b6-7555-96ec-f071c998443f", "window_hash": "851f80b9f8a6baff941be28ace8f87eb"}', 100, 'obsolete', 1, '2026-09-27 22:47:29.514544+00', NULL, NULL, '2026-09-27 22:47:29.514544+00', '2026-09-27 22:47:30.633193+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0e50d-4790-7686-b8a9-7bfc858792a0:3de7d4601979d570aff52f036556d39a:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-4790-7686-b8a9-7bfc858792a0", "window_hash": "3de7d4601979d570aff52f036556d39a"}', 100, 'obsolete', 1, '2026-09-27 22:47:29.514544+00', NULL, NULL, '2026-09-27 22:47:29.514544+00', '2026-09-27 22:47:30.636753+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0e50d-544e-79de-895a-8775562ae846:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-544e-79de-895a-8775562ae846"}', 150, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.728641+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0e50d-544d-79ce-988c-c88011b887d6:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-544d-79ce-988c-c88011b887d6"}', 150, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.767546+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0e50d-544c-7b0c-a548-d307424ae19e:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-544c-7b0c-a548-d307424ae19e"}', 150, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.787164+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0e50d-544c-7014-a344-b4a7f86bd831:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-544c-7014-a344-b4a7f86bd831"}', 150, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.806116+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0e50d-544b-7c1b-b384-f5197fc2862d:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-544b-7c1b-b384-f5197fc2862d"}', 150, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.824403+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0e50d-544e-79de-895a-8775562ae846:a9574d56ee4aa73843e580b2c5690452:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-544e-79de-895a-8775562ae846", "window_hash": "a9574d56ee4aa73843e580b2c5690452"}', 200, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.847016+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0e50d-544d-79ce-988c-c88011b887d6:570d67d3883025674ae56ff878f1300f:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-544d-79ce-988c-c88011b887d6", "window_hash": "570d67d3883025674ae56ff878f1300f"}', 200, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.867856+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0e50d-544c-7014-a344-b4a7f86bd831:9e4b26d9781684de9abecfef1a44cb2a:extract-de532d894a86bf0cd75dd4831f040c9b', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "extract-de532d894a86bf0cd75dd4831f040c9b", "revision_id": "01a0e50d-544c-7014-a344-b4a7f86bd831", "window_hash": "9e4b26d9781684de9abecfef1a44cb2a"}', 200, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.88861+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0e50d-544f-762e-a70a-42267e86fb61:embed-7e9d78b207db2cb4bc407bb153c910c8', '01a0e50d-5446-7365-af2f-6dc779076142', '{"generation": "embed-7e9d78b207db2cb4bc407bb153c910c8", "revision_id": "01a0e50d-544f-762e-a70a-42267e86fb61"}', 150, 'done', 1, '2026-09-27 22:47:31.146971+00', NULL, NULL, '2026-09-27 22:47:31.146971+00', '2026-09-27 22:47:31.707258+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0e50d-475c-731a-8713-d57149d485a3', '01a0e50d-474e-7801-af89-7da0a33c9bdf');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-de532d894a86bf0cd75dd4831f040c9b', 'extract', 'stub', 'http://127.0.0.1:40295/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "3c80e6a1b8b262a4", "compiler": "extract-v12", "endpoint": "http://127.0.0.1:40295/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "c17fde3c9948898d", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-27 22:47:27.744414+00', '2026-09-27 22:47:27.745576+00');
INSERT INTO public.projection_generation VALUES ('embed-7e9d78b207db2cb4bc407bb153c910c8', 'embed', 'stub-embed', 'http://127.0.0.1:40295/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:40295/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-27 22:47:27.744414+00', '2026-09-27 22:47:27.749211+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0e50d-4783-7a63-92de-95c14068efb4', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '01a0e50d-475d-723d-8a09-0ca7b9d03335', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e50d-4759-7cc1-997b-115ad4c2cb98", "host_logical_id": "146cfad5-a2e7-43f0-81b4-9ef2f8e134d5"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e50d-4759-7cc1-997b-115ad4c2cb98", "host_logical_id": "146cfad5-a2e7-43f0-81b4-9ef2f8e134d5"}]', 0, '{"fit": 0.0, "embed": 23.06, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 1.94, "fits_at": null, "lexical": 3.36, "threads": 0, "extractor": "extract-de532d894a86", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 32.25, "embedding_projection": "embed-7e9d78b207db2c", "memory_mode_withheld": 0}', 'fresh', '2026-09-27 22:47:27.84341+00', 'packet-v4', 600, 3, '', '["146cfad5-a2e7-43f0-81b4-9ef2f8e134d5", "76ed04e3-4e7e-4df2-ba97-2a1825899d39", "a060144d-8d75-4374-95ae-308df5760366", "e1c2f23e-2bb6-42fe-9093-50c04f78fa85"]', 'extract-de532d894a86bf0cd75dd4831f040c9b', 'embed-7e9d78b207db2cb4bc407bb153c910c8', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e50d-47ad-774d-a16b-a7871785b520', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '01a0e50d-475d-723d-8a09-0ca7b9d03335', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e50d-4790-79d9-ad06-8ea8d9240cdd", "host_logical_id": "78851a2a-232e-404e-977a-cc20c0848d15"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e50d-4790-79d9-ad06-8ea8d9240cdd", "host_logical_id": "78851a2a-232e-404e-977a-cc20c0848d15"}]', 0, '{"fit": 0.0, "embed": 14.25, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 0.86, "fits_at": null, "lexical": 2.27, "threads": 0, "extractor": "extract-de532d894a86", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.85, "embedding_projection": "embed-7e9d78b207db2c", "memory_mode_withheld": 0}', 'fresh', '2026-09-27 22:47:27.897206+00', 'packet-v4', 600, 7, '', '["00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "2b9c6209-3972-4f5c-b050-04bfdf938cc5", "78851a2a-232e-404e-977a-cc20c0848d15", "860407f5-66be-4293-aaa3-e31c07b5e6e7"]', 'extract-de532d894a86bf0cd75dd4831f040c9b', 'embed-7e9d78b207db2cb4bc407bb153c910c8', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e50d-47d4-7eaa-90a1-c947626ed60b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '01a0e50d-475d-723d-8a09-0ca7b9d03335', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e50d-47b7-715a-a482-d44e57848c9b", "host_logical_id": "af37fd99-2f07-4511-9c1d-d69359f38f5a"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e50d-47b7-715a-a482-d44e57848c9b", "host_logical_id": "af37fd99-2f07-4511-9c1d-d69359f38f5a"}]', 0, '{"fit": 0.0, "embed": 13.75, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 0.8, "fits_at": null, "lexical": 2.57, "threads": 0, "extractor": "extract-de532d894a86", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.48, "embedding_projection": "embed-7e9d78b207db2c", "memory_mode_withheld": 0}', 'fresh', '2026-09-27 22:47:27.936702+00', 'packet-v4', 600, 11, '', '["69393859-90ab-4e84-a98e-25d03648cdf9", "736129b9-7145-400f-80d0-e6b5cd5b2b89", "af37fd99-2f07-4511-9c1d-d69359f38f5a", "b00c75a0-8b47-4ff6-b18f-934633a0ef40"]', 'extract-de532d894a86bf0cd75dd4831f040c9b', 'embed-7e9d78b207db2cb4bc407bb153c910c8', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e50d-47fa-7a44-8ed5-27632512884e', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '01a0e50d-475d-723d-8a09-0ca7b9d03335', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e50d-47de-727f-977f-1f0503a07055", "host_logical_id": "1f954246-d0d1-4729-8392-347861a1a036"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0e50d-475a-7dc2-9f79-79e77d7f3536", "host_logical_id": "76ed04e3-4e7e-4df2-ba97-2a1825899d39"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0e50d-4758-7c15-a79e-a1ca327d4b0d", "host_logical_id": "e1c2f23e-2bb6-42fe-9093-50c04f78fa85"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0e50d-4758-7c15-a79e-a1ca327d4b0d"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e50d-475a-7dc2-9f79-79e77d7f3536"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e50d-47de-727f-977f-1f0503a07055", "host_logical_id": "1f954246-d0d1-4729-8392-347861a1a036"}]', 174, '{"fit": 0.0, "embed": 14.35, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 0.88, "fits_at": null, "lexical": 2.78, "threads": 0, "extractor": "extract-de532d894a86", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.6, "embedding_projection": "embed-7e9d78b207db2c", "memory_mode_withheld": 0}', 'fresh', '2026-09-27 22:47:27.973739+00', 'packet-v4', 600, 12, '', '["1f954246-d0d1-4729-8392-347861a1a036", "69393859-90ab-4e84-a98e-25d03648cdf9", "736129b9-7145-400f-80d0-e6b5cd5b2b89", "af37fd99-2f07-4511-9c1d-d69359f38f5a"]', 'extract-de532d894a86bf0cd75dd4831f040c9b', 'embed-7e9d78b207db2cb4bc407bb153c910c8', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e50d-475a-7dc2-9f79-79e77d7f3536"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 3, "placed": true}, {"ref": {"revision": "01a0e50d-4758-7c15-a79e-a1ca327d4b0d"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e50d-4e09-78f4-85d7-0ada50a42924', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '01a0e50d-4def-7fee-8797-d5412d736ec0', 'And the compass?', '[{"rrf": 0.03151, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0e50d-47b6-7555-96ec-f071c998443f", "host_logical_id": "69393859-90ab-4e84-a98e-25d03648cdf9"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e50d-4dec-7921-8ae5-6a4cbffede94", "host_logical_id": "7b425248-121d-489b-8207-0979cc4c1508"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0e50d-4758-7c15-a79e-a1ca327d4b0d", "host_logical_id": "e1c2f23e-2bb6-42fe-9093-50c04f78fa85"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0e50d-4756-78a9-8026-38c45c4ab013", "host_logical_id": "a060144d-8d75-4374-95ae-308df5760366"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0e50d-4790-7686-b8a9-7bfc858792a0", "host_logical_id": "00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0e50d-4756-78a9-8026-38c45c4ab013"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0e50d-4758-7c15-a79e-a1ca327d4b0d"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0e50d-4790-7686-b8a9-7bfc858792a0"}, {"turn": 9, "score": 0.03151, "revision_id": "01a0e50d-47b6-7555-96ec-f071c998443f"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e50d-4dec-7921-8ae5-6a4cbffede94", "host_logical_id": "7b425248-121d-489b-8207-0979cc4c1508"}]', 223, '{"fit": 0.0, "embed": 15.21, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 4}, "vector": 1.0, "fits_at": null, "lexical": 2.55, "threads": 0, "extractor": "extract-de532d894a86", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 21.32, "embedding_projection": "embed-7e9d78b207db2c", "memory_mode_withheld": 0}', 'fresh', '2026-09-27 22:47:29.524161+00', 'packet-v4', 600, 14, '', '["1f954246-d0d1-4729-8392-347861a1a036", "736129b9-7145-400f-80d0-e6b5cd5b2b89", "7b425248-121d-489b-8207-0979cc4c1508", "d5abcb2b-91fe-457b-894e-e364e66288ab"]', 'extract-de532d894a86bf0cd75dd4831f040c9b', 'embed-7e9d78b207db2cb4bc407bb153c910c8', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e50d-47b6-7555-96ec-f071c998443f"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e50d-4758-7c15-a79e-a1ca327d4b0d"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}, {"ref": {"revision": "01a0e50d-4756-78a9-8026-38c45c4ab013"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a0e50d-4790-7686-b8a9-7bfc858792a0"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 7, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e50d-4e30-7ab2-86cc-cf1f888f1f78', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '01a0e50d-4def-7fee-8797-d5412d736ec0', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0e50d-47b6-7555-96ec-f071c998443f", "host_logical_id": "69393859-90ab-4e84-a98e-25d03648cdf9"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e50d-4dec-7921-8ae5-6a4cbffede94", "host_logical_id": "7b425248-121d-489b-8207-0979cc4c1508"}, {"rrf": 0.01639, "sim": 0.5799, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0e50d-478f-78a7-b3cf-8df717607ebc", "host_logical_id": "860407f5-66be-4293-aaa3-e31c07b5e6e7"}, {"rrf": 0.01613, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0e50d-47b8-7ca2-9d1d-384eea54c8e6", "host_logical_id": "736129b9-7145-400f-80d0-e6b5cd5b2b89"}]', '[{"turn": 5, "score": 0.01639, "revision_id": "01a0e50d-478f-78a7-b3cf-8df717607ebc"}, {"turn": 9, "score": 0.03002, "revision_id": "01a0e50d-47b6-7555-96ec-f071c998443f"}, {"turn": 11, "score": 0.01613, "revision_id": "01a0e50d-47b8-7ca2-9d1d-384eea54c8e6"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e50d-4dec-7921-8ae5-6a4cbffede94", "host_logical_id": "7b425248-121d-489b-8207-0979cc4c1508"}]', 200, '{"fit": 0.0, "embed": 13.7, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 3}, "vector": 0.99, "fits_at": null, "lexical": 3.39, "threads": 0, "extractor": "extract-de532d894a86", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 21.49, "embedding_projection": "embed-7e9d78b207db2c", "memory_mode_withheld": 0}', 'fresh', '2026-09-27 22:47:29.562751+00', 'packet-v4', 600, 15, '', '["1f954246-d0d1-4729-8392-347861a1a036", "412076cb-caff-48ba-9221-38fbca3bf2af", "7b425248-121d-489b-8207-0979cc4c1508", "d5abcb2b-91fe-457b-894e-e364e66288ab"]', 'extract-de532d894a86bf0cd75dd4831f040c9b', 'embed-7e9d78b207db2cb4bc407bb153c910c8', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e50d-47b6-7555-96ec-f071c998443f"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e50d-478f-78a7-b3cf-8df717607ebc"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Yuuma to return before the bell rings.", "turn": 5, "placed": true}, {"ref": {"revision": "01a0e50d-47b8-7ca2-9d1d-384eea54c8e6"}, "tok": 24, "why": "placed", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 11, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e50d-4e59-758a-9f59-2bd368f41492', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0e50d-4790-79d9-ad06-8ea8d9240cdd", "host_logical_id": "78851a2a-232e-404e-977a-cc20c0848d15"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e50d-4e3c-771a-9952-5ae7feb5fbb0", "host_logical_id": "340cf8b5-f9a3-46f3-92ee-49e72570a9b0"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0e50d-4790-79d9-ad06-8ea8d9240cdd"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e50d-4e3c-771a-9952-5ae7feb5fbb0", "host_logical_id": "340cf8b5-f9a3-46f3-92ee-49e72570a9b0"}]', 138, '{"fit": 0.0, "embed": 15.34, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1}, "vector": 1.0, "fits_at": null, "lexical": 1.87, "threads": 0, "extractor": "extract-de532d894a86", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.51, "embedding_projection": "embed-7e9d78b207db2c", "memory_mode_withheld": 0}', 'fresh', '2026-09-27 22:47:29.60524+00', 'packet-v4', 600, 16, '', '["340cf8b5-f9a3-46f3-92ee-49e72570a9b0", "412076cb-caff-48ba-9221-38fbca3bf2af", "7b425248-121d-489b-8207-0979cc4c1508", "d5abcb2b-91fe-457b-894e-e364e66288ab"]', 'extract-de532d894a86bf0cd75dd4831f040c9b', 'embed-7e9d78b207db2cb4bc407bb153c910c8', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e50d-4790-79d9-ad06-8ea8d9240cdd"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 6, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e50d-546c-755b-ae96-d421915fb1e0', '01a0e50d-5446-7365-af2f-6dc779076142', '01a0e50d-5451-7c73-a2b1-44a31d3afadb', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0e50d-544c-7b0c-a548-d307424ae19e", "host_logical_id": "b6703e73-33d8-4fd3-a45b-e0bcbd82b1e0"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0e50d-544d-79ce-988c-c88011b887d6", "host_logical_id": "7dad2adb-0e12-4157-b53a-79f1a8d8dd11"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0e50d-544c-7b0c-a548-d307424ae19e"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e50d-544d-79ce-988c-c88011b887d6"}]', '[]', 164, '{"fit": 0.0, "embed": 16.21, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 0.77, "fits_at": null, "lexical": 2.41, "threads": 0, "extractor": "extract-de532d894a86", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 21.65, "embedding_projection": "embed-7e9d78b207db2c", "memory_mode_withheld": 0}', 'fresh', '2026-09-27 22:47:31.158473+00', 'packet-v4', 600, 7, '', '["1d7bfe39-ac73-4327-a87a-218ddfdfbc86", "b10d2faa-12f5-4e4c-9a32-90707682f720", "bfaf0ed8-191b-4bdc-ba49-22948c2f25ea", "e95a1ba6-228c-468e-b0a5-dfab0d4a5ed2"]', 'extract-de532d894a86bf0cd75dd4831f040c9b', 'embed-7e9d78b207db2cb4bc407bb153c910c8', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e50d-544c-7b0c-a548-d307424ae19e"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 2, "placed": true}, {"ref": {"revision": "01a0e50d-544d-79ce-988c-c88011b887d6"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 3, "placed": true}]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0e50d-47de-727f-977f-1f0503a07055', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.038167+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-47b8-7ca2-9d1d-384eea54c8e6', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.060584+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-47b7-715a-a482-d44e57848c9b', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.081366+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-47b6-7555-96ec-f071c998443f', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.1042+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-47b5-7014-b256-efa5a177cf63', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.123636+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4790-7686-b8a9-7bfc858792a0', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.142975+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4790-79d9-ad06-8ea8d9240cdd', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.16255+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-478f-78a7-b3cf-8df717607ebc', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.181587+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-478e-73d1-b69f-ac286a2d7dde', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.202236+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-475a-7dc2-9f79-79e77d7f3536', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.225711+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4759-7cc1-997b-115ad4c2cb98', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.360408+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4758-7c15-a79e-a1ca327d4b0d', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.380198+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4756-78a9-8026-38c45c4ab013', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:29.399295+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4e3c-771a-9952-5ae7feb5fbb0', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:30.45481+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4e3b-7a49-b01e-0b824500e4d2', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:30.473127+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4dec-7921-8ae5-6a4cbffede94', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:30.492368+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4dec-77e0-9a52-b08e903b58c0', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:30.510519+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-4deb-7f64-98bc-c773a6101ef4', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:30.529337+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-544f-762e-a70a-42267e86fb61', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:31.705793+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-544e-79de-895a-8775562ae846', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:31.727216+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-544d-777a-837a-d6f81157d4ff', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:31.747602+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-544d-79ce-988c-c88011b887d6', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:31.766189+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-544c-7b0c-a548-d307424ae19e', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:31.785781+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-544c-7014-a344-b4a7f86bd831', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:31.804702+00');
INSERT INTO public.revision_embedding VALUES ('01a0e50d-544b-7c1b-b384-f5197fc2862d', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-7e9d78b207db2cb4bc407bb153c910c8', '2026-09-27 22:47:31.823064+00');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0e50d-4756-78a9-8026-38c45c4ab013', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-27 22:47:27.829337+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4758-7c15-a79e-a1ca327d4b0d', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-27 22:47:27.829337+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4759-7cc1-997b-115ad4c2cb98', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-27 22:47:27.829337+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-475a-7dc2-9f79-79e77d7f3536', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-27 22:47:27.829337+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-478e-73d1-b69f-ac286a2d7dde', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-27 22:47:27.885159+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-478f-78a7-b3cf-8df717607ebc', 'clean-v3', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-27 22:47:27.885159+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4790-79d9-ad06-8ea8d9240cdd', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-09-27 22:47:27.885159+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4790-7686-b8a9-7bfc858792a0', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-27 22:47:27.885159+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-47b5-7014-b256-efa5a177cf63', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-27 22:47:27.925133+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-47b6-7555-96ec-f071c998443f', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-27 22:47:27.925133+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-47b7-715a-a482-d44e57848c9b', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-09-27 22:47:27.925133+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-47b8-7ca2-9d1d-384eea54c8e6', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-09-27 22:47:27.925133+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-47de-727f-977f-1f0503a07055', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-09-27 22:47:27.96505+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4deb-7f64-98bc-c773a6101ef4', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-27 22:47:29.514544+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4dec-77e0-9a52-b08e903b58c0', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-09-27 22:47:29.514544+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4dec-7921-8ae5-6a4cbffede94', 'clean-v3', 'And the compass?', 16, 16, '2026-09-27 22:47:29.514544+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4e14-7b64-9d25-549e481e2306', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-27 22:47:29.555249+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4e3b-7e59-b3cc-766a0e2c4605', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-27 22:47:29.594079+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4e3b-7a49-b01e-0b824500e4d2', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-09-27 22:47:29.594079+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-4e3c-771a-9952-5ae7feb5fbb0', 'clean-v3', 'Let''s go.', 9, 9, '2026-09-27 22:47:29.594079+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-544b-7c1b-b384-f5197fc2862d', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-27 22:47:31.146971+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-544c-7014-a344-b4a7f86bd831', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-27 22:47:31.146971+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-544c-7b0c-a548-d307424ae19e', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-27 22:47:31.146971+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-544d-79ce-988c-c88011b887d6', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-27 22:47:31.146971+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-544d-777a-837a-d6f81157d4ff', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-27 22:47:31.146971+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-544e-79de-895a-8775562ae846', 'clean-v3', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-27 22:47:31.146971+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-544f-793a-b4e9-14e987935b6a', 'clean-v3', '{{specialcomment::branchedfrom::9135e722-f916-40e5-83f8-a6ea007df4a1::Harbor route::860407f5-66be-4293-aaa3-e31c07b5e6e7::}}', 124, 124, '2026-09-27 22:47:31.146971+00');
INSERT INTO public.revision_text VALUES ('01a0e50d-544f-762e-a70a-42267e86fb61', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-09-27 22:47:31.146971+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-27 22:47:26.685142+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-27 22:47:26.767678+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-27 22:47:26.783964+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-27 22:47:26.829938+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-27 22:47:26.851123+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-27 22:47:26.860482+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-27 22:47:26.862747+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-27 22:47:26.872903+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-27 22:47:26.890212+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-27 22:47:26.892313+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-27 22:47:26.894072+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-27 22:47:26.903477+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-27 22:47:26.928236+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-27 22:47:26.94485+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-27 22:47:26.947782+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-27 22:47:26.960497+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-27 22:47:26.962762+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-27 22:47:26.964681+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-09-27 22:47:26.966425+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-09-27 22:47:26.979403+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-09-27 22:47:26.98176+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0e50d-4755-741d-af25-a7dafdf9000f', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'a060144d-8d75-4374-95ae-308df5760366', 'message', '2026-09-27 22:47:27.829337+00');
INSERT INTO public.source_object VALUES ('01a0e50d-4758-72e5-a216-8b3f08ce2c0a', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'e1c2f23e-2bb6-42fe-9093-50c04f78fa85', 'message', '2026-09-27 22:47:27.829337+00');
INSERT INTO public.source_object VALUES ('01a0e50d-4758-70ef-b0ec-1bc666f6abbd', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '146cfad5-a2e7-43f0-81b4-9ef2f8e134d5', 'message', '2026-09-27 22:47:27.829337+00');
INSERT INTO public.source_object VALUES ('01a0e50d-475a-7fa1-a12e-f486e61591ff', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '76ed04e3-4e7e-4df2-ba97-2a1825899d39', 'message', '2026-09-27 22:47:27.829337+00');
INSERT INTO public.source_object VALUES ('01a0e50d-478d-7f1f-8d3d-c4471d4264d1', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '2b9c6209-3972-4f5c-b050-04bfdf938cc5', 'message', '2026-09-27 22:47:27.885159+00');
INSERT INTO public.source_object VALUES ('01a0e50d-478e-7c26-b211-3f10a5e29bb6', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '860407f5-66be-4293-aaa3-e31c07b5e6e7', 'message', '2026-09-27 22:47:27.885159+00');
INSERT INTO public.source_object VALUES ('01a0e50d-478f-7715-a01d-5e94bb80f31e', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '78851a2a-232e-404e-977a-cc20c0848d15', 'message', '2026-09-27 22:47:27.885159+00');
INSERT INTO public.source_object VALUES ('01a0e50d-4790-7170-9208-dc6d7904e8cb', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7', 'message', '2026-09-27 22:47:27.885159+00');
INSERT INTO public.source_object VALUES ('01a0e50d-47b5-7fa7-bcd0-74d9e513c088', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'b00c75a0-8b47-4ff6-b18f-934633a0ef40', 'message', '2026-09-27 22:47:27.925133+00');
INSERT INTO public.source_object VALUES ('01a0e50d-47b6-7534-9a46-5ebb5b3c2e75', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '69393859-90ab-4e84-a98e-25d03648cdf9', 'message', '2026-09-27 22:47:27.925133+00');
INSERT INTO public.source_object VALUES ('01a0e50d-47b7-7a7e-b97a-bbd30a84d1aa', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'af37fd99-2f07-4511-9c1d-d69359f38f5a', 'message', '2026-09-27 22:47:27.925133+00');
INSERT INTO public.source_object VALUES ('01a0e50d-47b8-7374-938c-c472e7e79add', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '736129b9-7145-400f-80d0-e6b5cd5b2b89', 'message', '2026-09-27 22:47:27.925133+00');
INSERT INTO public.source_object VALUES ('01a0e50d-47dd-7038-8de7-a0722cf4f07b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '1f954246-d0d1-4729-8392-347861a1a036', 'message', '2026-09-27 22:47:27.96505+00');
INSERT INTO public.source_object VALUES ('01a0e50d-4deb-7e5c-b89a-4ae50f32e301', '01a0e50d-474e-7801-af89-7da0a33c9bdf', 'd5abcb2b-91fe-457b-894e-e364e66288ab', 'message', '2026-09-27 22:47:29.514544+00');
INSERT INTO public.source_object VALUES ('01a0e50d-4dec-72ea-89ab-0fb1a42827ec', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '7b425248-121d-489b-8207-0979cc4c1508', 'message', '2026-09-27 22:47:29.514544+00');
INSERT INTO public.source_object VALUES ('01a0e50d-4e13-7986-a3b2-8cca939baa5b', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '412076cb-caff-48ba-9221-38fbca3bf2af', 'message', '2026-09-27 22:47:29.555249+00');
INSERT INTO public.source_object VALUES ('01a0e50d-4e3c-7f08-aad4-7d26aca1dbfd', '01a0e50d-474e-7801-af89-7da0a33c9bdf', '340cf8b5-f9a3-46f3-92ee-49e72570a9b0', 'message', '2026-09-27 22:47:29.594079+00');
INSERT INTO public.source_object VALUES ('01a0e50d-544b-7b3f-9e74-12c029bfc630', '01a0e50d-5446-7365-af2f-6dc779076142', 'afeb64d1-3b1d-40a5-a418-6a9c516beb3a', 'message', '2026-09-27 22:47:31.146971+00');
INSERT INTO public.source_object VALUES ('01a0e50d-544c-7471-a018-5c1fc73d1f50', '01a0e50d-5446-7365-af2f-6dc779076142', '83909bd8-7e3b-4223-9ffd-ca3b4eecfdff', 'message', '2026-09-27 22:47:31.146971+00');
INSERT INTO public.source_object VALUES ('01a0e50d-544c-7d7a-a36a-62b397020e9f', '01a0e50d-5446-7365-af2f-6dc779076142', 'b6703e73-33d8-4fd3-a45b-e0bcbd82b1e0', 'message', '2026-09-27 22:47:31.146971+00');
INSERT INTO public.source_object VALUES ('01a0e50d-544d-7627-b4f5-b06a5a578ffe', '01a0e50d-5446-7365-af2f-6dc779076142', '7dad2adb-0e12-4157-b53a-79f1a8d8dd11', 'message', '2026-09-27 22:47:31.146971+00');
INSERT INTO public.source_object VALUES ('01a0e50d-544d-75cd-8a7d-0eddc796e19d', '01a0e50d-5446-7365-af2f-6dc779076142', 'e95a1ba6-228c-468e-b0a5-dfab0d4a5ed2', 'message', '2026-09-27 22:47:31.146971+00');
INSERT INTO public.source_object VALUES ('01a0e50d-544e-79ba-aadc-39d5417c847a', '01a0e50d-5446-7365-af2f-6dc779076142', '1d7bfe39-ac73-4327-a87a-218ddfdfbc86', 'message', '2026-09-27 22:47:31.146971+00');
INSERT INTO public.source_object VALUES ('01a0e50d-544e-7c65-8a52-d754559010ad', '01a0e50d-5446-7365-af2f-6dc779076142', 'bfaf0ed8-191b-4bdc-ba49-22948c2f25ea', 'message', '2026-09-27 22:47:31.146971+00');
INSERT INTO public.source_object VALUES ('01a0e50d-544f-7f91-a36f-c94fc908eb1c', '01a0e50d-5446-7365-af2f-6dc779076142', 'b10d2faa-12f5-4e4c-9a32-90707682f720', 'message', '2026-09-27 22:47:31.146971+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0e50d-4756-78a9-8026-38c45c4ab013', '01a0e50d-4755-741d-af25-a7dafdf9000f', '96ddf919be36476491778386d3f09ab5d62ac59ca7c1b38612f82dbe52e5c5b3', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "a060144d-8d75-4374-95ae-308df5760366", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:27.829337+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4759-7cc1-997b-115ad4c2cb98', '01a0e50d-4758-70ef-b0ec-1bc666f6abbd', '766cd4f9855fca81b403949fbaf46cb70cfae9d7091200059c76950dde1f22e9', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "146cfad5-a2e7-43f0-81b4-9ef2f8e134d5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:27.829337+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4758-7c15-a79e-a1ca327d4b0d', '01a0e50d-4758-72e5-a216-8b3f08ce2c0a', 'f09b274b86309f927942511a56ee2ec50db1ec863dc36f82dcc26917cf03b999', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "e1c2f23e-2bb6-42fe-9093-50c04f78fa85", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e1c2f23e-2bb6-42fe-9093-50c04f78fa85", "specialComments": []}', '2026-09-27 22:47:27.829337+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-478e-73d1-b69f-ac286a2d7dde', '01a0e50d-478d-7f1f-8d3d-c4471d4264d1', '2f69ee9eb657bd0cdf89ac86858bfc4151acd8b3258f7b97f617d64d93c6f04d', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "2b9c6209-3972-4f5c-b050-04bfdf938cc5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:27.885159+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4790-79d9-ad06-8ea8d9240cdd', '01a0e50d-478f-7715-a01d-5e94bb80f31e', '64be4db5059633c4e1a697a08b050237fd0c95e5b227ad8f8103ff5c0f154666', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "78851a2a-232e-404e-977a-cc20c0848d15", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:27.885159+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-47b5-7014-b256-efa5a177cf63', '01a0e50d-47b5-7fa7-bcd0-74d9e513c088', 'f538f16d9a5fab2b5739cc9a564938509f9808efdb3e93f111ab5c1170980f4b', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "b00c75a0-8b47-4ff6-b18f-934633a0ef40", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:27.925133+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-478f-78a7-b3cf-8df717607ebc', '01a0e50d-478e-7c26-b211-3f10a5e29bb6', '622602feb18e9ad6ccd3722a363fe76aa8b00351a6e8d479130592d4e44e4bae', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "860407f5-66be-4293-aaa3-e31c07b5e6e7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "860407f5-66be-4293-aaa3-e31c07b5e6e7", "specialComments": []}', '2026-09-27 22:47:27.885159+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-47b7-715a-a482-d44e57848c9b', '01a0e50d-47b7-7a7e-b97a-bbd30a84d1aa', '9a5b4d71394a1ef5066a51609aa5ca53c7d287a2250a7edba96cc05af6ae3859', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "af37fd99-2f07-4511-9c1d-d69359f38f5a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:27.925133+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4790-7686-b8a9-7bfc858792a0', '01a0e50d-4790-7170-9208-dc6d7904e8cb', 'c7529e7693ac8212b08b2163b62859f9e08a151c40fd0d53cb5cba4a1a332d9b', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "specialComments": []}', '2026-09-27 22:47:27.885159+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-47b6-7555-96ec-f071c998443f', '01a0e50d-47b6-7534-9a46-5ebb5b3c2e75', '729739b4fc6ebbbdc15a08d856f91eeb42fb42c54d3aa588dcc0d381c88793a9', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "69393859-90ab-4e84-a98e-25d03648cdf9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "69393859-90ab-4e84-a98e-25d03648cdf9", "specialComments": []}', '2026-09-27 22:47:27.925133+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-47de-727f-977f-1f0503a07055', '01a0e50d-47dd-7038-8de7-a0722cf4f07b', 'c19544c36e9a787fc6ad1969b93643a321eafabbfdee78b259d240f446906ee6', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "1f954246-d0d1-4729-8392-347861a1a036", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:27.96505+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-47b8-7ca2-9d1d-384eea54c8e6', '01a0e50d-47b8-7374-938c-c472e7e79add', 'eb1658873ddd1daf70b210de2f1e830ea3fdd0721696de5e25359fdf7aa8fac9', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "736129b9-7145-400f-80d0-e6b5cd5b2b89", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "736129b9-7145-400f-80d0-e6b5cd5b2b89", "specialComments": []}', '2026-09-27 22:47:27.925133+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4dec-7921-8ae5-6a4cbffede94', '01a0e50d-4dec-72ea-89ab-0fb1a42827ec', '4eed7de0f0305536c463024e1cb42ad4fb081cffbce9bbdf2ed61970e7d265db', 'And the compass?', '{"name": null, "role": "user", "chatId": "7b425248-121d-489b-8207-0979cc4c1508", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:29.514544+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-475a-7dc2-9f79-79e77d7f3536', '01a0e50d-475a-7fa1-a12e-f486e61591ff', '315367c14657cd6b70ec76dd5bc80f0a0486ce0084b01a854852b697786084ba', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "76ed04e3-4e7e-4df2-ba97-2a1825899d39", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "76ed04e3-4e7e-4df2-ba97-2a1825899d39", "specialComments": []}', '2026-09-27 22:47:27.829337+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4deb-7f64-98bc-c773a6101ef4', '01a0e50d-475a-7fa1-a12e-f486e61591ff', 'b6ea8fb28e8857625f4e54103dbc4524dc21710f5d499253dd6af5ec362e3c93', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "76ed04e3-4e7e-4df2-ba97-2a1825899d39", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "76ed04e3-4e7e-4df2-ba97-2a1825899d39", "specialComments": []}', '2026-09-27 22:47:29.514544+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4dec-77e0-9a52-b08e903b58c0', '01a0e50d-4deb-7e5c-b89a-4ae50f32e301', '1d414c5fb1561e09277bf77610e37221c8921a871872df60efec79ff163141ad', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "d5abcb2b-91fe-457b-894e-e364e66288ab", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "d5abcb2b-91fe-457b-894e-e364e66288ab", "specialComments": []}', '2026-09-27 22:47:29.514544+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4e3b-7e59-b3cc-766a0e2c4605', '01a0e50d-47b5-7fa7-bcd0-74d9e513c088', 'fc6606ed3f4695640d0732042e5ff4d65676e65693b73efd1015c62bc2612ab2', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "b00c75a0-8b47-4ff6-b18f-934633a0ef40", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:29.594079+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4e3c-771a-9952-5ae7feb5fbb0', '01a0e50d-4e3c-7f08-aad4-7d26aca1dbfd', '9026e2e4bb8fb3318af9255a69c9848e4a7e4ea4a145e439f0ec15cf0291d865', 'Let''s go.', '{"name": null, "role": "user", "chatId": "340cf8b5-f9a3-46f3-92ee-49e72570a9b0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:29.594079+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4e3b-7a49-b01e-0b824500e4d2', '01a0e50d-4e13-7986-a3b2-8cca939baa5b', '22d3b215a6a43fff66e078a2bb32cb1560f5960d74c0e00e491a64a80a25f108', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "412076cb-caff-48ba-9221-38fbca3bf2af", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "412076cb-caff-48ba-9221-38fbca3bf2af", "specialComments": []}', '2026-09-27 22:47:29.594079+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-4e14-7b64-9d25-549e481e2306', '01a0e50d-4e13-7986-a3b2-8cca939baa5b', 'f5cc0ccce67eb7e912536c26d246154b3435365583608c321aa9324c557a26ea', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "412076cb-caff-48ba-9221-38fbca3bf2af", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "412076cb-caff-48ba-9221-38fbca3bf2af", "specialComments": []}', '2026-09-27 22:47:29.555249+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-544b-7c1b-b384-f5197fc2862d', '01a0e50d-544b-7b3f-9e74-12c029bfc630', 'eaf24a65d767200cba3296c1e541b92033ba503c21426885d22b7330a7f306bc', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "afeb64d1-3b1d-40a5-a418-6a9c516beb3a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:31.146971+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-544c-7b0c-a548-d307424ae19e', '01a0e50d-544c-7d7a-a36a-62b397020e9f', 'd2f5100dd028659b67a1292bb97bae5c45df66dcedcff740d12bfc7d478d7881', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "b6703e73-33d8-4fd3-a45b-e0bcbd82b1e0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:31.146971+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-544d-777a-837a-d6f81157d4ff', '01a0e50d-544d-75cd-8a7d-0eddc796e19d', '0f41ea07051721fc99370a4298177a6e1d3c4ff7e93aff303f939f074083ff0a', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "e95a1ba6-228c-468e-b0a5-dfab0d4a5ed2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:31.146971+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-544f-793a-b4e9-14e987935b6a', '01a0e50d-544e-7c65-8a52-d754559010ad', '326420ccbc56127e035909e7750038e7bde83499bc508504c4c6810a0c4c749c', '{{specialcomment::branchedfrom::9135e722-f916-40e5-83f8-a6ea007df4a1::Harbor route::860407f5-66be-4293-aaa3-e31c07b5e6e7::}}', '{"name": null, "role": "char", "chatId": "bfaf0ed8-191b-4bdc-ba49-22948c2f25ea", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::9135e722-f916-40e5-83f8-a6ea007df4a1::Harbor route::860407f5-66be-4293-aaa3-e31c07b5e6e7::}}"]}', '2026-09-27 22:47:31.146971+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-544f-762e-a70a-42267e86fb61', '01a0e50d-544f-7f91-a36f-c94fc908eb1c', '6c056ed63d766d0ad0d4b3d7fcc26201c52d1417231f4303d3a1c8479561e355', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "b10d2faa-12f5-4e4c-9a32-90707682f720", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 22:47:31.146971+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-544e-79de-895a-8775562ae846', '01a0e50d-544e-79ba-aadc-39d5417c847a', '8431eb49298514973c19d9576dd6f0784d29b251185951c8f81315d7829494f7', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "1d7bfe39-ac73-4327-a87a-218ddfdfbc86", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "860407f5-66be-4293-aaa3-e31c07b5e6e7", "specialComments": []}', '2026-09-27 22:47:31.146971+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-544d-79ce-988c-c88011b887d6', '01a0e50d-544d-7627-b4f5-b06a5a578ffe', '2d7d104f32c7c491c6d0d5ba4e23a7dd3869827c84ff4df58d49ff4fa28330ec', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "7dad2adb-0e12-4157-b53a-79f1a8d8dd11", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "76ed04e3-4e7e-4df2-ba97-2a1825899d39", "specialComments": []}', '2026-09-27 22:47:31.146971+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e50d-544c-7014-a344-b4a7f86bd831', '01a0e50d-544c-7471-a018-5c1fc73d1f50', '79f50ee67c002d1c1292c160de3b1608841d9c2d0d7129ece1f5dc59363c9798', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "83909bd8-7e3b-4223-9ffd-ca3b4eecfdff", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e1c2f23e-2bb6-42fe-9093-50c04f78fa85", "specialComments": []}', '2026-09-27 22:47:31.146971+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0e50d-475d-723d-8a09-0ca7b9d03335', '[{"op": "insert", "after": ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "315367c14657cd6b70ec76dd5bc80f0a0486ce0084b01a854852b697786084ba"], "member": ["2b9c6209-3972-4f5c-b050-04bfdf938cc5", "2f69ee9eb657bd0cdf89ac86858bfc4151acd8b3258f7b97f617d64d93c6f04d"]}, {"op": "insert", "after": ["2b9c6209-3972-4f5c-b050-04bfdf938cc5", "2f69ee9eb657bd0cdf89ac86858bfc4151acd8b3258f7b97f617d64d93c6f04d"], "member": ["860407f5-66be-4293-aaa3-e31c07b5e6e7", "622602feb18e9ad6ccd3722a363fe76aa8b00351a6e8d479130592d4e44e4bae"]}, {"op": "insert", "after": ["860407f5-66be-4293-aaa3-e31c07b5e6e7", "622602feb18e9ad6ccd3722a363fe76aa8b00351a6e8d479130592d4e44e4bae"], "member": ["78851a2a-232e-404e-977a-cc20c0848d15", "64be4db5059633c4e1a697a08b050237fd0c95e5b227ad8f8103ff5c0f154666"]}, {"op": "insert", "after": ["78851a2a-232e-404e-977a-cc20c0848d15", "64be4db5059633c4e1a697a08b050237fd0c95e5b227ad8f8103ff5c0f154666"], "member": ["00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "c7529e7693ac8212b08b2163b62859f9e08a151c40fd0d53cb5cba4a1a332d9b"]}]', '[{"new": ["2b9c6209-3972-4f5c-b050-04bfdf938cc5", "2f69ee9eb657bd0cdf89ac86858bfc4151acd8b3258f7b97f617d64d93c6f04d"], "old": null, "kind": "append", "position": 4, "host_logical_id": "2b9c6209-3972-4f5c-b050-04bfdf938cc5"}, {"new": ["860407f5-66be-4293-aaa3-e31c07b5e6e7", "622602feb18e9ad6ccd3722a363fe76aa8b00351a6e8d479130592d4e44e4bae"], "old": null, "kind": "append", "position": 5, "host_logical_id": "860407f5-66be-4293-aaa3-e31c07b5e6e7"}, {"new": ["78851a2a-232e-404e-977a-cc20c0848d15", "64be4db5059633c4e1a697a08b050237fd0c95e5b227ad8f8103ff5c0f154666"], "old": null, "kind": "append", "position": 6, "host_logical_id": "78851a2a-232e-404e-977a-cc20c0848d15"}, {"new": ["00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "c7529e7693ac8212b08b2163b62859f9e08a151c40fd0d53cb5cba4a1a332d9b"], "old": null, "kind": "append", "position": 7, "host_logical_id": "00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7"}]', '01a0e50d-4793-756f-b055-1702969ff4da', '2026-09-27 22:47:27.885159+00');
INSERT INTO public.worldline_append VALUES (2, '01a0e50d-475d-723d-8a09-0ca7b9d03335', '[{"op": "insert", "after": ["00dfcb33-6b9e-4173-b5e7-69b1c62d8dd7", "c7529e7693ac8212b08b2163b62859f9e08a151c40fd0d53cb5cba4a1a332d9b"], "member": ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "f538f16d9a5fab2b5739cc9a564938509f9808efdb3e93f111ab5c1170980f4b"]}, {"op": "insert", "after": ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "f538f16d9a5fab2b5739cc9a564938509f9808efdb3e93f111ab5c1170980f4b"], "member": ["69393859-90ab-4e84-a98e-25d03648cdf9", "729739b4fc6ebbbdc15a08d856f91eeb42fb42c54d3aa588dcc0d381c88793a9"]}, {"op": "insert", "after": ["69393859-90ab-4e84-a98e-25d03648cdf9", "729739b4fc6ebbbdc15a08d856f91eeb42fb42c54d3aa588dcc0d381c88793a9"], "member": ["af37fd99-2f07-4511-9c1d-d69359f38f5a", "9a5b4d71394a1ef5066a51609aa5ca53c7d287a2250a7edba96cc05af6ae3859"]}, {"op": "insert", "after": ["af37fd99-2f07-4511-9c1d-d69359f38f5a", "9a5b4d71394a1ef5066a51609aa5ca53c7d287a2250a7edba96cc05af6ae3859"], "member": ["736129b9-7145-400f-80d0-e6b5cd5b2b89", "eb1658873ddd1daf70b210de2f1e830ea3fdd0721696de5e25359fdf7aa8fac9"]}]', '[{"new": ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "f538f16d9a5fab2b5739cc9a564938509f9808efdb3e93f111ab5c1170980f4b"], "old": null, "kind": "append", "position": 8, "host_logical_id": "b00c75a0-8b47-4ff6-b18f-934633a0ef40"}, {"new": ["69393859-90ab-4e84-a98e-25d03648cdf9", "729739b4fc6ebbbdc15a08d856f91eeb42fb42c54d3aa588dcc0d381c88793a9"], "old": null, "kind": "append", "position": 9, "host_logical_id": "69393859-90ab-4e84-a98e-25d03648cdf9"}, {"new": ["af37fd99-2f07-4511-9c1d-d69359f38f5a", "9a5b4d71394a1ef5066a51609aa5ca53c7d287a2250a7edba96cc05af6ae3859"], "old": null, "kind": "append", "position": 10, "host_logical_id": "af37fd99-2f07-4511-9c1d-d69359f38f5a"}, {"new": ["736129b9-7145-400f-80d0-e6b5cd5b2b89", "eb1658873ddd1daf70b210de2f1e830ea3fdd0721696de5e25359fdf7aa8fac9"], "old": null, "kind": "append", "position": 11, "host_logical_id": "736129b9-7145-400f-80d0-e6b5cd5b2b89"}]', '01a0e50d-47ba-7051-9c63-9361ce6e2349', '2026-09-27 22:47:27.925133+00');
INSERT INTO public.worldline_append VALUES (3, '01a0e50d-475d-723d-8a09-0ca7b9d03335', '[{"op": "insert", "after": ["736129b9-7145-400f-80d0-e6b5cd5b2b89", "eb1658873ddd1daf70b210de2f1e830ea3fdd0721696de5e25359fdf7aa8fac9"], "member": ["1f954246-d0d1-4729-8392-347861a1a036", "c19544c36e9a787fc6ad1969b93643a321eafabbfdee78b259d240f446906ee6"]}]', '[{"new": ["1f954246-d0d1-4729-8392-347861a1a036", "c19544c36e9a787fc6ad1969b93643a321eafabbfdee78b259d240f446906ee6"], "old": null, "kind": "append", "position": 12, "host_logical_id": "1f954246-d0d1-4729-8392-347861a1a036"}]', '01a0e50d-47e1-73f6-8642-bbea8f83f0e2', '2026-09-27 22:47:27.96505+00');
INSERT INTO public.worldline_append VALUES (4, '01a0e50d-4def-7fee-8797-d5412d736ec0', '[{"op": "insert", "after": ["7b425248-121d-489b-8207-0979cc4c1508", "4eed7de0f0305536c463024e1cb42ad4fb081cffbce9bbdf2ed61970e7d265db"], "member": ["412076cb-caff-48ba-9221-38fbca3bf2af", "f5cc0ccce67eb7e912536c26d246154b3435365583608c321aa9324c557a26ea"]}]', '[{"new": ["412076cb-caff-48ba-9221-38fbca3bf2af", "f5cc0ccce67eb7e912536c26d246154b3435365583608c321aa9324c557a26ea"], "old": null, "kind": "append", "position": 15, "host_logical_id": "412076cb-caff-48ba-9221-38fbca3bf2af"}]', '01a0e50d-4e17-7698-aa19-bc2f11e52c87', '2026-09-27 22:47:29.555249+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e50d-475d-723d-8a09-0ca7b9d03335', 1, '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{}', 'import', '2e71b29f8bf1f3164969140d396f63892d67f9f1581e629755c813149f99bf5c', '{"ops": [{"op": "set", "members": [["a060144d-8d75-4374-95ae-308df5760366", "96ddf919be36476491778386d3f09ab5d62ac59ca7c1b38612f82dbe52e5c5b3"], ["e1c2f23e-2bb6-42fe-9093-50c04f78fa85", "f09b274b86309f927942511a56ee2ec50db1ec863dc36f82dcc26917cf03b999"], ["146cfad5-a2e7-43f0-81b4-9ef2f8e134d5", "766cd4f9855fca81b403949fbaf46cb70cfae9d7091200059c76950dde1f22e9"], ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "315367c14657cd6b70ec76dd5bc80f0a0486ce0084b01a854852b697786084ba"]]}], "changes": [{"new": ["a060144d-8d75-4374-95ae-308df5760366", "96ddf919be36476491778386d3f09ab5d62ac59ca7c1b38612f82dbe52e5c5b3"], "old": null, "kind": "append", "position": 0, "host_logical_id": "a060144d-8d75-4374-95ae-308df5760366"}, {"new": ["e1c2f23e-2bb6-42fe-9093-50c04f78fa85", "f09b274b86309f927942511a56ee2ec50db1ec863dc36f82dcc26917cf03b999"], "old": null, "kind": "append", "position": 1, "host_logical_id": "e1c2f23e-2bb6-42fe-9093-50c04f78fa85"}, {"new": ["146cfad5-a2e7-43f0-81b4-9ef2f8e134d5", "766cd4f9855fca81b403949fbaf46cb70cfae9d7091200059c76950dde1f22e9"], "old": null, "kind": "append", "position": 2, "host_logical_id": "146cfad5-a2e7-43f0-81b4-9ef2f8e134d5"}, {"new": ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "315367c14657cd6b70ec76dd5bc80f0a0486ce0084b01a854852b697786084ba"], "old": null, "kind": "append", "position": 3, "host_logical_id": "76ed04e3-4e7e-4df2-ba97-2a1825899d39"}]}', '2026-09-27 22:47:27.829337+00', '01a0e50d-475c-731a-8713-d57149d485a3');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e50d-4def-7fee-8797-d5412d736ec0', 2, '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{01a0e50d-475d-723d-8a09-0ca7b9d03335}', 'edit', 'd56bbfb87911d341b3bbc84ec79ab8945503b17884c0ac86456c779170c516c8', '{"ops": [{"op": "replace", "to": ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "b6ea8fb28e8857625f4e54103dbc4524dc21710f5d499253dd6af5ec362e3c93"], "from": ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "315367c14657cd6b70ec76dd5bc80f0a0486ce0084b01a854852b697786084ba"]}, {"op": "insert", "after": ["1f954246-d0d1-4729-8392-347861a1a036", "c19544c36e9a787fc6ad1969b93643a321eafabbfdee78b259d240f446906ee6"], "member": ["d5abcb2b-91fe-457b-894e-e364e66288ab", "1d414c5fb1561e09277bf77610e37221c8921a871872df60efec79ff163141ad"]}, {"op": "insert", "after": ["d5abcb2b-91fe-457b-894e-e364e66288ab", "1d414c5fb1561e09277bf77610e37221c8921a871872df60efec79ff163141ad"], "member": ["7b425248-121d-489b-8207-0979cc4c1508", "4eed7de0f0305536c463024e1cb42ad4fb081cffbce9bbdf2ed61970e7d265db"]}], "changes": [{"new": ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "b6ea8fb28e8857625f4e54103dbc4524dc21710f5d499253dd6af5ec362e3c93"], "old": ["76ed04e3-4e7e-4df2-ba97-2a1825899d39", "315367c14657cd6b70ec76dd5bc80f0a0486ce0084b01a854852b697786084ba"], "kind": "edit", "position": 3, "host_logical_id": "76ed04e3-4e7e-4df2-ba97-2a1825899d39"}, {"new": ["d5abcb2b-91fe-457b-894e-e364e66288ab", "1d414c5fb1561e09277bf77610e37221c8921a871872df60efec79ff163141ad"], "old": null, "kind": "append", "position": 13, "host_logical_id": "d5abcb2b-91fe-457b-894e-e364e66288ab"}, {"new": ["7b425248-121d-489b-8207-0979cc4c1508", "4eed7de0f0305536c463024e1cb42ad4fb081cffbce9bbdf2ed61970e7d265db"], "old": null, "kind": "append", "position": 14, "host_logical_id": "7b425248-121d-489b-8207-0979cc4c1508"}]}', '2026-09-27 22:47:29.514544+00', '01a0e50d-4dee-7d65-91cf-8868ee70f046');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e50d-4e3f-7418-ba39-bcd93ad99ae2', 3, '01a0e50d-474e-7801-af89-7da0a33c9bdf', '{01a0e50d-4def-7fee-8797-d5412d736ec0}', 'reconciliation', '3098e368a19edee9c922d6a9e3fafe43854bac3dfff763d427069a507f078482', '{"ops": [{"op": "replace", "to": ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "fc6606ed3f4695640d0732042e5ff4d65676e65693b73efd1015c62bc2612ab2"], "from": ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "f538f16d9a5fab2b5739cc9a564938509f9808efdb3e93f111ab5c1170980f4b"]}, {"op": "replace", "to": ["412076cb-caff-48ba-9221-38fbca3bf2af", "22d3b215a6a43fff66e078a2bb32cb1560f5960d74c0e00e491a64a80a25f108"], "from": ["412076cb-caff-48ba-9221-38fbca3bf2af", "f5cc0ccce67eb7e912536c26d246154b3435365583608c321aa9324c557a26ea"]}, {"op": "insert", "after": ["412076cb-caff-48ba-9221-38fbca3bf2af", "22d3b215a6a43fff66e078a2bb32cb1560f5960d74c0e00e491a64a80a25f108"], "member": ["340cf8b5-f9a3-46f3-92ee-49e72570a9b0", "9026e2e4bb8fb3318af9255a69c9848e4a7e4ea4a145e439f0ec15cf0291d865"]}], "changes": [{"new": ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "fc6606ed3f4695640d0732042e5ff4d65676e65693b73efd1015c62bc2612ab2"], "old": ["b00c75a0-8b47-4ff6-b18f-934633a0ef40", "f538f16d9a5fab2b5739cc9a564938509f9808efdb3e93f111ab5c1170980f4b"], "kind": "disable", "position": 8, "host_logical_id": "b00c75a0-8b47-4ff6-b18f-934633a0ef40"}, {"new": ["412076cb-caff-48ba-9221-38fbca3bf2af", "22d3b215a6a43fff66e078a2bb32cb1560f5960d74c0e00e491a64a80a25f108"], "old": ["412076cb-caff-48ba-9221-38fbca3bf2af", "f5cc0ccce67eb7e912536c26d246154b3435365583608c321aa9324c557a26ea"], "kind": "swipe", "position": 15, "host_logical_id": "412076cb-caff-48ba-9221-38fbca3bf2af"}, {"new": ["340cf8b5-f9a3-46f3-92ee-49e72570a9b0", "9026e2e4bb8fb3318af9255a69c9848e4a7e4ea4a145e439f0ec15cf0291d865"], "old": null, "kind": "append", "position": 16, "host_logical_id": "340cf8b5-f9a3-46f3-92ee-49e72570a9b0"}]}', '2026-09-27 22:47:29.594079+00', '01a0e50d-4e3e-7e21-84dc-f1ecf5cdac93');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e50d-5451-7c73-a2b1-44a31d3afadb', 4, '01a0e50d-5446-7365-af2f-6dc779076142', '{}', 'branch', '9f5220f03a3ad6a9907717655c27ec6c4d17490abab488e0359c25c1f17c04b7', '{"ops": [{"op": "set", "members": [["afeb64d1-3b1d-40a5-a418-6a9c516beb3a", "eaf24a65d767200cba3296c1e541b92033ba503c21426885d22b7330a7f306bc"], ["83909bd8-7e3b-4223-9ffd-ca3b4eecfdff", "79f50ee67c002d1c1292c160de3b1608841d9c2d0d7129ece1f5dc59363c9798"], ["b6703e73-33d8-4fd3-a45b-e0bcbd82b1e0", "d2f5100dd028659b67a1292bb97bae5c45df66dcedcff740d12bfc7d478d7881"], ["7dad2adb-0e12-4157-b53a-79f1a8d8dd11", "2d7d104f32c7c491c6d0d5ba4e23a7dd3869827c84ff4df58d49ff4fa28330ec"], ["e95a1ba6-228c-468e-b0a5-dfab0d4a5ed2", "0f41ea07051721fc99370a4298177a6e1d3c4ff7e93aff303f939f074083ff0a"], ["1d7bfe39-ac73-4327-a87a-218ddfdfbc86", "8431eb49298514973c19d9576dd6f0784d29b251185951c8f81315d7829494f7"], ["bfaf0ed8-191b-4bdc-ba49-22948c2f25ea", "326420ccbc56127e035909e7750038e7bde83499bc508504c4c6810a0c4c749c"], ["b10d2faa-12f5-4e4c-9a32-90707682f720", "6c056ed63d766d0ad0d4b3d7fcc26201c52d1417231f4303d3a1c8479561e355"]]}], "changes": [{"new": ["afeb64d1-3b1d-40a5-a418-6a9c516beb3a", "eaf24a65d767200cba3296c1e541b92033ba503c21426885d22b7330a7f306bc"], "old": null, "kind": "append", "position": 0, "host_logical_id": "afeb64d1-3b1d-40a5-a418-6a9c516beb3a"}, {"new": ["83909bd8-7e3b-4223-9ffd-ca3b4eecfdff", "79f50ee67c002d1c1292c160de3b1608841d9c2d0d7129ece1f5dc59363c9798"], "old": null, "kind": "append", "position": 1, "host_logical_id": "83909bd8-7e3b-4223-9ffd-ca3b4eecfdff"}, {"new": ["b6703e73-33d8-4fd3-a45b-e0bcbd82b1e0", "d2f5100dd028659b67a1292bb97bae5c45df66dcedcff740d12bfc7d478d7881"], "old": null, "kind": "append", "position": 2, "host_logical_id": "b6703e73-33d8-4fd3-a45b-e0bcbd82b1e0"}, {"new": ["7dad2adb-0e12-4157-b53a-79f1a8d8dd11", "2d7d104f32c7c491c6d0d5ba4e23a7dd3869827c84ff4df58d49ff4fa28330ec"], "old": null, "kind": "append", "position": 3, "host_logical_id": "7dad2adb-0e12-4157-b53a-79f1a8d8dd11"}, {"new": ["e95a1ba6-228c-468e-b0a5-dfab0d4a5ed2", "0f41ea07051721fc99370a4298177a6e1d3c4ff7e93aff303f939f074083ff0a"], "old": null, "kind": "append", "position": 4, "host_logical_id": "e95a1ba6-228c-468e-b0a5-dfab0d4a5ed2"}, {"new": ["1d7bfe39-ac73-4327-a87a-218ddfdfbc86", "8431eb49298514973c19d9576dd6f0784d29b251185951c8f81315d7829494f7"], "old": null, "kind": "append", "position": 5, "host_logical_id": "1d7bfe39-ac73-4327-a87a-218ddfdfbc86"}, {"new": ["bfaf0ed8-191b-4bdc-ba49-22948c2f25ea", "326420ccbc56127e035909e7750038e7bde83499bc508504c4c6810a0c4c749c"], "old": null, "kind": "append", "position": 6, "host_logical_id": "bfaf0ed8-191b-4bdc-ba49-22948c2f25ea"}, {"new": ["b10d2faa-12f5-4e4c-9a32-90707682f720", "6c056ed63d766d0ad0d4b3d7fcc26201c52d1417231f4303d3a1c8479561e355"], "old": null, "kind": "append", "position": 7, "host_logical_id": "b10d2faa-12f5-4e4c-9a32-90707682f720"}]}', '2026-09-27 22:47:31.146971+00', '01a0e50d-5450-758f-8849-4db0d92301ac');


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


