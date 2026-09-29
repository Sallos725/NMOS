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
    CONSTRAINT owner_repair_kind_check CHECK ((kind = ANY (ARRAY['thread_close'::text, 'thread_reopen'::text, 'secret_found_out'::text, 'secret_keep'::text, 'fact_retract'::text, 'fact_correct'::text, 'name_split'::text])))
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
    CONSTRAINT projection_generation_kind_check CHECK ((kind = ANY (ARRAY['extract'::text, 'embed'::text, 'summarize'::text])))
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

INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 0, '01a0eb13-b3e6-7082-8972-95961ee4258b', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 1, '01a0eb13-b3e9-7867-a892-8768a67a0310', NULL, 0, 'ab353189b3838bb6971b0ec46d6a5e2f');
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 2, '01a0eb13-b3ea-7545-8529-4c53faf349a0', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 3, '01a0eb13-baa7-7899-8417-8d2af20060e7', NULL, 1, '25c3a98289b86ddd6a6450f989d1ea78');
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 4, '01a0eb13-b42e-715b-bf3c-67f26abb22ad', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 5, '01a0eb13-b42f-7b45-b68b-f6e99aee8575', NULL, 2, '29d7884c84ef3d3ee5bdb78c2d74340f');
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 6, '01a0eb13-b430-76dd-865f-2bd240ffef59', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 7, '01a0eb13-b431-73a9-9d9a-ee0695e5d1bf', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 8, '01a0eb13-bb00-72ff-944e-65602522f363', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 9, '01a0eb13-b460-7dde-a568-c410fee4ff6b', NULL, 3, 'f0f10546cc294e9b9fb6e22c7b1d7b89');
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 10, '01a0eb13-b461-731f-8749-818b3518b01f', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 11, '01a0eb13-b462-7ea7-8cb6-d9dc3d223aea', NULL, 4, '220a8f5f72efd48a5f996bf75d87aa00');
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 12, '01a0eb13-b492-7430-86cd-b47a39ce8d6c', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 13, '01a0eb13-baa8-7229-90ae-544a07a5b6b2', NULL, 5, '5ecf5f8c827299a4794fd4784758caa6');
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 14, '01a0eb13-baa8-7819-b61a-af25dc99d165', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 15, '01a0eb13-bb00-7353-80ff-25d33aedd0a1', NULL, 6, '09f68cd35014a615cc9288106beaf701');
INSERT INTO public.active_membership VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 16, '01a0eb13-bb01-768d-8829-f36aeda1e65e', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 0, '01a0eb13-c113-7398-a2ec-2494fd474f28', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 1, '01a0eb13-c114-7b56-a8d4-29dd29760190', NULL, 0, 'ff301b633269f17558cf81bbd611a8c6');
INSERT INTO public.active_membership VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 2, '01a0eb13-c114-7e23-8431-d39725ec67e5', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 3, '01a0eb13-c115-73ae-b58d-43cd89c53978', NULL, 1, 'a592698990b5c8bc9ae0b53ec65f4c28');
INSERT INTO public.active_membership VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 4, '01a0eb13-c116-7e76-b174-79e561872974', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 5, '01a0eb13-c116-7129-b87e-bfb69ea5b6fa', NULL, 2, 'f14a38d7d1f2db8906e9c3dc5a68a5ea');
INSERT INTO public.active_membership VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 6, '01a0eb13-c117-7967-9118-3c255087ec7a', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 7, '01a0eb13-c117-791d-b1ab-5012376283f8', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0eb13-b9a7-79cd-b452-4bb45923f4fd', '01a0eb13-b462-7ea7-8cb6-d9dc3d223aea', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0eb13-b9c9-7140-a54a-fadd48daf5a0', '01a0eb13-b460-7dde-a568-c410fee4ff6b', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0eb13-b9fe-7cb2-b404-2545d69178bb', '01a0eb13-b42f-7b45-b68b-f6e99aee8575', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0eb13-ba17-7d34-9887-3a61d1bfc65c', '01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0eb13-ba17-7d34-9887-3a61d1bfc65c', '01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0eb13-ba76-76c2-88a0-8baf5cdebd37', '01a0eb13-b3e9-7867-a892-8768a67a0310', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0eb13-ba76-76c2-88a0-8baf5cdebd37', '01a0eb13-b3e9-7867-a892-8768a67a0310', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0eb13-bef0-7d1c-92ef-74ec0615747e', '01a0eb13-bb00-7353-80ff-25d33aedd0a1', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0eb13-bf26-733c-b619-a86814eb7ce9', '01a0eb13-b462-7ea7-8cb6-d9dc3d223aea', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0eb13-bf45-7bed-807b-ada64dd3be18', '01a0eb13-b460-7dde-a568-c410fee4ff6b', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0eb13-bf69-7405-9be4-bd6d0a7be8ff', '01a0eb13-b42f-7b45-b68b-f6e99aee8575', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0eb13-bf85-7ccf-9936-154dc64977b3', '01a0eb13-baa7-7899-8417-8d2af20060e7', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0eb13-bf85-7ccf-9936-154dc64977b3', '01a0eb13-baa7-7899-8417-8d2af20060e7', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0eb13-c41e-7674-b7cb-3325e9b05723', '01a0eb13-c116-7129-b87e-bfb69ea5b6fa', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0eb13-c437-7cdd-b3cf-516b7954a61a', '01a0eb13-c115-73ae-b58d-43cd89c53978', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0eb13-c437-7cdd-b3cf-516b7954a61a', '01a0eb13-c115-73ae-b58d-43cd89c53978', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0eb13-c453-7043-a2ac-82c6f89df041', '01a0eb13-c114-7b56-a8d4-29dd29760190', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0eb13-c453-7043-a2ac-82c6f89df041', '01a0eb13-c114-7b56-a8d4-29dd29760190', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0eb13-b3da-72b7-a357-c47332366c13', 'pocketrisu', NULL, 'd6830dde-55bf-45d1-9dcc-a254722632ca', '2026-09-29 02:52:12.122573+00', NULL, NULL, NULL, '01a0eb13-bb04-7179-80b4-698d30dfc66e', 'de38c534f7763ca07028a52b7851f55cf39fc63a6c6048770b0bd480d568be1f', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL);
INSERT INTO public.conversation VALUES ('01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', 'pocketrisu', NULL, '3627df37-7e08-4f01-a39c-ccfbea70e327', '2026-09-29 02:52:15.501791+00', '01a0eb13-b3da-72b7-a357-c47332366c13', 'd6830dde-55bf-45d1-9dcc-a254722632ca', '7b35be19-c7d4-449f-ab11-4a433d37ad58', '01a0eb13-c119-7fa6-beec-5af802c5ff91', '539c506b8d241201afb46ee7d78eecf0af66968dada431a94d779bcf982cca3e', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0eb13-b9a7-79cd-b452-4bb45923f4fd', '01a0eb13-b462-7ea7-8cb6-d9dc3d223aea', '4f3e19a99cb476d716d0d60730855ea6', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:13.607224+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0eb13-b461-731f-8749-818b3518b01f,01a0eb13-b462-7ea7-8cb6-d9dc3d223aea}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-b9c9-7140-a54a-fadd48daf5a0', '01a0eb13-b460-7dde-a568-c410fee4ff6b', '01925c7bdd6209d1d1ed98c0aa6af8af', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:13.64106+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0eb13-b45f-7415-bf4a-b8be40922afe,01a0eb13-b460-7dde-a568-c410fee4ff6b}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-b9e2-7442-910f-43aadd193a57', '01a0eb13-b431-73a9-9d9a-ee0695e5d1bf', 'f78c40fa678ede044de72b39f91b9a7c', 'extract-v13', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-29 02:52:13.666932+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0eb13-b430-76dd-865f-2bd240ffef59,01a0eb13-b431-73a9-9d9a-ee0695e5d1bf}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-b9fe-7cb2-b404-2545d69178bb', '01a0eb13-b42f-7b45-b68b-f6e99aee8575', 'e89fb51599faa932fcf36d3274015089', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:13.694286+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0eb13-b42e-715b-bf3c-67f26abb22ad,01a0eb13-b42f-7b45-b68b-f6e99aee8575}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-ba17-7d34-9887-3a61d1bfc65c', '01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff', 'd3e6d48c9b2950f66dbee64cdea7cb1c', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:13.719124+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0eb13-b3ea-7545-8529-4c53faf349a0,01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-ba76-76c2-88a0-8baf5cdebd37', '01a0eb13-b3e9-7867-a892-8768a67a0310', 'ab353189b3838bb6971b0ec46d6a5e2f', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:13.814738+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0eb13-b3e6-7082-8972-95961ee4258b,01a0eb13-b3e9-7867-a892-8768a67a0310}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-bef0-7d1c-92ef-74ec0615747e', '01a0eb13-bb00-7353-80ff-25d33aedd0a1', '09f68cd35014a615cc9288106beaf701', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:14.960583+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0eb13-baa8-7819-b61a-af25dc99d165,01a0eb13-bb00-7353-80ff-25d33aedd0a1}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-bf0a-73bd-b591-57a58679f710', '01a0eb13-baa8-7229-90ae-544a07a5b6b2', '5ecf5f8c827299a4794fd4784758caa6', 'extract-v13', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-29 02:52:14.986191+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0eb13-b492-7430-86cd-b47a39ce8d6c,01a0eb13-baa8-7229-90ae-544a07a5b6b2}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-bf26-733c-b619-a86814eb7ce9', '01a0eb13-b462-7ea7-8cb6-d9dc3d223aea', '220a8f5f72efd48a5f996bf75d87aa00', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:15.013924+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0eb13-b461-731f-8749-818b3518b01f,01a0eb13-b462-7ea7-8cb6-d9dc3d223aea}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-bf45-7bed-807b-ada64dd3be18', '01a0eb13-b460-7dde-a568-c410fee4ff6b', 'f0f10546cc294e9b9fb6e22c7b1d7b89', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:15.045734+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0eb13-b430-76dd-865f-2bd240ffef59,01a0eb13-b431-73a9-9d9a-ee0695e5d1bf,01a0eb13-b460-7dde-a568-c410fee4ff6b}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-bf69-7405-9be4-bd6d0a7be8ff', '01a0eb13-b42f-7b45-b68b-f6e99aee8575', '29d7884c84ef3d3ee5bdb78c2d74340f', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:15.081781+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0eb13-b42e-715b-bf3c-67f26abb22ad,01a0eb13-b42f-7b45-b68b-f6e99aee8575}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-bf85-7ccf-9936-154dc64977b3', '01a0eb13-baa7-7899-8417-8d2af20060e7', '25c3a98289b86ddd6a6450f989d1ea78', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:15.109406+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0eb13-b3ea-7545-8529-4c53faf349a0,01a0eb13-baa7-7899-8417-8d2af20060e7}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-c41e-7674-b7cb-3325e9b05723', '01a0eb13-c116-7129-b87e-bfb69ea5b6fa', 'f14a38d7d1f2db8906e9c3dc5a68a5ea', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:16.286361+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0eb13-c116-7e76-b174-79e561872974,01a0eb13-c116-7129-b87e-bfb69ea5b6fa}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-c437-7cdd-b3cf-516b7954a61a', '01a0eb13-c115-73ae-b58d-43cd89c53978', 'a592698990b5c8bc9ae0b53ec65f4c28', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:16.311688+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0eb13-c114-7e23-8431-d39725ec67e5,01a0eb13-c115-73ae-b58d-43cd89c53978}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0eb13-c453-7043-a2ac-82c6f89df041', '01a0eb13-c114-7b56-a8d4-29dd29760190', 'ff301b633269f17558cf81bbd611a8c6', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-29 02:52:16.338926+00', 'extract-285407df4e52d85cbd6a4c44bca5872b', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0eb13-c113-7398-a2ec-2494fd474f28,01a0eb13-c114-7b56-a8d4-29dd29760190}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0eb13-b3ec-7e56-b714-56f51a997b15', '01a0eb13-b3da-72b7-a357-c47332366c13', 'manifest', '34dcac788b8a0a60257215b50b71ac6b386490a94579720a4b2cafd3724a1b80', '01a0eb13-b3da-72b7-a357-c47332366c13:34dcac788b8a0a60257215b50b71ac6b386490a94579720a4b2cafd3724a1b80:manifest', '2026-09-29 02:52:12.129701+00', '{"chat_id": "d6830dde-55bf-45d1-9dcc-a254722632ca", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["d0889bbf-4f07-4fcb-9e44-cefc6991f37e", "b8c4a48dea49380c9a264c28eadd2ee0bbeb1c07c2afed3657df3dfcaa003dcc", "user", null, null, null, 0, null, null], ["a74b56ab-0957-415a-8ac9-649e4c3426cb", "cbaba78c9b10c22bd174781e4946d204509c1faf5bfa7bea444c4b174f524291", "char", null, null, null, 0, "a74b56ab-0957-415a-8ac9-649e4c3426cb", null], ["74a13137-7dfb-4f33-8c34-565591481d00", "313bcc1bfcffa28ca8937d46ce792accf790c978cd3b4ffbc0ba7ca3e996ccf3", "user", null, null, null, 0, null, null], ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "c1d022b085f350c5d059f5220765b78195c6f03116b3ca98d7afd50142838827", "char", null, null, null, 0, "c57a256d-a258-4e26-af72-b8f5dc4a5328", null]]}');
INSERT INTO public.host_observation VALUES ('01a0eb13-b434-7d6b-a673-66c28804c676', '01a0eb13-b3da-72b7-a357-c47332366c13', 'manifest', 'aaf8f577cb736bf0c4da5d83143215822df463c1693fc3759e4c3b8912d45401', '01a0eb13-b3da-72b7-a357-c47332366c13:aaf8f577cb736bf0c4da5d83143215822df463c1693fc3759e4c3b8912d45401:manifest', '2026-09-29 02:52:12.204997+00', '{"chat_id": "d6830dde-55bf-45d1-9dcc-a254722632ca", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["4cb6e5a2-7db4-46fd-9574-6894f9707ff5", "48f7e9ed3223fac86c89fed47fea2a1be827347482ace27bcaa8a592b89f4eda", "user", null, null, null, 0, null, null], ["7b35be19-c7d4-449f-ab11-4a433d37ad58", "7aa628ab8d1b33fa4a0651b82aeab76cf74d23e5c544dee0ff1315c1c4586682", "char", null, null, null, 0, "7b35be19-c7d4-449f-ab11-4a433d37ad58", null], ["67f82ecc-cc74-40ea-a79a-06405c7df2fb", "c5eadd3b95a3c8e5de86435280d361ad1d00fdb2786a8cd56cee94fa53eed6fc", "user", null, null, null, 0, null, null], ["8b8e698b-a605-4fce-a713-9ffaf524d534", "55852e691edd6c7cbcf18ac40c5814055f5eba3e9f89edc24616e59ad0cffe2b", "char", null, null, null, 0, "8b8e698b-a605-4fce-a713-9ffaf524d534", null]], "base_manifest_hash": "34dcac788b8a0a60257215b50b71ac6b386490a94579720a4b2cafd3724a1b80"}');
INSERT INTO public.host_observation VALUES ('01a0eb13-b465-7272-b2ef-d21d022885cb', '01a0eb13-b3da-72b7-a357-c47332366c13', 'manifest', '11b00ab225090e73c30738437302105b14304ca005a4c27cfecd45234e24b351', '01a0eb13-b3da-72b7-a357-c47332366c13:11b00ab225090e73c30738437302105b14304ca005a4c27cfecd45234e24b351:manifest', '2026-09-29 02:52:12.25462+00', '{"chat_id": "d6830dde-55bf-45d1-9dcc-a254722632ca", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "b08ce6896025ff621a441a1d4d7ebc9b8349c97dfae3d9f4510b70fc2e78cc39", "user", null, null, null, 0, null, null], ["74701285-4c4b-448b-9830-18fd4644943e", "fe0e408fe9e8009d507fef8b728807d0ee399b5d367903e212bf702e84caaa38", "char", null, null, null, 0, "74701285-4c4b-448b-9830-18fd4644943e", null], ["06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "1c4fdf8b0c639ae0c071b9695ab812081de9a1b24741720344b7f741974b9ece", "user", null, null, null, 0, null, null], ["e83cd7bf-e640-49ec-b7a7-f894b5087400", "186ce574a6f5e1da6457bb1a6a242443f7024eeca9fe3ba019569511f9a5d435", "char", null, null, null, 0, "e83cd7bf-e640-49ec-b7a7-f894b5087400", null]], "base_manifest_hash": "aaf8f577cb736bf0c4da5d83143215822df463c1693fc3759e4c3b8912d45401"}');
INSERT INTO public.host_observation VALUES ('01a0eb13-b495-7e36-9946-bbeaf6a2ed2b', '01a0eb13-b3da-72b7-a357-c47332366c13', 'manifest', 'ba902b8d1c8cbee4c6f973f9f898b77b7c7fdee51f6ad00d2fd63f648d956f3a', '01a0eb13-b3da-72b7-a357-c47332366c13:ba902b8d1c8cbee4c6f973f9f898b77b7c7fdee51f6ad00d2fd63f648d956f3a:manifest', '2026-09-29 02:52:12.305142+00', '{"chat_id": "d6830dde-55bf-45d1-9dcc-a254722632ca", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["63ea9dc4-0978-468e-bb74-16984b48883c", "b2d9710475052cbcd5b072e219f4d6fee84aed4dcc88e41821041817724559ac", "user", null, null, null, 0, null, null]], "base_manifest_hash": "11b00ab225090e73c30738437302105b14304ca005a4c27cfecd45234e24b351"}');
INSERT INTO public.host_observation VALUES ('01a0eb13-baaa-7b45-ad7d-2f7fd6a1427a', '01a0eb13-b3da-72b7-a357-c47332366c13', 'manifest', 'e4d2ac9c0c08b8f1c04549c70623bc7a193b1f4df08adad8824e5019d70a711a', '01a0eb13-b3da-72b7-a357-c47332366c13:e4d2ac9c0c08b8f1c04549c70623bc7a193b1f4df08adad8824e5019d70a711a:manifest', '2026-09-29 02:52:13.862526+00', '{"chat_id": "d6830dde-55bf-45d1-9dcc-a254722632ca", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["d0889bbf-4f07-4fcb-9e44-cefc6991f37e", "b8c4a48dea49380c9a264c28eadd2ee0bbeb1c07c2afed3657df3dfcaa003dcc", "user", null, null, null, 0, null, null], ["a74b56ab-0957-415a-8ac9-649e4c3426cb", "cbaba78c9b10c22bd174781e4946d204509c1faf5bfa7bea444c4b174f524291", "char", null, null, null, 0, "a74b56ab-0957-415a-8ac9-649e4c3426cb", null], ["74a13137-7dfb-4f33-8c34-565591481d00", "313bcc1bfcffa28ca8937d46ce792accf790c978cd3b4ffbc0ba7ca3e996ccf3", "user", null, null, null, 0, null, null], ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "cfed99eb304c91e7553ef66b3e53ff1af1d63333e72b263e455a1b2b5a6a74dc", "char", null, null, null, 0, "c57a256d-a258-4e26-af72-b8f5dc4a5328", null], ["4cb6e5a2-7db4-46fd-9574-6894f9707ff5", "48f7e9ed3223fac86c89fed47fea2a1be827347482ace27bcaa8a592b89f4eda", "user", null, null, null, 0, null, null], ["7b35be19-c7d4-449f-ab11-4a433d37ad58", "7aa628ab8d1b33fa4a0651b82aeab76cf74d23e5c544dee0ff1315c1c4586682", "char", null, null, null, 0, "7b35be19-c7d4-449f-ab11-4a433d37ad58", null], ["67f82ecc-cc74-40ea-a79a-06405c7df2fb", "c5eadd3b95a3c8e5de86435280d361ad1d00fdb2786a8cd56cee94fa53eed6fc", "user", null, null, null, 0, null, null], ["8b8e698b-a605-4fce-a713-9ffaf524d534", "55852e691edd6c7cbcf18ac40c5814055f5eba3e9f89edc24616e59ad0cffe2b", "char", null, null, null, 0, "8b8e698b-a605-4fce-a713-9ffaf524d534", null], ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "b08ce6896025ff621a441a1d4d7ebc9b8349c97dfae3d9f4510b70fc2e78cc39", "user", null, null, null, 0, null, null], ["74701285-4c4b-448b-9830-18fd4644943e", "fe0e408fe9e8009d507fef8b728807d0ee399b5d367903e212bf702e84caaa38", "char", null, null, null, 0, "74701285-4c4b-448b-9830-18fd4644943e", null], ["06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "1c4fdf8b0c639ae0c071b9695ab812081de9a1b24741720344b7f741974b9ece", "user", null, null, null, 0, null, null], ["e83cd7bf-e640-49ec-b7a7-f894b5087400", "186ce574a6f5e1da6457bb1a6a242443f7024eeca9fe3ba019569511f9a5d435", "char", null, null, null, 0, "e83cd7bf-e640-49ec-b7a7-f894b5087400", null], ["63ea9dc4-0978-468e-bb74-16984b48883c", "b2d9710475052cbcd5b072e219f4d6fee84aed4dcc88e41821041817724559ac", "user", null, null, null, 0, null, null], ["33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "17e1b43c2902bbe980eb01d45857514ce6f9e6397dd0e592d3847f4915dccf2f", "char", null, null, null, 0, "33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", null], ["bffb4a0f-f94e-45f2-b6a0-f681b80b08f1", "f6de08bd11a97313cd1bffbfed2a49c3bbf30cf3f1f2b05da9e3a23b4405fe3a", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0eb13-bad7-7302-b654-e277544b2ec9', '01a0eb13-b3da-72b7-a357-c47332366c13', 'manifest', 'ae8255dc058665e7bd3a226349245167c337eb89cb9c9c355f958e42e6c3496f', '01a0eb13-b3da-72b7-a357-c47332366c13:ae8255dc058665e7bd3a226349245167c337eb89cb9c9c355f958e42e6c3496f:manifest', '2026-09-29 02:52:13.907676+00', '{"chat_id": "d6830dde-55bf-45d1-9dcc-a254722632ca", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "8b492d6e0c4cf5d62c274b507a57a2cc449e1d6451fd6b8b9a6897896762c5bc", "char", null, null, 1, 2, "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", null]], "base_manifest_hash": "e4d2ac9c0c08b8f1c04549c70623bc7a193b1f4df08adad8824e5019d70a711a"}');
INSERT INTO public.host_observation VALUES ('01a0eb13-bb03-7482-ae17-d17b3442bde0', '01a0eb13-b3da-72b7-a357-c47332366c13', 'manifest', 'de38c534f7763ca07028a52b7851f55cf39fc63a6c6048770b0bd480d568be1f', '01a0eb13-b3da-72b7-a357-c47332366c13:de38c534f7763ca07028a52b7851f55cf39fc63a6c6048770b0bd480d568be1f:manifest', '2026-09-29 02:52:13.95169+00', '{"chat_id": "d6830dde-55bf-45d1-9dcc-a254722632ca", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["d0889bbf-4f07-4fcb-9e44-cefc6991f37e", "b8c4a48dea49380c9a264c28eadd2ee0bbeb1c07c2afed3657df3dfcaa003dcc", "user", null, null, null, 0, null, null], ["a74b56ab-0957-415a-8ac9-649e4c3426cb", "cbaba78c9b10c22bd174781e4946d204509c1faf5bfa7bea444c4b174f524291", "char", null, null, null, 0, "a74b56ab-0957-415a-8ac9-649e4c3426cb", null], ["74a13137-7dfb-4f33-8c34-565591481d00", "313bcc1bfcffa28ca8937d46ce792accf790c978cd3b4ffbc0ba7ca3e996ccf3", "user", null, null, null, 0, null, null], ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "cfed99eb304c91e7553ef66b3e53ff1af1d63333e72b263e455a1b2b5a6a74dc", "char", null, null, null, 0, "c57a256d-a258-4e26-af72-b8f5dc4a5328", null], ["4cb6e5a2-7db4-46fd-9574-6894f9707ff5", "48f7e9ed3223fac86c89fed47fea2a1be827347482ace27bcaa8a592b89f4eda", "user", null, null, null, 0, null, null], ["7b35be19-c7d4-449f-ab11-4a433d37ad58", "7aa628ab8d1b33fa4a0651b82aeab76cf74d23e5c544dee0ff1315c1c4586682", "char", null, null, null, 0, "7b35be19-c7d4-449f-ab11-4a433d37ad58", null], ["67f82ecc-cc74-40ea-a79a-06405c7df2fb", "c5eadd3b95a3c8e5de86435280d361ad1d00fdb2786a8cd56cee94fa53eed6fc", "user", null, null, null, 0, null, null], ["8b8e698b-a605-4fce-a713-9ffaf524d534", "55852e691edd6c7cbcf18ac40c5814055f5eba3e9f89edc24616e59ad0cffe2b", "char", null, null, null, 0, "8b8e698b-a605-4fce-a713-9ffaf524d534", null], ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "cc941c7a8773e160fee830289b569b191e530538ae8b414b994906d414492ac0", "user", true, null, null, 0, null, null], ["74701285-4c4b-448b-9830-18fd4644943e", "fe0e408fe9e8009d507fef8b728807d0ee399b5d367903e212bf702e84caaa38", "char", null, null, null, 0, "74701285-4c4b-448b-9830-18fd4644943e", null], ["06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "1c4fdf8b0c639ae0c071b9695ab812081de9a1b24741720344b7f741974b9ece", "user", null, null, null, 0, null, null], ["e83cd7bf-e640-49ec-b7a7-f894b5087400", "186ce574a6f5e1da6457bb1a6a242443f7024eeca9fe3ba019569511f9a5d435", "char", null, null, null, 0, "e83cd7bf-e640-49ec-b7a7-f894b5087400", null], ["63ea9dc4-0978-468e-bb74-16984b48883c", "b2d9710475052cbcd5b072e219f4d6fee84aed4dcc88e41821041817724559ac", "user", null, null, null, 0, null, null], ["33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "17e1b43c2902bbe980eb01d45857514ce6f9e6397dd0e592d3847f4915dccf2f", "char", null, null, null, 0, "33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", null], ["bffb4a0f-f94e-45f2-b6a0-f681b80b08f1", "f6de08bd11a97313cd1bffbfed2a49c3bbf30cf3f1f2b05da9e3a23b4405fe3a", "user", null, null, null, 0, null, null], ["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "53967474367c08fd1c1d7c9a0e56b7fca381ad01ed98a868b2015ba3f7a58440", "char", null, null, 0, 2, "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", null], ["245648ae-4dd7-4e67-bd55-6d876219624c", "bd10199879b8ff095bc344faeff90b34f00d459f36cc4e5546a530fef008982c", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0eb13-c118-7f30-a764-68b838df56a6', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', 'manifest', '539c506b8d241201afb46ee7d78eecf0af66968dada431a94d779bcf982cca3e', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba:539c506b8d241201afb46ee7d78eecf0af66968dada431a94d779bcf982cca3e:manifest', '2026-09-29 02:52:15.506738+00', '{"chat_id": "3627df37-7e08-4f01-a39c-ccfbea70e327", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["f37f8310-5f55-419b-98f6-b8f9efc7077b", "d30bd7d13334b4bed3a934ed708d5b19ce0708bc0f16e5ed609b725052cacb5a", "user", null, null, null, 0, null, null], ["4a65f7b7-8dab-46aa-b6e3-d1ffeccd92e5", "ac0434aeecb17f05627a83bdafd0ae5e7bd2c039e5a3c2d26be89f36041ef758", "char", null, null, null, 0, "a74b56ab-0957-415a-8ac9-649e4c3426cb", null], ["55a551fa-858e-4259-bb80-660d2fcc1e6a", "db7b1737b9a3a9e2923177e0fdc852b8fa9e92f95ebd04c86c957c11315bfb3c", "user", null, null, null, 0, null, null], ["b4dba62c-fcfe-4f17-b895-fce840245c4b", "10e407d4220a5db1df33bac370f628f613383bf3b7ae7c4b82df5a383a3b0cb1", "char", null, null, null, 0, "c57a256d-a258-4e26-af72-b8f5dc4a5328", null], ["e52aab32-61d9-41fc-8587-2ea93e6a2280", "307d3b875cc26be83d9d9c4c0f3318af5b29f31b2e8f2ec12398aeff755d9346", "user", null, null, null, 0, null, null], ["b109ab9e-b2d4-4c0f-9efa-0447abcb2a89", "cc695dda9a75f4df204db672428ce54c3d0a7ab7b768d7ee192ec988e26dc8b6", "char", null, null, null, 0, "7b35be19-c7d4-449f-ab11-4a433d37ad58", null], ["62f89ae2-0190-49e8-b328-facba4b19adb", "8a65694d6c6ba2417bee7d0930d54786bdcba5fa5e3b36ba970b3957565f2a10", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::d6830dde-55bf-45d1-9dcc-a254722632ca::Harbor route::7b35be19-c7d4-449f-ab11-4a433d37ad58::}}"]], ["ef44cadf-57a0-4097-8ecf-10695ac1dee0", "805dd656c0f859ead2c7038f22903babb435cd92ca6cd00edde515734925b077", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0eb13-b492-7430-86cd-b47a39ce8d6c:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b492-7430-86cd-b47a39ce8d6c"}', 50, 'done', 1, '2026-09-29 02:52:12.305142+00', NULL, NULL, '2026-09-29 02:52:12.305142+00', '2026-09-29 02:52:13.379638+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0eb13-b462-7ea7-8cb6-d9dc3d223aea:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b462-7ea7-8cb6-d9dc3d223aea"}', 50, 'done', 1, '2026-09-29 02:52:12.305142+00', NULL, NULL, '2026-09-29 02:52:12.305142+00', '2026-09-29 02:52:13.403412+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0eb13-b42e-715b-bf3c-67f26abb22ad:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b42e-715b-bf3c-67f26abb22ad"}', 50, 'done', 1, '2026-09-29 02:52:12.204997+00', NULL, NULL, '2026-09-29 02:52:12.204997+00', '2026-09-29 02:52:13.554214+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff"}', 50, 'done', 1, '2026-09-29 02:52:12.204997+00', NULL, NULL, '2026-09-29 02:52:12.204997+00', '2026-09-29 02:52:13.580391+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0eb13-b462-7ea7-8cb6-d9dc3d223aea:4f3e19a99cb476d716d0d60730855ea6:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b462-7ea7-8cb6-d9dc3d223aea", "window_hash": "4f3e19a99cb476d716d0d60730855ea6"}', 100, 'done', 1, '2026-09-29 02:52:12.305142+00', NULL, NULL, '2026-09-29 02:52:12.305142+00', '2026-09-29 02:52:13.613066+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0eb13-b460-7dde-a568-c410fee4ff6b:01925c7bdd6209d1d1ed98c0aa6af8af:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b460-7dde-a568-c410fee4ff6b", "window_hash": "01925c7bdd6209d1d1ed98c0aa6af8af"}', 100, 'done', 1, '2026-09-29 02:52:12.25462+00', NULL, NULL, '2026-09-29 02:52:12.25462+00', '2026-09-29 02:52:13.645644+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0eb13-b3e9-7867-a892-8768a67a0310:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b3e9-7867-a892-8768a67a0310"}', 150, 'done', 1, '2026-09-29 02:52:12.129701+00', NULL, NULL, '2026-09-29 02:52:12.129701+00', '2026-09-29 02:52:13.763671+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0eb13-b3e6-7082-8972-95961ee4258b:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b3e6-7082-8972-95961ee4258b"}', 150, 'done', 1, '2026-09-29 02:52:12.129701+00', NULL, NULL, '2026-09-29 02:52:12.129701+00', '2026-09-29 02:52:13.784804+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0eb13-b3e9-7867-a892-8768a67a0310:ab353189b3838bb6971b0ec46d6a5e2f:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b3e9-7867-a892-8768a67a0310", "window_hash": "ab353189b3838bb6971b0ec46d6a5e2f"}', 200, 'done', 1, '2026-09-29 02:52:12.129701+00', NULL, NULL, '2026-09-29 02:52:12.129701+00', '2026-09-29 02:52:13.819191+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0eb13-baa8-7819-b61a-af25dc99d165:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-baa8-7819-b61a-af25dc99d165"}', 50, 'done', 1, '2026-09-29 02:52:13.862526+00', NULL, NULL, '2026-09-29 02:52:13.862526+00', '2026-09-29 02:52:14.884878+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0eb13-baa8-7229-90ae-544a07a5b6b2:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-baa8-7229-90ae-544a07a5b6b2"}', 50, 'done', 1, '2026-09-29 02:52:13.862526+00', NULL, NULL, '2026-09-29 02:52:13.862526+00', '2026-09-29 02:52:14.904973+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0eb13-baa7-7899-8417-8d2af20060e7:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-baa7-7899-8417-8d2af20060e7"}', 50, 'done', 1, '2026-09-29 02:52:13.862526+00', NULL, NULL, '2026-09-29 02:52:13.862526+00', '2026-09-29 02:52:14.935168+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0eb13-baa8-7229-90ae-544a07a5b6b2:c389cea1fa08ab6bdc7cfe5f7b8a391b:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-baa8-7229-90ae-544a07a5b6b2", "window_hash": "c389cea1fa08ab6bdc7cfe5f7b8a391b"}', 100, 'obsolete', 1, '2026-09-29 02:52:13.862526+00', NULL, NULL, '2026-09-29 02:52:13.862526+00', '2026-09-29 02:52:15.053728+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0eb13-b460-7dde-a568-c410fee4ff6b:b30a10b04e0ca9ab1634b70eabc4e3b8:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b460-7dde-a568-c410fee4ff6b", "window_hash": "b30a10b04e0ca9ab1634b70eabc4e3b8"}', 100, 'obsolete', 1, '2026-09-29 02:52:13.862526+00', NULL, NULL, '2026-09-29 02:52:13.862526+00', '2026-09-29 02:52:15.057127+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0eb13-b461-731f-8749-818b3518b01f:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b461-731f-8749-818b3518b01f"}', 50, 'done', 1, '2026-09-29 02:52:12.25462+00', NULL, NULL, '2026-09-29 02:52:12.25462+00', '2026-09-29 02:52:13.424213+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0eb13-b460-7dde-a568-c410fee4ff6b:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b460-7dde-a568-c410fee4ff6b"}', 50, 'done', 1, '2026-09-29 02:52:12.25462+00', NULL, NULL, '2026-09-29 02:52:12.25462+00', '2026-09-29 02:52:13.446183+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0eb13-b45f-7415-bf4a-b8be40922afe:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b45f-7415-bf4a-b8be40922afe"}', 50, 'done', 1, '2026-09-29 02:52:12.25462+00', NULL, NULL, '2026-09-29 02:52:12.25462+00', '2026-09-29 02:52:13.470148+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0eb13-b431-73a9-9d9a-ee0695e5d1bf:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b431-73a9-9d9a-ee0695e5d1bf"}', 50, 'done', 1, '2026-09-29 02:52:12.25462+00', NULL, NULL, '2026-09-29 02:52:12.25462+00', '2026-09-29 02:52:13.490223+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0eb13-b430-76dd-865f-2bd240ffef59:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b430-76dd-865f-2bd240ffef59"}', 50, 'done', 1, '2026-09-29 02:52:12.204997+00', NULL, NULL, '2026-09-29 02:52:12.204997+00', '2026-09-29 02:52:13.510578+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0eb13-b42f-7b45-b68b-f6e99aee8575:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b42f-7b45-b68b-f6e99aee8575"}', 50, 'done', 1, '2026-09-29 02:52:12.204997+00', NULL, NULL, '2026-09-29 02:52:12.204997+00', '2026-09-29 02:52:13.531061+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0eb13-b431-73a9-9d9a-ee0695e5d1bf:f78c40fa678ede044de72b39f91b9a7c:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b431-73a9-9d9a-ee0695e5d1bf", "window_hash": "f78c40fa678ede044de72b39f91b9a7c"}', 100, 'done', 1, '2026-09-29 02:52:12.25462+00', NULL, NULL, '2026-09-29 02:52:12.25462+00', '2026-09-29 02:52:13.671646+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0eb13-b42f-7b45-b68b-f6e99aee8575:e89fb51599faa932fcf36d3274015089:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b42f-7b45-b68b-f6e99aee8575", "window_hash": "e89fb51599faa932fcf36d3274015089"}', 100, 'done', 1, '2026-09-29 02:52:12.204997+00', NULL, NULL, '2026-09-29 02:52:12.204997+00', '2026-09-29 02:52:13.698666+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff:d3e6d48c9b2950f66dbee64cdea7cb1c:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff", "window_hash": "d3e6d48c9b2950f66dbee64cdea7cb1c"}', 100, 'done', 1, '2026-09-29 02:52:12.204997+00', NULL, NULL, '2026-09-29 02:52:12.204997+00', '2026-09-29 02:52:13.72396+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0eb13-b3ea-7545-8529-4c53faf349a0:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-b3ea-7545-8529-4c53faf349a0"}', 150, 'done', 1, '2026-09-29 02:52:12.129701+00', NULL, NULL, '2026-09-29 02:52:12.129701+00', '2026-09-29 02:52:13.744175+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0eb13-b431-73a9-9d9a-ee0695e5d1bf:da05deb0405738a0dcee1ff682d941de:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b431-73a9-9d9a-ee0695e5d1bf", "window_hash": "da05deb0405738a0dcee1ff682d941de"}', 100, 'obsolete', 1, '2026-09-29 02:52:13.862526+00', NULL, NULL, '2026-09-29 02:52:13.862526+00', '2026-09-29 02:52:15.060566+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0eb13-b42f-7b45-b68b-f6e99aee8575:29d7884c84ef3d3ee5bdb78c2d74340f:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b42f-7b45-b68b-f6e99aee8575", "window_hash": "29d7884c84ef3d3ee5bdb78c2d74340f"}', 100, 'done', 1, '2026-09-29 02:52:13.862526+00', NULL, NULL, '2026-09-29 02:52:13.862526+00', '2026-09-29 02:52:15.085952+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0eb13-baa7-7899-8417-8d2af20060e7:25c3a98289b86ddd6a6450f989d1ea78:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-baa7-7899-8417-8d2af20060e7", "window_hash": "25c3a98289b86ddd6a6450f989d1ea78"}', 100, 'done', 1, '2026-09-29 02:52:13.862526+00', NULL, NULL, '2026-09-29 02:52:13.862526+00', '2026-09-29 02:52:15.113154+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0eb13-bb01-768d-8829-f36aeda1e65e:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-bb01-768d-8829-f36aeda1e65e"}', 50, 'done', 1, '2026-09-29 02:52:13.95169+00', NULL, NULL, '2026-09-29 02:52:13.95169+00', '2026-09-29 02:52:14.841656+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0eb13-bb00-7353-80ff-25d33aedd0a1:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-bb00-7353-80ff-25d33aedd0a1"}', 50, 'done', 1, '2026-09-29 02:52:13.95169+00', NULL, NULL, '2026-09-29 02:52:13.95169+00', '2026-09-29 02:52:14.863642+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0eb13-bb00-7353-80ff-25d33aedd0a1:09f68cd35014a615cc9288106beaf701:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-bb00-7353-80ff-25d33aedd0a1", "window_hash": "09f68cd35014a615cc9288106beaf701"}', 100, 'done', 1, '2026-09-29 02:52:13.95169+00', NULL, NULL, '2026-09-29 02:52:13.95169+00', '2026-09-29 02:52:14.96476+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0eb13-baa8-7229-90ae-544a07a5b6b2:5ecf5f8c827299a4794fd4784758caa6:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-baa8-7229-90ae-544a07a5b6b2", "window_hash": "5ecf5f8c827299a4794fd4784758caa6"}', 100, 'done', 1, '2026-09-29 02:52:13.95169+00', NULL, NULL, '2026-09-29 02:52:13.95169+00', '2026-09-29 02:52:14.989645+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0eb13-b462-7ea7-8cb6-d9dc3d223aea:220a8f5f72efd48a5f996bf75d87aa00:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b462-7ea7-8cb6-d9dc3d223aea", "window_hash": "220a8f5f72efd48a5f996bf75d87aa00"}', 100, 'done', 1, '2026-09-29 02:52:13.95169+00', NULL, NULL, '2026-09-29 02:52:13.95169+00', '2026-09-29 02:52:15.018001+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0eb13-b460-7dde-a568-c410fee4ff6b:f0f10546cc294e9b9fb6e22c7b1d7b89:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-b3da-72b7-a357-c47332366c13', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-b460-7dde-a568-c410fee4ff6b", "window_hash": "f0f10546cc294e9b9fb6e22c7b1d7b89"}', 100, 'done', 1, '2026-09-29 02:52:13.95169+00', NULL, NULL, '2026-09-29 02:52:13.95169+00', '2026-09-29 02:52:15.049979+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0eb13-c116-7129-b87e-bfb69ea5b6fa:f14a38d7d1f2db8906e9c3dc5a68a5ea:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-c116-7129-b87e-bfb69ea5b6fa", "window_hash": "f14a38d7d1f2db8906e9c3dc5a68a5ea"}', 200, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.289809+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0eb13-c115-73ae-b58d-43cd89c53978:a592698990b5c8bc9ae0b53ec65f4c28:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-c115-73ae-b58d-43cd89c53978", "window_hash": "a592698990b5c8bc9ae0b53ec65f4c28"}', 200, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.315191+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0eb13-c114-7b56-a8d4-29dd29760190:ff301b633269f17558cf81bbd611a8c6:extract-285407df4e52d85cbd6a4c44bca5872b', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "extract-285407df4e52d85cbd6a4c44bca5872b", "revision_id": "01a0eb13-c114-7b56-a8d4-29dd29760190", "window_hash": "ff301b633269f17558cf81bbd611a8c6"}', 200, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.34267+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0eb13-c117-791d-b1ab-5012376283f8:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-c117-791d-b1ab-5012376283f8"}', 150, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.134569+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0eb13-c116-7129-b87e-bfb69ea5b6fa:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-c116-7129-b87e-bfb69ea5b6fa"}', 150, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.15786+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0eb13-c116-7e76-b174-79e561872974:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-c116-7e76-b174-79e561872974"}', 150, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.17763+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0eb13-c115-73ae-b58d-43cd89c53978:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-c115-73ae-b58d-43cd89c53978"}', 150, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.199111+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0eb13-c114-7e23-8431-d39725ec67e5:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-c114-7e23-8431-d39725ec67e5"}', 150, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.220782+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0eb13-c114-7b56-a8d4-29dd29760190:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-c114-7b56-a8d4-29dd29760190"}', 150, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.246125+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0eb13-c113-7398-a2ec-2494fd474f28:embed-b611e6e8a97ebe27e6c14c13dd855471', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{"generation": "embed-b611e6e8a97ebe27e6c14c13dd855471", "revision_id": "01a0eb13-c113-7398-a2ec-2494fd474f28"}', 150, 'done', 1, '2026-09-29 02:52:15.506738+00', NULL, NULL, '2026-09-29 02:52:15.506738+00', '2026-09-29 02:52:16.266171+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0eb13-b3ec-7e56-b714-56f51a997b15', '01a0eb13-b3da-72b7-a357-c47332366c13');


--
-- Data for Name: owner_repair; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-285407df4e52d85cbd6a4c44bca5872b', 'extract', 'stub', 'http://127.0.0.1:38007/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "a0de52e41b72df2c", "compiler": "extract-v13", "endpoint": "http://127.0.0.1:38007/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "a6511d2d7b4e2fca", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-29 02:52:11.986982+00', '2026-09-29 02:52:11.988179+00');
INSERT INTO public.projection_generation VALUES ('embed-b611e6e8a97ebe27e6c14c13dd855471', 'embed', 'stub-embed', 'http://127.0.0.1:38007/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:38007/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-29 02:52:11.986982+00', '2026-09-29 02:52:11.991788+00');
INSERT INTO public.projection_generation VALUES ('summarize-62cdebdaeb63565bcd957fb11170f429', 'summarize', 'stub', 'http://127.0.0.1:38007/v1', '{"lag": 4, "kind": "summarize", "model": "stub", "prompt": "1cb5649d13d81671", "window": 8, "version": "summarize-v3", "endpoint": "http://127.0.0.1:38007/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "message_chars": 6000}', '2026-09-29 02:52:11.986982+00', '2026-09-29 02:52:11.994072+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0eb13-b41d-7675-be88-41b190866b2f', '01a0eb13-b3da-72b7-a357-c47332366c13', '01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0eb13-b3ea-7545-8529-4c53faf349a0", "host_logical_id": "74a13137-7dfb-4f33-8c34-565591481d00"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0eb13-b3ea-7545-8529-4c53faf349a0", "host_logical_id": "74a13137-7dfb-4f33-8c34-565591481d00"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 26.35, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 2.21, "fits_at": null, "lexical": 3.88, "threads": 0, "extractor": "extract-285407df4e52", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 38.87, "embedding_projection": "embed-b611e6e8a97ebe", "memory_mode_withheld": 0}', 'fresh', '2026-09-29 02:52:12.151066+00', 'packet-v8', 600, 3, '', '["74a13137-7dfb-4f33-8c34-565591481d00", "a74b56ab-0957-415a-8ac9-649e4c3426cb", "c57a256d-a258-4e26-af72-b8f5dc4a5328", "d0889bbf-4f07-4fcb-9e44-cefc6991f37e"]', 'extract-285407df4e52d85cbd6a4c44bca5872b', 'embed-b611e6e8a97ebe27e6c14c13dd855471', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-62cdebdaeb63565bcd957fb11170f429", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0eb13-b452-7f4a-a5ef-28c4009b9a29', '01a0eb13-b3da-72b7-a357-c47332366c13', '01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0eb13-b430-76dd-865f-2bd240ffef59", "host_logical_id": "67f82ecc-cc74-40ea-a79a-06405c7df2fb"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0eb13-b430-76dd-865f-2bd240ffef59", "host_logical_id": "67f82ecc-cc74-40ea-a79a-06405c7df2fb"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 16.06, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 1.2, "fits_at": null, "lexical": 2.58, "threads": 0, "extractor": "extract-285407df4e52", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 23.87, "embedding_projection": "embed-b611e6e8a97ebe", "memory_mode_withheld": 0}', 'fresh', '2026-09-29 02:52:12.219072+00', 'packet-v8', 600, 7, '', '["4cb6e5a2-7db4-46fd-9574-6894f9707ff5", "67f82ecc-cc74-40ea-a79a-06405c7df2fb", "7b35be19-c7d4-449f-ab11-4a433d37ad58", "8b8e698b-a605-4fce-a713-9ffaf524d534"]', 'extract-285407df4e52d85cbd6a4c44bca5872b', 'embed-b611e6e8a97ebe27e6c14c13dd855471', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-62cdebdaeb63565bcd957fb11170f429", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0eb13-b485-7c8f-9a52-1263c36ceb6a', '01a0eb13-b3da-72b7-a357-c47332366c13', '01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0eb13-b461-731f-8749-818b3518b01f", "host_logical_id": "06616427-d933-4ab0-a5d2-3adfd5b2ecb4"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0eb13-b461-731f-8749-818b3518b01f", "host_logical_id": "06616427-d933-4ab0-a5d2-3adfd5b2ecb4"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 16.71, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 1.16, "fits_at": null, "lexical": 2.73, "threads": 0, "extractor": "extract-285407df4e52", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 24.85, "embedding_projection": "embed-b611e6e8a97ebe", "memory_mode_withheld": 0}', 'fresh', '2026-09-29 02:52:12.269215+00', 'packet-v8', 600, 11, '', '["06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "74701285-4c4b-448b-9830-18fd4644943e", "e83cd7bf-e640-49ec-b7a7-f894b5087400"]', 'extract-285407df4e52d85cbd6a4c44bca5872b', 'embed-b611e6e8a97ebe27e6c14c13dd855471', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-62cdebdaeb63565bcd957fb11170f429", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]');
INSERT INTO public.retrieval_trace VALUES ('01a0eb13-b4b4-7986-bad4-5cc9ccc61792', '01a0eb13-b3da-72b7-a357-c47332366c13', '01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0eb13-b492-7430-86cd-b47a39ce8d6c", "host_logical_id": "63ea9dc4-0978-468e-bb74-16984b48883c"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff", "host_logical_id": "c57a256d-a258-4e26-af72-b8f5dc4a5328"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0eb13-b3e9-7867-a892-8768a67a0310", "host_logical_id": "a74b56ab-0957-415a-8ac9-649e4c3426cb"}]', '[{"turn": 0, "score": 0.01587, "revision_id": "01a0eb13-b3e9-7867-a892-8768a67a0310"}, {"turn": 1, "score": 0.01613, "revision_id": "01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0eb13-b492-7430-86cd-b47a39ce8d6c", "host_logical_id": "63ea9dc4-0978-468e-bb74-16984b48883c"}]', 174, '{"fit": 0.0, "cast": 0, "embed": 16.01, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2, "summary": 0}, "vector": 1.37, "fits_at": null, "lexical": 2.75, "threads": 0, "extractor": "extract-285407df4e52", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 25.0, "embedding_projection": "embed-b611e6e8a97ebe", "memory_mode_withheld": 0}', 'fresh', '2026-09-29 02:52:12.315997+00', 'packet-v8', 600, 12, '', '["06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "63ea9dc4-0978-468e-bb74-16984b48883c", "74701285-4c4b-448b-9830-18fd4644943e", "e83cd7bf-e640-49ec-b7a7-f894b5087400"]', 'extract-285407df4e52d85cbd6a4c44bca5872b', 'embed-b611e6e8a97ebe27e6c14c13dd855471', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-62cdebdaeb63565bcd957fb11170f429", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 1, "placed": true}, {"ref": {"revision": "01a0eb13-b3e9-7867-a892-8768a67a0310"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 0, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0eb13-bac9-778b-9a56-82b93a3364f3', '01a0eb13-b3da-72b7-a357-c47332366c13', '01a0eb13-baab-7f4c-90b1-caddc8d6b497', 'And the compass?', '[{"rrf": 0.03128, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0eb13-b460-7dde-a568-c410fee4ff6b", "host_logical_id": "74701285-4c4b-448b-9830-18fd4644943e"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0eb13-baa8-7819-b61a-af25dc99d165", "host_logical_id": "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0eb13-b3e9-7867-a892-8768a67a0310", "host_logical_id": "a74b56ab-0957-415a-8ac9-649e4c3426cb"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0eb13-b3e6-7082-8972-95961ee4258b", "host_logical_id": "d0889bbf-4f07-4fcb-9e44-cefc6991f37e"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0eb13-b431-73a9-9d9a-ee0695e5d1bf", "host_logical_id": "8b8e698b-a605-4fce-a713-9ffaf524d534"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0eb13-b42f-7b45-b68b-f6e99aee8575", "host_logical_id": "7b35be19-c7d4-449f-ab11-4a433d37ad58"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0eb13-b3e6-7082-8972-95961ee4258b"}, {"turn": 0, "score": 0.01639, "revision_id": "01a0eb13-b3e9-7867-a892-8768a67a0310"}, {"turn": 2, "score": 0.01562, "revision_id": "01a0eb13-b42f-7b45-b68b-f6e99aee8575"}, {"turn": 3, "score": 0.01587, "revision_id": "01a0eb13-b431-73a9-9d9a-ee0695e5d1bf"}, {"turn": 4, "score": 0.03128, "revision_id": "01a0eb13-b460-7dde-a568-c410fee4ff6b"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0eb13-baa8-7819-b61a-af25dc99d165", "host_logical_id": "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1"}]', 326, '{"fit": 0.0, "cast": 2, "embed": 14.76, "facts": 0, "placed": {"fact": 2, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 5, "summary": 0}, "vector": 1.05, "fits_at": null, "lexical": 2.45, "threads": 0, "extractor": "extract-285407df4e52", "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 24.05, "embedding_projection": "embed-b611e6e8a97ebe", "memory_mode_withheld": 0}', 'fresh', '2026-09-29 02:52:13.873653+00', 'packet-v8', 600, 14, '', '["33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "63ea9dc4-0978-468e-bb74-16984b48883c", "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1", "e83cd7bf-e640-49ec-b7a7-f894b5087400"]', 'extract-285407df4e52d85cbd6a4c44bca5872b', 'embed-b611e6e8a97ebe27e6c14c13dd855471', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-62cdebdaeb63565bcd957fb11170f429", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 1}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 7}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a0eb13-b460-7dde-a568-c410fee4ff6b"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "placed": true}, {"ref": {"revision": "01a0eb13-b3e9-7867-a892-8768a67a0310"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 0, "placed": true}, {"ref": {"revision": "01a0eb13-b3e6-7082-8972-95961ee4258b"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a0eb13-b431-73a9-9d9a-ee0695e5d1bf"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 3, "placed": true}, {"ref": {"revision": "01a0eb13-b42f-7b45-b68b-f6e99aee8575"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0eb13-baf5-738e-a27b-c289b405a2ce', '01a0eb13-b3da-72b7-a357-c47332366c13', '01a0eb13-baab-7f4c-90b1-caddc8d6b497', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0eb13-b460-7dde-a568-c410fee4ff6b", "host_logical_id": "74701285-4c4b-448b-9830-18fd4644943e"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0eb13-baa8-7819-b61a-af25dc99d165", "host_logical_id": "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0eb13-b462-7ea7-8cb6-d9dc3d223aea", "host_logical_id": "e83cd7bf-e640-49ec-b7a7-f894b5087400"}]', '[{"turn": 4, "score": 0.03002, "revision_id": "01a0eb13-b460-7dde-a568-c410fee4ff6b"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0eb13-baa8-7819-b61a-af25dc99d165", "host_logical_id": "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1"}]', 222, '{"fit": 0.0, "cast": 2, "embed": 15.04, "facts": 0, "placed": {"fact": 2, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0}, "vector": 1.08, "fits_at": null, "lexical": 3.05, "threads": 0, "extractor": "extract-285407df4e52", "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 24.54, "embedding_projection": "embed-b611e6e8a97ebe", "memory_mode_withheld": 0}', 'fresh', '2026-09-29 02:52:13.916724+00', 'packet-v8', 600, 15, '', '["33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "63ea9dc4-0978-468e-bb74-16984b48883c", "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1"]', 'extract-285407df4e52d85cbd6a4c44bca5872b', 'embed-b611e6e8a97ebe27e6c14c13dd855471', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-62cdebdaeb63565bcd957fb11170f429", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 1}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 7}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a0eb13-b460-7dde-a568-c410fee4ff6b"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "placed": true}, {"ref": {"revision": "01a0eb13-b462-7ea7-8cb6-d9dc3d223aea"}, "tok": 0, "why": "repeats", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 5, "placed": false, "repeats": {"assertion": 1}}]');
INSERT INTO public.retrieval_trace VALUES ('01a0eb13-bb22-70d6-80eb-dd202ec98208', '01a0eb13-b3da-72b7-a357-c47332366c13', '01a0eb13-bb04-7179-80b4-698d30dfc66e', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0eb13-b430-76dd-865f-2bd240ffef59", "host_logical_id": "67f82ecc-cc74-40ea-a79a-06405c7df2fb"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0eb13-bb01-768d-8829-f36aeda1e65e", "host_logical_id": "245648ae-4dd7-4e67-bd55-6d876219624c"}]', '[{"turn": 3, "score": 0.03252, "revision_id": "01a0eb13-b430-76dd-865f-2bd240ffef59"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0eb13-bb01-768d-8829-f36aeda1e65e", "host_logical_id": "245648ae-4dd7-4e67-bd55-6d876219624c"}]', 138, '{"fit": 0.0, "cast": 0, "embed": 15.28, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0}, "vector": 0.89, "fits_at": null, "lexical": 3.39, "threads": 0, "extractor": "extract-285407df4e52", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 23.14, "embedding_projection": "embed-b611e6e8a97ebe", "memory_mode_withheld": 0}', 'fresh', '2026-09-29 02:52:13.963669+00', 'packet-v8', 600, 16, '', '["245648ae-4dd7-4e67-bd55-6d876219624c", "33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1"]', 'extract-285407df4e52d85cbd6a4c44bca5872b', 'embed-b611e6e8a97ebe27e6c14c13dd855471', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-62cdebdaeb63565bcd957fb11170f429", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0eb13-b430-76dd-865f-2bd240ffef59"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 3, "placed": true}]');
INSERT INTO public.retrieval_trace VALUES ('01a0eb13-c137-7bd6-96dd-fcb4f50eb07f', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '01a0eb13-c119-7fa6-beec-5af802c5ff91', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0eb13-c114-7e23-8431-d39725ec67e5", "host_logical_id": "55a551fa-858e-4259-bb80-660d2fcc1e6a"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0eb13-c115-73ae-b58d-43cd89c53978", "host_logical_id": "b4dba62c-fcfe-4f17-b895-fce840245c4b"}]', '[{"turn": 1, "score": 0.01639, "revision_id": "01a0eb13-c114-7e23-8431-d39725ec67e5"}, {"turn": 1, "score": 0.01613, "revision_id": "01a0eb13-c115-73ae-b58d-43cd89c53978"}]', '[]', 164, '{"fit": 0.0, "cast": 0, "embed": 17.95, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2, "summary": 0}, "vector": 0.86, "fits_at": null, "lexical": 2.12, "threads": 0, "extractor": "extract-285407df4e52", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 24.26, "embedding_projection": "embed-b611e6e8a97ebe", "memory_mode_withheld": 0}', 'fresh', '2026-09-29 02:52:15.519419+00', 'packet-v8', 600, 7, '', '["62f89ae2-0190-49e8-b328-facba4b19adb", "b109ab9e-b2d4-4c0f-9efa-0447abcb2a89", "e52aab32-61d9-41fc-8587-2ea93e6a2280", "ef44cadf-57a0-4097-8ecf-10695ac1dee0"]', 'extract-285407df4e52d85cbd6a4c44bca5872b', 'embed-b611e6e8a97ebe27e6c14c13dd855471', 'none', '{"top_k": 5, "strict": false, "narrator": null, "threshold": 0.4, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-62cdebdaeb63565bcd957fb11170f429", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a0eb13-c114-7e23-8431-d39725ec67e5"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 1, "placed": true}, {"ref": {"revision": "01a0eb13-c115-73ae-b58d-43cd89c53978"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 1, "placed": true}]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0eb13-b492-7430-86cd-b47a39ce8d6c', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.376653+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b462-7ea7-8cb6-d9dc3d223aea', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.401652+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b461-731f-8749-818b3518b01f', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.422598+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b460-7dde-a568-c410fee4ff6b', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.444246+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b45f-7415-bf4a-b8be40922afe', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.468522+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b431-73a9-9d9a-ee0695e5d1bf', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.488572+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b430-76dd-865f-2bd240ffef59', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.508891+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b42f-7b45-b68b-f6e99aee8575', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.529438+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b42e-715b-bf3c-67f26abb22ad', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.552622+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.578849+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b3ea-7545-8529-4c53faf349a0', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.74255+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b3e9-7867-a892-8768a67a0310', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.762003+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-b3e6-7082-8972-95961ee4258b', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:13.783243+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-bb01-768d-8829-f36aeda1e65e', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:14.839964+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-bb00-7353-80ff-25d33aedd0a1', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:14.861869+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-baa8-7819-b61a-af25dc99d165', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:14.883152+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-baa8-7229-90ae-544a07a5b6b2', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:14.903328+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-baa7-7899-8417-8d2af20060e7', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:14.93061+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-c117-791d-b1ab-5012376283f8', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:16.132849+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-c116-7129-b87e-bfb69ea5b6fa', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:16.156173+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-c116-7e76-b174-79e561872974', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:16.176048+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-c115-73ae-b58d-43cd89c53978', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:16.197459+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-c114-7e23-8431-d39725ec67e5', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:16.219149+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-c114-7b56-a8d4-29dd29760190', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:16.244295+00');
INSERT INTO public.revision_embedding VALUES ('01a0eb13-c113-7398-a2ec-2494fd474f28', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-b611e6e8a97ebe27e6c14c13dd855471', '2026-09-29 02:52:16.264513+00');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0eb13-b3e6-7082-8972-95961ee4258b', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-29 02:52:12.129701+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b3e9-7867-a892-8768a67a0310', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-29 02:52:12.129701+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b3ea-7545-8529-4c53faf349a0', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-29 02:52:12.129701+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-29 02:52:12.129701+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b42e-715b-bf3c-67f26abb22ad', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-29 02:52:12.204997+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b42f-7b45-b68b-f6e99aee8575', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-29 02:52:12.204997+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b430-76dd-865f-2bd240ffef59', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-09-29 02:52:12.204997+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b431-73a9-9d9a-ee0695e5d1bf', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-29 02:52:12.204997+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b45f-7415-bf4a-b8be40922afe', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-29 02:52:12.25462+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b460-7dde-a568-c410fee4ff6b', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-29 02:52:12.25462+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b461-731f-8749-818b3518b01f', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-09-29 02:52:12.25462+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b462-7ea7-8cb6-d9dc3d223aea', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-09-29 02:52:12.25462+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-b492-7430-86cd-b47a39ce8d6c', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-09-29 02:52:12.305142+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-baa7-7899-8417-8d2af20060e7', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-29 02:52:13.862526+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-baa8-7229-90ae-544a07a5b6b2', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-09-29 02:52:13.862526+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-baa8-7819-b61a-af25dc99d165', 'clean-v3', 'And the compass?', 16, 16, '2026-09-29 02:52:13.862526+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-bad4-7810-9a18-9356e74c53c0', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-29 02:52:13.907676+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-bb00-72ff-944e-65602522f363', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-09-29 02:52:13.95169+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-bb00-7353-80ff-25d33aedd0a1', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-09-29 02:52:13.95169+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-bb01-768d-8829-f36aeda1e65e', 'clean-v3', 'Let''s go.', 9, 9, '2026-09-29 02:52:13.95169+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-c113-7398-a2ec-2494fd474f28', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-09-29 02:52:15.506738+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-c114-7b56-a8d4-29dd29760190', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-29 02:52:15.506738+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-c114-7e23-8431-d39725ec67e5', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-09-29 02:52:15.506738+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-c115-73ae-b58d-43cd89c53978', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-29 02:52:15.506738+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-c116-7e76-b174-79e561872974', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-09-29 02:52:15.506738+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-c116-7129-b87e-bfb69ea5b6fa', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-29 02:52:15.506738+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-c117-7967-9118-3c255087ec7a', 'clean-v3', '{{specialcomment::branchedfrom::d6830dde-55bf-45d1-9dcc-a254722632ca::Harbor route::7b35be19-c7d4-449f-ab11-4a433d37ad58::}}', 124, 124, '2026-09-29 02:52:15.506738+00');
INSERT INTO public.revision_text VALUES ('01a0eb13-c117-791d-b1ab-5012376283f8', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-09-29 02:52:15.506738+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-29 02:52:10.888825+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-29 02:52:10.966427+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-29 02:52:10.982811+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-29 02:52:11.025051+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-29 02:52:11.04854+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-29 02:52:11.059772+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-29 02:52:11.061593+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-29 02:52:11.071479+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-29 02:52:11.090178+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-29 02:52:11.094287+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-29 02:52:11.096244+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-29 02:52:11.109307+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-29 02:52:11.13876+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-29 02:52:11.160572+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-29 02:52:11.163187+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-29 02:52:11.182763+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-29 02:52:11.185117+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-29 02:52:11.187883+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-09-29 02:52:11.197518+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-09-29 02:52:11.223255+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-09-29 02:52:11.227604+00');
INSERT INTO public.schema_migrations VALUES ('0022_thread_outcome_and_cause.sql', '9a8507f1b42457d2c44d568a2bd60d868f923613f8c83acb2be7f9104041cc88', '2026-09-29 02:52:11.231874+00');
INSERT INTO public.schema_migrations VALUES ('0023_summaries.sql', 'da452cf41917f9cc59c3a9d71e4114bf5179d3c5493669a5c7ce83ea13e0fb77', '2026-09-29 02:52:11.235922+00');
INSERT INTO public.schema_migrations VALUES ('0024_owner_repair.sql', 'de78024aceb993e7822500bb13d17d034b0123cdf67225fc9c8d82e16164e3be', '2026-09-29 02:52:11.255768+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0eb13-b3e5-744a-9366-1afd904ab590', '01a0eb13-b3da-72b7-a357-c47332366c13', 'd0889bbf-4f07-4fcb-9e44-cefc6991f37e', 'message', '2026-09-29 02:52:12.129701+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b3e8-737a-91c9-c5375fcf455c', '01a0eb13-b3da-72b7-a357-c47332366c13', 'a74b56ab-0957-415a-8ac9-649e4c3426cb', 'message', '2026-09-29 02:52:12.129701+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b3e9-7b74-88e2-e2416c70f8d2', '01a0eb13-b3da-72b7-a357-c47332366c13', '74a13137-7dfb-4f33-8c34-565591481d00', 'message', '2026-09-29 02:52:12.129701+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b3ea-77d0-a4c4-db60b0456980', '01a0eb13-b3da-72b7-a357-c47332366c13', 'c57a256d-a258-4e26-af72-b8f5dc4a5328', 'message', '2026-09-29 02:52:12.129701+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b42d-7565-bff0-861e5d8a4a35', '01a0eb13-b3da-72b7-a357-c47332366c13', '4cb6e5a2-7db4-46fd-9574-6894f9707ff5', 'message', '2026-09-29 02:52:12.204997+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b42e-75fa-971a-6056b4f75654', '01a0eb13-b3da-72b7-a357-c47332366c13', '7b35be19-c7d4-449f-ab11-4a433d37ad58', 'message', '2026-09-29 02:52:12.204997+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b430-7031-99cd-852c8ae8c4ce', '01a0eb13-b3da-72b7-a357-c47332366c13', '67f82ecc-cc74-40ea-a79a-06405c7df2fb', 'message', '2026-09-29 02:52:12.204997+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b430-7fa6-bb9a-724ba65f60c5', '01a0eb13-b3da-72b7-a357-c47332366c13', '8b8e698b-a605-4fce-a713-9ffaf524d534', 'message', '2026-09-29 02:52:12.204997+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b45f-73fd-bf52-a7d8b9e81e91', '01a0eb13-b3da-72b7-a357-c47332366c13', '1c5fd87c-49a7-4b2f-bf3e-299706dfff2a', 'message', '2026-09-29 02:52:12.25462+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b460-799d-88e2-aa635b058642', '01a0eb13-b3da-72b7-a357-c47332366c13', '74701285-4c4b-448b-9830-18fd4644943e', 'message', '2026-09-29 02:52:12.25462+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b460-7ac2-ac0d-2c4b4d04a952', '01a0eb13-b3da-72b7-a357-c47332366c13', '06616427-d933-4ab0-a5d2-3adfd5b2ecb4', 'message', '2026-09-29 02:52:12.25462+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b461-7e70-b3a2-3a37a35503d5', '01a0eb13-b3da-72b7-a357-c47332366c13', 'e83cd7bf-e640-49ec-b7a7-f894b5087400', 'message', '2026-09-29 02:52:12.25462+00');
INSERT INTO public.source_object VALUES ('01a0eb13-b491-72fb-a148-cddf91768428', '01a0eb13-b3da-72b7-a357-c47332366c13', '63ea9dc4-0978-468e-bb74-16984b48883c', 'message', '2026-09-29 02:52:12.305142+00');
INSERT INTO public.source_object VALUES ('01a0eb13-baa7-73f8-a624-2dc2140ce3e8', '01a0eb13-b3da-72b7-a357-c47332366c13', '33ea0d1c-59b4-4015-95e7-19b0dc4a11b6', 'message', '2026-09-29 02:52:13.862526+00');
INSERT INTO public.source_object VALUES ('01a0eb13-baa8-70ae-b123-b9f8fb7df356', '01a0eb13-b3da-72b7-a357-c47332366c13', 'bffb4a0f-f94e-45f2-b6a0-f681b80b08f1', 'message', '2026-09-29 02:52:13.862526+00');
INSERT INTO public.source_object VALUES ('01a0eb13-bad4-7576-863e-d81d0565aa18', '01a0eb13-b3da-72b7-a357-c47332366c13', '8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6', 'message', '2026-09-29 02:52:13.907676+00');
INSERT INTO public.source_object VALUES ('01a0eb13-bb01-7eef-aea2-f710b3436409', '01a0eb13-b3da-72b7-a357-c47332366c13', '245648ae-4dd7-4e67-bd55-6d876219624c', 'message', '2026-09-29 02:52:13.95169+00');
INSERT INTO public.source_object VALUES ('01a0eb13-c113-75fd-9c18-f53e1336cf0b', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', 'f37f8310-5f55-419b-98f6-b8f9efc7077b', 'message', '2026-09-29 02:52:15.506738+00');
INSERT INTO public.source_object VALUES ('01a0eb13-c113-7ec5-bb1c-b698237a198b', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '4a65f7b7-8dab-46aa-b6e3-d1ffeccd92e5', 'message', '2026-09-29 02:52:15.506738+00');
INSERT INTO public.source_object VALUES ('01a0eb13-c114-704b-8549-e957b27245d3', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '55a551fa-858e-4259-bb80-660d2fcc1e6a', 'message', '2026-09-29 02:52:15.506738+00');
INSERT INTO public.source_object VALUES ('01a0eb13-c115-7d63-bb7a-6baff9a8e3e9', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', 'b4dba62c-fcfe-4f17-b895-fce840245c4b', 'message', '2026-09-29 02:52:15.506738+00');
INSERT INTO public.source_object VALUES ('01a0eb13-c115-7a6d-9851-f6b3460694b4', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', 'e52aab32-61d9-41fc-8587-2ea93e6a2280', 'message', '2026-09-29 02:52:15.506738+00');
INSERT INTO public.source_object VALUES ('01a0eb13-c116-75b6-8fa5-4842c042c6cb', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', 'b109ab9e-b2d4-4c0f-9efa-0447abcb2a89', 'message', '2026-09-29 02:52:15.506738+00');
INSERT INTO public.source_object VALUES ('01a0eb13-c116-7f63-be2d-28b8f0764211', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '62f89ae2-0190-49e8-b328-facba4b19adb', 'message', '2026-09-29 02:52:15.506738+00');
INSERT INTO public.source_object VALUES ('01a0eb13-c117-7401-b928-95676ff95fda', '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', 'ef44cadf-57a0-4097-8ecf-10695ac1dee0', 'message', '2026-09-29 02:52:15.506738+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0eb13-b3e6-7082-8972-95961ee4258b', '01a0eb13-b3e5-744a-9366-1afd904ab590', 'b8c4a48dea49380c9a264c28eadd2ee0bbeb1c07c2afed3657df3dfcaa003dcc', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "d0889bbf-4f07-4fcb-9e44-cefc6991f37e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:12.129701+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b3ea-7545-8529-4c53faf349a0', '01a0eb13-b3e9-7b74-88e2-e2416c70f8d2', '313bcc1bfcffa28ca8937d46ce792accf790c978cd3b4ffbc0ba7ca3e996ccf3', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "74a13137-7dfb-4f33-8c34-565591481d00", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:12.129701+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b3e9-7867-a892-8768a67a0310', '01a0eb13-b3e8-737a-91c9-c5375fcf455c', 'cbaba78c9b10c22bd174781e4946d204509c1faf5bfa7bea444c4b174f524291', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "a74b56ab-0957-415a-8ac9-649e4c3426cb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a74b56ab-0957-415a-8ac9-649e4c3426cb", "specialComments": []}', '2026-09-29 02:52:12.129701+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b42e-715b-bf3c-67f26abb22ad', '01a0eb13-b42d-7565-bff0-861e5d8a4a35', '48f7e9ed3223fac86c89fed47fea2a1be827347482ace27bcaa8a592b89f4eda', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "4cb6e5a2-7db4-46fd-9574-6894f9707ff5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:12.204997+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b430-76dd-865f-2bd240ffef59', '01a0eb13-b430-7031-99cd-852c8ae8c4ce', 'c5eadd3b95a3c8e5de86435280d361ad1d00fdb2786a8cd56cee94fa53eed6fc', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "67f82ecc-cc74-40ea-a79a-06405c7df2fb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:12.204997+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b42f-7b45-b68b-f6e99aee8575', '01a0eb13-b42e-75fa-971a-6056b4f75654', '7aa628ab8d1b33fa4a0651b82aeab76cf74d23e5c544dee0ff1315c1c4586682', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "7b35be19-c7d4-449f-ab11-4a433d37ad58", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "7b35be19-c7d4-449f-ab11-4a433d37ad58", "specialComments": []}', '2026-09-29 02:52:12.204997+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b461-731f-8749-818b3518b01f', '01a0eb13-b460-7ac2-ac0d-2c4b4d04a952', '1c4fdf8b0c639ae0c071b9695ab812081de9a1b24741720344b7f741974b9ece', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:12.25462+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b460-7dde-a568-c410fee4ff6b', '01a0eb13-b460-799d-88e2-aa635b058642', 'fe0e408fe9e8009d507fef8b728807d0ee399b5d367903e212bf702e84caaa38', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "74701285-4c4b-448b-9830-18fd4644943e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "74701285-4c4b-448b-9830-18fd4644943e", "specialComments": []}', '2026-09-29 02:52:12.25462+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b431-73a9-9d9a-ee0695e5d1bf', '01a0eb13-b430-7fa6-bb9a-724ba65f60c5', '55852e691edd6c7cbcf18ac40c5814055f5eba3e9f89edc24616e59ad0cffe2b', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "8b8e698b-a605-4fce-a713-9ffaf524d534", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "8b8e698b-a605-4fce-a713-9ffaf524d534", "specialComments": []}', '2026-09-29 02:52:12.204997+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b492-7430-86cd-b47a39ce8d6c', '01a0eb13-b491-72fb-a148-cddf91768428', 'b2d9710475052cbcd5b072e219f4d6fee84aed4dcc88e41821041817724559ac', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "63ea9dc4-0978-468e-bb74-16984b48883c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:12.305142+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b3eb-7ea0-b1d7-d644cc2a32ff', '01a0eb13-b3ea-77d0-a4c4-db60b0456980', 'c1d022b085f350c5d059f5220765b78195c6f03116b3ca98d7afd50142838827', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "c57a256d-a258-4e26-af72-b8f5dc4a5328", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c57a256d-a258-4e26-af72-b8f5dc4a5328", "specialComments": []}', '2026-09-29 02:52:12.129701+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b45f-7415-bf4a-b8be40922afe', '01a0eb13-b45f-73fd-bf52-a7d8b9e81e91', 'b08ce6896025ff621a441a1d4d7ebc9b8349c97dfae3d9f4510b70fc2e78cc39', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:12.25462+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-b462-7ea7-8cb6-d9dc3d223aea', '01a0eb13-b461-7e70-b3a2-3a37a35503d5', '186ce574a6f5e1da6457bb1a6a242443f7024eeca9fe3ba019569511f9a5d435', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "e83cd7bf-e640-49ec-b7a7-f894b5087400", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e83cd7bf-e640-49ec-b7a7-f894b5087400", "specialComments": []}', '2026-09-29 02:52:12.25462+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-baa8-7819-b61a-af25dc99d165', '01a0eb13-baa8-70ae-b123-b9f8fb7df356', 'f6de08bd11a97313cd1bffbfed2a49c3bbf30cf3f1f2b05da9e3a23b4405fe3a', 'And the compass?', '{"name": null, "role": "user", "chatId": "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:13.862526+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-baa8-7229-90ae-544a07a5b6b2', '01a0eb13-baa7-73f8-a624-2dc2140ce3e8', '17e1b43c2902bbe980eb01d45857514ce6f9e6397dd0e592d3847f4915dccf2f', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "specialComments": []}', '2026-09-29 02:52:13.862526+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-baa7-7899-8417-8d2af20060e7', '01a0eb13-b3ea-77d0-a4c4-db60b0456980', 'cfed99eb304c91e7553ef66b3e53ff1af1d63333e72b263e455a1b2b5a6a74dc', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "c57a256d-a258-4e26-af72-b8f5dc4a5328", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c57a256d-a258-4e26-af72-b8f5dc4a5328", "specialComments": []}', '2026-09-29 02:52:13.862526+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-bb00-72ff-944e-65602522f363', '01a0eb13-b45f-73fd-bf52-a7d8b9e81e91', 'cc941c7a8773e160fee830289b569b191e530538ae8b414b994906d414492ac0', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:13.95169+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-bb01-768d-8829-f36aeda1e65e', '01a0eb13-bb01-7eef-aea2-f710b3436409', 'bd10199879b8ff095bc344faeff90b34f00d459f36cc4e5546a530fef008982c', 'Let''s go.', '{"name": null, "role": "user", "chatId": "245648ae-4dd7-4e67-bd55-6d876219624c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:13.95169+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-bb00-7353-80ff-25d33aedd0a1', '01a0eb13-bad4-7576-863e-d81d0565aa18', '53967474367c08fd1c1d7c9a0e56b7fca381ad01ed98a868b2015ba3f7a58440', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "specialComments": []}', '2026-09-29 02:52:13.95169+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-bad4-7810-9a18-9356e74c53c0', '01a0eb13-bad4-7576-863e-d81d0565aa18', '8b492d6e0c4cf5d62c274b507a57a2cc449e1d6451fd6b8b9a6897896762c5bc', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "specialComments": []}', '2026-09-29 02:52:13.907676+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-c113-7398-a2ec-2494fd474f28', '01a0eb13-c113-75fd-9c18-f53e1336cf0b', 'd30bd7d13334b4bed3a934ed708d5b19ce0708bc0f16e5ed609b725052cacb5a', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "f37f8310-5f55-419b-98f6-b8f9efc7077b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:15.506738+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-c114-7e23-8431-d39725ec67e5', '01a0eb13-c114-704b-8549-e957b27245d3', 'db7b1737b9a3a9e2923177e0fdc852b8fa9e92f95ebd04c86c957c11315bfb3c', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "55a551fa-858e-4259-bb80-660d2fcc1e6a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:15.506738+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-c116-7e76-b174-79e561872974', '01a0eb13-c115-7a6d-9851-f6b3460694b4', '307d3b875cc26be83d9d9c4c0f3318af5b29f31b2e8f2ec12398aeff755d9346', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "e52aab32-61d9-41fc-8587-2ea93e6a2280", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:15.506738+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-c117-7967-9118-3c255087ec7a', '01a0eb13-c116-7f63-be2d-28b8f0764211', '8a65694d6c6ba2417bee7d0930d54786bdcba5fa5e3b36ba970b3957565f2a10', '{{specialcomment::branchedfrom::d6830dde-55bf-45d1-9dcc-a254722632ca::Harbor route::7b35be19-c7d4-449f-ab11-4a433d37ad58::}}', '{"name": null, "role": "char", "chatId": "62f89ae2-0190-49e8-b328-facba4b19adb", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::d6830dde-55bf-45d1-9dcc-a254722632ca::Harbor route::7b35be19-c7d4-449f-ab11-4a433d37ad58::}}"]}', '2026-09-29 02:52:15.506738+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-c117-791d-b1ab-5012376283f8', '01a0eb13-c117-7401-b928-95676ff95fda', '805dd656c0f859ead2c7038f22903babb435cd92ca6cd00edde515734925b077', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "ef44cadf-57a0-4097-8ecf-10695ac1dee0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-29 02:52:15.506738+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-c114-7b56-a8d4-29dd29760190', '01a0eb13-c113-7ec5-bb1c-b698237a198b', 'ac0434aeecb17f05627a83bdafd0ae5e7bd2c039e5a3c2d26be89f36041ef758', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "4a65f7b7-8dab-46aa-b6e3-d1ffeccd92e5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a74b56ab-0957-415a-8ac9-649e4c3426cb", "specialComments": []}', '2026-09-29 02:52:15.506738+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-c116-7129-b87e-bfb69ea5b6fa', '01a0eb13-c116-75b6-8fa5-4842c042c6cb', 'cc695dda9a75f4df204db672428ce54c3d0a7ab7b768d7ee192ec988e26dc8b6', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "b109ab9e-b2d4-4c0f-9efa-0447abcb2a89", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "7b35be19-c7d4-449f-ab11-4a433d37ad58", "specialComments": []}', '2026-09-29 02:52:15.506738+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0eb13-c115-73ae-b58d-43cd89c53978', '01a0eb13-c115-7d63-bb7a-6baff9a8e3e9', '10e407d4220a5db1df33bac370f628f613383bf3b7ae7c4b82df5a383a3b0cb1', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "b4dba62c-fcfe-4f17-b895-fce840245c4b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c57a256d-a258-4e26-af72-b8f5dc4a5328", "specialComments": []}', '2026-09-29 02:52:15.506738+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: summary; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8', '[{"op": "insert", "after": ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "c1d022b085f350c5d059f5220765b78195c6f03116b3ca98d7afd50142838827"], "member": ["4cb6e5a2-7db4-46fd-9574-6894f9707ff5", "48f7e9ed3223fac86c89fed47fea2a1be827347482ace27bcaa8a592b89f4eda"]}, {"op": "insert", "after": ["4cb6e5a2-7db4-46fd-9574-6894f9707ff5", "48f7e9ed3223fac86c89fed47fea2a1be827347482ace27bcaa8a592b89f4eda"], "member": ["7b35be19-c7d4-449f-ab11-4a433d37ad58", "7aa628ab8d1b33fa4a0651b82aeab76cf74d23e5c544dee0ff1315c1c4586682"]}, {"op": "insert", "after": ["7b35be19-c7d4-449f-ab11-4a433d37ad58", "7aa628ab8d1b33fa4a0651b82aeab76cf74d23e5c544dee0ff1315c1c4586682"], "member": ["67f82ecc-cc74-40ea-a79a-06405c7df2fb", "c5eadd3b95a3c8e5de86435280d361ad1d00fdb2786a8cd56cee94fa53eed6fc"]}, {"op": "insert", "after": ["67f82ecc-cc74-40ea-a79a-06405c7df2fb", "c5eadd3b95a3c8e5de86435280d361ad1d00fdb2786a8cd56cee94fa53eed6fc"], "member": ["8b8e698b-a605-4fce-a713-9ffaf524d534", "55852e691edd6c7cbcf18ac40c5814055f5eba3e9f89edc24616e59ad0cffe2b"]}]', '[{"new": ["4cb6e5a2-7db4-46fd-9574-6894f9707ff5", "48f7e9ed3223fac86c89fed47fea2a1be827347482ace27bcaa8a592b89f4eda"], "old": null, "kind": "append", "position": 4, "host_logical_id": "4cb6e5a2-7db4-46fd-9574-6894f9707ff5"}, {"new": ["7b35be19-c7d4-449f-ab11-4a433d37ad58", "7aa628ab8d1b33fa4a0651b82aeab76cf74d23e5c544dee0ff1315c1c4586682"], "old": null, "kind": "append", "position": 5, "host_logical_id": "7b35be19-c7d4-449f-ab11-4a433d37ad58"}, {"new": ["67f82ecc-cc74-40ea-a79a-06405c7df2fb", "c5eadd3b95a3c8e5de86435280d361ad1d00fdb2786a8cd56cee94fa53eed6fc"], "old": null, "kind": "append", "position": 6, "host_logical_id": "67f82ecc-cc74-40ea-a79a-06405c7df2fb"}, {"new": ["8b8e698b-a605-4fce-a713-9ffaf524d534", "55852e691edd6c7cbcf18ac40c5814055f5eba3e9f89edc24616e59ad0cffe2b"], "old": null, "kind": "append", "position": 7, "host_logical_id": "8b8e698b-a605-4fce-a713-9ffaf524d534"}]', '01a0eb13-b434-7d6b-a673-66c28804c676', '2026-09-29 02:52:12.204997+00');
INSERT INTO public.worldline_append VALUES (2, '01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8', '[{"op": "insert", "after": ["8b8e698b-a605-4fce-a713-9ffaf524d534", "55852e691edd6c7cbcf18ac40c5814055f5eba3e9f89edc24616e59ad0cffe2b"], "member": ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "b08ce6896025ff621a441a1d4d7ebc9b8349c97dfae3d9f4510b70fc2e78cc39"]}, {"op": "insert", "after": ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "b08ce6896025ff621a441a1d4d7ebc9b8349c97dfae3d9f4510b70fc2e78cc39"], "member": ["74701285-4c4b-448b-9830-18fd4644943e", "fe0e408fe9e8009d507fef8b728807d0ee399b5d367903e212bf702e84caaa38"]}, {"op": "insert", "after": ["74701285-4c4b-448b-9830-18fd4644943e", "fe0e408fe9e8009d507fef8b728807d0ee399b5d367903e212bf702e84caaa38"], "member": ["06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "1c4fdf8b0c639ae0c071b9695ab812081de9a1b24741720344b7f741974b9ece"]}, {"op": "insert", "after": ["06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "1c4fdf8b0c639ae0c071b9695ab812081de9a1b24741720344b7f741974b9ece"], "member": ["e83cd7bf-e640-49ec-b7a7-f894b5087400", "186ce574a6f5e1da6457bb1a6a242443f7024eeca9fe3ba019569511f9a5d435"]}]', '[{"new": ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "b08ce6896025ff621a441a1d4d7ebc9b8349c97dfae3d9f4510b70fc2e78cc39"], "old": null, "kind": "append", "position": 8, "host_logical_id": "1c5fd87c-49a7-4b2f-bf3e-299706dfff2a"}, {"new": ["74701285-4c4b-448b-9830-18fd4644943e", "fe0e408fe9e8009d507fef8b728807d0ee399b5d367903e212bf702e84caaa38"], "old": null, "kind": "append", "position": 9, "host_logical_id": "74701285-4c4b-448b-9830-18fd4644943e"}, {"new": ["06616427-d933-4ab0-a5d2-3adfd5b2ecb4", "1c4fdf8b0c639ae0c071b9695ab812081de9a1b24741720344b7f741974b9ece"], "old": null, "kind": "append", "position": 10, "host_logical_id": "06616427-d933-4ab0-a5d2-3adfd5b2ecb4"}, {"new": ["e83cd7bf-e640-49ec-b7a7-f894b5087400", "186ce574a6f5e1da6457bb1a6a242443f7024eeca9fe3ba019569511f9a5d435"], "old": null, "kind": "append", "position": 11, "host_logical_id": "e83cd7bf-e640-49ec-b7a7-f894b5087400"}]', '01a0eb13-b465-7272-b2ef-d21d022885cb', '2026-09-29 02:52:12.25462+00');
INSERT INTO public.worldline_append VALUES (3, '01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8', '[{"op": "insert", "after": ["e83cd7bf-e640-49ec-b7a7-f894b5087400", "186ce574a6f5e1da6457bb1a6a242443f7024eeca9fe3ba019569511f9a5d435"], "member": ["63ea9dc4-0978-468e-bb74-16984b48883c", "b2d9710475052cbcd5b072e219f4d6fee84aed4dcc88e41821041817724559ac"]}]', '[{"new": ["63ea9dc4-0978-468e-bb74-16984b48883c", "b2d9710475052cbcd5b072e219f4d6fee84aed4dcc88e41821041817724559ac"], "old": null, "kind": "append", "position": 12, "host_logical_id": "63ea9dc4-0978-468e-bb74-16984b48883c"}]', '01a0eb13-b495-7e36-9946-bbeaf6a2ed2b', '2026-09-29 02:52:12.305142+00');
INSERT INTO public.worldline_append VALUES (4, '01a0eb13-baab-7f4c-90b1-caddc8d6b497', '[{"op": "insert", "after": ["bffb4a0f-f94e-45f2-b6a0-f681b80b08f1", "f6de08bd11a97313cd1bffbfed2a49c3bbf30cf3f1f2b05da9e3a23b4405fe3a"], "member": ["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "8b492d6e0c4cf5d62c274b507a57a2cc449e1d6451fd6b8b9a6897896762c5bc"]}]', '[{"new": ["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "8b492d6e0c4cf5d62c274b507a57a2cc449e1d6451fd6b8b9a6897896762c5bc"], "old": null, "kind": "append", "position": 15, "host_logical_id": "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6"}]', '01a0eb13-bad7-7302-b654-e277544b2ec9', '2026-09-29 02:52:13.907676+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8', 1, '01a0eb13-b3da-72b7-a357-c47332366c13', '{}', 'import', '34dcac788b8a0a60257215b50b71ac6b386490a94579720a4b2cafd3724a1b80', '{"ops": [{"op": "set", "members": [["d0889bbf-4f07-4fcb-9e44-cefc6991f37e", "b8c4a48dea49380c9a264c28eadd2ee0bbeb1c07c2afed3657df3dfcaa003dcc"], ["a74b56ab-0957-415a-8ac9-649e4c3426cb", "cbaba78c9b10c22bd174781e4946d204509c1faf5bfa7bea444c4b174f524291"], ["74a13137-7dfb-4f33-8c34-565591481d00", "313bcc1bfcffa28ca8937d46ce792accf790c978cd3b4ffbc0ba7ca3e996ccf3"], ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "c1d022b085f350c5d059f5220765b78195c6f03116b3ca98d7afd50142838827"]]}], "changes": [{"new": ["d0889bbf-4f07-4fcb-9e44-cefc6991f37e", "b8c4a48dea49380c9a264c28eadd2ee0bbeb1c07c2afed3657df3dfcaa003dcc"], "old": null, "kind": "append", "position": 0, "host_logical_id": "d0889bbf-4f07-4fcb-9e44-cefc6991f37e"}, {"new": ["a74b56ab-0957-415a-8ac9-649e4c3426cb", "cbaba78c9b10c22bd174781e4946d204509c1faf5bfa7bea444c4b174f524291"], "old": null, "kind": "append", "position": 1, "host_logical_id": "a74b56ab-0957-415a-8ac9-649e4c3426cb"}, {"new": ["74a13137-7dfb-4f33-8c34-565591481d00", "313bcc1bfcffa28ca8937d46ce792accf790c978cd3b4ffbc0ba7ca3e996ccf3"], "old": null, "kind": "append", "position": 2, "host_logical_id": "74a13137-7dfb-4f33-8c34-565591481d00"}, {"new": ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "c1d022b085f350c5d059f5220765b78195c6f03116b3ca98d7afd50142838827"], "old": null, "kind": "append", "position": 3, "host_logical_id": "c57a256d-a258-4e26-af72-b8f5dc4a5328"}]}', '2026-09-29 02:52:12.129701+00', '01a0eb13-b3ec-7e56-b714-56f51a997b15');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0eb13-baab-7f4c-90b1-caddc8d6b497', 2, '01a0eb13-b3da-72b7-a357-c47332366c13', '{01a0eb13-b3ee-76a5-9e98-56ca84bd4ae8}', 'edit', 'e4d2ac9c0c08b8f1c04549c70623bc7a193b1f4df08adad8824e5019d70a711a', '{"ops": [{"op": "replace", "to": ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "cfed99eb304c91e7553ef66b3e53ff1af1d63333e72b263e455a1b2b5a6a74dc"], "from": ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "c1d022b085f350c5d059f5220765b78195c6f03116b3ca98d7afd50142838827"]}, {"op": "insert", "after": ["63ea9dc4-0978-468e-bb74-16984b48883c", "b2d9710475052cbcd5b072e219f4d6fee84aed4dcc88e41821041817724559ac"], "member": ["33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "17e1b43c2902bbe980eb01d45857514ce6f9e6397dd0e592d3847f4915dccf2f"]}, {"op": "insert", "after": ["33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "17e1b43c2902bbe980eb01d45857514ce6f9e6397dd0e592d3847f4915dccf2f"], "member": ["bffb4a0f-f94e-45f2-b6a0-f681b80b08f1", "f6de08bd11a97313cd1bffbfed2a49c3bbf30cf3f1f2b05da9e3a23b4405fe3a"]}], "changes": [{"new": ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "cfed99eb304c91e7553ef66b3e53ff1af1d63333e72b263e455a1b2b5a6a74dc"], "old": ["c57a256d-a258-4e26-af72-b8f5dc4a5328", "c1d022b085f350c5d059f5220765b78195c6f03116b3ca98d7afd50142838827"], "kind": "edit", "position": 3, "host_logical_id": "c57a256d-a258-4e26-af72-b8f5dc4a5328"}, {"new": ["33ea0d1c-59b4-4015-95e7-19b0dc4a11b6", "17e1b43c2902bbe980eb01d45857514ce6f9e6397dd0e592d3847f4915dccf2f"], "old": null, "kind": "append", "position": 13, "host_logical_id": "33ea0d1c-59b4-4015-95e7-19b0dc4a11b6"}, {"new": ["bffb4a0f-f94e-45f2-b6a0-f681b80b08f1", "f6de08bd11a97313cd1bffbfed2a49c3bbf30cf3f1f2b05da9e3a23b4405fe3a"], "old": null, "kind": "append", "position": 14, "host_logical_id": "bffb4a0f-f94e-45f2-b6a0-f681b80b08f1"}]}', '2026-09-29 02:52:13.862526+00', '01a0eb13-baaa-7b45-ad7d-2f7fd6a1427a');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0eb13-bb04-7179-80b4-698d30dfc66e', 3, '01a0eb13-b3da-72b7-a357-c47332366c13', '{01a0eb13-baab-7f4c-90b1-caddc8d6b497}', 'reconciliation', 'de38c534f7763ca07028a52b7851f55cf39fc63a6c6048770b0bd480d568be1f', '{"ops": [{"op": "replace", "to": ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "cc941c7a8773e160fee830289b569b191e530538ae8b414b994906d414492ac0"], "from": ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "b08ce6896025ff621a441a1d4d7ebc9b8349c97dfae3d9f4510b70fc2e78cc39"]}, {"op": "replace", "to": ["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "53967474367c08fd1c1d7c9a0e56b7fca381ad01ed98a868b2015ba3f7a58440"], "from": ["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "8b492d6e0c4cf5d62c274b507a57a2cc449e1d6451fd6b8b9a6897896762c5bc"]}, {"op": "insert", "after": ["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "53967474367c08fd1c1d7c9a0e56b7fca381ad01ed98a868b2015ba3f7a58440"], "member": ["245648ae-4dd7-4e67-bd55-6d876219624c", "bd10199879b8ff095bc344faeff90b34f00d459f36cc4e5546a530fef008982c"]}], "changes": [{"new": ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "cc941c7a8773e160fee830289b569b191e530538ae8b414b994906d414492ac0"], "old": ["1c5fd87c-49a7-4b2f-bf3e-299706dfff2a", "b08ce6896025ff621a441a1d4d7ebc9b8349c97dfae3d9f4510b70fc2e78cc39"], "kind": "disable", "position": 8, "host_logical_id": "1c5fd87c-49a7-4b2f-bf3e-299706dfff2a"}, {"new": ["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "53967474367c08fd1c1d7c9a0e56b7fca381ad01ed98a868b2015ba3f7a58440"], "old": ["8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6", "8b492d6e0c4cf5d62c274b507a57a2cc449e1d6451fd6b8b9a6897896762c5bc"], "kind": "swipe", "position": 15, "host_logical_id": "8afc1ddf-a184-4d4c-9d4e-a07fa45a16e6"}, {"new": ["245648ae-4dd7-4e67-bd55-6d876219624c", "bd10199879b8ff095bc344faeff90b34f00d459f36cc4e5546a530fef008982c"], "old": null, "kind": "append", "position": 16, "host_logical_id": "245648ae-4dd7-4e67-bd55-6d876219624c"}]}', '2026-09-29 02:52:13.95169+00', '01a0eb13-bb03-7482-ae17-d17b3442bde0');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0eb13-c119-7fa6-beec-5af802c5ff91', 4, '01a0eb13-c10d-7221-ba7a-4ca8c4ac8bba', '{}', 'branch', '539c506b8d241201afb46ee7d78eecf0af66968dada431a94d779bcf982cca3e', '{"ops": [{"op": "set", "members": [["f37f8310-5f55-419b-98f6-b8f9efc7077b", "d30bd7d13334b4bed3a934ed708d5b19ce0708bc0f16e5ed609b725052cacb5a"], ["4a65f7b7-8dab-46aa-b6e3-d1ffeccd92e5", "ac0434aeecb17f05627a83bdafd0ae5e7bd2c039e5a3c2d26be89f36041ef758"], ["55a551fa-858e-4259-bb80-660d2fcc1e6a", "db7b1737b9a3a9e2923177e0fdc852b8fa9e92f95ebd04c86c957c11315bfb3c"], ["b4dba62c-fcfe-4f17-b895-fce840245c4b", "10e407d4220a5db1df33bac370f628f613383bf3b7ae7c4b82df5a383a3b0cb1"], ["e52aab32-61d9-41fc-8587-2ea93e6a2280", "307d3b875cc26be83d9d9c4c0f3318af5b29f31b2e8f2ec12398aeff755d9346"], ["b109ab9e-b2d4-4c0f-9efa-0447abcb2a89", "cc695dda9a75f4df204db672428ce54c3d0a7ab7b768d7ee192ec988e26dc8b6"], ["62f89ae2-0190-49e8-b328-facba4b19adb", "8a65694d6c6ba2417bee7d0930d54786bdcba5fa5e3b36ba970b3957565f2a10"], ["ef44cadf-57a0-4097-8ecf-10695ac1dee0", "805dd656c0f859ead2c7038f22903babb435cd92ca6cd00edde515734925b077"]]}], "changes": [{"new": ["f37f8310-5f55-419b-98f6-b8f9efc7077b", "d30bd7d13334b4bed3a934ed708d5b19ce0708bc0f16e5ed609b725052cacb5a"], "old": null, "kind": "append", "position": 0, "host_logical_id": "f37f8310-5f55-419b-98f6-b8f9efc7077b"}, {"new": ["4a65f7b7-8dab-46aa-b6e3-d1ffeccd92e5", "ac0434aeecb17f05627a83bdafd0ae5e7bd2c039e5a3c2d26be89f36041ef758"], "old": null, "kind": "append", "position": 1, "host_logical_id": "4a65f7b7-8dab-46aa-b6e3-d1ffeccd92e5"}, {"new": ["55a551fa-858e-4259-bb80-660d2fcc1e6a", "db7b1737b9a3a9e2923177e0fdc852b8fa9e92f95ebd04c86c957c11315bfb3c"], "old": null, "kind": "append", "position": 2, "host_logical_id": "55a551fa-858e-4259-bb80-660d2fcc1e6a"}, {"new": ["b4dba62c-fcfe-4f17-b895-fce840245c4b", "10e407d4220a5db1df33bac370f628f613383bf3b7ae7c4b82df5a383a3b0cb1"], "old": null, "kind": "append", "position": 3, "host_logical_id": "b4dba62c-fcfe-4f17-b895-fce840245c4b"}, {"new": ["e52aab32-61d9-41fc-8587-2ea93e6a2280", "307d3b875cc26be83d9d9c4c0f3318af5b29f31b2e8f2ec12398aeff755d9346"], "old": null, "kind": "append", "position": 4, "host_logical_id": "e52aab32-61d9-41fc-8587-2ea93e6a2280"}, {"new": ["b109ab9e-b2d4-4c0f-9efa-0447abcb2a89", "cc695dda9a75f4df204db672428ce54c3d0a7ab7b768d7ee192ec988e26dc8b6"], "old": null, "kind": "append", "position": 5, "host_logical_id": "b109ab9e-b2d4-4c0f-9efa-0447abcb2a89"}, {"new": ["62f89ae2-0190-49e8-b328-facba4b19adb", "8a65694d6c6ba2417bee7d0930d54786bdcba5fa5e3b36ba970b3957565f2a10"], "old": null, "kind": "append", "position": 6, "host_logical_id": "62f89ae2-0190-49e8-b328-facba4b19adb"}, {"new": ["ef44cadf-57a0-4097-8ecf-10695ac1dee0", "805dd656c0f859ead2c7038f22903babb435cd92ca6cd00edde515734925b077"], "old": null, "kind": "append", "position": 7, "host_logical_id": "ef44cadf-57a0-4097-8ecf-10695ac1dee0"}]}', '2026-09-29 02:52:15.506738+00', '01a0eb13-c118-7f30-a764-68b838df56a6');


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


