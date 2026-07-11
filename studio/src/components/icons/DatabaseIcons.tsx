/**
 * DatabaseIcons — icônes custom MySQL et PostgreSQL dans le style Lucide
 * (stroke="currentColor", strokeWidth=2, fill="none", round caps/joins)
 */
import React from 'react'

interface IconProps {
  size?: number
  style?: React.CSSProperties
  className?: string
}

/** Dauphin MySQL simplifié — silhouette reconnaissable en stroke Lucide */
export function MySQLIcon({ size = 24, style, className }: IconProps) {
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      xmlns="http://www.w3.org/2000/svg"
      style={style}
      className={className}
    >
      {/* Corps du dauphin */}
      <path d="M4 14C4 10 7 6.5 13 6C16.5 6.5 20 9.5 20 13.5C20 17.5 16.5 20 12 20C8 20 4.5 17 4 14Z"/>
      {/* Nageoire dorsale */}
      <path d="M10.5 6.5L9.5 2.5L14.5 6"/>
      {/* Queue — deux lobes */}
      <path d="M20 11L23 8.5"/>
      <path d="M20 15.5L23 18"/>
      {/* Œil */}
      <circle cx="8.5" cy="13" r="0.75" fill="currentColor" stroke="none"/>
    </svg>
  )
}

/** Tête d'éléphant PostgreSQL simplifiée — silhouette reconnaissable en stroke Lucide */
export function PostgreSQLIcon({ size = 24, style, className }: IconProps) {
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      xmlns="http://www.w3.org/2000/svg"
      style={style}
      className={className}
    >
      {/* Tête (cercle principal) */}
      <circle cx="13" cy="10" r="6.5"/>
      {/* Oreille gauche */}
      <path d="M6.5 7C5 6 3.5 6.5 3 8C2.5 9.5 3.5 11.5 6 11"/>
      {/* Trompe */}
      <path d="M13.5 16.5C14.5 19 14 21 12 22"/>
      {/* Défense */}
      <path d="M10 16L8.5 19"/>
      {/* Œil */}
      <circle cx="11" cy="9" r="1" fill="currentColor" stroke="none"/>
    </svg>
  )
}
