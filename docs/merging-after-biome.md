# Merging a branch into a linted `main`

For developers whose branch was cut **before** the Biome formatting landed on
`main`.

## Why it conflicts

The formatting commit rewrote almost every line in `frontend/assets/`, the `frontend/*.html`
pages and `frontend/src/`. For git, every line you touched, and every line you
didn't, looks changed on both sides. Don't fix that by hand, and don't run the
formatter on your branch first: that makes it worse (it turns every line into a
change on your side too, so any edit on `main` collides with it).

`scripts/merge-main-formatted.sh` fixes this by formatting all three versions of
each conflicted file (common ancestor, yours, main's) with the project's Biome
config, then three-way merging those. Only real overlaps are left for you.

## Before you start

- Node 20 or newer.
- Your work is committed.
- The steps use `my-branch` as your branch name.

## Steps

1. **Update and switch to your branch.**

   ```bash
   git fetch origin
   git checkout my-branch
   ```

2. **Bring in main's lint config and commit it.** This makes the config files
   identical on both sides so they can't conflict.

   ```bash
   git checkout origin/main -- biome.json .gitattributes frontend/package.json frontend/package-lock.json
   git commit -m "chore: take lint config from main"
   ```

   If you changed `frontend/package.json` for your own reasons, re-add that
   change after the merge.

3. **Install the tooling.**

   ```bash
   cd frontend && npm ci && cd ..
   ```

4. **Merge main.** Conflicts are expected.

   ```bash
   git merge origin/main
   ```

5. **Run the helper script.**

   ```bash
   bash scripts/merge-main-formatted.sh
   ```

   It prints one line per conflicted file, for example
   `merged cleanly: visualize.html` or
   `REAL conflicts left: frontend/assets/visualize.js (1 hunks)`. It also takes main's
   `package.json` / lockfile and rebuilds `frontend/assets/verification.js` for you.

6. **Resolve what's left.** Only genuine overlaps remain: your edit and someone
   else's touch the same code. Search for `<<<<<<< yours`, then pick or combine
   the two sides (`=======` separates them; `>>>>>>> main` ends the hunk). In
   VS Code use "Resolve in Merge Editor". Then `git add` the file.

7. **Format, lint and rebuild.**

   ```bash
   cd frontend
   npm run format      # fixes formatting and safe lint issues
   npm run lint        # must finish with 0 errors; warnings are fine
   npm run build       # always run if you changed frontend/src/verification.ts
   ```

   `frontend/assets/verification.js` can merge without a conflict yet be stale: it only
   contains your `verification.ts` change after `npm run build`. CI's "compiled
   assets are up to date" check fails if you skip this.

8. **Commit and push.**

   ```bash
   git add -A
   git commit --no-edit
   git push
   ```

   Check that the `frontend-lint` job passes on your PR.

## If the script fails on a file

Take main's version and re-apply your edit on top:

```bash
git checkout --theirs path/to/file
# re-make your change, then:
git add path/to/file
```

## Don't

- Hand-edit `frontend/assets/verification.js`. It is compiled: resolve
  `frontend/src/verification.ts`, then run `npm run build`.
- Run `npm run format` before merging.
- Rebase. It replays every commit and repeats the conflicts at each one.
