#!/bin/sh
# DB(pg_dump)와 업로드·출력 파일을 한 폴더에 백업한다. 사용: infra/backup.sh [백업폴더]
set -e
DEST="${1:-./backups}/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
COMPOSE="docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod"
$COMPOSE exec -T db pg_dump -U tnp -d tnp_platform -Fc > "$DEST/db.dump"
$COMPOSE cp api:/data "$DEST/files"
echo "백업 완료: $DEST"
