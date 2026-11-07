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

INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 0, '01a1b503-5a38-77ec-8162-15882f38fe84', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 1, '01a1b503-5a3a-7f10-a68c-6bcfaa588817', NULL, 0, '2f335d09dcaacbcf02ec8e89f317e045');
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 2, '01a1b503-5a3b-7495-99a7-605ad39cf6ff', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 3, '01a1b503-62e5-70f0-9059-639da7836d39', NULL, 1, '4f24c11842d8548d6c1aaca217673205');
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 4, '01a1b503-5a86-7ba5-a8a6-c40fe3f4215f', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 5, '01a1b503-5a88-7590-bd48-0a5829f8be50', NULL, 2, '1b486d90698139d55cf93df2de95aaf3');
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 6, '01a1b503-5a89-7b86-a6c2-5a6c3573e7a9', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 7, '01a1b503-5a8a-71df-ab4b-338ad64371a0', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 8, '01a1b503-632e-71d7-b838-3548a004dfa5', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 9, '01a1b503-5ab4-7655-b423-5dc052054436', NULL, 3, '8b63bffe2b4762e1506061c48dd28ce8');
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 10, '01a1b503-5ab5-749f-b0fc-965a248e61f8', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 11, '01a1b503-5ab6-7513-bc12-4f96b7689363', NULL, 4, '9c6b9541d63d543f57327d77018cfa5d');
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 12, '01a1b503-5adb-73bf-baff-30c66e290592', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 13, '01a1b503-62e6-7719-9da9-289c6668aa35', NULL, 5, '8c8c60409c41e6a67d765de394b42805');
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 14, '01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 15, '01a1b503-632f-7fc8-b29a-22d2b22c7074', NULL, 6, '4a40d7e73001910ec22c621a74e87de1');
INSERT INTO public.active_membership VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 16, '01a1b503-632f-7255-a524-b3b4453890f9', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 0, '01a1b503-6748-78ff-8ced-e4552c25c878', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 1, '01a1b503-6749-77c5-b971-23e10117bbe7', NULL, 0, '2debec0bb3c3ec2fbd15817a7c25c99c');
INSERT INTO public.active_membership VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 2, '01a1b503-674a-77ef-87a7-01dd0bfc32ea', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 3, '01a1b503-674b-76c1-9e42-b0fe12a99c0b', NULL, 1, 'dfbda48b7fe7476ad6781ff374cfe906');
INSERT INTO public.active_membership VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 4, '01a1b503-6751-7f95-a588-4d829ef73cc7', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 5, '01a1b503-6753-741e-b987-e504cab053b5', NULL, 2, '320cf026f4df0d55f9fb9c9fc6348173');
INSERT INTO public.active_membership VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 6, '01a1b503-6754-7cab-8462-4bfed95733cb', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 7, '01a1b503-6754-7d15-8e9d-b2e32482c8d4', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a1b503-6104-7d91-b59e-6fae1b47fc8a', '01a1b503-5a3a-7f10-a68c-6bcfaa588817', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a1b503-6104-7d91-b59e-6fae1b47fc8a', '01a1b503-5a3a-7f10-a68c-6bcfaa588817', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a1b503-6119-7861-ba94-30580137c15a', '01a1b503-5a3c-7db8-bc44-d742c1edd6a6', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a1b503-6119-7861-ba94-30580137c15a', '01a1b503-5a3c-7db8-bc44-d742c1edd6a6', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a1b503-612a-7c55-81b2-8a2751df1c5c', '01a1b503-5a88-7590-bd48-0a5829f8be50', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a1b503-614e-7337-b8b2-bf5001233bd4', '01a1b503-5ab4-7655-b423-5dc052054436', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a1b503-6162-74bf-9b91-b6435f259200', '01a1b503-5ab6-7513-bc12-4f96b7689363', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a1b503-659f-7c21-9613-a71e8bdf44e2', '01a1b503-632f-7fc8-b29a-22d2b22c7074', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a1b503-65c0-7153-94da-e8cadfccdc97', '01a1b503-5ab6-7513-bc12-4f96b7689363', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a1b503-65d1-7afd-aeb4-d2514d1ce54f', '01a1b503-5ab4-7655-b423-5dc052054436', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a1b503-65ea-70de-a693-205552a8e6f4', '01a1b503-5a88-7590-bd48-0a5829f8be50', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a1b503-65fc-7924-9b56-0937a3265242', '01a1b503-62e5-70f0-9059-639da7836d39', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a1b503-65fc-7924-9b56-0937a3265242', '01a1b503-62e5-70f0-9059-639da7836d39', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a1b503-6a44-7a32-b543-f9c852a907d9', '01a1b503-6749-77c5-b971-23e10117bbe7', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a1b503-6a44-7a32-b543-f9c852a907d9', '01a1b503-6749-77c5-b971-23e10117bbe7', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a1b503-6a54-7a65-a7e4-1f88854162b1', '01a1b503-674b-76c1-9e42-b0fe12a99c0b', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a1b503-6a54-7a65-a7e4-1f88854162b1', '01a1b503-674b-76c1-9e42-b0fe12a99c0b', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a1b503-6a63-788a-9815-764c60f83a41', '01a1b503-6753-741e-b987-e504cab053b5', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: canon_applied; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: canon_manifest; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a1b503-5a30-72cb-9fa1-2afca8014f95', 'pocketrisu', NULL, '98405043-f67e-457a-89e2-f2af77e95f73', '2026-11-07 07:57:38.224233+00', NULL, NULL, NULL, '01a1b503-6333-7a9b-92c4-069cd38d61ac', '4982d9a6a4fc353f3ebb5b98808c56080987645d80e85d2241504f4db611152a', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL, false);
INSERT INTO public.conversation VALUES ('01a1b503-673b-74ee-9196-ed4ad8d4b49f', 'pocketrisu', NULL, '65045fb6-a788-4d69-8d94-a465c77dc180', '2026-11-07 07:57:41.563143+00', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '98405043-f67e-457a-89e2-f2af77e95f73', 'c30ed147-7dd3-488b-bf9e-3791d614131e', '01a1b503-6756-7f28-9160-637f47941c22', '8636056fd57ccf27c01355270cb77626fad0ffa33436bfc9c76e224a0997477d', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL, false);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a1b503-6104-7d91-b59e-6fae1b47fc8a', '01a1b503-5a3a-7f10-a68c-6bcfaa588817', '2f335d09dcaacbcf02ec8e89f317e045', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:39.972567+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a1b503-5a38-77ec-8162-15882f38fe84,01a1b503-5a3a-7f10-a68c-6bcfaa588817}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-6119-7861-ba94-30580137c15a', '01a1b503-5a3c-7db8-bc44-d742c1edd6a6', '17b54f5779a8c0669b09af1f89cfb912', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:39.992781+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a1b503-5a3b-7495-99a7-605ad39cf6ff,01a1b503-5a3c-7db8-bc44-d742c1edd6a6}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-612a-7c55-81b2-8a2751df1c5c', '01a1b503-5a88-7590-bd48-0a5829f8be50', '2ae2831913352d4cf5fc99e35967861b', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:40.010421+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a1b503-5a86-7ba5-a8a6-c40fe3f4215f,01a1b503-5a88-7590-bd48-0a5829f8be50}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-613b-793d-b78d-d9c4f76502d7', '01a1b503-5a8a-71df-ab4b-338ad64371a0', '447f339c2164b052a9d164f18ec1a8ae', 'extract-v16', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-11-07 07:57:40.027318+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a1b503-5a89-7b86-a6c2-5a6c3573e7a9,01a1b503-5a8a-71df-ab4b-338ad64371a0}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-614e-7337-b8b2-bf5001233bd4', '01a1b503-5ab4-7655-b423-5dc052054436', 'a2d6d9bdaa469ab8de7dc10038002466', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:40.046012+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a1b503-5ab3-7136-9826-415cda22b3ca,01a1b503-5ab4-7655-b423-5dc052054436}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 8, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-6162-74bf-9b91-b6435f259200', '01a1b503-5ab6-7513-bc12-4f96b7689363', '7c4dba26c661acc5a6951658d010f90b', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:40.066111+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a1b503-5ab5-749f-b0fc-965a248e61f8,01a1b503-5ab6-7513-bc12-4f96b7689363}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "silver compass", "type": "item"}, {"name": "Rin", "type": "character"}, {"name": "Mina", "type": "character"}, {"name": "harbor", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": [{"by": "Mina", "to": "Takumi", "text": "return before the bell rings", "turn": 2}]}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-659f-7c21-9613-a71e8bdf44e2', '01a1b503-632f-7fc8-b29a-22d2b22c7074', '4a40d7e73001910ec22c621a74e87de1', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:41.151577+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7,01a1b503-632f-7fc8-b29a-22d2b22c7074}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-65ae-7f54-a45e-7060cad8cfec', '01a1b503-62e6-7719-9da9-289c6668aa35', '8c8c60409c41e6a67d765de394b42805', 'extract-v16', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-11-07 07:57:41.166618+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a1b503-5adb-73bf-baff-30c66e290592,01a1b503-62e6-7719-9da9-289c6668aa35}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-65c0-7153-94da-e8cadfccdc97', '01a1b503-5ab6-7513-bc12-4f96b7689363', '9c6b9541d63d543f57327d77018cfa5d', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:41.18369+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a1b503-5ab5-749f-b0fc-965a248e61f8,01a1b503-5ab6-7513-bc12-4f96b7689363}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-65d1-7afd-aeb4-d2514d1ce54f', '01a1b503-5ab4-7655-b423-5dc052054436', '8b63bffe2b4762e1506061c48dd28ce8', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:41.200954+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a1b503-5a89-7b86-a6c2-5a6c3573e7a9,01a1b503-5a8a-71df-ab4b-338ad64371a0,01a1b503-5ab4-7655-b423-5dc052054436}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-65ea-70de-a693-205552a8e6f4', '01a1b503-5a88-7590-bd48-0a5829f8be50', '1b486d90698139d55cf93df2de95aaf3', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:41.226396+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a1b503-5a86-7ba5-a8a6-c40fe3f4215f,01a1b503-5a88-7590-bd48-0a5829f8be50}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-65fc-7924-9b56-0937a3265242', '01a1b503-62e5-70f0-9059-639da7836d39', '4f24c11842d8548d6c1aaca217673205', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:41.244115+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a1b503-5a3b-7495-99a7-605ad39cf6ff,01a1b503-62e5-70f0-9059-639da7836d39}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 6, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-6a44-7a32-b543-f9c852a907d9', '01a1b503-6749-77c5-b971-23e10117bbe7', '2debec0bb3c3ec2fbd15817a7c25c99c', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:42.340305+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a1b503-6748-78ff-8ced-e4552c25c878,01a1b503-6749-77c5-b971-23e10117bbe7}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}', '{"ms": 5, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-6a54-7a65-a7e4-1f88854162b1', '01a1b503-674b-76c1-9e42-b0fe12a99c0b', 'dfbda48b7fe7476ad6781ff374cfe906', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:42.356196+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a1b503-674a-77ef-87a7-01dd0bfc32ea,01a1b503-674b-76c1-9e42-b0fe12a99c0b}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 7, "calls": 1}', NULL);
INSERT INTO public.extraction VALUES ('01a1b503-6a63-788a-9815-764c60f83a41', '01a1b503-6753-741e-b987-e504cab053b5', '320cf026f4df0d55f9fb9c9fc6348173', 'extract-v16', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-11-07 07:57:42.370999+00', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a1b503-6751-7f95-a588-4d829ef73cc7,01a1b503-6753-741e-b987-e504cab053b5}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "Mina", "type": "character"}, {"name": "Rin", "type": "character"}, {"name": "lighthouse", "type": "place"}, {"name": "brass key", "type": "item"}, {"name": "old chapel", "type": "place"}], "promises": []}', '{"ms": 5, "calls": 1}', NULL);


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a1b503-5a3d-7154-8287-0d5972d7c509', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'manifest', '71798870fa9f256181e078fcfb6538cda23e9a63f885fdf5f4256403c43a2be1', '01a1b503-5a30-72cb-9fa1-2afca8014f95:71798870fa9f256181e078fcfb6538cda23e9a63f885fdf5f4256403c43a2be1:manifest', '2026-11-07 07:57:38.23094+00', '{"chat_id": "98405043-f67e-457a-89e2-f2af77e95f73", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["70cd448a-58da-4fea-8704-2391be23f338", "65f847d9f7017d97e6d1cb92f04cb050257988a6ef9b03b347ebeb5633a5aeb2", "user", null, null, null, 0, null, null], ["6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "3e9774abad2195b81a7fed51fad8234ed4a7b850107f7caca7edad217e0bff1a", "char", null, null, null, 0, "6d7ee8d3-4979-49a3-8617-5d7b6a93e670", null], ["c95b397e-473b-46a2-b2ea-6b97401b9c5e", "638cb8257d8b7271fd1435932a97af74f1e23d4b479b90238387ff1cc1fc7b3a", "user", null, null, null, 0, null, null], ["b3da5d55-e823-4892-8104-c1423e7442a4", "cfe1e656056acb7b028b6f6a0b1bac65a5473408c6262df04b848f53be865956", "char", null, null, null, 0, "b3da5d55-e823-4892-8104-c1423e7442a4", null]]}');
INSERT INTO public.host_observation VALUES ('01a1b503-5a8d-702f-87d7-4077449e498e', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'manifest', '7d9a628c0e45317737cd579e9fdd284750d92b3e13817ab610e1c1f6796d3697', '01a1b503-5a30-72cb-9fa1-2afca8014f95:7d9a628c0e45317737cd579e9fdd284750d92b3e13817ab610e1c1f6796d3697:manifest', '2026-11-07 07:57:38.309858+00', '{"chat_id": "98405043-f67e-457a-89e2-f2af77e95f73", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["f06fa6c1-f1f1-4193-bd75-78001bee73f3", "c7ca04a0b2da85805cad7f4fdd25d7520efd94c9e9d53d2745fe20b083c544fb", "user", null, null, null, 0, null, null], ["c30ed147-7dd3-488b-bf9e-3791d614131e", "db497aa6518625416281e1fd845ca7b5c396a91be5b3b17e378845933a58e341", "char", null, null, null, 0, "c30ed147-7dd3-488b-bf9e-3791d614131e", null], ["996bd6eb-d0e6-446a-9b4b-83703cd77dde", "19653fd2cc47be59352f7f37395cb55cf0cd03016846120ab76ffcd478632c53", "user", null, null, null, 0, null, null], ["a2cbea71-1ec5-4040-9d3b-cca020053637", "4bc10a063e87042cdb8f1dd78bd175d49c3371991e3c008c2456d4e1b317cad8", "char", null, null, null, 0, "a2cbea71-1ec5-4040-9d3b-cca020053637", null]], "base_manifest_hash": "71798870fa9f256181e078fcfb6538cda23e9a63f885fdf5f4256403c43a2be1"}');
INSERT INTO public.host_observation VALUES ('01a1b503-5ab9-700b-b12c-0d91f212ffa2', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'manifest', '9df6cf9e2153b934d7d1257a03a95fe49f78967bae7769aed70df166c81cbf0b', '01a1b503-5a30-72cb-9fa1-2afca8014f95:9df6cf9e2153b934d7d1257a03a95fe49f78967bae7769aed70df166c81cbf0b:manifest', '2026-11-07 07:57:38.354652+00', '{"chat_id": "98405043-f67e-457a-89e2-f2af77e95f73", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["7fa62829-c1e7-4483-b91d-db55407aa75f", "1d59fa3d6e5e01cfc95291f1b7febd3d93f2ada9f0158c41ac5af938eb4eb23a", "user", null, null, null, 0, null, null], ["fc31de31-a026-4d42-80e1-1fd90dec0422", "28ea885e98c3b3bd20d41c22124ef6b4097ac91ac86dc9503d77ba0075cc335c", "char", null, null, null, 0, "fc31de31-a026-4d42-80e1-1fd90dec0422", null], ["549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "02859d31959e548854aa42b29aeec2238788379bf417482f1f5cdf894056b3a3", "user", null, null, null, 0, null, null], ["882cdb55-4602-48de-acd0-67f63b04119f", "c8351031ff3c625c826c74c7a9d8c50d6c7cee647c011240f12901db0c70d248", "char", null, null, null, 0, "882cdb55-4602-48de-acd0-67f63b04119f", null]], "base_manifest_hash": "7d9a628c0e45317737cd579e9fdd284750d92b3e13817ab610e1c1f6796d3697"}');
INSERT INTO public.host_observation VALUES ('01a1b503-5ae0-72ff-8f24-fdd4585bd128', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'manifest', '78faacde944dd51a9d5ff69cef5ef3b817d95337b7669a9cdca638ebfd5d9633', '01a1b503-5a30-72cb-9fa1-2afca8014f95:78faacde944dd51a9d5ff69cef5ef3b817d95337b7669a9cdca638ebfd5d9633:manifest', '2026-11-07 07:57:38.394074+00', '{"chat_id": "98405043-f67e-457a-89e2-f2af77e95f73", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["40385c3d-40de-4832-92a7-71a158bb74ff", "56834ab93fd8fe041d04d197594830e0dce74b2f6064b50ce1d39d767c1645a1", "user", null, null, null, 0, null, null]], "base_manifest_hash": "9df6cf9e2153b934d7d1257a03a95fe49f78967bae7769aed70df166c81cbf0b"}');
INSERT INTO public.host_observation VALUES ('01a1b503-62e8-7a94-a446-a7e658651b4e', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'manifest', '2595c91fd3c7833bc6be60710a9f8106d5ab52c29f81967bfee7e4f2b6947d5e', '01a1b503-5a30-72cb-9fa1-2afca8014f95:2595c91fd3c7833bc6be60710a9f8106d5ab52c29f81967bfee7e4f2b6947d5e:manifest', '2026-11-07 07:57:40.452615+00', '{"chat_id": "98405043-f67e-457a-89e2-f2af77e95f73", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["70cd448a-58da-4fea-8704-2391be23f338", "65f847d9f7017d97e6d1cb92f04cb050257988a6ef9b03b347ebeb5633a5aeb2", "user", null, null, null, 0, null, null], ["6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "3e9774abad2195b81a7fed51fad8234ed4a7b850107f7caca7edad217e0bff1a", "char", null, null, null, 0, "6d7ee8d3-4979-49a3-8617-5d7b6a93e670", null], ["c95b397e-473b-46a2-b2ea-6b97401b9c5e", "638cb8257d8b7271fd1435932a97af74f1e23d4b479b90238387ff1cc1fc7b3a", "user", null, null, null, 0, null, null], ["b3da5d55-e823-4892-8104-c1423e7442a4", "ed5d1d1f75e65aa66d802ac1df08f935cbe9ad992e30026db413d930ef5386b8", "char", null, null, null, 0, "b3da5d55-e823-4892-8104-c1423e7442a4", null], ["f06fa6c1-f1f1-4193-bd75-78001bee73f3", "c7ca04a0b2da85805cad7f4fdd25d7520efd94c9e9d53d2745fe20b083c544fb", "user", null, null, null, 0, null, null], ["c30ed147-7dd3-488b-bf9e-3791d614131e", "db497aa6518625416281e1fd845ca7b5c396a91be5b3b17e378845933a58e341", "char", null, null, null, 0, "c30ed147-7dd3-488b-bf9e-3791d614131e", null], ["996bd6eb-d0e6-446a-9b4b-83703cd77dde", "19653fd2cc47be59352f7f37395cb55cf0cd03016846120ab76ffcd478632c53", "user", null, null, null, 0, null, null], ["a2cbea71-1ec5-4040-9d3b-cca020053637", "4bc10a063e87042cdb8f1dd78bd175d49c3371991e3c008c2456d4e1b317cad8", "char", null, null, null, 0, "a2cbea71-1ec5-4040-9d3b-cca020053637", null], ["7fa62829-c1e7-4483-b91d-db55407aa75f", "1d59fa3d6e5e01cfc95291f1b7febd3d93f2ada9f0158c41ac5af938eb4eb23a", "user", null, null, null, 0, null, null], ["fc31de31-a026-4d42-80e1-1fd90dec0422", "28ea885e98c3b3bd20d41c22124ef6b4097ac91ac86dc9503d77ba0075cc335c", "char", null, null, null, 0, "fc31de31-a026-4d42-80e1-1fd90dec0422", null], ["549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "02859d31959e548854aa42b29aeec2238788379bf417482f1f5cdf894056b3a3", "user", null, null, null, 0, null, null], ["882cdb55-4602-48de-acd0-67f63b04119f", "c8351031ff3c625c826c74c7a9d8c50d6c7cee647c011240f12901db0c70d248", "char", null, null, null, 0, "882cdb55-4602-48de-acd0-67f63b04119f", null], ["40385c3d-40de-4832-92a7-71a158bb74ff", "56834ab93fd8fe041d04d197594830e0dce74b2f6064b50ce1d39d767c1645a1", "user", null, null, null, 0, null, null], ["8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", "bc9b065c4c970811014b8cd163484a304e9aacb5c746b288ccf0e1cf4831fa06", "char", null, null, null, 0, "8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", null], ["80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "9e2de1060d74ed8c1871bf8a881759b6cd78bbe0d1a8bcc5f0bad40325008ca2", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a1b503-630f-750a-9c44-a73b4a57b46d', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'manifest', '84bf10b8dca43f2654b2015102001a2764bf7896283623a62a4bdd4927a2c281', '01a1b503-5a30-72cb-9fa1-2afca8014f95:84bf10b8dca43f2654b2015102001a2764bf7896283623a62a4bdd4927a2c281:manifest', '2026-11-07 07:57:40.491227+00', '{"chat_id": "98405043-f67e-457a-89e2-f2af77e95f73", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "d6ff49f9de5835ddcc7d01e3c474e3e65af5179c7118f745c8dba6ff8d39d99e", "char", null, null, 1, 2, "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", null]], "base_manifest_hash": "2595c91fd3c7833bc6be60710a9f8106d5ab52c29f81967bfee7e4f2b6947d5e"}');
INSERT INTO public.host_observation VALUES ('01a1b503-6331-763a-9179-cf1faaf118d4', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'manifest', '4982d9a6a4fc353f3ebb5b98808c56080987645d80e85d2241504f4db611152a', '01a1b503-5a30-72cb-9fa1-2afca8014f95:4982d9a6a4fc353f3ebb5b98808c56080987645d80e85d2241504f4db611152a:manifest', '2026-11-07 07:57:40.52419+00', '{"chat_id": "98405043-f67e-457a-89e2-f2af77e95f73", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["70cd448a-58da-4fea-8704-2391be23f338", "65f847d9f7017d97e6d1cb92f04cb050257988a6ef9b03b347ebeb5633a5aeb2", "user", null, null, null, 0, null, null], ["6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "3e9774abad2195b81a7fed51fad8234ed4a7b850107f7caca7edad217e0bff1a", "char", null, null, null, 0, "6d7ee8d3-4979-49a3-8617-5d7b6a93e670", null], ["c95b397e-473b-46a2-b2ea-6b97401b9c5e", "638cb8257d8b7271fd1435932a97af74f1e23d4b479b90238387ff1cc1fc7b3a", "user", null, null, null, 0, null, null], ["b3da5d55-e823-4892-8104-c1423e7442a4", "ed5d1d1f75e65aa66d802ac1df08f935cbe9ad992e30026db413d930ef5386b8", "char", null, null, null, 0, "b3da5d55-e823-4892-8104-c1423e7442a4", null], ["f06fa6c1-f1f1-4193-bd75-78001bee73f3", "c7ca04a0b2da85805cad7f4fdd25d7520efd94c9e9d53d2745fe20b083c544fb", "user", null, null, null, 0, null, null], ["c30ed147-7dd3-488b-bf9e-3791d614131e", "db497aa6518625416281e1fd845ca7b5c396a91be5b3b17e378845933a58e341", "char", null, null, null, 0, "c30ed147-7dd3-488b-bf9e-3791d614131e", null], ["996bd6eb-d0e6-446a-9b4b-83703cd77dde", "19653fd2cc47be59352f7f37395cb55cf0cd03016846120ab76ffcd478632c53", "user", null, null, null, 0, null, null], ["a2cbea71-1ec5-4040-9d3b-cca020053637", "4bc10a063e87042cdb8f1dd78bd175d49c3371991e3c008c2456d4e1b317cad8", "char", null, null, null, 0, "a2cbea71-1ec5-4040-9d3b-cca020053637", null], ["7fa62829-c1e7-4483-b91d-db55407aa75f", "c1dcbbdbf05756b484f3c5650057fd82d0e2b013e6cbe32c0eb7e3ad4b0e10a0", "user", true, null, null, 0, null, null], ["fc31de31-a026-4d42-80e1-1fd90dec0422", "28ea885e98c3b3bd20d41c22124ef6b4097ac91ac86dc9503d77ba0075cc335c", "char", null, null, null, 0, "fc31de31-a026-4d42-80e1-1fd90dec0422", null], ["549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "02859d31959e548854aa42b29aeec2238788379bf417482f1f5cdf894056b3a3", "user", null, null, null, 0, null, null], ["882cdb55-4602-48de-acd0-67f63b04119f", "c8351031ff3c625c826c74c7a9d8c50d6c7cee647c011240f12901db0c70d248", "char", null, null, null, 0, "882cdb55-4602-48de-acd0-67f63b04119f", null], ["40385c3d-40de-4832-92a7-71a158bb74ff", "56834ab93fd8fe041d04d197594830e0dce74b2f6064b50ce1d39d767c1645a1", "user", null, null, null, 0, null, null], ["8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", "bc9b065c4c970811014b8cd163484a304e9aacb5c746b288ccf0e1cf4831fa06", "char", null, null, null, 0, "8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", null], ["80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "9e2de1060d74ed8c1871bf8a881759b6cd78bbe0d1a8bcc5f0bad40325008ca2", "user", null, null, null, 0, null, null], ["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "91f0a780fda81328b9f498ec57ec9326890791254e1ab84720215f43754821b9", "char", null, null, 0, 2, "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", null], ["0c5da5ea-720e-4f0c-b84b-498d8b8a6167", "ce31c892f7f80e940383b129aa2ba2d656af81978c37d286a9800d7d8aa8b063", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a1b503-6756-70bb-8e35-d212d8c249f5', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', 'manifest', '8636056fd57ccf27c01355270cb77626fad0ffa33436bfc9c76e224a0997477d', '01a1b503-673b-74ee-9196-ed4ad8d4b49f:8636056fd57ccf27c01355270cb77626fad0ffa33436bfc9c76e224a0997477d:manifest', '2026-11-07 07:57:41.575328+00', '{"chat_id": "65045fb6-a788-4d69-8d94-a465c77dc180", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["331805f3-83d9-4257-b3cc-9b9141400d94", "ecec626fad5202ee7eb5546110058a5544099309ceb271bfe2388616b7ea1898", "user", null, null, null, 0, null, null], ["cd0c29fa-9be6-4048-a1ae-ad337afd6f85", "27b6814b57f61e918bd60a33e7cc5c89bb990e651e502eba106d0cded7268bba", "char", null, null, null, 0, "6d7ee8d3-4979-49a3-8617-5d7b6a93e670", null], ["e7b82fc7-1321-40d7-8142-b09a42bfa3ec", "c8491994a68b6172abb2981cf1fc0875f897d3a1e1788b7505b600ee170da9f1", "user", null, null, null, 0, null, null], ["f4978ecf-4707-4df8-80c3-dddfb653b7e9", "406068d2201d0bd07b560172498283f1b5f1ac9449952211bcbadf084a468e56", "char", null, null, null, 0, "b3da5d55-e823-4892-8104-c1423e7442a4", null], ["3ab7c5fb-b128-4c9e-ab39-16245bf1566a", "83baad89627c4c3f13a85b984b87762073e27609c221cd43b252c1777f02427a", "user", null, null, null, 0, null, null], ["9903f26e-1644-438b-920c-71a4aa2f3aac", "c4a5fa731d4d479dd06f4deccb5e608b1ac5047254e993228b7ee3e1a00bcba0", "char", null, null, null, 0, "c30ed147-7dd3-488b-bf9e-3791d614131e", null], ["7b599dea-63be-4140-b759-7d4991883d79", "f84ce26081c4ffa6eacb43ebec519cb2509537b28dbf95a9182e53269db7aaa9", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::98405043-f67e-457a-89e2-f2af77e95f73::Harbor route::c30ed147-7dd3-488b-bf9e-3791d614131e::}}"]], ["f2a9b2ae-3129-4125-85f4-f9fa966b7013", "e39d372832d5889f2441e52849dfd3a995f6b5b3a6a954273cc986cb45258740", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a1b503-5adb-73bf-baff-30c66e290592:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5adb-73bf-baff-30c66e290592"}', 50, 'done', 1, '2026-11-07 07:57:38.394074+00', NULL, NULL, '2026-11-07 07:57:38.394074+00', '2026-11-07 07:57:39.826325+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a1b503-5ab6-7513-bc12-4f96b7689363:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5ab6-7513-bc12-4f96b7689363"}', 50, 'done', 1, '2026-11-07 07:57:38.394074+00', NULL, NULL, '2026-11-07 07:57:38.394074+00', '2026-11-07 07:57:39.838306+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a1b503-5ab5-749f-b0fc-965a248e61f8:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5ab5-749f-b0fc-965a248e61f8"}', 50, 'done', 1, '2026-11-07 07:57:38.354652+00', NULL, NULL, '2026-11-07 07:57:38.354652+00', '2026-11-07 07:57:39.849263+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a1b503-5ab4-7655-b423-5dc052054436:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5ab4-7655-b423-5dc052054436"}', 50, 'done', 1, '2026-11-07 07:57:38.354652+00', NULL, NULL, '2026-11-07 07:57:38.354652+00', '2026-11-07 07:57:39.862298+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a1b503-5ab3-7136-9826-415cda22b3ca:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5ab3-7136-9826-415cda22b3ca"}', 50, 'done', 1, '2026-11-07 07:57:38.354652+00', NULL, NULL, '2026-11-07 07:57:38.354652+00', '2026-11-07 07:57:39.875037+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a1b503-5a8a-71df-ab4b-338ad64371a0:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5a8a-71df-ab4b-338ad64371a0"}', 50, 'done', 1, '2026-11-07 07:57:38.354652+00', NULL, NULL, '2026-11-07 07:57:38.354652+00', '2026-11-07 07:57:39.885611+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a1b503-5a89-7b86-a6c2-5a6c3573e7a9:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5a89-7b86-a6c2-5a6c3573e7a9"}', 50, 'done', 1, '2026-11-07 07:57:38.309858+00', NULL, NULL, '2026-11-07 07:57:38.309858+00', '2026-11-07 07:57:39.895653+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a1b503-5a88-7590-bd48-0a5829f8be50:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5a88-7590-bd48-0a5829f8be50"}', 50, 'done', 1, '2026-11-07 07:57:38.309858+00', NULL, NULL, '2026-11-07 07:57:38.309858+00', '2026-11-07 07:57:39.906213+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a1b503-5a86-7ba5-a8a6-c40fe3f4215f:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5a86-7ba5-a8a6-c40fe3f4215f"}', 50, 'done', 1, '2026-11-07 07:57:38.309858+00', NULL, NULL, '2026-11-07 07:57:38.309858+00', '2026-11-07 07:57:39.9167+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a1b503-5a3c-7db8-bc44-d742c1edd6a6:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5a3c-7db8-bc44-d742c1edd6a6"}', 50, 'done', 1, '2026-11-07 07:57:38.309858+00', NULL, NULL, '2026-11-07 07:57:38.309858+00', '2026-11-07 07:57:39.929719+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a1b503-5a3b-7495-99a7-605ad39cf6ff:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5a3b-7495-99a7-605ad39cf6ff"}', 150, 'done', 1, '2026-11-07 07:57:38.23094+00', NULL, NULL, '2026-11-07 07:57:38.23094+00', '2026-11-07 07:57:39.939524+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a1b503-5a3a-7f10-a68c-6bcfaa588817:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5a3a-7f10-a68c-6bcfaa588817"}', 150, 'done', 1, '2026-11-07 07:57:38.23094+00', NULL, NULL, '2026-11-07 07:57:38.23094+00', '2026-11-07 07:57:39.949109+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a1b503-5a38-77ec-8162-15882f38fe84:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-5a38-77ec-8162-15882f38fe84"}', 150, 'done', 1, '2026-11-07 07:57:38.23094+00', NULL, NULL, '2026-11-07 07:57:38.23094+00', '2026-11-07 07:57:39.95875+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a1b503-5a3a-7f10-a68c-6bcfaa588817:2f335d09dcaacbcf02ec8e89f317e045:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5a3a-7f10-a68c-6bcfaa588817", "window_hash": "2f335d09dcaacbcf02ec8e89f317e045"}', 210, 'done', 1, '2026-11-07 07:57:38.23094+00', NULL, NULL, '2026-11-07 07:57:38.23094+00', '2026-11-07 07:57:39.978811+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a1b503-5a3c-7db8-bc44-d742c1edd6a6:17b54f5779a8c0669b09af1f89cfb912:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5a3c-7db8-bc44-d742c1edd6a6", "window_hash": "17b54f5779a8c0669b09af1f89cfb912"}', 210, 'done', 1, '2026-11-07 07:57:38.309858+00', NULL, NULL, '2026-11-07 07:57:38.309858+00', '2026-11-07 07:57:39.99827+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a1b503-5a88-7590-bd48-0a5829f8be50:2ae2831913352d4cf5fc99e35967861b:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5a88-7590-bd48-0a5829f8be50", "window_hash": "2ae2831913352d4cf5fc99e35967861b"}', 210, 'done', 1, '2026-11-07 07:57:38.309858+00', NULL, NULL, '2026-11-07 07:57:38.309858+00', '2026-11-07 07:57:40.015559+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a1b503-5a8a-71df-ab4b-338ad64371a0:447f339c2164b052a9d164f18ec1a8ae:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5a8a-71df-ab4b-338ad64371a0", "window_hash": "447f339c2164b052a9d164f18ec1a8ae"}', 210, 'done', 1, '2026-11-07 07:57:38.354652+00', NULL, NULL, '2026-11-07 07:57:38.354652+00', '2026-11-07 07:57:40.031365+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a1b503-5ab4-7655-b423-5dc052054436:a2d6d9bdaa469ab8de7dc10038002466:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5ab4-7655-b423-5dc052054436", "window_hash": "a2d6d9bdaa469ab8de7dc10038002466"}', 210, 'done', 1, '2026-11-07 07:57:38.354652+00', NULL, NULL, '2026-11-07 07:57:38.354652+00', '2026-11-07 07:57:40.051363+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a1b503-5ab6-7513-bc12-4f96b7689363:7c4dba26c661acc5a6951658d010f90b:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5ab6-7513-bc12-4f96b7689363", "window_hash": "7c4dba26c661acc5a6951658d010f90b"}', 210, 'done', 1, '2026-11-07 07:57:38.394074+00', NULL, NULL, '2026-11-07 07:57:38.394074+00', '2026-11-07 07:57:40.073812+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a1b503-5a88-7590-bd48-0a5829f8be50:1b486d90698139d55cf93df2de95aaf3:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5a88-7590-bd48-0a5829f8be50", "window_hash": "1b486d90698139d55cf93df2de95aaf3"}', 100, 'done', 1, '2026-11-07 07:57:40.452615+00', NULL, NULL, '2026-11-07 07:57:40.452615+00', '2026-11-07 07:57:41.230588+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a1b503-62e5-70f0-9059-639da7836d39:4f24c11842d8548d6c1aaca217673205:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-62e5-70f0-9059-639da7836d39", "window_hash": "4f24c11842d8548d6c1aaca217673205"}', 100, 'done', 1, '2026-11-07 07:57:40.452615+00', NULL, NULL, '2026-11-07 07:57:40.452615+00', '2026-11-07 07:57:41.247984+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a1b503-6748-78ff-8ced-e4552c25c878:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-6748-78ff-8ced-e4552c25c878"}', 150, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.329886+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a1b503-632f-7255-a524-b3b4453890f9:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-632f-7255-a524-b3b4453890f9"}', 50, 'done', 1, '2026-11-07 07:57:40.52419+00', NULL, NULL, '2026-11-07 07:57:40.52419+00', '2026-11-07 07:57:41.093448+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a1b503-632f-7fc8-b29a-22d2b22c7074:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-632f-7fc8-b29a-22d2b22c7074"}', 50, 'done', 1, '2026-11-07 07:57:40.52419+00', NULL, NULL, '2026-11-07 07:57:40.52419+00', '2026-11-07 07:57:41.103935+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7"}', 50, 'done', 1, '2026-11-07 07:57:40.452615+00', NULL, NULL, '2026-11-07 07:57:40.452615+00', '2026-11-07 07:57:41.114021+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a1b503-62e6-7719-9da9-289c6668aa35:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-62e6-7719-9da9-289c6668aa35"}', 50, 'done', 1, '2026-11-07 07:57:40.452615+00', NULL, NULL, '2026-11-07 07:57:40.452615+00', '2026-11-07 07:57:41.128148+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a1b503-62e5-70f0-9059-639da7836d39:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-62e5-70f0-9059-639da7836d39"}', 50, 'done', 1, '2026-11-07 07:57:40.452615+00', NULL, NULL, '2026-11-07 07:57:40.452615+00', '2026-11-07 07:57:41.138644+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a1b503-632f-7fc8-b29a-22d2b22c7074:4a40d7e73001910ec22c621a74e87de1:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-632f-7fc8-b29a-22d2b22c7074", "window_hash": "4a40d7e73001910ec22c621a74e87de1"}', 100, 'done', 1, '2026-11-07 07:57:40.52419+00', NULL, NULL, '2026-11-07 07:57:40.52419+00', '2026-11-07 07:57:41.155297+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a1b503-62e6-7719-9da9-289c6668aa35:8c8c60409c41e6a67d765de394b42805:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-62e6-7719-9da9-289c6668aa35", "window_hash": "8c8c60409c41e6a67d765de394b42805"}', 100, 'done', 1, '2026-11-07 07:57:40.52419+00', NULL, NULL, '2026-11-07 07:57:40.52419+00', '2026-11-07 07:57:41.17006+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a1b503-5ab6-7513-bc12-4f96b7689363:9c6b9541d63d543f57327d77018cfa5d:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5ab6-7513-bc12-4f96b7689363", "window_hash": "9c6b9541d63d543f57327d77018cfa5d"}', 100, 'done', 1, '2026-11-07 07:57:40.52419+00', NULL, NULL, '2026-11-07 07:57:40.52419+00', '2026-11-07 07:57:41.188373+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a1b503-5ab4-7655-b423-5dc052054436:8b63bffe2b4762e1506061c48dd28ce8:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5ab4-7655-b423-5dc052054436", "window_hash": "8b63bffe2b4762e1506061c48dd28ce8"}', 100, 'done', 1, '2026-11-07 07:57:40.52419+00', NULL, NULL, '2026-11-07 07:57:40.52419+00', '2026-11-07 07:57:41.204763+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a1b503-62e6-7719-9da9-289c6668aa35:ff1fde84de9b061aabc1ba5c0734d6e9:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-62e6-7719-9da9-289c6668aa35", "window_hash": "ff1fde84de9b061aabc1ba5c0734d6e9"}', 100, 'obsolete', 1, '2026-11-07 07:57:40.452615+00', NULL, NULL, '2026-11-07 07:57:40.452615+00', '2026-11-07 07:57:41.208329+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a1b503-5ab4-7655-b423-5dc052054436:50e263fd7e86c5ba3928463401ba80ae:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5ab4-7655-b423-5dc052054436", "window_hash": "50e263fd7e86c5ba3928463401ba80ae"}', 100, 'obsolete', 1, '2026-11-07 07:57:40.452615+00', NULL, NULL, '2026-11-07 07:57:40.452615+00', '2026-11-07 07:57:41.211594+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a1b503-5a8a-71df-ab4b-338ad64371a0:92ac738b21db0a9a556e3b0d00d8d702:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-5a8a-71df-ab4b-338ad64371a0", "window_hash": "92ac738b21db0a9a556e3b0d00d8d702"}', 100, 'obsolete', 1, '2026-11-07 07:57:40.452615+00', NULL, NULL, '2026-11-07 07:57:40.452615+00', '2026-11-07 07:57:41.214931+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a1b503-6749-77c5-b971-23e10117bbe7:2debec0bb3c3ec2fbd15817a7c25c99c:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-6749-77c5-b971-23e10117bbe7", "window_hash": "2debec0bb3c3ec2fbd15817a7c25c99c"}', 210, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.343593+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a1b503-674b-76c1-9e42-b0fe12a99c0b:dfbda48b7fe7476ad6781ff374cfe906:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-674b-76c1-9e42-b0fe12a99c0b", "window_hash": "dfbda48b7fe7476ad6781ff374cfe906"}', 210, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.359774+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a1b503-6753-741e-b987-e504cab053b5:320cf026f4df0d55f9fb9c9fc6348173:extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "extract-dc3abbb00004ab00b7ae2cf9cb44d1b6", "revision_id": "01a1b503-6753-741e-b987-e504cab053b5", "window_hash": "320cf026f4df0d55f9fb9c9fc6348173"}', 210, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.374555+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a1b503-6754-7d15-8e9d-b2e32482c8d4:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-6754-7d15-8e9d-b2e32482c8d4"}', 150, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.26742+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a1b503-6753-741e-b987-e504cab053b5:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-6753-741e-b987-e504cab053b5"}', 150, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.277795+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a1b503-6751-7f95-a588-4d829ef73cc7:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-6751-7f95-a588-4d829ef73cc7"}', 150, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.287641+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a1b503-674b-76c1-9e42-b0fe12a99c0b:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-674b-76c1-9e42-b0fe12a99c0b"}', 150, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.30083+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a1b503-674a-77ef-87a7-01dd0bfc32ea:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-674a-77ef-87a7-01dd0bfc32ea"}', 150, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.310669+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a1b503-6749-77c5-b971-23e10117bbe7:embed-0cd496c1d1f1682e03f4510aedb56f3a', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{"generation": "embed-0cd496c1d1f1682e03f4510aedb56f3a", "revision_id": "01a1b503-6749-77c5-b971-23e10117bbe7"}', 150, 'done', 1, '2026-11-07 07:57:41.575328+00', NULL, NULL, '2026-11-07 07:57:41.575328+00', '2026-11-07 07:57:42.320487+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a1b503-5a3d-7154-8287-0d5972d7c509', '01a1b503-5a30-72cb-9fa1-2afca8014f95');


--
-- Data for Name: owner_repair; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'extract', 'stub', 'http://127.0.0.1:40281/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "a6fec3fe3aabc852", "aliases": "361e584289ae46a4", "confirm": "c1a68b38f8fcae60", "compiler": "extract-v16", "endpoint": "http://127.0.0.1:40281/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "ec86a5ac4362f77d", "temperature": 0, "target_chars": 6000, "context_chars": 1000, "context_turns": 3}', '2026-11-07 07:57:38.153388+00', '2026-11-07 07:57:38.154684+00');
INSERT INTO public.projection_generation VALUES ('embed-0cd496c1d1f1682e03f4510aedb56f3a', 'embed', 'stub-embed', 'http://127.0.0.1:40281/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:40281/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-11-07 07:57:38.153388+00', '2026-11-07 07:57:38.158744+00');
INSERT INTO public.projection_generation VALUES ('summarize-efca59fe8eb938762d007b25679b5a2b', 'summarize', 'stub', 'http://127.0.0.1:40281/v1', '{"lag": 4, "kind": "summarize", "model": "stub", "prompt": "1cb5649d13d81671", "window": 8, "version": "summarize-v3", "endpoint": "http://127.0.0.1:40281/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "message_chars": 6000}', '2026-11-07 07:57:38.153388+00', '2026-11-07 07:57:38.161256+00');
INSERT INTO public.projection_generation VALUES ('canon-8ff90dc73b2fbde57fc6b2f8c70ab44c', 'canon', 'stub', 'http://127.0.0.1:40281/v1', '{"kind": "canon", "model": "stub", "prompt": "c084747d55328ce7", "version": "canon-v1", "endpoint": "http://127.0.0.1:40281/v1", "json_mode": true, "max_parts": 4, "normalizer": "clean-v3", "part_chars": 6000, "predicates": "9aebb33c40fcda7c", "temperature": 0}', '2026-11-07 07:57:38.153388+00', '2026-11-07 07:57:38.162662+00');
INSERT INTO public.projection_generation VALUES ('reveal-9e87f99ec71b5eb62a68b6921127734c', 'reveal', 'stub', 'http://127.0.0.1:40281/v1', '{"kind": "reveal", "model": "stub", "prompt": "799b88903bfe0c44", "version": "reveal-v1", "compiler": "extract-v15", "endpoint": "http://127.0.0.1:40281/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "target_chars": 6000, "context_chars": 1000, "context_turns": 3}', '2026-11-07 07:57:38.153388+00', '2026-11-07 07:57:38.165877+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a1b503-5a7b-7cf8-a3cf-3028e3c1f42f', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a', 'Is Rin with you?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a1b503-5a3b-7495-99a7-605ad39cf6ff", "keyword_score": 1.0986, "host_logical_id": "c95b397e-473b-46a2-b2ea-6b97401b9c5e"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a1b503-5a3b-7495-99a7-605ad39cf6ff", "keyword_score": 1.0986, "host_logical_id": "c95b397e-473b-46a2-b2ea-6b97401b9c5e"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 48.79, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.67, "fits_at": null, "lexical": 9.64, "threads": 0, "keywords": 16.01, "extractor": "extract-dc3abbb00004", "embed_wait": 12.48, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 52.62, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-0cd496c1d1f168", "memory_mode_withheld": 0}', 'fresh', '2026-11-07 07:57:38.247283+00', 'packet-v19', 600, 3, '', '["6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "70cd448a-58da-4fea-8704-2391be23f338", "b3da5d55-e823-4892-8104-c1423e7442a4", "c95b397e-473b-46a2-b2ea-6b97401b9c5e"]', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-8ff90dc73b2fbde57fc6b2f8c70ab44c", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-efca59fe8eb938762d007b25679b5a2b", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a1b503-5aa8-72f0-8423-d28005581faa', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a', 'Let''s check the market.', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a1b503-5a89-7b86-a6c2-5a6c3573e7a9", "keyword_score": 5.8377, "host_logical_id": "996bd6eb-d0e6-446a-9b4b-83703cd77dde"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a1b503-5a89-7b86-a6c2-5a6c3573e7a9", "keyword_score": 5.8377, "host_logical_id": "996bd6eb-d0e6-446a-9b4b-83703cd77dde"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 8.49, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.76, "fits_at": null, "lexical": 2.87, "threads": 0, "keywords": 7.26, "extractor": "extract-dc3abbb00004", "embed_wait": 0.01, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 15.74, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-0cd496c1d1f168", "memory_mode_withheld": 0}', 'fresh', '2026-11-07 07:57:38.329125+00', 'packet-v19', 600, 7, '', '["996bd6eb-d0e6-446a-9b4b-83703cd77dde", "a2cbea71-1ec5-4040-9d3b-cca020053637", "c30ed147-7dd3-488b-bf9e-3791d614131e", "f06fa6c1-f1f1-4193-bd75-78001bee73f3"]', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-8ff90dc73b2fbde57fc6b2f8c70ab44c", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-efca59fe8eb938762d007b25679b5a2b", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a1b503-5ad0-7b6e-ba2f-993b95f4f9fc', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a', 'Where do we meet tonight?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a1b503-5ab5-749f-b0fc-965a248e61f8", "keyword_score": 4.7958, "host_logical_id": "549d9b75-9af3-44ed-9487-f6f42ab3b3eb"}]', '[]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a1b503-5ab5-749f-b0fc-965a248e61f8", "keyword_score": 4.7958, "host_logical_id": "549d9b75-9af3-44ed-9487-f6f42ab3b3eb"}]', 0, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 8.09, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.92, "fits_at": null, "lexical": 3.01, "threads": 0, "keywords": 5.55, "extractor": "extract-dc3abbb00004", "embed_wait": 0.01, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 14.75, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-0cd496c1d1f168", "memory_mode_withheld": 0}', 'fresh', '2026-11-07 07:57:38.369449+00', 'packet-v19', 600, 11, '', '["549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "7fa62829-c1e7-4483-b91d-db55407aa75f", "882cdb55-4602-48de-acd0-67f63b04119f", "fc31de31-a026-4d42-80e1-1fd90dec0422"]', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-8ff90dc73b2fbde57fc6b2f8c70ab44c", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-efca59fe8eb938762d007b25679b5a2b", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a1b503-5af8-75ac-bb88-95ae27cdd796', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a', 'Where is Mina now?', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a1b503-5adb-73bf-baff-30c66e290592", "keyword_score": 0.7732, "host_logical_id": "40385c3d-40de-4832-92a7-71a158bb74ff"}, {"rrf": 0.03151, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a1b503-5a3c-7db8-bc44-d742c1edd6a6", "keyword_score": 0.7732, "host_logical_id": "b3da5d55-e823-4892-8104-c1423e7442a4"}, {"rrf": 0.03102, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a1b503-5a3a-7f10-a68c-6bcfaa588817", "keyword_score": 0.7732, "host_logical_id": "6d7ee8d3-4979-49a3-8617-5d7b6a93e670"}, {"rrf": 0.01613, "sim": null, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a1b503-5ab6-7513-bc12-4f96b7689363", "keyword_score": 0.7732, "host_logical_id": "882cdb55-4602-48de-acd0-67f63b04119f"}, {"rrf": 0.01587, "sim": null, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a1b503-5a88-7590-bd48-0a5829f8be50", "keyword_score": 0.7732, "host_logical_id": "c30ed147-7dd3-488b-bf9e-3791d614131e"}, {"rrf": 0.01562, "sim": null, "score": 0.0, "position": 4, "user_score": 0.0, "revision_id": "01a1b503-5a86-7ba5-a8a6-c40fe3f4215f", "keyword_score": 0.7732, "host_logical_id": "f06fa6c1-f1f1-4193-bd75-78001bee73f3"}]', '[{"turn": 0, "score": 0.03102, "revision_id": "01a1b503-5a3a-7f10-a68c-6bcfaa588817"}, {"turn": 1, "score": 0.03151, "revision_id": "01a1b503-5a3c-7db8-bc44-d742c1edd6a6"}, {"turn": 2, "score": 0.01562, "revision_id": "01a1b503-5a86-7ba5-a8a6-c40fe3f4215f"}, {"turn": 2, "score": 0.01587, "revision_id": "01a1b503-5a88-7590-bd48-0a5829f8be50"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a1b503-5adb-73bf-baff-30c66e290592", "keyword_score": 0.7732, "host_logical_id": "40385c3d-40de-4832-92a7-71a158bb74ff"}, {"rrf": 0.01613, "sim": null, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a1b503-5ab6-7513-bc12-4f96b7689363", "keyword_score": 0.7732, "host_logical_id": "882cdb55-4602-48de-acd0-67f63b04119f"}]', 227, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 9.76, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 4, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 2.21, "fits_at": null, "lexical": 3.33, "threads": 0, "keywords": 2.64, "extractor": "extract-dc3abbb00004", "embed_lead": 17.87, "embed_wait": 0.01, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 15.37, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-0cd496c1d1f168", "memory_mode_withheld": 0}', 'fresh', '2026-11-07 07:57:38.409019+00', 'packet-v19', 600, 12, '', '["40385c3d-40de-4832-92a7-71a158bb74ff", "549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "882cdb55-4602-48de-acd0-67f63b04119f", "fc31de31-a026-4d42-80e1-1fd90dec0422"]', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-8ff90dc73b2fbde57fc6b2f8c70ab44c", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-efca59fe8eb938762d007b25679b5a2b", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a1b503-5a3c-7db8-bc44-d742c1edd6a6"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 1, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a1b503-5a3a-7f10-a68c-6bcfaa588817"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 0, "label": "supportive", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a1b503-5a88-7590-bd48-0a5829f8be50"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a1b503-5a86-7ba5-a8a6-c40fe3f4215f"}, "tok": 23, "why": "placed", "kind": "excerpt", "text": "What did Mina say before she left?", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a1b503-6300-72a6-99b1-05d01df25149', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '01a1b503-62eb-7ec2-9b48-a822fb9e682e', 'And the compass?', '[{"rrf": 0.04741, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a1b503-5ab4-7655-b423-5dc052054436", "keyword_score": 2.0149, "host_logical_id": "fc31de31-a026-4d42-80e1-1fd90dec0422"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7", "keyword_score": 2.0149, "host_logical_id": "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a1b503-5a3a-7f10-a68c-6bcfaa588817", "keyword_score": 0.0, "host_logical_id": "6d7ee8d3-4979-49a3-8617-5d7b6a93e670"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a1b503-5a38-77ec-8162-15882f38fe84", "keyword_score": 0.0, "host_logical_id": "70cd448a-58da-4fea-8704-2391be23f338"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a1b503-5a8a-71df-ab4b-338ad64371a0", "keyword_score": 0.0, "host_logical_id": "a2cbea71-1ec5-4040-9d3b-cca020053637"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a1b503-5a88-7590-bd48-0a5829f8be50", "keyword_score": 0.0, "host_logical_id": "c30ed147-7dd3-488b-bf9e-3791d614131e"}]', '[{"turn": 4, "score": 0.04741, "revision_id": "01a1b503-5ab4-7655-b423-5dc052054436"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7", "keyword_score": 2.0149, "host_logical_id": "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7"}]', 222, '{"fit": 0.01, "cast": 2, "path": "normal", "embed": 7.0, "facts": 0, "placed": {"fact": 2, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.86, "fits_at": null, "lexical": 2.86, "threads": 0, "keywords": 2.64, "extractor": "extract-dc3abbb00004", "embed_lead": 16.22, "embed_wait": 0.01, "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["Mina", "{{user}}"], "below_floor": 3, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 14.54, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 1, "embedding_projection": "embed-0cd496c1d1f168", "memory_mode_withheld": 0}', 'fresh', '2026-11-07 07:57:40.466222+00', 'packet-v19', 600, 14, '', '["40385c3d-40de-4832-92a7-71a158bb74ff", "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "882cdb55-4602-48de-acd0-67f63b04119f", "8a3be60a-4e0d-4b60-b42f-04f0f6aa260a"]', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-8ff90dc73b2fbde57fc6b2f8c70ab44c", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-efca59fe8eb938762d007b25679b5a2b", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 7}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "label": "required", "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 2}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "label": "required", "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a1b503-5ab4-7655-b423-5dc052054436"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a1b503-5a38-77ec-8162-15882f38fe84"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "label": "supportive", "placed": false}, {"ref": {"revision": "01a1b503-5a8a-71df-ab4b-338ad64371a0"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 3, "label": "supportive", "marks": {"unextracted": true}, "placed": false}, {"ref": {"revision": "01a1b503-5a88-7590-bd48-0a5829f8be50"}, "tok": 0, "why": "below_floor", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "label": "supportive", "marks": {"unextracted": true}, "placed": false}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a1b503-6322-7a1e-b7f4-93f773f2cf09', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '01a1b503-62eb-7ec2-9b48-a822fb9e682e', 'compass', '[{"rrf": 0.04615, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a1b503-5ab4-7655-b423-5dc052054436", "keyword_score": 2.0149, "host_logical_id": "fc31de31-a026-4d42-80e1-1fd90dec0422"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7", "keyword_score": 2.0149, "host_logical_id": "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a1b503-5ab6-7513-bc12-4f96b7689363", "keyword_score": 0.0, "host_logical_id": "882cdb55-4602-48de-acd0-67f63b04119f"}]', '[{"turn": 4, "score": 0.04615, "revision_id": "01a1b503-5ab4-7655-b423-5dc052054436"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7", "keyword_score": 2.0149, "host_logical_id": "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7"}]', 222, '{"fit": 0.0, "cast": 2, "path": "normal", "embed": 6.56, "facts": 0, "placed": {"fact": 2, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.05, "fits_at": null, "lexical": 3.24, "threads": 0, "keywords": 3.14, "extractor": "extract-dc3abbb00004", "embed_wait": 0.0, "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["Mina", "{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 14.73, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-0cd496c1d1f168", "memory_mode_withheld": 0}', 'fresh', '2026-11-07 07:57:40.500295+00', 'packet-v19', 600, 15, '', '["40385c3d-40de-4832-92a7-71a158bb74ff", "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "8a3be60a-4e0d-4b60-b42f-04f0f6aa260a"]', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-8ff90dc73b2fbde57fc6b2f8c70ab44c", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-efca59fe8eb938762d007b25679b5a2b", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 7}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "label": "required", "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 2}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "label": "required", "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a1b503-5ab4-7655-b423-5dc052054436"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a1b503-5ab6-7513-bc12-4f96b7689363"}, "tok": 0, "why": "repeats", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 5, "label": "supportive", "placed": false, "repeats": {"assertion": 7}}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a1b503-6345-7309-83e5-6c1fbe46ccd4', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '01a1b503-6333-7a9b-92c4-069cd38d61ac', 'Let''s go.', '[{"rrf": 0.04865, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a1b503-5a89-7b86-a6c2-5a6c3573e7a9", "keyword_score": 2.0794, "host_logical_id": "996bd6eb-d0e6-446a-9b4b-83703cd77dde"}, {"rrf": 0.03279, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a1b503-632f-7255-a524-b3b4453890f9", "keyword_score": 2.0794, "host_logical_id": "0c5da5ea-720e-4f0c-b84b-498d8b8a6167"}]', '[{"turn": 3, "score": 0.04865, "revision_id": "01a1b503-5a89-7b86-a6c2-5a6c3573e7a9"}]', '[{"rrf": 0.03279, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a1b503-632f-7255-a524-b3b4453890f9", "keyword_score": 2.0794, "host_logical_id": "0c5da5ea-720e-4f0c-b84b-498d8b8a6167"}]', 138, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 7.86, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 1.64, "fits_at": null, "lexical": 2.95, "threads": 0, "keywords": 2.66, "extractor": "extract-dc3abbb00004", "embed_lead": 15.28, "embed_wait": 0.0, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 12.45, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-0cd496c1d1f168", "memory_mode_withheld": 0}', 'fresh', '2026-11-07 07:57:40.537377+00', 'packet-v19', 600, 16, '', '["0c5da5ea-720e-4f0c-b84b-498d8b8a6167", "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "8a3be60a-4e0d-4b60-b42f-04f0f6aa260a"]', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-8ff90dc73b2fbde57fc6b2f8c70ab44c", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-efca59fe8eb938762d007b25679b5a2b", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a1b503-5a89-7b86-a6c2-5a6c3573e7a9"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 3, "label": "required", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a1b503-676a-765a-813c-d91bdd36cf51', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '01a1b503-6756-7f28-9160-637f47941c22', 'Where is Rin?', '[{"rrf": 0.03227, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a1b503-674a-77ef-87a7-01dd0bfc32ea", "keyword_score": 0.8473, "host_logical_id": "e7b82fc7-1321-40d7-8142-b09a42bfa3ec"}, {"rrf": 0.03226, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a1b503-674b-76c1-9e42-b0fe12a99c0b", "keyword_score": 0.8473, "host_logical_id": "f4978ecf-4707-4df8-80c3-dddfb653b7e9"}, {"rrf": 0.01639, "sim": null, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a1b503-6754-7d15-8e9d-b2e32482c8d4", "keyword_score": 0.8473, "host_logical_id": "f2a9b2ae-3129-4125-85f4-f9fa966b7013"}]', '[{"turn": 1, "score": 0.03227, "revision_id": "01a1b503-674a-77ef-87a7-01dd0bfc32ea"}, {"turn": 1, "score": 0.03226, "revision_id": "01a1b503-674b-76c1-9e42-b0fe12a99c0b"}]', '[{"rrf": 0.01639, "sim": null, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a1b503-6754-7d15-8e9d-b2e32482c8d4", "keyword_score": 0.8473, "host_logical_id": "f2a9b2ae-3129-4125-85f4-f9fa966b7013"}]', 164, '{"fit": 0.0, "cast": 0, "path": "normal", "embed": 9.72, "facts": 0, "placed": {"fact": 0, "claim": 0, "quote": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2, "summary": 0, "source_time": 0, "state_history": 0}, "quotes": 0, "rested": 0, "vector": 0.83, "fits_at": null, "lexical": 2.82, "threads": 0, "keywords": 2.62, "extractor": "extract-dc3abbb00004", "embed_wait": 0.0, "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "quote_mode": "off", "scene_cast": ["{{user}}"], "below_floor": 0, "state_items": 0, "vector_mode": "on", "kept_threads": 0, "keyword_mode": "on", "lexical_mode": "on", "sidecar_total": 13.09, "ended_left_out": 0, "quote_withheld": 0, "keyword_withheld": 0, "replaced_left_out": 0, "embedding_projection": "embed-0cd496c1d1f168", "memory_mode_withheld": 0}', 'fresh', '2026-11-07 07:57:41.597409+00', 'packet-v19', 600, 7, '', '["3ab7c5fb-b128-4c9e-ab39-16245bf1566a", "7b599dea-63be-4140-b759-7d4991883d79", "9903f26e-1644-438b-920c-71a4aa2f3aac", "f2a9b2ae-3129-4125-85f4-f9fa966b7013"]', 'extract-dc3abbb00004ab00b7ae2cf9cb44d1b6', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', 'none', '{"fill": 1.0, "top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-8ff90dc73b2fbde57fc6b2f8c70ab44c", "first_cue": true, "threshold": 0.4, "rest_after": 2, "state_pins": [], "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "replies_only": false, "source_clock": true, "history_marks": true, "name_variants": true, "state_changes": true, "summarize_key": "summarize-efca59fe8eb938762d007b25679b5a2b", "threads_limit": 3, "excerpt_anchor": "keywords", "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_keywords": true, "keyword_particles": true, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a1b503-674a-77ef-87a7-01dd0bfc32ea"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 1, "label": "required", "marks": {"unextracted": true}, "placed": true}, {"ref": {"revision": "01a1b503-674b-76c1-9e42-b0fe12a99c0b"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 1, "label": "supportive", "marks": {"unextracted": true}, "placed": true}]', NULL, '[]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a1b503-5adb-73bf-baff-30c66e290592', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.823403+00', '{"ms": 58, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5ab6-7513-bc12-4f96b7689363', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.836788+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5ab5-749f-b0fc-965a248e61f8', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.847737+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5ab4-7655-b423-5dc052054436', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.860729+00', '{"ms": 7, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5ab3-7136-9826-415cda22b3ca', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.873467+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5a8a-71df-ab4b-338ad64371a0', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.884062+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5a89-7b86-a6c2-5a6c3573e7a9', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.894168+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5a88-7590-bd48-0a5829f8be50', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.904786+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5a86-7ba5-a8a6-c40fe3f4215f', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.915267+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5a3c-7db8-bc44-d742c1edd6a6', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.928262+00', '{"ms": 8, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5a3b-7495-99a7-605ad39cf6ff', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.938098+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5a3a-7f10-a68c-6bcfaa588817', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.947732+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-5a38-77ec-8162-15882f38fe84', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:39.957177+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-632f-7255-a524-b3b4453890f9', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:41.091839+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-632f-7fc8-b29a-22d2b22c7074', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:41.102396+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:41.112612+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-62e6-7719-9da9-289c6668aa35', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:41.12672+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-62e5-70f0-9059-639da7836d39', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:41.137175+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-6754-7d15-8e9d-b2e32482c8d4', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:42.265892+00', '{"ms": 6, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-6753-741e-b987-e504cab053b5', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:42.276395+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-6751-7f95-a588-4d829ef73cc7', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:42.286144+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-674b-76c1-9e42-b0fe12a99c0b', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:42.299237+00', '{"ms": 8, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-674a-77ef-87a7-01dd0bfc32ea', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:42.309215+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-6749-77c5-b971-23e10117bbe7', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:42.318954+00', '{"ms": 5, "calls": 1}');
INSERT INTO public.revision_embedding VALUES ('01a1b503-6748-78ff-8ced-e4552c25c878', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-0cd496c1d1f1682e03f4510aedb56f3a', '2026-11-07 07:57:42.328439+00', '{"ms": 5, "calls": 1}');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a1b503-5a38-77ec-8162-15882f38fe84', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-11-07 07:57:38.23094+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5a3a-7f10-a68c-6bcfaa588817', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-11-07 07:57:38.23094+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5a3b-7495-99a7-605ad39cf6ff', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-11-07 07:57:38.23094+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5a3c-7db8-bc44-d742c1edd6a6', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-11-07 07:57:38.23094+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5a86-7ba5-a8a6-c40fe3f4215f', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-11-07 07:57:38.309858+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5a88-7590-bd48-0a5829f8be50', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-11-07 07:57:38.309858+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5a89-7b86-a6c2-5a6c3573e7a9', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-11-07 07:57:38.309858+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5a8a-71df-ab4b-338ad64371a0', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-11-07 07:57:38.309858+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5ab3-7136-9826-415cda22b3ca', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-11-07 07:57:38.354652+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5ab4-7655-b423-5dc052054436', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-11-07 07:57:38.354652+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5ab5-749f-b0fc-965a248e61f8', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-11-07 07:57:38.354652+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5ab6-7513-bc12-4f96b7689363', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-11-07 07:57:38.354652+00');
INSERT INTO public.revision_text VALUES ('01a1b503-5adb-73bf-baff-30c66e290592', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-11-07 07:57:38.394074+00');
INSERT INTO public.revision_text VALUES ('01a1b503-62e5-70f0-9059-639da7836d39', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-11-07 07:57:40.452615+00');
INSERT INTO public.revision_text VALUES ('01a1b503-62e6-7719-9da9-289c6668aa35', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-11-07 07:57:40.452615+00');
INSERT INTO public.revision_text VALUES ('01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7', 'clean-v3', 'And the compass?', 16, 16, '2026-11-07 07:57:40.452615+00');
INSERT INTO public.revision_text VALUES ('01a1b503-630c-7932-ae53-4f2c9f277bd4', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-11-07 07:57:40.491227+00');
INSERT INTO public.revision_text VALUES ('01a1b503-632e-71d7-b838-3548a004dfa5', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-11-07 07:57:40.52419+00');
INSERT INTO public.revision_text VALUES ('01a1b503-632f-7fc8-b29a-22d2b22c7074', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-11-07 07:57:40.52419+00');
INSERT INTO public.revision_text VALUES ('01a1b503-632f-7255-a524-b3b4453890f9', 'clean-v3', 'Let''s go.', 9, 9, '2026-11-07 07:57:40.52419+00');
INSERT INTO public.revision_text VALUES ('01a1b503-6748-78ff-8ced-e4552c25c878', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-11-07 07:57:41.575328+00');
INSERT INTO public.revision_text VALUES ('01a1b503-6749-77c5-b971-23e10117bbe7', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-11-07 07:57:41.575328+00');
INSERT INTO public.revision_text VALUES ('01a1b503-674a-77ef-87a7-01dd0bfc32ea', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-11-07 07:57:41.575328+00');
INSERT INTO public.revision_text VALUES ('01a1b503-674b-76c1-9e42-b0fe12a99c0b', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-11-07 07:57:41.575328+00');
INSERT INTO public.revision_text VALUES ('01a1b503-6751-7f95-a588-4d829ef73cc7', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-11-07 07:57:41.575328+00');
INSERT INTO public.revision_text VALUES ('01a1b503-6753-741e-b987-e504cab053b5', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-11-07 07:57:41.575328+00');
INSERT INTO public.revision_text VALUES ('01a1b503-6754-7cab-8462-4bfed95733cb', 'clean-v3', '{{specialcomment::branchedfrom::98405043-f67e-457a-89e2-f2af77e95f73::Harbor route::c30ed147-7dd3-488b-bf9e-3791d614131e::}}', 124, 124, '2026-11-07 07:57:41.575328+00');
INSERT INTO public.revision_text VALUES ('01a1b503-6754-7d15-8e9d-b2e32482c8d4', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-11-07 07:57:41.575328+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-11-07 07:57:36.602192+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-11-07 07:57:36.677045+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-11-07 07:57:36.694266+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-11-07 07:57:36.737445+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-11-07 07:57:36.75893+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-11-07 07:57:36.766952+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-11-07 07:57:36.768731+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-11-07 07:57:36.778452+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-11-07 07:57:36.804286+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-11-07 07:57:36.809203+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-11-07 07:57:36.810856+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-11-07 07:57:36.82004+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-11-07 07:57:36.843684+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-11-07 07:57:36.860878+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-11-07 07:57:36.863466+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-11-07 07:57:36.875813+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-11-07 07:57:36.877632+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-11-07 07:57:36.879489+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-11-07 07:57:36.881112+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-11-07 07:57:36.893664+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-11-07 07:57:36.895726+00');
INSERT INTO public.schema_migrations VALUES ('0022_thread_outcome_and_cause.sql', '9a8507f1b42457d2c44d568a2bd60d868f923613f8c83acb2be7f9104041cc88', '2026-11-07 07:57:36.897651+00');
INSERT INTO public.schema_migrations VALUES ('0023_summaries.sql', 'da452cf41917f9cc59c3a9d71e4114bf5179d3c5493669a5c7ce83ea13e0fb77', '2026-11-07 07:57:36.899245+00');
INSERT INTO public.schema_migrations VALUES ('0024_owner_repair.sql', 'de78024aceb993e7822500bb13d17d034b0123cdf67225fc9c8d82e16164e3be', '2026-11-07 07:57:36.911881+00');
INSERT INTO public.schema_migrations VALUES ('0025_canon.sql', '692a149bab93cd46b4bff801fc8ca0d857dc72ae88ca73471b33668cc2e694e3', '2026-11-07 07:57:36.924749+00');
INSERT INTO public.schema_migrations VALUES ('0026_canon_facts.sql', '5998bd556819cc977b9c0dabf9baa53303a5ac0504abb5742f6c3c11f1ec81dd', '2026-11-07 07:57:36.941415+00');
INSERT INTO public.schema_migrations VALUES ('0027_model_usage.sql', 'a0397dba46c52771feba09a4ce8f7fa1e8307fe36ba1a5fbaf4ad1489bfda2c6', '2026-11-07 07:57:36.946934+00');
INSERT INTO public.schema_migrations VALUES ('0028_reveal_checks.sql', '24d4cea55f72664dd0370f396582daa93d69881fc5f06dd5de46bfc295eb3325', '2026-11-07 07:57:36.948646+00');
INSERT INTO public.schema_migrations VALUES ('0029_state_dismiss.sql', '6d6c3162977286ea96ad0860e74e102fcd0fe24847a4aa49d9d72d9c16f3227d', '2026-11-07 07:57:36.950607+00');
INSERT INTO public.schema_migrations VALUES ('0030_extract_v17.sql', '2b5769d94c377d07b2ae6b7e1d4832211a9e9850443b54e5ffa057900ca2fb58', '2026-11-07 07:57:36.952422+00');
INSERT INTO public.schema_migrations VALUES ('0031_entity_exclude.sql', '46ca60d3b6c3d2c0e1af72a4d4581c57e8ae1bd156f437a277235cdb18fbd055', '2026-11-07 07:57:36.954805+00');
INSERT INTO public.schema_migrations VALUES ('0032_replies_only.sql', 'def2b7e56a5f87f72763664df386407be7e7df8fc4725d7c223fd40d187bd1a3', '2026-11-07 07:57:36.956763+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a1b503-5a37-779a-9de8-771da34d37fd', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '70cd448a-58da-4fea-8704-2391be23f338', 'message', '2026-11-07 07:57:38.23094+00');
INSERT INTO public.source_object VALUES ('01a1b503-5a39-7299-88d4-5da2d2142afc', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '6d7ee8d3-4979-49a3-8617-5d7b6a93e670', 'message', '2026-11-07 07:57:38.23094+00');
INSERT INTO public.source_object VALUES ('01a1b503-5a3a-789b-abf9-5c2e5335a58b', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'c95b397e-473b-46a2-b2ea-6b97401b9c5e', 'message', '2026-11-07 07:57:38.23094+00');
INSERT INTO public.source_object VALUES ('01a1b503-5a3b-794c-aaea-24910fbfd8ba', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'b3da5d55-e823-4892-8104-c1423e7442a4', 'message', '2026-11-07 07:57:38.23094+00');
INSERT INTO public.source_object VALUES ('01a1b503-5a86-714f-89eb-b9768ef6d688', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'f06fa6c1-f1f1-4193-bd75-78001bee73f3', 'message', '2026-11-07 07:57:38.309858+00');
INSERT INTO public.source_object VALUES ('01a1b503-5a87-75dd-9881-299075fda5bd', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'c30ed147-7dd3-488b-bf9e-3791d614131e', 'message', '2026-11-07 07:57:38.309858+00');
INSERT INTO public.source_object VALUES ('01a1b503-5a88-7303-b974-37810aa9b940', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '996bd6eb-d0e6-446a-9b4b-83703cd77dde', 'message', '2026-11-07 07:57:38.309858+00');
INSERT INTO public.source_object VALUES ('01a1b503-5a89-72e1-932b-6b649638453f', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'a2cbea71-1ec5-4040-9d3b-cca020053637', 'message', '2026-11-07 07:57:38.309858+00');
INSERT INTO public.source_object VALUES ('01a1b503-5ab3-77e8-b73f-7e57ae298ba8', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '7fa62829-c1e7-4483-b91d-db55407aa75f', 'message', '2026-11-07 07:57:38.354652+00');
INSERT INTO public.source_object VALUES ('01a1b503-5ab4-7756-924d-722bd66ff048', '01a1b503-5a30-72cb-9fa1-2afca8014f95', 'fc31de31-a026-4d42-80e1-1fd90dec0422', 'message', '2026-11-07 07:57:38.354652+00');
INSERT INTO public.source_object VALUES ('01a1b503-5ab5-77d0-bcbd-c849303e3e2f', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '549d9b75-9af3-44ed-9487-f6f42ab3b3eb', 'message', '2026-11-07 07:57:38.354652+00');
INSERT INTO public.source_object VALUES ('01a1b503-5ab5-7c79-933c-821e2c40359f', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '882cdb55-4602-48de-acd0-67f63b04119f', 'message', '2026-11-07 07:57:38.354652+00');
INSERT INTO public.source_object VALUES ('01a1b503-5ada-77ec-a4b5-d0da24802ece', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '40385c3d-40de-4832-92a7-71a158bb74ff', 'message', '2026-11-07 07:57:38.394074+00');
INSERT INTO public.source_object VALUES ('01a1b503-62e6-7ab6-a94d-1558400e34d1', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '8a3be60a-4e0d-4b60-b42f-04f0f6aa260a', 'message', '2026-11-07 07:57:40.452615+00');
INSERT INTO public.source_object VALUES ('01a1b503-62e6-73d0-b736-152e003b0190', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7', 'message', '2026-11-07 07:57:40.452615+00');
INSERT INTO public.source_object VALUES ('01a1b503-630b-705d-a198-f13ae6615e52', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2', 'message', '2026-11-07 07:57:40.491227+00');
INSERT INTO public.source_object VALUES ('01a1b503-632f-7815-a712-9c4bfeaea67e', '01a1b503-5a30-72cb-9fa1-2afca8014f95', '0c5da5ea-720e-4f0c-b84b-498d8b8a6167', 'message', '2026-11-07 07:57:40.52419+00');
INSERT INTO public.source_object VALUES ('01a1b503-6747-78cb-97ad-fb0ca173a18b', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '331805f3-83d9-4257-b3cc-9b9141400d94', 'message', '2026-11-07 07:57:41.575328+00');
INSERT INTO public.source_object VALUES ('01a1b503-6748-7aa9-9d53-dc55b8096064', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', 'cd0c29fa-9be6-4048-a1ae-ad337afd6f85', 'message', '2026-11-07 07:57:41.575328+00');
INSERT INTO public.source_object VALUES ('01a1b503-6749-79ab-b078-d94e3369a135', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', 'e7b82fc7-1321-40d7-8142-b09a42bfa3ec', 'message', '2026-11-07 07:57:41.575328+00');
INSERT INTO public.source_object VALUES ('01a1b503-674a-7c4d-a78e-d7af23708c03', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', 'f4978ecf-4707-4df8-80c3-dddfb653b7e9', 'message', '2026-11-07 07:57:41.575328+00');
INSERT INTO public.source_object VALUES ('01a1b503-674b-74ce-a711-bc078c8fe2c2', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '3ab7c5fb-b128-4c9e-ab39-16245bf1566a', 'message', '2026-11-07 07:57:41.575328+00');
INSERT INTO public.source_object VALUES ('01a1b503-6752-7e75-aefe-e80b24290a09', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '9903f26e-1644-438b-920c-71a4aa2f3aac', 'message', '2026-11-07 07:57:41.575328+00');
INSERT INTO public.source_object VALUES ('01a1b503-6754-79a4-8758-a26ac493070c', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '7b599dea-63be-4140-b759-7d4991883d79', 'message', '2026-11-07 07:57:41.575328+00');
INSERT INTO public.source_object VALUES ('01a1b503-6754-7808-b923-730155e7da59', '01a1b503-673b-74ee-9196-ed4ad8d4b49f', 'f2a9b2ae-3129-4125-85f4-f9fa966b7013', 'message', '2026-11-07 07:57:41.575328+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a1b503-5a38-77ec-8162-15882f38fe84', '01a1b503-5a37-779a-9de8-771da34d37fd', '65f847d9f7017d97e6d1cb92f04cb050257988a6ef9b03b347ebeb5633a5aeb2', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "70cd448a-58da-4fea-8704-2391be23f338", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:38.23094+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5a3b-7495-99a7-605ad39cf6ff', '01a1b503-5a3a-789b-abf9-5c2e5335a58b', '638cb8257d8b7271fd1435932a97af74f1e23d4b479b90238387ff1cc1fc7b3a', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "c95b397e-473b-46a2-b2ea-6b97401b9c5e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:38.23094+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5a3a-7f10-a68c-6bcfaa588817', '01a1b503-5a39-7299-88d4-5da2d2142afc', '3e9774abad2195b81a7fed51fad8234ed4a7b850107f7caca7edad217e0bff1a', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "specialComments": []}', '2026-11-07 07:57:38.23094+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5a86-7ba5-a8a6-c40fe3f4215f', '01a1b503-5a86-714f-89eb-b9768ef6d688', 'c7ca04a0b2da85805cad7f4fdd25d7520efd94c9e9d53d2745fe20b083c544fb', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "f06fa6c1-f1f1-4193-bd75-78001bee73f3", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:38.309858+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5a89-7b86-a6c2-5a6c3573e7a9', '01a1b503-5a88-7303-b974-37810aa9b940', '19653fd2cc47be59352f7f37395cb55cf0cd03016846120ab76ffcd478632c53', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "996bd6eb-d0e6-446a-9b4b-83703cd77dde", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:38.309858+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5ab3-7136-9826-415cda22b3ca', '01a1b503-5ab3-77e8-b73f-7e57ae298ba8', '1d59fa3d6e5e01cfc95291f1b7febd3d93f2ada9f0158c41ac5af938eb4eb23a', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "7fa62829-c1e7-4483-b91d-db55407aa75f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:38.354652+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5a88-7590-bd48-0a5829f8be50', '01a1b503-5a87-75dd-9881-299075fda5bd', 'db497aa6518625416281e1fd845ca7b5c396a91be5b3b17e378845933a58e341', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "c30ed147-7dd3-488b-bf9e-3791d614131e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c30ed147-7dd3-488b-bf9e-3791d614131e", "specialComments": []}', '2026-11-07 07:57:38.309858+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5ab5-749f-b0fc-965a248e61f8', '01a1b503-5ab5-77d0-bcbd-c849303e3e2f', '02859d31959e548854aa42b29aeec2238788379bf417482f1f5cdf894056b3a3', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:38.354652+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5a8a-71df-ab4b-338ad64371a0', '01a1b503-5a89-72e1-932b-6b649638453f', '4bc10a063e87042cdb8f1dd78bd175d49c3371991e3c008c2456d4e1b317cad8', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "a2cbea71-1ec5-4040-9d3b-cca020053637", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a2cbea71-1ec5-4040-9d3b-cca020053637", "specialComments": []}', '2026-11-07 07:57:38.309858+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5ab4-7655-b423-5dc052054436', '01a1b503-5ab4-7756-924d-722bd66ff048', '28ea885e98c3b3bd20d41c22124ef6b4097ac91ac86dc9503d77ba0075cc335c', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "fc31de31-a026-4d42-80e1-1fd90dec0422", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "fc31de31-a026-4d42-80e1-1fd90dec0422", "specialComments": []}', '2026-11-07 07:57:38.354652+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5adb-73bf-baff-30c66e290592', '01a1b503-5ada-77ec-a4b5-d0da24802ece', '56834ab93fd8fe041d04d197594830e0dce74b2f6064b50ce1d39d767c1645a1', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "40385c3d-40de-4832-92a7-71a158bb74ff", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:38.394074+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5ab6-7513-bc12-4f96b7689363', '01a1b503-5ab5-7c79-933c-821e2c40359f', 'c8351031ff3c625c826c74c7a9d8c50d6c7cee647c011240f12901db0c70d248', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "882cdb55-4602-48de-acd0-67f63b04119f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "882cdb55-4602-48de-acd0-67f63b04119f", "specialComments": []}', '2026-11-07 07:57:38.354652+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-62e7-79ce-9fb5-6ccf3bfbe5e7', '01a1b503-62e6-73d0-b736-152e003b0190', '9e2de1060d74ed8c1871bf8a881759b6cd78bbe0d1a8bcc5f0bad40325008ca2', 'And the compass?', '{"name": null, "role": "user", "chatId": "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:40.452615+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-62e6-7719-9da9-289c6668aa35', '01a1b503-62e6-7ab6-a94d-1558400e34d1', 'bc9b065c4c970811014b8cd163484a304e9aacb5c746b288ccf0e1cf4831fa06', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", "specialComments": []}', '2026-11-07 07:57:40.452615+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-5a3c-7db8-bc44-d742c1edd6a6', '01a1b503-5a3b-794c-aaea-24910fbfd8ba', 'cfe1e656056acb7b028b6f6a0b1bac65a5473408c6262df04b848f53be865956', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "b3da5d55-e823-4892-8104-c1423e7442a4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b3da5d55-e823-4892-8104-c1423e7442a4", "specialComments": []}', '2026-11-07 07:57:38.23094+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-62e5-70f0-9059-639da7836d39', '01a1b503-5a3b-794c-aaea-24910fbfd8ba', 'ed5d1d1f75e65aa66d802ac1df08f935cbe9ad992e30026db413d930ef5386b8', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "b3da5d55-e823-4892-8104-c1423e7442a4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b3da5d55-e823-4892-8104-c1423e7442a4", "specialComments": []}', '2026-11-07 07:57:40.452615+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-632e-71d7-b838-3548a004dfa5', '01a1b503-5ab3-77e8-b73f-7e57ae298ba8', 'c1dcbbdbf05756b484f3c5650057fd82d0e2b013e6cbe32c0eb7e3ad4b0e10a0', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "7fa62829-c1e7-4483-b91d-db55407aa75f", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:40.52419+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-632f-7255-a524-b3b4453890f9', '01a1b503-632f-7815-a712-9c4bfeaea67e', 'ce31c892f7f80e940383b129aa2ba2d656af81978c37d286a9800d7d8aa8b063', 'Let''s go.', '{"name": null, "role": "user", "chatId": "0c5da5ea-720e-4f0c-b84b-498d8b8a6167", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:40.52419+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-632f-7fc8-b29a-22d2b22c7074', '01a1b503-630b-705d-a198-f13ae6615e52', '91f0a780fda81328b9f498ec57ec9326890791254e1ab84720215f43754821b9', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "specialComments": []}', '2026-11-07 07:57:40.52419+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-630c-7932-ae53-4f2c9f277bd4', '01a1b503-630b-705d-a198-f13ae6615e52', 'd6ff49f9de5835ddcc7d01e3c474e3e65af5179c7118f745c8dba6ff8d39d99e', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "specialComments": []}', '2026-11-07 07:57:40.491227+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-6748-78ff-8ced-e4552c25c878', '01a1b503-6747-78cb-97ad-fb0ca173a18b', 'ecec626fad5202ee7eb5546110058a5544099309ceb271bfe2388616b7ea1898', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "331805f3-83d9-4257-b3cc-9b9141400d94", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:41.575328+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-674a-77ef-87a7-01dd0bfc32ea', '01a1b503-6749-79ab-b078-d94e3369a135', 'c8491994a68b6172abb2981cf1fc0875f897d3a1e1788b7505b600ee170da9f1', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "e7b82fc7-1321-40d7-8142-b09a42bfa3ec", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:41.575328+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-6751-7f95-a588-4d829ef73cc7', '01a1b503-674b-74ce-a711-bc078c8fe2c2', '83baad89627c4c3f13a85b984b87762073e27609c221cd43b252c1777f02427a', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "3ab7c5fb-b128-4c9e-ab39-16245bf1566a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:41.575328+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-6754-7cab-8462-4bfed95733cb', '01a1b503-6754-79a4-8758-a26ac493070c', 'f84ce26081c4ffa6eacb43ebec519cb2509537b28dbf95a9182e53269db7aaa9', '{{specialcomment::branchedfrom::98405043-f67e-457a-89e2-f2af77e95f73::Harbor route::c30ed147-7dd3-488b-bf9e-3791d614131e::}}', '{"name": null, "role": "char", "chatId": "7b599dea-63be-4140-b759-7d4991883d79", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::98405043-f67e-457a-89e2-f2af77e95f73::Harbor route::c30ed147-7dd3-488b-bf9e-3791d614131e::}}"]}', '2026-11-07 07:57:41.575328+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-6754-7d15-8e9d-b2e32482c8d4', '01a1b503-6754-7808-b923-730155e7da59', 'e39d372832d5889f2441e52849dfd3a995f6b5b3a6a954273cc986cb45258740', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "f2a9b2ae-3129-4125-85f4-f9fa966b7013", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-11-07 07:57:41.575328+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-6753-741e-b987-e504cab053b5', '01a1b503-6752-7e75-aefe-e80b24290a09', 'c4a5fa731d4d479dd06f4deccb5e608b1ac5047254e993228b7ee3e1a00bcba0', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "9903f26e-1644-438b-920c-71a4aa2f3aac", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c30ed147-7dd3-488b-bf9e-3791d614131e", "specialComments": []}', '2026-11-07 07:57:41.575328+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-6749-77c5-b971-23e10117bbe7', '01a1b503-6748-7aa9-9d53-dc55b8096064', '27b6814b57f61e918bd60a33e7cc5c89bb990e651e502eba106d0cded7268bba', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "cd0c29fa-9be6-4048-a1ae-ad337afd6f85", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "specialComments": []}', '2026-11-07 07:57:41.575328+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a1b503-674b-76c1-9e42-b0fe12a99c0b', '01a1b503-674a-7c4d-a78e-d7af23708c03', '406068d2201d0bd07b560172498283f1b5f1ac9449952211bcbadf084a468e56', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "f4978ecf-4707-4df8-80c3-dddfb653b7e9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b3da5d55-e823-4892-8104-c1423e7442a4", "specialComments": []}', '2026-11-07 07:57:41.575328+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: summary; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a', '[{"op": "insert", "after": ["b3da5d55-e823-4892-8104-c1423e7442a4", "cfe1e656056acb7b028b6f6a0b1bac65a5473408c6262df04b848f53be865956"], "member": ["f06fa6c1-f1f1-4193-bd75-78001bee73f3", "c7ca04a0b2da85805cad7f4fdd25d7520efd94c9e9d53d2745fe20b083c544fb"]}, {"op": "insert", "after": ["f06fa6c1-f1f1-4193-bd75-78001bee73f3", "c7ca04a0b2da85805cad7f4fdd25d7520efd94c9e9d53d2745fe20b083c544fb"], "member": ["c30ed147-7dd3-488b-bf9e-3791d614131e", "db497aa6518625416281e1fd845ca7b5c396a91be5b3b17e378845933a58e341"]}, {"op": "insert", "after": ["c30ed147-7dd3-488b-bf9e-3791d614131e", "db497aa6518625416281e1fd845ca7b5c396a91be5b3b17e378845933a58e341"], "member": ["996bd6eb-d0e6-446a-9b4b-83703cd77dde", "19653fd2cc47be59352f7f37395cb55cf0cd03016846120ab76ffcd478632c53"]}, {"op": "insert", "after": ["996bd6eb-d0e6-446a-9b4b-83703cd77dde", "19653fd2cc47be59352f7f37395cb55cf0cd03016846120ab76ffcd478632c53"], "member": ["a2cbea71-1ec5-4040-9d3b-cca020053637", "4bc10a063e87042cdb8f1dd78bd175d49c3371991e3c008c2456d4e1b317cad8"]}]', '[{"new": ["f06fa6c1-f1f1-4193-bd75-78001bee73f3", "c7ca04a0b2da85805cad7f4fdd25d7520efd94c9e9d53d2745fe20b083c544fb"], "old": null, "kind": "append", "position": 4, "host_logical_id": "f06fa6c1-f1f1-4193-bd75-78001bee73f3"}, {"new": ["c30ed147-7dd3-488b-bf9e-3791d614131e", "db497aa6518625416281e1fd845ca7b5c396a91be5b3b17e378845933a58e341"], "old": null, "kind": "append", "position": 5, "host_logical_id": "c30ed147-7dd3-488b-bf9e-3791d614131e"}, {"new": ["996bd6eb-d0e6-446a-9b4b-83703cd77dde", "19653fd2cc47be59352f7f37395cb55cf0cd03016846120ab76ffcd478632c53"], "old": null, "kind": "append", "position": 6, "host_logical_id": "996bd6eb-d0e6-446a-9b4b-83703cd77dde"}, {"new": ["a2cbea71-1ec5-4040-9d3b-cca020053637", "4bc10a063e87042cdb8f1dd78bd175d49c3371991e3c008c2456d4e1b317cad8"], "old": null, "kind": "append", "position": 7, "host_logical_id": "a2cbea71-1ec5-4040-9d3b-cca020053637"}]', '01a1b503-5a8d-702f-87d7-4077449e498e', '2026-11-07 07:57:38.309858+00');
INSERT INTO public.worldline_append VALUES (2, '01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a', '[{"op": "insert", "after": ["a2cbea71-1ec5-4040-9d3b-cca020053637", "4bc10a063e87042cdb8f1dd78bd175d49c3371991e3c008c2456d4e1b317cad8"], "member": ["7fa62829-c1e7-4483-b91d-db55407aa75f", "1d59fa3d6e5e01cfc95291f1b7febd3d93f2ada9f0158c41ac5af938eb4eb23a"]}, {"op": "insert", "after": ["7fa62829-c1e7-4483-b91d-db55407aa75f", "1d59fa3d6e5e01cfc95291f1b7febd3d93f2ada9f0158c41ac5af938eb4eb23a"], "member": ["fc31de31-a026-4d42-80e1-1fd90dec0422", "28ea885e98c3b3bd20d41c22124ef6b4097ac91ac86dc9503d77ba0075cc335c"]}, {"op": "insert", "after": ["fc31de31-a026-4d42-80e1-1fd90dec0422", "28ea885e98c3b3bd20d41c22124ef6b4097ac91ac86dc9503d77ba0075cc335c"], "member": ["549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "02859d31959e548854aa42b29aeec2238788379bf417482f1f5cdf894056b3a3"]}, {"op": "insert", "after": ["549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "02859d31959e548854aa42b29aeec2238788379bf417482f1f5cdf894056b3a3"], "member": ["882cdb55-4602-48de-acd0-67f63b04119f", "c8351031ff3c625c826c74c7a9d8c50d6c7cee647c011240f12901db0c70d248"]}]', '[{"new": ["7fa62829-c1e7-4483-b91d-db55407aa75f", "1d59fa3d6e5e01cfc95291f1b7febd3d93f2ada9f0158c41ac5af938eb4eb23a"], "old": null, "kind": "append", "position": 8, "host_logical_id": "7fa62829-c1e7-4483-b91d-db55407aa75f"}, {"new": ["fc31de31-a026-4d42-80e1-1fd90dec0422", "28ea885e98c3b3bd20d41c22124ef6b4097ac91ac86dc9503d77ba0075cc335c"], "old": null, "kind": "append", "position": 9, "host_logical_id": "fc31de31-a026-4d42-80e1-1fd90dec0422"}, {"new": ["549d9b75-9af3-44ed-9487-f6f42ab3b3eb", "02859d31959e548854aa42b29aeec2238788379bf417482f1f5cdf894056b3a3"], "old": null, "kind": "append", "position": 10, "host_logical_id": "549d9b75-9af3-44ed-9487-f6f42ab3b3eb"}, {"new": ["882cdb55-4602-48de-acd0-67f63b04119f", "c8351031ff3c625c826c74c7a9d8c50d6c7cee647c011240f12901db0c70d248"], "old": null, "kind": "append", "position": 11, "host_logical_id": "882cdb55-4602-48de-acd0-67f63b04119f"}]', '01a1b503-5ab9-700b-b12c-0d91f212ffa2', '2026-11-07 07:57:38.354652+00');
INSERT INTO public.worldline_append VALUES (3, '01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a', '[{"op": "insert", "after": ["882cdb55-4602-48de-acd0-67f63b04119f", "c8351031ff3c625c826c74c7a9d8c50d6c7cee647c011240f12901db0c70d248"], "member": ["40385c3d-40de-4832-92a7-71a158bb74ff", "56834ab93fd8fe041d04d197594830e0dce74b2f6064b50ce1d39d767c1645a1"]}]', '[{"new": ["40385c3d-40de-4832-92a7-71a158bb74ff", "56834ab93fd8fe041d04d197594830e0dce74b2f6064b50ce1d39d767c1645a1"], "old": null, "kind": "append", "position": 12, "host_logical_id": "40385c3d-40de-4832-92a7-71a158bb74ff"}]', '01a1b503-5ae0-72ff-8f24-fdd4585bd128', '2026-11-07 07:57:38.394074+00');
INSERT INTO public.worldline_append VALUES (4, '01a1b503-62eb-7ec2-9b48-a822fb9e682e', '[{"op": "insert", "after": ["80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "9e2de1060d74ed8c1871bf8a881759b6cd78bbe0d1a8bcc5f0bad40325008ca2"], "member": ["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "d6ff49f9de5835ddcc7d01e3c474e3e65af5179c7118f745c8dba6ff8d39d99e"]}]', '[{"new": ["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "d6ff49f9de5835ddcc7d01e3c474e3e65af5179c7118f745c8dba6ff8d39d99e"], "old": null, "kind": "append", "position": 15, "host_logical_id": "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2"}]', '01a1b503-630f-750a-9c44-a73b4a57b46d', '2026-11-07 07:57:40.491227+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a', 1, '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{}', 'import', '71798870fa9f256181e078fcfb6538cda23e9a63f885fdf5f4256403c43a2be1', '{"ops": [{"op": "set", "members": [["70cd448a-58da-4fea-8704-2391be23f338", "65f847d9f7017d97e6d1cb92f04cb050257988a6ef9b03b347ebeb5633a5aeb2"], ["6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "3e9774abad2195b81a7fed51fad8234ed4a7b850107f7caca7edad217e0bff1a"], ["c95b397e-473b-46a2-b2ea-6b97401b9c5e", "638cb8257d8b7271fd1435932a97af74f1e23d4b479b90238387ff1cc1fc7b3a"], ["b3da5d55-e823-4892-8104-c1423e7442a4", "cfe1e656056acb7b028b6f6a0b1bac65a5473408c6262df04b848f53be865956"]]}], "changes": [{"new": ["70cd448a-58da-4fea-8704-2391be23f338", "65f847d9f7017d97e6d1cb92f04cb050257988a6ef9b03b347ebeb5633a5aeb2"], "old": null, "kind": "append", "position": 0, "host_logical_id": "70cd448a-58da-4fea-8704-2391be23f338"}, {"new": ["6d7ee8d3-4979-49a3-8617-5d7b6a93e670", "3e9774abad2195b81a7fed51fad8234ed4a7b850107f7caca7edad217e0bff1a"], "old": null, "kind": "append", "position": 1, "host_logical_id": "6d7ee8d3-4979-49a3-8617-5d7b6a93e670"}, {"new": ["c95b397e-473b-46a2-b2ea-6b97401b9c5e", "638cb8257d8b7271fd1435932a97af74f1e23d4b479b90238387ff1cc1fc7b3a"], "old": null, "kind": "append", "position": 2, "host_logical_id": "c95b397e-473b-46a2-b2ea-6b97401b9c5e"}, {"new": ["b3da5d55-e823-4892-8104-c1423e7442a4", "cfe1e656056acb7b028b6f6a0b1bac65a5473408c6262df04b848f53be865956"], "old": null, "kind": "append", "position": 3, "host_logical_id": "b3da5d55-e823-4892-8104-c1423e7442a4"}]}', '2026-11-07 07:57:38.23094+00', '01a1b503-5a3d-7154-8287-0d5972d7c509');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a1b503-62eb-7ec2-9b48-a822fb9e682e', 2, '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{01a1b503-5a3f-7cb0-a5e6-cc86cc01ec4a}', 'edit', '2595c91fd3c7833bc6be60710a9f8106d5ab52c29f81967bfee7e4f2b6947d5e', '{"ops": [{"op": "replace", "to": ["b3da5d55-e823-4892-8104-c1423e7442a4", "ed5d1d1f75e65aa66d802ac1df08f935cbe9ad992e30026db413d930ef5386b8"], "from": ["b3da5d55-e823-4892-8104-c1423e7442a4", "cfe1e656056acb7b028b6f6a0b1bac65a5473408c6262df04b848f53be865956"]}, {"op": "insert", "after": ["40385c3d-40de-4832-92a7-71a158bb74ff", "56834ab93fd8fe041d04d197594830e0dce74b2f6064b50ce1d39d767c1645a1"], "member": ["8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", "bc9b065c4c970811014b8cd163484a304e9aacb5c746b288ccf0e1cf4831fa06"]}, {"op": "insert", "after": ["8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", "bc9b065c4c970811014b8cd163484a304e9aacb5c746b288ccf0e1cf4831fa06"], "member": ["80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "9e2de1060d74ed8c1871bf8a881759b6cd78bbe0d1a8bcc5f0bad40325008ca2"]}], "changes": [{"new": ["b3da5d55-e823-4892-8104-c1423e7442a4", "ed5d1d1f75e65aa66d802ac1df08f935cbe9ad992e30026db413d930ef5386b8"], "old": ["b3da5d55-e823-4892-8104-c1423e7442a4", "cfe1e656056acb7b028b6f6a0b1bac65a5473408c6262df04b848f53be865956"], "kind": "edit", "position": 3, "host_logical_id": "b3da5d55-e823-4892-8104-c1423e7442a4"}, {"new": ["8a3be60a-4e0d-4b60-b42f-04f0f6aa260a", "bc9b065c4c970811014b8cd163484a304e9aacb5c746b288ccf0e1cf4831fa06"], "old": null, "kind": "append", "position": 13, "host_logical_id": "8a3be60a-4e0d-4b60-b42f-04f0f6aa260a"}, {"new": ["80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7", "9e2de1060d74ed8c1871bf8a881759b6cd78bbe0d1a8bcc5f0bad40325008ca2"], "old": null, "kind": "append", "position": 14, "host_logical_id": "80c4db3e-8acf-4bb3-8ccb-f8553fec4ed7"}]}', '2026-11-07 07:57:40.452615+00', '01a1b503-62e8-7a94-a446-a7e658651b4e');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a1b503-6333-7a9b-92c4-069cd38d61ac', 3, '01a1b503-5a30-72cb-9fa1-2afca8014f95', '{01a1b503-62eb-7ec2-9b48-a822fb9e682e}', 'reconciliation', '4982d9a6a4fc353f3ebb5b98808c56080987645d80e85d2241504f4db611152a', '{"ops": [{"op": "replace", "to": ["7fa62829-c1e7-4483-b91d-db55407aa75f", "c1dcbbdbf05756b484f3c5650057fd82d0e2b013e6cbe32c0eb7e3ad4b0e10a0"], "from": ["7fa62829-c1e7-4483-b91d-db55407aa75f", "1d59fa3d6e5e01cfc95291f1b7febd3d93f2ada9f0158c41ac5af938eb4eb23a"]}, {"op": "replace", "to": ["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "91f0a780fda81328b9f498ec57ec9326890791254e1ab84720215f43754821b9"], "from": ["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "d6ff49f9de5835ddcc7d01e3c474e3e65af5179c7118f745c8dba6ff8d39d99e"]}, {"op": "insert", "after": ["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "91f0a780fda81328b9f498ec57ec9326890791254e1ab84720215f43754821b9"], "member": ["0c5da5ea-720e-4f0c-b84b-498d8b8a6167", "ce31c892f7f80e940383b129aa2ba2d656af81978c37d286a9800d7d8aa8b063"]}], "changes": [{"new": ["7fa62829-c1e7-4483-b91d-db55407aa75f", "c1dcbbdbf05756b484f3c5650057fd82d0e2b013e6cbe32c0eb7e3ad4b0e10a0"], "old": ["7fa62829-c1e7-4483-b91d-db55407aa75f", "1d59fa3d6e5e01cfc95291f1b7febd3d93f2ada9f0158c41ac5af938eb4eb23a"], "kind": "disable", "position": 8, "host_logical_id": "7fa62829-c1e7-4483-b91d-db55407aa75f"}, {"new": ["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "91f0a780fda81328b9f498ec57ec9326890791254e1ab84720215f43754821b9"], "old": ["7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2", "d6ff49f9de5835ddcc7d01e3c474e3e65af5179c7118f745c8dba6ff8d39d99e"], "kind": "swipe", "position": 15, "host_logical_id": "7561cb30-2b36-4f4f-bfd1-36e04ffe4ef2"}, {"new": ["0c5da5ea-720e-4f0c-b84b-498d8b8a6167", "ce31c892f7f80e940383b129aa2ba2d656af81978c37d286a9800d7d8aa8b063"], "old": null, "kind": "append", "position": 16, "host_logical_id": "0c5da5ea-720e-4f0c-b84b-498d8b8a6167"}]}', '2026-11-07 07:57:40.52419+00', '01a1b503-6331-763a-9179-cf1faaf118d4');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a1b503-6756-7f28-9160-637f47941c22', 4, '01a1b503-673b-74ee-9196-ed4ad8d4b49f', '{}', 'branch', '8636056fd57ccf27c01355270cb77626fad0ffa33436bfc9c76e224a0997477d', '{"ops": [{"op": "set", "members": [["331805f3-83d9-4257-b3cc-9b9141400d94", "ecec626fad5202ee7eb5546110058a5544099309ceb271bfe2388616b7ea1898"], ["cd0c29fa-9be6-4048-a1ae-ad337afd6f85", "27b6814b57f61e918bd60a33e7cc5c89bb990e651e502eba106d0cded7268bba"], ["e7b82fc7-1321-40d7-8142-b09a42bfa3ec", "c8491994a68b6172abb2981cf1fc0875f897d3a1e1788b7505b600ee170da9f1"], ["f4978ecf-4707-4df8-80c3-dddfb653b7e9", "406068d2201d0bd07b560172498283f1b5f1ac9449952211bcbadf084a468e56"], ["3ab7c5fb-b128-4c9e-ab39-16245bf1566a", "83baad89627c4c3f13a85b984b87762073e27609c221cd43b252c1777f02427a"], ["9903f26e-1644-438b-920c-71a4aa2f3aac", "c4a5fa731d4d479dd06f4deccb5e608b1ac5047254e993228b7ee3e1a00bcba0"], ["7b599dea-63be-4140-b759-7d4991883d79", "f84ce26081c4ffa6eacb43ebec519cb2509537b28dbf95a9182e53269db7aaa9"], ["f2a9b2ae-3129-4125-85f4-f9fa966b7013", "e39d372832d5889f2441e52849dfd3a995f6b5b3a6a954273cc986cb45258740"]]}], "changes": [{"new": ["331805f3-83d9-4257-b3cc-9b9141400d94", "ecec626fad5202ee7eb5546110058a5544099309ceb271bfe2388616b7ea1898"], "old": null, "kind": "append", "position": 0, "host_logical_id": "331805f3-83d9-4257-b3cc-9b9141400d94"}, {"new": ["cd0c29fa-9be6-4048-a1ae-ad337afd6f85", "27b6814b57f61e918bd60a33e7cc5c89bb990e651e502eba106d0cded7268bba"], "old": null, "kind": "append", "position": 1, "host_logical_id": "cd0c29fa-9be6-4048-a1ae-ad337afd6f85"}, {"new": ["e7b82fc7-1321-40d7-8142-b09a42bfa3ec", "c8491994a68b6172abb2981cf1fc0875f897d3a1e1788b7505b600ee170da9f1"], "old": null, "kind": "append", "position": 2, "host_logical_id": "e7b82fc7-1321-40d7-8142-b09a42bfa3ec"}, {"new": ["f4978ecf-4707-4df8-80c3-dddfb653b7e9", "406068d2201d0bd07b560172498283f1b5f1ac9449952211bcbadf084a468e56"], "old": null, "kind": "append", "position": 3, "host_logical_id": "f4978ecf-4707-4df8-80c3-dddfb653b7e9"}, {"new": ["3ab7c5fb-b128-4c9e-ab39-16245bf1566a", "83baad89627c4c3f13a85b984b87762073e27609c221cd43b252c1777f02427a"], "old": null, "kind": "append", "position": 4, "host_logical_id": "3ab7c5fb-b128-4c9e-ab39-16245bf1566a"}, {"new": ["9903f26e-1644-438b-920c-71a4aa2f3aac", "c4a5fa731d4d479dd06f4deccb5e608b1ac5047254e993228b7ee3e1a00bcba0"], "old": null, "kind": "append", "position": 5, "host_logical_id": "9903f26e-1644-438b-920c-71a4aa2f3aac"}, {"new": ["7b599dea-63be-4140-b759-7d4991883d79", "f84ce26081c4ffa6eacb43ebec519cb2509537b28dbf95a9182e53269db7aaa9"], "old": null, "kind": "append", "position": 6, "host_logical_id": "7b599dea-63be-4140-b759-7d4991883d79"}, {"new": ["f2a9b2ae-3129-4125-85f4-f9fa966b7013", "e39d372832d5889f2441e52849dfd3a995f6b5b3a6a954273cc986cb45258740"], "old": null, "kind": "append", "position": 7, "host_logical_id": "f2a9b2ae-3129-4125-85f4-f9fa966b7013"}]}', '2026-11-07 07:57:41.575328+00', '01a1b503-6756-70bb-8e35-d212d8c249f5');


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


