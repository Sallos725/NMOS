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
    created_at timestamp with time zone DEFAULT now() NOT NULL
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
    projection text NOT NULL
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

INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 0, '01a0dd31-5fce-75fd-bd98-691b4b362c68', '680b827faeca44f17b6babe8dfc59db0', 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 1, '01a0dd31-5fd0-7722-8440-9875fa916e2a', '6537ceb0f3b8de466807b2a6855de3a7', 0, 'aea2a12d21fc10a4df42afe0fe0a5dd3');
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 2, '01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca', 'b8fd612ada0479bfad631abaaae476c1', 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 3, '01a0dd31-6663-7945-a8a1-95b7ad76ecb5', '982b1f870521c2bddb9b84583c712922', 1, 'b16458eed3fc4f556354e513bb60527c');
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 4, '01a0dd31-6004-7b5f-a4b2-3069de3c0776', 'd1388b74e2eb9c034979af92e4b97616', 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 5, '01a0dd31-6005-7b82-89f6-13419ba61afa', '4d781752e7d56c2addf5be1363c4adaf', 2, '7b5aaf03811574ac0e5807af12aef05a');
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 6, '01a0dd31-6006-703b-a6f7-4fd969993060', 'cb5d3403f75516dee9c020fe5520b928', 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 7, '01a0dd31-6007-76ca-89f4-8d640dac0cf4', '0326ed8d7c53ab30b68629585453fc86', 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 8, '01a0dd31-66b2-70f6-a9ac-264a8fc421b0', '06c55c7f15eb2119e38603af6b9620f9', NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 9, '01a0dd31-6032-7ac9-a319-a3a98421a215', '081ac2c7d4356b00dd58d3815a3a52e5', 3, '66331167fbe8bc877c82df3e728ece53');
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 10, '01a0dd31-6033-7d63-b8d4-f9ce3b235d5d', '7b8b7788d15d0bddaeecb22dddf60ac4', 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 11, '01a0dd31-6034-7f18-92da-907912a645e5', 'e7e2b5f790b36edffb88063205c7b2a9', 4, '894b7d6e9d487ed46b378d7aef2f0d0c');
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 12, '01a0dd31-6058-7ecb-ada4-0e9cde103a91', 'f89758eeaef86f3d5c811ba295e18547', 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 13, '01a0dd31-6664-721d-b5e0-389f15a8d9e5', 'fcd36b24738eb6448ae1da5026bc57b4', 5, '5f77092b9d7e255227d17faa7d6401cc');
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 14, '01a0dd31-6664-7d3f-aa65-8451458edc01', 'e56f4f472b3fc84525855813059a1adf', 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 15, '01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9', 'dda47db8cbcd7d8126d05569c1f6b9bb', 6, 'aa3b21cb2e652503f5a8f8a1ad8a8ee0');
INSERT INTO public.active_membership VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 16, '01a0dd31-66b4-7e2b-87be-d4ae3174eb3e', 'd6222c3a136f249946f2f490054e2e78', 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 0, '01a0dd31-6cc4-776a-9bca-4bf13c7371e5', '1ccbe0fd9c1adc99e5e2a44063e0214d', 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 1, '01a0dd31-6cc5-7caf-bcee-6cff921cdd71', '4d3e33053ccfb87db9948ba97a7835e3', 0, '57a939bdacffb2f65cf3a3ad75fe0a46');
INSERT INTO public.active_membership VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 2, '01a0dd31-6cc6-71c1-9d37-dd382e94556e', 'd643df88cab7b8d5554f7fe53ba57b5e', 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 3, '01a0dd31-6cc7-791c-afc3-2e42be82debb', '6f8facc8ac5f70b2baa86728ea8a3c35', 1, '19499a6991961b1f6ccb00db195645fc');
INSERT INTO public.active_membership VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 4, '01a0dd31-6cc8-7e74-96aa-0e26e9e627a9', '6dbc55b2b1292543d26e1515739ba060', 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 5, '01a0dd31-6cc8-7503-affe-a74c60ef3892', '0b31f57cef7d2c92aa1ab6ca76d49a02', 2, 'e48f1ce2bf6b78d1395b3c812d01f0b1');
INSERT INTO public.active_membership VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 6, '01a0dd31-6cc9-72e2-be57-75cc10f64121', 'a31a4c2d56671b7fdb00c0b5d98d5652', NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 7, '01a0dd31-6cca-74ae-906e-4e4eb1922436', '0fcb9b0a3bb8afa42d35bfe72385e3a5', 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0dd31-655c-7f78-bb35-191bdedc0e68', '01a0dd31-6034-7f18-92da-907912a645e5', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0dd31-6573-7fea-aa91-62874913484b', '01a0dd31-6032-7ac9-a319-a3a98421a215', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0dd31-65a2-7850-8fb3-09bee84a8739', '01a0dd31-6005-7b82-89f6-13419ba61afa', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0dd31-65b9-75e1-b981-b701026cc5b6', '01a0dd31-5fd2-7a38-9da8-c167328b926c', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0dd31-65b9-75e1-b981-b701026cc5b6', '01a0dd31-5fd2-7a38-9da8-c167328b926c', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0dd31-6606-763b-a187-ab5603f381e2', '01a0dd31-5fd0-7722-8440-9875fa916e2a', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0dd31-6606-763b-a187-ab5603f381e2', '01a0dd31-5fd0-7722-8440-9875fa916e2a', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0dd31-6a78-7039-be72-9666621402fd', '01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0dd31-6aa6-7ecd-b61a-7e76251e9305', '01a0dd31-6034-7f18-92da-907912a645e5', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0dd31-6abc-7fbe-844b-f44483f42fc9', '01a0dd31-6032-7ac9-a319-a3a98421a215', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0dd31-6ae1-73d6-b259-eb4997777b32', '01a0dd31-6005-7b82-89f6-13419ba61afa', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0dd31-6af8-7f4b-b195-a4a7af44d171', '01a0dd31-6663-7945-a8a1-95b7ad76ecb5', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0dd31-6af8-7f4b-b195-a4a7af44d171', '01a0dd31-6663-7945-a8a1-95b7ad76ecb5', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0dd31-6f7e-7653-83eb-73d42168b60c', '01a0dd31-6cc8-7503-affe-a74c60ef3892', 'Mina', 'character', 'promised', 'Yuuma', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Yuuma to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0dd31-6f97-7410-b8f7-e4cb72bfe14b', '01a0dd31-6cc7-791c-afc3-2e42be82debb', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0dd31-6f97-7410-b8f7-e4cb72bfe14b', '01a0dd31-6cc7-791c-afc3-2e42be82debb', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0dd31-6fac-75f2-9c74-d02c1655424d', '01a0dd31-6cc5-7caf-bcee-6cff921cdd71', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0dd31-6fac-75f2-9c74-d02c1655424d', '01a0dd31-6cc5-7caf-bcee-6cff921cdd71', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'pocketrisu', NULL, 'fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a', '2026-09-26 10:09:55.654395+00', NULL, NULL, NULL, '01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 'fb6b86501600c4240c5b2d90ebfc4d2b942f390072ffcbc67b4c1c890b40dd72', 'Mina', 'Upgrade fixture', 'Yuuma');
INSERT INTO public.conversation VALUES ('01a0dd31-6cba-78f6-8285-1b619853d965', 'pocketrisu', NULL, 'a2ae0aac-6d84-4552-93e9-15da78b997ed', '2026-09-26 10:09:58.97069+00', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a', 'f74600fd-8da6-4c58-ae9b-1e2e3300d9d2', '01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', '77e6df65c43735dbcde5158a5e780510fc716fee20b691adfce876459690df82', 'Mina', 'Upgrade fixture', 'Yuuma');


--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0dd31-655c-7f78-bb35-191bdedc0e68', '01a0dd31-6034-7f18-92da-907912a645e5', 'cd651e16f99b7c39f1abca830c1ba70b', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:57.084064+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0dd31-6033-7d63-b8d4-f9ce3b235d5d,01a0dd31-6034-7f18-92da-907912a645e5}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6573-7fea-aa91-62874913484b', '01a0dd31-6032-7ac9-a319-a3a98421a215', 'fca518c925621bb903176ca538d13374', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:57.107491+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0dd31-6031-7c06-913a-452c0929ea84,01a0dd31-6032-7ac9-a319-a3a98421a215}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-658a-7614-84f2-e1fb6ec613ff', '01a0dd31-6007-76ca-89f4-8d640dac0cf4', '24a98a589ec562e02af7b24aea8772ec', 'extract-v8', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:57.129939+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0dd31-6006-703b-a6f7-4fd969993060,01a0dd31-6007-76ca-89f4-8d640dac0cf4}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-65a2-7850-8fb3-09bee84a8739', '01a0dd31-6005-7b82-89f6-13419ba61afa', '248c0adb3156de8e84a76b60b06badab', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:57.154898+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0dd31-6004-7b5f-a4b2-3069de3c0776,01a0dd31-6005-7b82-89f6-13419ba61afa}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-65b9-75e1-b981-b701026cc5b6', '01a0dd31-5fd2-7a38-9da8-c167328b926c', '348cd351fa278390391ef8d633bcda8e', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:57.176962+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca,01a0dd31-5fd2-7a38-9da8-c167328b926c}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6606-763b-a187-ab5603f381e2', '01a0dd31-5fd0-7722-8440-9875fa916e2a', 'aea2a12d21fc10a4df42afe0fe0a5dd3', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:57.254845+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0dd31-5fce-75fd-bd98-691b4b362c68,01a0dd31-5fd0-7722-8440-9875fa916e2a}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6a78-7039-be72-9666621402fd', '01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9', 'aa3b21cb2e652503f5a8f8a1ad8a8ee0', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:58.392226+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0dd31-6664-7d3f-aa65-8451458edc01,01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6a90-7547-8873-28b0b77c531e', '01a0dd31-6664-721d-b5e0-389f15a8d9e5', '5f77092b9d7e255227d17faa7d6401cc', 'extract-v8', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-26 10:09:58.416104+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0dd31-6058-7ecb-ada4-0e9cde103a91,01a0dd31-6664-721d-b5e0-389f15a8d9e5}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6aa6-7ecd-b61a-7e76251e9305', '01a0dd31-6034-7f18-92da-907912a645e5', '894b7d6e9d487ed46b378d7aef2f0d0c', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:58.43814+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0dd31-6033-7d63-b8d4-f9ce3b235d5d,01a0dd31-6034-7f18-92da-907912a645e5}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6abc-7fbe-844b-f44483f42fc9', '01a0dd31-6032-7ac9-a319-a3a98421a215', '66331167fbe8bc877c82df3e728ece53', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:58.460075+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0dd31-6006-703b-a6f7-4fd969993060,01a0dd31-6007-76ca-89f4-8d640dac0cf4,01a0dd31-6032-7ac9-a319-a3a98421a215}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6ae1-73d6-b259-eb4997777b32', '01a0dd31-6005-7b82-89f6-13419ba61afa', '7b5aaf03811574ac0e5807af12aef05a', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:58.497725+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0dd31-6004-7b5f-a4b2-3069de3c0776,01a0dd31-6005-7b82-89f6-13419ba61afa}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6af8-7f4b-b195-a4a7af44d171', '01a0dd31-6663-7945-a8a1-95b7ad76ecb5', 'b16458eed3fc4f556354e513bb60527c', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:58.520196+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca,01a0dd31-6663-7945-a8a1-95b7ad76ecb5}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6f7e-7653-83eb-73d42168b60c', '01a0dd31-6cc8-7503-affe-a74c60ef3892', 'e48f1ce2bf6b78d1395b3c812d01f0b1', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Yuuma\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Yuuma to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:59.678514+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 86, "target_chars": 86, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0dd31-6cc8-7e74-96aa-0e26e9e627a9,01a0dd31-6cc8-7503-affe-a74c60ef3892}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6f97-7410-b8f7-e4cb72bfe14b', '01a0dd31-6cc7-791c-afc3-2e42be82debb', '19499a6991961b1f6ccb00db195645fc', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:59.703009+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0dd31-6cc6-71c1-9d37-dd382e94556e,01a0dd31-6cc7-791c-afc3-2e42be82debb}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0dd31-6fac-75f2-9c74-d02c1655424d', '01a0dd31-6cc5-7caf-bcee-6cff921cdd71', '57a939bdacffb2f65cf3a3ad75fe0a46', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-26 10:09:59.724904+00', 'extract-34fea47ace259d385ba741bcaf6d023e', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0dd31-6cc4-776a-9bca-4bf13c7371e5,01a0dd31-6cc5-7caf-bcee-6cff921cdd71}', NULL, '{"entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0dd31-5fd4-7ffd-ae4f-a4888e01ddfc', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'manifest', '172900f9fb7d34d3f9cf486aaf047fff89cada916fca1ef812af61270a38ddd7', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c:172900f9fb7d34d3f9cf486aaf047fff89cada916fca1ef812af61270a38ddd7:manifest', '2026-09-26 10:09:55.660365+00', '{"chat_id": "fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["ca230e03-fe28-4be7-ba01-93bba6012861", "acc4463065e74da1e1df7bbf7af6a6773c044058606d2bb554f7b40fe810ecdc", "user", null, null, null, 0, null, null], ["a61e4bdf-d3f2-4817-afec-3ec788c56c1a", "0d739e5dbe2d14807ac44cbced79ef97f13340998113ac24e7467a9845a9672d", "char", null, null, null, 0, "a61e4bdf-d3f2-4817-afec-3ec788c56c1a", null], ["05b11192-7267-46aa-8838-b086ee29dc4e", "c9e4f099193e89a11af985f27b08544ea664867a91041d45193c3fada06e423d", "user", null, null, null, 0, null, null], ["b8061b51-c576-434a-bda9-78874a305413", "aa5b436eb87dca5afb8a913f9ee7f5f09b2a683d0f058febc3d546c41ecc8c32", "char", null, null, null, 0, "b8061b51-c576-434a-bda9-78874a305413", null]]}');
INSERT INTO public.host_observation VALUES ('01a0dd31-600a-73ac-b6d3-d2503fb99564', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'manifest', '17132ca02d551e1c744986a78b3a7d0c053eec75db9a56139b3693b694fac264', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c:17132ca02d551e1c744986a78b3a7d0c053eec75db9a56139b3693b694fac264:manifest', '2026-09-26 10:09:55.715697+00', '{"chat_id": "fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["0b449ecb-456d-4159-9ae3-312e7a7b7d8c", "95a44e926986fd6b2c1a358c24cbbbac66b3bd65553d3d27881fc36558cbf8ce", "user", null, null, null, 0, null, null], ["f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "b530323378cf45ed3a933c8964250e0b698978569219a9f80ced22ad15059409", "char", null, null, null, 0, "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", null], ["ed74e6ad-5304-4066-8c08-9d9bad7afd56", "fe15fdbb3e9cfe72b6cc41221cf83060c115a494f7a4134bd58f1da72fc40c73", "user", null, null, null, 0, null, null], ["497a21d0-18ef-4cb3-b1f3-26396f379cea", "f19728ccc60af24be42b521c6da334f47fcecd74c8119bc097e152e3a91e84ac", "char", null, null, null, 0, "497a21d0-18ef-4cb3-b1f3-26396f379cea", null]], "base_manifest_hash": "172900f9fb7d34d3f9cf486aaf047fff89cada916fca1ef812af61270a38ddd7"}');
INSERT INTO public.host_observation VALUES ('01a0dd31-6036-70fd-9e99-8ae364541fdf', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'manifest', '3750a788ebeffbf53b6ef556cf8babcfb8dd267a6e1601a9f284091b0009f75d', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c:3750a788ebeffbf53b6ef556cf8babcfb8dd267a6e1601a9f284091b0009f75d:manifest', '2026-09-26 10:09:55.760394+00', '{"chat_id": "fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["f30bc75d-44af-4002-b14b-eff8b7b57568", "61ec30500664168be0d03afb3929ce5208f43eb4cf8dcacb4e92e9c1a0f41dea", "user", null, null, null, 0, null, null], ["6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", "90a9037d7ae1bf5138c13535c42a4280c2278e10dedaad9ee4c0bfd3c5e41bb3", "char", null, null, null, 0, "6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", null], ["fc6da17a-2495-489c-94cf-37d92cb51559", "8c40513a9b8ffbcdde65a432ae2d9bd46be6a8f1a02c4c7566efdc894ddb82dd", "user", null, null, null, 0, null, null], ["c194d9aa-7c70-4a6e-aea0-82095d57272f", "c7572f9f27ce3fa1a0a187ca421fc767d888843601a94bd5396879a1adb26445", "char", null, null, null, 0, "c194d9aa-7c70-4a6e-aea0-82095d57272f", null]], "base_manifest_hash": "17132ca02d551e1c744986a78b3a7d0c053eec75db9a56139b3693b694fac264"}');
INSERT INTO public.host_observation VALUES ('01a0dd31-605b-7ace-abf4-2637d09a3ab3', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'manifest', 'e24bcdcae8028650545017a3fa5a7e7cf8bf723873f4144355532872c4b7d781', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c:e24bcdcae8028650545017a3fa5a7e7cf8bf723873f4144355532872c4b7d781:manifest', '2026-09-26 10:09:55.799196+00', '{"chat_id": "fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["79a0f669-e994-47e5-a58c-27732636c960", "95871755373e3ecd13131bdf053af6f0e1820746afca439f21078aab31be2bad", "user", null, null, null, 0, null, null]], "base_manifest_hash": "3750a788ebeffbf53b6ef556cf8babcfb8dd267a6e1601a9f284091b0009f75d"}');
INSERT INTO public.host_observation VALUES ('01a0dd31-6667-7ede-930e-47e396c29495', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'manifest', '3fbade8d73df6619ec288339ecb2e4c31902d92e0eab4cd69a0d0cee8910f58f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c:3fbade8d73df6619ec288339ecb2e4c31902d92e0eab4cd69a0d0cee8910f58f:manifest', '2026-09-26 10:09:57.346463+00', '{"chat_id": "fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["ca230e03-fe28-4be7-ba01-93bba6012861", "acc4463065e74da1e1df7bbf7af6a6773c044058606d2bb554f7b40fe810ecdc", "user", null, null, null, 0, null, null], ["a61e4bdf-d3f2-4817-afec-3ec788c56c1a", "0d739e5dbe2d14807ac44cbced79ef97f13340998113ac24e7467a9845a9672d", "char", null, null, null, 0, "a61e4bdf-d3f2-4817-afec-3ec788c56c1a", null], ["05b11192-7267-46aa-8838-b086ee29dc4e", "c9e4f099193e89a11af985f27b08544ea664867a91041d45193c3fada06e423d", "user", null, null, null, 0, null, null], ["b8061b51-c576-434a-bda9-78874a305413", "e3622f0f5ea1734a684f6e3f1775d94fd006d99aaf78cdfa788ed9624ff220e6", "char", null, null, null, 0, "b8061b51-c576-434a-bda9-78874a305413", null], ["0b449ecb-456d-4159-9ae3-312e7a7b7d8c", "95a44e926986fd6b2c1a358c24cbbbac66b3bd65553d3d27881fc36558cbf8ce", "user", null, null, null, 0, null, null], ["f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "b530323378cf45ed3a933c8964250e0b698978569219a9f80ced22ad15059409", "char", null, null, null, 0, "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", null], ["ed74e6ad-5304-4066-8c08-9d9bad7afd56", "fe15fdbb3e9cfe72b6cc41221cf83060c115a494f7a4134bd58f1da72fc40c73", "user", null, null, null, 0, null, null], ["497a21d0-18ef-4cb3-b1f3-26396f379cea", "f19728ccc60af24be42b521c6da334f47fcecd74c8119bc097e152e3a91e84ac", "char", null, null, null, 0, "497a21d0-18ef-4cb3-b1f3-26396f379cea", null], ["f30bc75d-44af-4002-b14b-eff8b7b57568", "61ec30500664168be0d03afb3929ce5208f43eb4cf8dcacb4e92e9c1a0f41dea", "user", null, null, null, 0, null, null], ["6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", "90a9037d7ae1bf5138c13535c42a4280c2278e10dedaad9ee4c0bfd3c5e41bb3", "char", null, null, null, 0, "6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", null], ["fc6da17a-2495-489c-94cf-37d92cb51559", "8c40513a9b8ffbcdde65a432ae2d9bd46be6a8f1a02c4c7566efdc894ddb82dd", "user", null, null, null, 0, null, null], ["c194d9aa-7c70-4a6e-aea0-82095d57272f", "c7572f9f27ce3fa1a0a187ca421fc767d888843601a94bd5396879a1adb26445", "char", null, null, null, 0, "c194d9aa-7c70-4a6e-aea0-82095d57272f", null], ["79a0f669-e994-47e5-a58c-27732636c960", "95871755373e3ecd13131bdf053af6f0e1820746afca439f21078aab31be2bad", "user", null, null, null, 0, null, null], ["52d52349-a893-470a-8e19-67b31f658ff7", "2faeeaf8bbff6fdd6fc848a7e5d72c6b4193a03531cd27146b2d52a8fbb7a096", "char", null, null, null, 0, "52d52349-a893-470a-8e19-67b31f658ff7", null], ["7bb0457d-d5ff-4215-91a8-b5d9e434a8ec", "f769ff0e29b3e7755e82ebccc38b32817ad4836ed7a9caa0a845e0a7e0344f19", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0dd31-668f-721f-926a-418b58f8004d', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'manifest', '8a41053eccd38dc38f9f4332502d14aca77d004ae69dcbe80e62717902f33fb4', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c:8a41053eccd38dc38f9f4332502d14aca77d004ae69dcbe80e62717902f33fb4:manifest', '2026-09-26 10:09:57.38789+00', '{"chat_id": "fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["ed95e553-b9cd-4910-9514-d3c1225c54a1", "a7dd4e0a8a8c6667b8b5c6b3545f9941d76a95119bf7bf56e8ef6e3e2671e89d", "char", null, null, 1, 2, "ed95e553-b9cd-4910-9514-d3c1225c54a1", null]], "base_manifest_hash": "3fbade8d73df6619ec288339ecb2e4c31902d92e0eab4cd69a0d0cee8910f58f"}');
INSERT INTO public.host_observation VALUES ('01a0dd31-66b5-79dd-ab29-84065c48705d', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'manifest', 'fb6b86501600c4240c5b2d90ebfc4d2b942f390072ffcbc67b4c1c890b40dd72', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c:fb6b86501600c4240c5b2d90ebfc4d2b942f390072ffcbc67b4c1c890b40dd72:manifest', '2026-09-26 10:09:57.425809+00', '{"chat_id": "fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["ca230e03-fe28-4be7-ba01-93bba6012861", "acc4463065e74da1e1df7bbf7af6a6773c044058606d2bb554f7b40fe810ecdc", "user", null, null, null, 0, null, null], ["a61e4bdf-d3f2-4817-afec-3ec788c56c1a", "0d739e5dbe2d14807ac44cbced79ef97f13340998113ac24e7467a9845a9672d", "char", null, null, null, 0, "a61e4bdf-d3f2-4817-afec-3ec788c56c1a", null], ["05b11192-7267-46aa-8838-b086ee29dc4e", "c9e4f099193e89a11af985f27b08544ea664867a91041d45193c3fada06e423d", "user", null, null, null, 0, null, null], ["b8061b51-c576-434a-bda9-78874a305413", "e3622f0f5ea1734a684f6e3f1775d94fd006d99aaf78cdfa788ed9624ff220e6", "char", null, null, null, 0, "b8061b51-c576-434a-bda9-78874a305413", null], ["0b449ecb-456d-4159-9ae3-312e7a7b7d8c", "95a44e926986fd6b2c1a358c24cbbbac66b3bd65553d3d27881fc36558cbf8ce", "user", null, null, null, 0, null, null], ["f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "b530323378cf45ed3a933c8964250e0b698978569219a9f80ced22ad15059409", "char", null, null, null, 0, "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", null], ["ed74e6ad-5304-4066-8c08-9d9bad7afd56", "fe15fdbb3e9cfe72b6cc41221cf83060c115a494f7a4134bd58f1da72fc40c73", "user", null, null, null, 0, null, null], ["497a21d0-18ef-4cb3-b1f3-26396f379cea", "f19728ccc60af24be42b521c6da334f47fcecd74c8119bc097e152e3a91e84ac", "char", null, null, null, 0, "497a21d0-18ef-4cb3-b1f3-26396f379cea", null], ["f30bc75d-44af-4002-b14b-eff8b7b57568", "3016fde15437528b93249fbd96bde73ecf196bd37706966129df9d518ed13162", "user", true, null, null, 0, null, null], ["6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", "90a9037d7ae1bf5138c13535c42a4280c2278e10dedaad9ee4c0bfd3c5e41bb3", "char", null, null, null, 0, "6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", null], ["fc6da17a-2495-489c-94cf-37d92cb51559", "8c40513a9b8ffbcdde65a432ae2d9bd46be6a8f1a02c4c7566efdc894ddb82dd", "user", null, null, null, 0, null, null], ["c194d9aa-7c70-4a6e-aea0-82095d57272f", "c7572f9f27ce3fa1a0a187ca421fc767d888843601a94bd5396879a1adb26445", "char", null, null, null, 0, "c194d9aa-7c70-4a6e-aea0-82095d57272f", null], ["79a0f669-e994-47e5-a58c-27732636c960", "95871755373e3ecd13131bdf053af6f0e1820746afca439f21078aab31be2bad", "user", null, null, null, 0, null, null], ["52d52349-a893-470a-8e19-67b31f658ff7", "2faeeaf8bbff6fdd6fc848a7e5d72c6b4193a03531cd27146b2d52a8fbb7a096", "char", null, null, null, 0, "52d52349-a893-470a-8e19-67b31f658ff7", null], ["7bb0457d-d5ff-4215-91a8-b5d9e434a8ec", "f769ff0e29b3e7755e82ebccc38b32817ad4836ed7a9caa0a845e0a7e0344f19", "user", null, null, null, 0, null, null], ["ed95e553-b9cd-4910-9514-d3c1225c54a1", "638c8c0e712b06b7b6dcfc5cc792ad07d74f740266278d6a947b61039519dab4", "char", null, null, 0, 2, "ed95e553-b9cd-4910-9514-d3c1225c54a1", null], ["83714a7e-a494-453c-96bc-2531c4d49f60", "f59b9a6078e102ebfa833efcfb7278bd8a43c68efa8e4a03bcd6706febe19b49", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0dd31-6ccb-72fd-8065-00f407a8e767', '01a0dd31-6cba-78f6-8285-1b619853d965', 'manifest', '77e6df65c43735dbcde5158a5e780510fc716fee20b691adfce876459690df82', '01a0dd31-6cba-78f6-8285-1b619853d965:77e6df65c43735dbcde5158a5e780510fc716fee20b691adfce876459690df82:manifest', '2026-09-26 10:09:58.979515+00', '{"chat_id": "a2ae0aac-6d84-4552-93e9-15da78b997ed", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["d28f72fe-2480-42af-87e2-fe0ced529473", "737f81a173a6c874aced55d7c1c2c1b79e59b8980e294a1a01b9c973ae2038ce", "user", null, null, null, 0, null, null], ["7f11be62-d170-449c-a429-1cc2ff3d6dc0", "3c0c3ed65e595da9deae0d4647791efcbbf4d319b871310bbb69b944dc063451", "char", null, null, null, 0, "a61e4bdf-d3f2-4817-afec-3ec788c56c1a", null], ["f2f07485-7cbc-41df-82f0-871d5ccba645", "f3d91c54730b31eca7e123ce34397b0f0187d348a6bbad6a824c7e9bcff5ddc3", "user", null, null, null, 0, null, null], ["4f78985e-bbaf-416d-81a4-4e29303bcfb4", "8236b1cd2cf13940345d1c953e6bbd1d2a5a011c335c7ec724956f3cbcd705d5", "char", null, null, null, 0, "b8061b51-c576-434a-bda9-78874a305413", null], ["1746ecfe-6328-4b1c-aa58-1b8cf3448d8b", "01e2b4743458af5279f0510ffb2a2ab59de68efbae433eb71e3dc1162cd5015d", "user", null, null, null, 0, null, null], ["5094bbfe-c238-45a4-ae56-f763add012c3", "3224b9e9499f6841ef7f07a926a9205be69f4f43bc7587fadc1a5ac744af6d9b", "char", null, null, null, 0, "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", null], ["c565e305-e7e3-4d7d-b12b-7b6e473ae971", "013b27337c81119eb17e9affa35ac972d3b983a4f9e064866da0fbbd379fedcc", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a::Harbor route::f74600fd-8da6-4c58-ae9b-1e2e3300d9d2::}}"]], ["4a4098ec-8e73-4b54-a59f-403048ca9106", "ea140a645d8edb44add8057dc85db5d68be8eaaf2c3aaa50489458571daef09c", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0dd31-6058-7ecb-ada4-0e9cde103a91:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6058-7ecb-ada4-0e9cde103a91"}', 50, 'done', 1, '2026-09-26 10:09:55.799196+00', NULL, NULL, '2026-09-26 10:09:55.799196+00', '2026-09-26 10:09:56.874058+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0dd31-6034-7f18-92da-907912a645e5:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6034-7f18-92da-907912a645e5"}', 50, 'done', 1, '2026-09-26 10:09:55.799196+00', NULL, NULL, '2026-09-26 10:09:55.799196+00', '2026-09-26 10:09:56.895154+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0dd31-6033-7d63-b8d4-f9ce3b235d5d:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6033-7d63-b8d4-f9ce3b235d5d"}', 50, 'done', 1, '2026-09-26 10:09:55.760394+00', NULL, NULL, '2026-09-26 10:09:55.760394+00', '2026-09-26 10:09:56.915175+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0dd31-6032-7ac9-a319-a3a98421a215:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6032-7ac9-a319-a3a98421a215"}', 50, 'done', 1, '2026-09-26 10:09:55.760394+00', NULL, NULL, '2026-09-26 10:09:55.760394+00', '2026-09-26 10:09:56.937333+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0dd31-6031-7c06-913a-452c0929ea84:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6031-7c06-913a-452c0929ea84"}', 50, 'done', 1, '2026-09-26 10:09:55.760394+00', NULL, NULL, '2026-09-26 10:09:55.760394+00', '2026-09-26 10:09:56.957075+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0dd31-6007-76ca-89f4-8d640dac0cf4:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6007-76ca-89f4-8d640dac0cf4"}', 50, 'done', 1, '2026-09-26 10:09:55.760394+00', NULL, NULL, '2026-09-26 10:09:55.760394+00', '2026-09-26 10:09:56.97702+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0dd31-6006-703b-a6f7-4fd969993060:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6006-703b-a6f7-4fd969993060"}', 50, 'done', 1, '2026-09-26 10:09:55.715697+00', NULL, NULL, '2026-09-26 10:09:55.715697+00', '2026-09-26 10:09:56.995762+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0dd31-6005-7b82-89f6-13419ba61afa:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6005-7b82-89f6-13419ba61afa"}', 50, 'done', 1, '2026-09-26 10:09:55.715697+00', NULL, NULL, '2026-09-26 10:09:55.715697+00', '2026-09-26 10:09:57.017368+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0dd31-6004-7b5f-a4b2-3069de3c0776:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6004-7b5f-a4b2-3069de3c0776"}', 50, 'done', 1, '2026-09-26 10:09:55.715697+00', NULL, NULL, '2026-09-26 10:09:55.715697+00', '2026-09-26 10:09:57.03773+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0dd31-5fd2-7a38-9da8-c167328b926c:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-5fd2-7a38-9da8-c167328b926c"}', 50, 'done', 1, '2026-09-26 10:09:55.715697+00', NULL, NULL, '2026-09-26 10:09:55.715697+00', '2026-09-26 10:09:57.062464+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0dd31-6034-7f18-92da-907912a645e5:cd651e16f99b7c39f1abca830c1ba70b:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6034-7f18-92da-907912a645e5", "window_hash": "cd651e16f99b7c39f1abca830c1ba70b"}', 100, 'done', 1, '2026-09-26 10:09:55.799196+00', NULL, NULL, '2026-09-26 10:09:55.799196+00', '2026-09-26 10:09:57.086598+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0dd31-6032-7ac9-a319-a3a98421a215:fca518c925621bb903176ca538d13374:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6032-7ac9-a319-a3a98421a215", "window_hash": "fca518c925621bb903176ca538d13374"}', 100, 'done', 1, '2026-09-26 10:09:55.760394+00', NULL, NULL, '2026-09-26 10:09:55.760394+00', '2026-09-26 10:09:57.109378+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0dd31-6007-76ca-89f4-8d640dac0cf4:24a98a589ec562e02af7b24aea8772ec:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6007-76ca-89f4-8d640dac0cf4", "window_hash": "24a98a589ec562e02af7b24aea8772ec"}', 100, 'done', 1, '2026-09-26 10:09:55.760394+00', NULL, NULL, '2026-09-26 10:09:55.760394+00', '2026-09-26 10:09:57.131671+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0dd31-6005-7b82-89f6-13419ba61afa:248c0adb3156de8e84a76b60b06badab:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6005-7b82-89f6-13419ba61afa", "window_hash": "248c0adb3156de8e84a76b60b06badab"}', 100, 'done', 1, '2026-09-26 10:09:55.715697+00', NULL, NULL, '2026-09-26 10:09:55.715697+00', '2026-09-26 10:09:57.157127+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0dd31-5fd2-7a38-9da8-c167328b926c:348cd351fa278390391ef8d633bcda8e:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-5fd2-7a38-9da8-c167328b926c", "window_hash": "348cd351fa278390391ef8d633bcda8e"}', 100, 'done', 1, '2026-09-26 10:09:55.715697+00', NULL, NULL, '2026-09-26 10:09:55.715697+00', '2026-09-26 10:09:57.17903+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca"}', 150, 'done', 1, '2026-09-26 10:09:55.660365+00', NULL, NULL, '2026-09-26 10:09:55.660365+00', '2026-09-26 10:09:57.198067+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0dd31-5fd0-7722-8440-9875fa916e2a:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-5fd0-7722-8440-9875fa916e2a"}', 150, 'done', 1, '2026-09-26 10:09:55.660365+00', NULL, NULL, '2026-09-26 10:09:55.660365+00', '2026-09-26 10:09:57.216256+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0dd31-5fce-75fd-bd98-691b4b362c68:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-5fce-75fd-bd98-691b4b362c68"}', 150, 'done', 1, '2026-09-26 10:09:55.660365+00', NULL, NULL, '2026-09-26 10:09:55.660365+00', '2026-09-26 10:09:57.235092+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0dd31-5fd0-7722-8440-9875fa916e2a:aea2a12d21fc10a4df42afe0fe0a5dd3:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-5fd0-7722-8440-9875fa916e2a", "window_hash": "aea2a12d21fc10a4df42afe0fe0a5dd3"}', 200, 'done', 1, '2026-09-26 10:09:55.660365+00', NULL, NULL, '2026-09-26 10:09:55.660365+00', '2026-09-26 10:09:57.261175+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0dd31-6005-7b82-89f6-13419ba61afa:7b5aaf03811574ac0e5807af12aef05a:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6005-7b82-89f6-13419ba61afa", "window_hash": "7b5aaf03811574ac0e5807af12aef05a"}', 100, 'done', 1, '2026-09-26 10:09:57.346463+00', NULL, NULL, '2026-09-26 10:09:57.346463+00', '2026-09-26 10:09:58.499751+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0dd31-6663-7945-a8a1-95b7ad76ecb5:b16458eed3fc4f556354e513bb60527c:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6663-7945-a8a1-95b7ad76ecb5", "window_hash": "b16458eed3fc4f556354e513bb60527c"}', 100, 'done', 1, '2026-09-26 10:09:57.346463+00', NULL, NULL, '2026-09-26 10:09:57.346463+00', '2026-09-26 10:09:58.52251+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0dd31-66b4-7e2b-87be-d4ae3174eb3e:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-66b4-7e2b-87be-d4ae3174eb3e"}', 50, 'done', 1, '2026-09-26 10:09:57.425809+00', NULL, NULL, '2026-09-26 10:09:57.425809+00', '2026-09-26 10:09:58.2887+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9"}', 50, 'done', 1, '2026-09-26 10:09:57.425809+00', NULL, NULL, '2026-09-26 10:09:57.425809+00', '2026-09-26 10:09:58.309598+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0dd31-6664-7d3f-aa65-8451458edc01:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6664-7d3f-aa65-8451458edc01"}', 50, 'done', 1, '2026-09-26 10:09:57.346463+00', NULL, NULL, '2026-09-26 10:09:57.346463+00', '2026-09-26 10:09:58.32908+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0dd31-6664-721d-b5e0-389f15a8d9e5:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6664-721d-b5e0-389f15a8d9e5"}', 50, 'done', 1, '2026-09-26 10:09:57.346463+00', NULL, NULL, '2026-09-26 10:09:57.346463+00', '2026-09-26 10:09:58.34835+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0dd31-6663-7945-a8a1-95b7ad76ecb5:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6663-7945-a8a1-95b7ad76ecb5"}', 50, 'done', 1, '2026-09-26 10:09:57.346463+00', NULL, NULL, '2026-09-26 10:09:57.346463+00', '2026-09-26 10:09:58.368238+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9:aa3b21cb2e652503f5a8f8a1ad8a8ee0:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9", "window_hash": "aa3b21cb2e652503f5a8f8a1ad8a8ee0"}', 100, 'done', 1, '2026-09-26 10:09:57.425809+00', NULL, NULL, '2026-09-26 10:09:57.425809+00', '2026-09-26 10:09:58.394148+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0dd31-6664-721d-b5e0-389f15a8d9e5:5f77092b9d7e255227d17faa7d6401cc:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6664-721d-b5e0-389f15a8d9e5", "window_hash": "5f77092b9d7e255227d17faa7d6401cc"}', 100, 'done', 1, '2026-09-26 10:09:57.425809+00', NULL, NULL, '2026-09-26 10:09:57.425809+00', '2026-09-26 10:09:58.417681+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0dd31-6034-7f18-92da-907912a645e5:894b7d6e9d487ed46b378d7aef2f0d0c:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6034-7f18-92da-907912a645e5", "window_hash": "894b7d6e9d487ed46b378d7aef2f0d0c"}', 100, 'done', 1, '2026-09-26 10:09:57.425809+00', NULL, NULL, '2026-09-26 10:09:57.425809+00', '2026-09-26 10:09:58.439947+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0dd31-6032-7ac9-a319-a3a98421a215:66331167fbe8bc877c82df3e728ece53:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6032-7ac9-a319-a3a98421a215", "window_hash": "66331167fbe8bc877c82df3e728ece53"}', 100, 'done', 1, '2026-09-26 10:09:57.425809+00', NULL, NULL, '2026-09-26 10:09:57.425809+00', '2026-09-26 10:09:58.461926+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0dd31-6664-721d-b5e0-389f15a8d9e5:61b5ed1daddf030d2583419f03ef2f34:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6664-721d-b5e0-389f15a8d9e5", "window_hash": "61b5ed1daddf030d2583419f03ef2f34"}', 100, 'obsolete', 1, '2026-09-26 10:09:57.346463+00', NULL, NULL, '2026-09-26 10:09:57.346463+00', '2026-09-26 10:09:58.465684+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0dd31-6032-7ac9-a319-a3a98421a215:0f0748808d4fbf9a20c9fc6eecbe3d28:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6032-7ac9-a319-a3a98421a215", "window_hash": "0f0748808d4fbf9a20c9fc6eecbe3d28"}', 100, 'obsolete', 1, '2026-09-26 10:09:57.346463+00', NULL, NULL, '2026-09-26 10:09:57.346463+00', '2026-09-26 10:09:58.470027+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0dd31-6007-76ca-89f4-8d640dac0cf4:8b2e44f0dd96b67215133ae82a7019d7:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6007-76ca-89f4-8d640dac0cf4", "window_hash": "8b2e44f0dd96b67215133ae82a7019d7"}', 100, 'obsolete', 1, '2026-09-26 10:09:57.346463+00', NULL, NULL, '2026-09-26 10:09:57.346463+00', '2026-09-26 10:09:58.473423+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0dd31-6cca-74ae-906e-4e4eb1922436:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6cca-74ae-906e-4e4eb1922436"}', 150, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.542388+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0dd31-6cc8-7503-affe-a74c60ef3892:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6cc8-7503-affe-a74c60ef3892"}', 150, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.560984+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0dd31-6cc8-7e74-96aa-0e26e9e627a9:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6cc8-7e74-96aa-0e26e9e627a9"}', 150, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.5833+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0dd31-6cc7-791c-afc3-2e42be82debb:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6cc7-791c-afc3-2e42be82debb"}', 150, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.602285+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0dd31-6cc6-71c1-9d37-dd382e94556e:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6cc6-71c1-9d37-dd382e94556e"}', 150, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.621058+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0dd31-6cc5-7caf-bcee-6cff921cdd71:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6cc5-7caf-bcee-6cff921cdd71"}', 150, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.640781+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0dd31-6cc4-776a-9bca-4bf13c7371e5:embed-5b01ef89c6358fee1493caf5d5c8f05f', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "embed-5b01ef89c6358fee1493caf5d5c8f05f", "revision_id": "01a0dd31-6cc4-776a-9bca-4bf13c7371e5"}', 150, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.659719+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0dd31-6cc8-7503-affe-a74c60ef3892:e48f1ce2bf6b78d1395b3c812d01f0b1:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6cc8-7503-affe-a74c60ef3892", "window_hash": "e48f1ce2bf6b78d1395b3c812d01f0b1"}', 200, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.680345+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0dd31-6cc7-791c-afc3-2e42be82debb:19499a6991961b1f6ccb00db195645fc:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6cc7-791c-afc3-2e42be82debb", "window_hash": "19499a6991961b1f6ccb00db195645fc"}', 200, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.70495+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0dd31-6cc5-7caf-bcee-6cff921cdd71:57a939bdacffb2f65cf3a3ad75fe0a46:extract-34fea47ace259d385ba741bcaf6d023e', '01a0dd31-6cba-78f6-8285-1b619853d965', '{"generation": "extract-34fea47ace259d385ba741bcaf6d023e", "revision_id": "01a0dd31-6cc5-7caf-bcee-6cff921cdd71", "window_hash": "57a939bdacffb2f65cf3a3ad75fe0a46"}', 200, 'done', 1, '2026-09-26 10:09:58.979515+00', NULL, NULL, '2026-09-26 10:09:58.979515+00', '2026-09-26 10:09:59.726767+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0dd31-5fd4-7ffd-ae4f-a4888e01ddfc', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-34fea47ace259d385ba741bcaf6d023e', 'extract', 'stub', 'http://127.0.0.1:37159/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "7e75e2f51ebbb3a1", "compiler": "extract-v8", "endpoint": "http://127.0.0.1:37159/v1", "json_mode": true, "normalizer": "clean-v2", "predicates": "0cb801b7a0826109", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-26 10:09:55.489616+00', '2026-09-26 10:09:55.495201+00');
INSERT INTO public.projection_generation VALUES ('embed-5b01ef89c6358fee1493caf5d5c8f05f', 'embed', 'stub-embed', 'http://127.0.0.1:37159/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:37159/v1", "max_chunks": 8, "normalizer": "clean-v2", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-26 10:09:55.489616+00', '2026-09-26 10:09:55.499342+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0dd31-5ffa-7b50-bebf-79a0b269b965', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca", "host_logical_id": "05b11192-7267-46aa-8838-b086ee29dc4e"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca", "host_logical_id": "05b11192-7267-46aa-8838-b086ee29dc4e"}]', 0, '{"embed": 23.74, "facts": 0, "vector": 1.48, "lexical": 3.47, "threads": 0, "extractor": "extract-34fea47ace25", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 30.47, "embedding_projection": "embed-5b01ef89c6358f"}', 'fresh', '2026-09-26 10:09:55.675787+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-6027-745e-8809-2c15d83c14a8', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0dd31-6006-703b-a6f7-4fd969993060", "host_logical_id": "ed74e6ad-5304-4066-8c08-9d9bad7afd56"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0dd31-6006-703b-a6f7-4fd969993060", "host_logical_id": "ed74e6ad-5304-4066-8c08-9d9bad7afd56"}]', 0, '{"embed": 15.07, "facts": 0, "vector": 1.94, "lexical": 3.37, "threads": 0, "extractor": "extract-34fea47ace25", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 22.22, "embedding_projection": "embed-5b01ef89c6358f"}', 'fresh', '2026-09-26 10:09:55.729016+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-604d-7ffe-b2ad-418e0c073d3b', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0dd31-6033-7d63-b8d4-f9ce3b235d5d", "host_logical_id": "fc6da17a-2495-489c-94cf-37d92cb51559"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0dd31-6033-7d63-b8d4-f9ce3b235d5d", "host_logical_id": "fc6da17a-2495-489c-94cf-37d92cb51559"}]', 0, '{"embed": 13.51, "facts": 0, "vector": 0.83, "lexical": 2.57, "threads": 0, "extractor": "extract-34fea47ace25", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 17.92, "embedding_projection": "embed-5b01ef89c6358f"}', 'fresh', '2026-09-26 10:09:55.771938+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-6074-71f0-a324-e43abb692ff1', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0dd31-6058-7ecb-ada4-0e9cde103a91", "host_logical_id": "79a0f669-e994-47e5-a58c-27732636c960"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0dd31-5fd2-7a38-9da8-c167328b926c", "host_logical_id": "b8061b51-c576-434a-bda9-78874a305413"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0dd31-5fd0-7722-8440-9875fa916e2a", "host_logical_id": "a61e4bdf-d3f2-4817-afec-3ec788c56c1a"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0dd31-5fd0-7722-8440-9875fa916e2a"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0dd31-5fd2-7a38-9da8-c167328b926c"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0dd31-6058-7ecb-ada4-0e9cde103a91", "host_logical_id": "79a0f669-e994-47e5-a58c-27732636c960"}]', 174, '{"embed": 15.16, "facts": 0, "vector": 1.23, "lexical": 2.54, "threads": 0, "extractor": "extract-34fea47ace25", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 20.24, "embedding_projection": "embed-5b01ef89c6358f"}', 'fresh', '2026-09-26 10:09:55.808145+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-6683-76aa-9188-d33cd7279952', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '01a0dd31-6669-7f0a-ad55-f72b77008c02', 'And the compass?', '[{"rrf": 0.03151, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0dd31-6032-7ac9-a319-a3a98421a215", "host_logical_id": "6195eaaa-9a9d-40a2-9553-eb87a4b5b79c"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0dd31-6664-7d3f-aa65-8451458edc01", "host_logical_id": "7bb0457d-d5ff-4215-91a8-b5d9e434a8ec"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0dd31-5fd0-7722-8440-9875fa916e2a", "host_logical_id": "a61e4bdf-d3f2-4817-afec-3ec788c56c1a"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0dd31-5fce-75fd-bd98-691b4b362c68", "host_logical_id": "ca230e03-fe28-4be7-ba01-93bba6012861"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0dd31-6007-76ca-89f4-8d640dac0cf4", "host_logical_id": "497a21d0-18ef-4cb3-b1f3-26396f379cea"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0dd31-5fce-75fd-bd98-691b4b362c68"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0dd31-5fd0-7722-8440-9875fa916e2a"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0dd31-6007-76ca-89f4-8d640dac0cf4"}, {"turn": 9, "score": 0.03151, "revision_id": "01a0dd31-6032-7ac9-a319-a3a98421a215"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0dd31-6664-7d3f-aa65-8451458edc01", "host_logical_id": "7bb0457d-d5ff-4215-91a8-b5d9e434a8ec"}]', 223, '{"embed": 14.1, "facts": 0, "vector": 1.16, "lexical": 3.28, "threads": 0, "extractor": "extract-34fea47ace25", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 20.14, "embedding_projection": "embed-5b01ef89c6358f"}', 'fresh', '2026-09-26 10:09:57.359235+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-66a7-7a6e-9faa-2984562e43a1', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '01a0dd31-6669-7f0a-ad55-f72b77008c02', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0dd31-6032-7ac9-a319-a3a98421a215", "host_logical_id": "6195eaaa-9a9d-40a2-9553-eb87a4b5b79c"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0dd31-6664-7d3f-aa65-8451458edc01", "host_logical_id": "7bb0457d-d5ff-4215-91a8-b5d9e434a8ec"}, {"rrf": 0.01639, "sim": 0.5799, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0dd31-6005-7b82-89f6-13419ba61afa", "host_logical_id": "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2"}, {"rrf": 0.01613, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0dd31-6034-7f18-92da-907912a645e5", "host_logical_id": "c194d9aa-7c70-4a6e-aea0-82095d57272f"}]', '[{"turn": 5, "score": 0.01639, "revision_id": "01a0dd31-6005-7b82-89f6-13419ba61afa"}, {"turn": 9, "score": 0.03002, "revision_id": "01a0dd31-6032-7ac9-a319-a3a98421a215"}, {"turn": 11, "score": 0.01613, "revision_id": "01a0dd31-6034-7f18-92da-907912a645e5"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0dd31-6664-7d3f-aa65-8451458edc01", "host_logical_id": "7bb0457d-d5ff-4215-91a8-b5d9e434a8ec"}]', 200, '{"embed": 12.97, "facts": 0, "vector": 1.17, "lexical": 3.17, "threads": 0, "extractor": "extract-34fea47ace25", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 19.23, "embedding_projection": "embed-5b01ef89c6358f"}', 'fresh', '2026-09-26 10:09:57.396616+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-66cf-7096-b549-c4572f251f7e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0dd31-6006-703b-a6f7-4fd969993060", "host_logical_id": "ed74e6ad-5304-4066-8c08-9d9bad7afd56"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0dd31-66b4-7e2b-87be-d4ae3174eb3e", "host_logical_id": "83714a7e-a494-453c-96bc-2531c4d49f60"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0dd31-6006-703b-a6f7-4fd969993060"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0dd31-66b4-7e2b-87be-d4ae3174eb3e", "host_logical_id": "83714a7e-a494-453c-96bc-2531c4d49f60"}]', 138, '{"embed": 14.07, "facts": 0, "vector": 1.0, "lexical": 2.46, "threads": 0, "extractor": "extract-34fea47ace25", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 19.01, "embedding_projection": "embed-5b01ef89c6358f"}', 'fresh', '2026-09-26 10:09:57.436138+00');
INSERT INTO public.retrieval_trace VALUES ('01a0dd31-6ce9-76a0-93f1-8877447d3819', '01a0dd31-6cba-78f6-8285-1b619853d965', '01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0dd31-6cc6-71c1-9d37-dd382e94556e", "host_logical_id": "f2f07485-7cbc-41df-82f0-871d5ccba645"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0dd31-6cc7-791c-afc3-2e42be82debb", "host_logical_id": "4f78985e-bbaf-416d-81a4-4e29303bcfb4"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0dd31-6cc6-71c1-9d37-dd382e94556e"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0dd31-6cc7-791c-afc3-2e42be82debb"}]', '[]', 164, '{"embed": 17.24, "facts": 0, "vector": 1.39, "lexical": 3.21, "threads": 0, "extractor": "extract-34fea47ace25", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 23.41, "embedding_projection": "embed-5b01ef89c6358f"}', 'fresh', '2026-09-26 10:09:58.993825+00');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0dd31-6058-7ecb-ada4-0e9cde103a91', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6034-7f18-92da-907912a645e5', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6033-7d63-b8d4-f9ce3b235d5d', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6032-7ac9-a319-a3a98421a215', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6031-7c06-913a-452c0929ea84', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6007-76ca-89f4-8d640dac0cf4', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6006-703b-a6f7-4fd969993060', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6005-7b82-89f6-13419ba61afa', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6004-7b5f-a4b2-3069de3c0776', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-5fd2-7a38-9da8-c167328b926c', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-5fd0-7722-8440-9875fa916e2a', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-5fce-75fd-bd98-691b4b362c68', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-66b4-7e2b-87be-d4ae3174eb3e', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6664-7d3f-aa65-8451458edc01', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6664-721d-b5e0-389f15a8d9e5', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6663-7945-a8a1-95b7ad76ecb5', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6cca-74ae-906e-4e4eb1922436', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6cc8-7503-affe-a74c60ef3892', 'stub-embed', 0, 8, 0, 52, '[0.372576,-0.424413,0.651199,-0.0356377,0.346658,-0.31426,0.016199,-0.191148]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6cc8-7e74-96aa-0e26e9e627a9', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6cc7-791c-afc3-2e42be82debb', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6cc6-71c1-9d37-dd382e94556e', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6cc5-7caf-bcee-6cff921cdd71', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');
INSERT INTO public.revision_embedding VALUES ('01a0dd31-6cc4-776a-9bca-4bf13c7371e5', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-5b01ef89c6358fee1493caf5d5c8f05f');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0dd31-5fce-75fd-bd98-691b4b362c68', 'clean-v2', 'We should rest somewhere safe.', 30, 30, '2026-09-26 10:09:55.660365+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-5fd0-7722-8440-9875fa916e2a', 'clean-v2', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-26 10:09:55.660365+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca', 'clean-v2', 'Is Rin with you?', 16, 16, '2026-09-26 10:09:55.660365+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-5fd2-7a38-9da8-c167328b926c', 'clean-v2', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-26 10:09:55.660365+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6004-7b5f-a4b2-3069de3c0776', 'clean-v2', 'What did Mina say before she left?', 34, 34, '2026-09-26 10:09:55.715697+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6005-7b82-89f6-13419ba61afa', 'clean-v2', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-26 10:09:55.715697+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6006-703b-a6f7-4fd969993060', 'clean-v2', 'Let''s check the market.', 23, 23, '2026-09-26 10:09:55.715697+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6007-76ca-89f4-8d640dac0cf4', 'clean-v2', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-26 10:09:55.715697+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6031-7c06-913a-452c0929ea84', 'clean-v2', 'Any news from the harbor?', 25, 25, '2026-09-26 10:09:55.760394+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6032-7ac9-a319-a3a98421a215', 'clean-v2', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-26 10:09:55.760394+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6033-7d63-b8d4-f9ce3b235d5d', 'clean-v2', 'Where do we meet tonight?', 25, 25, '2026-09-26 10:09:55.760394+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6034-7f18-92da-907912a645e5', 'clean-v2', 'Mina moved to the bell tower.', 29, 29, '2026-09-26 10:09:55.760394+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6058-7ecb-ada4-0e9cde103a91', 'clean-v2', 'Where is Mina now?', 18, 18, '2026-09-26 10:09:55.799196+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6663-7945-a8a1-95b7ad76ecb5', 'clean-v2', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-26 10:09:57.346463+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6664-721d-b5e0-389f15a8d9e5', 'clean-v2', 'Mina keeps the brass key close.', 31, 31, '2026-09-26 10:09:57.346463+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6664-7d3f-aa65-8451458edc01', 'clean-v2', 'And the compass?', 16, 16, '2026-09-26 10:09:57.346463+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-668c-7306-9dc2-e539fe4a6883', 'clean-v2', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-26 10:09:57.38789+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-66b2-70f6-a9ac-264a8fc421b0', 'clean-v2', 'Any news from the harbor?', 25, 25, '2026-09-26 10:09:57.425809+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9', 'clean-v2', 'Rin has the silver compass.', 27, 27, '2026-09-26 10:09:57.425809+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-66b4-7e2b-87be-d4ae3174eb3e', 'clean-v2', 'Let''s go.', 9, 9, '2026-09-26 10:09:57.425809+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6cc4-776a-9bca-4bf13c7371e5', 'clean-v2', 'We should rest somewhere safe.', 30, 30, '2026-09-26 10:09:58.979515+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6cc5-7caf-bcee-6cff921cdd71', 'clean-v2', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-26 10:09:58.979515+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6cc6-71c1-9d37-dd382e94556e', 'clean-v2', 'Is Rin with you?', 16, 16, '2026-09-26 10:09:58.979515+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6cc7-791c-afc3-2e42be82debb', 'clean-v2', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-26 10:09:58.979515+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6cc8-7e74-96aa-0e26e9e627a9', 'clean-v2', 'What did Mina say before she left?', 34, 34, '2026-09-26 10:09:58.979515+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6cc8-7503-affe-a74c60ef3892', 'clean-v2', 'Mina promised Yuuma to return before the bell rings.', 52, 52, '2026-09-26 10:09:58.979515+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6cc9-72e2-be57-75cc10f64121', 'clean-v2', '{{specialcomment::branchedfrom::fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a::Harbor route::f74600fd-8da6-4c58-ae9b-1e2e3300d9d2::}}', 124, 124, '2026-09-26 10:09:58.979515+00');
INSERT INTO public.revision_text VALUES ('01a0dd31-6cca-74ae-906e-4e4eb1922436', 'clean-v2', 'Rin moved to the market.', 24, 24, '2026-09-26 10:09:58.979515+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-26 10:09:54.735519+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-26 10:09:54.821552+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-26 10:09:54.838226+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-26 10:09:54.880591+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-26 10:09:54.900864+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-26 10:09:54.910032+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-26 10:09:54.911764+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-26 10:09:54.921025+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-26 10:09:54.941363+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-26 10:09:54.94345+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-26 10:09:54.94493+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-26 10:09:54.954403+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-26 10:09:54.980692+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-26 10:09:54.99741+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-26 10:09:54.99982+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-26 10:09:55.011771+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-26 10:09:55.013587+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-26 10:09:55.015264+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0dd31-5fcd-745d-a6f1-c0896bce301a', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'ca230e03-fe28-4be7-ba01-93bba6012861', 'message', '2026-09-26 10:09:55.660365+00');
INSERT INTO public.source_object VALUES ('01a0dd31-5fd0-7cd7-9130-faa498795a82', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'a61e4bdf-d3f2-4817-afec-3ec788c56c1a', 'message', '2026-09-26 10:09:55.660365+00');
INSERT INTO public.source_object VALUES ('01a0dd31-5fd1-73b4-8bdd-e02729f1c315', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '05b11192-7267-46aa-8838-b086ee29dc4e', 'message', '2026-09-26 10:09:55.660365+00');
INSERT INTO public.source_object VALUES ('01a0dd31-5fd2-72f5-b1de-2ee467383c49', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'b8061b51-c576-434a-bda9-78874a305413', 'message', '2026-09-26 10:09:55.660365+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6004-72ff-b0f3-446dc18e65a9', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '0b449ecb-456d-4159-9ae3-312e7a7b7d8c', 'message', '2026-09-26 10:09:55.715697+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6005-78be-ae03-78865b01ac81', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'f74600fd-8da6-4c58-ae9b-1e2e3300d9d2', 'message', '2026-09-26 10:09:55.715697+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6006-7466-8fcf-35f1d7c101d2', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'ed74e6ad-5304-4066-8c08-9d9bad7afd56', 'message', '2026-09-26 10:09:55.715697+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6007-7e17-8a31-a48fb7eb9abf', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '497a21d0-18ef-4cb3-b1f3-26396f379cea', 'message', '2026-09-26 10:09:55.715697+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6030-7f44-844f-1ee5c9dde211', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'f30bc75d-44af-4002-b14b-eff8b7b57568', 'message', '2026-09-26 10:09:55.760394+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6031-7a6a-ba53-1049d33825a0', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '6195eaaa-9a9d-40a2-9553-eb87a4b5b79c', 'message', '2026-09-26 10:09:55.760394+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6033-7e76-836d-88b91c81f166', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'fc6da17a-2495-489c-94cf-37d92cb51559', 'message', '2026-09-26 10:09:55.760394+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6033-76e4-bb2b-82af35d6b5e9', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'c194d9aa-7c70-4a6e-aea0-82095d57272f', 'message', '2026-09-26 10:09:55.760394+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6057-71a9-9b7e-625a1f22772e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '79a0f669-e994-47e5-a58c-27732636c960', 'message', '2026-09-26 10:09:55.799196+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6664-7edb-b38e-1d23cc84810e', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '52d52349-a893-470a-8e19-67b31f658ff7', 'message', '2026-09-26 10:09:57.346463+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6664-7e3c-9cc4-2b79501eb417', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '7bb0457d-d5ff-4215-91a8-b5d9e434a8ec', 'message', '2026-09-26 10:09:57.346463+00');
INSERT INTO public.source_object VALUES ('01a0dd31-668c-77e5-9bd9-1000657d2d4f', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', 'ed95e553-b9cd-4910-9514-d3c1225c54a1', 'message', '2026-09-26 10:09:57.38789+00');
INSERT INTO public.source_object VALUES ('01a0dd31-66b3-72f5-b5fd-f3fa3af619ad', '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '83714a7e-a494-453c-96bc-2531c4d49f60', 'message', '2026-09-26 10:09:57.425809+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6cc4-7731-b9c9-c7902faa9bb7', '01a0dd31-6cba-78f6-8285-1b619853d965', 'd28f72fe-2480-42af-87e2-fe0ced529473', 'message', '2026-09-26 10:09:58.979515+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6cc5-7da9-92f0-b31c47693ad4', '01a0dd31-6cba-78f6-8285-1b619853d965', '7f11be62-d170-449c-a429-1cc2ff3d6dc0', 'message', '2026-09-26 10:09:58.979515+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6cc6-7918-8ace-29184b2b1ebe', '01a0dd31-6cba-78f6-8285-1b619853d965', 'f2f07485-7cbc-41df-82f0-871d5ccba645', 'message', '2026-09-26 10:09:58.979515+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6cc7-7ca5-8575-fbc2f1e45aff', '01a0dd31-6cba-78f6-8285-1b619853d965', '4f78985e-bbaf-416d-81a4-4e29303bcfb4', 'message', '2026-09-26 10:09:58.979515+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6cc7-7dc5-83c8-a626eb682af7', '01a0dd31-6cba-78f6-8285-1b619853d965', '1746ecfe-6328-4b1c-aa58-1b8cf3448d8b', 'message', '2026-09-26 10:09:58.979515+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6cc8-783d-b76e-6448145fa483', '01a0dd31-6cba-78f6-8285-1b619853d965', '5094bbfe-c238-45a4-ae56-f763add012c3', 'message', '2026-09-26 10:09:58.979515+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6cc9-790c-9787-916a738b1949', '01a0dd31-6cba-78f6-8285-1b619853d965', 'c565e305-e7e3-4d7d-b12b-7b6e473ae971', 'message', '2026-09-26 10:09:58.979515+00');
INSERT INTO public.source_object VALUES ('01a0dd31-6cc9-767a-a5f9-d280ca9e7193', '01a0dd31-6cba-78f6-8285-1b619853d965', '4a4098ec-8e73-4b54-a59f-403048ca9106', 'message', '2026-09-26 10:09:58.979515+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0dd31-5fce-75fd-bd98-691b4b362c68', '01a0dd31-5fcd-745d-a6f1-c0896bce301a', 'acc4463065e74da1e1df7bbf7af6a6773c044058606d2bb554f7b40fe810ecdc', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "ca230e03-fe28-4be7-ba01-93bba6012861", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:55.660365+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-5fd1-7d5c-8b14-f5946b8f7aca', '01a0dd31-5fd1-73b4-8bdd-e02729f1c315', 'c9e4f099193e89a11af985f27b08544ea664867a91041d45193c3fada06e423d', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "05b11192-7267-46aa-8838-b086ee29dc4e", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:55.660365+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-5fd0-7722-8440-9875fa916e2a', '01a0dd31-5fd0-7cd7-9130-faa498795a82', '0d739e5dbe2d14807ac44cbced79ef97f13340998113ac24e7467a9845a9672d', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "a61e4bdf-d3f2-4817-afec-3ec788c56c1a", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a61e4bdf-d3f2-4817-afec-3ec788c56c1a", "specialComments": []}', '2026-09-26 10:09:55.660365+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6004-7b5f-a4b2-3069de3c0776', '01a0dd31-6004-72ff-b0f3-446dc18e65a9', '95a44e926986fd6b2c1a358c24cbbbac66b3bd65553d3d27881fc36558cbf8ce', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "0b449ecb-456d-4159-9ae3-312e7a7b7d8c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:55.715697+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6006-703b-a6f7-4fd969993060', '01a0dd31-6006-7466-8fcf-35f1d7c101d2', 'fe15fdbb3e9cfe72b6cc41221cf83060c115a494f7a4134bd58f1da72fc40c73', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "ed74e6ad-5304-4066-8c08-9d9bad7afd56", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:55.715697+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6005-7b82-89f6-13419ba61afa', '01a0dd31-6005-78be-ae03-78865b01ac81', 'b530323378cf45ed3a933c8964250e0b698978569219a9f80ced22ad15059409', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "specialComments": []}', '2026-09-26 10:09:55.715697+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6033-7d63-b8d4-f9ce3b235d5d', '01a0dd31-6033-7e76-836d-88b91c81f166', '8c40513a9b8ffbcdde65a432ae2d9bd46be6a8f1a02c4c7566efdc894ddb82dd', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "fc6da17a-2495-489c-94cf-37d92cb51559", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:55.760394+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6007-76ca-89f4-8d640dac0cf4', '01a0dd31-6007-7e17-8a31-a48fb7eb9abf', 'f19728ccc60af24be42b521c6da334f47fcecd74c8119bc097e152e3a91e84ac', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "497a21d0-18ef-4cb3-b1f3-26396f379cea", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "497a21d0-18ef-4cb3-b1f3-26396f379cea", "specialComments": []}', '2026-09-26 10:09:55.715697+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6032-7ac9-a319-a3a98421a215', '01a0dd31-6031-7a6a-ba53-1049d33825a0', '90a9037d7ae1bf5138c13535c42a4280c2278e10dedaad9ee4c0bfd3c5e41bb3', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", "specialComments": []}', '2026-09-26 10:09:55.760394+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6058-7ecb-ada4-0e9cde103a91', '01a0dd31-6057-71a9-9b7e-625a1f22772e', '95871755373e3ecd13131bdf053af6f0e1820746afca439f21078aab31be2bad', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "79a0f669-e994-47e5-a58c-27732636c960", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:55.799196+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6034-7f18-92da-907912a645e5', '01a0dd31-6033-76e4-bb2b-82af35d6b5e9', 'c7572f9f27ce3fa1a0a187ca421fc767d888843601a94bd5396879a1adb26445', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "c194d9aa-7c70-4a6e-aea0-82095d57272f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "c194d9aa-7c70-4a6e-aea0-82095d57272f", "specialComments": []}', '2026-09-26 10:09:55.760394+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6664-7d3f-aa65-8451458edc01', '01a0dd31-6664-7e3c-9cc4-2b79501eb417', 'f769ff0e29b3e7755e82ebccc38b32817ad4836ed7a9caa0a845e0a7e0344f19', 'And the compass?', '{"name": null, "role": "user", "chatId": "7bb0457d-d5ff-4215-91a8-b5d9e434a8ec", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:57.346463+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6664-721d-b5e0-389f15a8d9e5', '01a0dd31-6664-7edb-b38e-1d23cc84810e', '2faeeaf8bbff6fdd6fc848a7e5d72c6b4193a03531cd27146b2d52a8fbb7a096', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "52d52349-a893-470a-8e19-67b31f658ff7", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "52d52349-a893-470a-8e19-67b31f658ff7", "specialComments": []}', '2026-09-26 10:09:57.346463+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-5fd2-7a38-9da8-c167328b926c', '01a0dd31-5fd2-72f5-b1de-2ee467383c49', 'aa5b436eb87dca5afb8a913f9ee7f5f09b2a683d0f058febc3d546c41ecc8c32', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "b8061b51-c576-434a-bda9-78874a305413", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b8061b51-c576-434a-bda9-78874a305413", "specialComments": []}', '2026-09-26 10:09:55.660365+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-668c-7306-9dc2-e539fe4a6883', '01a0dd31-668c-77e5-9bd9-1000657d2d4f', 'a7dd4e0a8a8c6667b8b5c6b3545f9941d76a95119bf7bf56e8ef6e3e2671e89d', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "ed95e553-b9cd-4910-9514-d3c1225c54a1", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "ed95e553-b9cd-4910-9514-d3c1225c54a1", "specialComments": []}', '2026-09-26 10:09:57.38789+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6031-7c06-913a-452c0929ea84', '01a0dd31-6030-7f44-844f-1ee5c9dde211', '61ec30500664168be0d03afb3929ce5208f43eb4cf8dcacb4e92e9c1a0f41dea', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "f30bc75d-44af-4002-b14b-eff8b7b57568", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:55.760394+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6cc4-776a-9bca-4bf13c7371e5', '01a0dd31-6cc4-7731-b9c9-c7902faa9bb7', '737f81a173a6c874aced55d7c1c2c1b79e59b8980e294a1a01b9c973ae2038ce', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "d28f72fe-2480-42af-87e2-fe0ced529473", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:58.979515+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6663-7945-a8a1-95b7ad76ecb5', '01a0dd31-5fd2-72f5-b1de-2ee467383c49', 'e3622f0f5ea1734a684f6e3f1775d94fd006d99aaf78cdfa788ed9624ff220e6', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "b8061b51-c576-434a-bda9-78874a305413", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b8061b51-c576-434a-bda9-78874a305413", "specialComments": []}', '2026-09-26 10:09:57.346463+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-66b2-70f6-a9ac-264a8fc421b0', '01a0dd31-6030-7f44-844f-1ee5c9dde211', '3016fde15437528b93249fbd96bde73ecf196bd37706966129df9d518ed13162', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "f30bc75d-44af-4002-b14b-eff8b7b57568", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:57.425809+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-66b4-7e2b-87be-d4ae3174eb3e', '01a0dd31-66b3-72f5-b5fd-f3fa3af619ad', 'f59b9a6078e102ebfa833efcfb7278bd8a43c68efa8e4a03bcd6706febe19b49', 'Let''s go.', '{"name": null, "role": "user", "chatId": "83714a7e-a494-453c-96bc-2531c4d49f60", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:57.425809+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-66b3-7b7b-9c5e-8a46798a2cc9', '01a0dd31-668c-77e5-9bd9-1000657d2d4f', '638c8c0e712b06b7b6dcfc5cc792ad07d74f740266278d6a947b61039519dab4', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "ed95e553-b9cd-4910-9514-d3c1225c54a1", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "ed95e553-b9cd-4910-9514-d3c1225c54a1", "specialComments": []}', '2026-09-26 10:09:57.425809+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6cc6-71c1-9d37-dd382e94556e', '01a0dd31-6cc6-7918-8ace-29184b2b1ebe', 'f3d91c54730b31eca7e123ce34397b0f0187d348a6bbad6a824c7e9bcff5ddc3', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "f2f07485-7cbc-41df-82f0-871d5ccba645", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:58.979515+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6cc8-7e74-96aa-0e26e9e627a9', '01a0dd31-6cc7-7dc5-83c8-a626eb682af7', '01e2b4743458af5279f0510ffb2a2ab59de68efbae433eb71e3dc1162cd5015d', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "1746ecfe-6328-4b1c-aa58-1b8cf3448d8b", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:58.979515+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6cc9-72e2-be57-75cc10f64121', '01a0dd31-6cc9-790c-9787-916a738b1949', '013b27337c81119eb17e9affa35ac972d3b983a4f9e064866da0fbbd379fedcc', '{{specialcomment::branchedfrom::fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a::Harbor route::f74600fd-8da6-4c58-ae9b-1e2e3300d9d2::}}', '{"name": null, "role": "char", "chatId": "c565e305-e7e3-4d7d-b12b-7b6e473ae971", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::fc5a921a-9f5b-4eb9-a95e-35c7a08b2b7a::Harbor route::f74600fd-8da6-4c58-ae9b-1e2e3300d9d2::}}"]}', '2026-09-26 10:09:58.979515+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6cca-74ae-906e-4e4eb1922436', '01a0dd31-6cc9-767a-a5f9-d280ca9e7193', 'ea140a645d8edb44add8057dc85db5d68be8eaaf2c3aaa50489458571daef09c', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "4a4098ec-8e73-4b54-a59f-403048ca9106", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-26 10:09:58.979515+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6cc7-791c-afc3-2e42be82debb', '01a0dd31-6cc7-7ca5-8575-fbc2f1e45aff', '8236b1cd2cf13940345d1c953e6bbd1d2a5a011c335c7ec724956f3cbcd705d5', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "4f78985e-bbaf-416d-81a4-4e29303bcfb4", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b8061b51-c576-434a-bda9-78874a305413", "specialComments": []}', '2026-09-26 10:09:58.979515+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6cc8-7503-affe-a74c60ef3892', '01a0dd31-6cc8-783d-b76e-6448145fa483', '3224b9e9499f6841ef7f07a926a9205be69f4f43bc7587fadc1a5ac744af6d9b', 'Mina promised Yuuma to return before the bell rings.', '{"name": null, "role": "char", "chatId": "5094bbfe-c238-45a4-ae56-f763add012c3", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "specialComments": []}', '2026-09-26 10:09:58.979515+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0dd31-6cc5-7caf-bcee-6cff921cdd71', '01a0dd31-6cc5-7da9-92f0-b31c47693ad4', '3c0c3ed65e595da9deae0d4647791efcbbf4d319b871310bbb69b944dc063451', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "7f11be62-d170-449c-a429-1cc2ff3d6dc0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "a61e4bdf-d3f2-4817-afec-3ec788c56c1a", "specialComments": []}', '2026-09-26 10:09:58.979515+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4', '[{"op": "insert", "after": ["b8061b51-c576-434a-bda9-78874a305413", "aa5b436eb87dca5afb8a913f9ee7f5f09b2a683d0f058febc3d546c41ecc8c32"], "member": ["0b449ecb-456d-4159-9ae3-312e7a7b7d8c", "95a44e926986fd6b2c1a358c24cbbbac66b3bd65553d3d27881fc36558cbf8ce"]}, {"op": "insert", "after": ["0b449ecb-456d-4159-9ae3-312e7a7b7d8c", "95a44e926986fd6b2c1a358c24cbbbac66b3bd65553d3d27881fc36558cbf8ce"], "member": ["f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "b530323378cf45ed3a933c8964250e0b698978569219a9f80ced22ad15059409"]}, {"op": "insert", "after": ["f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "b530323378cf45ed3a933c8964250e0b698978569219a9f80ced22ad15059409"], "member": ["ed74e6ad-5304-4066-8c08-9d9bad7afd56", "fe15fdbb3e9cfe72b6cc41221cf83060c115a494f7a4134bd58f1da72fc40c73"]}, {"op": "insert", "after": ["ed74e6ad-5304-4066-8c08-9d9bad7afd56", "fe15fdbb3e9cfe72b6cc41221cf83060c115a494f7a4134bd58f1da72fc40c73"], "member": ["497a21d0-18ef-4cb3-b1f3-26396f379cea", "f19728ccc60af24be42b521c6da334f47fcecd74c8119bc097e152e3a91e84ac"]}]', '[{"new": ["0b449ecb-456d-4159-9ae3-312e7a7b7d8c", "95a44e926986fd6b2c1a358c24cbbbac66b3bd65553d3d27881fc36558cbf8ce"], "old": null, "kind": "append", "position": 4, "host_logical_id": "0b449ecb-456d-4159-9ae3-312e7a7b7d8c"}, {"new": ["f74600fd-8da6-4c58-ae9b-1e2e3300d9d2", "b530323378cf45ed3a933c8964250e0b698978569219a9f80ced22ad15059409"], "old": null, "kind": "append", "position": 5, "host_logical_id": "f74600fd-8da6-4c58-ae9b-1e2e3300d9d2"}, {"new": ["ed74e6ad-5304-4066-8c08-9d9bad7afd56", "fe15fdbb3e9cfe72b6cc41221cf83060c115a494f7a4134bd58f1da72fc40c73"], "old": null, "kind": "append", "position": 6, "host_logical_id": "ed74e6ad-5304-4066-8c08-9d9bad7afd56"}, {"new": ["497a21d0-18ef-4cb3-b1f3-26396f379cea", "f19728ccc60af24be42b521c6da334f47fcecd74c8119bc097e152e3a91e84ac"], "old": null, "kind": "append", "position": 7, "host_logical_id": "497a21d0-18ef-4cb3-b1f3-26396f379cea"}]', '01a0dd31-600a-73ac-b6d3-d2503fb99564', '2026-09-26 10:09:55.715697+00');
INSERT INTO public.worldline_append VALUES (2, '01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4', '[{"op": "insert", "after": ["497a21d0-18ef-4cb3-b1f3-26396f379cea", "f19728ccc60af24be42b521c6da334f47fcecd74c8119bc097e152e3a91e84ac"], "member": ["f30bc75d-44af-4002-b14b-eff8b7b57568", "61ec30500664168be0d03afb3929ce5208f43eb4cf8dcacb4e92e9c1a0f41dea"]}, {"op": "insert", "after": ["f30bc75d-44af-4002-b14b-eff8b7b57568", "61ec30500664168be0d03afb3929ce5208f43eb4cf8dcacb4e92e9c1a0f41dea"], "member": ["6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", "90a9037d7ae1bf5138c13535c42a4280c2278e10dedaad9ee4c0bfd3c5e41bb3"]}, {"op": "insert", "after": ["6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", "90a9037d7ae1bf5138c13535c42a4280c2278e10dedaad9ee4c0bfd3c5e41bb3"], "member": ["fc6da17a-2495-489c-94cf-37d92cb51559", "8c40513a9b8ffbcdde65a432ae2d9bd46be6a8f1a02c4c7566efdc894ddb82dd"]}, {"op": "insert", "after": ["fc6da17a-2495-489c-94cf-37d92cb51559", "8c40513a9b8ffbcdde65a432ae2d9bd46be6a8f1a02c4c7566efdc894ddb82dd"], "member": ["c194d9aa-7c70-4a6e-aea0-82095d57272f", "c7572f9f27ce3fa1a0a187ca421fc767d888843601a94bd5396879a1adb26445"]}]', '[{"new": ["f30bc75d-44af-4002-b14b-eff8b7b57568", "61ec30500664168be0d03afb3929ce5208f43eb4cf8dcacb4e92e9c1a0f41dea"], "old": null, "kind": "append", "position": 8, "host_logical_id": "f30bc75d-44af-4002-b14b-eff8b7b57568"}, {"new": ["6195eaaa-9a9d-40a2-9553-eb87a4b5b79c", "90a9037d7ae1bf5138c13535c42a4280c2278e10dedaad9ee4c0bfd3c5e41bb3"], "old": null, "kind": "append", "position": 9, "host_logical_id": "6195eaaa-9a9d-40a2-9553-eb87a4b5b79c"}, {"new": ["fc6da17a-2495-489c-94cf-37d92cb51559", "8c40513a9b8ffbcdde65a432ae2d9bd46be6a8f1a02c4c7566efdc894ddb82dd"], "old": null, "kind": "append", "position": 10, "host_logical_id": "fc6da17a-2495-489c-94cf-37d92cb51559"}, {"new": ["c194d9aa-7c70-4a6e-aea0-82095d57272f", "c7572f9f27ce3fa1a0a187ca421fc767d888843601a94bd5396879a1adb26445"], "old": null, "kind": "append", "position": 11, "host_logical_id": "c194d9aa-7c70-4a6e-aea0-82095d57272f"}]', '01a0dd31-6036-70fd-9e99-8ae364541fdf', '2026-09-26 10:09:55.760394+00');
INSERT INTO public.worldline_append VALUES (3, '01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4', '[{"op": "insert", "after": ["c194d9aa-7c70-4a6e-aea0-82095d57272f", "c7572f9f27ce3fa1a0a187ca421fc767d888843601a94bd5396879a1adb26445"], "member": ["79a0f669-e994-47e5-a58c-27732636c960", "95871755373e3ecd13131bdf053af6f0e1820746afca439f21078aab31be2bad"]}]', '[{"new": ["79a0f669-e994-47e5-a58c-27732636c960", "95871755373e3ecd13131bdf053af6f0e1820746afca439f21078aab31be2bad"], "old": null, "kind": "append", "position": 12, "host_logical_id": "79a0f669-e994-47e5-a58c-27732636c960"}]', '01a0dd31-605b-7ace-abf4-2637d09a3ab3', '2026-09-26 10:09:55.799196+00');
INSERT INTO public.worldline_append VALUES (4, '01a0dd31-6669-7f0a-ad55-f72b77008c02', '[{"op": "insert", "after": ["7bb0457d-d5ff-4215-91a8-b5d9e434a8ec", "f769ff0e29b3e7755e82ebccc38b32817ad4836ed7a9caa0a845e0a7e0344f19"], "member": ["ed95e553-b9cd-4910-9514-d3c1225c54a1", "a7dd4e0a8a8c6667b8b5c6b3545f9941d76a95119bf7bf56e8ef6e3e2671e89d"]}]', '[{"new": ["ed95e553-b9cd-4910-9514-d3c1225c54a1", "a7dd4e0a8a8c6667b8b5c6b3545f9941d76a95119bf7bf56e8ef6e3e2671e89d"], "old": null, "kind": "append", "position": 15, "host_logical_id": "ed95e553-b9cd-4910-9514-d3c1225c54a1"}]', '01a0dd31-668f-721f-926a-418b58f8004d', '2026-09-26 10:09:57.38789+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4', 1, '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{}', 'import', '172900f9fb7d34d3f9cf486aaf047fff89cada916fca1ef812af61270a38ddd7', '{"ops": [{"op": "set", "members": [["ca230e03-fe28-4be7-ba01-93bba6012861", "acc4463065e74da1e1df7bbf7af6a6773c044058606d2bb554f7b40fe810ecdc"], ["a61e4bdf-d3f2-4817-afec-3ec788c56c1a", "0d739e5dbe2d14807ac44cbced79ef97f13340998113ac24e7467a9845a9672d"], ["05b11192-7267-46aa-8838-b086ee29dc4e", "c9e4f099193e89a11af985f27b08544ea664867a91041d45193c3fada06e423d"], ["b8061b51-c576-434a-bda9-78874a305413", "aa5b436eb87dca5afb8a913f9ee7f5f09b2a683d0f058febc3d546c41ecc8c32"]]}], "changes": [{"new": ["ca230e03-fe28-4be7-ba01-93bba6012861", "acc4463065e74da1e1df7bbf7af6a6773c044058606d2bb554f7b40fe810ecdc"], "old": null, "kind": "append", "position": 0, "host_logical_id": "ca230e03-fe28-4be7-ba01-93bba6012861"}, {"new": ["a61e4bdf-d3f2-4817-afec-3ec788c56c1a", "0d739e5dbe2d14807ac44cbced79ef97f13340998113ac24e7467a9845a9672d"], "old": null, "kind": "append", "position": 1, "host_logical_id": "a61e4bdf-d3f2-4817-afec-3ec788c56c1a"}, {"new": ["05b11192-7267-46aa-8838-b086ee29dc4e", "c9e4f099193e89a11af985f27b08544ea664867a91041d45193c3fada06e423d"], "old": null, "kind": "append", "position": 2, "host_logical_id": "05b11192-7267-46aa-8838-b086ee29dc4e"}, {"new": ["b8061b51-c576-434a-bda9-78874a305413", "aa5b436eb87dca5afb8a913f9ee7f5f09b2a683d0f058febc3d546c41ecc8c32"], "old": null, "kind": "append", "position": 3, "host_logical_id": "b8061b51-c576-434a-bda9-78874a305413"}]}', '2026-09-26 10:09:55.660365+00', '01a0dd31-5fd4-7ffd-ae4f-a4888e01ddfc');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0dd31-6669-7f0a-ad55-f72b77008c02', 2, '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{01a0dd31-5fd5-7049-90f2-1caa7b7c3ed4}', 'edit', '3fbade8d73df6619ec288339ecb2e4c31902d92e0eab4cd69a0d0cee8910f58f', '{"ops": [{"op": "replace", "to": ["b8061b51-c576-434a-bda9-78874a305413", "e3622f0f5ea1734a684f6e3f1775d94fd006d99aaf78cdfa788ed9624ff220e6"], "from": ["b8061b51-c576-434a-bda9-78874a305413", "aa5b436eb87dca5afb8a913f9ee7f5f09b2a683d0f058febc3d546c41ecc8c32"]}, {"op": "insert", "after": ["79a0f669-e994-47e5-a58c-27732636c960", "95871755373e3ecd13131bdf053af6f0e1820746afca439f21078aab31be2bad"], "member": ["52d52349-a893-470a-8e19-67b31f658ff7", "2faeeaf8bbff6fdd6fc848a7e5d72c6b4193a03531cd27146b2d52a8fbb7a096"]}, {"op": "insert", "after": ["52d52349-a893-470a-8e19-67b31f658ff7", "2faeeaf8bbff6fdd6fc848a7e5d72c6b4193a03531cd27146b2d52a8fbb7a096"], "member": ["7bb0457d-d5ff-4215-91a8-b5d9e434a8ec", "f769ff0e29b3e7755e82ebccc38b32817ad4836ed7a9caa0a845e0a7e0344f19"]}], "changes": [{"new": ["b8061b51-c576-434a-bda9-78874a305413", "e3622f0f5ea1734a684f6e3f1775d94fd006d99aaf78cdfa788ed9624ff220e6"], "old": ["b8061b51-c576-434a-bda9-78874a305413", "aa5b436eb87dca5afb8a913f9ee7f5f09b2a683d0f058febc3d546c41ecc8c32"], "kind": "edit", "position": 3, "host_logical_id": "b8061b51-c576-434a-bda9-78874a305413"}, {"new": ["52d52349-a893-470a-8e19-67b31f658ff7", "2faeeaf8bbff6fdd6fc848a7e5d72c6b4193a03531cd27146b2d52a8fbb7a096"], "old": null, "kind": "append", "position": 13, "host_logical_id": "52d52349-a893-470a-8e19-67b31f658ff7"}, {"new": ["7bb0457d-d5ff-4215-91a8-b5d9e434a8ec", "f769ff0e29b3e7755e82ebccc38b32817ad4836ed7a9caa0a845e0a7e0344f19"], "old": null, "kind": "append", "position": 14, "host_logical_id": "7bb0457d-d5ff-4215-91a8-b5d9e434a8ec"}]}', '2026-09-26 10:09:57.346463+00', '01a0dd31-6667-7ede-930e-47e396c29495');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0dd31-66b6-7277-b8ac-e44e3ee9003f', 3, '01a0dd31-5fc6-72f2-b8d1-53ebca8adf0c', '{01a0dd31-6669-7f0a-ad55-f72b77008c02}', 'reconciliation', 'fb6b86501600c4240c5b2d90ebfc4d2b942f390072ffcbc67b4c1c890b40dd72', '{"ops": [{"op": "replace", "to": ["f30bc75d-44af-4002-b14b-eff8b7b57568", "3016fde15437528b93249fbd96bde73ecf196bd37706966129df9d518ed13162"], "from": ["f30bc75d-44af-4002-b14b-eff8b7b57568", "61ec30500664168be0d03afb3929ce5208f43eb4cf8dcacb4e92e9c1a0f41dea"]}, {"op": "replace", "to": ["ed95e553-b9cd-4910-9514-d3c1225c54a1", "638c8c0e712b06b7b6dcfc5cc792ad07d74f740266278d6a947b61039519dab4"], "from": ["ed95e553-b9cd-4910-9514-d3c1225c54a1", "a7dd4e0a8a8c6667b8b5c6b3545f9941d76a95119bf7bf56e8ef6e3e2671e89d"]}, {"op": "insert", "after": ["ed95e553-b9cd-4910-9514-d3c1225c54a1", "638c8c0e712b06b7b6dcfc5cc792ad07d74f740266278d6a947b61039519dab4"], "member": ["83714a7e-a494-453c-96bc-2531c4d49f60", "f59b9a6078e102ebfa833efcfb7278bd8a43c68efa8e4a03bcd6706febe19b49"]}], "changes": [{"new": ["f30bc75d-44af-4002-b14b-eff8b7b57568", "3016fde15437528b93249fbd96bde73ecf196bd37706966129df9d518ed13162"], "old": ["f30bc75d-44af-4002-b14b-eff8b7b57568", "61ec30500664168be0d03afb3929ce5208f43eb4cf8dcacb4e92e9c1a0f41dea"], "kind": "disable", "position": 8, "host_logical_id": "f30bc75d-44af-4002-b14b-eff8b7b57568"}, {"new": ["ed95e553-b9cd-4910-9514-d3c1225c54a1", "638c8c0e712b06b7b6dcfc5cc792ad07d74f740266278d6a947b61039519dab4"], "old": ["ed95e553-b9cd-4910-9514-d3c1225c54a1", "a7dd4e0a8a8c6667b8b5c6b3545f9941d76a95119bf7bf56e8ef6e3e2671e89d"], "kind": "swipe", "position": 15, "host_logical_id": "ed95e553-b9cd-4910-9514-d3c1225c54a1"}, {"new": ["83714a7e-a494-453c-96bc-2531c4d49f60", "f59b9a6078e102ebfa833efcfb7278bd8a43c68efa8e4a03bcd6706febe19b49"], "old": null, "kind": "append", "position": 16, "host_logical_id": "83714a7e-a494-453c-96bc-2531c4d49f60"}]}', '2026-09-26 10:09:57.425809+00', '01a0dd31-66b5-79dd-ab29-84065c48705d');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0dd31-6ccc-7958-ac7b-d9eb1cf08d87', 4, '01a0dd31-6cba-78f6-8285-1b619853d965', '{}', 'branch', '77e6df65c43735dbcde5158a5e780510fc716fee20b691adfce876459690df82', '{"ops": [{"op": "set", "members": [["d28f72fe-2480-42af-87e2-fe0ced529473", "737f81a173a6c874aced55d7c1c2c1b79e59b8980e294a1a01b9c973ae2038ce"], ["7f11be62-d170-449c-a429-1cc2ff3d6dc0", "3c0c3ed65e595da9deae0d4647791efcbbf4d319b871310bbb69b944dc063451"], ["f2f07485-7cbc-41df-82f0-871d5ccba645", "f3d91c54730b31eca7e123ce34397b0f0187d348a6bbad6a824c7e9bcff5ddc3"], ["4f78985e-bbaf-416d-81a4-4e29303bcfb4", "8236b1cd2cf13940345d1c953e6bbd1d2a5a011c335c7ec724956f3cbcd705d5"], ["1746ecfe-6328-4b1c-aa58-1b8cf3448d8b", "01e2b4743458af5279f0510ffb2a2ab59de68efbae433eb71e3dc1162cd5015d"], ["5094bbfe-c238-45a4-ae56-f763add012c3", "3224b9e9499f6841ef7f07a926a9205be69f4f43bc7587fadc1a5ac744af6d9b"], ["c565e305-e7e3-4d7d-b12b-7b6e473ae971", "013b27337c81119eb17e9affa35ac972d3b983a4f9e064866da0fbbd379fedcc"], ["4a4098ec-8e73-4b54-a59f-403048ca9106", "ea140a645d8edb44add8057dc85db5d68be8eaaf2c3aaa50489458571daef09c"]]}], "changes": [{"new": ["d28f72fe-2480-42af-87e2-fe0ced529473", "737f81a173a6c874aced55d7c1c2c1b79e59b8980e294a1a01b9c973ae2038ce"], "old": null, "kind": "append", "position": 0, "host_logical_id": "d28f72fe-2480-42af-87e2-fe0ced529473"}, {"new": ["7f11be62-d170-449c-a429-1cc2ff3d6dc0", "3c0c3ed65e595da9deae0d4647791efcbbf4d319b871310bbb69b944dc063451"], "old": null, "kind": "append", "position": 1, "host_logical_id": "7f11be62-d170-449c-a429-1cc2ff3d6dc0"}, {"new": ["f2f07485-7cbc-41df-82f0-871d5ccba645", "f3d91c54730b31eca7e123ce34397b0f0187d348a6bbad6a824c7e9bcff5ddc3"], "old": null, "kind": "append", "position": 2, "host_logical_id": "f2f07485-7cbc-41df-82f0-871d5ccba645"}, {"new": ["4f78985e-bbaf-416d-81a4-4e29303bcfb4", "8236b1cd2cf13940345d1c953e6bbd1d2a5a011c335c7ec724956f3cbcd705d5"], "old": null, "kind": "append", "position": 3, "host_logical_id": "4f78985e-bbaf-416d-81a4-4e29303bcfb4"}, {"new": ["1746ecfe-6328-4b1c-aa58-1b8cf3448d8b", "01e2b4743458af5279f0510ffb2a2ab59de68efbae433eb71e3dc1162cd5015d"], "old": null, "kind": "append", "position": 4, "host_logical_id": "1746ecfe-6328-4b1c-aa58-1b8cf3448d8b"}, {"new": ["5094bbfe-c238-45a4-ae56-f763add012c3", "3224b9e9499f6841ef7f07a926a9205be69f4f43bc7587fadc1a5ac744af6d9b"], "old": null, "kind": "append", "position": 5, "host_logical_id": "5094bbfe-c238-45a4-ae56-f763add012c3"}, {"new": ["c565e305-e7e3-4d7d-b12b-7b6e473ae971", "013b27337c81119eb17e9affa35ac972d3b983a4f9e064866da0fbbd379fedcc"], "old": null, "kind": "append", "position": 6, "host_logical_id": "c565e305-e7e3-4d7d-b12b-7b6e473ae971"}, {"new": ["4a4098ec-8e73-4b54-a59f-403048ca9106", "ea140a645d8edb44add8057dc85db5d68be8eaaf2c3aaa50489458571daef09c"], "old": null, "kind": "append", "position": 7, "host_logical_id": "4a4098ec-8e73-4b54-a59f-403048ca9106"}]}', '2026-09-26 10:09:58.979515+00', '01a0dd31-6ccb-72fd-8065-00f407a8e767');


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


