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

INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 0, '01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23', '5c4f929a08d63a46103028e3593129d9', 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 1, '01a0e7b4-edad-768a-a063-7a1239eb37f2', '8cb82222822286ea5cc0b6295c324524', 0, 'd9071497a0cd7a3b2a707fc39856dfc1');
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 2, '01a0e7b4-edae-7cc2-85ee-0445a9abeb94', '3aca06e536b08afdd137e534f4e7eacf', 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 3, '01a0e7b4-f446-70ae-a1b0-8f4bb58b088a', '759b8ac6435987712a95e73a404561f4', 1, '765bdc1556d2cdd4fc8611361f344844');
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 4, '01a0e7b4-ede1-79be-8cff-42aed7411c94', 'bece80c043dd3ab036ab11e1d01ac4ea', 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 5, '01a0e7b4-ede3-7649-b137-ffab3970c16a', 'aa420f491c998c08f80f415681ecfaf2', 2, '400ff2edac0964189fcb7454658ab5cf');
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 6, '01a0e7b4-ede3-7ffd-a5ea-26da9b734a24', 'fa0f2a792f2d0e1ec57ca45eb586cd54', 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 7, '01a0e7b4-ede4-723b-a7c4-0755c53a942a', '4df9a89a5b8d98d98ecfc747018242e7', 3, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 8, '01a0e7b4-f495-7ee1-827a-a97347dab3da', '713fa4ae5c96733ec2d2641e81af369f', NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 9, '01a0e7b4-ee0d-722e-b472-47284937b79b', 'd0f8df96549c6e6bdbebcaa8e17c1c87', 3, 'ce94b870e4cf07a1b5a99330b7a35330');
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 10, '01a0e7b4-ee0e-778b-bedb-3426de63cc2e', '1a2fbe04563e6f5a5c9f2d318c945c82', 4, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 11, '01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87', '24b98e8752e9c8e42b08262a94dce389', 4, '36125a5f886798d8aaa020eeb55272b4');
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 12, '01a0e7b4-ee35-7aa0-9a98-3e826b15cc10', 'ee0c5a60f8c7ba4f524f5bd0f1b49c9b', 5, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 13, '01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9', '42352669babf127662637083d754a045', 5, '71c5e25c54638074d9fec975f303cee0');
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 14, '01a0e7b4-f447-7fcb-9235-86f78ff1bd3d', '1404621b50b0d3ee6c1d9eb74de08948', 6, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 15, '01a0e7b4-f496-7cd4-b9d4-d6850d72b649', '9c54e5c5fd9ce8eea739cc1aebb5351d', 6, 'eb463bc836e8d04a513f5a8537f465b7');
INSERT INTO public.active_membership VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 16, '01a0e7b4-f496-7547-9ff6-9ba32462ee2a', 'f0fd3741301f55ba59f32870a451b1a7', 7, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 0, '01a0e7b4-faaa-7f6a-80f1-8a979367c2b4', '32ce436668be5094786f0123469fdeae', 0, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 1, '01a0e7b4-faab-752d-bf21-4a731a2e8061', '28d0d3320f4f13504bc5fc84bd09ad87', 0, 'a90e9ef2054d923d9f0eba05426796c0');
INSERT INTO public.active_membership VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 2, '01a0e7b4-faac-7e67-9e9a-60814a5b1670', '2fcdd6397ae2e5b4342d994b44393d02', 1, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 3, '01a0e7b4-faad-751e-9e6d-97ae379ee445', '6a014b2d8aec0eee1d729cc8a57ab544', 1, 'caa56c537159d7bb2d3052d1ff356b28');
INSERT INTO public.active_membership VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 4, '01a0e7b4-faae-79dd-8bf1-8e29472f6aae', 'a829599decbb1e359a17218854c62add', 2, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 5, '01a0e7b4-faae-7b48-b13f-52c5caa759a5', '25a08b5bbb5c34587c50a8a28851723e', 2, 'e32c64e362d4f18261958a123237aa64');
INSERT INTO public.active_membership VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 6, '01a0e7b4-faaf-7356-9417-23637addc0a7', '72c7ebdd3d4a5f2866412e4e0fa0f408', NULL, NULL);
INSERT INTO public.active_membership VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 7, '01a0e7b4-faaf-718f-82f8-9cb1d61591af', '55ebdcd6ebd7a33ebcd1aa0109566127', 3, NULL);


--
-- Data for Name: app_config; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: assertion; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (1, '01a0e7b4-f338-72ed-afb8-291bf5427fee', '01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (2, '01a0e7b4-f350-78d1-b86b-8ab9fd9ebafa', '01a0e7b4-ee0d-722e-b472-47284937b79b', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (3, '01a0e7b4-f380-7033-a376-1d0f8c96749b', '01a0e7b4-ede3-7649-b137-ffab3970c16a', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (4, '01a0e7b4-f396-7001-82d3-befd70319cf3', '01a0e7b4-edaf-710e-b47e-7429ee49637d', 'Rin', 'character', 'located_in', 'harbor', 'place', NULL, 'stated', 0.9, 'Rin went to the harbor.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (5, '01a0e7b4-f396-7001-82d3-befd70319cf3', '01a0e7b4-edaf-710e-b47e-7429ee49637d', 'Rin', 'character', 'relationship', 'Mina', 'character', 'sister', 'stated', 0.9, 'Rin is Mina''s sister.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (6, '01a0e7b4-f3e7-75b4-96f9-e5168945cf8c', '01a0e7b4-edad-768a-a063-7a1239eb37f2', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (7, '01a0e7b4-f3e7-75b4-96f9-e5168945cf8c', '01a0e7b4-edad-768a-a063-7a1239eb37f2', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (8, '01a0e7b4-f857-7fa0-8828-2bfd7200166a', '01a0e7b4-f496-7cd4-b9d4-d6850d72b649', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (9, '01a0e7b4-f883-7a6c-b03e-ff9ba2f74805', '01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87', 'Mina', 'character', 'located_in', 'bell tower', 'place', NULL, 'stated', 0.9, 'Mina moved to the bell tower.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (10, '01a0e7b4-f899-7b29-a4c9-a5ef159f7992', '01a0e7b4-ee0d-722e-b472-47284937b79b', 'Rin', 'character', 'possesses', 'silver compass', 'item', NULL, 'stated', 0.9, 'Rin has the silver compass.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (11, '01a0e7b4-f8bc-7695-a1ae-2f000bf82f4d', '01a0e7b4-ede3-7649-b137-ffab3970c16a', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (12, '01a0e7b4-f8d1-7209-85ca-a087be11609d', '01a0e7b4-f446-70ae-a1b0-8f4bb58b088a', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (13, '01a0e7b4-f8d1-7209-85ca-a087be11609d', '01a0e7b4-f446-70ae-a1b0-8f4bb58b088a', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (14, '01a0e7b4-fd5b-7495-b96d-6907fd59d955', '01a0e7b4-faae-7b48-b13f-52c5caa759a5', 'Mina', 'character', 'promised', 'Takumi', 'character', 'return before the bell rings', 'stated', 0.9, 'Mina promised Takumi to return before the bell rings.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (15, '01a0e7b4-fd73-7433-a15c-e8d123c50b3e', '01a0e7b4-faad-751e-9e6d-97ae379ee445', 'Rin', 'character', 'located_in', 'lighthouse', 'place', NULL, 'stated', 0.9, 'Rin went to the lighthouse.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (16, '01a0e7b4-fd73-7433-a15c-e8d123c50b3e', '01a0e7b4-faad-751e-9e6d-97ae379ee445', 'Rin', 'character', 'relationship', 'Mina', 'character', 'rival', 'stated', 0.9, 'Rin is Mina''s rival.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (17, '01a0e7b4-fd87-7342-8be2-d42b18b6085a', '01a0e7b4-faab-752d-bf21-4a731a2e8061', 'Mina', 'character', 'located_in', 'old chapel', 'place', NULL, 'stated', 0.9, 'Mina is in the old chapel.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);
INSERT INTO public.assertion OVERRIDING SYSTEM VALUE VALUES (18, '01a0e7b4-fd87-7342-8be2-d42b18b6085a', '01a0e7b4-faab-752d-bf21-4a731a2e8061', 'Mina', 'character', 'possesses', 'brass key', 'item', NULL, 'stated', 0.9, 'Mina has the brass key.', 'valid', NULL, NULL, NULL, 'unknown', 'positive', 'actual', 'narration', NULL, NULL, NULL);


--
-- Data for Name: conversation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.conversation VALUES ('01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'pocketrisu', NULL, 'ecb64de9-5dc4-49a8-acd7-5316b07991d7', '2026-09-28 11:09:49.348203+00', NULL, NULL, NULL, '01a0e7b4-f499-765d-89aa-c9bd070b972d', 'c75a78e11ec82afa5ca6ea00c9cd26a0da9798b99eedf76ae80b62d5e45fc70b', 'Mina', 'Upgrade fixture', 'Takumi');
INSERT INTO public.conversation VALUES ('01a0e7b4-fa9d-71fb-9096-8df6ba220669', 'pocketrisu', NULL, '0ec9d173-162e-4b8f-8992-9301c574c227', '2026-09-28 11:09:52.670023+00', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'ecb64de9-5dc4-49a8-acd7-5316b07991d7', '09d0130f-1641-4848-85e1-2d20445c08b2', '01a0e7b4-fab1-72bf-93e1-9806dcd4893a', '1bb75b60e16fe2581210a3b1d5d603c1f0625c37b389acbfb118ab37801d3205', 'Mina', 'Upgrade fixture', 'Takumi');


--
-- Data for Name: extraction; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.extraction VALUES ('01a0e7b4-f338-72ed-afb8-291bf5427fee', '01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87', '077c9171b456ff74f464bfe4758fe1bc', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:50.776753+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b4-ee0e-778b-bedb-3426de63cc2e,01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f350-78d1-b86b-8ab9fd9ebafa', '01a0e7b4-ee0d-722e-b472-47284937b79b', '65839f185668f21bc7e4892a3c5d92b4', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:50.800163+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 78, "target_chars": 78, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b4-ee0c-77cf-990f-76123938a7a4,01a0e7b4-ee0d-722e-b472-47284937b79b}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f367-759f-95c4-803919884af2', '01a0e7b4-ede4-723b-a7c4-0755c53a942a', 'a8ee8712b462c3591868120459b6bc59', 'extract-v8', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:50.823269+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 58, "target_chars": 58, "target_messages": 2, "context_messages": 6, "context_truncated": 0}', '{01a0e7b4-ede3-7ffd-a5ea-26da9b734a24,01a0e7b4-ede4-723b-a7c4-0755c53a942a}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f380-7033-a376-1d0f8c96749b', '01a0e7b4-ede3-7649-b137-ffab3970c16a', '7d62c7bfd48f2767d0809efed686f878', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:50.848761+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b4-ede1-79be-8cff-42aed7411c94,01a0e7b4-ede3-7649-b137-ffab3970c16a}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f396-7001-82d3-befd70319cf3', '01a0e7b4-edaf-710e-b47e-7429ee49637d', 'e97640e4d4a24190bdd8b6863df117f8', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"harbor\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the harbor.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"sister\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s sister.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:50.870343+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 61, "target_chars": 61, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b4-edae-7cc2-85ee-0445a9abeb94,01a0e7b4-edaf-710e-b47e-7429ee49637d}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f3e7-75b4-96f9-e5168945cf8c', '01a0e7b4-edad-768a-a063-7a1239eb37f2', 'd9071497a0cd7a3b2a707fc39856dfc1', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:50.951874+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23,01a0e7b4-edad-768a-a063-7a1239eb37f2}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f857-7fa0-8828-2bfd7200166a', '01a0e7b4-f496-7cd4-b9d4-d6850d72b649', 'eb463bc836e8d04a513f5a8537f465b7', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:52.087486+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 43, "target_chars": 43, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b4-f447-7fcb-9235-86f78ff1bd3d,01a0e7b4-f496-7cd4-b9d4-d6850d72b649}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f86d-7b32-bb84-1bc8e6da1e26', '01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9', '71c5e25c54638074d9fec975f303cee0', 'extract-v8', 'stub', '{"reply": "{\"assertions\": []}"}', '2026-09-28 11:09:52.109243+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 49, "target_chars": 49, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b4-ee35-7aa0-9a98-3e826b15cc10,01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f883-7a6c-b03e-ff9ba2f74805', '01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87', '36125a5f886798d8aaa020eeb55272b4', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"bell tower\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina moved to the bell tower.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:52.131279+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 54, "target_chars": 54, "target_messages": 2, "context_messages": 7, "context_truncated": 0}', '{01a0e7b4-ee0e-778b-bedb-3426de63cc2e,01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f899-7b29-a4c9-a5ef159f7992', '01a0e7b4-ee0d-722e-b472-47284937b79b', 'ce94b870e4cf07a1b5a99330b7a35330', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"silver compass\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin has the silver compass.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:52.153013+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 111, "target_chars": 111, "target_messages": 3, "context_messages": 6, "context_truncated": 0}', '{01a0e7b4-ede3-7ffd-a5ea-26da9b734a24,01a0e7b4-ede4-723b-a7c4-0755c53a942a,01a0e7b4-ee0d-722e-b472-47284937b79b}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f8bc-7695-a1ae-2f000bf82f4d', '01a0e7b4-ede3-7649-b137-ffab3970c16a', '400ff2edac0964189fcb7454658ab5cf', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:52.18866+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b4-ede1-79be-8cff-42aed7411c94,01a0e7b4-ede3-7649-b137-ffab3970c16a}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-f8d1-7209-85ca-a087be11609d', '01a0e7b4-f446-70ae-a1b0-8f4bb58b088a', '765bdc1556d2cdd4fc8611361f344844', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:52.208946+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b4-edae-7cc2-85ee-0445a9abeb94,01a0e7b4-f446-70ae-a1b0-8f4bb58b088a}', NULL, '{"entities": [{"name": "brass key", "type": "item"}, {"name": "Mina", "type": "character"}, {"name": "old chapel", "type": "place"}], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-fd5b-7495-b96d-6907fd59d955', '01a0e7b4-faae-7b48-b13f-52c5caa759a5', 'e32c64e362d4f18261958a123237aa64', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"promised\", \"object\": \"Takumi\", \"object_type\": \"character\", \"value\": \"return before the bell rings\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina promised Takumi to return before the bell rings.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:53.371433+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 87, "target_chars": 87, "target_messages": 2, "context_messages": 4, "context_truncated": 0}', '{01a0e7b4-faae-79dd-8bf1-8e29472f6aae,01a0e7b4-faae-7b48-b13f-52c5caa759a5}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-fd73-7433-a15c-e8d123c50b3e', '01a0e7b4-faad-751e-9e6d-97ae379ee445', 'caa56c537159d7bb2d3052d1ff356b28', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"lighthouse\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin went to the lighthouse.\", \"modality\": \"actual\"}, {\"subject\": \"Rin\", \"subject_type\": \"character\", \"predicate\": \"relationship\", \"object\": \"Mina\", \"object_type\": \"character\", \"value\": \"rival\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Rin is Mina''s rival.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:53.395495+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 64, "target_chars": 64, "target_messages": 2, "context_messages": 2, "context_truncated": 0}', '{01a0e7b4-faac-7e67-9e9a-60814a5b1670,01a0e7b4-faad-751e-9e6d-97ae379ee445}', NULL, '{"entities": [], "promises": []}');
INSERT INTO public.extraction VALUES ('01a0e7b4-fd87-7342-8be2-d42b18b6085a', '01a0e7b4-faab-752d-bf21-4a731a2e8061', 'a90e9ef2054d923d9f0eba05426796c0', 'extract-v8', 'stub', '{"reply": "{\"assertions\": [{\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"located_in\", \"object\": \"old chapel\", \"object_type\": \"place\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina is in the old chapel.\", \"modality\": \"actual\"}, {\"subject\": \"Mina\", \"subject_type\": \"character\", \"predicate\": \"possesses\", \"object\": \"brass key\", \"object_type\": \"item\", \"epistemic\": \"stated\", \"confidence\": 0.9, \"evidence\": \"Mina has the brass key.\", \"modality\": \"actual\"}]}"}', '2026-09-28 11:09:53.415279+00', 'extract-18f6eaa8dcf24b7916dac3bca790d78c', '{"target_used": 80, "target_chars": 80, "target_messages": 2, "context_messages": 0, "context_truncated": 0}', '{01a0e7b4-faaa-7f6a-80f1-8a979367c2b4,01a0e7b4-faab-752d-bf21-4a731a2e8061}', NULL, '{"entities": [], "promises": []}');


--
-- Data for Name: host_observation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.host_observation VALUES ('01a0e7b4-edb0-7f6e-9f41-e1e2533cbf6b', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'manifest', 'e618d3bf2f7bc2e7597d88267821ade066f58f30e2dad7e074dee3dfbebb00d0', '01a0e7b4-eda4-7f1f-b543-a0b42c101930:e618d3bf2f7bc2e7597d88267821ade066f58f30e2dad7e074dee3dfbebb00d0:manifest', '2026-09-28 11:09:49.353327+00', '{"chat_id": "ecb64de9-5dc4-49a8-acd7-5316b07991d7", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["7e43bffb-482f-4939-86ef-1fa8edda8b5f", "062e6a45e1dc047b3c9df81b154f32cae60873107b5d20e78c24a872e16c8674", "user", null, null, null, 0, null, null], ["f4232d50-a0c9-41d8-b632-0eb358382e07", "497f7626ea4e8090434592902bb3833caece890715d78436a944f18a9ba9866a", "char", null, null, null, 0, "f4232d50-a0c9-41d8-b632-0eb358382e07", null], ["b22e7f6d-c0e2-499b-9c71-02e6a53bef53", "5b9325e3b5b11a47c2cf7934fabfb36191cb37641f0cc192f12c6d56c54f59a5", "user", null, null, null, 0, null, null], ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "418c25808b62d0d3533fdb7aa5b568f0bb93998a54cc210ca8b8ff12a3681e4e", "char", null, null, null, 0, "b9086fbc-6eeb-4657-a0da-cb0a06777db5", null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-ede7-7133-8f5d-b8d89216c28b', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'manifest', '0e84d3eb80efb053e97114a7c26c20f49abfe79dea3093437ba34d8a4e12d837', '01a0e7b4-eda4-7f1f-b543-a0b42c101930:0e84d3eb80efb053e97114a7c26c20f49abfe79dea3093437ba34d8a4e12d837:manifest', '2026-09-28 11:09:49.408975+00', '{"chat_id": "ecb64de9-5dc4-49a8-acd7-5316b07991d7", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["6b8c231f-f49e-4e1c-bee1-97f36fe8c537", "654b3588a0b6c119ebe8ab25d4a4ef7d1ea5f9d3c67729e496ef216c129786ac", "user", null, null, null, 0, null, null], ["09d0130f-1641-4848-85e1-2d20445c08b2", "c0f342afaa4ed5242523a6948a420d4dea59a59c4e163417dde013f7e6d1bf5b", "char", null, null, null, 0, "09d0130f-1641-4848-85e1-2d20445c08b2", null], ["54da3271-7f1a-42d2-b88e-fc79f2efdaad", "1ccdc6fc667881ef62284e0b894d817bc0cc1092c0cfc38c7a49cc0a195e2f79", "user", null, null, null, 0, null, null], ["f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", "298cd3a38869a060ee34def836275b751d1b81f977bea83fc0239e8f76f78311", "char", null, null, null, 0, "f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", null]], "base_manifest_hash": "e618d3bf2f7bc2e7597d88267821ade066f58f30e2dad7e074dee3dfbebb00d0"}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-ee12-76b1-8b79-b58001632601', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'manifest', 'c6eab19d21a2fd71e10a1c03e77c459250120e7b7d1836578574be79bbf5bf8c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930:c6eab19d21a2fd71e10a1c03e77c459250120e7b7d1836578574be79bbf5bf8c:manifest', '2026-09-28 11:09:49.451528+00', '{"chat_id": "ecb64de9-5dc4-49a8-acd7-5316b07991d7", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["4da88bf2-78f7-4292-b2c6-86e376e71964", "9795c392926d5c63fe7a0588302d90be8ea002cdb5241b811f25eff30ef61f53", "user", null, null, null, 0, null, null], ["654c12f1-85cc-41cd-995c-1fe08fb40614", "b9ff7953631888fdb2f2ed0e606f5879c42fe5e47846f04c81748d833e6376f9", "char", null, null, null, 0, "654c12f1-85cc-41cd-995c-1fe08fb40614", null], ["ccd66991-40e8-4ccb-b467-c1cfce62ecd0", "41a770b984cce35df3230443c5e3291d3e494542bfe6ee785af62f75913657eb", "user", null, null, null, 0, null, null], ["d1f36a29-0a86-4824-b4ed-76a9f0b26e54", "d48ed942168ba30643de9f89ad2dfce9512281de9093342ce44929f986d4681f", "char", null, null, null, 0, "d1f36a29-0a86-4824-b4ed-76a9f0b26e54", null]], "base_manifest_hash": "0e84d3eb80efb053e97114a7c26c20f49abfe79dea3093437ba34d8a4e12d837"}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-ee38-71c8-b303-aaa72294db4d', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'manifest', '41a3d13719fe1fd721a52d3fc84b519a29695b48f96bcf4e944e55d84ccf2429', '01a0e7b4-eda4-7f1f-b543-a0b42c101930:41a3d13719fe1fd721a52d3fc84b519a29695b48f96bcf4e944e55d84ccf2429:manifest', '2026-09-28 11:09:49.49214+00', '{"chat_id": "ecb64de9-5dc4-49a8-acd7-5316b07991d7", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["24319f0f-127a-4149-b780-59083977f410", "3dfbe939779b60c1d27fd8ad972b2341ac783cfce4e05b8da7f2e9d967997e08", "user", null, null, null, 0, null, null]], "base_manifest_hash": "c6eab19d21a2fd71e10a1c03e77c459250120e7b7d1836578574be79bbf5bf8c"}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-f449-761c-ad65-c23d0dca3ded', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'manifest', '081927cf65aea8e42a48d07cbd4addb974d6e74633375c1ede36e1c7883629d6', '01a0e7b4-eda4-7f1f-b543-a0b42c101930:081927cf65aea8e42a48d07cbd4addb974d6e74633375c1ede36e1c7883629d6:manifest', '2026-09-28 11:09:51.045231+00', '{"chat_id": "ecb64de9-5dc4-49a8-acd7-5316b07991d7", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["7e43bffb-482f-4939-86ef-1fa8edda8b5f", "062e6a45e1dc047b3c9df81b154f32cae60873107b5d20e78c24a872e16c8674", "user", null, null, null, 0, null, null], ["f4232d50-a0c9-41d8-b632-0eb358382e07", "497f7626ea4e8090434592902bb3833caece890715d78436a944f18a9ba9866a", "char", null, null, null, 0, "f4232d50-a0c9-41d8-b632-0eb358382e07", null], ["b22e7f6d-c0e2-499b-9c71-02e6a53bef53", "5b9325e3b5b11a47c2cf7934fabfb36191cb37641f0cc192f12c6d56c54f59a5", "user", null, null, null, 0, null, null], ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "e34bca87e8c8690b498e47cb05a90fea0f5ed83b5f1fafd8fdb146462d115b02", "char", null, null, null, 0, "b9086fbc-6eeb-4657-a0da-cb0a06777db5", null], ["6b8c231f-f49e-4e1c-bee1-97f36fe8c537", "654b3588a0b6c119ebe8ab25d4a4ef7d1ea5f9d3c67729e496ef216c129786ac", "user", null, null, null, 0, null, null], ["09d0130f-1641-4848-85e1-2d20445c08b2", "c0f342afaa4ed5242523a6948a420d4dea59a59c4e163417dde013f7e6d1bf5b", "char", null, null, null, 0, "09d0130f-1641-4848-85e1-2d20445c08b2", null], ["54da3271-7f1a-42d2-b88e-fc79f2efdaad", "1ccdc6fc667881ef62284e0b894d817bc0cc1092c0cfc38c7a49cc0a195e2f79", "user", null, null, null, 0, null, null], ["f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", "298cd3a38869a060ee34def836275b751d1b81f977bea83fc0239e8f76f78311", "char", null, null, null, 0, "f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", null], ["4da88bf2-78f7-4292-b2c6-86e376e71964", "9795c392926d5c63fe7a0588302d90be8ea002cdb5241b811f25eff30ef61f53", "user", null, null, null, 0, null, null], ["654c12f1-85cc-41cd-995c-1fe08fb40614", "b9ff7953631888fdb2f2ed0e606f5879c42fe5e47846f04c81748d833e6376f9", "char", null, null, null, 0, "654c12f1-85cc-41cd-995c-1fe08fb40614", null], ["ccd66991-40e8-4ccb-b467-c1cfce62ecd0", "41a770b984cce35df3230443c5e3291d3e494542bfe6ee785af62f75913657eb", "user", null, null, null, 0, null, null], ["d1f36a29-0a86-4824-b4ed-76a9f0b26e54", "d48ed942168ba30643de9f89ad2dfce9512281de9093342ce44929f986d4681f", "char", null, null, null, 0, "d1f36a29-0a86-4824-b4ed-76a9f0b26e54", null], ["24319f0f-127a-4149-b780-59083977f410", "3dfbe939779b60c1d27fd8ad972b2341ac783cfce4e05b8da7f2e9d967997e08", "user", null, null, null, 0, null, null], ["61789a3c-a601-4f30-94f6-4c53ad38be8d", "2be3e9bbd99d7ce8af66bb2e7160bb43fa1fa8ee46ec7fd157c1e9fd33eba171", "char", null, null, null, 0, "61789a3c-a601-4f30-94f6-4c53ad38be8d", null], ["3a262e2c-b2b2-4191-bc0c-c6539d90acd1", "709879d5affa7031ad359a76c0af8ec5d8fd96ff6cb1c6101bb74e8a7b8c890c", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-f474-795a-a5da-66e75a112481', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'manifest', '1c497ebc43c0b1c4d8ce596d6ba9483a1074f73b564ea0a0792d7a65d5c107b6', '01a0e7b4-eda4-7f1f-b543-a0b42c101930:1c497ebc43c0b1c4d8ce596d6ba9483a1074f73b564ea0a0792d7a65d5c107b6:manifest', '2026-09-28 11:09:51.088043+00', '{"chat_id": "ecb64de9-5dc4-49a8-acd7-5316b07991d7", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "appended": [["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "fffb37f0673f1a8170f446e52318ba8fbe3743356edb48a745f2da2653955d3f", "char", null, null, 1, 2, "0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", null]], "base_manifest_hash": "081927cf65aea8e42a48d07cbd4addb974d6e74633375c1ede36e1c7883629d6"}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-f498-760b-9e04-e7d2a2f4b188', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'manifest', 'c75a78e11ec82afa5ca6ea00c9cd26a0da9798b99eedf76ae80b62d5e45fc70b', '01a0e7b4-eda4-7f1f-b543-a0b42c101930:c75a78e11ec82afa5ca6ea00c9cd26a0da9798b99eedf76ae80b62d5e45fc70b:manifest', '2026-09-28 11:09:51.12461+00', '{"chat_id": "ecb64de9-5dc4-49a8-acd7-5316b07991d7", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["7e43bffb-482f-4939-86ef-1fa8edda8b5f", "062e6a45e1dc047b3c9df81b154f32cae60873107b5d20e78c24a872e16c8674", "user", null, null, null, 0, null, null], ["f4232d50-a0c9-41d8-b632-0eb358382e07", "497f7626ea4e8090434592902bb3833caece890715d78436a944f18a9ba9866a", "char", null, null, null, 0, "f4232d50-a0c9-41d8-b632-0eb358382e07", null], ["b22e7f6d-c0e2-499b-9c71-02e6a53bef53", "5b9325e3b5b11a47c2cf7934fabfb36191cb37641f0cc192f12c6d56c54f59a5", "user", null, null, null, 0, null, null], ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "e34bca87e8c8690b498e47cb05a90fea0f5ed83b5f1fafd8fdb146462d115b02", "char", null, null, null, 0, "b9086fbc-6eeb-4657-a0da-cb0a06777db5", null], ["6b8c231f-f49e-4e1c-bee1-97f36fe8c537", "654b3588a0b6c119ebe8ab25d4a4ef7d1ea5f9d3c67729e496ef216c129786ac", "user", null, null, null, 0, null, null], ["09d0130f-1641-4848-85e1-2d20445c08b2", "c0f342afaa4ed5242523a6948a420d4dea59a59c4e163417dde013f7e6d1bf5b", "char", null, null, null, 0, "09d0130f-1641-4848-85e1-2d20445c08b2", null], ["54da3271-7f1a-42d2-b88e-fc79f2efdaad", "1ccdc6fc667881ef62284e0b894d817bc0cc1092c0cfc38c7a49cc0a195e2f79", "user", null, null, null, 0, null, null], ["f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", "298cd3a38869a060ee34def836275b751d1b81f977bea83fc0239e8f76f78311", "char", null, null, null, 0, "f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", null], ["4da88bf2-78f7-4292-b2c6-86e376e71964", "0b3d75dd50bc6adbdb57bbf0c251249bcf30362be0427240748e0a12b76f09c6", "user", true, null, null, 0, null, null], ["654c12f1-85cc-41cd-995c-1fe08fb40614", "b9ff7953631888fdb2f2ed0e606f5879c42fe5e47846f04c81748d833e6376f9", "char", null, null, null, 0, "654c12f1-85cc-41cd-995c-1fe08fb40614", null], ["ccd66991-40e8-4ccb-b467-c1cfce62ecd0", "41a770b984cce35df3230443c5e3291d3e494542bfe6ee785af62f75913657eb", "user", null, null, null, 0, null, null], ["d1f36a29-0a86-4824-b4ed-76a9f0b26e54", "d48ed942168ba30643de9f89ad2dfce9512281de9093342ce44929f986d4681f", "char", null, null, null, 0, "d1f36a29-0a86-4824-b4ed-76a9f0b26e54", null], ["24319f0f-127a-4149-b780-59083977f410", "3dfbe939779b60c1d27fd8ad972b2341ac783cfce4e05b8da7f2e9d967997e08", "user", null, null, null, 0, null, null], ["61789a3c-a601-4f30-94f6-4c53ad38be8d", "2be3e9bbd99d7ce8af66bb2e7160bb43fa1fa8ee46ec7fd157c1e9fd33eba171", "char", null, null, null, 0, "61789a3c-a601-4f30-94f6-4c53ad38be8d", null], ["3a262e2c-b2b2-4191-bc0c-c6539d90acd1", "709879d5affa7031ad359a76c0af8ec5d8fd96ff6cb1c6101bb74e8a7b8c890c", "user", null, null, null, 0, null, null], ["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "e2cbc0421b2dcc4c5f63be6e537df7d177484c4c4c1513eeb28c36136b970e77", "char", null, null, 0, 2, "0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", null], ["ab2f10fe-0082-4c2d-8496-0e884fb2d35f", "0fcbee8bf86b1dcee91fe2d3b202fd900331756214e57ad0571e2e7773f9f202", "user", null, null, null, 0, null, null]]}');
INSERT INTO public.host_observation VALUES ('01a0e7b4-fab1-7d22-ab4c-d5957b53e552', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', 'manifest', '1bb75b60e16fe2581210a3b1d5d603c1f0625c37b389acbfb118ab37801d3205', '01a0e7b4-fa9d-71fb-9096-8df6ba220669:1bb75b60e16fe2581210a3b1d5d603c1f0625c37b389acbfb118ab37801d3205:manifest', '2026-09-28 11:09:52.681844+00', '{"chat_id": "0ec9d173-162e-4b8f-8992-9301c574c227", "columns": ["host_logical_id", "revision_hash", "role", "disabled", "is_comment", "swipe_id", "swipe_count", "generation_id", "special_comments"], "entries": [["59f0d7f8-ed76-48c0-a601-49aaa09000cb", "c7f83db81d06934ffdf021857d2632e671d24cc1df6b1504730ce91262ecf4a6", "user", null, null, null, 0, null, null], ["e0ab75cc-48fe-4a2d-bb7c-6720c4c753e8", "2902fe7feb4c62040328852b11e91e83bc85440573002fa66499ba91f8e8d9f0", "char", null, null, null, 0, "f4232d50-a0c9-41d8-b632-0eb358382e07", null], ["f14dab15-9ba7-4200-b101-14282be57d98", "a25a03b58d70062aab7cb6610bb00514f9de4a66ae1837dddf817cf3befc1778", "user", null, null, null, 0, null, null], ["0a81f9a2-b5b3-491a-b7a8-576ee19d9c77", "1f59a96fe93b87c706be773e6c0fb97c7daf1aafb828ffa2f8e86a7607e7b833", "char", null, null, null, 0, "b9086fbc-6eeb-4657-a0da-cb0a06777db5", null], ["1e858747-f428-46c4-b2dd-f01a4f534ad6", "8294caf5be1f2fb7f4922e0de6e7ad4adca06bc04fe47f9896ae342fc890729f", "user", null, null, null, 0, null, null], ["c91a2a09-ad4e-49ba-a8b3-8b0602cef307", "ff0d62f5a8c4e15ae250ef23ea1747edf06d7bafb9d6c88ef36126fa950d0e27", "char", null, null, null, 0, "09d0130f-1641-4848-85e1-2d20445c08b2", null], ["24261722-e908-4c75-9092-0547ad1f3cd6", "4381be6dc747e55e6f1a5aaddab356884481378b62ccd1ac36396bae35500cbc", "char", true, true, null, 0, null, ["{{specialcomment::branchedfrom::ecb64de9-5dc4-49a8-acd7-5316b07991d7::Harbor route::09d0130f-1641-4848-85e1-2d20445c08b2::}}"]], ["4e359d4d-f2dc-45f3-8e80-d3c921af8f71", "aed37c6d8df03f47fbd923e4aaa9a9949680d5e303b20ecb2edee747b536e28d", "user", null, null, null, 0, null, null]]}');


--
-- Data for Name: job; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (19, 'embed', 'embed:01a0e7b4-ee35-7aa0-9a98-3e826b15cc10:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ee35-7aa0-9a98-3e826b15cc10"}', 50, 'done', 1, '2026-09-28 11:09:49.49214+00', NULL, NULL, '2026-09-28 11:09:49.49214+00', '2026-09-28 11:09:50.569359+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (18, 'embed', 'embed:01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87"}', 50, 'done', 1, '2026-09-28 11:09:49.49214+00', NULL, NULL, '2026-09-28 11:09:49.49214+00', '2026-09-28 11:09:50.590197+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (16, 'embed', 'embed:01a0e7b4-ee0e-778b-bedb-3426de63cc2e:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ee0e-778b-bedb-3426de63cc2e"}', 50, 'done', 1, '2026-09-28 11:09:49.451528+00', NULL, NULL, '2026-09-28 11:09:49.451528+00', '2026-09-28 11:09:50.611448+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (15, 'embed', 'embed:01a0e7b4-ee0d-722e-b472-47284937b79b:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ee0d-722e-b472-47284937b79b"}', 50, 'done', 1, '2026-09-28 11:09:49.451528+00', NULL, NULL, '2026-09-28 11:09:49.451528+00', '2026-09-28 11:09:50.633339+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (14, 'embed', 'embed:01a0e7b4-ee0c-77cf-990f-76123938a7a4:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ee0c-77cf-990f-76123938a7a4"}', 50, 'done', 1, '2026-09-28 11:09:49.451528+00', NULL, NULL, '2026-09-28 11:09:49.451528+00', '2026-09-28 11:09:50.65243+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (13, 'embed', 'embed:01a0e7b4-ede4-723b-a7c4-0755c53a942a:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ede4-723b-a7c4-0755c53a942a"}', 50, 'done', 1, '2026-09-28 11:09:49.451528+00', NULL, NULL, '2026-09-28 11:09:49.451528+00', '2026-09-28 11:09:50.672342+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (10, 'embed', 'embed:01a0e7b4-ede3-7ffd-a5ea-26da9b734a24:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ede3-7ffd-a5ea-26da9b734a24"}', 50, 'done', 1, '2026-09-28 11:09:49.408975+00', NULL, NULL, '2026-09-28 11:09:49.408975+00', '2026-09-28 11:09:50.69074+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (9, 'embed', 'embed:01a0e7b4-ede3-7649-b137-ffab3970c16a:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ede3-7649-b137-ffab3970c16a"}', 50, 'done', 1, '2026-09-28 11:09:49.408975+00', NULL, NULL, '2026-09-28 11:09:49.408975+00', '2026-09-28 11:09:50.710368+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (8, 'embed', 'embed:01a0e7b4-ede1-79be-8cff-42aed7411c94:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-ede1-79be-8cff-42aed7411c94"}', 50, 'done', 1, '2026-09-28 11:09:49.408975+00', NULL, NULL, '2026-09-28 11:09:49.408975+00', '2026-09-28 11:09:50.730311+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (7, 'embed', 'embed:01a0e7b4-edaf-710e-b47e-7429ee49637d:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-edaf-710e-b47e-7429ee49637d"}', 50, 'done', 1, '2026-09-28 11:09:49.408975+00', NULL, NULL, '2026-09-28 11:09:49.408975+00', '2026-09-28 11:09:50.753857+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (17, 'extract', 'extract:01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87:077c9171b456ff74f464bfe4758fe1bc:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87", "window_hash": "077c9171b456ff74f464bfe4758fe1bc"}', 100, 'done', 1, '2026-09-28 11:09:49.49214+00', NULL, NULL, '2026-09-28 11:09:49.49214+00', '2026-09-28 11:09:50.779283+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (12, 'extract', 'extract:01a0e7b4-ee0d-722e-b472-47284937b79b:65839f185668f21bc7e4892a3c5d92b4:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ee0d-722e-b472-47284937b79b", "window_hash": "65839f185668f21bc7e4892a3c5d92b4"}', 100, 'done', 1, '2026-09-28 11:09:49.451528+00', NULL, NULL, '2026-09-28 11:09:49.451528+00', '2026-09-28 11:09:50.802293+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (11, 'extract', 'extract:01a0e7b4-ede4-723b-a7c4-0755c53a942a:a8ee8712b462c3591868120459b6bc59:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ede4-723b-a7c4-0755c53a942a", "window_hash": "a8ee8712b462c3591868120459b6bc59"}', 100, 'done', 1, '2026-09-28 11:09:49.451528+00', NULL, NULL, '2026-09-28 11:09:49.451528+00', '2026-09-28 11:09:50.825061+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (6, 'extract', 'extract:01a0e7b4-ede3-7649-b137-ffab3970c16a:7d62c7bfd48f2767d0809efed686f878:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ede3-7649-b137-ffab3970c16a", "window_hash": "7d62c7bfd48f2767d0809efed686f878"}', 100, 'done', 1, '2026-09-28 11:09:49.408975+00', NULL, NULL, '2026-09-28 11:09:49.408975+00', '2026-09-28 11:09:50.850681+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (5, 'extract', 'extract:01a0e7b4-edaf-710e-b47e-7429ee49637d:e97640e4d4a24190bdd8b6863df117f8:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-edaf-710e-b47e-7429ee49637d", "window_hash": "e97640e4d4a24190bdd8b6863df117f8"}', 100, 'done', 1, '2026-09-28 11:09:49.408975+00', NULL, NULL, '2026-09-28 11:09:49.408975+00', '2026-09-28 11:09:50.872355+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (4, 'embed', 'embed:01a0e7b4-edae-7cc2-85ee-0445a9abeb94:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-edae-7cc2-85ee-0445a9abeb94"}', 150, 'done', 1, '2026-09-28 11:09:49.353327+00', NULL, NULL, '2026-09-28 11:09:49.353327+00', '2026-09-28 11:09:50.892648+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (3, 'embed', 'embed:01a0e7b4-edad-768a-a063-7a1239eb37f2:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-edad-768a-a063-7a1239eb37f2"}', 150, 'done', 1, '2026-09-28 11:09:49.353327+00', NULL, NULL, '2026-09-28 11:09:49.353327+00', '2026-09-28 11:09:50.911406+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (2, 'embed', 'embed:01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23"}', 150, 'done', 1, '2026-09-28 11:09:49.353327+00', NULL, NULL, '2026-09-28 11:09:49.353327+00', '2026-09-28 11:09:50.931269+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (1, 'extract', 'extract:01a0e7b4-edad-768a-a063-7a1239eb37f2:d9071497a0cd7a3b2a707fc39856dfc1:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-edad-768a-a063-7a1239eb37f2", "window_hash": "d9071497a0cd7a3b2a707fc39856dfc1"}', 200, 'done', 1, '2026-09-28 11:09:49.353327+00', NULL, NULL, '2026-09-28 11:09:49.353327+00', '2026-09-28 11:09:50.957175+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (21, 'extract', 'extract:01a0e7b4-ede3-7649-b137-ffab3970c16a:400ff2edac0964189fcb7454658ab5cf:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ede3-7649-b137-ffab3970c16a", "window_hash": "400ff2edac0964189fcb7454658ab5cf"}', 100, 'done', 1, '2026-09-28 11:09:51.045231+00', NULL, NULL, '2026-09-28 11:09:51.045231+00', '2026-09-28 11:09:52.190575+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (20, 'extract', 'extract:01a0e7b4-f446-70ae-a1b0-8f4bb58b088a:765bdc1556d2cdd4fc8611361f344844:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-f446-70ae-a1b0-8f4bb58b088a", "window_hash": "765bdc1556d2cdd4fc8611361f344844"}', 100, 'done', 1, '2026-09-28 11:09:51.045231+00', NULL, NULL, '2026-09-28 11:09:51.045231+00', '2026-09-28 11:09:52.210933+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (33, 'embed', 'embed:01a0e7b4-f496-7547-9ff6-9ba32462ee2a:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-f496-7547-9ff6-9ba32462ee2a"}', 50, 'done', 1, '2026-09-28 11:09:51.12461+00', NULL, NULL, '2026-09-28 11:09:51.12461+00', '2026-09-28 11:09:51.985093+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (32, 'embed', 'embed:01a0e7b4-f496-7cd4-b9d4-d6850d72b649:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-f496-7cd4-b9d4-d6850d72b649"}', 50, 'done', 1, '2026-09-28 11:09:51.12461+00', NULL, NULL, '2026-09-28 11:09:51.12461+00', '2026-09-28 11:09:52.005105+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (27, 'embed', 'embed:01a0e7b4-f447-7fcb-9235-86f78ff1bd3d:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-f447-7fcb-9235-86f78ff1bd3d"}', 50, 'done', 1, '2026-09-28 11:09:51.045231+00', NULL, NULL, '2026-09-28 11:09:51.045231+00', '2026-09-28 11:09:52.023964+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (26, 'embed', 'embed:01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9"}', 50, 'done', 1, '2026-09-28 11:09:51.045231+00', NULL, NULL, '2026-09-28 11:09:51.045231+00', '2026-09-28 11:09:52.043422+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (25, 'embed', 'embed:01a0e7b4-f446-70ae-a1b0-8f4bb58b088a:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-f446-70ae-a1b0-8f4bb58b088a"}', 50, 'done', 1, '2026-09-28 11:09:51.045231+00', NULL, NULL, '2026-09-28 11:09:51.045231+00', '2026-09-28 11:09:52.062635+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (31, 'extract', 'extract:01a0e7b4-f496-7cd4-b9d4-d6850d72b649:eb463bc836e8d04a513f5a8537f465b7:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-f496-7cd4-b9d4-d6850d72b649", "window_hash": "eb463bc836e8d04a513f5a8537f465b7"}', 100, 'done', 1, '2026-09-28 11:09:51.12461+00', NULL, NULL, '2026-09-28 11:09:51.12461+00', '2026-09-28 11:09:52.08947+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (30, 'extract', 'extract:01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9:71c5e25c54638074d9fec975f303cee0:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9", "window_hash": "71c5e25c54638074d9fec975f303cee0"}', 100, 'done', 1, '2026-09-28 11:09:51.12461+00', NULL, NULL, '2026-09-28 11:09:51.12461+00', '2026-09-28 11:09:52.110716+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (29, 'extract', 'extract:01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87:36125a5f886798d8aaa020eeb55272b4:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87", "window_hash": "36125a5f886798d8aaa020eeb55272b4"}', 100, 'done', 1, '2026-09-28 11:09:51.12461+00', NULL, NULL, '2026-09-28 11:09:51.12461+00', '2026-09-28 11:09:52.133078+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (28, 'extract', 'extract:01a0e7b4-ee0d-722e-b472-47284937b79b:ce94b870e4cf07a1b5a99330b7a35330:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ee0d-722e-b472-47284937b79b", "window_hash": "ce94b870e4cf07a1b5a99330b7a35330"}', 100, 'done', 1, '2026-09-28 11:09:51.12461+00', NULL, NULL, '2026-09-28 11:09:51.12461+00', '2026-09-28 11:09:52.154852+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (24, 'extract', 'extract:01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9:d9d9c01034d8e10e48fbd228dda24721:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9", "window_hash": "d9d9c01034d8e10e48fbd228dda24721"}', 100, 'obsolete', 1, '2026-09-28 11:09:51.045231+00', NULL, NULL, '2026-09-28 11:09:51.045231+00', '2026-09-28 11:09:52.158307+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (23, 'extract', 'extract:01a0e7b4-ee0d-722e-b472-47284937b79b:a389c47ee23e08cae196020a9da9d7ee:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ee0d-722e-b472-47284937b79b", "window_hash": "a389c47ee23e08cae196020a9da9d7ee"}', 100, 'obsolete', 1, '2026-09-28 11:09:51.045231+00', NULL, NULL, '2026-09-28 11:09:51.045231+00', '2026-09-28 11:09:52.162065+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (22, 'extract', 'extract:01a0e7b4-ede4-723b-a7c4-0755c53a942a:5c2163dd91f5b6a724896d61dedaf882:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-ede4-723b-a7c4-0755c53a942a", "window_hash": "5c2163dd91f5b6a724896d61dedaf882"}', 100, 'obsolete', 1, '2026-09-28 11:09:51.045231+00', NULL, NULL, '2026-09-28 11:09:51.045231+00', '2026-09-28 11:09:52.165252+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (34, 'extract', 'extract:01a0e7b4-faab-752d-bf21-4a731a2e8061:a90e9ef2054d923d9f0eba05426796c0:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-faab-752d-bf21-4a731a2e8061", "window_hash": "a90e9ef2054d923d9f0eba05426796c0"}', 200, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.417175+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (43, 'embed', 'embed:01a0e7b4-faaf-718f-82f8-9cb1d61591af:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-faaf-718f-82f8-9cb1d61591af"}', 150, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.24071+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (42, 'embed', 'embed:01a0e7b4-faae-7b48-b13f-52c5caa759a5:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-faae-7b48-b13f-52c5caa759a5"}', 150, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.259182+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (41, 'embed', 'embed:01a0e7b4-faae-79dd-8bf1-8e29472f6aae:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-faae-79dd-8bf1-8e29472f6aae"}', 150, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.279852+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (40, 'embed', 'embed:01a0e7b4-faad-751e-9e6d-97ae379ee445:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-faad-751e-9e6d-97ae379ee445"}', 150, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.298049+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (39, 'embed', 'embed:01a0e7b4-faac-7e67-9e9a-60814a5b1670:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-faac-7e67-9e9a-60814a5b1670"}', 150, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.31652+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (38, 'embed', 'embed:01a0e7b4-faab-752d-bf21-4a731a2e8061:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-faab-752d-bf21-4a731a2e8061"}', 150, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.335753+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (37, 'embed', 'embed:01a0e7b4-faaa-7f6a-80f1-8a979367c2b4:embed-160d2f2a8473ac5661dfeb055b1f400f', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "embed-160d2f2a8473ac5661dfeb055b1f400f", "revision_id": "01a0e7b4-faaa-7f6a-80f1-8a979367c2b4"}', 150, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.353688+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (36, 'extract', 'extract:01a0e7b4-faae-7b48-b13f-52c5caa759a5:e32c64e362d4f18261958a123237aa64:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-faae-7b48-b13f-52c5caa759a5", "window_hash": "e32c64e362d4f18261958a123237aa64"}', 200, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.373239+00');
INSERT INTO public.job OVERRIDING SYSTEM VALUE VALUES (35, 'extract', 'extract:01a0e7b4-faad-751e-9e6d-97ae379ee445:caa56c537159d7bb2d3052d1ff356b28:extract-18f6eaa8dcf24b7916dac3bca790d78c', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{"generation": "extract-18f6eaa8dcf24b7916dac3bca790d78c", "revision_id": "01a0e7b4-faad-751e-9e6d-97ae379ee445", "window_hash": "caa56c537159d7bb2d3052d1ff356b28"}', 200, 'done', 1, '2026-09-28 11:09:52.681844+00', NULL, NULL, '2026-09-28 11:09:52.681844+00', '2026-09-28 11:09:53.397312+00');


--
-- Data for Name: observation_base; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.observation_base VALUES ('01a0e7b4-edb0-7f6e-9f41-e1e2533cbf6b', '01a0e7b4-eda4-7f1f-b543-a0b42c101930');


--
-- Data for Name: projection_generation; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.projection_generation VALUES ('extract-18f6eaa8dcf24b7916dac3bca790d78c', 'extract', 'stub', 'http://127.0.0.1:32785/v1', '{"kind": "extract", "unit": "turn", "hints": 40, "model": "stub", "prompt": "7e75e2f51ebbb3a1", "compiler": "extract-v8", "endpoint": "http://127.0.0.1:32785/v1", "json_mode": true, "normalizer": "clean-v2", "predicates": "0cb801b7a0826109", "temperature": 0, "target_chars": 6000, "context_chars": 2000, "context_turns": 3}', '2026-09-28 11:09:49.216821+00', '2026-09-28 11:09:49.222518+00');
INSERT INTO public.projection_generation VALUES ('embed-160d2f2a8473ac5661dfeb055b1f400f', 'embed', 'stub-embed', 'http://127.0.0.1:32785/v1', '{"kind": "embed", "model": "stub-embed", "chunker": "chunk-v1", "endpoint": "http://127.0.0.1:32785/v1", "max_chunks": 8, "normalizer": "clean-v2", "chunk_chars": 700, "document_profile": "plain"}', '2026-09-28 11:09:49.216821+00', '2026-09-28 11:09:49.226253+00');


--
-- Data for Name: retrieval_trace; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-edd7-76c7-9545-341b98eec374', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b', 'Is Rin with you?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b4-edae-7cc2-85ee-0445a9abeb94", "host_logical_id": "b22e7f6d-c0e2-499b-9c71-02e6a53bef53"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 2, "user_score": 1.0, "revision_id": "01a0e7b4-edae-7cc2-85ee-0445a9abeb94", "host_logical_id": "b22e7f6d-c0e2-499b-9c71-02e6a53bef53"}]', 0, '{"embed": 23.7, "facts": 0, "vector": 1.81, "lexical": 3.63, "threads": 0, "extractor": "extract-18f6eaa8dcf2", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 30.89, "embedding_projection": "embed-160d2f2a8473ac"}', 'fresh', '2026-09-28 11:09:49.368292+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-ee02-703d-80f3-85b19e784023', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b', 'Let''s check the market.', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b4-ede3-7ffd-a5ea-26da9b734a24", "host_logical_id": "54da3271-7f1a-42d2-b88e-fc79f2efdaad"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 6, "user_score": 1.0, "revision_id": "01a0e7b4-ede3-7ffd-a5ea-26da9b734a24", "host_logical_id": "54da3271-7f1a-42d2-b88e-fc79f2efdaad"}]', 0, '{"embed": 14.21, "facts": 0, "vector": 1.73, "lexical": 3.24, "threads": 0, "extractor": "extract-18f6eaa8dcf2", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 21.34, "embedding_projection": "embed-160d2f2a8473ac"}', 'fresh', '2026-09-28 11:09:49.421555+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-ee2a-77e9-af27-6d13cf656e13', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b', 'Where do we meet tonight?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b4-ee0e-778b-bedb-3426de63cc2e", "host_logical_id": "ccd66991-40e8-4ccb-b467-c1cfce62ecd0"}]', '[]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 10, "user_score": 1.0, "revision_id": "01a0e7b4-ee0e-778b-bedb-3426de63cc2e", "host_logical_id": "ccd66991-40e8-4ccb-b467-c1cfce62ecd0"}]', 0, '{"embed": 14.16, "facts": 0, "vector": 0.95, "lexical": 2.56, "threads": 0, "extractor": "extract-18f6eaa8dcf2", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 18.89, "embedding_projection": "embed-160d2f2a8473ac"}', 'fresh', '2026-09-28 11:09:49.464137+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-ee52-759e-8e7d-92f9ca4341e3', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b', 'Where is Mina now?', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b4-ee35-7aa0-9a98-3e826b15cc10", "host_logical_id": "24319f0f-127a-4149-b780-59083977f410"}, {"rrf": 0.01613, "sim": null, "score": 0.4444, "position": 3, "user_score": 0.4444, "revision_id": "01a0e7b4-edaf-710e-b47e-7429ee49637d", "host_logical_id": "b9086fbc-6eeb-4657-a0da-cb0a06777db5"}, {"rrf": 0.01587, "sim": null, "score": 0.4444, "position": 1, "user_score": 0.4444, "revision_id": "01a0e7b4-edad-768a-a063-7a1239eb37f2", "host_logical_id": "f4232d50-a0c9-41d8-b632-0eb358382e07"}]', '[{"turn": 1, "score": 0.01587, "revision_id": "01a0e7b4-edad-768a-a063-7a1239eb37f2"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b4-edaf-710e-b47e-7429ee49637d"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 12, "user_score": 1.0, "revision_id": "01a0e7b4-ee35-7aa0-9a98-3e826b15cc10", "host_logical_id": "24319f0f-127a-4149-b780-59083977f410"}]', 174, '{"embed": 16.23, "facts": 0, "vector": 1.56, "lexical": 2.77, "threads": 0, "extractor": "extract-18f6eaa8dcf2", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 22.28, "embedding_projection": "embed-160d2f2a8473ac"}', 'fresh', '2026-09-28 11:09:49.500519+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-f467-737a-a1b8-1363419f7330', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '01a0e7b4-f44b-7030-a7d2-4d09831733f5', 'And the compass?', '[{"rrf": 0.03128, "sim": 0.2407, "score": 0.75, "position": 9, "user_score": 0.75, "revision_id": "01a0e7b4-ee0d-722e-b472-47284937b79b", "host_logical_id": "654c12f1-85cc-41cd-995c-1fe08fb40614"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b4-f447-7fcb-9235-86f78ff1bd3d", "host_logical_id": "3a262e2c-b2b2-4191-bc0c-c6539d90acd1"}, {"rrf": 0.01639, "sim": 0.7934, "score": 0.0, "position": 1, "user_score": 0.0, "revision_id": "01a0e7b4-edad-768a-a063-7a1239eb37f2", "host_logical_id": "f4232d50-a0c9-41d8-b632-0eb358382e07"}, {"rrf": 0.01613, "sim": 0.6967, "score": 0.0, "position": 0, "user_score": 0.0, "revision_id": "01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23", "host_logical_id": "7e43bffb-482f-4939-86ef-1fa8edda8b5f"}, {"rrf": 0.01587, "sim": 0.6691, "score": 0.0, "position": 7, "user_score": 0.0, "revision_id": "01a0e7b4-ede4-723b-a7c4-0755c53a942a", "host_logical_id": "f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40"}, {"rrf": 0.01562, "sim": 0.4307, "score": 0.0, "position": 5, "user_score": 0.0, "revision_id": "01a0e7b4-ede3-7649-b137-ffab3970c16a", "host_logical_id": "09d0130f-1641-4848-85e1-2d20445c08b2"}]', '[{"turn": 0, "score": 0.01613, "revision_id": "01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23"}, {"turn": 1, "score": 0.01639, "revision_id": "01a0e7b4-edad-768a-a063-7a1239eb37f2"}, {"turn": 5, "score": 0.01562, "revision_id": "01a0e7b4-ede3-7649-b137-ffab3970c16a"}, {"turn": 7, "score": 0.01587, "revision_id": "01a0e7b4-ede4-723b-a7c4-0755c53a942a"}, {"turn": 9, "score": 0.03128, "revision_id": "01a0e7b4-ee0d-722e-b472-47284937b79b"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b4-f447-7fcb-9235-86f78ff1bd3d", "host_logical_id": "3a262e2c-b2b2-4191-bc0c-c6539d90acd1"}]', 252, '{"embed": 16.04, "facts": 0, "vector": 1.26, "lexical": 2.95, "threads": 0, "extractor": "extract-18f6eaa8dcf2", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 21.98, "embedding_projection": "embed-160d2f2a8473ac"}', 'fresh', '2026-09-28 11:09:51.057648+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-f48c-7fbd-9b43-884feaa06d9d', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '01a0e7b4-f44b-7030-a7d2-4d09831733f5', 'compass', '[{"rrf": 0.03002, "sim": -0.5878, "score": 1.0, "position": 9, "user_score": 1.0, "revision_id": "01a0e7b4-ee0d-722e-b472-47284937b79b", "host_logical_id": "654c12f1-85cc-41cd-995c-1fe08fb40614"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b4-f447-7fcb-9235-86f78ff1bd3d", "host_logical_id": "3a262e2c-b2b2-4191-bc0c-c6539d90acd1"}, {"rrf": 0.01639, "sim": 0.4581, "score": 0.0, "position": 11, "user_score": 0.0, "revision_id": "01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87", "host_logical_id": "d1f36a29-0a86-4824-b4ed-76a9f0b26e54"}]', '[{"turn": 9, "score": 0.03002, "revision_id": "01a0e7b4-ee0d-722e-b472-47284937b79b"}, {"turn": 11, "score": 0.01639, "revision_id": "01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 14, "user_score": 1.0, "revision_id": "01a0e7b4-f447-7fcb-9235-86f78ff1bd3d", "host_logical_id": "3a262e2c-b2b2-4191-bc0c-c6539d90acd1"}]', 171, '{"embed": 14.19, "facts": 0, "vector": 1.11, "lexical": 2.63, "threads": 0, "extractor": "extract-18f6eaa8dcf2", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 19.33, "embedding_projection": "embed-160d2f2a8473ac"}', 'fresh', '2026-09-28 11:09:51.096995+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-f4b2-7f6b-b4c1-141dbb5afe8a', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '01a0e7b4-f499-765d-89aa-c9bd070b972d', 'Let''s go.', '[{"rrf": 0.03252, "sim": 0.5775, "score": 0.6667, "position": 6, "user_score": 0.6667, "revision_id": "01a0e7b4-ede3-7ffd-a5ea-26da9b734a24", "host_logical_id": "54da3271-7f1a-42d2-b88e-fc79f2efdaad"}, {"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b4-f496-7547-9ff6-9ba32462ee2a", "host_logical_id": "ab2f10fe-0082-4c2d-8496-0e884fb2d35f"}]', '[{"turn": 6, "score": 0.03252, "revision_id": "01a0e7b4-ede3-7ffd-a5ea-26da9b734a24"}]', '[{"rrf": 0.01639, "sim": null, "score": 1.0, "position": 16, "user_score": 1.0, "revision_id": "01a0e7b4-f496-7547-9ff6-9ba32462ee2a", "host_logical_id": "ab2f10fe-0082-4c2d-8496-0e884fb2d35f"}]', 138, '{"embed": 14.37, "facts": 0, "vector": 0.88, "lexical": 2.97, "threads": 0, "extractor": "extract-18f6eaa8dcf2", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 19.78, "embedding_projection": "embed-160d2f2a8473ac"}', 'fresh', '2026-09-28 11:09:51.135246+00');
INSERT INTO public.retrieval_trace VALUES ('01a0e7b4-facb-7a5d-8d99-9401ee6a1bce', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 'Where is Rin?', '[{"rrf": 0.01639, "sim": null, "score": 0.6154, "position": 2, "user_score": 0.6154, "revision_id": "01a0e7b4-faac-7e67-9e9a-60814a5b1670", "host_logical_id": "f14dab15-9ba7-4200-b101-14282be57d98"}, {"rrf": 0.01613, "sim": null, "score": 0.5385, "position": 3, "user_score": 0.5385, "revision_id": "01a0e7b4-faad-751e-9e6d-97ae379ee445", "host_logical_id": "0a81f9a2-b5b3-491a-b7a8-576ee19d9c77"}]', '[{"turn": 2, "score": 0.01639, "revision_id": "01a0e7b4-faac-7e67-9e9a-60814a5b1670"}, {"turn": 3, "score": 0.01613, "revision_id": "01a0e7b4-faad-751e-9e6d-97ae379ee445"}]', '[]', 164, '{"embed": 15.87, "facts": 0, "vector": 0.88, "lexical": 2.91, "threads": 0, "extractor": "extract-18f6eaa8dcf2", "state_items": 0, "vector_mode": "on", "lexical_mode": "on", "sidecar_total": 21.08, "embedding_projection": "embed-160d2f2a8473ac"}', 'fresh', '2026-09-28 11:09:52.694977+00');


--
-- Data for Name: revision_embedding; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ee35-7aa0-9a98-3e826b15cc10', 'stub-embed', 0, 8, 0, 18, '[-0.233931,-0.15847,0.586086,0.1635,-0.173562,0.465347,-0.0729463,-0.54584]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87', 'stub-embed', 0, 8, 0, 29, '[0.271687,-0.046505,-0.433231,0.257001,0.565403,0.0905623,-0.183572,-0.555612]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ee0e-778b-bedb-3426de63cc2e', 'stub-embed', 0, 8, 0, 25, '[-0.241049,0.405869,-0.381146,0.0473857,-0.265772,0.455315,0.364664,-0.467677]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ee0d-722e-b472-47284937b79b', 'stub-embed', 0, 8, 0, 53, '[0.0115691,0.590025,-0.354015,-0.340132,-0.247579,-0.0347073,-0.391036,-0.44194]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ee0c-77cf-990f-76123938a7a4', 'stub-embed', 0, 8, 0, 25, '[-0.163073,-0.203126,-0.529272,-0.140186,-0.0658014,0.391947,-0.512106,-0.46061]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ede4-723b-a7c4-0755c53a942a', 'stub-embed', 0, 8, 0, 35, '[0.393995,0.322822,0.521091,0.521091,0.0432124,0.317738,0.307571,0.00762572]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ede3-7ffd-a5ea-26da9b734a24', 'stub-embed', 0, 8, 0, 23, '[0.190974,-0.374309,0.384494,-0.33866,-0.0738432,0.231715,-0.5882,0.394679]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ede3-7649-b137-ffab3970c16a', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-ede1-79be-8cff-42aed7411c94', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-edaf-710e-b47e-7429ee49637d', 'stub-embed', 0, 8, 0, 45, '[0.00244447,-0.422893,-0.422893,0.30067,-0.0268892,0.540228,0.418004,0.290892]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-edae-7cc2-85ee-0445a9abeb94', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-edad-768a-a063-7a1239eb37f2', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-f496-7547-9ff6-9ba32462ee2a', 'stub-embed', 0, 8, 0, 9, '[0.431965,-0.245728,0.0181063,0.380232,-0.406098,0.230209,-0.540602,0.31298]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-f496-7cd4-b9d4-d6850d72b649', 'stub-embed', 0, 8, 0, 27, '[-0.383691,0.28722,-0.370536,-0.0898933,-0.120589,0.550322,-0.225829,0.506472]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-f447-7fcb-9235-86f78ff1bd3d', 'stub-embed', 0, 8, 0, 16, '[0.543079,0.579113,0.239367,0.0694935,0.393797,0.321729,-0.0334598,-0.218776]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9', 'stub-embed', 0, 8, 0, 31, '[-0.366575,0.115356,-0.176879,-0.45886,-0.433225,-0.238402,-0.146117,-0.587033]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-f446-70ae-a1b0-8f4bb58b088a', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-faaf-718f-82f8-9cb1d61591af', 'stub-embed', 0, 8, 0, 24, '[0.162346,-0.189033,-0.527068,-0.406976,-0.309124,-0.340259,-0.233511,0.478142]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-faae-7b48-b13f-52c5caa759a5', 'stub-embed', 0, 8, 0, 53, '[0.301112,0.390946,0.281149,-0.417564,-0.367656,0.221259,0.390946,-0.407582]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-faae-79dd-8bf1-8e29472f6aae', 'stub-embed', 0, 8, 0, 34, '[-0.527883,-0.229689,-0.648772,0.0523853,-0.0765631,0.302223,0.33446,-0.189393]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-faad-751e-9e6d-97ae379ee445', 'stub-embed', 0, 8, 0, 48, '[0.293462,-0.419512,-0.395878,-0.238315,-0.187107,0.321035,0.454964,-0.423452]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-faac-7e67-9e9a-60814a5b1670', 'stub-embed', 0, 8, 0, 16, '[-0.200389,-0.403031,0.385018,0.0788048,0.398527,-0.461571,0.240918,-0.461571]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-faab-752d-bf21-4a731a2e8061', 'stub-embed', 0, 8, 0, 50, '[0.608081,0.251967,-0.0839891,0.104147,0.359474,0.245248,0.258687,-0.54089]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');
INSERT INTO public.revision_embedding VALUES ('01a0e7b4-faaa-7f6a-80f1-8a979367c2b4', 'stub-embed', 0, 8, 0, 30, '[0.40009,0.258882,0.626023,-0.211812,0.10826,0.550712,-0.0706041,0.127087]', 'embed-160d2f2a8473ac5661dfeb055b1f400f');


--
-- Data for Name: revision_text; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.revision_text VALUES ('01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23', 'clean-v2', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:09:49.353327+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-edad-768a-a063-7a1239eb37f2', 'clean-v2', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:09:49.353327+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-edae-7cc2-85ee-0445a9abeb94', 'clean-v2', 'Is Rin with you?', 16, 16, '2026-09-28 11:09:49.353327+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-edaf-710e-b47e-7429ee49637d', 'clean-v2', 'Rin is Mina''s sister. Rin went to the harbor.', 45, 45, '2026-09-28 11:09:49.353327+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ede1-79be-8cff-42aed7411c94', 'clean-v2', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:09:49.408975+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ede3-7649-b137-ffab3970c16a', 'clean-v2', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:09:49.408975+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ede3-7ffd-a5ea-26da9b734a24', 'clean-v2', 'Let''s check the market.', 23, 23, '2026-09-28 11:09:49.408975+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ede4-723b-a7c4-0755c53a942a', 'clean-v2', 'Idle reply about lanterns and rain.', 35, 35, '2026-09-28 11:09:49.408975+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ee0c-77cf-990f-76123938a7a4', 'clean-v2', 'Any news from the harbor?', 25, 25, '2026-09-28 11:09:49.451528+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ee0d-722e-b472-47284937b79b', 'clean-v2', 'Rin has the silver compass. The gulls are loud today.', 53, 53, '2026-09-28 11:09:49.451528+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ee0e-778b-bedb-3426de63cc2e', 'clean-v2', 'Where do we meet tonight?', 25, 25, '2026-09-28 11:09:49.451528+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87', 'clean-v2', 'Mina moved to the bell tower.', 29, 29, '2026-09-28 11:09:49.451528+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-ee35-7aa0-9a98-3e826b15cc10', 'clean-v2', 'Where is Mina now?', 18, 18, '2026-09-28 11:09:49.49214+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-f446-70ae-a1b0-8f4bb58b088a', 'clean-v2', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:09:51.045231+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9', 'clean-v2', 'Mina keeps the brass key close.', 31, 31, '2026-09-28 11:09:51.045231+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-f447-7fcb-9235-86f78ff1bd3d', 'clean-v2', 'And the compass?', 16, 16, '2026-09-28 11:09:51.045231+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-f471-7d5f-a10f-1be07ae2f2a1', 'clean-v2', 'Rin carries the silver compass and a map.', 41, 41, '2026-09-28 11:09:51.088043+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-f495-7ee1-827a-a97347dab3da', 'clean-v2', 'Any news from the harbor?', 25, 25, '2026-09-28 11:09:51.12461+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-f496-7cd4-b9d4-d6850d72b649', 'clean-v2', 'Rin has the silver compass.', 27, 27, '2026-09-28 11:09:51.12461+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-f496-7547-9ff6-9ba32462ee2a', 'clean-v2', 'Let''s go.', 9, 9, '2026-09-28 11:09:51.12461+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-faaa-7f6a-80f1-8a979367c2b4', 'clean-v2', 'We should rest somewhere safe.', 30, 30, '2026-09-28 11:09:52.681844+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-faab-752d-bf21-4a731a2e8061', 'clean-v2', 'Mina is in the old chapel. Mina has the brass key.', 50, 50, '2026-09-28 11:09:52.681844+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-faac-7e67-9e9a-60814a5b1670', 'clean-v2', 'Is Rin with you?', 16, 16, '2026-09-28 11:09:52.681844+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-faad-751e-9e6d-97ae379ee445', 'clean-v2', 'Rin is Mina''s rival. Rin went to the lighthouse.', 48, 48, '2026-09-28 11:09:52.681844+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-faae-79dd-8bf1-8e29472f6aae', 'clean-v2', 'What did Mina say before she left?', 34, 34, '2026-09-28 11:09:52.681844+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-faae-7b48-b13f-52c5caa759a5', 'clean-v2', 'Mina promised Takumi to return before the bell rings.', 53, 53, '2026-09-28 11:09:52.681844+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-faaf-7356-9417-23637addc0a7', 'clean-v2', '{{specialcomment::branchedfrom::ecb64de9-5dc4-49a8-acd7-5316b07991d7::Harbor route::09d0130f-1641-4848-85e1-2d20445c08b2::}}', 124, 124, '2026-09-28 11:09:52.681844+00');
INSERT INTO public.revision_text VALUES ('01a0e7b4-faaf-718f-82f8-9cb1d61591af', 'clean-v2', 'Rin moved to the market.', 24, 24, '2026-09-28 11:09:52.681844+00');


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.schema_migrations VALUES ('0001_source_layer.sql', '638e0ec52a7b07c84c59ba26bdf0cfe108aa1cb87898c7e53c4e2c9ad23c2cd8', '2026-09-28 11:09:48.436296+00');
INSERT INTO public.schema_migrations VALUES ('0002_state_observation.sql', '72c74bf739dd90c171dfd3dba1294bd794ca307e706a9e6850bc9ae4e6a16cae', '2026-09-28 11:09:48.518585+00');
INSERT INTO public.schema_migrations VALUES ('0003_extraction.sql', '587f4232c0b552a1139df319d90a3fb53a84d21800660d8b4ceb7b4b969b4e93', '2026-09-28 11:09:48.542255+00');
INSERT INTO public.schema_migrations VALUES ('0004_embeddings.sql', '3d4afb7f842fb9d86be9ab56ee983f892be535f3fe5ef4c719eb9e342e052704', '2026-09-28 11:09:48.583713+00');
INSERT INTO public.schema_migrations VALUES ('0005_app_config.sql', '8a563690e0c87d333a08d33686bd47108c32876b3e2f357b82cfdc7bf9c796f6', '2026-09-28 11:09:48.603959+00');
INSERT INTO public.schema_migrations VALUES ('0006_knowledge.sql', 'deed697a1ca758ebf0e23a47df9a0d922a0714e0501ab5870cd6883dd16e897f', '2026-09-28 11:09:48.612841+00');
INSERT INTO public.schema_migrations VALUES ('0007_normalized_text.sql', 'ba1b4656ce595f7c9d471d20137b603fbca6d3a52f63184d1b63d863d231aecc', '2026-09-28 11:09:48.614514+00');
INSERT INTO public.schema_migrations VALUES ('0008_projection_generations.sql', 'a18c2870dcaec3d5fec05b2a2def6def74e0e377eb7d69a6fbdd00cc0232d7ae', '2026-09-28 11:09:48.624415+00');
INSERT INTO public.schema_migrations VALUES ('0009_knowledge_scope.sql', '01f8c241a3a760f9caf982eee64192cfa6c10cc30dc075cafda95328cbf1f156', '2026-09-28 11:09:48.64095+00');
INSERT INTO public.schema_migrations VALUES ('0010_conversation_labels.sql', 'eae4508050525090580b6451ee84eb1755385cbf9c6c44f3cc095934a355717a', '2026-09-28 11:09:48.642887+00');
INSERT INTO public.schema_migrations VALUES ('0011_turn_extraction.sql', '5e88ea510bf25d241f2304260bf43983a7060c93daef03f920d697d2b520d25f', '2026-09-28 11:09:48.644585+00');
INSERT INTO public.schema_migrations VALUES ('0012_conversation_delete.sql', '055e219a5ddc27f17442ab0961aca9c6201a0c6d4b44819849ef23ebff175fde', '2026-09-28 11:09:48.65323+00');
INSERT INTO public.schema_migrations VALUES ('0013_worldline_append.sql', 'cf5882dbc0f25785ef7fed2ab6feaa6b90989cdbda2345364aba6bf5c16b0a82', '2026-09-28 11:09:48.678488+00');
INSERT INTO public.schema_migrations VALUES ('0014_assertion_semantics.sql', 'e8bcdb0ac0c70040dc0ccfb120ef7cb1ebc238ea2fba64cd49fcab3a427b4e7b', '2026-09-28 11:09:48.694284+00');
INSERT INTO public.schema_migrations VALUES ('0015_observation_compaction.sql', '80b08845a8dae426f83ea49628277cd2debb89477432cea0e8389ac5b718aa65', '2026-09-28 11:09:48.696727+00');
INSERT INTO public.schema_migrations VALUES ('0016_event_salience.sql', 'abe34caf31f5c86893ac8ecadc3cc043f5f224ddec913f932a83bc950e715dac', '2026-09-28 11:09:48.708749+00');
INSERT INTO public.schema_migrations VALUES ('0017_assertion_participants.sql', '03e762f36f8309f34363f15b9808ae47a761c41147d0e7bbd55eb969845b8843', '2026-09-28 11:09:48.710462+00');
INSERT INTO public.schema_migrations VALUES ('0018_conversation_persona.sql', '36b797a79bccc3c1d6d1bcd46532cd1060c9e1044faca6ae90d53552df8a2b0e', '2026-09-28 11:09:48.712092+00');


--
-- Data for Name: source_object; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_object VALUES ('01a0e7b4-edaa-7c01-9e5d-6197ee3c902d', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '7e43bffb-482f-4939-86ef-1fa8edda8b5f', 'message', '2026-09-28 11:09:49.353327+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-edad-7139-b3b9-7bb052f5c867', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'f4232d50-a0c9-41d8-b632-0eb358382e07', 'message', '2026-09-28 11:09:49.353327+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-edae-76c0-838f-1c941b0d66b2', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'b22e7f6d-c0e2-499b-9c71-02e6a53bef53', 'message', '2026-09-28 11:09:49.353327+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-edaf-7b16-a443-aa4c14fdd7d0', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'b9086fbc-6eeb-4657-a0da-cb0a06777db5', 'message', '2026-09-28 11:09:49.353327+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ede1-7fbb-9808-ea2a9f9a4909', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '6b8c231f-f49e-4e1c-bee1-97f36fe8c537', 'message', '2026-09-28 11:09:49.408975+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ede2-786a-8e41-d1add91e5d62', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '09d0130f-1641-4848-85e1-2d20445c08b2', 'message', '2026-09-28 11:09:49.408975+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ede3-77fe-b24b-67e736214a7f', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '54da3271-7f1a-42d2-b88e-fc79f2efdaad', 'message', '2026-09-28 11:09:49.408975+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ede4-72f2-88e8-554f8bfb4f56', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40', 'message', '2026-09-28 11:09:49.408975+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ee0c-738b-bae3-fa43353f6367', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '4da88bf2-78f7-4292-b2c6-86e376e71964', 'message', '2026-09-28 11:09:49.451528+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ee0d-76be-94c1-d0b5f2536b17', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '654c12f1-85cc-41cd-995c-1fe08fb40614', 'message', '2026-09-28 11:09:49.451528+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ee0e-724c-b44e-e4a8127a3dd6', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'ccd66991-40e8-4ccb-b467-c1cfce62ecd0', 'message', '2026-09-28 11:09:49.451528+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ee0f-706e-b04b-9d37f04bb7f1', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'd1f36a29-0a86-4824-b4ed-76a9f0b26e54', 'message', '2026-09-28 11:09:49.451528+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-ee34-7864-8511-117e5a4e22e6', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '24319f0f-127a-4149-b780-59083977f410', 'message', '2026-09-28 11:09:49.49214+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-f446-7da0-a899-096173cff8f4', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '61789a3c-a601-4f30-94f6-4c53ad38be8d', 'message', '2026-09-28 11:09:51.045231+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-f447-759d-8e3c-578cd7abd95c', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '3a262e2c-b2b2-4191-bc0c-c6539d90acd1', 'message', '2026-09-28 11:09:51.045231+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-f470-79d7-8c44-812c18babcde', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '0a31a3d5-e10b-401d-8a4f-c36ce85da8a1', 'message', '2026-09-28 11:09:51.088043+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-f496-7544-a763-0bd6b64cb9c0', '01a0e7b4-eda4-7f1f-b543-a0b42c101930', 'ab2f10fe-0082-4c2d-8496-0e884fb2d35f', 'message', '2026-09-28 11:09:51.12461+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-faaa-7e0b-a760-77a86959d11c', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '59f0d7f8-ed76-48c0-a601-49aaa09000cb', 'message', '2026-09-28 11:09:52.681844+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-faab-76bb-8763-7991b2c2836b', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', 'e0ab75cc-48fe-4a2d-bb7c-6720c4c753e8', 'message', '2026-09-28 11:09:52.681844+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-faac-738a-b558-d8180f1e43b5', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', 'f14dab15-9ba7-4200-b101-14282be57d98', 'message', '2026-09-28 11:09:52.681844+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-faac-70bf-bde9-585c313b95b9', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '0a81f9a2-b5b3-491a-b7a8-576ee19d9c77', 'message', '2026-09-28 11:09:52.681844+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-faad-7c89-bfb3-bd88746d2c87', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '1e858747-f428-46c4-b2dd-f01a4f534ad6', 'message', '2026-09-28 11:09:52.681844+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-faae-78e9-bcb8-5aa9ad7bb366', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', 'c91a2a09-ad4e-49ba-a8b3-8b0602cef307', 'message', '2026-09-28 11:09:52.681844+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-faaf-7ff9-88ff-f308526a9f51', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '24261722-e908-4c75-9092-0547ad1f3cd6', 'message', '2026-09-28 11:09:52.681844+00');
INSERT INTO public.source_object VALUES ('01a0e7b4-faaf-7619-9a05-d62cbe630ca5', '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '4e359d4d-f2dc-45f3-8e80-d3c921af8f71', 'message', '2026-09-28 11:09:52.681844+00');


--
-- Data for Name: source_revision; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.source_revision VALUES ('01a0e7b4-edab-7ca4-b8a8-b6230d3dfb23', '01a0e7b4-edaa-7c01-9e5d-6197ee3c902d', '062e6a45e1dc047b3c9df81b154f32cae60873107b5d20e78c24a872e16c8674', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "7e43bffb-482f-4939-86ef-1fa8edda8b5f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:49.353327+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-edae-7cc2-85ee-0445a9abeb94', '01a0e7b4-edae-76c0-838f-1c941b0d66b2', '5b9325e3b5b11a47c2cf7934fabfb36191cb37641f0cc192f12c6d56c54f59a5', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "b22e7f6d-c0e2-499b-9c71-02e6a53bef53", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:49.353327+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-edad-768a-a063-7a1239eb37f2', '01a0e7b4-edad-7139-b3b9-7bb052f5c867', '497f7626ea4e8090434592902bb3833caece890715d78436a944f18a9ba9866a', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "f4232d50-a0c9-41d8-b632-0eb358382e07", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "f4232d50-a0c9-41d8-b632-0eb358382e07", "specialComments": []}', '2026-09-28 11:09:49.353327+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ede1-79be-8cff-42aed7411c94', '01a0e7b4-ede1-7fbb-9808-ea2a9f9a4909', '654b3588a0b6c119ebe8ab25d4a4ef7d1ea5f9d3c67729e496ef216c129786ac', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "6b8c231f-f49e-4e1c-bee1-97f36fe8c537", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:49.408975+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ede3-7ffd-a5ea-26da9b734a24', '01a0e7b4-ede3-77fe-b24b-67e736214a7f', '1ccdc6fc667881ef62284e0b894d817bc0cc1092c0cfc38c7a49cc0a195e2f79', 'Let''s check the market.', '{"name": null, "role": "user", "chatId": "54da3271-7f1a-42d2-b88e-fc79f2efdaad", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:49.408975+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ede3-7649-b137-ffab3970c16a', '01a0e7b4-ede2-786a-8e41-d1add91e5d62', 'c0f342afaa4ed5242523a6948a420d4dea59a59c4e163417dde013f7e6d1bf5b', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "09d0130f-1641-4848-85e1-2d20445c08b2", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "09d0130f-1641-4848-85e1-2d20445c08b2", "specialComments": []}', '2026-09-28 11:09:49.408975+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ee0e-778b-bedb-3426de63cc2e', '01a0e7b4-ee0e-724c-b44e-e4a8127a3dd6', '41a770b984cce35df3230443c5e3291d3e494542bfe6ee785af62f75913657eb', 'Where do we meet tonight?', '{"name": null, "role": "user", "chatId": "ccd66991-40e8-4ccb-b467-c1cfce62ecd0", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:49.451528+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ee0d-722e-b472-47284937b79b', '01a0e7b4-ee0d-76be-94c1-d0b5f2536b17', 'b9ff7953631888fdb2f2ed0e606f5879c42fe5e47846f04c81748d833e6376f9', 'Rin has the silver compass. The gulls are loud today.', '{"name": null, "role": "char", "chatId": "654c12f1-85cc-41cd-995c-1fe08fb40614", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "654c12f1-85cc-41cd-995c-1fe08fb40614", "specialComments": []}', '2026-09-28 11:09:49.451528+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ede4-723b-a7c4-0755c53a942a', '01a0e7b4-ede4-72f2-88e8-554f8bfb4f56', '298cd3a38869a060ee34def836275b751d1b81f977bea83fc0239e8f76f78311', 'Idle reply about lanterns and rain.', '{"name": null, "role": "char", "chatId": "f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", "specialComments": []}', '2026-09-28 11:09:49.408975+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ee35-7aa0-9a98-3e826b15cc10', '01a0e7b4-ee34-7864-8511-117e5a4e22e6', '3dfbe939779b60c1d27fd8ad972b2341ac783cfce4e05b8da7f2e9d967997e08', 'Where is Mina now?', '{"name": null, "role": "user", "chatId": "24319f0f-127a-4149-b780-59083977f410", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:49.49214+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ee0f-7804-9a5c-6d7f96c9eb87', '01a0e7b4-ee0f-706e-b04b-9d37f04bb7f1', 'd48ed942168ba30643de9f89ad2dfce9512281de9093342ce44929f986d4681f', 'Mina moved to the bell tower.', '{"name": null, "role": "char", "chatId": "d1f36a29-0a86-4824-b4ed-76a9f0b26e54", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "d1f36a29-0a86-4824-b4ed-76a9f0b26e54", "specialComments": []}', '2026-09-28 11:09:49.451528+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-f447-7fcb-9235-86f78ff1bd3d', '01a0e7b4-f447-759d-8e3c-578cd7abd95c', '709879d5affa7031ad359a76c0af8ec5d8fd96ff6cb1c6101bb74e8a7b8c890c', 'And the compass?', '{"name": null, "role": "user", "chatId": "3a262e2c-b2b2-4191-bc0c-c6539d90acd1", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:51.045231+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-f447-7f7e-8df2-eddd4ca7d7d9', '01a0e7b4-f446-7da0-a899-096173cff8f4', '2be3e9bbd99d7ce8af66bb2e7160bb43fa1fa8ee46ec7fd157c1e9fd33eba171', 'Mina keeps the brass key close.', '{"name": null, "role": "char", "chatId": "61789a3c-a601-4f30-94f6-4c53ad38be8d", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "61789a3c-a601-4f30-94f6-4c53ad38be8d", "specialComments": []}', '2026-09-28 11:09:51.045231+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-edaf-710e-b47e-7429ee49637d', '01a0e7b4-edaf-7b16-a443-aa4c14fdd7d0', '418c25808b62d0d3533fdb7aa5b568f0bb93998a54cc210ca8b8ff12a3681e4e', 'Rin is Mina''s sister. Rin went to the harbor.', '{"name": null, "role": "char", "chatId": "b9086fbc-6eeb-4657-a0da-cb0a06777db5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b9086fbc-6eeb-4657-a0da-cb0a06777db5", "specialComments": []}', '2026-09-28 11:09:49.353327+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-f471-7d5f-a10f-1be07ae2f2a1', '01a0e7b4-f470-79d7-8c44-812c18babcde', 'fffb37f0673f1a8170f446e52318ba8fbe3743356edb48a745f2da2653955d3f', 'Rin carries the silver compass and a map.', '{"name": null, "role": "char", "chatId": "0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "saying": null, "swipeId": 1, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "specialComments": []}', '2026-09-28 11:09:51.088043+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-ee0c-77cf-990f-76123938a7a4', '01a0e7b4-ee0c-738b-bae3-fa43353f6367', '9795c392926d5c63fe7a0588302d90be8ea002cdb5241b811f25eff30ef61f53', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "4da88bf2-78f7-4292-b2c6-86e376e71964", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:49.451528+00', 'superseded', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-faaa-7f6a-80f1-8a979367c2b4', '01a0e7b4-faaa-7e0b-a760-77a86959d11c', 'c7f83db81d06934ffdf021857d2632e671d24cc1df6b1504730ce91262ecf4a6', 'We should rest somewhere safe.', '{"name": null, "role": "user", "chatId": "59f0d7f8-ed76-48c0-a601-49aaa09000cb", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:52.681844+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-f446-70ae-a1b0-8f4bb58b088a', '01a0e7b4-edaf-7b16-a443-aa4c14fdd7d0', 'e34bca87e8c8690b498e47cb05a90fea0f5ed83b5f1fafd8fdb146462d115b02', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "b9086fbc-6eeb-4657-a0da-cb0a06777db5", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b9086fbc-6eeb-4657-a0da-cb0a06777db5", "specialComments": []}', '2026-09-28 11:09:51.045231+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-f495-7ee1-827a-a97347dab3da', '01a0e7b4-ee0c-738b-bae3-fa43353f6367', '0b3d75dd50bc6adbdb57bbf0c251249bcf30362be0427240748e0a12b76f09c6', 'Any news from the harbor?', '{"name": null, "role": "user", "chatId": "4da88bf2-78f7-4292-b2c6-86e376e71964", "saying": null, "swipeId": null, "disabled": true, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:51.12461+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-f496-7547-9ff6-9ba32462ee2a', '01a0e7b4-f496-7544-a763-0bd6b64cb9c0', '0fcbee8bf86b1dcee91fe2d3b202fd900331756214e57ad0571e2e7773f9f202', 'Let''s go.', '{"name": null, "role": "user", "chatId": "ab2f10fe-0082-4c2d-8496-0e884fb2d35f", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:51.12461+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-f496-7cd4-b9d4-d6850d72b649', '01a0e7b4-f470-79d7-8c44-812c18babcde', 'e2cbc0421b2dcc4c5f63be6e537df7d177484c4c4c1513eeb28c36136b970e77', 'Rin has the silver compass.', '{"name": null, "role": "char", "chatId": "0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "saying": null, "swipeId": 0, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 2, "generationId": "0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "specialComments": []}', '2026-09-28 11:09:51.12461+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-faac-7e67-9e9a-60814a5b1670', '01a0e7b4-faac-738a-b558-d8180f1e43b5', 'a25a03b58d70062aab7cb6610bb00514f9de4a66ae1837dddf817cf3befc1778', 'Is Rin with you?', '{"name": null, "role": "user", "chatId": "f14dab15-9ba7-4200-b101-14282be57d98", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:52.681844+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-faae-79dd-8bf1-8e29472f6aae', '01a0e7b4-faad-7c89-bfb3-bd88746d2c87', '8294caf5be1f2fb7f4922e0de6e7ad4adca06bc04fe47f9896ae342fc890729f', 'What did Mina say before she left?', '{"name": null, "role": "user", "chatId": "1e858747-f428-46c4-b2dd-f01a4f534ad6", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:52.681844+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-faaf-7356-9417-23637addc0a7', '01a0e7b4-faaf-7ff9-88ff-f308526a9f51', '4381be6dc747e55e6f1a5aaddab356884481378b62ccd1ac36396bae35500cbc', '{{specialcomment::branchedfrom::ecb64de9-5dc4-49a8-acd7-5316b07991d7::Harbor route::09d0130f-1641-4848-85e1-2d20445c08b2::}}', '{"name": null, "role": "char", "chatId": "24261722-e908-4c75-9092-0547ad1f3cd6", "saying": null, "swipeId": null, "disabled": true, "isComment": true, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": ["{{specialcomment::branchedfrom::ecb64de9-5dc4-49a8-acd7-5316b07991d7::Harbor route::09d0130f-1641-4848-85e1-2d20445c08b2::}}"]}', '2026-09-28 11:09:52.681844+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-faaf-718f-82f8-9cb1d61591af', '01a0e7b4-faaf-7619-9a05-d62cbe630ca5', 'aed37c6d8df03f47fbd923e4aaa9a9949680d5e303b20ecb2edee747b536e28d', 'Rin moved to the market.', '{"name": null, "role": "user", "chatId": "4e359d4d-f2dc-45f3-8e80-d3c921af8f71", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": null, "specialComments": []}', '2026-09-28 11:09:52.681844+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-faad-751e-9e6d-97ae379ee445', '01a0e7b4-faac-70bf-bde9-585c313b95b9', '1f59a96fe93b87c706be773e6c0fb97c7daf1aafb828ffa2f8e86a7607e7b833', 'Rin is Mina''s rival. Rin went to the lighthouse.', '{"name": null, "role": "char", "chatId": "0a81f9a2-b5b3-491a-b7a8-576ee19d9c77", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "b9086fbc-6eeb-4657-a0da-cb0a06777db5", "specialComments": []}', '2026-09-28 11:09:52.681844+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-faae-7b48-b13f-52c5caa759a5', '01a0e7b4-faae-78e9-bcb8-5aa9ad7bb366', 'ff0d62f5a8c4e15ae250ef23ea1747edf06d7bafb9d6c88ef36126fa950d0e27', 'Mina promised Takumi to return before the bell rings.', '{"name": null, "role": "char", "chatId": "c91a2a09-ad4e-49ba-a8b3-8b0602cef307", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "09d0130f-1641-4848-85e1-2d20445c08b2", "specialComments": []}', '2026-09-28 11:09:52.681844+00', 'accepted', NULL);
INSERT INTO public.source_revision VALUES ('01a0e7b4-faab-752d-bf21-4a731a2e8061', '01a0e7b4-faab-76bb-8763-7991b2c2836b', '2902fe7feb4c62040328852b11e91e83bc85440573002fa66499ba91f8e8d9f0', 'Mina is in the old chapel. Mina has the brass key.', '{"name": null, "role": "char", "chatId": "e0ab75cc-48fe-4a2d-bb7c-6720c4c753e8", "saying": null, "swipeId": null, "disabled": null, "isComment": null, "otherUser": null, "swipeCount": 0, "generationId": "f4232d50-a0c9-41d8-b632-0eb358382e07", "specialComments": []}', '2026-09-28 11:09:52.681844+00', 'accepted', NULL);


--
-- Data for Name: state_observation; Type: TABLE DATA; Schema: public; Owner: -
--



--
-- Data for Name: worldline_append; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_append VALUES (1, '01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b', '[{"op": "insert", "after": ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "418c25808b62d0d3533fdb7aa5b568f0bb93998a54cc210ca8b8ff12a3681e4e"], "member": ["6b8c231f-f49e-4e1c-bee1-97f36fe8c537", "654b3588a0b6c119ebe8ab25d4a4ef7d1ea5f9d3c67729e496ef216c129786ac"]}, {"op": "insert", "after": ["6b8c231f-f49e-4e1c-bee1-97f36fe8c537", "654b3588a0b6c119ebe8ab25d4a4ef7d1ea5f9d3c67729e496ef216c129786ac"], "member": ["09d0130f-1641-4848-85e1-2d20445c08b2", "c0f342afaa4ed5242523a6948a420d4dea59a59c4e163417dde013f7e6d1bf5b"]}, {"op": "insert", "after": ["09d0130f-1641-4848-85e1-2d20445c08b2", "c0f342afaa4ed5242523a6948a420d4dea59a59c4e163417dde013f7e6d1bf5b"], "member": ["54da3271-7f1a-42d2-b88e-fc79f2efdaad", "1ccdc6fc667881ef62284e0b894d817bc0cc1092c0cfc38c7a49cc0a195e2f79"]}, {"op": "insert", "after": ["54da3271-7f1a-42d2-b88e-fc79f2efdaad", "1ccdc6fc667881ef62284e0b894d817bc0cc1092c0cfc38c7a49cc0a195e2f79"], "member": ["f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", "298cd3a38869a060ee34def836275b751d1b81f977bea83fc0239e8f76f78311"]}]', '[{"new": ["6b8c231f-f49e-4e1c-bee1-97f36fe8c537", "654b3588a0b6c119ebe8ab25d4a4ef7d1ea5f9d3c67729e496ef216c129786ac"], "old": null, "kind": "append", "position": 4, "host_logical_id": "6b8c231f-f49e-4e1c-bee1-97f36fe8c537"}, {"new": ["09d0130f-1641-4848-85e1-2d20445c08b2", "c0f342afaa4ed5242523a6948a420d4dea59a59c4e163417dde013f7e6d1bf5b"], "old": null, "kind": "append", "position": 5, "host_logical_id": "09d0130f-1641-4848-85e1-2d20445c08b2"}, {"new": ["54da3271-7f1a-42d2-b88e-fc79f2efdaad", "1ccdc6fc667881ef62284e0b894d817bc0cc1092c0cfc38c7a49cc0a195e2f79"], "old": null, "kind": "append", "position": 6, "host_logical_id": "54da3271-7f1a-42d2-b88e-fc79f2efdaad"}, {"new": ["f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", "298cd3a38869a060ee34def836275b751d1b81f977bea83fc0239e8f76f78311"], "old": null, "kind": "append", "position": 7, "host_logical_id": "f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40"}]', '01a0e7b4-ede7-7133-8f5d-b8d89216c28b', '2026-09-28 11:09:49.408975+00');
INSERT INTO public.worldline_append VALUES (2, '01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b', '[{"op": "insert", "after": ["f51f5901-2d4e-4dd7-9f9a-4bc5e8464b40", "298cd3a38869a060ee34def836275b751d1b81f977bea83fc0239e8f76f78311"], "member": ["4da88bf2-78f7-4292-b2c6-86e376e71964", "9795c392926d5c63fe7a0588302d90be8ea002cdb5241b811f25eff30ef61f53"]}, {"op": "insert", "after": ["4da88bf2-78f7-4292-b2c6-86e376e71964", "9795c392926d5c63fe7a0588302d90be8ea002cdb5241b811f25eff30ef61f53"], "member": ["654c12f1-85cc-41cd-995c-1fe08fb40614", "b9ff7953631888fdb2f2ed0e606f5879c42fe5e47846f04c81748d833e6376f9"]}, {"op": "insert", "after": ["654c12f1-85cc-41cd-995c-1fe08fb40614", "b9ff7953631888fdb2f2ed0e606f5879c42fe5e47846f04c81748d833e6376f9"], "member": ["ccd66991-40e8-4ccb-b467-c1cfce62ecd0", "41a770b984cce35df3230443c5e3291d3e494542bfe6ee785af62f75913657eb"]}, {"op": "insert", "after": ["ccd66991-40e8-4ccb-b467-c1cfce62ecd0", "41a770b984cce35df3230443c5e3291d3e494542bfe6ee785af62f75913657eb"], "member": ["d1f36a29-0a86-4824-b4ed-76a9f0b26e54", "d48ed942168ba30643de9f89ad2dfce9512281de9093342ce44929f986d4681f"]}]', '[{"new": ["4da88bf2-78f7-4292-b2c6-86e376e71964", "9795c392926d5c63fe7a0588302d90be8ea002cdb5241b811f25eff30ef61f53"], "old": null, "kind": "append", "position": 8, "host_logical_id": "4da88bf2-78f7-4292-b2c6-86e376e71964"}, {"new": ["654c12f1-85cc-41cd-995c-1fe08fb40614", "b9ff7953631888fdb2f2ed0e606f5879c42fe5e47846f04c81748d833e6376f9"], "old": null, "kind": "append", "position": 9, "host_logical_id": "654c12f1-85cc-41cd-995c-1fe08fb40614"}, {"new": ["ccd66991-40e8-4ccb-b467-c1cfce62ecd0", "41a770b984cce35df3230443c5e3291d3e494542bfe6ee785af62f75913657eb"], "old": null, "kind": "append", "position": 10, "host_logical_id": "ccd66991-40e8-4ccb-b467-c1cfce62ecd0"}, {"new": ["d1f36a29-0a86-4824-b4ed-76a9f0b26e54", "d48ed942168ba30643de9f89ad2dfce9512281de9093342ce44929f986d4681f"], "old": null, "kind": "append", "position": 11, "host_logical_id": "d1f36a29-0a86-4824-b4ed-76a9f0b26e54"}]', '01a0e7b4-ee12-76b1-8b79-b58001632601', '2026-09-28 11:09:49.451528+00');
INSERT INTO public.worldline_append VALUES (3, '01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b', '[{"op": "insert", "after": ["d1f36a29-0a86-4824-b4ed-76a9f0b26e54", "d48ed942168ba30643de9f89ad2dfce9512281de9093342ce44929f986d4681f"], "member": ["24319f0f-127a-4149-b780-59083977f410", "3dfbe939779b60c1d27fd8ad972b2341ac783cfce4e05b8da7f2e9d967997e08"]}]', '[{"new": ["24319f0f-127a-4149-b780-59083977f410", "3dfbe939779b60c1d27fd8ad972b2341ac783cfce4e05b8da7f2e9d967997e08"], "old": null, "kind": "append", "position": 12, "host_logical_id": "24319f0f-127a-4149-b780-59083977f410"}]', '01a0e7b4-ee38-71c8-b303-aaa72294db4d', '2026-09-28 11:09:49.49214+00');
INSERT INTO public.worldline_append VALUES (4, '01a0e7b4-f44b-7030-a7d2-4d09831733f5', '[{"op": "insert", "after": ["3a262e2c-b2b2-4191-bc0c-c6539d90acd1", "709879d5affa7031ad359a76c0af8ec5d8fd96ff6cb1c6101bb74e8a7b8c890c"], "member": ["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "fffb37f0673f1a8170f446e52318ba8fbe3743356edb48a745f2da2653955d3f"]}]', '[{"new": ["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "fffb37f0673f1a8170f446e52318ba8fbe3743356edb48a745f2da2653955d3f"], "old": null, "kind": "append", "position": 15, "host_logical_id": "0a31a3d5-e10b-401d-8a4f-c36ce85da8a1"}]', '01a0e7b4-f474-795a-a5da-66e75a112481', '2026-09-28 11:09:51.088043+00');


--
-- Data for Name: worldline_commit; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b', 1, '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{}', 'import', 'e618d3bf2f7bc2e7597d88267821ade066f58f30e2dad7e074dee3dfbebb00d0', '{"ops": [{"op": "set", "members": [["7e43bffb-482f-4939-86ef-1fa8edda8b5f", "062e6a45e1dc047b3c9df81b154f32cae60873107b5d20e78c24a872e16c8674"], ["f4232d50-a0c9-41d8-b632-0eb358382e07", "497f7626ea4e8090434592902bb3833caece890715d78436a944f18a9ba9866a"], ["b22e7f6d-c0e2-499b-9c71-02e6a53bef53", "5b9325e3b5b11a47c2cf7934fabfb36191cb37641f0cc192f12c6d56c54f59a5"], ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "418c25808b62d0d3533fdb7aa5b568f0bb93998a54cc210ca8b8ff12a3681e4e"]]}], "changes": [{"new": ["7e43bffb-482f-4939-86ef-1fa8edda8b5f", "062e6a45e1dc047b3c9df81b154f32cae60873107b5d20e78c24a872e16c8674"], "old": null, "kind": "append", "position": 0, "host_logical_id": "7e43bffb-482f-4939-86ef-1fa8edda8b5f"}, {"new": ["f4232d50-a0c9-41d8-b632-0eb358382e07", "497f7626ea4e8090434592902bb3833caece890715d78436a944f18a9ba9866a"], "old": null, "kind": "append", "position": 1, "host_logical_id": "f4232d50-a0c9-41d8-b632-0eb358382e07"}, {"new": ["b22e7f6d-c0e2-499b-9c71-02e6a53bef53", "5b9325e3b5b11a47c2cf7934fabfb36191cb37641f0cc192f12c6d56c54f59a5"], "old": null, "kind": "append", "position": 2, "host_logical_id": "b22e7f6d-c0e2-499b-9c71-02e6a53bef53"}, {"new": ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "418c25808b62d0d3533fdb7aa5b568f0bb93998a54cc210ca8b8ff12a3681e4e"], "old": null, "kind": "append", "position": 3, "host_logical_id": "b9086fbc-6eeb-4657-a0da-cb0a06777db5"}]}', '2026-09-28 11:09:49.353327+00', '01a0e7b4-edb0-7f6e-9f41-e1e2533cbf6b');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b4-f44b-7030-a7d2-4d09831733f5', 2, '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{01a0e7b4-edb2-730f-b4eb-940ad7a4ec7b}', 'edit', '081927cf65aea8e42a48d07cbd4addb974d6e74633375c1ede36e1c7883629d6', '{"ops": [{"op": "replace", "to": ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "e34bca87e8c8690b498e47cb05a90fea0f5ed83b5f1fafd8fdb146462d115b02"], "from": ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "418c25808b62d0d3533fdb7aa5b568f0bb93998a54cc210ca8b8ff12a3681e4e"]}, {"op": "insert", "after": ["24319f0f-127a-4149-b780-59083977f410", "3dfbe939779b60c1d27fd8ad972b2341ac783cfce4e05b8da7f2e9d967997e08"], "member": ["61789a3c-a601-4f30-94f6-4c53ad38be8d", "2be3e9bbd99d7ce8af66bb2e7160bb43fa1fa8ee46ec7fd157c1e9fd33eba171"]}, {"op": "insert", "after": ["61789a3c-a601-4f30-94f6-4c53ad38be8d", "2be3e9bbd99d7ce8af66bb2e7160bb43fa1fa8ee46ec7fd157c1e9fd33eba171"], "member": ["3a262e2c-b2b2-4191-bc0c-c6539d90acd1", "709879d5affa7031ad359a76c0af8ec5d8fd96ff6cb1c6101bb74e8a7b8c890c"]}], "changes": [{"new": ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "e34bca87e8c8690b498e47cb05a90fea0f5ed83b5f1fafd8fdb146462d115b02"], "old": ["b9086fbc-6eeb-4657-a0da-cb0a06777db5", "418c25808b62d0d3533fdb7aa5b568f0bb93998a54cc210ca8b8ff12a3681e4e"], "kind": "edit", "position": 3, "host_logical_id": "b9086fbc-6eeb-4657-a0da-cb0a06777db5"}, {"new": ["61789a3c-a601-4f30-94f6-4c53ad38be8d", "2be3e9bbd99d7ce8af66bb2e7160bb43fa1fa8ee46ec7fd157c1e9fd33eba171"], "old": null, "kind": "append", "position": 13, "host_logical_id": "61789a3c-a601-4f30-94f6-4c53ad38be8d"}, {"new": ["3a262e2c-b2b2-4191-bc0c-c6539d90acd1", "709879d5affa7031ad359a76c0af8ec5d8fd96ff6cb1c6101bb74e8a7b8c890c"], "old": null, "kind": "append", "position": 14, "host_logical_id": "3a262e2c-b2b2-4191-bc0c-c6539d90acd1"}]}', '2026-09-28 11:09:51.045231+00', '01a0e7b4-f449-761c-ad65-c23d0dca3ded');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b4-f499-765d-89aa-c9bd070b972d', 3, '01a0e7b4-eda4-7f1f-b543-a0b42c101930', '{01a0e7b4-f44b-7030-a7d2-4d09831733f5}', 'reconciliation', 'c75a78e11ec82afa5ca6ea00c9cd26a0da9798b99eedf76ae80b62d5e45fc70b', '{"ops": [{"op": "replace", "to": ["4da88bf2-78f7-4292-b2c6-86e376e71964", "0b3d75dd50bc6adbdb57bbf0c251249bcf30362be0427240748e0a12b76f09c6"], "from": ["4da88bf2-78f7-4292-b2c6-86e376e71964", "9795c392926d5c63fe7a0588302d90be8ea002cdb5241b811f25eff30ef61f53"]}, {"op": "replace", "to": ["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "e2cbc0421b2dcc4c5f63be6e537df7d177484c4c4c1513eeb28c36136b970e77"], "from": ["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "fffb37f0673f1a8170f446e52318ba8fbe3743356edb48a745f2da2653955d3f"]}, {"op": "insert", "after": ["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "e2cbc0421b2dcc4c5f63be6e537df7d177484c4c4c1513eeb28c36136b970e77"], "member": ["ab2f10fe-0082-4c2d-8496-0e884fb2d35f", "0fcbee8bf86b1dcee91fe2d3b202fd900331756214e57ad0571e2e7773f9f202"]}], "changes": [{"new": ["4da88bf2-78f7-4292-b2c6-86e376e71964", "0b3d75dd50bc6adbdb57bbf0c251249bcf30362be0427240748e0a12b76f09c6"], "old": ["4da88bf2-78f7-4292-b2c6-86e376e71964", "9795c392926d5c63fe7a0588302d90be8ea002cdb5241b811f25eff30ef61f53"], "kind": "disable", "position": 8, "host_logical_id": "4da88bf2-78f7-4292-b2c6-86e376e71964"}, {"new": ["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "e2cbc0421b2dcc4c5f63be6e537df7d177484c4c4c1513eeb28c36136b970e77"], "old": ["0a31a3d5-e10b-401d-8a4f-c36ce85da8a1", "fffb37f0673f1a8170f446e52318ba8fbe3743356edb48a745f2da2653955d3f"], "kind": "swipe", "position": 15, "host_logical_id": "0a31a3d5-e10b-401d-8a4f-c36ce85da8a1"}, {"new": ["ab2f10fe-0082-4c2d-8496-0e884fb2d35f", "0fcbee8bf86b1dcee91fe2d3b202fd900331756214e57ad0571e2e7773f9f202"], "old": null, "kind": "append", "position": 16, "host_logical_id": "ab2f10fe-0082-4c2d-8496-0e884fb2d35f"}]}', '2026-09-28 11:09:51.12461+00', '01a0e7b4-f498-760b-9e04-e7d2a2f4b188');
INSERT INTO public.worldline_commit OVERRIDING SYSTEM VALUE VALUES ('01a0e7b4-fab1-72bf-93e1-9806dcd4893a', 4, '01a0e7b4-fa9d-71fb-9096-8df6ba220669', '{}', 'branch', '1bb75b60e16fe2581210a3b1d5d603c1f0625c37b389acbfb118ab37801d3205', '{"ops": [{"op": "set", "members": [["59f0d7f8-ed76-48c0-a601-49aaa09000cb", "c7f83db81d06934ffdf021857d2632e671d24cc1df6b1504730ce91262ecf4a6"], ["e0ab75cc-48fe-4a2d-bb7c-6720c4c753e8", "2902fe7feb4c62040328852b11e91e83bc85440573002fa66499ba91f8e8d9f0"], ["f14dab15-9ba7-4200-b101-14282be57d98", "a25a03b58d70062aab7cb6610bb00514f9de4a66ae1837dddf817cf3befc1778"], ["0a81f9a2-b5b3-491a-b7a8-576ee19d9c77", "1f59a96fe93b87c706be773e6c0fb97c7daf1aafb828ffa2f8e86a7607e7b833"], ["1e858747-f428-46c4-b2dd-f01a4f534ad6", "8294caf5be1f2fb7f4922e0de6e7ad4adca06bc04fe47f9896ae342fc890729f"], ["c91a2a09-ad4e-49ba-a8b3-8b0602cef307", "ff0d62f5a8c4e15ae250ef23ea1747edf06d7bafb9d6c88ef36126fa950d0e27"], ["24261722-e908-4c75-9092-0547ad1f3cd6", "4381be6dc747e55e6f1a5aaddab356884481378b62ccd1ac36396bae35500cbc"], ["4e359d4d-f2dc-45f3-8e80-d3c921af8f71", "aed37c6d8df03f47fbd923e4aaa9a9949680d5e303b20ecb2edee747b536e28d"]]}], "changes": [{"new": ["59f0d7f8-ed76-48c0-a601-49aaa09000cb", "c7f83db81d06934ffdf021857d2632e671d24cc1df6b1504730ce91262ecf4a6"], "old": null, "kind": "append", "position": 0, "host_logical_id": "59f0d7f8-ed76-48c0-a601-49aaa09000cb"}, {"new": ["e0ab75cc-48fe-4a2d-bb7c-6720c4c753e8", "2902fe7feb4c62040328852b11e91e83bc85440573002fa66499ba91f8e8d9f0"], "old": null, "kind": "append", "position": 1, "host_logical_id": "e0ab75cc-48fe-4a2d-bb7c-6720c4c753e8"}, {"new": ["f14dab15-9ba7-4200-b101-14282be57d98", "a25a03b58d70062aab7cb6610bb00514f9de4a66ae1837dddf817cf3befc1778"], "old": null, "kind": "append", "position": 2, "host_logical_id": "f14dab15-9ba7-4200-b101-14282be57d98"}, {"new": ["0a81f9a2-b5b3-491a-b7a8-576ee19d9c77", "1f59a96fe93b87c706be773e6c0fb97c7daf1aafb828ffa2f8e86a7607e7b833"], "old": null, "kind": "append", "position": 3, "host_logical_id": "0a81f9a2-b5b3-491a-b7a8-576ee19d9c77"}, {"new": ["1e858747-f428-46c4-b2dd-f01a4f534ad6", "8294caf5be1f2fb7f4922e0de6e7ad4adca06bc04fe47f9896ae342fc890729f"], "old": null, "kind": "append", "position": 4, "host_logical_id": "1e858747-f428-46c4-b2dd-f01a4f534ad6"}, {"new": ["c91a2a09-ad4e-49ba-a8b3-8b0602cef307", "ff0d62f5a8c4e15ae250ef23ea1747edf06d7bafb9d6c88ef36126fa950d0e27"], "old": null, "kind": "append", "position": 5, "host_logical_id": "c91a2a09-ad4e-49ba-a8b3-8b0602cef307"}, {"new": ["24261722-e908-4c75-9092-0547ad1f3cd6", "4381be6dc747e55e6f1a5aaddab356884481378b62ccd1ac36396bae35500cbc"], "old": null, "kind": "append", "position": 6, "host_logical_id": "24261722-e908-4c75-9092-0547ad1f3cd6"}, {"new": ["4e359d4d-f2dc-45f3-8e80-d3c921af8f71", "aed37c6d8df03f47fbd923e4aaa9a9949680d5e303b20ecb2edee747b536e28d"], "old": null, "kind": "append", "position": 7, "host_logical_id": "4e359d4d-f2dc-45f3-8e80-d3c921af8f71"}]}', '2026-09-28 11:09:52.681844+00', '01a0e7b4-fab1-7d22-ab4c-d5957b53e552');


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


