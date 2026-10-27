#!/bin/sh
# 백업에서 복원한다. 현재 DB를 먼저 백업한 뒤 덮어쓴다. 사용: infra/restore.sh <백업폴더> --yes
set -e
SRC="$1"
[ -f "$SRC/db.dump" ] || { echo "백업 폴더에 db.dump 가 없습니다"; exit 1; }
[ "$2" = "--yes" ] || { echo "복원하면 현재 데이터가 바뀝니다. 확인했다면 --yes 를 붙여 다시 실행하세요"; exit 1; }
COMPOSE="docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod"
sh "$(dirname "$0")/backup.sh" ./backups/before-restore
$COMPOSE exec -T db pg_restore -U tnp -d tnp_platform --clean --if-exists < "$SRC/db.dump"
[ -d "$SRC/files" ] && $COMPOSE cp "$SRC/files/." api:/data
echo "복원 완료: $SRC"
