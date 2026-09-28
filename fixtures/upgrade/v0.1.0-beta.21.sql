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
    host_persona_name text
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

INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 0, '01a0e7b5-075e-7e6d-b338-794c3f6f57be', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 1, '01a0e7b5-0761-730f-8d9e-b0cff6a3dae4', NULL, 0, '35e5994b595faa4ff91361cf4537880d');
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 2, '01a0e7b5-0761-7bbb-b9a1-dfe4890135a3', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 3, '01a0e7b5-0dff-702d-b2e6-c3a4e7493501', NULL, 1, '319d395546abef681dd3d21a72b9a02c');
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 4, '01a0e7b5-0798-790b-8f45-440966429dd4', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 5, '01a0e7b5-0799-7928-96e5-9b8adf91c6f6', NULL, 2, '07f2b000863e2438f4b220e2cf6bff82');
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 6, '01a0e7b5-079a-7e5b-aabf-d12ccb5a421b', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 7, '01a0e7b5-079a-7622-af08-db1df68add2f', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 8, '01a0e7b5-0e4e-7b15-9708-86e2c70427a7', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 9, '01a0e7b5-07cb-7856-9f40-fec804720311', NULL, 3, 'd6b4b5ba4092256da725b3992224623b');
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 10, '01a0e7b5-07cc-766b-b207-4e45719027e3', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 11, '01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4', NULL, 4, '411df4e4007758439ea2c0d64475fddd');
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 12, '01a0e7b5-07f3-7fee-bc41-1c7da88dc283', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 13, '01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d', NULL, 5, 'd3f73bb81072859c95f0098e9eb9d4f6');
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 14, '01a0e7b5-0e00-7c0c-96b8-99034cd44ee6', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 15, '01a0e7b5-0e4e-70bd-978b-51f59946e64a', NULL, 6, '4bc987c9c0e8f18312e952745d5fa8a1');
INSERT INTO public.active_membership VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 16, '01a0e7b5-0e4f-7235-ad87-24100c6ca2e5', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 0, '01a0e7b5-1463-748a-b48b-c948c2f60b58', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 1, '01a0e7b5-1464-7466-b1ac-2b210d9a190b', NULL, 0, '3560839149dac8654c3f170c3d393c17');
INSERT INTO public.active_membership VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 2, '01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 3, '01a0e7b5-1465-74b5-8b22-1e6d83d913d9', NULL, 1, '810665656207d8318de4ea40d679a410');
INSERT INTO public.active_membership VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 4, '01a0e7b5-1466-7906-be46-17f434542d68', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 5, '01a0e7b5-1467-712e-897a-3381d86c275a', NULL, 2, 'e386ba679ddd98acdf669ac8426e8d79');
INSERT INTO public.active_membership VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 6, '01a0e7b5-1467-7fef-9f54-4af3f344de1b', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 7, '01a0e7b5-1468-7ae6-89fa-32142af0da5f', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0e7b5-0ce7-776b-9916-bf432f5aed71', '01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0e7b5-0d00-7629-b0fc-a310abc3b498', '01a0e7b5-07cb-7856-9f40-fec804720311', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0e7b5-0d2e-7511-bd1b-8e72aed76339', '01a0e7b5-0799-7928-96e5-9b8adf91c6f6', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0e7b5-0d45-7f9e-bf69-f5b1bebd3e56', '01a0e7b5-0762-792d-b99f-f6474ba220e7', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0e7b5-0d45-7f9e-bf69-f5b1bebd3e56', '01a0e7b5-0762-792d-b99f-f6474ba220e7', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0e7b5-0d97-7692-aa35-cf58f55bb173', '01a0e7b5-0761-730f-8d9e-b0cff6a3dae4', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0e7b5-0d97-7692-aa35-cf58f55bb173', '01a0e7b5-0761-730f-8d9e-b0cff6a3dae4', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0e7b5-11fd-7c98-a4e4-3b61d626e793', '01a0e7b5-0e4e-70bd-978b-51f59946e64a', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0e7b5-122b-7f5b-a68e-f995a3ac0f3f', '01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0e7b5-1240-7401-9f71-5bea2431f6fc', '01a0e7b5-07cb-7856-9f40-fec804720311', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0e7b5-1263-7cfe-9a91-8ce9ba484db3', '01a0e7b5-0799-7928-96e5-9b8adf91c6f6', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0e7b5-1277-7083-a81b-b1c789b24181', '01a0e7b5-0dff-702d-b2e6-c3a4e7493501', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0e7b5-1277-7083-a81b-b1c789b24181', '01a0e7b5-0dff-702d-b2e6-c3a4e7493501', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0e7b5-16f9-7762-ac06-d5467db9dd57', '01a0e7b5-1467-712e-897a-3381d86c275a', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0e7b5-170f-7ffc-9e13-8e86f1d0fdd0', '01a0e7b5-1465-74b5-8b22-1e6d83d913d9', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0e7b5-170f-7ffc-9e13-8e86f1d0fdd0', '01a0e7b5-1465-74b5-8b22-1e6d83d913d9', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0e7b5-1724-7d54-a77d-d55245fbf576', '01a0e7b5-1464-7466-b1ac-2b210d9a190b', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0e7b5-1724-7d54-a77d-d55245fbf576', '01a0e7b5-1464-7466-b1ac-2b210d9a190b', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0e7b5-0756-79a1-9f83-ef04295be44f', 'pocketrisu', NULL, 'd3822c6c-3bde-4ec7-8712-8e0d6bef57bc', '2026-09-28 11:09:55.926509+00', NULL, NULL, NULL, '01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', '2e2291d9b1eed68dae68fb23db34fa739acb2b4221674ed3dd2e94e5e6a9a1c4', 'Mina', 'Upgrade fixture', 'Takumi');
INSERT INTO public.conversation VALUES ('01a0e7b5-1456-7d8c-8843-ed2204cbac43', 'pocketrisu', NULL, '2d931d51-7c4d-4631-b016-b8b788e4ade1', '2026-09-28 11:09:59.254462+00', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'd3822c6c-3bde-4ec7-8712-8e0d6bef57bc', '5d96946a-ea9f-45be-b43a-bc0a4cc8835d', '01a0e7b5-146a-79fe-8ba1-f76a065faead', '2eb22a573b14a2e7e7e7a13b34efe0f0233c5721b13cc9f4e51aaea507235f4d', 'Mina', 'Upgrade fixture', 'Takumi');


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0e7b5-0ce7-776b-9916-bf432f5aed71', '01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4', '8634dec006b76c4c450630b646958c79', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:57.351567+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-07cc-766b-b207-4e45719027e3,01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-0d00-7629-b0fc-a310abc3b498', '01a0e7b5-07cb-7856-9f40-fec804720311', '8acd509c6422e5397475ab9d5ca2cf63', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:57.375955+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-07cb-7052-9399-a2c0930c9865,01a0e7b5-07cb-7856-9f40-fec804720311}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-0d16-7370-b534-df21d6c5370c', '01a0e7b5-079a-7622-af08-db1df68add2f', 'a0391e951a70cd068d13aee4a638ff97', 'extract-v10', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:57.398529+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-079a-7e5b-aabf-d12ccb5a421b,01a0e7b5-079a-7622-af08-db1df68add2f}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-0d2e-7511-bd1b-8e72aed76339', '01a0e7b5-0799-7928-96e5-9b8adf91c6f6', 'ffee019c77398db7dc546cc516975c3b', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:57.422843+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-0798-790b-8f45-440966429dd4,01a0e7b5-0799-7928-96e5-9b8adf91c6f6}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-0d45-7f9e-bf69-f5b1bebd3e56', '01a0e7b5-0762-792d-b99f-f6474ba220e7', 'e29966f8218007fd8f103b4a5df3e2e9', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:57.445103+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-0761-7bbb-b9a1-dfe4890135a3,01a0e7b5-0762-792d-b99f-f6474ba220e7}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-0d97-7692-aa35-cf58f55bb173', '01a0e7b5-0761-730f-8d9e-b0cff6a3dae4', '35e5994b595faa4ff91361cf4537880d', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:57.527799+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e7b5-075e-7e6d-b338-794c3f6f57be,01a0e7b5-0761-730f-8d9e-b0cff6a3dae4}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-11fd-7c98-a4e4-3b61d626e793', '01a0e7b5-0e4e-70bd-978b-51f59946e64a', '4bc987c9c0e8f18312e952745d5fa8a1', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:58.65329+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-0e00-7c0c-96b8-99034cd44ee6,01a0e7b5-0e4e-70bd-978b-51f59946e64a}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-1213-74f7-b1d9-18464d8e98b4', '01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d', 'd3f73bb81072859c95f0098e9eb9d4f6', 'extract-v10', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:58.675792+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-07f3-7fee-bc41-1c7da88dc283,01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-122b-7f5b-a68e-f995a3ac0f3f', '01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4', '411df4e4007758439ea2c0d64475fddd', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:58.699019+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-07cc-766b-b207-4e45719027e3,01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-1240-7401-9f71-5bea2431f6fc', '01a0e7b5-07cb-7856-9f40-fec804720311', 'd6b4b5ba4092256da725b3992224623b', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:58.720643+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-079a-7e5b-aabf-d12ccb5a421b,01a0e7b5-079a-7622-af08-db1df68add2f,01a0e7b5-07cb-7856-9f40-fec804720311}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-1263-7cfe-9a91-8ce9ba484db3', '01a0e7b5-0799-7928-96e5-9b8adf91c6f6', '07f2b000863e2438f4b220e2cf6bff82', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:58.755337+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-0798-790b-8f45-440966429dd4,01a0e7b5-0799-7928-96e5-9b8adf91c6f6}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-1277-7083-a81b-b1c789b24181', '01a0e7b5-0dff-702d-b2e6-c3a4e7493501', '319d395546abef681dd3d21a72b9a02c', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:58.775475+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-0761-7bbb-b9a1-dfe4890135a3,01a0e7b5-0dff-702d-b2e6-c3a4e7493501}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-16f9-7762-ac06-d5467db9dd57', '01a0e7b5-1467-712e-897a-3381d86c275a', 'e386ba679ddd98acdf669ac8426e8d79', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:59.928983+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-1466-7906-be46-17f434542d68,01a0e7b5-1467-712e-897a-3381d86c275a}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-170f-7ffc-9e13-8e86f1d0fdd0', '01a0e7b5-1465-74b5-8b22-1e6d83d913d9', '810665656207d8318de4ea40d679a410', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:59.951445+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40,01a0e7b5-1465-74b5-8b22-1e6d83d913d9}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-1724-7d54-a77d-d55245fbf576', '01a0e7b5-1464-7466-b1ac-2b210d9a190b', '3560839149dac8654c3f170c3d393c17', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:59.971974+00', 'extract-897ded81bcfd87619b8c05c9580112db', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e7b5-1463-748a-b48b-c948c2f60b58,01a0e7b5-1464-7466-b1ac-2b210d9a190b}', NULL, '{"entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0e7b5-0764-790f-868a-b460969947c2', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'manifest', '2e738abe5d3461e5b4f47bfc3af7dc7da125455acdfe02caea8e1be5cfecf8e0', '01a0e7b5-0756-79a1-9f83-ef04295be44f:2e738abe5d3461e5b4f47bfc3af7dc7da125455acdfe02caea8e1be5cfecf8e0:manifest', '2026-09-28 11:09:55.933718+00', '{"chat_id": "d3822c6c-3bde-4ec7-8712-8e0d6bef57bc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["cb4bd0ca-0319-4d3a-a081-098511e19acf", "3ab060d7eb9726c76778004088029511da46829e13886b41662c4e3f25ae4788", "user", null, null, null, 0, null, null], ["cc5b55ab-37c1-43f9-b528-4bbf7cc66398", "2a08e7b30c9113825faed0b03479316422500b3d60cf3c4e98987be88cccb3f8", "char", null, null, null, 0, "cc5b55ab-37c1-43f9-b528-4bbf7cc66398", null], ["0f03ac5d-1862-4270-a4ef-f09c6003d06b", "64f1f6e7a4a03a75b4dd278572e1acc9a4516f45d01fef517642dc0d17c7a913", "user", null, null, null, 0, null, null], ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "9e71ff8dd4c5917de2223763faee08f56e77d9e0693c688eed69c4968ecda162", "char", null, null, null, 0, "bbd036fc-b526-4e64-8d32-2d07ac48bb75", null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-079d-7768-84ae-84feed7f2725', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'manifest', '3504764c140c005b61678b714fe30838c1f464e82813b7f170a97f1e936d3dd7', '01a0e7b5-0756-79a1-9f83-ef04295be44f:3504764c140c005b61678b714fe30838c1f464e82813b7f170a97f1e936d3dd7:manifest', '2026-09-28 11:09:55.990994+00', '{"chat_id": "d3822c6c-3bde-4ec7-8712-8e0d6bef57bc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["2e55b534-e6c7-4191-bca5-4c0c2bfc5156", "49d0255d4c896ee2403d02dbebe5b7c74b938da47e5bb40d9336fd07d3ed1770", "user", null, null, null, 0, null, null], ["5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "87a050b6f5c969eac5c5e640b7d8e0839043426a9c0fb6b0092fbdaf00f9c132", "char", null, null, null, 0, "5d96946a-ea9f-45be-b43a-bc0a4cc8835d", null], ["05136bb0-6c4f-480c-b6e2-2cc4a37db816", "d0e9a9c583ae6ff1083cba2f0ec01cfd4e1e22ab864212c3d9d59d96673b624d", "user", null, null, null, 0, null, null], ["95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", "e9cbf942aaef6e0c6493166c8afe4a8723aa1d5d763d6578a77301a9ed3468e9", "char", null, null, null, 0, "95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", null]], "base_manifest_hash": "2e738abe5d3461e5b4f47bfc3af7dc7da125455acdfe02caea8e1be5cfecf8e0"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-07d0-751d-8239-b1c579aa7ac1', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'manifest', 'e4d0b2db85dc4c267e96881d29078430a4563d1cd2c74b93ff9a64613361beb9', '01a0e7b5-0756-79a1-9f83-ef04295be44f:e4d0b2db85dc4c267e96881d29078430a4563d1cd2c74b93ff9a64613361beb9:manifest', '2026-09-28 11:09:56.042293+00', '{"chat_id": "d3822c6c-3bde-4ec7-8712-8e0d6bef57bc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["9729a8e1-7b8b-42bd-be30-d54449b757b6", "5c743491e6032b4bed95427ec856cc938f5b881f1def6a435411db1bf9bd57c1", "user", null, null, null, 0, null, null], ["36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "298775bb005050c6c5fdc4643a9d5bacf8e16269321e3c398e61877f9f873c0d", "char", null, null, null, 0, "36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", null], ["ccc42a11-ed9f-466d-9d06-a69b7210f9b9", "b88a3f0b5c03a0f58190950211af0140e3d0d652654e8ae1aa0c4304ce4c5cb3", "user", null, null, null, 0, null, null], ["bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "555cdb38d59556dc9f4a11c1262a988fba0e6ec21c6eacbba71a920840fabd51", "char", null, null, null, 0, "bae9505c-fe9c-47bc-b979-8b5db5b4ca14", null]], "base_manifest_hash": "3504764c140c005b61678b714fe30838c1f464e82813b7f170a97f1e936d3dd7"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-07f6-7889-81bb-1f46b50d8c8a', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'manifest', '8ace00ed25bafa1182eb9e20d4cb41311d1c4c0e787d755e8228036b8acd4ee5', '01a0e7b5-0756-79a1-9f83-ef04295be44f:8ace00ed25bafa1182eb9e20d4cb41311d1c4c0e787d755e8228036b8acd4ee5:manifest', '2026-09-28 11:09:56.08295+00', '{"chat_id": "d3822c6c-3bde-4ec7-8712-8e0d6bef57bc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["4ba6efb2-1393-488c-81a4-c4388efd4ebc", "2cc1b2dcc5e54fe8b7a8345b49900deebcbf62097bf94a9b1f81f41ff14201b3", "user", null, null, null, 0, null, null]], "base_manifest_hash": "e4d0b2db85dc4c267e96881d29078430a4563d1cd2c74b93ff9a64613361beb9"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-0e02-7397-bac7-2d33b427e73a', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'manifest', '605690129413ad7d6d915a152a51393bacee9855fc8aeee691a0780a64d21576', '01a0e7b5-0756-79a1-9f83-ef04295be44f:605690129413ad7d6d915a152a51393bacee9855fc8aeee691a0780a64d21576:manifest', '2026-09-28 11:09:57.630478+00', '{"chat_id": "d3822c6c-3bde-4ec7-8712-8e0d6bef57bc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["cb4bd0ca-0319-4d3a-a081-098511e19acf", "3ab060d7eb9726c76778004088029511da46829e13886b41662c4e3f25ae4788", "user", null, null, null, 0, null, null], ["cc5b55ab-37c1-43f9-b528-4bbf7cc66398", "2a08e7b30c9113825faed0b03479316422500b3d60cf3c4e98987be88cccb3f8", "char", null, null, null, 0, "cc5b55ab-37c1-43f9-b528-4bbf7cc66398", null], ["0f03ac5d-1862-4270-a4ef-f09c6003d06b", "64f1f6e7a4a03a75b4dd278572e1acc9a4516f45d01fef517642dc0d17c7a913", "user", null, null, null, 0, null, null], ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "cd170743b8399eaef6ff9d748f66edc1d5f9e6101dacd43a906c8e466e83cdf2", "char", null, null, null, 0, "bbd036fc-b526-4e64-8d32-2d07ac48bb75", null], ["2e55b534-e6c7-4191-bca5-4c0c2bfc5156", "49d0255d4c896ee2403d02dbebe5b7c74b938da47e5bb40d9336fd07d3ed1770", "user", null, null, null, 0, null, null], ["5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "87a050b6f5c969eac5c5e640b7d8e0839043426a9c0fb6b0092fbdaf00f9c132", "char", null, null, null, 0, "5d96946a-ea9f-45be-b43a-bc0a4cc8835d", null], ["05136bb0-6c4f-480c-b6e2-2cc4a37db816", "d0e9a9c583ae6ff1083cba2f0ec01cfd4e1e22ab864212c3d9d59d96673b624d", "user", null, null, null, 0, null, null], ["95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", "e9cbf942aaef6e0c6493166c8afe4a8723aa1d5d763d6578a77301a9ed3468e9", "char", null, null, null, 0, "95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", null], ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "5c743491e6032b4bed95427ec856cc938f5b881f1def6a435411db1bf9bd57c1", "user", null, null, null, 0, null, null], ["36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "298775bb005050c6c5fdc4643a9d5bacf8e16269321e3c398e61877f9f873c0d", "char", null, null, null, 0, "36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", null], ["ccc42a11-ed9f-466d-9d06-a69b7210f9b9", "b88a3f0b5c03a0f58190950211af0140e3d0d652654e8ae1aa0c4304ce4c5cb3", "user", null, null, null, 0, null, null], ["bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "555cdb38d59556dc9f4a11c1262a988fba0e6ec21c6eacbba71a920840fabd51", "char", null, null, null, 0, "bae9505c-fe9c-47bc-b979-8b5db5b4ca14", null], ["4ba6efb2-1393-488c-81a4-c4388efd4ebc", "2cc1b2dcc5e54fe8b7a8345b49900deebcbf62097bf94a9b1f81f41ff14201b3", "user", null, null, null, 0, null, null], ["2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "f717308a6912ff6283a9b359bb2f2623502b8ae65e599ff108cb7670fe6ef769", "char", null, null, null, 0, "2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", null], ["106c9e6d-8abb-4516-bccd-26520636fbe0", "2dc587143e36ebe53c01e10cc109baf9581e309d4814fa5fff9ab084893741e2", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-0e2a-74de-969e-db50589362d4', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'manifest', 'e1297bd85acdd4b4adf5308aac9d472850f07027b2cf0d6cb8876b123d644fb4', '01a0e7b5-0756-79a1-9f83-ef04295be44f:e1297bd85acdd4b4adf5308aac9d472850f07027b2cf0d6cb8876b123d644fb4:manifest', '2026-09-28 11:09:57.671472+00', '{"chat_id": "d3822c6c-3bde-4ec7-8712-8e0d6bef57bc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["3f8f4725-1990-4370-b352-9fa652c723fc", "910725335822e4d7fa097938b0ebebb5f39db8b69a689ab815d195337778a2b9", "char", null, null, 1, 2, "3f8f4725-1990-4370-b352-9fa652c723fc", null]], "base_manifest_hash": "605690129413ad7d6d915a152a51393bacee9855fc8aeee691a0780a64d21576"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-0e51-76ad-a1c2-bb8e203d9722', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'manifest', '2e2291d9b1eed68dae68fb23db34fa739acb2b4221674ed3dd2e94e5e6a9a1c4', '01a0e7b5-0756-79a1-9f83-ef04295be44f:2e2291d9b1eed68dae68fb23db34fa739acb2b4221674ed3dd2e94e5e6a9a1c4:manifest', '2026-09-28 11:09:57.70939+00', '{"chat_id": "d3822c6c-3bde-4ec7-8712-8e0d6bef57bc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["cb4bd0ca-0319-4d3a-a081-098511e19acf", "3ab060d7eb9726c76778004088029511da46829e13886b41662c4e3f25ae4788", "user", null, null, null, 0, null, null], ["cc5b55ab-37c1-43f9-b528-4bbf7cc66398", "2a08e7b30c9113825faed0b03479316422500b3d60cf3c4e98987be88cccb3f8", "char", null, null, null, 0, "cc5b55ab-37c1-43f9-b528-4bbf7cc66398", null], ["0f03ac5d-1862-4270-a4ef-f09c6003d06b", "64f1f6e7a4a03a75b4dd278572e1acc9a4516f45d01fef517642dc0d17c7a913", "user", null, null, null, 0, null, null], ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "cd170743b8399eaef6ff9d748f66edc1d5f9e6101dacd43a906c8e466e83cdf2", "char", null, null, null, 0, "bbd036fc-b526-4e64-8d32-2d07ac48bb75", null], ["2e55b534-e6c7-4191-bca5-4c0c2bfc5156", "49d0255d4c896ee2403d02dbebe5b7c74b938da47e5bb40d9336fd07d3ed1770", "user", null, null, null, 0, null, null], ["5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "87a050b6f5c969eac5c5e640b7d8e0839043426a9c0fb6b0092fbdaf00f9c132", "char", null, null, null, 0, "5d96946a-ea9f-45be-b43a-bc0a4cc8835d", null], ["05136bb0-6c4f-480c-b6e2-2cc4a37db816", "d0e9a9c583ae6ff1083cba2f0ec01cfd4e1e22ab864212c3d9d59d96673b624d", "user", null, null, null, 0, null, null], ["95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", "e9cbf942aaef6e0c6493166c8afe4a8723aa1d5d763d6578a77301a9ed3468e9", "char", null, null, null, 0, "95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", null], ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "4d462e10ee5cc7807e92628b2ca3be8a4d6391ca9e1f51d34e5dba9dcc50725f", "user", true, null, null, 0, null, null], ["36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "298775bb005050c6c5fdc4643a9d5bacf8e16269321e3c398e61877f9f873c0d", "char", null, null, null, 0, "36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", null], ["ccc42a11-ed9f-466d-9d06-a69b7210f9b9", "b88a3f0b5c03a0f58190950211af0140e3d0d652654e8ae1aa0c4304ce4c5cb3", "user", null, null, null, 0, null, null], ["bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "555cdb38d59556dc9f4a11c1262a988fba0e6ec21c6eacbba71a920840fabd51", "char", null, null, null, 0, "bae9505c-fe9c-47bc-b979-8b5db5b4ca14", null], ["4ba6efb2-1393-488c-81a4-c4388efd4ebc", "2cc1b2dcc5e54fe8b7a8345b49900deebcbf62097bf94a9b1f81f41ff14201b3", "user", null, null, null, 0, null, null], ["2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "f717308a6912ff6283a9b359bb2f2623502b8ae65e599ff108cb7670fe6ef769", "char", null, null, null, 0, "2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", null], ["106c9e6d-8abb-4516-bccd-26520636fbe0", "2dc587143e36ebe53c01e10cc109baf9581e309d4814fa5fff9ab084893741e2", "user", null, null, null, 0, null, null], ["3f8f4725-1990-4370-b352-9fa652c723fc", "b50b632ac29d5df133028260b35e569df787b0efaea43605bc78f1a8a28fb069", "char", null, null, 0, 2, "3f8f4725-1990-4370-b352-9fa652c723fc", null], ["f6cc4960-acb0-48b7-82bb-dc59d2862b07", "e601e59c8d7423ceb53ceede26eca87fc01d28c6e7987d921bcbacac104a2653", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-1469-7508-90c1-897acfd73018', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', 'manifest', '2eb22a573b14a2e7e7e7a13b34efe0f0233c5721b13cc9f4e51aaea507235f4d', '01a0e7b5-1456-7d8c-8843-ed2204cbac43:2eb22a573b14a2e7e7e7a13b34efe0f0233c5721b13cc9f4e51aaea507235f4d:manifest', '2026-09-28 11:09:59.267105+00', '{"chat_id": "2d931d51-7c4d-4631-b016-b8b788e4ade1", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["1af50461-8f6d-4c7f-ac61-62070e6e029d", "8d9f9459a639dab622f60affa648beeda454289bc637091b67e5001835cf68b2", "user", null, null, null, 0, null, null], ["7ed02b26-0280-4a97-bbc9-6092c425d2dc", "6b03c237fd46582677a3734937dfa37336962c54483cdaa04d0dc0bc41edc663", "char", null, null, null, 0, "cc5b55ab-37c1-43f9-b528-4bbf7cc66398", null], ["0b20e385-0483-47e0-b7de-d15c1a54f8bb", "657a2638588d97b3f420e1e09c29cf3ed02485198e3b0b62d41bbbfc57544ce2", "user", null, null, null, 0, null, null], ["a9cc4e94-3d8f-4aa1-8c6c-d70b9bee14d8", "94b450c5d55488956120379e7b06f61df91b6a6e2c2f6f9d0c7719216f8735ef", "char", null, null, null, 0, "bbd036fc-b526-4e64-8d32-2d07ac48bb75", null], ["09ebcac2-9a60-4786-ae35-b80856075afd", "8f1bfc22eb07c87d6667d6b70746dd7389b93b617ed988363f8a7abcb373be99", "user", null, null, null, 0, null, null], ["032ae72c-f9a3-47e5-bb6e-04a6a9afd9e3", "2d9adb6f49ef78ad0f67ac94f8dab8d8c27758738e7807599e3172bbe029f68c", "char", null, null, null, 0, "5d96946a-ea9f-45be-b43a-bc0a4cc8835d", null], ["3569bf4c-197e-41c6-ba77-862c755395df", "3ce1d4461b809c4d72cc8956f3e00e46ff61ffb700b56a9b25b0e19768416a72", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::d3822c6c-3bde-4ec7-8712-8e0d6bef57bc::Harbor route::5d96946a-ea9f-45be-b43a-bc0a4cc8835d::}}"]], ["d1946c9d-4a55-4a5d-a26a-c4b892571bb8", "4d6188ab40104f958bcdbe36a8f5f556e2868e05d8bfd65c9df51d0ae20751ef", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0e7b5-07f3-7fee-bc41-1c7da88dc283:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-07f3-7fee-bc41-1c7da88dc283"}', 50, 'done', 1, '2026-09-28 11:09:56.08295+00', NULL, NULL, '2026-09-28 11:09:56.08295+00', '2026-09-28 11:09:57.144389+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4"}', 50, 'done', 1, '2026-09-28 11:09:56.08295+00', NULL, NULL, '2026-09-28 11:09:56.08295+00', '2026-09-28 11:09:57.164735+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0e7b5-07cc-766b-b207-4e45719027e3:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-07cc-766b-b207-4e45719027e3"}', 50, 'done', 1, '2026-09-28 11:09:56.042293+00', NULL, NULL, '2026-09-28 11:09:56.042293+00', '2026-09-28 11:09:57.185322+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0e7b5-07cb-7856-9f40-fec804720311:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-07cb-7856-9f40-fec804720311"}', 50, 'done', 1, '2026-09-28 11:09:56.042293+00', NULL, NULL, '2026-09-28 11:09:56.042293+00', '2026-09-28 11:09:57.207719+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0e7b5-07cb-7052-9399-a2c0930c9865:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-07cb-7052-9399-a2c0930c9865"}', 50, 'done', 1, '2026-09-28 11:09:56.042293+00', NULL, NULL, '2026-09-28 11:09:56.042293+00', '2026-09-28 11:09:57.226909+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0e7b5-079a-7622-af08-db1df68add2f:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-079a-7622-af08-db1df68add2f"}', 50, 'done', 1, '2026-09-28 11:09:56.042293+00', NULL, NULL, '2026-09-28 11:09:56.042293+00', '2026-09-28 11:09:57.246429+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0e7b5-079a-7e5b-aabf-d12ccb5a421b:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-079a-7e5b-aabf-d12ccb5a421b"}', 50, 'done', 1, '2026-09-28 11:09:55.990994+00', NULL, NULL, '2026-09-28 11:09:55.990994+00', '2026-09-28 11:09:57.264621+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0e7b5-0799-7928-96e5-9b8adf91c6f6:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0799-7928-96e5-9b8adf91c6f6"}', 50, 'done', 1, '2026-09-28 11:09:55.990994+00', NULL, NULL, '2026-09-28 11:09:55.990994+00', '2026-09-28 11:09:57.284681+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0e7b5-0798-790b-8f45-440966429dd4:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0798-790b-8f45-440966429dd4"}', 50, 'done', 1, '2026-09-28 11:09:55.990994+00', NULL, NULL, '2026-09-28 11:09:55.990994+00', '2026-09-28 11:09:57.304556+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0e7b5-0762-792d-b99f-f6474ba220e7:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0762-792d-b99f-f6474ba220e7"}', 50, 'done', 1, '2026-09-28 11:09:55.990994+00', NULL, NULL, '2026-09-28 11:09:55.990994+00', '2026-09-28 11:09:57.328333+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4:8634dec006b76c4c450630b646958c79:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4", "window_hash": "8634dec006b76c4c450630b646958c79"}', 100, 'done', 1, '2026-09-28 11:09:56.08295+00', NULL, NULL, '2026-09-28 11:09:56.08295+00', '2026-09-28 11:09:57.354576+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0e7b5-07cb-7856-9f40-fec804720311:8acd509c6422e5397475ab9d5ca2cf63:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-07cb-7856-9f40-fec804720311", "window_hash": "8acd509c6422e5397475ab9d5ca2cf63"}', 100, 'done', 1, '2026-09-28 11:09:56.042293+00', NULL, NULL, '2026-09-28 11:09:56.042293+00', '2026-09-28 11:09:57.378348+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0e7b5-079a-7622-af08-db1df68add2f:a0391e951a70cd068d13aee4a638ff97:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-079a-7622-af08-db1df68add2f", "window_hash": "a0391e951a70cd068d13aee4a638ff97"}', 100, 'done', 1, '2026-09-28 11:09:56.042293+00', NULL, NULL, '2026-09-28 11:09:56.042293+00', '2026-09-28 11:09:57.400047+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0e7b5-0799-7928-96e5-9b8adf91c6f6:ffee019c77398db7dc546cc516975c3b:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-0799-7928-96e5-9b8adf91c6f6", "window_hash": "ffee019c77398db7dc546cc516975c3b"}', 100, 'done', 1, '2026-09-28 11:09:55.990994+00', NULL, NULL, '2026-09-28 11:09:55.990994+00', '2026-09-28 11:09:57.424691+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0e7b5-0762-792d-b99f-f6474ba220e7:e29966f8218007fd8f103b4a5df3e2e9:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-0762-792d-b99f-f6474ba220e7", "window_hash": "e29966f8218007fd8f103b4a5df3e2e9"}', 100, 'done', 1, '2026-09-28 11:09:55.990994+00', NULL, NULL, '2026-09-28 11:09:55.990994+00', '2026-09-28 11:09:57.447235+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0e7b5-0761-7bbb-b9a1-dfe4890135a3:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0761-7bbb-b9a1-dfe4890135a3"}', 150, 'done', 1, '2026-09-28 11:09:55.933718+00', NULL, NULL, '2026-09-28 11:09:55.933718+00', '2026-09-28 11:09:57.467749+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0e7b5-0761-730f-8d9e-b0cff6a3dae4:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0761-730f-8d9e-b0cff6a3dae4"}', 150, 'done', 1, '2026-09-28 11:09:55.933718+00', NULL, NULL, '2026-09-28 11:09:55.933718+00', '2026-09-28 11:09:57.487251+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0e7b5-075e-7e6d-b338-794c3f6f57be:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-075e-7e6d-b338-794c3f6f57be"}', 150, 'done', 1, '2026-09-28 11:09:55.933718+00', NULL, NULL, '2026-09-28 11:09:55.933718+00', '2026-09-28 11:09:57.506942+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0e7b5-0761-730f-8d9e-b0cff6a3dae4:35e5994b595faa4ff91361cf4537880d:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-0761-730f-8d9e-b0cff6a3dae4", "window_hash": "35e5994b595faa4ff91361cf4537880d"}', 200, 'done', 1, '2026-09-28 11:09:55.933718+00', NULL, NULL, '2026-09-28 11:09:55.933718+00', '2026-09-28 11:09:57.533446+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0e7b5-0799-7928-96e5-9b8adf91c6f6:07f2b000863e2438f4b220e2cf6bff82:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-0799-7928-96e5-9b8adf91c6f6", "window_hash": "07f2b000863e2438f4b220e2cf6bff82"}', 100, 'done', 1, '2026-09-28 11:09:57.630478+00', NULL, NULL, '2026-09-28 11:09:57.630478+00', '2026-09-28 11:09:58.75723+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0e7b5-0dff-702d-b2e6-c3a4e7493501:319d395546abef681dd3d21a72b9a02c:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-0dff-702d-b2e6-c3a4e7493501", "window_hash": "319d395546abef681dd3d21a72b9a02c"}', 100, 'done', 1, '2026-09-28 11:09:57.630478+00', NULL, NULL, '2026-09-28 11:09:57.630478+00', '2026-09-28 11:09:58.77726+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0e7b5-1466-7906-be46-17f434542d68:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-1466-7906-be46-17f434542d68"}', 150, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.833816+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0e7b5-0e4f-7235-ad87-24100c6ca2e5:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0e4f-7235-ad87-24100c6ca2e5"}', 50, 'done', 1, '2026-09-28 11:09:57.70939+00', NULL, NULL, '2026-09-28 11:09:57.70939+00', '2026-09-28 11:09:58.553996+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0e7b5-0e4e-70bd-978b-51f59946e64a:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0e4e-70bd-978b-51f59946e64a"}', 50, 'done', 1, '2026-09-28 11:09:57.70939+00', NULL, NULL, '2026-09-28 11:09:57.70939+00', '2026-09-28 11:09:58.572068+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0e7b5-0e00-7c0c-96b8-99034cd44ee6:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0e00-7c0c-96b8-99034cd44ee6"}', 50, 'done', 1, '2026-09-28 11:09:57.630478+00', NULL, NULL, '2026-09-28 11:09:57.630478+00', '2026-09-28 11:09:58.590116+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d"}', 50, 'done', 1, '2026-09-28 11:09:57.630478+00', NULL, NULL, '2026-09-28 11:09:57.630478+00', '2026-09-28 11:09:58.608778+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0e7b5-0dff-702d-b2e6-c3a4e7493501:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-0dff-702d-b2e6-c3a4e7493501"}', 50, 'done', 1, '2026-09-28 11:09:57.630478+00', NULL, NULL, '2026-09-28 11:09:57.630478+00', '2026-09-28 11:09:58.627456+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0e7b5-0e4e-70bd-978b-51f59946e64a:4bc987c9c0e8f18312e952745d5fa8a1:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-0e4e-70bd-978b-51f59946e64a", "window_hash": "4bc987c9c0e8f18312e952745d5fa8a1"}', 100, 'done', 1, '2026-09-28 11:09:57.70939+00', NULL, NULL, '2026-09-28 11:09:57.70939+00', '2026-09-28 11:09:58.655062+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d:d3f73bb81072859c95f0098e9eb9d4f6:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d", "window_hash": "d3f73bb81072859c95f0098e9eb9d4f6"}', 100, 'done', 1, '2026-09-28 11:09:57.70939+00', NULL, NULL, '2026-09-28 11:09:57.70939+00', '2026-09-28 11:09:58.677278+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4:411df4e4007758439ea2c0d64475fddd:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4", "window_hash": "411df4e4007758439ea2c0d64475fddd"}', 100, 'done', 1, '2026-09-28 11:09:57.70939+00', NULL, NULL, '2026-09-28 11:09:57.70939+00', '2026-09-28 11:09:58.700843+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0e7b5-07cb-7856-9f40-fec804720311:d6b4b5ba4092256da725b3992224623b:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-07cb-7856-9f40-fec804720311", "window_hash": "d6b4b5ba4092256da725b3992224623b"}', 100, 'done', 1, '2026-09-28 11:09:57.70939+00', NULL, NULL, '2026-09-28 11:09:57.70939+00', '2026-09-28 11:09:58.722396+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d:8840dd14a30087b054931b5cb599a58a:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d", "window_hash": "8840dd14a30087b054931b5cb599a58a"}', 100, 'obsolete', 1, '2026-09-28 11:09:57.630478+00', NULL, NULL, '2026-09-28 11:09:57.630478+00', '2026-09-28 11:09:58.725857+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0e7b5-07cb-7856-9f40-fec804720311:e75e4371075fc190e21a3a9945ac5a13:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-07cb-7856-9f40-fec804720311", "window_hash": "e75e4371075fc190e21a3a9945ac5a13"}', 100, 'obsolete', 1, '2026-09-28 11:09:57.630478+00', NULL, NULL, '2026-09-28 11:09:57.630478+00', '2026-09-28 11:09:58.729137+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0e7b5-079a-7622-af08-db1df68add2f:7bf9ee9491481e145ced9e9ec55f1665:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-079a-7622-af08-db1df68add2f", "window_hash": "7bf9ee9491481e145ced9e9ec55f1665"}', 100, 'obsolete', 1, '2026-09-28 11:09:57.630478+00', NULL, NULL, '2026-09-28 11:09:57.630478+00', '2026-09-28 11:09:58.732645+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0e7b5-1467-712e-897a-3381d86c275a:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-1467-712e-897a-3381d86c275a"}', 150, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.816454+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0e7b5-1465-74b5-8b22-1e6d83d913d9:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-1465-74b5-8b22-1e6d83d913d9"}', 150, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.855491+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40"}', 150, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.873219+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0e7b5-1464-7466-b1ac-2b210d9a190b:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-1464-7466-b1ac-2b210d9a190b"}', 150, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.892133+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0e7b5-1463-748a-b48b-c948c2f60b58:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-1463-748a-b48b-c948c2f60b58"}', 150, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.91035+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0e7b5-1467-712e-897a-3381d86c275a:e386ba679ddd98acdf669ac8426e8d79:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-1467-712e-897a-3381d86c275a", "window_hash": "e386ba679ddd98acdf669ac8426e8d79"}', 200, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.93076+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0e7b5-1465-74b5-8b22-1e6d83d913d9:810665656207d8318de4ea40d679a410:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-1465-74b5-8b22-1e6d83d913d9", "window_hash": "810665656207d8318de4ea40d679a410"}', 200, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.953326+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0e7b5-1464-7466-b1ac-2b210d9a190b:3560839149dac8654c3f170c3d393c17:extract-897ded81bcfd87619b8c05c9580112db', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "extract-897ded81bcfd87619b8c05c9580112db", "revision_id": "01a0e7b5-1464-7466-b1ac-2b210d9a190b", "window_hash": "3560839149dac8654c3f170c3d393c17"}', 200, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.973811+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0e7b5-1468-7ae6-89fa-32142af0da5f:embed-462854906a786ed88ac309260e1d19a5', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{"generation": "embed-462854906a786ed88ac309260e1d19a5", "revision_id": "01a0e7b5-1468-7ae6-89fa-32142af0da5f"}', 150, 'done', 1, '2026-09-28 11:09:59.267105+00', NULL, NULL, '2026-09-28 11:09:59.267105+00', '2026-09-28 11:09:59.798753+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0e7b5-0764-790f-868a-b460969947c2', '01a0e7b5-0756-79a1-9f83-ef04295be44f');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-897ded81bcfd87619b8c05c9580112db', 'extract', 'stub', 'http://127.0.0.1:34747/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "905fe0abfc193a9d", "compiler": "extract-v10", "endpoint": "http://127.0.0.1:34747/v1", "json_mode": true, "normalizer": "clean-v2", "predicates": "4e6ac6c47a6da74e", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-28 11:09:55.772293+00', '2026-09-28 11:09:55.773448+00');
INSERT INTO public.projection_generation VALUES ('embed-462854906a786ed88ac309260e1d19a5', 'embed', 'stub-embed', 'http://127.0.0.1:34747/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:34747/v1", "max_chunks": 8, "normalizer": "clean-v2", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-28 11:09:55.772293+00', '2026-09-28 11:09:55.777166+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-078c-7e58-98e5-5d4a7b617ac3', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '01a0e7b5-0765-7a75-953f-ffa2b44d5497', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b5-0761-7bbb-b9a1-dfe4890135a3", "host_logical_id": "0f03ac5d-1862-4270-a4ef-f09c6003d06b"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b5-0761-7bbb-b9a1-dfe4890135a3", "host_logical_id": "0f03ac5d-1862-4270-a4ef-f09c6003d06b"}]', 0, '{"embed": 24.03, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 0}, "vector": 2.0, "lexical": 3.43, "threads": 0, "extractor": "extract-897ded81bcfd", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 32.47, "embedding_projection": "embed-462854906a786e"}', 'fresh', '2026-09-28 11:09:55.948035+00', 'packet-v1', 600, 3, '', '["0f03ac5d-1862-4270-a4ef-f09c6003d06b", "bbd036fc-b526-4e64-8d32-2d07ac48bb75", "cb4bd0ca-0319-4d3a-a081-098511e19acf", "cc5b55ab-37c1-43f9-b528-4bbf7cc66398"]', 'extract-897ded81bcfd87619b8c05c9580112db', 'embed-462854906a786ed88ac309260e1d19a5', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-07c0-751f-9647-a82574cd0900', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '01a0e7b5-0765-7a75-953f-ffa2b44d5497', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b5-079a-7e5b-aabf-d12ccb5a421b", "host_logical_id": "05136bb0-6c4f-480c-b6e2-2cc4a37db816"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b5-079a-7e5b-aabf-d12ccb5a421b", "host_logical_id": "05136bb0-6c4f-480c-b6e2-2cc4a37db816"}]', 0, '{"embed": 22.38, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 0}, "vector": 1.43, "lexical": 3.07, "threads": 0, "extractor": "extract-897ded81bcfd", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 28.8, "embedding_projection": "embed-462854906a786e"}', 'fresh', '2026-09-28 11:09:56.004233+00', 'packet-v1', 600, 7, '', '["05136bb0-6c4f-480c-b6e2-2cc4a37db816", "2e55b534-e6c7-4191-bca5-4c0c2bfc5156", "5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b"]', 'extract-897ded81bcfd87619b8c05c9580112db', 'embed-462854906a786ed88ac309260e1d19a5', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-07e9-7521-b5ea-984fb56ec97b', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '01a0e7b5-0765-7a75-953f-ffa2b44d5497', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b5-07cc-766b-b207-4e45719027e3", "host_logical_id": "ccc42a11-ed9f-466d-9d06-a69b7210f9b9"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b5-07cc-766b-b207-4e45719027e3", "host_logical_id": "ccc42a11-ed9f-466d-9d06-a69b7210f9b9"}]', 0, '{"embed": 13.96, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 0}, "vector": 0.93, "lexical": 2.56, "threads": 0, "extractor": "extract-897ded81bcfd", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.13, "embedding_projection": "embed-462854906a786e"}', 'fresh', '2026-09-28 11:09:56.054286+00', 'packet-v1', 600, 11, '', '["36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "9729a8e1-7b8b-42bd-be30-d54449b757b6", "bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "ccc42a11-ed9f-466d-9d06-a69b7210f9b9"]', 'extract-897ded81bcfd87619b8c05c9580112db', 'embed-462854906a786ed88ac309260e1d19a5', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-080e-7dff-9119-5aec2732e67a', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '01a0e7b5-0765-7a75-953f-ffa2b44d5497', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b5-07f3-7fee-bc41-1c7da88dc283", "host_logical_id": "4ba6efb2-1393-488c-81a4-c4388efd4ebc"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0e7b5-0762-792d-b99f-f6474ba220e7", "host_logical_id": "bbd036fc-b526-4e64-8d32-2d07ac48bb75"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0e7b5-0761-730f-8d9e-b0cff6a3dae4", "host_logical_id": "cc5b55ab-37c1-43f9-b528-4bbf7cc66398"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0e7b5-0761-730f-8d9e-b0cff6a3dae4"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b5-0762-792d-b99f-f6474ba220e7"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b5-07f3-7fee-bc41-1c7da88dc283", "host_logical_id": "4ba6efb2-1393-488c-81a4-c4388efd4ebc"}]', 174, '{"embed": 13.89, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 2}, "vector": 0.93, "lexical": 2.52, "threads": 0, "extractor": "extract-897ded81bcfd", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.21, "embedding_projection": "embed-462854906a786e"}', 'fresh', '2026-09-28 11:09:56.090877+00', 'packet-v1', 600, 12, '', '["36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "4ba6efb2-1393-488c-81a4-c4388efd4ebc", "bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "ccc42a11-ed9f-466d-9d06-a69b7210f9b9"]', 'extract-897ded81bcfd87619b8c05c9580112db', 'embed-462854906a786ed88ac309260e1d19a5', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-0762-792d-b99f-f6474ba220e7"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 3, "placed": true}, {"ref": {"revision": "01a0e7b5-0761-730f-8d9e-b0cff6a3dae4"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-0e1d-79e4-a33b-67775df68400', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '01a0e7b5-0e03-7467-8705-b3a5050063f3', 'And the compass?', '[{"rrf": 0.03128, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0e7b5-07cb-7856-9f40-fec804720311", "host_logical_id": "36bab45a-ac21-42fc-8ddd-a0d6baad1ce3"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-0e00-7c0c-96b8-99034cd44ee6", "host_logical_id": "106c9e6d-8abb-4516-bccd-26520636fbe0"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0e7b5-0761-730f-8d9e-b0cff6a3dae4", "host_logical_id": "cc5b55ab-37c1-43f9-b528-4bbf7cc66398"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0e7b5-075e-7e6d-b338-794c3f6f57be", "host_logical_id": "cb4bd0ca-0319-4d3a-a081-098511e19acf"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0e7b5-079a-7622-af08-db1df68add2f", "host_logical_id": "95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0e7b5-0799-7928-96e5-9b8adf91c6f6", "host_logical_id": "5d96946a-ea9f-45be-b43a-bc0a4cc8835d"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0e7b5-075e-7e6d-b338-794c3f6f57be"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0e7b5-0761-730f-8d9e-b0cff6a3dae4"}, {"turn": 5, "score": 0.01562, "revision_id": "01a0e7b5-0799-7928-96e5-9b8adf91c6f6"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0e7b5-079a-7622-af08-db1df68add2f"}, {"turn": 9, "score": 0.03128, "revision_id": "01a0e7b5-07cb-7856-9f40-fec804720311"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-0e00-7c0c-96b8-99034cd44ee6", "host_logical_id": "106c9e6d-8abb-4516-bccd-26520636fbe0"}]', 252, '{"embed": 14.52, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 5}, "vector": 1.21, "lexical": 2.58, "threads": 0, "extractor": "extract-897ded81bcfd", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.56, "embedding_projection": "embed-462854906a786e"}', 'fresh', '2026-09-28 11:09:57.641371+00', 'packet-v1', 600, 14, '', '["106c9e6d-8abb-4516-bccd-26520636fbe0", "2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "4ba6efb2-1393-488c-81a4-c4388efd4ebc", "bae9505c-fe9c-47bc-b979-8b5db5b4ca14"]', 'extract-897ded81bcfd87619b8c05c9580112db', 'embed-462854906a786ed88ac309260e1d19a5', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-07cb-7856-9f40-fec804720311"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e7b5-0761-730f-8d9e-b0cff6a3dae4"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}, {"ref": {"revision": "01a0e7b5-075e-7e6d-b338-794c3f6f57be"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a0e7b5-079a-7622-af08-db1df68add2f"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 7, "placed": true}, {"ref": {"revision": "01a0e7b5-0799-7928-96e5-9b8adf91c6f6"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 5, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-0e43-7ad3-a0f2-01c3ad2522b8', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '01a0e7b5-0e03-7467-8705-b3a5050063f3', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0e7b5-07cb-7856-9f40-fec804720311", "host_logical_id": "36bab45a-ac21-42fc-8ddd-a0d6baad1ce3"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-0e00-7c0c-96b8-99034cd44ee6", "host_logical_id": "106c9e6d-8abb-4516-bccd-26520636fbe0"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4", "host_logical_id": "bae9505c-fe9c-47bc-b979-8b5db5b4ca14"}]', '[{"turn": 9, "score": 0.03002, "revision_id": "01a0e7b5-07cb-7856-9f40-fec804720311"}, {"turn": 11, "score": 0.01639, "revision_id": "01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-0e00-7c0c-96b8-99034cd44ee6", "host_logical_id": "106c9e6d-8abb-4516-bccd-26520636fbe0"}]', 171, '{"embed": 14.11, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 2}, "vector": 1.2, "lexical": 2.95, "threads": 0, "extractor": "extract-897ded81bcfd", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.67, "embedding_projection": "embed-462854906a786e"}', 'fresh', '2026-09-28 11:09:57.679203+00', 'packet-v1', 600, 15, '', '["106c9e6d-8abb-4516-bccd-26520636fbe0", "2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "3f8f4725-1990-4370-b352-9fa652c723fc", "4ba6efb2-1393-488c-81a4-c4388efd4ebc"]', 'extract-897ded81bcfd87619b8c05c9580112db', 'embed-462854906a786ed88ac309260e1d19a5', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-07cb-7856-9f40-fec804720311"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4"}, "tok": 24, "why": "placed", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 11, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-0e6a-7449-ad81-eebf5c6b3038', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0e7b5-079a-7e5b-aabf-d12ccb5a421b", "host_logical_id": "05136bb0-6c4f-480c-b6e2-2cc4a37db816"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b5-0e4f-7235-ad87-24100c6ca2e5", "host_logical_id": "f6cc4960-acb0-48b7-82bb-dc59d2862b07"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0e7b5-079a-7e5b-aabf-d12ccb5a421b"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b5-0e4f-7235-ad87-24100c6ca2e5", "host_logical_id": "f6cc4960-acb0-48b7-82bb-dc59d2862b07"}]', 138, '{"embed": 14.73, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 1}, "vector": 0.89, "lexical": 2.11, "threads": 0, "extractor": "extract-897ded81bcfd", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.4, "embedding_projection": "embed-462854906a786e"}', 'fresh', '2026-09-28 11:09:57.719349+00', 'packet-v1', 600, 16, '', '["106c9e6d-8abb-4516-bccd-26520636fbe0", "2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "3f8f4725-1990-4370-b352-9fa652c723fc", "f6cc4960-acb0-48b7-82bb-dc59d2862b07"]', 'extract-897ded81bcfd87619b8c05c9580112db', 'embed-462854906a786ed88ac309260e1d19a5', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-079a-7e5b-aabf-d12ccb5a421b"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 6, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-1482-7df0-ad55-b35abfec1f0b', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '01a0e7b5-146a-79fe-8ba1-f76a065faead', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40", "host_logical_id": "0b20e385-0483-47e0-b7de-d15c1a54f8bb"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0e7b5-1465-74b5-8b22-1e6d83d913d9", "host_logical_id": "a9cc4e94-3d8f-4aa1-8c6c-d70b9bee14d8"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b5-1465-74b5-8b22-1e6d83d913d9"}]', '[]', 164, '{"embed": 13.33, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 2}, "vector": 0.68, "lexical": 2.65, "threads": 0, "extractor": "extract-897ded81bcfd", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 18.42, "embedding_projection": "embed-462854906a786e"}', 'fresh', '2026-09-28 11:09:59.279699+00', 'packet-v1', 600, 7, '', '["032ae72c-f9a3-47e5-bb6e-04a6a9afd9e3", "09ebcac2-9a60-4786-ae35-b80856075afd", "3569bf4c-197e-41c6-ba77-862c755395df", "d1946c9d-4a55-4a5d-a26a-c4b892571bb8"]', 'extract-897ded81bcfd87619b8c05c9580112db', 'embed-462854906a786ed88ac309260e1d19a5', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 2, "placed": true}, {"ref": {"revision": "01a0e7b5-1465-74b5-8b22-1e6d83d913d9"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 3, "placed": true}]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0e7b5-07f3-7fee-bc41-1c7da88dc283', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.141713+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.163337+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-07cc-766b-b207-4e45719027e3', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.183913+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-07cb-7856-9f40-fec804720311', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.206321+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-07cb-7052-9399-a2c0930c9865', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.225491+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-079a-7622-af08-db1df68add2f', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.245+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-079a-7e5b-aabf-d12ccb5a421b', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.26325+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0799-7928-96e5-9b8adf91c6f6', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.28324+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0798-790b-8f45-440966429dd4', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.303107+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0762-792d-b99f-f6474ba220e7', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.32688+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0761-7bbb-b9a1-dfe4890135a3', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.466315+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0761-730f-8d9e-b0cff6a3dae4', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.485812+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-075e-7e6d-b338-794c3f6f57be', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:57.505508+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0e4f-7235-ad87-24100c6ca2e5', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:58.552558+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0e4e-70bd-978b-51f59946e64a', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:58.570704+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0e00-7c0c-96b8-99034cd44ee6', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:58.588744+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:58.607306+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-0dff-702d-b2e6-c3a4e7493501', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:58.626093+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-1468-7ae6-89fa-32142af0da5f', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:59.796933+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-1467-712e-897a-3381d86c275a', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:59.815066+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-1466-7906-be46-17f434542d68', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:59.832477+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-1465-74b5-8b22-1e6d83d913d9', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:59.854006+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:59.871869+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-1464-7466-b1ac-2b210d9a190b', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:59.890811+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-1463-748a-b48b-c948c2f60b58', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-462854906a786ed88ac309260e1d19a5', '2026-09-28 11:09:59.909024+00');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0e7b5-075e-7e6d-b338-794c3f6f57be', 'clean-v2', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:09:55.933718+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0761-730f-8d9e-b0cff6a3dae4', 'clean-v2', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:09:55.933718+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0761-7bbb-b9a1-dfe4890135a3', 'clean-v2', 'Is Rin with you?', 16, 16, '2026-09-28 11:09:55.933718+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0762-792d-b99f-f6474ba220e7', 'clean-v2', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-28 11:09:55.933718+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0798-790b-8f45-440966429dd4', 'clean-v2', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:09:55.990994+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0799-7928-96e5-9b8adf91c6f6', 'clean-v2', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:09:55.990994+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-079a-7e5b-aabf-d12ccb5a421b', 'clean-v2', 'Let''s check the market.', 23, 23, '2026-09-28 11:09:55.990994+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-079a-7622-af08-db1df68add2f', 'clean-v2', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-28 11:09:55.990994+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-07cb-7052-9399-a2c0930c9865', 'clean-v2', 'Any news from the harbor?', 25, 25, '2026-09-28 11:09:56.042293+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-07cb-7856-9f40-fec804720311', 'clean-v2', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-28 11:09:56.042293+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-07cc-766b-b207-4e45719027e3', 'clean-v2', 'Where do we meet tonight?', 25, 25, '2026-09-28 11:09:56.042293+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4', 'clean-v2', 'Mina moved to the bell tower.', 29, 29, '2026-09-28 11:09:56.042293+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-07f3-7fee-bc41-1c7da88dc283', 'clean-v2', 'Where is Mina now?', 18, 18, '2026-09-28 11:09:56.08295+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0dff-702d-b2e6-c3a4e7493501', 'clean-v2', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:09:57.630478+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d', 'clean-v2', 'Mina keeps the brass key close.', 31, 31, '2026-09-28 11:09:57.630478+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0e00-7c0c-96b8-99034cd44ee6', 'clean-v2', 'And the compass?', 16, 16, '2026-09-28 11:09:57.630478+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0e28-72d2-932d-a1b8064536af', 'clean-v2', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-28 11:09:57.671472+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0e4e-7b15-9708-86e2c70427a7', 'clean-v2', 'Any news from the harbor?', 25, 25, '2026-09-28 11:09:57.70939+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0e4e-70bd-978b-51f59946e64a', 'clean-v2', 'Rin has the silver compass.', 27, 27, '2026-09-28 11:09:57.70939+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-0e4f-7235-ad87-24100c6ca2e5', 'clean-v2', 'Let''s go.', 9, 9, '2026-09-28 11:09:57.70939+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-1463-748a-b48b-c948c2f60b58', 'clean-v2', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:09:59.267105+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-1464-7466-b1ac-2b210d9a190b', 'clean-v2', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:09:59.267105+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40', 'clean-v2', 'Is Rin with you?', 16, 16, '2026-09-28 11:09:59.267105+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-1465-74b5-8b22-1e6d83d913d9', 'clean-v2', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:09:59.267105+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-1466-7906-be46-17f434542d68', 'clean-v2', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:09:59.267105+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-1467-712e-897a-3381d86c275a', 'clean-v2', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:09:59.267105+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-1467-7fef-9f54-4af3f344de1b', 'clean-v2', '{{specialcomment::branchedfrom::d3822c6c-3bde-4ec7-8712-8e0d6bef57bc::Harbor route::5d96946a-ea9f-45be-b43a-bc0a4cc8835d::}}', 124, 124, '2026-09-28 11:09:59.267105+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-1468-7ae6-89fa-32142af0da5f', 'clean-v2', 'Rin moved to the market.', 24, 24, '2026-09-28 11:09:59.267105+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-28 11:09:54.979578+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-28 11:09:55.063855+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-28 11:09:55.080707+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-28 11:09:55.123433+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-28 11:09:55.143726+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-28 11:09:55.152445+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-28 11:09:55.154319+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-28 11:09:55.164621+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-28 11:09:55.181657+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-28 11:09:55.183608+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-28 11:09:55.185159+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-28 11:09:55.203081+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-28 11:09:55.230261+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-28 11:09:55.246887+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-28 11:09:55.249172+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-28 11:09:55.269616+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-28 11:09:55.271297+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-28 11:09:55.275823+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-09-28 11:09:55.277384+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-09-28 11:09:55.289905+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0e7b5-075e-7be5-8fce-2df6b2062503', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'cb4bd0ca-0319-4d3a-a081-098511e19acf', 'message', '2026-09-28 11:09:55.933718+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0760-7f84-a16a-89ddfbcb09d0', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'cc5b55ab-37c1-43f9-b528-4bbf7cc66398', 'message', '2026-09-28 11:09:55.933718+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0761-77b7-988e-3424ea9c64a8', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '0f03ac5d-1862-4270-a4ef-f09c6003d06b', 'message', '2026-09-28 11:09:55.933718+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0762-7ed0-88d3-50ee1d2a09bf', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'bbd036fc-b526-4e64-8d32-2d07ac48bb75', 'message', '2026-09-28 11:09:55.933718+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0797-77c3-a4ab-456ca8c555aa', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '2e55b534-e6c7-4191-bca5-4c0c2bfc5156', 'message', '2026-09-28 11:09:55.990994+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0798-7de5-ac2f-4301e68702a4', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '5d96946a-ea9f-45be-b43a-bc0a4cc8835d', 'message', '2026-09-28 11:09:55.990994+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0799-75a2-a7f1-6579a51521e5', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '05136bb0-6c4f-480c-b6e2-2cc4a37db816', 'message', '2026-09-28 11:09:55.990994+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-079a-7e49-8999-49f04f9ae380', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b', 'message', '2026-09-28 11:09:55.990994+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-07ca-7ee4-a79d-89047111ca44', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '9729a8e1-7b8b-42bd-be30-d54449b757b6', 'message', '2026-09-28 11:09:56.042293+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-07cb-709b-b9d1-0e9b7cc8cf0a', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '36bab45a-ac21-42fc-8ddd-a0d6baad1ce3', 'message', '2026-09-28 11:09:56.042293+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-07cc-7ef1-978b-b8cb40b8c5ad', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'ccc42a11-ed9f-466d-9d06-a69b7210f9b9', 'message', '2026-09-28 11:09:56.042293+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-07cd-7067-9fa3-387d15a86507', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'bae9505c-fe9c-47bc-b979-8b5db5b4ca14', 'message', '2026-09-28 11:09:56.042293+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-07f3-7d4c-90e5-1c6cd7760b00', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '4ba6efb2-1393-488c-81a4-c4388efd4ebc', 'message', '2026-09-28 11:09:56.08295+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0dff-7e59-8c1b-ea8855b392e2', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a', 'message', '2026-09-28 11:09:57.630478+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0e00-7e08-9713-f7f3e4af2674', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '106c9e6d-8abb-4516-bccd-26520636fbe0', 'message', '2026-09-28 11:09:57.630478+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0e27-7ab9-bf2e-a4af0b0cdb45', '01a0e7b5-0756-79a1-9f83-ef04295be44f', '3f8f4725-1990-4370-b352-9fa652c723fc', 'message', '2026-09-28 11:09:57.671472+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-0e4f-7d35-8c03-f81e584f73ed', '01a0e7b5-0756-79a1-9f83-ef04295be44f', 'f6cc4960-acb0-48b7-82bb-dc59d2862b07', 'message', '2026-09-28 11:09:57.70939+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-1463-7c66-8d89-f544fbd90286', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '1af50461-8f6d-4c7f-ac61-62070e6e029d', 'message', '2026-09-28 11:09:59.267105+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-1464-77f5-8a72-98ff07d291b2', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '7ed02b26-0280-4a97-bbc9-6092c425d2dc', 'message', '2026-09-28 11:09:59.267105+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-1464-74ac-924f-3bb68f516fea', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '0b20e385-0483-47e0-b7de-d15c1a54f8bb', 'message', '2026-09-28 11:09:59.267105+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-1465-7f9f-9763-65b7c95b1f9d', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', 'a9cc4e94-3d8f-4aa1-8c6c-d70b9bee14d8', 'message', '2026-09-28 11:09:59.267105+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-1466-7809-bf3b-f5e05b3a52e6', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '09ebcac2-9a60-4786-ae35-b80856075afd', 'message', '2026-09-28 11:09:59.267105+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-1466-7303-bfd8-30652c7fdffb', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '032ae72c-f9a3-47e5-bb6e-04a6a9afd9e3', 'message', '2026-09-28 11:09:59.267105+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-1467-74b1-a8d1-b1c13d715cfb', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '3569bf4c-197e-41c6-ba77-862c755395df', 'message', '2026-09-28 11:09:59.267105+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-1468-7c54-a17a-41c3526246d0', '01a0e7b5-1456-7d8c-8843-ed2204cbac43', 'd1946c9d-4a55-4a5d-a26a-c4b892571bb8', 'message', '2026-09-28 11:09:59.267105+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0e7b5-075e-7e6d-b338-794c3f6f57be', '01a0e7b5-075e-7be5-8fce-2df6b2062503', '3ab060d7eb9726c76778004088029511da46829e13886b41662c4e3f25ae4788', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "cb4bd0ca-0319-4d3a-a081-098511e19acf", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:55.933718+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0761-7bbb-b9a1-dfe4890135a3', '01a0e7b5-0761-77b7-988e-3424ea9c64a8', '64f1f6e7a4a03a75b4dd278572e1acc9a4516f45d01fef517642dc0d17c7a913', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "0f03ac5d-1862-4270-a4ef-f09c6003d06b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:55.933718+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0761-730f-8d9e-b0cff6a3dae4', '01a0e7b5-0760-7f84-a16a-89ddfbcb09d0', '2a08e7b30c9113825faed0b03479316422500b3d60cf3c4e98987be88cccb3f8', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "cc5b55ab-37c1-43f9-b528-4bbf7cc66398", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "cc5b55ab-37c1-43f9-b528-4bbf7cc66398", "specialComments": []}', '2026-09-28 11:09:55.933718+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0798-790b-8f45-440966429dd4', '01a0e7b5-0797-77c3-a4ab-456ca8c555aa', '49d0255d4c896ee2403d02dbebe5b7c74b938da47e5bb40d9336fd07d3ed1770', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "2e55b534-e6c7-4191-bca5-4c0c2bfc5156", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:55.990994+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-079a-7e5b-aabf-d12ccb5a421b', '01a0e7b5-0799-75a2-a7f1-6579a51521e5', 'd0e9a9c583ae6ff1083cba2f0ec01cfd4e1e22ab864212c3d9d59d96673b624d', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "05136bb0-6c4f-480c-b6e2-2cc4a37db816", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:55.990994+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0799-7928-96e5-9b8adf91c6f6', '01a0e7b5-0798-7de5-ac2f-4301e68702a4', '87a050b6f5c969eac5c5e640b7d8e0839043426a9c0fb6b0092fbdaf00f9c132', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "specialComments": []}', '2026-09-28 11:09:55.990994+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-07cb-7052-9399-a2c0930c9865', '01a0e7b5-07ca-7ee4-a79d-89047111ca44', '5c743491e6032b4bed95427ec856cc938f5b881f1def6a435411db1bf9bd57c1', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "9729a8e1-7b8b-42bd-be30-d54449b757b6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:56.042293+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-07cc-766b-b207-4e45719027e3', '01a0e7b5-07cc-7ef1-978b-b8cb40b8c5ad', 'b88a3f0b5c03a0f58190950211af0140e3d0d652654e8ae1aa0c4304ce4c5cb3', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "ccc42a11-ed9f-466d-9d06-a69b7210f9b9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:56.042293+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-07cb-7856-9f40-fec804720311', '01a0e7b5-07cb-709b-b9d1-0e9b7cc8cf0a', '298775bb005050c6c5fdc4643a9d5bacf8e16269321e3c398e61877f9f873c0d', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "specialComments": []}', '2026-09-28 11:09:56.042293+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-079a-7622-af08-db1df68add2f', '01a0e7b5-079a-7e49-8999-49f04f9ae380', 'e9cbf942aaef6e0c6493166c8afe4a8723aa1d5d763d6578a77301a9ed3468e9', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", "specialComments": []}', '2026-09-28 11:09:55.990994+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-07f3-7fee-bc41-1c7da88dc283', '01a0e7b5-07f3-7d4c-90e5-1c6cd7760b00', '2cc1b2dcc5e54fe8b7a8345b49900deebcbf62097bf94a9b1f81f41ff14201b3', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "4ba6efb2-1393-488c-81a4-c4388efd4ebc", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:56.08295+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-07cd-7f7e-8c83-7b50239ac7b4', '01a0e7b5-07cd-7067-9fa3-387d15a86507', '555cdb38d59556dc9f4a11c1262a988fba0e6ec21c6eacbba71a920840fabd51', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "specialComments": []}', '2026-09-28 11:09:56.042293+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0e00-7c0c-96b8-99034cd44ee6', '01a0e7b5-0e00-7e08-9713-f7f3e4af2674', '2dc587143e36ebe53c01e10cc109baf9581e309d4814fa5fff9ab084893741e2', 'And the compass?', '{"name": null, "role": "user", "chatId": "106c9e6d-8abb-4516-bccd-26520636fbe0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:57.630478+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0e00-7ae5-8a4f-9cf36901c03d', '01a0e7b5-0dff-7e59-8c1b-ea8855b392e2', 'f717308a6912ff6283a9b359bb2f2623502b8ae65e599ff108cb7670fe6ef769', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "specialComments": []}', '2026-09-28 11:09:57.630478+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0762-792d-b99f-f6474ba220e7', '01a0e7b5-0762-7ed0-88d3-50ee1d2a09bf', '9e71ff8dd4c5917de2223763faee08f56e77d9e0693c688eed69c4968ecda162', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "bbd036fc-b526-4e64-8d32-2d07ac48bb75", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "bbd036fc-b526-4e64-8d32-2d07ac48bb75", "specialComments": []}', '2026-09-28 11:09:55.933718+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0dff-702d-b2e6-c3a4e7493501', '01a0e7b5-0762-7ed0-88d3-50ee1d2a09bf', 'cd170743b8399eaef6ff9d748f66edc1d5f9e6101dacd43a906c8e466e83cdf2', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "bbd036fc-b526-4e64-8d32-2d07ac48bb75", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "bbd036fc-b526-4e64-8d32-2d07ac48bb75", "specialComments": []}', '2026-09-28 11:09:57.630478+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0e4e-7b15-9708-86e2c70427a7', '01a0e7b5-07ca-7ee4-a79d-89047111ca44', '4d462e10ee5cc7807e92628b2ca3be8a4d6391ca9e1f51d34e5dba9dcc50725f', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "9729a8e1-7b8b-42bd-be30-d54449b757b6", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:57.70939+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0e4f-7235-ad87-24100c6ca2e5', '01a0e7b5-0e4f-7d35-8c03-f81e584f73ed', 'e601e59c8d7423ceb53ceede26eca87fc01d28c6e7987d921bcbacac104a2653', 'Let''s go.', '{"name": null, "role": "user", "chatId": "f6cc4960-acb0-48b7-82bb-dc59d2862b07", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:57.70939+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0e28-72d2-932d-a1b8064536af', '01a0e7b5-0e27-7ab9-bf2e-a4af0b0cdb45', '910725335822e4d7fa097938b0ebebb5f39db8b69a689ab815d195337778a2b9', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "3f8f4725-1990-4370-b352-9fa652c723fc", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "3f8f4725-1990-4370-b352-9fa652c723fc", "specialComments": []}', '2026-09-28 11:09:57.671472+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-0e4e-70bd-978b-51f59946e64a', '01a0e7b5-0e27-7ab9-bf2e-a4af0b0cdb45', 'b50b632ac29d5df133028260b35e569df787b0efaea43605bc78f1a8a28fb069', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "3f8f4725-1990-4370-b352-9fa652c723fc", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "3f8f4725-1990-4370-b352-9fa652c723fc", "specialComments": []}', '2026-09-28 11:09:57.70939+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-1463-748a-b48b-c948c2f60b58', '01a0e7b5-1463-7c66-8d89-f544fbd90286', '8d9f9459a639dab622f60affa648beeda454289bc637091b67e5001835cf68b2', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "1af50461-8f6d-4c7f-ac61-62070e6e029d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:59.267105+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-1465-7dda-8b1b-0b6fc08e8f40', '01a0e7b5-1464-74ac-924f-3bb68f516fea', '657a2638588d97b3f420e1e09c29cf3ed02485198e3b0b62d41bbbfc57544ce2', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "0b20e385-0483-47e0-b7de-d15c1a54f8bb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:59.267105+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-1466-7906-be46-17f434542d68', '01a0e7b5-1466-7809-bf3b-f5e05b3a52e6', '8f1bfc22eb07c87d6667d6b70746dd7389b93b617ed988363f8a7abcb373be99', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "09ebcac2-9a60-4786-ae35-b80856075afd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:59.267105+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-1467-7fef-9f54-4af3f344de1b', '01a0e7b5-1467-74b1-a8d1-b1c13d715cfb', '3ce1d4461b809c4d72cc8956f3e00e46ff61ffb700b56a9b25b0e19768416a72', '{{specialcomment::branchedfrom::d3822c6c-3bde-4ec7-8712-8e0d6bef57bc::Harbor route::5d96946a-ea9f-45be-b43a-bc0a4cc8835d::}}', '{"name": null, "role": "char", "chatId": "3569bf4c-197e-41c6-ba77-862c755395df", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::d3822c6c-3bde-4ec7-8712-8e0d6bef57bc::Harbor route::5d96946a-ea9f-45be-b43a-bc0a4cc8835d::}}"]}', '2026-09-28 11:09:59.267105+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-1468-7ae6-89fa-32142af0da5f', '01a0e7b5-1468-7c54-a17a-41c3526246d0', '4d6188ab40104f958bcdbe36a8f5f556e2868e05d8bfd65c9df51d0ae20751ef', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "d1946c9d-4a55-4a5d-a26a-c4b892571bb8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:59.267105+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-1467-712e-897a-3381d86c275a', '01a0e7b5-1466-7303-bfd8-30652c7fdffb', '2d9adb6f49ef78ad0f67ac94f8dab8d8c27758738e7807599e3172bbe029f68c', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "032ae72c-f9a3-47e5-bb6e-04a6a9afd9e3", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "specialComments": []}', '2026-09-28 11:09:59.267105+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-1464-7466-b1ac-2b210d9a190b', '01a0e7b5-1464-77f5-8a72-98ff07d291b2', '6b03c237fd46582677a3734937dfa37336962c54483cdaa04d0dc0bc41edc663', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "7ed02b26-0280-4a97-bbc9-6092c425d2dc", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "cc5b55ab-37c1-43f9-b528-4bbf7cc66398", "specialComments": []}', '2026-09-28 11:09:59.267105+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-1465-74b5-8b22-1e6d83d913d9', '01a0e7b5-1465-7f9f-9763-65b7c95b1f9d', '94b450c5d55488956120379e7b06f61df91b6a6e2c2f6f9d0c7719216f8735ef', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "a9cc4e94-3d8f-4aa1-8c6c-d70b9bee14d8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "bbd036fc-b526-4e64-8d32-2d07ac48bb75", "specialComments": []}', '2026-09-28 11:09:59.267105+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0e7b5-0765-7a75-953f-ffa2b44d5497', '[{"op": "insert", "after": ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "9e71ff8dd4c5917de2223763faee08f56e77d9e0693c688eed69c4968ecda162"], "member": ["2e55b534-e6c7-4191-bca5-4c0c2bfc5156", "49d0255d4c896ee2403d02dbebe5b7c74b938da47e5bb40d9336fd07d3ed1770"]}, {"op": "insert", "after": ["2e55b534-e6c7-4191-bca5-4c0c2bfc5156", "49d0255d4c896ee2403d02dbebe5b7c74b938da47e5bb40d9336fd07d3ed1770"], "member": ["5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "87a050b6f5c969eac5c5e640b7d8e0839043426a9c0fb6b0092fbdaf00f9c132"]}, {"op": "insert", "after": ["5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "87a050b6f5c969eac5c5e640b7d8e0839043426a9c0fb6b0092fbdaf00f9c132"], "member": ["05136bb0-6c4f-480c-b6e2-2cc4a37db816", "d0e9a9c583ae6ff1083cba2f0ec01cfd4e1e22ab864212c3d9d59d96673b624d"]}, {"op": "insert", "after": ["05136bb0-6c4f-480c-b6e2-2cc4a37db816", "d0e9a9c583ae6ff1083cba2f0ec01cfd4e1e22ab864212c3d9d59d96673b624d"], "member": ["95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", "e9cbf942aaef6e0c6493166c8afe4a8723aa1d5d763d6578a77301a9ed3468e9"]}]', '[{"new": ["2e55b534-e6c7-4191-bca5-4c0c2bfc5156", "49d0255d4c896ee2403d02dbebe5b7c74b938da47e5bb40d9336fd07d3ed1770"], "old": null, "kind": "append", "position": 4, "host_logical_id": "2e55b534-e6c7-4191-bca5-4c0c2bfc5156"}, {"new": ["5d96946a-ea9f-45be-b43a-bc0a4cc8835d", "87a050b6f5c969eac5c5e640b7d8e0839043426a9c0fb6b0092fbdaf00f9c132"], "old": null, "kind": "append", "position": 5, "host_logical_id": "5d96946a-ea9f-45be-b43a-bc0a4cc8835d"}, {"new": ["05136bb0-6c4f-480c-b6e2-2cc4a37db816", "d0e9a9c583ae6ff1083cba2f0ec01cfd4e1e22ab864212c3d9d59d96673b624d"], "old": null, "kind": "append", "position": 6, "host_logical_id": "05136bb0-6c4f-480c-b6e2-2cc4a37db816"}, {"new": ["95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", "e9cbf942aaef6e0c6493166c8afe4a8723aa1d5d763d6578a77301a9ed3468e9"], "old": null, "kind": "append", "position": 7, "host_logical_id": "95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b"}]', '01a0e7b5-079d-7768-84ae-84feed7f2725', '2026-09-28 11:09:55.990994+00');
INSERT INTO public.worldline_append VALUES (2, '01a0e7b5-0765-7a75-953f-ffa2b44d5497', '[{"op": "insert", "after": ["95a8e5cc-19b9-433e-9432-f4d0a9ae9b0b", "e9cbf942aaef6e0c6493166c8afe4a8723aa1d5d763d6578a77301a9ed3468e9"], "member": ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "5c743491e6032b4bed95427ec856cc938f5b881f1def6a435411db1bf9bd57c1"]}, {"op": "insert", "after": ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "5c743491e6032b4bed95427ec856cc938f5b881f1def6a435411db1bf9bd57c1"], "member": ["36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "298775bb005050c6c5fdc4643a9d5bacf8e16269321e3c398e61877f9f873c0d"]}, {"op": "insert", "after": ["36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "298775bb005050c6c5fdc4643a9d5bacf8e16269321e3c398e61877f9f873c0d"], "member": ["ccc42a11-ed9f-466d-9d06-a69b7210f9b9", "b88a3f0b5c03a0f58190950211af0140e3d0d652654e8ae1aa0c4304ce4c5cb3"]}, {"op": "insert", "after": ["ccc42a11-ed9f-466d-9d06-a69b7210f9b9", "b88a3f0b5c03a0f58190950211af0140e3d0d652654e8ae1aa0c4304ce4c5cb3"], "member": ["bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "555cdb38d59556dc9f4a11c1262a988fba0e6ec21c6eacbba71a920840fabd51"]}]', '[{"new": ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "5c743491e6032b4bed95427ec856cc938f5b881f1def6a435411db1bf9bd57c1"], "old": null, "kind": "append", "position": 8, "host_logical_id": "9729a8e1-7b8b-42bd-be30-d54449b757b6"}, {"new": ["36bab45a-ac21-42fc-8ddd-a0d6baad1ce3", "298775bb005050c6c5fdc4643a9d5bacf8e16269321e3c398e61877f9f873c0d"], "old": null, "kind": "append", "position": 9, "host_logical_id": "36bab45a-ac21-42fc-8ddd-a0d6baad1ce3"}, {"new": ["ccc42a11-ed9f-466d-9d06-a69b7210f9b9", "b88a3f0b5c03a0f58190950211af0140e3d0d652654e8ae1aa0c4304ce4c5cb3"], "old": null, "kind": "append", "position": 10, "host_logical_id": "ccc42a11-ed9f-466d-9d06-a69b7210f9b9"}, {"new": ["bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "555cdb38d59556dc9f4a11c1262a988fba0e6ec21c6eacbba71a920840fabd51"], "old": null, "kind": "append", "position": 11, "host_logical_id": "bae9505c-fe9c-47bc-b979-8b5db5b4ca14"}]', '01a0e7b5-07d0-751d-8239-b1c579aa7ac1', '2026-09-28 11:09:56.042293+00');
INSERT INTO public.worldline_append VALUES (3, '01a0e7b5-0765-7a75-953f-ffa2b44d5497', '[{"op": "insert", "after": ["bae9505c-fe9c-47bc-b979-8b5db5b4ca14", "555cdb38d59556dc9f4a11c1262a988fba0e6ec21c6eacbba71a920840fabd51"], "member": ["4ba6efb2-1393-488c-81a4-c4388efd4ebc", "2cc1b2dcc5e54fe8b7a8345b49900deebcbf62097bf94a9b1f81f41ff14201b3"]}]', '[{"new": ["4ba6efb2-1393-488c-81a4-c4388efd4ebc", "2cc1b2dcc5e54fe8b7a8345b49900deebcbf62097bf94a9b1f81f41ff14201b3"], "old": null, "kind": "append", "position": 12, "host_logical_id": "4ba6efb2-1393-488c-81a4-c4388efd4ebc"}]', '01a0e7b5-07f6-7889-81bb-1f46b50d8c8a', '2026-09-28 11:09:56.08295+00');
INSERT INTO public.worldline_append VALUES (4, '01a0e7b5-0e03-7467-8705-b3a5050063f3', '[{"op": "insert", "after": ["106c9e6d-8abb-4516-bccd-26520636fbe0", "2dc587143e36ebe53c01e10cc109baf9581e309d4814fa5fff9ab084893741e2"], "member": ["3f8f4725-1990-4370-b352-9fa652c723fc", "910725335822e4d7fa097938b0ebebb5f39db8b69a689ab815d195337778a2b9"]}]', '[{"new": ["3f8f4725-1990-4370-b352-9fa652c723fc", "910725335822e4d7fa097938b0ebebb5f39db8b69a689ab815d195337778a2b9"], "old": null, "kind": "append", "position": 15, "host_logical_id": "3f8f4725-1990-4370-b352-9fa652c723fc"}]', '01a0e7b5-0e2a-74de-969e-db50589362d4', '2026-09-28 11:09:57.671472+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-0765-7a75-953f-ffa2b44d5497', 1, '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{}', 'import', '2e738abe5d3461e5b4f47bfc3af7dc7da125455acdfe02caea8e1be5cfecf8e0', '{"ops": [{"op": "set", "members": [["cb4bd0ca-0319-4d3a-a081-098511e19acf", "3ab060d7eb9726c76778004088029511da46829e13886b41662c4e3f25ae4788"], ["cc5b55ab-37c1-43f9-b528-4bbf7cc66398", "2a08e7b30c9113825faed0b03479316422500b3d60cf3c4e98987be88cccb3f8"], ["0f03ac5d-1862-4270-a4ef-f09c6003d06b", "64f1f6e7a4a03a75b4dd278572e1acc9a4516f45d01fef517642dc0d17c7a913"], ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "9e71ff8dd4c5917de2223763faee08f56e77d9e0693c688eed69c4968ecda162"]]}], "changes": [{"new": ["cb4bd0ca-0319-4d3a-a081-098511e19acf", "3ab060d7eb9726c76778004088029511da46829e13886b41662c4e3f25ae4788"], "old": null, "kind": "append", "position": 0, "host_logical_id": "cb4bd0ca-0319-4d3a-a081-098511e19acf"}, {"new": ["cc5b55ab-37c1-43f9-b528-4bbf7cc66398", "2a08e7b30c9113825faed0b03479316422500b3d60cf3c4e98987be88cccb3f8"], "old": null, "kind": "append", "position": 1, "host_logical_id": "cc5b55ab-37c1-43f9-b528-4bbf7cc66398"}, {"new": ["0f03ac5d-1862-4270-a4ef-f09c6003d06b", "64f1f6e7a4a03a75b4dd278572e1acc9a4516f45d01fef517642dc0d17c7a913"], "old": null, "kind": "append", "position": 2, "host_logical_id": "0f03ac5d-1862-4270-a4ef-f09c6003d06b"}, {"new": ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "9e71ff8dd4c5917de2223763faee08f56e77d9e0693c688eed69c4968ecda162"], "old": null, "kind": "append", "position": 3, "host_logical_id": "bbd036fc-b526-4e64-8d32-2d07ac48bb75"}]}', '2026-09-28 11:09:55.933718+00', '01a0e7b5-0764-790f-868a-b460969947c2');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-0e03-7467-8705-b3a5050063f3', 2, '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{01a0e7b5-0765-7a75-953f-ffa2b44d5497}', 'edit', '605690129413ad7d6d915a152a51393bacee9855fc8aeee691a0780a64d21576', '{"ops": [{"op": "replace", "to": ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "cd170743b8399eaef6ff9d748f66edc1d5f9e6101dacd43a906c8e466e83cdf2"], "from": ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "9e71ff8dd4c5917de2223763faee08f56e77d9e0693c688eed69c4968ecda162"]}, {"op": "insert", "after": ["4ba6efb2-1393-488c-81a4-c4388efd4ebc", "2cc1b2dcc5e54fe8b7a8345b49900deebcbf62097bf94a9b1f81f41ff14201b3"], "member": ["2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "f717308a6912ff6283a9b359bb2f2623502b8ae65e599ff108cb7670fe6ef769"]}, {"op": "insert", "after": ["2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "f717308a6912ff6283a9b359bb2f2623502b8ae65e599ff108cb7670fe6ef769"], "member": ["106c9e6d-8abb-4516-bccd-26520636fbe0", "2dc587143e36ebe53c01e10cc109baf9581e309d4814fa5fff9ab084893741e2"]}], "changes": [{"new": ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "cd170743b8399eaef6ff9d748f66edc1d5f9e6101dacd43a906c8e466e83cdf2"], "old": ["bbd036fc-b526-4e64-8d32-2d07ac48bb75", "9e71ff8dd4c5917de2223763faee08f56e77d9e0693c688eed69c4968ecda162"], "kind": "edit", "position": 3, "host_logical_id": "bbd036fc-b526-4e64-8d32-2d07ac48bb75"}, {"new": ["2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a", "f717308a6912ff6283a9b359bb2f2623502b8ae65e599ff108cb7670fe6ef769"], "old": null, "kind": "append", "position": 13, "host_logical_id": "2b0ec9d1-ce0e-4fdb-aa96-597809c97f0a"}, {"new": ["106c9e6d-8abb-4516-bccd-26520636fbe0", "2dc587143e36ebe53c01e10cc109baf9581e309d4814fa5fff9ab084893741e2"], "old": null, "kind": "append", "position": 14, "host_logical_id": "106c9e6d-8abb-4516-bccd-26520636fbe0"}]}', '2026-09-28 11:09:57.630478+00', '01a0e7b5-0e02-7397-bac7-2d33b427e73a');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-0e52-777b-9e6b-11ff0fa4bfde', 3, '01a0e7b5-0756-79a1-9f83-ef04295be44f', '{01a0e7b5-0e03-7467-8705-b3a5050063f3}', 'reconciliation', '2e2291d9b1eed68dae68fb23db34fa739acb2b4221674ed3dd2e94e5e6a9a1c4', '{"ops": [{"op": "replace", "to": ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "4d462e10ee5cc7807e92628b2ca3be8a4d6391ca9e1f51d34e5dba9dcc50725f"], "from": ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "5c743491e6032b4bed95427ec856cc938f5b881f1def6a435411db1bf9bd57c1"]}, {"op": "replace", "to": ["3f8f4725-1990-4370-b352-9fa652c723fc", "b50b632ac29d5df133028260b35e569df787b0efaea43605bc78f1a8a28fb069"], "from": ["3f8f4725-1990-4370-b352-9fa652c723fc", "910725335822e4d7fa097938b0ebebb5f39db8b69a689ab815d195337778a2b9"]}, {"op": "insert", "after": ["3f8f4725-1990-4370-b352-9fa652c723fc", "b50b632ac29d5df133028260b35e569df787b0efaea43605bc78f1a8a28fb069"], "member": ["f6cc4960-acb0-48b7-82bb-dc59d2862b07", "e601e59c8d7423ceb53ceede26eca87fc01d28c6e7987d921bcbacac104a2653"]}], "changes": [{"new": ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "4d462e10ee5cc7807e92628b2ca3be8a4d6391ca9e1f51d34e5dba9dcc50725f"], "old": ["9729a8e1-7b8b-42bd-be30-d54449b757b6", "5c743491e6032b4bed95427ec856cc938f5b881f1def6a435411db1bf9bd57c1"], "kind": "disable", "position": 8, "host_logical_id": "9729a8e1-7b8b-42bd-be30-d54449b757b6"}, {"new": ["3f8f4725-1990-4370-b352-9fa652c723fc", "b50b632ac29d5df133028260b35e569df787b0efaea43605bc78f1a8a28fb069"], "old": ["3f8f4725-1990-4370-b352-9fa652c723fc", "910725335822e4d7fa097938b0ebebb5f39db8b69a689ab815d195337778a2b9"], "kind": "swipe", "position": 15, "host_logical_id": "3f8f4725-1990-4370-b352-9fa652c723fc"}, {"new": ["f6cc4960-acb0-48b7-82bb-dc59d2862b07", "e601e59c8d7423ceb53ceede26eca87fc01d28c6e7987d921bcbacac104a2653"], "old": null, "kind": "append", "position": 16, "host_logical_id": "f6cc4960-acb0-48b7-82bb-dc59d2862b07"}]}', '2026-09-28 11:09:57.70939+00', '01a0e7b5-0e51-76ad-a1c2-bb8e203d9722');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-146a-79fe-8ba1-f76a065faead', 4, '01a0e7b5-1456-7d8c-8843-ed2204cbac43', '{}', 'branch', '2eb22a573b14a2e7e7e7a13b34efe0f0233c5721b13cc9f4e51aaea507235f4d', '{"ops": [{"op": "set", "members": [["1af50461-8f6d-4c7f-ac61-62070e6e029d", "8d9f9459a639dab622f60affa648beeda454289bc637091b67e5001835cf68b2"], ["7ed02b26-0280-4a97-bbc9-6092c425d2dc", "6b03c237fd46582677a3734937dfa37336962c54483cdaa04d0dc0bc41edc663"], ["0b20e385-0483-47e0-b7de-d15c1a54f8bb", "657a2638588d97b3f420e1e09c29cf3ed02485198e3b0b62d41bbbfc57544ce2"], ["a9cc4e94-3d8f-4aa1-8c6c-d70b9bee14d8", "94b450c5d55488956120379e7b06f61df91b6a6e2c2f6f9d0c7719216f8735ef"], ["09ebcac2-9a60-4786-ae35-b80856075afd", "8f1bfc22eb07c87d6667d6b70746dd7389b93b617ed988363f8a7abcb373be99"], ["032ae72c-f9a3-47e5-bb6e-04a6a9afd9e3", "2d9adb6f49ef78ad0f67ac94f8dab8d8c27758738e7807599e3172bbe029f68c"], ["3569bf4c-197e-41c6-ba77-862c755395df", "3ce1d4461b809c4d72cc8956f3e00e46ff61ffb700b56a9b25b0e19768416a72"], ["d1946c9d-4a55-4a5d-a26a-c4b892571bb8", "4d6188ab40104f958bcdbe36a8f5f556e2868e05d8bfd65c9df51d0ae20751ef"]]}], "changes": [{"new": ["1af50461-8f6d-4c7f-ac61-62070e6e029d", "8d9f9459a639dab622f60affa648beeda454289bc637091b67e5001835cf68b2"], "old": null, "kind": "append", "position": 0, "host_logical_id": "1af50461-8f6d-4c7f-ac61-62070e6e029d"}, {"new": ["7ed02b26-0280-4a97-bbc9-6092c425d2dc", "6b03c237fd46582677a3734937dfa37336962c54483cdaa04d0dc0bc41edc663"], "old": null, "kind": "append", "position": 1, "host_logical_id": "7ed02b26-0280-4a97-bbc9-6092c425d2dc"}, {"new": ["0b20e385-0483-47e0-b7de-d15c1a54f8bb", "657a2638588d97b3f420e1e09c29cf3ed02485198e3b0b62d41bbbfc57544ce2"], "old": null, "kind": "append", "position": 2, "host_logical_id": "0b20e385-0483-47e0-b7de-d15c1a54f8bb"}, {"new": ["a9cc4e94-3d8f-4aa1-8c6c-d70b9bee14d8", "94b450c5d55488956120379e7b06f61df91b6a6e2c2f6f9d0c7719216f8735ef"], "old": null, "kind": "append", "position": 3, "host_logical_id": "a9cc4e94-3d8f-4aa1-8c6c-d70b9bee14d8"}, {"new": ["09ebcac2-9a60-4786-ae35-b80856075afd", "8f1bfc22eb07c87d6667d6b70746dd7389b93b617ed988363f8a7abcb373be99"], "old": null, "kind": "append", "position": 4, "host_logical_id": "09ebcac2-9a60-4786-ae35-b80856075afd"}, {"new": ["032ae72c-f9a3-47e5-bb6e-04a6a9afd9e3", "2d9adb6f49ef78ad0f67ac94f8dab8d8c27758738e7807599e3172bbe029f68c"], "old": null, "kind": "append", "position": 5, "host_logical_id": "032ae72c-f9a3-47e5-bb6e-04a6a9afd9e3"}, {"new": ["3569bf4c-197e-41c6-ba77-862c755395df", "3ce1d4461b809c4d72cc8956f3e00e46ff61ffb700b56a9b25b0e19768416a72"], "old": null, "kind": "append", "position": 6, "host_logical_id": "3569bf4c-197e-41c6-ba77-862c755395df"}, {"new": ["d1946c9d-4a55-4a5d-a26a-c4b892571bb8", "4d6188ab40104f958bcdbe36a8f5f556e2868e05d8bfd65c9df51d0ae20751ef"], "old": null, "kind": "append", "position": 7, "host_logical_id": "d1946c9d-4a55-4a5d-a26a-c4b892571bb8"}]}', '2026-09-28 11:09:59.267105+00', '01a0e7b5-1469-7508-90c1-897acfd73018');


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


