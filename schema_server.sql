--
-- PostgreSQL database dump
--

\restrict xVOwDmZMRDHensQDo1GuoWXeH2O8G7vgSkeiEL8BR0DXKgFYru7aqbaTATzbLDZ

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg13+1)

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

ALTER TABLE IF EXISTS ONLY public.user_identities DROP CONSTRAINT IF EXISTS user_identities_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.teachers DROP CONSTRAINT IF EXISTS teachers_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.students DROP CONSTRAINT IF EXISTS students_user_id_fkey;
ALTER TABLE IF EXISTS ONLY public.events DROP CONSTRAINT IF EXISTS events_teacher_id_fkey;
ALTER TABLE IF EXISTS ONLY public.events DROP CONSTRAINT IF EXISTS events_student_id_fkey;
ALTER TABLE IF EXISTS ONLY public.events DROP CONSTRAINT IF EXISTS events_created_by_fkey;
ALTER TABLE IF EXISTS ONLY public.events DROP CONSTRAINT IF EXISTS events_court_id_fkey;
DROP TRIGGER IF EXISTS trg_users_updated_at ON public.users;
DROP TRIGGER IF EXISTS trg_teachers_updated_at ON public.teachers;
DROP TRIGGER IF EXISTS trg_students_updated_at ON public.students;
DROP TRIGGER IF EXISTS trg_events_updated_at ON public.events;
DROP TRIGGER IF EXISTS trg_courts_updated_at ON public.courts;
DROP INDEX IF EXISTS public.uq_google_email;
DROP INDEX IF EXISTS public.idx_events_teacher_start;
DROP INDEX IF EXISTS public.idx_events_start_end;
DROP INDEX IF EXISTS public.idx_events_court_start;
DROP INDEX IF EXISTS public.idx_events_confirmed_teacher_start;
DROP INDEX IF EXISTS public.idx_events_confirmed_start_end;
DROP INDEX IF EXISTS public.idx_events_confirmed_court_start;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_pkey;
ALTER TABLE IF EXISTS ONLY public.users DROP CONSTRAINT IF EXISTS users_email_key;
ALTER TABLE IF EXISTS ONLY public.user_identities DROP CONSTRAINT IF EXISTS user_identities_pkey;
ALTER TABLE IF EXISTS ONLY public.user_identities DROP CONSTRAINT IF EXISTS uq_provider_sub;
ALTER TABLE IF EXISTS ONLY public.teachers DROP CONSTRAINT IF EXISTS teachers_user_id_key;
ALTER TABLE IF EXISTS ONLY public.teachers DROP CONSTRAINT IF EXISTS teachers_pkey;
ALTER TABLE IF EXISTS ONLY public.teachers DROP CONSTRAINT IF EXISTS teachers_email_key;
ALTER TABLE IF EXISTS ONLY public.students DROP CONSTRAINT IF EXISTS students_user_id_key;
ALTER TABLE IF EXISTS ONLY public.students DROP CONSTRAINT IF EXISTS students_pkey;
ALTER TABLE IF EXISTS ONLY public.students DROP CONSTRAINT IF EXISTS students_email_key;
ALTER TABLE IF EXISTS ONLY public.events DROP CONSTRAINT IF EXISTS ex_events_no_overlap_teacher;
ALTER TABLE IF EXISTS ONLY public.events DROP CONSTRAINT IF EXISTS ex_events_no_overlap_court;
ALTER TABLE IF EXISTS ONLY public.events DROP CONSTRAINT IF EXISTS events_pkey;
ALTER TABLE IF EXISTS ONLY public.courts DROP CONSTRAINT IF EXISTS courts_pkey;
ALTER TABLE IF EXISTS ONLY public.courts DROP CONSTRAINT IF EXISTS courts_name_key;
DROP VIEW IF EXISTS public.vw_agenda;
DROP TABLE IF EXISTS public.users;
DROP TABLE IF EXISTS public.user_identities;
DROP TABLE IF EXISTS public.teachers;
DROP TABLE IF EXISTS public.students;
DROP TABLE IF EXISTS public.events;
DROP TABLE IF EXISTS public.courts;
DROP FUNCTION IF EXISTS public.set_updated_at();
DROP FUNCTION IF EXISTS public.fn_quadras_disponiveis(p_from timestamp with time zone, p_to timestamp with time zone);
DROP FUNCTION IF EXISTS public.fn_professores_disponiveis(p_from timestamp with time zone, p_to timestamp with time zone);
DROP FUNCTION IF EXISTS public.fn_agenda_periodo(p_from timestamp with time zone, p_to timestamp with time zone, p_status text, p_kind text, p_court uuid, p_teacher uuid);
DROP EXTENSION IF EXISTS pgcrypto;
DROP EXTENSION IF EXISTS citext;
DROP EXTENSION IF EXISTS btree_gist;
--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: fn_agenda_periodo(timestamp with time zone, timestamp with time zone, text, text, uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_agenda_periodo(p_from timestamp with time zone, p_to timestamp with time zone, p_status text DEFAULT NULL::text, p_kind text DEFAULT NULL::text, p_court uuid DEFAULT NULL::uuid, p_teacher uuid DEFAULT NULL::uuid) RETURNS TABLE(event_id uuid, kind text, status text, start_at timestamp with time zone, end_at timestamp with time zone, notes text, court_id uuid, court_name text, teacher_id uuid, teacher_name text, student_id uuid, student_name text, created_by_user_id uuid, created_by_email public.citext, created_at timestamp with time zone, updated_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
  SELECT
    a.event_id, a.kind, a.status, a.start_at, a.end_at, a.notes,
    a.court_id, a.court_name,
    a.teacher_id, a.teacher_name,
    a.student_id, a.student_name,
    a.created_by_user_id, a.created_by_email,
    a.created_at, a.updated_at
  FROM vw_agenda a
  WHERE a.start_at < p_to
    AND a.end_at   > p_from
    AND (p_status  IS NULL OR a.status = p_status)
    AND (p_kind    IS NULL OR a.kind   = p_kind)
    AND (p_court   IS NULL OR a.court_id = p_court)
    AND (p_teacher IS NULL OR a.teacher_id = p_teacher)
  ORDER BY a.start_at, a.court_name;
$$;


--
-- Name: fn_professores_disponiveis(timestamp with time zone, timestamp with time zone); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_professores_disponiveis(p_from timestamp with time zone, p_to timestamp with time zone) RETURNS TABLE(teacher_id uuid, teacher_name text)
    LANGUAGE sql STABLE
    AS $$
  SELECT t.id, t.full_name
  FROM teachers t
  WHERE t.is_active = true
    AND NOT EXISTS (
      SELECT 1
      FROM events e
      WHERE e.teacher_id = t.id
        AND e.status = 'confirmado'
        AND e.start_at < p_to
        AND e.end_at   > p_from
    )
  ORDER BY t.full_name;
$$;


--
-- Name: fn_quadras_disponiveis(timestamp with time zone, timestamp with time zone); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.fn_quadras_disponiveis(p_from timestamp with time zone, p_to timestamp with time zone) RETURNS TABLE(court_id uuid, court_name text)
    LANGUAGE sql STABLE
    AS $$
  SELECT c.id, c.name
  FROM courts c
  WHERE c.is_active = true
    AND NOT EXISTS (
      SELECT 1
      FROM events e
      WHERE e.court_id = c.id
        AND e.status = 'confirmado'
        AND e.start_at < p_to
        AND e.end_at   > p_from
    )
  ORDER BY c.name;
$$;


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: courts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.courts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    court_id uuid NOT NULL,
    teacher_id uuid,
    student_id uuid,
    created_by uuid,
    kind text NOT NULL,
    status text DEFAULT 'confirmado'::text NOT NULL,
    start_at timestamp with time zone NOT NULL,
    end_at timestamp with time zone NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_events_time CHECK ((end_at > start_at)),
    CONSTRAINT chk_teacher_required CHECK (((kind <> ALL (ARRAY['aula_regular'::text, 'primeira_aula'::text])) OR (teacher_id IS NOT NULL))),
    CONSTRAINT events_kind_check CHECK ((kind = ANY (ARRAY['aula_regular'::text, 'primeira_aula'::text, 'locacao'::text, 'bloqueio'::text]))),
    CONSTRAINT events_status_check CHECK ((status = ANY (ARRAY['confirmado'::text, 'cancelado'::text])))
);


--
-- Name: students; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.students (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    full_name text NOT NULL,
    email public.citext,
    phone text,
    notes text,
    profession text,
    instagram_handle text,
    share_profession boolean DEFAULT false NOT NULL,
    share_instagram boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_instagram_handle CHECK (((instagram_handle IS NULL) OR (instagram_handle ~ '^[A-Za-z0-9._]{1,30}$'::text)))
);


--
-- Name: teachers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teachers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid,
    full_name text NOT NULL,
    email public.citext,
    phone text,
    notes text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: user_identities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_identities (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    provider text NOT NULL,
    provider_sub text NOT NULL,
    provider_email public.citext,
    email_verified boolean,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT user_identities_provider_check CHECK ((provider = 'google'::text))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email public.citext NOT NULL,
    password_hash text NOT NULL,
    full_name text,
    role text DEFAULT 'admin'::text NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT users_role_check CHECK ((role = ANY (ARRAY['admin'::text, 'coach'::text, 'staff'::text])))
);


--
-- Name: vw_agenda; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.vw_agenda AS
 SELECT e.id AS event_id,
    e.kind,
    e.status,
    e.start_at,
    e.end_at,
    e.notes,
    c.id AS court_id,
    c.name AS court_name,
    t.id AS teacher_id,
    t.full_name AS teacher_name,
    s.id AS student_id,
    s.full_name AS student_name,
    u.id AS created_by_user_id,
    u.email AS created_by_email,
    e.created_at,
    e.updated_at
   FROM ((((public.events e
     JOIN public.courts c ON ((c.id = e.court_id)))
     LEFT JOIN public.teachers t ON ((t.id = e.teacher_id)))
     LEFT JOIN public.students s ON ((s.id = e.student_id)))
     LEFT JOIN public.users u ON ((u.id = e.created_by)));


--
-- Name: courts courts_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courts
    ADD CONSTRAINT courts_name_key UNIQUE (name);


--
-- Name: courts courts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.courts
    ADD CONSTRAINT courts_pkey PRIMARY KEY (id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: events ex_events_no_overlap_court; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT ex_events_no_overlap_court EXCLUDE USING gist (court_id WITH =, tstzrange(start_at, end_at, '[)'::text) WITH &&) WHERE ((status = 'confirmado'::text));


--
-- Name: events ex_events_no_overlap_teacher; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT ex_events_no_overlap_teacher EXCLUDE USING gist (teacher_id WITH =, tstzrange(start_at, end_at, '[)'::text) WITH &&) WHERE (((status = 'confirmado'::text) AND (teacher_id IS NOT NULL)));


--
-- Name: students students_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_email_key UNIQUE (email);


--
-- Name: students students_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_pkey PRIMARY KEY (id);


--
-- Name: students students_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_user_id_key UNIQUE (user_id);


--
-- Name: teachers teachers_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teachers
    ADD CONSTRAINT teachers_email_key UNIQUE (email);


--
-- Name: teachers teachers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teachers
    ADD CONSTRAINT teachers_pkey PRIMARY KEY (id);


--
-- Name: teachers teachers_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teachers
    ADD CONSTRAINT teachers_user_id_key UNIQUE (user_id);


--
-- Name: user_identities uq_provider_sub; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_identities
    ADD CONSTRAINT uq_provider_sub UNIQUE (provider, provider_sub);


--
-- Name: user_identities user_identities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_identities
    ADD CONSTRAINT user_identities_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_events_confirmed_court_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_confirmed_court_start ON public.events USING btree (court_id, start_at) WHERE (status = 'confirmado'::text);


--
-- Name: idx_events_confirmed_start_end; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_confirmed_start_end ON public.events USING btree (start_at, end_at) WHERE (status = 'confirmado'::text);


--
-- Name: idx_events_confirmed_teacher_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_confirmed_teacher_start ON public.events USING btree (teacher_id, start_at) WHERE ((status = 'confirmado'::text) AND (teacher_id IS NOT NULL));


--
-- Name: idx_events_court_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_court_start ON public.events USING btree (court_id, start_at);


--
-- Name: idx_events_start_end; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_start_end ON public.events USING btree (start_at, end_at);


--
-- Name: idx_events_teacher_start; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_events_teacher_start ON public.events USING btree (teacher_id, start_at);


--
-- Name: uq_google_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_google_email ON public.user_identities USING btree (provider, provider_email) WHERE (provider_email IS NOT NULL);


--
-- Name: courts trg_courts_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_courts_updated_at BEFORE UPDATE ON public.courts FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: events trg_events_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_events_updated_at BEFORE UPDATE ON public.events FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: students trg_students_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_students_updated_at BEFORE UPDATE ON public.students FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: teachers trg_teachers_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_teachers_updated_at BEFORE UPDATE ON public.teachers FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: users trg_users_updated_at; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: events events_court_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_court_id_fkey FOREIGN KEY (court_id) REFERENCES public.courts(id) ON DELETE RESTRICT;


--
-- Name: events events_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: events events_student_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_student_id_fkey FOREIGN KEY (student_id) REFERENCES public.students(id) ON DELETE SET NULL;


--
-- Name: events events_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.teachers(id) ON DELETE SET NULL;


--
-- Name: students students_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.students
    ADD CONSTRAINT students_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: teachers teachers_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teachers
    ADD CONSTRAINT teachers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: user_identities user_identities_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_identities
    ADD CONSTRAINT user_identities_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict xVOwDmZMRDHensQDo1GuoWXeH2O8G7vgSkeiEL8BR0DXKgFYru7aqbaTATzbLDZ

