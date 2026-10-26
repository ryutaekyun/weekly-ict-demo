#!/usr/bin/env bash
# DOCX→PDF 변환(LibreOffice)과 한글 렌더링에 필요한 도구를 CI(Ubuntu)에 설치한다.
# 한글 글꼴은 SIL OFL 라이선스의 Noto CJK를 apt로 설치하며, 저장소에는 글꼴 파일을 포함하지 않는다.
# 보고서 템플릿의 '맑은 고딕'은 Ubuntu에 없으므로 fontconfig 별칭으로 Noto Sans CJK KR에 매핑한다.
set -euo pipefail
sudo apt-get update -qq
sudo apt-get install -y -qq --no-install-recommends libreoffice-writer libreoffice-impress fonts-noto-cjk
mkdir -p "$HOME/.config/fontconfig"
cat > "$HOME/.config/fontconfig/fonts.conf" <<'XMLEOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <alias binding="same"><family>맑은 고딕</family><prefer><family>Noto Sans CJK KR</family></prefer></alias>
  <alias binding="same"><family>Malgun Gothic</family><prefer><family>Noto Sans CJK KR</family></prefer></alias>
</fontconfig>
XMLEOF
fc-cache -f >/dev/null
soffice --version
fc-match "맑은 고딕"
