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

INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 0, '01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 1, '01a0e7b5-3a61-7541-8ef3-af00948a55b1', NULL, 0, 'fbfe561ce3b5209d633073320d636bad');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 2, '01a0e7b5-3a62-7da7-98a3-20cc432f5e29', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 3, '01a0e7b5-40f7-7a0a-94de-32aeacb1d05d', NULL, 1, 'c35d8c77bf082ed17f74bdb1b4702cda');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 4, '01a0e7b5-3a9c-7aac-8a54-d690d8eccf47', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 5, '01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8', NULL, 2, 'dd45b5db7fd73063aeed8e1740e42340');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 6, '01a0e7b5-3a9e-77e9-83c6-5d522c261db3', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 7, '01a0e7b5-3a9f-7dbe-8771-40f2571b65f4', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 8, '01a0e7b5-4145-7a6d-982f-4fc83be5a34e', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 9, '01a0e7b5-3ac6-7eb4-859d-e986228c9a27', NULL, 3, 'e7db7ae4358e2b3978e8f25aa4a49708');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 10, '01a0e7b5-3ac7-7ade-b622-20874b69a4ca', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 11, '01a0e7b5-3ac7-7cda-89b9-da652207eb88', NULL, 4, 'ecf6193f9421be16c6fdec525b966b4e');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 12, '01a0e7b5-3aed-70ac-b486-85ac3a496f61', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 13, '01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a', NULL, 5, 'fe093ed26daa1e45f2472c371bf5398b');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 14, '01a0e7b5-40f8-7295-b7ab-8713d3c2d900', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 15, '01a0e7b5-4146-7614-a731-50bd00f60138', NULL, 6, 'e4ecdd33c7dd62c1259be9fb0d1bed8e');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 16, '01a0e7b5-4147-7728-b54f-8a8e63e1bd36', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 0, '01a0e7b5-475b-7ae0-93d8-858764b5d69f', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 1, '01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d', NULL, 0, '449f1ffb727cbca043aae2268a5fb168');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 2, '01a0e7b5-475d-7029-8dd4-4008a06e11c7', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 3, '01a0e7b5-475d-7c6b-ab2b-f5b182101e1e', NULL, 1, 'eb88aee802ef8caee91f06c6135a00d5');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 4, '01a0e7b5-475e-7ca9-bfe5-3104a630af49', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 5, '01a0e7b5-475e-7ea5-b037-6ea4cbd2c043', NULL, 2, '1c1279cb37937b8b600344efc2f91ae9');
INSERT INTO public.active_membership VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 6, '01a0e7b5-475f-7c40-b005-0ffe47093d8f', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 7, '01a0e7b5-475f-774f-af41-2e9c22520d9f', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0e7b5-3ff4-76ee-9af2-f38bc4be686c', '01a0e7b5-3ac7-7cda-89b9-da652207eb88', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0e7b5-400c-7b09-a1f4-c91c5fd40f10', '01a0e7b5-3ac6-7eb4-859d-e986228c9a27', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0e7b5-4039-7e2b-8b1b-9e22b89b5c90', '01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0e7b5-4053-7215-a2a7-86153234b2cd', '01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0e7b5-4053-7215-a2a7-86153234b2cd', '01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0e7b5-40a0-7e35-8e80-62634aadf99b', '01a0e7b5-3a61-7541-8ef3-af00948a55b1', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0e7b5-40a0-7e35-8e80-62634aadf99b', '01a0e7b5-3a61-7541-8ef3-af00948a55b1', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0e7b5-450c-7109-8d6c-7c039c696017', '01a0e7b5-4146-7614-a731-50bd00f60138', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0e7b5-453c-7f4d-a7c4-af3e0d0aec81', '01a0e7b5-3ac7-7cda-89b9-da652207eb88', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0e7b5-4553-746e-aa95-7754a25f3079', '01a0e7b5-3ac6-7eb4-859d-e986228c9a27', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0e7b5-4577-7177-bb87-cd01ad5f0b57', '01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0e7b5-458d-7760-88a1-7ba3e357148a', '01a0e7b5-40f7-7a0a-94de-32aeacb1d05d', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0e7b5-458d-7760-88a1-7ba3e357148a', '01a0e7b5-40f7-7a0a-94de-32aeacb1d05d', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0e7b5-4a1e-7d38-a99b-9284f9b1d750', '01a0e7b5-475e-7ea5-b037-6ea4cbd2c043', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0e7b5-4a33-76ff-8012-c255bfa0e9b9', '01a0e7b5-475d-7c6b-ab2b-f5b182101e1e', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0e7b5-4a33-76ff-8012-c255bfa0e9b9', '01a0e7b5-475d-7c6b-ab2b-f5b182101e1e', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0e7b5-4a4c-7bf0-bda1-4a54c16a31c9', '01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0e7b5-4a4c-7bf0-bda1-4a54c16a31c9', '01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'pocketrisu', NULL, '273c4d94-f678-4f2d-9431-32a348078fde', '2026-09-28 11:10:08.976371+00', NULL, NULL, NULL, '01a0e7b5-4149-7dcd-b605-35f011c51c62', '57d1f49d1855be6dbde8e8da4138dc02645c87e7d89f99ee8f169bc4b53473f2', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL);
INSERT INTO public.conversation VALUES ('01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', 'pocketrisu', NULL, 'd3d7cfeb-2ff2-4092-be4d-d305806d111d', '2026-09-28 11:10:12.302165+00', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '273c4d94-f678-4f2d-9431-32a348078fde', '8b77fdf5-98b3-4208-a699-323af0a1a49a', '01a0e7b5-4761-702d-8954-459e9a0380e9', '19621681438213d69152f91c10c05fffdd18925ca882e3dd5ec43fec24066c04', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0e7b5-3ff4-76ee-9af2-f38bc4be686c', '01a0e7b5-3ac7-7cda-89b9-da652207eb88', '55514c76f7f4bd1f659e11bc453a9ecb', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:10.42044+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-3ac7-7ade-b622-20874b69a4ca,01a0e7b5-3ac7-7cda-89b9-da652207eb88}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-400c-7b09-a1f4-c91c5fd40f10', '01a0e7b5-3ac6-7eb4-859d-e986228c9a27', '3d9674bc5f1ae9e2ec37c49e28fdd8df', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:10.444271+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-3ac5-7be9-bb77-731a6f61d60e,01a0e7b5-3ac6-7eb4-859d-e986228c9a27}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4023-7d96-b3fb-1f3fd6b96c7c', '01a0e7b5-3a9f-7dbe-8771-40f2571b65f4', '64ad7591f62fa2bb21572f0094006af2', 'extract-v13', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:10:10.467221+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-3a9e-77e9-83c6-5d522c261db3,01a0e7b5-3a9f-7dbe-8771-40f2571b65f4}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4039-7e2b-8b1b-9e22b89b5c90', '01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8', '6546910496fc06d077d322014855afaa', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:10.489448+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-3a9c-7aac-8a54-d690d8eccf47,01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4053-7215-a2a7-86153234b2cd', '01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7', '70b6b9ed880c7df131baa11169920449', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:10.515105+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-3a62-7da7-98a3-20cc432f5e29,01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-40a0-7e35-8e80-62634aadf99b', '01a0e7b5-3a61-7541-8ef3-af00948a55b1', 'fbfe561ce3b5209d633073320d636bad', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:10.592744+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2,01a0e7b5-3a61-7541-8ef3-af00948a55b1}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-450c-7109-8d6c-7c039c696017', '01a0e7b5-4146-7614-a731-50bd00f60138', 'e4ecdd33c7dd62c1259be9fb0d1bed8e', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:11.724002+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-40f8-7295-b7ab-8713d3c2d900,01a0e7b5-4146-7614-a731-50bd00f60138}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4526-74d0-920d-bcc6ef7c9569', '01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a', 'fe093ed26daa1e45f2472c371bf5398b', 'extract-v13', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:10:11.750102+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-3aed-70ac-b486-85ac3a496f61,01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-453c-7f4d-a7c4-af3e0d0aec81', '01a0e7b5-3ac7-7cda-89b9-da652207eb88', 'ecf6193f9421be16c6fdec525b966b4e', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:11.772201+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b5-3ac7-7ade-b622-20874b69a4ca,01a0e7b5-3ac7-7cda-89b9-da652207eb88}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4553-746e-aa95-7754a25f3079', '01a0e7b5-3ac6-7eb4-859d-e986228c9a27', 'e7db7ae4358e2b3978e8f25aa4a49708', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:11.795782+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0e7b5-3a9e-77e9-83c6-5d522c261db3,01a0e7b5-3a9f-7dbe-8771-40f2571b65f4,01a0e7b5-3ac6-7eb4-859d-e986228c9a27}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4577-7177-bb87-cd01ad5f0b57', '01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8', 'dd45b5db7fd73063aeed8e1740e42340', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:11.831695+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-3a9c-7aac-8a54-d690d8eccf47,01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-458d-7760-88a1-7ba3e357148a', '01a0e7b5-40f7-7a0a-94de-32aeacb1d05d', 'c35d8c77bf082ed17f74bdb1b4702cda', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:11.853736+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-3a62-7da7-98a3-20cc432f5e29,01a0e7b5-40f7-7a0a-94de-32aeacb1d05d}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4a1e-7d38-a99b-9284f9b1d750', '01a0e7b5-475e-7ea5-b037-6ea4cbd2c043', '1c1279cb37937b8b600344efc2f91ae9', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:13.022152+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b5-475e-7ca9-bfe5-3104a630af49,01a0e7b5-475e-7ea5-b037-6ea4cbd2c043}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4a33-76ff-8012-c255bfa0e9b9', '01a0e7b5-475d-7c6b-ab2b-f5b182101e1e', 'eb88aee802ef8caee91f06c6135a00d5', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:13.043073+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b5-475d-7029-8dd4-4008a06e11c7,01a0e7b5-475d-7c6b-ab2b-f5b182101e1e}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b5-4a4c-7bf0-bda1-4a54c16a31c9', '01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d', '449f1ffb727cbca043aae2268a5fb168', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:10:13.068742+00', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e7b5-475b-7ae0-93d8-858764b5d69f,01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0e7b5-3a65-7ce1-867d-3228b1264140', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'manifest', '971ed53b0b62686e77361bf028328c9f59aad87d03b000bf522b7481fec44174', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd:971ed53b0b62686e77361bf028328c9f59aad87d03b000bf522b7481fec44174:manifest', '2026-09-28 11:10:08.990664+00', '{"chat_id": "273c4d94-f678-4f2d-9431-32a348078fde", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["cd6a7cd4-cef5-4cd3-87ec-ddceb141921d", "9fd8ea9fcb1339d6dac5f9cfcb978080ad41f3b1279b9fd2ca5f93633be78336", "user", null, null, null, 0, null, null], ["b09b7305-d34c-40b5-91bd-7c643eb30338", "ab1049189a29d91bcc8b4128e4a6da70b4f67e68536ba5ab078dfa6dcbe6132c", "char", null, null, null, 0, "b09b7305-d34c-40b5-91bd-7c643eb30338", null], ["81718ea8-5069-4c34-868f-ea32146ea055", "86f6c6d3ae8a645cc7fc25e8c7b7292b1ff8802e9884260a5f1a322be8f9e03e", "user", null, null, null, 0, null, null], ["fffce903-2a78-440d-9151-01c2b1cec7dd", "5b7fc56ebffee128ba1e60d26b33b69a3a78d0d410537802c5a4670215af61ec", "char", null, null, null, 0, "fffce903-2a78-440d-9151-01c2b1cec7dd", null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-3aa2-7bec-9e4e-8f4cea82b6c4', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'manifest', '26fa1ad695a8fde271b864232f037ce78aa83df0dfbe4d2cf7962f53cff80687', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd:26fa1ad695a8fde271b864232f037ce78aa83df0dfbe4d2cf7962f53cff80687:manifest', '2026-09-28 11:10:09.051769+00', '{"chat_id": "273c4d94-f678-4f2d-9431-32a348078fde", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["bdfdfc0e-f7d2-4291-ae20-336e934dae93", "c0b71332b0cf65b6dbb244c0a277bcbb5e17377a3acf2415336ba58780c32cf9", "user", null, null, null, 0, null, null], ["8b77fdf5-98b3-4208-a699-323af0a1a49a", "2d4285c87770b28e17a967f6c78e4eca34852188b8b7c10e55e230adf9b0577b", "char", null, null, null, 0, "8b77fdf5-98b3-4208-a699-323af0a1a49a", null], ["1acc7d2a-ade9-4534-ba82-12f94b551cfc", "bc261e8aa34452c97b82310565001bf2fb3fed2d9aaaced71f165de77971b094", "user", null, null, null, 0, null, null], ["8ddd2d3f-082e-4c86-b701-d9e5551378b2", "2c6cb12da146d099782d13d1f93220d7f2d0bb9d05b4dfb4123735dc1f44c177", "char", null, null, null, 0, "8ddd2d3f-082e-4c86-b701-d9e5551378b2", null]], "base_manifest_hash": "971ed53b0b62686e77361bf028328c9f59aad87d03b000bf522b7481fec44174"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-3aca-7442-bc84-85da6c5fdfa3', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'manifest', '93aebe9725ab6d43dc6a10eddca37565f225d838df877a5f06310098ee477b11', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd:93aebe9725ab6d43dc6a10eddca37565f225d838df877a5f06310098ee477b11:manifest', '2026-09-28 11:10:09.092877+00', '{"chat_id": "273c4d94-f678-4f2d-9431-32a348078fde", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "a87d844f3b5885683b2838b1bf79b713e7746934d17d449ccdcab740f4dd4708", "user", null, null, null, 0, null, null], ["dc887fc7-2665-469c-8a75-2d4f5924b37f", "7088c1d9881a9be48c6fe4a3dad533ca841c8d620b66b75a0007022074158a11", "char", null, null, null, 0, "dc887fc7-2665-469c-8a75-2d4f5924b37f", null], ["74af895d-9072-4a66-afe9-203bc958c798", "b86dd570e65f136840bffc3b0bc3400b2c549b7f3f1986d624d37fe55a6e9578", "user", null, null, null, 0, null, null], ["f169d7c1-1029-413d-85a4-8126d286cdf8", "4152861dab5e6d52abeea22477540e178ed0d2a12b9f57b86cc6e24fde70d11b", "char", null, null, null, 0, "f169d7c1-1029-413d-85a4-8126d286cdf8", null]], "base_manifest_hash": "26fa1ad695a8fde271b864232f037ce78aa83df0dfbe4d2cf7962f53cff80687"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-3aef-7fe4-a813-a7b8ada87540', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'manifest', '9c80ef3062bb397f66d11ed6cab707a3fa8a01ca2f6e05d3e1610fbfe238e341', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd:9c80ef3062bb397f66d11ed6cab707a3fa8a01ca2f6e05d3e1610fbfe238e341:manifest', '2026-09-28 11:10:09.132469+00', '{"chat_id": "273c4d94-f678-4f2d-9431-32a348078fde", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["965ae0c4-23c1-4938-9596-33cc710c64e0", "fbe7c95481a9557ff14948e09c8137b3b3cbbb1b0b8449cf4c3f9fa8afdbf7b8", "user", null, null, null, 0, null, null]], "base_manifest_hash": "93aebe9725ab6d43dc6a10eddca37565f225d838df877a5f06310098ee477b11"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-40fb-7ebf-960c-4beddccdbd81', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'manifest', 'b4bd742e66e5113b5416d049463dd97ff8cab159dbe24b8b99fd2167f1e88bca', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd:b4bd742e66e5113b5416d049463dd97ff8cab159dbe24b8b99fd2167f1e88bca:manifest', '2026-09-28 11:10:10.678219+00', '{"chat_id": "273c4d94-f678-4f2d-9431-32a348078fde", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["cd6a7cd4-cef5-4cd3-87ec-ddceb141921d", "9fd8ea9fcb1339d6dac5f9cfcb978080ad41f3b1279b9fd2ca5f93633be78336", "user", null, null, null, 0, null, null], ["b09b7305-d34c-40b5-91bd-7c643eb30338", "ab1049189a29d91bcc8b4128e4a6da70b4f67e68536ba5ab078dfa6dcbe6132c", "char", null, null, null, 0, "b09b7305-d34c-40b5-91bd-7c643eb30338", null], ["81718ea8-5069-4c34-868f-ea32146ea055", "86f6c6d3ae8a645cc7fc25e8c7b7292b1ff8802e9884260a5f1a322be8f9e03e", "user", null, null, null, 0, null, null], ["fffce903-2a78-440d-9151-01c2b1cec7dd", "58427731059beac6d93a54ef95c418a477fcc3952493896b546a110049cd3283", "char", null, null, null, 0, "fffce903-2a78-440d-9151-01c2b1cec7dd", null], ["bdfdfc0e-f7d2-4291-ae20-336e934dae93", "c0b71332b0cf65b6dbb244c0a277bcbb5e17377a3acf2415336ba58780c32cf9", "user", null, null, null, 0, null, null], ["8b77fdf5-98b3-4208-a699-323af0a1a49a", "2d4285c87770b28e17a967f6c78e4eca34852188b8b7c10e55e230adf9b0577b", "char", null, null, null, 0, "8b77fdf5-98b3-4208-a699-323af0a1a49a", null], ["1acc7d2a-ade9-4534-ba82-12f94b551cfc", "bc261e8aa34452c97b82310565001bf2fb3fed2d9aaaced71f165de77971b094", "user", null, null, null, 0, null, null], ["8ddd2d3f-082e-4c86-b701-d9e5551378b2", "2c6cb12da146d099782d13d1f93220d7f2d0bb9d05b4dfb4123735dc1f44c177", "char", null, null, null, 0, "8ddd2d3f-082e-4c86-b701-d9e5551378b2", null], ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "a87d844f3b5885683b2838b1bf79b713e7746934d17d449ccdcab740f4dd4708", "user", null, null, null, 0, null, null], ["dc887fc7-2665-469c-8a75-2d4f5924b37f", "7088c1d9881a9be48c6fe4a3dad533ca841c8d620b66b75a0007022074158a11", "char", null, null, null, 0, "dc887fc7-2665-469c-8a75-2d4f5924b37f", null], ["74af895d-9072-4a66-afe9-203bc958c798", "b86dd570e65f136840bffc3b0bc3400b2c549b7f3f1986d624d37fe55a6e9578", "user", null, null, null, 0, null, null], ["f169d7c1-1029-413d-85a4-8126d286cdf8", "4152861dab5e6d52abeea22477540e178ed0d2a12b9f57b86cc6e24fde70d11b", "char", null, null, null, 0, "f169d7c1-1029-413d-85a4-8126d286cdf8", null], ["965ae0c4-23c1-4938-9596-33cc710c64e0", "fbe7c95481a9557ff14948e09c8137b3b3cbbb1b0b8449cf4c3f9fa8afdbf7b8", "user", null, null, null, 0, null, null], ["78c92f7d-ba33-47d3-b467-ddebbc064a14", "d8af5de848a7718bf3c5a8b0de5a56c295194fe23068cca0254a88dcf307281e", "char", null, null, null, 0, "78c92f7d-ba33-47d3-b467-ddebbc064a14", null], ["29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "8109b743a1f2e3179c85e3c6acd33315afe7dee42ddd7213746213cb68e6ab35", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-4122-7b4a-86bb-b6206688d802', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'manifest', '55d7f561bb1c25bacf832fa673a2649215e28d1b2ede3e215b9194da2a96c8f3', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd:55d7f561bb1c25bacf832fa673a2649215e28d1b2ede3e215b9194da2a96c8f3:manifest', '2026-09-28 11:10:10.718855+00', '{"chat_id": "273c4d94-f678-4f2d-9431-32a348078fde", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["77b2a637-a479-4e62-82dd-35e47dcaa59d", "61b3b9c346c3724ff9a069be8e036f2d4dc2fce88085d9d19c4c36c702fe02a6", "char", null, null, 1, 2, "77b2a637-a479-4e62-82dd-35e47dcaa59d", null]], "base_manifest_hash": "b4bd742e66e5113b5416d049463dd97ff8cab159dbe24b8b99fd2167f1e88bca"}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-4149-77f9-bad9-e6c67501183d', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'manifest', '57d1f49d1855be6dbde8e8da4138dc02645c87e7d89f99ee8f169bc4b53473f2', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd:57d1f49d1855be6dbde8e8da4138dc02645c87e7d89f99ee8f169bc4b53473f2:manifest', '2026-09-28 11:10:10.757055+00', '{"chat_id": "273c4d94-f678-4f2d-9431-32a348078fde", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["cd6a7cd4-cef5-4cd3-87ec-ddceb141921d", "9fd8ea9fcb1339d6dac5f9cfcb978080ad41f3b1279b9fd2ca5f93633be78336", "user", null, null, null, 0, null, null], ["b09b7305-d34c-40b5-91bd-7c643eb30338", "ab1049189a29d91bcc8b4128e4a6da70b4f67e68536ba5ab078dfa6dcbe6132c", "char", null, null, null, 0, "b09b7305-d34c-40b5-91bd-7c643eb30338", null], ["81718ea8-5069-4c34-868f-ea32146ea055", "86f6c6d3ae8a645cc7fc25e8c7b7292b1ff8802e9884260a5f1a322be8f9e03e", "user", null, null, null, 0, null, null], ["fffce903-2a78-440d-9151-01c2b1cec7dd", "58427731059beac6d93a54ef95c418a477fcc3952493896b546a110049cd3283", "char", null, null, null, 0, "fffce903-2a78-440d-9151-01c2b1cec7dd", null], ["bdfdfc0e-f7d2-4291-ae20-336e934dae93", "c0b71332b0cf65b6dbb244c0a277bcbb5e17377a3acf2415336ba58780c32cf9", "user", null, null, null, 0, null, null], ["8b77fdf5-98b3-4208-a699-323af0a1a49a", "2d4285c87770b28e17a967f6c78e4eca34852188b8b7c10e55e230adf9b0577b", "char", null, null, null, 0, "8b77fdf5-98b3-4208-a699-323af0a1a49a", null], ["1acc7d2a-ade9-4534-ba82-12f94b551cfc", "bc261e8aa34452c97b82310565001bf2fb3fed2d9aaaced71f165de77971b094", "user", null, null, null, 0, null, null], ["8ddd2d3f-082e-4c86-b701-d9e5551378b2", "2c6cb12da146d099782d13d1f93220d7f2d0bb9d05b4dfb4123735dc1f44c177", "char", null, null, null, 0, "8ddd2d3f-082e-4c86-b701-d9e5551378b2", null], ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "2cdd1e15085b18e3fc68359e69f6aa28ac70895f5d6e447582e18c36bf5d8bcd", "user", true, null, null, 0, null, null], ["dc887fc7-2665-469c-8a75-2d4f5924b37f", "7088c1d9881a9be48c6fe4a3dad533ca841c8d620b66b75a0007022074158a11", "char", null, null, null, 0, "dc887fc7-2665-469c-8a75-2d4f5924b37f", null], ["74af895d-9072-4a66-afe9-203bc958c798", "b86dd570e65f136840bffc3b0bc3400b2c549b7f3f1986d624d37fe55a6e9578", "user", null, null, null, 0, null, null], ["f169d7c1-1029-413d-85a4-8126d286cdf8", "4152861dab5e6d52abeea22477540e178ed0d2a12b9f57b86cc6e24fde70d11b", "char", null, null, null, 0, "f169d7c1-1029-413d-85a4-8126d286cdf8", null], ["965ae0c4-23c1-4938-9596-33cc710c64e0", "fbe7c95481a9557ff14948e09c8137b3b3cbbb1b0b8449cf4c3f9fa8afdbf7b8", "user", null, null, null, 0, null, null], ["78c92f7d-ba33-47d3-b467-ddebbc064a14", "d8af5de848a7718bf3c5a8b0de5a56c295194fe23068cca0254a88dcf307281e", "char", null, null, null, 0, "78c92f7d-ba33-47d3-b467-ddebbc064a14", null], ["29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "8109b743a1f2e3179c85e3c6acd33315afe7dee42ddd7213746213cb68e6ab35", "user", null, null, null, 0, null, null], ["77b2a637-a479-4e62-82dd-35e47dcaa59d", "b85e6e8be367ca14b7c34ec0194c9ca8fdcc51967e0d48814e7496a0d13101a2", "char", null, null, 0, 2, "77b2a637-a479-4e62-82dd-35e47dcaa59d", null], ["a527db9f-94c6-4a56-b7cb-37a165ffc0ea", "47c57607d693a652099e95dcd63fb8fd0cd1575a9f8a7fd362692d8d88867d13", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b5-4760-7b36-a7cc-e69f0d4576df', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', 'manifest', '19621681438213d69152f91c10c05fffdd18925ca882e3dd5ec43fec24066c04', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1:19621681438213d69152f91c10c05fffdd18925ca882e3dd5ec43fec24066c04:manifest', '2026-09-28 11:10:12.314227+00', '{"chat_id": "d3d7cfeb-2ff2-4092-be4d-d305806d111d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["9a7613c9-3840-45c9-96ea-6eff41ed4fec", "2d6296964956439addcc5c81116dbd5ac305ba39df4ad226f64fd87e0071c0af", "user", null, null, null, 0, null, null], ["93c6395c-dad5-4cce-b134-602f33b3b38f", "7ff052024bb9bb44730ac2198c4fe6c5faed9cb616841b5a53ccb8b11b252598", "char", null, null, null, 0, "b09b7305-d34c-40b5-91bd-7c643eb30338", null], ["967a0cf5-747c-4be7-b34f-97f8c7c59e6c", "3c734e5035b08eba037494548624e0d8b183da3c21d3e11a0a9f6dbca4a6c14d", "user", null, null, null, 0, null, null], ["fb317d3c-6e92-4ba9-9af5-31615178b3e2", "246f9eb3f0ecc2075df443f008b488d05ed6542583dce1fde8a017cd2baf1094", "char", null, null, null, 0, "fffce903-2a78-440d-9151-01c2b1cec7dd", null], ["1c8ade77-53f0-4fdf-b443-62f35da15666", "3ac9631b4849222c97d11449b951cb90f2a0affef6dbc28201155947c7590db7", "user", null, null, null, 0, null, null], ["a39302f1-0ad4-4bb8-baa4-4d0025688449", "099acc80013ea6ad29c6b463f4b34d8fc5c8b93620a9b56d29ede5587739b6d3", "char", null, null, null, 0, "8b77fdf5-98b3-4208-a699-323af0a1a49a", null], ["6e749dd6-4882-417e-b05c-29806e0ffa65", "5f7701648408f09cb0ee50ee25b55977904d52dc9138ed75c7791b211b5e8fff", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::273c4d94-f678-4f2d-9431-32a348078fde::Harbor route::8b77fdf5-98b3-4208-a699-323af0a1a49a::}}"]], ["0ac2227f-398f-4c1e-a306-c1584e7ae92c", "087971b168a1280adab5736fba4641f88c2e26729f7b1b085be3d2afa5ed25ea", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0e7b5-3aed-70ac-b486-85ac3a496f61:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3aed-70ac-b486-85ac3a496f61"}', 50, 'done', 1, '2026-09-28 11:10:09.132469+00', NULL, NULL, '2026-09-28 11:10:09.132469+00', '2026-09-28 11:10:10.214543+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0e7b5-3ac7-7cda-89b9-da652207eb88:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3ac7-7cda-89b9-da652207eb88"}', 50, 'done', 1, '2026-09-28 11:10:09.132469+00', NULL, NULL, '2026-09-28 11:10:09.132469+00', '2026-09-28 11:10:10.234755+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0e7b5-3ac7-7ade-b622-20874b69a4ca:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3ac7-7ade-b622-20874b69a4ca"}', 50, 'done', 1, '2026-09-28 11:10:09.092877+00', NULL, NULL, '2026-09-28 11:10:09.092877+00', '2026-09-28 11:10:10.255501+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0e7b5-3ac6-7eb4-859d-e986228c9a27:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27"}', 50, 'done', 1, '2026-09-28 11:10:09.092877+00', NULL, NULL, '2026-09-28 11:10:09.092877+00', '2026-09-28 11:10:10.275526+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0e7b5-3ac5-7be9-bb77-731a6f61d60e:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3ac5-7be9-bb77-731a6f61d60e"}', 50, 'done', 1, '2026-09-28 11:10:09.092877+00', NULL, NULL, '2026-09-28 11:10:09.092877+00', '2026-09-28 11:10:10.298418+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0e7b5-3a9f-7dbe-8771-40f2571b65f4:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3a9f-7dbe-8771-40f2571b65f4"}', 50, 'done', 1, '2026-09-28 11:10:09.092877+00', NULL, NULL, '2026-09-28 11:10:09.092877+00', '2026-09-28 11:10:10.31814+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0e7b5-3a9e-77e9-83c6-5d522c261db3:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3a9e-77e9-83c6-5d522c261db3"}', 50, 'done', 1, '2026-09-28 11:10:09.051769+00', NULL, NULL, '2026-09-28 11:10:09.051769+00', '2026-09-28 11:10:10.337475+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8"}', 50, 'done', 1, '2026-09-28 11:10:09.051769+00', NULL, NULL, '2026-09-28 11:10:09.051769+00', '2026-09-28 11:10:10.356879+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0e7b5-3a9c-7aac-8a54-d690d8eccf47:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3a9c-7aac-8a54-d690d8eccf47"}', 50, 'done', 1, '2026-09-28 11:10:09.051769+00', NULL, NULL, '2026-09-28 11:10:09.051769+00', '2026-09-28 11:10:10.376219+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7"}', 50, 'done', 1, '2026-09-28 11:10:09.051769+00', NULL, NULL, '2026-09-28 11:10:09.051769+00', '2026-09-28 11:10:10.395307+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0e7b5-3ac7-7cda-89b9-da652207eb88:55514c76f7f4bd1f659e11bc453a9ecb:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3ac7-7cda-89b9-da652207eb88", "window_hash": "55514c76f7f4bd1f659e11bc453a9ecb"}', 100, 'done', 1, '2026-09-28 11:10:09.132469+00', NULL, NULL, '2026-09-28 11:10:09.132469+00', '2026-09-28 11:10:10.42307+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0e7b5-3ac6-7eb4-859d-e986228c9a27:3d9674bc5f1ae9e2ec37c49e28fdd8df:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27", "window_hash": "3d9674bc5f1ae9e2ec37c49e28fdd8df"}', 100, 'done', 1, '2026-09-28 11:10:09.092877+00', NULL, NULL, '2026-09-28 11:10:09.092877+00', '2026-09-28 11:10:10.446155+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0e7b5-3a9f-7dbe-8771-40f2571b65f4:64ad7591f62fa2bb21572f0094006af2:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3a9f-7dbe-8771-40f2571b65f4", "window_hash": "64ad7591f62fa2bb21572f0094006af2"}', 100, 'done', 1, '2026-09-28 11:10:09.092877+00', NULL, NULL, '2026-09-28 11:10:09.092877+00', '2026-09-28 11:10:10.468995+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8:6546910496fc06d077d322014855afaa:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8", "window_hash": "6546910496fc06d077d322014855afaa"}', 100, 'done', 1, '2026-09-28 11:10:09.051769+00', NULL, NULL, '2026-09-28 11:10:09.051769+00', '2026-09-28 11:10:10.491332+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7:70b6b9ed880c7df131baa11169920449:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7", "window_hash": "70b6b9ed880c7df131baa11169920449"}', 100, 'done', 1, '2026-09-28 11:10:09.051769+00', NULL, NULL, '2026-09-28 11:10:09.051769+00', '2026-09-28 11:10:10.51714+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0e7b5-3a62-7da7-98a3-20cc432f5e29:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3a62-7da7-98a3-20cc432f5e29"}', 150, 'done', 1, '2026-09-28 11:10:08.990664+00', NULL, NULL, '2026-09-28 11:10:08.990664+00', '2026-09-28 11:10:10.535535+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0e7b5-3a61-7541-8ef3-af00948a55b1:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3a61-7541-8ef3-af00948a55b1"}', 150, 'done', 1, '2026-09-28 11:10:08.990664+00', NULL, NULL, '2026-09-28 11:10:08.990664+00', '2026-09-28 11:10:10.552996+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2"}', 150, 'done', 1, '2026-09-28 11:10:08.990664+00', NULL, NULL, '2026-09-28 11:10:08.990664+00', '2026-09-28 11:10:10.571838+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0e7b5-3a61-7541-8ef3-af00948a55b1:fbfe561ce3b5209d633073320d636bad:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3a61-7541-8ef3-af00948a55b1", "window_hash": "fbfe561ce3b5209d633073320d636bad"}', 200, 'done', 1, '2026-09-28 11:10:08.990664+00', NULL, NULL, '2026-09-28 11:10:08.990664+00', '2026-09-28 11:10:10.594771+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8:dd45b5db7fd73063aeed8e1740e42340:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8", "window_hash": "dd45b5db7fd73063aeed8e1740e42340"}', 100, 'done', 1, '2026-09-28 11:10:10.678219+00', NULL, NULL, '2026-09-28 11:10:10.678219+00', '2026-09-28 11:10:11.833769+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0e7b5-40f7-7a0a-94de-32aeacb1d05d:c35d8c77bf082ed17f74bdb1b4702cda:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-40f7-7a0a-94de-32aeacb1d05d", "window_hash": "c35d8c77bf082ed17f74bdb1b4702cda"}', 100, 'done', 1, '2026-09-28 11:10:10.678219+00', NULL, NULL, '2026-09-28 11:10:10.678219+00', '2026-09-28 11:10:11.855518+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0e7b5-475e-7ca9-bfe5-3104a630af49:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-475e-7ca9-bfe5-3104a630af49"}', 150, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:12.921022+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0e7b5-4147-7728-b54f-8a8e63e1bd36:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-4147-7728-b54f-8a8e63e1bd36"}', 50, 'done', 1, '2026-09-28 11:10:10.757055+00', NULL, NULL, '2026-09-28 11:10:10.757055+00', '2026-09-28 11:10:11.627884+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0e7b5-4146-7614-a731-50bd00f60138:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-4146-7614-a731-50bd00f60138"}', 50, 'done', 1, '2026-09-28 11:10:10.757055+00', NULL, NULL, '2026-09-28 11:10:10.757055+00', '2026-09-28 11:10:11.646361+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0e7b5-40f8-7295-b7ab-8713d3c2d900:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-40f8-7295-b7ab-8713d3c2d900"}', 50, 'done', 1, '2026-09-28 11:10:10.678219+00', NULL, NULL, '2026-09-28 11:10:10.678219+00', '2026-09-28 11:10:11.664898+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a"}', 50, 'done', 1, '2026-09-28 11:10:10.678219+00', NULL, NULL, '2026-09-28 11:10:10.678219+00', '2026-09-28 11:10:11.683947+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0e7b5-40f7-7a0a-94de-32aeacb1d05d:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-40f7-7a0a-94de-32aeacb1d05d"}', 50, 'done', 1, '2026-09-28 11:10:10.678219+00', NULL, NULL, '2026-09-28 11:10:10.678219+00', '2026-09-28 11:10:11.703581+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0e7b5-4146-7614-a731-50bd00f60138:e4ecdd33c7dd62c1259be9fb0d1bed8e:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-4146-7614-a731-50bd00f60138", "window_hash": "e4ecdd33c7dd62c1259be9fb0d1bed8e"}', 100, 'done', 1, '2026-09-28 11:10:10.757055+00', NULL, NULL, '2026-09-28 11:10:10.757055+00', '2026-09-28 11:10:11.725859+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a:fe093ed26daa1e45f2472c371bf5398b:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a", "window_hash": "fe093ed26daa1e45f2472c371bf5398b"}', 100, 'done', 1, '2026-09-28 11:10:10.757055+00', NULL, NULL, '2026-09-28 11:10:10.757055+00', '2026-09-28 11:10:11.751768+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0e7b5-3ac7-7cda-89b9-da652207eb88:ecf6193f9421be16c6fdec525b966b4e:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3ac7-7cda-89b9-da652207eb88", "window_hash": "ecf6193f9421be16c6fdec525b966b4e"}', 100, 'done', 1, '2026-09-28 11:10:10.757055+00', NULL, NULL, '2026-09-28 11:10:10.757055+00', '2026-09-28 11:10:11.774109+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0e7b5-3ac6-7eb4-859d-e986228c9a27:e7db7ae4358e2b3978e8f25aa4a49708:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27", "window_hash": "e7db7ae4358e2b3978e8f25aa4a49708"}', 100, 'done', 1, '2026-09-28 11:10:10.757055+00', NULL, NULL, '2026-09-28 11:10:10.757055+00', '2026-09-28 11:10:11.797809+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a:7ead75a0ce7791b9192c5cfa57931602:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a", "window_hash": "7ead75a0ce7791b9192c5cfa57931602"}', 100, 'obsolete', 1, '2026-09-28 11:10:10.678219+00', NULL, NULL, '2026-09-28 11:10:10.678219+00', '2026-09-28 11:10:11.801459+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0e7b5-3ac6-7eb4-859d-e986228c9a27:44041fd5765f6ecac7df330c58604cec:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27", "window_hash": "44041fd5765f6ecac7df330c58604cec"}', 100, 'obsolete', 1, '2026-09-28 11:10:10.678219+00', NULL, NULL, '2026-09-28 11:10:10.678219+00', '2026-09-28 11:10:11.805165+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0e7b5-3a9f-7dbe-8771-40f2571b65f4:f7198de2e71c90b3cc657773bfca3e2d:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-3a9f-7dbe-8771-40f2571b65f4", "window_hash": "f7198de2e71c90b3cc657773bfca3e2d"}', 100, 'obsolete', 1, '2026-09-28 11:10:10.678219+00', NULL, NULL, '2026-09-28 11:10:10.678219+00', '2026-09-28 11:10:11.808792+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0e7b5-475e-7ea5-b037-6ea4cbd2c043:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-475e-7ea5-b037-6ea4cbd2c043"}', 150, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:12.901978+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0e7b5-475d-7c6b-ab2b-f5b182101e1e:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-475d-7c6b-ab2b-f5b182101e1e"}', 150, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:12.943147+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0e7b5-475d-7029-8dd4-4008a06e11c7:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-475d-7029-8dd4-4008a06e11c7"}', 150, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:12.962449+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d"}', 150, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:12.980972+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0e7b5-475b-7ae0-93d8-858764b5d69f:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-475b-7ae0-93d8-858764b5d69f"}', 150, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:13.002475+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0e7b5-475e-7ea5-b037-6ea4cbd2c043:1c1279cb37937b8b600344efc2f91ae9:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-475e-7ea5-b037-6ea4cbd2c043", "window_hash": "1c1279cb37937b8b600344efc2f91ae9"}', 200, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:13.024006+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0e7b5-475d-7c6b-ab2b-f5b182101e1e:eb88aee802ef8caee91f06c6135a00d5:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-475d-7c6b-ab2b-f5b182101e1e", "window_hash": "eb88aee802ef8caee91f06c6135a00d5"}', 200, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:13.04796+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d:449f1ffb727cbca043aae2268a5fb168:extract-3805bf5bf9aa8cf5d10854c51b33fc51', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "extract-3805bf5bf9aa8cf5d10854c51b33fc51", "revision_id": "01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d", "window_hash": "449f1ffb727cbca043aae2268a5fb168"}', 200, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:13.070631+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0e7b5-475f-774f-af41-2e9c22520d9f:embed-787eaaec1a1eb094c1d3a82e29cd303f', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{"generation": "embed-787eaaec1a1eb094c1d3a82e29cd303f", "revision_id": "01a0e7b5-475f-774f-af41-2e9c22520d9f"}', 150, 'done', 1, '2026-09-28 11:10:12.314227+00', NULL, NULL, '2026-09-28 11:10:12.314227+00', '2026-09-28 11:10:12.882768+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0e7b5-3a65-7ce1-867d-3228b1264140', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'extract', 'stub', 'http://127.0.0.1:44559/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "a0de52e41b72df2c", "compiler": "extract-v13", "endpoint": "http://127.0.0.1:44559/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "a6511d2d7b4e2fca", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-28 11:10:08.835384+00', '2026-09-28 11:10:08.836524+00');
INSERT INTO public.projection_generation VALUES ('embed-787eaaec1a1eb094c1d3a82e29cd303f', 'embed', 'stub-embed', 'http://127.0.0.1:44559/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:44559/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-28 11:10:08.835384+00', '2026-09-28 11:10:08.840162+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-3a92-795e-9c2f-e57e0b728cd6', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '01a0e7b5-3a66-7692-ba35-05f400815f29', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b5-3a62-7da7-98a3-20cc432f5e29", "host_logical_id": "81718ea8-5069-4c34-868f-ea32146ea055"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b5-3a62-7da7-98a3-20cc432f5e29", "host_logical_id": "81718ea8-5069-4c34-868f-ea32146ea055"}]', 0, '{"fit": 0.0, "embed": 26.7, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 2.17, "fits_at": null, "lexical": 3.43, "threads": 0, "extractor": "extract-3805bf5bf9aa", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 36.34, "embedding_projection": "embed-787eaaec1a1eb0", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:09.005926+00', 'packet-v6', 600, 3, '', '["81718ea8-5069-4c34-868f-ea32146ea055", "b09b7305-d34c-40b5-91bd-7c643eb30338", "cd6a7cd4-cef5-4cd3-87ec-ddceb141921d", "fffce903-2a78-440d-9151-01c2b1cec7dd"]', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-3abc-7e45-aa5e-4ec0f47160a8', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '01a0e7b5-3a66-7692-ba35-05f400815f29', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b5-3a9e-77e9-83c6-5d522c261db3", "host_logical_id": "1acc7d2a-ade9-4534-ba82-12f94b551cfc"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b5-3a9e-77e9-83c6-5d522c261db3", "host_logical_id": "1acc7d2a-ade9-4534-ba82-12f94b551cfc"}]', 0, '{"fit": 0.0, "embed": 14.63, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 1.14, "fits_at": null, "lexical": 2.33, "threads": 0, "extractor": "extract-3805bf5bf9aa", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.49, "embedding_projection": "embed-787eaaec1a1eb0", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:09.063778+00', 'packet-v6', 600, 7, '', '["1acc7d2a-ade9-4534-ba82-12f94b551cfc", "8b77fdf5-98b3-4208-a699-323af0a1a49a", "8ddd2d3f-082e-4c86-b701-d9e5551378b2", "bdfdfc0e-f7d2-4291-ae20-336e934dae93"]', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-3ae3-7118-a77f-f2caae1d48e1', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '01a0e7b5-3a66-7692-ba35-05f400815f29', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b5-3ac7-7ade-b622-20874b69a4ca", "host_logical_id": "74af895d-9072-4a66-afe9-203bc958c798"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b5-3ac7-7ade-b622-20874b69a4ca", "host_logical_id": "74af895d-9072-4a66-afe9-203bc958c798"}]', 0, '{"fit": 0.0, "embed": 14.12, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0}, "vector": 0.99, "fits_at": null, "lexical": 2.23, "threads": 0, "extractor": "extract-3805bf5bf9aa", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.61, "embedding_projection": "embed-787eaaec1a1eb0", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:09.104032+00', 'packet-v6', 600, 11, '', '["74af895d-9072-4a66-afe9-203bc958c798", "7bf2ca56-5816-4653-983f-ec3ec2cf6371", "dc887fc7-2665-469c-8a75-2d4f5924b37f", "f169d7c1-1029-413d-85a4-8126d286cdf8"]', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-3b07-7cad-9188-89b052053fbb', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '01a0e7b5-3a66-7692-ba35-05f400815f29', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b5-3aed-70ac-b486-85ac3a496f61", "host_logical_id": "965ae0c4-23c1-4938-9596-33cc710c64e0"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7", "host_logical_id": "fffce903-2a78-440d-9151-01c2b1cec7dd"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0e7b5-3a61-7541-8ef3-af00948a55b1", "host_logical_id": "b09b7305-d34c-40b5-91bd-7c643eb30338"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0e7b5-3a61-7541-8ef3-af00948a55b1"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b5-3aed-70ac-b486-85ac3a496f61", "host_logical_id": "965ae0c4-23c1-4938-9596-33cc710c64e0"}]', 174, '{"fit": 0.0, "embed": 13.34, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 0.73, "fits_at": null, "lexical": 2.22, "threads": 0, "extractor": "extract-3805bf5bf9aa", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 18.56, "embedding_projection": "embed-787eaaec1a1eb0", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:09.140609+00', 'packet-v6', 600, 12, '', '["74af895d-9072-4a66-afe9-203bc958c798", "965ae0c4-23c1-4938-9596-33cc710c64e0", "dc887fc7-2665-469c-8a75-2d4f5924b37f", "f169d7c1-1029-413d-85a4-8126d286cdf8"]', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 3, "placed": true}, {"ref": {"revision": "01a0e7b5-3a61-7541-8ef3-af00948a55b1"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-4115-71eb-8fc3-6f3452647dbb', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '01a0e7b5-40fc-7b02-b25a-d03420f925b9', 'And the compass?', '[{"rrf": 0.03128, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27", "host_logical_id": "dc887fc7-2665-469c-8a75-2d4f5924b37f"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-40f8-7295-b7ab-8713d3c2d900", "host_logical_id": "29ce81c7-0c6b-4723-8c59-c9ed706aecb9"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0e7b5-3a61-7541-8ef3-af00948a55b1", "host_logical_id": "b09b7305-d34c-40b5-91bd-7c643eb30338"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2", "host_logical_id": "cd6a7cd4-cef5-4cd3-87ec-ddceb141921d"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0e7b5-3a9f-7dbe-8771-40f2571b65f4", "host_logical_id": "8ddd2d3f-082e-4c86-b701-d9e5551378b2"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8", "host_logical_id": "8b77fdf5-98b3-4208-a699-323af0a1a49a"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0e7b5-3a61-7541-8ef3-af00948a55b1"}, {"turn": 5, "score": 0.01562, "revision_id": "01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0e7b5-3a9f-7dbe-8771-40f2571b65f4"}, {"turn": 9, "score": 0.03128, "revision_id": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-40f8-7295-b7ab-8713d3c2d900", "host_logical_id": "29ce81c7-0c6b-4723-8c59-c9ed706aecb9"}]', 252, '{"fit": 0.0, "embed": 14.3, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 5}, "vector": 0.95, "fits_at": null, "lexical": 2.08, "threads": 0, "extractor": "extract-3805bf5bf9aa", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.93, "embedding_projection": "embed-787eaaec1a1eb0", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:10.689275+00', 'packet-v6', 600, 14, '', '["29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "78c92f7d-ba33-47d3-b467-ddebbc064a14", "965ae0c4-23c1-4938-9596-33cc710c64e0", "f169d7c1-1029-413d-85a4-8126d286cdf8"]', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e7b5-3a61-7541-8ef3-af00948a55b1"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 1, "placed": true}, {"ref": {"revision": "01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a0e7b5-3a9f-7dbe-8771-40f2571b65f4"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 7, "placed": true}, {"ref": {"revision": "01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 5, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-413b-7c83-b096-1d11efc0a20b', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '01a0e7b5-40fc-7b02-b25a-d03420f925b9', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27", "host_logical_id": "dc887fc7-2665-469c-8a75-2d4f5924b37f"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-40f8-7295-b7ab-8713d3c2d900", "host_logical_id": "29ce81c7-0c6b-4723-8c59-c9ed706aecb9"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0e7b5-3ac7-7cda-89b9-da652207eb88", "host_logical_id": "f169d7c1-1029-413d-85a4-8126d286cdf8"}]', '[{"turn": 9, "score": 0.03002, "revision_id": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27"}, {"turn": 11, "score": 0.01639, "revision_id": "01a0e7b5-3ac7-7cda-89b9-da652207eb88"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b5-40f8-7295-b7ab-8713d3c2d900", "host_logical_id": "29ce81c7-0c6b-4723-8c59-c9ed706aecb9"}]', 171, '{"fit": 0.0, "embed": 13.69, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 1.02, "fits_at": null, "lexical": 2.81, "threads": 0, "extractor": "extract-3805bf5bf9aa", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.73, "embedding_projection": "embed-787eaaec1a1eb0", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:10.726513+00', 'packet-v6', 600, 15, '', '["29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "77b2a637-a479-4e62-82dd-35e47dcaa59d", "78c92f7d-ba33-47d3-b467-ddebbc064a14", "965ae0c4-23c1-4938-9596-33cc710c64e0"]', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-3ac6-7eb4-859d-e986228c9a27"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 9, "placed": true}, {"ref": {"revision": "01a0e7b5-3ac7-7cda-89b9-da652207eb88"}, "tok": 24, "why": "placed", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 11, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-4162-7dac-8118-3895830265f6', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '01a0e7b5-4149-7dcd-b605-35f011c51c62', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0e7b5-3a9e-77e9-83c6-5d522c261db3", "host_logical_id": "1acc7d2a-ade9-4534-ba82-12f94b551cfc"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b5-4147-7728-b54f-8a8e63e1bd36", "host_logical_id": "a527db9f-94c6-4a56-b7cb-37a165ffc0ea"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0e7b5-3a9e-77e9-83c6-5d522c261db3"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b5-4147-7728-b54f-8a8e63e1bd36", "host_logical_id": "a527db9f-94c6-4a56-b7cb-37a165ffc0ea"}]', 138, '{"fit": 0.0, "embed": 14.41, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1}, "vector": 0.85, "fits_at": null, "lexical": 2.61, "threads": 0, "extractor": "extract-3805bf5bf9aa", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 20.02, "embedding_projection": "embed-787eaaec1a1eb0", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:10.766712+00', 'packet-v6', 600, 16, '', '["29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "77b2a637-a479-4e62-82dd-35e47dcaa59d", "78c92f7d-ba33-47d3-b467-ddebbc064a14", "a527db9f-94c6-4a56-b7cb-37a165ffc0ea"]', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-3a9e-77e9-83c6-5d522c261db3"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 6, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b5-4779-7bc1-829e-b80c9026741b', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '01a0e7b5-4761-702d-8954-459e9a0380e9', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0e7b5-475d-7029-8dd4-4008a06e11c7", "host_logical_id": "967a0cf5-747c-4be7-b34f-97f8c7c59e6c"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0e7b5-475d-7c6b-ab2b-f5b182101e1e", "host_logical_id": "fb317d3c-6e92-4ba9-9af5-31615178b3e2"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0e7b5-475d-7029-8dd4-4008a06e11c7"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b5-475d-7c6b-ab2b-f5b182101e1e"}]', '[]', 164, '{"fit": 0.0, "embed": 14.01, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2}, "vector": 0.74, "fits_at": null, "lexical": 2.58, "threads": 0, "extractor": "extract-3805bf5bf9aa", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 19.33, "embedding_projection": "embed-787eaaec1a1eb0", "memory_mode_withheld": 0}', 'fresh', '2026-09-28 11:10:12.326717+00', 'packet-v6', 600, 7, '', '["0ac2227f-398f-4c1e-a306-c1584e7ae92c", "1c8ade77-53f0-4fdf-b443-62f35da15666", "6e749dd6-4882-417e-b05c-29806e0ffa65", "a39302f1-0ad4-4bb8-baa4-4d0025688449"]', 'extract-3805bf5bf9aa8cf5d10854c51b33fc51', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0e7b5-475d-7029-8dd4-4008a06e11c7"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 2, "placed": true}, {"ref": {"revision": "01a0e7b5-475d-7c6b-ab2b-f5b182101e1e"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 3, "placed": true}]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3aed-70ac-b486-85ac3a496f61', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.211849+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3ac7-7cda-89b9-da652207eb88', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.233328+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3ac7-7ade-b622-20874b69a4ca', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.253907+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3ac6-7eb4-859d-e986228c9a27', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.274046+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3ac5-7be9-bb77-731a6f61d60e', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.296788+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3a9f-7dbe-8771-40f2571b65f4', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.316623+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3a9e-77e9-83c6-5d522c261db3', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.336122+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.355522+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3a9c-7aac-8a54-d690d8eccf47', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.37482+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.393879+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3a62-7da7-98a3-20cc432f5e29', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.534178+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3a61-7541-8ef3-af00948a55b1', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.551548+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:10.570501+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-4147-7728-b54f-8a8e63e1bd36', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:11.626306+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-4146-7614-a731-50bd00f60138', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:11.644991+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-40f8-7295-b7ab-8713d3c2d900', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:11.66355+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:11.682603+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-40f7-7a0a-94de-32aeacb1d05d', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:11.702138+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-475f-774f-af41-2e9c22520d9f', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:12.881317+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-475e-7ea5-b037-6ea4cbd2c043', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:12.900486+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-475e-7ca9-bfe5-3104a630af49', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:12.919645+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-475d-7c6b-ab2b-f5b182101e1e', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:12.941794+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-475d-7029-8dd4-4008a06e11c7', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:12.961116+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:12.979563+00');
INSERT INTO public.revision_embedding VALUES ('01a0e7b5-475b-7ae0-93d8-858764b5d69f', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-787eaaec1a1eb094c1d3a82e29cd303f', '2026-09-28 11:10:13.000839+00');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:10:08.990664+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3a61-7541-8ef3-af00948a55b1', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:10:08.990664+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3a62-7da7-98a3-20cc432f5e29', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-28 11:10:08.990664+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-28 11:10:08.990664+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3a9c-7aac-8a54-d690d8eccf47', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:10:09.051769+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:10:09.051769+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3a9e-77e9-83c6-5d522c261db3', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-09-28 11:10:09.051769+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3a9f-7dbe-8771-40f2571b65f4', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-28 11:10:09.051769+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3ac5-7be9-bb77-731a6f61d60e', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-28 11:10:09.092877+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3ac6-7eb4-859d-e986228c9a27', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-28 11:10:09.092877+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3ac7-7ade-b622-20874b69a4ca', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-09-28 11:10:09.092877+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3ac7-7cda-89b9-da652207eb88', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-09-28 11:10:09.092877+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-3aed-70ac-b486-85ac3a496f61', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-09-28 11:10:09.132469+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-40f7-7a0a-94de-32aeacb1d05d', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:10:10.678219+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-09-28 11:10:10.678219+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-40f8-7295-b7ab-8713d3c2d900', 'clean-v3', 'And the compass?', 16, 16, '2026-09-28 11:10:10.678219+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-411f-7f56-8818-f5385a83f5f5', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-28 11:10:10.718855+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-4145-7a6d-982f-4fc83be5a34e', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-28 11:10:10.757055+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-4146-7614-a731-50bd00f60138', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-09-28 11:10:10.757055+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-4147-7728-b54f-8a8e63e1bd36', 'clean-v3', 'Let''s go.', 9, 9, '2026-09-28 11:10:10.757055+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-475b-7ae0-93d8-858764b5d69f', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:10:12.314227+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:10:12.314227+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-475d-7029-8dd4-4008a06e11c7', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-28 11:10:12.314227+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-475d-7c6b-ab2b-f5b182101e1e', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:10:12.314227+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-475e-7ca9-bfe5-3104a630af49', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:10:12.314227+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-475e-7ea5-b037-6ea4cbd2c043', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:10:12.314227+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-475f-7c40-b005-0ffe47093d8f', 'clean-v3', '{{specialcomment::branchedfrom::273c4d94-f678-4f2d-9431-32a348078fde::Harbor route::8b77fdf5-98b3-4208-a699-323af0a1a49a::}}', 124, 124, '2026-09-28 11:10:12.314227+00');
INSERT INTO public.revision_text VALUES ('01a0e7b5-475f-774f-af41-2e9c22520d9f', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-09-28 11:10:12.314227+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-28 11:10:08.047844+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-28 11:10:08.126202+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-28 11:10:08.143393+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-28 11:10:08.185043+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-28 11:10:08.205572+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-28 11:10:08.215611+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-28 11:10:08.217622+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-28 11:10:08.228092+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-28 11:10:08.244966+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-28 11:10:08.246877+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-28 11:10:08.248399+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-28 11:10:08.256933+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-28 11:10:08.281518+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-28 11:10:08.299706+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-28 11:10:08.302458+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-28 11:10:08.314957+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-28 11:10:08.316781+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-28 11:10:08.318908+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-09-28 11:10:08.320509+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-09-28 11:10:08.333439+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-09-28 11:10:08.335914+00');
INSERT INTO public.schema_migrations VALUES ('0022_thread_outcome_and_cause.sql', '9a8507f1b42457d2c44d568a2bd60d868f923613f8c83acb2be7f9104041cc88', '2026-09-28 11:10:08.337681+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0e7b5-3a5f-77da-9e39-b2519372ac8c', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'cd6a7cd4-cef5-4cd3-87ec-ddceb141921d', 'message', '2026-09-28 11:10:08.990664+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3a61-71b4-a605-abfc8ed223f1', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'b09b7305-d34c-40b5-91bd-7c643eb30338', 'message', '2026-09-28 11:10:08.990664+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3a62-74d7-afb7-aaeba464bca8', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '81718ea8-5069-4c34-868f-ea32146ea055', 'message', '2026-09-28 11:10:08.990664+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3a63-77fe-aaf6-fd9a98aa3113', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'fffce903-2a78-440d-9151-01c2b1cec7dd', 'message', '2026-09-28 11:10:08.990664+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3a9c-772f-9c89-231e0717bacf', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'bdfdfc0e-f7d2-4291-ae20-336e934dae93', 'message', '2026-09-28 11:10:09.051769+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3a9d-71da-9631-12e2cebadadc', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '8b77fdf5-98b3-4208-a699-323af0a1a49a', 'message', '2026-09-28 11:10:09.051769+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3a9e-7e8c-808d-5c12f4c2d3f9', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '1acc7d2a-ade9-4534-ba82-12f94b551cfc', 'message', '2026-09-28 11:10:09.051769+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3a9f-72e4-903b-73e707d6bf62', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '8ddd2d3f-082e-4c86-b701-d9e5551378b2', 'message', '2026-09-28 11:10:09.051769+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3ac5-702c-9e69-46c50cca6921', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '7bf2ca56-5816-4653-983f-ec3ec2cf6371', 'message', '2026-09-28 11:10:09.092877+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3ac6-7fa9-8f35-4932a03ae4a0', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'dc887fc7-2665-469c-8a75-2d4f5924b37f', 'message', '2026-09-28 11:10:09.092877+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3ac6-7cb0-ba38-dade94ee2f16', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '74af895d-9072-4a66-afe9-203bc958c798', 'message', '2026-09-28 11:10:09.092877+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3ac7-7ebe-8bde-1afa9bc8bc15', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'f169d7c1-1029-413d-85a4-8126d286cdf8', 'message', '2026-09-28 11:10:09.092877+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-3aed-7e03-ba7f-e880ca1e895e', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '965ae0c4-23c1-4938-9596-33cc710c64e0', 'message', '2026-09-28 11:10:09.132469+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-40f7-7d49-aeef-4d618d91cec4', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '78c92f7d-ba33-47d3-b467-ddebbc064a14', 'message', '2026-09-28 11:10:10.678219+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-40f8-764e-ae02-bc7b9c23167d', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '29ce81c7-0c6b-4723-8c59-c9ed706aecb9', 'message', '2026-09-28 11:10:10.678219+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-411f-7d1c-9fa3-4c56f79ae1d9', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '77b2a637-a479-4e62-82dd-35e47dcaa59d', 'message', '2026-09-28 11:10:10.718855+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-4146-702f-8dfd-c508d59930c8', '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', 'a527db9f-94c6-4a56-b7cb-37a165ffc0ea', 'message', '2026-09-28 11:10:10.757055+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-475a-74cb-b49b-7d430b3ee4e6', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '9a7613c9-3840-45c9-96ea-6eff41ed4fec', 'message', '2026-09-28 11:10:12.314227+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-475b-7fbd-bb28-d544d1053ea8', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '93c6395c-dad5-4cce-b134-602f33b3b38f', 'message', '2026-09-28 11:10:12.314227+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-475c-7c28-9696-9b23f03918ac', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '967a0cf5-747c-4be7-b34f-97f8c7c59e6c', 'message', '2026-09-28 11:10:12.314227+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-475d-7af3-bcea-c27e314e212e', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', 'fb317d3c-6e92-4ba9-9af5-31615178b3e2', 'message', '2026-09-28 11:10:12.314227+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-475d-74b5-aee0-52bd81903197', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '1c8ade77-53f0-4fdf-b443-62f35da15666', 'message', '2026-09-28 11:10:12.314227+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-475e-785d-8674-1fdbc3d5478d', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', 'a39302f1-0ad4-4bb8-baa4-4d0025688449', 'message', '2026-09-28 11:10:12.314227+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-475f-733b-95d7-e1ad0dde32f8', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '6e749dd6-4882-417e-b05c-29806e0ffa65', 'message', '2026-09-28 11:10:12.314227+00');
INSERT INTO public.source_object VALUES ('01a0e7b5-475f-7ff5-bd6d-b69b25570af1', '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '0ac2227f-398f-4c1e-a306-c1584e7ae92c', 'message', '2026-09-28 11:10:12.314227+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0e7b5-3a5f-753a-a4a0-f0d473f66fb2', '01a0e7b5-3a5f-77da-9e39-b2519372ac8c', '9fd8ea9fcb1339d6dac5f9cfcb978080ad41f3b1279b9fd2ca5f93633be78336', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "cd6a7cd4-cef5-4cd3-87ec-ddceb141921d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:08.990664+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3a62-7da7-98a3-20cc432f5e29', '01a0e7b5-3a62-74d7-afb7-aaeba464bca8', '86f6c6d3ae8a645cc7fc25e8c7b7292b1ff8802e9884260a5f1a322be8f9e03e', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "81718ea8-5069-4c34-868f-ea32146ea055", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:08.990664+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3a61-7541-8ef3-af00948a55b1', '01a0e7b5-3a61-71b4-a605-abfc8ed223f1', 'ab1049189a29d91bcc8b4128e4a6da70b4f67e68536ba5ab078dfa6dcbe6132c', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "b09b7305-d34c-40b5-91bd-7c643eb30338", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b09b7305-d34c-40b5-91bd-7c643eb30338", "specialComments": []}', '2026-09-28 11:10:08.990664+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3a9c-7aac-8a54-d690d8eccf47', '01a0e7b5-3a9c-772f-9c89-231e0717bacf', 'c0b71332b0cf65b6dbb244c0a277bcbb5e17377a3acf2415336ba58780c32cf9', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "bdfdfc0e-f7d2-4291-ae20-336e934dae93", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:09.051769+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3a9e-77e9-83c6-5d522c261db3', '01a0e7b5-3a9e-7e8c-808d-5c12f4c2d3f9', 'bc261e8aa34452c97b82310565001bf2fb3fed2d9aaaced71f165de77971b094', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "1acc7d2a-ade9-4534-ba82-12f94b551cfc", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:09.051769+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3a9d-76c9-9686-2c6cd7e9a8c8', '01a0e7b5-3a9d-71da-9631-12e2cebadadc', '2d4285c87770b28e17a967f6c78e4eca34852188b8b7c10e55e230adf9b0577b', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "8b77fdf5-98b3-4208-a699-323af0a1a49a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "8b77fdf5-98b3-4208-a699-323af0a1a49a", "specialComments": []}', '2026-09-28 11:10:09.051769+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3ac5-7be9-bb77-731a6f61d60e', '01a0e7b5-3ac5-702c-9e69-46c50cca6921', 'a87d844f3b5885683b2838b1bf79b713e7746934d17d449ccdcab740f4dd4708', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "7bf2ca56-5816-4653-983f-ec3ec2cf6371", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:09.092877+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3ac7-7ade-b622-20874b69a4ca', '01a0e7b5-3ac6-7cb0-ba38-dade94ee2f16', 'b86dd570e65f136840bffc3b0bc3400b2c549b7f3f1986d624d37fe55a6e9578', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "74af895d-9072-4a66-afe9-203bc958c798", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:09.092877+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3a9f-7dbe-8771-40f2571b65f4', '01a0e7b5-3a9f-72e4-903b-73e707d6bf62', '2c6cb12da146d099782d13d1f93220d7f2d0bb9d05b4dfb4123735dc1f44c177', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "8ddd2d3f-082e-4c86-b701-d9e5551378b2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "8ddd2d3f-082e-4c86-b701-d9e5551378b2", "specialComments": []}', '2026-09-28 11:10:09.051769+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3ac6-7eb4-859d-e986228c9a27', '01a0e7b5-3ac6-7fa9-8f35-4932a03ae4a0', '7088c1d9881a9be48c6fe4a3dad533ca841c8d620b66b75a0007022074158a11', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "dc887fc7-2665-469c-8a75-2d4f5924b37f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "dc887fc7-2665-469c-8a75-2d4f5924b37f", "specialComments": []}', '2026-09-28 11:10:09.092877+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3aed-70ac-b486-85ac3a496f61', '01a0e7b5-3aed-7e03-ba7f-e880ca1e895e', 'fbe7c95481a9557ff14948e09c8137b3b3cbbb1b0b8449cf4c3f9fa8afdbf7b8', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "965ae0c4-23c1-4938-9596-33cc710c64e0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:09.132469+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3ac7-7cda-89b9-da652207eb88', '01a0e7b5-3ac7-7ebe-8bde-1afa9bc8bc15', '4152861dab5e6d52abeea22477540e178ed0d2a12b9f57b86cc6e24fde70d11b', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "f169d7c1-1029-413d-85a4-8126d286cdf8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "f169d7c1-1029-413d-85a4-8126d286cdf8", "specialComments": []}', '2026-09-28 11:10:09.092877+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-40f8-7295-b7ab-8713d3c2d900', '01a0e7b5-40f8-764e-ae02-bc7b9c23167d', '8109b743a1f2e3179c85e3c6acd33315afe7dee42ddd7213746213cb68e6ab35', 'And the compass?', '{"name": null, "role": "user", "chatId": "29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:10.678219+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-40f8-729f-84b1-e74a4dc6cd0a', '01a0e7b5-40f7-7d49-aeef-4d618d91cec4', 'd8af5de848a7718bf3c5a8b0de5a56c295194fe23068cca0254a88dcf307281e', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "78c92f7d-ba33-47d3-b467-ddebbc064a14", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "78c92f7d-ba33-47d3-b467-ddebbc064a14", "specialComments": []}', '2026-09-28 11:10:10.678219+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-40f7-7a0a-94de-32aeacb1d05d', '01a0e7b5-3a63-77fe-aaf6-fd9a98aa3113', '58427731059beac6d93a54ef95c418a477fcc3952493896b546a110049cd3283', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "fffce903-2a78-440d-9151-01c2b1cec7dd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "fffce903-2a78-440d-9151-01c2b1cec7dd", "specialComments": []}', '2026-09-28 11:10:10.678219+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-3a63-72ec-b3c3-f50ae5343ff7', '01a0e7b5-3a63-77fe-aaf6-fd9a98aa3113', '5b7fc56ebffee128ba1e60d26b33b69a3a78d0d410537802c5a4670215af61ec', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "fffce903-2a78-440d-9151-01c2b1cec7dd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "fffce903-2a78-440d-9151-01c2b1cec7dd", "specialComments": []}', '2026-09-28 11:10:08.990664+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-4145-7a6d-982f-4fc83be5a34e', '01a0e7b5-3ac5-702c-9e69-46c50cca6921', '2cdd1e15085b18e3fc68359e69f6aa28ac70895f5d6e447582e18c36bf5d8bcd', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "7bf2ca56-5816-4653-983f-ec3ec2cf6371", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:10.757055+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-4147-7728-b54f-8a8e63e1bd36', '01a0e7b5-4146-702f-8dfd-c508d59930c8', '47c57607d693a652099e95dcd63fb8fd0cd1575a9f8a7fd362692d8d88867d13', 'Let''s go.', '{"name": null, "role": "user", "chatId": "a527db9f-94c6-4a56-b7cb-37a165ffc0ea", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:10.757055+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-411f-7f56-8818-f5385a83f5f5', '01a0e7b5-411f-7d1c-9fa3-4c56f79ae1d9', '61b3b9c346c3724ff9a069be8e036f2d4dc2fce88085d9d19c4c36c702fe02a6', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "77b2a637-a479-4e62-82dd-35e47dcaa59d", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "77b2a637-a479-4e62-82dd-35e47dcaa59d", "specialComments": []}', '2026-09-28 11:10:10.718855+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-4146-7614-a731-50bd00f60138', '01a0e7b5-411f-7d1c-9fa3-4c56f79ae1d9', 'b85e6e8be367ca14b7c34ec0194c9ca8fdcc51967e0d48814e7496a0d13101a2', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "77b2a637-a479-4e62-82dd-35e47dcaa59d", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "77b2a637-a479-4e62-82dd-35e47dcaa59d", "specialComments": []}', '2026-09-28 11:10:10.757055+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-475b-7ae0-93d8-858764b5d69f', '01a0e7b5-475a-74cb-b49b-7d430b3ee4e6', '2d6296964956439addcc5c81116dbd5ac305ba39df4ad226f64fd87e0071c0af', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "9a7613c9-3840-45c9-96ea-6eff41ed4fec", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:12.314227+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-475d-7029-8dd4-4008a06e11c7', '01a0e7b5-475c-7c28-9696-9b23f03918ac', '3c734e5035b08eba037494548624e0d8b183da3c21d3e11a0a9f6dbca4a6c14d', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "967a0cf5-747c-4be7-b34f-97f8c7c59e6c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:12.314227+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-475e-7ca9-bfe5-3104a630af49', '01a0e7b5-475d-74b5-aee0-52bd81903197', '3ac9631b4849222c97d11449b951cb90f2a0affef6dbc28201155947c7590db7', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "1c8ade77-53f0-4fdf-b443-62f35da15666", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:12.314227+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-475f-7c40-b005-0ffe47093d8f', '01a0e7b5-475f-733b-95d7-e1ad0dde32f8', '5f7701648408f09cb0ee50ee25b55977904d52dc9138ed75c7791b211b5e8fff', '{{specialcomment::branchedfrom::273c4d94-f678-4f2d-9431-32a348078fde::Harbor route::8b77fdf5-98b3-4208-a699-323af0a1a49a::}}', '{"name": null, "role": "char", "chatId": "6e749dd6-4882-417e-b05c-29806e0ffa65", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::273c4d94-f678-4f2d-9431-32a348078fde::Harbor route::8b77fdf5-98b3-4208-a699-323af0a1a49a::}}"]}', '2026-09-28 11:10:12.314227+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-475f-774f-af41-2e9c22520d9f', '01a0e7b5-475f-7ff5-bd6d-b69b25570af1', '087971b168a1280adab5736fba4641f88c2e26729f7b1b085be3d2afa5ed25ea', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "0ac2227f-398f-4c1e-a306-c1584e7ae92c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:10:12.314227+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-475c-7c28-ae1a-37c9de4c5c2d', '01a0e7b5-475b-7fbd-bb28-d544d1053ea8', '7ff052024bb9bb44730ac2198c4fe6c5faed9cb616841b5a53ccb8b11b252598', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "93c6395c-dad5-4cce-b134-602f33b3b38f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b09b7305-d34c-40b5-91bd-7c643eb30338", "specialComments": []}', '2026-09-28 11:10:12.314227+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-475e-7ea5-b037-6ea4cbd2c043', '01a0e7b5-475e-785d-8674-1fdbc3d5478d', '099acc80013ea6ad29c6b463f4b34d8fc5c8b93620a9b56d29ede5587739b6d3', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "a39302f1-0ad4-4bb8-baa4-4d0025688449", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "8b77fdf5-98b3-4208-a699-323af0a1a49a", "specialComments": []}', '2026-09-28 11:10:12.314227+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b5-475d-7c6b-ab2b-f5b182101e1e', '01a0e7b5-475d-7af3-bcea-c27e314e212e', '246f9eb3f0ecc2075df443f008b488d05ed6542583dce1fde8a017cd2baf1094', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "fb317d3c-6e92-4ba9-9af5-31615178b3e2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "fffce903-2a78-440d-9151-01c2b1cec7dd", "specialComments": []}', '2026-09-28 11:10:12.314227+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0e7b5-3a66-7692-ba35-05f400815f29', '[{"op": "insert", "after": ["fffce903-2a78-440d-9151-01c2b1cec7dd", "5b7fc56ebffee128ba1e60d26b33b69a3a78d0d410537802c5a4670215af61ec"], "member": ["bdfdfc0e-f7d2-4291-ae20-336e934dae93", "c0b71332b0cf65b6dbb244c0a277bcbb5e17377a3acf2415336ba58780c32cf9"]}, {"op": "insert", "after": ["bdfdfc0e-f7d2-4291-ae20-336e934dae93", "c0b71332b0cf65b6dbb244c0a277bcbb5e17377a3acf2415336ba58780c32cf9"], "member": ["8b77fdf5-98b3-4208-a699-323af0a1a49a", "2d4285c87770b28e17a967f6c78e4eca34852188b8b7c10e55e230adf9b0577b"]}, {"op": "insert", "after": ["8b77fdf5-98b3-4208-a699-323af0a1a49a", "2d4285c87770b28e17a967f6c78e4eca34852188b8b7c10e55e230adf9b0577b"], "member": ["1acc7d2a-ade9-4534-ba82-12f94b551cfc", "bc261e8aa34452c97b82310565001bf2fb3fed2d9aaaced71f165de77971b094"]}, {"op": "insert", "after": ["1acc7d2a-ade9-4534-ba82-12f94b551cfc", "bc261e8aa34452c97b82310565001bf2fb3fed2d9aaaced71f165de77971b094"], "member": ["8ddd2d3f-082e-4c86-b701-d9e5551378b2", "2c6cb12da146d099782d13d1f93220d7f2d0bb9d05b4dfb4123735dc1f44c177"]}]', '[{"new": ["bdfdfc0e-f7d2-4291-ae20-336e934dae93", "c0b71332b0cf65b6dbb244c0a277bcbb5e17377a3acf2415336ba58780c32cf9"], "old": null, "kind": "append", "position": 4, "host_logical_id": "bdfdfc0e-f7d2-4291-ae20-336e934dae93"}, {"new": ["8b77fdf5-98b3-4208-a699-323af0a1a49a", "2d4285c87770b28e17a967f6c78e4eca34852188b8b7c10e55e230adf9b0577b"], "old": null, "kind": "append", "position": 5, "host_logical_id": "8b77fdf5-98b3-4208-a699-323af0a1a49a"}, {"new": ["1acc7d2a-ade9-4534-ba82-12f94b551cfc", "bc261e8aa34452c97b82310565001bf2fb3fed2d9aaaced71f165de77971b094"], "old": null, "kind": "append", "position": 6, "host_logical_id": "1acc7d2a-ade9-4534-ba82-12f94b551cfc"}, {"new": ["8ddd2d3f-082e-4c86-b701-d9e5551378b2", "2c6cb12da146d099782d13d1f93220d7f2d0bb9d05b4dfb4123735dc1f44c177"], "old": null, "kind": "append", "position": 7, "host_logical_id": "8ddd2d3f-082e-4c86-b701-d9e5551378b2"}]', '01a0e7b5-3aa2-7bec-9e4e-8f4cea82b6c4', '2026-09-28 11:10:09.051769+00');
INSERT INTO public.worldline_append VALUES (2, '01a0e7b5-3a66-7692-ba35-05f400815f29', '[{"op": "insert", "after": ["8ddd2d3f-082e-4c86-b701-d9e5551378b2", "2c6cb12da146d099782d13d1f93220d7f2d0bb9d05b4dfb4123735dc1f44c177"], "member": ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "a87d844f3b5885683b2838b1bf79b713e7746934d17d449ccdcab740f4dd4708"]}, {"op": "insert", "after": ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "a87d844f3b5885683b2838b1bf79b713e7746934d17d449ccdcab740f4dd4708"], "member": ["dc887fc7-2665-469c-8a75-2d4f5924b37f", "7088c1d9881a9be48c6fe4a3dad533ca841c8d620b66b75a0007022074158a11"]}, {"op": "insert", "after": ["dc887fc7-2665-469c-8a75-2d4f5924b37f", "7088c1d9881a9be48c6fe4a3dad533ca841c8d620b66b75a0007022074158a11"], "member": ["74af895d-9072-4a66-afe9-203bc958c798", "b86dd570e65f136840bffc3b0bc3400b2c549b7f3f1986d624d37fe55a6e9578"]}, {"op": "insert", "after": ["74af895d-9072-4a66-afe9-203bc958c798", "b86dd570e65f136840bffc3b0bc3400b2c549b7f3f1986d624d37fe55a6e9578"], "member": ["f169d7c1-1029-413d-85a4-8126d286cdf8", "4152861dab5e6d52abeea22477540e178ed0d2a12b9f57b86cc6e24fde70d11b"]}]', '[{"new": ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "a87d844f3b5885683b2838b1bf79b713e7746934d17d449ccdcab740f4dd4708"], "old": null, "kind": "append", "position": 8, "host_logical_id": "7bf2ca56-5816-4653-983f-ec3ec2cf6371"}, {"new": ["dc887fc7-2665-469c-8a75-2d4f5924b37f", "7088c1d9881a9be48c6fe4a3dad533ca841c8d620b66b75a0007022074158a11"], "old": null, "kind": "append", "position": 9, "host_logical_id": "dc887fc7-2665-469c-8a75-2d4f5924b37f"}, {"new": ["74af895d-9072-4a66-afe9-203bc958c798", "b86dd570e65f136840bffc3b0bc3400b2c549b7f3f1986d624d37fe55a6e9578"], "old": null, "kind": "append", "position": 10, "host_logical_id": "74af895d-9072-4a66-afe9-203bc958c798"}, {"new": ["f169d7c1-1029-413d-85a4-8126d286cdf8", "4152861dab5e6d52abeea22477540e178ed0d2a12b9f57b86cc6e24fde70d11b"], "old": null, "kind": "append", "position": 11, "host_logical_id": "f169d7c1-1029-413d-85a4-8126d286cdf8"}]', '01a0e7b5-3aca-7442-bc84-85da6c5fdfa3', '2026-09-28 11:10:09.092877+00');
INSERT INTO public.worldline_append VALUES (3, '01a0e7b5-3a66-7692-ba35-05f400815f29', '[{"op": "insert", "after": ["f169d7c1-1029-413d-85a4-8126d286cdf8", "4152861dab5e6d52abeea22477540e178ed0d2a12b9f57b86cc6e24fde70d11b"], "member": ["965ae0c4-23c1-4938-9596-33cc710c64e0", "fbe7c95481a9557ff14948e09c8137b3b3cbbb1b0b8449cf4c3f9fa8afdbf7b8"]}]', '[{"new": ["965ae0c4-23c1-4938-9596-33cc710c64e0", "fbe7c95481a9557ff14948e09c8137b3b3cbbb1b0b8449cf4c3f9fa8afdbf7b8"], "old": null, "kind": "append", "position": 12, "host_logical_id": "965ae0c4-23c1-4938-9596-33cc710c64e0"}]', '01a0e7b5-3aef-7fe4-a813-a7b8ada87540', '2026-09-28 11:10:09.132469+00');
INSERT INTO public.worldline_append VALUES (4, '01a0e7b5-40fc-7b02-b25a-d03420f925b9', '[{"op": "insert", "after": ["29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "8109b743a1f2e3179c85e3c6acd33315afe7dee42ddd7213746213cb68e6ab35"], "member": ["77b2a637-a479-4e62-82dd-35e47dcaa59d", "61b3b9c346c3724ff9a069be8e036f2d4dc2fce88085d9d19c4c36c702fe02a6"]}]', '[{"new": ["77b2a637-a479-4e62-82dd-35e47dcaa59d", "61b3b9c346c3724ff9a069be8e036f2d4dc2fce88085d9d19c4c36c702fe02a6"], "old": null, "kind": "append", "position": 15, "host_logical_id": "77b2a637-a479-4e62-82dd-35e47dcaa59d"}]', '01a0e7b5-4122-7b4a-86bb-b6206688d802', '2026-09-28 11:10:10.718855+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-3a66-7692-ba35-05f400815f29', 1, '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{}', 'import', '971ed53b0b62686e77361bf028328c9f59aad87d03b000bf522b7481fec44174', '{"ops": [{"op": "set", "members": [["cd6a7cd4-cef5-4cd3-87ec-ddceb141921d", "9fd8ea9fcb1339d6dac5f9cfcb978080ad41f3b1279b9fd2ca5f93633be78336"], ["b09b7305-d34c-40b5-91bd-7c643eb30338", "ab1049189a29d91bcc8b4128e4a6da70b4f67e68536ba5ab078dfa6dcbe6132c"], ["81718ea8-5069-4c34-868f-ea32146ea055", "86f6c6d3ae8a645cc7fc25e8c7b7292b1ff8802e9884260a5f1a322be8f9e03e"], ["fffce903-2a78-440d-9151-01c2b1cec7dd", "5b7fc56ebffee128ba1e60d26b33b69a3a78d0d410537802c5a4670215af61ec"]]}], "changes": [{"new": ["cd6a7cd4-cef5-4cd3-87ec-ddceb141921d", "9fd8ea9fcb1339d6dac5f9cfcb978080ad41f3b1279b9fd2ca5f93633be78336"], "old": null, "kind": "append", "position": 0, "host_logical_id": "cd6a7cd4-cef5-4cd3-87ec-ddceb141921d"}, {"new": ["b09b7305-d34c-40b5-91bd-7c643eb30338", "ab1049189a29d91bcc8b4128e4a6da70b4f67e68536ba5ab078dfa6dcbe6132c"], "old": null, "kind": "append", "position": 1, "host_logical_id": "b09b7305-d34c-40b5-91bd-7c643eb30338"}, {"new": ["81718ea8-5069-4c34-868f-ea32146ea055", "86f6c6d3ae8a645cc7fc25e8c7b7292b1ff8802e9884260a5f1a322be8f9e03e"], "old": null, "kind": "append", "position": 2, "host_logical_id": "81718ea8-5069-4c34-868f-ea32146ea055"}, {"new": ["fffce903-2a78-440d-9151-01c2b1cec7dd", "5b7fc56ebffee128ba1e60d26b33b69a3a78d0d410537802c5a4670215af61ec"], "old": null, "kind": "append", "position": 3, "host_logical_id": "fffce903-2a78-440d-9151-01c2b1cec7dd"}]}', '2026-09-28 11:10:08.990664+00', '01a0e7b5-3a65-7ce1-867d-3228b1264140');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-40fc-7b02-b25a-d03420f925b9', 2, '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{01a0e7b5-3a66-7692-ba35-05f400815f29}', 'edit', 'b4bd742e66e5113b5416d049463dd97ff8cab159dbe24b8b99fd2167f1e88bca', '{"ops": [{"op": "replace", "to": ["fffce903-2a78-440d-9151-01c2b1cec7dd", "58427731059beac6d93a54ef95c418a477fcc3952493896b546a110049cd3283"], "from": ["fffce903-2a78-440d-9151-01c2b1cec7dd", "5b7fc56ebffee128ba1e60d26b33b69a3a78d0d410537802c5a4670215af61ec"]}, {"op": "insert", "after": ["965ae0c4-23c1-4938-9596-33cc710c64e0", "fbe7c95481a9557ff14948e09c8137b3b3cbbb1b0b8449cf4c3f9fa8afdbf7b8"], "member": ["78c92f7d-ba33-47d3-b467-ddebbc064a14", "d8af5de848a7718bf3c5a8b0de5a56c295194fe23068cca0254a88dcf307281e"]}, {"op": "insert", "after": ["78c92f7d-ba33-47d3-b467-ddebbc064a14", "d8af5de848a7718bf3c5a8b0de5a56c295194fe23068cca0254a88dcf307281e"], "member": ["29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "8109b743a1f2e3179c85e3c6acd33315afe7dee42ddd7213746213cb68e6ab35"]}], "changes": [{"new": ["fffce903-2a78-440d-9151-01c2b1cec7dd", "58427731059beac6d93a54ef95c418a477fcc3952493896b546a110049cd3283"], "old": ["fffce903-2a78-440d-9151-01c2b1cec7dd", "5b7fc56ebffee128ba1e60d26b33b69a3a78d0d410537802c5a4670215af61ec"], "kind": "edit", "position": 3, "host_logical_id": "fffce903-2a78-440d-9151-01c2b1cec7dd"}, {"new": ["78c92f7d-ba33-47d3-b467-ddebbc064a14", "d8af5de848a7718bf3c5a8b0de5a56c295194fe23068cca0254a88dcf307281e"], "old": null, "kind": "append", "position": 13, "host_logical_id": "78c92f7d-ba33-47d3-b467-ddebbc064a14"}, {"new": ["29ce81c7-0c6b-4723-8c59-c9ed706aecb9", "8109b743a1f2e3179c85e3c6acd33315afe7dee42ddd7213746213cb68e6ab35"], "old": null, "kind": "append", "position": 14, "host_logical_id": "29ce81c7-0c6b-4723-8c59-c9ed706aecb9"}]}', '2026-09-28 11:10:10.678219+00', '01a0e7b5-40fb-7ebf-960c-4beddccdbd81');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-4149-7dcd-b605-35f011c51c62', 3, '01a0e7b5-3a50-72c1-9a21-4914fefd6cfd', '{01a0e7b5-40fc-7b02-b25a-d03420f925b9}', 'reconciliation', '57d1f49d1855be6dbde8e8da4138dc02645c87e7d89f99ee8f169bc4b53473f2', '{"ops": [{"op": "replace", "to": ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "2cdd1e15085b18e3fc68359e69f6aa28ac70895f5d6e447582e18c36bf5d8bcd"], "from": ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "a87d844f3b5885683b2838b1bf79b713e7746934d17d449ccdcab740f4dd4708"]}, {"op": "replace", "to": ["77b2a637-a479-4e62-82dd-35e47dcaa59d", "b85e6e8be367ca14b7c34ec0194c9ca8fdcc51967e0d48814e7496a0d13101a2"], "from": ["77b2a637-a479-4e62-82dd-35e47dcaa59d", "61b3b9c346c3724ff9a069be8e036f2d4dc2fce88085d9d19c4c36c702fe02a6"]}, {"op": "insert", "after": ["77b2a637-a479-4e62-82dd-35e47dcaa59d", "b85e6e8be367ca14b7c34ec0194c9ca8fdcc51967e0d48814e7496a0d13101a2"], "member": ["a527db9f-94c6-4a56-b7cb-37a165ffc0ea", "47c57607d693a652099e95dcd63fb8fd0cd1575a9f8a7fd362692d8d88867d13"]}], "changes": [{"new": ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "2cdd1e15085b18e3fc68359e69f6aa28ac70895f5d6e447582e18c36bf5d8bcd"], "old": ["7bf2ca56-5816-4653-983f-ec3ec2cf6371", "a87d844f3b5885683b2838b1bf79b713e7746934d17d449ccdcab740f4dd4708"], "kind": "disable", "position": 8, "host_logical_id": "7bf2ca56-5816-4653-983f-ec3ec2cf6371"}, {"new": ["77b2a637-a479-4e62-82dd-35e47dcaa59d", "b85e6e8be367ca14b7c34ec0194c9ca8fdcc51967e0d48814e7496a0d13101a2"], "old": ["77b2a637-a479-4e62-82dd-35e47dcaa59d", "61b3b9c346c3724ff9a069be8e036f2d4dc2fce88085d9d19c4c36c702fe02a6"], "kind": "swipe", "position": 15, "host_logical_id": "77b2a637-a479-4e62-82dd-35e47dcaa59d"}, {"new": ["a527db9f-94c6-4a56-b7cb-37a165ffc0ea", "47c57607d693a652099e95dcd63fb8fd0cd1575a9f8a7fd362692d8d88867d13"], "old": null, "kind": "append", "position": 16, "host_logical_id": "a527db9f-94c6-4a56-b7cb-37a165ffc0ea"}]}', '2026-09-28 11:10:10.757055+00', '01a0e7b5-4149-77f9-bad9-e6c67501183d');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b5-4761-702d-8954-459e9a0380e9', 4, '01a0e7b5-474e-7e26-b1f4-2662bd4e47c1', '{}', 'branch', '19621681438213d69152f91c10c05fffdd18925ca882e3dd5ec43fec24066c04', '{"ops": [{"op": "set", "members": [["9a7613c9-3840-45c9-96ea-6eff41ed4fec", "2d6296964956439addcc5c81116dbd5ac305ba39df4ad226f64fd87e0071c0af"], ["93c6395c-dad5-4cce-b134-602f33b3b38f", "7ff052024bb9bb44730ac2198c4fe6c5faed9cb616841b5a53ccb8b11b252598"], ["967a0cf5-747c-4be7-b34f-97f8c7c59e6c", "3c734e5035b08eba037494548624e0d8b183da3c21d3e11a0a9f6dbca4a6c14d"], ["fb317d3c-6e92-4ba9-9af5-31615178b3e2", "246f9eb3f0ecc2075df443f008b488d05ed6542583dce1fde8a017cd2baf1094"], ["1c8ade77-53f0-4fdf-b443-62f35da15666", "3ac9631b4849222c97d11449b951cb90f2a0affef6dbc28201155947c7590db7"], ["a39302f1-0ad4-4bb8-baa4-4d0025688449", "099acc80013ea6ad29c6b463f4b34d8fc5c8b93620a9b56d29ede5587739b6d3"], ["6e749dd6-4882-417e-b05c-29806e0ffa65", "5f7701648408f09cb0ee50ee25b55977904d52dc9138ed75c7791b211b5e8fff"], ["0ac2227f-398f-4c1e-a306-c1584e7ae92c", "087971b168a1280adab5736fba4641f88c2e26729f7b1b085be3d2afa5ed25ea"]]}], "changes": [{"new": ["9a7613c9-3840-45c9-96ea-6eff41ed4fec", "2d6296964956439addcc5c81116dbd5ac305ba39df4ad226f64fd87e0071c0af"], "old": null, "kind": "append", "position": 0, "host_logical_id": "9a7613c9-3840-45c9-96ea-6eff41ed4fec"}, {"new": ["93c6395c-dad5-4cce-b134-602f33b3b38f", "7ff052024bb9bb44730ac2198c4fe6c5faed9cb616841b5a53ccb8b11b252598"], "old": null, "kind": "append", "position": 1, "host_logical_id": "93c6395c-dad5-4cce-b134-602f33b3b38f"}, {"new": ["967a0cf5-747c-4be7-b34f-97f8c7c59e6c", "3c734e5035b08eba037494548624e0d8b183da3c21d3e11a0a9f6dbca4a6c14d"], "old": null, "kind": "append", "position": 2, "host_logical_id": "967a0cf5-747c-4be7-b34f-97f8c7c59e6c"}, {"new": ["fb317d3c-6e92-4ba9-9af5-31615178b3e2", "246f9eb3f0ecc2075df443f008b488d05ed6542583dce1fde8a017cd2baf1094"], "old": null, "kind": "append", "position": 3, "host_logical_id": "fb317d3c-6e92-4ba9-9af5-31615178b3e2"}, {"new": ["1c8ade77-53f0-4fdf-b443-62f35da15666", "3ac9631b4849222c97d11449b951cb90f2a0affef6dbc28201155947c7590db7"], "old": null, "kind": "append", "position": 4, "host_logical_id": "1c8ade77-53f0-4fdf-b443-62f35da15666"}, {"new": ["a39302f1-0ad4-4bb8-baa4-4d0025688449", "099acc80013ea6ad29c6b463f4b34d8fc5c8b93620a9b56d29ede5587739b6d3"], "old": null, "kind": "append", "position": 5, "host_logical_id": "a39302f1-0ad4-4bb8-baa4-4d0025688449"}, {"new": ["6e749dd6-4882-417e-b05c-29806e0ffa65", "5f7701648408f09cb0ee50ee25b55977904d52dc9138ed75c7791b211b5e8fff"], "old": null, "kind": "append", "position": 6, "host_logical_id": "6e749dd6-4882-417e-b05c-29806e0ffa65"}, {"new": ["0ac2227f-398f-4c1e-a306-c1584e7ae92c", "087971b168a1280adab5736fba4641f88c2e26729f7b1b085be3d2afa5ed25ea"], "old": null, "kind": "append", "position": 7, "host_logical_id": "0ac2227f-398f-4c1e-a306-c1584e7ae92c"}]}', '2026-09-28 11:10:12.314227+00', '01a0e7b5-4760-7b36-a7cc-e69f0d4576df');


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


