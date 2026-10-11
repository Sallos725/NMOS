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
-- Name: canon_applied; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.canon_applied (
    conversation_id uuid NOT NULL,
    manifest_id text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    observed_at timestamp with time zone
);


--
-- Name: canon_manifest; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.canon_manifest (
    conversation_id uuid NOT NULL,
    id text NOT NULL,
    entries jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
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
    canon_manifest_id text,
    canon_observed_at timestamp with time zone,
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
    hints jsonb,
    usage jsonb
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
-- Name: owner_repair; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.owner_repair (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    kind text NOT NULL,
    target jsonb NOT NULL,
    value jsonb DEFAULT '{}'::jsonb NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    removed_at timestamp with time zone,
    CONSTRAINT owner_repair_kind_check CHECK ((kind = ANY (ARRAY['thread_close'::text, 'thread_reopen'::text, 'secret_found_out'::text, 'secret_keep'::text, 'fact_retract'::text, 'fact_correct'::text, 'name_split'::text, 'fact_lock'::text, 'fact_restore'::text, 'state_dismiss'::text])))
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
    CONSTRAINT projection_generation_kind_check CHECK ((kind = ANY (ARRAY['extract'::text, 'embed'::text, 'summarize'::text, 'canon'::text, 'reveal'::text])))
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
    lines jsonb,
    canon_manifest_id text,
    canon_held jsonb DEFAULT '[]'::jsonb NOT NULL
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
    created_at timestamp with time zone DEFAULT now(),
    usage jsonb
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
-- Name: summary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.summary (
    id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    generation text NOT NULL,
    level text NOT NULL,
    window_key text NOT NULL,
    members uuid[] NOT NULL,
    first_turn integer,
    last_turn integer,
    text text NOT NULL,
    raw jsonb NOT NULL,
    coverage jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    discarded_at timestamp with time zone,
    usage jsonb,
    CONSTRAINT summary_level_check CHECK ((level = ANY (ARRAY['scene'::text, 'story'::text])))
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

INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 0, '01a12ab2-bafd-7812-adcb-6153e939fabf', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 1, '01a12ab2-baff-70c5-8c6a-dd94dd91e6d5', NULL, 0, 'e5534eba5e9b25ecb60d38b86c8b7d69');
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 2, '01a12ab2-bb00-77e0-8abc-8a057a0db9bb', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 3, '01a12ab2-c37f-7852-aa92-f9c91c6c7e39', NULL, 1, 'acd7f2e09d0259eec994f3e5a7d24542');
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 4, '01a12ab2-bb32-78d4-b754-108ff7399032', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 5, '01a12ab2-bb33-7340-a8e3-309146f3dd0f', NULL, 2, 'ff43923bb60e0cee930234d0c2a1c767');
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 6, '01a12ab2-bb34-74b7-93cc-bd626728d04f', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 7, '01a12ab2-bb34-76d5-be42-5b22a0f49bba', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 8, '01a12ab2-c3c7-70e1-89b2-9805f9fb849a', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 9, '01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8', NULL, 3, 'db8cd24e002858fa24667b027bdd72a3');
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 10, '01a12ab2-bb5c-761c-91cf-8092161fc719', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 11, '01a12ab2-bb5d-7e07-aeca-6f7d8562910c', NULL, 4, 'e6697eb6d6584c6ad78062dc21d680c4');
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 12, '01a12ab2-bb83-7927-805f-15d068f093dc', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 13, '01a12ab2-c380-7c9b-83f5-1f677c6d0c67', NULL, 5, '00b44b2d3a57070cee8795fbec29cd14');
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 14, '01a12ab2-c381-7f09-b3d3-b437c25cfe20', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 15, '01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82', NULL, 6, '48eefa9350505deb98634067554df286');
INSERT INTO public.active_membership VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 16, '01a12ab2-c3c9-77f9-b3a7-b8a8abbef319', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 0, '01a12ab2-c7da-759c-a768-578ae1cc3ca3', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 1, '01a12ab2-c7db-7fa2-aee0-29538601fb48', NULL, 0, '1d6984f44c1043346f59c3b8f6d66f0d');
INSERT INTO public.active_membership VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 2, '01a12ab2-c7dc-7205-bc89-8e146ebf67e0', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 3, '01a12ab2-c7dd-744c-82cf-2ad53c416cb3', NULL, 1, 'a104ea7b7ab71e51cfe7b5c47687be05');
INSERT INTO public.active_membership VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 4, '01a12ab2-c7dd-7ae1-b099-a7b855abed49', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 5, '01a12ab2-c7de-74d6-b33e-44b4be8721e3', NULL, 2, 'e240afb3975a37081a4ed034a181f9d5');
INSERT INTO public.active_membership VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 6, '01a12ab2-c7de-70e8-917b-48a68b976d71', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 7, '01a12ab2-c7df-7d97-b772-4540f7b7d110', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a12ab2-c113-7d70-a73d-4dcd08c46ad7', '01a12ab2-baff-70c5-8c6a-dd94dd91e6d5', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a12ab2-c113-7d70-a73d-4dcd08c46ad7', '01a12ab2-baff-70c5-8c6a-dd94dd91e6d5', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a12ab2-c134-7052-8978-6ddcb2a27f78', '01a12ab2-bb01-727a-b700-17c138eb7459', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a12ab2-c134-7052-8978-6ddcb2a27f78', '01a12ab2-bb01-727a-b700-17c138eb7459', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a12ab2-c14d-7502-bf1b-164bdeebac7c', '01a12ab2-bb33-7340-a8e3-309146f3dd0f', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a12ab2-c180-78f5-8b11-9673c6d34269', '01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a12ab2-c19a-7aa4-9551-08b22e73ee96', '01a12ab2-bb5d-7e07-aeca-6f7d8562910c', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a12ab2-c604-7ec9-b31b-6fa344842c70', '01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a12ab2-c637-7dba-b2b9-031cf8d93a85', '01a12ab2-bb5d-7e07-aeca-6f7d8562910c', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a12ab2-c64e-779d-8a1d-13ff8a6be032', '01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a12ab2-c672-7e98-8a03-1cbada746c6a', '01a12ab2-bb33-7340-a8e3-309146f3dd0f', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a12ab2-c68a-76fa-b26d-9f1e40068a8a', '01a12ab2-c37f-7852-aa92-f9c91c6c7e39', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a12ab2-c68a-76fa-b26d-9f1e40068a8a', '01a12ab2-c37f-7852-aa92-f9c91c6c7e39', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a12ab2-cb18-7f77-9d54-7a95fda8481c', '01a12ab2-c7db-7fa2-aee0-29538601fb48', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a12ab2-cb18-7f77-9d54-7a95fda8481c', '01a12ab2-c7db-7fa2-aee0-29538601fb48', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a12ab2-cb33-7b98-a0e0-94116fc21ff4', '01a12ab2-c7dd-744c-82cf-2ad53c416cb3', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a12ab2-cb33-7b98-a0e0-94116fc21ff4', '01a12ab2-c7dd-744c-82cf-2ad53c416cb3', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a12ab2-cb4b-7550-b7d2-62f3ed77272d', '01a12ab2-c7de-74d6-b33e-44b4be8721e3', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: canon_applied; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: canon_manifest; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'pocketrisu', NULL, '4ea648f9-bc84-454a-8ea8-73a62c7c5a56', '2026-10-11 11:21:58.773771+00', NULL, NULL, NULL, '01a12ab2-c3cd-7991-8480-0f447d42757d', 'd0c4e60f8b06eb464a075f8b33d6405cfbbe3a7a267a9424dc30afb14c93ef91', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL);
INSERT INTO public.conversation VALUES ('01a12ab2-c7d4-7381-9761-4dd9ac9635f1', 'pocketrisu', NULL, 'e181f244-c5a5-4b93-a7ab-771cf3f44576', '2026-10-11 11:22:02.068414+00', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '4ea648f9-bc84-454a-8ea8-73a62c7c5a56', '50d9cad5-21f7-42e7-ba75-48efb3baa723', '01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 'da7b3b28d42b8a6533f0886447503e3c63aa7250615cf8393cfa4716f0d9a0c0', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a12ab2-c113-7d70-a73d-4dcd08c46ad7', '01a12ab2-baff-70c5-8c6a-dd94dd91e6d5', 'e5534eba5e9b25ecb60d38b86c8b7d69', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:00.33909+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a12ab2-bafd-7812-adcb-6153e939fabf,01a12ab2-baff-70c5-8c6a-dd94dd91e6d5}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}', '{"ms": 14, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c134-7052-8978-6ddcb2a27f78', '01a12ab2-bb01-727a-b700-17c138eb7459', 'a6631876a0ba1a0dbb42b05c70dd36a5', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:00.372093+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a12ab2-bb00-77e0-8abc-8a057a0db9bb,01a12ab2-bb01-727a-b700-17c138eb7459}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 16, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c14d-7502-bf1b-164bdeebac7c', '01a12ab2-bb33-7340-a8e3-309146f3dd0f', 'ac803c0d7afeb8c8dd4f09bba7b6f088', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:00.397634+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a12ab2-bb32-78d4-b754-108ff7399032,01a12ab2-bb33-7340-a8e3-309146f3dd0f}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c168-71ec-a121-7da737d6585a', '01a12ab2-bb34-76d5-be42-5b22a0f49bba', '73a658c0867f9ef0b81e8076a0649f38', 'extract-v16', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-10-11 11:22:00.424427+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a12ab2-bb34-74b7-93cc-bd626728d04f,01a12ab2-bb34-76d5-be42-5b22a0f49bba}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 15, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c180-78f5-8b11-9673c6d34269', '01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8', '7cb1fbea71194dc7473f102f1f0b20a5', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:00.448415+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a12ab2-bb5b-7724-8df5-b5315afed081,01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c19a-7aa4-9551-08b22e73ee96', '01a12ab2-bb5d-7e07-aeca-6f7d8562910c', 'eac20fc4c526dec6b78e05373e3b6079', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:00.474278+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a12ab2-bb5c-761c-91cf-8092161fc719,01a12ab2-bb5d-7e07-aeca-6f7d8562910c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "silver compass", "type": "item"}, {"name": "Rin", "type": "character"}, {"name": "Mina", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 14, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c604-7ec9-b31b-6fa344842c70', '01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82', '48eefa9350505deb98634067554df286', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:01.604525+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a12ab2-c381-7f09-b3d3-b437c25cfe20,01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c620-777d-a5e0-5330f8b27cb0', '01a12ab2-c380-7c9b-83f5-1f677c6d0c67', '00b44b2d3a57070cee8795fbec29cd14', 'extract-v16', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-10-11 11:22:01.632172+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a12ab2-bb83-7927-805f-15d068f093dc,01a12ab2-c380-7c9b-83f5-1f677c6d0c67}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c637-7dba-b2b9-031cf8d93a85', '01a12ab2-bb5d-7e07-aeca-6f7d8562910c', 'e6697eb6d6584c6ad78062dc21d680c4', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:01.655556+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a12ab2-bb5c-761c-91cf-8092161fc719,01a12ab2-bb5d-7e07-aeca-6f7d8562910c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c64e-779d-8a1d-13ff8a6be032', '01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8', 'db8cd24e002858fa24667b027bdd72a3', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:01.678529+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a12ab2-bb34-74b7-93cc-bd626728d04f,01a12ab2-bb34-76d5-be42-5b22a0f49bba,01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c672-7e98-8a03-1cbada746c6a', '01a12ab2-bb33-7340-a8e3-309146f3dd0f', 'ff43923bb60e0cee930234d0c2a1c767', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:01.714512+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a12ab2-bb32-78d4-b754-108ff7399032,01a12ab2-bb33-7340-a8e3-309146f3dd0f}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-c68a-76fa-b26d-9f1e40068a8a', '01a12ab2-c37f-7852-aa92-f9c91c6c7e39', 'acd7f2e09d0259eec994f3e5a7d24542', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:01.738532+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a12ab2-bb00-77e0-8abc-8a057a0db9bb,01a12ab2-c37f-7852-aa92-f9c91c6c7e39}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 14, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-cb18-7f77-9d54-7a95fda8481c', '01a12ab2-c7db-7fa2-aee0-29538601fb48', '1d6984f44c1043346f59c3b8f6d66f0d', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:02.904791+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a12ab2-c7da-759c-a768-578ae1cc3ca3,01a12ab2-c7db-7fa2-aee0-29538601fb48}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-cb33-7b98-a0e0-94116fc21ff4', '01a12ab2-c7dd-744c-82cf-2ad53c416cb3', 'a104ea7b7ab71e51cfe7b5c47687be05', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:02.931174+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a12ab2-c7dc-7205-bc89-8e146ebf67e0,01a12ab2-c7dd-744c-82cf-2ad53c416cb3}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 14, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a12ab2-cb4b-7550-b7d2-62f3ed77272d', '01a12ab2-c7de-74d6-b33e-44b4be8721e3', 'e240afb3975a37081a4ed034a181f9d5', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-11 11:22:02.954882+00', 'extract-8699464cd39d3cb507ef6499baa2194d', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a12ab2-c7dd-7ae1-b099-a7b855abed49,01a12ab2-c7de-74d6-b33e-44b4be8721e3}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "lighthouse", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 14, "calls": 1}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a12ab2-bb02-7af5-a69c-0d41376c31fc', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'manifest', 'bd57174999803e548b84fec69645bb49e3ebc39c89ca1de9e7c5a471407019db', '01a12ab2-baf5-734d-8ca1-b4958264b7a5:bd57174999803e548b84fec69645bb49e3ebc39c89ca1de9e7c5a471407019db:manifest', '2026-10-11 11:21:58.780457+00', '{"chat_id": "4ea648f9-bc84-454a-8ea8-73a62c7c5a56", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["d64c8320-c697-417d-8710-c617cfbef277", "78b8883ea8c7cafb67ffa3801ad56cc2f046e5255b5eafd3441df6eb18a96e21", "user", null, null, null, 0, null, null], ["c3123f08-0ddc-4b65-9c30-74aebc6bf998", "845748cbbca27595ceba5775941b8af46cf8139c8201153a31354f09ae1ea60f", "char", null, null, null, 0, "c3123f08-0ddc-4b65-9c30-74aebc6bf998", null], ["d52a5b71-d751-42b5-881c-9e41613da06d", "1e028f7c63b339545914cf3765bd5881467406483af9934126923a03ee6f48ff", "user", null, null, null, 0, null, null], ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "e979899954fc3bcc27bd6a0a3c6ddd8a823d2c172d893485b0d3e8de3c3cc896", "char", null, null, null, 0, "ebb131db-f700-4f22-8925-9a0ee091f6c1", null]]}');
INSERT INTO public.host_observation VALUES ('01a12ab2-bb37-7178-acc7-71fffc93515d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'manifest', '5305d73e86bdbc3e8dc83bd7aa4646002b6ad2376f85c60dc3dec9c3fab0d263', '01a12ab2-baf5-734d-8ca1-b4958264b7a5:5305d73e86bdbc3e8dc83bd7aa4646002b6ad2376f85c60dc3dec9c3fab0d263:manifest', '2026-10-11 11:21:58.833559+00', '{"chat_id": "4ea648f9-bc84-454a-8ea8-73a62c7c5a56", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["446ba4a4-a027-4318-be2c-c1f2f0255af1", "7037c01fddb0ddf15754ffeff3898211cfbcc74c9ba589f04193cfa664e7855a", "user", null, null, null, 0, null, null], ["50d9cad5-21f7-42e7-ba75-48efb3baa723", "075e494d5474898cfb593beac3ee14f9f6044689e80223eab63ae730ffacf5a7", "char", null, null, null, 0, "50d9cad5-21f7-42e7-ba75-48efb3baa723", null], ["20e8e3dc-7aa3-4e1a-920b-965dcde740fc", "c4497d917f03729cfa7f1ba25f6bba324d070b1c74a216cb1d530ee0ed8c0c20", "user", null, null, null, 0, null, null], ["2ecc70c8-321f-4631-b645-82e61876d467", "e803a3c60f7e9d0d5ea00263b13603d3ed375220fe7dac836e93c4c177b9ef0d", "char", null, null, null, 0, "2ecc70c8-321f-4631-b645-82e61876d467", null]], "base_manifest_hash": "bd57174999803e548b84fec69645bb49e3ebc39c89ca1de9e7c5a471407019db"}');
INSERT INTO public.host_observation VALUES ('01a12ab2-bb60-7e84-ac16-419d6298a669', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'manifest', '4530cb218f90a137052de06a11445fdd00971f67ec5dba30474dcd1ccbaf2d18', '01a12ab2-baf5-734d-8ca1-b4958264b7a5:4530cb218f90a137052de06a11445fdd00971f67ec5dba30474dcd1ccbaf2d18:manifest', '2026-10-11 11:21:58.874307+00', '{"chat_id": "4ea648f9-bc84-454a-8ea8-73a62c7c5a56", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "66a24070b2480c6366d96071d6c17bdae78176ee6dd445e2a32a6f846b28e4f4", "user", null, null, null, 0, null, null], ["a76d3054-750f-4478-b87d-9d0b752e8fa6", "408b37f938a9df09cf390c66376563bf5af0558a7e129b69994274df1dd0de25", "char", null, null, null, 0, "a76d3054-750f-4478-b87d-9d0b752e8fa6", null], ["d32437bc-74de-42bc-96d0-83adb4ebe195", "d4b1780ba1c5d25fa8351d246fd957553d42a1116feb30880a762009bc1b8c99", "user", null, null, null, 0, null, null], ["60c09464-a3cb-40a7-a206-4138535a589b", "d93ff3535c6e227618afba3f54e1f38928f399866f34021b4a26b6f1ec01242a", "char", null, null, null, 0, "60c09464-a3cb-40a7-a206-4138535a589b", null]], "base_manifest_hash": "5305d73e86bdbc3e8dc83bd7aa4646002b6ad2376f85c60dc3dec9c3fab0d263"}');
INSERT INTO public.host_observation VALUES ('01a12ab2-bb87-73ce-82a5-7460c1b50674', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'manifest', 'f672fa4121800c3b2cdb531f84908b9caba1b409518c71dadbc7f0deb0420ca1', '01a12ab2-baf5-734d-8ca1-b4958264b7a5:f672fa4121800c3b2cdb531f84908b9caba1b409518c71dadbc7f0deb0420ca1:manifest', '2026-10-11 11:21:58.914711+00', '{"chat_id": "4ea648f9-bc84-454a-8ea8-73a62c7c5a56", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["be443e90-4d48-4d1d-b636-3882189eafc8", "04d1e000a5b2ed8c017e81fd37e68b930885c6c032488f7d6ca8a54f440d2568", "user", null, null, null, 0, null, null]], "base_manifest_hash": "4530cb218f90a137052de06a11445fdd00971f67ec5dba30474dcd1ccbaf2d18"}');
INSERT INTO public.host_observation VALUES ('01a12ab2-c382-7e6e-a45f-69d56201590e', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'manifest', '8bbaf8dad0a71f2c5da66139933c8756e2d6e316d910e79ccad8c7cf87b03a59', '01a12ab2-baf5-734d-8ca1-b4958264b7a5:8bbaf8dad0a71f2c5da66139933c8756e2d6e316d910e79ccad8c7cf87b03a59:manifest', '2026-10-11 11:22:00.959084+00', '{"chat_id": "4ea648f9-bc84-454a-8ea8-73a62c7c5a56", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["d64c8320-c697-417d-8710-c617cfbef277", "78b8883ea8c7cafb67ffa3801ad56cc2f046e5255b5eafd3441df6eb18a96e21", "user", null, null, null, 0, null, null], ["c3123f08-0ddc-4b65-9c30-74aebc6bf998", "845748cbbca27595ceba5775941b8af46cf8139c8201153a31354f09ae1ea60f", "char", null, null, null, 0, "c3123f08-0ddc-4b65-9c30-74aebc6bf998", null], ["d52a5b71-d751-42b5-881c-9e41613da06d", "1e028f7c63b339545914cf3765bd5881467406483af9934126923a03ee6f48ff", "user", null, null, null, 0, null, null], ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "bfd13aa69d8a2ddf7cb4357d6b158fa9308f0e27e8faf3ab789b14d07e43c4b9", "char", null, null, null, 0, "ebb131db-f700-4f22-8925-9a0ee091f6c1", null], ["446ba4a4-a027-4318-be2c-c1f2f0255af1", "7037c01fddb0ddf15754ffeff3898211cfbcc74c9ba589f04193cfa664e7855a", "user", null, null, null, 0, null, null], ["50d9cad5-21f7-42e7-ba75-48efb3baa723", "075e494d5474898cfb593beac3ee14f9f6044689e80223eab63ae730ffacf5a7", "char", null, null, null, 0, "50d9cad5-21f7-42e7-ba75-48efb3baa723", null], ["20e8e3dc-7aa3-4e1a-920b-965dcde740fc", "c4497d917f03729cfa7f1ba25f6bba324d070b1c74a216cb1d530ee0ed8c0c20", "user", null, null, null, 0, null, null], ["2ecc70c8-321f-4631-b645-82e61876d467", "e803a3c60f7e9d0d5ea00263b13603d3ed375220fe7dac836e93c4c177b9ef0d", "char", null, null, null, 0, "2ecc70c8-321f-4631-b645-82e61876d467", null], ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "66a24070b2480c6366d96071d6c17bdae78176ee6dd445e2a32a6f846b28e4f4", "user", null, null, null, 0, null, null], ["a76d3054-750f-4478-b87d-9d0b752e8fa6", "408b37f938a9df09cf390c66376563bf5af0558a7e129b69994274df1dd0de25", "char", null, null, null, 0, "a76d3054-750f-4478-b87d-9d0b752e8fa6", null], ["d32437bc-74de-42bc-96d0-83adb4ebe195", "d4b1780ba1c5d25fa8351d246fd957553d42a1116feb30880a762009bc1b8c99", "user", null, null, null, 0, null, null], ["60c09464-a3cb-40a7-a206-4138535a589b", "d93ff3535c6e227618afba3f54e1f38928f399866f34021b4a26b6f1ec01242a", "char", null, null, null, 0, "60c09464-a3cb-40a7-a206-4138535a589b", null], ["be443e90-4d48-4d1d-b636-3882189eafc8", "04d1e000a5b2ed8c017e81fd37e68b930885c6c032488f7d6ca8a54f440d2568", "user", null, null, null, 0, null, null], ["0274889a-af3b-4e04-983d-155a37e41975", "9a95b875b7edf9f19c598137ccdf2d938bf564f3b66bca0e8e95283755de1e0b", "char", null, null, null, 0, "0274889a-af3b-4e04-983d-155a37e41975", null], ["8e91bc3b-9a23-4e2a-ad24-5778a255d320", "25f4c2a7b664c4d35319eb58ef9abb66f6e1015ca1b971a40531da959dde2de3", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a12ab2-c3a4-74dc-ad42-529184ba9b2e', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'manifest', 'e59ec0ffecae64b8b77c4639d73609689f5af53a29c338718a20ce1eb9853130', '01a12ab2-baf5-734d-8ca1-b4958264b7a5:e59ec0ffecae64b8b77c4639d73609689f5af53a29c338718a20ce1eb9853130:manifest', '2026-10-11 11:22:00.992672+00', '{"chat_id": "4ea648f9-bc84-454a-8ea8-73a62c7c5a56", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "948864a31544a3da03f78b774e1e9106cfd4854cef4c37e6b1a12d1f079e65ab", "char", null, null, 1, 2, "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", null]], "base_manifest_hash": "8bbaf8dad0a71f2c5da66139933c8756e2d6e316d910e79ccad8c7cf87b03a59"}');
INSERT INTO public.host_observation VALUES ('01a12ab2-c3cc-7566-9223-be49c7b44758', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'manifest', 'd0c4e60f8b06eb464a075f8b33d6405cfbbe3a7a267a9424dc30afb14c93ef91', '01a12ab2-baf5-734d-8ca1-b4958264b7a5:d0c4e60f8b06eb464a075f8b33d6405cfbbe3a7a267a9424dc30afb14c93ef91:manifest', '2026-10-11 11:22:01.030845+00', '{"chat_id": "4ea648f9-bc84-454a-8ea8-73a62c7c5a56", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["d64c8320-c697-417d-8710-c617cfbef277", "78b8883ea8c7cafb67ffa3801ad56cc2f046e5255b5eafd3441df6eb18a96e21", "user", null, null, null, 0, null, null], ["c3123f08-0ddc-4b65-9c30-74aebc6bf998", "845748cbbca27595ceba5775941b8af46cf8139c8201153a31354f09ae1ea60f", "char", null, null, null, 0, "c3123f08-0ddc-4b65-9c30-74aebc6bf998", null], ["d52a5b71-d751-42b5-881c-9e41613da06d", "1e028f7c63b339545914cf3765bd5881467406483af9934126923a03ee6f48ff", "user", null, null, null, 0, null, null], ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "bfd13aa69d8a2ddf7cb4357d6b158fa9308f0e27e8faf3ab789b14d07e43c4b9", "char", null, null, null, 0, "ebb131db-f700-4f22-8925-9a0ee091f6c1", null], ["446ba4a4-a027-4318-be2c-c1f2f0255af1", "7037c01fddb0ddf15754ffeff3898211cfbcc74c9ba589f04193cfa664e7855a", "user", null, null, null, 0, null, null], ["50d9cad5-21f7-42e7-ba75-48efb3baa723", "075e494d5474898cfb593beac3ee14f9f6044689e80223eab63ae730ffacf5a7", "char", null, null, null, 0, "50d9cad5-21f7-42e7-ba75-48efb3baa723", null], ["20e8e3dc-7aa3-4e1a-920b-965dcde740fc", "c4497d917f03729cfa7f1ba25f6bba324d070b1c74a216cb1d530ee0ed8c0c20", "user", null, null, null, 0, null, null], ["2ecc70c8-321f-4631-b645-82e61876d467", "e803a3c60f7e9d0d5ea00263b13603d3ed375220fe7dac836e93c4c177b9ef0d", "char", null, null, null, 0, "2ecc70c8-321f-4631-b645-82e61876d467", null], ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "351e2bf75bf3809c86663493b58be0452dc0bb4654a33a7420952c1398489426", "user", true, null, null, 0, null, null], ["a76d3054-750f-4478-b87d-9d0b752e8fa6", "408b37f938a9df09cf390c66376563bf5af0558a7e129b69994274df1dd0de25", "char", null, null, null, 0, "a76d3054-750f-4478-b87d-9d0b752e8fa6", null], ["d32437bc-74de-42bc-96d0-83adb4ebe195", "d4b1780ba1c5d25fa8351d246fd957553d42a1116feb30880a762009bc1b8c99", "user", null, null, null, 0, null, null], ["60c09464-a3cb-40a7-a206-4138535a589b", "d93ff3535c6e227618afba3f54e1f38928f399866f34021b4a26b6f1ec01242a", "char", null, null, null, 0, "60c09464-a3cb-40a7-a206-4138535a589b", null], ["be443e90-4d48-4d1d-b636-3882189eafc8", "04d1e000a5b2ed8c017e81fd37e68b930885c6c032488f7d6ca8a54f440d2568", "user", null, null, null, 0, null, null], ["0274889a-af3b-4e04-983d-155a37e41975", "9a95b875b7edf9f19c598137ccdf2d938bf564f3b66bca0e8e95283755de1e0b", "char", null, null, null, 0, "0274889a-af3b-4e04-983d-155a37e41975", null], ["8e91bc3b-9a23-4e2a-ad24-5778a255d320", "25f4c2a7b664c4d35319eb58ef9abb66f6e1015ca1b971a40531da959dde2de3", "user", null, null, null, 0, null, null], ["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "84878c111016e389e57bc175a17a62cfba5ab64acea58b4946b17f6d5473e75a", "char", null, null, 0, 2, "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", null], ["7df9fd76-8ad3-401c-94ab-c3dd71276e90", "e7c45d1a9f1c9b962f9a47156d3a3f7a4dec625dec72ac46a64e2a8b7e85277f", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a12ab2-c7e0-7604-bac6-87fe54df8478', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', 'manifest', 'da7b3b28d42b8a6533f0886447503e3c63aa7250615cf8393cfa4716f0d9a0c0', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1:da7b3b28d42b8a6533f0886447503e3c63aa7250615cf8393cfa4716f0d9a0c0:manifest', '2026-10-11 11:22:02.074049+00', '{"chat_id": "e181f244-c5a5-4b93-a7ab-771cf3f44576", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["490c1c84-1110-4688-9240-1c03d7c4ed6b", "c2a5afc38ee4e371965c22027b04cb0478202ab3c6aeedbb2e4e74611bb64838", "user", null, null, null, 0, null, null], ["c20e6ac4-4d9f-4ed0-872e-61c7c9ae0079", "ad297434ebc1ba73976dfe795cac5cd2bbf58e5a7027f7660009faa7140c8535", "char", null, null, null, 0, "c3123f08-0ddc-4b65-9c30-74aebc6bf998", null], ["6ad9c28e-e130-4423-b0fc-fa1861d0859d", "e9c6fe6fb5346c799961261f1f68ae766ac20823ae35a9c9dd6d00f53951fd55", "user", null, null, null, 0, null, null], ["3a91d72d-83af-46df-9cd6-5b4c314617eb", "daadba12db3b660f9aa24bf6b05598f83356971fd9a15f26e6dafc2a37f86a1a", "char", null, null, null, 0, "ebb131db-f700-4f22-8925-9a0ee091f6c1", null], ["a1a10fdb-f53f-4e1c-a8bd-fdd7544fb6d3", "c64cea4670281aebb76877555cb94248275b30c3926a65e70ea8ff116ead70b5", "user", null, null, null, 0, null, null], ["2d3bc64b-12c4-400e-a3a0-615cc99647b2", "5c1dcbade87be1ee545962cb774315612996bde700d433e55853266a5b6845b1", "char", null, null, null, 0, "50d9cad5-21f7-42e7-ba75-48efb3baa723", null], ["9d97f962-d538-4ce1-8c64-26aca1b41724", "834e1b91d461cf3528077c6e61391f68a104e9b157d1799bf6feb70e6b438094", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::4ea648f9-bc84-454a-8ea8-73a62c7c5a56::Harbor route::50d9cad5-21f7-42e7-ba75-48efb3baa723::}}"]], ["8abe6b83-57bf-464e-b2b2-01c6f0716087", "283f587d2528ad1c9806727d5cc70ea1d0ea0eaebb88796d7a9aba829ba2294b", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a12ab2-bb83-7927-805f-15d068f093dc:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb83-7927-805f-15d068f093dc"}', 50, 'done', 1, '2026-10-11 11:21:58.914711+00', NULL, NULL, '2026-10-11 11:21:58.914711+00', '2026-10-11 11:22:00.072667+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a12ab2-bb5d-7e07-aeca-6f7d8562910c:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb5d-7e07-aeca-6f7d8562910c"}', 50, 'done', 1, '2026-10-11 11:21:58.914711+00', NULL, NULL, '2026-10-11 11:21:58.914711+00', '2026-10-11 11:22:00.094682+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a12ab2-bb5c-761c-91cf-8092161fc719:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb5c-761c-91cf-8092161fc719"}', 50, 'done', 1, '2026-10-11 11:21:58.874307+00', NULL, NULL, '2026-10-11 11:21:58.874307+00', '2026-10-11 11:22:00.116403+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8"}', 50, 'done', 1, '2026-10-11 11:21:58.874307+00', NULL, NULL, '2026-10-11 11:21:58.874307+00', '2026-10-11 11:22:00.136488+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a12ab2-bb5b-7724-8df5-b5315afed081:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb5b-7724-8df5-b5315afed081"}', 50, 'done', 1, '2026-10-11 11:21:58.874307+00', NULL, NULL, '2026-10-11 11:21:58.874307+00', '2026-10-11 11:22:00.156085+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a12ab2-bb34-76d5-be42-5b22a0f49bba:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb34-76d5-be42-5b22a0f49bba"}', 50, 'done', 1, '2026-10-11 11:21:58.874307+00', NULL, NULL, '2026-10-11 11:21:58.874307+00', '2026-10-11 11:22:00.175811+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a12ab2-bb34-74b7-93cc-bd626728d04f:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb34-74b7-93cc-bd626728d04f"}', 50, 'done', 1, '2026-10-11 11:21:58.833559+00', NULL, NULL, '2026-10-11 11:21:58.833559+00', '2026-10-11 11:22:00.195271+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a12ab2-bb33-7340-a8e3-309146f3dd0f:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb33-7340-a8e3-309146f3dd0f"}', 50, 'done', 1, '2026-10-11 11:21:58.833559+00', NULL, NULL, '2026-10-11 11:21:58.833559+00', '2026-10-11 11:22:00.214748+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a12ab2-bb32-78d4-b754-108ff7399032:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb32-78d4-b754-108ff7399032"}', 50, 'done', 1, '2026-10-11 11:21:58.833559+00', NULL, NULL, '2026-10-11 11:21:58.833559+00', '2026-10-11 11:22:00.238536+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a12ab2-bb01-727a-b700-17c138eb7459:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb01-727a-b700-17c138eb7459"}', 50, 'done', 1, '2026-10-11 11:21:58.833559+00', NULL, NULL, '2026-10-11 11:21:58.833559+00', '2026-10-11 11:22:00.258123+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a12ab2-bb00-77e0-8abc-8a057a0db9bb:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bb00-77e0-8abc-8a057a0db9bb"}', 150, 'done', 1, '2026-10-11 11:21:58.780457+00', NULL, NULL, '2026-10-11 11:21:58.780457+00', '2026-10-11 11:22:00.277731+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a12ab2-baff-70c5-8c6a-dd94dd91e6d5:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-baff-70c5-8c6a-dd94dd91e6d5"}', 150, 'done', 1, '2026-10-11 11:21:58.780457+00', NULL, NULL, '2026-10-11 11:21:58.780457+00', '2026-10-11 11:22:00.296605+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a12ab2-bafd-7812-adcb-6153e939fabf:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-bafd-7812-adcb-6153e939fabf"}', 150, 'done', 1, '2026-10-11 11:21:58.780457+00', NULL, NULL, '2026-10-11 11:21:58.780457+00', '2026-10-11 11:22:00.316321+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a12ab2-baff-70c5-8c6a-dd94dd91e6d5:e5534eba5e9b25ecb60d38b86c8b7d69:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-baff-70c5-8c6a-dd94dd91e6d5", "window_hash": "e5534eba5e9b25ecb60d38b86c8b7d69"}', 210, 'done', 1, '2026-10-11 11:21:58.780457+00', NULL, NULL, '2026-10-11 11:21:58.780457+00', '2026-10-11 11:22:00.348391+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a12ab2-bb01-727a-b700-17c138eb7459:a6631876a0ba1a0dbb42b05c70dd36a5:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb01-727a-b700-17c138eb7459", "window_hash": "a6631876a0ba1a0dbb42b05c70dd36a5"}', 210, 'done', 1, '2026-10-11 11:21:58.833559+00', NULL, NULL, '2026-10-11 11:21:58.833559+00', '2026-10-11 11:22:00.377426+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a12ab2-bb33-7340-a8e3-309146f3dd0f:ac803c0d7afeb8c8dd4f09bba7b6f088:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb33-7340-a8e3-309146f3dd0f", "window_hash": "ac803c0d7afeb8c8dd4f09bba7b6f088"}', 210, 'done', 1, '2026-10-11 11:21:58.833559+00', NULL, NULL, '2026-10-11 11:21:58.833559+00', '2026-10-11 11:22:00.402323+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a12ab2-bb34-76d5-be42-5b22a0f49bba:73a658c0867f9ef0b81e8076a0649f38:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb34-76d5-be42-5b22a0f49bba", "window_hash": "73a658c0867f9ef0b81e8076a0649f38"}', 210, 'done', 1, '2026-10-11 11:21:58.874307+00', NULL, NULL, '2026-10-11 11:21:58.874307+00', '2026-10-11 11:22:00.428627+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8:7cb1fbea71194dc7473f102f1f0b20a5:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8", "window_hash": "7cb1fbea71194dc7473f102f1f0b20a5"}', 210, 'done', 1, '2026-10-11 11:21:58.874307+00', NULL, NULL, '2026-10-11 11:21:58.874307+00', '2026-10-11 11:22:00.452853+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a12ab2-bb5d-7e07-aeca-6f7d8562910c:eac20fc4c526dec6b78e05373e3b6079:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb5d-7e07-aeca-6f7d8562910c", "window_hash": "eac20fc4c526dec6b78e05373e3b6079"}', 210, 'done', 1, '2026-10-11 11:21:58.914711+00', NULL, NULL, '2026-10-11 11:21:58.914711+00', '2026-10-11 11:22:00.478645+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a12ab2-bb33-7340-a8e3-309146f3dd0f:ff43923bb60e0cee930234d0c2a1c767:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb33-7340-a8e3-309146f3dd0f", "window_hash": "ff43923bb60e0cee930234d0c2a1c767"}', 100, 'done', 1, '2026-10-11 11:22:00.959084+00', NULL, NULL, '2026-10-11 11:22:00.959084+00', '2026-10-11 11:22:01.718383+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a12ab2-c37f-7852-aa92-f9c91c6c7e39:acd7f2e09d0259eec994f3e5a7d24542:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-c37f-7852-aa92-f9c91c6c7e39", "window_hash": "acd7f2e09d0259eec994f3e5a7d24542"}', 100, 'done', 1, '2026-10-11 11:22:00.959084+00', NULL, NULL, '2026-10-11 11:22:00.959084+00', '2026-10-11 11:22:01.742283+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a12ab2-c7da-759c-a768-578ae1cc3ca3:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c7da-759c-a768-578ae1cc3ca3"}', 150, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.886531+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a12ab2-c3c9-77f9-b3a7-b8a8abbef319:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c3c9-77f9-b3a7-b8a8abbef319"}', 50, 'done', 1, '2026-10-11 11:22:01.030845+00', NULL, NULL, '2026-10-11 11:22:01.030845+00', '2026-10-11 11:22:01.506991+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82"}', 50, 'done', 1, '2026-10-11 11:22:01.030845+00', NULL, NULL, '2026-10-11 11:22:01.030845+00', '2026-10-11 11:22:01.527132+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a12ab2-c381-7f09-b3d3-b437c25cfe20:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c381-7f09-b3d3-b437c25cfe20"}', 50, 'done', 1, '2026-10-11 11:22:00.959084+00', NULL, NULL, '2026-10-11 11:22:00.959084+00', '2026-10-11 11:22:01.546812+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a12ab2-c380-7c9b-83f5-1f677c6d0c67:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c380-7c9b-83f5-1f677c6d0c67"}', 50, 'done', 1, '2026-10-11 11:22:00.959084+00', NULL, NULL, '2026-10-11 11:22:00.959084+00', '2026-10-11 11:22:01.565266+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a12ab2-c37f-7852-aa92-f9c91c6c7e39:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c37f-7852-aa92-f9c91c6c7e39"}', 50, 'done', 1, '2026-10-11 11:22:00.959084+00', NULL, NULL, '2026-10-11 11:22:00.959084+00', '2026-10-11 11:22:01.58424+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82:48eefa9350505deb98634067554df286:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82", "window_hash": "48eefa9350505deb98634067554df286"}', 100, 'done', 1, '2026-10-11 11:22:01.030845+00', NULL, NULL, '2026-10-11 11:22:01.030845+00', '2026-10-11 11:22:01.608114+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a12ab2-c380-7c9b-83f5-1f677c6d0c67:00b44b2d3a57070cee8795fbec29cd14:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-c380-7c9b-83f5-1f677c6d0c67", "window_hash": "00b44b2d3a57070cee8795fbec29cd14"}', 100, 'done', 1, '2026-10-11 11:22:01.030845+00', NULL, NULL, '2026-10-11 11:22:01.030845+00', '2026-10-11 11:22:01.635271+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a12ab2-bb5d-7e07-aeca-6f7d8562910c:e6697eb6d6584c6ad78062dc21d680c4:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb5d-7e07-aeca-6f7d8562910c", "window_hash": "e6697eb6d6584c6ad78062dc21d680c4"}', 100, 'done', 1, '2026-10-11 11:22:01.030845+00', NULL, NULL, '2026-10-11 11:22:01.030845+00', '2026-10-11 11:22:01.659281+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8:db8cd24e002858fa24667b027bdd72a3:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8", "window_hash": "db8cd24e002858fa24667b027bdd72a3"}', 100, 'done', 1, '2026-10-11 11:22:01.030845+00', NULL, NULL, '2026-10-11 11:22:01.030845+00', '2026-10-11 11:22:01.682121+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a12ab2-c380-7c9b-83f5-1f677c6d0c67:36cc41ed1d70ebaef141d8d6878d93da:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-c380-7c9b-83f5-1f677c6d0c67", "window_hash": "36cc41ed1d70ebaef141d8d6878d93da"}', 100, 'obsolete', 1, '2026-10-11 11:22:00.959084+00', NULL, NULL, '2026-10-11 11:22:00.959084+00', '2026-10-11 11:22:01.685856+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8:359ac67e5593661c5efc262d070d202b:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8", "window_hash": "359ac67e5593661c5efc262d070d202b"}', 100, 'obsolete', 1, '2026-10-11 11:22:00.959084+00', NULL, NULL, '2026-10-11 11:22:00.959084+00', '2026-10-11 11:22:01.689537+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a12ab2-bb34-76d5-be42-5b22a0f49bba:4ce4c11ecceb2383123fc5a7f68921bc:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-bb34-76d5-be42-5b22a0f49bba", "window_hash": "4ce4c11ecceb2383123fc5a7f68921bc"}', 100, 'obsolete', 1, '2026-10-11 11:22:00.959084+00', NULL, NULL, '2026-10-11 11:22:00.959084+00', '2026-10-11 11:22:01.693127+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a12ab2-c7db-7fa2-aee0-29538601fb48:1d6984f44c1043346f59c3b8f6d66f0d:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-c7db-7fa2-aee0-29538601fb48", "window_hash": "1d6984f44c1043346f59c3b8f6d66f0d"}', 210, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.911422+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a12ab2-c7dd-744c-82cf-2ad53c416cb3:a104ea7b7ab71e51cfe7b5c47687be05:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-c7dd-744c-82cf-2ad53c416cb3", "window_hash": "a104ea7b7ab71e51cfe7b5c47687be05"}', 210, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.934695+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a12ab2-c7de-74d6-b33e-44b4be8721e3:e240afb3975a37081a4ed034a181f9d5:extract-8699464cd39d3cb507ef6499baa2194d', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "extract-8699464cd39d3cb507ef6499baa2194d", "revision_id": "01a12ab2-c7de-74d6-b33e-44b4be8721e3", "window_hash": "e240afb3975a37081a4ed034a181f9d5"}', 210, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.958464+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a12ab2-c7df-7d97-b772-4540f7b7d110:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c7df-7d97-b772-4540f7b7d110"}', 150, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.770778+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a12ab2-c7de-74d6-b33e-44b4be8721e3:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c7de-74d6-b33e-44b4be8721e3"}', 150, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.789982+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a12ab2-c7dd-7ae1-b099-a7b855abed49:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c7dd-7ae1-b099-a7b855abed49"}', 150, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.810648+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a12ab2-c7dd-744c-82cf-2ad53c416cb3:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c7dd-744c-82cf-2ad53c416cb3"}', 150, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.829521+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a12ab2-c7dc-7205-bc89-8e146ebf67e0:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c7dc-7205-bc89-8e146ebf67e0"}', 150, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.848453+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a12ab2-c7db-7fa2-aee0-29538601fb48:embed-d66e081cac8d37cfe4dcaada9668e759', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{"generation": "embed-d66e081cac8d37cfe4dcaada9668e759", "revision_id": "01a12ab2-c7db-7fa2-aee0-29538601fb48"}', 150, 'done', 1, '2026-10-11 11:22:02.074049+00', NULL, NULL, '2026-10-11 11:22:02.074049+00', '2026-10-11 11:22:02.868107+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a12ab2-bb02-7af5-a69c-0d41376c31fc', '01a12ab2-baf5-734d-8ca1-b4958264b7a5');


--
-- Data for Name: owner_repair; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-8699464cd39d3cb507ef6499baa2194d', 'extract', 'stub', 'http://127.0.0.1:40373/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "a6fec3fe3aabc852", "aliases": "361e584289ae46a4", "confirm": "c1a68b38f8fcae60", "compiler": "extract-v16", "endpoint": "http://127.0.0.1:40373/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "ec86a5ac4362f77d", "temperature": 0, "target_chars": 6000, "context_chars": 1000, "context_turns": 3}', '2026-10-11 11:21:58.673247+00', '2026-10-11 11:21:58.674376+00');
INSERT INTO public.projection_generation VALUES ('embed-d66e081cac8d37cfe4dcaada9668e759', 'embed', 'stub-embed', 'http://127.0.0.1:40373/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:40373/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-10-11 11:21:58.673247+00', '2026-10-11 11:21:58.678075+00');
INSERT INTO public.projection_generation VALUES ('summarize-4bfd640ffcfa149199110bc43c642a7d', 'summarize', 'stub', 'http://127.0.0.1:40373/v1', '{"lag": 4, "kind": "summarize", "model": "stub", "prompt": "1cb5649d13d81671", "window": 8, "version": "summarize-v3", "endpoint": "http://127.0.0.1:40373/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "message_chars": 6000}', '2026-10-11 11:21:58.673247+00', '2026-10-11 11:21:58.680318+00');
INSERT INTO public.projection_generation VALUES ('canon-080815bdc8da462e2310e6a14e08034f', 'canon', 'stub', 'http://127.0.0.1:40373/v1', '{"kind": "canon", "model": "stub", "prompt": "c084747d55328ce7", "version": "canon-v1", "endpoint": "http://127.0.0.1:40373/v1", "json_mode": true, "max_parts": 4, "normalizer": "clean-v3", "part_chars": 6000, "predicates": "9aebb33c40fcda7c", "temperature": 0}', '2026-10-11 11:21:58.673247+00', '2026-10-11 11:21:58.681667+00');
INSERT INTO public.projection_generation VALUES ('reveal-6d0a6a1600ad81e522bc0b4b83be1d44', 'reveal', 'stub', 'http://127.0.0.1:40373/v1', '{"kind": "reveal", "model": "stub", "prompt": "799b88903bfe0c44", "version": "reveal-v1", "compiler": "extract-v15", "endpoint": "http://127.0.0.1:40373/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "target_chars": 6000, "context_chars": 1000, "context_turns": 3}', '2026-10-11 11:21:58.673247+00', '2026-10-11 11:21:58.685055+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a12ab2-bb28-7691-b5a2-095315db3f08', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '01a12ab2-bb03-7819-b7eb-4040dec7430d', 'Is Rin with you?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a12ab2-bb00-77e0-8abc-8a057a0db9bb", "keyword_score": 1.0986, "host_logical_id": "d52a5b71-d751-42b5-881c-9e41613da06d"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a12ab2-bb00-77e0-8abc-8a057a0db9bb", "keyword_score": 1.0986, "host_logical_id": "d52a5b71-d751-42b5-881c-9e41613da06d"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 25.95, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.55, "fits_at": null, "lexical": 4.42, "threads": 0, "keywords": 4.32, "extractor": "extract-8699464cd39d", "embed_wait": 12.57, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 29.66, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d66e081cac8d37", "memory_mode_withheld": 0}', 'fresh', '2026-10-11 11:21:58.794656+00', 'packet-v18', 600, 3, '', '["c3123f08-0ddc-4b65-9c30-74aebc6bf998", "d52a5b71-d751-42b5-881c-9e41613da06d", "d64c8320-c697-417d-8710-c617cfbef277", "ebb131db-f700-4f22-8925-9a0ee091f6c1"]', 'extract-8699464cd39d3cb507ef6499baa2194d', 'embed-d66e081cac8d37cfe4dcaada9668e759', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-080815bdc8da462e2310e6a14e08034f", "first_cue": true, "threshold": 0.4, "rest_after": 2, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "source_clock": true, "history_marks": true, "name_variants": true, "summarize_key": "summarize-4bfd640ffcfa149199110bc43c642a7d", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a12ab2-bb51-7e39-b749-b0ea9dfece3a', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '01a12ab2-bb03-7819-b7eb-4040dec7430d', 'Let''s check the market.', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a12ab2-bb34-74b7-93cc-bd626728d04f", "keyword_score": 5.8377, "host_logical_id": "20e8e3dc-7aa3-4e1a-920b-965dcde740fc"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a12ab2-bb34-74b7-93cc-bd626728d04f", "keyword_score": 5.8377, "host_logical_id": "20e8e3dc-7aa3-4e1a-920b-965dcde740fc"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 15.84, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.0, "fits_at": null, "lexical": 2.34, "threads": 0, "keywords": 4.08, "extractor": "extract-8699464cd39d", "embed_wait": 7.15, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 18.65, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d66e081cac8d37", "memory_mode_withheld": 0}', 'fresh', '2026-10-11 11:21:58.846638+00', 'packet-v18', 600, 7, '', '["20e8e3dc-7aa3-4e1a-920b-965dcde740fc", "2ecc70c8-321f-4631-b645-82e61876d467", "446ba4a4-a027-4318-be2c-c1f2f0255af1", "50d9cad5-21f7-42e7-ba75-48efb3baa723"]', 'extract-8699464cd39d3cb507ef6499baa2194d', 'embed-d66e081cac8d37cfe4dcaada9668e759', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-080815bdc8da462e2310e6a14e08034f", "first_cue": true, "threshold": 0.4, "rest_after": 2, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "source_clock": true, "history_marks": true, "name_variants": true, "summarize_key": "summarize-4bfd640ffcfa149199110bc43c642a7d", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a12ab2-bb79-7a10-aac4-d25c6f1e7635', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '01a12ab2-bb03-7819-b7eb-4040dec7430d', 'Where do we meet tonight?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a12ab2-bb5c-761c-91cf-8092161fc719", "keyword_score": 4.7958, "host_logical_id": "d32437bc-74de-42bc-96d0-83adb4ebe195"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a12ab2-bb5c-761c-91cf-8092161fc719", "keyword_score": 4.7958, "host_logical_id": "d32437bc-74de-42bc-96d0-83adb4ebe195"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 15.69, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.84, "fits_at": null, "lexical": 3.53, "threads": 0, "keywords": 3.24, "extractor": "extract-8699464cd39d", "embed_wait": 6.96, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 19.52, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d66e081cac8d37", "memory_mode_withheld": 0}', 'fresh', '2026-10-11 11:21:58.886382+00', 'packet-v18', 600, 11, '', '["60c09464-a3cb-40a7-a206-4138535a589b", "a76d3054-750f-4478-b87d-9d0b752e8fa6", "b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "d32437bc-74de-42bc-96d0-83adb4ebe195"]', 'extract-8699464cd39d3cb507ef6499baa2194d', 'embed-d66e081cac8d37cfe4dcaada9668e759', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-080815bdc8da462e2310e6a14e08034f", "first_cue": true, "threshold": 0.4, "rest_after": 2, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "source_clock": true, "history_marks": true, "name_variants": true, "summarize_key": "summarize-4bfd640ffcfa149199110bc43c642a7d", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a12ab2-bb98-75be-bf0e-9184f745053c', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '01a12ab2-bb03-7819-b7eb-4040dec7430d', 'Where is Mina now?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a12ab2-bb83-7927-805f-15d068f093dc", "keyword_score": 0.7732, "host_logical_id": "be443e90-4d48-4d1d-b636-3882189eafc8"}, {"rrf": 0.03151, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a12ab2-bb01-727a-b700-17c138eb7459", "keyword_score": 0.7732, "host_logical_id": "ebb131db-f700-4f22-8925-9a0ee091f6c1"}, {"rrf": 0.03102, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a12ab2-baff-70c5-8c6a-dd94dd91e6d5", "keyword_score": 0.7732, "host_logical_id": "c3123f08-0ddc-4b65-9c30-74aebc6bf998"}, {"rrf": 0.01613, "sim": null, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a12ab2-bb5d-7e07-aeca-6f7d8562910c", "keyword_score": 0.7732, "host_logical_id": "60c09464-a3cb-40a7-a206-4138535a589b"}, {"rrf": 0.01587, "sim": null, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a12ab2-bb33-7340-a8e3-309146f3dd0f", "keyword_score": 0.7732, "host_logical_id": "50d9cad5-21f7-42e7-ba75-48efb3baa723"}, {"rrf": 0.01562, "sim": null, "score": 0.0, "position": 4, "user_score": 0.0, "revision_id": "01a12ab2-bb32-78d4-b754-108ff7399032", "keyword_score": 0.7732, "host_logical_id": "446ba4a4-a027-4318-be2c-c1f2f0255af1"}]', '[{"turn": 0, "score": 0.03102, "revision_id": "01a12ab2-baff-70c5-8c6a-dd94dd91e6d5"}, {"turn": 1, "score": 0.03151, "revision_id": "01a12ab2-bb01-727a-b700-17c138eb7459"}, {"turn": 2, "score": 0.01562, "revision_id": "01a12ab2-bb32-78d4-b754-108ff7399032"}, {"turn": 2, "score": 0.01587, "revision_id": "01a12ab2-bb33-7340-a8e3-309146f3dd0f"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a12ab2-bb83-7927-805f-15d068f093dc", "keyword_score": 0.7732, "host_logical_id": "be443e90-4d48-4d1d-b636-3882189eafc8"}, {"rrf": 0.01613, "sim": null, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a12ab2-bb5d-7e07-aeca-6f7d8562910c", "keyword_score": 0.7732, "host_logical_id": "60c09464-a3cb-40a7-a206-4138535a589b"}]', 227, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 15.81, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 4, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.88, "fits_at": null, "lexical": 2.85, "threads": 0, "keywords": 3.26, "extractor": "extract-8699464cd39d", "embed_lead": 11.86, "embed_wait": 0.0, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 12.73, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d66e081cac8d37", "memory_mode_withheld": 0}', 'fresh', '2026-10-11 11:21:58.924232+00', 'packet-v18', 600, 12, '', '["60c09464-a3cb-40a7-a206-4138535a589b", "a76d3054-750f-4478-b87d-9d0b752e8fa6", "be443e90-4d48-4d1d-b636-3882189eafc8", "d32437bc-74de-42bc-96d0-83adb4ebe195"]', 'extract-8699464cd39d3cb507ef6499baa2194d', 'embed-d66e081cac8d37cfe4dcaada9668e759', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-080815bdc8da462e2310e6a14e08034f", "first_cue": true, "threshold": 0.4, "rest_after": 2, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "source_clock": true, "history_marks": true, "name_variants": true, "summarize_key": "summarize-4bfd640ffcfa149199110bc43c642a7d", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a12ab2-bb01-727a-b700-17c138eb7459"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 1, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a12ab2-baff-70c5-8c6a-dd94dd91e6d5"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 0, "label": "supportive", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a12ab2-bb33-7340-a8e3-309146f3dd0f"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a12ab2-bb32-78d4-b754-108ff7399032"}, "tok": 23, "why": "placed", "kind": "excerpt", "text": "What did Mina say before she left?", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a12ab2-c397-7042-a82c-1e400ff88956', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '01a12ab2-c384-741f-8584-08c6e0c98ae6', 'And the compass?', '[{"rrf": 0.04741, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8", "keyword_score": 2.0149, "host_logical_id": "a76d3054-750f-4478-b87d-9d0b752e8fa6"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a12ab2-c381-7f09-b3d3-b437c25cfe20", "keyword_score": 2.0149, "host_logical_id": "8e91bc3b-9a23-4e2a-ad24-5778a255d320"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a12ab2-baff-70c5-8c6a-dd94dd91e6d5", "keyword_score": 0.0, "host_logical_id": "c3123f08-0ddc-4b65-9c30-74aebc6bf998"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a12ab2-bafd-7812-adcb-6153e939fabf", "keyword_score": 0.0, "host_logical_id": "d64c8320-c697-417d-8710-c617cfbef277"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a12ab2-bb34-76d5-be42-5b22a0f49bba", "keyword_score": 0.0, "host_logical_id": "2ecc70c8-321f-4631-b645-82e61876d467"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a12ab2-bb33-7340-a8e3-309146f3dd0f", "keyword_score": 0.0, "host_logical_id": "50d9cad5-21f7-42e7-ba75-48efb3baa723"}]', '[{"turn": 4, "score": 0.04741, "revision_id": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a12ab2-c381-7f09-b3d3-b437c25cfe20", "keyword_score": 2.0149, "host_logical_id": "8e91bc3b-9a23-4e2a-ad24-5778a255d320"}]', 222, '{"fit": 0.0, "cast": 2, "path": "normal", "embed": 15.67, "facts": 0, "placed": {"fact": 2, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.87, "fits_at": null, "lexical": 3.07, "threads": 0, "keywords": 2.08, "extractor": "extract-8699464cd39d", "embed_lead": 14.75, "embed_wait": 0.0, "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["Mina", "{{user}}"], "below_floor": 3, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 12.74, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 1, "embedding_projection": "embed-d66e081cac8d37", "memory_mode_withheld": 0}', 'fresh', '2026-10-11 11:22:00.970745+00', 'packet-v18', 600, 14, '', '["0274889a-af3b-4e04-983d-155a37e41975", "60c09464-a3cb-40a7-a206-4138535a589b", "8e91bc3b-9a23-4e2a-ad24-5778a255d320", "be443e90-4d48-4d1d-b636-3882189eafc8"]', 'extract-8699464cd39d3cb507ef6499baa2194d', 'embed-d66e081cac8d37cfe4dcaada9668e759', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-080815bdc8da462e2310e6a14e08034f", "first_cue": true, "threshold": 0.4, "rest_after": 2, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "source_clock": true, "history_marks": true, "name_variants": true, "summarize_key": "summarize-4bfd640ffcfa149199110bc43c642a7d", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 7}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "label": "required", "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 2}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "label": "required", "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a12ab2-bafd-7812-adcb-6153e939fabf"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "label": "supportive", "placed": false}, {"ref": {"revision": "01a12ab2-bb34-76d5-be42-5b22a0f49bba"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 3, "label": "supportive", "marks": {"unextracted": true}, "placed": false}, {"ref": {"revision": "01a12ab2-bb33-7340-a8e3-309146f3dd0f"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": false}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a12ab2-c3bd-7b6f-bbc4-879d98e72371', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '01a12ab2-c384-741f-8584-08c6e0c98ae6', 'compass', '[{"rrf": 0.04615, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8", "keyword_score": 2.0149, "host_logical_id": "a76d3054-750f-4478-b87d-9d0b752e8fa6"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a12ab2-c381-7f09-b3d3-b437c25cfe20", "keyword_score": 2.0149, "host_logical_id": "8e91bc3b-9a23-4e2a-ad24-5778a255d320"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a12ab2-bb5d-7e07-aeca-6f7d8562910c", "keyword_score": 0.0, "host_logical_id": "60c09464-a3cb-40a7-a206-4138535a589b"}]', '[{"turn": 4, "score": 0.04615, "revision_id": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a12ab2-c381-7f09-b3d3-b437c25cfe20", "keyword_score": 2.0149, "host_logical_id": "8e91bc3b-9a23-4e2a-ad24-5778a255d320"}]', 222, '{"fit": 0.0, "cast": 2, "path": "normal", "embed": 14.59, "facts": 0, "placed": {"fact": 2, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.16, "fits_at": null, "lexical": 3.36, "threads": 0, "keywords": 2.14, "extractor": "extract-8699464cd39d", "embed_wait": 6.56, "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["Mina", "{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 20.42, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d66e081cac8d37", "memory_mode_withheld": 0}', 'fresh', '2026-10-11 11:22:01.00088+00', 'packet-v18', 600, 15, '', '["0274889a-af3b-4e04-983d-155a37e41975", "8e91bc3b-9a23-4e2a-ad24-5778a255d320", "be443e90-4d48-4d1d-b636-3882189eafc8", "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e"]', 'extract-8699464cd39d3cb507ef6499baa2194d', 'embed-d66e081cac8d37cfe4dcaada9668e759', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-080815bdc8da462e2310e6a14e08034f", "first_cue": true, "threshold": 0.4, "rest_after": 2, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "source_clock": true, "history_marks": true, "name_variants": true, "summarize_key": "summarize-4bfd640ffcfa149199110bc43c642a7d", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 7}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "label": "required", "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 2}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "label": "required", "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a12ab2-bb5d-7e07-aeca-6f7d8562910c"}, "tok": 0, "why": "repeats", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 5, "label": "supportive", "placed": false, "repeats": {"assertion": 7}}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a12ab2-c3dd-71e7-beb0-0bcfa893382d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '01a12ab2-c3cd-7991-8480-0f447d42757d', 'Let''s go.', '[{"rrf": 0.04865, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a12ab2-bb34-74b7-93cc-bd626728d04f", "keyword_score": 2.0794, "host_logical_id": "20e8e3dc-7aa3-4e1a-920b-965dcde740fc"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a12ab2-c3c9-77f9-b3a7-b8a8abbef319", "keyword_score": 2.0794, "host_logical_id": "7df9fd76-8ad3-401c-94ab-c3dd71276e90"}]', '[{"turn": 3, "score": 0.04865, "revision_id": "01a12ab2-bb34-74b7-93cc-bd626728d04f"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a12ab2-c3c9-77f9-b3a7-b8a8abbef319", "keyword_score": 2.0794, "host_logical_id": "7df9fd76-8ad3-401c-94ab-c3dd71276e90"}]', 138, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 16.91, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.83, "fits_at": null, "lexical": 2.82, "threads": 0, "keywords": 2.15, "extractor": "extract-8699464cd39d", "embed_lead": 14.38, "embed_wait": 0.0, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 10.29, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d66e081cac8d37", "memory_mode_withheld": 0}', 'fresh', '2026-10-11 11:22:01.043304+00', 'packet-v18', 600, 16, '', '["0274889a-af3b-4e04-983d-155a37e41975", "7df9fd76-8ad3-401c-94ab-c3dd71276e90", "8e91bc3b-9a23-4e2a-ad24-5778a255d320", "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e"]', 'extract-8699464cd39d3cb507ef6499baa2194d', 'embed-d66e081cac8d37cfe4dcaada9668e759', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-080815bdc8da462e2310e6a14e08034f", "first_cue": true, "threshold": 0.4, "rest_after": 2, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "source_clock": true, "history_marks": true, "name_variants": true, "summarize_key": "summarize-4bfd640ffcfa149199110bc43c642a7d", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a12ab2-bb34-74b7-93cc-bd626728d04f"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 3, "label": "required", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a12ab2-c7fb-7bc7-bbe5-2263f8e7ff17', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 'Where is Rin?', '[{"rrf": 0.03227, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a12ab2-c7dc-7205-bc89-8e146ebf67e0", "keyword_score": 0.8473, "host_logical_id": "6ad9c28e-e130-4423-b0fc-fa1861d0859d"}, {"rrf": 0.03226, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a12ab2-c7dd-744c-82cf-2ad53c416cb3", "keyword_score": 0.8473, "host_logical_id": "3a91d72d-83af-46df-9cd6-5b4c314617eb"}, {"rrf": 0.01639, "sim": null, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a12ab2-c7df-7d97-b772-4540f7b7d110", "keyword_score": 0.8473, "host_logical_id": "8abe6b83-57bf-464e-b2b2-01c6f0716087"}]', '[{"turn": 1, "score": 0.03227, "revision_id": "01a12ab2-c7dc-7205-bc89-8e146ebf67e0"}, {"turn": 1, "score": 0.03226, "revision_id": "01a12ab2-c7dd-744c-82cf-2ad53c416cb3"}]', '[{"rrf": 0.01639, "sim": null, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a12ab2-c7df-7d97-b772-4540f7b7d110", "keyword_score": 0.8473, "host_logical_id": "8abe6b83-57bf-464e-b2b2-01c6f0716087"}]', 164, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 15.93, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.96, "fits_at": null, "lexical": 2.2, "threads": 0, "keywords": 1.82, "extractor": "extract-8699464cd39d", "embed_wait": 10.11, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 19.16, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d66e081cac8d37", "memory_mode_withheld": 0}', 'fresh', '2026-10-11 11:22:02.08793+00', 'packet-v18', 600, 7, '', '["2d3bc64b-12c4-400e-a3a0-615cc99647b2", "8abe6b83-57bf-464e-b2b2-01c6f0716087", "9d97f962-d538-4ce1-8c64-26aca1b41724", "a1a10fdb-f53f-4e1c-a8bd-fdd7544fb6d3"]', 'extract-8699464cd39d3cb507ef6499baa2194d', 'embed-d66e081cac8d37cfe4dcaada9668e759', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-080815bdc8da462e2310e6a14e08034f", "first_cue": true, "threshold": 0.4, "rest_after": 2, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "source_clock": true, "history_marks": true, "name_variants": true, "summarize_key": "summarize-4bfd640ffcfa149199110bc43c642a7d", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a12ab2-c7dc-7205-bc89-8e146ebf67e0"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 1, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a12ab2-c7dd-744c-82cf-2ad53c416cb3"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 1, "label": "supportive", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb83-7927-805f-15d068f093dc', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.070084+00', '{"ms": 30, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb5d-7e07-aeca-6f7d8562910c', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.093083+00', '{"ms": 16, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb5c-761c-91cf-8092161fc719', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.114846+00', '{"ms": 16, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.134917+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb5b-7724-8df5-b5315afed081', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.154683+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb34-76d5-be42-5b22a0f49bba', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.17432+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb34-74b7-93cc-bd626728d04f', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.193843+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb33-7340-a8e3-309146f3dd0f', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.213263+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb32-78d4-b754-108ff7399032', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.237162+00', '{"ms": 18, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb01-727a-b700-17c138eb7459', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.256588+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bb00-77e0-8abc-8a057a0db9bb', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.276254+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-baff-70c5-8c6a-dd94dd91e6d5', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.295169+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-bafd-7812-adcb-6153e939fabf', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:00.314781+00', '{"ms": 15, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c3c9-77f9-b3a7-b8a8abbef319', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:01.505511+00', '{"ms": 15, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:01.525539+00', '{"ms": 13, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c381-7f09-b3d3-b437c25cfe20', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:01.54545+00', '{"ms": 15, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c380-7c9b-83f5-1f677c6d0c67', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:01.563854+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c37f-7852-aa92-f9c91c6c7e39', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:01.582858+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c7df-7d97-b772-4540f7b7d110', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:02.769331+00', '{"ms": 15, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c7de-74d6-b33e-44b4be8721e3', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:02.788637+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c7dd-7ae1-b099-a7b855abed49', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:02.809215+00', '{"ms": 13, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c7dd-744c-82cf-2ad53c416cb3', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:02.828177+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c7dc-7205-bc89-8e146ebf67e0', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:02.847078+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c7db-7fa2-aee0-29538601fb48', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:02.866766+00', '{"ms": 15, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a12ab2-c7da-759c-a768-578ae1cc3ca3', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-d66e081cac8d37cfe4dcaada9668e759', '2026-10-11 11:22:02.885193+00', '{"ms": 14, "calls": 1}');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a12ab2-bafd-7812-adcb-6153e939fabf', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-10-11 11:21:58.780457+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-baff-70c5-8c6a-dd94dd91e6d5', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-10-11 11:21:58.780457+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb00-77e0-8abc-8a057a0db9bb', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-10-11 11:21:58.780457+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb01-727a-b700-17c138eb7459', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-10-11 11:21:58.780457+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb32-78d4-b754-108ff7399032', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-10-11 11:21:58.833559+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb33-7340-a8e3-309146f3dd0f', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-10-11 11:21:58.833559+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb34-74b7-93cc-bd626728d04f', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-10-11 11:21:58.833559+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb34-76d5-be42-5b22a0f49bba', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-10-11 11:21:58.833559+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb5b-7724-8df5-b5315afed081', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-10-11 11:21:58.874307+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-10-11 11:21:58.874307+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb5c-761c-91cf-8092161fc719', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-10-11 11:21:58.874307+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb5d-7e07-aeca-6f7d8562910c', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-10-11 11:21:58.874307+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-bb83-7927-805f-15d068f093dc', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-10-11 11:21:58.914711+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c37f-7852-aa92-f9c91c6c7e39', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-10-11 11:22:00.959084+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c380-7c9b-83f5-1f677c6d0c67', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-10-11 11:22:00.959084+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c381-7f09-b3d3-b437c25cfe20', 'clean-v3', 'And the compass?', 16, 16, '2026-10-11 11:22:00.959084+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c3a1-7ec5-8643-59530e376178', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-10-11 11:22:00.992672+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c3c7-70e1-89b2-9805f9fb849a', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-10-11 11:22:01.030845+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-10-11 11:22:01.030845+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c3c9-77f9-b3a7-b8a8abbef319', 'clean-v3', 'Let''s go.', 9, 9, '2026-10-11 11:22:01.030845+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c7da-759c-a768-578ae1cc3ca3', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-10-11 11:22:02.074049+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c7db-7fa2-aee0-29538601fb48', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-10-11 11:22:02.074049+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c7dc-7205-bc89-8e146ebf67e0', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-10-11 11:22:02.074049+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c7dd-744c-82cf-2ad53c416cb3', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-10-11 11:22:02.074049+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c7dd-7ae1-b099-a7b855abed49', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-10-11 11:22:02.074049+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c7de-74d6-b33e-44b4be8721e3', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-10-11 11:22:02.074049+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c7de-70e8-917b-48a68b976d71', 'clean-v3', '{{specialcomment::branchedfrom::4ea648f9-bc84-454a-8ea8-73a62c7c5a56::Harbor route::50d9cad5-21f7-42e7-ba75-48efb3baa723::}}', 124, 124, '2026-10-11 11:22:02.074049+00');
INSERT INTO public.revision_text VALUES ('01a12ab2-c7df-7d97-b772-4540f7b7d110', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-10-11 11:22:02.074049+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-10-11 11:21:57.574004+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-10-11 11:21:57.655782+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-10-11 11:21:57.67278+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-10-11 11:21:57.717016+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-10-11 11:21:57.73789+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-10-11 11:21:57.747361+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-10-11 11:21:57.749501+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-10-11 11:21:57.760696+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-10-11 11:21:57.77842+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-10-11 11:21:57.780578+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-10-11 11:21:57.782485+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-10-11 11:21:57.792034+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-10-11 11:21:57.818665+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-10-11 11:21:57.835665+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-10-11 11:21:57.838585+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-10-11 11:21:57.851184+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-10-11 11:21:57.853173+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-10-11 11:21:57.854996+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-10-11 11:21:57.856769+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-10-11 11:21:57.870043+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-10-11 11:21:57.872186+00');
INSERT INTO public.schema_migrations VALUES ('0022_thread_outcome_and_cause.sql', '9a8507f1b42457d2c44d568a2bd60d868f923613f8c83acb2be7f9104041cc88', '2026-10-11 11:21:57.874283+00');
INSERT INTO public.schema_migrations VALUES ('0023_summaries.sql', 'da452cf41917f9cc59c3a9d71e4114bf5179d3c5493669a5c7ce83ea13e0fb77', '2026-10-11 11:21:57.87613+00');
INSERT INTO public.schema_migrations VALUES ('0024_owner_repair.sql', 'de78024aceb993e7822500bb13d17d034b0123cdf67225fc9c8d82e16164e3be', '2026-10-11 11:21:57.890142+00');
INSERT INTO public.schema_migrations VALUES ('0025_canon.sql', '692a149bab93cd46b4bff801fc8ca0d857dc72ae88ca73471b33668cc2e694e3', '2026-10-11 11:21:57.903652+00');
INSERT INTO public.schema_migrations VALUES ('0026_canon_facts.sql', '5998bd556819cc977b9c0dabf9baa53303a5ac0504abb5742f6c3c11f1ec81dd', '2026-10-11 11:21:57.922212+00');
INSERT INTO public.schema_migrations VALUES ('0027_model_usage.sql', 'a0397dba46c52771feba09a4ce8f7fa1e8307fe36ba1a5fbaf4ad1489bfda2c6', '2026-10-11 11:21:57.928516+00');
INSERT INTO public.schema_migrations VALUES ('0028_reveal_checks.sql', '24d4cea55f72664dd0370f396582daa93d69881fc5f06dd5de46bfc295eb3325', '2026-10-11 11:21:57.930574+00');
INSERT INTO public.schema_migrations VALUES ('0029_state_dismiss.sql', '6d6c3162977286ea96ad0860e74e102fcd0fe24847a4aa49d9d72d9c16f3227d', '2026-10-11 11:21:57.932513+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a12ab2-bafc-70a5-820d-401d58f57314', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'd64c8320-c697-417d-8710-c617cfbef277', 'message', '2026-10-11 11:21:58.780457+00');
INSERT INTO public.source_object VALUES ('01a12ab2-baff-7088-b8bc-505e2ca3f903', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'c3123f08-0ddc-4b65-9c30-74aebc6bf998', 'message', '2026-10-11 11:21:58.780457+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb00-7434-a42b-e4dfcd47dc9c', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'd52a5b71-d751-42b5-881c-9e41613da06d', 'message', '2026-10-11 11:21:58.780457+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb00-7742-a8a3-aaf2db87a99c', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'ebb131db-f700-4f22-8925-9a0ee091f6c1', 'message', '2026-10-11 11:21:58.780457+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb32-713b-802f-7ca596f6fb92', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '446ba4a4-a027-4318-be2c-c1f2f0255af1', 'message', '2026-10-11 11:21:58.833559+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb32-7a95-ac7e-d9657c43b270', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '50d9cad5-21f7-42e7-ba75-48efb3baa723', 'message', '2026-10-11 11:21:58.833559+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb34-7a9c-8e3b-3dc67a9a56ff', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '20e8e3dc-7aa3-4e1a-920b-965dcde740fc', 'message', '2026-10-11 11:21:58.833559+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb34-7adc-acec-9a2218bca323', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '2ecc70c8-321f-4631-b645-82e61876d467', 'message', '2026-10-11 11:21:58.833559+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb5a-71bb-9ef0-7cc5941a9bd9', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'b7dcaefc-6d75-4505-b8e6-47e00f7672b4', 'message', '2026-10-11 11:21:58.874307+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb5b-7ebc-9908-e9269fc4dcbe', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'a76d3054-750f-4478-b87d-9d0b752e8fa6', 'message', '2026-10-11 11:21:58.874307+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb5c-739c-bbcf-e2431660bae6', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'd32437bc-74de-42bc-96d0-83adb4ebe195', 'message', '2026-10-11 11:21:58.874307+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb5d-7732-ad0c-6474ea229942', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '60c09464-a3cb-40a7-a206-4138535a589b', 'message', '2026-10-11 11:21:58.874307+00');
INSERT INTO public.source_object VALUES ('01a12ab2-bb83-70d8-9a78-1129c7f23892', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'be443e90-4d48-4d1d-b636-3882189eafc8', 'message', '2026-10-11 11:21:58.914711+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c380-767c-bdb6-b923de9b08f5', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '0274889a-af3b-4e04-983d-155a37e41975', 'message', '2026-10-11 11:22:00.959084+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c380-7e78-8c1a-912f4a028e0d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '8e91bc3b-9a23-4e2a-ad24-5778a255d320', 'message', '2026-10-11 11:22:00.959084+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c3a1-704b-ab87-8ed2b4f98a86', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', 'd4ea17dc-8a1e-4a34-8986-d45d37cbb27e', 'message', '2026-10-11 11:22:00.992672+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c3c8-76b7-8ab0-1b7490f13d8d', '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '7df9fd76-8ad3-401c-94ab-c3dd71276e90', 'message', '2026-10-11 11:22:01.030845+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c7da-7407-96ae-bc38eb1ae18c', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '490c1c84-1110-4688-9240-1c03d7c4ed6b', 'message', '2026-10-11 11:22:02.074049+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c7db-7bde-8bb0-b2509fe6b60c', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', 'c20e6ac4-4d9f-4ed0-872e-61c7c9ae0079', 'message', '2026-10-11 11:22:02.074049+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c7db-771f-b4fc-74cf4ecffc22', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '6ad9c28e-e130-4423-b0fc-fa1861d0859d', 'message', '2026-10-11 11:22:02.074049+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c7dc-7ceb-977d-2e2e38398061', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '3a91d72d-83af-46df-9cd6-5b4c314617eb', 'message', '2026-10-11 11:22:02.074049+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c7dd-7a45-b8a8-fcfcac523fc2', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', 'a1a10fdb-f53f-4e1c-a8bd-fdd7544fb6d3', 'message', '2026-10-11 11:22:02.074049+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c7de-7250-94ef-6525fda0ebdb', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '2d3bc64b-12c4-400e-a3a0-615cc99647b2', 'message', '2026-10-11 11:22:02.074049+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c7de-7029-a2b6-056588c962b3', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '9d97f962-d538-4ce1-8c64-26aca1b41724', 'message', '2026-10-11 11:22:02.074049+00');
INSERT INTO public.source_object VALUES ('01a12ab2-c7df-71e3-87c8-254750e68ff8', '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '8abe6b83-57bf-464e-b2b2-01c6f0716087', 'message', '2026-10-11 11:22:02.074049+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a12ab2-bafd-7812-adcb-6153e939fabf', '01a12ab2-bafc-70a5-820d-401d58f57314', '78b8883ea8c7cafb67ffa3801ad56cc2f046e5255b5eafd3441df6eb18a96e21', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "d64c8320-c697-417d-8710-c617cfbef277", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:21:58.780457+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb00-77e0-8abc-8a057a0db9bb', '01a12ab2-bb00-7434-a42b-e4dfcd47dc9c', '1e028f7c63b339545914cf3765bd5881467406483af9934126923a03ee6f48ff', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "d52a5b71-d751-42b5-881c-9e41613da06d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:21:58.780457+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-baff-70c5-8c6a-dd94dd91e6d5', '01a12ab2-baff-7088-b8bc-505e2ca3f903', '845748cbbca27595ceba5775941b8af46cf8139c8201153a31354f09ae1ea60f', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "c3123f08-0ddc-4b65-9c30-74aebc6bf998", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c3123f08-0ddc-4b65-9c30-74aebc6bf998", "specialComments": []}', '2026-10-11 11:21:58.780457+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb32-78d4-b754-108ff7399032', '01a12ab2-bb32-713b-802f-7ca596f6fb92', '7037c01fddb0ddf15754ffeff3898211cfbcc74c9ba589f04193cfa664e7855a', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "446ba4a4-a027-4318-be2c-c1f2f0255af1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:21:58.833559+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb34-74b7-93cc-bd626728d04f', '01a12ab2-bb34-7a9c-8e3b-3dc67a9a56ff', 'c4497d917f03729cfa7f1ba25f6bba324d070b1c74a216cb1d530ee0ed8c0c20', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "20e8e3dc-7aa3-4e1a-920b-965dcde740fc", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:21:58.833559+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb33-7340-a8e3-309146f3dd0f', '01a12ab2-bb32-7a95-ac7e-d9657c43b270', '075e494d5474898cfb593beac3ee14f9f6044689e80223eab63ae730ffacf5a7', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "50d9cad5-21f7-42e7-ba75-48efb3baa723", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "50d9cad5-21f7-42e7-ba75-48efb3baa723", "specialComments": []}', '2026-10-11 11:21:58.833559+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb5b-7724-8df5-b5315afed081', '01a12ab2-bb5a-71bb-9ef0-7cc5941a9bd9', '66a24070b2480c6366d96071d6c17bdae78176ee6dd445e2a32a6f846b28e4f4', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:21:58.874307+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb5c-761c-91cf-8092161fc719', '01a12ab2-bb5c-739c-bbcf-e2431660bae6', 'd4b1780ba1c5d25fa8351d246fd957553d42a1116feb30880a762009bc1b8c99', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "d32437bc-74de-42bc-96d0-83adb4ebe195", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:21:58.874307+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb34-76d5-be42-5b22a0f49bba', '01a12ab2-bb34-7adc-acec-9a2218bca323', 'e803a3c60f7e9d0d5ea00263b13603d3ed375220fe7dac836e93c4c177b9ef0d', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "2ecc70c8-321f-4631-b645-82e61876d467", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "2ecc70c8-321f-4631-b645-82e61876d467", "specialComments": []}', '2026-10-11 11:21:58.833559+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb5b-7f9e-afb8-9c76b16e3da8', '01a12ab2-bb5b-7ebc-9908-e9269fc4dcbe', '408b37f938a9df09cf390c66376563bf5af0558a7e129b69994274df1dd0de25', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "a76d3054-750f-4478-b87d-9d0b752e8fa6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a76d3054-750f-4478-b87d-9d0b752e8fa6", "specialComments": []}', '2026-10-11 11:21:58.874307+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb83-7927-805f-15d068f093dc', '01a12ab2-bb83-70d8-9a78-1129c7f23892', '04d1e000a5b2ed8c017e81fd37e68b930885c6c032488f7d6ca8a54f440d2568', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "be443e90-4d48-4d1d-b636-3882189eafc8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:21:58.914711+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb5d-7e07-aeca-6f7d8562910c', '01a12ab2-bb5d-7732-ad0c-6474ea229942', 'd93ff3535c6e227618afba3f54e1f38928f399866f34021b4a26b6f1ec01242a', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "60c09464-a3cb-40a7-a206-4138535a589b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "60c09464-a3cb-40a7-a206-4138535a589b", "specialComments": []}', '2026-10-11 11:21:58.874307+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c381-7f09-b3d3-b437c25cfe20', '01a12ab2-c380-7e78-8c1a-912f4a028e0d', '25f4c2a7b664c4d35319eb58ef9abb66f6e1015ca1b971a40531da959dde2de3', 'And the compass?', '{"name": null, "role": "user", "chatId": "8e91bc3b-9a23-4e2a-ad24-5778a255d320", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:22:00.959084+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c380-7c9b-83f5-1f677c6d0c67', '01a12ab2-c380-767c-bdb6-b923de9b08f5', '9a95b875b7edf9f19c598137ccdf2d938bf564f3b66bca0e8e95283755de1e0b', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "0274889a-af3b-4e04-983d-155a37e41975", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "0274889a-af3b-4e04-983d-155a37e41975", "specialComments": []}', '2026-10-11 11:22:00.959084+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c37f-7852-aa92-f9c91c6c7e39', '01a12ab2-bb00-7742-a8a3-aaf2db87a99c', 'bfd13aa69d8a2ddf7cb4357d6b158fa9308f0e27e8faf3ab789b14d07e43c4b9', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "ebb131db-f700-4f22-8925-9a0ee091f6c1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "ebb131db-f700-4f22-8925-9a0ee091f6c1", "specialComments": []}', '2026-10-11 11:22:00.959084+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-bb01-727a-b700-17c138eb7459', '01a12ab2-bb00-7742-a8a3-aaf2db87a99c', 'e979899954fc3bcc27bd6a0a3c6ddd8a823d2c172d893485b0d3e8de3c3cc896', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "ebb131db-f700-4f22-8925-9a0ee091f6c1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "ebb131db-f700-4f22-8925-9a0ee091f6c1", "specialComments": []}', '2026-10-11 11:21:58.780457+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c3c7-70e1-89b2-9805f9fb849a', '01a12ab2-bb5a-71bb-9ef0-7cc5941a9bd9', '351e2bf75bf3809c86663493b58be0452dc0bb4654a33a7420952c1398489426', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:22:01.030845+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c3c9-77f9-b3a7-b8a8abbef319', '01a12ab2-c3c8-76b7-8ab0-1b7490f13d8d', 'e7c45d1a9f1c9b962f9a47156d3a3f7a4dec625dec72ac46a64e2a8b7e85277f', 'Let''s go.', '{"name": null, "role": "user", "chatId": "7df9fd76-8ad3-401c-94ab-c3dd71276e90", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:22:01.030845+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c3c8-7e3d-81f9-2f0bdeacae82', '01a12ab2-c3a1-704b-ab87-8ed2b4f98a86', '84878c111016e389e57bc175a17a62cfba5ab64acea58b4946b17f6d5473e75a', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "specialComments": []}', '2026-10-11 11:22:01.030845+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c3a1-7ec5-8643-59530e376178', '01a12ab2-c3a1-704b-ab87-8ed2b4f98a86', '948864a31544a3da03f78b774e1e9106cfd4854cef4c37e6b1a12d1f079e65ab', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "specialComments": []}', '2026-10-11 11:22:00.992672+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c7da-759c-a768-578ae1cc3ca3', '01a12ab2-c7da-7407-96ae-bc38eb1ae18c', 'c2a5afc38ee4e371965c22027b04cb0478202ab3c6aeedbb2e4e74611bb64838', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "490c1c84-1110-4688-9240-1c03d7c4ed6b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:22:02.074049+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c7dc-7205-bc89-8e146ebf67e0', '01a12ab2-c7db-771f-b4fc-74cf4ecffc22', 'e9c6fe6fb5346c799961261f1f68ae766ac20823ae35a9c9dd6d00f53951fd55', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "6ad9c28e-e130-4423-b0fc-fa1861d0859d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:22:02.074049+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c7dd-7ae1-b099-a7b855abed49', '01a12ab2-c7dd-7a45-b8a8-fcfcac523fc2', 'c64cea4670281aebb76877555cb94248275b30c3926a65e70ea8ff116ead70b5', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "a1a10fdb-f53f-4e1c-a8bd-fdd7544fb6d3", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:22:02.074049+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c7de-70e8-917b-48a68b976d71', '01a12ab2-c7de-7029-a2b6-056588c962b3', '834e1b91d461cf3528077c6e61391f68a104e9b157d1799bf6feb70e6b438094', '{{specialcomment::branchedfrom::4ea648f9-bc84-454a-8ea8-73a62c7c5a56::Harbor route::50d9cad5-21f7-42e7-ba75-48efb3baa723::}}', '{"name": null, "role": "char", "chatId": "9d97f962-d538-4ce1-8c64-26aca1b41724", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::4ea648f9-bc84-454a-8ea8-73a62c7c5a56::Harbor route::50d9cad5-21f7-42e7-ba75-48efb3baa723::}}"]}', '2026-10-11 11:22:02.074049+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c7df-7d97-b772-4540f7b7d110', '01a12ab2-c7df-71e3-87c8-254750e68ff8', '283f587d2528ad1c9806727d5cc70ea1d0ea0eaebb88796d7a9aba829ba2294b', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "8abe6b83-57bf-464e-b2b2-01c6f0716087", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-11 11:22:02.074049+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c7de-74d6-b33e-44b4be8721e3', '01a12ab2-c7de-7250-94ef-6525fda0ebdb', '5c1dcbade87be1ee545962cb774315612996bde700d433e55853266a5b6845b1', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "2d3bc64b-12c4-400e-a3a0-615cc99647b2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "50d9cad5-21f7-42e7-ba75-48efb3baa723", "specialComments": []}', '2026-10-11 11:22:02.074049+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c7dd-744c-82cf-2ad53c416cb3', '01a12ab2-c7dc-7ceb-977d-2e2e38398061', 'daadba12db3b660f9aa24bf6b05598f83356971fd9a15f26e6dafc2a37f86a1a', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "3a91d72d-83af-46df-9cd6-5b4c314617eb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "ebb131db-f700-4f22-8925-9a0ee091f6c1", "specialComments": []}', '2026-10-11 11:22:02.074049+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a12ab2-c7db-7fa2-aee0-29538601fb48', '01a12ab2-c7db-7bde-8bb0-b2509fe6b60c', 'ad297434ebc1ba73976dfe795cac5cd2bbf58e5a7027f7660009faa7140c8535', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "c20e6ac4-4d9f-4ed0-872e-61c7c9ae0079", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c3123f08-0ddc-4b65-9c30-74aebc6bf998", "specialComments": []}', '2026-10-11 11:22:02.074049+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: summary; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a12ab2-bb03-7819-b7eb-4040dec7430d', '[{"op": "insert", "after": ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "e979899954fc3bcc27bd6a0a3c6ddd8a823d2c172d893485b0d3e8de3c3cc896"], "member": ["446ba4a4-a027-4318-be2c-c1f2f0255af1", "7037c01fddb0ddf15754ffeff3898211cfbcc74c9ba589f04193cfa664e7855a"]}, {"op": "insert", "after": ["446ba4a4-a027-4318-be2c-c1f2f0255af1", "7037c01fddb0ddf15754ffeff3898211cfbcc74c9ba589f04193cfa664e7855a"], "member": ["50d9cad5-21f7-42e7-ba75-48efb3baa723", "075e494d5474898cfb593beac3ee14f9f6044689e80223eab63ae730ffacf5a7"]}, {"op": "insert", "after": ["50d9cad5-21f7-42e7-ba75-48efb3baa723", "075e494d5474898cfb593beac3ee14f9f6044689e80223eab63ae730ffacf5a7"], "member": ["20e8e3dc-7aa3-4e1a-920b-965dcde740fc", "c4497d917f03729cfa7f1ba25f6bba324d070b1c74a216cb1d530ee0ed8c0c20"]}, {"op": "insert", "after": ["20e8e3dc-7aa3-4e1a-920b-965dcde740fc", "c4497d917f03729cfa7f1ba25f6bba324d070b1c74a216cb1d530ee0ed8c0c20"], "member": ["2ecc70c8-321f-4631-b645-82e61876d467", "e803a3c60f7e9d0d5ea00263b13603d3ed375220fe7dac836e93c4c177b9ef0d"]}]', '[{"new": ["446ba4a4-a027-4318-be2c-c1f2f0255af1", "7037c01fddb0ddf15754ffeff3898211cfbcc74c9ba589f04193cfa664e7855a"], "old": null, "kind": "append", "position": 4, "host_logical_id": "446ba4a4-a027-4318-be2c-c1f2f0255af1"}, {"new": ["50d9cad5-21f7-42e7-ba75-48efb3baa723", "075e494d5474898cfb593beac3ee14f9f6044689e80223eab63ae730ffacf5a7"], "old": null, "kind": "append", "position": 5, "host_logical_id": "50d9cad5-21f7-42e7-ba75-48efb3baa723"}, {"new": ["20e8e3dc-7aa3-4e1a-920b-965dcde740fc", "c4497d917f03729cfa7f1ba25f6bba324d070b1c74a216cb1d530ee0ed8c0c20"], "old": null, "kind": "append", "position": 6, "host_logical_id": "20e8e3dc-7aa3-4e1a-920b-965dcde740fc"}, {"new": ["2ecc70c8-321f-4631-b645-82e61876d467", "e803a3c60f7e9d0d5ea00263b13603d3ed375220fe7dac836e93c4c177b9ef0d"], "old": null, "kind": "append", "position": 7, "host_logical_id": "2ecc70c8-321f-4631-b645-82e61876d467"}]', '01a12ab2-bb37-7178-acc7-71fffc93515d', '2026-10-11 11:21:58.833559+00');
INSERT INTO public.worldline_append VALUES (2, '01a12ab2-bb03-7819-b7eb-4040dec7430d', '[{"op": "insert", "after": ["2ecc70c8-321f-4631-b645-82e61876d467", "e803a3c60f7e9d0d5ea00263b13603d3ed375220fe7dac836e93c4c177b9ef0d"], "member": ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "66a24070b2480c6366d96071d6c17bdae78176ee6dd445e2a32a6f846b28e4f4"]}, {"op": "insert", "after": ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "66a24070b2480c6366d96071d6c17bdae78176ee6dd445e2a32a6f846b28e4f4"], "member": ["a76d3054-750f-4478-b87d-9d0b752e8fa6", "408b37f938a9df09cf390c66376563bf5af0558a7e129b69994274df1dd0de25"]}, {"op": "insert", "after": ["a76d3054-750f-4478-b87d-9d0b752e8fa6", "408b37f938a9df09cf390c66376563bf5af0558a7e129b69994274df1dd0de25"], "member": ["d32437bc-74de-42bc-96d0-83adb4ebe195", "d4b1780ba1c5d25fa8351d246fd957553d42a1116feb30880a762009bc1b8c99"]}, {"op": "insert", "after": ["d32437bc-74de-42bc-96d0-83adb4ebe195", "d4b1780ba1c5d25fa8351d246fd957553d42a1116feb30880a762009bc1b8c99"], "member": ["60c09464-a3cb-40a7-a206-4138535a589b", "d93ff3535c6e227618afba3f54e1f38928f399866f34021b4a26b6f1ec01242a"]}]', '[{"new": ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "66a24070b2480c6366d96071d6c17bdae78176ee6dd445e2a32a6f846b28e4f4"], "old": null, "kind": "append", "position": 8, "host_logical_id": "b7dcaefc-6d75-4505-b8e6-47e00f7672b4"}, {"new": ["a76d3054-750f-4478-b87d-9d0b752e8fa6", "408b37f938a9df09cf390c66376563bf5af0558a7e129b69994274df1dd0de25"], "old": null, "kind": "append", "position": 9, "host_logical_id": "a76d3054-750f-4478-b87d-9d0b752e8fa6"}, {"new": ["d32437bc-74de-42bc-96d0-83adb4ebe195", "d4b1780ba1c5d25fa8351d246fd957553d42a1116feb30880a762009bc1b8c99"], "old": null, "kind": "append", "position": 10, "host_logical_id": "d32437bc-74de-42bc-96d0-83adb4ebe195"}, {"new": ["60c09464-a3cb-40a7-a206-4138535a589b", "d93ff3535c6e227618afba3f54e1f38928f399866f34021b4a26b6f1ec01242a"], "old": null, "kind": "append", "position": 11, "host_logical_id": "60c09464-a3cb-40a7-a206-4138535a589b"}]', '01a12ab2-bb60-7e84-ac16-419d6298a669', '2026-10-11 11:21:58.874307+00');
INSERT INTO public.worldline_append VALUES (3, '01a12ab2-bb03-7819-b7eb-4040dec7430d', '[{"op": "insert", "after": ["60c09464-a3cb-40a7-a206-4138535a589b", "d93ff3535c6e227618afba3f54e1f38928f399866f34021b4a26b6f1ec01242a"], "member": ["be443e90-4d48-4d1d-b636-3882189eafc8", "04d1e000a5b2ed8c017e81fd37e68b930885c6c032488f7d6ca8a54f440d2568"]}]', '[{"new": ["be443e90-4d48-4d1d-b636-3882189eafc8", "04d1e000a5b2ed8c017e81fd37e68b930885c6c032488f7d6ca8a54f440d2568"], "old": null, "kind": "append", "position": 12, "host_logical_id": "be443e90-4d48-4d1d-b636-3882189eafc8"}]', '01a12ab2-bb87-73ce-82a5-7460c1b50674', '2026-10-11 11:21:58.914711+00');
INSERT INTO public.worldline_append VALUES (4, '01a12ab2-c384-741f-8584-08c6e0c98ae6', '[{"op": "insert", "after": ["8e91bc3b-9a23-4e2a-ad24-5778a255d320", "25f4c2a7b664c4d35319eb58ef9abb66f6e1015ca1b971a40531da959dde2de3"], "member": ["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "948864a31544a3da03f78b774e1e9106cfd4854cef4c37e6b1a12d1f079e65ab"]}]', '[{"new": ["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "948864a31544a3da03f78b774e1e9106cfd4854cef4c37e6b1a12d1f079e65ab"], "old": null, "kind": "append", "position": 15, "host_logical_id": "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e"}]', '01a12ab2-c3a4-74dc-ad42-529184ba9b2e', '2026-10-11 11:22:00.992672+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a12ab2-bb03-7819-b7eb-4040dec7430d', 1, '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{}', 'import', 'bd57174999803e548b84fec69645bb49e3ebc39c89ca1de9e7c5a471407019db', '{"ops": [{"op": "set", "members": [["d64c8320-c697-417d-8710-c617cfbef277", "78b8883ea8c7cafb67ffa3801ad56cc2f046e5255b5eafd3441df6eb18a96e21"], ["c3123f08-0ddc-4b65-9c30-74aebc6bf998", "845748cbbca27595ceba5775941b8af46cf8139c8201153a31354f09ae1ea60f"], ["d52a5b71-d751-42b5-881c-9e41613da06d", "1e028f7c63b339545914cf3765bd5881467406483af9934126923a03ee6f48ff"], ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "e979899954fc3bcc27bd6a0a3c6ddd8a823d2c172d893485b0d3e8de3c3cc896"]]}], "changes": [{"new": ["d64c8320-c697-417d-8710-c617cfbef277", "78b8883ea8c7cafb67ffa3801ad56cc2f046e5255b5eafd3441df6eb18a96e21"], "old": null, "kind": "append", "position": 0, "host_logical_id": "d64c8320-c697-417d-8710-c617cfbef277"}, {"new": ["c3123f08-0ddc-4b65-9c30-74aebc6bf998", "845748cbbca27595ceba5775941b8af46cf8139c8201153a31354f09ae1ea60f"], "old": null, "kind": "append", "position": 1, "host_logical_id": "c3123f08-0ddc-4b65-9c30-74aebc6bf998"}, {"new": ["d52a5b71-d751-42b5-881c-9e41613da06d", "1e028f7c63b339545914cf3765bd5881467406483af9934126923a03ee6f48ff"], "old": null, "kind": "append", "position": 2, "host_logical_id": "d52a5b71-d751-42b5-881c-9e41613da06d"}, {"new": ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "e979899954fc3bcc27bd6a0a3c6ddd8a823d2c172d893485b0d3e8de3c3cc896"], "old": null, "kind": "append", "position": 3, "host_logical_id": "ebb131db-f700-4f22-8925-9a0ee091f6c1"}]}', '2026-10-11 11:21:58.780457+00', '01a12ab2-bb02-7af5-a69c-0d41376c31fc');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a12ab2-c384-741f-8584-08c6e0c98ae6', 2, '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{01a12ab2-bb03-7819-b7eb-4040dec7430d}', 'edit', '8bbaf8dad0a71f2c5da66139933c8756e2d6e316d910e79ccad8c7cf87b03a59', '{"ops": [{"op": "replace", "to": ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "bfd13aa69d8a2ddf7cb4357d6b158fa9308f0e27e8faf3ab789b14d07e43c4b9"], "from": ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "e979899954fc3bcc27bd6a0a3c6ddd8a823d2c172d893485b0d3e8de3c3cc896"]}, {"op": "insert", "after": ["be443e90-4d48-4d1d-b636-3882189eafc8", "04d1e000a5b2ed8c017e81fd37e68b930885c6c032488f7d6ca8a54f440d2568"], "member": ["0274889a-af3b-4e04-983d-155a37e41975", "9a95b875b7edf9f19c598137ccdf2d938bf564f3b66bca0e8e95283755de1e0b"]}, {"op": "insert", "after": ["0274889a-af3b-4e04-983d-155a37e41975", "9a95b875b7edf9f19c598137ccdf2d938bf564f3b66bca0e8e95283755de1e0b"], "member": ["8e91bc3b-9a23-4e2a-ad24-5778a255d320", "25f4c2a7b664c4d35319eb58ef9abb66f6e1015ca1b971a40531da959dde2de3"]}], "changes": [{"new": ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "bfd13aa69d8a2ddf7cb4357d6b158fa9308f0e27e8faf3ab789b14d07e43c4b9"], "old": ["ebb131db-f700-4f22-8925-9a0ee091f6c1", "e979899954fc3bcc27bd6a0a3c6ddd8a823d2c172d893485b0d3e8de3c3cc896"], "kind": "edit", "position": 3, "host_logical_id": "ebb131db-f700-4f22-8925-9a0ee091f6c1"}, {"new": ["0274889a-af3b-4e04-983d-155a37e41975", "9a95b875b7edf9f19c598137ccdf2d938bf564f3b66bca0e8e95283755de1e0b"], "old": null, "kind": "append", "position": 13, "host_logical_id": "0274889a-af3b-4e04-983d-155a37e41975"}, {"new": ["8e91bc3b-9a23-4e2a-ad24-5778a255d320", "25f4c2a7b664c4d35319eb58ef9abb66f6e1015ca1b971a40531da959dde2de3"], "old": null, "kind": "append", "position": 14, "host_logical_id": "8e91bc3b-9a23-4e2a-ad24-5778a255d320"}]}', '2026-10-11 11:22:00.959084+00', '01a12ab2-c382-7e6e-a45f-69d56201590e');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a12ab2-c3cd-7991-8480-0f447d42757d', 3, '01a12ab2-baf5-734d-8ca1-b4958264b7a5', '{01a12ab2-c384-741f-8584-08c6e0c98ae6}', 'reconciliation', 'd0c4e60f8b06eb464a075f8b33d6405cfbbe3a7a267a9424dc30afb14c93ef91', '{"ops": [{"op": "replace", "to": ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "351e2bf75bf3809c86663493b58be0452dc0bb4654a33a7420952c1398489426"], "from": ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "66a24070b2480c6366d96071d6c17bdae78176ee6dd445e2a32a6f846b28e4f4"]}, {"op": "replace", "to": ["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "84878c111016e389e57bc175a17a62cfba5ab64acea58b4946b17f6d5473e75a"], "from": ["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "948864a31544a3da03f78b774e1e9106cfd4854cef4c37e6b1a12d1f079e65ab"]}, {"op": "insert", "after": ["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "84878c111016e389e57bc175a17a62cfba5ab64acea58b4946b17f6d5473e75a"], "member": ["7df9fd76-8ad3-401c-94ab-c3dd71276e90", "e7c45d1a9f1c9b962f9a47156d3a3f7a4dec625dec72ac46a64e2a8b7e85277f"]}], "changes": [{"new": ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "351e2bf75bf3809c86663493b58be0452dc0bb4654a33a7420952c1398489426"], "old": ["b7dcaefc-6d75-4505-b8e6-47e00f7672b4", "66a24070b2480c6366d96071d6c17bdae78176ee6dd445e2a32a6f846b28e4f4"], "kind": "disable", "position": 8, "host_logical_id": "b7dcaefc-6d75-4505-b8e6-47e00f7672b4"}, {"new": ["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "84878c111016e389e57bc175a17a62cfba5ab64acea58b4946b17f6d5473e75a"], "old": ["d4ea17dc-8a1e-4a34-8986-d45d37cbb27e", "948864a31544a3da03f78b774e1e9106cfd4854cef4c37e6b1a12d1f079e65ab"], "kind": "swipe", "position": 15, "host_logical_id": "d4ea17dc-8a1e-4a34-8986-d45d37cbb27e"}, {"new": ["7df9fd76-8ad3-401c-94ab-c3dd71276e90", "e7c45d1a9f1c9b962f9a47156d3a3f7a4dec625dec72ac46a64e2a8b7e85277f"], "old": null, "kind": "append", "position": 16, "host_logical_id": "7df9fd76-8ad3-401c-94ab-c3dd71276e90"}]}', '2026-10-11 11:22:01.030845+00', '01a12ab2-c3cc-7566-9223-be49c7b44758');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a12ab2-c7e1-7e8b-8b52-0bed57f6b8a3', 4, '01a12ab2-c7d4-7381-9761-4dd9ac9635f1', '{}', 'branch', 'da7b3b28d42b8a6533f0886447503e3c63aa7250615cf8393cfa4716f0d9a0c0', '{"ops": [{"op": "set", "members": [["490c1c84-1110-4688-9240-1c03d7c4ed6b", "c2a5afc38ee4e371965c22027b04cb0478202ab3c6aeedbb2e4e74611bb64838"], ["c20e6ac4-4d9f-4ed0-872e-61c7c9ae0079", "ad297434ebc1ba73976dfe795cac5cd2bbf58e5a7027f7660009faa7140c8535"], ["6ad9c28e-e130-4423-b0fc-fa1861d0859d", "e9c6fe6fb5346c799961261f1f68ae766ac20823ae35a9c9dd6d00f53951fd55"], ["3a91d72d-83af-46df-9cd6-5b4c314617eb", "daadba12db3b660f9aa24bf6b05598f83356971fd9a15f26e6dafc2a37f86a1a"], ["a1a10fdb-f53f-4e1c-a8bd-fdd7544fb6d3", "c64cea4670281aebb76877555cb94248275b30c3926a65e70ea8ff116ead70b5"], ["2d3bc64b-12c4-400e-a3a0-615cc99647b2", "5c1dcbade87be1ee545962cb774315612996bde700d433e55853266a5b6845b1"], ["9d97f962-d538-4ce1-8c64-26aca1b41724", "834e1b91d461cf3528077c6e61391f68a104e9b157d1799bf6feb70e6b438094"], ["8abe6b83-57bf-464e-b2b2-01c6f0716087", "283f587d2528ad1c9806727d5cc70ea1d0ea0eaebb88796d7a9aba829ba2294b"]]}], "changes": [{"new": ["490c1c84-1110-4688-9240-1c03d7c4ed6b", "c2a5afc38ee4e371965c22027b04cb0478202ab3c6aeedbb2e4e74611bb64838"], "old": null, "kind": "append", "position": 0, "host_logical_id": "490c1c84-1110-4688-9240-1c03d7c4ed6b"}, {"new": ["c20e6ac4-4d9f-4ed0-872e-61c7c9ae0079", "ad297434ebc1ba73976dfe795cac5cd2bbf58e5a7027f7660009faa7140c8535"], "old": null, "kind": "append", "position": 1, "host_logical_id": "c20e6ac4-4d9f-4ed0-872e-61c7c9ae0079"}, {"new": ["6ad9c28e-e130-4423-b0fc-fa1861d0859d", "e9c6fe6fb5346c799961261f1f68ae766ac20823ae35a9c9dd6d00f53951fd55"], "old": null, "kind": "append", "position": 2, "host_logical_id": "6ad9c28e-e130-4423-b0fc-fa1861d0859d"}, {"new": ["3a91d72d-83af-46df-9cd6-5b4c314617eb", "daadba12db3b660f9aa24bf6b05598f83356971fd9a15f26e6dafc2a37f86a1a"], "old": null, "kind": "append", "position": 3, "host_logical_id": "3a91d72d-83af-46df-9cd6-5b4c314617eb"}, {"new": ["a1a10fdb-f53f-4e1c-a8bd-fdd7544fb6d3", "c64cea4670281aebb76877555cb94248275b30c3926a65e70ea8ff116ead70b5"], "old": null, "kind": "append", "position": 4, "host_logical_id": "a1a10fdb-f53f-4e1c-a8bd-fdd7544fb6d3"}, {"new": ["2d3bc64b-12c4-400e-a3a0-615cc99647b2", "5c1dcbade87be1ee545962cb774315612996bde700d433e55853266a5b6845b1"], "old": null, "kind": "append", "position": 5, "host_logical_id": "2d3bc64b-12c4-400e-a3a0-615cc99647b2"}, {"new": ["9d97f962-d538-4ce1-8c64-26aca1b41724", "834e1b91d461cf3528077c6e61391f68a104e9b157d1799bf6feb70e6b438094"], "old": null, "kind": "append", "position": 6, "host_logical_id": "9d97f962-d538-4ce1-8c64-26aca1b41724"}, {"new": ["8abe6b83-57bf-464e-b2b2-01c6f0716087", "283f587d2528ad1c9806727d5cc70ea1d0ea0eaebb88796d7a9aba829ba2294b"], "old": null, "kind": "append", "position": 7, "host_logical_id": "8abe6b83-57bf-464e-b2b2-01c6f0716087"}]}', '2026-10-11 11:22:02.074049+00', '01a12ab2-c7e0-7604-bac6-87fe54df8478');


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
-- Name: canon_manifest canon_manifest_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.canon_manifest
    ADD CONSTRAINT canon_manifest_pkey PRIMARY KEY (conversation_id, id);


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
-- Name: owner_repair owner_repair_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.owner_repair
    ADD CONSTRAINT owner_repair_pkey PRIMARY KEY (id);


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
-- Name: summary summary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.summary
    ADD CONSTRAINT summary_pkey PRIMARY KEY (id);


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
-- Name: canon_applied_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX canon_applied_conversation ON public.canon_applied USING btree (conversation_id, applied_at);


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
-- Name: owner_repair_conversation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX owner_repair_conversation ON public.owner_repair USING btree (conversation_id) WHERE (removed_at IS NULL);


--
-- Name: retrieval_trace_canon_held; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX retrieval_trace_canon_held ON public.retrieval_trace USING btree (conversation_id) WHERE (canon_held <> '[]'::jsonb);


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
-- Name: summary_window; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX summary_window ON public.summary USING btree (conversation_id, generation, level, window_key) WHERE (discarded_at IS NULL);


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
-- Name: canon_applied canon_applied_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.canon_applied
    ADD CONSTRAINT canon_applied_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


--
-- Name: canon_manifest canon_manifest_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.canon_manifest
    ADD CONSTRAINT canon_manifest_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


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
-- Name: owner_repair owner_repair_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.owner_repair
    ADD CONSTRAINT owner_repair_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


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
-- Name: summary summary_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.summary
    ADD CONSTRAINT summary_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversation(id);


--
-- Name: summary summary_generation_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.summary
    ADD CONSTRAINT summary_generation_fkey FOREIGN KEY (generation) REFERENCES public.projection_generation(key);


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


