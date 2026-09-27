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

INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 0, '01a0e247-5d3a-7ad2-bbe9-911660be0cad', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 1, '01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c', NULL, 0, 'a15b63019cacbcb813aa95b376d8a895');
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 2, '01a0e247-5d3d-7c4f-a4f0-fec41c6c8504', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 3, '01a0e247-63d6-75e0-934e-7e0c38c02e8f', NULL, 1, 'c9439a40045c6a18880b6cade149d82d');
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 4, '01a0e247-5d74-74c0-8750-ab7692c72128', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 5, '01a0e247-5d75-7314-ba2a-35bbe3b8321c', NULL, 2, 'e99f93650f14e8855931dad2c6ff85e8');
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 6, '01a0e247-5d76-7621-a497-f1ed97bf11f7', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 7, '01a0e247-5d77-7f77-9e5f-0eb915f083df', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 8, '01a0e247-6428-76be-a890-8cd0180a66ab', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 9, '01a0e247-5d9e-7df8-8f8a-a997df016385', NULL, 3, '081d8edfedb133db63004b0d3d2823a0');
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 10, '01a0e247-5d9f-7246-b37c-3bea9e4c1a58', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 11, '01a0e247-5d9f-7cb3-8c8c-3f129863dad2', NULL, 4, 'c72101b01a766edc77e2ee7d0c1fef63');
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 12, '01a0e247-5dc7-7a19-8b70-51c0d09069e3', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 13, '01a0e247-63d6-7050-9984-c84df00d8a96', NULL, 5, 'e55b46e4a142869f84a2c9c877dfb64c');
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 14, '01a0e247-63d7-7e55-b134-655e194ed510', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 15, '01a0e247-6429-7c8a-8a92-9a5eb802a4a8', NULL, 6, '0a79f89d61c8e3627d28d2c7aeafe1ec');
INSERT INTO public.active_membership VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 16, '01a0e247-642a-7c17-9fa3-5b2ad5473dff', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 0, '01a0e247-6a38-77e8-bfbb-15debe73231f', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 1, '01a0e247-6a39-7d33-a7be-f49e0319cac1', NULL, 0, '5ca4d2496e37dbc65ec511b26c67d923');
INSERT INTO public.active_membership VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 2, '01a0e247-6a39-7395-b6ce-1f53ee8de76e', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 3, '01a0e247-6a3a-7834-986d-cbb5ad5064d0', NULL, 1, '58d820986f23f19869cf9ff16b725c4d');
INSERT INTO public.active_membership VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 4, '01a0e247-6a3b-775c-950a-6186256af0b9', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 5, '01a0e247-6a3b-73c9-b1f0-46dd096ffc36', NULL, 2, 'ceab0800aa4a37aac3b6597c785999d1');
INSERT INTO public.active_membership VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 6, '01a0e247-6a3c-752a-95e9-b43697f66c63', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 7, '01a0e247-6a3d-731f-81d2-18cb9553804d', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0e247-62c7-7ee5-9418-90718710158c', '01a0e247-5d9f-7cb3-8c8c-3f129863dad2', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0e247-62df-75dd-93d6-d04776b273e6', '01a0e247-5d9e-7df8-8f8a-a997df016385', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0e247-630c-78ee-9e44-92703011fa0c', '01a0e247-5d75-7314-ba2a-35bbe3b8321c', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0e247-6325-7ffb-9bff-86a69bd756ba', '01a0e247-5d3e-775c-b0f2-538e91387729', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0e247-6325-7ffb-9bff-86a69bd756ba', '01a0e247-5d3e-775c-b0f2-538e91387729', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0e247-6376-79cb-8400-8cac707f8289', '01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0e247-6376-79cb-8400-8cac707f8289', '01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0e247-67ef-72c9-8e1e-c33ea32d8ad3', '01a0e247-6429-7c8a-8a92-9a5eb802a4a8', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0e247-681f-7152-a750-cbbabd2308ba', '01a0e247-5d9f-7cb3-8c8c-3f129863dad2', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0e247-6836-78c4-a02f-05b9b501a9e0', '01a0e247-5d9e-7df8-8f8a-a997df016385', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0e247-6859-76d3-b049-df5cc591f155', '01a0e247-5d75-7314-ba2a-35bbe3b8321c', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0e247-686e-7482-a826-90be125c94c3', '01a0e247-63d6-75e0-934e-7e0c38c02e8f', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0e247-686e-7482-a826-90be125c94c3', '01a0e247-63d6-75e0-934e-7e0c38c02e8f', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0e247-6cfa-7d0e-bf10-7b92f3495144', '01a0e247-6a3b-73c9-b1f0-46dd096ffc36', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0e247-6d12-7af2-9b77-714e6a2a1eb4', '01a0e247-6a3a-7834-986d-cbb5ad5064d0', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0e247-6d12-7af2-9b77-714e6a2a1eb4', '01a0e247-6a3a-7834-986d-cbb5ad5064d0', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0e247-6d28-71c6-aedb-8526dfb8414c', '01a0e247-6a39-7d33-a7be-f49e0319cac1', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0e247-6d28-71c6-aedb-8526dfb8414c', '01a0e247-6a39-7d33-a7be-f49e0319cac1', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0e247-5d32-7d21-a51c-21745cbe1882', 'pocketrisu', NULL, 'c035bf48-f66c-43ff-92c5-e02cb7394cdc', '2026-09-27 09:52:02.866861+00', NULL, NULL, NULL, '01a0e247-642d-7236-a94f-350ff70ef05b', 'c86ecde851c307e98d7ced1f01c28f384cdb0682766bf758d2af356db3635dff', 'Mina', 'Upgrade fixture', 'Yuuma');
INSERT INTO public.conversation VALUES ('01a0e247-6a31-7fef-85da-d6e25cf4e3f9', 'pocketrisu', NULL, '6dabb2fa-b3d1-44c6-8fee-08309bb64ac2', '2026-09-27 09:52:06.193375+00', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'c035bf48-f66c-43ff-92c5-e02cb7394cdc', '81b82fa5-270b-4815-be8b-c41d5534bd74', '01a0e247-6a3f-7186-a921-05ec6e3014b2', '14d036bccb1afbfd6a2f5754d4b7d8409ee9660cd4ada6c51f204faadda9dcdf', 'Mina', 'Upgrade fixture', 'Yuuma');


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0e247-62c7-7ee5-9418-90718710158c', '01a0e247-5d9f-7cb3-8c8c-3f129863dad2', '7bf0bc4855a6f78eb0fff2ba241cfbd7', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:04.295429+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e247-5d9f-7246-b37c-3bea9e4c1a58,01a0e247-5d9f-7cb3-8c8c-3f129863dad2}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-62df-75dd-93d6-d04776b273e6', '01a0e247-5d9e-7df8-8f8a-a997df016385', 'f826d6a78781c22e9c01d56665c5bd69', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:04.319703+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e247-5d9d-70ba-b274-9c4f31e89259,01a0e247-5d9e-7df8-8f8a-a997df016385}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-62f6-7626-b06a-9a0cf975de87', '01a0e247-5d77-7f77-9e5f-0eb915f083df', 'cc66f00348e887007565a2efbb39680d', 'extract-v10', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-27 09:52:04.342273+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e247-5d76-7621-a497-f1ed97bf11f7,01a0e247-5d77-7f77-9e5f-0eb915f083df}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-630c-78ee-9e44-92703011fa0c', '01a0e247-5d75-7314-ba2a-35bbe3b8321c', '5c5da6bb1ac46bd7a8e6173632ea3597', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:04.364795+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e247-5d74-74c0-8750-ab7692c72128,01a0e247-5d75-7314-ba2a-35bbe3b8321c}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-6325-7ffb-9bff-86a69bd756ba', '01a0e247-5d3e-775c-b0f2-538e91387729', 'd782ea2bba133009c296ab4d6c94ab40', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:04.389739+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e247-5d3d-7c4f-a4f0-fec41c6c8504,01a0e247-5d3e-775c-b0f2-538e91387729}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-6376-79cb-8400-8cac707f8289', '01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c', 'a15b63019cacbcb813aa95b376d8a895', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:04.470443+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e247-5d3a-7ad2-bbe9-911660be0cad,01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-67ef-72c9-8e1e-c33ea32d8ad3', '01a0e247-6429-7c8a-8a92-9a5eb802a4a8', '0a79f89d61c8e3627d28d2c7aeafe1ec', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:05.615715+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e247-63d7-7e55-b134-655e194ed510,01a0e247-6429-7c8a-8a92-9a5eb802a4a8}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-6808-7e53-87d2-bc83c7fc8f9c', '01a0e247-63d6-7050-9984-c84df00d8a96', 'e55b46e4a142869f84a2c9c877dfb64c', 'extract-v10', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-27 09:52:05.640456+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e247-5dc7-7a19-8b70-51c0d09069e3,01a0e247-63d6-7050-9984-c84df00d8a96}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-681f-7152-a750-cbbabd2308ba', '01a0e247-5d9f-7cb3-8c8c-3f129863dad2', 'c72101b01a766edc77e2ee7d0c1fef63', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:05.662982+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e247-5d9f-7246-b37c-3bea9e4c1a58,01a0e247-5d9f-7cb3-8c8c-3f129863dad2}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-6836-78c4-a02f-05b9b501a9e0', '01a0e247-5d9e-7df8-8f8a-a997df016385', '081d8edfedb133db63004b0d3d2823a0', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:05.686671+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0e247-5d76-7621-a497-f1ed97bf11f7,01a0e247-5d77-7f77-9e5f-0eb915f083df,01a0e247-5d9e-7df8-8f8a-a997df016385}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-6859-76d3-b049-df5cc591f155', '01a0e247-5d75-7314-ba2a-35bbe3b8321c', 'e99f93650f14e8855931dad2c6ff85e8', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:05.721806+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e247-5d74-74c0-8750-ab7692c72128,01a0e247-5d75-7314-ba2a-35bbe3b8321c}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-686e-7482-a826-90be125c94c3', '01a0e247-63d6-75e0-934e-7e0c38c02e8f', 'c9439a40045c6a18880b6cade149d82d', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:05.742917+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e247-5d3d-7c4f-a4f0-fec41c6c8504,01a0e247-63d6-75e0-934e-7e0c38c02e8f}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-6cfa-7d0e-bf10-7b92f3495144', '01a0e247-6a3b-73c9-b1f0-46dd096ffc36', 'ceab0800aa4a37aac3b6597c785999d1', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:06.906736+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e247-6a3b-775c-950a-6186256af0b9,01a0e247-6a3b-73c9-b1f0-46dd096ffc36}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-6d12-7af2-9b77-714e6a2a1eb4', '01a0e247-6a3a-7834-986d-cbb5ad5064d0', '58d820986f23f19869cf9ff16b725c4d', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:06.930435+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e247-6a39-7395-b6ce-1f53ee8de76e,01a0e247-6a3a-7834-986d-cbb5ad5064d0}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e247-6d28-71c6-aedb-8526dfb8414c', '01a0e247-6a39-7d33-a7be-f49e0319cac1', '5ca4d2496e37dbc65ec511b26c67d923', 'extract-v10', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-27 09:52:06.952402+00', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e247-6a38-77e8-bfbb-15debe73231f,01a0e247-6a39-7d33-a7be-f49e0319cac1}', NULL, '{"entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0e247-5d3f-7375-afe5-6f582e7b45fb', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'manifest', '87903964bfc137e43abc378fd022e641ce60819e3adadedebf54a64c8235063f', '01a0e247-5d32-7d21-a51c-21745cbe1882:87903964bfc137e43abc378fd022e641ce60819e3adadedebf54a64c8235063f:manifest', '2026-09-27 09:52:02.873335+00', '{"chat_id": "c035bf48-f66c-43ff-92c5-e02cb7394cdc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["359555fe-f91f-4a5c-938e-54c5267269d7", "6e670a4f782b434fe5eda19655ce3cd2a5b5aee9f00d0642d9b6bfb48f6fd614", "user", null, null, null, 0, null, null], ["bb57d506-013d-4829-ba99-4e7a1c640a4f", "9469d74f66d65e6249639ec49051a02cba1735dae1676caa85cc47de9228a07b", "char", null, null, null, 0, "bb57d506-013d-4829-ba99-4e7a1c640a4f", null], ["9d98eb62-7f5b-4587-807d-b8e73e49829b", "22203c487916f901977b6cd07f178176aef697e19b99adad4c00d526dce13990", "user", null, null, null, 0, null, null], ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "fa10d1571d7feb590585125c47c705c9977f13366a888094e5599aff19e41b27", "char", null, null, null, 0, "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", null]]}');
INSERT INTO public.host_observation VALUES ('01a0e247-5d7a-77f5-aa98-a5f213f6ead0', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'manifest', 'dd43dc1526fd943c65db3bc28f57fbc44ac06dd57b5f9a64ebffa5f751c9e825', '01a0e247-5d32-7d21-a51c-21745cbe1882:dd43dc1526fd943c65db3bc28f57fbc44ac06dd57b5f9a64ebffa5f751c9e825:manifest', '2026-09-27 09:52:02.931625+00', '{"chat_id": "c035bf48-f66c-43ff-92c5-e02cb7394cdc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9", "2749272e633381bf70985044f4bb57b7296cdb20db01426740d5652381cfa483", "user", null, null, null, 0, null, null], ["81b82fa5-270b-4815-be8b-c41d5534bd74", "e8638cbdd39bd3ddfac3afa05010dff2faeab533ffe8aa1363f97e689e599c4d", "char", null, null, null, 0, "81b82fa5-270b-4815-be8b-c41d5534bd74", null], ["65c4532c-6887-4e52-895e-36cc95b2b837", "7d09ae9c696daf228032dd7362b2b672681f67786e33d42e6cf254aa2813c799", "user", null, null, null, 0, null, null], ["53d88061-a807-481d-85f6-aeefea0f28eb", "ead1b8cb623da4c751dd5fad9d4a8837cdf43a68c0bf463fe7e23b296e74ae09", "char", null, null, null, 0, "53d88061-a807-481d-85f6-aeefea0f28eb", null]], "base_manifest_hash": "87903964bfc137e43abc378fd022e641ce60819e3adadedebf54a64c8235063f"}');
INSERT INTO public.host_observation VALUES ('01a0e247-5da2-7f21-8b1d-ba987b5baee0', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'manifest', 'bc112b6aff321cd837d27404d6956351faf23a59200fee7cb781c151f255fdba', '01a0e247-5d32-7d21-a51c-21745cbe1882:bc112b6aff321cd837d27404d6956351faf23a59200fee7cb781c151f255fdba:manifest', '2026-09-27 09:52:02.972713+00', '{"chat_id": "c035bf48-f66c-43ff-92c5-e02cb7394cdc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "cda6d6576242431252169697e8032effc87e156b7fa87b02357f59c01fe0cf40", "user", null, null, null, 0, null, null], ["dfe052e2-bb71-4726-a021-0f93079eda4c", "e5c4bcc89a05faa3019bc04a56abb49b9a78c48eb13b17b0ad9314612e5c2f49", "char", null, null, null, 0, "dfe052e2-bb71-4726-a021-0f93079eda4c", null], ["fc83f16d-f3bd-4b01-abd7-0433dffef66f", "d29b5be63bc7579484460c9eec5e4cfb24a4029089303d21402a85d51625df89", "user", null, null, null, 0, null, null], ["2e64778d-8d11-4bdf-b978-214aa0a7a22d", "3cd4d4154155c00a9434f81704d2b7ffd56864d33235de1e65416f10ed6d0f49", "char", null, null, null, 0, "2e64778d-8d11-4bdf-b978-214aa0a7a22d", null]], "base_manifest_hash": "dd43dc1526fd943c65db3bc28f57fbc44ac06dd57b5f9a64ebffa5f751c9e825"}');
INSERT INTO public.host_observation VALUES ('01a0e247-5dca-7408-a44c-d54d5b236c4d', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'manifest', '19db502c39bd563416e20e12d04cf8975fb005212167c274f4793c8b014ab6e9', '01a0e247-5d32-7d21-a51c-21745cbe1882:19db502c39bd563416e20e12d04cf8975fb005212167c274f4793c8b014ab6e9:manifest', '2026-09-27 09:52:03.014504+00', '{"chat_id": "c035bf48-f66c-43ff-92c5-e02cb7394cdc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["d273fd74-9fa7-4a8c-9e79-d21b4dbafbac", "5cfa3a8f54951b7d6f1317e4e5f327379c7cb7cdd1e087a17fd87ee475121ae1", "user", null, null, null, 0, null, null]], "base_manifest_hash": "bc112b6aff321cd837d27404d6956351faf23a59200fee7cb781c151f255fdba"}');
INSERT INTO public.host_observation VALUES ('01a0e247-63d9-7a20-ba85-810788e7cd7e', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'manifest', 'a8ab24c00d894f9f8239b59e4a3678fa202b36e9a43612d6dc77c5cb9fb412c3', '01a0e247-5d32-7d21-a51c-21745cbe1882:a8ab24c00d894f9f8239b59e4a3678fa202b36e9a43612d6dc77c5cb9fb412c3:manifest', '2026-09-27 09:52:04.565183+00', '{"chat_id": "c035bf48-f66c-43ff-92c5-e02cb7394cdc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["359555fe-f91f-4a5c-938e-54c5267269d7", "6e670a4f782b434fe5eda19655ce3cd2a5b5aee9f00d0642d9b6bfb48f6fd614", "user", null, null, null, 0, null, null], ["bb57d506-013d-4829-ba99-4e7a1c640a4f", "9469d74f66d65e6249639ec49051a02cba1735dae1676caa85cc47de9228a07b", "char", null, null, null, 0, "bb57d506-013d-4829-ba99-4e7a1c640a4f", null], ["9d98eb62-7f5b-4587-807d-b8e73e49829b", "22203c487916f901977b6cd07f178176aef697e19b99adad4c00d526dce13990", "user", null, null, null, 0, null, null], ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "3815783b4fecde0bbc007e350ca73f068c8bdddd0ef0a5fb80cf0388540c33de", "char", null, null, null, 0, "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", null], ["e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9", "2749272e633381bf70985044f4bb57b7296cdb20db01426740d5652381cfa483", "user", null, null, null, 0, null, null], ["81b82fa5-270b-4815-be8b-c41d5534bd74", "e8638cbdd39bd3ddfac3afa05010dff2faeab533ffe8aa1363f97e689e599c4d", "char", null, null, null, 0, "81b82fa5-270b-4815-be8b-c41d5534bd74", null], ["65c4532c-6887-4e52-895e-36cc95b2b837", "7d09ae9c696daf228032dd7362b2b672681f67786e33d42e6cf254aa2813c799", "user", null, null, null, 0, null, null], ["53d88061-a807-481d-85f6-aeefea0f28eb", "ead1b8cb623da4c751dd5fad9d4a8837cdf43a68c0bf463fe7e23b296e74ae09", "char", null, null, null, 0, "53d88061-a807-481d-85f6-aeefea0f28eb", null], ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "cda6d6576242431252169697e8032effc87e156b7fa87b02357f59c01fe0cf40", "user", null, null, null, 0, null, null], ["dfe052e2-bb71-4726-a021-0f93079eda4c", "e5c4bcc89a05faa3019bc04a56abb49b9a78c48eb13b17b0ad9314612e5c2f49", "char", null, null, null, 0, "dfe052e2-bb71-4726-a021-0f93079eda4c", null], ["fc83f16d-f3bd-4b01-abd7-0433dffef66f", "d29b5be63bc7579484460c9eec5e4cfb24a4029089303d21402a85d51625df89", "user", null, null, null, 0, null, null], ["2e64778d-8d11-4bdf-b978-214aa0a7a22d", "3cd4d4154155c00a9434f81704d2b7ffd56864d33235de1e65416f10ed6d0f49", "char", null, null, null, 0, "2e64778d-8d11-4bdf-b978-214aa0a7a22d", null], ["d273fd74-9fa7-4a8c-9e79-d21b4dbafbac", "5cfa3a8f54951b7d6f1317e4e5f327379c7cb7cdd1e087a17fd87ee475121ae1", "user", null, null, null, 0, null, null], ["b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "b69709544c998fb99ef5be3c991bf2a31de615ad442d69bd94c0d0f5fd9488d1", "char", null, null, null, 0, "b7f77fdd-4177-43ee-8d92-051ffe89bfd1", null], ["28b91209-f6c3-49a1-81fc-70bcfc30e32e", "674f9a08c8991098af3f49b2c379521a8240d1a1ff33502b2453afbf36aa2ad8", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e247-6405-7e28-b523-e646f5c9f1cf', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'manifest', '4e92eafed729475600207aafd8eb15649b6ae44bc1ab9ba631ca0fca1332aa51', '01a0e247-5d32-7d21-a51c-21745cbe1882:4e92eafed729475600207aafd8eb15649b6ae44bc1ab9ba631ca0fca1332aa51:manifest', '2026-09-27 09:52:04.609686+00', '{"chat_id": "c035bf48-f66c-43ff-92c5-e02cb7394cdc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["7daa6d5c-44ab-420e-835a-dd07eb037746", "afedf7b04345543ae71d0313873887ff0722c7a98f8524a707e85596257900c3", "char", null, null, 1, 2, "7daa6d5c-44ab-420e-835a-dd07eb037746", null]], "base_manifest_hash": "a8ab24c00d894f9f8239b59e4a3678fa202b36e9a43612d6dc77c5cb9fb412c3"}');
INSERT INTO public.host_observation VALUES ('01a0e247-642c-77ed-9258-3744b2c02026', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'manifest', 'c86ecde851c307e98d7ced1f01c28f384cdb0682766bf758d2af356db3635dff', '01a0e247-5d32-7d21-a51c-21745cbe1882:c86ecde851c307e98d7ced1f01c28f384cdb0682766bf758d2af356db3635dff:manifest', '2026-09-27 09:52:04.648021+00', '{"chat_id": "c035bf48-f66c-43ff-92c5-e02cb7394cdc", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["359555fe-f91f-4a5c-938e-54c5267269d7", "6e670a4f782b434fe5eda19655ce3cd2a5b5aee9f00d0642d9b6bfb48f6fd614", "user", null, null, null, 0, null, null], ["bb57d506-013d-4829-ba99-4e7a1c640a4f", "9469d74f66d65e6249639ec49051a02cba1735dae1676caa85cc47de9228a07b", "char", null, null, null, 0, "bb57d506-013d-4829-ba99-4e7a1c640a4f", null], ["9d98eb62-7f5b-4587-807d-b8e73e49829b", "22203c487916f901977b6cd07f178176aef697e19b99adad4c00d526dce13990", "user", null, null, null, 0, null, null], ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "3815783b4fecde0bbc007e350ca73f068c8bdddd0ef0a5fb80cf0388540c33de", "char", null, null, null, 0, "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", null], ["e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9", "2749272e633381bf70985044f4bb57b7296cdb20db01426740d5652381cfa483", "user", null, null, null, 0, null, null], ["81b82fa5-270b-4815-be8b-c41d5534bd74", "e8638cbdd39bd3ddfac3afa05010dff2faeab533ffe8aa1363f97e689e599c4d", "char", null, null, null, 0, "81b82fa5-270b-4815-be8b-c41d5534bd74", null], ["65c4532c-6887-4e52-895e-36cc95b2b837", "7d09ae9c696daf228032dd7362b2b672681f67786e33d42e6cf254aa2813c799", "user", null, null, null, 0, null, null], ["53d88061-a807-481d-85f6-aeefea0f28eb", "ead1b8cb623da4c751dd5fad9d4a8837cdf43a68c0bf463fe7e23b296e74ae09", "char", null, null, null, 0, "53d88061-a807-481d-85f6-aeefea0f28eb", null], ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "28a80b4ae8fcca7aaba4759ecb322badaeb238b14c78c6ff94e348b4478cc72c", "user", true, null, null, 0, null, null], ["dfe052e2-bb71-4726-a021-0f93079eda4c", "e5c4bcc89a05faa3019bc04a56abb49b9a78c48eb13b17b0ad9314612e5c2f49", "char", null, null, null, 0, "dfe052e2-bb71-4726-a021-0f93079eda4c", null], ["fc83f16d-f3bd-4b01-abd7-0433dffef66f", "d29b5be63bc7579484460c9eec5e4cfb24a4029089303d21402a85d51625df89", "user", null, null, null, 0, null, null], ["2e64778d-8d11-4bdf-b978-214aa0a7a22d", "3cd4d4154155c00a9434f81704d2b7ffd56864d33235de1e65416f10ed6d0f49", "char", null, null, null, 0, "2e64778d-8d11-4bdf-b978-214aa0a7a22d", null], ["d273fd74-9fa7-4a8c-9e79-d21b4dbafbac", "5cfa3a8f54951b7d6f1317e4e5f327379c7cb7cdd1e087a17fd87ee475121ae1", "user", null, null, null, 0, null, null], ["b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "b69709544c998fb99ef5be3c991bf2a31de615ad442d69bd94c0d0f5fd9488d1", "char", null, null, null, 0, "b7f77fdd-4177-43ee-8d92-051ffe89bfd1", null], ["28b91209-f6c3-49a1-81fc-70bcfc30e32e", "674f9a08c8991098af3f49b2c379521a8240d1a1ff33502b2453afbf36aa2ad8", "user", null, null, null, 0, null, null], ["7daa6d5c-44ab-420e-835a-dd07eb037746", "34703d03e559602f38dcb038f80b1efd05c0fc165627b1d5e5bb1303ad4b1277", "char", null, null, 0, 2, "7daa6d5c-44ab-420e-835a-dd07eb037746", null], ["27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90", "cb976c5abceb76c96d58fa066028d912a7ee16b06d8de397542c15b23d5ade85", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e247-6a3e-77de-85e6-ccf4b9a4c24d', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', 'manifest', '14d036bccb1afbfd6a2f5754d4b7d8409ee9660cd4ada6c51f204faadda9dcdf', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9:14d036bccb1afbfd6a2f5754d4b7d8409ee9660cd4ada6c51f204faadda9dcdf:manifest', '2026-09-27 09:52:06.199548+00', '{"chat_id": "6dabb2fa-b3d1-44c6-8fee-08309bb64ac2", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["3ae772fc-dd31-4638-8440-210aa2f04e9d", "a1c11c03717e3fa1b5c745fdf79d3880fb251327a7c186f54a5e2e025f2e0837", "user", null, null, null, 0, null, null], ["392a9def-cbd3-4628-a85e-47174575dcb9", "7aba12c150ab94e963017e0ac13fa10cb0bbf2cac695a4835a8210d0ac799550", "char", null, null, null, 0, "bb57d506-013d-4829-ba99-4e7a1c640a4f", null], ["14874b3d-04a4-4de0-a685-fd1cff501cc0", "61368663da9f8719dede77f6673d39c5bfdd5e835af434e6a22506bdd0261b66", "user", null, null, null, 0, null, null], ["b1116625-e6e1-46f1-ab55-8dc28e520d3d", "f6aeb6373692b0b972c412a3ac2f41bf297661e9c86623a010c3278a20192ebf", "char", null, null, null, 0, "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", null], ["33302beb-0f03-49c2-91b8-f55addfa5def", "65cb91dd6509bb6e1d67d346a7ee95d92f8e5173ad8e9af4aa3e7cb6065a1b10", "user", null, null, null, 0, null, null], ["cce4830b-0f60-436d-8b77-680683becb0a", "6bfb50fdb7a0732dea8518e3cf2543b12c907b1669d159badb284fc1d9bfc2fc", "char", null, null, null, 0, "81b82fa5-270b-4815-be8b-c41d5534bd74", null], ["dd7ac5fc-ced8-40fb-ac0a-f0080ab3dcbb", "6248441a3378aaee004b65b5b9a70d842a0c56be9285b05cd2c83049f3da1f23", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::c035bf48-f66c-43ff-92c5-e02cb7394cdc::Harbor route::81b82fa5-270b-4815-be8b-c41d5534bd74::}}"]], ["2a54ce34-aec8-46cc-a2dd-131074896fc9", "24a1c23ab38ce8ff0717092170424a1141738b32d5d427d457c6fcbed70cda46", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0e247-5dc7-7a19-8b70-51c0d09069e3:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5dc7-7a19-8b70-51c0d09069e3"}', 50, 'done', 1, '2026-09-27 09:52:03.014504+00', NULL, NULL, '2026-09-27 09:52:03.014504+00', '2026-09-27 09:52:04.085163+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0e247-5d9f-7cb3-8c8c-3f129863dad2:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d9f-7cb3-8c8c-3f129863dad2"}', 50, 'done', 1, '2026-09-27 09:52:03.014504+00', NULL, NULL, '2026-09-27 09:52:03.014504+00', '2026-09-27 09:52:04.106362+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0e247-5d9f-7246-b37c-3bea9e4c1a58:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d9f-7246-b37c-3bea9e4c1a58"}', 50, 'done', 1, '2026-09-27 09:52:02.972713+00', NULL, NULL, '2026-09-27 09:52:02.972713+00', '2026-09-27 09:52:04.127324+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0e247-5d9e-7df8-8f8a-a997df016385:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d9e-7df8-8f8a-a997df016385"}', 50, 'done', 1, '2026-09-27 09:52:02.972713+00', NULL, NULL, '2026-09-27 09:52:02.972713+00', '2026-09-27 09:52:04.149734+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0e247-5d9d-70ba-b274-9c4f31e89259:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d9d-70ba-b274-9c4f31e89259"}', 50, 'done', 1, '2026-09-27 09:52:02.972713+00', NULL, NULL, '2026-09-27 09:52:02.972713+00', '2026-09-27 09:52:04.169354+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0e247-5d77-7f77-9e5f-0eb915f083df:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d77-7f77-9e5f-0eb915f083df"}', 50, 'done', 1, '2026-09-27 09:52:02.972713+00', NULL, NULL, '2026-09-27 09:52:02.972713+00', '2026-09-27 09:52:04.189001+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0e247-5d76-7621-a497-f1ed97bf11f7:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d76-7621-a497-f1ed97bf11f7"}', 50, 'done', 1, '2026-09-27 09:52:02.931625+00', NULL, NULL, '2026-09-27 09:52:02.931625+00', '2026-09-27 09:52:04.208262+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0e247-5d75-7314-ba2a-35bbe3b8321c:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d75-7314-ba2a-35bbe3b8321c"}', 50, 'done', 1, '2026-09-27 09:52:02.931625+00', NULL, NULL, '2026-09-27 09:52:02.931625+00', '2026-09-27 09:52:04.229164+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0e247-5d74-74c0-8750-ab7692c72128:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d74-74c0-8750-ab7692c72128"}', 50, 'done', 1, '2026-09-27 09:52:02.931625+00', NULL, NULL, '2026-09-27 09:52:02.931625+00', '2026-09-27 09:52:04.249868+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0e247-5d3e-775c-b0f2-538e91387729:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d3e-775c-b0f2-538e91387729"}', 50, 'done', 1, '2026-09-27 09:52:02.931625+00', NULL, NULL, '2026-09-27 09:52:02.931625+00', '2026-09-27 09:52:04.273414+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0e247-5d9f-7cb3-8c8c-3f129863dad2:7bf0bc4855a6f78eb0fff2ba241cfbd7:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d9f-7cb3-8c8c-3f129863dad2", "window_hash": "7bf0bc4855a6f78eb0fff2ba241cfbd7"}', 100, 'done', 1, '2026-09-27 09:52:03.014504+00', NULL, NULL, '2026-09-27 09:52:03.014504+00', '2026-09-27 09:52:04.29833+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0e247-5d9e-7df8-8f8a-a997df016385:f826d6a78781c22e9c01d56665c5bd69:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d9e-7df8-8f8a-a997df016385", "window_hash": "f826d6a78781c22e9c01d56665c5bd69"}', 100, 'done', 1, '2026-09-27 09:52:02.972713+00', NULL, NULL, '2026-09-27 09:52:02.972713+00', '2026-09-27 09:52:04.321834+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0e247-5d77-7f77-9e5f-0eb915f083df:cc66f00348e887007565a2efbb39680d:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d77-7f77-9e5f-0eb915f083df", "window_hash": "cc66f00348e887007565a2efbb39680d"}', 100, 'done', 1, '2026-09-27 09:52:02.972713+00', NULL, NULL, '2026-09-27 09:52:02.972713+00', '2026-09-27 09:52:04.3439+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0e247-5d75-7314-ba2a-35bbe3b8321c:5c5da6bb1ac46bd7a8e6173632ea3597:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d75-7314-ba2a-35bbe3b8321c", "window_hash": "5c5da6bb1ac46bd7a8e6173632ea3597"}', 100, 'done', 1, '2026-09-27 09:52:02.931625+00', NULL, NULL, '2026-09-27 09:52:02.931625+00', '2026-09-27 09:52:04.366808+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0e247-5d3e-775c-b0f2-538e91387729:d782ea2bba133009c296ab4d6c94ab40:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d3e-775c-b0f2-538e91387729", "window_hash": "d782ea2bba133009c296ab4d6c94ab40"}', 100, 'done', 1, '2026-09-27 09:52:02.931625+00', NULL, NULL, '2026-09-27 09:52:02.931625+00', '2026-09-27 09:52:04.392251+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0e247-5d3d-7c4f-a4f0-fec41c6c8504:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d3d-7c4f-a4f0-fec41c6c8504"}', 150, 'done', 1, '2026-09-27 09:52:02.873335+00', NULL, NULL, '2026-09-27 09:52:02.873335+00', '2026-09-27 09:52:04.411459+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c"}', 150, 'done', 1, '2026-09-27 09:52:02.873335+00', NULL, NULL, '2026-09-27 09:52:02.873335+00', '2026-09-27 09:52:04.428986+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0e247-5d3a-7ad2-bbe9-911660be0cad:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-5d3a-7ad2-bbe9-911660be0cad"}', 150, 'done', 1, '2026-09-27 09:52:02.873335+00', NULL, NULL, '2026-09-27 09:52:02.873335+00', '2026-09-27 09:52:04.449107+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c:a15b63019cacbcb813aa95b376d8a895:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c", "window_hash": "a15b63019cacbcb813aa95b376d8a895"}', 200, 'done', 1, '2026-09-27 09:52:02.873335+00', NULL, NULL, '2026-09-27 09:52:02.873335+00', '2026-09-27 09:52:04.475711+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0e247-5d75-7314-ba2a-35bbe3b8321c:e99f93650f14e8855931dad2c6ff85e8:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d75-7314-ba2a-35bbe3b8321c", "window_hash": "e99f93650f14e8855931dad2c6ff85e8"}', 100, 'done', 1, '2026-09-27 09:52:04.565183+00', NULL, NULL, '2026-09-27 09:52:04.565183+00', '2026-09-27 09:52:05.72366+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0e247-63d6-75e0-934e-7e0c38c02e8f:c9439a40045c6a18880b6cade149d82d:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-63d6-75e0-934e-7e0c38c02e8f", "window_hash": "c9439a40045c6a18880b6cade149d82d"}', 100, 'done', 1, '2026-09-27 09:52:04.565183+00', NULL, NULL, '2026-09-27 09:52:04.565183+00', '2026-09-27 09:52:05.744865+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0e247-6a3b-775c-950a-6186256af0b9:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-6a3b-775c-950a-6186256af0b9"}', 150, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.80486+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0e247-642a-7c17-9fa3-5b2ad5473dff:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-642a-7c17-9fa3-5b2ad5473dff"}', 50, 'done', 1, '2026-09-27 09:52:04.648021+00', NULL, NULL, '2026-09-27 09:52:04.648021+00', '2026-09-27 09:52:05.503244+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0e247-6429-7c8a-8a92-9a5eb802a4a8:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-6429-7c8a-8a92-9a5eb802a4a8"}', 50, 'done', 1, '2026-09-27 09:52:04.648021+00', NULL, NULL, '2026-09-27 09:52:04.648021+00', '2026-09-27 09:52:05.522154+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0e247-63d7-7e55-b134-655e194ed510:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-63d7-7e55-b134-655e194ed510"}', 50, 'done', 1, '2026-09-27 09:52:04.565183+00', NULL, NULL, '2026-09-27 09:52:04.565183+00', '2026-09-27 09:52:05.54113+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0e247-63d6-7050-9984-c84df00d8a96:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-63d6-7050-9984-c84df00d8a96"}', 50, 'done', 1, '2026-09-27 09:52:04.565183+00', NULL, NULL, '2026-09-27 09:52:04.565183+00', '2026-09-27 09:52:05.561654+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0e247-63d6-75e0-934e-7e0c38c02e8f:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-63d6-75e0-934e-7e0c38c02e8f"}', 50, 'done', 1, '2026-09-27 09:52:04.565183+00', NULL, NULL, '2026-09-27 09:52:04.565183+00', '2026-09-27 09:52:05.583264+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0e247-6429-7c8a-8a92-9a5eb802a4a8:0a79f89d61c8e3627d28d2c7aeafe1ec:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-6429-7c8a-8a92-9a5eb802a4a8", "window_hash": "0a79f89d61c8e3627d28d2c7aeafe1ec"}', 100, 'done', 1, '2026-09-27 09:52:04.648021+00', NULL, NULL, '2026-09-27 09:52:04.648021+00', '2026-09-27 09:52:05.620518+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0e247-63d6-7050-9984-c84df00d8a96:e55b46e4a142869f84a2c9c877dfb64c:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-63d6-7050-9984-c84df00d8a96", "window_hash": "e55b46e4a142869f84a2c9c877dfb64c"}', 100, 'done', 1, '2026-09-27 09:52:04.648021+00', NULL, NULL, '2026-09-27 09:52:04.648021+00', '2026-09-27 09:52:05.641932+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0e247-5d9f-7cb3-8c8c-3f129863dad2:c72101b01a766edc77e2ee7d0c1fef63:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d9f-7cb3-8c8c-3f129863dad2", "window_hash": "c72101b01a766edc77e2ee7d0c1fef63"}', 100, 'done', 1, '2026-09-27 09:52:04.648021+00', NULL, NULL, '2026-09-27 09:52:04.648021+00', '2026-09-27 09:52:05.665104+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0e247-5d9e-7df8-8f8a-a997df016385:081d8edfedb133db63004b0d3d2823a0:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d9e-7df8-8f8a-a997df016385", "window_hash": "081d8edfedb133db63004b0d3d2823a0"}', 100, 'done', 1, '2026-09-27 09:52:04.648021+00', NULL, NULL, '2026-09-27 09:52:04.648021+00', '2026-09-27 09:52:05.688413+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0e247-63d6-7050-9984-c84df00d8a96:6db5550cb67e893049eed1f86ef55568:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-63d6-7050-9984-c84df00d8a96", "window_hash": "6db5550cb67e893049eed1f86ef55568"}', 100, 'obsolete', 1, '2026-09-27 09:52:04.565183+00', NULL, NULL, '2026-09-27 09:52:04.565183+00', '2026-09-27 09:52:05.692299+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0e247-5d9e-7df8-8f8a-a997df016385:bfd47b8a78f197bd80703fc2da714d3a:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d9e-7df8-8f8a-a997df016385", "window_hash": "bfd47b8a78f197bd80703fc2da714d3a"}', 100, 'obsolete', 1, '2026-09-27 09:52:04.565183+00', NULL, NULL, '2026-09-27 09:52:04.565183+00', '2026-09-27 09:52:05.696072+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0e247-5d77-7f77-9e5f-0eb915f083df:c8242c16eccde85c44e32b15e82f2af6:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-5d32-7d21-a51c-21745cbe1882', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-5d77-7f77-9e5f-0eb915f083df", "window_hash": "c8242c16eccde85c44e32b15e82f2af6"}', 100, 'obsolete', 1, '2026-09-27 09:52:04.565183+00', NULL, NULL, '2026-09-27 09:52:04.565183+00', '2026-09-27 09:52:05.699637+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0e247-6a3b-73c9-b1f0-46dd096ffc36:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-6a3b-73c9-b1f0-46dd096ffc36"}', 150, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.785611+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0e247-6a3a-7834-986d-cbb5ad5064d0:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-6a3a-7834-986d-cbb5ad5064d0"}', 150, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.82896+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0e247-6a39-7395-b6ce-1f53ee8de76e:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-6a39-7395-b6ce-1f53ee8de76e"}', 150, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.848143+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0e247-6a39-7d33-a7be-f49e0319cac1:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-6a39-7d33-a7be-f49e0319cac1"}', 150, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.867664+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0e247-6a38-77e8-bfbb-15debe73231f:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-6a38-77e8-bfbb-15debe73231f"}', 150, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.886731+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0e247-6a3b-73c9-b1f0-46dd096ffc36:ceab0800aa4a37aac3b6597c785999d1:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-6a3b-73c9-b1f0-46dd096ffc36", "window_hash": "ceab0800aa4a37aac3b6597c785999d1"}', 200, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.908755+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0e247-6a3a-7834-986d-cbb5ad5064d0:58d820986f23f19869cf9ff16b725c4d:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-6a3a-7834-986d-cbb5ad5064d0", "window_hash": "58d820986f23f19869cf9ff16b725c4d"}', 200, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.932378+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0e247-6a39-7d33-a7be-f49e0319cac1:5ca4d2496e37dbc65ec511b26c67d923:extract-2e80051e1522b167ee4f25b90c1f4f5a', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "extract-2e80051e1522b167ee4f25b90c1f4f5a", "revision_id": "01a0e247-6a39-7d33-a7be-f49e0319cac1", "window_hash": "5ca4d2496e37dbc65ec511b26c67d923"}', 200, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.954242+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0e247-6a3d-731f-81d2-18cb9553804d:embed-8bb522ed4abfb88b7b2a95dd30178daf', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{"generation": "embed-8bb522ed4abfb88b7b2a95dd30178daf", "revision_id": "01a0e247-6a3d-731f-81d2-18cb9553804d"}', 150, 'done', 1, '2026-09-27 09:52:06.199548+00', NULL, NULL, '2026-09-27 09:52:06.199548+00', '2026-09-27 09:52:06.766227+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0e247-5d3f-7375-afe5-6f582e7b45fb', '01a0e247-5d32-7d21-a51c-21745cbe1882');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-2e80051e1522b167ee4f25b90c1f4f5a', 'extract', 'stub', 'http://127.0.0.1:33655/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "905fe0abfc193a9d", "compiler": "extract-v10", "endpoint": "http://127.0.0.1:33655/v1", "json_mode": true, "normalizer": "clean-v2", "predicates": "4e6ac6c47a6da74e", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-27 09:52:02.827389+00', '2026-09-27 09:52:02.829021+00');
INSERT INTO public.projection_generation VALUES ('embed-8bb522ed4abfb88b7b2a95dd30178daf', 'embed', 'stub-embed', 'http://127.0.0.1:33655/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:33655/v1", "max_chunks": 8, "normalizer": "clean-v2", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-27 09:52:02.827389+00', '2026-09-27 09:52:02.832618+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0e247-5d69-7f21-868c-669621079c50', '01a0e247-5d32-7d21-a51c-21745cbe1882', '01a0e247-5d40-76e8-8193-37612b02c66d', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e247-5d3d-7c4f-a4f0-fec41c6c8504", "host_logical_id": "9d98eb62-7f5b-4587-807d-b8e73e49829b"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e247-5d3d-7c4f-a4f0-fec41c6c8504", "host_logical_id": "9d98eb62-7f5b-4587-807d-b8e73e49829b"}]', 0, '{"embed": 25.58, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 0}, "vector": 2.02, "lexical": 3.85, "threads": 0, "extractor": "extract-2e80051e1522", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 34.23, "embedding_projection": "embed-8bb522ed4abfb8"}', 'fresh', '2026-09-27 09:52:02.88721+00', 'packet-v1', 600, 3, '', '["359555fe-f91f-4a5c-938e-54c5267269d7", "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "9d98eb62-7f5b-4587-807d-b8e73e49829b", "bb57d506-013d-4829-ba99-4e7a1c640a4f"]', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e247-5d94-7849-8b95-6fa59338cc73', '01a0e247-5d32-7d21-a51c-21745cbe1882', '01a0e247-5d40-76e8-8193-37612b02c66d', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e247-5d76-7621-a497-f1ed97bf11f7", "host_logical_id": "65c4532c-6887-4e52-895e-36cc95b2b837"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e247-5d76-7621-a497-f1ed97bf11f7", "host_logical_id": "65c4532c-6887-4e52-895e-36cc95b2b837"}]', 0, '{"embed": 15.75, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 0}, "vector": 0.98, "lexical": 2.54, "threads": 0, "extractor": "extract-2e80051e1522", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.89, "embedding_projection": "embed-8bb522ed4abfb8"}', 'fresh', '2026-09-27 09:52:02.943513+00', 'packet-v1', 600, 7, '', '["53d88061-a807-481d-85f6-aeefea0f28eb", "65c4532c-6887-4e52-895e-36cc95b2b837", "81b82fa5-270b-4815-be8b-c41d5534bd74", "e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9"]', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e247-5dbc-7fb0-8a25-f03ba8a97112', '01a0e247-5d32-7d21-a51c-21745cbe1882', '01a0e247-5d40-76e8-8193-37612b02c66d', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e247-5d9f-7246-b37c-3bea9e4c1a58", "host_logical_id": "fc83f16d-f3bd-4b01-abd7-0433dffef66f"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e247-5d9f-7246-b37c-3bea9e4c1a58", "host_logical_id": "fc83f16d-f3bd-4b01-abd7-0433dffef66f"}]', 0, '{"embed": 15.89, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 0}, "vector": 0.93, "lexical": 2.34, "threads": 0, "extractor": "extract-2e80051e1522", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.7, "embedding_projection": "embed-8bb522ed4abfb8"}', 'fresh', '2026-09-27 09:52:02.984024+00', 'packet-v1', 600, 11, '', '["2e64778d-8d11-4bdf-b978-214aa0a7a22d", "8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "dfe052e2-bb71-4726-a021-0f93079eda4c", "fc83f16d-f3bd-4b01-abd7-0433dffef66f"]', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e247-5de4-7b77-b7b6-4107b82f0dc7', '01a0e247-5d32-7d21-a51c-21745cbe1882', '01a0e247-5d40-76e8-8193-37612b02c66d', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e247-5dc7-7a19-8b70-51c0d09069e3", "host_logical_id": "d273fd74-9fa7-4a8c-9e79-d21b4dbafbac"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0e247-5d3e-775c-b0f2-538e91387729", "host_logical_id": "6beac9f6-32fa-4fd1-9882-c0fc42421bc3"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c", "host_logical_id": "bb57d506-013d-4829-ba99-4e7a1c640a4f"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e247-5d3e-775c-b0f2-538e91387729"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e247-5dc7-7a19-8b70-51c0d09069e3", "host_logical_id": "d273fd74-9fa7-4a8c-9e79-d21b4dbafbac"}]', 174, '{"embed": 15.21, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 2}, "vector": 0.72, "lexical": 2.88, "threads": 0, "extractor": "extract-2e80051e1522", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.59, "embedding_projection": "embed-8bb522ed4abfb8"}', 'fresh', '2026-09-27 09:52:03.023713+00', 'packet-v1', 600, 12, '', '["2e64778d-8d11-4bdf-b978-214aa0a7a22d", "d273fd74-9fa7-4a8c-9e79-d21b4dbafbac", "dfe052e2-bb71-4726-a021-0f93079eda4c", "fc83f16d-f3bd-4b01-abd7-0433dffef66f"]', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e247-5d3e-775c-b0f2-538e91387729"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 3, "placed": true}, {"ref": {"revision": "01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e247-63f7-7320-9411-6d6c82865d32', '01a0e247-5d32-7d21-a51c-21745cbe1882', '01a0e247-63da-7f06-b7c4-f6934f4d2214', 'And the compass?', '[{"rrf": 0.03151, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0e247-5d9e-7df8-8f8a-a997df016385", "host_logical_id": "dfe052e2-bb71-4726-a021-0f93079eda4c"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e247-63d7-7e55-b134-655e194ed510", "host_logical_id": "28b91209-f6c3-49a1-81fc-70bcfc30e32e"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c", "host_logical_id": "bb57d506-013d-4829-ba99-4e7a1c640a4f"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0e247-5d3a-7ad2-bbe9-911660be0cad", "host_logical_id": "359555fe-f91f-4a5c-938e-54c5267269d7"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0e247-5d77-7f77-9e5f-0eb915f083df", "host_logical_id": "53d88061-a807-481d-85f6-aeefea0f28eb"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0e247-5d3a-7ad2-bbe9-911660be0cad"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0e247-5d77-7f77-9e5f-0eb915f083df"}, {"turn": 9, "score": 0.03151, "revision_id": "01a0e247-5d9e-7df8-8f8a-a997df016385"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e247-63d7-7e55-b134-655e194ed510", "host_logical_id": "28b91209-f6c3-49a1-81fc-70bcfc30e32e"}]', 223, '{"embed": 16.66, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 4}, "vector": 1.0, "lexical": 2.25, "threads": 0, "extractor": "extract-2e80051e1522", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 22.31, "embedding_projection": "embed-8bb522ed4abfb8"}', 'fresh', '2026-09-27 09:52:04.577118+00', 'packet-v1', 600, 14, '', '["28b91209-f6c3-49a1-81fc-70bcfc30e32e", "2e64778d-8d11-4bdf-b978-214aa0a7a22d", "b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "d273fd74-9fa7-4a8c-9e79-d21b4dbafbac"]', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e247-5d9e-7df8-8f8a-a997df016385"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}, {"ref": {"revision": "01a0e247-5d3a-7ad2-bbe9-911660be0cad"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a0e247-5d77-7f77-9e5f-0eb915f083df"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 7, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e247-641e-798f-99ea-c895c23bc9e3', '01a0e247-5d32-7d21-a51c-21745cbe1882', '01a0e247-63da-7f06-b7c4-f6934f4d2214', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0e247-5d9e-7df8-8f8a-a997df016385", "host_logical_id": "dfe052e2-bb71-4726-a021-0f93079eda4c"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e247-63d7-7e55-b134-655e194ed510", "host_logical_id": "28b91209-f6c3-49a1-81fc-70bcfc30e32e"}, {"rrf": 0.01639, "sim": 0.5799, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0e247-5d75-7314-ba2a-35bbe3b8321c", "host_logical_id": "81b82fa5-270b-4815-be8b-c41d5534bd74"}, {"rrf": 0.01613, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0e247-5d9f-7cb3-8c8c-3f129863dad2", "host_logical_id": "2e64778d-8d11-4bdf-b978-214aa0a7a22d"}]', '[{"turn": 5, "score": 0.01639, "revision_id": "01a0e247-5d75-7314-ba2a-35bbe3b8321c"}, {"turn": 9, "score": 0.03002, "revision_id": "01a0e247-5d9e-7df8-8f8a-a997df016385"}, {"turn": 11, "score": 0.01613, "revision_id": "01a0e247-5d9f-7cb3-8c8c-3f129863dad2"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e247-63d7-7e55-b134-655e194ed510", "host_logical_id": "28b91209-f6c3-49a1-81fc-70bcfc30e32e"}]', 200, '{"embed": 14.95, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 3}, "vector": 1.13, "lexical": 3.18, "threads": 0, "extractor": "extract-2e80051e1522", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 21.63, "embedding_projection": "embed-8bb522ed4abfb8"}', 'fresh', '2026-09-27 09:52:04.616813+00', 'packet-v1', 600, 15, '', '["28b91209-f6c3-49a1-81fc-70bcfc30e32e", "7daa6d5c-44ab-420e-835a-dd07eb037746", "b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "d273fd74-9fa7-4a8c-9e79-d21b4dbafbac"]', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e247-5d9e-7df8-8f8a-a997df016385"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e247-5d75-7314-ba2a-35bbe3b8321c"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Yuuma to return before the bell rings.", "turn": 5, "placed": true}, {"ref": {"revision": "01a0e247-5d9f-7cb3-8c8c-3f129863dad2"}, "tok": 24, "why": "placed", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 11, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e247-6447-760a-8a58-17a9c5ecb8b5', '01a0e247-5d32-7d21-a51c-21745cbe1882', '01a0e247-642d-7236-a94f-350ff70ef05b', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0e247-5d76-7621-a497-f1ed97bf11f7", "host_logical_id": "65c4532c-6887-4e52-895e-36cc95b2b837"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e247-642a-7c17-9fa3-5b2ad5473dff", "host_logical_id": "27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0e247-5d76-7621-a497-f1ed97bf11f7"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e247-642a-7c17-9fa3-5b2ad5473dff", "host_logical_id": "27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90"}]', 138, '{"embed": 15.64, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 1}, "vector": 0.81, "lexical": 2.59, "threads": 0, "extractor": "extract-2e80051e1522", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.83, "embedding_projection": "embed-8bb522ed4abfb8"}', 'fresh', '2026-09-27 09:52:04.658787+00', 'packet-v1', 600, 16, '', '["27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90", "28b91209-f6c3-49a1-81fc-70bcfc30e32e", "7daa6d5c-44ab-420e-835a-dd07eb037746", "b7f77fdd-4177-43ee-8d92-051ffe89bfd1"]', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e247-5d76-7621-a497-f1ed97bf11f7"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 6, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e247-6a58-763d-9c66-d037e065f6ee', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '01a0e247-6a3f-7186-a921-05ec6e3014b2', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0e247-6a39-7395-b6ce-1f53ee8de76e", "host_logical_id": "14874b3d-04a4-4de0-a685-fd1cff501cc0"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0e247-6a3a-7834-986d-cbb5ad5064d0", "host_logical_id": "b1116625-e6e1-46f1-ab55-8dc28e520d3d"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0e247-6a39-7395-b6ce-1f53ee8de76e"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e247-6a3a-7834-986d-cbb5ad5064d0"}]', '[]', 164, '{"embed": 14.82, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "thread": 0, "excerpt": 2}, "vector": 0.69, "lexical": 2.4, "threads": 0, "extractor": "extract-2e80051e1522", "kept_facts": 0, "kept_state": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.41, "embedding_projection": "embed-8bb522ed4abfb8"}', 'fresh', '2026-09-27 09:52:06.212948+00', 'packet-v1', 600, 7, '', '["2a54ce34-aec8-46cc-a2dd-131074896fc9", "33302beb-0f03-49c2-91b8-f55addfa5def", "cce4830b-0f60-436d-8b77-680683becb0a", "dd7ac5fc-ced8-40fb-ac0a-f0080ab3dcbb"]', 'extract-2e80051e1522b167ee4f25b90c1f4f5a', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', 'none', '{"top_k": 5, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e247-6a39-7395-b6ce-1f53ee8de76e"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 2, "placed": true}, {"ref": {"revision": "01a0e247-6a3a-7834-986d-cbb5ad5064d0"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 3, "placed": true}]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0e247-5dc7-7a19-8b70-51c0d09069e3', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.082516+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d9f-7cb3-8c8c-3f129863dad2', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.104795+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d9f-7246-b37c-3bea9e4c1a58', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.12585+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d9e-7df8-8f8a-a997df016385', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.148216+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d9d-70ba-b274-9c4f31e89259', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.167797+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d77-7f77-9e5f-0eb915f083df', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.187426+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d76-7621-a497-f1ed97bf11f7', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.206846+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d75-7314-ba2a-35bbe3b8321c', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.227782+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d74-74c0-8750-ab7692c72128', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.24843+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d3e-775c-b0f2-538e91387729', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.271912+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d3d-7c4f-a4f0-fec41c6c8504', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.409949+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.427669+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-5d3a-7ad2-bbe9-911660be0cad', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:04.447738+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-642a-7c17-9fa3-5b2ad5473dff', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:05.50182+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-6429-7c8a-8a92-9a5eb802a4a8', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:05.520668+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-63d7-7e55-b134-655e194ed510', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:05.539681+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-63d6-7050-9984-c84df00d8a96', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:05.560189+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-63d6-75e0-934e-7e0c38c02e8f', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:05.578886+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-6a3d-731f-81d2-18cb9553804d', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:06.764769+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-6a3b-73c9-b1f0-46dd096ffc36', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:06.784206+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-6a3b-775c-950a-6186256af0b9', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:06.803483+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-6a3a-7834-986d-cbb5ad5064d0', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:06.827614+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-6a39-7395-b6ce-1f53ee8de76e', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:06.846772+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-6a39-7d33-a7be-f49e0319cac1', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:06.866195+00');
INSERT INTO public.revision_embedding VALUES ('01a0e247-6a38-77e8-bfbb-15debe73231f', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-8bb522ed4abfb88b7b2a95dd30178daf', '2026-09-27 09:52:06.885352+00');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0e247-5d3a-7ad2-bbe9-911660be0cad', 'clean-v2', 'We should rest somewhere safe.', 30, 30, '2026-09-27 09:52:02.873335+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c', 'clean-v2', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-27 09:52:02.873335+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d3d-7c4f-a4f0-fec41c6c8504', 'clean-v2', 'Is Rin with you?', 16, 16, '2026-09-27 09:52:02.873335+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d3e-775c-b0f2-538e91387729', 'clean-v2', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-27 09:52:02.873335+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d74-74c0-8750-ab7692c72128', 'clean-v2', 'What did Mina say before she left?', 34, 34, '2026-09-27 09:52:02.931625+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d75-7314-ba2a-35bbe3b8321c', 'clean-v2', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-27 09:52:02.931625+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d76-7621-a497-f1ed97bf11f7', 'clean-v2', 'Let''s check the market.', 23, 23, '2026-09-27 09:52:02.931625+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d77-7f77-9e5f-0eb915f083df', 'clean-v2', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-27 09:52:02.931625+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d9d-70ba-b274-9c4f31e89259', 'clean-v2', 'Any news from the harbor?', 25, 25, '2026-09-27 09:52:02.972713+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d9e-7df8-8f8a-a997df016385', 'clean-v2', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-27 09:52:02.972713+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d9f-7246-b37c-3bea9e4c1a58', 'clean-v2', 'Where do we meet tonight?', 25, 25, '2026-09-27 09:52:02.972713+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5d9f-7cb3-8c8c-3f129863dad2', 'clean-v2', 'Mina moved to the bell tower.', 29, 29, '2026-09-27 09:52:02.972713+00');
INSERT INTO public.revision_text VALUES ('01a0e247-5dc7-7a19-8b70-51c0d09069e3', 'clean-v2', 'Where is Mina now?', 18, 18, '2026-09-27 09:52:03.014504+00');
INSERT INTO public.revision_text VALUES ('01a0e247-63d6-75e0-934e-7e0c38c02e8f', 'clean-v2', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-27 09:52:04.565183+00');
INSERT INTO public.revision_text VALUES ('01a0e247-63d6-7050-9984-c84df00d8a96', 'clean-v2', 'Mina keeps the brass key close.', 31, 31, '2026-09-27 09:52:04.565183+00');
INSERT INTO public.revision_text VALUES ('01a0e247-63d7-7e55-b134-655e194ed510', 'clean-v2', 'And the compass?', 16, 16, '2026-09-27 09:52:04.565183+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6402-758e-8d4a-076feee5a050', 'clean-v2', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-27 09:52:04.609686+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6428-76be-a890-8cd0180a66ab', 'clean-v2', 'Any news from the harbor?', 25, 25, '2026-09-27 09:52:04.648021+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6429-7c8a-8a92-9a5eb802a4a8', 'clean-v2', 'Rin has the silver compass.', 27, 27, '2026-09-27 09:52:04.648021+00');
INSERT INTO public.revision_text VALUES ('01a0e247-642a-7c17-9fa3-5b2ad5473dff', 'clean-v2', 'Let''s go.', 9, 9, '2026-09-27 09:52:04.648021+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6a38-77e8-bfbb-15debe73231f', 'clean-v2', 'We should rest somewhere safe.', 30, 30, '2026-09-27 09:52:06.199548+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6a39-7d33-a7be-f49e0319cac1', 'clean-v2', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-27 09:52:06.199548+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6a39-7395-b6ce-1f53ee8de76e', 'clean-v2', 'Is Rin with you?', 16, 16, '2026-09-27 09:52:06.199548+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6a3a-7834-986d-cbb5ad5064d0', 'clean-v2', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-27 09:52:06.199548+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6a3b-775c-950a-6186256af0b9', 'clean-v2', 'What did Mina say before she left?', 34, 34, '2026-09-27 09:52:06.199548+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6a3b-73c9-b1f0-46dd096ffc36', 'clean-v2', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-27 09:52:06.199548+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6a3c-752a-95e9-b43697f66c63', 'clean-v2', '{{specialcomment::branchedfrom::c035bf48-f66c-43ff-92c5-e02cb7394cdc::Harbor route::81b82fa5-270b-4815-be8b-c41d5534bd74::}}', 124, 124, '2026-09-27 09:52:06.199548+00');
INSERT INTO public.revision_text VALUES ('01a0e247-6a3d-731f-81d2-18cb9553804d', 'clean-v2', 'Rin moved to the market.', 24, 24, '2026-09-27 09:52:06.199548+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-27 09:52:01.93298+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-27 09:52:02.014952+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-27 09:52:02.03195+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-27 09:52:02.074519+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-27 09:52:02.095023+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-27 09:52:02.104122+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-27 09:52:02.106172+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-27 09:52:02.116354+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-27 09:52:02.133443+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-27 09:52:02.135625+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-27 09:52:02.137375+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-27 09:52:02.14632+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-27 09:52:02.174939+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-27 09:52:02.191569+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-27 09:52:02.193794+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-27 09:52:02.206659+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-27 09:52:02.208388+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-27 09:52:02.21024+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-09-27 09:52:02.211736+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-09-27 09:52:02.224657+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0e247-5d39-78fa-ac2c-29dea28c3adc', '01a0e247-5d32-7d21-a51c-21745cbe1882', '359555fe-f91f-4a5c-938e-54c5267269d7', 'message', '2026-09-27 09:52:02.873335+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d3c-7755-85aa-18e359ddc27d', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'bb57d506-013d-4829-ba99-4e7a1c640a4f', 'message', '2026-09-27 09:52:02.873335+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d3d-73b3-9846-67446bdba290', '01a0e247-5d32-7d21-a51c-21745cbe1882', '9d98eb62-7f5b-4587-807d-b8e73e49829b', 'message', '2026-09-27 09:52:02.873335+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d3d-7ad2-ab4b-dd70cd40dd7e', '01a0e247-5d32-7d21-a51c-21745cbe1882', '6beac9f6-32fa-4fd1-9882-c0fc42421bc3', 'message', '2026-09-27 09:52:02.873335+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d74-7199-ae1a-4578bcd057bf', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9', 'message', '2026-09-27 09:52:02.931625+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d75-7838-8097-edb71f78295c', '01a0e247-5d32-7d21-a51c-21745cbe1882', '81b82fa5-270b-4815-be8b-c41d5534bd74', 'message', '2026-09-27 09:52:02.931625+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d76-74ed-90a2-15de5789e4f3', '01a0e247-5d32-7d21-a51c-21745cbe1882', '65c4532c-6887-4e52-895e-36cc95b2b837', 'message', '2026-09-27 09:52:02.931625+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d77-7e90-b65f-15d6e0e89415', '01a0e247-5d32-7d21-a51c-21745cbe1882', '53d88061-a807-481d-85f6-aeefea0f28eb', 'message', '2026-09-27 09:52:02.931625+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d9d-7e14-a9ae-def01cad33dd', '01a0e247-5d32-7d21-a51c-21745cbe1882', '8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59', 'message', '2026-09-27 09:52:02.972713+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d9d-75bf-94ad-d0950bd75c8f', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'dfe052e2-bb71-4726-a021-0f93079eda4c', 'message', '2026-09-27 09:52:02.972713+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d9e-79d3-901a-9ce9c064b793', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'fc83f16d-f3bd-4b01-abd7-0433dffef66f', 'message', '2026-09-27 09:52:02.972713+00');
INSERT INTO public.source_object VALUES ('01a0e247-5d9f-71ce-a706-62576077972f', '01a0e247-5d32-7d21-a51c-21745cbe1882', '2e64778d-8d11-4bdf-b978-214aa0a7a22d', 'message', '2026-09-27 09:52:02.972713+00');
INSERT INTO public.source_object VALUES ('01a0e247-5dc7-7ea6-a0ff-cb5320cdac86', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'd273fd74-9fa7-4a8c-9e79-d21b4dbafbac', 'message', '2026-09-27 09:52:03.014504+00');
INSERT INTO public.source_object VALUES ('01a0e247-63d6-7309-b181-9b24a6f56d38', '01a0e247-5d32-7d21-a51c-21745cbe1882', 'b7f77fdd-4177-43ee-8d92-051ffe89bfd1', 'message', '2026-09-27 09:52:04.565183+00');
INSERT INTO public.source_object VALUES ('01a0e247-63d7-7873-a691-848fb20a3846', '01a0e247-5d32-7d21-a51c-21745cbe1882', '28b91209-f6c3-49a1-81fc-70bcfc30e32e', 'message', '2026-09-27 09:52:04.565183+00');
INSERT INTO public.source_object VALUES ('01a0e247-6402-789b-a8cf-da49df25d598', '01a0e247-5d32-7d21-a51c-21745cbe1882', '7daa6d5c-44ab-420e-835a-dd07eb037746', 'message', '2026-09-27 09:52:04.609686+00');
INSERT INTO public.source_object VALUES ('01a0e247-642a-76b8-96ba-d58ed8da3e64', '01a0e247-5d32-7d21-a51c-21745cbe1882', '27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90', 'message', '2026-09-27 09:52:04.648021+00');
INSERT INTO public.source_object VALUES ('01a0e247-6a38-71d7-b1a1-5356e2d2cd14', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '3ae772fc-dd31-4638-8440-210aa2f04e9d', 'message', '2026-09-27 09:52:06.199548+00');
INSERT INTO public.source_object VALUES ('01a0e247-6a38-7a8c-98b4-116fb63eec65', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '392a9def-cbd3-4628-a85e-47174575dcb9', 'message', '2026-09-27 09:52:06.199548+00');
INSERT INTO public.source_object VALUES ('01a0e247-6a39-7bad-9b8b-4c17b868ad3a', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '14874b3d-04a4-4de0-a685-fd1cff501cc0', 'message', '2026-09-27 09:52:06.199548+00');
INSERT INTO public.source_object VALUES ('01a0e247-6a3a-7c22-8720-b6f89c5e3c0a', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', 'b1116625-e6e1-46f1-ab55-8dc28e520d3d', 'message', '2026-09-27 09:52:06.199548+00');
INSERT INTO public.source_object VALUES ('01a0e247-6a3a-7737-a039-3d4ff52e7e68', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '33302beb-0f03-49c2-91b8-f55addfa5def', 'message', '2026-09-27 09:52:06.199548+00');
INSERT INTO public.source_object VALUES ('01a0e247-6a3b-7a90-af07-24583f76f8ca', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', 'cce4830b-0f60-436d-8b77-680683becb0a', 'message', '2026-09-27 09:52:06.199548+00');
INSERT INTO public.source_object VALUES ('01a0e247-6a3c-7240-833e-6aef2285613e', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', 'dd7ac5fc-ced8-40fb-ac0a-f0080ab3dcbb', 'message', '2026-09-27 09:52:06.199548+00');
INSERT INTO public.source_object VALUES ('01a0e247-6a3c-73f3-af3d-fc1da2e2438c', '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '2a54ce34-aec8-46cc-a2dd-131074896fc9', 'message', '2026-09-27 09:52:06.199548+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0e247-5d3a-7ad2-bbe9-911660be0cad', '01a0e247-5d39-78fa-ac2c-29dea28c3adc', '6e670a4f782b434fe5eda19655ce3cd2a5b5aee9f00d0642d9b6bfb48f6fd614', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "359555fe-f91f-4a5c-938e-54c5267269d7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:02.873335+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d3d-7c4f-a4f0-fec41c6c8504', '01a0e247-5d3d-73b3-9846-67446bdba290', '22203c487916f901977b6cd07f178176aef697e19b99adad4c00d526dce13990', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "9d98eb62-7f5b-4587-807d-b8e73e49829b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:02.873335+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d3c-7f5b-9e59-1eeb4a48b75c', '01a0e247-5d3c-7755-85aa-18e359ddc27d', '9469d74f66d65e6249639ec49051a02cba1735dae1676caa85cc47de9228a07b', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "bb57d506-013d-4829-ba99-4e7a1c640a4f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "bb57d506-013d-4829-ba99-4e7a1c640a4f", "specialComments": []}', '2026-09-27 09:52:02.873335+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d74-74c0-8750-ab7692c72128', '01a0e247-5d74-7199-ae1a-4578bcd057bf', '2749272e633381bf70985044f4bb57b7296cdb20db01426740d5652381cfa483', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:02.931625+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d76-7621-a497-f1ed97bf11f7', '01a0e247-5d76-74ed-90a2-15de5789e4f3', '7d09ae9c696daf228032dd7362b2b672681f67786e33d42e6cf254aa2813c799', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "65c4532c-6887-4e52-895e-36cc95b2b837", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:02.931625+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d9d-70ba-b274-9c4f31e89259', '01a0e247-5d9d-7e14-a9ae-def01cad33dd', 'cda6d6576242431252169697e8032effc87e156b7fa87b02357f59c01fe0cf40', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:02.972713+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d75-7314-ba2a-35bbe3b8321c', '01a0e247-5d75-7838-8097-edb71f78295c', 'e8638cbdd39bd3ddfac3afa05010dff2faeab533ffe8aa1363f97e689e599c4d', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "81b82fa5-270b-4815-be8b-c41d5534bd74", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "81b82fa5-270b-4815-be8b-c41d5534bd74", "specialComments": []}', '2026-09-27 09:52:02.931625+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d9f-7246-b37c-3bea9e4c1a58', '01a0e247-5d9e-79d3-901a-9ce9c064b793', 'd29b5be63bc7579484460c9eec5e4cfb24a4029089303d21402a85d51625df89', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "fc83f16d-f3bd-4b01-abd7-0433dffef66f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:02.972713+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d77-7f77-9e5f-0eb915f083df', '01a0e247-5d77-7e90-b65f-15d6e0e89415', 'ead1b8cb623da4c751dd5fad9d4a8837cdf43a68c0bf463fe7e23b296e74ae09', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "53d88061-a807-481d-85f6-aeefea0f28eb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "53d88061-a807-481d-85f6-aeefea0f28eb", "specialComments": []}', '2026-09-27 09:52:02.931625+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d9e-7df8-8f8a-a997df016385', '01a0e247-5d9d-75bf-94ad-d0950bd75c8f', 'e5c4bcc89a05faa3019bc04a56abb49b9a78c48eb13b17b0ad9314612e5c2f49', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "dfe052e2-bb71-4726-a021-0f93079eda4c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "dfe052e2-bb71-4726-a021-0f93079eda4c", "specialComments": []}', '2026-09-27 09:52:02.972713+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5dc7-7a19-8b70-51c0d09069e3', '01a0e247-5dc7-7ea6-a0ff-cb5320cdac86', '5cfa3a8f54951b7d6f1317e4e5f327379c7cb7cdd1e087a17fd87ee475121ae1', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "d273fd74-9fa7-4a8c-9e79-d21b4dbafbac", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:03.014504+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d9f-7cb3-8c8c-3f129863dad2', '01a0e247-5d9f-71ce-a706-62576077972f', '3cd4d4154155c00a9434f81704d2b7ffd56864d33235de1e65416f10ed6d0f49', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "2e64778d-8d11-4bdf-b978-214aa0a7a22d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "2e64778d-8d11-4bdf-b978-214aa0a7a22d", "specialComments": []}', '2026-09-27 09:52:02.972713+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-63d7-7e55-b134-655e194ed510', '01a0e247-63d7-7873-a691-848fb20a3846', '674f9a08c8991098af3f49b2c379521a8240d1a1ff33502b2453afbf36aa2ad8', 'And the compass?', '{"name": null, "role": "user", "chatId": "28b91209-f6c3-49a1-81fc-70bcfc30e32e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:04.565183+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-63d6-75e0-934e-7e0c38c02e8f', '01a0e247-5d3d-7ad2-ab4b-dd70cd40dd7e', '3815783b4fecde0bbc007e350ca73f068c8bdddd0ef0a5fb80cf0388540c33de', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "specialComments": []}', '2026-09-27 09:52:04.565183+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-5d3e-775c-b0f2-538e91387729', '01a0e247-5d3d-7ad2-ab4b-dd70cd40dd7e', 'fa10d1571d7feb590585125c47c705c9977f13366a888094e5599aff19e41b27', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "specialComments": []}', '2026-09-27 09:52:02.873335+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-63d6-7050-9984-c84df00d8a96', '01a0e247-63d6-7309-b181-9b24a6f56d38', 'b69709544c998fb99ef5be3c991bf2a31de615ad442d69bd94c0d0f5fd9488d1', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "specialComments": []}', '2026-09-27 09:52:04.565183+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6428-76be-a890-8cd0180a66ab', '01a0e247-5d9d-7e14-a9ae-def01cad33dd', '28a80b4ae8fcca7aaba4759ecb322badaeb238b14c78c6ff94e348b4478cc72c', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:04.648021+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-642a-7c17-9fa3-5b2ad5473dff', '01a0e247-642a-76b8-96ba-d58ed8da3e64', 'cb976c5abceb76c96d58fa066028d912a7ee16b06d8de397542c15b23d5ade85', 'Let''s go.', '{"name": null, "role": "user", "chatId": "27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:04.648021+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6429-7c8a-8a92-9a5eb802a4a8', '01a0e247-6402-789b-a8cf-da49df25d598', '34703d03e559602f38dcb038f80b1efd05c0fc165627b1d5e5bb1303ad4b1277', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "7daa6d5c-44ab-420e-835a-dd07eb037746", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "7daa6d5c-44ab-420e-835a-dd07eb037746", "specialComments": []}', '2026-09-27 09:52:04.648021+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6402-758e-8d4a-076feee5a050', '01a0e247-6402-789b-a8cf-da49df25d598', 'afedf7b04345543ae71d0313873887ff0722c7a98f8524a707e85596257900c3', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "7daa6d5c-44ab-420e-835a-dd07eb037746", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "7daa6d5c-44ab-420e-835a-dd07eb037746", "specialComments": []}', '2026-09-27 09:52:04.609686+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6a38-77e8-bfbb-15debe73231f', '01a0e247-6a38-71d7-b1a1-5356e2d2cd14', 'a1c11c03717e3fa1b5c745fdf79d3880fb251327a7c186f54a5e2e025f2e0837', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "3ae772fc-dd31-4638-8440-210aa2f04e9d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:06.199548+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6a39-7395-b6ce-1f53ee8de76e', '01a0e247-6a39-7bad-9b8b-4c17b868ad3a', '61368663da9f8719dede77f6673d39c5bfdd5e835af434e6a22506bdd0261b66', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "14874b3d-04a4-4de0-a685-fd1cff501cc0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:06.199548+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6a3b-775c-950a-6186256af0b9', '01a0e247-6a3a-7737-a039-3d4ff52e7e68', '65cb91dd6509bb6e1d67d346a7ee95d92f8e5173ad8e9af4aa3e7cb6065a1b10', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "33302beb-0f03-49c2-91b8-f55addfa5def", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:06.199548+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6a3c-752a-95e9-b43697f66c63', '01a0e247-6a3c-7240-833e-6aef2285613e', '6248441a3378aaee004b65b5b9a70d842a0c56be9285b05cd2c83049f3da1f23', '{{specialcomment::branchedfrom::c035bf48-f66c-43ff-92c5-e02cb7394cdc::Harbor route::81b82fa5-270b-4815-be8b-c41d5534bd74::}}', '{"name": null, "role": "char", "chatId": "dd7ac5fc-ced8-40fb-ac0a-f0080ab3dcbb", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::c035bf48-f66c-43ff-92c5-e02cb7394cdc::Harbor route::81b82fa5-270b-4815-be8b-c41d5534bd74::}}"]}', '2026-09-27 09:52:06.199548+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6a3d-731f-81d2-18cb9553804d', '01a0e247-6a3c-73f3-af3d-fc1da2e2438c', '24a1c23ab38ce8ff0717092170424a1141738b32d5d427d457c6fcbed70cda46', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "2a54ce34-aec8-46cc-a2dd-131074896fc9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-27 09:52:06.199548+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6a39-7d33-a7be-f49e0319cac1', '01a0e247-6a38-7a8c-98b4-116fb63eec65', '7aba12c150ab94e963017e0ac13fa10cb0bbf2cac695a4835a8210d0ac799550', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "392a9def-cbd3-4628-a85e-47174575dcb9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "bb57d506-013d-4829-ba99-4e7a1c640a4f", "specialComments": []}', '2026-09-27 09:52:06.199548+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6a3a-7834-986d-cbb5ad5064d0', '01a0e247-6a3a-7c22-8720-b6f89c5e3c0a', 'f6aeb6373692b0b972c412a3ac2f41bf297661e9c86623a010c3278a20192ebf', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "b1116625-e6e1-46f1-ab55-8dc28e520d3d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "specialComments": []}', '2026-09-27 09:52:06.199548+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e247-6a3b-73c9-b1f0-46dd096ffc36', '01a0e247-6a3b-7a90-af07-24583f76f8ca', '6bfb50fdb7a0732dea8518e3cf2543b12c907b1669d159badb284fc1d9bfc2fc', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "cce4830b-0f60-436d-8b77-680683becb0a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "81b82fa5-270b-4815-be8b-c41d5534bd74", "specialComments": []}', '2026-09-27 09:52:06.199548+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0e247-5d40-76e8-8193-37612b02c66d', '[{"op": "insert", "after": ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "fa10d1571d7feb590585125c47c705c9977f13366a888094e5599aff19e41b27"], "member": ["e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9", "2749272e633381bf70985044f4bb57b7296cdb20db01426740d5652381cfa483"]}, {"op": "insert", "after": ["e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9", "2749272e633381bf70985044f4bb57b7296cdb20db01426740d5652381cfa483"], "member": ["81b82fa5-270b-4815-be8b-c41d5534bd74", "e8638cbdd39bd3ddfac3afa05010dff2faeab533ffe8aa1363f97e689e599c4d"]}, {"op": "insert", "after": ["81b82fa5-270b-4815-be8b-c41d5534bd74", "e8638cbdd39bd3ddfac3afa05010dff2faeab533ffe8aa1363f97e689e599c4d"], "member": ["65c4532c-6887-4e52-895e-36cc95b2b837", "7d09ae9c696daf228032dd7362b2b672681f67786e33d42e6cf254aa2813c799"]}, {"op": "insert", "after": ["65c4532c-6887-4e52-895e-36cc95b2b837", "7d09ae9c696daf228032dd7362b2b672681f67786e33d42e6cf254aa2813c799"], "member": ["53d88061-a807-481d-85f6-aeefea0f28eb", "ead1b8cb623da4c751dd5fad9d4a8837cdf43a68c0bf463fe7e23b296e74ae09"]}]', '[{"new": ["e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9", "2749272e633381bf70985044f4bb57b7296cdb20db01426740d5652381cfa483"], "old": null, "kind": "append", "position": 4, "host_logical_id": "e31ccf1b-25d7-44f5-a3b5-e4363e0e1dc9"}, {"new": ["81b82fa5-270b-4815-be8b-c41d5534bd74", "e8638cbdd39bd3ddfac3afa05010dff2faeab533ffe8aa1363f97e689e599c4d"], "old": null, "kind": "append", "position": 5, "host_logical_id": "81b82fa5-270b-4815-be8b-c41d5534bd74"}, {"new": ["65c4532c-6887-4e52-895e-36cc95b2b837", "7d09ae9c696daf228032dd7362b2b672681f67786e33d42e6cf254aa2813c799"], "old": null, "kind": "append", "position": 6, "host_logical_id": "65c4532c-6887-4e52-895e-36cc95b2b837"}, {"new": ["53d88061-a807-481d-85f6-aeefea0f28eb", "ead1b8cb623da4c751dd5fad9d4a8837cdf43a68c0bf463fe7e23b296e74ae09"], "old": null, "kind": "append", "position": 7, "host_logical_id": "53d88061-a807-481d-85f6-aeefea0f28eb"}]', '01a0e247-5d7a-77f5-aa98-a5f213f6ead0', '2026-09-27 09:52:02.931625+00');
INSERT INTO public.worldline_append VALUES (2, '01a0e247-5d40-76e8-8193-37612b02c66d', '[{"op": "insert", "after": ["53d88061-a807-481d-85f6-aeefea0f28eb", "ead1b8cb623da4c751dd5fad9d4a8837cdf43a68c0bf463fe7e23b296e74ae09"], "member": ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "cda6d6576242431252169697e8032effc87e156b7fa87b02357f59c01fe0cf40"]}, {"op": "insert", "after": ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "cda6d6576242431252169697e8032effc87e156b7fa87b02357f59c01fe0cf40"], "member": ["dfe052e2-bb71-4726-a021-0f93079eda4c", "e5c4bcc89a05faa3019bc04a56abb49b9a78c48eb13b17b0ad9314612e5c2f49"]}, {"op": "insert", "after": ["dfe052e2-bb71-4726-a021-0f93079eda4c", "e5c4bcc89a05faa3019bc04a56abb49b9a78c48eb13b17b0ad9314612e5c2f49"], "member": ["fc83f16d-f3bd-4b01-abd7-0433dffef66f", "d29b5be63bc7579484460c9eec5e4cfb24a4029089303d21402a85d51625df89"]}, {"op": "insert", "after": ["fc83f16d-f3bd-4b01-abd7-0433dffef66f", "d29b5be63bc7579484460c9eec5e4cfb24a4029089303d21402a85d51625df89"], "member": ["2e64778d-8d11-4bdf-b978-214aa0a7a22d", "3cd4d4154155c00a9434f81704d2b7ffd56864d33235de1e65416f10ed6d0f49"]}]', '[{"new": ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "cda6d6576242431252169697e8032effc87e156b7fa87b02357f59c01fe0cf40"], "old": null, "kind": "append", "position": 8, "host_logical_id": "8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59"}, {"new": ["dfe052e2-bb71-4726-a021-0f93079eda4c", "e5c4bcc89a05faa3019bc04a56abb49b9a78c48eb13b17b0ad9314612e5c2f49"], "old": null, "kind": "append", "position": 9, "host_logical_id": "dfe052e2-bb71-4726-a021-0f93079eda4c"}, {"new": ["fc83f16d-f3bd-4b01-abd7-0433dffef66f", "d29b5be63bc7579484460c9eec5e4cfb24a4029089303d21402a85d51625df89"], "old": null, "kind": "append", "position": 10, "host_logical_id": "fc83f16d-f3bd-4b01-abd7-0433dffef66f"}, {"new": ["2e64778d-8d11-4bdf-b978-214aa0a7a22d", "3cd4d4154155c00a9434f81704d2b7ffd56864d33235de1e65416f10ed6d0f49"], "old": null, "kind": "append", "position": 11, "host_logical_id": "2e64778d-8d11-4bdf-b978-214aa0a7a22d"}]', '01a0e247-5da2-7f21-8b1d-ba987b5baee0', '2026-09-27 09:52:02.972713+00');
INSERT INTO public.worldline_append VALUES (3, '01a0e247-5d40-76e8-8193-37612b02c66d', '[{"op": "insert", "after": ["2e64778d-8d11-4bdf-b978-214aa0a7a22d", "3cd4d4154155c00a9434f81704d2b7ffd56864d33235de1e65416f10ed6d0f49"], "member": ["d273fd74-9fa7-4a8c-9e79-d21b4dbafbac", "5cfa3a8f54951b7d6f1317e4e5f327379c7cb7cdd1e087a17fd87ee475121ae1"]}]', '[{"new": ["d273fd74-9fa7-4a8c-9e79-d21b4dbafbac", "5cfa3a8f54951b7d6f1317e4e5f327379c7cb7cdd1e087a17fd87ee475121ae1"], "old": null, "kind": "append", "position": 12, "host_logical_id": "d273fd74-9fa7-4a8c-9e79-d21b4dbafbac"}]', '01a0e247-5dca-7408-a44c-d54d5b236c4d', '2026-09-27 09:52:03.014504+00');
INSERT INTO public.worldline_append VALUES (4, '01a0e247-63da-7f06-b7c4-f6934f4d2214', '[{"op": "insert", "after": ["28b91209-f6c3-49a1-81fc-70bcfc30e32e", "674f9a08c8991098af3f49b2c379521a8240d1a1ff33502b2453afbf36aa2ad8"], "member": ["7daa6d5c-44ab-420e-835a-dd07eb037746", "afedf7b04345543ae71d0313873887ff0722c7a98f8524a707e85596257900c3"]}]', '[{"new": ["7daa6d5c-44ab-420e-835a-dd07eb037746", "afedf7b04345543ae71d0313873887ff0722c7a98f8524a707e85596257900c3"], "old": null, "kind": "append", "position": 15, "host_logical_id": "7daa6d5c-44ab-420e-835a-dd07eb037746"}]', '01a0e247-6405-7e28-b523-e646f5c9f1cf', '2026-09-27 09:52:04.609686+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e247-5d40-76e8-8193-37612b02c66d', 1, '01a0e247-5d32-7d21-a51c-21745cbe1882', '{}', 'import', '87903964bfc137e43abc378fd022e641ce60819e3adadedebf54a64c8235063f', '{"ops": [{"op": "set", "members": [["359555fe-f91f-4a5c-938e-54c5267269d7", "6e670a4f782b434fe5eda19655ce3cd2a5b5aee9f00d0642d9b6bfb48f6fd614"], ["bb57d506-013d-4829-ba99-4e7a1c640a4f", "9469d74f66d65e6249639ec49051a02cba1735dae1676caa85cc47de9228a07b"], ["9d98eb62-7f5b-4587-807d-b8e73e49829b", "22203c487916f901977b6cd07f178176aef697e19b99adad4c00d526dce13990"], ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "fa10d1571d7feb590585125c47c705c9977f13366a888094e5599aff19e41b27"]]}], "changes": [{"new": ["359555fe-f91f-4a5c-938e-54c5267269d7", "6e670a4f782b434fe5eda19655ce3cd2a5b5aee9f00d0642d9b6bfb48f6fd614"], "old": null, "kind": "append", "position": 0, "host_logical_id": "359555fe-f91f-4a5c-938e-54c5267269d7"}, {"new": ["bb57d506-013d-4829-ba99-4e7a1c640a4f", "9469d74f66d65e6249639ec49051a02cba1735dae1676caa85cc47de9228a07b"], "old": null, "kind": "append", "position": 1, "host_logical_id": "bb57d506-013d-4829-ba99-4e7a1c640a4f"}, {"new": ["9d98eb62-7f5b-4587-807d-b8e73e49829b", "22203c487916f901977b6cd07f178176aef697e19b99adad4c00d526dce13990"], "old": null, "kind": "append", "position": 2, "host_logical_id": "9d98eb62-7f5b-4587-807d-b8e73e49829b"}, {"new": ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "fa10d1571d7feb590585125c47c705c9977f13366a888094e5599aff19e41b27"], "old": null, "kind": "append", "position": 3, "host_logical_id": "6beac9f6-32fa-4fd1-9882-c0fc42421bc3"}]}', '2026-09-27 09:52:02.873335+00', '01a0e247-5d3f-7375-afe5-6f582e7b45fb');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e247-63da-7f06-b7c4-f6934f4d2214', 2, '01a0e247-5d32-7d21-a51c-21745cbe1882', '{01a0e247-5d40-76e8-8193-37612b02c66d}', 'edit', 'a8ab24c00d894f9f8239b59e4a3678fa202b36e9a43612d6dc77c5cb9fb412c3', '{"ops": [{"op": "replace", "to": ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "3815783b4fecde0bbc007e350ca73f068c8bdddd0ef0a5fb80cf0388540c33de"], "from": ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "fa10d1571d7feb590585125c47c705c9977f13366a888094e5599aff19e41b27"]}, {"op": "insert", "after": ["d273fd74-9fa7-4a8c-9e79-d21b4dbafbac", "5cfa3a8f54951b7d6f1317e4e5f327379c7cb7cdd1e087a17fd87ee475121ae1"], "member": ["b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "b69709544c998fb99ef5be3c991bf2a31de615ad442d69bd94c0d0f5fd9488d1"]}, {"op": "insert", "after": ["b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "b69709544c998fb99ef5be3c991bf2a31de615ad442d69bd94c0d0f5fd9488d1"], "member": ["28b91209-f6c3-49a1-81fc-70bcfc30e32e", "674f9a08c8991098af3f49b2c379521a8240d1a1ff33502b2453afbf36aa2ad8"]}], "changes": [{"new": ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "3815783b4fecde0bbc007e350ca73f068c8bdddd0ef0a5fb80cf0388540c33de"], "old": ["6beac9f6-32fa-4fd1-9882-c0fc42421bc3", "fa10d1571d7feb590585125c47c705c9977f13366a888094e5599aff19e41b27"], "kind": "edit", "position": 3, "host_logical_id": "6beac9f6-32fa-4fd1-9882-c0fc42421bc3"}, {"new": ["b7f77fdd-4177-43ee-8d92-051ffe89bfd1", "b69709544c998fb99ef5be3c991bf2a31de615ad442d69bd94c0d0f5fd9488d1"], "old": null, "kind": "append", "position": 13, "host_logical_id": "b7f77fdd-4177-43ee-8d92-051ffe89bfd1"}, {"new": ["28b91209-f6c3-49a1-81fc-70bcfc30e32e", "674f9a08c8991098af3f49b2c379521a8240d1a1ff33502b2453afbf36aa2ad8"], "old": null, "kind": "append", "position": 14, "host_logical_id": "28b91209-f6c3-49a1-81fc-70bcfc30e32e"}]}', '2026-09-27 09:52:04.565183+00', '01a0e247-63d9-7a20-ba85-810788e7cd7e');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e247-642d-7236-a94f-350ff70ef05b', 3, '01a0e247-5d32-7d21-a51c-21745cbe1882', '{01a0e247-63da-7f06-b7c4-f6934f4d2214}', 'reconciliation', 'c86ecde851c307e98d7ced1f01c28f384cdb0682766bf758d2af356db3635dff', '{"ops": [{"op": "replace", "to": ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "28a80b4ae8fcca7aaba4759ecb322badaeb238b14c78c6ff94e348b4478cc72c"], "from": ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "cda6d6576242431252169697e8032effc87e156b7fa87b02357f59c01fe0cf40"]}, {"op": "replace", "to": ["7daa6d5c-44ab-420e-835a-dd07eb037746", "34703d03e559602f38dcb038f80b1efd05c0fc165627b1d5e5bb1303ad4b1277"], "from": ["7daa6d5c-44ab-420e-835a-dd07eb037746", "afedf7b04345543ae71d0313873887ff0722c7a98f8524a707e85596257900c3"]}, {"op": "insert", "after": ["7daa6d5c-44ab-420e-835a-dd07eb037746", "34703d03e559602f38dcb038f80b1efd05c0fc165627b1d5e5bb1303ad4b1277"], "member": ["27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90", "cb976c5abceb76c96d58fa066028d912a7ee16b06d8de397542c15b23d5ade85"]}], "changes": [{"new": ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "28a80b4ae8fcca7aaba4759ecb322badaeb238b14c78c6ff94e348b4478cc72c"], "old": ["8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59", "cda6d6576242431252169697e8032effc87e156b7fa87b02357f59c01fe0cf40"], "kind": "disable", "position": 8, "host_logical_id": "8fc02146-e1a5-4816-8a1a-ccc5f5fc0c59"}, {"new": ["7daa6d5c-44ab-420e-835a-dd07eb037746", "34703d03e559602f38dcb038f80b1efd05c0fc165627b1d5e5bb1303ad4b1277"], "old": ["7daa6d5c-44ab-420e-835a-dd07eb037746", "afedf7b04345543ae71d0313873887ff0722c7a98f8524a707e85596257900c3"], "kind": "swipe", "position": 15, "host_logical_id": "7daa6d5c-44ab-420e-835a-dd07eb037746"}, {"new": ["27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90", "cb976c5abceb76c96d58fa066028d912a7ee16b06d8de397542c15b23d5ade85"], "old": null, "kind": "append", "position": 16, "host_logical_id": "27b9feb2-0ace-4f2d-9c7f-d6b2d3980a90"}]}', '2026-09-27 09:52:04.648021+00', '01a0e247-642c-77ed-9258-3744b2c02026');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e247-6a3f-7186-a921-05ec6e3014b2', 4, '01a0e247-6a31-7fef-85da-d6e25cf4e3f9', '{}', 'branch', '14d036bccb1afbfd6a2f5754d4b7d8409ee9660cd4ada6c51f204faadda9dcdf', '{"ops": [{"op": "set", "members": [["3ae772fc-dd31-4638-8440-210aa2f04e9d", "a1c11c03717e3fa1b5c745fdf79d3880fb251327a7c186f54a5e2e025f2e0837"], ["392a9def-cbd3-4628-a85e-47174575dcb9", "7aba12c150ab94e963017e0ac13fa10cb0bbf2cac695a4835a8210d0ac799550"], ["14874b3d-04a4-4de0-a685-fd1cff501cc0", "61368663da9f8719dede77f6673d39c5bfdd5e835af434e6a22506bdd0261b66"], ["b1116625-e6e1-46f1-ab55-8dc28e520d3d", "f6aeb6373692b0b972c412a3ac2f41bf297661e9c86623a010c3278a20192ebf"], ["33302beb-0f03-49c2-91b8-f55addfa5def", "65cb91dd6509bb6e1d67d346a7ee95d92f8e5173ad8e9af4aa3e7cb6065a1b10"], ["cce4830b-0f60-436d-8b77-680683becb0a", "6bfb50fdb7a0732dea8518e3cf2543b12c907b1669d159badb284fc1d9bfc2fc"], ["dd7ac5fc-ced8-40fb-ac0a-f0080ab3dcbb", "6248441a3378aaee004b65b5b9a70d842a0c56be9285b05cd2c83049f3da1f23"], ["2a54ce34-aec8-46cc-a2dd-131074896fc9", "24a1c23ab38ce8ff0717092170424a1141738b32d5d427d457c6fcbed70cda46"]]}], "changes": [{"new": ["3ae772fc-dd31-4638-8440-210aa2f04e9d", "a1c11c03717e3fa1b5c745fdf79d3880fb251327a7c186f54a5e2e025f2e0837"], "old": null, "kind": "append", "position": 0, "host_logical_id": "3ae772fc-dd31-4638-8440-210aa2f04e9d"}, {"new": ["392a9def-cbd3-4628-a85e-47174575dcb9", "7aba12c150ab94e963017e0ac13fa10cb0bbf2cac695a4835a8210d0ac799550"], "old": null, "kind": "append", "position": 1, "host_logical_id": "392a9def-cbd3-4628-a85e-47174575dcb9"}, {"new": ["14874b3d-04a4-4de0-a685-fd1cff501cc0", "61368663da9f8719dede77f6673d39c5bfdd5e835af434e6a22506bdd0261b66"], "old": null, "kind": "append", "position": 2, "host_logical_id": "14874b3d-04a4-4de0-a685-fd1cff501cc0"}, {"new": ["b1116625-e6e1-46f1-ab55-8dc28e520d3d", "f6aeb6373692b0b972c412a3ac2f41bf297661e9c86623a010c3278a20192ebf"], "old": null, "kind": "append", "position": 3, "host_logical_id": "b1116625-e6e1-46f1-ab55-8dc28e520d3d"}, {"new": ["33302beb-0f03-49c2-91b8-f55addfa5def", "65cb91dd6509bb6e1d67d346a7ee95d92f8e5173ad8e9af4aa3e7cb6065a1b10"], "old": null, "kind": "append", "position": 4, "host_logical_id": "33302beb-0f03-49c2-91b8-f55addfa5def"}, {"new": ["cce4830b-0f60-436d-8b77-680683becb0a", "6bfb50fdb7a0732dea8518e3cf2543b12c907b1669d159badb284fc1d9bfc2fc"], "old": null, "kind": "append", "position": 5, "host_logical_id": "cce4830b-0f60-436d-8b77-680683becb0a"}, {"new": ["dd7ac5fc-ced8-40fb-ac0a-f0080ab3dcbb", "6248441a3378aaee004b65b5b9a70d842a0c56be9285b05cd2c83049f3da1f23"], "old": null, "kind": "append", "position": 6, "host_logical_id": "dd7ac5fc-ced8-40fb-ac0a-f0080ab3dcbb"}, {"new": ["2a54ce34-aec8-46cc-a2dd-131074896fc9", "24a1c23ab38ce8ff0717092170424a1141738b32d5d427d457c6fcbed70cda46"], "old": null, "kind": "append", "position": 7, "host_logical_id": "2a54ce34-aec8-46cc-a2dd-131074896fc9"}]}', '2026-09-27 09:52:06.199548+00', '01a0e247-6a3e-77de-85e6-ccf4b9a4c24d');


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


