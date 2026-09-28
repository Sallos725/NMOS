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

INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 0, '01a0e7b5-20da-7ecf-9d76-edb78b5ca883', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 1, '01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc', NULL, 0, '4ef4ed1b7274423e84b3092d58361c14');
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 2, '01a0e7b5-20dd-7655-90b2-0102151f0b95', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 3, '01a0e7b5-2774-7119-b0d7-f39dfb8319b2', NULL, 1, '06e9ec1908c8c9cd65eb405377935e2a');
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 4, '01a0e7b5-2113-7359-9ab5-da2a5b8737fb', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 5, '01a0e7b5-2114-794b-ac6c-f0624a1ab7f5', NULL, 2, '05155d48de41e7c30fcd8c823a9d757b');
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 6, '01a0e7b5-2115-745d-85c8-4cdd5ae67a11', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 7, '01a0e7b5-2116-7e6c-9c5c-9d308fd86545', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 8, '01a0e7b5-27c6-77a1-ad56-a0d3bb280a29', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 9, '01a0e7b5-213b-7844-a60c-9d8a266b13d6', NULL, 3, '519f1f545bb6a80169cdb054f9bc230e');
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 10, '01a0e7b5-213c-7cba-9d7e-206c45c37a60', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 11, '01a0e7b5-213c-70af-90d9-5d8ebd125aa0', NULL, 4, 'fdd682db37fad6bb22ad94870d2df71f');
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 12, '01a0e7b5-2164-7076-828c-348e5345b47f', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 13, '01a0e7b5-2775-709e-aa2e-99cd39d5b052', NULL, 5, 'b543af844f7bb3a785e1c3c403e5cd20');
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 14, '01a0e7b5-2775-7e24-aadf-086fe06818af', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 15, '01a0e7b5-27c7-79e0-8c70-49c363fd994b', NULL, 6, 'de1e1a73868f0e37680698163db53e57');
INSERT INTO public.active_membership VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 16, '01a0e7b5-27c8-7b77-947a-47d6c704dd58', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 0, '01a0e7b5-2ddd-7b24-9920-7e81bb976a2f', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 1, '01a0e7b5-2dde-797f-842d-f52c7651005e', NULL, 0, 'f2e2af9487c37d483cf748c810c8f949');
INSERT INTO public.active_membership VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 2, '01a0e7b5-2dde-72ec-accc-a936a3c5fb29', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 3, '01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41', NULL, 1, 'd869b844b9a27d01175aeead04a12de5');
INSERT INTO public.active_membership VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 4, '01a0e7b5-2de0-7eff-9f82-9b86d244525d', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 5, '01a0e7b5-2de1-74ff-92b0-684d89bccd83', NULL, 2, '0e2d01d5ac2adb89484708bf25f43954');
INSERT INTO public.active_membership VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 6, '01a0e7b5-2de2-7716-bd7f-684bfcb580ee', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 7, '01a0e7b5-2de2-763c-9764-625141747e0d', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0e7b5-2666-71fc-80ea-fcdf81c70e3c', '01a0e7b5-213c-70af-90d9-5d8ebd125aa0', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0e7b5-267f-7a5e-a519-83a6a60c63bb', '01a0e7b5-213b-7844-a60c-9d8a266b13d6', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0e7b5-26af-7c5e-ab1a-f35ecaa0265d', '01a0e7b5-2114-794b-ac6c-f0624a1ab7f5', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0e7b5-26c6-76b7-9a9c-6984033b31ee', '01a0e7b5-20de-7b40-bf24-30986bec9d97', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0e7b5-26c6-76b7-9a9c-6984033b31ee', '01a0e7b5-20de-7b40-bf24-30986bec9d97', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0e7b5-271b-7c1e-aedc-5999044ff44a', '01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0e7b5-271b-7c1e-aedc-5999044ff44a', '01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0e7b5-2b80-7c3e-9da0-43a61023340a', '01a0e7b5-27c7-79e0-8c70-49c363fd994b', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0e7b5-2bae-7cbc-a139-5a984fb3437c', '01a0e7b5-213c-70af-90d9-5d8ebd125aa0', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0e7b5-2bc4-7f85-aac9-beef3e3de592', '01a0e7b5-213b-7844-a60c-9d8a266b13d6', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0e7b5-2be7-7a3b-a646-8050568fcb12', '01a0e7b5-2114-794b-ac6c-f0624a1ab7f5', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0e7b5-2bfb-74eb-bebb-23549fe79a7e', '01a0e7b5-2774-7119-b0d7-f39dfb8319b2', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0e7b5-2bfb-74eb-bebb-23549fe79a7e', '01a0e7b5-2774-7119-b0d7-f39dfb8319b2', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0e7b5-3089-7d97-93e5-10dc62e6cb23', '01a0e7b5-2de1-74ff-92b0-684d89bccd83', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0e7b5-309f-781f-bd3d-f447103f6886', '01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0e7b5-309f-781f-bd3d-f447103f6886', '01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0e7b5-30b5-74ec-81f9-e9b50fa5b857', '01a0e7b5-2dde-797f-842d-f52c7651005e', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0e7b5-30b5-74ec-81f9-e9b50fa5b857', '01a0e7b5-2dde-797f-842d-f52c7651005e', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'pocketrisu', NULL, '639d7574-da5e-4c87-a60a-ab7c9f64390f', '2026-09-28 11:10:02.443685+00', NULL, NULL, NULL, '01a0e7b5-27cb-7b67-993b-678a3177503c', '355b944de5b2d09debd74e4e59cab8a38f79dbfa09f77cad52d87bf2d886a861', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL);
INSERT INTO public.conversation VALUES ('01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', 'pocketrisu', NULL, '55ce4143-42b3-4e16-b63c-db2798704311', '2026-09-28 11:10:05.77666+00', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '639d7574-da5e-4c87-a60a-ab7c9f64390f', '59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4', '01a0e7b5-2de4-70f6-aaef-f1f6f542333d', '6444119e56594b6003f0a6e02ff6f8a067737bb2a5f4669907116413ad3daf0a', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0e7b5-2666-71fc-80ea-fcdf81c70e3c', '01a0e7b5-213c-70af-90d9-5d8ebd125aa0', '3b9df15e13c4966bdcba9fe825278658', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:03.878568+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-213c-7cba-9d7e-206c45c37a60,01a0e7b5-213c-70af-90d9-5d8ebd125aa0}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-267f-7a5e-a519-83a6a60c63bb', '01a0e7b5-213b-7844-a60c-9d8a266b13d6', '006e2a2661a29b6ae69c1c96b71d839d', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:03.902982+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-213a-7d1b-99f6-e67e767f373e,01a0e7b5-213b-7844-a60c-9d8a266b13d6}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-2696-7571-805c-17963630c644', '01a0e7b5-2116-7e6c-9c5c-9d308fd86545', 'd9914f89e39cb0ee2ca239ebeee1e1ad', 'extract-v12', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:10:03.926473+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-2115-745d-85c8-4cdd5ae67a11,01a0e7b5-2116-7e6c-9c5c-9d308fd86545}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-26af-7c5e-ab1a-f35ecaa0265d', '01a0e7b5-2114-794b-ac6c-f0624a1ab7f5', 'a9f184e364577750423091658a8bf451', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:03.951689+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-2113-7359-9ab5-da2a5b8737fb,01a0e7b5-2114-794b-ac6c-f0624a1ab7f5}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-26c6-76b7-9a9c-6984033b31ee', '01a0e7b5-20de-7b40-bf24-30986bec9d97', '874c86e98228eca6ddf6541cfa8b89fb', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:03.974669+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-20dd-7655-90b2-0102151f0b95,01a0e7b5-20de-7b40-bf24-30986bec9d97}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-271b-7c1e-aedc-5999044ff44a', '01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc', '4ef4ed1b7274423e84b3092d58361c14', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:04.05929+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e7b5-20da-7ecf-9d76-edb78b5ca883,01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-2b80-7c3e-9da0-43a61023340a', '01a0e7b5-27c7-79e0-8c70-49c363fd994b', 'de1e1a73868f0e37680698163db53e57', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:05.184328+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-2775-7e24-aadf-086fe06818af,01a0e7b5-27c7-79e0-8c70-49c363fd994b}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-2b96-7945-89bf-13054b4c96dd', '01a0e7b5-2775-709e-aa2e-99cd39d5b052', 'b543af844f7bb3a785e1c3c403e5cd20', 'extract-v12', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:10:05.206927+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-2164-7076-828c-348e5345b47f,01a0e7b5-2775-709e-aa2e-99cd39d5b052}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-2bae-7cbc-a139-5a984fb3437c', '01a0e7b5-213c-70af-90d9-5d8ebd125aa0', 'fdd682db37fad6bb22ad94870d2df71f', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:05.229946+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-213c-7cba-9d7e-206c45c37a60,01a0e7b5-213c-70af-90d9-5d8ebd125aa0}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-2bc4-7f85-aac9-beef3e3de592', '01a0e7b5-213b-7844-a60c-9d8a266b13d6', '519f1f545bb6a80169cdb054f9bc230e', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:05.252622+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-2115-745d-85c8-4cdd5ae67a11,01a0e7b5-2116-7e6c-9c5c-9d308fd86545,01a0e7b5-213b-7844-a60c-9d8a266b13d6}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-2be7-7a3b-a646-8050568fcb12', '01a0e7b5-2114-794b-ac6c-f0624a1ab7f5', '05155d48de41e7c30fcd8c823a9d757b', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:05.287127+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-2113-7359-9ab5-da2a5b8737fb,01a0e7b5-2114-794b-ac6c-f0624a1ab7f5}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-2bfb-74eb-bebb-23549fe79a7e', '01a0e7b5-2774-7119-b0d7-f39dfb8319b2', '06e9ec1908c8c9cd65eb405377935e2a', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:05.307486+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-20dd-7655-90b2-0102151f0b95,01a0e7b5-2774-7119-b0d7-f39dfb8319b2}', NULL, '{"secrets": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-3089-7d97-93e5-10dc62e6cb23', '01a0e7b5-2de1-74ff-92b0-684d89bccd83', '0e2d01d5ac2adb89484708bf25f43954', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:06.473651+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-2de0-7eff-9f82-9b86d244525d,01a0e7b5-2de1-74ff-92b0-684d89bccd83}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-309f-781f-bd3d-f447103f6886', '01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41', 'd869b844b9a27d01175aeead04a12de5', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:06.495165+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-2dde-72ec-accc-a936a3c5fb29,01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41}', NULL, '{"secrets": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-30b5-74ec-81f9-e9b50fa5b857', '01a0e7b5-2dde-797f-842d-f52c7651005e', 'f2e2af9487c37d483cf748c810c8f949', 'extract-v12', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:06.517276+00', 'extract-35e7b76278482b96dcd90975177ced03', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e7b5-2ddd-7b24-9920-7e81bb976a2f,01a0e7b5-2dde-797f-842d-f52c7651005e}', NULL, '{"secrets": [], "entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0e7b5-20df-7992-bdcf-2f5c66e405be', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'manifest', 'be6a8d1bc1384a900fee0206aea8fa31ca489f2e625a36fc885cf904ec2dea54', '01a0e7b5-20cb-7021-b60c-61f7e017c02d:be6a8d1bc1384a900fee0206aea8fa31ca489f2e625a36fc885cf904ec2dea54:manifest', '2026-09-28 11:10:02.457406+00', '{"chat_id": "639d7574-da5e-4c87-a60a-ab7c9f64390f", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0", "fdb0c67d3a237cbdf28efa890c1335e4ef7d2ba0a9cf1261fd8e8566e7bc36ad", "user", null, null, null, 0, null, null], ["6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "b759a46b5489e7e814ce7d3498b89899ab8abd90ce7a3c9d73eb37fbc0468a3a", "char", null, null, null, 0, "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", null], ["fa738f50-4cb5-48c5-8762-db4ef50a09d7", "d29544fce5de10cdeaaa56eeea7d6e906098f306e220c6281bc08cefde2166d5", "user", null, null, null, 0, null, null], ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "b5f75a5928bdb40d3ede9b1f78a25d8238824f099324153891a6b85736c89268", "char", null, null, null, 0, "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-2118-72eb-aa3f-19150ae1aee1', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'manifest', 'ddbf600515e4e56e0efaa83070b388b20a29063ec777ba8a8c672650a1ef3180', '01a0e7b5-20cb-7021-b60c-61f7e017c02d:ddbf600515e4e56e0efaa83070b388b20a29063ec777ba8a8c672650a1ef3180:manifest', '2026-09-28 11:10:02.514146+00', '{"chat_id": "639d7574-da5e-4c87-a60a-ab7c9f64390f", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["a6d08c16-dedc-4e3f-b0ce-80e0b463bb98", "4b35fb09784acd8884eafbfe17f5ca8b68a782d8d4d426a3e2d29f20bd420c91", "user", null, null, null, 0, null, null], ["59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "8eb30031f0e10c03c2b88a336b142659998dd2e4603b348eeb3427b255543653", "char", null, null, null, 0, "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", null], ["6bc5f53f-d973-49c9-89b6-3e95cca6b6a8", "7e3ecd3ca7269f4cae8ffdfbfc9bb79b2dc00ef9f842f360eb393ac09d8a2890", "user", null, null, null, 0, null, null], ["00c253fa-1c5d-4307-b8a9-f40e23be9720", "e60838eb910ba8aada0af1e976cd67f9b21a0b8d3a3f32cef17fa5a55b9a2991", "char", null, null, null, 0, "00c253fa-1c5d-4307-b8a9-f40e23be9720", null]], "base_manifest_hash": "be6a8d1bc1384a900fee0206aea8fa31ca489f2e625a36fc885cf904ec2dea54"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-213f-7b93-b19c-9662c15e6afd', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'manifest', '0bcb910a019b23f13f48034d32ade47d87ab4aa7e79dc6d71d9072340c7c1ce3', '01a0e7b5-20cb-7021-b60c-61f7e017c02d:0bcb910a019b23f13f48034d32ade47d87ab4aa7e79dc6d71d9072340c7c1ce3:manifest', '2026-09-28 11:10:02.553573+00', '{"chat_id": "639d7574-da5e-4c87-a60a-ab7c9f64390f", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["61af0df1-52a5-4961-94f0-491e2dddad97", "667550678330d0132518136c11303758f555a324706e06bd50b8cb008c2a1b85", "user", null, null, null, 0, null, null], ["ac90526c-c7cf-4ecf-9afa-76329149b711", "5b3bebf630f2109261ec09420613793d316eeae758d0c74bde99f6af29556d51", "char", null, null, null, 0, "ac90526c-c7cf-4ecf-9afa-76329149b711", null], ["5ab2ae85-762e-4719-bc30-a77170b547f5", "7d6594de632fa8e8ea1e6cb6fd922174600cc32e750069e451df1fc6e5756879", "user", null, null, null, 0, null, null], ["6b0b474d-5296-4c13-869a-c7fa687e8a50", "53b898cf68752332543b573a40d0133c3da13054ce6d007b60a71eaeb3913d7c", "char", null, null, null, 0, "6b0b474d-5296-4c13-869a-c7fa687e8a50", null]], "base_manifest_hash": "ddbf600515e4e56e0efaa83070b388b20a29063ec777ba8a8c672650a1ef3180"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-2167-7eca-91a9-e181bcc70f43', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'manifest', '2a59ddcef70a334b8ac31c9359a7abd08b7acf20146293c290080a7ca2d1d946', '01a0e7b5-20cb-7021-b60c-61f7e017c02d:2a59ddcef70a334b8ac31c9359a7abd08b7acf20146293c290080a7ca2d1d946:manifest', '2026-09-28 11:10:02.595385+00', '{"chat_id": "639d7574-da5e-4c87-a60a-ab7c9f64390f", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["30bb5d2c-7bb5-448f-821f-5fed48647096", "50d47a8eedca12fddbcfd0af23c999726e3f598d1022228d0e05411644bacf71", "user", null, null, null, 0, null, null]], "base_manifest_hash": "0bcb910a019b23f13f48034d32ade47d87ab4aa7e79dc6d71d9072340c7c1ce3"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-2778-7c81-87e7-c0ef4d5cfecd', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'manifest', '95ea12758e0566e64cfa71c4c1f3d77610977ac0285826dc0294261d50c5462d', '01a0e7b5-20cb-7021-b60c-61f7e017c02d:95ea12758e0566e64cfa71c4c1f3d77610977ac0285826dc0294261d50c5462d:manifest', '2026-09-28 11:10:04.147731+00', '{"chat_id": "639d7574-da5e-4c87-a60a-ab7c9f64390f", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0", "fdb0c67d3a237cbdf28efa890c1335e4ef7d2ba0a9cf1261fd8e8566e7bc36ad", "user", null, null, null, 0, null, null], ["6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "b759a46b5489e7e814ce7d3498b89899ab8abd90ce7a3c9d73eb37fbc0468a3a", "char", null, null, null, 0, "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", null], ["fa738f50-4cb5-48c5-8762-db4ef50a09d7", "d29544fce5de10cdeaaa56eeea7d6e906098f306e220c6281bc08cefde2166d5", "user", null, null, null, 0, null, null], ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "ca09907fe0a053cafc022934dc5b6c13a83a053d3ee41ac087c17de651b2bd0a", "char", null, null, null, 0, "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", null], ["a6d08c16-dedc-4e3f-b0ce-80e0b463bb98", "4b35fb09784acd8884eafbfe17f5ca8b68a782d8d4d426a3e2d29f20bd420c91", "user", null, null, null, 0, null, null], ["59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "8eb30031f0e10c03c2b88a336b142659998dd2e4603b348eeb3427b255543653", "char", null, null, null, 0, "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", null], ["6bc5f53f-d973-49c9-89b6-3e95cca6b6a8", "7e3ecd3ca7269f4cae8ffdfbfc9bb79b2dc00ef9f842f360eb393ac09d8a2890", "user", null, null, null, 0, null, null], ["00c253fa-1c5d-4307-b8a9-f40e23be9720", "e60838eb910ba8aada0af1e976cd67f9b21a0b8d3a3f32cef17fa5a55b9a2991", "char", null, null, null, 0, "00c253fa-1c5d-4307-b8a9-f40e23be9720", null], ["61af0df1-52a5-4961-94f0-491e2dddad97", "667550678330d0132518136c11303758f555a324706e06bd50b8cb008c2a1b85", "user", null, null, null, 0, null, null], ["ac90526c-c7cf-4ecf-9afa-76329149b711", "5b3bebf630f2109261ec09420613793d316eeae758d0c74bde99f6af29556d51", "char", null, null, null, 0, "ac90526c-c7cf-4ecf-9afa-76329149b711", null], ["5ab2ae85-762e-4719-bc30-a77170b547f5", "7d6594de632fa8e8ea1e6cb6fd922174600cc32e750069e451df1fc6e5756879", "user", null, null, null, 0, null, null], ["6b0b474d-5296-4c13-869a-c7fa687e8a50", "53b898cf68752332543b573a40d0133c3da13054ce6d007b60a71eaeb3913d7c", "char", null, null, null, 0, "6b0b474d-5296-4c13-869a-c7fa687e8a50", null], ["30bb5d2c-7bb5-448f-821f-5fed48647096", "50d47a8eedca12fddbcfd0af23c999726e3f598d1022228d0e05411644bacf71", "user", null, null, null, 0, null, null], ["5938ae9c-9645-432d-bb24-2fc80d7b3c84", "60a5ac8bab10e35c748df1f956a66f5b2196b433b5f5221249956eb8702161ed", "char", null, null, null, 0, "5938ae9c-9645-432d-bb24-2fc80d7b3c84", null], ["2164e47d-cd8f-44ce-b063-a87e78b80ec4", "ca5256def799a0f22e8018598074970e376dd1a904cc95b0a68a008d257d21c4", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-27a0-78c5-89e4-739222f59d60', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'manifest', '24dc2a91935f1a719ac85ce30518aefbb8a829f20d81dfbb5956a250aba04987', '01a0e7b5-20cb-7021-b60c-61f7e017c02d:24dc2a91935f1a719ac85ce30518aefbb8a829f20d81dfbb5956a250aba04987:manifest', '2026-09-28 11:10:04.188238+00', '{"chat_id": "639d7574-da5e-4c87-a60a-ab7c9f64390f", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["04854e26-fbd3-47fc-841d-8163f9d9b232", "ef851653440f5f1a3d4c39176fc86107e6f2c84f85a874b8497c385bcd40a73b", "char", null, null, 1, 2, "04854e26-fbd3-47fc-841d-8163f9d9b232", null]], "base_manifest_hash": "95ea12758e0566e64cfa71c4c1f3d77610977ac0285826dc0294261d50c5462d"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-27ca-793a-a3c1-a4d5abca1b94', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'manifest', '355b944de5b2d09debd74e4e59cab8a38f79dbfa09f77cad52d87bf2d886a861', '01a0e7b5-20cb-7021-b60c-61f7e017c02d:355b944de5b2d09debd74e4e59cab8a38f79dbfa09f77cad52d87bf2d886a861:manifest', '2026-09-28 11:10:04.229781+00', '{"chat_id": "639d7574-da5e-4c87-a60a-ab7c9f64390f", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0", "fdb0c67d3a237cbdf28efa890c1335e4ef7d2ba0a9cf1261fd8e8566e7bc36ad", "user", null, null, null, 0, null, null], ["6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "b759a46b5489e7e814ce7d3498b89899ab8abd90ce7a3c9d73eb37fbc0468a3a", "char", null, null, null, 0, "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", null], ["fa738f50-4cb5-48c5-8762-db4ef50a09d7", "d29544fce5de10cdeaaa56eeea7d6e906098f306e220c6281bc08cefde2166d5", "user", null, null, null, 0, null, null], ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "ca09907fe0a053cafc022934dc5b6c13a83a053d3ee41ac087c17de651b2bd0a", "char", null, null, null, 0, "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", null], ["a6d08c16-dedc-4e3f-b0ce-80e0b463bb98", "4b35fb09784acd8884eafbfe17f5ca8b68a782d8d4d426a3e2d29f20bd420c91", "user", null, null, null, 0, null, null], ["59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "8eb30031f0e10c03c2b88a336b142659998dd2e4603b348eeb3427b255543653", "char", null, null, null, 0, "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", null], ["6bc5f53f-d973-49c9-89b6-3e95cca6b6a8", "7e3ecd3ca7269f4cae8ffdfbfc9bb79b2dc00ef9f842f360eb393ac09d8a2890", "user", null, null, null, 0, null, null], ["00c253fa-1c5d-4307-b8a9-f40e23be9720", "e60838eb910ba8aada0af1e976cd67f9b21a0b8d3a3f32cef17fa5a55b9a2991", "char", null, null, null, 0, "00c253fa-1c5d-4307-b8a9-f40e23be9720", null], ["61af0df1-52a5-4961-94f0-491e2dddad97", "eb8d2e0c839d775001f7bf78e52ea2299b104374d01ceb6b97449bc004fd77e5", "user", true, null, null, 0, null, null], ["ac90526c-c7cf-4ecf-9afa-76329149b711", "5b3bebf630f2109261ec09420613793d316eeae758d0c74bde99f6af29556d51", "char", null, null, null, 0, "ac90526c-c7cf-4ecf-9afa-76329149b711", null], ["5ab2ae85-762e-4719-bc30-a77170b547f5", "7d6594de632fa8e8ea1e6cb6fd922174600cc32e750069e451df1fc6e5756879", "user", null, null, null, 0, null, null], ["6b0b474d-5296-4c13-869a-c7fa687e8a50", "53b898cf68752332543b573a40d0133c3da13054ce6d007b60a71eaeb3913d7c", "char", null, null, null, 0, "6b0b474d-5296-4c13-869a-c7fa687e8a50", null], ["30bb5d2c-7bb5-448f-821f-5fed48647096", "50d47a8eedca12fddbcfd0af23c999726e3f598d1022228d0e05411644bacf71", "user", null, null, null, 0, null, null], ["5938ae9c-9645-432d-bb24-2fc80d7b3c84", "60a5ac8bab10e35c748df1f956a66f5b2196b433b5f5221249956eb8702161ed", "char", null, null, null, 0, "5938ae9c-9645-432d-bb24-2fc80d7b3c84", null], ["2164e47d-cd8f-44ce-b063-a87e78b80ec4", "ca5256def799a0f22e8018598074970e376dd1a904cc95b0a68a008d257d21c4", "user", null, null, null, 0, null, null], ["04854e26-fbd3-47fc-841d-8163f9d9b232", "04515d12a9232684d3036bdb84590b7d744735187d5ad66aed9cc3f7ffab8b14", "char", null, null, 0, 2, "04854e26-fbd3-47fc-841d-8163f9d9b232", null], ["257964a9-d5e2-4f26-a08d-1357de84b9ef", "146984ad54312dbe6b69d136f6bea838583602c2722e4995bf7d60f192b8064d", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-2de3-76f4-b008-f5933453671c', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', 'manifest', '6444119e56594b6003f0a6e02ff6f8a067737bb2a5f4669907116413ad3daf0a', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f:6444119e56594b6003f0a6e02ff6f8a067737bb2a5f4669907116413ad3daf0a:manifest', '2026-09-28 11:10:05.788865+00', '{"chat_id": "55ce4143-42b3-4e16-b63c-db2798704311", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["cf3ff4ac-6940-40a5-a569-275f83510a09", "770a35cadbae253c81752fb4d8fac11d5865bceb2f9d29050171657567636dd4", "user", null, null, null, 0, null, null], ["0bf0142d-96bf-4db0-a326-6d7cfd1984cb", "e408bdd346239f4780a97f5740213a74a875d1574ae3b860ddf4aa4ec8a2d8ea", "char", null, null, null, 0, "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", null], ["273e3852-e8ab-4383-ad7f-fe3d60f47bc5", "4bc8f7688da153e23ab7fb26153072b4d6d27590665f23298eda135ac8fa1e77", "user", null, null, null, 0, null, null], ["b36e8a9d-d079-469f-b817-c47d85616278", "41f952c653b46087914bf1ed92edab391335957e9c56cc24d39c4bcbdfbbf766", "char", null, null, null, 0, "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", null], ["c4229c71-8b1f-4dd3-a674-0260be62c787", "8636d304980d45ec07067e78a94056d33e5755d2a50c14abcfea3249d5395c94", "user", null, null, null, 0, null, null], ["57deb76e-bea9-47d9-9ead-a54c39541fb5", "b0067213cd013f455edd9abcd381404084d7c18f711af3f926442955a82ff0e9", "char", null, null, null, 0, "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", null], ["c522fd58-ec6f-4ede-b7f4-a0ae152a6a82", "036c9ec43082ef06e184af3cfedcda2d95b910a6c356ff20a3fe6e2d0b55b3dd", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::639d7574-da5e-4c87-a60a-ab7c9f64390f::Harbor route::59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4::}}"]], ["8a99fec6-9d9b-4207-b1df-d11f8a387f43", "b6354cd750101e02f009cec99a7ab6eb59a3e8eff03519f0a162e2fb0cd229d0", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0e7b5-2164-7076-828c-348e5345b47f:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2164-7076-828c-348e5345b47f"}', 50, 'done', 1, '2026-09-28 11:10:02.595385+00', NULL, NULL, '2026-09-28 11:10:02.595385+00', '2026-09-28 11:10:03.66897+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0e7b5-213c-70af-90d9-5d8ebd125aa0:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-213c-70af-90d9-5d8ebd125aa0"}', 50, 'done', 1, '2026-09-28 11:10:02.595385+00', NULL, NULL, '2026-09-28 11:10:02.595385+00', '2026-09-28 11:10:03.690477+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0e7b5-213c-7cba-9d7e-206c45c37a60:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-213c-7cba-9d7e-206c45c37a60"}', 50, 'done', 1, '2026-09-28 11:10:02.553573+00', NULL, NULL, '2026-09-28 11:10:02.553573+00', '2026-09-28 11:10:03.710506+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0e7b5-213b-7844-a60c-9d8a266b13d6:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-213b-7844-a60c-9d8a266b13d6"}', 50, 'done', 1, '2026-09-28 11:10:02.553573+00', NULL, NULL, '2026-09-28 11:10:02.553573+00', '2026-09-28 11:10:03.731555+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0e7b5-213a-7d1b-99f6-e67e767f373e:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-213a-7d1b-99f6-e67e767f373e"}', 50, 'done', 1, '2026-09-28 11:10:02.553573+00', NULL, NULL, '2026-09-28 11:10:02.553573+00', '2026-09-28 11:10:03.751118+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0e7b5-2116-7e6c-9c5c-9d308fd86545:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2116-7e6c-9c5c-9d308fd86545"}', 50, 'done', 1, '2026-09-28 11:10:02.553573+00', NULL, NULL, '2026-09-28 11:10:02.553573+00', '2026-09-28 11:10:03.770831+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0e7b5-2115-745d-85c8-4cdd5ae67a11:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2115-745d-85c8-4cdd5ae67a11"}', 50, 'done', 1, '2026-09-28 11:10:02.514146+00', NULL, NULL, '2026-09-28 11:10:02.514146+00', '2026-09-28 11:10:03.790542+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0e7b5-2114-794b-ac6c-f0624a1ab7f5:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2114-794b-ac6c-f0624a1ab7f5"}', 50, 'done', 1, '2026-09-28 11:10:02.514146+00', NULL, NULL, '2026-09-28 11:10:02.514146+00', '2026-09-28 11:10:03.810938+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0e7b5-2113-7359-9ab5-da2a5b8737fb:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2113-7359-9ab5-da2a5b8737fb"}', 50, 'done', 1, '2026-09-28 11:10:02.514146+00', NULL, NULL, '2026-09-28 11:10:02.514146+00', '2026-09-28 11:10:03.831709+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0e7b5-20de-7b40-bf24-30986bec9d97:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-20de-7b40-bf24-30986bec9d97"}', 50, 'done', 1, '2026-09-28 11:10:02.514146+00', NULL, NULL, '2026-09-28 11:10:02.514146+00', '2026-09-28 11:10:03.855645+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0e7b5-213c-70af-90d9-5d8ebd125aa0:3b9df15e13c4966bdcba9fe825278658:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-213c-70af-90d9-5d8ebd125aa0", "window_hash": "3b9df15e13c4966bdcba9fe825278658"}', 100, 'done', 1, '2026-09-28 11:10:02.595385+00', NULL, NULL, '2026-09-28 11:10:02.595385+00', '2026-09-28 11:10:03.881204+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0e7b5-213b-7844-a60c-9d8a266b13d6:006e2a2661a29b6ae69c1c96b71d839d:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-213b-7844-a60c-9d8a266b13d6", "window_hash": "006e2a2661a29b6ae69c1c96b71d839d"}', 100, 'done', 1, '2026-09-28 11:10:02.553573+00', NULL, NULL, '2026-09-28 11:10:02.553573+00', '2026-09-28 11:10:03.904909+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0e7b5-2116-7e6c-9c5c-9d308fd86545:d9914f89e39cb0ee2ca239ebeee1e1ad:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2116-7e6c-9c5c-9d308fd86545", "window_hash": "d9914f89e39cb0ee2ca239ebeee1e1ad"}', 100, 'done', 1, '2026-09-28 11:10:02.553573+00', NULL, NULL, '2026-09-28 11:10:02.553573+00', '2026-09-28 11:10:03.928174+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0e7b5-2114-794b-ac6c-f0624a1ab7f5:a9f184e364577750423091658a8bf451:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2114-794b-ac6c-f0624a1ab7f5", "window_hash": "a9f184e364577750423091658a8bf451"}', 100, 'done', 1, '2026-09-28 11:10:02.514146+00', NULL, NULL, '2026-09-28 11:10:02.514146+00', '2026-09-28 11:10:03.953795+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0e7b5-20de-7b40-bf24-30986bec9d97:874c86e98228eca6ddf6541cfa8b89fb:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-20de-7b40-bf24-30986bec9d97", "window_hash": "874c86e98228eca6ddf6541cfa8b89fb"}', 100, 'done', 1, '2026-09-28 11:10:02.514146+00', NULL, NULL, '2026-09-28 11:10:02.514146+00', '2026-09-28 11:10:03.976838+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0e7b5-20dd-7655-90b2-0102151f0b95:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-20dd-7655-90b2-0102151f0b95"}', 150, 'done', 1, '2026-09-28 11:10:02.457406+00', NULL, NULL, '2026-09-28 11:10:02.457406+00', '2026-09-28 11:10:03.997342+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc"}', 150, 'done', 1, '2026-09-28 11:10:02.457406+00', NULL, NULL, '2026-09-28 11:10:02.457406+00', '2026-09-28 11:10:04.016566+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0e7b5-20da-7ecf-9d76-edb78b5ca883:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-20da-7ecf-9d76-edb78b5ca883"}', 150, 'done', 1, '2026-09-28 11:10:02.457406+00', NULL, NULL, '2026-09-28 11:10:02.457406+00', '2026-09-28 11:10:04.035211+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc:4ef4ed1b7274423e84b3092d58361c14:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc", "window_hash": "4ef4ed1b7274423e84b3092d58361c14"}', 200, 'done', 1, '2026-09-28 11:10:02.457406+00', NULL, NULL, '2026-09-28 11:10:02.457406+00', '2026-09-28 11:10:04.061548+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0e7b5-2114-794b-ac6c-f0624a1ab7f5:05155d48de41e7c30fcd8c823a9d757b:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2114-794b-ac6c-f0624a1ab7f5", "window_hash": "05155d48de41e7c30fcd8c823a9d757b"}', 100, 'done', 1, '2026-09-28 11:10:04.147731+00', NULL, NULL, '2026-09-28 11:10:04.147731+00', '2026-09-28 11:10:05.289267+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0e7b5-2774-7119-b0d7-f39dfb8319b2:06e9ec1908c8c9cd65eb405377935e2a:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2774-7119-b0d7-f39dfb8319b2", "window_hash": "06e9ec1908c8c9cd65eb405377935e2a"}', 100, 'done', 1, '2026-09-28 11:10:04.147731+00', NULL, NULL, '2026-09-28 11:10:04.147731+00', '2026-09-28 11:10:05.30933+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0e7b5-2de0-7eff-9f82-9b86d244525d:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2de0-7eff-9f82-9b86d244525d"}', 150, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.377265+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0e7b5-27c8-7b77-947a-47d6c704dd58:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-27c8-7b77-947a-47d6c704dd58"}', 50, 'done', 1, '2026-09-28 11:10:04.229781+00', NULL, NULL, '2026-09-28 11:10:04.229781+00', '2026-09-28 11:10:05.08205+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0e7b5-27c7-79e0-8c70-49c363fd994b:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-27c7-79e0-8c70-49c363fd994b"}', 50, 'done', 1, '2026-09-28 11:10:04.229781+00', NULL, NULL, '2026-09-28 11:10:04.229781+00', '2026-09-28 11:10:05.1009+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0e7b5-2775-7e24-aadf-086fe06818af:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2775-7e24-aadf-086fe06818af"}', 50, 'done', 1, '2026-09-28 11:10:04.147731+00', NULL, NULL, '2026-09-28 11:10:04.147731+00', '2026-09-28 11:10:05.120563+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0e7b5-2775-709e-aa2e-99cd39d5b052:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2775-709e-aa2e-99cd39d5b052"}', 50, 'done', 1, '2026-09-28 11:10:04.147731+00', NULL, NULL, '2026-09-28 11:10:04.147731+00', '2026-09-28 11:10:05.140047+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0e7b5-2774-7119-b0d7-f39dfb8319b2:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2774-7119-b0d7-f39dfb8319b2"}', 50, 'done', 1, '2026-09-28 11:10:04.147731+00', NULL, NULL, '2026-09-28 11:10:04.147731+00', '2026-09-28 11:10:05.158756+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0e7b5-27c7-79e0-8c70-49c363fd994b:de1e1a73868f0e37680698163db53e57:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-27c7-79e0-8c70-49c363fd994b", "window_hash": "de1e1a73868f0e37680698163db53e57"}', 100, 'done', 1, '2026-09-28 11:10:04.229781+00', NULL, NULL, '2026-09-28 11:10:04.229781+00', '2026-09-28 11:10:05.186129+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0e7b5-2775-709e-aa2e-99cd39d5b052:b543af844f7bb3a785e1c3c403e5cd20:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2775-709e-aa2e-99cd39d5b052", "window_hash": "b543af844f7bb3a785e1c3c403e5cd20"}', 100, 'done', 1, '2026-09-28 11:10:04.229781+00', NULL, NULL, '2026-09-28 11:10:04.229781+00', '2026-09-28 11:10:05.20864+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0e7b5-213c-70af-90d9-5d8ebd125aa0:fdd682db37fad6bb22ad94870d2df71f:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-213c-70af-90d9-5d8ebd125aa0", "window_hash": "fdd682db37fad6bb22ad94870d2df71f"}', 100, 'done', 1, '2026-09-28 11:10:04.229781+00', NULL, NULL, '2026-09-28 11:10:04.229781+00', '2026-09-28 11:10:05.231921+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0e7b5-213b-7844-a60c-9d8a266b13d6:519f1f545bb6a80169cdb054f9bc230e:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-213b-7844-a60c-9d8a266b13d6", "window_hash": "519f1f545bb6a80169cdb054f9bc230e"}', 100, 'done', 1, '2026-09-28 11:10:04.229781+00', NULL, NULL, '2026-09-28 11:10:04.229781+00', '2026-09-28 11:10:05.254491+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0e7b5-2775-709e-aa2e-99cd39d5b052:0c491c135f738dfff0a91234d3d1da5d:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2775-709e-aa2e-99cd39d5b052", "window_hash": "0c491c135f738dfff0a91234d3d1da5d"}', 100, 'obsolete', 1, '2026-09-28 11:10:04.147731+00', NULL, NULL, '2026-09-28 11:10:04.147731+00', '2026-09-28 11:10:05.257845+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0e7b5-213b-7844-a60c-9d8a266b13d6:facbfc6b6c5c97431d99f27d8d7f2c60:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-213b-7844-a60c-9d8a266b13d6", "window_hash": "facbfc6b6c5c97431d99f27d8d7f2c60"}', 100, 'obsolete', 1, '2026-09-28 11:10:04.147731+00', NULL, NULL, '2026-09-28 11:10:04.147731+00', '2026-09-28 11:10:05.263711+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0e7b5-2116-7e6c-9c5c-9d308fd86545:bb412bb491b5396495e650d6bfd18c9e:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2116-7e6c-9c5c-9d308fd86545", "window_hash": "bb412bb491b5396495e650d6bfd18c9e"}', 100, 'obsolete', 1, '2026-09-28 11:10:04.147731+00', NULL, NULL, '2026-09-28 11:10:04.147731+00', '2026-09-28 11:10:05.266868+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0e7b5-2de1-74ff-92b0-684d89bccd83:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2de1-74ff-92b0-684d89bccd83"}', 150, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.358305+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41"}', 150, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.396123+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0e7b5-2dde-72ec-accc-a936a3c5fb29:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2dde-72ec-accc-a936a3c5fb29"}', 150, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.415297+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0e7b5-2dde-797f-842d-f52c7651005e:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2dde-797f-842d-f52c7651005e"}', 150, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.434286+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0e7b5-2ddd-7b24-9920-7e81bb976a2f:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2ddd-7b24-9920-7e81bb976a2f"}', 150, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.453215+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0e7b5-2de1-74ff-92b0-684d89bccd83:0e2d01d5ac2adb89484708bf25f43954:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2de1-74ff-92b0-684d89bccd83", "window_hash": "0e2d01d5ac2adb89484708bf25f43954"}', 200, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.475515+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41:d869b844b9a27d01175aeead04a12de5:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41", "window_hash": "d869b844b9a27d01175aeead04a12de5"}', 200, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.497034+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0e7b5-2dde-797f-842d-f52c7651005e:f2e2af9487c37d483cf748c810c8f949:extract-35e7b76278482b96dcd90975177ced03', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "extract-35e7b76278482b96dcd90975177ced03", "revision_id": "01a0e7b5-2dde-797f-842d-f52c7651005e", "window_hash": "f2e2af9487c37d483cf748c810c8f949"}', 200, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.519062+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0e7b5-2de2-763c-9764-625141747e0d:embed-e4f0b4762962cd53b278741ec7f2dea6', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{"generation": "embed-e4f0b4762962cd53b278741ec7f2dea6", "revision_id": "01a0e7b5-2de2-763c-9764-625141747e0d"}', 150, 'done', 1, '2026-09-28 11:10:05.788865+00', NULL, NULL, '2026-09-28 11:10:05.788865+00', '2026-09-28 11:10:06.338377+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0e7b5-20df-7992-bdcf-2f5c66e405be', '01a0e7b5-20cb-7021-b60c-61f7e017c02d');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-35e7b76278482b96dcd90975177ced03', 'extract', 'stub', 'http://127.0.0.1:38569/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "3c80e6a1b8b262a4", "compiler": "extract-v12", "endpoint": "http://127.0.0.1:38569/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "c17fde3c9948898d", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-28 11:10:02.326825+00', '2026-09-28 11:10:02.328144+00');
INSERT INTO public.projection_generation VALUES ('embed-e4f0b4762962cd53b278741ec7f2dea6', 'embed', 'stub-embed', 'http://127.0.0.1:38569/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:38569/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-28 11:10:02.326825+00', '2026-09-28 11:10:02.331968+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-2108-7792-95ae-85fdc6da351d', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '01a0e7b5-20e0-75f6-b502-623c1d4568b0', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b5-20dd-7655-90b2-0102151f0b95", "host_logical_id": "fa738f50-4cb5-48c5-8762-db4ef50a09d7"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b5-20dd-7655-90b2-0102151f0b95", "host_logical_id": "fa738f50-4cb5-48c5-8762-db4ef50a09d7"}]', 0, '{"fit": 0.0, "embed": 24.19, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 1.94, "fits_at": null, "lexical": 3.32, "threads": 0, "extractor": "extract-35e7b7627848", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 33.38, "embedding_projection": "embed-e4f0b4762962cd", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:02.471291+00', 'packet-v4', 600, 3, '', '["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0", "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "fa738f50-4cb5-48c5-8762-db4ef50a09d7"]', 'extract-35e7b76278482b96dcd90975177ced03', 'embed-e4f0b4762962cd53b278741ec7f2dea6', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-2131-7f30-aaa2-c6b73cffc4e5', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '01a0e7b5-20e0-75f6-b502-623c1d4568b0', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b5-2115-745d-85c8-4cdd5ae67a11", "host_logical_id": "6bc5f53f-d973-49c9-89b6-3e95cca6b6a8"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b5-2115-745d-85c8-4cdd5ae67a11", "host_logical_id": "6bc5f53f-d973-49c9-89b6-3e95cca6b6a8"}]', 0, '{"fit": 0.0, "embed": 13.36, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 0.75, "fits_at": null, "lexical": 2.47, "threads": 0, "extractor": "extract-35e7b7627848", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 18.82, "embedding_projection": "embed-e4f0b4762962cd", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:02.526669+00', 'packet-v4', 600, 7, '', '["00c253fa-1c5d-4307-b8a9-f40e23be9720", "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "6bc5f53f-d973-49c9-89b6-3e95cca6b6a8", "a6d08c16-dedc-4e3f-b0ce-80e0b463bb98"]', 'extract-35e7b76278482b96dcd90975177ced03', 'embed-e4f0b4762962cd53b278741ec7f2dea6', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-2159-70f5-8c17-399d5b2a037f', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '01a0e7b5-20e0-75f6-b502-623c1d4568b0', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b5-213c-7cba-9d7e-206c45c37a60", "host_logical_id": "5ab2ae85-762e-4719-bc30-a77170b547f5"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b5-213c-7cba-9d7e-206c45c37a60", "host_logical_id": "5ab2ae85-762e-4719-bc30-a77170b547f5"}]', 0, '{"fit": 0.0, "embed": 14.21, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 1.11, "fits_at": null, "lexical": 2.4, "threads": 0, "extractor": "extract-35e7b7627848", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.14, "embedding_projection": "embed-e4f0b4762962cd", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:02.565345+00', 'packet-v4', 600, 11, '', '["5ab2ae85-762e-4719-bc30-a77170b547f5", "61af0df1-52a5-4961-94f0-491e2dddad97", "6b0b474d-5296-4c13-869a-c7fa687e8a50", "ac90526c-c7cf-4ecf-9afa-76329149b711"]', 'extract-35e7b76278482b96dcd90975177ced03', 'embed-e4f0b4762962cd53b278741ec7f2dea6', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-2182-7e09-bcaa-4da62c901ba7', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '01a0e7b5-20e0-75f6-b502-623c1d4568b0', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b5-2164-7076-828c-348e5345b47f", "host_logical_id": "30bb5d2c-7bb5-448f-821f-5fed48647096"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0e7b5-20de-7b40-bf24-30986bec9d97", "host_logical_id": "0e41040c-4158-4b3d-ade6-a947e4d9a2b0"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc", "host_logical_id": "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b5-20de-7b40-bf24-30986bec9d97"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b5-2164-7076-828c-348e5345b47f", "host_logical_id": "30bb5d2c-7bb5-448f-821f-5fed48647096"}]', 174, '{"fit": 0.0, "embed": 13.81, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 0.87, "fits_at": null, "lexical": 3.0, "threads": 0, "extractor": "extract-35e7b7627848", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.97, "embedding_projection": "embed-e4f0b4762962cd", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:02.605481+00', 'packet-v4', 600, 12, '', '["30bb5d2c-7bb5-448f-821f-5fed48647096", "5ab2ae85-762e-4719-bc30-a77170b547f5", "6b0b474d-5296-4c13-869a-c7fa687e8a50", "ac90526c-c7cf-4ecf-9afa-76329149b711"]', 'extract-35e7b76278482b96dcd90975177ced03', 'embed-e4f0b4762962cd53b278741ec7f2dea6', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-20de-7b40-bf24-30986bec9d97"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 3, "placed": true}, {"ref": {"revision": "01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-2793-7266-b788-4d5e2760b711', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '01a0e7b5-2779-7a5c-a336-cf065dae6f7c', 'And the compass?', '[{"rrf": 0.03128, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0e7b5-213b-7844-a60c-9d8a266b13d6", "host_logical_id": "ac90526c-c7cf-4ecf-9afa-76329149b711"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-2775-7e24-aadf-086fe06818af", "host_logical_id": "2164e47d-cd8f-44ce-b063-a87e78b80ec4"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc", "host_logical_id": "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0e7b5-20da-7ecf-9d76-edb78b5ca883", "host_logical_id": "0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0e7b5-2116-7e6c-9c5c-9d308fd86545", "host_logical_id": "00c253fa-1c5d-4307-b8a9-f40e23be9720"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0e7b5-2114-794b-ac6c-f0624a1ab7f5", "host_logical_id": "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0e7b5-20da-7ecf-9d76-edb78b5ca883"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc"}, {"turn": 5, "score": 0.01562, "revision_id": "01a0e7b5-2114-794b-ac6c-f0624a1ab7f5"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0e7b5-2116-7e6c-9c5c-9d308fd86545"}, {"turn": 9, "score": 0.03128, "revision_id": "01a0e7b5-213b-7844-a60c-9d8a266b13d6"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-2775-7e24-aadf-086fe06818af", "host_logical_id": "2164e47d-cd8f-44ce-b063-a87e78b80ec4"}]', 252, '{"fit": 0.0, "embed": 14.13, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 5}, "vector": 0.94, "fits_at": null, "lexical": 2.92, "threads": 0, "extractor": "extract-35e7b7627848", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.76, "embedding_projection": "embed-e4f0b4762962cd", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:04.158523+00', 'packet-v4', 600, 14, '', '["2164e47d-cd8f-44ce-b063-a87e78b80ec4", "30bb5d2c-7bb5-448f-821f-5fed48647096", "5938ae9c-9645-432d-bb24-2fc80d7b3c84", "6b0b474d-5296-4c13-869a-c7fa687e8a50"]', 'extract-35e7b76278482b96dcd90975177ced03', 'embed-e4f0b4762962cd53b278741ec7f2dea6', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-213b-7844-a60c-9d8a266b13d6"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}, {"ref": {"revision": "01a0e7b5-20da-7ecf-9d76-edb78b5ca883"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a0e7b5-2116-7e6c-9c5c-9d308fd86545"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 7, "placed": true}, {"ref": {"revision": "01a0e7b5-2114-794b-ac6c-f0624a1ab7f5"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 5, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-27bb-78cb-8883-375e1b66cc21', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '01a0e7b5-2779-7a5c-a336-cf065dae6f7c', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0e7b5-213b-7844-a60c-9d8a266b13d6", "host_logical_id": "ac90526c-c7cf-4ecf-9afa-76329149b711"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-2775-7e24-aadf-086fe06818af", "host_logical_id": "2164e47d-cd8f-44ce-b063-a87e78b80ec4"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0e7b5-213c-70af-90d9-5d8ebd125aa0", "host_logical_id": "6b0b474d-5296-4c13-869a-c7fa687e8a50"}]', '[{"turn": 9, "score": 0.03002, "revision_id": "01a0e7b5-213b-7844-a60c-9d8a266b13d6"}, {"turn": 11, "score": 0.01639, "revision_id": "01a0e7b5-213c-70af-90d9-5d8ebd125aa0"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-2775-7e24-aadf-086fe06818af", "host_logical_id": "2164e47d-cd8f-44ce-b063-a87e78b80ec4"}]', 171, '{"fit": 0.0, "embed": 14.43, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 1.1, "fits_at": null, "lexical": 3.67, "threads": 0, "extractor": "extract-35e7b7627848", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 22.52, "embedding_projection": "embed-e4f0b4762962cd", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:04.196938+00', 'packet-v4', 600, 15, '', '["04854e26-fbd3-47fc-841d-8163f9d9b232", "2164e47d-cd8f-44ce-b063-a87e78b80ec4", "30bb5d2c-7bb5-448f-821f-5fed48647096", "5938ae9c-9645-432d-bb24-2fc80d7b3c84"]', 'extract-35e7b76278482b96dcd90975177ced03', 'embed-e4f0b4762962cd53b278741ec7f2dea6', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-213b-7844-a60c-9d8a266b13d6"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e7b5-213c-70af-90d9-5d8ebd125aa0"}, "tok": 24, "why": "placed", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 11, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-27e5-7ec4-b30e-25585d51c521', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '01a0e7b5-27cb-7b67-993b-678a3177503c', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0e7b5-2115-745d-85c8-4cdd5ae67a11", "host_logical_id": "6bc5f53f-d973-49c9-89b6-3e95cca6b6a8"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b5-27c8-7b77-947a-47d6c704dd58", "host_logical_id": "257964a9-d5e2-4f26-a08d-1357de84b9ef"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0e7b5-2115-745d-85c8-4cdd5ae67a11"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b5-27c8-7b77-947a-47d6c704dd58", "host_logical_id": "257964a9-d5e2-4f26-a08d-1357de84b9ef"}]', 138, '{"fit": 0.0, "embed": 14.17, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1}, "vector": 0.85, "fits_at": null, "lexical": 2.19, "threads": 0, "extractor": "extract-35e7b7627848", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.06, "embedding_projection": "embed-e4f0b4762962cd", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:04.24138+00', 'packet-v4', 600, 16, '', '["04854e26-fbd3-47fc-841d-8163f9d9b232", "2164e47d-cd8f-44ce-b063-a87e78b80ec4", "257964a9-d5e2-4f26-a08d-1357de84b9ef", "5938ae9c-9645-432d-bb24-2fc80d7b3c84"]', 'extract-35e7b76278482b96dcd90975177ced03', 'embed-e4f0b4762962cd53b278741ec7f2dea6', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-2115-745d-85c8-4cdd5ae67a11"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 6, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-2dfd-7aad-a103-2620ff2e57e0', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0e7b5-2dde-72ec-accc-a936a3c5fb29", "host_logical_id": "273e3852-e8ab-4383-ad7f-fe3d60f47bc5"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41", "host_logical_id": "b36e8a9d-d079-469f-b817-c47d85616278"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0e7b5-2dde-72ec-accc-a936a3c5fb29"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41"}]', '[]', 164, '{"fit": 0.0, "embed": 14.15, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 0.68, "fits_at": null, "lexical": 2.87, "threads": 0, "extractor": "extract-35e7b7627848", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.71, "embedding_projection": "embed-e4f0b4762962cd", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:05.801552+00', 'packet-v4', 600, 7, '', '["57deb76e-bea9-47d9-9ead-a54c39541fb5", "8a99fec6-9d9b-4207-b1df-d11f8a387f43", "c4229c71-8b1f-4dd3-a674-0260be62c787", "c522fd58-ec6f-4ede-b7f4-a0ae152a6a82"]', 'extract-35e7b76278482b96dcd90975177ced03', 'embed-e4f0b4762962cd53b278741ec7f2dea6', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-2dde-72ec-accc-a936a3c5fb29"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 2, "placed": true}, {"ref": {"revision": "01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 3, "placed": true}]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2164-7076-828c-348e5345b47f', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.666019+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-213c-70af-90d9-5d8ebd125aa0', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.688866+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-213c-7cba-9d7e-206c45c37a60', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.709003+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-213b-7844-a60c-9d8a266b13d6', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.730015+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-213a-7d1b-99f6-e67e767f373e', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.749527+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2116-7e6c-9c5c-9d308fd86545', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.769342+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2115-745d-85c8-4cdd5ae67a11', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.78903+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2114-794b-ac6c-f0624a1ab7f5', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.809294+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2113-7359-9ab5-da2a5b8737fb', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.830189+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-20de-7b40-bf24-30986bec9d97', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.854264+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-20dd-7655-90b2-0102151f0b95', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:03.995884+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:04.015092+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-20da-7ecf-9d76-edb78b5ca883', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:04.033751+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-27c8-7b77-947a-47d6c704dd58', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:05.080493+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-27c7-79e0-8c70-49c363fd994b', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:05.099416+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2775-7e24-aadf-086fe06818af', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:05.119095+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2775-709e-aa2e-99cd39d5b052', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:05.138629+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2774-7119-b0d7-f39dfb8319b2', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:05.157352+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2de2-763c-9764-625141747e0d', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:06.336982+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2de1-74ff-92b0-684d89bccd83', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:06.3569+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2de0-7eff-9f82-9b86d244525d', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:06.37586+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:06.394567+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2dde-72ec-accc-a936a3c5fb29', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:06.413484+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2dde-797f-842d-f52c7651005e', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:06.432882+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-2ddd-7b24-9920-7e81bb976a2f', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-e4f0b4762962cd53b278741ec7f2dea6', '2026-09-28 11:10:06.451764+00');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0e7b5-20da-7ecf-9d76-edb78b5ca883', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:10:02.457406+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:10:02.457406+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-20dd-7655-90b2-0102151f0b95', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-28 11:10:02.457406+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-20de-7b40-bf24-30986bec9d97', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-28 11:10:02.457406+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2113-7359-9ab5-da2a5b8737fb', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:10:02.514146+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2114-794b-ac6c-f0624a1ab7f5', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:10:02.514146+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2115-745d-85c8-4cdd5ae67a11', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-09-28 11:10:02.514146+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2116-7e6c-9c5c-9d308fd86545', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-28 11:10:02.514146+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-213a-7d1b-99f6-e67e767f373e', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-28 11:10:02.553573+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-213b-7844-a60c-9d8a266b13d6', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-28 11:10:02.553573+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-213c-7cba-9d7e-206c45c37a60', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-09-28 11:10:02.553573+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-213c-70af-90d9-5d8ebd125aa0', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-09-28 11:10:02.553573+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2164-7076-828c-348e5345b47f', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-09-28 11:10:02.595385+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2774-7119-b0d7-f39dfb8319b2', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:10:04.147731+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2775-709e-aa2e-99cd39d5b052', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-09-28 11:10:04.147731+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2775-7e24-aadf-086fe06818af', 'clean-v3', 'And the compass?', 16, 16, '2026-09-28 11:10:04.147731+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-279d-7bfe-8549-503bb1e20f08', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-28 11:10:04.188238+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-27c6-77a1-ad56-a0d3bb280a29', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-28 11:10:04.229781+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-27c7-79e0-8c70-49c363fd994b', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-09-28 11:10:04.229781+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-27c8-7b77-947a-47d6c704dd58', 'clean-v3', 'Let''s go.', 9, 9, '2026-09-28 11:10:04.229781+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2ddd-7b24-9920-7e81bb976a2f', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:10:05.788865+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2dde-797f-842d-f52c7651005e', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:10:05.788865+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2dde-72ec-accc-a936a3c5fb29', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-28 11:10:05.788865+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:10:05.788865+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2de0-7eff-9f82-9b86d244525d', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:10:05.788865+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2de1-74ff-92b0-684d89bccd83', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:10:05.788865+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2de2-7716-bd7f-684bfcb580ee', 'clean-v3', '{{specialcomment::branchedfrom::639d7574-da5e-4c87-a60a-ab7c9f64390f::Harbor route::59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4::}}', 124, 124, '2026-09-28 11:10:05.788865+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-2de2-763c-9764-625141747e0d', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-09-28 11:10:05.788865+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-28 11:10:01.508387+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-28 11:10:01.591485+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-28 11:10:01.609186+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-28 11:10:01.65271+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-28 11:10:01.673606+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-28 11:10:01.682375+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-28 11:10:01.684111+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-28 11:10:01.69411+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-28 11:10:01.711964+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-28 11:10:01.714142+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-28 11:10:01.715768+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-28 11:10:01.725012+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-28 11:10:01.750955+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-28 11:10:01.767152+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-28 11:10:01.769867+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-28 11:10:01.782445+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-28 11:10:01.784428+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-28 11:10:01.785976+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-09-28 11:10:01.787511+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-09-28 11:10:01.801219+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-09-28 11:10:01.803257+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0e7b5-20da-76e6-a6bc-760f7f0b68c6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0', 'message', '2026-09-28 11:10:02.457406+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-20dc-70dd-bddd-a97111b63421', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '6e9cc6e3-0fe6-4cc2-8adf-927235bc0211', 'message', '2026-09-28 11:10:02.457406+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-20dd-7138-9af0-4426a7bebd83', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'fa738f50-4cb5-48c5-8762-db4ef50a09d7', 'message', '2026-09-28 11:10:02.457406+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-20de-7f86-a7dd-bbfd2d04ffb3', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '0e41040c-4158-4b3d-ade6-a947e4d9a2b0', 'message', '2026-09-28 11:10:02.457406+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2112-7f7c-8de0-c58a114c3a85', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'a6d08c16-dedc-4e3f-b0ce-80e0b463bb98', 'message', '2026-09-28 11:10:02.514146+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2113-7081-9a04-ab8f314eb12d', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4', 'message', '2026-09-28 11:10:02.514146+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2114-70e4-a47f-7f1985a00d6c', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '6bc5f53f-d973-49c9-89b6-3e95cca6b6a8', 'message', '2026-09-28 11:10:02.514146+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2115-7750-bd2a-5284ba90dc12', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '00c253fa-1c5d-4307-b8a9-f40e23be9720', 'message', '2026-09-28 11:10:02.514146+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-213a-7b3f-a376-950b930c81d6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '61af0df1-52a5-4961-94f0-491e2dddad97', 'message', '2026-09-28 11:10:02.553573+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-213a-720f-a62e-e495a9dace6f', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', 'ac90526c-c7cf-4ecf-9afa-76329149b711', 'message', '2026-09-28 11:10:02.553573+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-213b-738c-a758-f620d4fa8fc4', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '5ab2ae85-762e-4719-bc30-a77170b547f5', 'message', '2026-09-28 11:10:02.553573+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-213c-78db-a28b-a5ade30daba6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '6b0b474d-5296-4c13-869a-c7fa687e8a50', 'message', '2026-09-28 11:10:02.553573+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2163-78a5-8c8d-53acf2e9ad73', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '30bb5d2c-7bb5-448f-821f-5fed48647096', 'message', '2026-09-28 11:10:02.595385+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2775-77f0-8eee-438e91905c94', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '5938ae9c-9645-432d-bb24-2fc80d7b3c84', 'message', '2026-09-28 11:10:04.147731+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2775-7e78-af45-7123332034ab', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '2164e47d-cd8f-44ce-b063-a87e78b80ec4', 'message', '2026-09-28 11:10:04.147731+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-279c-7097-921d-d5a855ff77f6', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '04854e26-fbd3-47fc-841d-8163f9d9b232', 'message', '2026-09-28 11:10:04.188238+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-27c8-7b5f-9218-da752da5dba8', '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '257964a9-d5e2-4f26-a08d-1357de84b9ef', 'message', '2026-09-28 11:10:04.229781+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2ddd-78d4-a95b-e9c7184fcc80', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', 'cf3ff4ac-6940-40a5-a569-275f83510a09', 'message', '2026-09-28 11:10:05.788865+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2ddd-7e49-b0bf-b49e386b59d8', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '0bf0142d-96bf-4db0-a326-6d7cfd1984cb', 'message', '2026-09-28 11:10:05.788865+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2dde-73a9-a134-4ad63443b03a', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '273e3852-e8ab-4383-ad7f-fe3d60f47bc5', 'message', '2026-09-28 11:10:05.788865+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2ddf-7fdf-b24a-55afb8e01aa6', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', 'b36e8a9d-d079-469f-b817-c47d85616278', 'message', '2026-09-28 11:10:05.788865+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2de0-7318-8562-f07a505c4b55', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', 'c4229c71-8b1f-4dd3-a674-0260be62c787', 'message', '2026-09-28 11:10:05.788865+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2de0-7ce8-a2b9-d582812f08cd', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '57deb76e-bea9-47d9-9ead-a54c39541fb5', 'message', '2026-09-28 11:10:05.788865+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2de1-7c02-97eb-a0d5d016290f', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', 'c522fd58-ec6f-4ede-b7f4-a0ae152a6a82', 'message', '2026-09-28 11:10:05.788865+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-2de2-7214-9d30-a2e1aeedd2bc', '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '8a99fec6-9d9b-4207-b1df-d11f8a387f43', 'message', '2026-09-28 11:10:05.788865+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0e7b5-20da-7ecf-9d76-edb78b5ca883', '01a0e7b5-20da-76e6-a6bc-760f7f0b68c6', 'fdb0c67d3a237cbdf28efa890c1335e4ef7d2ba0a9cf1261fd8e8566e7bc36ad', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:02.457406+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-20dd-7655-90b2-0102151f0b95', '01a0e7b5-20dd-7138-9af0-4426a7bebd83', 'd29544fce5de10cdeaaa56eeea7d6e906098f306e220c6281bc08cefde2166d5', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "fa738f50-4cb5-48c5-8762-db4ef50a09d7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:02.457406+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-20dc-7d2a-a217-00d95a6b3fbc', '01a0e7b5-20dc-70dd-bddd-a97111b63421', 'b759a46b5489e7e814ce7d3498b89899ab8abd90ce7a3c9d73eb37fbc0468a3a', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "specialComments": []}', '2026-09-28 11:10:02.457406+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2113-7359-9ab5-da2a5b8737fb', '01a0e7b5-2112-7f7c-8de0-c58a114c3a85', '4b35fb09784acd8884eafbfe17f5ca8b68a782d8d4d426a3e2d29f20bd420c91', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "a6d08c16-dedc-4e3f-b0ce-80e0b463bb98", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:02.514146+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2115-745d-85c8-4cdd5ae67a11', '01a0e7b5-2114-70e4-a47f-7f1985a00d6c', '7e3ecd3ca7269f4cae8ffdfbfc9bb79b2dc00ef9f842f360eb393ac09d8a2890', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "6bc5f53f-d973-49c9-89b6-3e95cca6b6a8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:02.514146+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-213a-7d1b-99f6-e67e767f373e', '01a0e7b5-213a-7b3f-a376-950b930c81d6', '667550678330d0132518136c11303758f555a324706e06bd50b8cb008c2a1b85', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "61af0df1-52a5-4961-94f0-491e2dddad97", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:02.553573+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2114-794b-ac6c-f0624a1ab7f5', '01a0e7b5-2113-7081-9a04-ab8f314eb12d', '8eb30031f0e10c03c2b88a336b142659998dd2e4603b348eeb3427b255543653', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "specialComments": []}', '2026-09-28 11:10:02.514146+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-213c-7cba-9d7e-206c45c37a60', '01a0e7b5-213b-738c-a758-f620d4fa8fc4', '7d6594de632fa8e8ea1e6cb6fd922174600cc32e750069e451df1fc6e5756879', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "5ab2ae85-762e-4719-bc30-a77170b547f5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:02.553573+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2116-7e6c-9c5c-9d308fd86545', '01a0e7b5-2115-7750-bd2a-5284ba90dc12', 'e60838eb910ba8aada0af1e976cd67f9b21a0b8d3a3f32cef17fa5a55b9a2991', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "00c253fa-1c5d-4307-b8a9-f40e23be9720", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "00c253fa-1c5d-4307-b8a9-f40e23be9720", "specialComments": []}', '2026-09-28 11:10:02.514146+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-213b-7844-a60c-9d8a266b13d6', '01a0e7b5-213a-720f-a62e-e495a9dace6f', '5b3bebf630f2109261ec09420613793d316eeae758d0c74bde99f6af29556d51', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "ac90526c-c7cf-4ecf-9afa-76329149b711", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "ac90526c-c7cf-4ecf-9afa-76329149b711", "specialComments": []}', '2026-09-28 11:10:02.553573+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2164-7076-828c-348e5345b47f', '01a0e7b5-2163-78a5-8c8d-53acf2e9ad73', '50d47a8eedca12fddbcfd0af23c999726e3f598d1022228d0e05411644bacf71', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "30bb5d2c-7bb5-448f-821f-5fed48647096", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:02.595385+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-213c-70af-90d9-5d8ebd125aa0', '01a0e7b5-213c-78db-a28b-a5ade30daba6', '53b898cf68752332543b573a40d0133c3da13054ce6d007b60a71eaeb3913d7c', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "6b0b474d-5296-4c13-869a-c7fa687e8a50", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6b0b474d-5296-4c13-869a-c7fa687e8a50", "specialComments": []}', '2026-09-28 11:10:02.553573+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2775-7e24-aadf-086fe06818af', '01a0e7b5-2775-7e78-af45-7123332034ab', 'ca5256def799a0f22e8018598074970e376dd1a904cc95b0a68a008d257d21c4', 'And the compass?', '{"name": null, "role": "user", "chatId": "2164e47d-cd8f-44ce-b063-a87e78b80ec4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:04.147731+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-20de-7b40-bf24-30986bec9d97', '01a0e7b5-20de-7f86-a7dd-bbfd2d04ffb3', 'b5f75a5928bdb40d3ede9b1f78a25d8238824f099324153891a6b85736c89268', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "specialComments": []}', '2026-09-28 11:10:02.457406+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2774-7119-b0d7-f39dfb8319b2', '01a0e7b5-20de-7f86-a7dd-bbfd2d04ffb3', 'ca09907fe0a053cafc022934dc5b6c13a83a053d3ee41ac087c17de651b2bd0a', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "specialComments": []}', '2026-09-28 11:10:04.147731+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2775-709e-aa2e-99cd39d5b052', '01a0e7b5-2775-77f0-8eee-438e91905c94', '60a5ac8bab10e35c748df1f956a66f5b2196b433b5f5221249956eb8702161ed', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "5938ae9c-9645-432d-bb24-2fc80d7b3c84", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "5938ae9c-9645-432d-bb24-2fc80d7b3c84", "specialComments": []}', '2026-09-28 11:10:04.147731+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-27c6-77a1-ad56-a0d3bb280a29', '01a0e7b5-213a-7b3f-a376-950b930c81d6', 'eb8d2e0c839d775001f7bf78e52ea2299b104374d01ceb6b97449bc004fd77e5', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "61af0df1-52a5-4961-94f0-491e2dddad97", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:04.229781+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-27c8-7b77-947a-47d6c704dd58', '01a0e7b5-27c8-7b5f-9218-da752da5dba8', '146984ad54312dbe6b69d136f6bea838583602c2722e4995bf7d60f192b8064d', 'Let''s go.', '{"name": null, "role": "user", "chatId": "257964a9-d5e2-4f26-a08d-1357de84b9ef", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:04.229781+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-27c7-79e0-8c70-49c363fd994b', '01a0e7b5-279c-7097-921d-d5a855ff77f6', '04515d12a9232684d3036bdb84590b7d744735187d5ad66aed9cc3f7ffab8b14', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "04854e26-fbd3-47fc-841d-8163f9d9b232", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "04854e26-fbd3-47fc-841d-8163f9d9b232", "specialComments": []}', '2026-09-28 11:10:04.229781+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-279d-7bfe-8549-503bb1e20f08', '01a0e7b5-279c-7097-921d-d5a855ff77f6', 'ef851653440f5f1a3d4c39176fc86107e6f2c84f85a874b8497c385bcd40a73b', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "04854e26-fbd3-47fc-841d-8163f9d9b232", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "04854e26-fbd3-47fc-841d-8163f9d9b232", "specialComments": []}', '2026-09-28 11:10:04.188238+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2ddd-7b24-9920-7e81bb976a2f', '01a0e7b5-2ddd-78d4-a95b-e9c7184fcc80', '770a35cadbae253c81752fb4d8fac11d5865bceb2f9d29050171657567636dd4', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "cf3ff4ac-6940-40a5-a569-275f83510a09", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:05.788865+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2dde-72ec-accc-a936a3c5fb29', '01a0e7b5-2dde-73a9-a134-4ad63443b03a', '4bc8f7688da153e23ab7fb26153072b4d6d27590665f23298eda135ac8fa1e77', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "273e3852-e8ab-4383-ad7f-fe3d60f47bc5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:05.788865+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2de0-7eff-9f82-9b86d244525d', '01a0e7b5-2de0-7318-8562-f07a505c4b55', '8636d304980d45ec07067e78a94056d33e5755d2a50c14abcfea3249d5395c94', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "c4229c71-8b1f-4dd3-a674-0260be62c787", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:05.788865+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2de2-7716-bd7f-684bfcb580ee', '01a0e7b5-2de1-7c02-97eb-a0d5d016290f', '036c9ec43082ef06e184af3cfedcda2d95b910a6c356ff20a3fe6e2d0b55b3dd', '{{specialcomment::branchedfrom::639d7574-da5e-4c87-a60a-ab7c9f64390f::Harbor route::59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4::}}', '{"name": null, "role": "char", "chatId": "c522fd58-ec6f-4ede-b7f4-a0ae152a6a82", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::639d7574-da5e-4c87-a60a-ab7c9f64390f::Harbor route::59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4::}}"]}', '2026-09-28 11:10:05.788865+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2de2-763c-9764-625141747e0d', '01a0e7b5-2de2-7214-9d30-a2e1aeedd2bc', 'b6354cd750101e02f009cec99a7ab6eb59a3e8eff03519f0a162e2fb0cd229d0', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "8a99fec6-9d9b-4207-b1df-d11f8a387f43", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:05.788865+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2dde-797f-842d-f52c7651005e', '01a0e7b5-2ddd-7e49-b0bf-b49e386b59d8', 'e408bdd346239f4780a97f5740213a74a875d1574ae3b860ddf4aa4ec8a2d8ea', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "0bf0142d-96bf-4db0-a326-6d7cfd1984cb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "specialComments": []}', '2026-09-28 11:10:05.788865+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2de1-74ff-92b0-684d89bccd83', '01a0e7b5-2de0-7ce8-a2b9-d582812f08cd', 'b0067213cd013f455edd9abcd381404084d7c18f711af3f926442955a82ff0e9', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "57deb76e-bea9-47d9-9ead-a54c39541fb5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "specialComments": []}', '2026-09-28 11:10:05.788865+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-2ddf-775d-a37f-2dfdd9b3dc41', '01a0e7b5-2ddf-7fdf-b24a-55afb8e01aa6', '41f952c653b46087914bf1ed92edab391335957e9c56cc24d39c4bcbdfbbf766', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "b36e8a9d-d079-469f-b817-c47d85616278", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "specialComments": []}', '2026-09-28 11:10:05.788865+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0e7b5-20e0-75f6-b502-623c1d4568b0', '[{"op": "insert", "after": ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "b5f75a5928bdb40d3ede9b1f78a25d8238824f099324153891a6b85736c89268"], "member": ["a6d08c16-dedc-4e3f-b0ce-80e0b463bb98", "4b35fb09784acd8884eafbfe17f5ca8b68a782d8d4d426a3e2d29f20bd420c91"]}, {"op": "insert", "after": ["a6d08c16-dedc-4e3f-b0ce-80e0b463bb98", "4b35fb09784acd8884eafbfe17f5ca8b68a782d8d4d426a3e2d29f20bd420c91"], "member": ["59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "8eb30031f0e10c03c2b88a336b142659998dd2e4603b348eeb3427b255543653"]}, {"op": "insert", "after": ["59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "8eb30031f0e10c03c2b88a336b142659998dd2e4603b348eeb3427b255543653"], "member": ["6bc5f53f-d973-49c9-89b6-3e95cca6b6a8", "7e3ecd3ca7269f4cae8ffdfbfc9bb79b2dc00ef9f842f360eb393ac09d8a2890"]}, {"op": "insert", "after": ["6bc5f53f-d973-49c9-89b6-3e95cca6b6a8", "7e3ecd3ca7269f4cae8ffdfbfc9bb79b2dc00ef9f842f360eb393ac09d8a2890"], "member": ["00c253fa-1c5d-4307-b8a9-f40e23be9720", "e60838eb910ba8aada0af1e976cd67f9b21a0b8d3a3f32cef17fa5a55b9a2991"]}]', '[{"new": ["a6d08c16-dedc-4e3f-b0ce-80e0b463bb98", "4b35fb09784acd8884eafbfe17f5ca8b68a782d8d4d426a3e2d29f20bd420c91"], "old": null, "kind": "append", "position": 4, "host_logical_id": "a6d08c16-dedc-4e3f-b0ce-80e0b463bb98"}, {"new": ["59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4", "8eb30031f0e10c03c2b88a336b142659998dd2e4603b348eeb3427b255543653"], "old": null, "kind": "append", "position": 5, "host_logical_id": "59e89593-e4e5-4bd9-8f4a-a3e2cfa59ad4"}, {"new": ["6bc5f53f-d973-49c9-89b6-3e95cca6b6a8", "7e3ecd3ca7269f4cae8ffdfbfc9bb79b2dc00ef9f842f360eb393ac09d8a2890"], "old": null, "kind": "append", "position": 6, "host_logical_id": "6bc5f53f-d973-49c9-89b6-3e95cca6b6a8"}, {"new": ["00c253fa-1c5d-4307-b8a9-f40e23be9720", "e60838eb910ba8aada0af1e976cd67f9b21a0b8d3a3f32cef17fa5a55b9a2991"], "old": null, "kind": "append", "position": 7, "host_logical_id": "00c253fa-1c5d-4307-b8a9-f40e23be9720"}]', '01a0e7b5-2118-72eb-aa3f-19150ae1aee1', '2026-09-28 11:10:02.514146+00');
INSERT INTO public.worldline_append VALUES (2, '01a0e7b5-20e0-75f6-b502-623c1d4568b0', '[{"op": "insert", "after": ["00c253fa-1c5d-4307-b8a9-f40e23be9720", "e60838eb910ba8aada0af1e976cd67f9b21a0b8d3a3f32cef17fa5a55b9a2991"], "member": ["61af0df1-52a5-4961-94f0-491e2dddad97", "667550678330d0132518136c11303758f555a324706e06bd50b8cb008c2a1b85"]}, {"op": "insert", "after": ["61af0df1-52a5-4961-94f0-491e2dddad97", "667550678330d0132518136c11303758f555a324706e06bd50b8cb008c2a1b85"], "member": ["ac90526c-c7cf-4ecf-9afa-76329149b711", "5b3bebf630f2109261ec09420613793d316eeae758d0c74bde99f6af29556d51"]}, {"op": "insert", "after": ["ac90526c-c7cf-4ecf-9afa-76329149b711", "5b3bebf630f2109261ec09420613793d316eeae758d0c74bde99f6af29556d51"], "member": ["5ab2ae85-762e-4719-bc30-a77170b547f5", "7d6594de632fa8e8ea1e6cb6fd922174600cc32e750069e451df1fc6e5756879"]}, {"op": "insert", "after": ["5ab2ae85-762e-4719-bc30-a77170b547f5", "7d6594de632fa8e8ea1e6cb6fd922174600cc32e750069e451df1fc6e5756879"], "member": ["6b0b474d-5296-4c13-869a-c7fa687e8a50", "53b898cf68752332543b573a40d0133c3da13054ce6d007b60a71eaeb3913d7c"]}]', '[{"new": ["61af0df1-52a5-4961-94f0-491e2dddad97", "667550678330d0132518136c11303758f555a324706e06bd50b8cb008c2a1b85"], "old": null, "kind": "append", "position": 8, "host_logical_id": "61af0df1-52a5-4961-94f0-491e2dddad97"}, {"new": ["ac90526c-c7cf-4ecf-9afa-76329149b711", "5b3bebf630f2109261ec09420613793d316eeae758d0c74bde99f6af29556d51"], "old": null, "kind": "append", "position": 9, "host_logical_id": "ac90526c-c7cf-4ecf-9afa-76329149b711"}, {"new": ["5ab2ae85-762e-4719-bc30-a77170b547f5", "7d6594de632fa8e8ea1e6cb6fd922174600cc32e750069e451df1fc6e5756879"], "old": null, "kind": "append", "position": 10, "host_logical_id": "5ab2ae85-762e-4719-bc30-a77170b547f5"}, {"new": ["6b0b474d-5296-4c13-869a-c7fa687e8a50", "53b898cf68752332543b573a40d0133c3da13054ce6d007b60a71eaeb3913d7c"], "old": null, "kind": "append", "position": 11, "host_logical_id": "6b0b474d-5296-4c13-869a-c7fa687e8a50"}]', '01a0e7b5-213f-7b93-b19c-9662c15e6afd', '2026-09-28 11:10:02.553573+00');
INSERT INTO public.worldline_append VALUES (3, '01a0e7b5-20e0-75f6-b502-623c1d4568b0', '[{"op": "insert", "after": ["6b0b474d-5296-4c13-869a-c7fa687e8a50", "53b898cf68752332543b573a40d0133c3da13054ce6d007b60a71eaeb3913d7c"], "member": ["30bb5d2c-7bb5-448f-821f-5fed48647096", "50d47a8eedca12fddbcfd0af23c999726e3f598d1022228d0e05411644bacf71"]}]', '[{"new": ["30bb5d2c-7bb5-448f-821f-5fed48647096", "50d47a8eedca12fddbcfd0af23c999726e3f598d1022228d0e05411644bacf71"], "old": null, "kind": "append", "position": 12, "host_logical_id": "30bb5d2c-7bb5-448f-821f-5fed48647096"}]', '01a0e7b5-2167-7eca-91a9-e181bcc70f43', '2026-09-28 11:10:02.595385+00');
INSERT INTO public.worldline_append VALUES (4, '01a0e7b5-2779-7a5c-a336-cf065dae6f7c', '[{"op": "insert", "after": ["2164e47d-cd8f-44ce-b063-a87e78b80ec4", "ca5256def799a0f22e8018598074970e376dd1a904cc95b0a68a008d257d21c4"], "member": ["04854e26-fbd3-47fc-841d-8163f9d9b232", "ef851653440f5f1a3d4c39176fc86107e6f2c84f85a874b8497c385bcd40a73b"]}]', '[{"new": ["04854e26-fbd3-47fc-841d-8163f9d9b232", "ef851653440f5f1a3d4c39176fc86107e6f2c84f85a874b8497c385bcd40a73b"], "old": null, "kind": "append", "position": 15, "host_logical_id": "04854e26-fbd3-47fc-841d-8163f9d9b232"}]', '01a0e7b5-27a0-78c5-89e4-739222f59d60', '2026-09-28 11:10:04.188238+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-20e0-75f6-b502-623c1d4568b0', 1, '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{}', 'import', 'be6a8d1bc1384a900fee0206aea8fa31ca489f2e625a36fc885cf904ec2dea54', '{"ops": [{"op": "set", "members": [["0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0", "fdb0c67d3a237cbdf28efa890c1335e4ef7d2ba0a9cf1261fd8e8566e7bc36ad"], ["6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "b759a46b5489e7e814ce7d3498b89899ab8abd90ce7a3c9d73eb37fbc0468a3a"], ["fa738f50-4cb5-48c5-8762-db4ef50a09d7", "d29544fce5de10cdeaaa56eeea7d6e906098f306e220c6281bc08cefde2166d5"], ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "b5f75a5928bdb40d3ede9b1f78a25d8238824f099324153891a6b85736c89268"]]}], "changes": [{"new": ["0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0", "fdb0c67d3a237cbdf28efa890c1335e4ef7d2ba0a9cf1261fd8e8566e7bc36ad"], "old": null, "kind": "append", "position": 0, "host_logical_id": "0f6fcb8c-b7fb-4e83-9ce4-21fee26058a0"}, {"new": ["6e9cc6e3-0fe6-4cc2-8adf-927235bc0211", "b759a46b5489e7e814ce7d3498b89899ab8abd90ce7a3c9d73eb37fbc0468a3a"], "old": null, "kind": "append", "position": 1, "host_logical_id": "6e9cc6e3-0fe6-4cc2-8adf-927235bc0211"}, {"new": ["fa738f50-4cb5-48c5-8762-db4ef50a09d7", "d29544fce5de10cdeaaa56eeea7d6e906098f306e220c6281bc08cefde2166d5"], "old": null, "kind": "append", "position": 2, "host_logical_id": "fa738f50-4cb5-48c5-8762-db4ef50a09d7"}, {"new": ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "b5f75a5928bdb40d3ede9b1f78a25d8238824f099324153891a6b85736c89268"], "old": null, "kind": "append", "position": 3, "host_logical_id": "0e41040c-4158-4b3d-ade6-a947e4d9a2b0"}]}', '2026-09-28 11:10:02.457406+00', '01a0e7b5-20df-7992-bdcf-2f5c66e405be');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-2779-7a5c-a336-cf065dae6f7c', 2, '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{01a0e7b5-20e0-75f6-b502-623c1d4568b0}', 'edit', '95ea12758e0566e64cfa71c4c1f3d77610977ac0285826dc0294261d50c5462d', '{"ops": [{"op": "replace", "to": ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "ca09907fe0a053cafc022934dc5b6c13a83a053d3ee41ac087c17de651b2bd0a"], "from": ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "b5f75a5928bdb40d3ede9b1f78a25d8238824f099324153891a6b85736c89268"]}, {"op": "insert", "after": ["30bb5d2c-7bb5-448f-821f-5fed48647096", "50d47a8eedca12fddbcfd0af23c999726e3f598d1022228d0e05411644bacf71"], "member": ["5938ae9c-9645-432d-bb24-2fc80d7b3c84", "60a5ac8bab10e35c748df1f956a66f5b2196b433b5f5221249956eb8702161ed"]}, {"op": "insert", "after": ["5938ae9c-9645-432d-bb24-2fc80d7b3c84", "60a5ac8bab10e35c748df1f956a66f5b2196b433b5f5221249956eb8702161ed"], "member": ["2164e47d-cd8f-44ce-b063-a87e78b80ec4", "ca5256def799a0f22e8018598074970e376dd1a904cc95b0a68a008d257d21c4"]}], "changes": [{"new": ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "ca09907fe0a053cafc022934dc5b6c13a83a053d3ee41ac087c17de651b2bd0a"], "old": ["0e41040c-4158-4b3d-ade6-a947e4d9a2b0", "b5f75a5928bdb40d3ede9b1f78a25d8238824f099324153891a6b85736c89268"], "kind": "edit", "position": 3, "host_logical_id": "0e41040c-4158-4b3d-ade6-a947e4d9a2b0"}, {"new": ["5938ae9c-9645-432d-bb24-2fc80d7b3c84", "60a5ac8bab10e35c748df1f956a66f5b2196b433b5f5221249956eb8702161ed"], "old": null, "kind": "append", "position": 13, "host_logical_id": "5938ae9c-9645-432d-bb24-2fc80d7b3c84"}, {"new": ["2164e47d-cd8f-44ce-b063-a87e78b80ec4", "ca5256def799a0f22e8018598074970e376dd1a904cc95b0a68a008d257d21c4"], "old": null, "kind": "append", "position": 14, "host_logical_id": "2164e47d-cd8f-44ce-b063-a87e78b80ec4"}]}', '2026-09-28 11:10:04.147731+00', '01a0e7b5-2778-7c81-87e7-c0ef4d5cfecd');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-27cb-7b67-993b-678a3177503c', 3, '01a0e7b5-20cb-7021-b60c-61f7e017c02d', '{01a0e7b5-2779-7a5c-a336-cf065dae6f7c}', 'reconciliation', '355b944de5b2d09debd74e4e59cab8a38f79dbfa09f77cad52d87bf2d886a861', '{"ops": [{"op": "replace", "to": ["61af0df1-52a5-4961-94f0-491e2dddad97", "eb8d2e0c839d775001f7bf78e52ea2299b104374d01ceb6b97449bc004fd77e5"], "from": ["61af0df1-52a5-4961-94f0-491e2dddad97", "667550678330d0132518136c11303758f555a324706e06bd50b8cb008c2a1b85"]}, {"op": "replace", "to": ["04854e26-fbd3-47fc-841d-8163f9d9b232", "04515d12a9232684d3036bdb84590b7d744735187d5ad66aed9cc3f7ffab8b14"], "from": ["04854e26-fbd3-47fc-841d-8163f9d9b232", "ef851653440f5f1a3d4c39176fc86107e6f2c84f85a874b8497c385bcd40a73b"]}, {"op": "insert", "after": ["04854e26-fbd3-47fc-841d-8163f9d9b232", "04515d12a9232684d3036bdb84590b7d744735187d5ad66aed9cc3f7ffab8b14"], "member": ["257964a9-d5e2-4f26-a08d-1357de84b9ef", "146984ad54312dbe6b69d136f6bea838583602c2722e4995bf7d60f192b8064d"]}], "changes": [{"new": ["61af0df1-52a5-4961-94f0-491e2dddad97", "eb8d2e0c839d775001f7bf78e52ea2299b104374d01ceb6b97449bc004fd77e5"], "old": ["61af0df1-52a5-4961-94f0-491e2dddad97", "667550678330d0132518136c11303758f555a324706e06bd50b8cb008c2a1b85"], "kind": "disable", "position": 8, "host_logical_id": "61af0df1-52a5-4961-94f0-491e2dddad97"}, {"new": ["04854e26-fbd3-47fc-841d-8163f9d9b232", "04515d12a9232684d3036bdb84590b7d744735187d5ad66aed9cc3f7ffab8b14"], "old": ["04854e26-fbd3-47fc-841d-8163f9d9b232", "ef851653440f5f1a3d4c39176fc86107e6f2c84f85a874b8497c385bcd40a73b"], "kind": "swipe", "position": 15, "host_logical_id": "04854e26-fbd3-47fc-841d-8163f9d9b232"}, {"new": ["257964a9-d5e2-4f26-a08d-1357de84b9ef", "146984ad54312dbe6b69d136f6bea838583602c2722e4995bf7d60f192b8064d"], "old": null, "kind": "append", "position": 16, "host_logical_id": "257964a9-d5e2-4f26-a08d-1357de84b9ef"}]}', '2026-09-28 11:10:04.229781+00', '01a0e7b5-27ca-793a-a3c1-a4d5abca1b94');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-2de4-70f6-aaef-f1f6f542333d', 4, '01a0e7b5-2dd0-7bf8-afe6-6a7173673a7f', '{}', 'branch', '6444119e56594b6003f0a6e02ff6f8a067737bb2a5f4669907116413ad3daf0a', '{"ops": [{"op": "set", "members": [["cf3ff4ac-6940-40a5-a569-275f83510a09", "770a35cadbae253c81752fb4d8fac11d5865bceb2f9d29050171657567636dd4"], ["0bf0142d-96bf-4db0-a326-6d7cfd1984cb", "e408bdd346239f4780a97f5740213a74a875d1574ae3b860ddf4aa4ec8a2d8ea"], ["273e3852-e8ab-4383-ad7f-fe3d60f47bc5", "4bc8f7688da153e23ab7fb26153072b4d6d27590665f23298eda135ac8fa1e77"], ["b36e8a9d-d079-469f-b817-c47d85616278", "41f952c653b46087914bf1ed92edab391335957e9c56cc24d39c4bcbdfbbf766"], ["c4229c71-8b1f-4dd3-a674-0260be62c787", "8636d304980d45ec07067e78a94056d33e5755d2a50c14abcfea3249d5395c94"], ["57deb76e-bea9-47d9-9ead-a54c39541fb5", "b0067213cd013f455edd9abcd381404084d7c18f711af3f926442955a82ff0e9"], ["c522fd58-ec6f-4ede-b7f4-a0ae152a6a82", "036c9ec43082ef06e184af3cfedcda2d95b910a6c356ff20a3fe6e2d0b55b3dd"], ["8a99fec6-9d9b-4207-b1df-d11f8a387f43", "b6354cd750101e02f009cec99a7ab6eb59a3e8eff03519f0a162e2fb0cd229d0"]]}], "changes": [{"new": ["cf3ff4ac-6940-40a5-a569-275f83510a09", "770a35cadbae253c81752fb4d8fac11d5865bceb2f9d29050171657567636dd4"], "old": null, "kind": "append", "position": 0, "host_logical_id": "cf3ff4ac-6940-40a5-a569-275f83510a09"}, {"new": ["0bf0142d-96bf-4db0-a326-6d7cfd1984cb", "e408bdd346239f4780a97f5740213a74a875d1574ae3b860ddf4aa4ec8a2d8ea"], "old": null, "kind": "append", "position": 1, "host_logical_id": "0bf0142d-96bf-4db0-a326-6d7cfd1984cb"}, {"new": ["273e3852-e8ab-4383-ad7f-fe3d60f47bc5", "4bc8f7688da153e23ab7fb26153072b4d6d27590665f23298eda135ac8fa1e77"], "old": null, "kind": "append", "position": 2, "host_logical_id": "273e3852-e8ab-4383-ad7f-fe3d60f47bc5"}, {"new": ["b36e8a9d-d079-469f-b817-c47d85616278", "41f952c653b46087914bf1ed92edab391335957e9c56cc24d39c4bcbdfbbf766"], "old": null, "kind": "append", "position": 3, "host_logical_id": "b36e8a9d-d079-469f-b817-c47d85616278"}, {"new": ["c4229c71-8b1f-4dd3-a674-0260be62c787", "8636d304980d45ec07067e78a94056d33e5755d2a50c14abcfea3249d5395c94"], "old": null, "kind": "append", "position": 4, "host_logical_id": "c4229c71-8b1f-4dd3-a674-0260be62c787"}, {"new": ["57deb76e-bea9-47d9-9ead-a54c39541fb5", "b0067213cd013f455edd9abcd381404084d7c18f711af3f926442955a82ff0e9"], "old": null, "kind": "append", "position": 5, "host_logical_id": "57deb76e-bea9-47d9-9ead-a54c39541fb5"}, {"new": ["c522fd58-ec6f-4ede-b7f4-a0ae152a6a82", "036c9ec43082ef06e184af3cfedcda2d95b910a6c356ff20a3fe6e2d0b55b3dd"], "old": null, "kind": "append", "position": 6, "host_logical_id": "c522fd58-ec6f-4ede-b7f4-a0ae152a6a82"}, {"new": ["8a99fec6-9d9b-4207-b1df-d11f8a387f43", "b6354cd750101e02f009cec99a7ab6eb59a3e8eff03519f0a162e2fb0cd229d0"], "old": null, "kind": "append", "position": 7, "host_logical_id": "8a99fec6-9d9b-4207-b1df-d11f8a387f43"}]}', '2026-09-28 11:10:05.788865+00', '01a0e7b5-2de3-76f4-b008-f5933453671c');


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


