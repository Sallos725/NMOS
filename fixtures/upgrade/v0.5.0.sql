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
    CONSTRAINT assertion_salience_check CHECK ((salience = ANY (ARRAY['major'::text, 'minor'::text, 'scene'::text, 'arc'::text, 'lasting'::text]))),
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
    replies_only boolean DEFAULT false NOT NULL,
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
    usage jsonb,
    speakers jsonb
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
    CONSTRAINT owner_repair_kind_check CHECK ((kind = ANY (ARRAY['thread_close'::text, 'thread_reopen'::text, 'secret_found_out'::text, 'secret_keep'::text, 'fact_retract'::text, 'fact_correct'::text, 'name_split'::text, 'fact_lock'::text, 'fact_restore'::text, 'state_dismiss'::text, 'entity_exclude'::text])))
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

INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 0, '01a170ed-2e7c-72d0-8d26-a7038eb64c9d', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 1, '01a170ed-2e7e-7a3a-8fbf-0841a10a1666', NULL, 0, 'e17963d30bc882d8adf5bd5f609d7a58');
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 2, '01a170ed-2e7f-7649-a260-6be058733c05', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 3, '01a170ed-372e-7672-845b-02d3d672d7b2', NULL, 1, 'caff87806d0b9b02c10809893028216f');
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 4, '01a170ed-2ecf-73d7-8213-882ae190675a', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 5, '01a170ed-2ed1-733c-baa6-fb0cd63acc08', NULL, 2, '6a1d06aa06cdd7a15dddd0642cbdc7ff');
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 6, '01a170ed-2ed1-736d-9bed-8ceee7e553a2', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 7, '01a170ed-2ed2-7267-84ab-140e75785613', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 8, '01a170ed-377c-7b62-8498-2e44a5cea798', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 9, '01a170ed-2efe-730b-82e0-d70e79de710c', NULL, 3, '59594c42179145b191cb8ad246b29cb9');
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 10, '01a170ed-2eff-7f7d-bdef-e12c8e72cacf', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 11, '01a170ed-2eff-7251-a318-4fb161af4c35', NULL, 4, '85d728071b7463474db1f4302912144b');
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 12, '01a170ed-2f25-71f4-9f8f-ad73efeb552c', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 13, '01a170ed-372f-73b1-b080-509f6e67eb0a', NULL, 5, '2ce358b1e111c22140d2afcc76b869bd');
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 14, '01a170ed-3730-749a-8f03-e0e4b857cd76', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 15, '01a170ed-377f-77df-831d-61cb15df2751', NULL, 6, '96e2d73d40a27df3fd35201db9c87c2a');
INSERT INTO public.active_membership VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 16, '01a170ed-3780-747c-9eca-7f80668b61a1', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 0, '01a170ed-3b9b-7077-9c45-7b55b7361bbf', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 1, '01a170ed-3b9b-7b4a-8965-36c67a74fa0d', NULL, 0, '9854bd4b091eb578fa7a5c3c1c89b017');
INSERT INTO public.active_membership VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 2, '01a170ed-3b9c-7b57-8e6c-515d414980d4', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 3, '01a170ed-3b9d-7568-94b7-e82060a83df9', NULL, 1, 'b78bf90ec253a3af44fa156dede28842');
INSERT INTO public.active_membership VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 4, '01a170ed-3b9d-7eb7-bbe6-c3752295f193', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 5, '01a170ed-3b9e-70d7-b630-9e44ef8ab95c', NULL, 2, '2c32f3b82328ababcfe3a59f307eee90');
INSERT INTO public.active_membership VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 6, '01a170ed-3ba0-7c08-9a63-244b4324950d', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 7, '01a170ed-3ba1-7ad6-9dce-a38eb2660e35', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a170ed-3540-7a1b-8426-7f0218795a53', '01a170ed-2e7e-7a3a-8fbf-0841a10a1666', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a170ed-3540-7a1b-8426-7f0218795a53', '01a170ed-2e7e-7a3a-8fbf-0841a10a1666', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a170ed-3559-73a2-bf74-f53cf63ccbc9', '01a170ed-2e80-772b-aa1f-535b2cf1e8bc', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a170ed-3559-73a2-bf74-f53cf63ccbc9', '01a170ed-2e80-772b-aa1f-535b2cf1e8bc', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a170ed-356d-7e8c-be68-c8ee4c30bb78', '01a170ed-2ed1-733c-baa6-fb0cd63acc08', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a170ed-3593-77be-b86f-aba9b3a5ee15', '01a170ed-2efe-730b-82e0-d70e79de710c', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a170ed-35a6-732d-98a2-54e85415d44c', '01a170ed-2eff-7251-a318-4fb161af4c35', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a170ed-39e2-7072-bdd2-caf5a44ecead', '01a170ed-377f-77df-831d-61cb15df2751', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a170ed-3a04-74aa-a5d1-8ab3baa9ffe7', '01a170ed-2eff-7251-a318-4fb161af4c35', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a170ed-3a14-7de9-a70d-29700a2fcd6c', '01a170ed-2efe-730b-82e0-d70e79de710c', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a170ed-3a2e-77d4-998d-d87bae4adc6c', '01a170ed-2ed1-733c-baa6-fb0cd63acc08', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a170ed-3a3e-7618-a175-6b257bc24eeb', '01a170ed-372e-7672-845b-02d3d672d7b2', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a170ed-3a3e-7618-a175-6b257bc24eeb', '01a170ed-372e-7672-845b-02d3d672d7b2', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a170ed-3e8f-73c3-98fb-b2fe18a39dbf', '01a170ed-3b9b-7b4a-8965-36c67a74fa0d', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a170ed-3e8f-73c3-98fb-b2fe18a39dbf', '01a170ed-3b9b-7b4a-8965-36c67a74fa0d', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a170ed-3ea2-7ed0-b496-d8daff683e13', '01a170ed-3b9d-7568-94b7-e82060a83df9', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a170ed-3ea2-7ed0-b496-d8daff683e13', '01a170ed-3b9d-7568-94b7-e82060a83df9', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a170ed-3eb3-79af-81d8-7d2f86f3e934', '01a170ed-3b9e-70d7-b630-9e44ef8ab95c', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: canon_applied; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: canon_manifest; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a170ed-2e74-74dc-9126-8229dbb2001f', 'pocketrisu', NULL, '6156ec08-e8a7-41c2-9213-440899a53af5', '2026-10-25 02:39:14.548525+00', NULL, NULL, NULL, '01a170ed-3784-7603-abc4-a6e8596671c1', '05a8f9e652f3a754869cf6c19c979e08157ced056262f0e374acf3e336ab5704', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL, false);
INSERT INTO public.conversation VALUES ('01a170ed-3b8d-736e-b523-180f1b7f68c2', 'pocketrisu', NULL, '833db128-172a-4faa-95ff-bbc8f02f1840', '2026-10-25 02:39:17.901929+00', '01a170ed-2e74-74dc-9126-8229dbb2001f', '6156ec08-e8a7-41c2-9213-440899a53af5', '0bbd2d85-28eb-4394-a904-9fe3d5d8de33', '01a170ed-3ba4-74d6-89cd-993e44ecc303', '69ae882774cd7c1484c95e72180bbd5534bd49a92e876958f76f2863483f7bb3', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL, false);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a170ed-3540-7a1b-8426-7f0218795a53', '01a170ed-2e7e-7a3a-8fbf-0841a10a1666', 'e17963d30bc882d8adf5bd5f609d7a58', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:16.288263+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a170ed-2e7c-72d0-8d26-a7038eb64c9d,01a170ed-2e7e-7a3a-8fbf-0841a10a1666}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3559-73a2-bf74-f53cf63ccbc9', '01a170ed-2e80-772b-aa1f-535b2cf1e8bc', 'd45609d8a220a0de0ca3ecdb61b842c2', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:16.312553+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a170ed-2e7f-7649-a260-6be058733c05,01a170ed-2e80-772b-aa1f-535b2cf1e8bc}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-356d-7e8c-be68-c8ee4c30bb78', '01a170ed-2ed1-733c-baa6-fb0cd63acc08', 'ecbc5ea4ab42ecc8b950052da6c46acf', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:16.333142+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a170ed-2ecf-73d7-8213-882ae190675a,01a170ed-2ed1-733c-baa6-fb0cd63acc08}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3580-74fd-9ae0-9b71dda265c7', '01a170ed-2ed2-7267-84ab-140e75785613', '1906af4e4f89cfe929b45c254070beb6', 'extract-v16', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-10-25 02:39:16.351768+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a170ed-2ed1-736d-9bed-8ceee7e553a2,01a170ed-2ed2-7267-84ab-140e75785613}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3593-77be-b86f-aba9b3a5ee15', '01a170ed-2efe-730b-82e0-d70e79de710c', 'a2fc1770815533cabd75eaa30ac182ea', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:16.371009+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a170ed-2efd-794c-8feb-da8b6130c6f0,01a170ed-2efe-730b-82e0-d70e79de710c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 7, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-35a6-732d-98a2-54e85415d44c', '01a170ed-2eff-7251-a318-4fb161af4c35', '4fb260dfcdbc608ce8d17989f488729b', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:16.390162+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a170ed-2eff-7f7d-bdef-e12c8e72cacf,01a170ed-2eff-7251-a318-4fb161af4c35}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "silver compass", "type": "item"}, {"name": "Rin", "type": "character"}, {"name": "Mina", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 7, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-39e2-7072-bdd2-caf5a44ecead', '01a170ed-377f-77df-831d-61cb15df2751', '96e2d73d40a27df3fd35201db9c87c2a', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:17.473846+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a170ed-3730-749a-8f03-e0e4b857cd76,01a170ed-377f-77df-831d-61cb15df2751}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-39f3-78e2-a002-5112141287a7', '01a170ed-372f-73b1-b080-509f6e67eb0a', '2ce358b1e111c22140d2afcc76b869bd', 'extract-v16', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-10-25 02:39:17.49093+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a170ed-2f25-71f4-9f8f-ad73efeb552c,01a170ed-372f-73b1-b080-509f6e67eb0a}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3a04-74aa-a5d1-8ab3baa9ffe7', '01a170ed-2eff-7251-a318-4fb161af4c35', '85d728071b7463474db1f4302912144b', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:17.508236+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a170ed-2eff-7f7d-bdef-e12c8e72cacf,01a170ed-2eff-7251-a318-4fb161af4c35}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3a14-7de9-a70d-29700a2fcd6c', '01a170ed-2efe-730b-82e0-d70e79de710c', '59594c42179145b191cb8ad246b29cb9', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:17.524466+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a170ed-2ed1-736d-9bed-8ceee7e553a2,01a170ed-2ed2-7267-84ab-140e75785613,01a170ed-2efe-730b-82e0-d70e79de710c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3a2e-77d4-998d-d87bae4adc6c', '01a170ed-2ed1-733c-baa6-fb0cd63acc08', '6a1d06aa06cdd7a15dddd0642cbdc7ff', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:17.550006+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a170ed-2ecf-73d7-8213-882ae190675a,01a170ed-2ed1-733c-baa6-fb0cd63acc08}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3a3e-7618-a175-6b257bc24eeb', '01a170ed-372e-7672-845b-02d3d672d7b2', 'caff87806d0b9b02c10809893028216f', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:17.565993+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a170ed-2e7f-7649-a260-6be058733c05,01a170ed-372e-7672-845b-02d3d672d7b2}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3e8f-73c3-98fb-b2fe18a39dbf', '01a170ed-3b9b-7b4a-8965-36c67a74fa0d', '9854bd4b091eb578fa7a5c3c1c89b017', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:18.67103+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a170ed-3b9b-7077-9c45-7b55b7361bbf,01a170ed-3b9b-7b4a-8965-36c67a74fa0d}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3ea2-7ed0-b496-d8daff683e13', '01a170ed-3b9d-7568-94b7-e82060a83df9', 'b78bf90ec253a3af44fa156dede28842', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:18.689801+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a170ed-3b9c-7b57-8e6c-515d414980d4,01a170ed-3b9d-7568-94b7-e82060a83df9}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 9, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a170ed-3eb3-79af-81d8-7d2f86f3e934', '01a170ed-3b9e-70d7-b630-9e44ef8ab95c', '2c32f3b82328ababcfe3a59f307eee90', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-25 02:39:18.706762+00', 'extract-daff401945e5ac9a9cf3c73be2923769', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a170ed-3b9d-7eb7-bbe6-c3752295f193,01a170ed-3b9e-70d7-b630-9e44ef8ab95c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "lighthouse", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 6, "calls": 1}', NULL);


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a170ed-2e82-7066-b5aa-8e18629b3ebd', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'manifest', 'f3c9079aef4f21ca4bbeb48cacc251d7348419d42a62e93d432b20112bfb4cd7', '01a170ed-2e74-74dc-9126-8229dbb2001f:f3c9079aef4f21ca4bbeb48cacc251d7348419d42a62e93d432b20112bfb4cd7:manifest', '2026-10-25 02:39:14.555556+00', '{"chat_id": "6156ec08-e8a7-41c2-9213-440899a53af5", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["f38e7339-9400-43da-b1be-c877d18f8a36", "c149bb15bba0cffb6b2130a27314912abaa49d6a76710e6df6d6dcaacb301947", "user", null, null, null, 0, null, null], ["84071aae-41a4-47d6-924b-8c36e611a314", "462fa6f7201bf24cf59c0d09b2a17a41ecde09c8b2ee178ef919a4d17b875a5d", "char", null, null, null, 0, "84071aae-41a4-47d6-924b-8c36e611a314", null], ["6ac5e480-dcff-48e7-b6c0-eb651a1da3e0", "70b496b6c09431817bdbdd1e7987f510d74d3375ce3d4d6ad2876d2538cba74c", "user", null, null, null, 0, null, null], ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "001ca8a10e37e4937ed6aef6781c62bc91ac0a4ea53e32ef7a271a8e2eb132cc", "char", null, null, null, 0, "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", null]]}');
INSERT INTO public.host_observation VALUES ('01a170ed-2ed5-7c26-90ba-cda5a3ea172b', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'manifest', 'e05ed17240369307209a8940ccbca93fbdda6ad57aa0683003cd8af8069ffc5e', '01a170ed-2e74-74dc-9126-8229dbb2001f:e05ed17240369307209a8940ccbca93fbdda6ad57aa0683003cd8af8069ffc5e:manifest', '2026-10-25 02:39:14.639079+00', '{"chat_id": "6156ec08-e8a7-41c2-9213-440899a53af5", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["781c9920-7e76-4e10-b639-a6ff0a29e346", "6dbaa90cdf09f4351152aca1b3d122512c06d122a4544e1e4e6c5b4650051f0c", "user", null, null, null, 0, null, null], ["0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "42fd76ff2dbe365662a4828e495cfab9b1bb3bff40bfa8e6899ffa25a3582745", "char", null, null, null, 0, "0bbd2d85-28eb-4394-a904-9fe3d5d8de33", null], ["4ca459ab-8e1d-49c2-a496-83b729815e8d", "a75e32bbc6175d245709082f70a0e18e977e8e409d524230bdbd820879935572", "user", null, null, null, 0, null, null], ["addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", "275a3db894f968cea14e8ac64ffd2fc8115cb12db0ee41b99a1aecc744abaa44", "char", null, null, null, 0, "addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", null]], "base_manifest_hash": "f3c9079aef4f21ca4bbeb48cacc251d7348419d42a62e93d432b20112bfb4cd7"}');
INSERT INTO public.host_observation VALUES ('01a170ed-2f02-71f5-8f83-37a8e010d916', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'manifest', '8c7ad4af533b143c091a43cc375149f784f081743c8129684dd8afd8a5533cc4', '01a170ed-2e74-74dc-9126-8229dbb2001f:8c7ad4af533b143c091a43cc375149f784f081743c8129684dd8afd8a5533cc4:manifest', '2026-10-25 02:39:14.684408+00', '{"chat_id": "6156ec08-e8a7-41c2-9213-440899a53af5", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["2d22a703-4e99-478e-83e4-53f9fc05ea54", "09fd158139b781b06cb795e6be782627b2dc199eedd5081055096a56289d5ea7", "user", null, null, null, 0, null, null], ["c9182849-3005-4b67-bf1f-cf4f222b86fb", "de76e2e451561d73ee883eb2a615992d854b94205fff045c6e1c4161a6d16e6a", "char", null, null, null, 0, "c9182849-3005-4b67-bf1f-cf4f222b86fb", null], ["81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "adeacd829f7ad76966cdda19c5775e385ef089513f5fbd6cd5e6115f3b4bbfed", "user", null, null, null, 0, null, null], ["95695118-8f4a-44a8-9f70-4dd03a61a038", "25b60c016b06a8f2be0a97ef959dad10316828bc21b52ecd6aaeb3eaa7e01ad8", "char", null, null, null, 0, "95695118-8f4a-44a8-9f70-4dd03a61a038", null]], "base_manifest_hash": "e05ed17240369307209a8940ccbca93fbdda6ad57aa0683003cd8af8069ffc5e"}');
INSERT INTO public.host_observation VALUES ('01a170ed-2f2b-734b-962a-b3c197db34f8', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'manifest', 'e434cbff0312055c368a3e78bfd58bb8282f787f1a8fbfff31eccebfb725002e', '01a170ed-2e74-74dc-9126-8229dbb2001f:e434cbff0312055c368a3e78bfd58bb8282f787f1a8fbfff31eccebfb725002e:manifest', '2026-10-25 02:39:14.724603+00', '{"chat_id": "6156ec08-e8a7-41c2-9213-440899a53af5", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["25fa145b-c398-4611-b292-838ba031e1b2", "a7dfa70c82599858449423d9bcfcafdba6dffc51cf1a498922c61f8138e98ee4", "user", null, null, null, 0, null, null]], "base_manifest_hash": "8c7ad4af533b143c091a43cc375149f784f081743c8129684dd8afd8a5533cc4"}');
INSERT INTO public.host_observation VALUES ('01a170ed-3732-7aeb-a99a-6c2b187ce68c', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'manifest', '439a7af19e1827bfdfc37d67930968ca3667e64a93f0ba24de247dd02880be34', '01a170ed-2e74-74dc-9126-8229dbb2001f:439a7af19e1827bfdfc37d67930968ca3667e64a93f0ba24de247dd02880be34:manifest', '2026-10-25 02:39:16.782005+00', '{"chat_id": "6156ec08-e8a7-41c2-9213-440899a53af5", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["f38e7339-9400-43da-b1be-c877d18f8a36", "c149bb15bba0cffb6b2130a27314912abaa49d6a76710e6df6d6dcaacb301947", "user", null, null, null, 0, null, null], ["84071aae-41a4-47d6-924b-8c36e611a314", "462fa6f7201bf24cf59c0d09b2a17a41ecde09c8b2ee178ef919a4d17b875a5d", "char", null, null, null, 0, "84071aae-41a4-47d6-924b-8c36e611a314", null], ["6ac5e480-dcff-48e7-b6c0-eb651a1da3e0", "70b496b6c09431817bdbdd1e7987f510d74d3375ce3d4d6ad2876d2538cba74c", "user", null, null, null, 0, null, null], ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "11ade1a8ed77bd47804b1fd62a39b9dc817d960c9315a85cde1b9c2203349d8a", "char", null, null, null, 0, "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", null], ["781c9920-7e76-4e10-b639-a6ff0a29e346", "6dbaa90cdf09f4351152aca1b3d122512c06d122a4544e1e4e6c5b4650051f0c", "user", null, null, null, 0, null, null], ["0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "42fd76ff2dbe365662a4828e495cfab9b1bb3bff40bfa8e6899ffa25a3582745", "char", null, null, null, 0, "0bbd2d85-28eb-4394-a904-9fe3d5d8de33", null], ["4ca459ab-8e1d-49c2-a496-83b729815e8d", "a75e32bbc6175d245709082f70a0e18e977e8e409d524230bdbd820879935572", "user", null, null, null, 0, null, null], ["addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", "275a3db894f968cea14e8ac64ffd2fc8115cb12db0ee41b99a1aecc744abaa44", "char", null, null, null, 0, "addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", null], ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "09fd158139b781b06cb795e6be782627b2dc199eedd5081055096a56289d5ea7", "user", null, null, null, 0, null, null], ["c9182849-3005-4b67-bf1f-cf4f222b86fb", "de76e2e451561d73ee883eb2a615992d854b94205fff045c6e1c4161a6d16e6a", "char", null, null, null, 0, "c9182849-3005-4b67-bf1f-cf4f222b86fb", null], ["81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "adeacd829f7ad76966cdda19c5775e385ef089513f5fbd6cd5e6115f3b4bbfed", "user", null, null, null, 0, null, null], ["95695118-8f4a-44a8-9f70-4dd03a61a038", "25b60c016b06a8f2be0a97ef959dad10316828bc21b52ecd6aaeb3eaa7e01ad8", "char", null, null, null, 0, "95695118-8f4a-44a8-9f70-4dd03a61a038", null], ["25fa145b-c398-4611-b292-838ba031e1b2", "a7dfa70c82599858449423d9bcfcafdba6dffc51cf1a498922c61f8138e98ee4", "user", null, null, null, 0, null, null], ["c6010e47-59bb-41a7-8254-ec8a80cdbecc", "4b4503ef5b6d681aa713716e946e4b2f4940fe1cdc9dcd6d48c10b1a01de8654", "char", null, null, null, 0, "c6010e47-59bb-41a7-8254-ec8a80cdbecc", null], ["4107b879-0f06-4ee1-a727-a940117c0f98", "35694a1a6fe119d3d2161f77bc4c698c687086bc77b04df0815b8d7de0785975", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a170ed-3759-7695-857e-a6920405dffd', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'manifest', 'a74d474f355834d9d04b09a4bbe108c8bc73e31df97132d96749b57676116065', '01a170ed-2e74-74dc-9126-8229dbb2001f:a74d474f355834d9d04b09a4bbe108c8bc73e31df97132d96749b57676116065:manifest', '2026-10-25 02:39:16.821806+00', '{"chat_id": "6156ec08-e8a7-41c2-9213-440899a53af5", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "1076d7f5e87c731da81ca6dbbe31cbb091402bcf7a7fec879f74be8e3a321f9f", "char", null, null, 1, 2, "99f4ea34-3f07-4a98-9af3-cadd5b7251de", null]], "base_manifest_hash": "439a7af19e1827bfdfc37d67930968ca3667e64a93f0ba24de247dd02880be34"}');
INSERT INTO public.host_observation VALUES ('01a170ed-3783-7653-94e3-bcba09825888', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'manifest', '05a8f9e652f3a754869cf6c19c979e08157ced056262f0e374acf3e336ab5704', '01a170ed-2e74-74dc-9126-8229dbb2001f:05a8f9e652f3a754869cf6c19c979e08157ced056262f0e374acf3e336ab5704:manifest', '2026-10-25 02:39:16.859822+00', '{"chat_id": "6156ec08-e8a7-41c2-9213-440899a53af5", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["f38e7339-9400-43da-b1be-c877d18f8a36", "c149bb15bba0cffb6b2130a27314912abaa49d6a76710e6df6d6dcaacb301947", "user", null, null, null, 0, null, null], ["84071aae-41a4-47d6-924b-8c36e611a314", "462fa6f7201bf24cf59c0d09b2a17a41ecde09c8b2ee178ef919a4d17b875a5d", "char", null, null, null, 0, "84071aae-41a4-47d6-924b-8c36e611a314", null], ["6ac5e480-dcff-48e7-b6c0-eb651a1da3e0", "70b496b6c09431817bdbdd1e7987f510d74d3375ce3d4d6ad2876d2538cba74c", "user", null, null, null, 0, null, null], ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "11ade1a8ed77bd47804b1fd62a39b9dc817d960c9315a85cde1b9c2203349d8a", "char", null, null, null, 0, "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", null], ["781c9920-7e76-4e10-b639-a6ff0a29e346", "6dbaa90cdf09f4351152aca1b3d122512c06d122a4544e1e4e6c5b4650051f0c", "user", null, null, null, 0, null, null], ["0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "42fd76ff2dbe365662a4828e495cfab9b1bb3bff40bfa8e6899ffa25a3582745", "char", null, null, null, 0, "0bbd2d85-28eb-4394-a904-9fe3d5d8de33", null], ["4ca459ab-8e1d-49c2-a496-83b729815e8d", "a75e32bbc6175d245709082f70a0e18e977e8e409d524230bdbd820879935572", "user", null, null, null, 0, null, null], ["addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", "275a3db894f968cea14e8ac64ffd2fc8115cb12db0ee41b99a1aecc744abaa44", "char", null, null, null, 0, "addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", null], ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "d6a49ec5425b7451cdb2f93d116e425c03a02596e17b6d5025fa5afac734e00b", "user", true, null, null, 0, null, null], ["c9182849-3005-4b67-bf1f-cf4f222b86fb", "de76e2e451561d73ee883eb2a615992d854b94205fff045c6e1c4161a6d16e6a", "char", null, null, null, 0, "c9182849-3005-4b67-bf1f-cf4f222b86fb", null], ["81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "adeacd829f7ad76966cdda19c5775e385ef089513f5fbd6cd5e6115f3b4bbfed", "user", null, null, null, 0, null, null], ["95695118-8f4a-44a8-9f70-4dd03a61a038", "25b60c016b06a8f2be0a97ef959dad10316828bc21b52ecd6aaeb3eaa7e01ad8", "char", null, null, null, 0, "95695118-8f4a-44a8-9f70-4dd03a61a038", null], ["25fa145b-c398-4611-b292-838ba031e1b2", "a7dfa70c82599858449423d9bcfcafdba6dffc51cf1a498922c61f8138e98ee4", "user", null, null, null, 0, null, null], ["c6010e47-59bb-41a7-8254-ec8a80cdbecc", "4b4503ef5b6d681aa713716e946e4b2f4940fe1cdc9dcd6d48c10b1a01de8654", "char", null, null, null, 0, "c6010e47-59bb-41a7-8254-ec8a80cdbecc", null], ["4107b879-0f06-4ee1-a727-a940117c0f98", "35694a1a6fe119d3d2161f77bc4c698c687086bc77b04df0815b8d7de0785975", "user", null, null, null, 0, null, null], ["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "59bdd67f83572f3f4c8f8b1c12f5dbc11922eacb652efe1f8b87beccaa86d0a9", "char", null, null, 0, 2, "99f4ea34-3f07-4a98-9af3-cadd5b7251de", null], ["660db083-0a7d-42e2-8c16-1b38b97dd42c", "70447579b380527c7ade70e138891e563c53791694db84d622144c44e3c76d28", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a170ed-3ba3-721d-ab82-e4ad5f285973', '01a170ed-3b8d-736e-b523-180f1b7f68c2', 'manifest', '69ae882774cd7c1484c95e72180bbd5534bd49a92e876958f76f2863483f7bb3', '01a170ed-3b8d-736e-b523-180f1b7f68c2:69ae882774cd7c1484c95e72180bbd5534bd49a92e876958f76f2863483f7bb3:manifest', '2026-10-25 02:39:17.914144+00', '{"chat_id": "833db128-172a-4faa-95ff-bbc8f02f1840", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["ab88c7bf-c374-4e9e-ac1c-529198853f89", "44ebaa29747098dd45c4587bd3430f7450d39dae1a211a46437f071dc13017da", "user", null, null, null, 0, null, null], ["4e9eb8d8-8459-4732-a101-8306ef331a9e", "decc1b0b3e8b7870b0bd44031fe0d00a24233b773a0554d567874f8f6a589567", "char", null, null, null, 0, "84071aae-41a4-47d6-924b-8c36e611a314", null], ["e1a2ea0a-42a1-41ed-8878-4e01a74c31b6", "e15640d28134ad3c7598486233d76f94675989754ee0ef99c167af3bed740077", "user", null, null, null, 0, null, null], ["5d2c20ef-d024-474b-b24f-303940a9d3b8", "95f2ea83d2bc8362b945ddd98c5b4070f5a9f52ee78428295c1a5175492cb9bd", "char", null, null, null, 0, "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", null], ["8bdc0b17-5006-4c36-90d2-5a866ce6664a", "3e061f9d2a8d128d8b69d9fd91ec82e234955a20183b1ce1e29e972b01222452", "user", null, null, null, 0, null, null], ["105e2ec3-55e4-4535-9e83-d3ce9e6a841a", "eaa8ab3cd206a514aa62cc8d5339aee0dc2402d3d0f8ac23794dd492483270db", "char", null, null, null, 0, "0bbd2d85-28eb-4394-a904-9fe3d5d8de33", null], ["672fdb7d-c251-45b0-abae-a3837362a28b", "9fb795bd4e419bd4352803e57d512517c2435375c9863b1209596ff4ca7c2426", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::6156ec08-e8a7-41c2-9213-440899a53af5::Harbor route::0bbd2d85-28eb-4394-a904-9fe3d5d8de33::}}"]], ["fb3b6a7d-daba-4fbf-90d2-26dce4c7090e", "bd736791e96c5985a50e245c1de13c5e42b08de6152d545d9cac146d5b368eb3", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a170ed-2f25-71f4-9f8f-ad73efeb552c:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2f25-71f4-9f8f-ad73efeb552c"}', 50, 'done', 1, '2026-10-25 02:39:14.724603+00', NULL, NULL, '2026-10-25 02:39:14.724603+00', '2026-10-25 02:39:16.129675+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a170ed-2eff-7251-a318-4fb161af4c35:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2eff-7251-a318-4fb161af4c35"}', 50, 'done', 1, '2026-10-25 02:39:14.724603+00', NULL, NULL, '2026-10-25 02:39:14.724603+00', '2026-10-25 02:39:16.140927+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a170ed-2eff-7f7d-bdef-e12c8e72cacf:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2eff-7f7d-bdef-e12c8e72cacf"}', 50, 'done', 1, '2026-10-25 02:39:14.684408+00', NULL, NULL, '2026-10-25 02:39:14.684408+00', '2026-10-25 02:39:16.152493+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a170ed-2efe-730b-82e0-d70e79de710c:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2efe-730b-82e0-d70e79de710c"}', 50, 'done', 1, '2026-10-25 02:39:14.684408+00', NULL, NULL, '2026-10-25 02:39:14.684408+00', '2026-10-25 02:39:16.16484+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a170ed-2efd-794c-8feb-da8b6130c6f0:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2efd-794c-8feb-da8b6130c6f0"}', 50, 'done', 1, '2026-10-25 02:39:14.684408+00', NULL, NULL, '2026-10-25 02:39:14.684408+00', '2026-10-25 02:39:16.174732+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a170ed-2ed2-7267-84ab-140e75785613:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2ed2-7267-84ab-140e75785613"}', 50, 'done', 1, '2026-10-25 02:39:14.684408+00', NULL, NULL, '2026-10-25 02:39:14.684408+00', '2026-10-25 02:39:16.185002+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a170ed-2ed1-736d-9bed-8ceee7e553a2:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2ed1-736d-9bed-8ceee7e553a2"}', 50, 'done', 1, '2026-10-25 02:39:14.639079+00', NULL, NULL, '2026-10-25 02:39:14.639079+00', '2026-10-25 02:39:16.195978+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a170ed-2ed1-733c-baa6-fb0cd63acc08:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2ed1-733c-baa6-fb0cd63acc08"}', 50, 'done', 1, '2026-10-25 02:39:14.639079+00', NULL, NULL, '2026-10-25 02:39:14.639079+00', '2026-10-25 02:39:16.208589+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a170ed-2ecf-73d7-8213-882ae190675a:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2ecf-73d7-8213-882ae190675a"}', 50, 'done', 1, '2026-10-25 02:39:14.639079+00', NULL, NULL, '2026-10-25 02:39:14.639079+00', '2026-10-25 02:39:16.220877+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a170ed-2e80-772b-aa1f-535b2cf1e8bc:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2e80-772b-aa1f-535b2cf1e8bc"}', 50, 'done', 1, '2026-10-25 02:39:14.639079+00', NULL, NULL, '2026-10-25 02:39:14.639079+00', '2026-10-25 02:39:16.235288+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a170ed-2e7f-7649-a260-6be058733c05:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2e7f-7649-a260-6be058733c05"}', 150, 'done', 1, '2026-10-25 02:39:14.555556+00', NULL, NULL, '2026-10-25 02:39:14.555556+00', '2026-10-25 02:39:16.246392+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a170ed-2e7e-7a3a-8fbf-0841a10a1666:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2e7e-7a3a-8fbf-0841a10a1666"}', 150, 'done', 1, '2026-10-25 02:39:14.555556+00', NULL, NULL, '2026-10-25 02:39:14.555556+00', '2026-10-25 02:39:16.258038+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a170ed-2e7c-72d0-8d26-a7038eb64c9d:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-2e7c-72d0-8d26-a7038eb64c9d"}', 150, 'done', 1, '2026-10-25 02:39:14.555556+00', NULL, NULL, '2026-10-25 02:39:14.555556+00', '2026-10-25 02:39:16.27235+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a170ed-2e7e-7a3a-8fbf-0841a10a1666:e17963d30bc882d8adf5bd5f609d7a58:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2e7e-7a3a-8fbf-0841a10a1666", "window_hash": "e17963d30bc882d8adf5bd5f609d7a58"}', 210, 'done', 1, '2026-10-25 02:39:14.555556+00', NULL, NULL, '2026-10-25 02:39:14.555556+00', '2026-10-25 02:39:16.29515+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a170ed-2e80-772b-aa1f-535b2cf1e8bc:d45609d8a220a0de0ca3ecdb61b842c2:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2e80-772b-aa1f-535b2cf1e8bc", "window_hash": "d45609d8a220a0de0ca3ecdb61b842c2"}', 210, 'done', 1, '2026-10-25 02:39:14.639079+00', NULL, NULL, '2026-10-25 02:39:14.639079+00', '2026-10-25 02:39:16.318838+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a170ed-2ed1-733c-baa6-fb0cd63acc08:ecbc5ea4ab42ecc8b950052da6c46acf:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2ed1-733c-baa6-fb0cd63acc08", "window_hash": "ecbc5ea4ab42ecc8b950052da6c46acf"}', 210, 'done', 1, '2026-10-25 02:39:14.639079+00', NULL, NULL, '2026-10-25 02:39:14.639079+00', '2026-10-25 02:39:16.338424+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a170ed-2ed2-7267-84ab-140e75785613:1906af4e4f89cfe929b45c254070beb6:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2ed2-7267-84ab-140e75785613", "window_hash": "1906af4e4f89cfe929b45c254070beb6"}', 210, 'done', 1, '2026-10-25 02:39:14.684408+00', NULL, NULL, '2026-10-25 02:39:14.684408+00', '2026-10-25 02:39:16.356229+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a170ed-2efe-730b-82e0-d70e79de710c:a2fc1770815533cabd75eaa30ac182ea:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2efe-730b-82e0-d70e79de710c", "window_hash": "a2fc1770815533cabd75eaa30ac182ea"}', 210, 'done', 1, '2026-10-25 02:39:14.684408+00', NULL, NULL, '2026-10-25 02:39:14.684408+00', '2026-10-25 02:39:16.375692+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a170ed-2eff-7251-a318-4fb161af4c35:4fb260dfcdbc608ce8d17989f488729b:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2eff-7251-a318-4fb161af4c35", "window_hash": "4fb260dfcdbc608ce8d17989f488729b"}', 210, 'done', 1, '2026-10-25 02:39:14.724603+00', NULL, NULL, '2026-10-25 02:39:14.724603+00', '2026-10-25 02:39:16.394863+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a170ed-2ed1-733c-baa6-fb0cd63acc08:6a1d06aa06cdd7a15dddd0642cbdc7ff:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2ed1-733c-baa6-fb0cd63acc08", "window_hash": "6a1d06aa06cdd7a15dddd0642cbdc7ff"}', 100, 'done', 1, '2026-10-25 02:39:16.782005+00', NULL, NULL, '2026-10-25 02:39:16.782005+00', '2026-10-25 02:39:17.553829+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a170ed-372e-7672-845b-02d3d672d7b2:caff87806d0b9b02c10809893028216f:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-372e-7672-845b-02d3d672d7b2", "window_hash": "caff87806d0b9b02c10809893028216f"}', 100, 'done', 1, '2026-10-25 02:39:16.782005+00', NULL, NULL, '2026-10-25 02:39:16.782005+00', '2026-10-25 02:39:17.569525+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a170ed-3b9b-7077-9c45-7b55b7361bbf:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3b9b-7077-9c45-7b55b7361bbf"}', 150, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.660594+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a170ed-3780-747c-9eca-7f80668b61a1:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3780-747c-9eca-7f80668b61a1"}', 50, 'done', 1, '2026-10-25 02:39:16.859822+00', NULL, NULL, '2026-10-25 02:39:16.859822+00', '2026-10-25 02:39:17.414248+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a170ed-377f-77df-831d-61cb15df2751:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-377f-77df-831d-61cb15df2751"}', 50, 'done', 1, '2026-10-25 02:39:16.859822+00', NULL, NULL, '2026-10-25 02:39:16.859822+00', '2026-10-25 02:39:17.424629+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a170ed-3730-749a-8f03-e0e4b857cd76:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3730-749a-8f03-e0e4b857cd76"}', 50, 'done', 1, '2026-10-25 02:39:16.782005+00', NULL, NULL, '2026-10-25 02:39:16.782005+00', '2026-10-25 02:39:17.43524+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a170ed-372f-73b1-b080-509f6e67eb0a:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-372f-73b1-b080-509f6e67eb0a"}', 50, 'done', 1, '2026-10-25 02:39:16.782005+00', NULL, NULL, '2026-10-25 02:39:16.782005+00', '2026-10-25 02:39:17.451258+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a170ed-372e-7672-845b-02d3d672d7b2:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-372e-7672-845b-02d3d672d7b2"}', 50, 'done', 1, '2026-10-25 02:39:16.782005+00', NULL, NULL, '2026-10-25 02:39:16.782005+00', '2026-10-25 02:39:17.461796+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a170ed-377f-77df-831d-61cb15df2751:96e2d73d40a27df3fd35201db9c87c2a:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-377f-77df-831d-61cb15df2751", "window_hash": "96e2d73d40a27df3fd35201db9c87c2a"}', 100, 'done', 1, '2026-10-25 02:39:16.859822+00', NULL, NULL, '2026-10-25 02:39:16.859822+00', '2026-10-25 02:39:17.477926+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a170ed-372f-73b1-b080-509f6e67eb0a:2ce358b1e111c22140d2afcc76b869bd:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-372f-73b1-b080-509f6e67eb0a", "window_hash": "2ce358b1e111c22140d2afcc76b869bd"}', 100, 'done', 1, '2026-10-25 02:39:16.859822+00', NULL, NULL, '2026-10-25 02:39:16.859822+00', '2026-10-25 02:39:17.494288+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a170ed-2eff-7251-a318-4fb161af4c35:85d728071b7463474db1f4302912144b:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2eff-7251-a318-4fb161af4c35", "window_hash": "85d728071b7463474db1f4302912144b"}', 100, 'done', 1, '2026-10-25 02:39:16.859822+00', NULL, NULL, '2026-10-25 02:39:16.859822+00', '2026-10-25 02:39:17.512281+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a170ed-2efe-730b-82e0-d70e79de710c:59594c42179145b191cb8ad246b29cb9:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2efe-730b-82e0-d70e79de710c", "window_hash": "59594c42179145b191cb8ad246b29cb9"}', 100, 'done', 1, '2026-10-25 02:39:16.859822+00', NULL, NULL, '2026-10-25 02:39:16.859822+00', '2026-10-25 02:39:17.528183+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a170ed-372f-73b1-b080-509f6e67eb0a:a7db0efb96bcbe9d94167694f9739166:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-372f-73b1-b080-509f6e67eb0a", "window_hash": "a7db0efb96bcbe9d94167694f9739166"}', 100, 'obsolete', 1, '2026-10-25 02:39:16.782005+00', NULL, NULL, '2026-10-25 02:39:16.782005+00', '2026-10-25 02:39:17.531817+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a170ed-2efe-730b-82e0-d70e79de710c:115dd0a0d9b80d6778ba1e98af5e88be:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2efe-730b-82e0-d70e79de710c", "window_hash": "115dd0a0d9b80d6778ba1e98af5e88be"}', 100, 'obsolete', 1, '2026-10-25 02:39:16.782005+00', NULL, NULL, '2026-10-25 02:39:16.782005+00', '2026-10-25 02:39:17.535343+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a170ed-2ed2-7267-84ab-140e75785613:6e051f96820da041b3ee6ff14c66dd76:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-2e74-74dc-9126-8229dbb2001f', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-2ed2-7267-84ab-140e75785613", "window_hash": "6e051f96820da041b3ee6ff14c66dd76"}', 100, 'obsolete', 1, '2026-10-25 02:39:16.782005+00', NULL, NULL, '2026-10-25 02:39:16.782005+00', '2026-10-25 02:39:17.539075+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a170ed-3b9b-7b4a-8965-36c67a74fa0d:9854bd4b091eb578fa7a5c3c1c89b017:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-3b9b-7b4a-8965-36c67a74fa0d", "window_hash": "9854bd4b091eb578fa7a5c3c1c89b017"}', 210, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.6748+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a170ed-3b9d-7568-94b7-e82060a83df9:b78bf90ec253a3af44fa156dede28842:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-3b9d-7568-94b7-e82060a83df9", "window_hash": "b78bf90ec253a3af44fa156dede28842"}', 210, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.693919+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a170ed-3b9e-70d7-b630-9e44ef8ab95c:2c32f3b82328ababcfe3a59f307eee90:extract-daff401945e5ac9a9cf3c73be2923769', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "extract-daff401945e5ac9a9cf3c73be2923769", "revision_id": "01a170ed-3b9e-70d7-b630-9e44ef8ab95c", "window_hash": "2c32f3b82328ababcfe3a59f307eee90"}', 210, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.711085+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a170ed-3ba1-7ad6-9dce-a38eb2660e35:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3ba1-7ad6-9dce-a38eb2660e35"}', 150, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.582208+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a170ed-3b9e-70d7-b630-9e44ef8ab95c:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3b9e-70d7-b630-9e44ef8ab95c"}', 150, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.595546+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a170ed-3b9d-7eb7-bbe6-c3752295f193:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3b9d-7eb7-bbe6-c3752295f193"}', 150, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.608236+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a170ed-3b9d-7568-94b7-e82060a83df9:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3b9d-7568-94b7-e82060a83df9"}', 150, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.621994+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a170ed-3b9c-7b57-8e6c-515d414980d4:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3b9c-7b57-8e6c-515d414980d4"}', 150, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.632283+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a170ed-3b9b-7b4a-8965-36c67a74fa0d:embed-93ecc68adcc77f5e90b995c6b20b3473', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{"generation": "embed-93ecc68adcc77f5e90b995c6b20b3473", "revision_id": "01a170ed-3b9b-7b4a-8965-36c67a74fa0d"}', 150, 'done', 1, '2026-10-25 02:39:17.914144+00', NULL, NULL, '2026-10-25 02:39:17.914144+00', '2026-10-25 02:39:18.646878+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a170ed-2e82-7066-b5aa-8e18629b3ebd', '01a170ed-2e74-74dc-9126-8229dbb2001f');


--
-- Data for Name: owner_repair; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-daff401945e5ac9a9cf3c73be2923769', 'extract', 'stub', 'http://127.0.0.1:34845/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "a6fec3fe3aabc852", "aliases": "361e584289ae46a4", "confirm": "c1a68b38f8fcae60", "compiler": "extract-v16", "endpoint": "http://127.0.0.1:34845/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "ec86a5ac4362f77d", "temperature": 0, "target_chars": 6000, "context_chars": 1000, "context_turns": 3}', '2026-10-25 02:39:14.467606+00', '2026-10-25 02:39:14.469197+00');
INSERT INTO public.projection_generation VALUES ('embed-93ecc68adcc77f5e90b995c6b20b3473', 'embed', 'stub-embed', 'http://127.0.0.1:34845/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:34845/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-10-25 02:39:14.467606+00', '2026-10-25 02:39:14.474682+00');
INSERT INTO public.projection_generation VALUES ('summarize-1d802b810bb00b097e18e996887d1595', 'summarize', 'stub', 'http://127.0.0.1:34845/v1', '{"lag": 4, "kind": "summarize", "model": "stub", "prompt": "1cb5649d13d81671", "window": 8, "version": "summarize-v3", "endpoint": "http://127.0.0.1:34845/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "message_chars": 6000}', '2026-10-25 02:39:14.467606+00', '2026-10-25 02:39:14.477439+00');
INSERT INTO public.projection_generation VALUES ('canon-33d653cadbd2bc05d32398b7898c6ef7', 'canon', 'stub', 'http://127.0.0.1:34845/v1', '{"kind": "canon", "model": "stub", "prompt": "c084747d55328ce7", "version": "canon-v1", "endpoint": "http://127.0.0.1:34845/v1", "json_mode": true, "max_parts": 4, "normalizer": "clean-v3", "part_chars": 6000, "predicates": "9aebb33c40fcda7c", "temperature": 0}', '2026-10-25 02:39:14.467606+00', '2026-10-25 02:39:14.478831+00');
INSERT INTO public.projection_generation VALUES ('reveal-645401eb85e9a1eecec95b1d46d32f4d', 'reveal', 'stub', 'http://127.0.0.1:34845/v1', '{"kind": "reveal", "model": "stub", "prompt": "799b88903bfe0c44", "version": "reveal-v1", "compiler": "extract-v15", "endpoint": "http://127.0.0.1:34845/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "target_chars": 6000, "context_chars": 1000, "context_turns": 3}', '2026-10-25 02:39:14.467606+00', '2026-10-25 02:39:14.482461+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a170ed-2ec4-7466-8c19-d1cd1f5a83ef', '01a170ed-2e74-74dc-9126-8229dbb2001f', '01a170ed-2e83-71c7-8117-b888a9bc5471', 'Is Rin with you?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a170ed-2e7f-7649-a260-6be058733c05", "keyword_score": 1.0986, "host_logical_id": "6ac5e480-dcff-48e7-b6c0-eb651a1da3e0"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a170ed-2e7f-7649-a260-6be058733c05", "keyword_score": 1.0986, "host_logical_id": "6ac5e480-dcff-48e7-b6c0-eb651a1da3e0"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 51.86, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.87, "fits_at": null, "lexical": 11.3, "threads": 0, "keywords": 15.45, "extractor": "extract-daff401945e5", "embed_wait": 11.26, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 56.32, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-93ecc68adcc77f", "memory_mode_withheld": 0}', 'fresh', '2026-10-25 02:39:14.57237+00', 'packet-v19', 600, 3, '', '["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "6ac5e480-dcff-48e7-b6c0-eb651a1da3e0", "84071aae-41a4-47d6-924b-8c36e611a314", "f38e7339-9400-43da-b1be-c877d18f8a36"]', 'extract-daff401945e5ac9a9cf3c73be2923769', 'embed-93ecc68adcc77f5e90b995c6b20b3473', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-33d653cadbd2bc05d32398b7898c6ef7", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-1d802b810bb00b097e18e996887d1595", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a170ed-2ef2-7efc-8753-61d4fb9347dc', '01a170ed-2e74-74dc-9126-8229dbb2001f', '01a170ed-2e83-71c7-8117-b888a9bc5471', 'Let''s check the market.', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a170ed-2ed1-736d-9bed-8ceee7e553a2", "keyword_score": 5.8377, "host_logical_id": "4ca459ab-8e1d-49c2-a496-83b729815e8d"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a170ed-2ed1-736d-9bed-8ceee7e553a2", "keyword_score": 5.8377, "host_logical_id": "4ca459ab-8e1d-49c2-a496-83b729815e8d"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 8.17, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 2.29, "fits_at": null, "lexical": 3.01, "threads": 0, "keywords": 6.79, "extractor": "extract-daff401945e5", "embed_wait": 0.02, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 20.47, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-93ecc68adcc77f", "memory_mode_withheld": 0}', 'fresh', '2026-10-25 02:39:14.654458+00', 'packet-v19', 600, 7, '', '["0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "4ca459ab-8e1d-49c2-a496-83b729815e8d", "781c9920-7e76-4e10-b639-a6ff0a29e346", "addfdb4e-69d7-4c3c-93d3-f97c4853e2d6"]', 'extract-daff401945e5ac9a9cf3c73be2923769', 'embed-93ecc68adcc77f5e90b995c6b20b3473', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-33d653cadbd2bc05d32398b7898c6ef7", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-1d802b810bb00b097e18e996887d1595", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a170ed-2f1a-7a4e-b3c7-26ccca0558a4', '01a170ed-2e74-74dc-9126-8229dbb2001f', '01a170ed-2e83-71c7-8117-b888a9bc5471', 'Where do we meet tonight?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a170ed-2eff-7f7d-bdef-e12c8e72cacf", "keyword_score": 4.7958, "host_logical_id": "81d23b5a-e7fd-430d-9b8f-eb3ee24aa956"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a170ed-2eff-7f7d-bdef-e12c8e72cacf", "keyword_score": 4.7958, "host_logical_id": "81d23b5a-e7fd-430d-9b8f-eb3ee24aa956"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 9.23, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.04, "fits_at": null, "lexical": 3.29, "threads": 0, "keywords": 6.04, "extractor": "extract-daff401945e5", "embed_wait": 0.0, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 16.28, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-93ecc68adcc77f", "memory_mode_withheld": 0}', 'fresh', '2026-10-25 02:39:14.698333+00', 'packet-v19', 600, 11, '', '["2d22a703-4e99-478e-83e4-53f9fc05ea54", "81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "95695118-8f4a-44a8-9f70-4dd03a61a038", "c9182849-3005-4b67-bf1f-cf4f222b86fb"]', 'extract-daff401945e5ac9a9cf3c73be2923769', 'embed-93ecc68adcc77f5e90b995c6b20b3473', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-33d653cadbd2bc05d32398b7898c6ef7", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-1d802b810bb00b097e18e996887d1595", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a170ed-2f41-70d4-9b4d-5c2c1c9fa348', '01a170ed-2e74-74dc-9126-8229dbb2001f', '01a170ed-2e83-71c7-8117-b888a9bc5471', 'Where is Mina now?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a170ed-2f25-71f4-9f8f-ad73efeb552c", "keyword_score": 0.7732, "host_logical_id": "25fa145b-c398-4611-b292-838ba031e1b2"}, {"rrf": 0.03151, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a170ed-2e80-772b-aa1f-535b2cf1e8bc", "keyword_score": 0.7732, "host_logical_id": "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f"}, {"rrf": 0.03102, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a170ed-2e7e-7a3a-8fbf-0841a10a1666", "keyword_score": 0.7732, "host_logical_id": "84071aae-41a4-47d6-924b-8c36e611a314"}, {"rrf": 0.01613, "sim": null, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a170ed-2eff-7251-a318-4fb161af4c35", "keyword_score": 0.7732, "host_logical_id": "95695118-8f4a-44a8-9f70-4dd03a61a038"}, {"rrf": 0.01587, "sim": null, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a170ed-2ed1-733c-baa6-fb0cd63acc08", "keyword_score": 0.7732, "host_logical_id": "0bbd2d85-28eb-4394-a904-9fe3d5d8de33"}, {"rrf": 0.01562, "sim": null, "score": 0.0, "position": 4, "user_score": 0.0, "revision_id": "01a170ed-2ecf-73d7-8213-882ae190675a", "keyword_score": 0.7732, "host_logical_id": "781c9920-7e76-4e10-b639-a6ff0a29e346"}]', '[{"turn": 0, "score": 0.03102, "revision_id": "01a170ed-2e7e-7a3a-8fbf-0841a10a1666"}, {"turn": 1, "score": 0.03151, "revision_id": "01a170ed-2e80-772b-aa1f-535b2cf1e8bc"}, {"turn": 2, "score": 0.01562, "revision_id": "01a170ed-2ecf-73d7-8213-882ae190675a"}, {"turn": 2, "score": 0.01587, "revision_id": "01a170ed-2ed1-733c-baa6-fb0cd63acc08"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a170ed-2f25-71f4-9f8f-ad73efeb552c", "keyword_score": 0.7732, "host_logical_id": "25fa145b-c398-4611-b292-838ba031e1b2"}, {"rrf": 0.01613, "sim": null, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a170ed-2eff-7251-a318-4fb161af4c35", "keyword_score": 0.7732, "host_logical_id": "95695118-8f4a-44a8-9f70-4dd03a61a038"}]', 227, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 9.37, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 4, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 2.1, "fits_at": null, "lexical": 2.87, "threads": 0, "keywords": 2.54, "extractor": "extract-daff401945e5", "embed_lead": 16.57, "embed_wait": 0.0, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 14.63, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-93ecc68adcc77f", "memory_mode_withheld": 0}', 'fresh', '2026-10-25 02:39:14.738608+00', 'packet-v19', 600, 12, '', '["25fa145b-c398-4611-b292-838ba031e1b2", "81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "95695118-8f4a-44a8-9f70-4dd03a61a038", "c9182849-3005-4b67-bf1f-cf4f222b86fb"]', 'extract-daff401945e5ac9a9cf3c73be2923769', 'embed-93ecc68adcc77f5e90b995c6b20b3473', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-33d653cadbd2bc05d32398b7898c6ef7", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-1d802b810bb00b097e18e996887d1595", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a170ed-2e80-772b-aa1f-535b2cf1e8bc"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 1, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a170ed-2e7e-7a3a-8fbf-0841a10a1666"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 0, "label": "supportive", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a170ed-2ed1-733c-baa6-fb0cd63acc08"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a170ed-2ecf-73d7-8213-882ae190675a"}, "tok": 23, "why": "placed", "kind": "excerpt", "text": "What did Mina say before she left?", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a170ed-374b-7942-9a22-d938dadb6e33', '01a170ed-2e74-74dc-9126-8229dbb2001f', '01a170ed-3734-7267-9522-e800504524a2', 'And the compass?', '[{"rrf": 0.04741, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a170ed-2efe-730b-82e0-d70e79de710c", "keyword_score": 2.0149, "host_logical_id": "c9182849-3005-4b67-bf1f-cf4f222b86fb"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a170ed-3730-749a-8f03-e0e4b857cd76", "keyword_score": 2.0149, "host_logical_id": "4107b879-0f06-4ee1-a727-a940117c0f98"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a170ed-2e7e-7a3a-8fbf-0841a10a1666", "keyword_score": 0.0, "host_logical_id": "84071aae-41a4-47d6-924b-8c36e611a314"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a170ed-2e7c-72d0-8d26-a7038eb64c9d", "keyword_score": 0.0, "host_logical_id": "f38e7339-9400-43da-b1be-c877d18f8a36"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a170ed-2ed2-7267-84ab-140e75785613", "keyword_score": 0.0, "host_logical_id": "addfdb4e-69d7-4c3c-93d3-f97c4853e2d6"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a170ed-2ed1-733c-baa6-fb0cd63acc08", "keyword_score": 0.0, "host_logical_id": "0bbd2d85-28eb-4394-a904-9fe3d5d8de33"}]', '[{"turn": 4, "score": 0.04741, "revision_id": "01a170ed-2efe-730b-82e0-d70e79de710c"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a170ed-3730-749a-8f03-e0e4b857cd76", "keyword_score": 2.0149, "host_logical_id": "4107b879-0f06-4ee1-a727-a940117c0f98"}]', 222, '{"fit": 0.0, "cast": 2, "path": "normal", "embed": 7.67, "facts": 0, "placed": {"fact": 2, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.23, "fits_at": null, "lexical": 3.37, "threads": 0, "keywords": 2.86, "extractor": "extract-daff401945e5", "embed_lead": 16.49, "embed_wait": 0.01, "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["Mina", "{{user}}"], "below_floor": 3, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 16.29, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 1, "embedding_projection": "embed-93ecc68adcc77f", "memory_mode_withheld": 0}', 'fresh', '2026-10-25 02:39:16.795631+00', 'packet-v19', 600, 14, '', '["25fa145b-c398-4611-b292-838ba031e1b2", "4107b879-0f06-4ee1-a727-a940117c0f98", "95695118-8f4a-44a8-9f70-4dd03a61a038", "c6010e47-59bb-41a7-8254-ec8a80cdbecc"]', 'extract-daff401945e5ac9a9cf3c73be2923769', 'embed-93ecc68adcc77f5e90b995c6b20b3473', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-33d653cadbd2bc05d32398b7898c6ef7", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-1d802b810bb00b097e18e996887d1595", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 7}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "label": "required", "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 2}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "label": "required", "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a170ed-2efe-730b-82e0-d70e79de710c"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a170ed-2e7c-72d0-8d26-a7038eb64c9d"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "label": "supportive", "placed": false}, {"ref": {"revision": "01a170ed-2ed2-7267-84ab-140e75785613"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 3, "label": "supportive", "marks": {"unextracted": true}, "placed": false}, {"ref": {"revision": "01a170ed-2ed1-733c-baa6-fb0cd63acc08"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": false}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a170ed-3771-79e6-b40b-b68f2b74c6aa', '01a170ed-2e74-74dc-9126-8229dbb2001f', '01a170ed-3734-7267-9522-e800504524a2', 'compass', '[{"rrf": 0.04615, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a170ed-2efe-730b-82e0-d70e79de710c", "keyword_score": 2.0149, "host_logical_id": "c9182849-3005-4b67-bf1f-cf4f222b86fb"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a170ed-3730-749a-8f03-e0e4b857cd76", "keyword_score": 2.0149, "host_logical_id": "4107b879-0f06-4ee1-a727-a940117c0f98"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a170ed-2eff-7251-a318-4fb161af4c35", "keyword_score": 0.0, "host_logical_id": "95695118-8f4a-44a8-9f70-4dd03a61a038"}]', '[{"turn": 4, "score": 0.04615, "revision_id": "01a170ed-2efe-730b-82e0-d70e79de710c"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a170ed-3730-749a-8f03-e0e4b857cd76", "keyword_score": 2.0149, "host_logical_id": "4107b879-0f06-4ee1-a727-a940117c0f98"}]', 222, '{"fit": 0.01, "cast": 2, "path": "normal", "embed": 6.67, "facts": 0, "placed": {"fact": 2, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.24, "fits_at": null, "lexical": 4.34, "threads": 0, "keywords": 4.17, "extractor": "extract-daff401945e5", "embed_wait": 0.01, "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["Mina", "{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 18.29, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-93ecc68adcc77f", "memory_mode_withheld": 0}', 'fresh', '2026-10-25 02:39:16.831246+00', 'packet-v19', 600, 15, '', '["25fa145b-c398-4611-b292-838ba031e1b2", "4107b879-0f06-4ee1-a727-a940117c0f98", "99f4ea34-3f07-4a98-9af3-cadd5b7251de", "c6010e47-59bb-41a7-8254-ec8a80cdbecc"]', 'extract-daff401945e5ac9a9cf3c73be2923769', 'embed-93ecc68adcc77f5e90b995c6b20b3473', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-33d653cadbd2bc05d32398b7898c6ef7", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-1d802b810bb00b097e18e996887d1595", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 7}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "label": "required", "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 2}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "label": "required", "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a170ed-2efe-730b-82e0-d70e79de710c"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a170ed-2eff-7251-a318-4fb161af4c35"}, "tok": 0, "why": "repeats", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 5, "label": "supportive", "placed": false, "repeats": {"assertion": 7}}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a170ed-3798-773d-9923-9921789004f3', '01a170ed-2e74-74dc-9126-8229dbb2001f', '01a170ed-3784-7603-abc4-a6e8596671c1', 'Let''s go.', '[{"rrf": 0.04865, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a170ed-2ed1-736d-9bed-8ceee7e553a2", "keyword_score": 2.0794, "host_logical_id": "4ca459ab-8e1d-49c2-a496-83b729815e8d"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a170ed-3780-747c-9eca-7f80668b61a1", "keyword_score": 2.0794, "host_logical_id": "660db083-0a7d-42e2-8c16-1b38b97dd42c"}]', '[{"turn": 3, "score": 0.04865, "revision_id": "01a170ed-2ed1-736d-9bed-8ceee7e553a2"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a170ed-3780-747c-9eca-7f80668b61a1", "keyword_score": 2.0794, "host_logical_id": "660db083-0a7d-42e2-8c16-1b38b97dd42c"}]', 138, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 8.21, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 2.08, "fits_at": null, "lexical": 2.86, "threads": 0, "keywords": 2.69, "extractor": "extract-daff401945e5", "embed_lead": 17.35, "embed_wait": 0.01, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 13.29, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-93ecc68adcc77f", "memory_mode_withheld": 0}', 'fresh', '2026-10-25 02:39:16.875112+00', 'packet-v19', 600, 16, '', '["4107b879-0f06-4ee1-a727-a940117c0f98", "660db083-0a7d-42e2-8c16-1b38b97dd42c", "99f4ea34-3f07-4a98-9af3-cadd5b7251de", "c6010e47-59bb-41a7-8254-ec8a80cdbecc"]', 'extract-daff401945e5ac9a9cf3c73be2923769', 'embed-93ecc68adcc77f5e90b995c6b20b3473', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-33d653cadbd2bc05d32398b7898c6ef7", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-1d802b810bb00b097e18e996887d1595", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a170ed-2ed1-736d-9bed-8ceee7e553a2"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 3, "label": "required", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a170ed-3bb7-7619-824f-77a4980340a1', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '01a170ed-3ba4-74d6-89cd-993e44ecc303', 'Where is Rin?', '[{"rrf": 0.03227, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a170ed-3b9c-7b57-8e6c-515d414980d4", "keyword_score": 0.8473, "host_logical_id": "e1a2ea0a-42a1-41ed-8878-4e01a74c31b6"}, {"rrf": 0.03226, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a170ed-3b9d-7568-94b7-e82060a83df9", "keyword_score": 0.8473, "host_logical_id": "5d2c20ef-d024-474b-b24f-303940a9d3b8"}, {"rrf": 0.01639, "sim": null, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a170ed-3ba1-7ad6-9dce-a38eb2660e35", "keyword_score": 0.8473, "host_logical_id": "fb3b6a7d-daba-4fbf-90d2-26dce4c7090e"}]', '[{"turn": 1, "score": 0.03227, "revision_id": "01a170ed-3b9c-7b57-8e6c-515d414980d4"}, {"turn": 1, "score": 0.03226, "revision_id": "01a170ed-3b9d-7568-94b7-e82060a83df9"}]', '[{"rrf": 0.01639, "sim": null, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a170ed-3ba1-7ad6-9dce-a38eb2660e35", "keyword_score": 0.8473, "host_logical_id": "fb3b6a7d-daba-4fbf-90d2-26dce4c7090e"}]', 164, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 8.95, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.12, "fits_at": null, "lexical": 2.95, "threads": 0, "keywords": 2.51, "extractor": "extract-daff401945e5", "embed_wait": 0.0, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 12.82, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-93ecc68adcc77f", "memory_mode_withheld": 0}', 'fresh', '2026-10-25 02:39:17.93069+00', 'packet-v19', 600, 7, '', '["105e2ec3-55e4-4535-9e83-d3ce9e6a841a", "672fdb7d-c251-45b0-abae-a3837362a28b", "8bdc0b17-5006-4c36-90d2-5a866ce6664a", "fb3b6a7d-daba-4fbf-90d2-26dce4c7090e"]', 'extract-daff401945e5ac9a9cf3c73be2923769', 'embed-93ecc68adcc77f5e90b995c6b20b3473', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-33d653cadbd2bc05d32398b7898c6ef7", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-1d802b810bb00b097e18e996887d1595", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a170ed-3b9c-7b57-8e6c-515d414980d4"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 1, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a170ed-3b9d-7568-94b7-e82060a83df9"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 1, "label": "supportive", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a170ed-2f25-71f4-9f8f-ad73efeb552c', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.126683+00', '{"ms": 62, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2eff-7251-a318-4fb161af4c35', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.139435+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2eff-7f7d-bdef-e12c8e72cacf', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.150978+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2efe-730b-82e0-d70e79de710c', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.163357+00', '{"ms": 7, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2efd-794c-8feb-da8b6130c6f0', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.173277+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2ed2-7267-84ab-140e75785613', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.183538+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2ed1-736d-9bed-8ceee7e553a2', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.194512+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2ed1-733c-baa6-fb0cd63acc08', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.207061+00', '{"ms": 7, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2ecf-73d7-8213-882ae190675a', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.219211+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2e80-772b-aa1f-535b2cf1e8bc', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.233607+00', '{"ms": 8, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2e7f-7649-a260-6be058733c05', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.244869+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2e7e-7a3a-8fbf-0841a10a1666', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.256375+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-2e7c-72d0-8d26-a7038eb64c9d', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:16.270611+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3780-747c-9eca-7f80668b61a1', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:17.412715+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-377f-77df-831d-61cb15df2751', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:17.423241+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3730-749a-8f03-e0e4b857cd76', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:17.433745+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-372f-73b1-b080-509f6e67eb0a', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:17.449802+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-372e-7672-845b-02d3d672d7b2', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:17.460287+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3ba1-7ad6-9dce-a38eb2660e35', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:18.580679+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3b9e-70d7-b630-9e44ef8ab95c', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:18.593919+00', '{"ms": 8, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3b9d-7eb7-bbe6-c3752295f193', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:18.606693+00', '{"ms": 7, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3b9d-7568-94b7-e82060a83df9', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:18.620291+00', '{"ms": 8, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3b9c-7b57-8e6c-515d414980d4', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:18.630658+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3b9b-7b4a-8965-36c67a74fa0d', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:18.644539+00', '{"ms": 8, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a170ed-3b9b-7077-9c45-7b55b7361bbf', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-93ecc68adcc77f5e90b995c6b20b3473', '2026-10-25 02:39:18.658953+00', '{"ms": 8, "calls": 1}');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a170ed-2e7c-72d0-8d26-a7038eb64c9d', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-10-25 02:39:14.555556+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2e7e-7a3a-8fbf-0841a10a1666', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-10-25 02:39:14.555556+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2e7f-7649-a260-6be058733c05', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-10-25 02:39:14.555556+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2e80-772b-aa1f-535b2cf1e8bc', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-10-25 02:39:14.555556+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2ecf-73d7-8213-882ae190675a', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-10-25 02:39:14.639079+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2ed1-733c-baa6-fb0cd63acc08', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-10-25 02:39:14.639079+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2ed1-736d-9bed-8ceee7e553a2', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-10-25 02:39:14.639079+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2ed2-7267-84ab-140e75785613', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-10-25 02:39:14.639079+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2efd-794c-8feb-da8b6130c6f0', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-10-25 02:39:14.684408+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2efe-730b-82e0-d70e79de710c', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-10-25 02:39:14.684408+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2eff-7f7d-bdef-e12c8e72cacf', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-10-25 02:39:14.684408+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2eff-7251-a318-4fb161af4c35', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-10-25 02:39:14.684408+00');
INSERT INTO public.revision_text VALUES ('01a170ed-2f25-71f4-9f8f-ad73efeb552c', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-10-25 02:39:14.724603+00');
INSERT INTO public.revision_text VALUES ('01a170ed-372e-7672-845b-02d3d672d7b2', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-10-25 02:39:16.782005+00');
INSERT INTO public.revision_text VALUES ('01a170ed-372f-73b1-b080-509f6e67eb0a', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-10-25 02:39:16.782005+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3730-749a-8f03-e0e4b857cd76', 'clean-v3', 'And the compass?', 16, 16, '2026-10-25 02:39:16.782005+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3756-720b-bd1a-48128289e1ef', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-10-25 02:39:16.821806+00');
INSERT INTO public.revision_text VALUES ('01a170ed-377c-7b62-8498-2e44a5cea798', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-10-25 02:39:16.859822+00');
INSERT INTO public.revision_text VALUES ('01a170ed-377f-77df-831d-61cb15df2751', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-10-25 02:39:16.859822+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3780-747c-9eca-7f80668b61a1', 'clean-v3', 'Let''s go.', 9, 9, '2026-10-25 02:39:16.859822+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3b9b-7077-9c45-7b55b7361bbf', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-10-25 02:39:17.914144+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3b9b-7b4a-8965-36c67a74fa0d', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-10-25 02:39:17.914144+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3b9c-7b57-8e6c-515d414980d4', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-10-25 02:39:17.914144+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3b9d-7568-94b7-e82060a83df9', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-10-25 02:39:17.914144+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3b9d-7eb7-bbe6-c3752295f193', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-10-25 02:39:17.914144+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3b9e-70d7-b630-9e44ef8ab95c', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-10-25 02:39:17.914144+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3ba0-7c08-9a63-244b4324950d', 'clean-v3', '{{specialcomment::branchedfrom::6156ec08-e8a7-41c2-9213-440899a53af5::Harbor route::0bbd2d85-28eb-4394-a904-9fe3d5d8de33::}}', 124, 124, '2026-10-25 02:39:17.914144+00');
INSERT INTO public.revision_text VALUES ('01a170ed-3ba1-7ad6-9dce-a38eb2660e35', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-10-25 02:39:17.914144+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-10-25 02:39:12.916951+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-10-25 02:39:12.99649+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-10-25 02:39:13.013043+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-10-25 02:39:13.056004+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-10-25 02:39:13.077909+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-10-25 02:39:13.086859+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-10-25 02:39:13.088782+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-10-25 02:39:13.098809+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-10-25 02:39:13.116138+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-10-25 02:39:13.118438+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-10-25 02:39:13.120405+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-10-25 02:39:13.129453+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-10-25 02:39:13.158353+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-10-25 02:39:13.174842+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-10-25 02:39:13.177637+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-10-25 02:39:13.189946+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-10-25 02:39:13.191818+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-10-25 02:39:13.193563+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-10-25 02:39:13.195276+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-10-25 02:39:13.20837+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-10-25 02:39:13.210643+00');
INSERT INTO public.schema_migrations VALUES ('0022_thread_outcome_and_cause.sql', '9a8507f1b42457d2c44d568a2bd60d868f923613f8c83acb2be7f9104041cc88', '2026-10-25 02:39:13.212623+00');
INSERT INTO public.schema_migrations VALUES ('0023_summaries.sql', 'da452cf41917f9cc59c3a9d71e4114bf5179d3c5493669a5c7ce83ea13e0fb77', '2026-10-25 02:39:13.214347+00');
INSERT INTO public.schema_migrations VALUES ('0024_owner_repair.sql', 'de78024aceb993e7822500bb13d17d034b0123cdf67225fc9c8d82e16164e3be', '2026-10-25 02:39:13.228014+00');
INSERT INTO public.schema_migrations VALUES ('0025_canon.sql', '692a149bab93cd46b4bff801fc8ca0d857dc72ae88ca73471b33668cc2e694e3', '2026-10-25 02:39:13.241442+00');
INSERT INTO public.schema_migrations VALUES ('0026_canon_facts.sql', '5998bd556819cc977b9c0dabf9baa53303a5ac0504abb5742f6c3c11f1ec81dd', '2026-10-25 02:39:13.25831+00');
INSERT INTO public.schema_migrations VALUES ('0027_model_usage.sql', 'a0397dba46c52771feba09a4ce8f7fa1e8307fe36ba1a5fbaf4ad1489bfda2c6', '2026-10-25 02:39:13.264162+00');
INSERT INTO public.schema_migrations VALUES ('0028_reveal_checks.sql', '24d4cea55f72664dd0370f396582daa93d69881fc5f06dd5de46bfc295eb3325', '2026-10-25 02:39:13.266034+00');
INSERT INTO public.schema_migrations VALUES ('0029_state_dismiss.sql', '6d6c3162977286ea96ad0860e74e102fcd0fe24847a4aa49d9d72d9c16f3227d', '2026-10-25 02:39:13.268142+00');
INSERT INTO public.schema_migrations VALUES ('0030_extract_v17.sql', '2b5769d94c377d07b2ae6b7e1d4832211a9e9850443b54e5ffa057900ca2fb58', '2026-10-25 02:39:13.269864+00');
INSERT INTO public.schema_migrations VALUES ('0031_entity_exclude.sql', '46ca60d3b6c3d2c0e1af72a4d4581c57e8ae1bd156f437a277235cdb18fbd055', '2026-10-25 02:39:13.272247+00');
INSERT INTO public.schema_migrations VALUES ('0032_replies_only.sql', 'def2b7e56a5f87f72763664df386407be7e7df8fc4725d7c223fd40d187bd1a3', '2026-10-25 02:39:13.274089+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a170ed-2e7c-7aa5-8742-2f266872187e', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'f38e7339-9400-43da-b1be-c877d18f8a36', 'message', '2026-10-25 02:39:14.555556+00');
INSERT INTO public.source_object VALUES ('01a170ed-2e7e-74d9-beee-96c38387c7af', '01a170ed-2e74-74dc-9126-8229dbb2001f', '84071aae-41a4-47d6-924b-8c36e611a314', 'message', '2026-10-25 02:39:14.555556+00');
INSERT INTO public.source_object VALUES ('01a170ed-2e7f-761d-a5b9-e057a8711105', '01a170ed-2e74-74dc-9126-8229dbb2001f', '6ac5e480-dcff-48e7-b6c0-eb651a1da3e0', 'message', '2026-10-25 02:39:14.555556+00');
INSERT INTO public.source_object VALUES ('01a170ed-2e80-7302-a2d7-7f71ea742c65', '01a170ed-2e74-74dc-9126-8229dbb2001f', '5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f', 'message', '2026-10-25 02:39:14.555556+00');
INSERT INTO public.source_object VALUES ('01a170ed-2ecf-7155-aabb-efcb691e8512', '01a170ed-2e74-74dc-9126-8229dbb2001f', '781c9920-7e76-4e10-b639-a6ff0a29e346', 'message', '2026-10-25 02:39:14.639079+00');
INSERT INTO public.source_object VALUES ('01a170ed-2ed0-77a1-8325-f903aa386eed', '01a170ed-2e74-74dc-9126-8229dbb2001f', '0bbd2d85-28eb-4394-a904-9fe3d5d8de33', 'message', '2026-10-25 02:39:14.639079+00');
INSERT INTO public.source_object VALUES ('01a170ed-2ed1-72ec-94e5-cd5d26cea0c3', '01a170ed-2e74-74dc-9126-8229dbb2001f', '4ca459ab-8e1d-49c2-a496-83b729815e8d', 'message', '2026-10-25 02:39:14.639079+00');
INSERT INTO public.source_object VALUES ('01a170ed-2ed2-779b-973c-942f1be9b40f', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'addfdb4e-69d7-4c3c-93d3-f97c4853e2d6', 'message', '2026-10-25 02:39:14.639079+00');
INSERT INTO public.source_object VALUES ('01a170ed-2efc-7a15-9bd1-c4ab6a236ae1', '01a170ed-2e74-74dc-9126-8229dbb2001f', '2d22a703-4e99-478e-83e4-53f9fc05ea54', 'message', '2026-10-25 02:39:14.684408+00');
INSERT INTO public.source_object VALUES ('01a170ed-2efd-7a82-9f2e-2239d5c2f03b', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'c9182849-3005-4b67-bf1f-cf4f222b86fb', 'message', '2026-10-25 02:39:14.684408+00');
INSERT INTO public.source_object VALUES ('01a170ed-2efe-708c-bf32-74a640b25c4a', '01a170ed-2e74-74dc-9126-8229dbb2001f', '81d23b5a-e7fd-430d-9b8f-eb3ee24aa956', 'message', '2026-10-25 02:39:14.684408+00');
INSERT INTO public.source_object VALUES ('01a170ed-2eff-743f-abd8-aa723ecf90c7', '01a170ed-2e74-74dc-9126-8229dbb2001f', '95695118-8f4a-44a8-9f70-4dd03a61a038', 'message', '2026-10-25 02:39:14.684408+00');
INSERT INTO public.source_object VALUES ('01a170ed-2f25-7166-aeeb-2e2abeea4a78', '01a170ed-2e74-74dc-9126-8229dbb2001f', '25fa145b-c398-4611-b292-838ba031e1b2', 'message', '2026-10-25 02:39:14.724603+00');
INSERT INTO public.source_object VALUES ('01a170ed-372f-761c-a847-45116fe0002e', '01a170ed-2e74-74dc-9126-8229dbb2001f', 'c6010e47-59bb-41a7-8254-ec8a80cdbecc', 'message', '2026-10-25 02:39:16.782005+00');
INSERT INTO public.source_object VALUES ('01a170ed-3730-7fc2-a32f-faa8c47332eb', '01a170ed-2e74-74dc-9126-8229dbb2001f', '4107b879-0f06-4ee1-a727-a940117c0f98', 'message', '2026-10-25 02:39:16.782005+00');
INSERT INTO public.source_object VALUES ('01a170ed-3756-7283-9539-9c280ac55705', '01a170ed-2e74-74dc-9126-8229dbb2001f', '99f4ea34-3f07-4a98-9af3-cadd5b7251de', 'message', '2026-10-25 02:39:16.821806+00');
INSERT INTO public.source_object VALUES ('01a170ed-3780-7c09-9bee-369c5c0ec8d4', '01a170ed-2e74-74dc-9126-8229dbb2001f', '660db083-0a7d-42e2-8c16-1b38b97dd42c', 'message', '2026-10-25 02:39:16.859822+00');
INSERT INTO public.source_object VALUES ('01a170ed-3b9a-7135-8bce-094478c22805', '01a170ed-3b8d-736e-b523-180f1b7f68c2', 'ab88c7bf-c374-4e9e-ac1c-529198853f89', 'message', '2026-10-25 02:39:17.914144+00');
INSERT INTO public.source_object VALUES ('01a170ed-3b9b-7cec-b54f-784dcd3a3b83', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '4e9eb8d8-8459-4732-a101-8306ef331a9e', 'message', '2026-10-25 02:39:17.914144+00');
INSERT INTO public.source_object VALUES ('01a170ed-3b9c-76be-a1fb-e20e4f4c96ee', '01a170ed-3b8d-736e-b523-180f1b7f68c2', 'e1a2ea0a-42a1-41ed-8878-4e01a74c31b6', 'message', '2026-10-25 02:39:17.914144+00');
INSERT INTO public.source_object VALUES ('01a170ed-3b9c-78fb-9b88-4d8b16b10360', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '5d2c20ef-d024-474b-b24f-303940a9d3b8', 'message', '2026-10-25 02:39:17.914144+00');
INSERT INTO public.source_object VALUES ('01a170ed-3b9d-7936-b6ed-52032131838c', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '8bdc0b17-5006-4c36-90d2-5a866ce6664a', 'message', '2026-10-25 02:39:17.914144+00');
INSERT INTO public.source_object VALUES ('01a170ed-3b9e-746d-826f-714ec8a06523', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '105e2ec3-55e4-4535-9e83-d3ce9e6a841a', 'message', '2026-10-25 02:39:17.914144+00');
INSERT INTO public.source_object VALUES ('01a170ed-3b9f-74ef-94a0-ae82ae35bd1c', '01a170ed-3b8d-736e-b523-180f1b7f68c2', '672fdb7d-c251-45b0-abae-a3837362a28b', 'message', '2026-10-25 02:39:17.914144+00');
INSERT INTO public.source_object VALUES ('01a170ed-3ba1-7c8f-a97c-b1652cc2e6f5', '01a170ed-3b8d-736e-b523-180f1b7f68c2', 'fb3b6a7d-daba-4fbf-90d2-26dce4c7090e', 'message', '2026-10-25 02:39:17.914144+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a170ed-2e7c-72d0-8d26-a7038eb64c9d', '01a170ed-2e7c-7aa5-8742-2f266872187e', 'c149bb15bba0cffb6b2130a27314912abaa49d6a76710e6df6d6dcaacb301947', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "f38e7339-9400-43da-b1be-c877d18f8a36", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:14.555556+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2e7f-7649-a260-6be058733c05', '01a170ed-2e7f-761d-a5b9-e057a8711105', '70b496b6c09431817bdbdd1e7987f510d74d3375ce3d4d6ad2876d2538cba74c', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "6ac5e480-dcff-48e7-b6c0-eb651a1da3e0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:14.555556+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2e7e-7a3a-8fbf-0841a10a1666', '01a170ed-2e7e-74d9-beee-96c38387c7af', '462fa6f7201bf24cf59c0d09b2a17a41ecde09c8b2ee178ef919a4d17b875a5d', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "84071aae-41a4-47d6-924b-8c36e611a314", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "84071aae-41a4-47d6-924b-8c36e611a314", "specialComments": []}', '2026-10-25 02:39:14.555556+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2ecf-73d7-8213-882ae190675a', '01a170ed-2ecf-7155-aabb-efcb691e8512', '6dbaa90cdf09f4351152aca1b3d122512c06d122a4544e1e4e6c5b4650051f0c', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "781c9920-7e76-4e10-b639-a6ff0a29e346", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:14.639079+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2ed1-736d-9bed-8ceee7e553a2', '01a170ed-2ed1-72ec-94e5-cd5d26cea0c3', 'a75e32bbc6175d245709082f70a0e18e977e8e409d524230bdbd820879935572', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "4ca459ab-8e1d-49c2-a496-83b729815e8d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:14.639079+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2ed1-733c-baa6-fb0cd63acc08', '01a170ed-2ed0-77a1-8325-f903aa386eed', '42fd76ff2dbe365662a4828e495cfab9b1bb3bff40bfa8e6899ffa25a3582745', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "specialComments": []}', '2026-10-25 02:39:14.639079+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2efd-794c-8feb-da8b6130c6f0', '01a170ed-2efc-7a15-9bd1-c4ab6a236ae1', '09fd158139b781b06cb795e6be782627b2dc199eedd5081055096a56289d5ea7', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "2d22a703-4e99-478e-83e4-53f9fc05ea54", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:14.684408+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2eff-7f7d-bdef-e12c8e72cacf', '01a170ed-2efe-708c-bf32-74a640b25c4a', 'adeacd829f7ad76966cdda19c5775e385ef089513f5fbd6cd5e6115f3b4bbfed', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:14.684408+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2ed2-7267-84ab-140e75785613', '01a170ed-2ed2-779b-973c-942f1be9b40f', '275a3db894f968cea14e8ac64ffd2fc8115cb12db0ee41b99a1aecc744abaa44', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", "specialComments": []}', '2026-10-25 02:39:14.639079+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2efe-730b-82e0-d70e79de710c', '01a170ed-2efd-7a82-9f2e-2239d5c2f03b', 'de76e2e451561d73ee883eb2a615992d854b94205fff045c6e1c4161a6d16e6a', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "c9182849-3005-4b67-bf1f-cf4f222b86fb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c9182849-3005-4b67-bf1f-cf4f222b86fb", "specialComments": []}', '2026-10-25 02:39:14.684408+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2f25-71f4-9f8f-ad73efeb552c', '01a170ed-2f25-7166-aeeb-2e2abeea4a78', 'a7dfa70c82599858449423d9bcfcafdba6dffc51cf1a498922c61f8138e98ee4', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "25fa145b-c398-4611-b292-838ba031e1b2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:14.724603+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2eff-7251-a318-4fb161af4c35', '01a170ed-2eff-743f-abd8-aa723ecf90c7', '25b60c016b06a8f2be0a97ef959dad10316828bc21b52ecd6aaeb3eaa7e01ad8', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "95695118-8f4a-44a8-9f70-4dd03a61a038", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "95695118-8f4a-44a8-9f70-4dd03a61a038", "specialComments": []}', '2026-10-25 02:39:14.684408+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3730-749a-8f03-e0e4b857cd76', '01a170ed-3730-7fc2-a32f-faa8c47332eb', '35694a1a6fe119d3d2161f77bc4c698c687086bc77b04df0815b8d7de0785975', 'And the compass?', '{"name": null, "role": "user", "chatId": "4107b879-0f06-4ee1-a727-a940117c0f98", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:16.782005+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-2e80-772b-aa1f-535b2cf1e8bc', '01a170ed-2e80-7302-a2d7-7f71ea742c65', '001ca8a10e37e4937ed6aef6781c62bc91ac0a4ea53e32ef7a271a8e2eb132cc', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "specialComments": []}', '2026-10-25 02:39:14.555556+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-372e-7672-845b-02d3d672d7b2', '01a170ed-2e80-7302-a2d7-7f71ea742c65', '11ade1a8ed77bd47804b1fd62a39b9dc817d960c9315a85cde1b9c2203349d8a', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "specialComments": []}', '2026-10-25 02:39:16.782005+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-372f-73b1-b080-509f6e67eb0a', '01a170ed-372f-761c-a847-45116fe0002e', '4b4503ef5b6d681aa713716e946e4b2f4940fe1cdc9dcd6d48c10b1a01de8654', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "c6010e47-59bb-41a7-8254-ec8a80cdbecc", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c6010e47-59bb-41a7-8254-ec8a80cdbecc", "specialComments": []}', '2026-10-25 02:39:16.782005+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-377c-7b62-8498-2e44a5cea798', '01a170ed-2efc-7a15-9bd1-c4ab6a236ae1', 'd6a49ec5425b7451cdb2f93d116e425c03a02596e17b6d5025fa5afac734e00b', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "2d22a703-4e99-478e-83e4-53f9fc05ea54", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:16.859822+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3780-747c-9eca-7f80668b61a1', '01a170ed-3780-7c09-9bee-369c5c0ec8d4', '70447579b380527c7ade70e138891e563c53791694db84d622144c44e3c76d28', 'Let''s go.', '{"name": null, "role": "user", "chatId": "660db083-0a7d-42e2-8c16-1b38b97dd42c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:16.859822+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3756-720b-bd1a-48128289e1ef', '01a170ed-3756-7283-9539-9c280ac55705', '1076d7f5e87c731da81ca6dbbe31cbb091402bcf7a7fec879f74be8e3a321f9f', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "99f4ea34-3f07-4a98-9af3-cadd5b7251de", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "99f4ea34-3f07-4a98-9af3-cadd5b7251de", "specialComments": []}', '2026-10-25 02:39:16.821806+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-377f-77df-831d-61cb15df2751', '01a170ed-3756-7283-9539-9c280ac55705', '59bdd67f83572f3f4c8f8b1c12f5dbc11922eacb652efe1f8b87beccaa86d0a9', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "99f4ea34-3f07-4a98-9af3-cadd5b7251de", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "99f4ea34-3f07-4a98-9af3-cadd5b7251de", "specialComments": []}', '2026-10-25 02:39:16.859822+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3b9b-7077-9c45-7b55b7361bbf', '01a170ed-3b9a-7135-8bce-094478c22805', '44ebaa29747098dd45c4587bd3430f7450d39dae1a211a46437f071dc13017da', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "ab88c7bf-c374-4e9e-ac1c-529198853f89", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:17.914144+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3b9c-7b57-8e6c-515d414980d4', '01a170ed-3b9c-76be-a1fb-e20e4f4c96ee', 'e15640d28134ad3c7598486233d76f94675989754ee0ef99c167af3bed740077', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "e1a2ea0a-42a1-41ed-8878-4e01a74c31b6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:17.914144+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3b9d-7eb7-bbe6-c3752295f193', '01a170ed-3b9d-7936-b6ed-52032131838c', '3e061f9d2a8d128d8b69d9fd91ec82e234955a20183b1ce1e29e972b01222452', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "8bdc0b17-5006-4c36-90d2-5a866ce6664a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:17.914144+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3ba0-7c08-9a63-244b4324950d', '01a170ed-3b9f-74ef-94a0-ae82ae35bd1c', '9fb795bd4e419bd4352803e57d512517c2435375c9863b1209596ff4ca7c2426', '{{specialcomment::branchedfrom::6156ec08-e8a7-41c2-9213-440899a53af5::Harbor route::0bbd2d85-28eb-4394-a904-9fe3d5d8de33::}}', '{"name": null, "role": "char", "chatId": "672fdb7d-c251-45b0-abae-a3837362a28b", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::6156ec08-e8a7-41c2-9213-440899a53af5::Harbor route::0bbd2d85-28eb-4394-a904-9fe3d5d8de33::}}"]}', '2026-10-25 02:39:17.914144+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3ba1-7ad6-9dce-a38eb2660e35', '01a170ed-3ba1-7c8f-a97c-b1652cc2e6f5', 'bd736791e96c5985a50e245c1de13c5e42b08de6152d545d9cac146d5b368eb3', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "fb3b6a7d-daba-4fbf-90d2-26dce4c7090e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-25 02:39:17.914144+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3b9e-70d7-b630-9e44ef8ab95c', '01a170ed-3b9e-746d-826f-714ec8a06523', 'eaa8ab3cd206a514aa62cc8d5339aee0dc2402d3d0f8ac23794dd492483270db', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "105e2ec3-55e4-4535-9e83-d3ce9e6a841a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "specialComments": []}', '2026-10-25 02:39:17.914144+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3b9b-7b4a-8965-36c67a74fa0d', '01a170ed-3b9b-7cec-b54f-784dcd3a3b83', 'decc1b0b3e8b7870b0bd44031fe0d00a24233b773a0554d567874f8f6a589567', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "4e9eb8d8-8459-4732-a101-8306ef331a9e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "84071aae-41a4-47d6-924b-8c36e611a314", "specialComments": []}', '2026-10-25 02:39:17.914144+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a170ed-3b9d-7568-94b7-e82060a83df9', '01a170ed-3b9c-78fb-9b88-4d8b16b10360', '95f2ea83d2bc8362b945ddd98c5b4070f5a9f52ee78428295c1a5175492cb9bd', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "5d2c20ef-d024-474b-b24f-303940a9d3b8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "specialComments": []}', '2026-10-25 02:39:17.914144+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: summary; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a170ed-2e83-71c7-8117-b888a9bc5471', '[{"op": "insert", "after": ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "001ca8a10e37e4937ed6aef6781c62bc91ac0a4ea53e32ef7a271a8e2eb132cc"], "member": ["781c9920-7e76-4e10-b639-a6ff0a29e346", "6dbaa90cdf09f4351152aca1b3d122512c06d122a4544e1e4e6c5b4650051f0c"]}, {"op": "insert", "after": ["781c9920-7e76-4e10-b639-a6ff0a29e346", "6dbaa90cdf09f4351152aca1b3d122512c06d122a4544e1e4e6c5b4650051f0c"], "member": ["0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "42fd76ff2dbe365662a4828e495cfab9b1bb3bff40bfa8e6899ffa25a3582745"]}, {"op": "insert", "after": ["0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "42fd76ff2dbe365662a4828e495cfab9b1bb3bff40bfa8e6899ffa25a3582745"], "member": ["4ca459ab-8e1d-49c2-a496-83b729815e8d", "a75e32bbc6175d245709082f70a0e18e977e8e409d524230bdbd820879935572"]}, {"op": "insert", "after": ["4ca459ab-8e1d-49c2-a496-83b729815e8d", "a75e32bbc6175d245709082f70a0e18e977e8e409d524230bdbd820879935572"], "member": ["addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", "275a3db894f968cea14e8ac64ffd2fc8115cb12db0ee41b99a1aecc744abaa44"]}]', '[{"new": ["781c9920-7e76-4e10-b639-a6ff0a29e346", "6dbaa90cdf09f4351152aca1b3d122512c06d122a4544e1e4e6c5b4650051f0c"], "old": null, "kind": "append", "position": 4, "host_logical_id": "781c9920-7e76-4e10-b639-a6ff0a29e346"}, {"new": ["0bbd2d85-28eb-4394-a904-9fe3d5d8de33", "42fd76ff2dbe365662a4828e495cfab9b1bb3bff40bfa8e6899ffa25a3582745"], "old": null, "kind": "append", "position": 5, "host_logical_id": "0bbd2d85-28eb-4394-a904-9fe3d5d8de33"}, {"new": ["4ca459ab-8e1d-49c2-a496-83b729815e8d", "a75e32bbc6175d245709082f70a0e18e977e8e409d524230bdbd820879935572"], "old": null, "kind": "append", "position": 6, "host_logical_id": "4ca459ab-8e1d-49c2-a496-83b729815e8d"}, {"new": ["addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", "275a3db894f968cea14e8ac64ffd2fc8115cb12db0ee41b99a1aecc744abaa44"], "old": null, "kind": "append", "position": 7, "host_logical_id": "addfdb4e-69d7-4c3c-93d3-f97c4853e2d6"}]', '01a170ed-2ed5-7c26-90ba-cda5a3ea172b', '2026-10-25 02:39:14.639079+00');
INSERT INTO public.worldline_append VALUES (2, '01a170ed-2e83-71c7-8117-b888a9bc5471', '[{"op": "insert", "after": ["addfdb4e-69d7-4c3c-93d3-f97c4853e2d6", "275a3db894f968cea14e8ac64ffd2fc8115cb12db0ee41b99a1aecc744abaa44"], "member": ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "09fd158139b781b06cb795e6be782627b2dc199eedd5081055096a56289d5ea7"]}, {"op": "insert", "after": ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "09fd158139b781b06cb795e6be782627b2dc199eedd5081055096a56289d5ea7"], "member": ["c9182849-3005-4b67-bf1f-cf4f222b86fb", "de76e2e451561d73ee883eb2a615992d854b94205fff045c6e1c4161a6d16e6a"]}, {"op": "insert", "after": ["c9182849-3005-4b67-bf1f-cf4f222b86fb", "de76e2e451561d73ee883eb2a615992d854b94205fff045c6e1c4161a6d16e6a"], "member": ["81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "adeacd829f7ad76966cdda19c5775e385ef089513f5fbd6cd5e6115f3b4bbfed"]}, {"op": "insert", "after": ["81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "adeacd829f7ad76966cdda19c5775e385ef089513f5fbd6cd5e6115f3b4bbfed"], "member": ["95695118-8f4a-44a8-9f70-4dd03a61a038", "25b60c016b06a8f2be0a97ef959dad10316828bc21b52ecd6aaeb3eaa7e01ad8"]}]', '[{"new": ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "09fd158139b781b06cb795e6be782627b2dc199eedd5081055096a56289d5ea7"], "old": null, "kind": "append", "position": 8, "host_logical_id": "2d22a703-4e99-478e-83e4-53f9fc05ea54"}, {"new": ["c9182849-3005-4b67-bf1f-cf4f222b86fb", "de76e2e451561d73ee883eb2a615992d854b94205fff045c6e1c4161a6d16e6a"], "old": null, "kind": "append", "position": 9, "host_logical_id": "c9182849-3005-4b67-bf1f-cf4f222b86fb"}, {"new": ["81d23b5a-e7fd-430d-9b8f-eb3ee24aa956", "adeacd829f7ad76966cdda19c5775e385ef089513f5fbd6cd5e6115f3b4bbfed"], "old": null, "kind": "append", "position": 10, "host_logical_id": "81d23b5a-e7fd-430d-9b8f-eb3ee24aa956"}, {"new": ["95695118-8f4a-44a8-9f70-4dd03a61a038", "25b60c016b06a8f2be0a97ef959dad10316828bc21b52ecd6aaeb3eaa7e01ad8"], "old": null, "kind": "append", "position": 11, "host_logical_id": "95695118-8f4a-44a8-9f70-4dd03a61a038"}]', '01a170ed-2f02-71f5-8f83-37a8e010d916', '2026-10-25 02:39:14.684408+00');
INSERT INTO public.worldline_append VALUES (3, '01a170ed-2e83-71c7-8117-b888a9bc5471', '[{"op": "insert", "after": ["95695118-8f4a-44a8-9f70-4dd03a61a038", "25b60c016b06a8f2be0a97ef959dad10316828bc21b52ecd6aaeb3eaa7e01ad8"], "member": ["25fa145b-c398-4611-b292-838ba031e1b2", "a7dfa70c82599858449423d9bcfcafdba6dffc51cf1a498922c61f8138e98ee4"]}]', '[{"new": ["25fa145b-c398-4611-b292-838ba031e1b2", "a7dfa70c82599858449423d9bcfcafdba6dffc51cf1a498922c61f8138e98ee4"], "old": null, "kind": "append", "position": 12, "host_logical_id": "25fa145b-c398-4611-b292-838ba031e1b2"}]', '01a170ed-2f2b-734b-962a-b3c197db34f8', '2026-10-25 02:39:14.724603+00');
INSERT INTO public.worldline_append VALUES (4, '01a170ed-3734-7267-9522-e800504524a2', '[{"op": "insert", "after": ["4107b879-0f06-4ee1-a727-a940117c0f98", "35694a1a6fe119d3d2161f77bc4c698c687086bc77b04df0815b8d7de0785975"], "member": ["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "1076d7f5e87c731da81ca6dbbe31cbb091402bcf7a7fec879f74be8e3a321f9f"]}]', '[{"new": ["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "1076d7f5e87c731da81ca6dbbe31cbb091402bcf7a7fec879f74be8e3a321f9f"], "old": null, "kind": "append", "position": 15, "host_logical_id": "99f4ea34-3f07-4a98-9af3-cadd5b7251de"}]', '01a170ed-3759-7695-857e-a6920405dffd', '2026-10-25 02:39:16.821806+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a170ed-2e83-71c7-8117-b888a9bc5471', 1, '01a170ed-2e74-74dc-9126-8229dbb2001f', '{}', 'import', 'f3c9079aef4f21ca4bbeb48cacc251d7348419d42a62e93d432b20112bfb4cd7', '{"ops": [{"op": "set", "members": [["f38e7339-9400-43da-b1be-c877d18f8a36", "c149bb15bba0cffb6b2130a27314912abaa49d6a76710e6df6d6dcaacb301947"], ["84071aae-41a4-47d6-924b-8c36e611a314", "462fa6f7201bf24cf59c0d09b2a17a41ecde09c8b2ee178ef919a4d17b875a5d"], ["6ac5e480-dcff-48e7-b6c0-eb651a1da3e0", "70b496b6c09431817bdbdd1e7987f510d74d3375ce3d4d6ad2876d2538cba74c"], ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "001ca8a10e37e4937ed6aef6781c62bc91ac0a4ea53e32ef7a271a8e2eb132cc"]]}], "changes": [{"new": ["f38e7339-9400-43da-b1be-c877d18f8a36", "c149bb15bba0cffb6b2130a27314912abaa49d6a76710e6df6d6dcaacb301947"], "old": null, "kind": "append", "position": 0, "host_logical_id": "f38e7339-9400-43da-b1be-c877d18f8a36"}, {"new": ["84071aae-41a4-47d6-924b-8c36e611a314", "462fa6f7201bf24cf59c0d09b2a17a41ecde09c8b2ee178ef919a4d17b875a5d"], "old": null, "kind": "append", "position": 1, "host_logical_id": "84071aae-41a4-47d6-924b-8c36e611a314"}, {"new": ["6ac5e480-dcff-48e7-b6c0-eb651a1da3e0", "70b496b6c09431817bdbdd1e7987f510d74d3375ce3d4d6ad2876d2538cba74c"], "old": null, "kind": "append", "position": 2, "host_logical_id": "6ac5e480-dcff-48e7-b6c0-eb651a1da3e0"}, {"new": ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "001ca8a10e37e4937ed6aef6781c62bc91ac0a4ea53e32ef7a271a8e2eb132cc"], "old": null, "kind": "append", "position": 3, "host_logical_id": "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f"}]}', '2026-10-25 02:39:14.555556+00', '01a170ed-2e82-7066-b5aa-8e18629b3ebd');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a170ed-3734-7267-9522-e800504524a2', 2, '01a170ed-2e74-74dc-9126-8229dbb2001f', '{01a170ed-2e83-71c7-8117-b888a9bc5471}', 'edit', '439a7af19e1827bfdfc37d67930968ca3667e64a93f0ba24de247dd02880be34', '{"ops": [{"op": "replace", "to": ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "11ade1a8ed77bd47804b1fd62a39b9dc817d960c9315a85cde1b9c2203349d8a"], "from": ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "001ca8a10e37e4937ed6aef6781c62bc91ac0a4ea53e32ef7a271a8e2eb132cc"]}, {"op": "insert", "after": ["25fa145b-c398-4611-b292-838ba031e1b2", "a7dfa70c82599858449423d9bcfcafdba6dffc51cf1a498922c61f8138e98ee4"], "member": ["c6010e47-59bb-41a7-8254-ec8a80cdbecc", "4b4503ef5b6d681aa713716e946e4b2f4940fe1cdc9dcd6d48c10b1a01de8654"]}, {"op": "insert", "after": ["c6010e47-59bb-41a7-8254-ec8a80cdbecc", "4b4503ef5b6d681aa713716e946e4b2f4940fe1cdc9dcd6d48c10b1a01de8654"], "member": ["4107b879-0f06-4ee1-a727-a940117c0f98", "35694a1a6fe119d3d2161f77bc4c698c687086bc77b04df0815b8d7de0785975"]}], "changes": [{"new": ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "11ade1a8ed77bd47804b1fd62a39b9dc817d960c9315a85cde1b9c2203349d8a"], "old": ["5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f", "001ca8a10e37e4937ed6aef6781c62bc91ac0a4ea53e32ef7a271a8e2eb132cc"], "kind": "edit", "position": 3, "host_logical_id": "5cd9e6d8-2be0-4817-8ca8-6710f7c6b40f"}, {"new": ["c6010e47-59bb-41a7-8254-ec8a80cdbecc", "4b4503ef5b6d681aa713716e946e4b2f4940fe1cdc9dcd6d48c10b1a01de8654"], "old": null, "kind": "append", "position": 13, "host_logical_id": "c6010e47-59bb-41a7-8254-ec8a80cdbecc"}, {"new": ["4107b879-0f06-4ee1-a727-a940117c0f98", "35694a1a6fe119d3d2161f77bc4c698c687086bc77b04df0815b8d7de0785975"], "old": null, "kind": "append", "position": 14, "host_logical_id": "4107b879-0f06-4ee1-a727-a940117c0f98"}]}', '2026-10-25 02:39:16.782005+00', '01a170ed-3732-7aeb-a99a-6c2b187ce68c');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a170ed-3784-7603-abc4-a6e8596671c1', 3, '01a170ed-2e74-74dc-9126-8229dbb2001f', '{01a170ed-3734-7267-9522-e800504524a2}', 'reconciliation', '05a8f9e652f3a754869cf6c19c979e08157ced056262f0e374acf3e336ab5704', '{"ops": [{"op": "replace", "to": ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "d6a49ec5425b7451cdb2f93d116e425c03a02596e17b6d5025fa5afac734e00b"], "from": ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "09fd158139b781b06cb795e6be782627b2dc199eedd5081055096a56289d5ea7"]}, {"op": "replace", "to": ["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "59bdd67f83572f3f4c8f8b1c12f5dbc11922eacb652efe1f8b87beccaa86d0a9"], "from": ["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "1076d7f5e87c731da81ca6dbbe31cbb091402bcf7a7fec879f74be8e3a321f9f"]}, {"op": "insert", "after": ["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "59bdd67f83572f3f4c8f8b1c12f5dbc11922eacb652efe1f8b87beccaa86d0a9"], "member": ["660db083-0a7d-42e2-8c16-1b38b97dd42c", "70447579b380527c7ade70e138891e563c53791694db84d622144c44e3c76d28"]}], "changes": [{"new": ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "d6a49ec5425b7451cdb2f93d116e425c03a02596e17b6d5025fa5afac734e00b"], "old": ["2d22a703-4e99-478e-83e4-53f9fc05ea54", "09fd158139b781b06cb795e6be782627b2dc199eedd5081055096a56289d5ea7"], "kind": "disable", "position": 8, "host_logical_id": "2d22a703-4e99-478e-83e4-53f9fc05ea54"}, {"new": ["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "59bdd67f83572f3f4c8f8b1c12f5dbc11922eacb652efe1f8b87beccaa86d0a9"], "old": ["99f4ea34-3f07-4a98-9af3-cadd5b7251de", "1076d7f5e87c731da81ca6dbbe31cbb091402bcf7a7fec879f74be8e3a321f9f"], "kind": "swipe", "position": 15, "host_logical_id": "99f4ea34-3f07-4a98-9af3-cadd5b7251de"}, {"new": ["660db083-0a7d-42e2-8c16-1b38b97dd42c", "70447579b380527c7ade70e138891e563c53791694db84d622144c44e3c76d28"], "old": null, "kind": "append", "position": 16, "host_logical_id": "660db083-0a7d-42e2-8c16-1b38b97dd42c"}]}', '2026-10-25 02:39:16.859822+00', '01a170ed-3783-7653-94e3-bcba09825888');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a170ed-3ba4-74d6-89cd-993e44ecc303', 4, '01a170ed-3b8d-736e-b523-180f1b7f68c2', '{}', 'branch', '69ae882774cd7c1484c95e72180bbd5534bd49a92e876958f76f2863483f7bb3', '{"ops": [{"op": "set", "members": [["ab88c7bf-c374-4e9e-ac1c-529198853f89", "44ebaa29747098dd45c4587bd3430f7450d39dae1a211a46437f071dc13017da"], ["4e9eb8d8-8459-4732-a101-8306ef331a9e", "decc1b0b3e8b7870b0bd44031fe0d00a24233b773a0554d567874f8f6a589567"], ["e1a2ea0a-42a1-41ed-8878-4e01a74c31b6", "e15640d28134ad3c7598486233d76f94675989754ee0ef99c167af3bed740077"], ["5d2c20ef-d024-474b-b24f-303940a9d3b8", "95f2ea83d2bc8362b945ddd98c5b4070f5a9f52ee78428295c1a5175492cb9bd"], ["8bdc0b17-5006-4c36-90d2-5a866ce6664a", "3e061f9d2a8d128d8b69d9fd91ec82e234955a20183b1ce1e29e972b01222452"], ["105e2ec3-55e4-4535-9e83-d3ce9e6a841a", "eaa8ab3cd206a514aa62cc8d5339aee0dc2402d3d0f8ac23794dd492483270db"], ["672fdb7d-c251-45b0-abae-a3837362a28b", "9fb795bd4e419bd4352803e57d512517c2435375c9863b1209596ff4ca7c2426"], ["fb3b6a7d-daba-4fbf-90d2-26dce4c7090e", "bd736791e96c5985a50e245c1de13c5e42b08de6152d545d9cac146d5b368eb3"]]}], "changes": [{"new": ["ab88c7bf-c374-4e9e-ac1c-529198853f89", "44ebaa29747098dd45c4587bd3430f7450d39dae1a211a46437f071dc13017da"], "old": null, "kind": "append", "position": 0, "host_logical_id": "ab88c7bf-c374-4e9e-ac1c-529198853f89"}, {"new": ["4e9eb8d8-8459-4732-a101-8306ef331a9e", "decc1b0b3e8b7870b0bd44031fe0d00a24233b773a0554d567874f8f6a589567"], "old": null, "kind": "append", "position": 1, "host_logical_id": "4e9eb8d8-8459-4732-a101-8306ef331a9e"}, {"new": ["e1a2ea0a-42a1-41ed-8878-4e01a74c31b6", "e15640d28134ad3c7598486233d76f94675989754ee0ef99c167af3bed740077"], "old": null, "kind": "append", "position": 2, "host_logical_id": "e1a2ea0a-42a1-41ed-8878-4e01a74c31b6"}, {"new": ["5d2c20ef-d024-474b-b24f-303940a9d3b8", "95f2ea83d2bc8362b945ddd98c5b4070f5a9f52ee78428295c1a5175492cb9bd"], "old": null, "kind": "append", "position": 3, "host_logical_id": "5d2c20ef-d024-474b-b24f-303940a9d3b8"}, {"new": ["8bdc0b17-5006-4c36-90d2-5a866ce6664a", "3e061f9d2a8d128d8b69d9fd91ec82e234955a20183b1ce1e29e972b01222452"], "old": null, "kind": "append", "position": 4, "host_logical_id": "8bdc0b17-5006-4c36-90d2-5a866ce6664a"}, {"new": ["105e2ec3-55e4-4535-9e83-d3ce9e6a841a", "eaa8ab3cd206a514aa62cc8d5339aee0dc2402d3d0f8ac23794dd492483270db"], "old": null, "kind": "append", "position": 5, "host_logical_id": "105e2ec3-55e4-4535-9e83-d3ce9e6a841a"}, {"new": ["672fdb7d-c251-45b0-abae-a3837362a28b", "9fb795bd4e419bd4352803e57d512517c2435375c9863b1209596ff4ca7c2426"], "old": null, "kind": "append", "position": 6, "host_logical_id": "672fdb7d-c251-45b0-abae-a3837362a28b"}, {"new": ["fb3b6a7d-daba-4fbf-90d2-26dce4c7090e", "bd736791e96c5985a50e245c1de13c5e42b08de6152d545d9cac146d5b368eb3"], "old": null, "kind": "append", "position": 7, "host_logical_id": "fb3b6a7d-daba-4fbf-90d2-26dce4c7090e"}]}', '2026-10-25 02:39:17.914144+00', '01a170ed-3ba3-721d-ab82-e4ad5f285973');


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
-- Name: extraction_speakers_members; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX extraction_speakers_members ON public.extraction USING gin (members) WHERE (speakers IS NOT NULL);


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


