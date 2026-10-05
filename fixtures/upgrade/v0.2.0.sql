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
    CONSTRAINT owner_repair_kind_check CHECK ((kind = ANY (ARRAY['thread_close'::text, 'thread_reopen'::text, 'secret_found_out'::text, 'secret_keep'::text, 'fact_retract'::text, 'fact_correct'::text, 'name_split'::text, 'fact_lock'::text])))
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
    CONSTRAINT projection_generation_kind_check CHECK ((kind = ANY (ARRAY['extract'::text, 'embed'::text, 'summarize'::text, 'canon'::text])))
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

INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 0, '01a10c2a-2e8d-7a94-9b28-f1f2ac28a315', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 1, '01a10c2a-2e8f-7e14-86a6-f16a407f8b3b', NULL, 0, 'fece23e4cc335634193bc7945e032b0e');
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 2, '01a10c2a-2e90-7f4b-bab3-dcfb462e399a', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 3, '01a10c2a-3745-79fa-b483-b4d6e5e00d41', NULL, 1, '55f6f54053d1301a814a2ca19a028160');
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 4, '01a10c2a-2ee7-7a18-9d0c-a8c6e443ca39', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 5, '01a10c2a-2ee8-7522-82cc-b878074ee8e7', NULL, 2, '0139caf3ed29db317db5ba99c2b89936');
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 6, '01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 7, '01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd', NULL, 3, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 8, '01a10c2a-379a-7433-a394-5d60dc243155', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 9, '01a10c2a-2f16-75a4-a7c8-29986adde78e', NULL, 3, '8ed7cb63861d8100d1a148846279d9cf');
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 10, '01a10c2a-2f17-7795-8d4f-614ced4f918b', NULL, 4, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 11, '01a10c2a-2f18-7048-b375-c57832174f13', NULL, 4, 'b9e47c9e7e667a0515a133531ea68b2c');
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 12, '01a10c2a-2f41-70ed-983a-0da2c090f1fd', NULL, 5, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 13, '01a10c2a-3746-7b46-bf67-c12b9d867d9e', NULL, 5, 'c38dbbd747af0c4fe99ad0f7f67020a7');
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 14, '01a10c2a-3747-7a0f-ab47-7723b7cae834', NULL, 6, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 15, '01a10c2a-379b-7acb-b2ea-36f7af3d5931', NULL, 6, 'bf196a49fa68f0007ddc97a668d6eab0');
INSERT INTO public.active_membership VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 16, '01a10c2a-379c-7ae9-868c-fec057e3d4e1', NULL, 7, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 0, '01a10c2a-3bb4-7391-a2a2-b04dd06053f0', NULL, 0, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 1, '01a10c2a-3bb5-7404-a721-7dc43e88b2ac', NULL, 0, '309969c1d3c1a6d2c39636ab91a4b0d2');
INSERT INTO public.active_membership VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 2, '01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4', NULL, 1, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 3, '01a10c2a-3bb7-7c10-80b0-5340677a4815', NULL, 1, '14d1ba3d3b58b090344bb4958ea038d0');
INSERT INTO public.active_membership VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 4, '01a10c2a-3bb8-72cb-9e72-b70a57729101', NULL, 2, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 5, '01a10c2a-3bb9-7711-9bf2-0290167ee6c9', NULL, 2, 'f9b2bb8efbeba9b95180766a67980a10');
INSERT INTO public.active_membership VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 6, '01a10c2a-3bba-7aa9-8e42-d003a0c086ca', NULL, NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 7, '01a10c2a-3bbb-7052-bdf8-0970fe3b068d', NULL, 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a10c2a-3562-7582-9f07-ad77c3008609', '01a10c2a-2f18-7048-b375-c57832174f13', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a10c2a-357c-740d-9f7f-db0cab9024c1', '01a10c2a-2f16-75a4-a7c8-29986adde78e', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a10c2a-35b3-7950-9d8a-4e22fa75ee90', '01a10c2a-2ee8-7522-82cc-b878074ee8e7', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a10c2a-35cc-7345-8c3b-c2d2e74ddd8c', '01a10c2a-2e91-787f-a259-39ebc6f2dda2', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a10c2a-35cc-7345-8c3b-c2d2e74ddd8c', '01a10c2a-2e91-787f-a259-39ebc6f2dda2', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a10c2a-3627-79ea-9e6e-c150f73b5064', '01a10c2a-2e8f-7e14-86a6-f16a407f8b3b', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a10c2a-3627-79ea-9e6e-c150f73b5064', '01a10c2a-2e8f-7e14-86a6-f16a407f8b3b', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a10c2a-3a92-788a-aef2-5c9f589b5cbe', '01a10c2a-379b-7acb-b2ea-36f7af3d5931', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a10c2a-3ac4-7ddb-9a8f-9783712e6eda', '01a10c2a-2f18-7048-b375-c57832174f13', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a10c2a-3ade-766d-a809-cb6c2fb14925', '01a10c2a-2f16-75a4-a7c8-29986adde78e', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a10c2a-3b03-7fc7-85dd-fa4a9d5487f2', '01a10c2a-2ee8-7522-82cc-b878074ee8e7', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a10c2a-3b1c-77b0-a228-6b2ead3e1813', '01a10c2a-3745-79fa-b483-b4d6e5e00d41', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a10c2a-3b1c-77b0-a228-6b2ead3e1813', '01a10c2a-3745-79fa-b483-b4d6e5e00d41', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a10c2a-3fa9-7312-a89b-6cbff0686661', '01a10c2a-3bb9-7711-9bf2-0290167ee6c9', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a10c2a-3fc4-7b60-b03e-0133198b03d3', '01a10c2a-3bb7-7c10-80b0-5340677a4815', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a10c2a-3fc4-7b60-b03e-0133198b03d3', '01a10c2a-3bb7-7c10-80b0-5340677a4815', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a10c2a-3fdb-73f2-95e8-73f6ca5d34a7', '01a10c2a-3bb5-7404-a721-7dc43e88b2ac', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a10c2a-3fdb-73f2-95e8-73f6ca5d34a7', '01a10c2a-3bb5-7404-a721-7dc43e88b2ac', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL, NULL, NULL);


--
-- Data for Name: canon_applied; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: canon_manifest; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'pocketrisu', NULL, 'e4ad1406-ca8e-4235-9ab9-11046334e29d', '2026-10-05 13:04:13.445386+00', NULL, NULL, NULL, '01a10c2a-379e-7504-96c8-5bd11799666b', '42fb3278315abe4f7dca0f450ec17cc046c16b8173b52f807964e667673c501c', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL);
INSERT INTO public.conversation VALUES ('01a10c2a-3baf-754d-9ed5-e079f7126b6c', 'pocketrisu', NULL, 'c8a5360e-835a-4410-9218-6e74646a0bca', '2026-10-05 13:04:16.815298+00', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'e4ad1406-ca8e-4235-9ab9-11046334e29d', 'e32a2647-f28d-455f-b30b-157ffacbf186', '01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 'b32ce5dd7f1e90a18ccea031a5a666446c91147279327ecb2b83835078d43e34', 'Mina', 'Upgrade fixture', 'Takumi', false, NULL, NULL, NULL);


--
-- Data for Name: entity_link; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a10c2a-3562-7582-9f07-ad77c3008609', '01a10c2a-2f18-7048-b375-c57832174f13', 'ac3f9dfb3fb7bd53b49dbaf5dc7d23bb', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:15.202327+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a10c2a-2f17-7795-8d4f-614ced4f918b,01a10c2a-2f18-7048-b375-c57832174f13}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-357c-740d-9f7f-db0cab9024c1', '01a10c2a-2f16-75a4-a7c8-29986adde78e', 'd1e97e54504867c317e36e7d45f85772', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:15.228874+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a10c2a-2f15-77a5-981c-4062f17a9c7b,01a10c2a-2f16-75a4-a7c8-29986adde78e}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3599-7384-97fe-ecee9b44a411', '01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd', '5f696992a760818427af506c58bf38c4', 'extract-v13', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-10-05 13:04:15.257424+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b,01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-35b3-7950-9d8a-4e22fa75ee90', '01a10c2a-2ee8-7522-82cc-b878074ee8e7', '40b23daf24dcb4010577e562053849f8', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:15.28359+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a10c2a-2ee7-7a18-9d0c-a8c6e443ca39,01a10c2a-2ee8-7522-82cc-b878074ee8e7}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-35cc-7345-8c3b-c2d2e74ddd8c', '01a10c2a-2e91-787f-a259-39ebc6f2dda2', 'bd3804671b3de628a8a87aa03144bf3f', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:15.308883+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a10c2a-2e90-7f4b-bab3-dcfb462e399a,01a10c2a-2e91-787f-a259-39ebc6f2dda2}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3627-79ea-9e6e-c150f73b5064', '01a10c2a-2e8f-7e14-86a6-f16a407f8b3b', 'fece23e4cc335634193bc7945e032b0e', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:15.399226+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a10c2a-2e8d-7a94-9b28-f1f2ac28a315,01a10c2a-2e8f-7e14-86a6-f16a407f8b3b}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3a92-788a-aef2-5c9f589b5cbe', '01a10c2a-379b-7acb-b2ea-36f7af3d5931', 'bf196a49fa68f0007ddc97a668d6eab0', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:16.529943+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a10c2a-3747-7a0f-ab47-7723b7cae834,01a10c2a-379b-7acb-b2ea-36f7af3d5931}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3aa9-70a1-a8e5-06300b6b8198', '01a10c2a-3746-7b46-bf67-c12b9d867d9e', 'c38dbbd747af0c4fe99ad0f7f67020a7', 'extract-v13', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-10-05 13:04:16.553913+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a10c2a-2f41-70ed-983a-0da2c090f1fd,01a10c2a-3746-7b46-bf67-c12b9d867d9e}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3ac4-7ddb-9a8f-9783712e6eda', '01a10c2a-2f18-7048-b375-c57832174f13', 'b9e47c9e7e667a0515a133531ea68b2c', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:16.580547+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a10c2a-2f17-7795-8d4f-614ced4f918b,01a10c2a-2f18-7048-b375-c57832174f13}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3ade-766d-a809-cb6c2fb14925', '01a10c2a-2f16-75a4-a7c8-29986adde78e', '8ed7cb63861d8100d1a148846279d9cf', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:16.606087+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b,01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd,01a10c2a-2f16-75a4-a7c8-29986adde78e}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3b03-7fc7-85dd-fa4a9d5487f2', '01a10c2a-2ee8-7522-82cc-b878074ee8e7', '0139caf3ed29db317db5ba99c2b89936', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:16.643845+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a10c2a-2ee7-7a18-9d0c-a8c6e443ca39,01a10c2a-2ee8-7522-82cc-b878074ee8e7}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3b1c-77b0-a228-6b2ead3e1813', '01a10c2a-3745-79fa-b483-b4d6e5e00d41', '55f6f54053d1301a814a2ca19a028160', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:16.668244+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a10c2a-2e90-7f4b-bab3-dcfb462e399a,01a10c2a-3745-79fa-b483-b4d6e5e00d41}', NULL, '{"secrets": [], "threads": [], "entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3fa9-7312-a89b-6cbff0686661', '01a10c2a-3bb9-7711-9bf2-0290167ee6c9', 'f9b2bb8efbeba9b95180766a67980a10', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:17.833541+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a10c2a-3bb8-72cb-9e72-b70a57729101,01a10c2a-3bb9-7711-9bf2-0290167ee6c9}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3fc4-7b60-b03e-0133198b03d3', '01a10c2a-3bb7-7c10-80b0-5340677a4815', '14d1ba3d3b58b090344bb4958ea038d0', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:17.860247+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4,01a10c2a-3bb7-7c10-80b0-5340677a4815}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a10c2a-3fdb-73f2-95e8-73f6ca5d34a7', '01a10c2a-3bb5-7404-a721-7dc43e88b2ac', '309969c1d3c1a6d2c39636ab91a4b0d2', 'extract-v13', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-10-05 13:04:17.883912+00', 'extract-5235d13a80ba3a7498b825a56d1758c0', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a10c2a-3bb4-7391-a2a2-b04dd06053f0,01a10c2a-3bb5-7404-a721-7dc43e88b2ac}', NULL, '{"secrets": [], "threads": [], "entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a10c2a-2e92-7bee-819d-977b2399067c', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'manifest', '072165c9c4bf1b76f45923cc43fcd8645a7a68cfac28e3110d2065af10e641f6', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37:072165c9c4bf1b76f45923cc43fcd8645a7a68cfac28e3110d2065af10e641f6:manifest', '2026-10-05 13:04:13.452146+00', '{"chat_id": "e4ad1406-ca8e-4235-9ab9-11046334e29d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["61857019-d61e-47bd-ac35-9556a4737c79", "438ba2197046e81a69e66450d6f66855eebdba438d25aa296d117098d223e55e", "user", null, null, null, 0, null, null], ["af7eb463-5221-4b4a-ad6a-a1cde8a107d4", "48bb58cee73429e421964b3d06aaec3aa88b99d0ecfc88a04bfd70e731a8678a", "char", null, null, null, 0, "af7eb463-5221-4b4a-ad6a-a1cde8a107d4", null], ["1af17204-bcb8-4c25-9b4b-bc8c27161ec1", "79b6404077a6b1bf74cc73e0f21fba498bc622cf41f2512fed2b9dcb63a106dc", "user", null, null, null, 0, null, null], ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "de7d1eb4801be2759af17d49d5387d57bc4a8116c7886c385da8b5e0648b3b48", "char", null, null, null, 0, "26fdd18c-bcbb-49cc-baf9-3a84971867ba", null]]}');
INSERT INTO public.host_observation VALUES ('01a10c2a-2eec-7b4c-ba4c-2c57094da8a0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'manifest', '316946db94430f92403db50477d1032ace2183a3a97ccee8f6cc8c82399191b6', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37:316946db94430f92403db50477d1032ace2183a3a97ccee8f6cc8c82399191b6:manifest', '2026-10-05 13:04:13.542253+00', '{"chat_id": "e4ad1406-ca8e-4235-9ab9-11046334e29d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["acf00265-39de-4dc1-9ba0-527c1ea57862", "d806b686917b65167e3e6ccc52e2abeb09523b1cf4be3a19460d792a0f93d686", "user", null, null, null, 0, null, null], ["e32a2647-f28d-455f-b30b-157ffacbf186", "80da8646cc274798d103621ddadb5cbe0ac36f03b41ec4942f0b7f46a73ee36a", "char", null, null, null, 0, "e32a2647-f28d-455f-b30b-157ffacbf186", null], ["d59cf364-446e-493b-8031-774d0c6d56dc", "974009aa9786ed9674e495ff5ce69125f8e08381f7a7413284198cdba68ad561", "user", null, null, null, 0, null, null], ["bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "6f2ffc9e558dbf753ac836460e17c25741bdf6e71dd5a09ebb05603fe6d70b8b", "char", null, null, null, 0, "bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", null]], "base_manifest_hash": "072165c9c4bf1b76f45923cc43fcd8645a7a68cfac28e3110d2065af10e641f6"}');
INSERT INTO public.host_observation VALUES ('01a10c2a-2f1b-7b66-b0bc-4247d512e437', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'manifest', 'd7ffd4ab50896842d1230e961a36a8b1eb86fbf6d63b5bbbfe75d0b8216eb9d2', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37:d7ffd4ab50896842d1230e961a36a8b1eb86fbf6d63b5bbbfe75d0b8216eb9d2:manifest', '2026-10-05 13:04:13.588909+00', '{"chat_id": "e4ad1406-ca8e-4235-9ab9-11046334e29d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["c3f58464-fec1-480e-8564-ed37d52e5144", "844b5aa66a759804aab8b9417f83d8516fe8dad7a285826e46e3859b9d8a490c", "user", null, null, null, 0, null, null], ["1c451005-49fb-45a5-9cae-d3f9f84d651e", "5b641c5de15b30d2b76a71a91316756963d29073b9888cddf14aece3d6790907", "char", null, null, null, 0, "1c451005-49fb-45a5-9cae-d3f9f84d651e", null], ["359551e1-93a2-4dfe-a8e2-ea4df82f1604", "232fb75f443c71abcaa43084f7dd1e0c82c6c94d06c19e15e142013de08f4640", "user", null, null, null, 0, null, null], ["0ff13094-67b2-44a4-bbd3-3c814ab836e8", "fafaff9bbec4433e590cee473992c75ce8fe93c8a599567302f5ce68577081c1", "char", null, null, null, 0, "0ff13094-67b2-44a4-bbd3-3c814ab836e8", null]], "base_manifest_hash": "316946db94430f92403db50477d1032ace2183a3a97ccee8f6cc8c82399191b6"}');
INSERT INTO public.host_observation VALUES ('01a10c2a-2f43-7cfa-8476-ff3aad16e924', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'manifest', '60360b25f5c025d5a6f32d31ec5f7730f1d132da06b16af490cd2d640fa8082b', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37:60360b25f5c025d5a6f32d31ec5f7730f1d132da06b16af490cd2d640fa8082b:manifest', '2026-10-05 13:04:13.632368+00', '{"chat_id": "e4ad1406-ca8e-4235-9ab9-11046334e29d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "73461b6434f614e2eb37e20e380caa8551e035e8f71c62dbf39b73ddc044ed1a", "user", null, null, null, 0, null, null]], "base_manifest_hash": "d7ffd4ab50896842d1230e961a36a8b1eb86fbf6d63b5bbbfe75d0b8216eb9d2"}');
INSERT INTO public.host_observation VALUES ('01a10c2a-3749-785b-b2ae-ddda8915b4ec', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'manifest', 'b781c2891a1df1654d91531646bcf59ee0b94c011cec80c58d916dce2a35a1e6', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37:b781c2891a1df1654d91531646bcf59ee0b94c011cec80c58d916dce2a35a1e6:manifest', '2026-10-05 13:04:15.685127+00', '{"chat_id": "e4ad1406-ca8e-4235-9ab9-11046334e29d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["61857019-d61e-47bd-ac35-9556a4737c79", "438ba2197046e81a69e66450d6f66855eebdba438d25aa296d117098d223e55e", "user", null, null, null, 0, null, null], ["af7eb463-5221-4b4a-ad6a-a1cde8a107d4", "48bb58cee73429e421964b3d06aaec3aa88b99d0ecfc88a04bfd70e731a8678a", "char", null, null, null, 0, "af7eb463-5221-4b4a-ad6a-a1cde8a107d4", null], ["1af17204-bcb8-4c25-9b4b-bc8c27161ec1", "79b6404077a6b1bf74cc73e0f21fba498bc622cf41f2512fed2b9dcb63a106dc", "user", null, null, null, 0, null, null], ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "9cc84a64d410b19a5f983125ad08a8dd5cefc3aebc26ed55f77dc52c41b8237a", "char", null, null, null, 0, "26fdd18c-bcbb-49cc-baf9-3a84971867ba", null], ["acf00265-39de-4dc1-9ba0-527c1ea57862", "d806b686917b65167e3e6ccc52e2abeb09523b1cf4be3a19460d792a0f93d686", "user", null, null, null, 0, null, null], ["e32a2647-f28d-455f-b30b-157ffacbf186", "80da8646cc274798d103621ddadb5cbe0ac36f03b41ec4942f0b7f46a73ee36a", "char", null, null, null, 0, "e32a2647-f28d-455f-b30b-157ffacbf186", null], ["d59cf364-446e-493b-8031-774d0c6d56dc", "974009aa9786ed9674e495ff5ce69125f8e08381f7a7413284198cdba68ad561", "user", null, null, null, 0, null, null], ["bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "6f2ffc9e558dbf753ac836460e17c25741bdf6e71dd5a09ebb05603fe6d70b8b", "char", null, null, null, 0, "bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", null], ["c3f58464-fec1-480e-8564-ed37d52e5144", "844b5aa66a759804aab8b9417f83d8516fe8dad7a285826e46e3859b9d8a490c", "user", null, null, null, 0, null, null], ["1c451005-49fb-45a5-9cae-d3f9f84d651e", "5b641c5de15b30d2b76a71a91316756963d29073b9888cddf14aece3d6790907", "char", null, null, null, 0, "1c451005-49fb-45a5-9cae-d3f9f84d651e", null], ["359551e1-93a2-4dfe-a8e2-ea4df82f1604", "232fb75f443c71abcaa43084f7dd1e0c82c6c94d06c19e15e142013de08f4640", "user", null, null, null, 0, null, null], ["0ff13094-67b2-44a4-bbd3-3c814ab836e8", "fafaff9bbec4433e590cee473992c75ce8fe93c8a599567302f5ce68577081c1", "char", null, null, null, 0, "0ff13094-67b2-44a4-bbd3-3c814ab836e8", null], ["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "73461b6434f614e2eb37e20e380caa8551e035e8f71c62dbf39b73ddc044ed1a", "user", null, null, null, 0, null, null], ["d8a3e666-83b7-4e65-b07e-edccc52094af", "8fa70bd989afccfc9b40f3a9d6896e7f0485b79f7aadbe51a5c6c4fa088039f3", "char", null, null, null, 0, "d8a3e666-83b7-4e65-b07e-edccc52094af", null], ["169bacd1-e364-4493-81d5-3a61fb5ed678", "5a3a022de4f1ead4fcafbb14f9c3281d07e4dabbc9aa061e4bdec489ed6f2fef", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a10c2a-3773-7a89-8e4e-4632517e4a65', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'manifest', '302eb8be4a16929beca1d4576bf95593d971137b130dcc9b5426ce56ffedece3', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37:302eb8be4a16929beca1d4576bf95593d971137b130dcc9b5426ce56ffedece3:manifest', '2026-10-05 13:04:15.728028+00', '{"chat_id": "e4ad1406-ca8e-4235-9ab9-11046334e29d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["264ab270-3102-4325-ae47-1f735d3daeee", "e5056f171e5312a3a3469b57ac472e81625838213506023fae462eee3c55e904", "char", null, null, 1, 2, "264ab270-3102-4325-ae47-1f735d3daeee", null]], "base_manifest_hash": "b781c2891a1df1654d91531646bcf59ee0b94c011cec80c58d916dce2a35a1e6"}');
INSERT INTO public.host_observation VALUES ('01a10c2a-379d-747b-addf-ee90ecf9ffaf', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'manifest', '42fb3278315abe4f7dca0f450ec17cc046c16b8173b52f807964e667673c501c', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37:42fb3278315abe4f7dca0f450ec17cc046c16b8173b52f807964e667673c501c:manifest', '2026-10-05 13:04:15.770156+00', '{"chat_id": "e4ad1406-ca8e-4235-9ab9-11046334e29d", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["61857019-d61e-47bd-ac35-9556a4737c79", "438ba2197046e81a69e66450d6f66855eebdba438d25aa296d117098d223e55e", "user", null, null, null, 0, null, null], ["af7eb463-5221-4b4a-ad6a-a1cde8a107d4", "48bb58cee73429e421964b3d06aaec3aa88b99d0ecfc88a04bfd70e731a8678a", "char", null, null, null, 0, "af7eb463-5221-4b4a-ad6a-a1cde8a107d4", null], ["1af17204-bcb8-4c25-9b4b-bc8c27161ec1", "79b6404077a6b1bf74cc73e0f21fba498bc622cf41f2512fed2b9dcb63a106dc", "user", null, null, null, 0, null, null], ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "9cc84a64d410b19a5f983125ad08a8dd5cefc3aebc26ed55f77dc52c41b8237a", "char", null, null, null, 0, "26fdd18c-bcbb-49cc-baf9-3a84971867ba", null], ["acf00265-39de-4dc1-9ba0-527c1ea57862", "d806b686917b65167e3e6ccc52e2abeb09523b1cf4be3a19460d792a0f93d686", "user", null, null, null, 0, null, null], ["e32a2647-f28d-455f-b30b-157ffacbf186", "80da8646cc274798d103621ddadb5cbe0ac36f03b41ec4942f0b7f46a73ee36a", "char", null, null, null, 0, "e32a2647-f28d-455f-b30b-157ffacbf186", null], ["d59cf364-446e-493b-8031-774d0c6d56dc", "974009aa9786ed9674e495ff5ce69125f8e08381f7a7413284198cdba68ad561", "user", null, null, null, 0, null, null], ["bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "6f2ffc9e558dbf753ac836460e17c25741bdf6e71dd5a09ebb05603fe6d70b8b", "char", null, null, null, 0, "bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", null], ["c3f58464-fec1-480e-8564-ed37d52e5144", "084421254a179d1e822a1a1dea27d10b8d5e207e09db912c868c57aa333aea4c", "user", true, null, null, 0, null, null], ["1c451005-49fb-45a5-9cae-d3f9f84d651e", "5b641c5de15b30d2b76a71a91316756963d29073b9888cddf14aece3d6790907", "char", null, null, null, 0, "1c451005-49fb-45a5-9cae-d3f9f84d651e", null], ["359551e1-93a2-4dfe-a8e2-ea4df82f1604", "232fb75f443c71abcaa43084f7dd1e0c82c6c94d06c19e15e142013de08f4640", "user", null, null, null, 0, null, null], ["0ff13094-67b2-44a4-bbd3-3c814ab836e8", "fafaff9bbec4433e590cee473992c75ce8fe93c8a599567302f5ce68577081c1", "char", null, null, null, 0, "0ff13094-67b2-44a4-bbd3-3c814ab836e8", null], ["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "73461b6434f614e2eb37e20e380caa8551e035e8f71c62dbf39b73ddc044ed1a", "user", null, null, null, 0, null, null], ["d8a3e666-83b7-4e65-b07e-edccc52094af", "8fa70bd989afccfc9b40f3a9d6896e7f0485b79f7aadbe51a5c6c4fa088039f3", "char", null, null, null, 0, "d8a3e666-83b7-4e65-b07e-edccc52094af", null], ["169bacd1-e364-4493-81d5-3a61fb5ed678", "5a3a022de4f1ead4fcafbb14f9c3281d07e4dabbc9aa061e4bdec489ed6f2fef", "user", null, null, null, 0, null, null], ["264ab270-3102-4325-ae47-1f735d3daeee", "d26ae7ec07a6c4f05d83ec07ecd73b9120e66d60035f21450710eab684af84c3", "char", null, null, 0, 2, "264ab270-3102-4325-ae47-1f735d3daeee", null], ["e6740111-1013-4e0c-82b3-6c083eae658a", "e83b1c02b28e8f73d25b229638a1bf037a34fe21dc0cfd22d950340d5cfe1cac", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a10c2a-3bbc-75a0-b9df-233a7dbbfe14', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', 'manifest', 'b32ce5dd7f1e90a18ccea031a5a666446c91147279327ecb2b83835078d43e34', '01a10c2a-3baf-754d-9ed5-e079f7126b6c:b32ce5dd7f1e90a18ccea031a5a666446c91147279327ecb2b83835078d43e34:manifest', '2026-10-05 13:04:16.819874+00', '{"chat_id": "c8a5360e-835a-4410-9218-6e74646a0bca", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["874ab783-6047-40e0-ba2f-4b76129feac8", "7718160ef0941c43559324bd57ce40e40cd5e1375b0758c1c5a233a5753ef391", "user", null, null, null, 0, null, null], ["afb3dd85-970c-4279-8e3e-cdb319be40d4", "0121a9db3edf2a5085a429342db1c6348f8c06993c645660198e49d02640f276", "char", null, null, null, 0, "af7eb463-5221-4b4a-ad6a-a1cde8a107d4", null], ["2699928b-c953-4aea-b6bf-ad122f8b7f98", "bd8a42710193b7137de066369e4d7486e1b271a54412668d07d9a15ddb50b3ab", "user", null, null, null, 0, null, null], ["ac80afc6-61b4-4f29-b6e4-17dccec3aef9", "62dabee37b116eb38bc1e091e94486b07018662f231e3377f5879c1dacae6ac1", "char", null, null, null, 0, "26fdd18c-bcbb-49cc-baf9-3a84971867ba", null], ["c93d0dac-762d-4b7c-a684-1420957a41e7", "10df552da058df989fd11b0943e65d01c9314e88b52f1811f078d61ef2824ec9", "user", null, null, null, 0, null, null], ["87104492-ff3a-4c9d-88a7-f4d61e51482a", "d577d3925ec259b36e72f1914dc0e395fc08e3ce595dd0cabfc08e5d0e0b57bc", "char", null, null, null, 0, "e32a2647-f28d-455f-b30b-157ffacbf186", null], ["2fdb1ba6-ff9e-4a99-b3f9-175e2e840939", "a0b8809a72526e3ca885a778c47105b4976fde9b28fbe8ed3f0b2fdee77ffa83", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::e4ad1406-ca8e-4235-9ab9-11046334e29d::Harbor route::e32a2647-f28d-455f-b30b-157ffacbf186::}}"]], ["e44d3442-f931-4ece-b826-d6f7683cad2a", "5a2db35f13ee84f9d4733945ccd2ea4c7788895dd700b40df9bd9bb4ebd7fa7d", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a10c2a-2f41-70ed-983a-0da2c090f1fd:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2f41-70ed-983a-0da2c090f1fd"}', 50, 'done', 1, '2026-10-05 13:04:13.632368+00', NULL, NULL, '2026-10-05 13:04:13.632368+00', '2026-10-05 13:04:14.965601+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a10c2a-2f18-7048-b375-c57832174f13:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2f18-7048-b375-c57832174f13"}', 50, 'done', 1, '2026-10-05 13:04:13.632368+00', NULL, NULL, '2026-10-05 13:04:13.632368+00', '2026-10-05 13:04:14.986748+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a10c2a-2f17-7795-8d4f-614ced4f918b:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2f17-7795-8d4f-614ced4f918b"}', 50, 'done', 1, '2026-10-05 13:04:13.588909+00', NULL, NULL, '2026-10-05 13:04:13.588909+00', '2026-10-05 13:04:15.012136+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a10c2a-2f16-75a4-a7c8-29986adde78e:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2f16-75a4-a7c8-29986adde78e"}', 50, 'done', 1, '2026-10-05 13:04:13.588909+00', NULL, NULL, '2026-10-05 13:04:13.588909+00', '2026-10-05 13:04:15.036483+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a10c2a-2f15-77a5-981c-4062f17a9c7b:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2f15-77a5-981c-4062f17a9c7b"}', 50, 'done', 1, '2026-10-05 13:04:13.588909+00', NULL, NULL, '2026-10-05 13:04:13.588909+00', '2026-10-05 13:04:15.058947+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd"}', 50, 'done', 1, '2026-10-05 13:04:13.588909+00', NULL, NULL, '2026-10-05 13:04:13.588909+00', '2026-10-05 13:04:15.079102+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b"}', 50, 'done', 1, '2026-10-05 13:04:13.542253+00', NULL, NULL, '2026-10-05 13:04:13.542253+00', '2026-10-05 13:04:15.098794+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a10c2a-2ee8-7522-82cc-b878074ee8e7:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2ee8-7522-82cc-b878074ee8e7"}', 50, 'done', 1, '2026-10-05 13:04:13.542253+00', NULL, NULL, '2026-10-05 13:04:13.542253+00', '2026-10-05 13:04:15.119665+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a10c2a-2ee7-7a18-9d0c-a8c6e443ca39:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2ee7-7a18-9d0c-a8c6e443ca39"}', 50, 'done', 1, '2026-10-05 13:04:13.542253+00', NULL, NULL, '2026-10-05 13:04:13.542253+00', '2026-10-05 13:04:15.150152+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a10c2a-2e91-787f-a259-39ebc6f2dda2:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2e91-787f-a259-39ebc6f2dda2"}', 50, 'done', 1, '2026-10-05 13:04:13.542253+00', NULL, NULL, '2026-10-05 13:04:13.542253+00', '2026-10-05 13:04:15.177403+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a10c2a-2f18-7048-b375-c57832174f13:ac3f9dfb3fb7bd53b49dbaf5dc7d23bb:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2f18-7048-b375-c57832174f13", "window_hash": "ac3f9dfb3fb7bd53b49dbaf5dc7d23bb"}', 100, 'done', 1, '2026-10-05 13:04:13.632368+00', NULL, NULL, '2026-10-05 13:04:13.632368+00', '2026-10-05 13:04:15.208035+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a10c2a-2f16-75a4-a7c8-29986adde78e:d1e97e54504867c317e36e7d45f85772:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2f16-75a4-a7c8-29986adde78e", "window_hash": "d1e97e54504867c317e36e7d45f85772"}', 100, 'done', 1, '2026-10-05 13:04:13.588909+00', NULL, NULL, '2026-10-05 13:04:13.588909+00', '2026-10-05 13:04:15.233759+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd:5f696992a760818427af506c58bf38c4:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd", "window_hash": "5f696992a760818427af506c58bf38c4"}', 100, 'done', 1, '2026-10-05 13:04:13.588909+00', NULL, NULL, '2026-10-05 13:04:13.588909+00', '2026-10-05 13:04:15.262177+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a10c2a-2ee8-7522-82cc-b878074ee8e7:40b23daf24dcb4010577e562053849f8:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2ee8-7522-82cc-b878074ee8e7", "window_hash": "40b23daf24dcb4010577e562053849f8"}', 100, 'done', 1, '2026-10-05 13:04:13.542253+00', NULL, NULL, '2026-10-05 13:04:13.542253+00', '2026-10-05 13:04:15.28787+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a10c2a-2e91-787f-a259-39ebc6f2dda2:bd3804671b3de628a8a87aa03144bf3f:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2e91-787f-a259-39ebc6f2dda2", "window_hash": "bd3804671b3de628a8a87aa03144bf3f"}', 100, 'done', 1, '2026-10-05 13:04:13.542253+00', NULL, NULL, '2026-10-05 13:04:13.542253+00', '2026-10-05 13:04:15.31358+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a10c2a-2e90-7f4b-bab3-dcfb462e399a:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2e90-7f4b-bab3-dcfb462e399a"}', 150, 'done', 1, '2026-10-05 13:04:13.452146+00', NULL, NULL, '2026-10-05 13:04:13.452146+00', '2026-10-05 13:04:15.334779+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a10c2a-2e8f-7e14-86a6-f16a407f8b3b:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2e8f-7e14-86a6-f16a407f8b3b"}', 150, 'done', 1, '2026-10-05 13:04:13.452146+00', NULL, NULL, '2026-10-05 13:04:13.452146+00', '2026-10-05 13:04:15.35733+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a10c2a-2e8d-7a94-9b28-f1f2ac28a315:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-2e8d-7a94-9b28-f1f2ac28a315"}', 150, 'done', 1, '2026-10-05 13:04:13.452146+00', NULL, NULL, '2026-10-05 13:04:13.452146+00', '2026-10-05 13:04:15.378467+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a10c2a-2e8f-7e14-86a6-f16a407f8b3b:fece23e4cc335634193bc7945e032b0e:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2e8f-7e14-86a6-f16a407f8b3b", "window_hash": "fece23e4cc335634193bc7945e032b0e"}', 200, 'done', 1, '2026-10-05 13:04:13.452146+00', NULL, NULL, '2026-10-05 13:04:13.452146+00', '2026-10-05 13:04:15.403592+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a10c2a-2ee8-7522-82cc-b878074ee8e7:0139caf3ed29db317db5ba99c2b89936:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2ee8-7522-82cc-b878074ee8e7", "window_hash": "0139caf3ed29db317db5ba99c2b89936"}', 100, 'done', 1, '2026-10-05 13:04:15.685127+00', NULL, NULL, '2026-10-05 13:04:15.685127+00', '2026-10-05 13:04:16.647618+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a10c2a-3745-79fa-b483-b4d6e5e00d41:55f6f54053d1301a814a2ca19a028160:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-3745-79fa-b483-b4d6e5e00d41", "window_hash": "55f6f54053d1301a814a2ca19a028160"}', 100, 'done', 1, '2026-10-05 13:04:15.685127+00', NULL, NULL, '2026-10-05 13:04:15.685127+00', '2026-10-05 13:04:16.671882+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a10c2a-3bb8-72cb-9e72-b70a57729101:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3bb8-72cb-9e72-b70a57729101"}', 150, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.731716+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a10c2a-379c-7ae9-868c-fec057e3d4e1:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-379c-7ae9-868c-fec057e3d4e1"}', 50, 'done', 1, '2026-10-05 13:04:15.770156+00', NULL, NULL, '2026-10-05 13:04:15.770156+00', '2026-10-05 13:04:16.424023+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a10c2a-379b-7acb-b2ea-36f7af3d5931:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-379b-7acb-b2ea-36f7af3d5931"}', 50, 'done', 1, '2026-10-05 13:04:15.770156+00', NULL, NULL, '2026-10-05 13:04:15.770156+00', '2026-10-05 13:04:16.444796+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a10c2a-3747-7a0f-ab47-7723b7cae834:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3747-7a0f-ab47-7723b7cae834"}', 50, 'done', 1, '2026-10-05 13:04:15.685127+00', NULL, NULL, '2026-10-05 13:04:15.685127+00', '2026-10-05 13:04:16.469148+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a10c2a-3746-7b46-bf67-c12b9d867d9e:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3746-7b46-bf67-c12b9d867d9e"}', 50, 'done', 1, '2026-10-05 13:04:15.685127+00', NULL, NULL, '2026-10-05 13:04:15.685127+00', '2026-10-05 13:04:16.489033+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a10c2a-3745-79fa-b483-b4d6e5e00d41:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3745-79fa-b483-b4d6e5e00d41"}', 50, 'done', 1, '2026-10-05 13:04:15.685127+00', NULL, NULL, '2026-10-05 13:04:15.685127+00', '2026-10-05 13:04:16.508738+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a10c2a-379b-7acb-b2ea-36f7af3d5931:bf196a49fa68f0007ddc97a668d6eab0:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-379b-7acb-b2ea-36f7af3d5931", "window_hash": "bf196a49fa68f0007ddc97a668d6eab0"}', 100, 'done', 1, '2026-10-05 13:04:15.770156+00', NULL, NULL, '2026-10-05 13:04:15.770156+00', '2026-10-05 13:04:16.533561+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a10c2a-3746-7b46-bf67-c12b9d867d9e:c38dbbd747af0c4fe99ad0f7f67020a7:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-3746-7b46-bf67-c12b9d867d9e", "window_hash": "c38dbbd747af0c4fe99ad0f7f67020a7"}', 100, 'done', 1, '2026-10-05 13:04:15.770156+00', NULL, NULL, '2026-10-05 13:04:15.770156+00', '2026-10-05 13:04:16.557057+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a10c2a-2f18-7048-b375-c57832174f13:b9e47c9e7e667a0515a133531ea68b2c:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2f18-7048-b375-c57832174f13", "window_hash": "b9e47c9e7e667a0515a133531ea68b2c"}', 100, 'done', 1, '2026-10-05 13:04:15.770156+00', NULL, NULL, '2026-10-05 13:04:15.770156+00', '2026-10-05 13:04:16.584376+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a10c2a-2f16-75a4-a7c8-29986adde78e:8ed7cb63861d8100d1a148846279d9cf:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2f16-75a4-a7c8-29986adde78e", "window_hash": "8ed7cb63861d8100d1a148846279d9cf"}', 100, 'done', 1, '2026-10-05 13:04:15.770156+00', NULL, NULL, '2026-10-05 13:04:15.770156+00', '2026-10-05 13:04:16.610004+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a10c2a-3746-7b46-bf67-c12b9d867d9e:a8a22597855993c9a974aa3128496621:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-3746-7b46-bf67-c12b9d867d9e", "window_hash": "a8a22597855993c9a974aa3128496621"}', 100, 'obsolete', 1, '2026-10-05 13:04:15.685127+00', NULL, NULL, '2026-10-05 13:04:15.685127+00', '2026-10-05 13:04:16.613431+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a10c2a-2f16-75a4-a7c8-29986adde78e:f64cb69573cd9ff558077e834271fa2e:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2f16-75a4-a7c8-29986adde78e", "window_hash": "f64cb69573cd9ff558077e834271fa2e"}', 100, 'obsolete', 1, '2026-10-05 13:04:15.685127+00', NULL, NULL, '2026-10-05 13:04:15.685127+00', '2026-10-05 13:04:16.616644+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd:39e2c2990df788c686e195c19c8b6b4b:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd", "window_hash": "39e2c2990df788c686e195c19c8b6b4b"}', 100, 'obsolete', 1, '2026-10-05 13:04:15.685127+00', NULL, NULL, '2026-10-05 13:04:15.685127+00', '2026-10-05 13:04:16.619845+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a10c2a-3bb9-7711-9bf2-0290167ee6c9:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3bb9-7711-9bf2-0290167ee6c9"}', 150, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.711248+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a10c2a-3bb7-7c10-80b0-5340677a4815:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3bb7-7c10-80b0-5340677a4815"}', 150, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.753118+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4"}', 150, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.772719+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a10c2a-3bb5-7404-a721-7dc43e88b2ac:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3bb5-7404-a721-7dc43e88b2ac"}', 150, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.792539+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a10c2a-3bb4-7391-a2a2-b04dd06053f0:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3bb4-7391-a2a2-b04dd06053f0"}', 150, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.812727+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a10c2a-3bb9-7711-9bf2-0290167ee6c9:f9b2bb8efbeba9b95180766a67980a10:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-3bb9-7711-9bf2-0290167ee6c9", "window_hash": "f9b2bb8efbeba9b95180766a67980a10"}', 200, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.836846+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a10c2a-3bb7-7c10-80b0-5340677a4815:14d1ba3d3b58b090344bb4958ea038d0:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-3bb7-7c10-80b0-5340677a4815", "window_hash": "14d1ba3d3b58b090344bb4958ea038d0"}', 200, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.863736+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a10c2a-3bb5-7404-a721-7dc43e88b2ac:309969c1d3c1a6d2c39636ab91a4b0d2:extract-5235d13a80ba3a7498b825a56d1758c0', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "extract-5235d13a80ba3a7498b825a56d1758c0", "revision_id": "01a10c2a-3bb5-7404-a721-7dc43e88b2ac", "window_hash": "309969c1d3c1a6d2c39636ab91a4b0d2"}', 200, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.887664+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a10c2a-3bbb-7052-bdf8-0970fe3b068d:embed-84967123495eaeab3e25f668c1fa87c9', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{"generation": "embed-84967123495eaeab3e25f668c1fa87c9", "revision_id": "01a10c2a-3bbb-7052-bdf8-0970fe3b068d"}', 150, 'done', 1, '2026-10-05 13:04:16.819874+00', NULL, NULL, '2026-10-05 13:04:16.819874+00', '2026-10-05 13:04:17.692327+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a10c2a-2e92-7bee-819d-977b2399067c', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37');


--
-- Data for Name: owner_repair; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-5235d13a80ba3a7498b825a56d1758c0', 'extract', 'stub', 'http://127.0.0.1:42561/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "a0de52e41b72df2c", "compiler": "extract-v13", "endpoint": "http://127.0.0.1:42561/v1", "json_mode": true, "normalizer": "clean-v3", "predicates": "a6511d2d7b4e2fca", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-10-05 13:04:13.211675+00', '2026-10-05 13:04:13.212898+00');
INSERT INTO public.projection_generation VALUES ('embed-84967123495eaeab3e25f668c1fa87c9', 'embed', 'stub-embed', 'http://127.0.0.1:42561/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:42561/v1", "max_chunks": 8, "normalizer": "clean-v3", "chunk_chars": 700, "document_profile": "plain"}', '2026-10-05 13:04:13.211675+00', '2026-10-05 13:04:13.217225+00');
INSERT INTO public.projection_generation VALUES ('summarize-c10e0eef26640ac150f0535816a7786e', 'summarize', 'stub', 'http://127.0.0.1:42561/v1', '{"lag": 4, "kind": "summarize", "model": "stub", "prompt": "1cb5649d13d81671", "window": 8, "version": "summarize-v3", "endpoint": "http://127.0.0.1:42561/v1", "json_mode": true, "normalizer": "clean-v3", "temperature": 0, "message_chars": 6000}', '2026-10-05 13:04:13.211675+00', '2026-10-05 13:04:13.21989+00');
INSERT INTO public.projection_generation VALUES ('canon-1f41acb557fc3edb85431af50be6a68c', 'canon', 'stub', 'http://127.0.0.1:42561/v1', '{"kind": "canon", "model": "stub", "prompt": "c084747d55328ce7", "version": "canon-v1", "endpoint": "http://127.0.0.1:42561/v1", "json_mode": true, "max_parts": 4, "normalizer": "clean-v3", "part_chars": 6000, "predicates": "920807f41b347b88", "temperature": 0}', '2026-10-05 13:04:13.211675+00', '2026-10-05 13:04:13.221383+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a10c2a-2edb-7547-a037-6f92b709e4e4', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '01a10c2a-2e94-7a97-b4e1-f4f20188a701', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a10c2a-2e90-7f4b-bab3-dcfb462e399a", "host_logical_id": "1af17204-bcb8-4c25-9b4b-bc8c27161ec1"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a10c2a-2e90-7f4b-bab3-dcfb462e399a", "host_logical_id": "1af17204-bcb8-4c25-9b4b-bc8c27161ec1"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 51.28, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 2.31, "fits_at": null, "lexical": 3.66, "threads": 0, "extractor": "extract-5235d13a80ba", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 63.62, "embedding_projection": "embed-84967123495eae", "memory_mode_withheld": 0}', 'fresh', '2026-10-05 13:04:13.467484+00', 'packet-v8', 600, 3, '', '["1af17204-bcb8-4c25-9b4b-bc8c27161ec1", "26fdd18c-bcbb-49cc-baf9-3a84971867ba", "61857019-d61e-47bd-ac35-9556a4737c79", "af7eb463-5221-4b4a-ad6a-a1cde8a107d4"]', 'extract-5235d13a80ba3a7498b825a56d1758c0', 'embed-84967123495eaeab3e25f668c1fa87c9', 'none', '{"top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-1f41acb557fc3edb85431af50be6a68c", "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-c10e0eef26640ac150f0535816a7786e", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a10c2a-2f0a-7fcf-95bc-72d9d7e77a3d', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '01a10c2a-2e94-7a97-b4e1-f4f20188a701', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b", "host_logical_id": "d59cf364-446e-493b-8031-774d0c6d56dc"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b", "host_logical_id": "d59cf364-446e-493b-8031-774d0c6d56dc"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 14.73, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 0.98, "fits_at": null, "lexical": 2.45, "threads": 0, "extractor": "extract-5235d13a80ba", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 22.11, "embedding_projection": "embed-84967123495eae", "memory_mode_withheld": 0}', 'fresh', '2026-10-05 13:04:13.556459+00', 'packet-v8', 600, 7, '', '["acf00265-39de-4dc1-9ba0-527c1ea57862", "bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "d59cf364-446e-493b-8031-774d0c6d56dc", "e32a2647-f28d-455f-b30b-157ffacbf186"]', 'extract-5235d13a80ba3a7498b825a56d1758c0', 'embed-84967123495eaeab3e25f668c1fa87c9', 'none', '{"top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-1f41acb557fc3edb85431af50be6a68c", "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-c10e0eef26640ac150f0535816a7786e", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a10c2a-2f37-73b3-8df7-9cd1258735dc', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '01a10c2a-2e94-7a97-b4e1-f4f20188a701', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a10c2a-2f17-7795-8d4f-614ced4f918b", "host_logical_id": "359551e1-93a2-4dfe-a8e2-ea4df82f1604"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a10c2a-2f17-7795-8d4f-614ced4f918b", "host_logical_id": "359551e1-93a2-4dfe-a8e2-ea4df82f1604"}]', 0, '{"fit": 0.0, "cast": 0, "embed": 14.62, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 0, "summary": 0}, "vector": 1.0, "fits_at": null, "lexical": 2.19, "threads": 0, "extractor": "extract-5235d13a80ba", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 22.12, "embedding_projection": "embed-84967123495eae", "memory_mode_withheld": 0}', 'fresh', '2026-10-05 13:04:13.601314+00', 'packet-v8', 600, 11, '', '["0ff13094-67b2-44a4-bbd3-3c814ab836e8", "1c451005-49fb-45a5-9cae-d3f9f84d651e", "359551e1-93a2-4dfe-a8e2-ea4df82f1604", "c3f58464-fec1-480e-8564-ed37d52e5144"]', 'extract-5235d13a80ba3a7498b825a56d1758c0', 'embed-84967123495eaeab3e25f668c1fa87c9', 'none', '{"top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-1f41acb557fc3edb85431af50be6a68c", "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-c10e0eef26640ac150f0535816a7786e", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a10c2a-2f5f-71c6-a68a-ccc95809bf37', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '01a10c2a-2e94-7a97-b4e1-f4f20188a701', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a10c2a-2f41-70ed-983a-0da2c090f1fd", "host_logical_id": "0ae43371-a86f-46b9-8ebc-a97b6fe4af32"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a10c2a-2e91-787f-a259-39ebc6f2dda2", "host_logical_id": "26fdd18c-bcbb-49cc-baf9-3a84971867ba"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a10c2a-2e8f-7e14-86a6-f16a407f8b3b", "host_logical_id": "af7eb463-5221-4b4a-ad6a-a1cde8a107d4"}]', '[{"turn": 0, "score": 0.01587, "revision_id": "01a10c2a-2e8f-7e14-86a6-f16a407f8b3b"}, {"turn": 1, "score": 0.01613, "revision_id": "01a10c2a-2e91-787f-a259-39ebc6f2dda2"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a10c2a-2f41-70ed-983a-0da2c090f1fd", "host_logical_id": "0ae43371-a86f-46b9-8ebc-a97b6fe4af32"}]', 174, '{"fit": 0.0, "cast": 0, "embed": 14.85, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2, "summary": 0}, "vector": 1.04, "fits_at": null, "lexical": 2.86, "threads": 0, "extractor": "extract-5235d13a80ba", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 22.81, "embedding_projection": "embed-84967123495eae", "memory_mode_withheld": 0}', 'fresh', '2026-10-05 13:04:13.641019+00', 'packet-v8', 600, 12, '', '["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "0ff13094-67b2-44a4-bbd3-3c814ab836e8", "1c451005-49fb-45a5-9cae-d3f9f84d651e", "359551e1-93a2-4dfe-a8e2-ea4df82f1604"]', 'extract-5235d13a80ba3a7498b825a56d1758c0', 'embed-84967123495eaeab3e25f668c1fa87c9', 'none', '{"top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-1f41acb557fc3edb85431af50be6a68c", "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-c10e0eef26640ac150f0535816a7786e", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a10c2a-2e91-787f-a259-39ebc6f2dda2"}, "tok": 28, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s sister. Rin went to the harbor.", "turn": 1, "placed": true}, {"ref": {"revision": "01a10c2a-2e8f-7e14-86a6-f16a407f8b3b"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 0, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a10c2a-3767-74fc-8920-223b01f4a1f4', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '01a10c2a-374a-79a5-a618-1ced6394132d', 'And the compass?', '[{"rrf": 0.03128, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a10c2a-2f16-75a4-a7c8-29986adde78e", "host_logical_id": "1c451005-49fb-45a5-9cae-d3f9f84d651e"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a10c2a-3747-7a0f-ab47-7723b7cae834", "host_logical_id": "169bacd1-e364-4493-81d5-3a61fb5ed678"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a10c2a-2e8f-7e14-86a6-f16a407f8b3b", "host_logical_id": "af7eb463-5221-4b4a-ad6a-a1cde8a107d4"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a10c2a-2e8d-7a94-9b28-f1f2ac28a315", "host_logical_id": "61857019-d61e-47bd-ac35-9556a4737c79"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd", "host_logical_id": "bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a10c2a-2ee8-7522-82cc-b878074ee8e7", "host_logical_id": "e32a2647-f28d-455f-b30b-157ffacbf186"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a10c2a-2e8d-7a94-9b28-f1f2ac28a315"}, {"turn": 0, "score": 0.01639, "revision_id": "01a10c2a-2e8f-7e14-86a6-f16a407f8b3b"}, {"turn": 2, "score": 0.01562, "revision_id": "01a10c2a-2ee8-7522-82cc-b878074ee8e7"}, {"turn": 3, "score": 0.01587, "revision_id": "01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd"}, {"turn": 4, "score": 0.03128, "revision_id": "01a10c2a-2f16-75a4-a7c8-29986adde78e"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a10c2a-3747-7a0f-ab47-7723b7cae834", "host_logical_id": "169bacd1-e364-4493-81d5-3a61fb5ed678"}]', 326, '{"fit": 0.0, "cast": 2, "embed": 14.01, "facts": 0, "placed": {"fact": 2, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 5, "summary": 0}, "vector": 1.03, "fits_at": null, "lexical": 3.6, "threads": 0, "extractor": "extract-5235d13a80ba", "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 23.0, "embedding_projection": "embed-84967123495eae", "memory_mode_withheld": 0}', 'fresh', '2026-10-05 13:04:15.696113+00', 'packet-v8', 600, 14, '', '["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "0ff13094-67b2-44a4-bbd3-3c814ab836e8", "169bacd1-e364-4493-81d5-3a61fb5ed678", "d8a3e666-83b7-4e65-b07e-edccc52094af"]', 'extract-5235d13a80ba3a7498b825a56d1758c0', 'embed-84967123495eaeab3e25f668c1fa87c9', 'none', '{"top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-1f41acb557fc3edb85431af50be6a68c", "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-c10e0eef26640ac150f0535816a7786e", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 1}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 7}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a10c2a-2f16-75a4-a7c8-29986adde78e"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "placed": true}, {"ref": {"revision": "01a10c2a-2e8f-7e14-86a6-f16a407f8b3b"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Mina is in the old chapel. Mina has the brass key.", "turn": 0, "placed": true}, {"ref": {"revision": "01a10c2a-2e8d-7a94-9b28-f1f2ac28a315"}, "tok": 22, "why": "placed", "kind": "excerpt", "text": "We should rest somewhere safe.", "turn": 0, "placed": true}, {"ref": {"revision": "01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd"}, "tok": 25, "why": "placed", "kind": "excerpt", "text": "Idle reply about lanterns and rain.", "turn": 3, "placed": true}, {"ref": {"revision": "01a10c2a-2ee8-7522-82cc-b878074ee8e7"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Mina promised Takumi to return before the bell rings.", "turn": 2, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a10c2a-3791-7b20-b15c-a42efe83956c', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '01a10c2a-374a-79a5-a618-1ced6394132d', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a10c2a-2f16-75a4-a7c8-29986adde78e", "host_logical_id": "1c451005-49fb-45a5-9cae-d3f9f84d651e"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a10c2a-3747-7a0f-ab47-7723b7cae834", "host_logical_id": "169bacd1-e364-4493-81d5-3a61fb5ed678"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a10c2a-2f18-7048-b375-c57832174f13", "host_logical_id": "0ff13094-67b2-44a4-bbd3-3c814ab836e8"}]', '[{"turn": 4, "score": 0.03002, "revision_id": "01a10c2a-2f16-75a4-a7c8-29986adde78e"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a10c2a-3747-7a0f-ab47-7723b7cae834", "host_logical_id": "169bacd1-e364-4493-81d5-3a61fb5ed678"}]', 222, '{"fit": 0.0, "cast": 2, "embed": 14.62, "facts": 0, "placed": {"fact": 2, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0}, "vector": 1.12, "fits_at": null, "lexical": 4.1, "threads": 0, "extractor": "extract-5235d13a80ba", "kept_facts": 2, "kept_state": 0, "memory_cut": 0, "scene_cast": ["Mina", "{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 24.67, "embedding_projection": "embed-84967123495eae", "memory_mode_withheld": 0}', 'fresh', '2026-10-05 13:04:15.736572+00', 'packet-v8', 600, 15, '', '["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "169bacd1-e364-4493-81d5-3a61fb5ed678", "264ab270-3102-4325-ae47-1f735d3daeee", "d8a3e666-83b7-4e65-b07e-edccc52094af"]', 'extract-5235d13a80ba3a7498b825a56d1758c0', 'embed-84967123495eaeab3e25f668c1fa87c9', 'none', '{"top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-1f41acb557fc3edb85431af50be6a68c", "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-c10e0eef26640ac150f0535816a7786e", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"assertion": 1}, "tok": 55, "why": "placed", "kind": "fact", "text": "Mina located in bell tower", "turn": 5, "placed": true, "content": "bell tower", "section": "cast"}, {"ref": {"assertion": 7}, "tok": 20, "why": "placed", "kind": "fact", "text": "Mina possesses brass key", "turn": 0, "placed": true, "content": "brass key", "section": "cast"}, {"ref": {"revision": "01a10c2a-2f16-75a4-a7c8-29986adde78e"}, "tok": 30, "why": "placed", "kind": "excerpt", "text": "Rin has the silver compass. The gulls are loud today.", "turn": 4, "placed": true}, {"ref": {"revision": "01a10c2a-2f18-7048-b375-c57832174f13"}, "tok": 0, "why": "repeats", "kind": "excerpt", "text": "Mina moved to the bell tower.", "turn": 5, "placed": false, "repeats": {"assertion": 1}}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a10c2a-37b9-7ca1-9d27-045828300c76', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '01a10c2a-379e-7504-96c8-5bd11799666b', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b", "host_logical_id": "d59cf364-446e-493b-8031-774d0c6d56dc"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a10c2a-379c-7ae9-868c-fec057e3d4e1", "host_logical_id": "e6740111-1013-4e0c-82b3-6c083eae658a"}]', '[{"turn": 3, "score": 0.03252, "revision_id": "01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a10c2a-379c-7ae9-868c-fec057e3d4e1", "host_logical_id": "e6740111-1013-4e0c-82b3-6c083eae658a"}]', 138, '{"fit": 0.0, "cast": 0, "embed": 15.36, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 1, "summary": 0}, "vector": 0.89, "fits_at": null, "lexical": 2.15, "threads": 0, "extractor": "extract-5235d13a80ba", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 21.87, "embedding_projection": "embed-84967123495eae", "memory_mode_withheld": 0}', 'fresh', '2026-10-05 13:04:15.779959+00', 'packet-v8', 600, 16, '', '["169bacd1-e364-4493-81d5-3a61fb5ed678", "264ab270-3102-4325-ae47-1f735d3daeee", "d8a3e666-83b7-4e65-b07e-edccc52094af", "e6740111-1013-4e0c-82b3-6c083eae658a"]', 'extract-5235d13a80ba3a7498b825a56d1758c0', 'embed-84967123495eaeab3e25f668c1fa87c9', 'none', '{"top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-1f41acb557fc3edb85431af50be6a68c", "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-c10e0eef26640ac150f0535816a7786e", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b"}, "tok": 20, "why": "placed", "kind": "excerpt", "text": "Let''s check the market.", "turn": 3, "placed": true}]', NULL, '[]');
INSERT INTO public.retrieval_trace VALUES ('01a10c2a-3bdb-7c3e-8e85-fbba59ae31fe', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4", "host_logical_id": "2699928b-c953-4aea-b6bf-ad122f8b7f98"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a10c2a-3bb7-7c10-80b0-5340677a4815", "host_logical_id": "ac80afc6-61b4-4f29-b6e4-17dccec3aef9"}]', '[{"turn": 1, "score": 0.01639, "revision_id": "01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4"}, {"turn": 1, "score": 0.01613, "revision_id": "01a10c2a-3bb7-7c10-80b0-5340677a4815"}]', '[]', 164, '{"fit": 0.0, "cast": 0, "embed": 16.32, "facts": 0, "placed": {"fact": 0, "claim": 0, "state": 0, "secret": 0, "thread": 0, "excerpt": 2, "summary": 0}, "vector": 0.91, "fits_at": null, "lexical": 2.29, "threads": 0, "extractor": "extract-5235d13a80ba", "kept_facts": 0, "kept_state": 0, "memory_cut": 0, "scene_cast": ["{{user}}"], "state_items": 0, "vector_mode": "on", "kept_threads": 0, "lexical_mode": "on", "sidecar_total": 22.78, "embedding_projection": "embed-84967123495eae", "memory_mode_withheld": 0}', 'fresh', '2026-10-05 13:04:16.836307+00', 'packet-v8', 600, 7, '', '["2fdb1ba6-ff9e-4a99-b3f9-175e2e840939", "87104492-ff3a-4c9d-88a7-f4d61e51482a", "c93d0dac-762d-4b7c-a684-1420957a41e7", "e44d3442-f931-4ece-b826-d6f7683cad2a"]', 'extract-5235d13a80ba3a7498b825a56d1758c0', 'embed-84967123495eaeab3e25f668c1fa87c9', 'none', '{"top_k": 5, "strict": false, "narrator": null, "canon_key": "canon-1f41acb557fc3edb85431af50be6a68c", "threshold": 0.4, "canon_facts": null, "canon_names": null, "facts_limit": 8, "events_limit": 3, "query_prefix": "", "summarize_key": "summarize-c10e0eef26640ac150f0535816a7786e", "threads_limit": 3, "vector_min_sim": 0.42, "embed_timeout_ms": 3000, "lexical_timeout_ms": 300}', '[{"ref": {"revision": "01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4"}, "tok": 18, "why": "placed", "kind": "excerpt", "text": "Is Rin with you?", "turn": 1, "placed": true}, {"ref": {"revision": "01a10c2a-3bb7-7c10-80b0-5340677a4815"}, "tok": 29, "why": "placed", "kind": "excerpt", "text": "Rin is Mina''s rival. Rin went to the lighthouse.", "turn": 1, "placed": true}]', NULL, '[]');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a10c2a-2f41-70ed-983a-0da2c090f1fd', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:14.962572+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2f18-7048-b375-c57832174f13', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:14.985214+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2f17-7795-8d4f-614ced4f918b', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.010369+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2f16-75a4-a7c8-29986adde78e', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.034899+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2f15-77a5-981c-4062f17a9c7b', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.057268+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.077573+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.097235+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2ee8-7522-82cc-b878074ee8e7', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.11821+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2ee7-7a18-9d0c-a8c6e443ca39', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.145733+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2e91-787f-a259-39ebc6f2dda2', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.175896+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2e90-7f4b-bab3-dcfb462e399a', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.333252+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2e8f-7e14-86a6-f16a407f8b3b', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.355821+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-2e8d-7a94-9b28-f1f2ac28a315', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:15.377046+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-379c-7ae9-868c-fec057e3d4e1', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:16.42254+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-379b-7acb-b2ea-36f7af3d5931', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:16.443315+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3747-7a0f-ab47-7723b7cae834', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:16.467618+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3746-7b46-bf67-c12b9d867d9e', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:16.487521+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3745-79fa-b483-b4d6e5e00d41', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:16.507278+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3bbb-7052-bdf8-0970fe3b068d', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:17.690772+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3bb9-7711-9bf2-0290167ee6c9', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:17.709739+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3bb8-72cb-9e72-b70a57729101', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:17.730207+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3bb7-7c10-80b0-5340677a4815', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:17.751639+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:17.771201+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3bb5-7404-a721-7dc43e88b2ac', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:17.790963+00');
INSERT INTO public.revision_embedding VALUES ('01a10c2a-3bb4-7391-a2a2-b04dd06053f0', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-84967123495eaeab3e25f668c1fa87c9', '2026-10-05 13:04:17.81107+00');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a10c2a-2e8d-7a94-9b28-f1f2ac28a315', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-10-05 13:04:13.452146+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2e8f-7e14-86a6-f16a407f8b3b', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-10-05 13:04:13.452146+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2e90-7f4b-bab3-dcfb462e399a', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-10-05 13:04:13.452146+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2e91-787f-a259-39ebc6f2dda2', 'clean-v3', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-10-05 13:04:13.452146+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2ee7-7a18-9d0c-a8c6e443ca39', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-10-05 13:04:13.542253+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2ee8-7522-82cc-b878074ee8e7', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-10-05 13:04:13.542253+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b', 'clean-v3', 'Let''s check the market.', 23, 23, '2026-10-05 13:04:13.542253+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd', 'clean-v3', 'Idle reply about lanterns and rain.', 35, 35, '2026-10-05 13:04:13.542253+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2f15-77a5-981c-4062f17a9c7b', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-10-05 13:04:13.588909+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2f16-75a4-a7c8-29986adde78e', 'clean-v3', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-10-05 13:04:13.588909+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2f17-7795-8d4f-614ced4f918b', 'clean-v3', 'Where do we meet tonight?', 25, 25, '2026-10-05 13:04:13.588909+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2f18-7048-b375-c57832174f13', 'clean-v3', 'Mina moved to the bell tower.', 29, 29, '2026-10-05 13:04:13.588909+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-2f41-70ed-983a-0da2c090f1fd', 'clean-v3', 'Where is Mina now?', 18, 18, '2026-10-05 13:04:13.632368+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3745-79fa-b483-b4d6e5e00d41', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-10-05 13:04:15.685127+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3746-7b46-bf67-c12b9d867d9e', 'clean-v3', 'Mina keeps the brass key close.', 31, 31, '2026-10-05 13:04:15.685127+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3747-7a0f-ab47-7723b7cae834', 'clean-v3', 'And the compass?', 16, 16, '2026-10-05 13:04:15.685127+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3770-7b65-a8c9-af809dbe903a', 'clean-v3', 'Rin carries the silver compass and a map.', 41, 41, '2026-10-05 13:04:15.728028+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-379a-7433-a394-5d60dc243155', 'clean-v3', 'Any news from the harbor?', 25, 25, '2026-10-05 13:04:15.770156+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-379b-7acb-b2ea-36f7af3d5931', 'clean-v3', 'Rin has the silver compass.', 27, 27, '2026-10-05 13:04:15.770156+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-379c-7ae9-868c-fec057e3d4e1', 'clean-v3', 'Let''s go.', 9, 9, '2026-10-05 13:04:15.770156+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3bb4-7391-a2a2-b04dd06053f0', 'clean-v3', 'We should rest somewhere safe.', 30, 30, '2026-10-05 13:04:16.819874+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3bb5-7404-a721-7dc43e88b2ac', 'clean-v3', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-10-05 13:04:16.819874+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4', 'clean-v3', 'Is Rin with you?', 16, 16, '2026-10-05 13:04:16.819874+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3bb7-7c10-80b0-5340677a4815', 'clean-v3', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-10-05 13:04:16.819874+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3bb8-72cb-9e72-b70a57729101', 'clean-v3', 'What did Mina say before she left?', 34, 34, '2026-10-05 13:04:16.819874+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3bb9-7711-9bf2-0290167ee6c9', 'clean-v3', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-10-05 13:04:16.819874+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3bba-7aa9-8e42-d003a0c086ca', 'clean-v3', '{{specialcomment::branchedfrom::e4ad1406-ca8e-4235-9ab9-11046334e29d::Harbor route::e32a2647-f28d-455f-b30b-157ffacbf186::}}', 124, 124, '2026-10-05 13:04:16.819874+00');
INSERT INTO public.revision_text VALUES ('01a10c2a-3bbb-7052-bdf8-0970fe3b068d', 'clean-v3', 'Rin moved to the market.', 24, 24, '2026-10-05 13:04:16.819874+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-10-05 13:04:11.828114+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-10-05 13:04:11.906577+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-10-05 13:04:11.922451+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-10-05 13:04:11.963897+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-10-05 13:04:11.984677+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-10-05 13:04:11.993586+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-10-05 13:04:11.995354+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-10-05 13:04:12.00524+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-10-05 13:04:12.022794+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-10-05 13:04:12.02696+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-10-05 13:04:12.028897+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-10-05 13:04:12.037987+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-10-05 13:04:12.063236+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-10-05 13:04:12.083543+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-10-05 13:04:12.086083+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-10-05 13:04:12.098228+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-10-05 13:04:12.099895+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-10-05 13:04:12.101638+00');
INSERT INTO public.schema_migrations VALUES ('0019_entity_link.sql', 'b67091edc7910741211600a83c8eb819dcf5645cd14b29793ae5a06960eddfd0', '2026-10-05 13:04:12.10316+00');
INSERT INTO public.schema_migrations VALUES ('0020_packet_ledger.sql', '16fbe8fdb5813d158c99d065119ba90ca10fa2f8434756ae2db550c2690e8b1b', '2026-10-05 13:04:12.115107+00');
INSERT INTO public.schema_migrations VALUES ('0021_conversation_memory_mode.sql', 'ed67cf9e22eae4fa4f23935a1a43e64e9fa1114bc6f0ef34480441650b3f5235', '2026-10-05 13:04:12.11726+00');
INSERT INTO public.schema_migrations VALUES ('0022_thread_outcome_and_cause.sql', '9a8507f1b42457d2c44d568a2bd60d868f923613f8c83acb2be7f9104041cc88', '2026-10-05 13:04:12.119253+00');
INSERT INTO public.schema_migrations VALUES ('0023_summaries.sql', 'da452cf41917f9cc59c3a9d71e4114bf5179d3c5493669a5c7ce83ea13e0fb77', '2026-10-05 13:04:12.120879+00');
INSERT INTO public.schema_migrations VALUES ('0024_owner_repair.sql', 'de78024aceb993e7822500bb13d17d034b0123cdf67225fc9c8d82e16164e3be', '2026-10-05 13:04:12.133706+00');
INSERT INTO public.schema_migrations VALUES ('0025_canon.sql', '692a149bab93cd46b4bff801fc8ca0d857dc72ae88ca73471b33668cc2e694e3', '2026-10-05 13:04:12.146823+00');
INSERT INTO public.schema_migrations VALUES ('0026_canon_facts.sql', '5998bd556819cc977b9c0dabf9baa53303a5ac0504abb5742f6c3c11f1ec81dd', '2026-10-05 13:04:12.175234+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a10c2a-2e8c-7749-8dee-c3b95c165ee3', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '61857019-d61e-47bd-ac35-9556a4737c79', 'message', '2026-10-05 13:04:13.452146+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2e8f-7717-ab39-353a0d72b7ce', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'af7eb463-5221-4b4a-ad6a-a1cde8a107d4', 'message', '2026-10-05 13:04:13.452146+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2e90-7d08-803c-136609c6d8b5', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '1af17204-bcb8-4c25-9b4b-bc8c27161ec1', 'message', '2026-10-05 13:04:13.452146+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2e90-7609-88ab-92c6c870d394', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '26fdd18c-bcbb-49cc-baf9-3a84971867ba', 'message', '2026-10-05 13:04:13.452146+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2ee7-72d8-bfb4-3bb225de217f', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'acf00265-39de-4dc1-9ba0-527c1ea57862', 'message', '2026-10-05 13:04:13.542253+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2ee8-7619-9fb4-3aa5608db8e8', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'e32a2647-f28d-455f-b30b-157ffacbf186', 'message', '2026-10-05 13:04:13.542253+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2ee9-71fe-abfd-74120b48a5be', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'd59cf364-446e-493b-8031-774d0c6d56dc', 'message', '2026-10-05 13:04:13.542253+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2ee9-7416-b418-12dc59c723d3', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1', 'message', '2026-10-05 13:04:13.542253+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2f15-7840-84f1-a2a0e9ca06e8', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'c3f58464-fec1-480e-8564-ed37d52e5144', 'message', '2026-10-05 13:04:13.588909+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2f16-77ee-a892-11c3babf0406', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '1c451005-49fb-45a5-9cae-d3f9f84d651e', 'message', '2026-10-05 13:04:13.588909+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2f17-76a7-b0de-cd4bb304c076', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '359551e1-93a2-4dfe-a8e2-ea4df82f1604', 'message', '2026-10-05 13:04:13.588909+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2f17-7e06-8822-fc0206f5daf4', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '0ff13094-67b2-44a4-bbd3-3c814ab836e8', 'message', '2026-10-05 13:04:13.588909+00');
INSERT INTO public.source_object VALUES ('01a10c2a-2f40-75d4-9ae4-c6a1f9fb5f27', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '0ae43371-a86f-46b9-8ebc-a97b6fe4af32', 'message', '2026-10-05 13:04:13.632368+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3746-7c75-80dc-5be565cbaf3a', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'd8a3e666-83b7-4e65-b07e-edccc52094af', 'message', '2026-10-05 13:04:15.685127+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3747-7d8c-8f33-62284f1aae7d', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '169bacd1-e364-4493-81d5-3a61fb5ed678', 'message', '2026-10-05 13:04:15.685127+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3770-7932-9d57-d7981ccc6a98', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '264ab270-3102-4325-ae47-1f735d3daeee', 'message', '2026-10-05 13:04:15.728028+00');
INSERT INTO public.source_object VALUES ('01a10c2a-379b-7e85-9007-bab22e2463c1', '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', 'e6740111-1013-4e0c-82b3-6c083eae658a', 'message', '2026-10-05 13:04:15.770156+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3bb4-77ed-82d1-48e26ee63f41', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '874ab783-6047-40e0-ba2f-4b76129feac8', 'message', '2026-10-05 13:04:16.819874+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3bb5-79f8-9b0e-2088a780a6c4', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', 'afb3dd85-970c-4279-8e3e-cdb319be40d4', 'message', '2026-10-05 13:04:16.819874+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3bb5-799f-9bd2-a3793ece1e5f', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '2699928b-c953-4aea-b6bf-ad122f8b7f98', 'message', '2026-10-05 13:04:16.819874+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3bb7-74aa-be69-aa85a07ada88', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', 'ac80afc6-61b4-4f29-b6e4-17dccec3aef9', 'message', '2026-10-05 13:04:16.819874+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3bb8-705c-807f-d8d6c046207c', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', 'c93d0dac-762d-4b7c-a684-1420957a41e7', 'message', '2026-10-05 13:04:16.819874+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3bb9-7286-9798-7ecc63ce05e3', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '87104492-ff3a-4c9d-88a7-f4d61e51482a', 'message', '2026-10-05 13:04:16.819874+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3bba-7841-ab24-fad9e92301d5', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '2fdb1ba6-ff9e-4a99-b3f9-175e2e840939', 'message', '2026-10-05 13:04:16.819874+00');
INSERT INTO public.source_object VALUES ('01a10c2a-3bbb-7fc4-92ca-66ecd9301ebb', '01a10c2a-3baf-754d-9ed5-e079f7126b6c', 'e44d3442-f931-4ece-b826-d6f7683cad2a', 'message', '2026-10-05 13:04:16.819874+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a10c2a-2e8d-7a94-9b28-f1f2ac28a315', '01a10c2a-2e8c-7749-8dee-c3b95c165ee3', '438ba2197046e81a69e66450d6f66855eebdba438d25aa296d117098d223e55e', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "61857019-d61e-47bd-ac35-9556a4737c79", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:13.452146+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2e90-7f4b-bab3-dcfb462e399a', '01a10c2a-2e90-7d08-803c-136609c6d8b5', '79b6404077a6b1bf74cc73e0f21fba498bc622cf41f2512fed2b9dcb63a106dc', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "1af17204-bcb8-4c25-9b4b-bc8c27161ec1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:13.452146+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2e8f-7e14-86a6-f16a407f8b3b', '01a10c2a-2e8f-7717-ab39-353a0d72b7ce', '48bb58cee73429e421964b3d06aaec3aa88b99d0ecfc88a04bfd70e731a8678a', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "af7eb463-5221-4b4a-ad6a-a1cde8a107d4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "af7eb463-5221-4b4a-ad6a-a1cde8a107d4", "specialComments": []}', '2026-10-05 13:04:13.452146+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2ee7-7a18-9d0c-a8c6e443ca39', '01a10c2a-2ee7-72d8-bfb4-3bb225de217f', 'd806b686917b65167e3e6ccc52e2abeb09523b1cf4be3a19460d792a0f93d686', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "acf00265-39de-4dc1-9ba0-527c1ea57862", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:13.542253+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2ee9-704c-b0f3-3cf9d4c51e1b', '01a10c2a-2ee9-71fe-abfd-74120b48a5be', '974009aa9786ed9674e495ff5ce69125f8e08381f7a7413284198cdba68ad561', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "d59cf364-446e-493b-8031-774d0c6d56dc", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:13.542253+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2f15-77a5-981c-4062f17a9c7b', '01a10c2a-2f15-7840-84f1-a2a0e9ca06e8', '844b5aa66a759804aab8b9417f83d8516fe8dad7a285826e46e3859b9d8a490c', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "c3f58464-fec1-480e-8564-ed37d52e5144", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:13.588909+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2ee8-7522-82cc-b878074ee8e7', '01a10c2a-2ee8-7619-9fb4-3aa5608db8e8', '80da8646cc274798d103621ddadb5cbe0ac36f03b41ec4942f0b7f46a73ee36a', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "e32a2647-f28d-455f-b30b-157ffacbf186", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e32a2647-f28d-455f-b30b-157ffacbf186", "specialComments": []}', '2026-10-05 13:04:13.542253+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2f17-7795-8d4f-614ced4f918b', '01a10c2a-2f17-76a7-b0de-cd4bb304c076', '232fb75f443c71abcaa43084f7dd1e0c82c6c94d06c19e15e142013de08f4640', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "359551e1-93a2-4dfe-a8e2-ea4df82f1604", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:13.588909+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2f16-75a4-a7c8-29986adde78e', '01a10c2a-2f16-77ee-a892-11c3babf0406', '5b641c5de15b30d2b76a71a91316756963d29073b9888cddf14aece3d6790907', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "1c451005-49fb-45a5-9cae-d3f9f84d651e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "1c451005-49fb-45a5-9cae-d3f9f84d651e", "specialComments": []}', '2026-10-05 13:04:13.588909+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2ee9-7b1d-bfe6-a215b73a1dcd', '01a10c2a-2ee9-7416-b418-12dc59c723d3', '6f2ffc9e558dbf753ac836460e17c25741bdf6e71dd5a09ebb05603fe6d70b8b', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "specialComments": []}', '2026-10-05 13:04:13.542253+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2f41-70ed-983a-0da2c090f1fd', '01a10c2a-2f40-75d4-9ae4-c6a1f9fb5f27', '73461b6434f614e2eb37e20e380caa8551e035e8f71c62dbf39b73ddc044ed1a', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:13.632368+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2f18-7048-b375-c57832174f13', '01a10c2a-2f17-7e06-8822-fc0206f5daf4', 'fafaff9bbec4433e590cee473992c75ce8fe93c8a599567302f5ce68577081c1', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "0ff13094-67b2-44a4-bbd3-3c814ab836e8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "0ff13094-67b2-44a4-bbd3-3c814ab836e8", "specialComments": []}', '2026-10-05 13:04:13.588909+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3747-7a0f-ab47-7723b7cae834', '01a10c2a-3747-7d8c-8f33-62284f1aae7d', '5a3a022de4f1ead4fcafbb14f9c3281d07e4dabbc9aa061e4bdec489ed6f2fef', 'And the compass?', '{"name": null, "role": "user", "chatId": "169bacd1-e364-4493-81d5-3a61fb5ed678", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:15.685127+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3745-79fa-b483-b4d6e5e00d41', '01a10c2a-2e90-7609-88ab-92c6c870d394', '9cc84a64d410b19a5f983125ad08a8dd5cefc3aebc26ed55f77dc52c41b8237a', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "26fdd18c-bcbb-49cc-baf9-3a84971867ba", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "26fdd18c-bcbb-49cc-baf9-3a84971867ba", "specialComments": []}', '2026-10-05 13:04:15.685127+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-2e91-787f-a259-39ebc6f2dda2', '01a10c2a-2e90-7609-88ab-92c6c870d394', 'de7d1eb4801be2759af17d49d5387d57bc4a8116c7886c385da8b5e0648b3b48', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "26fdd18c-bcbb-49cc-baf9-3a84971867ba", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "26fdd18c-bcbb-49cc-baf9-3a84971867ba", "specialComments": []}', '2026-10-05 13:04:13.452146+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3746-7b46-bf67-c12b9d867d9e', '01a10c2a-3746-7c75-80dc-5be565cbaf3a', '8fa70bd989afccfc9b40f3a9d6896e7f0485b79f7aadbe51a5c6c4fa088039f3', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "d8a3e666-83b7-4e65-b07e-edccc52094af", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "d8a3e666-83b7-4e65-b07e-edccc52094af", "specialComments": []}', '2026-10-05 13:04:15.685127+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-379a-7433-a394-5d60dc243155', '01a10c2a-2f15-7840-84f1-a2a0e9ca06e8', '084421254a179d1e822a1a1dea27d10b8d5e207e09db912c868c57aa333aea4c', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "c3f58464-fec1-480e-8564-ed37d52e5144", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:15.770156+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-379c-7ae9-868c-fec057e3d4e1', '01a10c2a-379b-7e85-9007-bab22e2463c1', 'e83b1c02b28e8f73d25b229638a1bf037a34fe21dc0cfd22d950340d5cfe1cac', 'Let''s go.', '{"name": null, "role": "user", "chatId": "e6740111-1013-4e0c-82b3-6c083eae658a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:15.770156+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-379b-7acb-b2ea-36f7af3d5931', '01a10c2a-3770-7932-9d57-d7981ccc6a98', 'd26ae7ec07a6c4f05d83ec07ecd73b9120e66d60035f21450710eab684af84c3', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "264ab270-3102-4325-ae47-1f735d3daeee", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "264ab270-3102-4325-ae47-1f735d3daeee", "specialComments": []}', '2026-10-05 13:04:15.770156+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3770-7b65-a8c9-af809dbe903a', '01a10c2a-3770-7932-9d57-d7981ccc6a98', 'e5056f171e5312a3a3469b57ac472e81625838213506023fae462eee3c55e904', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "264ab270-3102-4325-ae47-1f735d3daeee", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "264ab270-3102-4325-ae47-1f735d3daeee", "specialComments": []}', '2026-10-05 13:04:15.728028+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3bb4-7391-a2a2-b04dd06053f0', '01a10c2a-3bb4-77ed-82d1-48e26ee63f41', '7718160ef0941c43559324bd57ce40e40cd5e1375b0758c1c5a233a5753ef391', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "874ab783-6047-40e0-ba2f-4b76129feac8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:16.819874+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3bb6-797a-bf6d-ccb52b85c5c4', '01a10c2a-3bb5-799f-9bd2-a3793ece1e5f', 'bd8a42710193b7137de066369e4d7486e1b271a54412668d07d9a15ddb50b3ab', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "2699928b-c953-4aea-b6bf-ad122f8b7f98", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:16.819874+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3bb8-72cb-9e72-b70a57729101', '01a10c2a-3bb8-705c-807f-d8d6c046207c', '10df552da058df989fd11b0943e65d01c9314e88b52f1811f078d61ef2824ec9', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "c93d0dac-762d-4b7c-a684-1420957a41e7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:16.819874+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3bba-7aa9-8e42-d003a0c086ca', '01a10c2a-3bba-7841-ab24-fad9e92301d5', 'a0b8809a72526e3ca885a778c47105b4976fde9b28fbe8ed3f0b2fdee77ffa83', '{{specialcomment::branchedfrom::e4ad1406-ca8e-4235-9ab9-11046334e29d::Harbor route::e32a2647-f28d-455f-b30b-157ffacbf186::}}', '{"name": null, "role": "char", "chatId": "2fdb1ba6-ff9e-4a99-b3f9-175e2e840939", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::e4ad1406-ca8e-4235-9ab9-11046334e29d::Harbor route::e32a2647-f28d-455f-b30b-157ffacbf186::}}"]}', '2026-10-05 13:04:16.819874+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3bbb-7052-bdf8-0970fe3b068d', '01a10c2a-3bbb-7fc4-92ca-66ecd9301ebb', '5a2db35f13ee84f9d4733945ccd2ea4c7788895dd700b40df9bd9bb4ebd7fa7d', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "e44d3442-f931-4ece-b826-d6f7683cad2a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-10-05 13:04:16.819874+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3bb9-7711-9bf2-0290167ee6c9', '01a10c2a-3bb9-7286-9798-7ecc63ce05e3', 'd577d3925ec259b36e72f1914dc0e395fc08e3ce595dd0cabfc08e5d0e0b57bc', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "87104492-ff3a-4c9d-88a7-f4d61e51482a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "e32a2647-f28d-455f-b30b-157ffacbf186", "specialComments": []}', '2026-10-05 13:04:16.819874+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3bb7-7c10-80b0-5340677a4815', '01a10c2a-3bb7-74aa-be69-aa85a07ada88', '62dabee37b116eb38bc1e091e94486b07018662f231e3377f5879c1dacae6ac1', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "ac80afc6-61b4-4f29-b6e4-17dccec3aef9", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "26fdd18c-bcbb-49cc-baf9-3a84971867ba", "specialComments": []}', '2026-10-05 13:04:16.819874+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a10c2a-3bb5-7404-a721-7dc43e88b2ac', '01a10c2a-3bb5-79f8-9b0e-2088a780a6c4', '0121a9db3edf2a5085a429342db1c6348f8c06993c645660198e49d02640f276', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "afb3dd85-970c-4279-8e3e-cdb319be40d4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "af7eb463-5221-4b4a-ad6a-a1cde8a107d4", "specialComments": []}', '2026-10-05 13:04:16.819874+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: summary; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a10c2a-2e94-7a97-b4e1-f4f20188a701', '[{"op": "insert", "after": ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "de7d1eb4801be2759af17d49d5387d57bc4a8116c7886c385da8b5e0648b3b48"], "member": ["acf00265-39de-4dc1-9ba0-527c1ea57862", "d806b686917b65167e3e6ccc52e2abeb09523b1cf4be3a19460d792a0f93d686"]}, {"op": "insert", "after": ["acf00265-39de-4dc1-9ba0-527c1ea57862", "d806b686917b65167e3e6ccc52e2abeb09523b1cf4be3a19460d792a0f93d686"], "member": ["e32a2647-f28d-455f-b30b-157ffacbf186", "80da8646cc274798d103621ddadb5cbe0ac36f03b41ec4942f0b7f46a73ee36a"]}, {"op": "insert", "after": ["e32a2647-f28d-455f-b30b-157ffacbf186", "80da8646cc274798d103621ddadb5cbe0ac36f03b41ec4942f0b7f46a73ee36a"], "member": ["d59cf364-446e-493b-8031-774d0c6d56dc", "974009aa9786ed9674e495ff5ce69125f8e08381f7a7413284198cdba68ad561"]}, {"op": "insert", "after": ["d59cf364-446e-493b-8031-774d0c6d56dc", "974009aa9786ed9674e495ff5ce69125f8e08381f7a7413284198cdba68ad561"], "member": ["bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "6f2ffc9e558dbf753ac836460e17c25741bdf6e71dd5a09ebb05603fe6d70b8b"]}]', '[{"new": ["acf00265-39de-4dc1-9ba0-527c1ea57862", "d806b686917b65167e3e6ccc52e2abeb09523b1cf4be3a19460d792a0f93d686"], "old": null, "kind": "append", "position": 4, "host_logical_id": "acf00265-39de-4dc1-9ba0-527c1ea57862"}, {"new": ["e32a2647-f28d-455f-b30b-157ffacbf186", "80da8646cc274798d103621ddadb5cbe0ac36f03b41ec4942f0b7f46a73ee36a"], "old": null, "kind": "append", "position": 5, "host_logical_id": "e32a2647-f28d-455f-b30b-157ffacbf186"}, {"new": ["d59cf364-446e-493b-8031-774d0c6d56dc", "974009aa9786ed9674e495ff5ce69125f8e08381f7a7413284198cdba68ad561"], "old": null, "kind": "append", "position": 6, "host_logical_id": "d59cf364-446e-493b-8031-774d0c6d56dc"}, {"new": ["bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "6f2ffc9e558dbf753ac836460e17c25741bdf6e71dd5a09ebb05603fe6d70b8b"], "old": null, "kind": "append", "position": 7, "host_logical_id": "bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1"}]', '01a10c2a-2eec-7b4c-ba4c-2c57094da8a0', '2026-10-05 13:04:13.542253+00');
INSERT INTO public.worldline_append VALUES (2, '01a10c2a-2e94-7a97-b4e1-f4f20188a701', '[{"op": "insert", "after": ["bdb21ff8-a8fc-45d6-8a6f-bb8024d2cec1", "6f2ffc9e558dbf753ac836460e17c25741bdf6e71dd5a09ebb05603fe6d70b8b"], "member": ["c3f58464-fec1-480e-8564-ed37d52e5144", "844b5aa66a759804aab8b9417f83d8516fe8dad7a285826e46e3859b9d8a490c"]}, {"op": "insert", "after": ["c3f58464-fec1-480e-8564-ed37d52e5144", "844b5aa66a759804aab8b9417f83d8516fe8dad7a285826e46e3859b9d8a490c"], "member": ["1c451005-49fb-45a5-9cae-d3f9f84d651e", "5b641c5de15b30d2b76a71a91316756963d29073b9888cddf14aece3d6790907"]}, {"op": "insert", "after": ["1c451005-49fb-45a5-9cae-d3f9f84d651e", "5b641c5de15b30d2b76a71a91316756963d29073b9888cddf14aece3d6790907"], "member": ["359551e1-93a2-4dfe-a8e2-ea4df82f1604", "232fb75f443c71abcaa43084f7dd1e0c82c6c94d06c19e15e142013de08f4640"]}, {"op": "insert", "after": ["359551e1-93a2-4dfe-a8e2-ea4df82f1604", "232fb75f443c71abcaa43084f7dd1e0c82c6c94d06c19e15e142013de08f4640"], "member": ["0ff13094-67b2-44a4-bbd3-3c814ab836e8", "fafaff9bbec4433e590cee473992c75ce8fe93c8a599567302f5ce68577081c1"]}]', '[{"new": ["c3f58464-fec1-480e-8564-ed37d52e5144", "844b5aa66a759804aab8b9417f83d8516fe8dad7a285826e46e3859b9d8a490c"], "old": null, "kind": "append", "position": 8, "host_logical_id": "c3f58464-fec1-480e-8564-ed37d52e5144"}, {"new": ["1c451005-49fb-45a5-9cae-d3f9f84d651e", "5b641c5de15b30d2b76a71a91316756963d29073b9888cddf14aece3d6790907"], "old": null, "kind": "append", "position": 9, "host_logical_id": "1c451005-49fb-45a5-9cae-d3f9f84d651e"}, {"new": ["359551e1-93a2-4dfe-a8e2-ea4df82f1604", "232fb75f443c71abcaa43084f7dd1e0c82c6c94d06c19e15e142013de08f4640"], "old": null, "kind": "append", "position": 10, "host_logical_id": "359551e1-93a2-4dfe-a8e2-ea4df82f1604"}, {"new": ["0ff13094-67b2-44a4-bbd3-3c814ab836e8", "fafaff9bbec4433e590cee473992c75ce8fe93c8a599567302f5ce68577081c1"], "old": null, "kind": "append", "position": 11, "host_logical_id": "0ff13094-67b2-44a4-bbd3-3c814ab836e8"}]', '01a10c2a-2f1b-7b66-b0bc-4247d512e437', '2026-10-05 13:04:13.588909+00');
INSERT INTO public.worldline_append VALUES (3, '01a10c2a-2e94-7a97-b4e1-f4f20188a701', '[{"op": "insert", "after": ["0ff13094-67b2-44a4-bbd3-3c814ab836e8", "fafaff9bbec4433e590cee473992c75ce8fe93c8a599567302f5ce68577081c1"], "member": ["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "73461b6434f614e2eb37e20e380caa8551e035e8f71c62dbf39b73ddc044ed1a"]}]', '[{"new": ["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "73461b6434f614e2eb37e20e380caa8551e035e8f71c62dbf39b73ddc044ed1a"], "old": null, "kind": "append", "position": 12, "host_logical_id": "0ae43371-a86f-46b9-8ebc-a97b6fe4af32"}]', '01a10c2a-2f43-7cfa-8476-ff3aad16e924', '2026-10-05 13:04:13.632368+00');
INSERT INTO public.worldline_append VALUES (4, '01a10c2a-374a-79a5-a618-1ced6394132d', '[{"op": "insert", "after": ["169bacd1-e364-4493-81d5-3a61fb5ed678", "5a3a022de4f1ead4fcafbb14f9c3281d07e4dabbc9aa061e4bdec489ed6f2fef"], "member": ["264ab270-3102-4325-ae47-1f735d3daeee", "e5056f171e5312a3a3469b57ac472e81625838213506023fae462eee3c55e904"]}]', '[{"new": ["264ab270-3102-4325-ae47-1f735d3daeee", "e5056f171e5312a3a3469b57ac472e81625838213506023fae462eee3c55e904"], "old": null, "kind": "append", "position": 15, "host_logical_id": "264ab270-3102-4325-ae47-1f735d3daeee"}]', '01a10c2a-3773-7a89-8e4e-4632517e4a65', '2026-10-05 13:04:15.728028+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a10c2a-2e94-7a97-b4e1-f4f20188a701', 1, '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{}', 'import', '072165c9c4bf1b76f45923cc43fcd8645a7a68cfac28e3110d2065af10e641f6', '{"ops": [{"op": "set", "members": [["61857019-d61e-47bd-ac35-9556a4737c79", "438ba2197046e81a69e66450d6f66855eebdba438d25aa296d117098d223e55e"], ["af7eb463-5221-4b4a-ad6a-a1cde8a107d4", "48bb58cee73429e421964b3d06aaec3aa88b99d0ecfc88a04bfd70e731a8678a"], ["1af17204-bcb8-4c25-9b4b-bc8c27161ec1", "79b6404077a6b1bf74cc73e0f21fba498bc622cf41f2512fed2b9dcb63a106dc"], ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "de7d1eb4801be2759af17d49d5387d57bc4a8116c7886c385da8b5e0648b3b48"]]}], "changes": [{"new": ["61857019-d61e-47bd-ac35-9556a4737c79", "438ba2197046e81a69e66450d6f66855eebdba438d25aa296d117098d223e55e"], "old": null, "kind": "append", "position": 0, "host_logical_id": "61857019-d61e-47bd-ac35-9556a4737c79"}, {"new": ["af7eb463-5221-4b4a-ad6a-a1cde8a107d4", "48bb58cee73429e421964b3d06aaec3aa88b99d0ecfc88a04bfd70e731a8678a"], "old": null, "kind": "append", "position": 1, "host_logical_id": "af7eb463-5221-4b4a-ad6a-a1cde8a107d4"}, {"new": ["1af17204-bcb8-4c25-9b4b-bc8c27161ec1", "79b6404077a6b1bf74cc73e0f21fba498bc622cf41f2512fed2b9dcb63a106dc"], "old": null, "kind": "append", "position": 2, "host_logical_id": "1af17204-bcb8-4c25-9b4b-bc8c27161ec1"}, {"new": ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "de7d1eb4801be2759af17d49d5387d57bc4a8116c7886c385da8b5e0648b3b48"], "old": null, "kind": "append", "position": 3, "host_logical_id": "26fdd18c-bcbb-49cc-baf9-3a84971867ba"}]}', '2026-10-05 13:04:13.452146+00', '01a10c2a-2e92-7bee-819d-977b2399067c');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a10c2a-374a-79a5-a618-1ced6394132d', 2, '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{01a10c2a-2e94-7a97-b4e1-f4f20188a701}', 'edit', 'b781c2891a1df1654d91531646bcf59ee0b94c011cec80c58d916dce2a35a1e6', '{"ops": [{"op": "replace", "to": ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "9cc84a64d410b19a5f983125ad08a8dd5cefc3aebc26ed55f77dc52c41b8237a"], "from": ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "de7d1eb4801be2759af17d49d5387d57bc4a8116c7886c385da8b5e0648b3b48"]}, {"op": "insert", "after": ["0ae43371-a86f-46b9-8ebc-a97b6fe4af32", "73461b6434f614e2eb37e20e380caa8551e035e8f71c62dbf39b73ddc044ed1a"], "member": ["d8a3e666-83b7-4e65-b07e-edccc52094af", "8fa70bd989afccfc9b40f3a9d6896e7f0485b79f7aadbe51a5c6c4fa088039f3"]}, {"op": "insert", "after": ["d8a3e666-83b7-4e65-b07e-edccc52094af", "8fa70bd989afccfc9b40f3a9d6896e7f0485b79f7aadbe51a5c6c4fa088039f3"], "member": ["169bacd1-e364-4493-81d5-3a61fb5ed678", "5a3a022de4f1ead4fcafbb14f9c3281d07e4dabbc9aa061e4bdec489ed6f2fef"]}], "changes": [{"new": ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "9cc84a64d410b19a5f983125ad08a8dd5cefc3aebc26ed55f77dc52c41b8237a"], "old": ["26fdd18c-bcbb-49cc-baf9-3a84971867ba", "de7d1eb4801be2759af17d49d5387d57bc4a8116c7886c385da8b5e0648b3b48"], "kind": "edit", "position": 3, "host_logical_id": "26fdd18c-bcbb-49cc-baf9-3a84971867ba"}, {"new": ["d8a3e666-83b7-4e65-b07e-edccc52094af", "8fa70bd989afccfc9b40f3a9d6896e7f0485b79f7aadbe51a5c6c4fa088039f3"], "old": null, "kind": "append", "position": 13, "host_logical_id": "d8a3e666-83b7-4e65-b07e-edccc52094af"}, {"new": ["169bacd1-e364-4493-81d5-3a61fb5ed678", "5a3a022de4f1ead4fcafbb14f9c3281d07e4dabbc9aa061e4bdec489ed6f2fef"], "old": null, "kind": "append", "position": 14, "host_logical_id": "169bacd1-e364-4493-81d5-3a61fb5ed678"}]}', '2026-10-05 13:04:15.685127+00', '01a10c2a-3749-785b-b2ae-ddda8915b4ec');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a10c2a-379e-7504-96c8-5bd11799666b', 3, '01a10c2a-2e85-7856-a82d-a1ee48b9ff37', '{01a10c2a-374a-79a5-a618-1ced6394132d}', 'reconciliation', '42fb3278315abe4f7dca0f450ec17cc046c16b8173b52f807964e667673c501c', '{"ops": [{"op": "replace", "to": ["c3f58464-fec1-480e-8564-ed37d52e5144", "084421254a179d1e822a1a1dea27d10b8d5e207e09db912c868c57aa333aea4c"], "from": ["c3f58464-fec1-480e-8564-ed37d52e5144", "844b5aa66a759804aab8b9417f83d8516fe8dad7a285826e46e3859b9d8a490c"]}, {"op": "replace", "to": ["264ab270-3102-4325-ae47-1f735d3daeee", "d26ae7ec07a6c4f05d83ec07ecd73b9120e66d60035f21450710eab684af84c3"], "from": ["264ab270-3102-4325-ae47-1f735d3daeee", "e5056f171e5312a3a3469b57ac472e81625838213506023fae462eee3c55e904"]}, {"op": "insert", "after": ["264ab270-3102-4325-ae47-1f735d3daeee", "d26ae7ec07a6c4f05d83ec07ecd73b9120e66d60035f21450710eab684af84c3"], "member": ["e6740111-1013-4e0c-82b3-6c083eae658a", "e83b1c02b28e8f73d25b229638a1bf037a34fe21dc0cfd22d950340d5cfe1cac"]}], "changes": [{"new": ["c3f58464-fec1-480e-8564-ed37d52e5144", "084421254a179d1e822a1a1dea27d10b8d5e207e09db912c868c57aa333aea4c"], "old": ["c3f58464-fec1-480e-8564-ed37d52e5144", "844b5aa66a759804aab8b9417f83d8516fe8dad7a285826e46e3859b9d8a490c"], "kind": "disable", "position": 8, "host_logical_id": "c3f58464-fec1-480e-8564-ed37d52e5144"}, {"new": ["264ab270-3102-4325-ae47-1f735d3daeee", "d26ae7ec07a6c4f05d83ec07ecd73b9120e66d60035f21450710eab684af84c3"], "old": ["264ab270-3102-4325-ae47-1f735d3daeee", "e5056f171e5312a3a3469b57ac472e81625838213506023fae462eee3c55e904"], "kind": "swipe", "position": 15, "host_logical_id": "264ab270-3102-4325-ae47-1f735d3daeee"}, {"new": ["e6740111-1013-4e0c-82b3-6c083eae658a", "e83b1c02b28e8f73d25b229638a1bf037a34fe21dc0cfd22d950340d5cfe1cac"], "old": null, "kind": "append", "position": 16, "host_logical_id": "e6740111-1013-4e0c-82b3-6c083eae658a"}]}', '2026-10-05 13:04:15.770156+00', '01a10c2a-379d-747b-addf-ee90ecf9ffaf');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a10c2a-3bbd-7eb1-944b-891f183aeaa3', 4, '01a10c2a-3baf-754d-9ed5-e079f7126b6c', '{}', 'branch', 'b32ce5dd7f1e90a18ccea031a5a666446c91147279327ecb2b83835078d43e34', '{"ops": [{"op": "set", "members": [["874ab783-6047-40e0-ba2f-4b76129feac8", "7718160ef0941c43559324bd57ce40e40cd5e1375b0758c1c5a233a5753ef391"], ["afb3dd85-970c-4279-8e3e-cdb319be40d4", "0121a9db3edf2a5085a429342db1c6348f8c06993c645660198e49d02640f276"], ["2699928b-c953-4aea-b6bf-ad122f8b7f98", "bd8a42710193b7137de066369e4d7486e1b271a54412668d07d9a15ddb50b3ab"], ["ac80afc6-61b4-4f29-b6e4-17dccec3aef9", "62dabee37b116eb38bc1e091e94486b07018662f231e3377f5879c1dacae6ac1"], ["c93d0dac-762d-4b7c-a684-1420957a41e7", "10df552da058df989fd11b0943e65d01c9314e88b52f1811f078d61ef2824ec9"], ["87104492-ff3a-4c9d-88a7-f4d61e51482a", "d577d3925ec259b36e72f1914dc0e395fc08e3ce595dd0cabfc08e5d0e0b57bc"], ["2fdb1ba6-ff9e-4a99-b3f9-175e2e840939", "a0b8809a72526e3ca885a778c47105b4976fde9b28fbe8ed3f0b2fdee77ffa83"], ["e44d3442-f931-4ece-b826-d6f7683cad2a", "5a2db35f13ee84f9d4733945ccd2ea4c7788895dd700b40df9bd9bb4ebd7fa7d"]]}], "changes": [{"new": ["874ab783-6047-40e0-ba2f-4b76129feac8", "7718160ef0941c43559324bd57ce40e40cd5e1375b0758c1c5a233a5753ef391"], "old": null, "kind": "append", "position": 0, "host_logical_id": "874ab783-6047-40e0-ba2f-4b76129feac8"}, {"new": ["afb3dd85-970c-4279-8e3e-cdb319be40d4", "0121a9db3edf2a5085a429342db1c6348f8c06993c645660198e49d02640f276"], "old": null, "kind": "append", "position": 1, "host_logical_id": "afb3dd85-970c-4279-8e3e-cdb319be40d4"}, {"new": ["2699928b-c953-4aea-b6bf-ad122f8b7f98", "bd8a42710193b7137de066369e4d7486e1b271a54412668d07d9a15ddb50b3ab"], "old": null, "kind": "append", "position": 2, "host_logical_id": "2699928b-c953-4aea-b6bf-ad122f8b7f98"}, {"new": ["ac80afc6-61b4-4f29-b6e4-17dccec3aef9", "62dabee37b116eb38bc1e091e94486b07018662f231e3377f5879c1dacae6ac1"], "old": null, "kind": "append", "position": 3, "host_logical_id": "ac80afc6-61b4-4f29-b6e4-17dccec3aef9"}, {"new": ["c93d0dac-762d-4b7c-a684-1420957a41e7", "10df552da058df989fd11b0943e65d01c9314e88b52f1811f078d61ef2824ec9"], "old": null, "kind": "append", "position": 4, "host_logical_id": "c93d0dac-762d-4b7c-a684-1420957a41e7"}, {"new": ["87104492-ff3a-4c9d-88a7-f4d61e51482a", "d577d3925ec259b36e72f1914dc0e395fc08e3ce595dd0cabfc08e5d0e0b57bc"], "old": null, "kind": "append", "position": 5, "host_logical_id": "87104492-ff3a-4c9d-88a7-f4d61e51482a"}, {"new": ["2fdb1ba6-ff9e-4a99-b3f9-175e2e840939", "a0b8809a72526e3ca885a778c47105b4976fde9b28fbe8ed3f0b2fdee77ffa83"], "old": null, "kind": "append", "position": 6, "host_logical_id": "2fdb1ba6-ff9e-4a99-b3f9-175e2e840939"}, {"new": ["e44d3442-f931-4ece-b826-d6f7683cad2a", "5a2db35f13ee84f9d4733945ccd2ea4c7788895dd700b40df9bd9bb4ebd7fa7d"], "old": null, "kind": "append", "position": 7, "host_logical_id": "e44d3442-f931-4ece-b826-d6f7683cad2a"}]}', '2026-10-05 13:04:16.819874+00', '01a10c2a-3bbc-75a0-b9df-233a7dbbfe14');


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


