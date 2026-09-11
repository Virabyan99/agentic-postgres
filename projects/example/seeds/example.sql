-- The example project's seed: two notes and one embedding, all the
-- development subject's.
--
-- Applied by `bin/apg.sh dev seed --project project.example.yaml example` as
-- the migration user, inside ONE transaction, with `app.user_id` already set
-- to the development subject before this text runs (ADR 0203 §7). Without that
-- identity every write below raises `AP401: no request identity for this
-- transaction` -- the tables' policies read `app.user_id`, and the seed's rows
-- are the subject's precisely because the command asserts it.
--
-- **This seed creates nothing.** No table, no view, no function, no grant: all
-- of that belongs in this project's migration set, where it is frozen under a
-- lock, ordered, and applied by a deploy. `dev_environment.lint_seed` refuses a
-- seed that creates anything, because such a seed would be an unversioned
-- migration running on one developer's cluster and on no deployment.
--
-- The writes go through the project's own published API -- `api.create_note`
-- and `api.set_note_embedding` -- rather than through `INSERT`. A seed that
-- inserted directly would be writing rows no caller could have produced, and
-- the cluster it left behind would not be one a developer could reason about.
SET LOCAL ROLE {{object_owner}};

SELECT api.create_note('Seeded note one', 'The first seeded note.');
SELECT api.create_note('Seeded note two', 'The second seeded note.');

-- 768 dimensions, which is what `app.note_embeddings` declares. Rig 22c
-- measured both forms the pinned pgvector accepts: this `real[]` cast and a
-- string literal of 768 floats. This one is a line a developer can edit.
SELECT api.set_note_embedding(
  (SELECT id FROM api.notes WHERE title = 'Seeded note one'),
  array_fill(0.1::real, ARRAY[768])::extensions.vector
);

RESET ROLE;
