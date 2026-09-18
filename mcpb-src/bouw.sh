#!/bin/zsh
# Bouw de MCPB-bundel (dist/be-biodiversiteit.mcpb) voor Claude Desktop.
# Vereist: uv, node/npx. De bundel en de wheels zijn build-artefacten en staan niet in git.
set -euo pipefail
setopt null_glob
HIER="${0:A:h}"
REPO="${HIER:h}"

cd "$REPO"
rm -f dist/gbif_mcp-*.whl dist/gbif_mcp-*.tar.gz
uv build
rm -f "$HIER"/wheels/gbif_mcp-*.whl
mkdir -p "$HIER/wheels"
cp dist/gbif_mcp-*-py3-none-any.whl "$HIER/wheels/"
cp LICENSE "$HIER/LICENSE"  # EUPL-1.2 ook zichtbaar in de bundel zelf
npx --yes @anthropic-ai/mcpb validate "$HIER/manifest.json"
npx --yes @anthropic-ai/mcpb pack "$HIER" "$REPO/dist/be-biodiversiteit.mcpb"
echo
echo "Klaar: $REPO/dist/be-biodiversiteit.mcpb"
echo "Installeren: Claude Desktop → Instellingen → Extensies → 'Geavanceerde instellingen' → Extensie installeren…"
