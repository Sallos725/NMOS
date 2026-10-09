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
    CONSTRAINT owner_repair_kind_check CHECK ((kind = ANY (ARRAY['thread_close'::text, 'thread_reopen'::text, 'secret_found_out'::text, 'secret_keep'::text, 'fact_retract'::text, 'fact_correct'::text, 'name_split'::text, 'fact_lock'::text, 'fact_restore'::text])))
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

INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 0, '01a11a37-b378-7bb1-bced-cfc4cef0a79f', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 1, '01a11a37-b37a-7a1b-b153-0d3fe00800fe', NULL, 0, 'cd45a20922ff7f4c19cb27dc4318a958');
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 2, '01a11a37-b37b-777a-b279-1d3eeddbeb64', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 3, '01a11a37-bbfb-708a-a24a-77cdd41aad8c', NULL, 1, '8dbfb63ad19ef0985ce675545a934fa3');
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 4, '01a11a37-b3af-79ea-a3ed-9b02bab293e9', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 5, '01a11a37-b3b0-724a-b495-ebdbbcafa865', NULL, 2, '2763730b0d453df95f598afd8083f315');
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 6, '01a11a37-b3b1-7d4e-ad41-e8e5c0badac8', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 7, '01a11a37-b3b2-72e7-bffa-db58a50031c6', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 8, '01a11a37-bc42-7e22-ac40-318161f2ed68', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 9, '01a11a37-b3d5-794c-b791-1ad15f06d957', NULL, 3, '38c9f450b52693cc611d9215810703ec');
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 10, '01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 11, '01a11a37-b3d6-7054-9c69-90be952d721c', NULL, 4, 'ca04d61b35e988c8c0ddf5890e2ec6ac');
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 12, '01a11a37-b3f9-734e-936a-c7abca08ed81', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 13, '01a11a37-bbfc-733d-aa09-fcebebde0fc4', NULL, 5, 'b9cb6463d29f5732d74415bda37d3540');
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 14, '01a11a37-bbfd-7449-8941-00f4ecde22df', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 15, '01a11a37-bc43-737d-a74e-b2becf57c606', NULL, 6, '1aabcfd3827f269f6d9275dd33706838');
INSERT INTO public.active_membership VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 16, '01a11a37-bc44-76f6-a5cc-7fe408a53a02', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 0, '01a11a37-c059-7470-926c-e3ed7b746136', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 1, '01a11a37-c059-73cc-8bec-28e751dcaba7', NULL, 0, '035073ef313dbdd6274fe4df4165eedc');
INSERT INTO public.active_membership VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 2, '01a11a37-c05a-7d8b-aa4b-4e3ad90e0386', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 3, '01a11a37-c05b-73be-bb0d-034a4c9dc3ae', NULL, 1, '8a0aa4fd532fd0be8e518d95efd2f135');
INSERT INTO public.active_membership VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 4, '01a11a37-c05b-7c59-9763-75bb9c83b91d', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 5, '01a11a37-c05c-79b4-884f-fd200ba0de29', NULL, 2, 'd065e1dd8f0b93243ccfd76951eda9ed');
INSERT INTO public.active_membership VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 6, '01a11a37-c05c-7822-b26d-51036175b04b', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 7, '01a11a37-c05d-7b54-b4c8-bd94906e3b4c', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a11a37-b97d-71a1-b4f0-2f897224e189', '01a11a37-b37a-7a1b-b153-0d3fe00800fe', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a11a37-b97d-71a1-b4f0-2f897224e189', '01a11a37-b37a-7a1b-b153-0d3fe00800fe', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a11a37-b99a-7b3f-894c-96ae9a3d1984', '01a11a37-b37c-7434-85b8-adc2891e44f1', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a11a37-b99a-7b3f-894c-96ae9a3d1984', '01a11a37-b37c-7434-85b8-adc2891e44f1', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a11a37-b9b3-72c1-ae54-6113be22fa73', '01a11a37-b3b0-724a-b495-ebdbbcafa865', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a11a37-b9e7-7c0d-b5d3-5e6929b0fb88', '01a11a37-b3d5-794c-b791-1ad15f06d957', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a11a37-ba01-769c-bf9c-3e466ed3fc41', '01a11a37-b3d6-7054-9c69-90be952d721c', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a11a37-be60-7697-9ba1-abbb508abeee', '01a11a37-bc43-737d-a74e-b2becf57c606', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a11a37-be91-7324-ae68-836f0530e812', '01a11a37-b3d6-7054-9c69-90be952d721c', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a11a37-bea8-7b31-a2d3-df31f559bf04', '01a11a37-b3d5-794c-b791-1ad15f06d957', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a11a37-becb-739b-afd3-4812d3590328', '01a11a37-b3b0-724a-b495-ebdbbcafa865', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a11a37-bee3-720e-be56-bb8501e7ecd5', '01a11a37-bbfb-708a-a24a-77cdd41aad8c', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a11a37-bee3-720e-be56-bb8501e7ecd5', '01a11a37-bbfb-708a-a24a-77cdd41aad8c', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a11a37-c36b-70ed-b1ce-e107cff73c61', '01a11a37-c059-73cc-8bec-28e751dcaba7', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a11a37-c36b-70ed-b1ce-e107cff73c61', '01a11a37-c059-73cc-8bec-28e751dcaba7', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a11a37-c383-7a7a-af79-0ba35bc68837', '01a11a37-c05b-73be-bb0d-034a4c9dc3ae', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a11a37-c383-7a7a-af79-0ba35bc68837', '01a11a37-c05b-73be-bb0d-034a4c9dc3ae', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a11a37-c399-7cbe-a320-60a0989e2a18', '01a11a37-c05c-79b4-884f-fd200ba0de29', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: canon_applied; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: canon_manifest; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a11a37-b369-7efd-bdb2-869680e8a3a0', 'pocketrisu', NULL, '125f228f-e94b-461c-b4bc-8afbf99a362d', '2026-10-08 06:33:40.458033+00', NULL, NULL, NULL, '01a11a37-bc47-7e9a-88f2-df2aad69d69d', 'df7c77451a32d1eb71fdd994e78323d1e029c4013736f85071b62cf5b5282c39', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL);
INSERT INTO public.conversation VALUES ('01a11a37-c04b-7aa7-9b86-637259a6907a', 'pocketrisu', NULL, 'c1288de9-6011-468c-9454-02bc69e00ee5', '2026-10-08 06:33:43.755542+00', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '125f228f-e94b-461c-b4bc-8afbf99a362d', 'db5334ea-f745-46c3-9318-267d04f87922', '01a11a37-c05f-71d5-8501-baeab8feb19c', '875611173088fc81683291e7e9b35077ea922279f156267484011a26e4c8d921', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a11a37-b97d-71a1-b4f0-2f897224e189', '01a11a37-b37a-7a1b-b153-0d3fe00800fe', 'cd45a20922ff7f4c19cb27dc4318a958', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:42.012756+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a11a37-b378-7bb1-bced-cfc4cef0a79f,01a11a37-b37a-7a1b-b153-0d3fe00800fe}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}', '{"ms": 14, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-b99a-7b3f-894c-96ae9a3d1984', '01a11a37-b37c-7434-85b8-adc2891e44f1', 'f966fa0fa9c7a3a7adacdea1ce8b66f3', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:42.041874+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a11a37-b37b-777a-b279-1d3eeddbeb64,01a11a37-b37c-7434-85b8-adc2891e44f1}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-b9b3-72c1-ae54-6113be22fa73', '01a11a37-b3b0-724a-b495-ebdbbcafa865', '04a0a4b99308087e60f69cb464e4be9d', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:42.066812+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a11a37-b3af-79ea-a3ed-9b02bab293e9,01a11a37-b3b0-724a-b495-ebdbbcafa865}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-b9cd-78ff-8e67-f1d921ebe7e5', '01a11a37-b3b2-72e7-bffa-db58a50031c6', '7754d2fce2f6063baac0947660ff8d62', 'extract-v16', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-10-08 06:33:42.093423+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a11a37-b3b1-7d4e-ad41-e8e5c0badac8,01a11a37-b3b2-72e7-bffa-db58a50031c6}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 15, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-b9e7-7c0d-b5d3-5e6929b0fb88', '01a11a37-b3d5-794c-b791-1ad15f06d957', 'b4d8f0307c41ef56b270eac87d78ba37', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:42.119682+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a11a37-b3d4-7314-b72d-941ac7d54bd8,01a11a37-b3d5-794c-b791-1ad15f06d957}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 14, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-ba01-769c-bf9c-3e466ed3fc41', '01a11a37-b3d6-7054-9c69-90be952d721c', '68e52fc43e42359d5d1f27376d68845c', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:42.145566+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0,01a11a37-b3d6-7054-9c69-90be952d721c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "silver compass", "type": "item"}, {"name": "Rin", "type": "character"}, {"name": "Mina", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-be60-7697-9ba1-abbb508abeee', '01a11a37-bc43-737d-a74e-b2becf57c606', '1aabcfd3827f269f6d9275dd33706838', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:43.263817+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a11a37-bbfd-7449-8941-00f4ecde22df,01a11a37-bc43-737d-a74e-b2becf57c606}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-be7a-73b4-adc4-b3d502597019', '01a11a37-bbfc-733d-aa09-fcebebde0fc4', 'b9cb6463d29f5732d74415bda37d3540', 'extract-v16', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-10-08 06:33:43.290327+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a11a37-b3f9-734e-936a-c7abca08ed81,01a11a37-bbfc-733d-aa09-fcebebde0fc4}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-be91-7324-ae68-836f0530e812', '01a11a37-b3d6-7054-9c69-90be952d721c', 'ca04d61b35e988c8c0ddf5890e2ec6ac', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:43.312954+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0,01a11a37-b3d6-7054-9c69-90be952d721c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-bea8-7b31-a2d3-df31f559bf04', '01a11a37-b3d5-794c-b791-1ad15f06d957', '38c9f450b52693cc611d9215810703ec', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:43.336097+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a11a37-b3b1-7d4e-ad41-e8e5c0badac8,01a11a37-b3b2-72e7-bffa-db58a50031c6,01a11a37-b3d5-794c-b791-1ad15f06d957}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-becb-739b-afd3-4812d3590328', '01a11a37-b3b0-724a-b495-ebdbbcafa865', '2763730b0d453df95f598afd8083f315', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:43.371711+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a11a37-b3af-79ea-a3ed-9b02bab293e9,01a11a37-b3b0-724a-b495-ebdbbcafa865}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-bee3-720e-be56-bb8501e7ecd5', '01a11a37-bbfb-708a-a24a-77cdd41aad8c', '8dbfb63ad19ef0985ce675545a934fa3', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:43.394889+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a11a37-b37b-777a-b279-1d3eeddbeb64,01a11a37-bbfb-708a-a24a-77cdd41aad8c}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 14, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-c36b-70ed-b1ce-e107cff73c61', '01a11a37-c059-73cc-8bec-28e751dcaba7', '035073ef313dbdd6274fe4df4165eedc', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:44.555584+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a11a37-c059-7470-926c-e3ed7b746136,01a11a37-c059-73cc-8bec-28e751dcaba7}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}', '{"ms": 17, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-c383-7a7a-af79-0ba35bc68837', '01a11a37-c05b-73be-bb0d-034a4c9dc3ae', '8a0aa4fd532fd0be8e518d95efd2f135', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:44.579069+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a11a37-c05a-7d8b-aa4b-4e3ad90e0386,01a11a37-c05b-73be-bb0d-034a4c9dc3ae}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 14, "calls": 1}');
INSERT INTO public.extraction VALUES ('01a11a37-c399-7cbe-a320-60a0989e2a18', '01a11a37-c05c-79b4-884f-fd200ba0de29', 'd065e1dd8f0b93243ccfd76951eda9ed', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-08 06:33:44.600918+00', 'extract-77dd347ed8019168e6d3b827877cad4a', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a11a37-c05b-7c59-9763-75bb9c83b91d,01a11a37-c05c-79b4-884f-fd200ba0de29}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "lighthouse", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 13, "calls": 1}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a11a37-b37d-788b-b326-cef914cc126f', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'manifest', '50ed30cae3d7585b207d9f3ace469667dad795b158164ca9ed3ce520a62f1d40', '01a11a37-b369-7efd-bdb2-869680e8a3a0:50ed30cae3d7585b207d9f3ace469667dad795b158164ca9ed3ce520a62f1d40:manifest', '2026-10-08 06:33:40.471501+00', '{"chat_id": "125f228f-e94b-461c-b4bc-8afbf99a362d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["9adf2606-d06d-48c0-8ab2-b41f320f0909", "e36f9551c56076721f946cd2535335975c4f9830473665373689cb0e45834da1", "user", null, null, null, 0, null, null], ["b9a40939-eb41-4218-9960-92453a451c7d", "ff551dffe0c80900759b58c1106a2181c91f0cf63d3d95a85617643c02b2466b", "char", null, null, null, 0, "b9a40939-eb41-4218-9960-92453a451c7d", null], ["8ed2da0c-b165-42bd-8a83-094fda9b646c", "a8499762ff56b19c333ee7e65a45bf1874145c77564cdb5ed035d5cf3f97c4da", "user", null, null, null, 0, null, null], ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "60b03a98c3edc8e1e7386837ba18af0e442eb24baf5e64d23ddbdd1077e6b63b", "char", null, null, null, 0, "e2024e47-1167-466c-90a1-04cefd4f5e9b", null]]}');
INSERT INTO public.host_observation VALUES ('01a11a37-b3b4-736b-902b-c94e6605e653', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'manifest', 'fa95ded8dd3cc4e0b97026b31abc73bbe0aa55498188deab9b8764f7c49648a1', '01a11a37-b369-7efd-bdb2-869680e8a3a0:fa95ded8dd3cc4e0b97026b31abc73bbe0aa55498188deab9b8764f7c49648a1:manifest', '2026-10-08 06:33:40.526552+00', '{"chat_id": "125f228f-e94b-461c-b4bc-8afbf99a362d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["4a23ebc8-b225-4788-9d4b-d5b68e73cc7f", "48bf4f0ad182ba0ee0e6c42f2783ac65f86760fc5ba42488192417ecc3458d34", "user", null, null, null, 0, null, null], ["db5334ea-f745-46c3-9318-267d04f87922", "1e702ba51bab01f6444cb540c7f0eafe833f93eb5468e5ca5c271ec89a6dcfdb", "char", null, null, null, 0, "db5334ea-f745-46c3-9318-267d04f87922", null], ["bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd", "d2d64ec42ab33b6ccac3c3f512a2565c50a57838652e990cc7db7fa42039f496", "user", null, null, null, 0, null, null], ["b97ad3bc-1991-4454-8a4b-684283f3b175", "feda22a6c319f6b58e812ab98da107b7db7d0028e8390f527af4792431281273", "char", null, null, null, 0, "b97ad3bc-1991-4454-8a4b-684283f3b175", null]], "base_manifest_hash": "50ed30cae3d7585b207d9f3ace469667dad795b158164ca9ed3ce520a62f1d40"}');
INSERT INTO public.host_observation VALUES ('01a11a37-b3d9-7664-833e-8659f3ca49b0', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'manifest', 'b53b168a9cff251051559b2fa9f78c8f76bc03368b509bd117772316b1f71920', '01a11a37-b369-7efd-bdb2-869680e8a3a0:b53b168a9cff251051559b2fa9f78c8f76bc03368b509bd117772316b1f71920:manifest', '2026-10-08 06:33:40.563543+00', '{"chat_id": "125f228f-e94b-461c-b4bc-8afbf99a362d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "ba75a43ad8cbe74ec036f3d9f3a5bc0da9c7f4a69b33f3aaaa4c89fb4d483cdf", "user", null, null, null, 0, null, null], ["a637975f-a844-46fb-a307-d7ae7d97a3fc", "78b2fc98e215b9b974efd92216b75fedf5f6b6d97b51334c2afdc8d95ebdf76b", "char", null, null, null, 0, "a637975f-a844-46fb-a307-d7ae7d97a3fc", null], ["374ed69f-3a2f-44f7-8b24-267ac414e034", "c94f9e78203ef15530f7789d9cf689381d57dbe48a53bc443bbf0b06116fd281", "user", null, null, null, 0, null, null], ["d492edfa-fc9e-468f-af9e-63863efeff58", "1e66df23f6901e4ed8f20751fcd06513447483ecf34039422cb1458d1c1c5d5b", "char", null, null, null, 0, "d492edfa-fc9e-468f-af9e-63863efeff58", null]], "base_manifest_hash": "fa95ded8dd3cc4e0b97026b31abc73bbe0aa55498188deab9b8764f7c49648a1"}');
INSERT INTO public.host_observation VALUES ('01a11a37-b3fb-7c73-982b-c8b85dc15cec', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'manifest', 'a772fd0ab1e1dab583fa603bd98e5b3e678f31eca74cb8dea7acbe7d99c9c8f6', '01a11a37-b369-7efd-bdb2-869680e8a3a0:a772fd0ab1e1dab583fa603bd98e5b3e678f31eca74cb8dea7acbe7d99c9c8f6:manifest', '2026-10-08 06:33:40.600257+00', '{"chat_id": "125f228f-e94b-461c-b4bc-8afbf99a362d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["a8d6d019-be96-4451-a351-1eeb2360bb49", "e412b6862d7365a6813f3f071c9a69f6fc6aef2daf7b0817889213e0640e8ebe", "user", null, null, null, 0, null, null]], "base_manifest_hash": "b53b168a9cff251051559b2fa9f78c8f76bc03368b509bd117772316b1f71920"}');
INSERT INTO public.host_observation VALUES ('01a11a37-bbff-7cf8-ad81-e767313dec51', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'manifest', '44b99609497fa1f1cd7257d068b7f7516bd92fce1a97b8238c8f515a9834826c', '01a11a37-b369-7efd-bdb2-869680e8a3a0:44b99609497fa1f1cd7257d068b7f7516bd92fce1a97b8238c8f515a9834826c:manifest', '2026-10-08 06:33:42.651098+00', '{"chat_id": "125f228f-e94b-461c-b4bc-8afbf99a362d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["9adf2606-d06d-48c0-8ab2-b41f320f0909", "e36f9551c56076721f946cd2535335975c4f9830473665373689cb0e45834da1", "user", null, null, null, 0, null, null], ["b9a40939-eb41-4218-9960-92453a451c7d", "ff551dffe0c80900759b58c1106a2181c91f0cf63d3d95a85617643c02b2466b", "char", null, null, null, 0, "b9a40939-eb41-4218-9960-92453a451c7d", null], ["8ed2da0c-b165-42bd-8a83-094fda9b646c", "a8499762ff56b19c333ee7e65a45bf1874145c77564cdb5ed035d5cf3f97c4da", "user", null, null, null, 0, null, null], ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "08716415adb3830ecaf492ef87a071ffb0f02e9f309bb6a51a88938352ddd793", "char", null, null, null, 0, "e2024e47-1167-466c-90a1-04cefd4f5e9b", null], ["4a23ebc8-b225-4788-9d4b-d5b68e73cc7f", "48bf4f0ad182ba0ee0e6c42f2783ac65f86760fc5ba42488192417ecc3458d34", "user", null, null, null, 0, null, null], ["db5334ea-f745-46c3-9318-267d04f87922", "1e702ba51bab01f6444cb540c7f0eafe833f93eb5468e5ca5c271ec89a6dcfdb", "char", null, null, null, 0, "db5334ea-f745-46c3-9318-267d04f87922", null], ["bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd", "d2d64ec42ab33b6ccac3c3f512a2565c50a57838652e990cc7db7fa42039f496", "user", null, null, null, 0, null, null], ["b97ad3bc-1991-4454-8a4b-684283f3b175", "feda22a6c319f6b58e812ab98da107b7db7d0028e8390f527af4792431281273", "char", null, null, null, 0, "b97ad3bc-1991-4454-8a4b-684283f3b175", null], ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "ba75a43ad8cbe74ec036f3d9f3a5bc0da9c7f4a69b33f3aaaa4c89fb4d483cdf", "user", null, null, null, 0, null, null], ["a637975f-a844-46fb-a307-d7ae7d97a3fc", "78b2fc98e215b9b974efd92216b75fedf5f6b6d97b51334c2afdc8d95ebdf76b", "char", null, null, null, 0, "a637975f-a844-46fb-a307-d7ae7d97a3fc", null], ["374ed69f-3a2f-44f7-8b24-267ac414e034", "c94f9e78203ef15530f7789d9cf689381d57dbe48a53bc443bbf0b06116fd281", "user", null, null, null, 0, null, null], ["d492edfa-fc9e-468f-af9e-63863efeff58", "1e66df23f6901e4ed8f20751fcd06513447483ecf34039422cb1458d1c1c5d5b", "char", null, null, null, 0, "d492edfa-fc9e-468f-af9e-63863efeff58", null], ["a8d6d019-be96-4451-a351-1eeb2360bb49", "e412b6862d7365a6813f3f071c9a69f6fc6aef2daf7b0817889213e0640e8ebe", "user", null, null, null, 0, null, null], ["3c3589eb-1c39-4d77-9d28-d00f1b12c425", "eaa872774c53ef8a46941527086963b8f6c49069c3e0f677413a5cbda71e762d", "char", null, null, null, 0, "3c3589eb-1c39-4d77-9d28-d00f1b12c425", null], ["e361c9c3-248e-432f-8302-4c8a95b2395e", "921ba606eb33407c887973aeb76507c47768ee1102ee5193163daec1032e7da8", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a11a37-bc1e-7d56-8269-3bcaddd7322b', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'manifest', 'cf076dbbbb8f5ca2e0a7385348dff86149314b20cd3bad0531d0482c1a43374f', '01a11a37-b369-7efd-bdb2-869680e8a3a0:cf076dbbbb8f5ca2e0a7385348dff86149314b20cd3bad0531d0482c1a43374f:manifest', '2026-10-08 06:33:42.682781+00', '{"chat_id": "125f228f-e94b-461c-b4bc-8afbf99a362d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "54849297958b13ce509684f084d573f434a122f68f338cd93de2d08f5e1c2309", "char", null, null, 1, 2, "ac0a057c-74b6-43ed-8fb8-afa805fa027f", null]], "base_manifest_hash": "44b99609497fa1f1cd7257d068b7f7516bd92fce1a97b8238c8f515a9834826c"}');
INSERT INTO public.host_observation VALUES ('01a11a37-bc46-721f-b5b7-3dba9c81dee8', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'manifest', 'df7c77451a32d1eb71fdd994e78323d1e029c4013736f85071b62cf5b5282c39', '01a11a37-b369-7efd-bdb2-869680e8a3a0:df7c77451a32d1eb71fdd994e78323d1e029c4013736f85071b62cf5b5282c39:manifest', '2026-10-08 06:33:42.721919+00', '{"chat_id": "125f228f-e94b-461c-b4bc-8afbf99a362d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["9adf2606-d06d-48c0-8ab2-b41f320f0909", "e36f9551c56076721f946cd2535335975c4f9830473665373689cb0e45834da1", "user", null, null, null, 0, null, null], ["b9a40939-eb41-4218-9960-92453a451c7d", "ff551dffe0c80900759b58c1106a2181c91f0cf63d3d95a85617643c02b2466b", "char", null, null, null, 0, "b9a40939-eb41-4218-9960-92453a451c7d", null], ["8ed2da0c-b165-42bd-8a83-094fda9b646c", "a8499762ff56b19c333ee7e65a45bf1874145c77564cdb5ed035d5cf3f97c4da", "user", null, null, null, 0, null, null], ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "08716415adb3830ecaf492ef87a071ffb0f02e9f309bb6a51a88938352ddd793", "char", null, null, null, 0, "e2024e47-1167-466c-90a1-04cefd4f5e9b", null], ["4a23ebc8-b225-4788-9d4b-d5b68e73cc7f", "48bf4f0ad182ba0ee0e6c42f2783ac65f86760fc5ba42488192417ecc3458d34", "user", null, null, null, 0, null, null], ["db5334ea-f745-46c3-9318-267d04f87922", "1e702ba51bab01f6444cb540c7f0eafe833f93eb5468e5ca5c271ec89a6dcfdb", "char", null, null, null, 0, "db5334ea-f745-46c3-9318-267d04f87922", null], ["bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd", "d2d64ec42ab33b6ccac3c3f512a2565c50a57838652e990cc7db7fa42039f496", "user", null, null, null, 0, null, null], ["b97ad3bc-1991-4454-8a4b-684283f3b175", "feda22a6c319f6b58e812ab98da107b7db7d0028e8390f527af4792431281273", "char", null, null, null, 0, "b97ad3bc-1991-4454-8a4b-684283f3b175", null], ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "b8469f3076dbca036a833ce64c7a309f38ba7760a370583c5ae1b690d140cab4", "user", true, null, null, 0, null, null], ["a637975f-a844-46fb-a307-d7ae7d97a3fc", "78b2fc98e215b9b974efd92216b75fedf5f6b6d97b51334c2afdc8d95ebdf76b", "char", null, null, null, 0, "a637975f-a844-46fb-a307-d7ae7d97a3fc", null], ["374ed69f-3a2f-44f7-8b24-267ac414e034", "c94f9e78203ef15530f7789d9cf689381d57dbe48a53bc443bbf0b06116fd281", "user", null, null, null, 0, null, null], ["d492edfa-fc9e-468f-af9e-63863efeff58", "1e66df23f6901e4ed8f20751fcd06513447483ecf34039422cb1458d1c1c5d5b", "char", null, null, null, 0, "d492edfa-fc9e-468f-af9e-63863efeff58", null], ["a8d6d019-be96-4451-a351-1eeb2360bb49", "e412b6862d7365a6813f3f071c9a69f6fc6aef2daf7b0817889213e0640e8ebe", "user", null, null, null, 0, null, null], ["3c3589eb-1c39-4d77-9d28-d00f1b12c425", "eaa872774c53ef8a46941527086963b8f6c49069c3e0f677413a5cbda71e762d", "char", null, null, null, 0, "3c3589eb-1c39-4d77-9d28-d00f1b12c425", null], ["e361c9c3-248e-432f-8302-4c8a95b2395e", "921ba606eb33407c887973aeb76507c47768ee1102ee5193163daec1032e7da8", "user", null, null, null, 0, null, null], ["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "fe6f019185169b470073eddfca146beb5b2512ac5b9a80ba225c70c2c06a0f13", "char", null, null, 0, 2, "ac0a057c-74b6-43ed-8fb8-afa805fa027f", null], ["5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e", "ede9033ffa403b50d19b9320cd94563e10670d4717b05385138a1b728b7b9035", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a11a37-c05e-7747-8b42-2cd2bb037e2d', '01a11a37-c04b-7aa7-9b86-637259a6907a', 'manifest', '875611173088fc81683291e7e9b35077ea922279f156267484011a26e4c8d921', '01a11a37-c04b-7aa7-9b86-637259a6907a:875611173088fc81683291e7e9b35077ea922279f156267484011a26e4c8d921:manifest', '2026-10-08 06:33:43.768368+00', '{"chat_id": "c1288de9-6011-468c-9454-02bc69e00ee5", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["c776a045-da0c-4eea-b8ea-8cde9e513eb8", "594aba0ea21c7a75357587423d4b6581d8768e5eeb956dfc4b355f51b26af7fb", "user", null, null, null, 0, null, null], ["83ae9fdf-749c-45a9-a92a-66f672eccd1e", "84ddc403e957de7bd514c4e8af44e332b605a474ec2f47bd70127c95260d81c3", "char", null, null, null, 0, "b9a40939-eb41-4218-9960-92453a451c7d", null], ["8025b532-342f-4336-994b-6943f1b4aeab", "37cbb59a5a9eb96360693f29d4637857c012db6fe171cedc98b574c9878f7326", "user", null, null, null, 0, null, null], ["0137f8df-0fb6-4424-829e-d09188013daa", "899323210bf98a82a43ab61dc00745687dcd97aa524be1809e1def01b2b14953", "char", null, null, null, 0, "e2024e47-1167-466c-90a1-04cefd4f5e9b", null], ["61e32194-8120-4db7-af10-e320c6bbb844", "99dbd67897062fac92e339128210a0bffff6d548a0bd40efc439a18b62668e9c", "user", null, null, null, 0, null, null], ["0745cc01-46ab-4db0-b7fc-59e76470f2f2", "e0993d8dfeb3a334a82fdbcb8e92ca605269d5a2993c8d91212e36ba0f29643c", "char", null, null, null, 0, "db5334ea-f745-46c3-9318-267d04f87922", null], ["67893689-6eac-48f2-a7cd-f2920092d287", "56e757f3371818ec7b95a7cbe2f312935eabbbe715f9e9100a58c5451cdfea5f", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::125f228f-e94b-461c-b4bc-8afbf99a362d::Harbor route::db5334ea-f745-46c3-9318-267d04f87922::}}"]], ["5faae7a5-e3fa-44c7-9430-972837c5c973", "c187d58dd21ea841fd54afce502d454de82bf81413491e8387beea658305692d", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a11a37-b3f9-734e-936a-c7abca08ed81:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3f9-734e-936a-c7abca08ed81"}', 50, 'done', 1, '2026-10-08 06:33:40.600257+00', NULL, NULL, '2026-10-08 06:33:40.600257+00', '2026-10-08 06:33:41.745283+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a11a37-b3d6-7054-9c69-90be952d721c:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3d6-7054-9c69-90be952d721c"}', 50, 'done', 1, '2026-10-08 06:33:40.600257+00', NULL, NULL, '2026-10-08 06:33:40.600257+00', '2026-10-08 06:33:41.766101+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0"}', 50, 'done', 1, '2026-10-08 06:33:40.563543+00', NULL, NULL, '2026-10-08 06:33:40.563543+00', '2026-10-08 06:33:41.786096+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a11a37-b3d5-794c-b791-1ad15f06d957:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3d5-794c-b791-1ad15f06d957"}', 50, 'done', 1, '2026-10-08 06:33:40.563543+00', NULL, NULL, '2026-10-08 06:33:40.563543+00', '2026-10-08 06:33:41.805609+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a11a37-b3d4-7314-b72d-941ac7d54bd8:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3d4-7314-b72d-941ac7d54bd8"}', 50, 'done', 1, '2026-10-08 06:33:40.563543+00', NULL, NULL, '2026-10-08 06:33:40.563543+00', '2026-10-08 06:33:41.828265+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a11a37-b3b2-72e7-bffa-db58a50031c6:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3b2-72e7-bffa-db58a50031c6"}', 50, 'done', 1, '2026-10-08 06:33:40.563543+00', NULL, NULL, '2026-10-08 06:33:40.563543+00', '2026-10-08 06:33:41.847524+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a11a37-b3b1-7d4e-ad41-e8e5c0badac8:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3b1-7d4e-ad41-e8e5c0badac8"}', 50, 'done', 1, '2026-10-08 06:33:40.526552+00', NULL, NULL, '2026-10-08 06:33:40.526552+00', '2026-10-08 06:33:41.867543+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a11a37-b3b0-724a-b495-ebdbbcafa865:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3b0-724a-b495-ebdbbcafa865"}', 50, 'done', 1, '2026-10-08 06:33:40.526552+00', NULL, NULL, '2026-10-08 06:33:40.526552+00', '2026-10-08 06:33:41.888912+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a11a37-b3af-79ea-a3ed-9b02bab293e9:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b3af-79ea-a3ed-9b02bab293e9"}', 50, 'done', 1, '2026-10-08 06:33:40.526552+00', NULL, NULL, '2026-10-08 06:33:40.526552+00', '2026-10-08 06:33:41.912853+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a11a37-b37c-7434-85b8-adc2891e44f1:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b37c-7434-85b8-adc2891e44f1"}', 50, 'done', 1, '2026-10-08 06:33:40.526552+00', NULL, NULL, '2026-10-08 06:33:40.526552+00', '2026-10-08 06:33:41.931057+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a11a37-b37b-777a-b279-1d3eeddbeb64:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b37b-777a-b279-1d3eeddbeb64"}', 150, 'done', 1, '2026-10-08 06:33:40.471501+00', NULL, NULL, '2026-10-08 06:33:40.471501+00', '2026-10-08 06:33:41.951252+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a11a37-b37a-7a1b-b153-0d3fe00800fe:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b37a-7a1b-b153-0d3fe00800fe"}', 150, 'done', 1, '2026-10-08 06:33:40.471501+00', NULL, NULL, '2026-10-08 06:33:40.471501+00', '2026-10-08 06:33:41.969798+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a11a37-b378-7bb1-bced-cfc4cef0a79f:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-b378-7bb1-bced-cfc4cef0a79f"}', 150, 'done', 1, '2026-10-08 06:33:40.471501+00', NULL, NULL, '2026-10-08 06:33:40.471501+00', '2026-10-08 06:33:41.988962+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a11a37-b37a-7a1b-b153-0d3fe00800fe:cd45a20922ff7f4c19cb27dc4318a958:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b37a-7a1b-b153-0d3fe00800fe", "window_hash": "cd45a20922ff7f4c19cb27dc4318a958"}', 210, 'done', 1, '2026-10-08 06:33:40.471501+00', NULL, NULL, '2026-10-08 06:33:40.471501+00', '2026-10-08 06:33:42.021778+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a11a37-b37c-7434-85b8-adc2891e44f1:f966fa0fa9c7a3a7adacdea1ce8b66f3:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b37c-7434-85b8-adc2891e44f1", "window_hash": "f966fa0fa9c7a3a7adacdea1ce8b66f3"}', 210, 'done', 1, '2026-10-08 06:33:40.526552+00', NULL, NULL, '2026-10-08 06:33:40.526552+00', '2026-10-08 06:33:42.046889+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a11a37-b3b0-724a-b495-ebdbbcafa865:04a0a4b99308087e60f69cb464e4be9d:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3b0-724a-b495-ebdbbcafa865", "window_hash": "04a0a4b99308087e60f69cb464e4be9d"}', 210, 'done', 1, '2026-10-08 06:33:40.526552+00', NULL, NULL, '2026-10-08 06:33:40.526552+00', '2026-10-08 06:33:42.071856+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a11a37-b3b2-72e7-bffa-db58a50031c6:7754d2fce2f6063baac0947660ff8d62:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3b2-72e7-bffa-db58a50031c6", "window_hash": "7754d2fce2f6063baac0947660ff8d62"}', 210, 'done', 1, '2026-10-08 06:33:40.563543+00', NULL, NULL, '2026-10-08 06:33:40.563543+00', '2026-10-08 06:33:42.09756+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a11a37-b3d5-794c-b791-1ad15f06d957:b4d8f0307c41ef56b270eac87d78ba37:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3d5-794c-b791-1ad15f06d957", "window_hash": "b4d8f0307c41ef56b270eac87d78ba37"}', 210, 'done', 1, '2026-10-08 06:33:40.563543+00', NULL, NULL, '2026-10-08 06:33:40.563543+00', '2026-10-08 06:33:42.124389+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a11a37-b3d6-7054-9c69-90be952d721c:68e52fc43e42359d5d1f27376d68845c:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3d6-7054-9c69-90be952d721c", "window_hash": "68e52fc43e42359d5d1f27376d68845c"}', 210, 'done', 1, '2026-10-08 06:33:40.600257+00', NULL, NULL, '2026-10-08 06:33:40.600257+00', '2026-10-08 06:33:42.150191+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a11a37-b3b0-724a-b495-ebdbbcafa865:2763730b0d453df95f598afd8083f315:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3b0-724a-b495-ebdbbcafa865", "window_hash": "2763730b0d453df95f598afd8083f315"}', 100, 'done', 1, '2026-10-08 06:33:42.651098+00', NULL, NULL, '2026-10-08 06:33:42.651098+00', '2026-10-08 06:33:43.375542+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a11a37-bbfb-708a-a24a-77cdd41aad8c:8dbfb63ad19ef0985ce675545a934fa3:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-bbfb-708a-a24a-77cdd41aad8c", "window_hash": "8dbfb63ad19ef0985ce675545a934fa3"}', 100, 'done', 1, '2026-10-08 06:33:42.651098+00', NULL, NULL, '2026-10-08 06:33:42.651098+00', '2026-10-08 06:33:43.39876+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a11a37-c059-7470-926c-e3ed7b746136:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-c059-7470-926c-e3ed7b746136"}', 150, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.532787+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a11a37-bc44-76f6-a5cc-7fe408a53a02:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-bc44-76f6-a5cc-7fe408a53a02"}', 50, 'done', 1, '2026-10-08 06:33:42.721919+00', NULL, NULL, '2026-10-08 06:33:42.721919+00', '2026-10-08 06:33:43.170246+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a11a37-bc43-737d-a74e-b2becf57c606:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-bc43-737d-a74e-b2becf57c606"}', 50, 'done', 1, '2026-10-08 06:33:42.721919+00', NULL, NULL, '2026-10-08 06:33:42.721919+00', '2026-10-08 06:33:43.189652+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a11a37-bbfd-7449-8941-00f4ecde22df:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-bbfd-7449-8941-00f4ecde22df"}', 50, 'done', 1, '2026-10-08 06:33:42.651098+00', NULL, NULL, '2026-10-08 06:33:42.651098+00', '2026-10-08 06:33:43.208033+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a11a37-bbfc-733d-aa09-fcebebde0fc4:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-bbfc-733d-aa09-fcebebde0fc4"}', 50, 'done', 1, '2026-10-08 06:33:42.651098+00', NULL, NULL, '2026-10-08 06:33:42.651098+00', '2026-10-08 06:33:43.226039+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a11a37-bbfb-708a-a24a-77cdd41aad8c:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-bbfb-708a-a24a-77cdd41aad8c"}', 50, 'done', 1, '2026-10-08 06:33:42.651098+00', NULL, NULL, '2026-10-08 06:33:42.651098+00', '2026-10-08 06:33:43.244295+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a11a37-bc43-737d-a74e-b2becf57c606:1aabcfd3827f269f6d9275dd33706838:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-bc43-737d-a74e-b2becf57c606", "window_hash": "1aabcfd3827f269f6d9275dd33706838"}', 100, 'done', 1, '2026-10-08 06:33:42.721919+00', NULL, NULL, '2026-10-08 06:33:42.721919+00', '2026-10-08 06:33:43.267547+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a11a37-bbfc-733d-aa09-fcebebde0fc4:b9cb6463d29f5732d74415bda37d3540:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-bbfc-733d-aa09-fcebebde0fc4", "window_hash": "b9cb6463d29f5732d74415bda37d3540"}', 100, 'done', 1, '2026-10-08 06:33:42.721919+00', NULL, NULL, '2026-10-08 06:33:42.721919+00', '2026-10-08 06:33:43.293775+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a11a37-b3d6-7054-9c69-90be952d721c:ca04d61b35e988c8c0ddf5890e2ec6ac:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3d6-7054-9c69-90be952d721c", "window_hash": "ca04d61b35e988c8c0ddf5890e2ec6ac"}', 100, 'done', 1, '2026-10-08 06:33:42.721919+00', NULL, NULL, '2026-10-08 06:33:42.721919+00', '2026-10-08 06:33:43.316666+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a11a37-b3d5-794c-b791-1ad15f06d957:38c9f450b52693cc611d9215810703ec:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3d5-794c-b791-1ad15f06d957", "window_hash": "38c9f450b52693cc611d9215810703ec"}', 100, 'done', 1, '2026-10-08 06:33:42.721919+00', NULL, NULL, '2026-10-08 06:33:42.721919+00', '2026-10-08 06:33:43.339913+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a11a37-bbfc-733d-aa09-fcebebde0fc4:68d8e02bec3b4082b2e7c4b50df83628:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-bbfc-733d-aa09-fcebebde0fc4", "window_hash": "68d8e02bec3b4082b2e7c4b50df83628"}', 100, 'obsolete', 1, '2026-10-08 06:33:42.651098+00', NULL, NULL, '2026-10-08 06:33:42.651098+00', '2026-10-08 06:33:43.343437+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a11a37-b3d5-794c-b791-1ad15f06d957:8fe4cd5714d57dab37dd4bf2ca5508eb:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3d5-794c-b791-1ad15f06d957", "window_hash": "8fe4cd5714d57dab37dd4bf2ca5508eb"}', 100, 'obsolete', 1, '2026-10-08 06:33:42.651098+00', NULL, NULL, '2026-10-08 06:33:42.651098+00', '2026-10-08 06:33:43.346804+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a11a37-b3b2-72e7-bffa-db58a50031c6:46c03220df294893319e1b2ed3088b8c:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-b3b2-72e7-bffa-db58a50031c6", "window_hash": "46c03220df294893319e1b2ed3088b8c"}', 100, 'obsolete', 1, '2026-10-08 06:33:42.651098+00', NULL, NULL, '2026-10-08 06:33:42.651098+00', '2026-10-08 06:33:43.353056+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a11a37-c059-73cc-8bec-28e751dcaba7:035073ef313dbdd6274fe4df4165eedc:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-c059-73cc-8bec-28e751dcaba7", "window_hash": "035073ef313dbdd6274fe4df4165eedc"}', 210, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.559114+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a11a37-c05b-73be-bb0d-034a4c9dc3ae:8a0aa4fd532fd0be8e518d95efd2f135:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-c05b-73be-bb0d-034a4c9dc3ae", "window_hash": "8a0aa4fd532fd0be8e518d95efd2f135"}', 210, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.582145+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a11a37-c05c-79b4-884f-fd200ba0de29:d065e1dd8f0b93243ccfd76951eda9ed:extract-77dd347ed8019168e6d3b827877cad4a', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "extract-77dd347ed8019168e6d3b827877cad4a", "revision_id": "01a11a37-c05c-79b4-884f-fd200ba0de29", "window_hash": "d065e1dd8f0b93243ccfd76951eda9ed"}', 210, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.604037+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a11a37-c05d-7b54-b4c8-bd94906e3b4c:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-c05d-7b54-b4c8-bd94906e3b4c"}', 150, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.419217+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a11a37-c05c-79b4-884f-fd200ba0de29:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-c05c-79b4-884f-fd200ba0de29"}', 150, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.439788+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a11a37-c05b-7c59-9763-75bb9c83b91d:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-c05b-7c59-9763-75bb9c83b91d"}', 150, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.458928+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a11a37-c05b-73be-bb0d-034a4c9dc3ae:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-c05b-73be-bb0d-034a4c9dc3ae"}', 150, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.477085+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a11a37-c05a-7d8b-aa4b-4e3ad90e0386:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-c05a-7d8b-aa4b-4e3ad90e0386"}', 150, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.494762+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a11a37-c059-73cc-8bec-28e751dcaba7:embed-d78dc4555c019de1b452a4e6f5173354', '01a11a37-c04b-7aa7-9b86-637259a6907a', '{"generation": "embed-d78dc4555c019de1b452a4e6f5173354", "revision_id": "01a11a37-c059-73cc-8bec-28e751dcaba7"}', 150, 'done', 1, '2026-10-08 06:33:43.768368+00', NULL, NULL, '2026-10-08 06:33:43.768368+00', '2026-10-08 06:33:44.513043+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a11a37-b37d-788b-b326-cef914cc126f', '01a11a37-b369-7efd-bdb2-869680e8a3a0');


--
-- Data for Name: owner_repair; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-77dd347ed8019168e6d3b827877cad4a', 'extract', 'stub', 'http://127.0.0.1:38995/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "a6fec3fe3aabc852", "aliases": "361e584289ae46a4", "confirm": "c1a68b38f8fcae60", "compiler": "extract-v16", "endpoint": "http://127.0.0.1:38995/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "ec86a5ac4362f77d", "temperature": 0, "target_chars": 6000, "context_chars": 1000, "context_turns": 3}', '2026-10-08 06:33:40.267232+00', '2026-10-08 06:33:40.268318+00');
INSERT INTO public.projection_generation VALUES ('embed-d78dc4555c019de1b452a4e6f5173354', 'embed', 'stub-embed', 'http://127.0.0.1:38995/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:38995/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-10-08 06:33:40.267232+00', '2026-10-08 06:33:40.272015+00');
INSERT INTO public.projection_generation VALUES ('summarize-92d501537d9475bbaa07a766aeb7aa3a', 'summarize', 'stub', 'http://127.0.0.1:38995/v1', '{"lag": 4, "kind": "summarize", "model": "stub", "prompt": "1cb5649d13d81671", "window": 8, "version": "summarize-v3", "endpoint": "http://127.0.0.1:38995/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "message_chars": 6000}', '2026-10-08 06:33:40.267232+00', '2026-10-08 06:33:40.274621+00');
INSERT INTO public.projection_generation VALUES ('canon-4b3f6ac11e86a08cfdc05f0e3c711dcc', 'canon', 'stub', 'http://127.0.0.1:38995/v1', '{"kind": "canon", "model": "stub", "prompt": "c084747d55328ce7", "version": "canon-v1", "endpoint": "http://127.0.0.1:38995/v1", "json_mode": true, "max_parts": 4, "normalizer": "clean-v3", "part_chars": 6000, "predicates": "9aebb33c40fcda7c", "temperature": 0}', '2026-10-08 06:33:40.267232+00', '2026-10-08 06:33:40.275913+00');
INSERT INTO public.projection_generation VALUES ('reveal-39ae591aff2f5c3e3cd1472175a54904', 'reveal', 'stub', 'http://127.0.0.1:38995/v1', '{"kind": "reveal", "model": "stub", "prompt": "799b88903bfe0c44", "version": "reveal-v1", "compiler": "extract-v15", "endpoint": "http://127.0.0.1:38995/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "target_chars": 6000, "context_chars": 1000, "context_turns": 3}', '2026-10-08 06:33:40.267232+00', '2026-10-08 06:33:40.279188+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a11a37-b3a3-7b4c-804c-e29f18f76528', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '01a11a37-b37f-7ef3-ade5-80ef92d0285d', 'Is Rin with you?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a11a37-b37b-777a-b279-1d3eeddbeb64", "keyword_score": 1.0986, "host_logical_id": "8ed2da0c-b165-42bd-8a83-094fda9b646c"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a11a37-b37b-777a-b279-1d3eeddbeb64", "keyword_score": 1.0986, "host_logical_id": "8ed2da0c-b165-42bd-8a83-094fda9b646c"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 26.64, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 1.44, "fits_at": null, "lexical": 4.28, "threads": 0, "keywords": 4.86, "extractor": "extract-77dd347ed801", "embed_wait": 12.54, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 29.61, "ended_left_out": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d78dc4555c019d", "memory_mode_withheld": 0}', 'fresh', '2026-10-08 06:33:40.486275+00', 'packet-v12', 600, 3, '', '["8ed2da0c-b165-42bd-8a83-094fda9b646c", "9adf2606-d06d-48c0-8ab2-b41f320f0909", "b9a40939-eb41-4218-9960-92453a451c7d", "e2024e47-1167-466c-90a1-04cefd4f5e9b"]', 'extract-77dd347ed8019168e6d3b827877cad4a', 'embed-d78dc4555c019de1b452a4e6f5173354', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-4b3f6ac11e86a08cfdc05f0e3c711dcc", "first_cue": true, "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "history_marks": true, "name_variants": true, "summarize_key": "summarize-92d501537d9475bbaa07a766aeb7aa3a", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a11a37-b3cb-792d-8a7e-682f2e0486d1', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '01a11a37-b37f-7ef3-ade5-80ef92d0285d', 'Let''s check the market.', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a11a37-b3b1-7d4e-ad41-e8e5c0badac8", "keyword_score": 5.8377, "host_logical_id": "bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a11a37-b3b1-7d4e-ad41-e8e5c0badac8", "keyword_score": 5.8377, "host_logical_id": "bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 14.05, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 0.8, "fits_at": null, "lexical": 2.89, "threads": 0, "keywords": 4.49, "extractor": "extract-77dd347ed801", "embed_wait": 4.43, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 16.07, "ended_left_out": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d78dc4555c019d", "memory_mode_withheld": 0}', 'fresh', '2026-10-08 06:33:40.539303+00', 'packet-v12', 600, 7, '', '["4a23ebc8-b225-4788-9d4b-d5b68e73cc7f", "b97ad3bc-1991-4454-8a4b-684283f3b175", "bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd", "db5334ea-f745-46c3-9318-267d04f87922"]', 'extract-77dd347ed8019168e6d3b827877cad4a', 'embed-d78dc4555c019de1b452a4e6f5173354', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-4b3f6ac11e86a08cfdc05f0e3c711dcc", "first_cue": true, "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "history_marks": true, "name_variants": true, "summarize_key": "summarize-92d501537d9475bbaa07a766aeb7aa3a", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a11a37-b3ef-71b4-918b-49ac164577db', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '01a11a37-b37f-7ef3-ade5-80ef92d0285d', 'Where do we meet tonight?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0", "keyword_score": 4.7958, "host_logical_id": "374ed69f-3a2f-44f7-8b24-267ac414e034"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0", "keyword_score": 4.7958, "host_logical_id": "374ed69f-3a2f-44f7-8b24-267ac414e034"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 14.19, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 0.77, "fits_at": null, "lexical": 2.68, "threads": 0, "keywords": 3.01, "extractor": "extract-77dd347ed801", "embed_wait": 6.34, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 16.1, "ended_left_out": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d78dc4555c019d", "memory_mode_withheld": 0}', 'fresh', '2026-10-08 06:33:40.575382+00', 'packet-v12', 600, 11, '', '["374ed69f-3a2f-44f7-8b24-267ac414e034", "919d82d5-f6d5-4888-b49b-e2ac96d441dd", "a637975f-a844-46fb-a307-d7ae7d97a3fc", "d492edfa-fc9e-468f-af9e-63863efeff58"]', 'extract-77dd347ed8019168e6d3b827877cad4a', 'embed-d78dc4555c019de1b452a4e6f5173354', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-4b3f6ac11e86a08cfdc05f0e3c711dcc", "first_cue": true, "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "history_marks": true, "name_variants": true, "summarize_key": "summarize-92d501537d9475bbaa07a766aeb7aa3a", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a11a37-b40f-7060-aa74-e1bbb86cf4aa', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '01a11a37-b37f-7ef3-ade5-80ef92d0285d', 'Where is Mina now?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a11a37-b3f9-734e-936a-c7abca08ed81", "keyword_score": 0.7732, "host_logical_id": "a8d6d019-be96-4451-a351-1eeb2360bb49"}, {"rrf": 0.03151, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a11a37-b37c-7434-85b8-adc2891e44f1", "keyword_score": 0.7732, "host_logical_id": "e2024e47-1167-466c-90a1-04cefd4f5e9b"}, {"rrf": 0.03102, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a11a37-b37a-7a1b-b153-0d3fe00800fe", "keyword_score": 0.7732, "host_logical_id": "b9a40939-eb41-4218-9960-92453a451c7d"}, {"rrf": 0.01613, "sim": null, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a11a37-b3d6-7054-9c69-90be952d721c", "keyword_score": 0.7732, "host_logical_id": "d492edfa-fc9e-468f-af9e-63863efeff58"}, {"rrf": 0.01587, "sim": null, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a11a37-b3b0-724a-b495-ebdbbcafa865", "keyword_score": 0.7732, "host_logical_id": "db5334ea-f745-46c3-9318-267d04f87922"}, {"rrf": 0.01562, "sim": null, "score": 0.0, "position": 4, "user_score": 0.0, "revision_id": "01a11a37-b3af-79ea-a3ed-9b02bab293e9", "keyword_score": 0.7732, "host_logical_id": "4a23ebc8-b225-4788-9d4b-d5b68e73cc7f"}]', '[{"turn": 0, "score": 0.03102, "revision_id": "01a11a37-b37a-7a1b-b153-0d3fe00800fe"}, {"turn": 1, "score": 0.03151, "revision_id": "01a11a37-b37c-7434-85b8-adc2891e44f1"}, {"turn": 2, "score": 0.01562, "revision_id": "01a11a37-b3af-79ea-a3ed-9b02bab293e9"}, {"turn": 2, "score": 0.01587, "revision_id": "01a11a37-b3b0-724a-b495-ebdbbcafa865"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a11a37-b3f9-734e-936a-c7abca08ed81", "keyword_score": 0.7732, "host_logical_id": "a8d6d019-be96-4451-a351-1eeb2360bb49"}, {"rrf": 0.01613, "sim": null, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a11a37-b3d6-7054-9c69-90be952d721c", "keyword_score": 0.7732, "host_logical_id": "d492edfa-fc9e-468f-af9e-63863efeff58"}]', 227, '{"fit": 0.0, "cast": 0, "embed": 14.24, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 4, "summary": 0}, "vector": 0.83, "fits_at": null, "lexical": 2.34, "threads": 0, "keywords": 6.69, "extractor": "extract-77dd347ed801", "embed_lead": 10.26, "embed_wait": 0.01, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 13.96, "ended_left_out": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d78dc4555c019d", "memory_mode_withheld": 0}', 'fresh', '2026-10-08 06:33:40.609146+00', 'packet-v12', 600, 12, '', '["374ed69f-3a2f-44f7-8b24-267ac414e034", "a637975f-a844-46fb-a307-d7ae7d97a3fc", "a8d6d019-be96-4451-a351-1eeb2360bb49", "d492edfa-fc9e-468f-af9e-63863efeff58"]', 'extract-77dd347ed8019168e6d3b827877cad4a', 'embed-d78dc4555c019de1b452a4e6f5173354', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-4b3f6ac11e86a08cfdc05f0e3c711dcc", "first_cue": true, "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "history_marks": true, "name_variants": true, "summarize_key": "summarize-92d501537d9475bbaa07a766aeb7aa3a", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a11a37-b37c-7434-85b8-adc2891e44f1"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 1, "placed": true}, {"ref": {"revision": "01a11a37-b37a-7a1b-b153-0d3fe00800fe"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 0, "placed": true}, {"ref": {"revision": "01a11a37-b3b0-724a-b495-ebdbbcafa865"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "placed": true}, {"ref": {"revision": "01a11a37-b3af-79ea-a3ed-9b02bab293e9"}, "tok": 23, "why": "placed", "kind": "excerpt", "text": "What did Mina say before she left?", "turn": 2, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a11a37-bc11-7368-b6b0-a0c2a3e32664', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '01a11a37-bc00-7ca3-96e9-0a3b500bdc9e', 'And the compass?', '[{"rrf": 0.04741, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a11a37-b3d5-794c-b791-1ad15f06d957", "keyword_score": 2.0149, "host_logical_id": "a637975f-a844-46fb-a307-d7ae7d97a3fc"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a11a37-bbfd-7449-8941-00f4ecde22df", "keyword_score": 2.0149, "host_logical_id": "e361c9c3-248e-432f-8302-4c8a95b2395e"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a11a37-b37a-7a1b-b153-0d3fe00800fe", "keyword_score": 0.0, "host_logical_id": "b9a40939-eb41-4218-9960-92453a451c7d"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a11a37-b378-7bb1-bced-cfc4cef0a79f", "keyword_score": 0.0, "host_logical_id": "9adf2606-d06d-48c0-8ab2-b41f320f0909"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a11a37-b3b2-72e7-bffa-db58a50031c6", "keyword_score": 0.0, "host_logical_id": "b97ad3bc-1991-4454-8a4b-684283f3b175"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a11a37-b3b0-724a-b495-ebdbbcafa865", "keyword_score": 0.0, "host_logical_id": "db5334ea-f745-46c3-9318-267d04f87922"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a11a37-b378-7bb1-bced-cfc4cef0a79f"}, {"turn": 2, "score": 0.01562, "revision_id": "01a11a37-b3b0-724a-b495-ebdbbcafa865"}, {"turn": 3, "score": 0.01587, "revision_id": "01a11a37-b3b2-72e7-bffa-db58a50031c6"}, {"turn": 4, "score": 0.04741, "revision_id": "01a11a37-b3d5-794c-b791-1ad15f06d957"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a11a37-bbfd-7449-8941-00f4ecde22df", "keyword_score": 2.0149, "host_logical_id": "e361c9c3-248e-432f-8302-4c8a95b2395e"}]', 298, '{"fit": 0.0, "cast": 2, "embed": 15.37, "facts": 0, "placed": {"fact": 2, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 4, "summary": 0}, "vector": 0.82, "fits_at": null, "lexical": 2.54, "threads": 0, "keywords": 2.01, "extractor": "extract-77dd347ed801", "embed_lead": 13.46, "embed_wait": 0.0, "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 9.8, "ended_left_out": 0, "keyword_withheld": 0, "replaced_left_out": 1, "embedding_projection": "embed-d78dc4555c019d", "memory_mode_withheld": 0}', 'fresh', '2026-10-08 06:33:42.663361+00', 'packet-v12', 600, 14, '', '["3c3589eb-1c39-4d77-9d28-d00f1b12c425", "a8d6d019-be96-4451-a351-1eeb2360bb49", "d492edfa-fc9e-468f-af9e-63863efeff58", "e361c9c3-248e-432f-8302-4c8a95b2395e"]', 'extract-77dd347ed8019168e6d3b827877cad4a', 'embed-d78dc4555c019de1b452a4e6f5173354', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-4b3f6ac11e86a08cfdc05f0e3c711dcc", "first_cue": true, "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "history_marks": true, "name_variants": true, "summarize_key": "summarize-92d501537d9475bbaa07a766aeb7aa3a", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 7}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 2}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a11a37-b3d5-794c-b791-1ad15f06d957"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "placed": true}, {"ref": {"revision": "01a11a37-b378-7bb1-bced-cfc4cef0a79f"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a11a37-b3b2-72e7-bffa-db58a50031c6"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 3, "placed": true}, {"ref": {"revision": "01a11a37-b3b0-724a-b495-ebdbbcafa865"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a11a37-bc35-7e13-90aa-429f726a85d9', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '01a11a37-bc00-7ca3-96e9-0a3b500bdc9e', 'compass', '[{"rrf": 0.04615, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a11a37-b3d5-794c-b791-1ad15f06d957", "keyword_score": 2.0149, "host_logical_id": "a637975f-a844-46fb-a307-d7ae7d97a3fc"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a11a37-bbfd-7449-8941-00f4ecde22df", "keyword_score": 2.0149, "host_logical_id": "e361c9c3-248e-432f-8302-4c8a95b2395e"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a11a37-b3d6-7054-9c69-90be952d721c", "keyword_score": 0.0, "host_logical_id": "d492edfa-fc9e-468f-af9e-63863efeff58"}]', '[{"turn": 4, "score": 0.04615, "revision_id": "01a11a37-b3d5-794c-b791-1ad15f06d957"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a11a37-bbfd-7449-8941-00f4ecde22df", "keyword_score": 2.0149, "host_logical_id": "e361c9c3-248e-432f-8302-4c8a95b2395e"}]', 222, '{"fit": 0.0, "cast": 2, "embed": 14.92, "facts": 0, "placed": {"fact": 2, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0}, "vector": 1.08, "fits_at": null, "lexical": 3.82, "threads": 0, "keywords": 2.25, "extractor": "extract-77dd347ed801", "embed_wait": 5.98, "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 18.53, "ended_left_out": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d78dc4555c019d", "memory_mode_withheld": 0}', 'fresh', '2026-10-08 06:33:42.691017+00', 'packet-v12', 600, 15, '', '["3c3589eb-1c39-4d77-9d28-d00f1b12c425", "a8d6d019-be96-4451-a351-1eeb2360bb49", "ac0a057c-74b6-43ed-8fb8-afa805fa027f", "e361c9c3-248e-432f-8302-4c8a95b2395e"]', 'extract-77dd347ed8019168e6d3b827877cad4a', 'embed-d78dc4555c019de1b452a4e6f5173354', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-4b3f6ac11e86a08cfdc05f0e3c711dcc", "first_cue": true, "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "history_marks": true, "name_variants": true, "summarize_key": "summarize-92d501537d9475bbaa07a766aeb7aa3a", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 7}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 2}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a11a37-b3d5-794c-b791-1ad15f06d957"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "placed": true}, {"ref": {"revision": "01a11a37-b3d6-7054-9c69-90be952d721c"}, "tok": 0, "why": "repeats", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 5, "placed": false, "repeats": {"assertion": 7}}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a11a37-bc55-7a04-9bea-763e36f7ec3c', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '01a11a37-bc47-7e9a-88f2-df2aad69d69d', 'Let''s go.', '[{"rrf": 0.04865, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a11a37-b3b1-7d4e-ad41-e8e5c0badac8", "keyword_score": 2.0794, "host_logical_id": "bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a11a37-bc44-76f6-a5cc-7fe408a53a02", "keyword_score": 2.0794, "host_logical_id": "5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e"}]', '[{"turn": 3, "score": 0.04865, "revision_id": "01a11a37-b3b1-7d4e-ad41-e8e5c0badac8"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a11a37-bc44-76f6-a5cc-7fe408a53a02", "keyword_score": 2.0794, "host_logical_id": "5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e"}]', 138, '{"fit": 0.0, "cast": 0, "embed": 14.05, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0}, "vector": 0.82, "fits_at": null, "lexical": 2.24, "threads": 0, "keywords": 2.05, "extractor": "extract-77dd347ed801", "embed_lead": 12.53, "embed_wait": 0.0, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 8.18, "ended_left_out": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d78dc4555c019d", "memory_mode_withheld": 0}', 'fresh', '2026-10-08 06:33:42.733044+00', 'packet-v12', 600, 16, '', '["3c3589eb-1c39-4d77-9d28-d00f1b12c425", "5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e", "ac0a057c-74b6-43ed-8fb8-afa805fa027f", "e361c9c3-248e-432f-8302-4c8a95b2395e"]', 'extract-77dd347ed8019168e6d3b827877cad4a', 'embed-d78dc4555c019de1b452a4e6f5173354', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-4b3f6ac11e86a08cfdc05f0e3c711dcc", "first_cue": true, "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "history_marks": true, "name_variants": true, "summarize_key": "summarize-92d501537d9475bbaa07a766aeb7aa3a", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a11a37-b3b1-7d4e-ad41-e8e5c0badac8"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 3, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a11a37-c076-7d8c-b346-db9ecfef4279', '01a11a37-c04b-7aa7-9b86-637259a6907a', '01a11a37-c05f-71d5-8501-baeab8feb19c', 'Where is Rin?', '[{"rrf": 0.03227, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a11a37-c05a-7d8b-aa4b-4e3ad90e0386", "keyword_score": 0.8473, "host_logical_id": "8025b532-342f-4336-994b-6943f1b4aeab"}, {"rrf": 0.03226, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a11a37-c05b-73be-bb0d-034a4c9dc3ae", "keyword_score": 0.8473, "host_logical_id": "0137f8df-0fb6-4424-829e-d09188013daa"}, {"rrf": 0.01639, "sim": null, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a11a37-c05d-7b54-b4c8-bd94906e3b4c", "keyword_score": 0.8473, "host_logical_id": "5faae7a5-e3fa-44c7-9430-972837c5c973"}]', '[{"turn": 1, "score": 0.03227, "revision_id": "01a11a37-c05a-7d8b-aa4b-4e3ad90e0386"}, {"turn": 1, "score": 0.03226, "revision_id": "01a11a37-c05b-73be-bb0d-034a4c9dc3ae"}]', '[{"rrf": 0.01639, "sim": null, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a11a37-c05d-7b54-b4c8-bd94906e3b4c", "keyword_score": 0.8473, "host_logical_id": "5faae7a5-e3fa-44c7-9430-972837c5c973"}]', 164, '{"fit": 0.0, "cast": 0, "embed": 15.64, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2, "summary": 0}, "vector": 0.96, "fits_at": null, "lexical": 2.69, "threads": 0, "keywords": 2.21, "extractor": "extract-77dd347ed801", "embed_wait": 8.76, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 17.97, "ended_left_out": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-d78dc4555c019d", "memory_mode_withheld": 0}', 'fresh', '2026-10-08 06:33:43.780995+00', 'packet-v12', 600, 7, '', '["0745cc01-46ab-4db0-b7fc-59e76470f2f2", "5faae7a5-e3fa-44c7-9430-972837c5c973", "61e32194-8120-4db7-af10-e320c6bbb844", "67893689-6eac-48f2-a7cd-f2920092d287"]', 'extract-77dd347ed8019168e6d3b827877cad4a', 'embed-d78dc4555c019de1b452a4e6f5173354', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-4b3f6ac11e86a08cfdc05f0e3c711dcc", "first_cue": true, "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "history_marks": true, "name_variants": true, "summarize_key": "summarize-92d501537d9475bbaa07a766aeb7aa3a", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a11a37-c05a-7d8b-aa4b-4e3ad90e0386"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 1, "placed": true}, {"ref": {"revision": "01a11a37-c05b-73be-bb0d-034a4c9dc3ae"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 1, "placed": true}]', NULL, '[]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a11a37-b3f9-734e-936a-c7abca08ed81', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.742652+00', '{"ms": 30, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b3d6-7054-9c69-90be952d721c', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.764693+00', '{"ms": 15, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.78457+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b3d5-794c-b791-1ad15f06d957', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.804228+00', '{"ms": 12, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b3d4-7314-b72d-941ac7d54bd8', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.826821+00', '{"ms": 17, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b3b2-72e7-bffa-db58a50031c6', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.846137+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b3b1-7d4e-ad41-e8e5c0badac8', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.866127+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b3b0-724a-b495-ebdbbcafa865', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.88761+00', '{"ms": 16, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b3af-79ea-a3ed-9b02bab293e9', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.911436+00', '{"ms": 18, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b37c-7434-85b8-adc2891e44f1', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.929654+00', '{"ms": 13, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b37b-777a-b279-1d3eeddbeb64', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.949712+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b37a-7a1b-b153-0d3fe00800fe', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.968394+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-b378-7bb1-bced-cfc4cef0a79f', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:41.987612+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-bc44-76f6-a5cc-7fe408a53a02', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:43.16874+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-bc43-737d-a74e-b2becf57c606', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:43.188232+00', '{"ms": 12, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-bbfd-7449-8941-00f4ecde22df', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:43.206647+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-bbfc-733d-aa09-fcebebde0fc4', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:43.224577+00', '{"ms": 13, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-bbfb-708a-a24a-77cdd41aad8c', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:43.242854+00', '{"ms": 13, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-c05d-7b54-b4c8-bd94906e3b4c', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:44.417824+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-c05c-79b4-884f-fd200ba0de29', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:44.438403+00', '{"ms": 15, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-c05b-7c59-9763-75bb9c83b91d', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:44.457581+00', '{"ms": 14, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-c05b-73be-bb0d-034a4c9dc3ae', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:44.475643+00', '{"ms": 13, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-c05a-7d8b-aa4b-4e3ad90e0386', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:44.493305+00', '{"ms": 13, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-c059-73cc-8bec-28e751dcaba7', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:44.511627+00', '{"ms": 13, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a11a37-c059-7470-926c-e3ed7b746136', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-d78dc4555c019de1b452a4e6f5173354', '2026-10-08 06:33:44.531452+00', '{"ms": 15, "calls": 1}');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a11a37-b378-7bb1-bced-cfc4cef0a79f', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-10-08 06:33:40.471501+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b37a-7a1b-b153-0d3fe00800fe', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-10-08 06:33:40.471501+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b37b-777a-b279-1d3eeddbeb64', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-10-08 06:33:40.471501+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b37c-7434-85b8-adc2891e44f1', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-10-08 06:33:40.471501+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3af-79ea-a3ed-9b02bab293e9', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-10-08 06:33:40.526552+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3b0-724a-b495-ebdbbcafa865', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-10-08 06:33:40.526552+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3b1-7d4e-ad41-e8e5c0badac8', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-10-08 06:33:40.526552+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3b2-72e7-bffa-db58a50031c6', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-10-08 06:33:40.526552+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3d4-7314-b72d-941ac7d54bd8', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-10-08 06:33:40.563543+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3d5-794c-b791-1ad15f06d957', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-10-08 06:33:40.563543+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-10-08 06:33:40.563543+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3d6-7054-9c69-90be952d721c', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-10-08 06:33:40.563543+00');
INSERT INTO public.revision_text VALUES ('01a11a37-b3f9-734e-936a-c7abca08ed81', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-10-08 06:33:40.600257+00');
INSERT INTO public.revision_text VALUES ('01a11a37-bbfb-708a-a24a-77cdd41aad8c', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-10-08 06:33:42.651098+00');
INSERT INTO public.revision_text VALUES ('01a11a37-bbfc-733d-aa09-fcebebde0fc4', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-10-08 06:33:42.651098+00');
INSERT INTO public.revision_text VALUES ('01a11a37-bbfd-7449-8941-00f4ecde22df', 'clean-v3', 'And the compass?', 16, 16, '2026-10-08 06:33:42.651098+00');
INSERT INTO public.revision_text VALUES ('01a11a37-bc1b-7537-bf81-fb6321665260', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-10-08 06:33:42.682781+00');
INSERT INTO public.revision_text VALUES ('01a11a37-bc42-7e22-ac40-318161f2ed68', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-10-08 06:33:42.721919+00');
INSERT INTO public.revision_text VALUES ('01a11a37-bc43-737d-a74e-b2becf57c606', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-10-08 06:33:42.721919+00');
INSERT INTO public.revision_text VALUES ('01a11a37-bc44-76f6-a5cc-7fe408a53a02', 'clean-v3', 'Let''s go.', 9, 9, '2026-10-08 06:33:42.721919+00');
INSERT INTO public.revision_text VALUES ('01a11a37-c059-7470-926c-e3ed7b746136', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-10-08 06:33:43.768368+00');
INSERT INTO public.revision_text VALUES ('01a11a37-c059-73cc-8bec-28e751dcaba7', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-10-08 06:33:43.768368+00');
INSERT INTO public.revision_text VALUES ('01a11a37-c05a-7d8b-aa4b-4e3ad90e0386', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-10-08 06:33:43.768368+00');
INSERT INTO public.revision_text VALUES ('01a11a37-c05b-73be-bb0d-034a4c9dc3ae', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-10-08 06:33:43.768368+00');
INSERT INTO public.revision_text VALUES ('01a11a37-c05b-7c59-9763-75bb9c83b91d', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-10-08 06:33:43.768368+00');
INSERT INTO public.revision_text VALUES ('01a11a37-c05c-79b4-884f-fd200ba0de29', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-10-08 06:33:43.768368+00');
INSERT INTO public.revision_text VALUES ('01a11a37-c05c-7822-b26d-51036175b04b', 'clean-v3', '{{specialcomment::branchedfrom::125f228f-e94b-461c-b4bc-8afbf99a362d::Harbor route::db5334ea-f745-46c3-9318-267d04f87922::}}', 124, 124, '2026-10-08 06:33:43.768368+00');
INSERT INTO public.revision_text VALUES ('01a11a37-c05d-7b54-b4c8-bd94906e3b4c', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-10-08 06:33:43.768368+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-10-08 06:33:39.231364+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-10-08 06:33:39.309893+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-10-08 06:33:39.326127+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-10-08 06:33:39.3708+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-10-08 06:33:39.391553+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-10-08 06:33:39.40039+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-10-08 06:33:39.402125+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-10-08 06:33:39.41268+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-10-08 06:33:39.431087+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-10-08 06:33:39.433809+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-10-08 06:33:39.435623+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-10-08 06:33:39.445103+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-10-08 06:33:39.470931+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-10-08 06:33:39.48741+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-10-08 06:33:39.489865+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-10-08 06:33:39.502329+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-10-08 06:33:39.504193+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-10-08 06:33:39.506119+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-10-08 06:33:39.507782+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-10-08 06:33:39.520963+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-10-08 06:33:39.523455+00');
INSERT INTO public.schema_migrations VALUES ('0022_thread_outcome_and_cause.sql', '9a8507f1b42457d2c44d568a2bd60d868f923613f8c83acb2be7f9104041cc88', '2026-10-08 06:33:39.525269+00');
INSERT INTO public.schema_migrations VALUES ('0023_summaries.sql', 'da452cf41917f9cc59c3a9d71e4114bf5179d3c5493669a5c7ce83ea13e0fb77', '2026-10-08 06:33:39.527068+00');
INSERT INTO public.schema_migrations VALUES ('0024_owner_repair.sql', 'de78024aceb993e7822500bb13d17d034b0123cdf67225fc9c8d82e16164e3be', '2026-10-08 06:33:39.540489+00');
INSERT INTO public.schema_migrations VALUES ('0025_canon.sql', '692a149bab93cd46b4bff801fc8ca0d857dc72ae88ca73471b33668cc2e694e3', '2026-10-08 06:33:39.554048+00');
INSERT INTO public.schema_migrations VALUES ('0026_canon_facts.sql', '5998bd556819cc977b9c0dabf9baa53303a5ac0504abb5742f6c3c11f1ec81dd', '2026-10-08 06:33:39.572228+00');
INSERT INTO public.schema_migrations VALUES ('0027_model_usage.sql', 'a0397dba46c52771feba09a4ce8f7fa1e8307fe36ba1a5fbaf4ad1489bfda2c6', '2026-10-08 06:33:39.578049+00');
INSERT INTO public.schema_migrations VALUES ('0028_reveal_checks.sql', '24d4cea55f72664dd0370f396582daa93d69881fc5f06dd5de46bfc295eb3325', '2026-10-08 06:33:39.579849+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a11a37-b378-7281-aa9c-f0d8b78b413e', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '9adf2606-d06d-48c0-8ab2-b41f320f0909', 'message', '2026-10-08 06:33:40.471501+00');
INSERT INTO public.source_object VALUES ('01a11a37-b37a-7e51-a05e-bc67b1540832', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'b9a40939-eb41-4218-9960-92453a451c7d', 'message', '2026-10-08 06:33:40.471501+00');
INSERT INTO public.source_object VALUES ('01a11a37-b37b-7639-b02b-648857a31bdd', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '8ed2da0c-b165-42bd-8a83-094fda9b646c', 'message', '2026-10-08 06:33:40.471501+00');
INSERT INTO public.source_object VALUES ('01a11a37-b37c-733a-8994-aa6bd3f8f8dd', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'e2024e47-1167-466c-90a1-04cefd4f5e9b', 'message', '2026-10-08 06:33:40.471501+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3af-70ba-bdc2-a35b106fcc7a', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '4a23ebc8-b225-4788-9d4b-d5b68e73cc7f', 'message', '2026-10-08 06:33:40.526552+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3af-768e-9b14-ec64b21bb7e8', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'db5334ea-f745-46c3-9318-267d04f87922', 'message', '2026-10-08 06:33:40.526552+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3b1-74cc-9ab7-cf8787504ced', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd', 'message', '2026-10-08 06:33:40.526552+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3b1-7ec7-9ddb-6f67ea6ccc3f', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'b97ad3bc-1991-4454-8a4b-684283f3b175', 'message', '2026-10-08 06:33:40.526552+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3d4-77c8-97f6-0e6b9866b7e6', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '919d82d5-f6d5-4888-b49b-e2ac96d441dd', 'message', '2026-10-08 06:33:40.563543+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3d4-7d87-a967-750b7da441f6', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'a637975f-a844-46fb-a307-d7ae7d97a3fc', 'message', '2026-10-08 06:33:40.563543+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3d5-782c-a7c3-d48eddf97f88', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '374ed69f-3a2f-44f7-8b24-267ac414e034', 'message', '2026-10-08 06:33:40.563543+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3d6-7f3b-a891-014efab65671', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'd492edfa-fc9e-468f-af9e-63863efeff58', 'message', '2026-10-08 06:33:40.563543+00');
INSERT INTO public.source_object VALUES ('01a11a37-b3f8-74cb-8019-71a5da70bc28', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'a8d6d019-be96-4451-a351-1eeb2360bb49', 'message', '2026-10-08 06:33:40.600257+00');
INSERT INTO public.source_object VALUES ('01a11a37-bbfc-74cd-bdb7-003bf16506e5', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '3c3589eb-1c39-4d77-9d28-d00f1b12c425', 'message', '2026-10-08 06:33:42.651098+00');
INSERT INTO public.source_object VALUES ('01a11a37-bbfd-7051-9fe6-560c700551e1', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'e361c9c3-248e-432f-8302-4c8a95b2395e', 'message', '2026-10-08 06:33:42.651098+00');
INSERT INTO public.source_object VALUES ('01a11a37-bc1b-77a5-8c3f-92d9da8b7134', '01a11a37-b369-7efd-bdb2-869680e8a3a0', 'ac0a057c-74b6-43ed-8fb8-afa805fa027f', 'message', '2026-10-08 06:33:42.682781+00');
INSERT INTO public.source_object VALUES ('01a11a37-bc43-7229-917e-1083eb78f0a9', '01a11a37-b369-7efd-bdb2-869680e8a3a0', '5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e', 'message', '2026-10-08 06:33:42.721919+00');
INSERT INTO public.source_object VALUES ('01a11a37-c058-7eb8-a744-555ff36c890f', '01a11a37-c04b-7aa7-9b86-637259a6907a', 'c776a045-da0c-4eea-b8ea-8cde9e513eb8', 'message', '2026-10-08 06:33:43.768368+00');
INSERT INTO public.source_object VALUES ('01a11a37-c059-799f-bd6a-87d32b80e60b', '01a11a37-c04b-7aa7-9b86-637259a6907a', '83ae9fdf-749c-45a9-a92a-66f672eccd1e', 'message', '2026-10-08 06:33:43.768368+00');
INSERT INTO public.source_object VALUES ('01a11a37-c05a-7fcc-9d35-f1be552708fc', '01a11a37-c04b-7aa7-9b86-637259a6907a', '8025b532-342f-4336-994b-6943f1b4aeab', 'message', '2026-10-08 06:33:43.768368+00');
INSERT INTO public.source_object VALUES ('01a11a37-c05a-7762-8c6e-0ce9a4cdd7a4', '01a11a37-c04b-7aa7-9b86-637259a6907a', '0137f8df-0fb6-4424-829e-d09188013daa', 'message', '2026-10-08 06:33:43.768368+00');
INSERT INTO public.source_object VALUES ('01a11a37-c05b-7a4e-9c37-d186857a2944', '01a11a37-c04b-7aa7-9b86-637259a6907a', '61e32194-8120-4db7-af10-e320c6bbb844', 'message', '2026-10-08 06:33:43.768368+00');
INSERT INTO public.source_object VALUES ('01a11a37-c05c-7e34-bea6-e068f0286366', '01a11a37-c04b-7aa7-9b86-637259a6907a', '0745cc01-46ab-4db0-b7fc-59e76470f2f2', 'message', '2026-10-08 06:33:43.768368+00');
INSERT INTO public.source_object VALUES ('01a11a37-c05c-76f4-be94-86960589b470', '01a11a37-c04b-7aa7-9b86-637259a6907a', '67893689-6eac-48f2-a7cd-f2920092d287', 'message', '2026-10-08 06:33:43.768368+00');
INSERT INTO public.source_object VALUES ('01a11a37-c05d-7040-8fa3-66d3b8876d8a', '01a11a37-c04b-7aa7-9b86-637259a6907a', '5faae7a5-e3fa-44c7-9430-972837c5c973', 'message', '2026-10-08 06:33:43.768368+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a11a37-b378-7bb1-bced-cfc4cef0a79f', '01a11a37-b378-7281-aa9c-f0d8b78b413e', 'e36f9551c56076721f946cd2535335975c4f9830473665373689cb0e45834da1', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "9adf2606-d06d-48c0-8ab2-b41f320f0909", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:40.471501+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b37b-777a-b279-1d3eeddbeb64', '01a11a37-b37b-7639-b02b-648857a31bdd', 'a8499762ff56b19c333ee7e65a45bf1874145c77564cdb5ed035d5cf3f97c4da', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "8ed2da0c-b165-42bd-8a83-094fda9b646c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:40.471501+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b37a-7a1b-b153-0d3fe00800fe', '01a11a37-b37a-7e51-a05e-bc67b1540832', 'ff551dffe0c80900759b58c1106a2181c91f0cf63d3d95a85617643c02b2466b', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "b9a40939-eb41-4218-9960-92453a451c7d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b9a40939-eb41-4218-9960-92453a451c7d", "specialComments": []}', '2026-10-08 06:33:40.471501+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3af-79ea-a3ed-9b02bab293e9', '01a11a37-b3af-70ba-bdc2-a35b106fcc7a', '48bf4f0ad182ba0ee0e6c42f2783ac65f86760fc5ba42488192417ecc3458d34', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "4a23ebc8-b225-4788-9d4b-d5b68e73cc7f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:40.526552+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3b1-7d4e-ad41-e8e5c0badac8', '01a11a37-b3b1-74cc-9ab7-cf8787504ced', 'd2d64ec42ab33b6ccac3c3f512a2565c50a57838652e990cc7db7fa42039f496', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:40.526552+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3b0-724a-b495-ebdbbcafa865', '01a11a37-b3af-768e-9b14-ec64b21bb7e8', '1e702ba51bab01f6444cb540c7f0eafe833f93eb5468e5ca5c271ec89a6dcfdb', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "db5334ea-f745-46c3-9318-267d04f87922", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "db5334ea-f745-46c3-9318-267d04f87922", "specialComments": []}', '2026-10-08 06:33:40.526552+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3d4-7314-b72d-941ac7d54bd8', '01a11a37-b3d4-77c8-97f6-0e6b9866b7e6', 'ba75a43ad8cbe74ec036f3d9f3a5bc0da9c7f4a69b33f3aaaa4c89fb4d483cdf', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "919d82d5-f6d5-4888-b49b-e2ac96d441dd", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:40.563543+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3d5-7f02-a7fb-76d2c4d8a0e0', '01a11a37-b3d5-782c-a7c3-d48eddf97f88', 'c94f9e78203ef15530f7789d9cf689381d57dbe48a53bc443bbf0b06116fd281', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "374ed69f-3a2f-44f7-8b24-267ac414e034", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:40.563543+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3d5-794c-b791-1ad15f06d957', '01a11a37-b3d4-7d87-a967-750b7da441f6', '78b2fc98e215b9b974efd92216b75fedf5f6b6d97b51334c2afdc8d95ebdf76b', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "a637975f-a844-46fb-a307-d7ae7d97a3fc", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a637975f-a844-46fb-a307-d7ae7d97a3fc", "specialComments": []}', '2026-10-08 06:33:40.563543+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3b2-72e7-bffa-db58a50031c6', '01a11a37-b3b1-7ec7-9ddb-6f67ea6ccc3f', 'feda22a6c319f6b58e812ab98da107b7db7d0028e8390f527af4792431281273', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "b97ad3bc-1991-4454-8a4b-684283f3b175", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b97ad3bc-1991-4454-8a4b-684283f3b175", "specialComments": []}', '2026-10-08 06:33:40.526552+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3f9-734e-936a-c7abca08ed81', '01a11a37-b3f8-74cb-8019-71a5da70bc28', 'e412b6862d7365a6813f3f071c9a69f6fc6aef2daf7b0817889213e0640e8ebe', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "a8d6d019-be96-4451-a351-1eeb2360bb49", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:40.600257+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b3d6-7054-9c69-90be952d721c', '01a11a37-b3d6-7f3b-a891-014efab65671', '1e66df23f6901e4ed8f20751fcd06513447483ecf34039422cb1458d1c1c5d5b', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "d492edfa-fc9e-468f-af9e-63863efeff58", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "d492edfa-fc9e-468f-af9e-63863efeff58", "specialComments": []}', '2026-10-08 06:33:40.563543+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-bbfd-7449-8941-00f4ecde22df', '01a11a37-bbfd-7051-9fe6-560c700551e1', '921ba606eb33407c887973aeb76507c47768ee1102ee5193163daec1032e7da8', 'And the compass?', '{"name": null, "role": "user", "chatId": "e361c9c3-248e-432f-8302-4c8a95b2395e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:42.651098+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-bbfc-733d-aa09-fcebebde0fc4', '01a11a37-bbfc-74cd-bdb7-003bf16506e5', 'eaa872774c53ef8a46941527086963b8f6c49069c3e0f677413a5cbda71e762d', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "3c3589eb-1c39-4d77-9d28-d00f1b12c425", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "3c3589eb-1c39-4d77-9d28-d00f1b12c425", "specialComments": []}', '2026-10-08 06:33:42.651098+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-bbfb-708a-a24a-77cdd41aad8c', '01a11a37-b37c-733a-8994-aa6bd3f8f8dd', '08716415adb3830ecaf492ef87a071ffb0f02e9f309bb6a51a88938352ddd793', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "e2024e47-1167-466c-90a1-04cefd4f5e9b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e2024e47-1167-466c-90a1-04cefd4f5e9b", "specialComments": []}', '2026-10-08 06:33:42.651098+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-b37c-7434-85b8-adc2891e44f1', '01a11a37-b37c-733a-8994-aa6bd3f8f8dd', '60b03a98c3edc8e1e7386837ba18af0e442eb24baf5e64d23ddbdd1077e6b63b', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "e2024e47-1167-466c-90a1-04cefd4f5e9b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e2024e47-1167-466c-90a1-04cefd4f5e9b", "specialComments": []}', '2026-10-08 06:33:40.471501+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-bc42-7e22-ac40-318161f2ed68', '01a11a37-b3d4-77c8-97f6-0e6b9866b7e6', 'b8469f3076dbca036a833ce64c7a309f38ba7760a370583c5ae1b690d140cab4', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "919d82d5-f6d5-4888-b49b-e2ac96d441dd", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:42.721919+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-bc44-76f6-a5cc-7fe408a53a02', '01a11a37-bc43-7229-917e-1083eb78f0a9', 'ede9033ffa403b50d19b9320cd94563e10670d4717b05385138a1b728b7b9035', 'Let''s go.', '{"name": null, "role": "user", "chatId": "5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:42.721919+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-bc1b-7537-bf81-fb6321665260', '01a11a37-bc1b-77a5-8c3f-92d9da8b7134', '54849297958b13ce509684f084d573f434a122f68f338cd93de2d08f5e1c2309', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "ac0a057c-74b6-43ed-8fb8-afa805fa027f", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "ac0a057c-74b6-43ed-8fb8-afa805fa027f", "specialComments": []}', '2026-10-08 06:33:42.682781+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-bc43-737d-a74e-b2becf57c606', '01a11a37-bc1b-77a5-8c3f-92d9da8b7134', 'fe6f019185169b470073eddfca146beb5b2512ac5b9a80ba225c70c2c06a0f13', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "ac0a057c-74b6-43ed-8fb8-afa805fa027f", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "ac0a057c-74b6-43ed-8fb8-afa805fa027f", "specialComments": []}', '2026-10-08 06:33:42.721919+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-c059-7470-926c-e3ed7b746136', '01a11a37-c058-7eb8-a744-555ff36c890f', '594aba0ea21c7a75357587423d4b6581d8768e5eeb956dfc4b355f51b26af7fb', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "c776a045-da0c-4eea-b8ea-8cde9e513eb8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:43.768368+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-c05a-7d8b-aa4b-4e3ad90e0386', '01a11a37-c05a-7fcc-9d35-f1be552708fc', '37cbb59a5a9eb96360693f29d4637857c012db6fe171cedc98b574c9878f7326', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "8025b532-342f-4336-994b-6943f1b4aeab", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:43.768368+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-c05b-7c59-9763-75bb9c83b91d', '01a11a37-c05b-7a4e-9c37-d186857a2944', '99dbd67897062fac92e339128210a0bffff6d548a0bd40efc439a18b62668e9c', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "61e32194-8120-4db7-af10-e320c6bbb844", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:43.768368+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-c05c-7822-b26d-51036175b04b', '01a11a37-c05c-76f4-be94-86960589b470', '56e757f3371818ec7b95a7cbe2f312935eabbbe715f9e9100a58c5451cdfea5f', '{{specialcomment::branchedfrom::125f228f-e94b-461c-b4bc-8afbf99a362d::Harbor route::db5334ea-f745-46c3-9318-267d04f87922::}}', '{"name": null, "role": "char", "chatId": "67893689-6eac-48f2-a7cd-f2920092d287", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::125f228f-e94b-461c-b4bc-8afbf99a362d::Harbor route::db5334ea-f745-46c3-9318-267d04f87922::}}"]}', '2026-10-08 06:33:43.768368+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-c05d-7b54-b4c8-bd94906e3b4c', '01a11a37-c05d-7040-8fa3-66d3b8876d8a', 'c187d58dd21ea841fd54afce502d454de82bf81413491e8387beea658305692d', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "5faae7a5-e3fa-44c7-9430-972837c5c973", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-08 06:33:43.768368+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-c05b-73be-bb0d-034a4c9dc3ae', '01a11a37-c05a-7762-8c6e-0ce9a4cdd7a4', '899323210bf98a82a43ab61dc00745687dcd97aa524be1809e1def01b2b14953', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "0137f8df-0fb6-4424-829e-d09188013daa", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e2024e47-1167-466c-90a1-04cefd4f5e9b", "specialComments": []}', '2026-10-08 06:33:43.768368+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-c05c-79b4-884f-fd200ba0de29', '01a11a37-c05c-7e34-bea6-e068f0286366', 'e0993d8dfeb3a334a82fdbcb8e92ca605269d5a2993c8d91212e36ba0f29643c', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "0745cc01-46ab-4db0-b7fc-59e76470f2f2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "db5334ea-f745-46c3-9318-267d04f87922", "specialComments": []}', '2026-10-08 06:33:43.768368+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a11a37-c059-73cc-8bec-28e751dcaba7', '01a11a37-c059-799f-bd6a-87d32b80e60b', '84ddc403e957de7bd514c4e8af44e332b605a474ec2f47bd70127c95260d81c3', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "83ae9fdf-749c-45a9-a92a-66f672eccd1e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b9a40939-eb41-4218-9960-92453a451c7d", "specialComments": []}', '2026-10-08 06:33:43.768368+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: summary; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a11a37-b37f-7ef3-ade5-80ef92d0285d', '[{"op": "insert", "after": ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "60b03a98c3edc8e1e7386837ba18af0e442eb24baf5e64d23ddbdd1077e6b63b"], "member": ["4a23ebc8-b225-4788-9d4b-d5b68e73cc7f", "48bf4f0ad182ba0ee0e6c42f2783ac65f86760fc5ba42488192417ecc3458d34"]}, {"op": "insert", "after": ["4a23ebc8-b225-4788-9d4b-d5b68e73cc7f", "48bf4f0ad182ba0ee0e6c42f2783ac65f86760fc5ba42488192417ecc3458d34"], "member": ["db5334ea-f745-46c3-9318-267d04f87922", "1e702ba51bab01f6444cb540c7f0eafe833f93eb5468e5ca5c271ec89a6dcfdb"]}, {"op": "insert", "after": ["db5334ea-f745-46c3-9318-267d04f87922", "1e702ba51bab01f6444cb540c7f0eafe833f93eb5468e5ca5c271ec89a6dcfdb"], "member": ["bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd", "d2d64ec42ab33b6ccac3c3f512a2565c50a57838652e990cc7db7fa42039f496"]}, {"op": "insert", "after": ["bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd", "d2d64ec42ab33b6ccac3c3f512a2565c50a57838652e990cc7db7fa42039f496"], "member": ["b97ad3bc-1991-4454-8a4b-684283f3b175", "feda22a6c319f6b58e812ab98da107b7db7d0028e8390f527af4792431281273"]}]', '[{"new": ["4a23ebc8-b225-4788-9d4b-d5b68e73cc7f", "48bf4f0ad182ba0ee0e6c42f2783ac65f86760fc5ba42488192417ecc3458d34"], "old": null, "kind": "append", "position": 4, "host_logical_id": "4a23ebc8-b225-4788-9d4b-d5b68e73cc7f"}, {"new": ["db5334ea-f745-46c3-9318-267d04f87922", "1e702ba51bab01f6444cb540c7f0eafe833f93eb5468e5ca5c271ec89a6dcfdb"], "old": null, "kind": "append", "position": 5, "host_logical_id": "db5334ea-f745-46c3-9318-267d04f87922"}, {"new": ["bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd", "d2d64ec42ab33b6ccac3c3f512a2565c50a57838652e990cc7db7fa42039f496"], "old": null, "kind": "append", "position": 6, "host_logical_id": "bb88c3d2-ba99-4ea2-b101-5fdda68f7dcd"}, {"new": ["b97ad3bc-1991-4454-8a4b-684283f3b175", "feda22a6c319f6b58e812ab98da107b7db7d0028e8390f527af4792431281273"], "old": null, "kind": "append", "position": 7, "host_logical_id": "b97ad3bc-1991-4454-8a4b-684283f3b175"}]', '01a11a37-b3b4-736b-902b-c94e6605e653', '2026-10-08 06:33:40.526552+00');
INSERT INTO public.worldline_append VALUES (2, '01a11a37-b37f-7ef3-ade5-80ef92d0285d', '[{"op": "insert", "after": ["b97ad3bc-1991-4454-8a4b-684283f3b175", "feda22a6c319f6b58e812ab98da107b7db7d0028e8390f527af4792431281273"], "member": ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "ba75a43ad8cbe74ec036f3d9f3a5bc0da9c7f4a69b33f3aaaa4c89fb4d483cdf"]}, {"op": "insert", "after": ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "ba75a43ad8cbe74ec036f3d9f3a5bc0da9c7f4a69b33f3aaaa4c89fb4d483cdf"], "member": ["a637975f-a844-46fb-a307-d7ae7d97a3fc", "78b2fc98e215b9b974efd92216b75fedf5f6b6d97b51334c2afdc8d95ebdf76b"]}, {"op": "insert", "after": ["a637975f-a844-46fb-a307-d7ae7d97a3fc", "78b2fc98e215b9b974efd92216b75fedf5f6b6d97b51334c2afdc8d95ebdf76b"], "member": ["374ed69f-3a2f-44f7-8b24-267ac414e034", "c94f9e78203ef15530f7789d9cf689381d57dbe48a53bc443bbf0b06116fd281"]}, {"op": "insert", "after": ["374ed69f-3a2f-44f7-8b24-267ac414e034", "c94f9e78203ef15530f7789d9cf689381d57dbe48a53bc443bbf0b06116fd281"], "member": ["d492edfa-fc9e-468f-af9e-63863efeff58", "1e66df23f6901e4ed8f20751fcd06513447483ecf34039422cb1458d1c1c5d5b"]}]', '[{"new": ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "ba75a43ad8cbe74ec036f3d9f3a5bc0da9c7f4a69b33f3aaaa4c89fb4d483cdf"], "old": null, "kind": "append", "position": 8, "host_logical_id": "919d82d5-f6d5-4888-b49b-e2ac96d441dd"}, {"new": ["a637975f-a844-46fb-a307-d7ae7d97a3fc", "78b2fc98e215b9b974efd92216b75fedf5f6b6d97b51334c2afdc8d95ebdf76b"], "old": null, "kind": "append", "position": 9, "host_logical_id": "a637975f-a844-46fb-a307-d7ae7d97a3fc"}, {"new": ["374ed69f-3a2f-44f7-8b24-267ac414e034", "c94f9e78203ef15530f7789d9cf689381d57dbe48a53bc443bbf0b06116fd281"], "old": null, "kind": "append", "position": 10, "host_logical_id": "374ed69f-3a2f-44f7-8b24-267ac414e034"}, {"new": ["d492edfa-fc9e-468f-af9e-63863efeff58", "1e66df23f6901e4ed8f20751fcd06513447483ecf34039422cb1458d1c1c5d5b"], "old": null, "kind": "append", "position": 11, "host_logical_id": "d492edfa-fc9e-468f-af9e-63863efeff58"}]', '01a11a37-b3d9-7664-833e-8659f3ca49b0', '2026-10-08 06:33:40.563543+00');
INSERT INTO public.worldline_append VALUES (3, '01a11a37-b37f-7ef3-ade5-80ef92d0285d', '[{"op": "insert", "after": ["d492edfa-fc9e-468f-af9e-63863efeff58", "1e66df23f6901e4ed8f20751fcd06513447483ecf34039422cb1458d1c1c5d5b"], "member": ["a8d6d019-be96-4451-a351-1eeb2360bb49", "e412b6862d7365a6813f3f071c9a69f6fc6aef2daf7b0817889213e0640e8ebe"]}]', '[{"new": ["a8d6d019-be96-4451-a351-1eeb2360bb49", "e412b6862d7365a6813f3f071c9a69f6fc6aef2daf7b0817889213e0640e8ebe"], "old": null, "kind": "append", "position": 12, "host_logical_id": "a8d6d019-be96-4451-a351-1eeb2360bb49"}]', '01a11a37-b3fb-7c73-982b-c8b85dc15cec', '2026-10-08 06:33:40.600257+00');
INSERT INTO public.worldline_append VALUES (4, '01a11a37-bc00-7ca3-96e9-0a3b500bdc9e', '[{"op": "insert", "after": ["e361c9c3-248e-432f-8302-4c8a95b2395e", "921ba606eb33407c887973aeb76507c47768ee1102ee5193163daec1032e7da8"], "member": ["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "54849297958b13ce509684f084d573f434a122f68f338cd93de2d08f5e1c2309"]}]', '[{"new": ["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "54849297958b13ce509684f084d573f434a122f68f338cd93de2d08f5e1c2309"], "old": null, "kind": "append", "position": 15, "host_logical_id": "ac0a057c-74b6-43ed-8fb8-afa805fa027f"}]', '01a11a37-bc1e-7d56-8269-3bcaddd7322b', '2026-10-08 06:33:42.682781+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a11a37-b37f-7ef3-ade5-80ef92d0285d', 1, '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{}', 'import', '50ed30cae3d7585b207d9f3ace469667dad795b158164ca9ed3ce520a62f1d40', '{"ops": [{"op": "set", "members": [["9adf2606-d06d-48c0-8ab2-b41f320f0909", "e36f9551c56076721f946cd2535335975c4f9830473665373689cb0e45834da1"], ["b9a40939-eb41-4218-9960-92453a451c7d", "ff551dffe0c80900759b58c1106a2181c91f0cf63d3d95a85617643c02b2466b"], ["8ed2da0c-b165-42bd-8a83-094fda9b646c", "a8499762ff56b19c333ee7e65a45bf1874145c77564cdb5ed035d5cf3f97c4da"], ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "60b03a98c3edc8e1e7386837ba18af0e442eb24baf5e64d23ddbdd1077e6b63b"]]}], "changes": [{"new": ["9adf2606-d06d-48c0-8ab2-b41f320f0909", "e36f9551c56076721f946cd2535335975c4f9830473665373689cb0e45834da1"], "old": null, "kind": "append", "position": 0, "host_logical_id": "9adf2606-d06d-48c0-8ab2-b41f320f0909"}, {"new": ["b9a40939-eb41-4218-9960-92453a451c7d", "ff551dffe0c80900759b58c1106a2181c91f0cf63d3d95a85617643c02b2466b"], "old": null, "kind": "append", "position": 1, "host_logical_id": "b9a40939-eb41-4218-9960-92453a451c7d"}, {"new": ["8ed2da0c-b165-42bd-8a83-094fda9b646c", "a8499762ff56b19c333ee7e65a45bf1874145c77564cdb5ed035d5cf3f97c4da"], "old": null, "kind": "append", "position": 2, "host_logical_id": "8ed2da0c-b165-42bd-8a83-094fda9b646c"}, {"new": ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "60b03a98c3edc8e1e7386837ba18af0e442eb24baf5e64d23ddbdd1077e6b63b"], "old": null, "kind": "append", "position": 3, "host_logical_id": "e2024e47-1167-466c-90a1-04cefd4f5e9b"}]}', '2026-10-08 06:33:40.471501+00', '01a11a37-b37d-788b-b326-cef914cc126f');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a11a37-bc00-7ca3-96e9-0a3b500bdc9e', 2, '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{01a11a37-b37f-7ef3-ade5-80ef92d0285d}', 'edit', '44b99609497fa1f1cd7257d068b7f7516bd92fce1a97b8238c8f515a9834826c', '{"ops": [{"op": "replace", "to": ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "08716415adb3830ecaf492ef87a071ffb0f02e9f309bb6a51a88938352ddd793"], "from": ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "60b03a98c3edc8e1e7386837ba18af0e442eb24baf5e64d23ddbdd1077e6b63b"]}, {"op": "insert", "after": ["a8d6d019-be96-4451-a351-1eeb2360bb49", "e412b6862d7365a6813f3f071c9a69f6fc6aef2daf7b0817889213e0640e8ebe"], "member": ["3c3589eb-1c39-4d77-9d28-d00f1b12c425", "eaa872774c53ef8a46941527086963b8f6c49069c3e0f677413a5cbda71e762d"]}, {"op": "insert", "after": ["3c3589eb-1c39-4d77-9d28-d00f1b12c425", "eaa872774c53ef8a46941527086963b8f6c49069c3e0f677413a5cbda71e762d"], "member": ["e361c9c3-248e-432f-8302-4c8a95b2395e", "921ba606eb33407c887973aeb76507c47768ee1102ee5193163daec1032e7da8"]}], "changes": [{"new": ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "08716415adb3830ecaf492ef87a071ffb0f02e9f309bb6a51a88938352ddd793"], "old": ["e2024e47-1167-466c-90a1-04cefd4f5e9b", "60b03a98c3edc8e1e7386837ba18af0e442eb24baf5e64d23ddbdd1077e6b63b"], "kind": "edit", "position": 3, "host_logical_id": "e2024e47-1167-466c-90a1-04cefd4f5e9b"}, {"new": ["3c3589eb-1c39-4d77-9d28-d00f1b12c425", "eaa872774c53ef8a46941527086963b8f6c49069c3e0f677413a5cbda71e762d"], "old": null, "kind": "append", "position": 13, "host_logical_id": "3c3589eb-1c39-4d77-9d28-d00f1b12c425"}, {"new": ["e361c9c3-248e-432f-8302-4c8a95b2395e", "921ba606eb33407c887973aeb76507c47768ee1102ee5193163daec1032e7da8"], "old": null, "kind": "append", "position": 14, "host_logical_id": "e361c9c3-248e-432f-8302-4c8a95b2395e"}]}', '2026-10-08 06:33:42.651098+00', '01a11a37-bbff-7cf8-ad81-e767313dec51');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a11a37-bc47-7e9a-88f2-df2aad69d69d', 3, '01a11a37-b369-7efd-bdb2-869680e8a3a0', '{01a11a37-bc00-7ca3-96e9-0a3b500bdc9e}', 'reconciliation', 'df7c77451a32d1eb71fdd994e78323d1e029c4013736f85071b62cf5b5282c39', '{"ops": [{"op": "replace", "to": ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "b8469f3076dbca036a833ce64c7a309f38ba7760a370583c5ae1b690d140cab4"], "from": ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "ba75a43ad8cbe74ec036f3d9f3a5bc0da9c7f4a69b33f3aaaa4c89fb4d483cdf"]}, {"op": "replace", "to": ["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "fe6f019185169b470073eddfca146beb5b2512ac5b9a80ba225c70c2c06a0f13"], "from": ["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "54849297958b13ce509684f084d573f434a122f68f338cd93de2d08f5e1c2309"]}, {"op": "insert", "after": ["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "fe6f019185169b470073eddfca146beb5b2512ac5b9a80ba225c70c2c06a0f13"], "member": ["5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e", "ede9033ffa403b50d19b9320cd94563e10670d4717b05385138a1b728b7b9035"]}], "changes": [{"new": ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "b8469f3076dbca036a833ce64c7a309f38ba7760a370583c5ae1b690d140cab4"], "old": ["919d82d5-f6d5-4888-b49b-e2ac96d441dd", "ba75a43ad8cbe74ec036f3d9f3a5bc0da9c7f4a69b33f3aaaa4c89fb4d483cdf"], "kind": "disable", "position": 8, "host_logical_id": "919d82d5-f6d5-4888-b49b-e2ac96d441dd"}, {"new": ["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "fe6f019185169b470073eddfca146beb5b2512ac5b9a80ba225c70c2c06a0f13"], "old": ["ac0a057c-74b6-43ed-8fb8-afa805fa027f", "54849297958b13ce509684f084d573f434a122f68f338cd93de2d08f5e1c2309"], "kind": "swipe", "position": 15, "host_logical_id": "ac0a057c-74b6-43ed-8fb8-afa805fa027f"}, {"new": ["5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e", "ede9033ffa403b50d19b9320cd94563e10670d4717b05385138a1b728b7b9035"], "old": null, "kind": "append", "position": 16, "host_logical_id": "5646b8bb-fa36-46ff-a5a9-aa0fd56cc48e"}]}', '2026-10-08 06:33:42.721919+00', '01a11a37-bc46-721f-b5b7-3dba9c81dee8');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a11a37-c05f-71d5-8501-baeab8feb19c', 4, '01a11a37-c04b-7aa7-9b86-637259a6907a', '{}', 'branch', '875611173088fc81683291e7e9b35077ea922279f156267484011a26e4c8d921', '{"ops": [{"op": "set", "members": [["c776a045-da0c-4eea-b8ea-8cde9e513eb8", "594aba0ea21c7a75357587423d4b6581d8768e5eeb956dfc4b355f51b26af7fb"], ["83ae9fdf-749c-45a9-a92a-66f672eccd1e", "84ddc403e957de7bd514c4e8af44e332b605a474ec2f47bd70127c95260d81c3"], ["8025b532-342f-4336-994b-6943f1b4aeab", "37cbb59a5a9eb96360693f29d4637857c012db6fe171cedc98b574c9878f7326"], ["0137f8df-0fb6-4424-829e-d09188013daa", "899323210bf98a82a43ab61dc00745687dcd97aa524be1809e1def01b2b14953"], ["61e32194-8120-4db7-af10-e320c6bbb844", "99dbd67897062fac92e339128210a0bffff6d548a0bd40efc439a18b62668e9c"], ["0745cc01-46ab-4db0-b7fc-59e76470f2f2", "e0993d8dfeb3a334a82fdbcb8e92ca605269d5a2993c8d91212e36ba0f29643c"], ["67893689-6eac-48f2-a7cd-f2920092d287", "56e757f3371818ec7b95a7cbe2f312935eabbbe715f9e9100a58c5451cdfea5f"], ["5faae7a5-e3fa-44c7-9430-972837c5c973", "c187d58dd21ea841fd54afce502d454de82bf81413491e8387beea658305692d"]]}], "changes": [{"new": ["c776a045-da0c-4eea-b8ea-8cde9e513eb8", "594aba0ea21c7a75357587423d4b6581d8768e5eeb956dfc4b355f51b26af7fb"], "old": null, "kind": "append", "position": 0, "host_logical_id": "c776a045-da0c-4eea-b8ea-8cde9e513eb8"}, {"new": ["83ae9fdf-749c-45a9-a92a-66f672eccd1e", "84ddc403e957de7bd514c4e8af44e332b605a474ec2f47bd70127c95260d81c3"], "old": null, "kind": "append", "position": 1, "host_logical_id": "83ae9fdf-749c-45a9-a92a-66f672eccd1e"}, {"new": ["8025b532-342f-4336-994b-6943f1b4aeab", "37cbb59a5a9eb96360693f29d4637857c012db6fe171cedc98b574c9878f7326"], "old": null, "kind": "append", "position": 2, "host_logical_id": "8025b532-342f-4336-994b-6943f1b4aeab"}, {"new": ["0137f8df-0fb6-4424-829e-d09188013daa", "899323210bf98a82a43ab61dc00745687dcd97aa524be1809e1def01b2b14953"], "old": null, "kind": "append", "position": 3, "host_logical_id": "0137f8df-0fb6-4424-829e-d09188013daa"}, {"new": ["61e32194-8120-4db7-af10-e320c6bbb844", "99dbd67897062fac92e339128210a0bffff6d548a0bd40efc439a18b62668e9c"], "old": null, "kind": "append", "position": 4, "host_logical_id": "61e32194-8120-4db7-af10-e320c6bbb844"}, {"new": ["0745cc01-46ab-4db0-b7fc-59e76470f2f2", "e0993d8dfeb3a334a82fdbcb8e92ca605269d5a2993c8d91212e36ba0f29643c"], "old": null, "kind": "append", "position": 5, "host_logical_id": "0745cc01-46ab-4db0-b7fc-59e76470f2f2"}, {"new": ["67893689-6eac-48f2-a7cd-f2920092d287", "56e757f3371818ec7b95a7cbe2f312935eabbbe715f9e9100a58c5451cdfea5f"], "old": null, "kind": "append", "position": 6, "host_logical_id": "67893689-6eac-48f2-a7cd-f2920092d287"}, {"new": ["5faae7a5-e3fa-44c7-9430-972837c5c973", "c187d58dd21ea841fd54afce502d454de82bf81413491e8387beea658305692d"], "old": null, "kind": "append", "position": 7, "host_logical_id": "5faae7a5-e3fa-44c7-9430-972837c5c973"}]}', '2026-10-08 06:33:43.768368+00', '01a11a37-c05e-7747-8b42-2cd2bb037e2d');


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


