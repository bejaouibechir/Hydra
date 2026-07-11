#!/usr/bin/env bash
# backup_studio.sh — Sauvegarde horodatée des fichiers Studio critiques
# Usage: bash studio/scripts/backup_studio.sh

STAMP=$(date +%Y%m%d_%H%M%S)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/src/_backups/$STAMP"
mkdir -p "$DEST"

FILES=(
  src/pages/workflows/WorkflowEditor.tsx
  src/pages/projects/Projects.tsx
  src/pages/projects/ProjectDetail.tsx
  src/pages/Settings.tsx
  src/pages/Help.tsx
  src/pages/Insights.tsx
  src/pages/Templates.tsx
  src/pages/Overview.tsx
  src/components/canvas/NodeConfigDialog.tsx
  src/components/canvas/YamlCodePanel.tsx
  src/components/canvas/TerminalPanel.tsx
  src/components/canvas/PropertiesPanel.tsx
  src/components/canvas/NodePalette.tsx
  src/components/canvas/CanvasToolbox.tsx
  src/components/canvas/JobCreatorWizard.tsx
  src/components/layout/AppLayout.tsx
  src/components/layout/Sidebar.tsx
  src/components/layout/Topbar.tsx
  src/lib/api.ts
  src/lib/workflowSerializer.ts
  src/lib/hdrSerializer.ts
  src/App.tsx
)

COUNT=0
for f in "${FILES[@]}"; do
  SRC="$ROOT/$f"
  if [ -f "$SRC" ]; then
    cp "$SRC" "$DEST/$(basename $f)"
    COUNT=$((COUNT+1))
  fi
done
echo "Backup $STAMP — $COUNT fichiers dans studio/src/_backups/$STAMP/"
