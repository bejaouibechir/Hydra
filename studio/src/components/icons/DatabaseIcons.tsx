/**
 * DatabaseIcons — logos officiels MySQL et PostgreSQL (paquet simple-icons,
 * licence CC0), rendus en couleur courante pour suivre la palette du Studio.
 * Microsoft ne distribue pas le logo SQL Server dans simple-icons : le nœud
 * SQL Server garde l'icône Database de Lucide.
 */
import React from 'react'
import { siMysql, siPostgresql } from 'simple-icons'

interface IconProps {
  size?: number
  style?: React.CSSProperties
  className?: string
}

function brandIcon(icon: { title: string; path: string }) {
  return function BrandIcon({ size = 24, style, className }: IconProps) {
    return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" role="img"
        xmlns="http://www.w3.org/2000/svg" style={style} className={className}>
        <title>{icon.title}</title>
        <path d={icon.path} />
      </svg>
    )
  }
}

export const MySQLIcon = brandIcon(siMysql)
export const PostgreSQLIcon = brandIcon(siPostgresql)
