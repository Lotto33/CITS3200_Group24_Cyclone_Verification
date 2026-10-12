#!/usr/bin/env bash
# Resolve the formatting-only conflicts left by `git merge origin/main`.
#
# Run it from the repo root while a merge is stopped on conflicts. For every
# conflicted frontend file it formats the common ancestor, your version and
# main's version with the project's Biome config, then three-way merges those.
# Conflicts that remain are real: your edit and someone else's touch the same code.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
BIOME="frontend/node_modules/.bin/biome"
[ -x "$BIOME" ] || { echo "Run 'cd frontend && npm ci' first."; exit 1; }
git rev-parse -q --verify MERGE_HEAD >/dev/null || { echo "No merge in progress. Run 'git merge origin/main' first."; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fmt() { "$BIOME" format --stdin-file-path="$1" 2>/dev/null; }

remaining=()
rebuild=0
while IFS= read -r f; do
	case "$f" in
	frontend/package-lock.json | frontend/package.json)
		git checkout --theirs -- "$f" && git add "$f"
		echo "took main's version: $f"
		;;
	frontend/assets/verification.js)
		# Compiled from frontend/src/verification.ts: never merge it by hand.
		git checkout --theirs -- "$f"
		rebuild=1
		echo "will rebuild: $f"
		;;
	frontend/assets/*.js | frontend/assets/*.css | frontend/*.html | frontend/src/*.ts)
		if ! git show ":1:$f" >"$tmp/base" 2>/dev/null; then
			remaining+=("$f")
			echo "no common ancestor, resolve by hand: $f"
			continue
		fi
		git show ":2:$f" >"$tmp/ours"
		git show ":3:$f" >"$tmp/theirs"
		fmt "$f" <"$tmp/base" >"$tmp/base.f"
		fmt "$f" <"$tmp/ours" >"$tmp/ours.f"
		if git merge-file -L "yours" -L "base" -L "main" -p "$tmp/ours.f" "$tmp/base.f" "$tmp/theirs" >"$tmp/merged"; then
			cp "$tmp/merged" "$f" && git add "$f"
			echo "merged cleanly: $f"
		else
			cp "$tmp/merged" "$f"
			remaining+=("$f")
			echo "REAL conflicts left: $f ($(grep -c '^<<<<<<<' "$f") hunks)"
		fi
		;;
	*)
		remaining+=("$f")
		echo "not a frontend file, resolve by hand: $f"
		;;
	esac
done < <(git diff --name-only --diff-filter=U)

if [ "$rebuild" = 1 ]; then
	if printf '%s\n' "${remaining[@]:-}" | grep -qx 'frontend/src/verification.ts'; then
		echo "Resolve frontend/src/verification.ts, then: cd frontend && npm run build && git add frontend/assets/verification.js"
	else
		(cd frontend && npm run build >/dev/null) && git add frontend/assets/verification.js
		echo "rebuilt frontend/assets/verification.js from verification.ts"
	fi
fi

if [ "${#remaining[@]}" -eq 0 ]; then
	echo "All conflicts resolved. Run 'cd frontend && npm run format && npm run lint', then 'git commit'."
else
	echo "Still to resolve by hand: ${remaining[*]}"
fi
